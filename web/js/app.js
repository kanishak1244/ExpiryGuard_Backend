/* ==========================================================================
   GLOBAL SECURITY SANITIZER & THEME MANAGER
   ========================================================================== */

window.escapeHtml = function(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

window.ExpiryTheme = {
  getTheme() {
    return localStorage.getItem('expiryguard_theme') || 'light';
  },
  setTheme(theme, syncBackend = true) {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('expiryguard_theme', theme);

    const btn = document.getElementById('theme-toggle-btn');
    if (btn) btn.textContent = theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode';

    const select = document.getElementById('pref-theme-select');
    if (select) select.value = theme;

    if (syncBackend && window.api && typeof api.getToken === 'function' && api.getToken()) {
      api.updateSettings({ preferred_theme: theme }).catch(err => {
        console.warn('Failed to sync theme to backend:', err);
      });
    }
  },
  toggleTheme() {
    const current = this.getTheme();
    this.setTheme(current === 'dark' ? 'light' : 'dark', true);
  },
  init() {
    const current = this.getTheme();
    this.setTheme(current, false);
  }
};

/* ==========================================================================
   CANONICAL NAVIGATION & SIDEBAR COMPONENT DELEGATION
   ========================================================================== */

function renderCanonicalSidebar() {
  if (window.ExpiryNav && typeof window.ExpiryNav.render === 'function') {
    window.ExpiryNav.render();
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Apply saved theme immediately across all pages
  window.ExpiryTheme.init();

  // Render Canonical 12-Item Sidebar across all pages
  renderCanonicalSidebar();

  // Ensure authenticated session on load
  if (window.api && typeof api.ensureAuthenticated === 'function') {
    await api.ensureAuthenticated();
  }

  // Identify and initialize active page components
  if (document.getElementById('dashboard-page')) {
    initDashboard();
  } else if (document.getElementById('inventory-page')) {
    initInventory();
  } else if (document.getElementById('sales-page')) {
    initSales();
  } else if (document.getElementById('ai-billing-page')) {
    initAiBilling();
  } else if (document.getElementById('returns-page')) {
    initReturns();
  } else if (document.getElementById('reports-page')) {
    initReports();
  } else if (document.getElementById('billing-page')) {
    if (typeof initBillingEngine === 'function') {
      initBillingEngine();
    }
  } else if (document.getElementById('restock-app-container') || document.getElementById('restock-page')) {
    if (typeof window.initRestockPage === 'function') {
      window.initRestockPage();
    } else if (typeof window.loadRestockSuggestions === 'function') {
      window.loadRestockSuggestions();
    }
  }
});

/* ==========================================================================
   1. DASHBOARD PAGE LOGIC & 5-SECOND POLLING
   ========================================================================== */

function initDashboard() {
  const renderDashboardData = async () => {
    try {
      const summary = await api.getDashboardSummary();

      // Render Shop Info
      if (document.getElementById('shop-name-header')) {
        document.getElementById('shop-name-header').textContent = summary.shop_name || 'ExpiryGuard Pharmacy';
      }

      // Render KPI Cards
      document.getElementById('kpi-total-products').textContent = summary.total_products || 0;
      document.getElementById('kpi-sales-count').textContent = summary.today_sales_count || 0;
      document.getElementById('kpi-revenue').textContent = `₹${(summary.today_revenue || 0).toLocaleString('en-IN')}`;
      document.getElementById('kpi-expiring').textContent = summary.expiring_soon_count || 0;
      document.getElementById('kpi-expired').textContent = summary.expired_count || 0;
      document.getElementById('kpi-returns').textContent = `₹${(summary.today_returns_amount || 0).toLocaleString('en-IN')}`;

      // Render Live Recent Transactions Feed
      const sales = await api.getSales(0, 10);
      renderLiveSalesFeed(sales);

      // Render Pending Payments Ledger
      if (summary.pending_payments_list) {
        renderPendingPaymentsLedger(summary.pending_payments_list, summary.pending_payments_total);
      }

    } catch (err) {
      console.error('Dashboard load error:', err);
    }
  };

  // Start 5-second polling engine
  api.startPolling(renderDashboardData, 5000);
}

function renderLiveSalesFeed(sales) {
  const container = document.getElementById('live-sales-table-body');
  if (!container) return;

  if (!sales || sales.length === 0) {
    container.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--color-text-muted); padding: 32px 16px;">
      <div style="font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 4px;">No counter bills recorded today</div>
      <div style="font-size: 12px; color: var(--color-text-muted);">Completed sales and GST bills generated at the counter will appear here in real time.</div>
    </td></tr>`;
    return;
  }

  container.innerHTML = sales.map(sale => {
    const dateStr = new Date(sale.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isReturned = sale.return_status && sale.return_status.includes('returned');
    const isPending = (sale.payment_status === 'PENDING' || sale.payment_method === 'PENDING');
    let badgeClass = isReturned ? 'badge-warning' : 'badge-safe';
    let badgeText = isReturned ? 'Returned' : 'Paid';
    if (isPending) {
      badgeClass = 'badge-warning';
      badgeText = 'Pending';
    }

    return `
      <tr onclick="openBillDetailModal(${sale.id})" style="cursor: pointer;">
        <td><strong class="num-tabular">${sale.bill_number}</strong></td>
        <td>${sale.customer_name || 'Walk-in Cash Customer'}</td>
        <td class="num-tabular" style="color: var(--color-text-muted);">${dateStr}</td>
        <td><strong class="num-currency">${sale.total_amount.toFixed(2)}</strong></td>
        <td><span class="badge ${isPending ? 'badge-warning' : 'badge-info'}">${sale.payment_method || 'CASH'}</span></td>
        <td><span class="badge ${badgeClass}">${badgeText}</span></td>
      </tr>
    `;
  }).join('');
}

function renderPendingPaymentsLedger(pendingList, totalDue = 0) {
  const container = document.getElementById('pending-payments-table-body');
  const countBadge = document.getElementById('pending-payments-count-badge');
  const totalHeader = document.getElementById('total-pending-amount-header');
  if (!container) return;

  if (countBadge) {
    countBadge.textContent = `${pendingList.length} Pending`;
  }
  if (totalHeader) {
    totalHeader.textContent = `Total Outstanding: ₹${(totalDue || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  }

  if (!pendingList || pendingList.length === 0) {
    container.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 24px 16px;">
      <div style="font-size: 14px; font-weight: 600; color: var(--status-safe); margin-bottom: 4px;">🎉 All customer bills are cleared!</div>
      <div style="font-size: 12px; color: var(--color-text-muted);">When you create a bill with "Pending" payment mode, it will appear here for payment settlement.</div>
    </td></tr>`;
    return;
  }

  container.innerHTML = pendingList.map(item => {
    return `
      <tr>
        <td><strong>${escapeHtml(item.customer_name)}</strong></td>
        <td>${escapeHtml(item.customer_phone || 'N/A')}</td>
        <td><strong class="num-tabular">${escapeHtml(item.bill_number)}</strong></td>
        <td class="num-tabular" style="color: var(--color-text-muted);">${escapeHtml(item.bill_date)}</td>
        <td><strong class="num-currency" style="color: var(--status-warning);">₹${Number(item.total_amount).toFixed(2)}</strong></td>
        <td><span class="badge badge-warning">Pending Payment</span></td>
        <td style="text-align: center;">
          <button type="button" class="btn btn-primary" style="padding: 5px 12px; font-size: 12px; font-weight: 600;" onclick="settlePendingPayment(${item.id})">
            ✓ Mark Settled
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function settlePendingPayment(saleId) {
  const proceed = async () => {
    try {
      const res = await api.request(`/sales/${saleId}/settle`, { method: 'POST' });
      if (window.showToastNotification) {
        showToastNotification(`✅ Bill marked as settled!`);
      } else {
        alert('Bill marked as settled!');
      }
      // Refresh dashboard immediately
      const summary = await api.getDashboardSummary();
      if (summary.pending_payments_list) {
        renderPendingPaymentsLedger(summary.pending_payments_list, summary.pending_payments_total);
      }
      const sales = await api.getSales(0, 10);
      renderLiveSalesFeed(sales);
    } catch (err) {
      alert(`Failed to settle payment: ${err.message}`);
    }
  };

  if (window.ConfirmModal) {
    ConfirmModal({
      isOpen: true,
      title: 'Mark Bill as Settled',
      message: 'Mark this pending bill as settled and clear the outstanding amount?',
      confirmText: '✓ Mark Settled',
      cancelText: 'Cancel',
      icon: '💰',
      onConfirm: proceed
    });
  } else if (confirm('Mark this pending bill as settled and clear the outstanding amount?')) {
    proceed();
  }
}

window.settlePendingPayment = settlePendingPayment;

/* ==========================================================================
   2. INVENTORY PAGE LOGIC & REAL-TIME SEARCH/FILTER & SOFT-DELETE
   ========================================================================== */

let allProducts = [];
let currentFilter = 'all';
let selectedStockIds = new Set();

function initInventory() {
  const loadInventory = async () => {
    try {
      allProducts = await api.getProducts();
      applyInventoryFilters();
    } catch (err) {
      console.error('Inventory load error:', err);
    }
  };

  // Setup Filter Buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.dataset.filter;
      applyInventoryFilters();
    });
  });

  // Setup Search Input
  const searchInput = document.getElementById('inventory-search');
  if (searchInput) {
    searchInput.addEventListener('input', applyInventoryFilters);
  }

  // Initial load & poll inventory every 10s
  loadInventory();
  api.startPolling(loadInventory, 10000);
}

function applyInventoryFilters() {
  const searchVal = (document.getElementById('inventory-search')?.value || '').toLowerCase().trim();

  let filtered = allProducts.filter(p => {
    const nameMatch = (p.product_name || '').toLowerCase().includes(searchVal) ||
                      (p.batch_number || '').toLowerCase().includes(searchVal);
    if (!nameMatch) return false;

    if (currentFilter === 'instock') return p.quantity > 0;
    if (currentFilter === 'lowstock') return p.quantity > 0 && p.quantity <= 10;
    if (currentFilter === 'expiring') return p.days_remaining > 0 && p.days_remaining <= 60;
    if (currentFilter === 'expired') return p.days_remaining <= 0;
    return true;
  });

  const tbody = document.getElementById('inventory-table-body');
  if (!tbody) return;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--color-text-muted); padding: 36px 16px;">
      <div style="font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 4px;">No inventory batches match this view</div>
      <div style="font-size: 12px; color: var(--color-text-muted); margin-bottom: 12px;">Try adjusting your filter or search keywords, or add new stock.</div>
      <button class="btn btn-primary" style="padding: 6px 14px; font-size: 12.5px;" onclick="openAddInventoryModal()">+ Add Inventory</button>
    </td></tr>`;
    updateSelectionUI();
    return;
  }

  tbody.innerHTML = filtered.map(p => {
    let statusBadge = `<span class="badge badge-safe">In Stock</span>`;
    if (p.days_remaining <= 0) {
      statusBadge = `<span class="badge badge-danger">Expired (${Math.abs(p.days_remaining)}d ago)</span>`;
    } else if (p.days_remaining <= 60) {
      statusBadge = `<span class="badge badge-warning">Expiring (${p.days_remaining}d left)</span>`;
    }

    const isChecked = selectedStockIds.has(p.id);

    return `
      <tr>
        <td style="text-align: center;">
          <input type="checkbox" class="stock-row-checkbox" value="${p.id}" ${isChecked ? 'checked' : ''} onchange="onStockSelectionChange(${p.id}, this.checked)">
        </td>
        <td>
          <div style="font-weight: 600; color: var(--color-text-primary);">${window.escapeHtml(p.product_name)}</div>
          <small style="color: var(--color-text-muted);">${window.escapeHtml(p.category || 'Pharmaceutical')}</small>
        </td>
        <td><span class="num-batch">${window.escapeHtml(p.batch_number || 'N/A')}</span></td>
        <td>
          <strong class="num-tabular" style="font-size: 14px;">${p.quantity}</strong> 
          <span style="font-size: 11.5px; color: var(--color-text-muted);">${window.escapeHtml(p.unit || 'strips')}</span>
          ${p.tablets_per_strip ? `<br><small class="num-tabular" style="color: var(--color-text-muted);">(${p.loose_tablet_stock || 0} loose tabs)</small>` : ''}
        </td>
        <td><span class="num-currency">${(p.unit_price || p.price || 0).toFixed(2)}</span></td>
        <td><span class="num-date">${p.expiry_date || '-'}</span></td>
        <td>${statusBadge}</td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="viewProductDetails(${p.id})">Stock Card</button>
        </td>
      </tr>
    `;
  }).join('');

  updateSelectionUI();
}

function onStockSelectionChange(productId, isChecked) {
  if (isChecked) {
    selectedStockIds.add(productId);
  } else {
    selectedStockIds.delete(productId);
  }
  updateSelectionUI();
}

function toggleSelectAllStock(masterCheckbox) {
  const checkboxes = document.querySelectorAll('.stock-row-checkbox');
  checkboxes.forEach(cb => {
    const id = parseInt(cb.value, 10);
    cb.checked = masterCheckbox.checked;
    if (masterCheckbox.checked) {
      selectedStockIds.add(id);
    } else {
      selectedStockIds.delete(id);
    }
  });
  updateSelectionUI();
}

function updateSelectionUI() {
  const count = selectedStockIds.size;
  const btnDeleteSelected = document.getElementById('btn-delete-selected');
  const countSpan = document.getElementById('selected-count');
  const selectAll = document.getElementById('select-all-stock');

  if (countSpan) countSpan.textContent = count;

  if (btnDeleteSelected) {
    btnDeleteSelected.style.display = count > 0 ? 'inline-flex' : 'none';
  }

  const allVisibleCheckboxes = document.querySelectorAll('.stock-row-checkbox');
  if (selectAll && allVisibleCheckboxes.length > 0) {
    const allChecked = Array.from(allVisibleCheckboxes).every(cb => cb.checked);
    selectAll.checked = allChecked;
  } else if (selectAll) {
    selectAll.checked = false;
  }
}

function openDeleteSelectedModal() {
  const count = selectedStockIds.size;
  if (count === 0) return;

  if (window.ConfirmModal) {
    ConfirmModal({
      isOpen: true,
      title: 'Move to Recently Deleted',
      message: `Are you sure you want to delete ${count} selected medicine batch(es)? Items are soft-deleted and can be recovered within 60 days from Recently Deleted.`,
      confirmText: 'Move to Deleted',
      cancelText: 'Cancel',
      icon: '🗑️',
      onConfirm: executeDeleteSelected
    });
  } else {
    const modalCount = document.getElementById('modal-delete-count');
    const modalEl = document.getElementById('delete-selected-modal');
    if (modalCount) modalCount.textContent = count;
    if (modalEl) modalEl.classList.add('active');
  }
}

function closeDeleteSelectedModal() {
  if (window.ConfirmModal) {
    ConfirmModal.close();
  }
  const modalEl = document.getElementById('delete-selected-modal');
  if (modalEl) modalEl.classList.remove('active');
}

async function executeDeleteSelected() {
  const ids = Array.from(selectedStockIds);
  if (ids.length === 0) return;

  const btn = document.getElementById('btn-confirm-delete-selected');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Deleting...';
  }

  try {
    let res;
    if (window.api && typeof window.api.deleteInventoryStock === 'function') {
      res = await window.api.deleteInventoryStock(ids);
    } else {
      const token = localStorage.getItem('expiryguard_token');
      const response = await fetch('/inventory/delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ stock_ids: ids })
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${response.status}`);
      }
      res = await response.json();
    }

    closeDeleteSelectedModal();
    selectedStockIds.clear();
    showToastNotification(res.message || `${ids.length} items moved to Recently Deleted, recoverable for 60 days.`, true);
    
    // Refresh inventory immediately
    if (window.api && typeof window.api.getProducts === 'function') {
      allProducts = await window.api.getProducts();
    } else {
      const token = localStorage.getItem('expiryguard_token');
      const r = await fetch('/products', {
        headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
      });
      allProducts = await r.json();
    }
    applyInventoryFilters();
  } catch (err) {
    console.error('Delete selected error:', err);
    showToastNotification(`Failed to delete items: ${err.message}`, false);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Move to Deleted';
    }
  }
}

function openDeleteAllModal() {
  const totalCount = allProducts.length;
  if (totalCount === 0) return;

  if (window.ConfirmModal) {
    ConfirmModal({
      isOpen: true,
      title: 'Delete All Stock',
      message: `This will remove all ${totalCount} items from your active live inventory. All items will be moved to Recently Deleted (60-day recovery guarantee).`,
      confirmText: 'Yes, Delete All Stock',
      cancelText: 'Cancel',
      icon: '⚠️',
      onConfirm: executeDeleteAll
    });
  } else {
    const modalCount = document.getElementById('modal-total-stock-count');
    const modalEl = document.getElementById('delete-all-modal');
    if (modalCount) modalCount.textContent = totalCount;
    if (modalEl) modalEl.classList.add('active');
  }
}

function closeDeleteAllModal() {
  if (window.ConfirmModal) {
    ConfirmModal.close();
  }
  const modalEl = document.getElementById('delete-all-modal');
  if (modalEl) modalEl.classList.remove('active');
}

async function executeDeleteAll() {
  const btn = document.getElementById('btn-confirm-delete-all');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Deleting All Stock...';
  }

  try {
    let res;
    if (window.api && typeof window.api.deleteAllInventoryStock === 'function') {
      res = await window.api.deleteAllInventoryStock();
    } else {
      const token = localStorage.getItem('expiryguard_token');
      const response = await fetch('/inventory/delete-all', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ confirm: true })
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${response.status}`);
      }
      res = await response.json();
    }

    closeDeleteAllModal();
    selectedStockIds.clear();
    showToastNotification(res.message || 'All items moved to Recently Deleted, recoverable for 60 days.', true);
    
    if (window.api && typeof window.api.getProducts === 'function') {
      allProducts = await window.api.getProducts();
    } else {
      const token = localStorage.getItem('expiryguard_token');
      const r = await fetch('/products', {
        headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
      });
      allProducts = await r.json();
    }
    applyInventoryFilters();
  } catch (err) {
    console.error('Delete all stock error:', err);
    showToastNotification(`Failed to delete all stock: ${err.message}`, false);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Yes, Delete All Stock';
    }
  }
}

function showToastNotification(message, isSuccess = true) {
  const toast = document.getElementById('toast-notification');
  const msgEl = document.getElementById('toast-message');
  const iconEl = document.getElementById('toast-icon');

  if (!toast) {
    alert(message);
    return;
  }

  if (msgEl) msgEl.textContent = message;
  if (iconEl) iconEl.textContent = isSuccess ? '✅' : '❌';
  toast.style.backgroundColor = isSuccess ? '#065F46' : '#991B1B';
  toast.style.display = 'flex';

  setTimeout(() => {
    toast.style.display = 'none';
  }, 4500);
}

/* ==========================================================================
   3. SALES PAGE LOGIC & BILL DETAIL MODAL
   ========================================================================== */

function initSales() {
  const loadSales = async () => {
    try {
      const sales = await api.getSales(0, 50);
      renderSalesList(sales);
    } catch (err) {
      console.error('Sales load error:', err);
    }
  };

  api.startPolling(loadSales, 5000);
}

function renderSalesList(sales) {
  const tbody = document.getElementById('sales-table-body');
  if (!tbody) return;

  if (!sales || sales.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 36px 16px;">
      <div style="font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 4px;">No counter transactions recorded</div>
      <div style="font-size: 12px; color: var(--color-text-muted);">Invoices and receipts generated at the counter POS will be archived here.</div>
    </td></tr>`;
    return;
  }

  tbody.innerHTML = sales.map(s => {
    const dateStr = new Date(s.created_at).toLocaleString();
    return `
      <tr onclick="openBillDetailModal(${s.id})" style="cursor: pointer;">
        <td><strong class="num-tabular">${s.bill_number}</strong></td>
        <td>${s.customer_name || 'Walk-in Customer'}</td>
        <td>${s.doctor_name ? `Dr. ${s.doctor_name}` : '-'}</td>
        <td class="num-date" style="color: var(--color-text-muted);">${dateStr}</td>
        <td><strong class="num-currency" style="font-size: 14px;">${s.total_amount.toFixed(2)}</strong></td>
        <td><span class="badge badge-info">${s.payment_method || 'CASH'}</span></td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="event.stopPropagation(); window.open('${api.getInvoicePdfUrl(s.id)}', '_blank')">
            <svg style="width: 12px; height: 12px; stroke: currentColor; fill: none;" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            PDF
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function openBillDetailModal(saleId) {
  try {
    const sales = await api.getSales(0, 100);
    const sale = sales.find(s => s.id === saleId);
    if (!sale) return;

    let modal = document.getElementById('bill-detail-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'bill-detail-modal';
      modal.className = 'modal-overlay';
      document.body.appendChild(modal);
    }

    const itemsHtml = (sale.items || []).map(i => `
      <tr>
        <td style="font-weight: 600;">${i.product_name}</td>
        <td><span class="badge badge-info" style="font-size: 11px;">${i.unit_type || 'strip'}</span></td>
        <td class="num-tabular" style="font-weight: 600;">${i.quantity}</td>
        <td class="num-currency">${i.unit_price.toFixed(2)}</td>
        <td class="num-currency">${(i.taxable_value || i.total_price).toFixed(2)}</td>
        <td><strong class="num-currency">${(i.total_with_tax || i.total_price).toFixed(2)}</strong></td>
      </tr>
    `).join('');

    modal.innerHTML = `
      <div class="modal-card" style="max-width: 680px;">
        <div class="modal-header">
          <div>
            <h3 class="panel-title" style="margin-bottom: 2px;">GST Tax Invoice #${sale.bill_number}</h3>
            <span style="font-size: 12px; color: var(--color-text-muted);">Verified Counter Sale Receipt</span>
          </div>
          <button class="close-btn" onclick="document.getElementById('bill-detail-modal').classList.remove('active')">&times;</button>
        </div>
        
        <div style="background-color: #F8FAFC; border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 12px 16px; margin-bottom: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12.5px;">
          <div><strong style="color: var(--color-text-muted);">Patient:</strong> ${sale.customer_name || 'Walk-in Customer'} ${sale.customer_phone ? `(${sale.customer_phone})` : ''}</div>
          <div><strong style="color: var(--color-text-muted);">Doctor:</strong> ${sale.doctor_name ? `Dr. ${sale.doctor_name}` : 'Over The Counter'}</div>
          <div><strong style="color: var(--color-text-muted);">Payment:</strong> <span class="badge badge-info" style="font-size: 11px;">${sale.payment_method || 'CASH'}</span></div>
          <div><strong style="color: var(--color-text-muted);">Timestamp:</strong> <span class="num-date">${new Date(sale.created_at).toLocaleString()}</span></div>
        </div>

        <div class="table-responsive" style="margin-bottom: 16px;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Item / Formulation</th>
                <th>Unit</th>
                <th>Qty</th>
                <th>Rate</th>
                <th>Taxable</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>${itemsHtml}</tbody>
          </table>
        </div>

        <div style="background-color: #F8FAFC; border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 14px 18px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 4px; font-size: 13px;">
          <div style="display: flex; justify-content: space-between; color: var(--color-text-muted);">
            <span>Subtotal (Taxable):</span>
            <span class="num-currency">${sale.subtotal.toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; color: var(--color-text-muted);">
            <span>Discount Applied:</span>
            <span class="num-currency">${sale.discount_amount.toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; color: var(--color-text-muted);">
            <span>GST Tax (CGST + SGST):</span>
            <span class="num-currency">${sale.tax_amount.toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 17px; font-weight: 700; color: var(--color-brand-deep); border-top: 1px solid var(--color-border); padding-top: 8px; margin-top: 4px;">
            <span>Grand Total:</span>
            <span class="num-currency" style="font-size: 20px;">${sale.total_amount.toFixed(2)}</span>
          </div>
        </div>

        <div style="display: flex; gap: 10px; justify-content: flex-end;">
          <button class="btn btn-secondary" onclick="document.getElementById('bill-detail-modal').classList.remove('active')">Close</button>
          <button class="btn btn-primary" onclick="window.open('${api.getInvoicePdfUrl(sale.id)}', '_blank')">
            <svg style="width: 14px; height: 14px; stroke: currentColor; fill: none;" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            Print / View PDF Invoice
          </button>
        </div>
      </div>
    `;

    modal.classList.add('active');
  } catch (err) {
    console.error('Error opening bill detail:', err);
  }
}

/* ==========================================================================
   4. AI CAMERA BILLING PAGE LOGIC
   ========================================================================== */

function initAiBilling() {
  const dropzone = document.getElementById('ai-dropzone');
  const fileInput = document.getElementById('ai-file-input');
  const previewDiv = document.getElementById('ai-preview-container');
  const resultsDiv = document.getElementById('ai-results-container');

  if (!dropzone || !fileInput) return;

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--color-brand-deep)';
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.style.borderColor = 'var(--color-border)';
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--color-border)';
    if (e.dataTransfer.files.length > 0) {
      handleAiImage(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleAiImage(e.target.files[0]);
    }
  });

  async function handleAiImage(file) {
    previewDiv.style.display = 'block';
    resultsDiv.style.display = 'none';

    document.getElementById('ai-image-preview').src = URL.createObjectURL(file);
    document.getElementById('ai-status-text').textContent = 'Analyzing photo with Gemini Vision AI...';

    try {
      const res = await api.scanLabel(file);
      document.getElementById('ai-status-text').textContent = 'Medicines Identified Successfully!';

      if (res && res.data) {
        renderAiResults(res.data);
      }
    } catch (err) {
      document.getElementById('ai-status-text').textContent = `AI Scanning Failed: ${err.message}`;
    }
  }

  function renderAiResults(data) {
    resultsDiv.style.display = 'block';
    const items = data.detected_medicines || [data];

    resultsDiv.innerHTML = `
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">${items.length} Medicine(s) Detected</h3>
          <span class="badge badge-safe">Vision Verified</span>
        </div>
        <div style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px;">
          ${items.map(item => `
            <div style="border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
              <div>
                <strong style="color: var(--color-text-primary);">${item.medicine_name || item.product_name || 'Medicine'}</strong>
                <div style="font-size: 12px; color: var(--color-text-muted); margin-top: 2px;">
                  Batch: <span class="num-batch">${item.batch_number || 'Auto-FEFO'}</span> | Exp: <span class="num-date">${item.expiry_date || 'Safe'}</span>
                </div>
              </div>
              <div style="text-align: right;">
                <span class="num-currency" style="font-size: 15px; font-weight: 700;">${(item.mrp || item.unit_price || 100).toFixed(2)}</span>
              </div>
            </div>
          `).join('')}
        </div>
        <button class="btn btn-primary" style="width: 100%;" onclick="alert('Sale confirmed via Web AI!')">Confirm & Generate GST Bill</button>
      </div>
    `;
  }
}

/* ==========================================================================
   5. RETURNS PAGE LOGIC
   ========================================================================== */

function initReturns() {
  const loadReturns = async () => {
    try {
      const returns = await api.getTodaysReturns();
      renderReturnsList(Array.isArray(returns) ? returns : []);
    } catch (err) {
      console.error('Returns load error:', err);
      const container = document.getElementById('returns-list-body');
      if (container) {
        container.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--status-danger); padding: 24px;">Failed to load returns log: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  };

  loadReturns();
  api.startPolling(loadReturns, 5000);
}

function renderReturnsList(returns) {
  const container = document.getElementById('returns-list-body');
  if (!container) return;

  const totalRefund = (Array.isArray(returns) ? returns : []).reduce((sum, r) => sum + (Number(r.return_amount) || 0), 0);
  const refundEl = document.getElementById('returns-total-refund');
  if (refundEl) {
    refundEl.textContent = `₹${totalRefund.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  }
  const countEl = document.getElementById('returns-count');
  if (countEl) {
    countEl.textContent = (Array.isArray(returns) ? returns : []).length;
  }

  if (!returns || returns.length === 0) {
    container.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--color-text-muted); padding: 32px 16px;">
      <div style="font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 4px;">No returns recorded today</div>
      <div style="font-size: 12px; color: var(--color-text-muted);">Patient returns and stock adjustments will be listed here.</div>
    </td></tr>`;
    return;
  }

  container.innerHTML = returns.map(r => `
    <tr>
      <td><strong class="num-tabular">#RET-${r.id}</strong></td>
      <td><span class="num-tabular">${escapeHtml(r.bill_number ? `Bill #${r.bill_number}` : `Bill #${r.sale_id}`)}</span></td>
      <td>${escapeHtml(r.reason || 'Patient Return')}</td>
      <td><strong class="num-currency" style="color: var(--status-danger);">₹${Number(r.return_amount || 0).toFixed(2)}</strong></td>
      <td class="num-date" style="color: var(--color-text-muted);">${r.created_at ? new Date(r.created_at).toLocaleTimeString() : '-'}</td>
    </tr>
  `).join('');
}

/* ==========================================================================
   6. REPORTS PAGE LOGIC
   ========================================================================== */

function initReports() {
  const loadReports = async () => {
    try {
      const [reports, dashSummary] = await Promise.all([
        api.getReportsSummary(),
        api.getDashboardSummary().catch(() => ({}))
      ]);

      // Render KPIs
      const todayRevEl = document.getElementById('rep-kpi-today-rev');
      const sevenDayRevEl = document.getElementById('rep-kpi-7d-rev');
      const ordersEl = document.getElementById('rep-kpi-orders');
      const expiringEl = document.getElementById('rep-kpi-expiring');

      if (todayRevEl && dashSummary) {
        todayRevEl.textContent = `₹${Number(dashSummary.today_revenue || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      }

      if (sevenDayRevEl && reports.daily_sales) {
        const sum7d = reports.daily_sales.reduce((acc, d) => acc + (d.revenue || 0), 0);
        sevenDayRevEl.textContent = `₹${Number(sum7d).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      }

      if (ordersEl && dashSummary) {
        ordersEl.textContent = dashSummary.today_sales_count || 0;
      }

      if (expiringEl) {
        expiringEl.textContent = (reports.expiring_products || []).length;
      }

      // Render Top Selling
      const topTbody = document.getElementById('top-selling-body');
      if (topTbody) {
        if (!reports.top_selling_products || reports.top_selling_products.length === 0) {
          topTbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--color-text-muted); padding: 24px;">No sales recorded yet</td></tr>`;
        } else {
          topTbody.innerHTML = reports.top_selling_products.map(p => `
            <tr>
              <td style="font-weight: 600;">${escapeHtml(p.product_name)}</td>
              <td class="num-tabular">${p.quantity_sold} units</td>
              <td><strong class="num-currency">₹${Number(p.total_revenue).toFixed(2)}</strong></td>
            </tr>
          `).join('');
        }
      }

      // Render Expiring Stock
      const expTbody = document.getElementById('expiring-report-body');
      if (expTbody) {
        if (!reports.expiring_products || reports.expiring_products.length === 0) {
          expTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--status-safe); padding: 24px;">🎉 No stock expiring in the next 60 days!</td></tr>`;
        } else {
          expTbody.innerHTML = reports.expiring_products.map(p => `
            <tr>
              <td style="font-weight: 600;">${escapeHtml(p.product_name)}</td>
              <td><span class="num-batch">${escapeHtml(p.batch_number || 'N/A')}</span></td>
              <td class="num-tabular">${p.quantity}</td>
              <td class="num-date">${escapeHtml(p.expiry_date)}</td>
              <td><span class="badge ${p.days_remaining <= 0 ? 'badge-danger' : 'badge-warning'}">${p.days_remaining <= 0 ? 'Expired' : `${p.days_remaining}d left`}</span></td>
            </tr>
          `).join('');
        }
      }
    } catch (err) {
      console.error('Reports load error:', err);
      const topTbody = document.getElementById('top-selling-body');
      if (topTbody) {
        topTbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--status-danger); padding: 24px;">Failed to load sales reports: ${escapeHtml(err.message)}</td></tr>`;
      }
      const expTbody = document.getElementById('expiring-report-body');
      if (expTbody) {
        expTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--status-danger); padding: 24px;">Failed to load expiring stock: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  };

  loadReports();
}

