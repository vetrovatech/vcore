/**
 * Enhanced Quote Form JavaScript
 * Handles hierarchical quote items with groups and sub-items
 * Matches sample quote format with detailed specifications
 * Phase 2: Chargeable Extra, Sq Mtr calculations, and new charge fields
 */

let itemCounter = 0;
let groupCounter = 0;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    // Check if we're editing an existing quote
    if (window.existingQuoteData && window.existingQuoteData.items.length > 0) {
        if (window.existingQuoteData.quoteType === 'B2C') {
            // Restore rate mode before loading rows
            if (window.existingQuoteData.b2cRateMode === 'qty') {
                b2cRateMode = 'qty';
                const modeSelect = document.querySelector('#b2cItemsTable thead select');
                if (modeSelect) modeSelect.value = 'qty';
                const sizeHeader = document.getElementById('b2cSizeHeader');
                if (sizeHeader) sizeHeader.textContent = 'Qty';
            }
            // Load flat B2C items (all items are non-group leaf nodes)
            loadB2CItems(window.existingQuoteData.items.filter(i => !i.is_group));
        } else {
            loadExistingItems(window.existingQuoteData.items);
        }
    } else {
        // New quote — B2C gets its first row via applyMode(); B2B gets a group
        const typeEl = document.querySelector('select[name="quote_type"]') ||
                       document.querySelector('input[type="hidden"][name="quote_type"]');
        if (!typeEl || typeEl.value !== 'B2C') {
            addGroup();
            // Default handling to 1% for new B2B quotes
            const handlingPctEl = document.getElementById('handling_percentage');
            if (handlingPctEl && !handlingPctEl.value) handlingPctEl.value = 1;
        }
    }

    // Update totals
    updateTotals();

    // Add event listeners for charges
    document.querySelectorAll('.charge-input').forEach(input => {
        input.addEventListener('input', updateTotals);
    });

    document.getElementById('gst_percentage').addEventListener('input', updateTotals);

    // Recalculate all items when jumbo rate percentages are changed
    document.querySelectorAll('.jumbo-rate-input').forEach(input => {
        input.addEventListener('input', () => {
            document.querySelectorAll('.sub-item-row').forEach(row => {
                const anyInput = row.querySelector('.qty-input');
                if (anyInput) calculateItemTotal(anyInput);
            });
        });
    });
});

/**
 * Load existing items when editing a quote
 */
function loadExistingItems(items) {
    items.forEach((item, index) => {
        if (item.is_group) {
            // Add group
            groupCounter++;
            const tbody = document.getElementById('itemsBody');
            const row = document.createElement('tr');
            row.className = 'item-row group-row';
            row.dataset.itemId = `group-${groupCounter}`;
            row.dataset.isGroup = 'true';

            row.innerHTML = `
                <td class="item-number" style="font-weight: bold;">${groupCounter}</td>
                <td colspan="12">
                    <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <input type="text" class="form-control form-control-sm particular-input"
                               name="items[${itemCounter}][particular]"
                               value="${item.particular}"
                               placeholder="Product Group (e.g., 8mm Toughened Glass)"
                               style="font-weight: bold; flex: 1; min-width: 200px;" required>
                        <button type="button" class="btn btn-sm btn-info" onclick="openGlassCatalogModal(this)" title="Browse Glass Catalog">
                            <i class="bi bi-grid-3x3"></i> Browse
                        </button>
                        <label class="form-label mb-0" style="white-space: nowrap;">Rate (₹/sqm):</label>
                        <input type="number" step="0.01" class="form-control form-control-sm group-rate-input"
                               name="items[${itemCounter}][rate_sqper]"
                               value="${item.rate_sqper || ''}"
                               placeholder="0.00" style="width: 90px;" min="0"
                               oninput="propagateGroupRate(this)" title="Set rate for all items in this group">
                        <label class="form-label mb-0" style="white-space: nowrap;">Chargeable Extra (MM):</label>
                        <input type="number" class="form-control form-control-sm chargeable-extra-input"
                               name="items[${itemCounter}][chargeable_extra]"
                               value="${item.chargeable_extra || 30}"
                               style="width: 80px;" min="0">
                        <label class="form-label mb-0" style="white-space: nowrap;">Hole Price:</label>
                        <input type="number" step="0.01" class="form-control form-control-sm hole-price-input"
                               name="items[${itemCounter}][hole_price]"
                               value="${item.hole_price}"
                               style="width: 80px;" min="0">
                        <label class="form-label mb-0" style="white-space: nowrap;">Cutout Price:</label>
                        <input type="number" step="0.01" class="form-control form-control-sm cutout-price-input"
                               name="items[${itemCounter}][cutout_price]"
                               value="${item.cutout_price}"
                               style="width: 80px;" min="0">
                        <button type="button" class="btn btn-sm btn-primary" onclick="recalculateGroupItems(this)" title="Recalculate all items in this group">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>
                        <input type="hidden" name="items[${itemCounter}][is_group]" value="true">
                        <input type="hidden" name="items[${itemCounter}][item_number]" value="${groupCounter}">
                        <button type="button" class="btn btn-sm btn-success" onclick="addSubItem(this)" title="Add Sub-item">
                            <i class="bi bi-plus"></i> Add Item
                        </button>
                        <button type="button" class="btn btn-sm btn-danger" onclick="removeItem(this)" title="Remove Group">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            `;

            tbody.appendChild(row);
            itemCounter++;

            // Load sub-items
            if (item.children && item.children.length > 0) {
                item.children.forEach(child => {
                    addSubItemWithData(row, child);
                });
            }
        }
    });
}

/**
 * Add a sub-item with existing data
 */
function addSubItemWithData(groupRow, data) {
    const groupId = groupRow.dataset.itemId;
    const groupNumber = groupRow.querySelector('.item-number').textContent;
    const existingSubItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);
    const subNumber = existingSubItems.length + 1;
    const chargeableExtra = parseInt(groupRow.querySelector('.chargeable-extra-input')?.value) || 30;

    const tbody = document.getElementById('itemsBody');
    const row = document.createElement('tr');
    row.className = 'item-row sub-item-row';
    row.dataset.itemId = `item-${itemCounter}`;
    row.dataset.parentId = groupId;
    row.dataset.isGroup = 'false';

    row.innerHTML = `
        <td class="item-number" style="padding-left: 30px;">${groupNumber}.${subNumber}</td>
        <td>
            <input type="text" class="form-control form-control-sm particular-input" 
                   name="items[${itemCounter}][particular]" 
                   value="${data.particular || ''}"
                   placeholder="Product description">
            <input type="hidden" name="items[${itemCounter}][parent_id]" value="${groupId}">
            <input type="hidden" name="items[${itemCounter}][is_group]" value="false">
            <input type="hidden" name="items[${itemCounter}][chargeable_extra]" value="${chargeableExtra}">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input actual-width" 
                   name="items[${itemCounter}][actual_width]" 
                   value="${data.actual_width || ''}"
                   placeholder="Width" oninput="applyChargeableExtra(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input actual-height"
                   name="items[${itemCounter}][actual_height]"
                   value="${data.actual_height || ''}"
                   placeholder="Height" oninput="applyChargeableExtra(this)">
        </td>
        <td>
            <select class="form-select form-select-sm" name="items[${itemCounter}][unit]"
                    onchange="calculateItemTotal(this)">
                <option value="MM" ${data.unit === 'MM' ? 'selected' : ''}>MM</option>
                <option value="sqft" ${data.unit === 'sqft' ? 'selected' : ''}>sqft</option>
                <option value="pcs" ${data.unit === 'pcs' ? 'selected' : ''}>pcs</option>
            </select>
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-width"
                   name="items[${itemCounter}][chargeable_width]"
                   value="${data.chargeable_width || ''}"
                   placeholder="Width" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-height"
                   name="items[${itemCounter}][chargeable_height]"
                   value="${data.chargeable_height || ''}"
                   placeholder="Height" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm qty-input"
                   name="items[${itemCounter}][quantity]"
                   value="${data.quantity}"
                   min="1" oninput="calculateItemTotal(this)" required>
        </td>
        <td>
            <input type="number" step="0.0001" class="form-control form-control-sm unit-square-display"
                   name="items[${itemCounter}][unit_square]"
                   value="${data.unit_square ? data.unit_square.toFixed(4) : ''}"
                   placeholder="0.0000" readonly>
        </td>
        <td>
            <input type="number" class="form-control form-control-sm hole-input"
                   name="items[${itemCounter}][hole]"
                   value="${data.hole || 0}"
                   min="0" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm cutout-input"
                   name="items[${itemCounter}][cutout]"
                   value="${data.cutout || 0}"
                   min="0" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm rate-input"
                   name="items[${itemCounter}][rate_sqper]"
                   value="${data.rate_sqper}"
                   placeholder="Rate" oninput="calculateItemTotal(this)" required>
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm total-display" 
                   name="items[${itemCounter}][total]" 
                   value="${data.total ? data.total.toFixed(2) : ''}"
                   placeholder="0.00" readonly>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeItem(this)">
                <i class="bi bi-trash"></i>
            </button>
        </td>
    `;

    // Insert after the last sub-item or after the group row
    if (existingSubItems.length > 0) {
        const lastSubItem = existingSubItems[existingSubItems.length - 1];
        lastSubItem.after(row);
    } else {
        groupRow.after(row);
    }

    // Set jumbo charge on load using saved unit_square, total, and saved tier percentages
    const loadedUnitSquare = parseFloat(data.unit_square) || 0;
    const loadedPct1 = parseFloat(document.getElementById('jumbo_pct_tier1')?.value) || 10;
    const loadedPct2 = parseFloat(document.getElementById('jumbo_pct_tier2')?.value) || 15;
    const loadedPct3 = parseFloat(document.getElementById('jumbo_pct_tier3')?.value) || 20;
    let loadedJumboPercent = 0;
    if (loadedUnitSquare >= 7) loadedJumboPercent = loadedPct3;
    else if (loadedUnitSquare >= 5.5) loadedJumboPercent = loadedPct2;
    else if (loadedUnitSquare >= 4.5) loadedJumboPercent = loadedPct1;
    row.dataset.jumboCharge = ((parseFloat(data.total || 0) * loadedJumboPercent) / 100).toFixed(2);

    itemCounter++;
}

/**
 * Add a new group (parent item)
 */
function addGroup() {
    groupCounter++;
    const tbody = document.getElementById('itemsBody');

    const row = document.createElement('tr');
    row.className = 'item-row group-row';
    row.dataset.itemId = `group-${groupCounter}`;
    row.dataset.isGroup = 'true';

    row.innerHTML = `
        <td class="item-number" style="font-weight: bold;">${groupCounter}</td>
        <td colspan="12">
            <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <input type="text" class="form-control form-control-sm particular-input"
                       name="items[${itemCounter}][particular]"
                       placeholder="Product Group (e.g., 8mm Toughened Glass)"
                       style="font-weight: bold; flex: 1; min-width: 200px;" required>
                <button type="button" class="btn btn-sm btn-info" onclick="openGlassCatalogModal(this)" title="Browse Glass Catalog">
                    <i class="bi bi-grid-3x3"></i> Browse
                </button>
                <label class="form-label mb-0" style="white-space: nowrap;">Rate (₹/sqm):</label>
                <input type="number" step="0.01" class="form-control form-control-sm group-rate-input"
                       name="items[${itemCounter}][rate_sqper]"
                       placeholder="0.00" style="width: 90px;" min="0"
                       oninput="propagateGroupRate(this)" title="Set rate for all items in this group">
                <label class="form-label mb-0" style="white-space: nowrap;">Chargeable Extra (MM):</label>
                <input type="number" class="form-control form-control-sm chargeable-extra-input"
                       name="items[${itemCounter}][chargeable_extra]"
                       value="30" style="width: 80px;" min="0">
                <label class="form-label mb-0" style="white-space: nowrap;">Hole Price:</label>
                <input type="number" step="0.01" class="form-control form-control-sm hole-price-input"
                       name="items[${itemCounter}][hole_price]"
                       value="400" style="width: 80px;" min="0">
                <label class="form-label mb-0" style="white-space: nowrap;">Cutout Price:</label>
                <input type="number" step="0.01" class="form-control form-control-sm cutout-price-input"
                       name="items[${itemCounter}][cutout_price]"
                       value="100" style="width: 80px;" min="0">
                <button type="button" class="btn btn-sm btn-primary" onclick="recalculateGroupItems(this)" title="Recalculate all items in this group">
                    <i class="bi bi-arrow-clockwise"></i>
                </button>
                <input type="hidden" name="items[${itemCounter}][is_group]" value="true">
                <input type="hidden" name="items[${itemCounter}][item_number]" value="${groupCounter}">
                <button type="button" class="btn btn-sm btn-success" onclick="addSubItem(this)" title="Add Sub-item">
                    <i class="bi bi-plus"></i> Add Item
                </button>
                <button type="button" class="btn btn-sm btn-danger" onclick="removeItem(this)" title="Remove Group">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </td>
    `;

    tbody.appendChild(row);
    itemCounter++;
}

/**
 * Add a sub-item under a group
 */
function addSubItem(button) {
    const groupRow = button.closest('.group-row');
    const groupId = groupRow.dataset.itemId;
    const groupNumber = groupRow.querySelector('.item-number').textContent;
    const chargeableExtra = parseInt(groupRow.querySelector('.chargeable-extra-input')?.value) || 30;

    // Count existing sub-items for this group
    const existingSubItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);
    const subNumber = existingSubItems.length + 1;

    const tbody = document.getElementById('itemsBody');
    const row = document.createElement('tr');
    row.className = 'item-row sub-item-row';
    row.dataset.itemId = `item-${itemCounter}`;
    row.dataset.parentId = groupId;
    row.dataset.isGroup = 'false';

    row.innerHTML = `
        <td class="item-number" style="padding-left: 30px;">${groupNumber}.${subNumber}</td>
        <td>
            <input type="text" class="form-control form-control-sm particular-input" 
                   name="items[${itemCounter}][particular]" 
                   placeholder="Product description">
            <input type="hidden" name="items[${itemCounter}][parent_id]" value="${groupId}">
            <input type="hidden" name="items[${itemCounter}][is_group]" value="false">
            <input type="hidden" name="items[${itemCounter}][chargeable_extra]" value="${chargeableExtra}">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input actual-width"
                   name="items[${itemCounter}][actual_width]"
                   placeholder="Width" oninput="applyChargeableExtra(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input actual-height"
                   name="items[${itemCounter}][actual_height]"
                   placeholder="Height" oninput="applyChargeableExtra(this)">
        </td>
        <td>
            <select class="form-select form-select-sm" name="items[${itemCounter}][unit]"
                    onchange="calculateItemTotal(this)">
                <option value="MM" selected>MM</option>
                <option value="sqft">sqft</option>
                <option value="pcs">pcs</option>
            </select>
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-width"
                   name="items[${itemCounter}][chargeable_width]"
                   placeholder="Width" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-height"
                   name="items[${itemCounter}][chargeable_height]"
                   placeholder="Height" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm qty-input"
                   name="items[${itemCounter}][quantity]"
                   value="1" min="1" oninput="calculateItemTotal(this)" required>
        </td>
        <td>
            <input type="number" step="0.0001" class="form-control form-control-sm unit-square-display"
                   name="items[${itemCounter}][unit_square]"
                   placeholder="0.0000" readonly>
        </td>
        <td>
            <input type="number" class="form-control form-control-sm hole-input"
                   name="items[${itemCounter}][hole]"
                   value="0" min="0" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm cutout-input"
                   name="items[${itemCounter}][cutout]"
                   value="0" min="0" oninput="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm rate-input"
                   name="items[${itemCounter}][rate_sqper]"
                   placeholder="Rate" oninput="calculateItemTotal(this)" required>
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm total-display" 
                   name="items[${itemCounter}][total]" 
                   placeholder="0.00" readonly>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeItem(this)">
                <i class="bi bi-trash"></i>
            </button>
        </td>
    `;

    // Insert after the group row or after the last sub-item of this group
    if (existingSubItems.length > 0) {
        const lastSubItem = existingSubItems[existingSubItems.length - 1];
        lastSubItem.after(row);
    } else {
        groupRow.after(row);
    }

    // Auto-populate rate from group rate input (covers both manual entry and glass catalog)
    const groupRate = groupRow.querySelector('.group-rate-input')?.value;
    if (groupRate) {
        const rateInput = row.querySelector('.rate-input');
        if (rateInput) rateInput.value = groupRate;
    }

    itemCounter++;
    renumberItems();
}

/**
 * Apply chargeable extra to actual dimensions
 */
function applyChargeableExtra(input) {
    const row = input.closest('.item-row');
    const actualWidth = parseFloat(row.querySelector('.actual-width')?.value) || 0;
    const actualHeight = parseFloat(row.querySelector('.actual-height')?.value) || 0;
    const chargeableExtra = parseInt(row.querySelector('input[name*="[chargeable_extra]"]')?.value) || 30;

    if (actualWidth > 0) {
        row.querySelector('.chargeable-width').value = (actualWidth + chargeableExtra).toFixed(2);
    }
    if (actualHeight > 0) {
        row.querySelector('.chargeable-height').value = (actualHeight + chargeableExtra).toFixed(2);
    }

    calculateItemTotal(input);
}

/**
 * Remove an item (group or sub-item)
 */
function removeItem(button) {
    const row = button.closest('.item-row');
    const isGroup = row.dataset.isGroup === 'true';

    if (isGroup) {
        // Remove group and all its sub-items
        const groupId = row.dataset.itemId;
        const subItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);
        subItems.forEach(item => item.remove());
    }

    row.remove();
    renumberItems();
    updateTotals();
}

/**
 * Calculate total for a single item.
 * - MM/sqft: Area (Sq Mtr) × Rate × Quantity + Hole/Cutout charges
 * - pcs:     Rate × Quantity  (no area — dimensions are ignored)
 */
function calculateItemTotal(input) {
    const row = input.closest('.item-row');

    const chargeableWidth  = parseFloat(row.querySelector('.chargeable-width')?.value)  || 0;
    const chargeableHeight = parseFloat(row.querySelector('.chargeable-height')?.value) || 0;
    const unit     = row.querySelector('select[name*="[unit]"]')?.value || 'MM';
    const quantity = parseInt(row.querySelector('.qty-input')?.value)   || 0;
    const rate     = parseFloat(row.querySelector('.rate-input')?.value) || 0;

    let unitSquare = 0;
    let total      = 0;

    if (unit === 'pcs') {
        // Per-piece: total = rate × qty, no area involved
        total = rate * quantity;
    } else {
        // Area-based: MM or sqft
        if (chargeableWidth && chargeableHeight) {
            unitSquare = unit === 'MM'
                ? (chargeableWidth * chargeableHeight) / 1000000
                : chargeableWidth * chargeableHeight;
        }
        total = unitSquare * rate * quantity;
    }

    // Update unit square display (blank for pcs)
    const unitSquareInput = row.querySelector('.unit-square-display');
    if (unitSquareInput) {
        unitSquareInput.value = unit === 'pcs' ? '' : unitSquare.toFixed(4);
    }

    // Add hole and cutout charges from parent group
    const holes = parseInt(row.querySelector('.hole-input')?.value) || 0;
    const cutouts = parseInt(row.querySelector('.cutout-input')?.value) || 0;

    // Get pricing from parent group row
    const parentId = row.dataset.parentId;
    if (parentId) {
        const groupRow = document.querySelector(`[data-item-id="${parentId}"]`);
        if (groupRow) {
            const holePrice = parseFloat(groupRow.querySelector('.hole-price-input')?.value) || 0;
            const cutoutPrice = parseFloat(groupRow.querySelector('.cutout-price-input')?.value) || 0;
            total += (holes * holePrice) + (cutouts * cutoutPrice);
        }
    }

    // Update total display
    const totalInput = row.querySelector('.total-display');
    if (totalInput) {
        totalInput.value = total.toFixed(2);
    }

    // Calculate jumbo charge for this item based on individual glass area (unitSquare per piece)
    const pctTier1 = parseFloat(document.getElementById('jumbo_pct_tier1')?.value) ?? 10;
    const pctTier2 = parseFloat(document.getElementById('jumbo_pct_tier2')?.value) ?? 15;
    const pctTier3 = parseFloat(document.getElementById('jumbo_pct_tier3')?.value) ?? 20;
    let jumboPercent = 0;
    if (unitSquare >= 7) {
        jumboPercent = pctTier3;
    } else if (unitSquare >= 5.5) {
        jumboPercent = pctTier2;
    } else if (unitSquare >= 4.5) {
        jumboPercent = pctTier1;
    }
    row.dataset.jumboCharge = ((total * jumboPercent) / 100).toFixed(2);

    updateTotals();
}

/**
 * Renumber all items with hierarchical numbering
 */
function renumberItems() {
    const groups = document.querySelectorAll('.group-row');
    let groupNum = 1;

    groups.forEach(group => {
        // Update group number
        group.querySelector('.item-number').textContent = groupNum;
        const groupId = group.dataset.itemId;

        // Update sub-items
        const subItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);
        let subNum = 1;
        subItems.forEach(subItem => {
            subItem.querySelector('.item-number').textContent = `${groupNum}.${subNum}`;
            subNum++;
        });

        groupNum++;
    });
}

/**
 * Update all totals (subtotal, GST, grand total) including new charge fields
 */
function updateTotals() {
    // Calculate subtotal from all sub-items (not groups)
    let subtotal = 0;
    document.querySelectorAll('.sub-item-row .total-display').forEach(input => {
        subtotal += parseFloat(input.value) || 0;
    });

    // Auto-calculate jumbo size charges from per-item jumbo charges
    let jumboSizeCharges = 0;
    document.querySelectorAll('.sub-item-row').forEach(row => {
        jumboSizeCharges += parseFloat(row.dataset.jumboCharge) || 0;
    });
    const jumboField = document.getElementById('jumbo_size_charges');
    if (jumboField) jumboField.value = jumboSizeCharges.toFixed(2);

    // Summarise hole & cutout charges across all sub-items (informational — already in subtotal)
    let totalHolesSummary = 0;
    let totalHolesCount = 0;
    let totalCutoutsSummary = 0;
    let totalCutoutsCount = 0;
    document.querySelectorAll('.sub-item-row').forEach(subRow => {
        const holes   = parseInt(subRow.querySelector('.hole-input')?.value) || 0;
        const cutouts = parseInt(subRow.querySelector('.cutout-input')?.value) || 0;
        if (holes > 0 || cutouts > 0) {
            const parentId = subRow.dataset.parentId;
            const groupRow = parentId ? document.querySelector(`[data-item-id="${parentId}"]`) : null;
            const holePrice   = parseFloat(groupRow?.querySelector('.hole-price-input')?.value) || 0;
            const cutoutPrice = parseFloat(groupRow?.querySelector('.cutout-price-input')?.value) || 0;
            totalHolesCount     += holes;
            totalHolesSummary   += holes * holePrice;
            totalCutoutsCount   += cutouts;
            totalCutoutsSummary += cutouts * cutoutPrice;
        }
    });
    const holesRow  = document.getElementById('row_holes_summary');
    const cutoutRow = document.getElementById('row_cutout_summary');
    if (holesRow) {
        holesRow.style.display = totalHolesSummary > 0 ? '' : 'none';
        const labelEl = holesRow.querySelector('td:first-child');
        if (labelEl) labelEl.innerHTML = `Holes Charges (${totalHolesCount} holes) <small class="text-muted">(incl. in subtotal)</small>:`;
        const el = document.getElementById('disp_holes_summary');
        if (el) el.textContent = totalHolesSummary.toFixed(2);
    }
    if (cutoutRow) {
        cutoutRow.style.display = totalCutoutsSummary > 0 ? '' : 'none';
        const labelEl = cutoutRow.querySelector('td:first-child');
        if (labelEl) labelEl.innerHTML = `Cutout Charges (${totalCutoutsCount} cutouts) <small class="text-muted">(incl. in subtotal)</small>:`;
        const el = document.getElementById('disp_cutout_summary');
        if (el) el.textContent = totalCutoutsSummary.toFixed(2);
    }

    // Handling: % of subtotal — B2B only
    const handlingPctEl = document.getElementById('handling_percentage');
    const handlingPct = parseFloat(handlingPctEl?.value) || 0;
    const handlingCharges = handlingPctEl ? (subtotal * handlingPct) / 100 : 0;
    const handlingField = document.getElementById('handling_charges');
    if (handlingField) handlingField.value = handlingCharges.toFixed(2);
    const handlingHint = document.getElementById('handling_amount_hint');
    if (handlingHint) handlingHint.textContent = handlingPct > 0 ? `= ₹${handlingCharges.toFixed(2)}` : '';

    // Get all charges
    const installationCharges = parseFloat(document.getElementById('installation_charges')?.value) || 0;
    const transportCharges = parseFloat(document.getElementById('transport_charges')?.value) || 0;
    const cutoutCharges = parseFloat(document.getElementById('cutout_charges')?.value) || 0;
    const holesCharges = parseFloat(document.getElementById('holes_charges')?.value) || 0;
    const shapeCuttingCharges = parseFloat(document.getElementById('shape_cutting_charges')?.value) || 0;
    const templateCharges = parseFloat(document.getElementById('template_charges')?.value) || 0;
    const polishCharges = parseFloat(document.getElementById('polish_charges')?.value) || 0;
    const documentCharges = parseFloat(document.getElementById('document_charges')?.value) || 0;
    const frostedCharges = parseFloat(document.getElementById('frosted_charges')?.value) || 0;

    // Insurance: % of subtotal (glass only)
    const insurancePct = parseFloat(document.getElementById('insurance_percentage')?.value) || 0;
    const insuranceCharges = (subtotal * insurancePct) / 100;
    const insuranceField = document.getElementById('insurance_charges');
    if (insuranceField) insuranceField.value = insuranceCharges.toFixed(2);
    const insuranceHint = document.getElementById('insurance_amount_hint');
    if (insuranceHint) insuranceHint.textContent = insurancePct > 0 ? `= ₹${insuranceCharges.toFixed(2)}` : '';

    // Show/hide individual charge rows in Totals panel
    const chargeFields = [
        ['installation_charges', installationCharges],
        ['transport_charges',    transportCharges],
        ['shape_cutting_charges',shapeCuttingCharges],
        ['jumbo_size_charges',   jumboSizeCharges],
        ['template_charges',     templateCharges],
        ['handling_charges',     handlingCharges],
        ['polish_charges',       polishCharges],
        ['document_charges',     documentCharges],
        ['frosted_charges',      frostedCharges],
    ];
    chargeFields.forEach(([key, val]) => {
        const row = document.getElementById(`row_${key}`);
        const el  = document.getElementById(`disp_${key}`);
        if (row) row.style.display = val > 0 ? '' : 'none';
        if (el)  el.textContent    = val.toFixed(2);
    });
    // Insurance row
    const insRow = document.getElementById('row_insurance_charges');
    const insEl  = document.getElementById('disp_insurance_charges');
    const insPctEl = document.getElementById('disp_insurance_pct');
    if (insRow) insRow.style.display = insuranceCharges > 0 ? '' : 'none';
    if (insEl)  insEl.textContent    = insuranceCharges.toFixed(2);
    if (insPctEl) insPctEl.textContent = insurancePct;

    // Calculate extra charges subtotal
    const chargesTotal = installationCharges + transportCharges + cutoutCharges +
        holesCharges + shapeCuttingCharges + jumboSizeCharges +
        templateCharges + handlingCharges + polishCharges + documentCharges + frostedCharges + insuranceCharges;

    // Calculate taxable amount (subtotal + all charges)
    const taxableAmount = subtotal + chargesTotal;

    // Show/hide taxable amount row
    const taxableRow = document.getElementById('taxable_row');
    const taxableEl  = document.getElementById('taxable_display');
    if (taxableRow) taxableRow.style.display = chargesTotal > 0 ? '' : 'none';
    if (taxableEl)  taxableEl.textContent    = taxableAmount.toFixed(2);

    // Calculate GST
    const gstPercentage = parseFloat(document.getElementById('gst_percentage')?.value) || 18;
    const gstAmount = (taxableAmount * gstPercentage) / 100;

    // Calculate total before round-off
    const totalBeforeRoundOff = taxableAmount + gstAmount;

    // Calculate round-off
    const roundedTotal = Math.round(totalBeforeRoundOff);
    const roundOff = roundedTotal - totalBeforeRoundOff;

    // Update displays
    document.getElementById('subtotal_display').textContent = subtotal.toFixed(2);
    document.getElementById('gst_display').textContent = gstAmount.toFixed(2);
    document.getElementById('roundoff_display').textContent = roundOff.toFixed(2);
    document.getElementById('total_display').textContent = roundedTotal.toFixed(2);

    // Update hidden fields
    document.getElementById('subtotal').value = subtotal.toFixed(2);
    document.getElementById('gst_amount').value = gstAmount.toFixed(2);
    document.getElementById('round_off').value = roundOff.toFixed(2);
    document.getElementById('total').value = roundedTotal.toFixed(2);
}

// ── B2C Mode Functions ────────────────────────────────────────────────────────

// Tracks the current rate-column mode for the whole B2C table
let b2cRateMode = 'sqft';  // 'sqft' = Size×Rate,  'qty' = Qty×Rate

/**
 * Called when the column-header dropdown changes (Rate/Sqft ↔ Rate/Qty).
 * Updates column labels and recalculates all rows.
 */
function onB2CRateModeChange(select) {
    b2cRateMode = select.value;

    // Update the Size column header label
    const sizeHeader = document.getElementById('b2cSizeHeader');
    if (sizeHeader) sizeHeader.textContent = b2cRateMode === 'qty' ? 'Qty' : 'Size (Sqft)';

    // Clear all row values and update placeholder
    document.querySelectorAll('#b2cItemsBody .b2c-item-row').forEach(row => {
        const sizeInput  = row.querySelector('.b2c-size');
        const rateInput  = row.querySelector('.b2c-rate');
        const totalInput = row.querySelector('.b2c-total');
        if (sizeInput)  { sizeInput.value = ''; sizeInput.placeholder = b2cRateMode === 'qty' ? 'e.g. 5' : 'e.g. 115'; }
        if (rateInput)  rateInput.value = '';
        if (totalInput) { totalInput.value = ''; totalInput.readOnly = false; }
        calculateB2CItemTotal(rateInput);
    });
}

/**
 * Add a simple B2C line item row (uses shared itemCounter for form field indices).
 */
function addB2CItem(data) {
    const idx    = itemCounter++;
    const tbody  = document.getElementById('b2cItemsBody');
    const rowNum = tbody.children.length + 1;
    const row    = document.createElement('tr');
    row.className = 'b2c-item-row';

    const particular  = data ? data.particular          : '';
    const rate        = data ? (data.rate_sqper || '')  : '';
    const total       = data ? (data.total      || '')  : '';
    // Pick the row's unit from saved data when reloading; otherwise from current mode.
    const initialUnit = (data && data.unit === 'pcs')
        ? 'pcs'
        : (data && data.unit === 'sqft')
            ? 'sqft'
            : (b2cRateMode === 'qty' ? 'pcs' : 'sqft');
    // For qty rows, restore the saved quantity into the Size input;
    // for sqft rows, restore the chargeable width (or computed unit_square as fallback).
    const displaySize = data
        ? (initialUnit === 'pcs'
            ? (data.quantity || '')
            : (data.chargeable_width || data.unit_square || ''))
        : '';
    const initialQty  = (data && initialUnit === 'pcs') ? (data.quantity || 1) : 1;
    const sizePh      = b2cRateMode === 'qty' ? 'e.g. 5' : 'e.g. 115';
    const existingKey = data ? (data.image_s3_key || '') : '';
    const existingUrl = data ? (data.image_presigned_url || '') : '';

    row.innerHTML = `
        <td class="b2c-row-num align-middle text-center">${rowNum}</td>
        <td>
            <textarea class="form-control form-control-sm b2c-particular"
                      name="items[${idx}][particular]"
                      rows="2" placeholder="Product description" required
                      style="resize:vertical; min-height:2.2rem;">${particular}</textarea>
            <input type="hidden" name="items[${idx}][is_group]"  value="false">
            <input type="hidden" name="items[${idx}][quantity]"  value="${initialQty}">
        </td>
        <td class="text-center align-middle">
            <label class="btn btn-outline-secondary btn-sm py-1 px-2 mb-1 d-block" style="font-size:0.75rem;cursor:pointer;" title="Upload product image">
                <i class="bi bi-camera"></i> Upload
                <input type="file" accept="image/*" class="b2c-img-input d-none" onchange="uploadB2CImage(this, ${idx})">
            </label>
            <span class="b2c-img-status d-block" style="font-size:0.7rem;color:#94a3b8;"></span>
            <a class="b2c-img-thumb" href="#" target="_blank" style="display:none;">
                <img style="width:60px;height:60px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;" alt="preview">
            </a>
            <input type="hidden" class="b2c-img-key" name="items[${idx}][image_s3_key]" value="${existingKey}">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm b2c-size"
                   value="${displaySize}" placeholder="${sizePh}"
                   oninput="calculateB2CItemTotal(this)">
            <input type="hidden" class="b2c-cw" name="items[${idx}][chargeable_width]"  value="${initialUnit === 'pcs' ? '' : displaySize}">
            <input type="hidden" class="b2c-ch" name="items[${idx}][chargeable_height]" value="${initialUnit === 'pcs' ? '' : (displaySize ? '1' : '')}">
            <input type="hidden" class="b2c-unit" name="items[${idx}][unit]" value="${initialUnit}">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm b2c-rate"
                   name="items[${idx}][rate_sqper]"
                   value="${rate}" placeholder="Rate"
                   oninput="calculateB2CItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm b2c-total"
                   name="items[${idx}][total]"
                   value="${total}" placeholder="0.00"
                   oninput="updateB2CTotals()">
        </td>
        <td class="text-center align-middle">
            <button type="button" class="btn btn-sm btn-danger" onclick="removeB2CItem(this)">
                <i class="bi bi-trash"></i>
            </button>
        </td>
    `;

    tbody.appendChild(row);

    // If editing and image already exists, show existing thumbnail directly from S3
    if (existingKey) {
        const thumbLink = row.querySelector('.b2c-img-thumb');
        const thumbImg  = thumbLink.querySelector('img');
        const url = existingUrl || `/api/quote-items/image-url?key=${encodeURIComponent(existingKey)}`;
        thumbLink.href          = url;
        thumbImg.src            = url;
        thumbLink.style.display = 'inline-block';
    }

    if (displaySize && rate) {
        row.querySelector('.b2c-total').readOnly = true;
        row.querySelector('.b2c-total').classList.add('bg-light');
    }

    updateB2CTotals();
}

function uploadB2CImage(input, idx) {
    const file = input.files[0];
    if (!file) return;

    const row      = input.closest('.b2c-item-row');
    const statusEl = row.querySelector('.b2c-img-status');
    const thumbEl  = row.querySelector('.b2c-img-thumb');
    const thumbImg = thumbEl.querySelector('img');
    const keyInput = row.querySelector('.b2c-img-key');

    statusEl.textContent = 'Uploading…';
    thumbEl.style.display = 'none';

    const fd = new FormData();
    fd.append('image', file);

    fetch('/api/quote-items/upload-image', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                keyInput.value  = data.s3_key;
                thumbImg.src    = data.presigned_url;
                thumbEl.href    = data.presigned_url;
                thumbEl.style.display = 'inline-block';
                statusEl.textContent = '';
            } else {
                statusEl.textContent = 'Upload failed';
                statusEl.style.color = '#ef4444';
            }
        })
        .catch(() => {
            statusEl.textContent = 'Upload failed';
            statusEl.style.color = '#ef4444';
        });
}

/**
 * Auto-calculate B2C row total.
 * sqft mode: Size × Rate = Total  (submitted as chargeable_width=size, height=1, unit=sqft)
 * qty  mode: Qty  × Rate = Total  (submitted as quantity=qty, no chargeable dims, unit=pcs)
 */
function calculateB2CItemTotal(input) {
    if (!input) return;
    const row        = input.closest('.b2c-item-row');
    if (!row) return;
    const sizeVal    = parseFloat(row.querySelector('.b2c-size')?.value)  || 0;
    const rate       = parseFloat(row.querySelector('.b2c-rate')?.value)  || 0;
    const totalInput = row.querySelector('.b2c-total');

    // Keep hidden backend fields in sync with current mode
    const isQty = b2cRateMode === 'qty';
    const cwEl  = row.querySelector('.b2c-cw');
    const chEl  = row.querySelector('.b2c-ch');
    const unitEl = row.querySelector('.b2c-unit');
    const qtyEl  = row.querySelector('input[name*="[quantity]"]');

    if (isQty) {
        if (cwEl)   cwEl.value  = '';
        if (chEl)   chEl.value  = '';
        if (unitEl) unitEl.value = 'pcs';
        if (qtyEl)  qtyEl.value  = sizeVal || 1;
    } else {
        if (cwEl)   cwEl.value   = sizeVal || '';
        if (chEl)   chEl.value   = sizeVal ? '1' : '';
        if (unitEl) unitEl.value = 'sqft';
        if (qtyEl)  qtyEl.value  = 1;
    }

    if (sizeVal > 0 && rate > 0) {
        totalInput.value    = (sizeVal * rate).toFixed(2);
        totalInput.readOnly = true;
        totalInput.classList.add('bg-light');
    } else {
        totalInput.readOnly = false;
        totalInput.classList.remove('bg-light');
    }

    updateB2CTotals();
}

/**
 * Remove a B2C row and renumber.
 */
function removeB2CItem(button) {
    button.closest('.b2c-item-row').remove();
    document.querySelectorAll('#b2cItemsBody .b2c-item-row').forEach((r, i) => {
        r.querySelector('.b2c-row-num').textContent = i + 1;
    });
    updateB2CTotals();
}

/**
 * Toggle B2C GST % input visibility when Apply GST checkbox is changed.
 */
function onB2CGstToggle() {
    const applyGst = document.getElementById('b2c_apply_gst')?.checked;
    const wrapper  = document.getElementById('b2c_gst_pct_wrapper');
    if (wrapper) wrapper.style.display = applyGst ? '' : 'none';
    updateB2CTotals();
}

/**
 * Recalculate subtotal, SGST, CGST, round-off, grand total for B2C.
 * Shows individual charge rows in the Totals panel (same as B2B).
 * Respects Apply GST toggle and editable GST %.
 */
function updateB2CTotals() {
    // Glass items subtotal only
    let subtotal = 0;
    document.querySelectorAll('#b2cItemsBody .b2c-total').forEach(inp => {
        subtotal += parseFloat(inp.value) || 0;
    });

    // B2C additional charges — kept separate so they show individually
    const installCharges  = parseFloat(document.getElementById('b2c_installation_charges')?.value) || 0;
    const transportCharges = parseFloat(document.getElementById('b2c_transport_charges')?.value)   || 0;
    const handlingCharges  = parseFloat(document.getElementById('b2c_handling_charges')?.value)    || 0;
    const chargesTotal     = installCharges + transportCharges + handlingCharges;
    const taxableAmount    = subtotal + chargesTotal;

    // Show individual charge rows in shared Totals panel
    const b2cChargeFields = [
        ['installation_charges', installCharges],
        ['transport_charges',    transportCharges],
        ['handling_charges',     handlingCharges],
    ];
    b2cChargeFields.forEach(([key, val]) => {
        const row = document.getElementById(`row_${key}`);
        const el  = document.getElementById(`disp_${key}`);
        if (row) row.style.display = val > 0 ? '' : 'none';
        if (el)  el.textContent    = val.toFixed(2);
    });

    // Show/hide Taxable Amount row
    const taxableRow = document.getElementById('taxable_row');
    const taxableEl  = document.getElementById('taxable_display');
    if (taxableRow) taxableRow.style.display = chargesTotal > 0 ? '' : 'none';
    if (taxableEl)  taxableEl.textContent    = taxableAmount.toFixed(2);

    const applyGst = document.getElementById('b2c_apply_gst')?.checked !== false;
    const gstPct   = parseFloat(document.getElementById('b2c_gst_pct')?.value) || 0;
    const halfPct  = gstPct / 2;

    const sgst     = (applyGst && gstPct > 0) ? (taxableAmount * halfPct / 100) : 0;
    const cgst     = (applyGst && gstPct > 0) ? (taxableAmount * halfPct / 100) : 0;
    const preRound = taxableAmount + sgst + cgst;
    const rounded  = Math.round(preRound);
    const roundOff = rounded - preRound;

    // Update SGST/CGST labels with actual rate
    const sgstLabel = document.getElementById('b2c_sgst_label');
    const cgstLabel = document.getElementById('b2c_cgst_label');
    if (sgstLabel) sgstLabel.textContent = `SGST @${halfPct}%`;
    if (cgstLabel) cgstLabel.textContent = `CGST @${halfPct}%`;

    // Show/hide SGST+CGST rows based on toggle + %
    const showGst = applyGst && gstPct > 0;
    document.getElementById('b2c_sgst_row').style.display = showGst ? '' : 'none';
    document.getElementById('b2c_cgst_row').style.display = showGst ? '' : 'none';

    document.getElementById('subtotal_display').textContent = subtotal.toFixed(2);
    document.getElementById('sgst_display').textContent     = sgst.toFixed(2);
    document.getElementById('cgst_display').textContent     = cgst.toFixed(2);
    document.getElementById('roundoff_display').textContent = roundOff.toFixed(2);
    document.getElementById('total_display').textContent    = rounded.toFixed(2);

    // subtotal hidden field = glass items only (charges stored in their own columns)
    document.getElementById('subtotal').value   = subtotal.toFixed(2);
    document.getElementById('gst_amount').value = (sgst + cgst).toFixed(2);
    document.getElementById('round_off').value  = roundOff.toFixed(2);
    document.getElementById('total').value      = rounded.toFixed(2);

    // Sync the gst_percentage field (submitted with the form)
    const gstPctField = document.getElementById('gst_percentage');
    if (gstPctField) gstPctField.value = (applyGst && gstPct > 0) ? gstPct : 0;
}

/**
 * Load existing B2C items when editing.
 */
function loadB2CItems(items) {
    items.forEach(item => addB2CItem(item));
}

/**
 * Pre-submit: for fixed-amount B2C rows (no size/qty entered, total filled manually),
 * copy total → rate_sqper so backend calculates: total = 1 × rate_sqper = total.
 */
document.getElementById('quoteForm')?.addEventListener('submit', function () {
    document.querySelectorAll('#b2cItemsBody .b2c-item-row').forEach(row => {
        const sizeVal = parseFloat(row.querySelector('.b2c-size')?.value)  || 0;
        const rateVal = parseFloat(row.querySelector('.b2c-rate')?.value)  || 0;
        if (sizeVal === 0 && rateVal === 0) {
            const total     = parseFloat(row.querySelector('.b2c-total')?.value) || 0;
            const rateInput = row.querySelector('.b2c-rate');
            if (rateInput) rateInput.value = total;
        }
    });
});

// ── End B2C ──────────────────────────────────────────────────────────────────

/**
 * Propagate the group rate to all existing sub-items and recalculate their totals.
 * Called whenever the group Rate (₹/sqm) input changes.
 */
function propagateGroupRate(input) {
    const groupRow = input.closest('.group-row');
    const groupId = groupRow.dataset.itemId;
    const rate = input.value;

    document.querySelectorAll(`[data-parent-id="${groupId}"]`).forEach(subItem => {
        const rateInput = subItem.querySelector('.rate-input');
        if (rateInput) {
            rateInput.value = rate;
            calculateItemTotal(rateInput);
        }
    });
}

/**
 * Recalculate all sub-items when group-level values change
 * This function is called when the refresh button is clicked
 */
function recalculateGroupItems(button) {
    const groupRow = button.closest('.group-row');
    const groupId = groupRow.dataset.itemId;

    const chargeableExtra = parseFloat(groupRow.querySelector('.chargeable-extra-input').value) || 30;
    const groupRate = groupRow.querySelector('.group-rate-input')?.value;

    const subItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);

    subItems.forEach(subItem => {
        // Update chargeable dimensions from actual + extra
        const actualWidth = parseFloat(subItem.querySelector('.actual-width')?.value) || 0;
        const actualHeight = parseFloat(subItem.querySelector('.actual-height')?.value) || 0;

        if (actualWidth > 0 && actualHeight > 0) {
            const cw = subItem.querySelector('.chargeable-width');
            const ch = subItem.querySelector('.chargeable-height');
            if (cw) cw.value = actualWidth + chargeableExtra;
            if (ch) ch.value = actualHeight + chargeableExtra;
        }

        // Propagate group rate to sub-item if group rate is set
        if (groupRate) {
            const rateInput = subItem.querySelector('.rate-input');
            if (rateInput) rateInput.value = groupRate;
        }

        const anyInput = subItem.querySelector('.qty-input');
        if (anyInput) calculateItemTotal(anyInput);
    });

    // Brief visual feedback
    button.classList.add('btn-success');
    button.classList.remove('btn-primary');
    setTimeout(() => {
        button.classList.remove('btn-success');
        button.classList.add('btn-primary');
    }, 500);
}
