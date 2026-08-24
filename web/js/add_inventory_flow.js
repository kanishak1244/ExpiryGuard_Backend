/**
 * ExpiryGuard ERP — Refined Add Inventory Flow & Multi-Medicine Session Manager
 */

let inventoryCart = [];
let selectedMedicineMeta = null;
let addInventorySuppliers = [];

document.addEventListener('DOMContentLoaded', async () => {
  createAddInventoryModalDOM();
  await refreshFlowSuppliers();
});

async function refreshFlowSuppliers() {
  try {
    addInventorySuppliers = await api.getSuppliers();
    const sel = document.getElementById('inv-flow-supplier');
    if (sel) {
      sel.innerHTML = '<option value="">-- Select Supplier (Optional) --</option>' +
        addInventorySuppliers.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
    }
  } catch (err) {
    console.error("Failed to load suppliers for inventory flow:", err);
  }
}

function createAddInventoryModalDOM() {
  if (document.getElementById('add-inventory-modal')) return;

  const modalHtml = `
  <div id="add-inventory-modal" class="modal-overlay">
    <div class="modal-card" style="max-width: 960px; max-height: 90vh; overflow-y: auto;">
      
      <!-- Modal Header -->
      <div class="modal-header" style="border-bottom: 1px solid var(--border-color); padding-bottom: 12px;">
        <div>
          <h2 style="margin: 0; font-size: 20px; color: var(--dark-text);">+ Add Inventory Stock</h2>
          <p style="font-size: 13px; color: var(--muted-text); margin: 4px 0 0 0;">Receive new stock from suppliers, parse bills, or search medicines manually.</p>
        </div>
        <button class="close-btn" onclick="closeAddInventoryModal()">&times;</button>
      </div>

      <!-- Step 1: Choice Hub (Scan Bill vs Search Medicine vs Bulk Excel) -->
      <div id="inv-step-choice" style="display: block; padding: 24px 0;">
        <h3 style="text-align: center; margin-bottom: 20px; color: var(--dark-text);">How would you like to add stock?</h3>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px;">
          <!-- Option 1: Scan / Upload Bill -->
          <div class="card" style="padding: 20px; text-align: center; cursor: pointer; border: 2px solid var(--border-color); transition: all 0.2s ease;"
               onclick="triggerScanBillOption()" onmouseover="this.style.borderColor='var(--primary-green)'" onmouseout="this.style.borderColor='var(--border-color)'">
            <div style="font-size: 40px; margin-bottom: 8px;">📄</div>
            <h3 style="margin-bottom: 6px; font-size: 16px;">Scan / Upload Bill</h3>
            <p style="font-size: 12.5px; color: var(--muted-text); margin: 0;">Upload supplier invoice image or PDF. Gemini AI vision extracts medicines, batches & prices.</p>
          </div>

          <!-- Option 2: Search Medicine -->
          <div class="card" style="padding: 20px; text-align: center; cursor: pointer; border: 2px solid var(--border-color); transition: all 0.2s ease;"
               onclick="showSearchMedicineStep()" onmouseover="this.style.borderColor='var(--primary-green)'" onmouseout="this.style.borderColor='var(--border-color)'">
            <div style="font-size: 40px; margin-bottom: 8px;">🔎</div>
            <h3 style="margin-bottom: 6px; font-size: 16px;">Search Medicine</h3>
            <p style="font-size: 12.5px; color: var(--muted-text); margin: 0;">Search against 240,000+ Indian medicines database by name, brand, or generic composition.</p>
          </div>

          <!-- Option 3: Bulk Excel Import -->
          <div class="card" style="padding: 20px; text-align: center; cursor: pointer; border: 2px solid var(--border-color); transition: all 0.2s ease;"
               onclick="showBulkImportStep()" onmouseover="this.style.borderColor='var(--primary-green)'" onmouseout="this.style.borderColor='var(--border-color)'">
            <div style="font-size: 40px; margin-bottom: 8px;">📊</div>
            <h3 style="margin-bottom: 6px; font-size: 16px;">Direct Excel / CSV Import</h3>
            <p style="font-size: 12.5px; color: var(--muted-text); margin: 0 0 12px 0;">Onboard hundreds of stock batches directly from spreadsheet without AI processing.</p>
            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
              <button class="btn btn-primary" style="font-size: 12px; padding: 6px 12px;" onclick="event.stopPropagation(); showBulkImportStep();">
                📂 Upload File
              </button>
              <a href="/api/inventory/import-template" download="ExpiryGuard_Inventory_Import_Template.xlsx" class="btn btn-secondary" style="font-size: 12px; padding: 6px 12px; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;" onclick="event.stopPropagation();">
                <span>📥 Template</span>
              </a>
            </div>
          </div>
        </div>
      </div>

      <!-- Step: Bulk Excel / CSV Direct Upload (No Gemini AI) -->
      <div id="inv-step-bulk-import" style="display: none; padding: 16px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="showChoiceStep()">← Back to Options</button>
          <a href="/api/inventory/import-template" download="ExpiryGuard_Inventory_Import_Template.xlsx" class="btn btn-secondary" style="padding: 4px 12px; font-size: 12px; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
            <span>📥 Download Template (.xlsx)</span>
          </a>
        </div>

        <div style="text-align: center; border: 2px dashed var(--border-color); border-radius: var(--radius-md); padding: 36px 20px; background: var(--bg-main); transition: all 0.2s ease;"
             id="bulk-import-dropzone" ondragover="handleBulkDragOver(event)" ondragleave="handleBulkDragLeave(event)" ondrop="handleBulkDropFile(event)">
          <div style="font-size: 48px; margin-bottom: 12px;">📊</div>
          <h3 style="margin-bottom: 6px;">Direct Excel / CSV Spreadsheet Upload</h3>
          <p style="font-size: 13px; color: var(--muted-text); max-width: 480px; margin: 0 auto 16px auto;">
            Upload your filled <code>.xlsx</code> or <code>.csv</code> spreadsheet. All stock batches will be verified and added directly to your inventory without AI wait times.
          </p>

          <input type="file" id="bulk-import-file-input" accept=".xlsx, .xls, .csv" style="display: none;" onchange="handleBulkFileSelected(event)">
          
          <button type="button" class="btn btn-primary" style="padding: 10px 24px; font-size: 14px;" onclick="document.getElementById('bulk-import-file-input').click()">
            📂 Choose Excel or CSV File
          </button>
          <div id="bulk-import-selected-filename" style="margin-top: 12px; font-size: 13px; color: var(--primary-green); font-weight: 600;"></div>
        </div>

        <!-- Import Progress & Results Container -->
        <div id="bulk-import-results-card" style="display: none; margin-top: 20px; padding: 16px; border-radius: var(--radius-md); background: #FFFFFF; border: 1px solid var(--border-color);">
          <div id="bulk-import-status-text" style="font-weight: 600; margin-bottom: 10px; font-size: 14px;"></div>
          <div id="bulk-import-error-list" style="color: #DC2626; font-size: 12.5px; max-height: 150px; overflow-y: auto; margin-bottom: 12px;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 10px;">
            <button class="btn btn-secondary" onclick="resetBulkImportView()">Upload Another File</button>
            <button class="btn btn-primary" onclick="closeAddInventoryModal(); if (typeof applyInventoryFilters === 'function') { window.location.reload(); }">Done / View Live Inventory</button>
          </div>
        </div>
      </div>

      <!-- Step 2: Search Medicine & Autocomplete -->
      <div id="inv-step-search" style="display: none; padding: 16px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="showChoiceStep()">← Back to Options</button>
          <button class="btn btn-primary" style="padding: 4px 12px; font-size: 12px;" onclick="showCustomMedicineForm()">+ Add New Medicine</button>
        </div>

        <div class="form-group" style="position: relative; margin-bottom: 20px;">
          <label class="form-label" style="font-size: 14px; font-weight: 600;">Search Medicine Name / Brand / Generic</label>
          <input type="text" id="inv-medicine-search-input" class="form-input" placeholder="Type medicine name (e.g. Paracetamol, Amoxicillin, ABC)..."
                 oninput="handleMedicineAutocomplete(this.value)" autocomplete="off" style="font-size: 15px; padding: 10px 14px;">
        </div>

        <!-- Autocomplete Suggestions List -->
        <div id="inv-search-results-list" style="display: flex; flex-direction: column; gap: 8px; max-height: 340px; overflow-y: auto;">
          <p style="text-align: center; color: var(--muted-text); padding: 20px;">Start typing medicine name to see autocomplete suggestions...</p>
        </div>
      </div>

      <!-- Custom Medicine Form (Fallback) -->
      <div id="inv-step-custom-med" style="display: none; padding: 16px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <h3 style="margin: 0;">+ Register Custom Medicine</h3>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="showSearchMedicineStep()">← Back to Search</button>
        </div>

        <form onsubmit="handleCustomMedicineSubmit(event)">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Medicine Name *</label>
              <input type="text" id="custom-med-name" class="form-input" required placeholder="ABC 500mg Tablet">
            </div>
            <div class="form-group">
              <label class="form-label">Manufacturer / Brand</label>
              <input type="text" id="custom-med-brand" class="form-input" placeholder="XYZ Pharma">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Generic / Active Composition</label>
              <input type="text" id="custom-med-comp" class="form-input" placeholder="Paracetamol IP 500mg">
            </div>
            <div class="form-group">
              <label class="form-label">Category / Dosage Form</label>
              <select id="custom-med-category" class="form-input">
                <option value="allopathy">Tablet / Capsule</option>
                <option value="syrup">Syrup / Liquid</option>
                <option value="injection">Injection</option>
                <option value="ointment">Ointment / Cream</option>
                <option value="ayurvedic">Ayurvedic / Herbal</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Tablets per Strip / Pack</label>
              <input type="number" id="custom-med-units" class="form-input" value="10">
            </div>
            <div class="form-group">
              <label class="form-label">Default MRP (₹)</label>
              <input type="number" step="0.01" id="custom-med-mrp" class="form-input" value="30.00">
            </div>
          </div>
          <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
            <button type="submit" class="btn btn-primary">Save & Continue Stock Entry →</button>
          </div>
        </form>
      </div>

      <!-- Step 3: Batch Details, Quantity Math & Pricing Form -->
      <div id="inv-step-batch" style="display: none; padding: 16px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 16px;">
          <div>
            <span class="badge badge-info" id="batch-selected-form">Tablet</span>
            <h3 id="batch-selected-title" style="margin: 4px 0 0 0; color: var(--primary-green);">Medicine Name</h3>
            <span id="batch-selected-sub" style="font-size: 12px; color: var(--muted-text);">Brand / Composition</span>
          </div>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="showSearchMedicineStep()">Change Medicine</button>
        </div>

        <form id="inv-batch-form" onsubmit="handleBatchFormQueue(event)">
          <!-- Expiry & Batch Details -->
          <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
            <h4 style="margin: 0 0 10px 0;">1. Batch & Expiry Validation</h4>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Batch Number *</label>
                <input type="text" id="inv-flow-batch-num" class="form-input" required placeholder="BATCH-2026-01">
              </div>
              <div class="form-group">
                <label class="form-label">Manufacturing Date</label>
                <input type="date" id="inv-flow-mfg-date" class="form-input">
              </div>
              <div class="form-group">
                <label class="form-label">Expiry Date *</label>
                <div style="display: flex; gap: 8px; align-items: center;">
                  <input type="date" id="inv-flow-exp-date" class="form-input" required onchange="calcExpiryBadge(this.value)">
                  <span id="expiry-badge-preview" class="badge badge-success">🟢 Active</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Quantity Math Calculator -->
          <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
            <h4 style="margin: 0 0 10px 0;">2. Quantity Calculator (Boxes / Strips / Loose)</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1.2fr; gap: 12px; align-items: center;">
              <div class="form-group">
                <label class="form-label">Number of Boxes</label>
                <input type="number" id="qty-boxes" class="form-input" value="1" min="1" oninput="calcTotalQuantity()">
              </div>
              <div class="form-group">
                <label class="form-label">Strips per Box</label>
                <input type="number" id="qty-strips-box" class="form-input" value="10" min="1" oninput="calcTotalQuantity()">
              </div>
              <div class="form-group">
                <label class="form-label">Tablets per Strip</label>
                <input type="number" id="qty-tablets-strip" class="form-input" value="10" min="1" oninput="calcTotalQuantity()">
              </div>
              <div class="form-group">
                <label class="form-label">Total Stock Quantity (Strips)</label>
                <input type="number" id="qty-total-strips" class="form-input" value="10" required readonly style="background: #E2E8F0; font-weight: bold;">
                <span id="qty-total-tablets-label" style="font-size: 11px; color: var(--primary-green); font-weight: 600;">= 100 Total Tablets</span>
              </div>
            </div>
          </div>

          <!-- Pricing & Taxes -->
          <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
            <h4 style="margin: 0 0 10px 0;">3. Pricing & GST Calculation</h4>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Purchase Price per Strip (₹) *</label>
                <input type="number" step="0.01" id="price-purchase" class="form-input" required value="15.00" oninput="calcPricingPerPill()">
              </div>
              <div class="form-group">
                <label class="form-label">MRP / Retail Price per Strip (₹) *</label>
                <input type="number" step="0.01" id="price-selling" class="form-input" required value="30.00" oninput="calcPricingPerPill()">
              </div>
              <div class="form-group">
                <label class="form-label">Calculated Loose Tablet Price</label>
                <input type="text" id="price-loose-pill" class="form-input" value="₹3.00 / pill" readonly style="background: #E2E8F0;">
              </div>
              <div class="form-group">
                <label class="form-label">GST Tax Rate (%)</label>
                <select id="price-gst-rate" class="form-input">
                  <option value="12.0">12% (Standard Pharma)</option>
                  <option value="5.0">5% (Essential Medicines)</option>
                  <option value="18.0">18% (Disinfectants/Supplies)</option>
                  <option value="0.0">0% (Nil / Life Saving)</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Supplier Selection -->
          <div class="form-group" style="margin-bottom: 20px;">
            <label class="form-label">Linked Supplier Distributor</label>
            <div style="display: flex; gap: 8px;">
              <select id="inv-flow-supplier" class="form-input">
                <option value="">-- Select Supplier (Optional) --</option>
              </select>
              <button type="button" class="btn btn-secondary" style="white-space: nowrap;" onclick="openAddSupplierModal()">+ Add Supplier</button>
            </div>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-color); padding-top: 16px;">
            <button type="button" class="btn btn-secondary" onclick="showSearchMedicineStep()">Cancel</button>
            <button type="submit" class="btn btn-primary">+ Add Medicine to Inventory Session Queue</button>
          </div>
        </form>
      </div>

      <!-- Step 4: Multi-Medicine Session Queue Summary -->
      <div id="inv-step-queue-summary" style="margin-top: 20px; border-top: 2px solid var(--border-color); padding-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h4 style="margin: 0;"><span id="cart-item-count">0</span> Medicines Queued in Current Session</h4>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="showSearchMedicineStep()">+ Add Another Medicine</button>
        </div>

        <div class="table-responsive" style="max-height: 180px; overflow-y: auto;">
          <table class="data-table" style="font-size: 12px;">
            <thead>
              <tr>
                <th>Medicine</th>
                <th>Batch #</th>
                <th>Qty (Strips)</th>
                <th>Purchase Price</th>
                <th>MRP</th>
                <th>Expiry</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="cart-items-tbody">
              <tr><td colspan="7" style="text-align: center; color: var(--muted-text); padding: 12px;">No medicines queued yet. Search or scan a bill to add.</td></tr>
            </tbody>
          </table>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; background: var(--very-light-green); padding: 14px 20px; border-radius: var(--radius-md); margin-top: 16px;">
          <div>
            <span style="font-size: 13px; color: var(--muted-text);">Total Stock Value:</span>
            <h3 id="cart-total-value" style="margin: 0; color: var(--primary-green);">₹0.00</h3>
          </div>
          <button class="btn btn-primary" id="commit-inventory-btn" style="padding: 10px 24px; font-size: 15px;" onclick="commitInventorySession()" disabled>
            Add All Medicines to Active Inventory
          </button>
        </div>
      </div>

    </div>
  </div>

  <!-- DUPLICATE BATCH ALERT MODAL -->
  <div id="duplicate-batch-modal" class="modal-overlay" style="z-index: 1100;">
    <div class="modal-card" style="max-width: 480px; text-align: center; padding: 24px;">
      <div style="font-size: 48px; margin-bottom: 8px;">⚠️</div>
      <h3 style="margin-bottom: 8px;">Duplicate Batch Detected</h3>
      <p id="dup-modal-msg" style="font-size: 14px; color: var(--muted-text); margin-bottom: 20px;">This batch already exists in your inventory.</p>
      
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <button class="btn btn-primary" onclick="resolveDuplicateMode('increment')">Add to Existing Stock Quantity</button>
        <button class="btn btn-secondary" onclick="resolveDuplicateMode('separate')">Create Separate Inventory Entry</button>
        <button class="btn btn-secondary" style="color: var(--error-red);" onclick="closeDuplicateModal()">Cancel Item</button>
      </div>
    </div>
  </div>
  `;

  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function openAddInventoryModal() {
  if (!document.getElementById('add-inventory-modal')) {
    createAddInventoryModalDOM();
  }
  inventoryCart = [];
  renderCartQueue();
  showChoiceStep();
  refreshFlowSuppliers();
  const modal = document.getElementById('add-inventory-modal');
  if (modal) modal.classList.add('active');
}

function closeAddInventoryModal() {
  document.getElementById('add-inventory-modal').classList.remove('active');
}

function showChoiceStep() {
  document.getElementById('inv-step-choice').style.display = 'block';
  document.getElementById('inv-step-search').style.display = 'none';
  document.getElementById('inv-step-custom-med').style.display = 'none';
  document.getElementById('inv-step-batch').style.display = 'none';
  const bulkStep = document.getElementById('inv-step-bulk-import');
  if (bulkStep) bulkStep.style.display = 'none';
}

function showBulkImportStep() {
  document.getElementById('inv-step-choice').style.display = 'none';
  document.getElementById('inv-step-search').style.display = 'none';
  document.getElementById('inv-step-custom-med').style.display = 'none';
  document.getElementById('inv-step-batch').style.display = 'none';
  const bulkStep = document.getElementById('inv-step-bulk-import');
  if (bulkStep) bulkStep.style.display = 'block';
  resetBulkImportView();
}

function showSearchMedicineStep() {
  document.getElementById('inv-step-choice').style.display = 'none';
  document.getElementById('inv-step-search').style.display = 'block';
  document.getElementById('inv-step-custom-med').style.display = 'none';
  document.getElementById('inv-step-batch').style.display = 'none';
  const bulkStep = document.getElementById('inv-step-bulk-import');
  if (bulkStep) bulkStep.style.display = 'none';
  document.getElementById('inv-medicine-search-input').focus();
}

function handleBulkFileSelected(event) {
  const file = event.target.files[0];
  if (file) uploadSpreadsheetFile(file);
}

function handleBulkDragOver(event) {
  event.preventDefault();
  event.stopPropagation();
  const dropzone = document.getElementById('bulk-import-dropzone');
  if (dropzone) dropzone.style.borderColor = 'var(--primary-green)';
}

function handleBulkDragLeave(event) {
  event.preventDefault();
  event.stopPropagation();
  const dropzone = document.getElementById('bulk-import-dropzone');
  if (dropzone) dropzone.style.borderColor = 'var(--border-color)';
}

function handleBulkDropFile(event) {
  event.preventDefault();
  event.stopPropagation();
  const dropzone = document.getElementById('bulk-import-dropzone');
  if (dropzone) dropzone.style.borderColor = 'var(--border-color)';
  
  if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length > 0) {
    uploadSpreadsheetFile(event.dataTransfer.files[0]);
  }
}

async function uploadSpreadsheetFile(file) {
  const fnElem = document.getElementById('bulk-import-selected-filename');
  const resCard = document.getElementById('bulk-import-results-card');
  const statusText = document.getElementById('bulk-import-status-text');
  const errorList = document.getElementById('bulk-import-error-list');

  fnElem.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  resCard.style.display = 'block';
  statusText.innerHTML = `⏳ Parsing and onboarding <strong>${file.name}</strong> directly into live inventory...`;
  statusText.style.color = 'var(--primary-green)';
  errorList.innerHTML = '';

  try {
    let res;
    if (window.api && typeof window.api.uploadInventorySpreadsheet === 'function') {
      res = await window.api.uploadInventorySpreadsheet(file);
    } else {
      const formData = new FormData();
      formData.append('file', file);
      const token = localStorage.getItem('expiryguard_token');
      const r = await fetch('/api/inventory/import', {
        method: 'POST',
        headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        body: formData
      });
      if (!r.ok) {
        const errData = await r.json().catch(() => ({}));
        throw new Error(errData.detail || `Import failed with status ${r.status}`);
      }
      res = await r.json();
    }

    if (res.imported_count > 0) {
      statusText.innerHTML = `✅ <strong>Success!</strong> ${res.imported_count} medicine batches imported directly into active inventory.`;
      statusText.style.color = '#059669';
    } else {
      statusText.innerHTML = `⚠️ <strong>Import Warning:</strong> No rows imported. Check errors below.`;
      statusText.style.color = '#D97706';
    }

    if (res.errors && res.errors.length > 0) {
      errorList.innerHTML = `<strong>Issues encountered (${res.errors.length}):</strong><ul style="margin: 6px 0 0 16px; padding: 0;">` +
        res.errors.map(e => `<li>${e}</li>`).join('') + `</ul>`;
    }

    // Refresh live inventory table if on inventory page
    if (typeof loadInventoryData === 'function') {
      loadInventoryData();
    }
  } catch (err) {
    console.error('Bulk import error:', err);
    statusText.innerHTML = `❌ <strong>Failed to import:</strong> ${err.message}`;
    statusText.style.color = '#DC2626';
  }
}

function resetBulkImportView() {
  const fileInput = document.getElementById('bulk-import-file-input');
  if (fileInput) fileInput.value = '';
  const fnElem = document.getElementById('bulk-import-selected-filename');
  if (fnElem) fnElem.textContent = '';
  const resCard = document.getElementById('bulk-import-results-card');
  if (resCard) resCard.style.display = 'none';
}

function showCustomMedicineForm() {
  document.getElementById('inv-step-search').style.display = 'none';
  document.getElementById('inv-step-custom-med').style.display = 'block';
}

function triggerScanBillOption() {
  closeAddInventoryModal();
  if (window.location.pathname.includes('documents.html')) {
    triggerUploadClick();
  } else {
    window.location.href = 'documents.html';
  }
}

let searchDebounce = null;
let currentSearchRequestId = 0;

function handleMedicineAutocomplete(val) {
  clearTimeout(searchDebounce);
  const resultsList = document.getElementById('inv-search-results-list');
  const cleanVal = (val || '').trim();

  if (cleanVal.length < 2) {
    currentSearchRequestId++;
    resultsList.innerHTML = '<p style="text-align: center; color: var(--muted-text); padding: 20px;">Type at least 2 characters to search Indian medicine catalog...</p>';
    return;
  }

  // Instant visual feedback for user action responsiveness
  resultsList.innerHTML = '<div style="text-align: center; color: var(--muted-text); padding: 20px;"><div class="pulse-dot" style="display: inline-block; margin-right: 6px;"></div> Searching catalog for "' + escapeHtml(cleanVal) + '"...</div>';

  const requestId = ++currentSearchRequestId;

  searchDebounce = setTimeout(async () => {
    try {
      const results = await api.searchCatalog(cleanVal, 20);
      // Discard stale out-of-order responses
      if (requestId === currentSearchRequestId) {
        renderAutocompleteResults(results, cleanVal);
      }
    } catch (err) {
      if (requestId === currentSearchRequestId) {
        console.error("Autocomplete search error:", err);
        resultsList.innerHTML = '<p style="text-align: center; color: var(--error-red); padding: 16px;">Failed to load search results. Please try again.</p>';
      }
    }
  }, 280);
}

function escapeHtml(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderAutocompleteResults(results, searchVal) {
  const resultsList = document.getElementById('inv-search-results-list');

  if (!results || results.length === 0) {
    resultsList.innerHTML = `
      <div style="text-align: center; padding: 24px; background: var(--bg-main); border-radius: var(--radius-md);">
        <p style="margin-bottom: 8px; font-weight: 500;">No medicines found matching "${escapeHtml(searchVal)}"</p>
        <button class="btn btn-primary" onclick="showCustomMedicineForm()">+ Add New Medicine '${escapeHtml(searchVal)}'</button>
      </div>
    `;
    return;
  }

  resultsList.innerHTML = results.map(item => {
    const escapedItem = JSON.stringify(item).replace(/'/g, "&#39;");
    return `
      <div class="card" style="padding: 12px 16px; cursor: pointer; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"
           onclick='selectCatalogMedicine(${escapedItem})'
           onmouseover="this.style.borderColor='var(--color-brand-deep)'" onmouseout="this.style.borderColor='var(--border-color)'">
        <div>
          <strong style="font-size: 14px; color: var(--dark-text);">${escapeHtml(item.product_name)}</strong>
          <div style="font-size: 12px; color: var(--muted-text); margin-top: 2px;">
            ${item.brand ? `Brand: ${escapeHtml(item.brand)} | ` : ''} Composition: ${escapeHtml(item.composition || 'N/A')} | HSN: ${escapeHtml(item.hsn_code || '3004')}
          </div>
        </div>
        <div style="text-align: right;">
          <span class="badge badge-info" style="text-transform: capitalize;">${escapeHtml(item.category || 'allopathy')}</span>
          <div style="font-size: 13px; font-weight: 600; margin-top: 4px; font-family: var(--font-mono);">MRP ₹${(item.default_price || 0).toFixed(2)}</div>
        </div>
      </div>
    `;
  }).join('');
}

function selectCatalogMedicine(med) {
  selectedMedicineMeta = med;
  
  document.getElementById('batch-selected-title').textContent = med.product_name;
  document.getElementById('batch-selected-sub').textContent = `${med.brand ? med.brand + ' | ' : ''}${med.composition || 'Allopathy'}`;
  document.getElementById('batch-selected-form').textContent = med.category || 'Tablet';

  document.getElementById('qty-tablets-strip').value = med.tablets_per_strip || med.units_per_pack || 10;
  document.getElementById('price-selling').value = med.default_price || 30.00;
  document.getElementById('price-purchase').value = roundTwo(med.default_price ? med.default_price * 0.6 : 18.00);
  document.getElementById('price-gst-rate').value = (med.gst_rate || 12.0).toFixed(1);

  calcTotalQuantity();
  calcPricingPerPill();

  // Set default expiry 2 years in future
  const d = new Date();
  d.setFullYear(d.getFullYear() + 2);
  const expStr = d.toISOString().split('T')[0];
  document.getElementById('inv-flow-exp-date').value = expStr;
  calcExpiryBadge(expStr);

  document.getElementById('inv-step-search').style.display = 'none';
  document.getElementById('inv-step-batch').style.display = 'block';
}

async function handleCustomMedicineSubmit(e) {
  e.preventDefault();
  const payload = {
    product_name: document.getElementById('custom-med-name').value,
    brand: document.getElementById('custom-med-brand').value,
    category: document.getElementById('custom-med-category').value,
    composition: document.getElementById('custom-med-comp').value,
    tablets_per_strip: parseInt(document.getElementById('custom-med-units').value) || 10,
    default_price: parseFloat(document.getElementById('custom-med-mrp').value) || 30.00,
    hsn_code: "3004",
    gst_rate: 12.0
  };

  try {
    const newMed = await api.createCustomMedicine(payload);
    selectCatalogMedicine(newMed);
  } catch (err) {
    alert(`Failed to create custom medicine: ${err.message}`);
  }
}

function calcTotalQuantity() {
  const boxes = parseInt(document.getElementById('qty-boxes').value) || 1;
  const stripsBox = parseInt(document.getElementById('qty-strips-box').value) || 10;
  const tabletsStrip = parseInt(document.getElementById('qty-tablets-strip').value) || 10;

  const totalStrips = boxes * stripsBox;
  const totalTablets = totalStrips * tabletsStrip;

  document.getElementById('qty-total-strips').value = totalStrips;
  document.getElementById('qty-total-tablets-label').textContent = `= ${totalTablets} Total Loose Pills/Units`;
  calcPricingPerPill();
}

function calcPricingPerPill() {
  const mrp = parseFloat(document.getElementById('price-selling').value) || 0.0;
  const tabletsStrip = parseInt(document.getElementById('qty-tablets-strip').value) || 10;
  
  if (tabletsStrip > 0 && mrp > 0) {
    const loose = (mrp / tabletsStrip).toFixed(2);
    document.getElementById('price-loose-pill').value = `₹${loose} / pill`;
  } else {
    document.getElementById('price-loose-pill').value = `N/A`;
  }
}

function calcExpiryBadge(expDateStr) {
  const badge = document.getElementById('expiry-badge-preview');
  if (!expDateStr) return;

  const exp = new Date(expDateStr);
  const today = new Date();
  const diffDays = Math.ceil((exp - today) / (1000 * 60 * 60 * 24));

  if (diffDays <= 0) {
    badge.className = 'badge badge-error';
    badge.textContent = '🔴 Expired';
  } else if (diffDays <= 30) {
    badge.className = 'badge badge-warning';
    badge.textContent = '🟠 Expiring Soon';
  } else {
    badge.className = 'badge badge-success';
    badge.textContent = '🟢 Active';
  }
}

let pendingBatchPayload = null;

async function handleBatchFormQueue(e) {
  e.preventDefault();
  if (!selectedMedicineMeta) return;

  const batchNum = document.getElementById('inv-flow-batch-num').value.trim();
  const pName = selectedMedicineMeta.product_name;

  pendingBatchPayload = {
    product_name: pName,
    brand: selectedMedicineMeta.brand || '',
    category: selectedMedicineMeta.category || 'allopathy',
    hsn_code: selectedMedicineMeta.hsn_code || '3004',
    gst_rate: parseFloat(document.getElementById('price-gst-rate').value) || 12.0,
    batch_number: batchNum,
    quantity: parseInt(document.getElementById('qty-total-strips').value) || 1,
    purchase_price: parseFloat(document.getElementById('price-purchase').value) || 0.0,
    unit_price: parseFloat(document.getElementById('price-selling').value) || 0.0,
    units_per_pack: parseInt(document.getElementById('qty-tablets-strip').value) || 10,
    manufacturing_date: document.getElementById('inv-flow-mfg-date').value || null,
    expiry_date: document.getElementById('inv-flow-exp-date').value,
    supplier_id: document.getElementById('inv-flow-supplier').value ? parseInt(document.getElementById('inv-flow-supplier').value) : null,
    duplicate_mode: 'auto'
  };

  // Check duplicate batch
  try {
    const dupCheck = await api.checkDuplicateBatch(pName, batchNum);
    if (dupCheck.is_duplicate) {
      document.getElementById('dup-modal-msg').textContent = dupCheck.message;
      document.getElementById('duplicate-batch-modal').classList.add('active');
      return;
    }
  } catch (err) {}

  addPendingItemToQueue();
}

function resolveDuplicateMode(mode) {
  if (pendingBatchPayload) {
    pendingBatchPayload.duplicate_mode = mode;
  }
  closeDuplicateModal();
  addPendingItemToQueue();
}

function closeDuplicateModal() {
  document.getElementById('duplicate-batch-modal').classList.remove('active');
}

function addPendingItemToQueue() {
  if (!pendingBatchPayload) return;

  inventoryCart.push(pendingBatchPayload);
  pendingBatchPayload = null;
  selectedMedicineMeta = null;
  document.getElementById('inv-batch-form').reset();

  renderCartQueue();
  showSearchMedicineStep();
}

function removeFromQueue(idx) {
  inventoryCart.splice(idx, 1);
  renderCartQueue();
}

function renderCartQueue() {
  const tbody = document.getElementById('cart-items-tbody');
  const countSpan = document.getElementById('cart-item-count');
  const totalValH3 = document.getElementById('cart-total-value');
  const commitBtn = document.getElementById('commit-inventory-btn');

  countSpan.textContent = inventoryCart.length;

  if (inventoryCart.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--muted-text); padding: 12px;">No medicines queued yet. Search or scan a bill to add.</td></tr>';
    totalValH3.textContent = '₹0.00';
    commitBtn.disabled = true;
    return;
  }

  commitBtn.disabled = false;
  let grandTotal = 0;

  tbody.innerHTML = inventoryCart.map((item, idx) => {
    const lineVal = item.quantity * item.unit_price;
    grandTotal += lineVal;

    return `
      <tr>
        <td><strong>${item.product_name}</strong></td>
        <td>${item.batch_number}</td>
        <td>${item.quantity} strips</td>
        <td>₹${item.purchase_price.toFixed(2)}</td>
        <td>₹${item.unit_price.toFixed(2)}</td>
        <td>${item.expiry_date}</td>
        <td><button class="btn btn-secondary" style="padding: 2px 6px; color: var(--error-red);" onclick="removeFromQueue(${idx})">🗑️</button></td>
      </tr>
    `;
  }).join('');

  totalValH3.textContent = `₹${grandTotal.toFixed(2)}`;
}

async function commitInventorySession() {
  if (inventoryCart.length === 0) return;

  try {
    const res = await api.batchAddInventory(inventoryCart);
    alert(res.message || `Successfully committed ${inventoryCart.length} medicines to active inventory!`);
    inventoryCart = [];
    closeAddInventoryModal();

    // Reload page tables if on inventory or dashboard
    if (typeof loadInventoryProducts === 'function') loadInventoryProducts();
    if (typeof loadDashboardData === 'function') loadDashboardData();
  } catch (err) {
    alert(`Failed to commit inventory: ${err.message}`);
  }
}

function roundTwo(num) {
  return Math.round(num * 100) / 100;
}

window.openAddInventoryForMedicine = function(medName, brand, suggestedQty, mrp) {
  openAddInventoryModal();
  const catItem = {
    product_name: medName,
    brand: brand || '',
    category: 'allopathy',
    composition: '',
    tablets_per_strip: 10,
    default_price: mrp || 30.0,
    hsn_code: '3004',
    gst_rate: 12.0
  };
  selectCatalogMedicine(catItem);
  if (suggestedQty) {
    const boxInput = document.getElementById('qty-boxes');
    const stripsInput = document.getElementById('qty-strips-box');
    if (boxInput && stripsInput) {
      boxInput.value = 1;
      stripsInput.value = Math.max(1, parseInt(suggestedQty) || 10);
      calcTotalQuantity();
    }
  }
};

