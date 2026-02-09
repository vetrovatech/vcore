/**
 * Glass Catalog Integration for Quote Form
 * Allows users to browse and select glass types from the catalog
 * Auto-populates pricing information
 */

let glassTypesData = [];
let currentGroupRow = null;

// Load glass types on page load
document.addEventListener('DOMContentLoaded', function () {
    loadGlassTypes();
});

/**
 * Load glass types from API
 */
async function loadGlassTypes() {
    try {
        const response = await fetch('/api/glass-types');
        glassTypesData = await response.json();

        // Populate category filter
        const categories = [...new Set(glassTypesData.map(gt => gt.category).filter(c => c))];
        const categoryFilter = document.getElementById('catalogCategoryFilter');
        if (categoryFilter) {
            categories.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat;
                option.textContent = cat;
                categoryFilter.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading glass types:', error);
    }
}

/**
 * Open glass catalog modal
 */
function openGlassCatalogModal(button) {
    currentGroupRow = button.closest('.group-row');
    renderCatalogTable(glassTypesData);

    const modal = new bootstrap.Modal(document.getElementById('glassCatalogModal'));
    modal.show();
}

/**
 * Render catalog table
 */
function renderCatalogTable(data) {
    const tbody = document.getElementById('catalogTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No glass types found</td></tr>';
        return;
    }

    data.forEach(glassType => {
        const row = document.createElement('tr');
        row.style.cursor = 'pointer';
        row.innerHTML = `
            <td>
                <strong>${escapeHtml(glassType.name)}</strong>
                ${glassType.is_frosted ? '<span class="badge bg-info ms-1">Frosted</span>' : ''}
                ${glassType.is_tinted ? '<span class="badge bg-warning ms-1">Tinted</span>' : ''}
            </td>
            <td>${glassType.category || '-'}</td>
            <td>${glassType.thickness_mm ? glassType.thickness_mm + ' mm' : '-'}</td>
            <td>${glassType.suppliers.length} supplier(s)</td>
            <td>
                ${glassType.best_price ? '<strong class="text-success">₹' + glassType.best_price.toFixed(2) + '/sqm</strong>' : '<span class="text-muted">-</span>'}
            </td>
            <td>
                <button type="button" class="btn btn-sm btn-primary select-glass-btn" data-glass-type='${JSON.stringify(glassType)}'>
                    <i class="bi bi-check-circle"></i> Select
                </button>
            </td>
        `;

        // Add click handler for the select button
        const selectBtn = row.querySelector('.select-glass-btn');
        selectBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            const glassTypeData = JSON.parse(this.dataset.glassType);
            selectGlassType(glassTypeData);
        });

        tbody.appendChild(row);
    });
}

/**
 * Select glass type and show supplier options
 */
function selectGlassType(glassType) {
    if (glassType.suppliers.length === 0) {
        alert('No pricing available for this glass type');
        return;
    }

    if (glassType.suppliers.length === 1) {
        // Auto-select if only one supplier
        applyGlassTypeToGroup(glassType, glassType.suppliers[0]);
        bootstrap.Modal.getInstance(document.getElementById('glassCatalogModal')).hide();
    } else {
        // Show supplier selection modal
        showSupplierPricingModal(glassType);
    }
}

/**
 * Show supplier pricing modal
 */
function showSupplierPricingModal(glassType) {
    const list = document.getElementById('supplierPricingList');
    if (!list) return;

    list.innerHTML = '';

    // Sort suppliers by price (lowest first)
    const sortedSuppliers = [...glassType.suppliers].sort((a, b) => a.rate_per_sqm - b.rate_per_sqm);

    sortedSuppliers.forEach((supplier, index) => {
        const card = document.createElement('div');
        card.className = 'card mb-2';
        if (index === 0) {
            card.classList.add('border-success');
        }

        card.innerHTML = `
            <div class="card-body">
                <div class="row align-items-center">
                    <div class="col-md-4">
                        <strong>${escapeHtml(supplier.supplier_name)}</strong>
                        ${index === 0 ? '<span class="badge bg-success ms-2">Best Price</span>' : ''}
                    </div>
                    <div class="col-md-3">
                        <div><strong class="text-success">₹${supplier.rate_per_sqm.toFixed(2)}/sqm</strong></div>
                        ${supplier.lead_time_days ? '<small class="text-muted">' + supplier.lead_time_days + ' days lead time</small>' : ''}
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">
                            Hole: ₹${supplier.hole_price.toFixed(2)}<br>
                            Cutout: ₹${supplier.cutout_price.toFixed(2)}
                        </small>
                    </div>
                    <div class="col-md-2">
                        <button type="button" class="btn btn-sm btn-primary select-supplier-btn" 
                                data-glass-type='${JSON.stringify(glassType)}' 
                                data-supplier='${JSON.stringify(supplier)}'>
                            <i class="bi bi-check-circle"></i> Select
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Add click handler
        const selectBtn = card.querySelector('.select-supplier-btn');
        selectBtn.addEventListener('click', function () {
            const glassTypeData = JSON.parse(this.dataset.glassType);
            const supplierData = JSON.parse(this.dataset.supplier);
            applyGlassTypeToGroup(glassTypeData, supplierData);
        });

        list.appendChild(card);
    });

    // Update modal title
    document.getElementById('supplierPricingModalTitle').textContent = `Select Supplier for ${glassType.name}`;

    // Hide catalog modal and show supplier modal
    bootstrap.Modal.getInstance(document.getElementById('glassCatalogModal')).hide();
    const supplierModal = new bootstrap.Modal(document.getElementById('supplierPricingModal'));
    supplierModal.show();
}

/**
 * Apply glass type and pricing to group
 */
function applyGlassTypeToGroup(glassType, supplier) {
    if (!currentGroupRow) return;

    // Set particular (group name)
    const particularInput = currentGroupRow.querySelector('.particular-input');
    if (particularInput) {
        particularInput.value = glassType.name;
    }

    // Set hole and cutout prices
    const holePriceInput = currentGroupRow.querySelector('.hole-price-input');
    const cutoutPriceInput = currentGroupRow.querySelector('.cutout-price-input');

    if (holePriceInput) holePriceInput.value = supplier.hole_price.toFixed(2);
    if (cutoutPriceInput) cutoutPriceInput.value = supplier.cutout_price.toFixed(2);

    // Store glass type ID, supplier ID, and rate for reference
    currentGroupRow.dataset.glassTypeId = glassType.id;
    currentGroupRow.dataset.supplierId = supplier.supplier_id;
    currentGroupRow.dataset.supplierName = supplier.supplier_name;
    currentGroupRow.dataset.ratePerSqm = supplier.rate_per_sqm.toFixed(2);

    // Add supplier badge next to particular input
    addSupplierBadge(currentGroupRow, supplier.supplier_name);

    // Auto-populate rate in existing sub-items
    const groupId = currentGroupRow.dataset.itemId;
    const existingSubItems = document.querySelectorAll(`[data-parent-id="${groupId}"]`);
    existingSubItems.forEach(subItem => {
        const rateInput = subItem.querySelector('.rate-input');
        if (rateInput && !rateInput.value) {
            rateInput.value = supplier.rate_per_sqm.toFixed(2);
            // Trigger calculation
            calculateItemTotal(rateInput);
        }
    });

    // Close modals
    const catalogModal = bootstrap.Modal.getInstance(document.getElementById('glassCatalogModal'));
    const supplierModal = bootstrap.Modal.getInstance(document.getElementById('supplierPricingModal'));
    if (catalogModal) catalogModal.hide();
    if (supplierModal) supplierModal.hide();

    // Show success feedback
    if (particularInput) {
        particularInput.classList.add('border-success');
        setTimeout(() => particularInput.classList.remove('border-success'), 2000);
    }

    // Show toast notification
    showToast(`Applied pricing from ${supplier.supplier_name}`, 'success');
}

/**
 * Add supplier badge to show selected supplier
 */
function addSupplierBadge(groupRow, supplierName) {
    // Remove existing badge if any
    const existingBadge = groupRow.querySelector('.supplier-badge');
    if (existingBadge) {
        existingBadge.remove();
    }

    // Create new badge
    const badge = document.createElement('span');
    badge.className = 'supplier-badge badge bg-info ms-2';
    badge.style.fontSize = '0.75rem';
    badge.innerHTML = `<i class="bi bi-building"></i> ${escapeHtml(supplierName)}`;

    // Insert after the particular input
    const particularInput = groupRow.querySelector('.particular-input');
    if (particularInput) {
        particularInput.parentNode.insertBefore(badge, particularInput.nextSibling);
    }
}


/**
 * Search functionality
 */
const catalogSearch = document.getElementById('catalogSearch');
if (catalogSearch) {
    catalogSearch.addEventListener('input', function (e) {
        const searchTerm = e.target.value.toLowerCase();
        const filtered = glassTypesData.filter(gt =>
            gt.name.toLowerCase().includes(searchTerm) ||
            (gt.category && gt.category.toLowerCase().includes(searchTerm))
        );
        renderCatalogTable(filtered);
    });
}

/**
 * Category filter
 */
const catalogCategoryFilter = document.getElementById('catalogCategoryFilter');
if (catalogCategoryFilter) {
    catalogCategoryFilter.addEventListener('change', function (e) {
        const category = e.target.value;
        const searchTerm = document.getElementById('catalogSearch')?.value.toLowerCase() || '';

        let filtered = category ? glassTypesData.filter(gt => gt.category === category) : glassTypesData;

        if (searchTerm) {
            filtered = filtered.filter(gt =>
                gt.name.toLowerCase().includes(searchTerm) ||
                (gt.category && gt.category.toLowerCase().includes(searchTerm))
            );
        }

        renderCatalogTable(filtered);
    });
}

/**
 * Utility function to escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toastContainer';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }

    // Create toast
    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `toast align-items-center text-white bg-${type === 'success' ? 'success' : 'info'} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="bi bi-check-circle me-2"></i>${escapeHtml(message)}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;

    toastContainer.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();

    // Remove toast after it's hidden
    toast.addEventListener('hidden.bs.toast', function () {
        toast.remove();
    });
}
