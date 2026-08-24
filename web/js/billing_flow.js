// billing_flow.js - ExpiryGuard Retail POS & Counter Billing Engine

let activeBillState = {
  customer: { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
  pendingCustomerName: '',
  invoiceNumber: '',
  invoiceDate: new Date().toISOString().split('T')[0],
  paymentMode: 'CASH',
  billDiscountPercent: 0.0,
  manualRoundOff: 0.0,
  useManualRoundOff: false,
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
  
  try {
    if (window.api && typeof window.api.getCustomers === 'function') {
      const custs = await window.api.getCustomers().catch(() => []);
      if (Array.isArray(custs) && custs.length > 0) {
        billingCustomersCache = [
          { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
          ...custs
        ];
      }
    }
  } catch (e) {
    console.warn('Could not load customer list:', e);
  }

  try {
    if (window.api && typeof window.api.getProducts === 'function') {
      const prods = await window.api.getProducts().catch(() => []);
      if (Array.isArray(prods)) {
        availableInventoryCache = prods;
      }
    }
  } catch (e) {
    console.warn('Could not load inventory cache:', e);
  }

  renderCustomerDropdown();
  renderBillItemsTable();
  recalculateTotals();
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
// AUTOCOMPLETE SEARCH (DEBOUNCED + PREFIX/FUZZY MATCH)
// ----------------------------------------------------

let searchTimeout = null;
let currentSearchQuery = '';

async function handleMedicineSearchInput(val) {
  clearTimeout(searchTimeout);
  const dropdown = document.getElementById('bill-search-results-dropdown');
  if (!dropdown) return;

  const q = (val || '').trim();
  currentSearchQuery = q;

  if (q.length < 2) {
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
    return;
  }

  // Show lightweight loading state immediately
  dropdown.innerHTML = `<div style="padding: 12px; text-align: center; color: var(--color-text-muted); font-size: 13px;">⏳ Searching inventory & catalog for "${escapeHtml(q)}"...</div>`;
  dropdown.style.display = 'block';

  searchTimeout = setTimeout(async () => {
    if (currentSearchQuery !== q) return; // Stale request guard
    const cleanLowerQ = q.toLowerCase();

    let results = [];

    // 1. Prefix and contains match over active shop inventory
    const invMatches = availableInventoryCache.filter(p => {
      const pName = (p.name || p.product_name || '').toLowerCase();
      const pBrand = (p.brand || p.manufacturer || '').toLowerCase();
      const pComp = (p.composition || '').toLowerCase();
      const pBatch = (p.batch_number || '').toLowerCase();
      return pName.includes(cleanLowerQ) || pBrand.includes(cleanLowerQ) || pComp.includes(cleanLowerQ) || pBatch.includes(cleanLowerQ);
    });

    results = invMatches.map(p => ({
      productId: p.id,
      name: p.name || p.product_name,
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
      isInventory: true
    }));

    // 2. Fetch catalog suggestions if needed (supports name, brand, salt)
    if (window.api && typeof window.api.request === 'function') {
      try {
        const catRes = await window.api.request(`/catalog/search?q=${encodeURIComponent(q)}&limit=8`).catch(() => []);
        if (Array.isArray(catRes)) {
          catRes.forEach(c => {
            const medName = c.product_name || c.name;
            if (medName && !results.some(r => r.name.toLowerCase() === medName.toLowerCase())) {
              results.push({
                productId: 0,
                name: medName,
                brand: c.brand || 'General',
                composition: c.composition || '',
                hsnCode: c.hsn_code || '3004',
                batchNumber: 'BATCH-01',
                expiryDate: '2028-12-31',
                stock: 25,
                mrp: c.default_price || c.mrp || 45.0,
                pricePerUnit: c.price_per_unit,
                unitsPerPack: c.units_per_pack || c.tablets_per_strip || 10,
                gst: c.gst_rate || c.gst || 12.0,
                isInventory: false
              });
            }
          });
        }
      } catch (err) {
        console.warn('Catalog search error:', err);
      }
    }

    if (currentSearchQuery !== q) return;

    if (results.length === 0) {
      dropdown.innerHTML = `<div style="padding: 14px 16px; color: var(--color-text-muted); text-align: center; font-size: 13px;">No medicines found matching "<strong>${escapeHtml(q)}</strong>".<br><span style="font-size: 11.5px;">Try typing generic salt (e.g. Paracetamol) or brand name.</span></div>`;
      dropdown.style.display = 'block';
      return;
    }

    dropdown.innerHTML = results.map((r, idx) => `
      <div class="search-result-item" onclick="selectMedicineForBill(${idx})" style="padding: 10px 14px; cursor: pointer; border-bottom: 1px solid var(--color-border); display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div style="font-weight: 600; font-size: 13.5px; color: var(--color-text-primary);">${escapeHtml(r.name)}</div>
          <div style="font-size: 11.5px; color: var(--color-text-muted); margin-top: 2px;">
            ${escapeHtml(r.brand)}${r.composition ? ' • ' + escapeHtml(r.composition) : ''}
            • Batch: <strong style="color: var(--status-safe);">${escapeHtml(r.batchNumber)}</strong>
            • Exp: ${escapeHtml(r.expiryDate)}
            • Avail: ${r.stock} ${r.unitsPerPack ? '(1x' + r.unitsPerPack + ')' : ''}
          </div>
        </div>
        <div style="text-align: right;">
          <div style="font-weight: 700; color: var(--status-safe); font-size: 14px;">₹${Number(r.mrp).toFixed(2)}</div>
          <span class="badge badge-info" style="font-size: 10.5px;">GST ${r.gst}%</span>
        </div>
      </div>
    `).join('');

    window._lastSearchResults = results;
    dropdown.style.display = 'block';
  }, 250);
}

function selectMedicineForBill(index) {
  const med = (window._lastSearchResults || [])[index];
  if (!med) return;

  const dropdown = document.getElementById('bill-search-results-dropdown');
  const searchInput = document.getElementById('bill-medicine-search-input');
  if (dropdown) dropdown.style.display = 'none';
  if (searchInput) searchInput.value = '';

  // FEFO: Find all active batches for this product in inventory
  const relatedBatches = availableInventoryCache.filter(p => 
    (p.name && p.name.toLowerCase() === med.name.toLowerCase()) ||
    (p.product_name && p.product_name.toLowerCase() === med.name.toLowerCase())
  );

  let batchesList = [];
  if (relatedBatches.length > 0) {
    batchesList = relatedBatches.map(b => ({
      productId: b.id,
      batchNumber: b.batch_number,
      expiryDate: b.expiry_date ? b.expiry_date.split('T')[0] : '2028-12-31',
      stock: b.quantity,
      mrp: b.unit_price,
      pricePerUnit: b.price_per_unit || b.loose_tablet_price,
      unitsPerPack: b.units_per_pack || b.tablets_per_strip || 10
    })).sort((a, b) => (a.expiryDate > b.expiryDate ? 1 : -1));
  } else {
    batchesList = [{
      productId: med.productId || (availableInventoryCache[0] ? availableInventoryCache[0].id : 1),
      batchNumber: med.batchNumber,
      expiryDate: med.expiryDate,
      stock: med.stock,
      mrp: med.mrp,
      pricePerUnit: med.pricePerUnit,
      unitsPerPack: med.unitsPerPack || 10
    }];
  }

  const primaryBatch = batchesList[0];
  const unitsPerPack = Number(primaryBatch.unitsPerPack || med.unitsPerPack || 10);
  const packPrice = Number(primaryBatch.mrp || med.mrp || 50.0);
  const loosePrice = primaryBatch.pricePerUnit ? Number(primaryBatch.pricePerUnit) : Number((packPrice / unitsPerPack).toFixed(2));

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
    unitType: 'strip', // 'strip' (full pack) vs 'loose' (loose/open tablets)
    packPrice: packPrice,
    unitsPerPack: unitsPerPack,
    loosePrice: loosePrice,
    rate: packPrice,
    quantity: 1,
    freeQuantity: 0,
    discountPercent: 0.0,
    gstRate: Number(med.gst) || 12.0,
    batches: batchesList
  };

  activeBillState.items.push(newItem);
  renderBillItemsTable();
  recalculateTotals();

  // Focus the Qty field of the newly added row
  setTimeout(() => {
    const qtyInputs = document.querySelectorAll('.item-qty-input');
    if (qtyInputs.length > 0) {
      const lastQty = qtyInputs[qtyInputs.length - 1];
      lastQty.focus();
      lastQty.select();
    }
  }, 50);
}

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
          <div style="font-size: 32px; margin-bottom: 8px;">🛒</div>
          <div style="font-weight: 600; font-size: 14px;">No medicines in active bill</div>
          <div style="font-size: 12px; margin-top: 4px;">Type medicine name or salt in the search box above to add items via FEFO order.</div>
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

  const promptBox = document.getElementById('pending-customer-prompt');
  if (promptBox) {
    if (mode === 'PENDING') {
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
// COMMITTING BILL & PDF GENERATION
// ----------------------------------------------------

async function commitBillTransaction(printPdf = false, saveAndNew = false) {
  if (activeBillState.items.length === 0) {
    alert('Cannot save empty bill. Please add at least one medicine.');
    return;
  }

  // Validate customer for Pending payment mode
  let finalCustomerName = (activeBillState.customer ? activeBillState.customer.name : 'Walk-in Customer');
  let finalCustomerPhone = (activeBillState.customer && activeBillState.customer.phone !== 'Cash Sale' ? activeBillState.customer.phone : null);

  if (activeBillState.paymentMode === 'PENDING') {
    const inlineName = (activeBillState.pendingCustomerName || (document.getElementById('pending-customer-name-input') ? document.getElementById('pending-customer-name-input').value : '')).trim();
    if (finalCustomerName === 'Walk-in Customer' || !finalCustomerName) {
      if (!inlineName) {
        alert('Please enter a Customer / Patient name to record this pending payment in the ledger.');
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

  const payload = {
    items: payloadItems,
    payment_method: activeBillState.paymentMode || 'CASH',
    customer_name: finalCustomerName,
    customer_phone: finalCustomerPhone,
    notes: `Retail POS Sale - ${activeBillState.invoiceNumber}`,
    is_interstate: false,
    discount_type: activeBillState.billDiscountPercent > 0 ? 'percent' : null,
    discount_value: Number(activeBillState.billDiscountPercent) || 0.0
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
    if (saveBtn && saveBtn.disabled) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = originalText;
    }
  }
}

function resetBillForm() {
  activeBillState = {
    customer: billingCustomersCache[0] || { id: 1, name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
    pendingCustomerName: '',
    invoiceNumber: generateBillInvoiceNumber(),
    invoiceDate: new Date().toISOString().split('T')[0],
    paymentMode: 'CASH',
    billDiscountPercent: 0.0,
    manualRoundOff: 0.0,
    useManualRoundOff: false,
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

  const searchInput = document.getElementById('bill-medicine-search-input');
  if (searchInput) {
    searchInput.value = '';
    searchInput.focus();
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
                <h2 style="margin: 0; font-size: 18px; color: var(--color-brand-deep);">Create New Retail Sale Bill — ExpiryGuard Quick POS</h2>
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
          <div class="billing-search-box">
            <input type="text" id="bill-medicine-search-input" class="form-input" style="font-size: 14px; padding: 10px 14px;"
                   placeholder="🔎 Type medicine name, brand, or generic salt (e.g. Augmentin, Dolo, Pantocid)..."
                   oninput="handleMedicineSearchInput(this.value)" autocomplete="off">
            <div id="bill-search-results-dropdown" class="billing-search-dropdown"></div>
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
