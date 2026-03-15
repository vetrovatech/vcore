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
                        <label class="form-label mb-0" style="white-space: nowrap;">Chargeable Extra (MM):</label>
                        <input type="number" class="form-control form-control-sm chargeable-extra-input" 
                               name="items[${itemCounter}][chargeable_extra]" 
                               value="${item.chargeable_extra || 30}"
                               style="width: 80px;" min="0">
                        <label class="form-label mb-0" style="white-space: nowrap;">Hole Price:</label>
                        <input type="number" step="0.01" class="form-control form-control-sm hole-price-input" 
                               name="items[${itemCounter}][hole_price]" 
                               value="${item.hole_price || 400}"
                               style="width: 80px;" min="0">
                        <label class="form-label mb-0" style="white-space: nowrap;">Cutout Price:</label>
                        <input type="number" step="0.01" class="form-control form-control-sm cutout-price-input" 
                               name="items[${itemCounter}][cutout_price]" 
                               value="${item.cutout_price || 100}"
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
                   placeholder="Width" onchange="applyChargeableExtra(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input actual-height" 
                   name="items[${itemCounter}][actual_height]" 
                   value="${data.actual_height || ''}"
                   placeholder="Height" onchange="applyChargeableExtra(this)">
        </td>
        <td>
            <select class="form-select form-select-sm" name="items[${itemCounter}][unit]">
                <option value="MM" ${data.unit === 'MM' ? 'selected' : ''}>MM</option>
                <option value="sqft" ${data.unit === 'sqft' ? 'selected' : ''}>sqft</option>
                <option value="pcs" ${data.unit === 'pcs' ? 'selected' : ''}>pcs</option>
            </select>
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-width" 
                   name="items[${itemCounter}][chargeable_width]" 
                   value="${data.chargeable_width || ''}"
                   placeholder="Width" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-height" 
                   name="items[${itemCounter}][chargeable_height]" 
                   value="${data.chargeable_height || ''}"
                   placeholder="Height" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm qty-input" 
                   name="items[${itemCounter}][quantity]" 
                   value="${data.quantity}"
                   min="1" onchange="calculateItemTotal(this)" required>
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
                   min="0" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm cutout-input" 
                   name="items[${itemCounter}][cutout]" 
                   value="${data.cutout || 0}"
                   min="0" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm rate-input" 
                   name="items[${itemCounter}][rate_sqper]" 
                   value="${data.rate_sqper}"
                   placeholder="Rate" onchange="calculateItemTotal(this)" required>
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
                <label class="form-label mb-0" style="white-space: nowrap;">Chargeable Extra (MM):</label>
                <input type="number" class="form-control form-control-sm chargeable-extra-input" 
                       name="items[${itemCounter}][chargeable_extra]" 
                       value="30"
                       style="width: 80px;" min="0">
                <label class="form-label mb-0" style="white-space: nowrap;">Hole Price:</label>
                <input type="number" step="0.01" class="form-control form-control-sm hole-price-input" 
                       name="items[${itemCounter}][hole_price]" 
                       value="400"
                       style="width: 80px;" min="0">
                <label class="form-label mb-0" style="white-space: nowrap;">Cutout Price:</label>
                <input type="number" step="0.01" class="form-control form-control-sm cutout-price-input" 
                       name="items[${itemCounter}][cutout_price]" 
                       value="100"
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
                   placeholder="Width" onchange="applyChargeableExtra(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input actual-height" 
                   name="items[${itemCounter}][actual_height]" 
                   placeholder="Height" onchange="applyChargeableExtra(this)">
        </td>
        <td>
            <select class="form-select form-select-sm" name="items[${itemCounter}][unit]">
                <option value="MM" selected>MM</option>
                <option value="sqft">sqft</option>
                <option value="pcs">pcs</option>
            </select>
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-width" 
                   name="items[${itemCounter}][chargeable_width]" 
                   placeholder="Width" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm size-input chargeable-height" 
                   name="items[${itemCounter}][chargeable_height]" 
                   placeholder="Height" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm qty-input" 
                   name="items[${itemCounter}][quantity]" 
                   value="1" min="1" onchange="calculateItemTotal(this)" required>
        </td>
        <td>
            <input type="number" step="0.0001" class="form-control form-control-sm unit-square-display" 
                   name="items[${itemCounter}][unit_square]" 
                   placeholder="0.0000" readonly>
        </td>
        <td>
            <input type="number" class="form-control form-control-sm hole-input" 
                   name="items[${itemCounter}][hole]" 
                   value="0" min="0" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" class="form-control form-control-sm cutout-input" 
                   name="items[${itemCounter}][cutout]" 
                   value="0" min="0" onchange="calculateItemTotal(this)">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm rate-input" 
                   name="items[${itemCounter}][rate_sqper]" 
                   placeholder="Rate" onchange="calculateItemTotal(this)" required>
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

    // Auto-populate rate if group has stored rate from glass catalog selection
    const storedRate = groupRow.dataset.ratePerSqm;
    if (storedRate) {
        const rateInput = row.querySelector('.rate-input');
        if (rateInput) {
            rateInput.value = storedRate;
        }
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
 * Calculate total for a single item using: Area (Sq Mtr) × Rate / Sq Mtr × Quantity + Hole/Cutout charges
 */
function calculateItemTotal(input) {
    const row = input.closest('.item-row');

    // Calculate unit square from chargeable dimensions
    const chargeableWidth = parseFloat(row.querySelector('.chargeable-width')?.value) || 0;
    const chargeableHeight = parseFloat(row.querySelector('.chargeable-height')?.value) || 0;
    const unit = row.querySelector('select[name*="[unit]"]')?.value || 'MM';

    let unitSquare = 0;
    if (chargeableWidth && chargeableHeight) {
        if (unit === 'MM') {
            // Convert MM² to M² (Sq Mtr)
            unitSquare = (chargeableWidth * chargeableHeight) / 1000000;
        } else {
            unitSquare = chargeableWidth * chargeableHeight;
        }
    }

    // Update unit square display
    const unitSquareInput = row.querySelector('.unit-square-display');
    if (unitSquareInput) {
        unitSquareInput.value = unitSquare.toFixed(4);
    }

    // Calculate base total: Area (Sq Mtr) × Rate / Sq Mtr × Quantity
    const quantity = parseInt(row.querySelector('.qty-input')?.value) || 0;
    const rate = parseFloat(row.querySelector('.rate-input')?.value) || 0;
    let total = unitSquare * rate * quantity;

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

    // Get all charges
    const installationCharges = parseFloat(document.getElementById('installation_charges')?.value) || 0;
    const transportCharges = parseFloat(document.getElementById('transport_charges')?.value) || 0;
    const cutoutCharges = parseFloat(document.getElementById('cutout_charges')?.value) || 0;
    const holesCharges = parseFloat(document.getElementById('holes_charges')?.value) || 0;
    const shapeCuttingCharges = parseFloat(document.getElementById('shape_cutting_charges')?.value) || 0;
    const templateCharges = parseFloat(document.getElementById('template_charges')?.value) || 0;
    const handlingCharges = parseFloat(document.getElementById('handling_charges')?.value) || 0;
    const polishCharges = parseFloat(document.getElementById('polish_charges')?.value) || 0;
    const documentCharges = parseFloat(document.getElementById('document_charges')?.value) || 0;
    const frostedCharges = parseFloat(document.getElementById('frosted_charges')?.value) || 0;

    // Calculate taxable amount (subtotal + all charges)
    const taxableAmount = subtotal + installationCharges + transportCharges + cutoutCharges +
        holesCharges + shapeCuttingCharges + jumboSizeCharges +
        templateCharges + handlingCharges + polishCharges + documentCharges + frostedCharges;

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
    const displaySize = data ? (data.chargeable_width || data.unit_square || '') : '';
    const sizePh      = b2cRateMode === 'qty' ? 'e.g. 5' : 'e.g. 115';

    row.innerHTML = `
        <td class="b2c-row-num align-middle text-center">${rowNum}</td>
        <td>
            <input type="text" class="form-control form-control-sm b2c-particular"
                   name="items[${idx}][particular]"
                   value="${particular}" placeholder="Product description" required>
            <input type="hidden" name="items[${idx}][is_group]"  value="false">
            <input type="hidden" name="items[${idx}][quantity]"  value="1">
        </td>
        <td>
            <input type="number" step="0.01" class="form-control form-control-sm b2c-size"
                   value="${displaySize}" placeholder="${sizePh}"
                   oninput="calculateB2CItemTotal(this)">
            <input type="hidden" class="b2c-cw" name="items[${idx}][chargeable_width]"  value="${displaySize}">
            <input type="hidden" class="b2c-ch" name="items[${idx}][chargeable_height]" value="${displaySize ? '1' : ''}">
            <input type="hidden" class="b2c-unit" name="items[${idx}][unit]" value="sqft">
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

    if (displaySize && rate) {
        row.querySelector('.b2c-total').readOnly = true;
        row.querySelector('.b2c-total').classList.add('bg-light');
    }

    updateB2CTotals();
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
 * Recalculate subtotal, SGST @9%, CGST @9%, round-off, grand total for B2C.
 * Includes Installation, Transport and Handling charges.
 */
function updateB2CTotals() {
    let subtotal = 0;
    document.querySelectorAll('#b2cItemsBody .b2c-total').forEach(inp => {
        subtotal += parseFloat(inp.value) || 0;
    });

    // Add B2C additional charges
    subtotal += parseFloat(document.getElementById('b2c_installation_charges')?.value) || 0;
    subtotal += parseFloat(document.getElementById('b2c_transport_charges')?.value)    || 0;
    subtotal += parseFloat(document.getElementById('b2c_handling_charges')?.value)     || 0;

    const sgst     = subtotal * 0.09;
    const cgst     = subtotal * 0.09;
    const preRound = subtotal + sgst + cgst;
    const rounded  = Math.round(preRound);
    const roundOff = rounded - preRound;

    document.getElementById('subtotal_display').textContent = subtotal.toFixed(2);
    document.getElementById('sgst_display').textContent     = sgst.toFixed(2);
    document.getElementById('cgst_display').textContent     = cgst.toFixed(2);
    document.getElementById('roundoff_display').textContent = roundOff.toFixed(2);
    document.getElementById('total_display').textContent    = rounded.toFixed(2);

    document.getElementById('subtotal').value   = subtotal.toFixed(2);
    document.getElementById('gst_amount').value = (sgst + cgst).toFixed(2);
    document.getElementById('round_off').value  = roundOff.toFixed(2);
    document.getElementById('total').value      = rounded.toFixed(2);

    const gstPct = document.getElementById('gst_percentage');
    if (gstPct) gstPct.value = 18;
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
 * Recalculate all sub-items when group-level values change
 * This function is called when the refresh button is clicked
 */
function recalculateGroupItems(button) {
    const groupRow = button.closest('.group-row');
    const groupId = groupRow.dataset.itemId;

    // Get the group-level values
    const chargeableExtra = parseFloat(groupRow.querySelector('.chargeable-extra-input').value) || 30;
    const holePrice = parseFloat(groupRow.querySelector('.hole-price-input').value) || 0;
    const cutoutPrice = parseFloat(groupRow.querySelector('.cutout-price-input').value) || 0;

    // Find all sub-items for this group
    const subItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);

    // Recalculate each sub-item
    subItems.forEach(subItem => {
        // Update chargeable dimensions based on actual dimensions and chargeable extra
        const actualWidthInput = subItem.querySelector('.actual-width');
        const actualHeightInput = subItem.querySelector('.actual-height');
        const actualWidth = parseFloat(actualWidthInput?.value) || 0;
        const actualHeight = parseFloat(actualHeightInput?.value) || 0;

        if (actualWidth > 0 && actualHeight > 0) {
            const chargeableWidthInput = subItem.querySelector('.chargeable-width');
            const chargeableHeightInput = subItem.querySelector('.chargeable-height');

            if (chargeableWidthInput && chargeableHeightInput) {
                chargeableWidthInput.value = actualWidth + chargeableExtra;
                chargeableHeightInput.value = actualHeight + chargeableExtra;
            }
        }

        // Trigger recalculation of the total
        const anyInput = subItem.querySelector('.qty-input');
        if (anyInput) {
            calculateItemTotal(anyInput);
        }
    });

    // Show a brief visual feedback
    button.classList.add('btn-success');
    button.classList.remove('btn-primary');
    setTimeout(() => {
        button.classList.remove('btn-success');
        button.classList.add('btn-primary');
    }, 500);
}
