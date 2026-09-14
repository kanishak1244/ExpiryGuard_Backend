/**
 * DawaiFlow Web App — Sales Return / Returned Items Engine
 * Handles 3-step Return Workflow: Select Item -> Find Original Sale -> Process Return & Stock Restoration
 */

let selectedBillReturnData = null;
let activeReturnsPeriod = 'today';
let customStartDate = '';
let customEndDate = '';

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('returns-page')) {
    initReturnsPage();
  }
});

function initReturnsPage() {
  loadTodayReturns();
}

function formatDateYMD(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getPeriodDates(period) {
  const now = new Date();

  if (period === 'today') {
    const todayStr = formatDateYMD(now);
    return { start: todayStr, end: todayStr };
  } else if (period === 'yesterday') {
    const yest = new Date(now);
    yest.setDate(now.getDate() - 1);
    const yestStr = formatDateYMD(yest);
    return { start: yestStr, end: yestStr };
  } else if (period === 'week') {
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? -6 : 1);
    const monday = new Date(now.setDate(diff));
    return { start: formatDateYMD(monday), end: formatDateYMD(new Date()) };
  } else if (period === 'month') {
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    return { start: formatDateYMD(firstDay), end: formatDateYMD(new Date()) };
  } else if (period === 'all') {
    return { start: '', end: '' };
  } else if (period === 'custom') {
    return { start: customStartDate, end: customEndDate };
  }
  return { start: formatDateYMD(now), end: formatDateYMD(now) };
}

function setReturnsPeriod(period) {
  activeReturnsPeriod = period;

  // Update active pill button styling
  document.querySelectorAll('#returns-period-pills button').forEach(btn => {
    if (btn.getAttribute('data-period') === period) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  const customContainer = document.getElementById('returns-custom-date-container');
  if (period === 'custom') {
    if (customContainer) customContainer.style.display = 'flex';
    const fromInput = document.getElementById('returns-date-from');
    const toInput = document.getElementById('returns-date-to');
    if (fromInput && !fromInput.value) fromInput.value = formatDateYMD(new Date());
    if (toInput && !toInput.value) toInput.value = formatDateYMD(new Date());
  } else {
    if (customContainer) customContainer.style.display = 'none';
    loadTodayReturns();
  }
}

function applyCustomDateRange() {
  const fromVal = document.getElementById('returns-date-from') ? document.getElementById('returns-date-from').value : '';
  const toVal = document.getElementById('returns-date-to') ? document.getElementById('returns-date-to').value : '';

  if (!fromVal || !toVal) {
    alert('Please select both From and To dates for custom range.');
    return;
  }

  customStartDate = fromVal;
  customEndDate = toVal;
  loadTodayReturns();
}

window.setReturnsPeriod = setReturnsPeriod;
window.applyCustomDateRange = applyCustomDateRange;

async function loadTodayReturns() {
  const tableBody = document.getElementById('returns-list-body');
  const refundTotalEl = document.getElementById('returns-total-refund');
  const countEl = document.getElementById('returns-count');
  const itemsCountEl = document.getElementById('returns-items-count');

  if (!tableBody) return;

  try {
    const searchQuery = document.getElementById('returns-search-input') ? document.getElementById('returns-search-input').value.trim() : '';
    const { start, end } = getPeriodDates(activeReturnsPeriod);

    let url = '/api/sales/returns?limit=1000';
    if (start) url += `&start_date=${encodeURIComponent(start)}`;
    if (end) url += `&end_date=${encodeURIComponent(end)}`;
    if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;

    const res = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('expiryguard_token') || ''}`,
        'Accept': 'application/json'
      }
    });

    if (!res.ok) {
      throw new Error(`Failed to load returns (HTTP ${res.status})`);
    }

    const data = await res.json();
    let returnsList = [];
    let totalRefund = 0;
    let returnsCount = 0;
    let totalItems = 0;

    if (Array.isArray(data)) {
      returnsList = data;
      returnsCount = returnsList.length;
      returnsList.forEach(r => {
        totalRefund += (r.refund_amount || 0);
        totalItems += (r.returned_quantity || 0);
      });
    } else {
      returnsList = data.returns || [];
      returnsCount = data.total_returns_count || returnsList.length;
      totalRefund = data.total_return_value || 0;
      totalItems = data.total_items_returned_count || 0;
    }

    if (refundTotalEl) refundTotalEl.textContent = `₹${totalRefund.toFixed(2)}`;
    if (countEl) countEl.textContent = returnsCount;
    if (itemsCountEl) itemsCountEl.textContent = `${totalItems} items`;

    if (returnsList.length === 0) {
      let mainEmptyMsg = "No returns found for today.";
      let subEmptyMsg = "Process a return to see it appear here.";

      if (activeReturnsPeriod === 'yesterday') {
        mainEmptyMsg = "No returns found for yesterday.";
        subEmptyMsg = "Try selecting a different time period or clear search.";
      } else if (activeReturnsPeriod === 'week') {
        mainEmptyMsg = "No returns found this week.";
        subEmptyMsg = "Try selecting a different time period or clear search.";
      } else if (activeReturnsPeriod === 'month') {
        mainEmptyMsg = "No returns found this month.";
        subEmptyMsg = "Try selecting a different time period or clear search.";
      } else if (activeReturnsPeriod === 'all') {
        mainEmptyMsg = "No return records found.";
        subEmptyMsg = "Process a return to see it appear here.";
      } else if (activeReturnsPeriod === 'custom') {
        mainEmptyMsg = "No returns found for the selected date range.";
        subEmptyMsg = "Try choosing different dates or clear search.";
      }

      if (searchQuery) {
        mainEmptyMsg = `No return records matching "${escapeHtml(searchQuery)}" found.`;
        subEmptyMsg = "Try adjusting your search or selecting a broader time period.";
      }

      tableBody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 28px 16px;">
            <div style="font-size: 22px; margin-bottom: 4px;">🔄</div>
            <div style="font-weight: 700; font-size: 14px; color: var(--color-text-primary);">${mainEmptyMsg}</div>
            <div style="font-size: 12px; color: var(--color-text-muted); margin-top: 2px;">${subEmptyMsg}</div>
          </td>
        </tr>
      `;
      return;
    }

    tableBody.innerHTML = returnsList.map(r => {
      const returnDate = r.returned_at ? new Date(r.returned_at).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true
      }) : 'N/A';

      const rawBill = r.bill_number ? String(r.bill_number) : (r.sale_id ? `BILL-${r.sale_id}` : 'N/A');
      const billNo = rawBill.toLowerCase().startsWith('bill') ? rawBill : `Bill #${rawBill}`;
      const medName = r.product_name || 'Medicine Item';

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 12.5px; font-weight: 700; color: var(--color-text-primary);">
            #RET-${r.return_id || r.id || 'N/A'}
          </td>
          <td>
            <div style="font-family: var(--font-mono); font-weight: 700; color: var(--color-brand-deep,#0D9488); font-size: 13px;">
              ${escapeHtml(billNo)}
            </div>
            <div style="font-size: 11.5px; color: var(--color-text-muted);">${escapeHtml(r.customer_name || 'Walk-in Customer')}</div>
          </td>
          <td>
            <div style="font-weight: 700; color: var(--color-text-primary); font-size: 13.5px;">${escapeHtml(medName)}</div>
            ${r.batch_number ? `<span style="font-size: 11px; background: rgba(13,148,136,0.1); color: #0D9488; padding: 2px 6px; border-radius: 4px; font-weight: 600;">Batch: ${escapeHtml(r.batch_number)}</span>` : ''}
          </td>
          <td style="font-family: var(--font-mono); font-weight: 800; font-size: 14px; text-align: center; color: #DC2626;">
            ${r.returned_quantity || r.quantity || 1}
          </td>
          <td style="font-family: var(--font-mono); font-weight: 800; font-size: 14px; color: #DC2626;">
            ₹${(r.refund_amount || r.return_amount || 0).toFixed(2)}
          </td>
          <td style="font-size: 12.5px; color: var(--color-text-secondary);">
            ${escapeHtml(r.reason || 'Customer Return')}
          </td>
          <td style="font-size: 12px; color: var(--color-text-muted);">
            ${returnDate}<br>
            <span style="font-size: 11px; color: var(--color-text-secondary);">By ${escapeHtml(r.processed_by || 'Pharmacist')}</span>
          </td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading today returns:', err);
    tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #DC2626; padding: 24px;">Failed to load returns: ${escapeHtml(err.message)}</td></tr>`;
  }
}

window.loadTodayReturns = loadTodayReturns;

function openProcessReturnModal() {
  let modal = document.getElementById('modal-process-return');
  if (!modal) {
    createReturnModalDOM();
    modal = document.getElementById('modal-process-return');
  }
  
  document.getElementById('return-search-input-modal').value = '';
  document.getElementById('return-search-results-container').innerHTML = `
    <div style="text-align: center; padding: 32px 16px; color: var(--color-text-muted);">
      <div style="font-size: 28px; margin-bottom: 8px;">🔍</div>
      <div style="font-weight: 600; font-size: 13.5px;">Search Medicine or Original Bill Number</div>
      <div style="font-size: 12px; margin-top: 4px;">Type a medicine name, batch number, customer phone, or bill number above to locate the sale.</div>
    </div>
  `;
  document.getElementById('return-step2-container').style.display = 'none';

  modal.style.display = 'flex';
  setTimeout(() => document.getElementById('return-search-input-modal').focus(), 150);
}

function closeProcessReturnModal() {
  const modal = document.getElementById('modal-process-return');
  if (modal) modal.style.display = 'none';
  selectedBillReturnData = null;
}

let searchReturnTimeout = null;
function onReturnSearchInput(query) {
  clearTimeout(searchReturnTimeout);
  if (!query || query.trim().length < 2) {
    document.getElementById('return-search-results-container').innerHTML = `
      <div style="text-align: center; padding: 32px 16px; color: var(--color-text-muted);">
        <div style="font-size: 28px; margin-bottom: 8px;">🔍</div>
        <div style="font-weight: 600; font-size: 13.5px;">Type at least 2 characters to search</div>
      </div>
    `;
    return;
  }

  document.getElementById('return-search-results-container').innerHTML = `
    <div style="text-align: center; padding: 24px; color: var(--color-text-muted);">
      <div>Searching original sales records...</div>
    </div>
  `;

  searchReturnTimeout = setTimeout(() => {
    fetchSalesForReturn(query.trim());
  }, 250);
}

async function fetchSalesForReturn(query) {
  const container = document.getElementById('return-search-results-container');
  try {
    const res = await fetch(`/api/sales/search-by-medicine?query=${encodeURIComponent(query)}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('expiryguard_token') || ''}`,
        'Accept': 'application/json'
      }
    });

    if (!res.ok) throw new Error('Search failed');

    const salesList = await res.json();

    if (!salesList || salesList.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 32px 16px; color: var(--color-text-muted);">
          <div style="font-size: 24px; margin-bottom: 6px;">❌</div>
          <div style="font-weight: 600; font-size: 13.5px;">No matching sales found for "${escapeHtml(query)}"</div>
          <div style="font-size: 12px; color: var(--color-text-muted); margin-top: 4px;">Verify medicine spelling or bill number and try again.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="font-size: 12px; font-weight: 700; color: var(--color-text-muted); text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">
        Matching Original Bills (${salesList.length})
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px; max-height: 280px; overflow-y: auto;">
        ${salesList.map(s => {
          const item = s.matching_item;
          const isFullyReturned = item.available_return_quantity <= 0;
          const saleDate = s.sale_date ? new Date(s.sale_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : 'N/A';

          return `
            <div style="border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 12px; background: var(--color-surface-card); display: flex; align-items: center; justify-content: space-between; gap: 12px; ${isFullyReturned ? 'opacity: 0.6;' : 'cursor: pointer;'}"
                 ${!isFullyReturned ? `onclick="selectBillItemForReturn(${s.sale_id}, '${escapeJsString(s.bill_number)}', ${item.sale_item_id}, '${escapeJsString(item.product_name)}', '${escapeJsString(item.batch_number || '')}', ${item.unit_price}, ${item.originally_sold_quantity}, ${item.already_returned_quantity}, ${item.available_return_quantity})"` : ''}>
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-family: var(--font-mono); font-weight: 800; color: var(--color-brand-deep,#0D9488); font-size: 13px;">${s.bill_number}</span>
                  <span style="font-size: 11.5px; color: var(--color-text-muted);">&bull; ${saleDate}</span>
                </div>
                <div style="font-weight: 700; font-size: 13.5px; color: var(--color-text-primary); margin-top: 2px;">
                  ${escapeHtml(item.product_name)}
                </div>
                <div style="font-size: 12px; color: var(--color-text-secondary); margin-top: 1px;">
                  Customer: <strong>${escapeHtml(s.customer_name || 'Walk-in Customer')}</strong>
                  ${item.batch_number ? ` &bull; Batch: <strong>${escapeHtml(item.batch_number)}</strong>` : ''}
                  &bull; Unit Price: <strong>₹${item.unit_price.toFixed(2)}</strong>
                </div>
              </div>
              
              <div style="text-align: right; min-width: 130px;">
                ${isFullyReturned ? `
                  <span style="display: inline-block; padding: 4px 8px; border-radius: 4px; background: #FEE2E2; color: #991B1B; font-weight: 700; font-size: 11.5px;">Fully Returned</span>
                ` : `
                  <div style="font-size: 12px; font-weight: 700; color: #059669;">
                    Available: <span style="font-size: 15px; font-family: var(--font-mono); font-weight: 800;">${item.available_return_quantity}</span> / ${item.originally_sold_quantity}
                  </div>
                  <button class="btn btn-sm btn-primary" style="margin-top: 4px; padding: 4px 10px; font-size: 12px;">Select Bill →</button>
                `}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

  } catch (err) {
    container.innerHTML = `<div style="color: #DC2626; padding: 16px; text-align: center;">Error: ${escapeHtml(err.message)}</div>`;
  }
}

function selectBillItemForReturn(saleId, billNumber, saleItemId, productName, batchNumber, unitPrice, origQty, alreadyReturned, availQty) {
  selectedBillReturnData = {
    saleId, billNumber, saleItemId, productName, batchNumber, unitPrice, origQty, alreadyReturned, availQty
  };

  const step2Container = document.getElementById('return-step2-container');
  step2Container.innerHTML = `
    <div style="background: var(--color-surface-card); border: 2px solid #0D9488; border-radius: var(--radius-md); padding: 14px; margin-top: 12px;">
      <div style="font-size: 12px; font-weight: 700; color: #0D9488; text-transform: uppercase; letter-spacing: 0.5px;">Selected Bill Transaction</div>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
        <div style="font-family: var(--font-mono); font-weight: 800; font-size: 15px; color: var(--color-text-primary);">Bill #${billNumber}</div>
        <div style="font-size: 13px; font-weight: 700; color: #059669;">Available Return: ${availQty} units</div>
      </div>

      <div style="font-size: 13.5px; font-weight: 700; color: var(--color-text-primary); margin-top: 6px;">${escapeHtml(productName)}</div>
      <div style="font-size: 12px; color: var(--color-text-secondary);">
        Selling Price: ₹${unitPrice.toFixed(2)} / unit &bull; Originally Sold: ${origQty} &bull; Already Returned: ${alreadyReturned}
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px;">
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--color-text-primary); display: block; margin-bottom: 4px;">
            Return Quantity (Max ${availQty}):
          </label>
          <input type="number" id="return-input-qty" class="form-input" min="1" max="${availQty}" value="1" style="font-weight: 800; font-family: var(--font-mono); font-size: 15px;" oninput="onReturnQtyChange(this.value, ${unitPrice}, ${availQty})">
        </div>

        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--color-text-primary); display: block; margin-bottom: 4px;">
            Total Refund Amount:
          </label>
          <div id="return-calc-refund-display" style="font-size: 18px; font-weight: 800; font-family: var(--font-mono); color: #DC2626; padding: 6px 0;">
            ₹${unitPrice.toFixed(2)}
          </div>
        </div>
      </div>

      <div style="margin-top: 10px;">
        <label style="font-size: 12px; font-weight: 700; color: var(--color-text-primary); display: block; margin-bottom: 4px;">Return Reason (Optional):</label>
        <input type="text" id="return-input-reason" class="form-input" placeholder="e.g. Patient brought back unused strips, wrong size" style="font-size: 12.5px;">
      </div>

      <div style="margin-top: 16px; display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn btn-secondary" onclick="document.getElementById('return-step2-container').style.display='none'; selectedBillReturnData=null;">Cancel Selection</button>
        <button class="btn btn-primary" id="btn-submit-return" onclick="submitProcessedReturn()" style="background-color: #DC2626; border-color: #DC2626; font-weight: 700;">
          <span>Confirm & Process Return →</span>
        </button>
      </div>
    </div>
  `;

  step2Container.style.display = 'block';
  step2Container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function onReturnQtyChange(val, unitPrice, maxQty) {
  const qty = parseInt(val, 10) || 0;
  const display = document.getElementById('return-calc-refund-display');
  const btn = document.getElementById('btn-submit-return');

  if (qty <= 0) {
    if (display) display.textContent = '₹0.00 (Invalid)';
    if (btn) btn.disabled = true;
    return;
  }

  if (qty > maxQty) {
    if (display) display.textContent = `Exceeds max available (${maxQty})`;
    if (btn) btn.disabled = true;
    return;
  }

  if (btn) btn.disabled = false;
  const refund = qty * unitPrice;
  if (display) display.textContent = `₹${refund.toFixed(2)}`;
}

async function submitProcessedReturn() {
  if (!selectedBillReturnData) {
    alert('Please select a bill item first.');
    return;
  }

  const qtyInput = document.getElementById('return-input-qty');
  const reasonInput = document.getElementById('return-input-reason');
  const submitBtn = document.getElementById('btn-submit-return');

  const returnQty = parseInt(qtyInput ? qtyInput.value : '0', 10);
  const reason = reasonInput ? reasonInput.value.trim() : '';

  if (returnQty <= 0) {
    alert('Please enter a valid return quantity (minimum 1).');
    return;
  }

  if (returnQty > selectedBillReturnData.availQty) {
    alert(`Cannot return ${returnQty} units. Maximum available return quantity for this bill is ${selectedBillReturnData.availQty}.`);
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing Return...';
  }

  try {
    const res = await fetch('/api/sales/returns', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('expiryguard_token') || ''}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        sale_id: selectedBillReturnData.saleId,
        reason: reason || 'Customer Return',
        items: [
          {
            sale_item_id: selectedBillReturnData.saleItemId,
            return_quantity: returnQty
          }
        ]
      })
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Failed to process return');
    }

    closeProcessReturnModal();
    
    if (window.showToast) {
      window.showToast(`✅ ${data.message}`);
    } else {
      alert(`✅ ${data.message}\nTotal Refund: ₹${data.total_refund_amount.toFixed(2)}\nStock updated in inventory.`);
    }

    loadTodayReturns();

  } catch (err) {
    alert(`Error processing return: ${err.message}`);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Confirm & Process Return →';
    }
  }
}

function createReturnModalDOM() {
  const modalHTML = `
    <div id="modal-process-return" class="modal-backdrop" style="display: none; position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(4px); z-index: 9999; justify-content: center; align-items: center; padding: 16px;">
      <div class="modal-content" style="background: var(--color-surface-card); border-radius: var(--radius-lg); width: 100%; max-width: 620px; border: 1px solid var(--color-border); box-shadow: var(--shadow-xl); overflow: hidden; display: flex; flex-direction: column; max-height: 90vh;">
        
        <!-- Modal Header -->
        <div style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); color: #FFF; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-weight: 800; font-size: 16px;">🔄 Process Item Return & Refund</div>
            <div style="font-size: 12px; color: #94A3B8; margin-top: 2px;">Search medicine -> Select original bill -> Restore stock</div>
          </div>
          <button onclick="closeProcessReturnModal()" style="background: none; border: none; color: #94A3B8; font-size: 20px; cursor: pointer; line-height: 1;">&times;</button>
        </div>

        <!-- Modal Body -->
        <div style="padding: 20px; overflow-y: auto; flex: 1;">
          
          <!-- Step 1: Search Box -->
          <div style="margin-bottom: 16px;">
            <label style="font-size: 12.5px; font-weight: 700; color: var(--color-text-primary); display: block; margin-bottom: 6px;">
              Step 1: Search Medicine / Original Bill Number
            </label>
            <input type="text" id="return-search-input-modal" class="form-input" placeholder="🔍 Type medicine name, batch number, or bill no..." style="font-size: 14px; padding: 10px 14px;" oninput="onReturnSearchInput(this.value)">
          </div>

          <!-- Step 2: Search Results -->
          <div id="return-search-results-container">
            <!-- Results dynamically injected -->
          </div>

          <!-- Step 3: Return Quantity & Confirmation -->
          <div id="return-step2-container" style="display: none;">
            <!-- Selection container dynamically injected -->
          </div>

        </div>

      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', modalHTML);
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

function escapeJsString(str) {
  if (!str) return '';
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}
