// Quote Form JavaScript
// Handles dynamic item rows and auto-calculations

let itemCounter = parseInt(document.getElementById('item_count').value) || 1;

// Add new item row
function addItem() {
    const tbody = document.getElementById('itemsBody');
    const newRow = document.createElement('tr');
    newRow.className = 'item-row';
    newRow.setAttribute('data-item-index', itemCounter);

    newRow.innerHTML = `
        <td>${itemCounter + 1}</td>
        <td><input type="text" class="form-control form-control-sm" name="item_${itemCounter}_particular" required></td>
        <td><input type="text" class="form-control form-control-sm" name="item_${itemCounter}_size_width"></td>
        <td><input type="text" class="form-control form-control-sm" name="item_${itemCounter}_size_height"></td>
        <td><input type="text" class="form-control form-control-sm" name="item_${itemCounter}_unit" placeholder="MM"></td>
        <td><input type="number" class="form-control form-control-sm item-qty" name="item_${itemCounter}_quantity" value="1" min="1" required></td>
        <td><input type="number" step="0.01" class="form-control form-control-sm item-rate" name="item_${itemCounter}_rate" required></td>
        <td><input type="number" step="0.01" class="form-control form-control-sm item-total" name="item_${itemCounter}_total" readonly></td>
        <td><button type="button" class="btn btn-sm btn-danger" onclick="removeItem(this)"><i class="bi bi-trash"></i></button></td>
    `;

    tbody.appendChild(newRow);
    itemCounter++;
    document.getElementById('item_count').value = itemCounter;

    // Attach event listeners to new row
    attachItemEventListeners(newRow);
    updateTotals();
}

// Remove item row
function removeItem(button) {
    const row = button.closest('tr');
    row.remove();
    renumberItems();
    updateTotals();
}

// Renumber items after deletion
function renumberItems() {
    const rows = document.querySelectorAll('#itemsBody tr');
    rows.forEach((row, index) => {
        row.querySelector('td:first-child').textContent = index + 1;
    });
}

// Attach event listeners to item inputs
function attachItemEventListeners(row) {
    const qtyInput = row.querySelector('.item-qty');
    const rateInput = row.querySelector('.item-rate');

    if (qtyInput) {
        qtyInput.addEventListener('input', function () {
            calculateItemTotal(row);
        });
    }

    if (rateInput) {
        rateInput.addEventListener('input', function () {
            calculateItemTotal(row);
        });
    }
}

// Calculate total for a single item
function calculateItemTotal(row) {
    const qty = parseFloat(row.querySelector('.item-qty').value) || 0;
    const rate = parseFloat(row.querySelector('.item-rate').value) || 0;
    const total = qty * rate;

    row.querySelector('.item-total').value = total.toFixed(2);
    updateTotals();
}

// Update all totals
function updateTotals() {
    // Calculate subtotal from all items
    let subtotal = 0;
    document.querySelectorAll('.item-total').forEach(input => {
        subtotal += parseFloat(input.value) || 0;
    });

    // Get charges
    const deliveryCharges = parseFloat(document.querySelector('[name="delivery_charges"]').value) || 0;
    const installationCharges = parseFloat(document.querySelector('[name="installation_charges"]').value) || 0;
    const freightCharges = parseFloat(document.querySelector('[name="freight_charges"]').value) || 0;
    const transportCharges = parseFloat(document.querySelector('[name="transport_charges"]').value) || 0;

    // Calculate taxable amount
    const taxableAmount = subtotal + deliveryCharges + installationCharges + freightCharges + transportCharges;

    // Get GST percentage
    const gstPercentage = parseFloat(document.getElementById('gst_percentage').value) || 18;
    const gstAmount = (taxableAmount * gstPercentage) / 100;

    // Calculate total before round-off
    const totalBeforeRoundoff = taxableAmount + gstAmount;

    // Calculate round-off
    const roundedTotal = Math.round(totalBeforeRoundoff);
    const roundOff = roundedTotal - totalBeforeRoundoff;

    // Update display
    document.getElementById('subtotal').textContent = '₹' + subtotal.toFixed(2);
    document.getElementById('gst_percent').textContent = gstPercentage.toFixed(2);
    document.getElementById('gst_amount').textContent = '₹' + gstAmount.toFixed(2);
    document.getElementById('round_off').textContent = '₹' + roundOff.toFixed(2);
    document.getElementById('total').textContent = '₹' + roundedTotal.toFixed(2);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    // Attach event listeners to existing items
    document.querySelectorAll('#itemsBody tr').forEach(row => {
        attachItemEventListeners(row);
    });

    // Attach event listeners to charge inputs
    document.querySelectorAll('.charge-input').forEach(input => {
        input.addEventListener('input', updateTotals);
    });

    // Attach event listener to GST percentage
    document.getElementById('gst_percentage').addEventListener('input', updateTotals);

    // Initial calculation
    updateTotals();
});
