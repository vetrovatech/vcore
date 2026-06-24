/**
 * Bulk Import for B2B Line Items — Standard Template flow.
 *
 * Workflow:
 *   1. BD downloads `vcore-quote-template.xlsx` (generated client-side).
 *   2. BD fills rows in Sheet 1 ("Items"). Sheet 2 has instructions.
 *   3. BD uploads filled file. Headers must match the template exactly;
 *      otherwise we refuse with a clear pointer back to the template.
 *   4. Rows are previewed with green/amber validation badges, BD picks
 *      target group + default rate, then commits via the existing
 *      addSubItemWithData() / addGroup() helpers.
 *
 * No DB changes, no server endpoint — pure client-side via SheetJS.
 * Touches the standard B2B form only; bathqube quotation is untouched.
 */

(function () {
    'use strict';

    // ─── template definition ─────────────────────────────────────────────────
    // Order here = order in the template. Change with care: existing user
    // template files will fail header validation if columns are reordered or
    // renamed. Headers are matched case-insensitively, but text must match.

    const TEMPLATE_HEADERS = [
        'Particular',
        'Actual W (MM)',
        'Actual H (MM)',
        'Unit (MM/sqft/pcs)',
        'Chargeable W (MM)',
        'Chargeable H (MM)',
        'Qty',
        'Rate (Rs/SqMt)',
        'Holes',
        'Cutouts',
    ];

    // Maps each template column position to the data-field key used by
    // addSubItemWithData(). Order MUST match TEMPLATE_HEADERS.
    const COL_TO_FIELD = [
        'particular',
        'actual_width',
        'actual_height',
        'unit',
        'chargeable_width',
        'chargeable_height',
        'quantity',
        'rate_sqper',
        'hole',
        'cutout',
    ];

    const SAMPLE_ROW = ['N-G-B1 T-BLOCK', 990, 2400, 'MM', 1020, 2430, 2, 1320, 0, 0];

    const INSTRUCTIONS = [
        ['VCore Bulk Quote Import — Instructions'],
        [''],
        ['1. Fill rows in the "Items" sheet. Do NOT rename or reorder columns.'],
        ['2. Each row becomes one line item under your chosen Group.'],
        ['3. Column rules:'],
        ['   - Particular:        text. The product description or ref code (e.g., "N-G-B1 T-BLOCK").'],
        ['   - Actual W / H:      mm. Optional. If filled, the system can derive Chargeable from these.'],
        ['   - Unit:              one of MM, sqft, pcs. Default MM. Use "pcs" only for piece-rate items (no area).'],
        ['   - Chargeable W / H:  mm. REQUIRED for MM / sqft rows. This is what drives Area (Sq Mtr).'],
        ['   - Qty:               whole number, REQUIRED, >= 1.'],
        ['   - Rate (Rs/SqMt):    optional. If blank, the group-default rate set during import is used.'],
        ['   - Holes / Cutouts:   integer counts. Default 0.'],
        [''],
        ['4. Sample row in "Items" sheet shows the expected format. Replace it with your data.'],
        ['5. Save as .xlsx and upload via "Import Items" on the quote form.'],
        ['6. The Preview screen shows valid (green) and warning (amber) rows.'],
        ['   Rows with missing required fields will be skipped at import.'],
        [''],
        ['Notes:'],
        ['  - For multiple glass types/specs, do separate imports per Group (e.g., one upload per thickness).'],
        ['  - Jumbo charge is computed from per-piece area (not Qty-multiplied).'],
        ['  - The new Total Area (Sq Mtr) column = per-piece area x Qty (display only).'],
    ];

    const SHEETJS_URL = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
    let sheetjsLoaded = false;

    function loadSheetJS() {
        return new Promise((resolve, reject) => {
            if (sheetjsLoaded || (typeof XLSX !== 'undefined')) {
                sheetjsLoaded = true;
                resolve();
                return;
            }
            const s = document.createElement('script');
            s.src = SHEETJS_URL;
            s.onload = () => { sheetjsLoaded = true; resolve(); };
            s.onerror = () => reject(new Error('Failed to load XLSX library — check your internet connection.'));
            document.head.appendChild(s);
        });
    }

    // ─── template generation ─────────────────────────────────────────────────

    function downloadTemplate() {
        loadSheetJS().then(() => {
            const itemsData = [TEMPLATE_HEADERS, SAMPLE_ROW];
            const wsItems = XLSX.utils.aoa_to_sheet(itemsData);
            // Set column widths roughly to header lengths
            wsItems['!cols'] = TEMPLATE_HEADERS.map(h => ({ wch: Math.max(h.length + 2, 12) }));
            // Freeze header row
            wsItems['!freeze'] = { xSplit: 0, ySplit: 1 };

            const wsInstructions = XLSX.utils.aoa_to_sheet(INSTRUCTIONS);
            wsInstructions['!cols'] = [{ wch: 110 }];

            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, wsItems, 'Items');
            XLSX.utils.book_append_sheet(wb, wsInstructions, 'Instructions');

            XLSX.writeFile(wb, 'vcore-quote-template.xlsx');
        }).catch(err => alert(err.message));
    }

    // ─── upload parsing ──────────────────────────────────────────────────────

    let parsedRows = [];  // data rows only (header already stripped)
    let parseError = '';  // populated when header validation fails

    function parseXLSX(file) {
        return loadSheetJS().then(() => new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => {
                try {
                    const wb = XLSX.read(e.target.result, { type: 'array' });
                    // Use "Items" sheet if present, else first sheet
                    const sheetName = wb.SheetNames.includes('Items') ? 'Items' : wb.SheetNames[0];
                    const ws = wb.Sheets[sheetName];
                    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '', raw: false });
                    resolve(rows.map(r => r.map(c => String(c == null ? '' : c).trim())));
                } catch (err) { reject(err); }
            };
            reader.onerror = () => reject(reader.error);
            reader.readAsArrayBuffer(file);
        }));
    }

    function normHeader(s) {
        return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
    }

    function validateHeaders(rows) {
        if (!rows.length) return 'File is empty.';
        const header = rows[0].map(normHeader);
        const expected = TEMPLATE_HEADERS.map(normHeader);
        for (let i = 0; i < expected.length; i++) {
            if (header[i] !== expected[i]) {
                return `Column ${i + 1} expected "${TEMPLATE_HEADERS[i]}" but found "${rows[0][i] || '(empty)'}". ` +
                       `Download the standard template and try again.`;
            }
        }
        return '';
    }

    // ─── validation + preview ────────────────────────────────────────────────

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }

    function numify(v) {
        if (v == null) return null;
        const cleaned = String(v).replace(/[₹,\s]/g, '');
        if (cleaned === '' || cleaned === '-') return null;
        const n = parseFloat(cleaned);
        return isNaN(n) ? null : n;
    }

    // Convert one parsed row (positional array) into an object keyed by field.
    function rowToObj(row) {
        const o = {};
        COL_TO_FIELD.forEach((field, idx) => {
            o[field] = (row[idx] || '').trim();
        });
        return o;
    }

    function validateRow(o) {
        const errors = [];
        const cw = numify(o.chargeable_width);
        const ch = numify(o.chargeable_height);
        const aw = numify(o.actual_width);
        const ah = numify(o.actual_height);
        const qty = numify(o.quantity);
        const unit = (o.unit || 'MM').toUpperCase();
        const isPcs = unit === 'PCS';

        if (!qty || qty < 1) errors.push('qty');
        if (!isPcs) {
            if ((!cw || !ch) && (!aw || !ah)) errors.push('dims');
        }
        const validUnits = ['MM', 'SQFT', 'PCS'];
        if (o.unit && !validUnits.includes(unit)) errors.push('unit');
        return errors;
    }

    function renderPreview() {
        const tbl = document.getElementById('bulkImportPreviewTbl');
        const summary = document.getElementById('bulkImportSummary');
        const errBox = document.getElementById('bulkImportError');
        if (!tbl) return;

        if (parseError) {
            errBox.style.display = 'block';
            errBox.textContent = parseError;
            tbl.querySelector('tbody').innerHTML =
                `<tr><td colspan="11" class="text-center text-muted py-3">Fix the file and re-upload.</td></tr>`;
            if (summary) summary.innerHTML = '';
            return;
        }
        errBox.style.display = 'none';
        errBox.textContent = '';

        let goodCount = 0, badCount = 0;
        const tbody = parsedRows.map((row, i) => {
            const o = rowToObj(row);
            const errs = validateRow(o);
            if (errs.length) badCount++; else goodCount++;
            const cls = errs.length ? 'table-warning' : '';
            const errTxt = errs.length ? errs.join(', ') : '';
            return `<tr class="${cls}">
                <td>${i + 1}</td>
                <td>${escapeHtml(o.particular)}</td>
                <td>${escapeHtml(o.actual_width)}</td>
                <td>${escapeHtml(o.actual_height)}</td>
                <td>${escapeHtml(o.unit || 'MM')}</td>
                <td>${escapeHtml(o.chargeable_width)}</td>
                <td>${escapeHtml(o.chargeable_height)}</td>
                <td>${escapeHtml(o.quantity)}</td>
                <td>${escapeHtml(o.rate_sqper)}</td>
                <td>${escapeHtml(o.hole)}</td>
                <td>${escapeHtml(o.cutout)}</td>
                <td class="text-danger small">${errTxt}</td>
            </tr>`;
        }).join('');

        tbl.querySelector('tbody').innerHTML = tbody ||
            `<tr><td colspan="12" class="text-center text-muted py-3">No data rows found in the file.</td></tr>`;

        if (summary) {
            summary.innerHTML = `
                <span class="badge bg-success me-2">${goodCount} valid</span>
                <span class="badge bg-warning text-dark me-2">${badCount} need attention</span>
                <span class="text-muted small">(invalid rows are skipped at import)</span>
            `;
        }

        refreshGroupSelector();
    }

    function refreshGroupSelector() {
        const sel = document.getElementById('bulkImportTargetGroup');
        if (!sel) return;
        const prev = sel.value;
        const groups = Array.from(document.querySelectorAll('#itemsBody .group-row'));
        const opts = [`<option value="__new__">— Create new group —</option>`]
            .concat(groups.map(g => {
                const num = g.querySelector('.item-number')?.textContent || '?';
                const name = g.querySelector('.particular-input')?.value || '(unnamed group)';
                return `<option value="${g.dataset.itemId}">${escapeHtml(num)}. ${escapeHtml(name)}</option>`;
            }))
            .join('');
        sel.innerHTML = opts;
        if (prev && Array.from(sel.options).some(o => o.value === prev)) sel.value = prev;
    }

    // ─── commit (insert as sub-items) ────────────────────────────────────────

    function commitImport() {
        if (parseError) {
            alert(parseError);
            return;
        }
        const validObjs = parsedRows.map(rowToObj).filter(o => validateRow(o).length === 0);
        if (!validObjs.length) {
            alert('No valid rows to import. Fix the warnings in the preview and try again.');
            return;
        }

        const targetVal = document.getElementById('bulkImportTargetGroup')?.value;
        const newName = document.getElementById('bulkImportNewGroupName')?.value.trim();
        const groupRate = document.getElementById('bulkImportDefaultRate')?.value;
        const chargeableExtra = document.getElementById('bulkImportChargeableExtra')?.value;

        let groupRow;
        if (!targetVal || targetVal === '__new__') {
            if (typeof window.addGroup !== 'function') {
                alert('addGroup() is unavailable — page state is broken.');
                return;
            }
            window.addGroup();
            const groupRows = document.querySelectorAll('#itemsBody .group-row');
            groupRow = groupRows[groupRows.length - 1];
            if (newName) {
                const nameInput = groupRow.querySelector('.particular-input');
                if (nameInput) nameInput.value = newName;
            }
        } else {
            groupRow = document.querySelector(`[data-item-id="${targetVal}"]`);
            if (!groupRow) {
                alert('Target group no longer exists. Pick another.');
                return;
            }
        }

        if (groupRate) {
            const gr = groupRow.querySelector('.group-rate-input');
            if (gr) gr.value = groupRate;
        }
        if (chargeableExtra) {
            const ce = groupRow.querySelector('.chargeable-extra-input');
            if (ce) ce.value = chargeableExtra;
        }

        validObjs.forEach(o => {
            const cw = numify(o.chargeable_width);
            const ch = numify(o.chargeable_height);
            const aw = numify(o.actual_width);
            const ah = numify(o.actual_height);
            const qty = numify(o.quantity);
            const rate = numify(o.rate_sqper) || numify(groupRate) || 0;
            // Form's <select> uses values exactly: 'MM', 'sqft', 'pcs'.
            const unitMap = { MM: 'MM', SQFT: 'sqft', PCS: 'pcs' };
            const unitNormalized = unitMap[(o.unit || 'MM').toUpperCase()] || 'MM';

            const data = {
                particular: o.particular || '',
                actual_width: aw,
                actual_height: ah,
                chargeable_width: cw,
                chargeable_height: ch,
                unit: unitNormalized,
                quantity: qty,
                rate_sqper: rate,
                hole: numify(o.hole) || 0,
                cutout: numify(o.cutout) || 0,
                chargeable_extra: numify(chargeableExtra) || 30,
                total: 0,
                unit_square: null,
            };

            if (typeof window.addSubItemWithData === 'function') {
                window.addSubItemWithData(groupRow, data);
            }
        });

        // Recalc all newly inserted rows so derived fields populate
        const groupId = groupRow.dataset.itemId;
        document.querySelectorAll(`[data-parent-id="${groupId}"]`).forEach(r => {
            const trigger = r.querySelector('.qty-input');
            if (trigger && typeof window.calculateItemTotal === 'function') {
                window.calculateItemTotal(trigger);
            }
        });

        if (typeof window.updateTotals === 'function') window.updateTotals();
        if (typeof window.renumberItems === 'function') window.renumberItems();

        const modalEl = document.getElementById('bulkImportModal');
        if (modalEl && window.bootstrap) {
            bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        }

        // Reset state
        parsedRows = [];
        parseError = '';
        const fileInput = document.getElementById('bulkImportFile');
        if (fileInput) fileInput.value = '';
        renderPreview();
    }

    // ─── entry points ────────────────────────────────────────────────────────

    function handleFile(file) {
        const name = (file.name || '').toLowerCase();
        if (!(name.endsWith('.xlsx') || name.endsWith('.xls'))) {
            parseError = 'Only .xlsx / .xls files are supported. Use the standard template.';
            parsedRows = [];
            renderPreview();
            return;
        }
        parseXLSX(file).then(rows => {
            const err = validateHeaders(rows);
            if (err) {
                parseError = err;
                parsedRows = [];
            } else {
                parseError = '';
                // Strip header, drop rows where every cell is blank
                parsedRows = rows.slice(1).filter(r => r.some(c => c && c.toString().trim()));
            }
            renderPreview();
        }).catch(err => {
            parseError = 'Could not parse file: ' + (err.message || err);
            parsedRows = [];
            renderPreview();
        });
    }

    function openModal() {
        const modalEl = document.getElementById('bulkImportModal');
        if (!modalEl || !window.bootstrap) return;
        refreshGroupSelector();
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    window.openBulkImportModal = openModal;
    window.bulkImportCommit = commitImport;
    window.bulkImportDownloadTemplate = downloadTemplate;

    document.addEventListener('DOMContentLoaded', () => {
        const fileInput = document.getElementById('bulkImportFile');
        if (fileInput) {
            fileInput.addEventListener('change', e => {
                if (e.target.files && e.target.files[0]) handleFile(e.target.files[0]);
            });
        }
    });
})();
