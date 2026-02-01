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
        // Load existing items
        loadExistingItems(window.existingQuoteData.items);
    } else {
        // Add first group if no items exist (new quote)
        addGroup();
    }

    // Update totals
    updateTotals();

    // Add event listeners for charges
    document.querySelectorAll('.charge-input').forEach(input => {
        input.addEventListener('input', updateTotals);
    });

    document.getElementById('gst_percentage').addEventListener('input', updateTotals);
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

    // Get all charges

    const installationCharges = parseFloat(document.getElementById('installation_charges')?.value) || 0;
    const transportCharges = parseFloat(document.getElementById('transport_charges')?.value) || 0;
    const cutoutCharges = parseFloat(document.getElementById('cutout_charges')?.value) || 0;
    const holesCharges = parseFloat(document.getElementById('holes_charges')?.value) || 0;
    const shapeCuttingCharges = parseFloat(document.getElementById('shape_cutting_charges')?.value) || 0;
    const jumboSizeCharges = parseFloat(document.getElementById('jumbo_size_charges')?.value) || 0;
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
