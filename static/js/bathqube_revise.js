// ────────────────────────────────────────────────────────────────────────────
//  Bathqube revise — sales-person bill editor
//
//  Responsibilities:
//    1. Bootstrap UI state from server-rendered initial JSON
//    2. Render an editable card per enclosure (collapsible, with all selections + panels)
//    3. Add/remove/clone enclosures; add/remove panels; recompute per-enclosure subtotal
//    4. Manage the "extras" rows (free-form line items)
//    5. Live-update the "totals" panel on every input change
//    6. On submit, serialize the enclosures array into the hidden field
//
//  The math (mirrors _bathqube_recompute_totals in app.py):
//    enc_subtotal = Σ enclosures (sqft × pricePerSqft × quantity)
//    ext_subtotal = Σ extras (qty × rate)
//    subtotal     = enc_subtotal + ext_subtotal
//    discount     = subtotal × (discount_pct / 100)
//    taxable      = subtotal − discount
//    cgst = sgst  = taxable × (gst_pct / 2 / 100)
//    grand_total  = taxable + cgst + sgst
//    balance      = max(0, grand_total − amount_received)
// ────────────────────────────────────────────────────────────────────────────

(function () {
  'use strict';

  // ── 1. Bootstrap from server-rendered initial state ────────────────────────
  const stateEl = document.getElementById('initialState');
  const initial = stateEl ? JSON.parse(stateEl.textContent) : { enclosures: [], options: {} };
  const options = initial.options || {};

  // Working state: a deep copy so we never accidentally mutate `initial`.
  // Each enclosure carries a synthetic _uid for React-like list keys.
  let nextUid = 1;
  const state = {
    enclosures: (initial.enclosures || []).map(e => normaliseEnclosureIn(e))
  };

  function normaliseEnclosureIn(e) {
    return {
      _uid: nextUid++,
      name: e.name || '',
      typeLabel: e.typeLabel || '',
      materialLabel: e.materialLabel || '',
      fittingLabel: e.fittingLabel || '',
      hardwareTypeLabel: e.hardwareTypeLabel || '',
      thicknessLabel: e.thicknessLabel || '',
      glassPanels: (e.glassPanels || []).map(p => ({
        width: numOr(p.width, 4),
        height: numOr(p.height, 7),
      })),
      pricePerSqft: numOr(e.pricePerSqft, 749),
      quantity: Math.max(1, Math.floor(numOr(e.quantity, 1))),
      _expanded: true,
    };
  }

  function numOr(v, fb) { const n = parseFloat(v); return isNaN(n) ? fb : n; }
  function fmtINR(n) {
    return '₹' + (Math.round((n || 0) * 100) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // Each option is a [label, surchargePerSqft] tuple from app.py:BATHQUBE_REVISE_OPTIONS.
  // Picking "Fluted" should bump per-sqft by ₹150; switching to "Tinted" bumps by
  // delta (newSurcharge − oldSurcharge). Unknown / "Other" entries surcharge = 0.
  const FIELD_TO_OPT_KEY = {
    typeLabel: 'types',
    materialLabel: 'materials',
    thicknessLabel: 'thicknesses',
    fittingLabel: 'fittings',
    hardwareTypeLabel: 'hardwareTypes',
  };
  function optLabel(o) { return Array.isArray(o) ? o[0] : o; }
  function optSurcharge(o) { return Array.isArray(o) ? Number(o[1]) || 0 : 0; }
  function surchargeFor(optKey, label) {
    const list = options[optKey] || [];
    for (const o of list) {
      if (optLabel(o) === label) return optSurcharge(o);
    }
    return 0;  // custom "Other" value — unknown, no surcharge
  }

  // ── 2. Render an enclosure card ────────────────────────────────────────────
  function renderEnclosure(enc, idx) {
    const sqft = enc.glassPanels.reduce((s, p) => s + Math.max(0.5, p.width) * Math.max(0.5, p.height), 0);
    const subtotal = sqft * enc.pricePerSqft * Math.max(1, enc.quantity);

    const card = document.createElement('div');
    card.className = 'border-bottom';
    card.dataset.uid = enc._uid;

    card.innerHTML = `
      <div class="d-flex align-items-center px-3 py-2 enc-header" style="cursor:pointer; background:${enc._expanded ? '#eaf3fb' : '#fff'}">
        <div class="flex-grow-1">
          <span class="badge bg-primary me-2">#${idx + 1}</span>
          <strong class="enc-summary-name">${escapeHtml(enc.name || ('Enclosure ' + (idx + 1)))}</strong>
          <span class="text-muted small ms-2 enc-summary-spec">
            ${escapeHtml(enc.typeLabel || '—')} · ${escapeHtml(enc.materialLabel || '—')} ·
            ${enc.glassPanels.length} panel${enc.glassPanels.length === 1 ? '' : 's'} ·
            ${sqft.toFixed(1)} sq.ft × ${enc.quantity}
          </span>
        </div>
        <div class="text-end">
          <div class="fw-bold text-primary enc-summary-subtotal">${fmtINR(subtotal)}</div>
          <small class="text-muted enc-toggle">${enc._expanded ? '▲ Collapse' : '▼ Expand'}</small>
        </div>
      </div>
      <div class="enc-body p-3 ${enc._expanded ? '' : 'd-none'}" style="background:#f8fbfd;">
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label">Enclosure name</label>
            <input class="form-control form-control-sm field-name" value="${escapeHtml(enc.name)}" placeholder="Enclosure ${idx + 1}">
          </div>
          <div class="col-md-6 text-end">
            <button type="button" class="btn btn-sm btn-outline-secondary act-clone"><i class="bi bi-files"></i> Duplicate</button>
            <button type="button" class="btn btn-sm btn-outline-danger act-remove"><i class="bi bi-trash"></i> Remove</button>
          </div>

          <div class="col-md-6">
            ${hybridSelectHtml('Enclosure type', options.types, enc.typeLabel, 'field-typeLabel')}
          </div>
          <div class="col-md-3">
            ${hybridSelectHtml('Material', options.materials, enc.materialLabel, 'field-materialLabel')}
          </div>
          <div class="col-md-3">
            ${hybridSelectHtml('Thickness', options.thicknesses, enc.thicknessLabel, 'field-thicknessLabel')}
          </div>
          <div class="col-md-6">
            ${hybridSelectHtml('Hardware colour (fitting)', options.fittings, enc.fittingLabel, 'field-fittingLabel')}
          </div>
          <div class="col-md-6">
            ${hybridSelectHtml('Hardware type', options.hardwareTypes, enc.hardwareTypeLabel, 'field-hardwareTypeLabel')}
          </div>

          <div class="col-md-4">
            <label class="form-label">Price per sq.ft (₹)</label>
            <input class="form-control form-control-sm field-pricePerSqft" type="number" min="0" step="1" value="${enc.pricePerSqft}">
          </div>
          <div class="col-md-2">
            <label class="form-label">Quantity</label>
            <input class="form-control form-control-sm field-quantity" type="number" min="1" step="1" value="${enc.quantity}">
          </div>
          <div class="col-md-6 d-flex align-items-end">
            <div class="text-end w-100 small">
              <div>Sqft: <strong class="enc-sqft">${sqft.toFixed(2)}</strong></div>
              <div>Subtotal: <strong class="text-primary enc-subtotal">${fmtINR(subtotal)}</strong></div>
            </div>
          </div>

          <div class="col-12">
            <label class="form-label">Glass panels</label>
            <div class="panels-container border rounded p-2 bg-white"></div>
            <button type="button" class="btn btn-sm btn-outline-primary mt-2 act-add-panel">
              <i class="bi bi-plus"></i> Add panel
            </button>
          </div>
        </div>
      </div>
    `;
    return card;
  }

  function hybridSelectHtml(label, opts, currentValue, fieldClass) {
    const safeOpts = Array.isArray(opts) ? opts : [];
    const labels = safeOpts.map(optLabel);
    const isInList = labels.includes(currentValue);
    const showOther = currentValue && !isInList;
    let html = `<label class="form-label">${escapeHtml(label)}</label>
      <select class="form-select form-select-sm ${fieldClass}-select">`;
    for (const o of safeOpts) {
      const lbl = optLabel(o);
      const sur = optSurcharge(o);
      const suffix = sur > 0 ? ` (+₹${sur}/sqft)` : (sur < 0 ? ` (₹${sur}/sqft)` : '');
      html += `<option value="${escapeHtml(lbl)}"${lbl === currentValue ? ' selected' : ''}>${escapeHtml(lbl)}${suffix}</option>`;
    }
    html += `<option value="__other__"${showOther || !currentValue ? ' selected' : ''}>Other (specify)…</option>`;
    html += `</select>`;
    html += `<input class="form-control form-control-sm mt-1 ${fieldClass}-other" placeholder="Type custom value"
              value="${showOther ? escapeHtml(currentValue) : ''}"
              style="display:${showOther ? 'block' : 'none'}">`;
    // Hidden combined field that consolidates select OR other for state read
    html += `<input type="hidden" class="${fieldClass}" value="${escapeHtml(currentValue)}">`;
    return html;
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  // ── 3. Render a panel row inside an enclosure body ─────────────────────────
  function renderPanel(panel, idx, total) {
    const sqft = Math.max(0.5, panel.width) * Math.max(0.5, panel.height);
    const row = document.createElement('div');
    row.className = 'row g-2 align-items-end mb-2 panel-row';
    row.innerHTML = `
      <div class="col-1 text-muted small">Panel ${idx + 1}</div>
      <div class="col-3">
        <label class="form-label small mb-0">Width (ft)</label>
        <input class="form-control form-control-sm field-panel-width" type="number" min="0.5" step="0.5" value="${panel.width}">
      </div>
      <div class="col-3">
        <label class="form-label small mb-0">Height (ft)</label>
        <input class="form-control form-control-sm field-panel-height" type="number" min="0.5" step="0.5" value="${panel.height}">
      </div>
      <div class="col-3 text-end small">
        <span class="text-muted">Sqft:</span> <strong class="panel-sqft">${sqft.toFixed(2)}</strong>
      </div>
      <div class="col-2 text-end">
        ${total > 1 ? '<button type="button" class="btn btn-sm btn-link text-danger act-remove-panel"><i class="bi bi-x-lg"></i></button>' : ''}
      </div>
    `;
    return row;
  }

  // ── 4. Re-render the whole enclosures container (called after every state change) ──
  function rerenderEnclosures() {
    const container = document.getElementById('enclosuresContainer');
    container.innerHTML = '';
    state.enclosures.forEach((enc, idx) => {
      const card = renderEnclosure(enc, idx);
      container.appendChild(card);

      // Mount the panels
      const panelsContainer = card.querySelector('.panels-container');
      enc.glassPanels.forEach((p, pIdx) => {
        panelsContainer.appendChild(renderPanel(p, pIdx, enc.glassPanels.length));
      });

      wireEnclosureCard(card, enc);
    });
    document.getElementById('encCount').textContent =
      `${state.enclosures.length} enclosure${state.enclosures.length === 1 ? '' : 's'}`;
    recomputeTotals();
  }

  // ── 5. Wire input handlers for one card (after it's in the DOM) ────────────
  function wireEnclosureCard(card, enc) {
    // Header click → toggle expand/collapse
    card.querySelector('.enc-header').addEventListener('click', (ev) => {
      // Ignore clicks on buttons inside the body (they're not in header anyway)
      enc._expanded = !enc._expanded;
      rerenderEnclosures();
    });

    // Field bindings (text & numeric)
    bind(card, '.field-name', 'name', 'string');
    bind(card, '.field-pricePerSqft', 'pricePerSqft', 'number');
    bind(card, '.field-quantity', 'quantity', 'int');

    // Hybrid select fields
    ['typeLabel', 'materialLabel', 'thicknessLabel', 'fittingLabel', 'hardwareTypeLabel'].forEach(fname => {
      const sel = card.querySelector(`.field-${fname}-select`);
      const other = card.querySelector(`.field-${fname}-other`);
      const hidden = card.querySelector(`.field-${fname}`);
      if (!sel) return;
      const optKey = FIELD_TO_OPT_KEY[fname];
      const priceEl = card.querySelector('.field-pricePerSqft');
      const applyDelta = (oldLabel, newLabel) => {
        const delta = surchargeFor(optKey, newLabel) - surchargeFor(optKey, oldLabel);
        if (delta !== 0) {
          enc.pricePerSqft = Math.max(0, (Number(enc.pricePerSqft) || 0) + delta);
          if (priceEl) priceEl.value = enc.pricePerSqft;
        }
      };
      const updateHidden = () => {
        const v = sel.value === '__other__' ? other.value : sel.value;
        const oldVal = enc[fname] || '';
        applyDelta(oldVal, v);
        hidden.value = v;
        enc[fname] = v;
        // update collapsed summary text without full re-render (cheaper)
        const sumName = card.querySelector('.enc-summary-name');
        const sumSpec = card.querySelector('.enc-summary-spec');
        if (sumName) sumName.textContent = enc.name || ('Enclosure ' + (state.enclosures.indexOf(enc) + 1));
        if (sumSpec) {
          const sqft = enc.glassPanels.reduce((s, p) => s + Math.max(0.5, p.width) * Math.max(0.5, p.height), 0);
          sumSpec.textContent = `${enc.typeLabel || '—'} · ${enc.materialLabel || '—'} · ${enc.glassPanels.length} panel${enc.glassPanels.length === 1 ? '' : 's'} · ${sqft.toFixed(1)} sq.ft × ${enc.quantity}`;
        }
        updateEnclosureSubtotalInPlace(card, enc);
        recomputeTotals();
      };
      sel.addEventListener('change', () => {
        other.style.display = sel.value === '__other__' ? 'block' : 'none';
        if (sel.value !== '__other__') other.value = '';
        updateHidden();
      });
      other.addEventListener('input', updateHidden);
    });

    // Action buttons
    card.querySelector('.act-clone').addEventListener('click', (ev) => {
      ev.stopPropagation();
      const idx = state.enclosures.indexOf(enc);
      const copy = JSON.parse(JSON.stringify(enc));
      copy._uid = nextUid++;
      copy.name = (enc.name || ('Enclosure ' + (idx + 1))) + ' (copy)';
      copy._expanded = true;
      state.enclosures.splice(idx + 1, 0, copy);
      rerenderEnclosures();
    });
    card.querySelector('.act-remove').addEventListener('click', (ev) => {
      ev.stopPropagation();
      if (state.enclosures.length <= 1) {
        alert('At least one enclosure is required. Add another before removing this one.');
        return;
      }
      if (!confirm(`Remove enclosure "${enc.name || 'this enclosure'}"?`)) return;
      state.enclosures = state.enclosures.filter(e => e._uid !== enc._uid);
      rerenderEnclosures();
    });
    card.querySelector('.act-add-panel').addEventListener('click', (ev) => {
      ev.stopPropagation();
      enc.glassPanels.push({ width: 3, height: 7 });
      rerenderEnclosures();
    });

    // Panel field bindings
    card.querySelectorAll('.panel-row').forEach((row, pIdx) => {
      const w = row.querySelector('.field-panel-width');
      const h = row.querySelector('.field-panel-height');
      const sqftEl = row.querySelector('.panel-sqft');
      const updatePanel = () => {
        enc.glassPanels[pIdx].width = numOr(w.value, 0.5);
        enc.glassPanels[pIdx].height = numOr(h.value, 0.5);
        const s = Math.max(0.5, enc.glassPanels[pIdx].width) * Math.max(0.5, enc.glassPanels[pIdx].height);
        if (sqftEl) sqftEl.textContent = s.toFixed(2);
        updateEnclosureSubtotalInPlace(card, enc);
        recomputeTotals();
      };
      w.addEventListener('input', updatePanel);
      h.addEventListener('input', updatePanel);
      const removeBtn = row.querySelector('.act-remove-panel');
      if (removeBtn) {
        removeBtn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          enc.glassPanels.splice(pIdx, 1);
          rerenderEnclosures();
        });
      }
    });
  }

  function bind(card, selector, key, kind) {
    const el = card.querySelector(selector);
    if (!el) return;
    const handler = () => {
      let v;
      if (kind === 'number') v = numOr(el.value, 0);
      else if (kind === 'int') v = Math.max(1, Math.floor(numOr(el.value, 1)));
      else v = el.value;
      const enc = state.enclosures.find(e => e._uid == card.dataset.uid);
      if (!enc) return;
      enc[key] = v;
      updateEnclosureSubtotalInPlace(card, enc);
      recomputeTotals();
    };
    el.addEventListener('input', handler);
  }

  function updateEnclosureSubtotalInPlace(card, enc) {
    const sqft = enc.glassPanels.reduce((s, p) => s + Math.max(0.5, p.width) * Math.max(0.5, p.height), 0);
    const subtotal = sqft * enc.pricePerSqft * Math.max(1, enc.quantity);
    const sumName = card.querySelector('.enc-summary-name');
    const sumSpec = card.querySelector('.enc-summary-spec');
    const sumAmt = card.querySelector('.enc-summary-subtotal');
    const encSqft = card.querySelector('.enc-sqft');
    const encSub = card.querySelector('.enc-subtotal');
    if (sumName) sumName.textContent = enc.name || ('Enclosure ' + (state.enclosures.indexOf(enc) + 1));
    if (sumSpec) sumSpec.textContent = `${enc.typeLabel || '—'} · ${enc.materialLabel || '—'} · ${enc.glassPanels.length} panel${enc.glassPanels.length === 1 ? '' : 's'} · ${sqft.toFixed(1)} sq.ft × ${enc.quantity}`;
    if (sumAmt) sumAmt.textContent = fmtINR(subtotal);
    if (encSqft) encSqft.textContent = sqft.toFixed(2);
    if (encSub) encSub.textContent = fmtINR(subtotal);
  }

  // ── 6. Extras (additional charges) wiring ──────────────────────────────────
  function wireExtraRow(row) {
    const q = row.querySelector('.qty');
    const r = row.querySelector('.rate');
    const a = row.querySelector('.amount');
    const recompute = () => {
      const qty = numOr(q.value, 0);
      const rate = numOr(r.value, 0);
      a.textContent = fmtINR(qty * rate);
      recomputeTotals();
    };
    q.addEventListener('input', recompute);
    r.addEventListener('input', recompute);
    row.querySelector('.remove-row').addEventListener('click', () => {
      row.remove();
      recomputeTotals();
    });
    recompute();
  }

  document.getElementById('addExtraBtn').addEventListener('click', () => {
    const tmpl = document.getElementById('extraRowTemplate');
    const node = tmpl.content.firstElementChild.cloneNode(true);
    document.getElementById('extrasBody').appendChild(node);
    wireExtraRow(node);
    node.querySelector('.desc').focus();
  });

  document.querySelectorAll('#extrasBody .extra-row').forEach(wireExtraRow);

  // ── 7. Add-enclosure action ────────────────────────────────────────────────
  document.getElementById('addEnclosureBtn').addEventListener('click', () => {
    state.enclosures.push({
      _uid: nextUid++,
      name: 'Enclosure ' + (state.enclosures.length + 1),
      typeLabel: optLabel((options.types || [])[0] || ''),
      materialLabel: optLabel((options.materials || [])[0] || ''),
      fittingLabel: optLabel((options.fittings || [])[0] || ''),
      hardwareTypeLabel: optLabel((options.hardwareTypes || [])[0] || ''),
      thicknessLabel: optLabel((options.thicknesses || [])[0] || ''),
      glassPanels: [{ width: 4, height: 7 }],
      pricePerSqft: 749,
      quantity: 1,
      _expanded: true,
    });
    rerenderEnclosures();
  });

  // ── 8. Live totals recomputation ───────────────────────────────────────────
  function recomputeTotals() {
    // Enclosure subtotal
    let encSubtotal = 0;
    for (const enc of state.enclosures) {
      const sqft = enc.glassPanels.reduce((s, p) => s + Math.max(0.5, p.width) * Math.max(0.5, p.height), 0);
      encSubtotal += sqft * enc.pricePerSqft * Math.max(1, enc.quantity);
    }
    // Extras subtotal
    let extSubtotal = 0;
    document.querySelectorAll('#extrasBody .extra-row').forEach(row => {
      const qty = numOr(row.querySelector('.qty').value, 0);
      const rate = numOr(row.querySelector('.rate').value, 0);
      extSubtotal += qty * rate;
    });
    const subtotal = encSubtotal + extSubtotal;
    const discountPct = Math.max(0, Math.min(100, numOr(document.getElementById('discountInput').value, 0)));
    const discountAmt = subtotal * discountPct / 100;
    const taxable = Math.max(0, subtotal - discountAmt);
    const gstPct = Math.max(0, numOr(document.getElementById('gstInput').value, 18));
    const halfGst = gstPct / 2;
    const cgst = taxable * halfGst / 100;
    const sgst = taxable * halfGst / 100;
    const grandTotal = taxable + cgst + sgst;
    const received = numOr(document.getElementById('amountReceivedInput').value, 0);
    const balance = Math.max(0, grandTotal - received);

    // Write to DOM
    setText('encSubtotalCell', fmtINR(encSubtotal));
    setText('extrasSubtotalCell', fmtINR(extSubtotal));
    const stCell = document.getElementById('subtotalCell');
    if (stCell) stCell.innerHTML = '<strong>' + fmtINR(subtotal) + '</strong>';
    setText('discountPctDisplay', discountPct.toFixed(discountPct % 1 === 0 ? 0 : 2));
    setText('discountAmtCell', '−' + fmtINR(discountAmt));
    setText('taxableCell', fmtINR(taxable));
    setText('cgstPctDisplay', halfGst.toFixed(halfGst % 1 === 0 ? 0 : 2));
    setText('sgstPctDisplay', halfGst.toFixed(halfGst % 1 === 0 ? 0 : 2));
    setText('cgstCell', fmtINR(cgst));
    setText('sgstCell', fmtINR(sgst));
    setText('grandTotalCell', fmtINR(grandTotal));
    setText('receivedCell', fmtINR(received));
    setText('balanceCell', fmtINR(balance));
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  ['gstInput', 'discountInput', 'amountReceivedInput'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', recomputeTotals);
  });

  // ── 9. Submit: serialize enclosures into the hidden field ──────────────────
  document.getElementById('reviseForm').addEventListener('submit', (ev) => {
    if (state.enclosures.length === 0) {
      ev.preventDefault();
      alert('Add at least one enclosure before saving.');
      return;
    }
    // Strip UI-only fields (_uid, _expanded) before serializing.
    const clean = state.enclosures.map(e => ({
      name: e.name || '',
      typeLabel: e.typeLabel || '',
      materialLabel: e.materialLabel || '',
      fittingLabel: e.fittingLabel || '',
      hardwareTypeLabel: e.hardwareTypeLabel || '',
      thicknessLabel: e.thicknessLabel || '',
      glassPanels: e.glassPanels.map(p => {
        const w = Math.max(0.5, p.width);
        const h = Math.max(0.5, p.height);
        return { width: w, height: h, sqft: w * h };
      }),
      pricePerSqft: e.pricePerSqft || 0,
      quantity: Math.max(1, Math.floor(e.quantity || 1)),
      sqft: e.glassPanels.reduce((s, p) => s + Math.max(0.5, p.width) * Math.max(0.5, p.height), 0),
      subtotal: e.glassPanels.reduce((s, p) => s + Math.max(0.5, p.width) * Math.max(0.5, p.height), 0)
                * (e.pricePerSqft || 0) * Math.max(1, e.quantity || 1),
    }));
    document.getElementById('enclosuresJson').value = JSON.stringify(clean);
  });

  // ── 10. Initial render ─────────────────────────────────────────────────────
  rerenderEnclosures();
})();
