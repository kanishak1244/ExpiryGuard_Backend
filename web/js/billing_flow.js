// billing_flow.js - ExpiryGuard Retail POS & Counter Billing Engine

let activeBillState = {
  customer: { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
  pendingCustomerName: '',
  invoiceNumber: '',
  invoiceDate: new Date().toISOString().split('T')[0],
  paymentMode: 'CASH',
  splitPayments: [],
  billDiscountPercent: 0.0,
  manualRoundOff: 0.0,
  useManualRoundOff: false,
  activeHeldBillId: null,
  activeHeldBillNumber: null,
  items: []
};

let billingCustomersCache = [
  { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
  { id: 2, name: 'Rajesh Sharma', phone: '9876543210', gstin: '07AAAAA0000A1Z5' },
  { id: 3, name: 'Pooja Verma', phone: '9811122334', gstin: '' },
  { id: 4, name: 'Dr. Alok Clinic (B2B)', phone: '9988776655', gstin: '07AAECP4589K1ZR' }
];

let availableInventoryCache = [];

function generateBillInvoiceNumber() {
  const ts = Math.floor(Date.now() / 1000) % 100000;
  return `INV-2026-${String(ts).padStart(5, '0')}`;
}

// ----------------------------------------------------
// INITIALIZATION & CUSTOMER LOAD
// ----------------------------------------------------

async function initBillingEngine() {
  if (!activeBillState.invoiceNumber) {
    activeBillState.invoiceNumber = generateBillInvoiceNumber();
  }
  
  // Load from AppDataPreloader or localStorage cache for instant 0ms billing load
  try {
    const preloaderCusts = window.AppDataPreloader ? window.AppDataPreloader.get('/customers') : null;
    const cachedCusts = preloaderCusts || (localStorage.getItem('expiryguard_cached_billing_customers') ? JSON.parse(localStorage.getItem('expiryguard_cached_billing_customers')) : null);
    if (Array.isArray(cachedCusts) && cachedCusts.length > 0) {
      billingCustomersCache = [
        { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
        ...cachedCusts
      ];
    }
    const preloaderProds = window.AppDataPreloader ? window.AppDataPreloader.get('/products') : null;
    const cachedProds = preloaderProds || (localStorage.getItem('expiryguard_cached_billing_products') ? JSON.parse(localStorage.getItem('expiryguard_cached_billing_products')) : null);
    if (Array.isArray(cachedProds)) {
      availableInventoryCache = cachedProds;
    }
  } catch (e) {
    console.warn('Failed to parse cached billing data:', e);
  }

  // Render initial UI immediately
  renderCustomerDropdown();
  renderBillItemsTable();
  recalculateTotals();
  updateResumedHeldBanner();
  refreshHeldBillsCount();

  // Re-fetch when customers or inventory are mutated
  window.addEventListener('dawaiflow:mutate', (e) => {
    if (e.detail && (e.detail.tag === 'inventory' || e.detail.tag === 'khata')) {
      if (window.api && window.api.getCustomers) {
        window.api.getCustomers().then(c => {
          if (Array.isArray(c)) {
            billingCustomersCache = [{ id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' }, ...c];
            renderCustomerDropdown();
          }
        }).catch(() => {});
      }
      if (window.api && window.api.getProducts) {
        window.api.getProducts().then(p => {
          if (Array.isArray(p)) availableInventoryCache = p;
        }).catch(() => {});
      }
    }
  });

  // Load backend data in parallel in the background without blocking page render
  Promise.all([
    window.api && typeof window.api.getCustomers === 'function'
      ? window.api.getCustomers().catch(() => [])
      : Promise.resolve([]),
    window.api && typeof window.api.getProducts === 'function'
      ? window.api.getProducts().catch(() => [])
      : Promise.resolve([])
  ]).then(([custs, prods]) => {
    if (Array.isArray(custs) && custs.length > 0) {
      billingCustomersCache = [
        { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
        ...custs
      ];
      localStorage.setItem('expiryguard_cached_billing_customers', JSON.stringify(custs));
      renderCustomerDropdown();
    }
    if (Array.isArray(prods)) {
      availableInventoryCache = prods;
      localStorage.setItem('expiryguard_cached_billing_products', JSON.stringify(prods));
    }
  }).catch(e => {
    console.warn('Billing background load failed:', e);
  });
}

function renderCustomerDropdown() {
  const select = document.getElementById('bill-customer-select');
  if (!select) return;
  
  select.innerHTML = billingCustomersCache.map(c => 
    `<option value="${c.id}" ${c.id === (activeBillState.customer ? activeBillState.customer.id : 1) ? 'selected' : ''}>
      ${c.name} (${c.phone})${c.gstin ? ' - ' + c.gstin : ''}
    </option>`
  ).join('') + `<option value="NEW">+ Add New Customer / Party...</option>`;
}

function handleCustomerSelectChange(val) {
  if (val === 'NEW') {
    openAddNewCustomerModal();
    return;
  }
  const found = billingCustomersCache.find(c => String(c.id) === String(val));
  if (found) {
    activeBillState.customer = found;
  }

  // If payment mode is pending, toggle prompt visibility based on selection
  if (activeBillState.paymentMode === 'PENDING') {
    const promptBox = document.getElementById('pending-customer-prompt');
    if (promptBox) {
      if (!activeBillState.customer || activeBillState.customer.name === 'Walk-in Customer') {
        promptBox.style.display = 'block';
      } else {
        promptBox.style.display = 'none';
      }
    }
  }
}

function openAddNewCustomerModal() {
  let modal = document.getElementById('bill-add-customer-modal');
  if (!modal) {
    const modalHtml = `
      <div id="bill-add-customer-modal" class="modal-overlay active" style="z-index: 1200;">
        <div class="modal-card" style="max-width: 440px;">
          <div class="modal-header">
            <h3 class="panel-title">Add New Customer Party</h3>
            <button class="modal-close" onclick="closeAddNewCustomerModal()">✕</button>
          </div>
          <form onsubmit="handleSaveNewCustomer(event)">
            <div class="form-group">
              <label class="form-label">Customer / Patient Name *</label>
              <input type="text" id="new-cust-name" class="form-input" required placeholder="e.g. Ramesh Patel">
            </div>
            <div class="form-group">
              <label class="form-label">Mobile Number *</label>
              <input type="tel" id="new-cust-phone" class="form-input" required placeholder="9876543210">
            </div>
            <div class="form-group">
              <label class="form-label">GSTIN (Optional)</label>
              <input type="text" id="new-cust-gstin" class="form-input" placeholder="07AAAAA0000A1Z5">
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
              <button type="button" class="btn btn-secondary" onclick="closeAddNewCustomerModal()">Cancel</button>
              <button type="submit" class="btn btn-primary">Save & Select Customer</button>
            </div>
          </form>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
  } else {
    modal.classList.add('active');
  }
}

function closeAddNewCustomerModal() {
  const modal = document.getElementById('bill-add-customer-modal');
  if (modal) modal.classList.remove('active');
  renderCustomerDropdown();
}

async function handleSaveNewCustomer(e) {
  e.preventDefault();
  const name = document.getElementById('new-cust-name').value.trim();
  const phone = document.getElementById('new-cust-phone').value.trim();
  const gstin = document.getElementById('new-cust-gstin').value.trim();

  if (!name || !phone) return;

  const newCust = {
    id: Date.now(),
    name: name,
    phone: phone,
    gstin: gstin
  };

  try {
    if (window.api && typeof window.api.createCustomer === 'function') {
      const saved = await window.api.createCustomer({
        name: name,
        phone: phone,
        patient_discount_percentage: 0.0
      }).catch(() => null);
      if (saved && saved.id) newCust.id = saved.id;
    }
  } catch (err) {
    console.warn('Backend customer save failed, using local:', err);
  }

  billingCustomersCache.push(newCust);
  activeBillState.customer = newCust;
  closeAddNewCustomerModal();
  renderCustomerDropdown();
  showToastNotification(`Customer "${name}" added successfully!`);
}

// ----------------------------------------------------
// =========================================================================
// REBUILT MEDICINE SEARCH ENGINE (DUAL-MODE: NAME vs CODE/BARCODE)
// Deterministic, keyboard-first, race-condition immune, zero-AI, POS-optimized
// =========================================================================

// ====================================================
// REBUILT MEDICINE SEARCH & SELECTION ENGINE (FROM SCRATCH)
// High-performance live inventory search matching mobile billing
// ====================================================

let currentBillingSearchMode = 'name'; // 'name' | 'code'
let searchAbortController = null;
let searchDebounceTimer = null;
let currentSearchSeq = 0;
let searchHighlightIndex = -1;

function setBillingSearchMode(mode) {
  currentBillingSearchMode = (mode === 'code') ? 'code' : 'name';

  // Update tabs across both billing.html and create-bill-modal
  const nameBtns = [
    document.getElementById('search-mode-name-btn'),
    document.getElementById('modal-search-mode-name-btn')
  ];
  const codeBtns = [
    document.getElementById('search-mode-code-btn'),
    document.getElementById('modal-search-mode-code-btn')
  ];

  nameBtns.forEach(btn => {
    if (btn) {
      if (currentBillingSearchMode === 'name') btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });

  codeBtns.forEach(btn => {
    if (btn) {
      if (currentBillingSearchMode === 'code') btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });

  // Update placeholder and clear search input
  const searchInput = document.getElementById('bill-medicine-search-input');
  if (searchInput) {
    searchInput.value = '';
    searchInput.placeholder = (currentBillingSearchMode === 'code')
      ? 'Search medicine by code or barcode…'
      : 'Search medicine by name, composition or barcode…';
    searchInput.focus();
  }

  clearMedicineSearch(false);
}
window.setBillingSearchMode = setBillingSearchMode;

function showSearchSpinner(show) {
  const spinner = document.getElementById('bill-search-loading-spinner');
  if (spinner) spinner.style.display = show ? 'block' : 'none';
}

function updateSearchClearBtn(hasValue) {
  const clearBtn = document.getElementById('bill-search-clear-btn');
  if (clearBtn) {
    clearBtn.style.display = hasValue ? 'block' : 'none';
  }
}

function clearMedicineSearch(refocus = true) {
  clearTimeout(searchDebounceTimer);
  if (searchAbortController) {
    searchAbortController.abort();
    searchAbortController = null;
  }
  showSearchSpinner(false);
  updateSearchClearBtn(false);

  const searchInput = document.getElementById('bill-medicine-search-input');
  if (searchInput && searchInput.value !== '') {
    searchInput.value = '';
  }

  const dropdown = document.getElementById('bill-search-results-dropdown');
  if (dropdown) {
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
  }

  window._lastSearchResults = [];
  searchHighlightIndex = -1;

  if (refocus && searchInput) {
    searchInput.focus();
  }
}
window.clearMedicineSearch = clearMedicineSearch;

async function handleMedicineSearchInput(val) {
  const cleanQ = (val || '').trim();
  const rawVal = val || '';
  updateSearchClearBtn(rawVal.length > 0);

  const dropdown = document.getElementById('bill-search-results-dropdown');
  if (!dropdown) return;

  // If input is empty, instantly close dropdown and cancel ongoing requests
  if (cleanQ.length === 0) {
    clearTimeout(searchDebounceTimer);
    if (searchAbortController) {
      searchAbortController.abort();
      searchAbortController = null;
    }
    showSearchSpinner(false);
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
    window._lastSearchResults = [];
    searchHighlightIndex = -1;
    return;
  }

  // Cancel prior timer & abort prior in-flight request
  clearTimeout(searchDebounceTimer);
  if (searchAbortController) {
    searchAbortController.abort();
  }
  searchAbortController = new AbortController();
  const currentSignal = searchAbortController.signal;
  const requestSeq = ++currentSearchSeq;

  // Show loading indicator
  showSearchSpinner(true);
  dropdown.innerHTML = `
    <div style="padding: 14px 18px; text-align: center; color: var(--color-text-muted); font-size: 13.5px; display: flex; align-items: center; justify-content: center; gap: 8px;">
      <span style="display: inline-block; animation: spin 1s linear infinite;">🔄</span> Searching inventory…
    </div>`;
  dropdown.style.display = 'block';

  // Debounce 200ms (within 200–300ms requirement)
  const debounceDelay = 200;

  searchDebounceTimer = setTimeout(async () => {
    if (currentSignal.aborted || requestSeq !== currentSearchSeq) return;

    try {
      let results = [];
      const endpoint = `/billing/search-products?query=${encodeURIComponent(cleanQ)}&search_mode=${encodeURIComponent(currentBillingSearchMode)}&limit=15`;

      if (window.api && typeof window.api.searchBillingProducts === 'function') {
        results = await window.api.searchBillingProducts(cleanQ, currentBillingSearchMode, 15, currentSignal);
      } else if (window.api && typeof window.api.request === 'function') {
        results = await window.api.request(endpoint, { signal: currentSignal });
      } else {
        const token = localStorage.getItem('expiryguard_token') || localStorage.getItem('token');
        const resp = await fetch(endpoint, {
          headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
          credentials: 'include',
          signal: currentSignal
        });
        if (resp.ok) {
          results = await resp.json();
        }
      }

      // Guard against stale response overwriting a newer search request
      if (currentSignal.aborted || requestSeq !== currentSearchSeq) return;

      showSearchSpinner(false);
      const itemsList = Array.isArray(results) ? results : (results && Array.isArray(results.items) ? results.items : []);
      renderSearchResultsDropdown(itemsList, cleanQ, false);

    } catch (err) {
      if (err.name === 'AbortError') return;
      if (requestSeq === currentSearchSeq) {
        showSearchSpinner(false);
        console.warn('Medicine search error:', err);
        renderSearchResultsDropdown([], cleanQ, true);
      }
    }
  }, debounceDelay);
}
window.handleMedicineSearchInput = handleMedicineSearchInput;

function renderSearchResultsDropdown(rawItems, query, isError = false) {
  const dropdown = document.getElementById('bill-search-results-dropdown');
  if (!dropdown) return;

  if (isError) {
    dropdown.innerHTML = `
      <div style="padding: 16px 20px; text-align: center; color: #DC2626; font-size: 13px;">
        ⚠️ Unable to search medicines. Please check connection and try again.
      </div>`;
    dropdown.style.display = 'block';
    window._lastSearchResults = [];
    return;
  }

  if (!rawItems || rawItems.length === 0) {
    dropdown.innerHTML = `
      <div style="padding: 18px 20px; text-align: center; color: var(--color-text-muted); font-size: 13.5px;">
        No medicines found matching "<strong>${escapeHtml(query)}</strong>"
        <div style="font-size: 12px; margin-top: 5px; opacity: 0.85;">
          ${currentBillingSearchMode === 'code' ? 'Check the medicine code or barcode and try again.' : 'Check the spelling or try generic composition.'}
        </div>
      </div>`;
    dropdown.style.display = 'block';
    window._lastSearchResults = [];
    return;
  }

  // Format uniform items from real inventory database
  const formattedItems = rawItems.map(p => {
    return {
      productId: p.id,
      name: p.product_name || p.name || 'Unknown Medicine',
      brand: p.brand || '',
      composition: p.composition || '',
      hsnCode: p.hsn_code || '3004',
      batchNumber: p.batch_number || 'BATCH-01',
      barcode: p.barcode || '',
      expiryDate: p.expiry_date ? String(p.expiry_date).split('T')[0] : '2028-12-31',
      stock: (p.quantity !== undefined && p.quantity !== null) ? Number(p.quantity) : 0,
      mrp: (p.unit_price !== undefined && p.unit_price !== null) ? Number(p.unit_price) : 50.0,
      pricePerUnit: p.price_per_unit || p.loose_tablet_price,
      unitsPerPack: p.units_per_pack || p.tablets_per_strip || 10,
      gst: p.gst_percentage || p.gst_rate || 12.0
    };
  });

  window._lastSearchResults = formattedItems;
  searchHighlightIndex = -1;

  let html = formattedItems.map((r, idx) => `
    <div class="search-result-item" id="search-res-item-${idx}" onclick="selectMedicineForBill(${idx})"
         style="padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--color-border); transition: background 0.12s ease;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
        <div style="flex: 1; min-width: 0;">
          <div style="font-weight: 700; font-size: 14.5px; color: var(--color-text-primary); display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span>${escapeHtml(r.name)}</span>
            ${r.brand ? `<span style="font-size: 11.5px; font-weight: 500; color: var(--color-text-muted); background: var(--color-surface-bg); padding: 1px 6px; border-radius: 4px; border: 1px solid var(--color-border);">${escapeHtml(r.brand)}</span>` : ''}
            ${r.barcode ? `<span class="badge badge-info" style="font-size: 10.5px;">🏷️ ${escapeHtml(r.barcode)}</span>` : ''}
          </div>
          ${r.composition ? `<div style="font-size: 12px; font-weight: 600; color: #2563EB; margin-top: 3px; text-transform: uppercase;">Composition: ${escapeHtml(r.composition)}</div>` : ''}
          <div style="font-size: 12px; color: var(--color-text-muted); margin-top: 4px; display: flex; flex-wrap: wrap; gap: 12px;">
            ${r.hsnCode ? `<span>Code: <strong>${escapeHtml(r.hsnCode)}</strong></span>` : ''}
            <span>Batch: <strong style="color: var(--status-safe);">${escapeHtml(r.batchNumber)}</strong></span>
            <span>Exp: <strong>${escapeHtml(r.expiryDate)}</strong></span>
            <span>Stock: <strong style="${r.stock <= 0 ? 'color: #DC2626;' : 'color: #10B981;'}">${r.stock}</strong></span>
          </div>
        </div>
        <div style="text-align: right; flex-shrink: 0; margin-left: 8px;">
          <div style="font-weight: 800; color: var(--status-safe); font-size: 16px;">₹${Number(r.mrp).toFixed(2)}</div>
          <span class="badge badge-info" style="font-size: 10px; margin-top: 4px; display: inline-block;">GST ${r.gst}%</span>
        </div>
      </div>
    </div>
  `).join('');

  dropdown.innerHTML = html;
  dropdown.style.display = 'block';
}

// ----------------------------------------------------
// KEYBOARD NAVIGATION IN SEARCH RESULTS (Arrows, Enter, Escape)
// ----------------------------------------------------

function handleSearchKeydown(e) {
  const dropdown = document.getElementById('bill-search-results-dropdown');
  const results = window._lastSearchResults || [];
  const isOpen = dropdown && dropdown.style.display === 'block' && results.length > 0;

  if (e.key === 'ArrowDown') {
    if (!isOpen) return;
    e.preventDefault();
    searchHighlightIndex = Math.min(results.length - 1, searchHighlightIndex + 1);
    updateSearchHighlight(results.length);
    return;
  }

  if (e.key === 'ArrowUp') {
    if (!isOpen) return;
    e.preventDefault();
    searchHighlightIndex = Math.max(0, searchHighlightIndex - 1);
    updateSearchHighlight(results.length);
    return;
  }

  if (e.key === 'Enter') {
    e.preventDefault();
    if (isOpen) {
      const targetIdx = (searchHighlightIndex >= 0) ? searchHighlightIndex : 0;
      selectMedicineForBill(targetIdx);
    }
    return;
  }

  if (e.key === 'Escape') {
    if (dropdown) dropdown.style.display = 'none';
    searchHighlightIndex = -1;
    e.target.blur();
    return;
  }
}

function updateSearchHighlight(count) {
  for (let i = 0; i < count; i++) {
    const el = document.getElementById(`search-res-item-${i}`);
    if (el) {
      if (i === searchHighlightIndex) {
        el.classList.add('selected');
        el.scrollIntoView({ block: 'nearest' });
      } else {
        el.classList.remove('selected');
      }
    }
  }
}

// Global click outside to dismiss search dropdown
document.addEventListener('click', (e) => {
  const searchBox = document.querySelector('.billing-search-box');
  const dropdown = document.getElementById('bill-search-results-dropdown');
  if (dropdown && searchBox && !searchBox.contains(e.target)) {
    dropdown.style.display = 'none';
  }
});

// Global listener for keydown on search input
document.addEventListener('keydown', (e) => {
  if (e.target && e.target.id === 'bill-medicine-search-input') {
    handleSearchKeydown(e);
  }
});

function selectMedicineForBill(index, overrides = {}) {
  const results = window._lastSearchResults || [];
  const med = results[index];
  if (!med) return;

  const currentSearchResults = [...results];
  // Clear search field, hide dropdown, hide clear button
  clearMedicineSearch(false);

  // FEFO: Gather all active batches for this product in inventory
  const seenBatches = new Set();
  const allBatches = [];

  function addBatch(b) {
    if (!b || !b.batchNumber || seenBatches.has(b.batchNumber)) return;
    seenBatches.add(b.batchNumber);
    allBatches.push(b);
  }

  // 1. Add the clicked medicine batch
  addBatch({
    productId: med.productId || 1,
    batchNumber: med.batchNumber || 'BATCH-01',
    expiryDate: med.expiryDate || '2028-12-31',
    stock: med.stock !== undefined ? med.stock : 10,
    mrp: med.mrp || 50.0,
    pricePerUnit: med.pricePerUnit,
    unitsPerPack: med.unitsPerPack || 10
  });

  // 2. Add matching batches from recent search results
  currentSearchResults.forEach(sm => {
    if (sm && sm.name && sm.name.trim().toLowerCase() === med.name.trim().toLowerCase()) {
      addBatch({
        productId: sm.productId || 1,
        batchNumber: sm.batchNumber || 'BATCH-01',
        expiryDate: sm.expiryDate || '2028-12-31',
        stock: sm.stock !== undefined ? sm.stock : 10,
        mrp: sm.mrp || 50.0,
        pricePerUnit: sm.pricePerUnit,
        unitsPerPack: sm.unitsPerPack || 10
      });
    }
  });

  // 3. Add matching batches from availableInventoryCache if populated
  if (Array.isArray(availableInventoryCache) && availableInventoryCache.length > 0) {
    availableInventoryCache.forEach(p => {
      const pName = (p.product_name || p.name || '').trim().toLowerCase();
      if (pName && pName === med.name.trim().toLowerCase()) {
        addBatch({
          productId: p.id,
          batchNumber: p.batch_number,
          expiryDate: p.expiry_date ? String(p.expiry_date).split('T')[0] : '2028-12-31',
          stock: p.quantity,
          mrp: p.unit_price,
          pricePerUnit: p.price_per_unit || p.loose_tablet_price,
          unitsPerPack: p.units_per_pack || p.tablets_per_strip || 10
        });
      }
    });
  }

  // Sort batches strictly by FEFO (First Expiry First Out)
  allBatches.sort((a, b) => {
    const expA = a.expiryDate || '9999-12-31';
    const expB = b.expiryDate || '9999-12-31';
    return expA.localeCompare(expB);
  });

  const batchesList = allBatches.length > 0 ? allBatches : [{
    productId: med.productId || 1,
    batchNumber: med.batchNumber || 'BATCH-01',
    expiryDate: med.expiryDate || '2028-12-31',
    stock: med.stock || 10,
    mrp: med.mrp || 50.0,
    pricePerUnit: med.pricePerUnit,
    unitsPerPack: med.unitsPerPack || 10
  }];

  // Pre-select first valid earliest-expiry batch (FEFO)
  const primaryBatch = batchesList[0];
  const unitsPerPack = Number(primaryBatch.unitsPerPack || med.unitsPerPack || 10);
  const packPrice = Number(primaryBatch.mrp || med.mrp || 50.0);
  const loosePrice = primaryBatch.pricePerUnit ? Number(primaryBatch.pricePerUnit) : Number((packPrice / unitsPerPack).toFixed(2));

  const requestedUnit = (overrides.unitType === 'loose') ? 'loose' : 'strip';
  const requestedQty = (overrides.quantity && overrides.quantity > 0) ? Number(overrides.quantity) : 1;
  const initialRate = requestedUnit === 'loose' ? loosePrice : packPrice;

  const newItem = {
    id: Date.now() + Math.random(),
    productId: primaryBatch.productId,
    name: med.name,
    brand: med.brand,
    composition: med.composition,
    hsnCode: med.hsnCode || '3004',
    selectedBatch: primaryBatch.batchNumber,
    expiryDate: primaryBatch.expiryDate,
    availableStock: primaryBatch.stock,
    unitType: requestedUnit,
    packPrice: packPrice,
    unitsPerPack: unitsPerPack,
    loosePrice: loosePrice,
    rate: initialRate,
    quantity: requestedQty,
    freeQuantity: 0,
    discountPercent: 0.0,
    gstRate: Number(med.gst) || 12.0,
    batches: batchesList
  };

  activeBillState.items.push(newItem);
  renderBillItemsTable();
  recalculateTotals();

  // Return focus to search input immediately for rapid counter billing
  setTimeout(() => {
    const sInput = document.getElementById('bill-medicine-search-input');
    if (sInput) {
      sInput.focus();
    }
  }, 20);
}
window.selectMedicineForBill = selectMedicineForBill;

// ----------------------------------------------------
// RUNNING BILL TABLE RENDERING & INLINE EDITING
// ----------------------------------------------------

function renderBillItemsTable() {
  const tbody = document.getElementById('bill-items-table-body');
  const countBadge = document.getElementById('bill-item-count-badge');
  if (!tbody) return;

  if (countBadge) {
    countBadge.textContent = `${activeBillState.items.length} lines • ${activeBillState.items.reduce((s, i) => s + (Number(i.quantity) || 0), 0)} units`;
  }

  if (activeBillState.items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align: center; padding: 36px 20px; color: var(--color-text-muted);">
          <div style="font-size: 28px; margin-bottom: 8px; opacity: 0.8;">💊</div>
          <div style="font-weight: 700; font-size: 14.5px; color: var(--color-text-primary);">No medicines added yet</div>
          <div style="font-size: 13px; margin-top: 4px; color: var(--color-text-muted);">Search for a medicine above to start the bill.</div>
          <div style="font-size: 11.5px; margin-top: 6px; color: var(--color-text-muted); opacity: 0.85;">⚡ Medicines are automatically selected in FEFO order.</div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = activeBillState.items.map((item, idx) => {
    const taxable = Number(item.quantity || 1) * Number(item.rate || 0) * (1 - (Number(item.discountPercent || 0) / 100));
    const gstAmt = taxable * (Number(item.gstRate || 12) / 100);
    const rowTotal = taxable + gstAmt;

    return `
      <tr style="border-bottom: 1px solid var(--color-border);">
        <td style="font-weight: 700; color: var(--color-text-muted); width: 30px; text-align: center;">${idx + 1}</td>
        
        <!-- Medicine & Brand -->
        <td style="min-width: 200px;">
          <div style="font-weight: 600; font-size: 13.5px; color: var(--color-text-primary);">${escapeHtml(item.name)}</div>
          <div style="font-size: 11px; color: var(--color-text-muted);">${escapeHtml(item.brand)}${item.composition ? ' • ' + escapeHtml(item.composition) : ''} • HSN: ${escapeHtml(item.hsnCode)}</div>
        </td>

        <!-- Batch & Expiry (FEFO dropdown) -->
        <td style="min-width: 150px;">
          <select class="form-input" style="padding: 4px 6px; font-size: 12px; height: auto;" onchange="handleItemBatchChange(${idx}, this.value)">
            ${item.batches.map(b => `
              <option value="${b.batchNumber}" ${b.batchNumber === item.selectedBatch ? 'selected' : ''}>
                ${b.batchNumber} (Exp: ${b.expiryDate}) [Stock: ${b.stock}]
              </option>
            `).join('')}
          </select>
        </td>

        <!-- Unit Type (Full Pack vs Loose/Open) -->
        <td style="min-width: 120px; text-align: center;">
          <select class="form-input" style="padding: 4px 6px; font-size: 12px; height: auto;" onchange="handleItemUnitTypeChange(${idx}, this.value)">
            <option value="strip" ${item.unitType === 'strip' ? 'selected' : ''}>📦 Full Strip</option>
            <option value="loose" ${item.unitType === 'loose' ? 'selected' : ''}>💊 Loose / Open</option>
          </select>
        </td>

        <!-- Qty -->
        <td style="width: 80px;">
          <input type="number" min="1" class="form-input item-qty-input" value="${item.quantity}"
                 style="padding: 4px 6px; font-size: 13px; font-weight: 600; text-align: center; height: auto;"
                 oninput="handleItemFieldChange(${idx}, 'quantity', this.value)">
        </td>

        <!-- Free Qty -->
        <td style="width: 65px;">
          <input type="number" min="0" class="form-input item-free-input" value="${item.freeQuantity}"
                 style="padding: 4px 6px; font-size: 13px; text-align: center; height: auto;"
                 oninput="handleItemFieldChange(${idx}, 'freeQuantity', this.value)">
        </td>

        <!-- Rate (₹) -->
        <td style="width: 95px;">
          <input type="number" step="0.01" min="0" class="form-input item-rate-input" value="${Number(item.rate).toFixed(2)}"
                 style="padding: 4px 6px; font-size: 13px; font-weight: 600; text-align: right; height: auto;"
                 oninput="handleItemFieldChange(${idx}, 'rate', this.value)">
        </td>

        <!-- Disc % -->
        <td style="width: 70px;">
          <input type="number" min="0" max="100" class="form-input item-disc-input" value="${item.discountPercent}"
                 style="padding: 4px 6px; font-size: 13px; text-align: center; height: auto;"
                 oninput="handleItemFieldChange(${idx}, 'discountPercent', this.value)">
        </td>

        <!-- GST % -->
        <td style="width: 70px;">
          <input type="number" min="0" max="100" class="form-input item-gst-input" value="${item.gstRate}"
                 style="padding: 4px 6px; font-size: 13px; text-align: center; height: auto;"
                 oninput="handleItemFieldChange(${idx}, 'gstRate', this.value)">
        </td>

        <!-- Amount (₹) -->
        <td style="width: 105px; text-align: right; font-weight: 700; font-size: 14px; color: var(--status-safe);">
          ₹${rowTotal.toFixed(2)}
        </td>

        <!-- Delete Action -->
        <td style="width: 45px; text-align: center;">
          <button type="button" class="btn btn-secondary" style="padding: 4px 8px; color: #DC2626; border-color: #FECACA;" onclick="removeBillItem(${idx})" title="Delete row">
            🗑️
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function handleItemUnitTypeChange(index, unitType) {
  const item = activeBillState.items[index];
  if (!item) return;

  item.unitType = unitType;
  if (unitType === 'loose') {
    item.rate = Number(item.loosePrice || (item.packPrice / (item.unitsPerPack || 10)).toFixed(2));
  } else {
    item.rate = Number(item.packPrice || (item.rate * (item.unitsPerPack || 10)).toFixed(2));
  }

  renderBillItemsTable();
  recalculateTotals();
}

function handleItemFieldChange(index, field, value) {
  if (!activeBillState.items[index]) return;
  const numVal = parseFloat(value) || 0;
  activeBillState.items[index][field] = numVal;
  recalculateTotals();
}

function handleItemBatchChange(index, batchNumber) {
  const item = activeBillState.items[index];
  if (!item) return;
  const bData = item.batches.find(b => b.batchNumber === batchNumber);
  if (bData) {
    if (bData.productId) {
      item.productId = bData.productId;
    }
    item.selectedBatch = batchNumber;
    item.expiryDate = bData.expiryDate;
    item.availableStock = bData.stock;
    item.packPrice = Number(bData.mrp);
    item.unitsPerPack = Number(bData.unitsPerPack || item.unitsPerPack || 10);
    item.loosePrice = bData.pricePerUnit ? Number(bData.pricePerUnit) : Number((item.packPrice / item.unitsPerPack).toFixed(2));
    item.rate = item.unitType === 'loose' ? item.loosePrice : item.packPrice;
    renderBillItemsTable();
    recalculateTotals();
  }
}

function removeBillItem(index) {
  activeBillState.items.splice(index, 1);
  renderBillItemsTable();
  recalculateTotals();
}

// ----------------------------------------------------
// FINANCIAL & GST CALCULATIONS
// ----------------------------------------------------

function recalculateTotals() {
  const rawSubtotal = activeBillState.items.reduce((sum, item) => {
    const itemTaxable = Number(item.quantity || 1) * Number(item.rate || 0) * (1 - (Number(item.discountPercent || 0) / 100));
    return sum + itemTaxable;
  }, 0);

  const billDiscount = rawSubtotal * (Number(activeBillState.billDiscountPercent || 0) / 100);
  const netTaxable = Math.max(0, rawSubtotal - billDiscount);

  const totalGst = activeBillState.items.reduce((sum, item) => {
    const itemTaxable = Number(item.quantity || 1) * Number(item.rate || 0) * (1 - (Number(item.discountPercent || 0) / 100));
    const ratio = rawSubtotal > 0 ? (netTaxable / rawSubtotal) : 1;
    return sum + (itemTaxable * (Number(item.gstRate || 12) / 100) * ratio);
  }, 0);

  const cgst = totalGst / 2;
  const sgst = totalGst / 2;
  const unroundedGrandTotal = netTaxable + totalGst;

  let roundOff = 0;
  if (activeBillState.useManualRoundOff) {
    roundOff = Number(activeBillState.manualRoundOff || 0);
  } else {
    roundOff = Math.round(unroundedGrandTotal) - unroundedGrandTotal;
  }

  const grandTotal = Math.max(0, unroundedGrandTotal + roundOff);

  // Update DOM Total Elements
  const elSubtotal = document.getElementById('bill-subtotal-val');
  const elDiscAmount = document.getElementById('bill-discount-amount-val');
  const elCgst = document.getElementById('bill-cgst-val');
  const elSgst = document.getElementById('bill-sgst-val');
  const elRoundOff = document.getElementById('bill-roundoff-val');
  const elGrandTotal = document.getElementById('bill-grand-total-val');

  if (elSubtotal) elSubtotal.textContent = `₹${rawSubtotal.toFixed(2)}`;
  if (elDiscAmount) elDiscAmount.textContent = `- ₹${billDiscount.toFixed(2)}`;
  if (elCgst) elCgst.textContent = `₹${cgst.toFixed(2)}`;
  if (elSgst) elSgst.textContent = `₹${sgst.toFixed(2)}`;
  if (elRoundOff) elRoundOff.textContent = `${roundOff >= 0 ? '+' : ''}₹${roundOff.toFixed(2)}`;
  if (elGrandTotal) elGrandTotal.textContent = `₹${grandTotal.toFixed(2)}`;

  // Store calculated values in state
  activeBillState.calculated = {
    rawSubtotal,
    billDiscount,
    netTaxable,
    totalGst,
    cgst,
    sgst,
    roundOff,
    grandTotal
  };
}

function handleBillDiscountChange(val) {
  activeBillState.billDiscountPercent = parseFloat(val) || 0;
  recalculateTotals();
}

function handlePaymentModeChange(mode) {
  activeBillState.paymentMode = mode;
  document.querySelectorAll('.pay-mode-btn').forEach(b => {
    if (b.dataset.mode === mode) {
      b.classList.add('btn-primary');
      b.classList.remove('btn-secondary');
    } else {
      b.classList.remove('btn-primary');
      b.classList.add('btn-secondary');
    }
  });

  if (mode !== 'SPLIT') {
    activeBillState.splitPayments = [];
    const splitStrip = document.getElementById('split-payment-summary-strip');
    if (splitStrip) splitStrip.style.display = 'none';
  }

  const promptBox = document.getElementById('pending-customer-prompt');
  if (promptBox) {
    if (mode === 'PENDING' || mode === 'CREDIT') {
      if (!activeBillState.customer || activeBillState.customer.name === 'Walk-in Customer') {
        promptBox.style.display = 'block';
        const inp = document.getElementById('pending-customer-name-input');
        if (inp) inp.focus();
      } else {
        promptBox.style.display = 'none';
      }
    } else {
      promptBox.style.display = 'none';
    }
  }
}

// ----------------------------------------------------
// SPLIT PAYMENT MODAL HANDLERS
// ----------------------------------------------------

let tempSplitAllocations = [];

function openSplitPaymentModal() {
  if (activeBillState.items.length === 0) {
    alert('Please add at least one medicine before configuring split payment.');
    return;
  }

  recalculateTotals();
  const grandTotal = activeBillState.calculated ? activeBillState.calculated.grandTotal : 0;
  if (grandTotal <= 0) {
    alert('Bill total must be greater than 0 for split payment.');
    return;
  }

  // Initialize modal state
  if (activeBillState.splitPayments && activeBillState.splitPayments.length > 0) {
    tempSplitAllocations = JSON.parse(JSON.stringify(activeBillState.splitPayments));
  } else {
    // Default suggestion: Cash for remaining
    tempSplitAllocations = [
      { payment_method: 'CASH', amount: grandTotal }
    ];
  }

  renderSplitModalState();
  const modal = document.getElementById('split-payment-modal');
  if (modal) modal.style.display = 'flex';
}

function closeSplitPaymentModal() {
  const modal = document.getElementById('split-payment-modal');
  if (modal) modal.style.display = 'none';
}

function renderSplitModalState() {
  const grandTotal = activeBillState.calculated ? activeBillState.calculated.grandTotal : 0;
  const allocated = tempSplitAllocations.reduce((sum, a) => sum + (parseFloat(a.amount) || 0), 0);
  const remaining = Math.round((grandTotal - allocated) * 100) / 100;

  const elTotal = document.getElementById('split-modal-total-bill');
  const elAlloc = document.getElementById('split-modal-allocated');
  const elRem = document.getElementById('split-modal-remaining');
  const elCreditWarn = document.getElementById('split-credit-customer-warning');

  if (elTotal) elTotal.textContent = `₹${grandTotal.toFixed(2)}`;
  if (elAlloc) elAlloc.textContent = `₹${allocated.toFixed(2)}`;
  if (elRem) {
    elRem.textContent = `₹${remaining.toFixed(2)}`;
    elRem.style.color = (Math.abs(remaining) < 0.01) ? '#16A34A' : '#DC2626';
  }

  // Check if credit is in allocations and customer is walk-in
  const hasCredit = tempSplitAllocations.some(a => a.payment_method === 'CREDIT');
  const isWalkIn = !activeBillState.customer || activeBillState.customer.name === 'Walk-in Customer';
  if (elCreditWarn) {
    elCreditWarn.style.display = (hasCredit && isWalkIn) ? 'block' : 'none';
  }

  // Render list
  const listContainer = document.getElementById('split-allocations-list');
  if (listContainer) {
    if (tempSplitAllocations.length === 0) {
      listContainer.innerHTML = `<div style="text-align: center; color: #94A3B8; font-size: 13px; padding: 12px;">No payment methods added yet. Add below.</div>`;
    } else {
      const methodLabels = { CASH: '💵 Cash', UPI: '📱 UPI', CARD: '💳 Card', CREDIT: '📒 Credit (Khata)' };
      listContainer.innerHTML = tempSplitAllocations.map((alloc, idx) => `
        <div style="display: flex; justify-content: space-between; align-items: center; background: #F8FAFC; border: 1px solid #E2E8F0; padding: 8px 12px; border-radius: 6px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 700; font-size: 13px; color: #1E293B;">${methodLabels[alloc.payment_method] || alloc.payment_method}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-weight: 800; font-size: 14px; color: #0F172A;">₹${(parseFloat(alloc.amount) || 0).toFixed(2)}</span>
            <button type="button" onclick="handleRemoveSplitAllocation(${idx})" style="background: none; border: none; color: #EF4444; font-size: 16px; cursor: pointer; padding: 0 4px;" title="Remove">✕</button>
          </div>
        </div>
      `).join('');
    }
  }

  // Pre-fill next allocation with remaining if > 0
  const addAmtInput = document.getElementById('split-add-amount');
  if (addAmtInput && remaining > 0) {
    addAmtInput.value = remaining.toFixed(2);
  }
}

function handleAddSplitAllocation() {
  const methodSelect = document.getElementById('split-add-method');
  const amountInput = document.getElementById('split-add-amount');
  if (!methodSelect || !amountInput) return;

  const method = methodSelect.value;
  const amount = Math.round(parseFloat(amountInput.value) * 100) / 100;

  if (isNaN(amount) || amount <= 0) {
    alert('Please enter a valid payment amount greater than 0.');
    return;
  }

  // Consolidate duplicate methods
  const existing = tempSplitAllocations.find(a => a.payment_method === method);
  if (existing) {
    existing.amount = Math.round((existing.amount + amount) * 100) / 100;
  } else {
    tempSplitAllocations.push({ payment_method: method, amount: amount });
  }

  amountInput.value = '';
  renderSplitModalState();
}

function handleRemoveSplitAllocation(index) {
  tempSplitAllocations.splice(index, 1);
  renderSplitModalState();
}

function handleClearSplitPayments() {
  tempSplitAllocations = [];
  activeBillState.splitPayments = [];
  activeBillState.paymentMode = 'CASH';
  handlePaymentModeChange('CASH');
  closeSplitPaymentModal();
  showToastNotification('Split payments reset to Cash sale.');
}

function applySplitPayments() {
  const grandTotal = activeBillState.calculated ? activeBillState.calculated.grandTotal : 0;
  const allocated = tempSplitAllocations.reduce((sum, a) => sum + (parseFloat(a.amount) || 0), 0);
  const remaining = Math.round((grandTotal - allocated) * 100) / 100;

  if (tempSplitAllocations.length === 0) {
    alert('Please add at least one payment allocation.');
    return;
  }

  if (Math.abs(remaining) >= 0.01) {
    if (remaining > 0) {
      alert(`Underpayment: Bill total is ₹${grandTotal.toFixed(2)}, but only ₹${allocated.toFixed(2)} is allocated. Remaining: ₹${remaining.toFixed(2)}.`);
    } else {
      alert(`Overpayment: Bill total is ₹${grandTotal.toFixed(2)}, but ₹${allocated.toFixed(2)} is allocated. Please adjust by ₹${Math.abs(remaining).toFixed(2)}.`);
    }
    return;
  }

  // Check credit ledger safety
  const hasCredit = tempSplitAllocations.some(a => a.payment_method === 'CREDIT');
  let finalCustomerName = (activeBillState.customer ? activeBillState.customer.name : 'Walk-in Customer');
  if (hasCredit && (finalCustomerName === 'Walk-in Customer' || !finalCustomerName)) {
    const inlineName = (activeBillState.pendingCustomerName || (document.getElementById('pending-customer-name-input') ? document.getElementById('pending-customer-name-input').value : '')).trim();
    if (!inlineName) {
      const promptedName = prompt('Credit allocation requires a Customer Name for Khata ledger. Enter customer name:');
      if (!promptedName || !promptedName.trim()) {
        alert('Cannot confirm split with Credit without a valid Customer Name.');
        return;
      }
      activeBillState.pendingCustomerName = promptedName.trim();
      const inp = document.getElementById('pending-customer-name-input');
      if (inp) inp.value = promptedName.trim();
    }
  }

  activeBillState.splitPayments = JSON.parse(JSON.stringify(tempSplitAllocations));
  activeBillState.paymentMode = 'SPLIT';

  // Highlight Split button
  document.querySelectorAll('.pay-mode-btn').forEach(b => {
    if (b.dataset.mode === 'SPLIT') {
      b.classList.add('btn-primary');
      b.classList.remove('btn-secondary');
    } else {
      b.classList.remove('btn-primary');
      b.classList.add('btn-secondary');
    }
  });

  // Show summary badge
  const splitStrip = document.getElementById('split-payment-summary-strip');
  const splitSummaryText = document.getElementById('split-payment-summary-text');
  if (splitStrip && splitSummaryText) {
    const breakdownStr = activeBillState.splitPayments.map(p => `${p.payment_method}: ₹${p.amount.toFixed(2)}`).join(' | ');
    splitSummaryText.textContent = `✂️ Split: ${breakdownStr}`;
    splitStrip.style.display = 'flex';
  }

  closeSplitPaymentModal();
  showToastNotification('Split payment allocations applied successfully.');
}

// ----------------------------------------------------
// COMMITTING BILL & PDF GENERATION
// ----------------------------------------------------

let isCommittingBill = false;

async function commitBillTransaction(printPdf = false, saveAndNew = false) {
  if (isCommittingBill) {
    console.warn('[BILLING] Commit transaction already in-flight. Duplicate tap suppressed.');
    return;
  }

  if (activeBillState.items.length === 0) {
    alert('Cannot save empty bill. Please add at least one medicine.');
    return;
  }

  isCommittingBill = true;

  // Validate customer for Pending/Credit payment modes
  let finalCustomerName = (activeBillState.customer ? activeBillState.customer.name : 'Walk-in Customer');
  let finalCustomerPhone = (activeBillState.customer && activeBillState.customer.phone !== 'Cash Sale' ? activeBillState.customer.phone : null);

  const hasCreditAllocation = activeBillState.paymentMode === 'CREDIT' || activeBillState.paymentMode === 'PENDING' ||
    (activeBillState.splitPayments && activeBillState.splitPayments.some(p => p.payment_method === 'CREDIT'));

  if (hasCreditAllocation) {
    const inlineName = (activeBillState.pendingCustomerName || (document.getElementById('pending-customer-name-input') ? document.getElementById('pending-customer-name-input').value : '')).trim();
    if (finalCustomerName === 'Walk-in Customer' || !finalCustomerName) {
      if (!inlineName) {
        alert('Please enter a Customer / Patient name to record this credit sale in the ledger.');
        const inp = document.getElementById('pending-customer-name-input');
        if (inp) inp.focus();
        return;
      }
      finalCustomerName = inlineName;
    }
  }

  const saveBtn = document.getElementById('bill-save-print-btn');
  const originalText = saveBtn ? saveBtn.innerHTML : 'Save & Print';
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '⏳ Saving...';
  }

  // Ensure every item has a valid backend payload structure
  const payloadItems = activeBillState.items.map(item => ({
    product_id: item.productId || (availableInventoryCache[0] ? availableInventoryCache[0].id : 1),
    quantity: Number(item.quantity) || 1,
    unit_price: Number(item.rate),
    unit_type: item.unitType || 'strip',
    batch_number: item.selectedBatch || 'BATCH-01',
    discount: Number(item.discountPercent) || 0.0,
    gst_percentage: Number(item.gstRate) || 12.0
  }));

  if (!activeBillState.idempotencyKey) {
    activeBillState.idempotencyKey = 'df_sale_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
  }

  const payload = {
    items: payloadItems,
    idempotency_key: activeBillState.idempotencyKey,
    payment_method: activeBillState.paymentMode || 'CASH',
    payments: (activeBillState.paymentMode === 'SPLIT' && activeBillState.splitPayments.length > 0) ? activeBillState.splitPayments : null,
    customer_name: finalCustomerName,
    customer_phone: finalCustomerPhone,
    notes: `Retail POS Sale - ${activeBillState.invoiceNumber}`,
    is_interstate: false,
    discount_type: activeBillState.billDiscountPercent > 0 ? 'percent' : null,
    discount_value: Number(activeBillState.billDiscountPercent) || 0.0,
    ...(activeBillState.activeHeldBillId ? { held_bill_id: activeBillState.activeHeldBillId } : {})
  };

  try {
    let saleRes;
    if (window.api && typeof window.api.createSale === 'function') {
      saleRes = await window.api.createSale(payload);
    } else {
      const token = localStorage.getItem('expiryguard_token');
      const r = await fetch('/sales', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Key': activeBillState.idempotencyKey,
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });
      if (!r.ok) {
        const errData = await r.json().catch(() => ({}));
        throw new Error(errData.detail || `Bill commit failed with status ${r.status}`);
      }
      saleRes = await r.json();
    }

    // Instantly unblock UI
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = originalText;
    }

    const invoiceNum = saleRes.bill_number || activeBillState.invoiceNumber;
    const grandTotalVal = (saleRes.total_amount || (activeBillState.calculated && activeBillState.calculated.grandTotal) || 0).toFixed(2);
    const modeLabel = activeBillState.paymentMode === 'PENDING' ? '⏳ PENDING (Ledger)' : activeBillState.paymentMode;
    const pdfUrl = saleRes.id ? `/billing/${saleRes.id}/pdf` : null;

    // Toast with instant feedback and PDF Print action button
    const toastHtml = `
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%;">
        <div>
          <div style="font-weight: 700; font-size: 14px;">✅ Bill ${invoiceNum} Saved! (${modeLabel})</div>
          <div style="font-size: 12px; opacity: 0.9; margin-top: 2px;">Total: ₹${grandTotalVal} • Stock updated live</div>
        </div>
        ${pdfUrl ? `
          <a href="${pdfUrl}" target="_blank" class="btn btn-secondary" style="padding: 5px 12px; font-size: 12px; font-weight: 700; background: #FFFFFF; color: #0C3B34; text-decoration: none; border-radius: 6px; white-space: nowrap;">
            🖨️ View PDF
          </a>
        ` : ''}
      </div>
    `;
    showToastNotification(toastHtml);

    // Asynchronous decoupled PDF launch
    if (printPdf && pdfUrl) {
      window.open(pdfUrl, '_blank');
    }

    // Completely non-blocking background refreshes
    setTimeout(() => {
      Promise.allSettled([
        (typeof loadSalesHistory === 'function' ? loadSalesHistory() : null),
        (typeof loadInventoryData === 'function' ? loadInventoryData() : null),
        (typeof loadDashboardData === 'function' ? loadDashboardData() : null),
        (window.api && typeof window.api.getProducts === 'function' ? window.api.getProducts().then(p => { if (Array.isArray(p)) availableInventoryCache = p; }) : null)
      ]).catch(() => {});
    }, 20);

    if (saveAndNew) {
      resetBillForm();
    } else {
      const modal = document.getElementById('create-bill-modal');
      if (modal && modal.classList.contains('active')) {
        closeCreateBillModal();
      } else {
        resetBillForm();
      }
    }
  } catch (err) {
    console.error('Bill save failed:', err);
    alert(`Failed to save bill: ${err.message}`);
  } finally {
    isCommittingBill = false;
    if (saveBtn && saveBtn.disabled) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = originalText;
    }
  }
}

function resetBillForm() {
  activeBillState = {
    idempotencyKey: 'df_sale_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9),
    customer: billingCustomersCache[0] || { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
    pendingCustomerName: '',
    invoiceNumber: generateBillInvoiceNumber(),
    invoiceDate: new Date().toISOString().split('T')[0],
    paymentMode: 'CASH',
    billDiscountPercent: 0.0,
    manualRoundOff: 0.0,
    useManualRoundOff: false,
    activeHeldBillId: null,
    activeHeldBillNumber: null,
    items: []
  };

  const invInput = document.getElementById('bill-invoice-number-input');
  if (invInput) invInput.value = activeBillState.invoiceNumber;

  const discInput = document.getElementById('bill-discount-percent-input');
  if (discInput) discInput.value = '0';

  const pendingNameInput = document.getElementById('pending-customer-name-input');
  if (pendingNameInput) pendingNameInput.value = '';

  renderCustomerDropdown();
  handlePaymentModeChange('CASH');
  renderBillItemsTable();
  recalculateTotals();
  updateResumedHeldBanner();
  refreshHeldBillsCount();

  clearMedicineSearch(false);
  setBillingSearchMode('name');
  const searchInput = document.getElementById('bill-medicine-search-input');
  if (searchInput) {
    searchInput.focus();
  }
}

// ----------------------------------------------------
// HELD BILLS (PARK / RESUME) SYSTEM
// ----------------------------------------------------

async function refreshHeldBillsCount() {
  try {
    if (window.api && typeof window.api.getHeldBillsCount === 'function') {
      const res = await window.api.getHeldBillsCount();
      const count = (res && typeof res.count === 'number') ? res.count : 0;
      const badge = document.getElementById('held-bills-badge-count');
      if (badge) badge.textContent = count;
    }
  } catch (e) {
    console.warn('Failed to refresh held bills count:', e);
  }
}

function updateResumedHeldBanner() {
  const banner = document.getElementById('resumed-held-banner');
  const numSpan = document.getElementById('resumed-held-number');
  if (!banner || !numSpan) return;

  if (activeBillState.activeHeldBillNumber) {
    numSpan.textContent = activeBillState.activeHeldBillNumber;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
    numSpan.textContent = '';
  }
}

function clearResumedHeldBill() {
  activeBillState.activeHeldBillId = null;
  activeBillState.activeHeldBillNumber = null;
  updateResumedHeldBanner();
  showToastNotification('Bill unlinked from held record. Will be saved as a new bill.');
}

async function holdCurrentBill() {
  if (!activeBillState.items || activeBillState.items.length === 0) {
    alert('Cannot hold an empty bill. Add at least one medicine before holding.');
    return;
  }

  const defaultName = (activeBillState.customer && activeBillState.customer.name !== 'Walk-in Customer')
    ? activeBillState.customer.name
    : '';

  const custName = prompt('Enter Customer / Patient Name (optional):', defaultName);
  if (custName === null) return; // User cancelled

  const note = prompt('Enter Hold Note / Reason (optional, e.g. Customer at ATM):', '');
  if (note === null) return;

  const payloadItems = activeBillState.items.map(item => ({
    product_id: item.productId || (availableInventoryCache[0] ? availableInventoryCache[0].id : 1),
    product_name: item.name || 'Medicine',
    quantity: Number(item.quantity) || 1,
    unit_type: item.unitType || 'strip',
    unit_price: Number(item.rate) || 0.0,
    discount: Number(item.discountPercent) || 0.0,
    tablets_per_strip: item.tabletsPerStrip || 10,
    batch_number: item.selectedBatch || 'BATCH-01',
    expiry_date: item.expiryDate || null,
    gst_percentage: Number(item.gstRate) || 12.0
  }));

  const payload = {
    customer_id: activeBillState.customer && activeBillState.customer.id !== 1 ? activeBillState.customer.id : null,
    customer_name: (custName && custName.trim()) ? custName.trim() : (activeBillState.customer ? activeBillState.customer.name : 'Walk-in Customer'),
    customer_phone: activeBillState.customer && activeBillState.customer.phone !== 'Cash Sale' ? activeBillState.customer.phone : null,
    payment_method: activeBillState.paymentMode || 'CASH',
    split_payments: (activeBillState.paymentMode === 'SPLIT' && activeBillState.splitPayments && activeBillState.splitPayments.length > 0) ? activeBillState.splitPayments : null,
    discount_type: activeBillState.billDiscountPercent > 0 ? 'percent' : null,
    discount_value: Number(activeBillState.billDiscountPercent) || 0.0,
    notes: (note && note.trim()) ? note.trim() : null,
    items: payloadItems
  };

  try {
    const res = await window.api.createHeldBill(payload);
    const billNumber = res.held_bill_number || 'HB-???';

    // CRITICAL: Cart is cleared ONLY after successful hold!
    resetBillForm();
    await refreshHeldBillsCount();

    showToastNotification(`⏸️ Bill successfully held as ${billNumber}! Parked safely.`);
  } catch (err) {
    // CRITICAL: On error, active cart remains untouched!
    alert(`Failed to hold bill: ${err.message || err}`);
  }
}

let heldBillsListCache = [];

async function openHeldBillsModal() {
  const modal = document.getElementById('held-bills-modal');
  if (!modal) return;
  modal.style.display = 'flex';

  const searchInput = document.getElementById('held-bills-search-input');
  if (searchInput) {
    searchInput.value = '';
    searchInput.focus();
  }

  await loadHeldBillsList();
}

function closeHeldBillsModal() {
  const modal = document.getElementById('held-bills-modal');
  if (modal) modal.style.display = 'none';
}

async function loadHeldBillsList(query = '') {
  const container = document.getElementById('held-bills-modal-list');
  if (!container) return;
  container.innerHTML = '<div style="text-align: center; color: #888; padding: 30px;">Loading held bills...</div>';

  try {
    const bills = await window.api.getHeldBills('HELD', query);
    heldBillsListCache = bills || [];
    renderHeldBillsList(heldBillsListCache);
  } catch (e) {
    container.innerHTML = `<div style="text-align: center; color: #dc2626; padding: 20px;">Failed to load held bills: ${e.message || e}</div>`;
  }
}

let heldSearchDebounceTimer = null;
function handleHeldBillsSearch(query) {
  clearTimeout(heldSearchDebounceTimer);
  heldSearchDebounceTimer = setTimeout(() => {
    loadHeldBillsList(query);
  }, 300);
}

function renderHeldBillsList(bills) {
  const container = document.getElementById('held-bills-modal-list');
  if (!container) return;

  if (!bills || bills.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; color: #64748b; padding: 40px 20px;">
        <div style="font-size: 40px; margin-bottom: 8px;">⏸️</div>
        <div style="font-weight: 600; font-size: 15px;">No Held Bills Found</div>
        <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">Use "⏸️ Hold Bill" on active cart to park customer sales.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = bills.map(bill => {
    const itemsPreview = (bill.items || []).slice(0, 3).map(it => `${it.product_name} (x${it.quantity})`).join(', ') + ((bill.items || []).length > 3 ? '...' : '');
    const dateStr = bill.created_at ? new Date(bill.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

    return `
      <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; background: white; display: flex; justify-content: space-between; align-items: center; gap: 14px;">
        <div style="flex: 1;">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span style="background: #ffedd5; color: #c2410c; font-weight: 700; font-size: 13px; padding: 2px 8px; border-radius: 4px; font-family: monospace;">
              ${bill.held_bill_number}
            </span>
            <span style="font-weight: 600; font-size: 14px; color: #1e293b;">
              ${bill.customer_name || 'Walk-in Customer'}
            </span>
            ${bill.customer_phone ? `<span style="font-size: 12.5px; color: #64748b;">(${bill.customer_phone})</span>` : ''}
            <span style="font-size: 12px; color: #94a3b8; margin-left: auto;">${dateStr}</span>
          </div>

          <div style="font-size: 12.5px; color: #64748b; margin-bottom: 4px;">
            ${(bill.items || []).length} item(s): <span style="color: #334155;">${itemsPreview}</span>
          </div>

          ${bill.notes ? `<div style="font-size: 12px; color: #9a3412; font-style: italic;">Note: "${bill.notes}"</div>` : ''}
        </div>

        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex-shrink: 0;">
          <div style="font-size: 17px; font-weight: 800; color: #16a34a;">
            ₹${(bill.estimated_total || 0).toFixed(2)}
          </div>
          <div style="display: flex; gap: 6px;">
            <button type="button" class="btn btn-secondary btn-sm" style="font-size: 12px; padding: 5px 10px; color: #dc2626;" onclick="cancelHeldBillWeb(${bill.id})">
              ✕ Cancel
            </button>
            <button type="button" class="btn btn-primary btn-sm" style="background: #16a34a; font-size: 12.5px; font-weight: 700; padding: 5px 14px;" onclick="resumeHeldBillWeb(${bill.id})">
              ▶ Resume
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function resumeHeldBillWeb(heldBillId) {
  if (activeBillState.items && activeBillState.items.length > 0) {
    const confirmReplace = confirm('You have items in your current bill. Resuming will replace the current active cart. Proceed?');
    if (!confirmReplace) return;
  }

  try {
    const resumeData = await window.api.resumeHeldBill(heldBillId);
    const heldBill = resumeData.held_bill;
    const resumeItems = resumeData.items || [];

    if (resumeData.has_stock_shortage) {
      const shortages = resumeItems.filter(it => !it.is_sufficient);
      const shortageDetails = shortages.map(it => `• ${it.product_name}: Requested ${it.requested_quantity}, Available ${it.available_stock}`).join('\n');
      const proceed = confirm(`⚠️ Stock Shortage Warning:\nSome items have lower stock than requested:\n\n${shortageDetails}\n\nDo you want to load the bill and adjust quantities?`);
      if (!proceed) return;
    }

    // Restore activeBillState
    activeBillState.activeHeldBillId = heldBill.id;
    activeBillState.activeHeldBillNumber = heldBill.held_bill_number;
    activeBillState.paymentMode = heldBill.payment_method || 'CASH';
    activeBillState.billDiscountPercent = (heldBill.discount_type === 'percent') ? heldBill.discount_value : 0;
    
    if (heldBill.split_payments && Array.isArray(heldBill.split_payments) && heldBill.split_payments.length > 0) {
      activeBillState.splitPayments = JSON.parse(JSON.stringify(heldBill.split_payments));
      activeBillState.paymentMode = 'SPLIT';
    } else {
      activeBillState.splitPayments = [];
    }
    
    // Match customer
    if (heldBill.customer_id) {
      const matched = billingCustomersCache.find(c => c.id === heldBill.customer_id);
      if (matched) activeBillState.customer = matched;
      else activeBillState.customer = { id: heldBill.customer_id, name: heldBill.customer_name, phone: heldBill.customer_phone || '' };
    } else if (heldBill.customer_name) {
      activeBillState.customer = { id: 1, name: heldBill.customer_name, phone: heldBill.customer_phone || '' };
    }

    activeBillState.items = resumeItems.map((it, idx) => {
      const isLoose = (it.unit_type === 'loose_tablet' || it.unit_type === 'loose' || it.unit_type === 'pill');
      return {
        id: idx + 1,
        productId: it.product_id,
        name: it.product_name,
        quantity: it.requested_quantity || 1,
        freeQty: 0,
        unitType: isLoose ? 'loose_tablet' : 'strip',
        tabletsPerStrip: it.tablets_per_strip || 10,
        rate: Number(it.unit_price) || 0.0,
        mrp: Number(it.unit_price) || 0.0,
        selectedBatch: it.batch_number || 'BATCH-01',
        expiryDate: it.expiry_date || '',
        gstRate: Number(it.gst_percentage) || 12.0,
        discountPercent: Number(it.discount) || 0.0,
        hsnCode: it.hsn_code || '3004',
        availableStock: it.available_stock
      };
    });

    renderCustomerDropdown();
    handlePaymentModeChange(activeBillState.paymentMode);
    if (activeBillState.paymentMode === 'SPLIT' && activeBillState.splitPayments.length > 0) {
      document.querySelectorAll('.pay-mode-btn').forEach(b => {
        if (b.dataset.mode === 'SPLIT') {
          b.classList.add('btn-primary');
          b.classList.remove('btn-secondary');
        } else {
          b.classList.remove('btn-primary');
          b.classList.add('btn-secondary');
        }
      });
      const splitStrip = document.getElementById('split-payment-summary-strip');
      const splitSummaryText = document.getElementById('split-payment-summary-text');
      if (splitStrip && splitSummaryText) {
        const breakdownStr = activeBillState.splitPayments.map(p => `${p.payment_method}: ₹${p.amount.toFixed(2)}`).join(' | ');
        splitSummaryText.textContent = `✂️ Split: ${breakdownStr}`;
        splitStrip.style.display = 'flex';
      }
    }
    renderBillItemsTable();
    recalculateTotals();
    updateResumedHeldBanner();

    closeHeldBillsModal();
    showToastNotification(`▶ Resumed bill ${heldBill.held_bill_number}`);
  } catch (err) {
    alert(`Failed to resume held bill: ${err.message || err}`);
  }
}

async function cancelHeldBillWeb(heldBillId) {
  if (!confirm('Are you sure you want to cancel this held bill? This cannot be undone.')) return;

  try {
    await window.api.cancelHeldBill(heldBillId);
    await refreshHeldBillsCount();
    await loadHeldBillsList();
    showToastNotification('Held bill cancelled successfully.');
  } catch (err) {
    alert(`Failed to cancel held bill: ${err.message || err}`);
  }
}

function showToastNotification(msg) {
  let toast = document.getElementById('billing-toast-notification');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'billing-toast-notification';
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--color-brand-deep, #0C3B34);
      color: #FFFFFF;
      padding: 14px 20px;
      border-radius: var(--radius-md, 8px);
      font-size: 13.5px;
      font-weight: 600;
      box-shadow: var(--shadow-modal, 0 10px 25px rgba(0,0,0,0.2));
      z-index: 99999;
      display: flex;
      align-items: center;
      gap: 10px;
      transition: all 0.3s ease;
    `;
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  toast.style.opacity = '1';
  toast.style.transform = 'translateY(0)';

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(20px)';
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ----------------------------------------------------
// GLOBAL BILLING MODAL DOM INJECTION (Quick POS)
// ----------------------------------------------------

function openCreateBillModal() {
  let modal = document.getElementById('create-bill-modal');
  if (!modal) {
    const modalHtml = `
      <div id="create-bill-modal" class="modal-overlay active" style="z-index: 1050;">
        <div class="modal-card" style="max-width: 1100px; width: 95vw; max-height: 92vh; overflow-y: auto; padding: 24px;">
          
          <!-- Modal Header -->
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--color-border); padding-bottom: 14px; margin-bottom: 18px;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <div style="font-size: 28px;">🧾</div>
              <div>
                <h2 style="margin: 0; font-size: 18px; color: var(--color-brand-deep);">Create New Retail Sale Bill — DawaiFlow Quick POS</h2>
                <div style="font-size: 12px; color: var(--color-text-muted);">High-speed keyboard billing, automated FEFO batch selection & GST invoice generation</div>
              </div>
            </div>
            <button class="modal-close" onclick="closeCreateBillModal()" style="font-size: 20px;">✕</button>
          </div>

          <!-- Section 1: Header (Party, Invoice No, Date, Payment Mode) -->
          <div class="billing-grid-header" style="margin-bottom: 16px;">
            <!-- Customer Party -->
            <div>
              <label class="form-label" style="font-weight: 600;">Customer / Patient Party</label>
              <select id="bill-customer-select" class="form-input" onchange="handleCustomerSelectChange(this.value)"></select>
            </div>

            <!-- Invoice No -->
            <div>
              <label class="form-label" style="font-weight: 600;">Invoice No</label>
              <input type="text" id="bill-invoice-number-input" class="form-input" value="${generateBillInvoiceNumber()}" oninput="activeBillState.invoiceNumber = this.value">
            </div>

            <!-- Invoice Date -->
            <div>
              <label class="form-label" style="font-weight: 600;">Date</label>
              <input type="date" id="bill-invoice-date-input" class="form-input" value="${new Date().toISOString().split('T')[0]}" onchange="activeBillState.invoiceDate = this.value">
            </div>

            <!-- Payment Mode -->
            <div>
              <label class="form-label" style="font-weight: 600;">Payment Mode</label>
              <div style="display: flex; gap: 6px;">
                <button type="button" class="btn btn-primary pay-mode-btn" data-mode="CASH" onclick="handlePaymentModeChange('CASH')" style="flex: 1; padding: 6px 0; font-size: 12px;">💵 Cash</button>
                <button type="button" class="btn btn-secondary pay-mode-btn" data-mode="UPI" onclick="handlePaymentModeChange('UPI')" style="flex: 1; padding: 6px 0; font-size: 12px;">📱 UPI</button>
                <button type="button" class="btn btn-secondary pay-mode-btn" data-mode="CREDIT" onclick="handlePaymentModeChange('CREDIT')" style="flex: 1; padding: 6px 0; font-size: 12px;">📋 Credit</button>
                <button type="button" class="btn btn-secondary pay-mode-btn" data-mode="PENDING" onclick="handlePaymentModeChange('PENDING')" style="flex: 1; padding: 6px 0; font-size: 12px;">⏳ Pending</button>
              </div>
              <div id="pending-customer-prompt" style="display: none; margin-top: 8px; padding: 8px 12px; background: rgba(245, 158, 11, 0.08); border: 1px solid var(--status-warning); border-radius: var(--radius-md);">
                <label style="font-size: 11.5px; font-weight: 600; color: var(--color-text-primary); display: block; margin-bottom: 3px;">Customer / Patient Name (for Pending Ledger):</label>
                <input type="text" id="pending-customer-name-input" class="form-input" style="font-size: 12.5px; padding: 6px 10px;" placeholder="e.g. Ramesh Kumar" oninput="activeBillState.pendingCustomerName = this.value">
              </div>
            </div>
          </div>

          <!-- Section 2: Search Medicine Autocomplete -->
          <div class="billing-search-box" style="position: relative;">
            <!-- Search Mode Selector -->
            <div class="billing-search-mode-bar">
              <button type="button" class="search-mode-tab active" id="modal-search-mode-name-btn" onclick="setBillingSearchMode('name')">
                🔎 Search by Medicine Name
              </button>
              <button type="button" class="search-mode-tab" id="modal-search-mode-code-btn" onclick="setBillingSearchMode('code')">
                🏷️ Search by Medicine Code
              </button>
            </div>
            <div style="position: relative;">
              <input type="text" id="bill-medicine-search-input" class="form-input" style="font-size: 14px; padding: 10px 60px 10px 14px; width: 100%; box-sizing: border-box;"
                     placeholder="Type medicine name…"
                     oninput="handleMedicineSearchInput(this.value)" autocomplete="off">
              <button type="button" id="bill-search-clear-btn" class="search-clear-btn" onclick="clearMedicineSearch()" title="Clear search" style="display: none;">&times;</button>
              <div id="bill-search-loading-spinner" class="search-spinner-inline" style="display: none;"></div>
              <div id="bill-search-results-dropdown" class="billing-search-dropdown"></div>
            </div>
          </div>

          <!-- Section 3: Horizontal Desktop Items Table -->
          <div class="panel" style="margin-bottom: 16px;">
            <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 16px;">
              <h3 class="panel-title" style="font-size: 14px; margin: 0;">Billed Items</h3>
              <span id="bill-item-count-badge" class="badge badge-info" style="font-size: 12px;">0 lines • 0 units</span>
            </div>
            <div class="table-responsive">
              <table class="data-table" style="font-size: 13px;">
                <thead>
                  <tr>
                    <th style="width: 30px; text-align: center;">#</th>
                    <th>Medicine & Brand</th>
                    <th>Batch & Expiry (FEFO)</th>
                    <th style="text-align: center;">Unit Type</th>
                    <th style="text-align: center;">Qty</th>
                    <th style="text-align: center;">Free</th>
                    <th style="text-align: right;">Rate (₹)</th>
                    <th style="text-align: center;">Disc%</th>
                    <th style="text-align: center;">GST%</th>
                    <th style="text-align: right;">Amount (₹)</th>
                    <th style="text-align: center;">Action</th>
                  </tr>
                </thead>
                <tbody id="bill-items-table-body"></tbody>
              </table>
            </div>
          </div>

          <!-- Section 4: Totals & Tax Breakup Footer -->
          <div class="totals-card" style="margin-bottom: 20px;">
            <div>
              <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                <label class="form-label" style="margin: 0; font-weight: 600;">Overall Bill Discount (%):</label>
                <input type="number" id="bill-discount-percent-input" min="0" max="100" class="form-input" style="width: 80px; text-align: center;" value="0" oninput="handleBillDiscountChange(this.value)">
              </div>
              <div class="totals-info-box">
                <div>⚡ <strong>FEFO Auto-Stock Deduction:</strong> Automatically deducts from nearest expiry batch.</div>
                <div style="margin-top: 4px;">⚡ <strong>GST Split:</strong> Computed live as 50% CGST + 50% SGST on taxable amounts.</div>
              </div>
            </div>

            <!-- Right: Computed Totals Stack -->
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--color-text-muted);">Subtotal (Taxable):</span>
                <span id="bill-subtotal-val" style="font-weight: 600;">₹0.00</span>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--color-text-muted);">Bill Discount:</span>
                <span id="bill-discount-amount-val" style="font-weight: 600; color: #059669;">- ₹0.00</span>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--color-text-muted);">CGST Tax Breakup:</span>
                <span id="bill-cgst-val" style="font-weight: 600;">₹0.00</span>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--color-text-muted);">SGST Tax Breakup:</span>
                <span id="bill-sgst-val" style="font-weight: 600;">₹0.00</span>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 13px;">
                <span style="color: var(--color-text-muted);">Round-Off:</span>
                <span id="bill-roundoff-val" style="font-weight: 600; color: var(--color-text-muted);">+₹0.00</span>
              </div>
              <div style="border-top: 2px solid var(--color-border); padding-top: 8px; margin-top: 4px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 16px; font-weight: 800; color: var(--color-text-primary);">Grand Total:</span>
                <span id="bill-grand-total-val" style="font-size: 22px; font-weight: 800; color: var(--status-safe);">₹0.00</span>
              </div>
            </div>
          </div>

          <!-- Section 5: Action Bottom Buttons -->
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <button type="button" class="btn btn-secondary" onclick="resetBillForm()">Clear / Reset</button>
            
            <div style="display: flex; gap: 12px;">
              <button type="button" class="btn btn-secondary" style="padding: 10px 20px; font-weight: 600;" onclick="commitBillTransaction(false, true)">
                Save & New Bill
              </button>
              <button type="button" class="btn btn-primary" id="bill-save-print-btn" style="padding: 10px 26px; font-size: 14px; font-weight: 700;" onclick="commitBillTransaction(true, false)">
                🖨️ Save & Print GST Invoice
              </button>
            </div>
          </div>

        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
  } else {
    modal.classList.add('active');
  }

  initBillingEngine();
  const searchInput = document.getElementById('bill-medicine-search-input');
  if (searchInput) setTimeout(() => searchInput.focus(), 100);
}

function closeCreateBillModal() {
  const modal = document.getElementById('create-bill-modal');
  if (modal) modal.classList.remove('active');
}

// Attach globally
window.openCreateBillModal = openCreateBillModal;
window.closeCreateBillModal = closeCreateBillModal;
window.initBillingEngine = initBillingEngine;

// ====================================================
// VOICE BILLING ENGINE (Web Speech API - 100% Free / On-Device)
// ====================================================

let voiceRecognition = null;
let isVoiceListening = false;
let voiceCandidateResults = [];

function checkVoiceSupport() {
  return ('webkitSpeechRecognition' in window) || ('SpeechRecognition' in window);
}

function initVoiceRecognition() {
  if (!checkVoiceSupport()) return null;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 3;
  recognition.lang = 'en-IN'; // Indian English / Hinglish optimized

  recognition.onstart = () => {
    isVoiceListening = true;
    updateVoiceUI(true, "Listening... Speak medicine name or HSN code");
  };

  recognition.onresult = (event) => {
    const spokenText = event.results[0][0].transcript;
    console.log("Voice recognized text:", spokenText);
    matchVoiceInputToItem(spokenText);
  };

  recognition.onerror = (event) => {
    console.warn("Voice recognition error:", event.error);
    isVoiceListening = false;
    updateVoiceUI(false);
    if (event.error === 'not-allowed') {
      showVoiceToast("Microphone permission denied. Please allow mic access.");
    } else if (event.error !== 'no-speech') {
      showVoiceToast(`Voice error: ${event.error}`);
    }
  };

  recognition.onend = () => {
    isVoiceListening = false;
    updateVoiceUI(false);
  };

  return recognition;
}

function toggleVoiceBilling() {
  if (!checkVoiceSupport()) {
    alert("Speech recognition is not supported in this browser. Please use Chrome, Edge, or Safari.");
    return;
  }

  if (isVoiceListening) {
    stopVoiceBilling();
  } else {
    startVoiceBilling();
  }
}

function startVoiceBilling() {
  try {
    if (!voiceRecognition) {
      voiceRecognition = initVoiceRecognition();
    }
    if (voiceRecognition) {
      voiceRecognition.start();
    }
  } catch (err) {
    console.warn("Could not start speech recognition:", err);
    isVoiceListening = false;
    updateVoiceUI(false);
  }
}

function stopVoiceBilling() {
  if (voiceRecognition && isVoiceListening) {
    voiceRecognition.stop();
  }
  isVoiceListening = false;
  updateVoiceUI(false);
}

function updateVoiceUI(isListening, statusText = "") {
  const micBtn = document.getElementById('voice-billing-mic-btn');
  const statusBar = document.getElementById('voice-status-bar');
  const statusMsg = document.getElementById('voice-status-text');

  if (micBtn) {
    if (isListening) {
      micBtn.classList.add('voice-listening-active');
      micBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="22" height="22" stroke="#EF4444" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="6" fill="#EF4444" />
        </svg>
      `;
    } else {
      micBtn.classList.remove('voice-listening-active');
      micBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="22" height="22" stroke="#2563EB" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
          <line x1="12" y1="19" x2="12" y2="23"></line>
          <line x1="8" y1="23" x2="16" y2="23"></line>
        </svg>
      `;
    }
  }

  if (statusBar) {
    if (isListening) {
      statusBar.style.display = 'flex';
      if (statusMsg) statusMsg.textContent = statusText;
    }
  }
}

function showVoiceToast(msg, isSuccess = false) {
  const statusBar = document.getElementById('voice-status-bar');
  const statusMsg = document.getElementById('voice-status-text');
  const pulseDot = document.getElementById('voice-pulse-dot');
  if (statusBar && statusMsg) {
    statusBar.style.display = 'flex';
    statusBar.style.background = isSuccess ? '#ECFDF5' : '#EFF6FF';
    statusBar.style.borderColor = isSuccess ? '#A7F3D0' : '#BFDBFE';
    statusBar.style.color = isSuccess ? '#065F46' : '#1E40AF';
    if (pulseDot) pulseDot.style.display = isSuccess ? 'none' : 'inline-block';
    statusMsg.innerHTML = msg;
    setTimeout(() => {
      if (!isVoiceListening) {
        dismissVoiceStatus();
      }
    }, 4500);
  }
}

function dismissVoiceStatus() {
  const statusBar = document.getElementById('voice-status-bar');
  if (statusBar) statusBar.style.display = 'none';
}

function dismissVoiceChips() {
  const chipsContainer = document.getElementById('voice-candidate-chips');
  if (chipsContainer) chipsContainer.style.display = 'none';
}

let lastVoiceParsedCommand = null;

function showVoiceConfirmationStrip(text) {
  const strip = document.getElementById('voice-confirmation-strip');
  const txt = document.getElementById('voice-confirmation-text');
  if (strip && txt) {
    txt.innerHTML = text;
    strip.style.display = 'flex';
  }
}

function dismissVoiceConfirmation() {
  const strip = document.getElementById('voice-confirmation-strip');
  if (strip) strip.style.display = 'none';
}

function editLastVoiceItem() {
  const qtyInputs = document.querySelectorAll('.item-qty-input');
  if (qtyInputs.length > 0) {
    const lastQty = qtyInputs[qtyInputs.length - 1];
    lastQty.focus();
    lastQty.select();
  }
}

// Intelligent Voice Matching Logic with Full Natural Command Parsing
async function matchVoiceInputToItem(spokenText) {
  const cleanSpoken = (spokenText || "").trim();
  if (!cleanSpoken) return;

  const parsed = (typeof parseVoiceCommand === 'function')
    ? parseVoiceCommand(cleanSpoken)
    : (window.parseVoiceCommand ? window.parseVoiceCommand(cleanSpoken) : { quantity: 1, unit: 'strip', itemNameGuess: cleanSpoken, rawText: cleanSpoken });

  lastVoiceParsedCommand = parsed;
  const searchQuery = parsed.itemNameGuess || cleanSpoken;

  const searchInput = document.getElementById('bill-medicine-search-input');
  if (searchInput) {
    searchInput.value = searchQuery;
  }

  const unitLabel = parsed.unit === 'loose'
    ? (parsed.quantity > 1 ? 'loose tablets' : 'loose tablet')
    : (parsed.quantity > 1 ? 'strips' : 'strip');

  showVoiceToast(`Heard: <strong>${parsed.quantity} ${unitLabel}</strong> of "<strong>${escapeHtml(parsed.itemNameGuess)}</strong>" • Finding match...`);

  try {
    // 1. Check if backend /items/search endpoint is available
    let items = [];
    if (window.api && typeof window.api.request === 'function') {
      try {
        const res = await window.api.request(`/items/search?q=${encodeURIComponent(searchQuery)}&limit=10`);
        if (res && res.items) {
          items = res.items;
        }
      } catch (e) {
        console.warn("/items/search network error, falling back to local:", e);
      }
    }

    // 2. Fallback to client-side availableInventoryCache if backend call didn't return
    if (!items || items.length === 0) {
      const hsnMatch = cleanSpoken.match(/\b\d{4,8}\b/);
      if (hsnMatch) {
        const hsn = hsnMatch[0];
        items = availableInventoryCache.filter(p => (p.hsn_code || '').includes(hsn));
      } else {
        const lowerQ = searchQuery.toLowerCase();
        items = availableInventoryCache.filter(p => {
          const name = (p.name || p.product_name || '').toLowerCase();
          return name.includes(lowerQ) || lowerQ.includes(name);
        });
      }
    }

    if (!items || items.length === 0) {
      showVoiceToast(`No items found for "<strong>${escapeHtml(searchQuery)}</strong>"`);
      handleMedicineSearchInput(searchQuery);
      return;
    }

    // 3. Format matched items
    const formattedList = items.map(p => ({
      productId: p.id,
      name: p.product_name || p.name,
      brand: p.brand || p.manufacturer || 'General',
      composition: p.composition || '',
      hsnCode: p.hsn_code || '3004',
      batchNumber: p.batch_number || 'BATCH-01',
      expiryDate: p.expiry_date ? p.expiry_date.split('T')[0] : '2028-12-31',
      stock: p.quantity || 10,
      mrp: p.unit_price || 50.0,
      pricePerUnit: p.price_per_unit || p.loose_tablet_price,
      unitsPerPack: p.units_per_pack || p.tablets_per_strip || 10,
      gst: p.gst_percentage || p.gst_rate || 12.0,
      similarity: p.similarity !== undefined ? p.similarity : 0.7,
      isInventory: p.is_inventory !== false
    }));

    window._lastSearchResults = formattedList;
    const topItem = formattedList[0];

    // High confidence (>0.6): Auto-populate with parsed quantity and unit
    if (topItem.similarity >= 0.6) {
      dismissVoiceChips();
      selectMedicineForBill(0, {
        quantity: parsed.quantity,
        unitType: parsed.unit
      });
      showVoiceConfirmationStrip(`Heard: <strong>${parsed.quantity} ${unitLabel}</strong> of <strong>${escapeHtml(topItem.name)}</strong>`);
      showVoiceToast(`Added: <strong>${parsed.quantity} ${unitLabel}</strong> of <strong>${escapeHtml(topItem.name)}</strong> to bill`, true);
    } else {
      // Confidence low (<0.6): Present top 3 candidates as chips for manual confirmation
      renderVoiceCandidateChips(formattedList.slice(0, 3));
      showVoiceToast(`Please confirm your match for "<strong>${escapeHtml(searchQuery)}</strong>":`);
    }
  } catch (err) {
    console.error("Error matching voice input:", err);
    showVoiceToast(`Matching failed: ${err.message}`);
  }
}

function renderVoiceCandidateChips(candidates) {
  voiceCandidateResults = candidates;
  const chipsContainer = document.getElementById('voice-candidate-chips');
  const chipsList = document.getElementById('voice-candidate-chips-list');
  if (!chipsContainer || !chipsList) return;

  if (!candidates || candidates.length === 0) {
    chipsContainer.style.display = 'none';
    return;
  }

  const qty = (lastVoiceParsedCommand && lastVoiceParsedCommand.quantity) ? lastVoiceParsedCommand.quantity : 1;
  const unit = (lastVoiceParsedCommand && lastVoiceParsedCommand.unit) ? lastVoiceParsedCommand.unit : 'strip';
  const unitLabel = unit === 'loose'
    ? (qty > 1 ? 'loose tablets' : 'loose tablet')
    : (qty > 1 ? 'strips' : 'strip');

  chipsList.innerHTML = candidates.map((item, idx) => `
    <button type="button" class="btn btn-secondary" onclick="confirmVoiceCandidate(${idx})"
            style="padding: 6px 12px; font-size: 12.5px; display: inline-flex; align-items: center; gap: 6px; border-color: #3B82F6; background: #F0FDF4;">
      <span style="font-weight: 600; color: #166534;">${escapeHtml(item.name)}</span>
      <span style="font-size: 11px; color: #4B5563;">₹${Number(item.mrp).toFixed(2)}</span>
      <span class="badge badge-info" style="font-size: 10px; padding: 1px 5px;">+${qty} ${unit}</span>
    </button>
  `).join('') + `
    <button type="button" class="btn btn-secondary" onclick="dismissVoiceChips()" style="padding: 6px 8px; font-size: 12px; color: #94A3B8;">
      Dismiss ✕
    </button>
  `;

  chipsContainer.style.display = 'flex';
}

function confirmVoiceCandidate(index) {
  const item = voiceCandidateResults[index];
  if (!item) return;
  dismissVoiceChips();
  const qty = (lastVoiceParsedCommand && lastVoiceParsedCommand.quantity) ? lastVoiceParsedCommand.quantity : 1;
  const unit = (lastVoiceParsedCommand && lastVoiceParsedCommand.unit) ? lastVoiceParsedCommand.unit : 'strip';
  const unitLabel = unit === 'loose'
    ? (qty > 1 ? 'loose tablets' : 'loose tablet')
    : (qty > 1 ? 'strips' : 'strip');

  window._lastSearchResults = [item];
  selectMedicineForBill(0, {
    quantity: qty,
    unitType: unit
  });
  showVoiceConfirmationStrip(`Heard: <strong>${qty} ${unitLabel}</strong> of <strong>${escapeHtml(item.name)}</strong>`);
  showVoiceToast(`Confirmed: <strong>${qty} ${unitLabel}</strong> of <strong>${escapeHtml(item.name)}</strong>`, true);
}

// Attach Voice Billing methods to global scope
window.toggleVoiceBilling = toggleVoiceBilling;
window.dismissVoiceStatus = dismissVoiceStatus;
window.dismissVoiceChips = dismissVoiceChips;
window.confirmVoiceCandidate = confirmVoiceCandidate;
window.dismissVoiceConfirmation = dismissVoiceConfirmation;
window.editLastVoiceItem = editLastVoiceItem;

// Attach Billing & Live Autocomplete methods to global scope
window.handleMedicineSearchInput = handleMedicineSearchInput;
window.selectMedicineForBill = selectMedicineForBill;
window.setBillingSearchMode = setBillingSearchMode;
window.renderSearchResultsDropdown = renderSearchResultsDropdown;
window.initBillingEngine = initBillingEngine;

// Auto-initialize if running directly on billing.html
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if (document.getElementById('billing-page')) {
        initBillingEngine();
      }
    });
  } else {
    if (document.getElementById('billing-page')) {
      initBillingEngine();
    }
  }
}


