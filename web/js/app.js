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

window.salesCache = new Map();
window.cacheSales = function(sales) {
  if (Array.isArray(sales)) {
    sales.forEach(s => {
      if (s && s.id) {
        window.salesCache.set(s.id, s);
      }
    });
  }
};

window.ExpiryTheme = {
  getPreference() {
    try {
      return localStorage.getItem('expiryguard_theme') || 'system';
    } catch (_) {
      return 'system';
    }
  },

  getTheme() {
    return this.resolveTheme(this.getPreference());
  },

  resolveTheme(pref) {
    if (pref === 'dark' || pref === 'light') return pref;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  },

  setTheme(pref, syncBackend = true) {
    const active = this.resolveTheme(pref);
    try {
      localStorage.setItem('expiryguard_theme', pref);
    } catch (_) {}

    const root = document.documentElement;
    root.setAttribute('data-theme', active);
    root.setAttribute('data-theme-preference', pref);
    root.style.backgroundColor = active === 'dark' ? '#0B132B' : '#F8FAFC';
    root.style.colorScheme = active;

    if (document.body) {
      document.body.setAttribute('data-theme', active);
      document.body.style.backgroundColor = active === 'dark' ? '#0B132B' : '#F8FAFC';
    }

    this.updateUI(pref, active);

    if (syncBackend && window.api && typeof api.getToken === 'function' && api.getToken()) {
      api.updateSettings({ preferred_theme: pref }).catch(err => {
        console.warn('Failed to sync theme to backend:', err);
      });
    }
  },

  updateUI(pref, active) {
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) btn.textContent = active === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode';

    const select = document.getElementById('pref-theme-select');
    if (select) select.value = pref;

    // Highlight active card in settings if present
    document.querySelectorAll('.theme-card').forEach(card => {
      const onclickAttr = card.getAttribute('onclick') || '';
      if (
        (pref === 'light' && onclickAttr.includes("'light'")) ||
        (pref === 'dark' && onclickAttr.includes("'dark'")) ||
        ((pref === 'system' || !pref) && onclickAttr.includes("'system'"))
      ) {
        card.style.borderColor = 'var(--color-brand-deep, #10B981)';
        card.style.boxShadow = '0 0 0 2px var(--color-brand-deep, #10B981)';
      } else {
        card.style.borderColor = 'var(--border-color, #E2E8F0)';
        card.style.boxShadow = 'none';
      }
    });
  },

  toggleTheme() {
    const current = this.getTheme();
    this.setTheme(current === 'dark' ? 'light' : 'dark', true);
  },

  init() {
    const pref = this.getPreference();
    const active = this.resolveTheme(pref);

    const root = document.documentElement;
    if (root.getAttribute('data-theme') !== active) {
      root.setAttribute('data-theme', active);
    }
    root.setAttribute('data-theme-preference', pref);
    root.style.backgroundColor = active === 'dark' ? '#0B132B' : '#F8FAFC';
    root.style.colorScheme = active;

    if (document.body) {
      document.body.setAttribute('data-theme', active);
      document.body.style.backgroundColor = active === 'dark' ? '#0B132B' : '#F8FAFC';
    }

    this.updateUI(pref, active);

    if (window.matchMedia && !this._mediaListenerAttached) {
      this._mediaListenerAttached = true;
      try {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
          if (this.getPreference() === 'system') {
            this.setTheme('system', false);
          }
        });
      } catch (_) {}
    }
  }
};

// Cross-tab synchronization
window.addEventListener('storage', (e) => {
  if (e.key === 'expiryguard_theme') {
    window.ExpiryTheme.init();
  }
});

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

  // Check if user is explicitly logged out or missing authentication token
  const isLoggedOut = localStorage.getItem('expiryguard_logged_out') === 'true';
  let token = window.api ? api.getToken() : null;

  if (isLoggedOut || !token) {
    // Hide the app container immediately to prevent any UI flashing
    const appContainer = document.querySelector('.app-container');
    if (appContainer) {
      appContainer.style.display = 'none';
    }

    if (!isLoggedOut && window.api && typeof api.ensureAuthenticated === 'function') {
      token = await api.ensureAuthenticated();
      if (token && appContainer) {
        appContainer.style.display = '';
      }
    }
    
    if (!token) {
      if (window.api && typeof api.showLoginModal === 'function') {
        api.showLoginModal(true);
      }
      // Intercept browser back button to trap user on Login Screen
      window.history.pushState(null, '', window.location.href);
      window.addEventListener('popstate', function() {
        window.history.pushState(null, '', window.location.href);
        if (window.api && typeof api.showLoginModal === 'function') {
          api.showLoginModal(true);
        }
      });
      return;
    }
  }

  // Render canonical sidebar immediately from cache so navigation and UI are instantaneous
  renderCanonicalSidebar();

  // Silently refresh user profile and permissions in the background without blocking page init
  if (token && window.api && typeof api.getUserProfile === 'function') {
    api.getUserProfile().then(profile => {
      if (profile) {
        const currentCached = localStorage.getItem('expiryguard_cached_user_profile');
        if (!currentCached || JSON.stringify(profile) !== currentCached) {
          localStorage.setItem('expiryguard_cached_user_profile', JSON.stringify(profile));
          renderCanonicalSidebar();
        }
      }
    }).catch(e => {
      console.warn('Silent user profile sync error:', e);
    });
  }

  // Sync auth state changes across other tabs
  window.addEventListener('storage', (e) => {
    if (e.key === 'expiryguard_logged_out' && e.newValue === 'true') {
      if (window.api && typeof api.showLoginModal === 'function') {
        api.showLoginModal(true);
      }
      const appContainer = document.querySelector('.app-container');
      if (appContainer) {
        appContainer.style.display = 'none';
      }
    } else if ((e.key === 'expiryguard_token' || e.key === 'expiryguard_session') && e.newValue) {
      window.location.reload();
    }
  });

  // Maintain popstate protection while browsing
  window.addEventListener('popstate', function() {
    if (localStorage.getItem('expiryguard_logged_out') === 'true' || (window.api && !api.getToken())) {
      window.history.pushState(null, '', window.location.href);
      if (window.api && typeof api.showLoginModal === 'function') {
        api.showLoginModal(true);
      }
    }
  });

  // Identify and initialize active page components
  if (document.getElementById('dashboard-page')) {
    initDashboard();
  } else if (document.getElementById('inventory-page')) {
    initInventory();
  } else if (document.getElementById('sales-page')) {
    initSales();
  } else if (document.getElementById('returns-page')) {
    initReturns();
  } else if (document.getElementById('reports-page')) {
    initReports();
  } else if (document.getElementById('billing-page')) {
    if (typeof initBillingEngine === 'function') {
      initBillingEngine();
    }
  }
});

/* ==========================================================================
   1. DASHBOARD PAGE LOGIC & 5-SECOND POLLING
   ========================================================================== */

function initDashboard() {
  let prefetchDone = false;
  const prefetchData = () => {
    if (prefetchDone) return;
    prefetchDone = true;
    
    // Low priority background prefetch to make navigation to other pages instant
    setTimeout(() => {
      // Prefetch products catalog
      if (api.getProducts) {
        api.getProducts().then(prods => {
          if (Array.isArray(prods)) {
            localStorage.setItem('expiryguard_cached_billing_products', JSON.stringify(prods));
            localStorage.setItem('expiryguard_cached_inventory', JSON.stringify(prods.slice(0, 50)));
          }
        }).catch(() => {});
      }

      // Prefetch customer profiles
      if (api.getCustomers) {
        api.getCustomers().then(custs => {
          if (Array.isArray(custs)) {
            localStorage.setItem('expiryguard_cached_billing_customers', JSON.stringify(custs));
          }
        }).catch(() => {});
      }

      // Prefetch supplier list
      if (api.getSuppliers) {
        api.getSuppliers().then(sups => {
          if (Array.isArray(sups)) {
            localStorage.setItem('expiryguard_cached_suppliers', JSON.stringify(sups));
          }
        }).catch(() => {});
      }

      // Prefetch analytics reports summary
      if (api.getReportsSummary) {
        api.getReportsSummary().then(rep => {
          if (rep) {
            localStorage.setItem('expiryguard_cached_reports', JSON.stringify(rep));
          }
        }).catch(() => {});
      }

      // Prefetch inventory intelligence KPIs
      api.request('/inventory/intelligence').then(intel => {
        if (intel) {
          localStorage.setItem('expiryguard_cached_intel', JSON.stringify(intel));
        }
      }).catch(() => {});
    }, 1500); // 1.5s delay to avoid CPU contention during initial load
  };

  const updateDashboardUI = (summary, sales = null) => {
    if (summary) {
      // Render Shop Info & Dynamic Greeting
      if (summary.shop_name) {
        if (window.ExpiryNav && typeof window.ExpiryNav.updateShopName === 'function') {
          window.ExpiryNav.updateShopName(summary.shop_name, summary.role);
        } else {
          const els = document.querySelectorAll('#shop-name-header, #topbar-shop-name, .topbar-shop-name');
          els.forEach(el => { el.textContent = summary.shop_name; });
        }
      }

      // Render KPI Cards
      const totalEl = document.getElementById('kpi-total-products');
      if (totalEl) totalEl.textContent = summary.total_products || 0;

      const salesEl = document.getElementById('kpi-sales-count');
      if (salesEl) salesEl.textContent = Number(summary.today_sales_count || 0).toLocaleString('en-IN');

      const revEl = document.getElementById('kpi-revenue');
      if (revEl) revEl.textContent = `₹${(summary.today_revenue || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

      const expEl = document.getElementById('kpi-expiring');
      if (expEl) expEl.textContent = Number(summary.expiring_soon_count || 0).toLocaleString('en-IN');

      const expdEl = document.getElementById('kpi-expired');
      if (expdEl) expdEl.textContent = Number(summary.expired_count || 0).toLocaleString('en-IN');

      const lowEl = document.getElementById('kpi-low-stock');
      if (lowEl) lowEl.textContent = Number(summary.low_stock_count !== undefined ? summary.low_stock_count : (summary.needs_attention?.low_stock_count || 0)).toLocaleString('en-IN');

      const deadEl = document.getElementById('kpi-dead-stock');
      if (deadEl) deadEl.textContent = Number(summary.dead_stock_count !== undefined ? summary.dead_stock_count : 0).toLocaleString('en-IN');

      const retEl = document.getElementById('kpi-returns');
      if (retEl) retEl.textContent = `₹${(summary.today_returns_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

      const pendSumEl = document.getElementById('kpi-pending-summary');
      if (pendSumEl) {
        const pCount = Array.isArray(summary.pending_payments_list) ? summary.pending_payments_list.length : 0;
        const pTotal = summary.pending_payments_total || 0;
        pendSumEl.textContent = `${pCount} customer${pCount === 1 ? '' : 's'} • ₹${pTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      }

      // Render Pending Payments Ledger
      if (summary.pending_payments_list) {
        renderPendingPaymentsLedger(summary.pending_payments_list, summary.pending_payments_total);
      }
    }

    // Render Live Recent Transactions Feed
    if (sales && Array.isArray(sales)) {
      renderLiveSalesFeed(sales);
    }
  };

  // Immediate 0ms cached render from AppDataPreloader / memory cache
  try {
    const cachedSummary = (window.AppDataPreloader && window.AppDataPreloader.get('/dashboard/summary')) 
      || (api.getCached && api.getCached('/dashboard/summary'))?.data;
    const cachedSales = (window.AppDataPreloader && window.AppDataPreloader.get('/sales?skip=0&limit=10'))
      || (api.getCached && api.getCached('/sales?skip=0&limit=10'))?.data;
    if (cachedSummary) {
      updateDashboardUI(cachedSummary, cachedSales || null);
    }
  } catch (e) {
    console.warn('Silent cache load notice:', e);
  }

  // React to bootstrap data arrival
  window.addEventListener('dawaiflow:bootstrap-ready', (e) => {
    if (e.detail && e.detail.dashboard_summary) {
      updateDashboardUI(e.detail.dashboard_summary, e.detail.recent_sales || null);
    }
  });

  // Re-fetch immediately when a sale, bill or return is mutated
  window.addEventListener('dawaiflow:mutate', (e) => {
    if (e.detail && (e.detail.tag === 'sales' || e.detail.tag === 'returns' || e.detail.tag === 'khata')) {
      renderDashboardData();
    }
  });

  const renderDashboardData = async () => {
    try {
      const [summary, sales] = await Promise.all([
        api.getDashboardSummary(),
        api.getSales(0, 10)
      ]);

      updateDashboardUI(summary, sales);
      prefetchData();

    } catch (err) {
      console.error('Dashboard load error:', err);
    }
  };

  // Start 5-second polling engine
  api.startPolling(renderDashboardData, 5000);
}

function renderLiveSalesFeed(sales) {
  window.cacheSales(sales);
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

let inventoryCurrentPage = 1;
let inventoryPageSize = 50;
let inventoryTotalCount = 0;
let inventoryTotalPages = 1;
let currentFilter = 'all';
let selectedStockIds = new Set();
let inventorySearchDebounce = null;

window.setInventoryFilter = function(filterKey) {
  currentFilter = filterKey;
  inventoryCurrentPage = 1;
  document.querySelectorAll('.filter-btn').forEach(b => {
    const bFilter = (b.dataset.filter || '').toLowerCase();
    const fk = (filterKey || '').toLowerCase();
    const isMatch = bFilter === fk || 
                    (fk.includes('dead') && bFilter.includes('dead')) ||
                    (fk.includes('risk') && bFilter.includes('risk')) ||
                    (fk === 'expiring' && bFilter === 'expiring');
    b.classList.toggle('active', isMatch);
  });
  fetchInventoryPage();

  const tablePanel = document.querySelector('.panel');
  if (tablePanel) {
    tablePanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};

window.changeInventoryPage = function(delta) {
  const newPage = inventoryCurrentPage + delta;
  if (newPage >= 1 && newPage <= inventoryTotalPages) {
    inventoryCurrentPage = newPage;
    fetchInventoryPage();
  }
};

window.changeInventoryPageSize = function(newSize) {
  inventoryPageSize = parseInt(newSize, 10) || 50;
  inventoryCurrentPage = 1;
  fetchInventoryPage();
};

async function fetchInventoryPage() {
  const tbody = document.getElementById('inventory-table-body');
  if (!tbody) return;

  const searchVal = (document.getElementById('inventory-search')?.value || '').trim();

  try {
    const res = await api.getProducts({
      page: inventoryCurrentPage,
      limit: inventoryPageSize,
      filter: currentFilter,
      search: searchVal,
    });

    let items = [];
    if (Array.isArray(res)) {
      items = res;
      inventoryTotalCount = res.length;
      inventoryTotalPages = 1;
    } else if (res && Array.isArray(res.items)) {
      items = res.items;
      inventoryTotalCount = res.total || 0;
      inventoryTotalPages = res.pages || Math.ceil(inventoryTotalCount / inventoryPageSize) || 1;
    }

    if (inventoryCurrentPage === 1 && !currentFilter && !searchVal) {
      localStorage.setItem('expiryguard_cached_inventory', JSON.stringify(items));
    }

    renderInventoryRows(items);
    updatePaginationUI();
  } catch (err) {
    console.error('Failed to fetch inventory page:', err);
  }
}

function updatePaginationUI() {
  const rangeEl = document.getElementById('pagination-range-info');
  const totalEl = document.getElementById('pagination-total-count');
  const pageEl = document.getElementById('pagination-current-page');
  const totalPagesEl = document.getElementById('pagination-total-pages');
  const prevBtn = document.getElementById('btn-page-prev');
  const nextBtn = document.getElementById('btn-page-next');

  const start = inventoryTotalCount === 0 ? 0 : (inventoryCurrentPage - 1) * inventoryPageSize + 1;
  const end = Math.min(inventoryCurrentPage * inventoryPageSize, inventoryTotalCount);

  if (rangeEl) rangeEl.textContent = `${start.toLocaleString('en-IN')}-${end.toLocaleString('en-IN')}`;
  if (totalEl) totalEl.textContent = inventoryTotalCount.toLocaleString('en-IN');
  if (pageEl) pageEl.textContent = inventoryCurrentPage.toLocaleString('en-IN');
  if (totalPagesEl) totalPagesEl.textContent = inventoryTotalPages.toLocaleString('en-IN');

  if (prevBtn) prevBtn.disabled = (inventoryCurrentPage <= 1);
  if (nextBtn) nextBtn.disabled = (inventoryCurrentPage >= inventoryTotalPages);
}

function renderInventoryRows(items) {
  const tbody = document.getElementById('inventory-table-body');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--color-text-muted); padding: 36px 16px;">
      <div style="font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 4px;">No inventory batches match this view</div>
      <div style="font-size: 12px; color: var(--color-text-muted); margin-bottom: 12px;">Try adjusting your filter or search keywords, or add new stock.</div>
      <button class="btn btn-primary" style="padding: 6px 14px; font-size: 12.5px;" onclick="openAddInventoryModal()">+ Add Inventory</button>
    </td></tr>`;
    updateSelectionUI();
    return;
  }

  tbody.innerHTML = items.map(p => {
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
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="viewProductDetails(${p.id})">Stock Card</button>
            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 12px; color: #DC2626; border-color: #FCA5A5;" onclick="deleteSingleInventoryStock(${p.id}, '${window.escapeHtml(p.product_name)}')">🗑️ Delete</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  updateSelectionUI();
}

window.deleteSingleInventoryStock = async function(stockId, medName) {
  if (!confirm(`Are you sure you want to delete '${medName}' from active inventory? It will be moved to Recently Deleted (60-day recovery guarantee).`)) {
    return;
  }
  try {
    const res = await api.deleteInventoryStock([stockId]);
    showToastNotification(res.message || `'${medName}' moved to Recently Deleted.`, true);
    if (window.api && typeof window.api.invalidateCache === 'function') {
      window.api.invalidateCache(['products', 'inventory', 'dashboard', 'reports', 'analytics']);
    }
    localStorage.removeItem('expiryguard_cached_inventory');
    localStorage.removeItem('expiryguard_cached_billing_products');
    if (typeof fetchInventoryPage === 'function') fetchInventoryPage();
    if (typeof initInventory === 'function') initInventory();
  } catch (err) {
    showToastNotification(`Failed to delete '${medName}': ${err.message}`, false);
  }
};

function initInventory() {
  const renderIntel = (intel) => {
    if (intel) {
      const s = intel.summary || {};
      const totalProducts = intel.total_products !== undefined ? intel.total_products : (s.total_products !== undefined ? s.total_products : 0);
      const totalStockValue = intel.total_stock_value !== undefined ? intel.total_stock_value : (s.total_stock_value !== undefined ? s.total_stock_value : 0);
      const expiringSoonCount = intel.expiring_30_days !== undefined ? intel.expiring_30_days : (intel.expiring_30d_count !== undefined ? intel.expiring_30d_count : (s.expiring_30_days !== undefined ? s.expiring_30_days : (s.expiry_risk || 0)));
      const expiredCount = intel.expired !== undefined ? intel.expired : (intel.expired_count !== undefined ? intel.expired_count : (s.expired !== undefined ? s.expired : 0));
      const lowStockCount = intel.low_stock !== undefined ? intel.low_stock : (intel.low_stock_count !== undefined ? intel.low_stock_count : (s.low_stock !== undefined ? s.low_stock : (s.critical_restock || 0)));
      const deadStockCount = intel.dead_stock !== undefined ? intel.dead_stock : (intel.dead_stock_count !== undefined ? intel.dead_stock_count : (s.dead_stock !== undefined ? s.dead_stock : 0));

      const totalEl = document.getElementById('kpi-total-products');
      if (totalEl) totalEl.textContent = Number(totalProducts).toLocaleString('en-IN');

      const valEl = document.getElementById('kpi-stock-value');
      if (valEl) valEl.textContent = `₹${Number(totalStockValue).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

      const expEl = document.getElementById('kpi-expiring-soon');
      if (expEl) expEl.textContent = Number(expiringSoonCount).toLocaleString('en-IN');

      const expdEl = document.getElementById('kpi-expired');
      if (expdEl) expdEl.textContent = Number(expiredCount).toLocaleString('en-IN');

      const lowEl = document.getElementById('kpi-low-stock');
      if (lowEl) lowEl.textContent = Number(lowStockCount).toLocaleString('en-IN');

      const deadEl = document.getElementById('kpi-dead-stock');
      if (deadEl) deadEl.textContent = Number(deadStockCount).toLocaleString('en-IN');

      const banner = document.getElementById('inventory-attention-banner');
      const chips = document.getElementById('inventory-attention-chips');
      if (banner && chips && Array.isArray(intel.needs_attention) && intel.needs_attention.length > 0) {
        banner.style.display = 'block';
        chips.innerHTML = intel.needs_attention.map(item => `
          <button type="button" class="btn btn-secondary" style="padding: 4px 10px; font-size: 11.5px; font-weight: 600;" onclick="setInventoryFilter('${item.type}')">
            ${item.title} (${item.subtitle})
          </button>
        `).join('');
      } else if (banner) {
        banner.style.display = 'none';
      }
    }
  };

  // Load cached metrics immediately for 0ms visual delay from AppDataPreloader or localStorage
  try {
    const preloaderIntel = window.AppDataPreloader ? window.AppDataPreloader.get('/inventory/intelligence') : null;
    const preloaderSummary = window.AppDataPreloader ? window.AppDataPreloader.get('/inventory/summary') : null;
    if (preloaderIntel) {
      renderIntel(preloaderIntel);
    } else if (preloaderSummary) {
      renderIntel({ summary: preloaderSummary, total_products: preloaderSummary.total_products, total_stock_value: preloaderSummary.total_stock_value });
    } else {
      const cachedIntel = localStorage.getItem('expiryguard_cached_intel');
      if (cachedIntel) renderIntel(JSON.parse(cachedIntel));
    }

    const preloaderInv = window.AppDataPreloader ? window.AppDataPreloader.get('/products') : null;
    if (Array.isArray(preloaderInv) && preloaderInv.length > 0) {
      renderInventoryRows(preloaderInv.slice(0, 50));
      updatePaginationUI();
    } else {
      const cachedInv = localStorage.getItem('expiryguard_cached_inventory');
      if (cachedInv) {
        const inv = JSON.parse(cachedInv);
        renderInventoryRows(inv);
        updatePaginationUI();
      }
    }
  } catch (e) {
    console.warn('Failed to load cached inventory data:', e);
  }

  // React to mutations
  window.addEventListener('dawaiflow:mutate', (e) => {
    if (e.detail && (e.detail.tag === 'inventory' || e.detail.tag === 'sales')) {
      fetchInventoryPage();
      loadIntelligence();
    }
  });

  const loadIntelligence = async () => {
    try {
      const intel = await api.request('/inventory/intelligence').catch(() => null);
      if (intel) {
        localStorage.setItem('expiryguard_cached_intel', JSON.stringify(intel));
        renderIntel(intel);
      }
    } catch (err) {
      console.error('Inventory intel load error:', err);
    }
  };

  // Setup Filter Buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.dataset.filter;
      inventoryCurrentPage = 1;
      fetchInventoryPage();
    });
  });

  // Setup Search Input with 300ms Debounce
  const searchInput = document.getElementById('inventory-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(inventorySearchDebounce);
      inventorySearchDebounce = setTimeout(() => {
        inventoryCurrentPage = 1;
        fetchInventoryPage();
      }, 300);
    });
  }

  // Initial load in the background
  loadIntelligence();
  const urlParams = new URLSearchParams(window.location.search);
  const filterParam = urlParams.get('filter') || urlParams.get('filter_key');
  if (filterParam && typeof window.setInventoryFilter === 'function') {
    window.setInventoryFilter(filterParam);
  } else {
    fetchInventoryPage();
  }
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
    
    // Invalidate client-side caches and refresh inventory page & KPIs immediately
    if (window.api && typeof window.api.invalidateCache === 'function') {
      window.api.invalidateCache(['products', 'inventory', 'dashboard', 'reports', 'analytics']);
    }
    localStorage.removeItem('expiryguard_cached_inventory');
    localStorage.removeItem('expiryguard_cached_billing_products');

    if (typeof fetchInventoryPage === 'function') {
      fetchInventoryPage();
    } else if (typeof loadInventoryProducts === 'function') {
      loadInventoryProducts();
    } else if (typeof applyInventoryFilters === 'function') {
      applyInventoryFilters();
    }
    if (typeof initInventory === 'function') {
      initInventory();
    }
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
  const totalCount = (typeof inventoryTotalCount === 'number' && inventoryTotalCount > 0) ? inventoryTotalCount : (Array.isArray(allProducts) ? allProducts.length : 0);
  if (window.ConfirmModal) {
    ConfirmModal({
      isOpen: true,
      title: 'Delete All Stock',
      message: `This will remove all stock items from your active live inventory. All items will be moved to Recently Deleted (60-day recovery guarantee).`,
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
    
    // Invalidate client-side caches and refresh inventory page & KPIs immediately
    if (window.api && typeof window.api.invalidateCache === 'function') {
      window.api.invalidateCache(['products', 'inventory', 'dashboard', 'reports', 'analytics']);
    }
    localStorage.removeItem('expiryguard_cached_inventory');
    localStorage.removeItem('expiryguard_cached_billing_products');

    if (typeof fetchInventoryPage === 'function') {
      fetchInventoryPage();
    } else if (typeof loadInventoryProducts === 'function') {
      loadInventoryProducts();
    } else if (typeof applyInventoryFilters === 'function') {
      applyInventoryFilters();
    }
    if (typeof initInventory === 'function') {
      initInventory();
    }
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

let salesCurrentPage = 1;
const salesPageLimit = 50;
let salesActivePeriod = 'today';
let salesActiveType = 'all';
let salesSearchQuery = '';
let salesCustomFrom = null;
let salesCustomTo = null;
let salesSearchDebounceTimer = null;
let salesInitialAutoCheckDone = false;

function initSales() {
  const urlParams = new URLSearchParams(window.location.search);
  const paramSource = urlParams.get('source') || urlParams.get('type') || urlParams.get('sales_type');
  const paramPeriod = urlParams.get('period') || urlParams.get('range');

  if (paramSource) {
    if (paramSource === 'historical') {
      salesActiveType = 'historical';
      salesActivePeriod = 'all_time';
    } else if (paramSource === 'live') {
      salesActiveType = 'live';
    } else {
      salesActiveType = 'all';
    }
    const typeSelect = document.getElementById('sales-type-select');
    if (typeSelect) typeSelect.value = salesActiveType;
  }

  if (paramPeriod) {
    salesActivePeriod = paramPeriod;
  }

  // Highlight active period button tab
  document.querySelectorAll('.sales-period-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-period') === salesActivePeriod);
  });

  updateSalesSummaryLabel();

  // Load cached sales immediately for 0ms visual delay if on default 'today' view
  try {
    const preloaderSales = window.AppDataPreloader ? window.AppDataPreloader.get(`/sales?skip=0&limit=50&period=${salesActivePeriod}`) : null;
    const cachedSales = preloaderSales
      || (window.api && typeof window.api.getCached === 'function' && window.api.getCached(`/sales?skip=0&limit=50&period=${salesActivePeriod}`))
      || (localStorage.getItem('expiryguard_cached_sales') ? JSON.parse(localStorage.getItem('expiryguard_cached_sales')) : null);
    if (Array.isArray(cachedSales) && cachedSales.length > 0 && salesActivePeriod === 'today' && !salesSearchQuery) {
      renderSalesList(cachedSales);
    }
  } catch (e) {}

  // Re-fetch immediately on sales or returns mutations
  window.addEventListener('dawaiflow:mutate', (e) => {
    if (e.detail && (e.detail.tag === 'sales' || e.detail.tag === 'returns')) {
      loadSalesFeed();
    }
  });

  loadSalesFeed();
  api.startPolling(() => {
    // Only auto-poll if user is looking at 'today' without active search
    if (salesActivePeriod === 'today' && !salesSearchQuery && salesCurrentPage === 1) {
      loadSalesFeed(false);
    }
  }, 5000);
}

async function loadSalesFeed(showLoading = true) {
  const tbody = document.getElementById('sales-table-body');
  if (showLoading && tbody && (!tbody.children || tbody.children.length === 0)) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--muted-text); padding: 24px;">Loading transactions...</td></tr>`;
  }

  const skip = (salesCurrentPage - 1) * salesPageLimit;
  const options = {
    period: salesActivePeriod,
    sales_type: salesActiveType,
    search: salesSearchQuery || null,
    from_date: salesCustomFrom || null,
    to_date: salesCustomTo || null,
  };

  try {
    const sales = await api.getSales(skip, salesPageLimit, null, options);
    if (Array.isArray(sales)) {
      const urlParams = new URLSearchParams(window.location.search);
      const hasExplicitPeriodInUrl = urlParams.has('period') || urlParams.has('range');

      // Auto-fallback: If default initial load is 'today' and returned 0 sales, check if user has 'all_time' sales (e.g. imported old bills)
      if (!salesInitialAutoCheckDone && salesActivePeriod === 'today' && sales.length === 0 && !salesSearchQuery && !hasExplicitPeriodInUrl) {
        salesInitialAutoCheckDone = true;
        try {
          const allTimeSales = await api.getSales(0, salesPageLimit, null, { ...options, period: 'all_time' });
          if (Array.isArray(allTimeSales) && allTimeSales.length > 0) {
            salesActivePeriod = 'all_time';
            document.querySelectorAll('.sales-period-btn').forEach(btn => {
              btn.classList.toggle('active', btn.getAttribute('data-period') === 'all_time');
            });
            updateSalesSummaryLabel();
            renderSalesList(allTimeSales);
            updateSalesPagination(allTimeSales.length);
            return;
          }
        } catch (checkErr) {}
      }
      salesInitialAutoCheckDone = true;

      if (salesActivePeriod === 'today' && !salesSearchQuery && salesCurrentPage === 1) {
        localStorage.setItem('expiryguard_cached_sales', JSON.stringify(sales));
      }
      renderSalesList(sales);
      updateSalesPagination(sales.length);
    }
  } catch (err) {
    console.error('Sales load error:', err);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--color-danger, #ef4444); padding: 24px;">Failed to load sales: ${err.message || 'Network error'}</td></tr>`;
    }
  }
}

function selectSalesPeriod(period) {
  salesActivePeriod = period;
  salesCurrentPage = 1;

  document.querySelectorAll('.sales-period-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-period') === period);
  });

  const customBox = document.getElementById('sales-custom-date-box');
  if (period === 'custom') {
    if (customBox) customBox.style.display = 'flex';
  } else {
    if (customBox) customBox.style.display = 'none';
    salesCustomFrom = null;
    salesCustomTo = null;
    updateSalesSummaryLabel();
    loadSalesFeed();
  }
}

function applySalesCustomDate() {
  const startInput = document.getElementById('sales-start-date');
  const endInput = document.getElementById('sales-end-date');
  if (!startInput?.value || !endInput?.value) {
    alert('Please select both start and end dates.');
    return;
  }
  if (startInput.value > endInput.value) {
    alert('Start date cannot be after end date.');
    return;
  }
  salesCustomFrom = startInput.value;
  salesCustomTo = endInput.value;
  salesCurrentPage = 1;
  updateSalesSummaryLabel();
  loadSalesFeed();
}

function onSalesTypeChange(type) {
  salesActiveType = type;
  salesCurrentPage = 1;
  updateSalesSummaryLabel();
  loadSalesFeed();
}

function onSalesSearchInput(val) {
  clearTimeout(salesSearchDebounceTimer);
  salesSearchDebounceTimer = setTimeout(() => {
    salesSearchQuery = (val || '').trim();
    salesCurrentPage = 1;
    updateSalesSummaryLabel();
    loadSalesFeed();
  }, 300);
}

function updateSalesSummaryLabel() {
  const summaryEl = document.getElementById('sales-results-summary');
  if (!summaryEl) return;

  let text = '';
  if (salesSearchQuery) {
    text = `Search results for "${salesSearchQuery}"`;
  } else if (salesActivePeriod === 'today') {
    text = "Showing today's counter transactions";
  } else if (salesActivePeriod === 'yesterday') {
    text = "Showing yesterday's transactions";
  } else if (salesActivePeriod === 'this_week') {
    text = "Showing transactions from this week (last 7 days)";
  } else if (salesActivePeriod === 'this_month') {
    text = "Showing transactions from this month";
  } else if (salesActivePeriod === 'all_time') {
    text = "Showing all historical and live transactions across all time";
  } else if (salesActivePeriod === 'custom') {
    text = `Showing transactions from ${salesCustomFrom || ''} to ${salesCustomTo || ''}`;
  } else {
    text = `Showing transactions for calendar year ${salesActivePeriod}`;
  }

  if (salesActiveType === 'historical') {
    text += ' (Imported Historical only)';
  } else if (salesActiveType === 'live') {
    text += ' (Live Counter POS only)';
  }

  summaryEl.textContent = text;
}

function changeSalesPage(delta) {
  salesCurrentPage = Math.max(1, salesCurrentPage + delta);
  loadSalesFeed();
}

function updateSalesPagination(returnedCount) {
  const pageInfo = document.getElementById('sales-page-info');
  const prevBtn = document.getElementById('btn-sales-prev');
  const nextBtn = document.getElementById('btn-sales-next');

  const start = (salesCurrentPage - 1) * salesPageLimit + 1;
  const end = (salesCurrentPage - 1) * salesPageLimit + returnedCount;

  if (pageInfo) {
    if (returnedCount === 0 && salesCurrentPage === 1) {
      pageInfo.textContent = 'No records found';
    } else {
      pageInfo.textContent = `Showing rows ${start} to ${end} (Page ${salesCurrentPage})`;
    }
  }

  if (prevBtn) prevBtn.disabled = (salesCurrentPage <= 1);
  if (nextBtn) nextBtn.disabled = (returnedCount < salesPageLimit);
}

function renderSalesList(sales) {
  window.cacheSales(sales);
  const tbody = document.getElementById('sales-table-body');
  if (!tbody) return;

  if (!sales || sales.length === 0) {
    const periodLabel = salesActivePeriod === 'today' ? 'today' : (salesActivePeriod === 'yesterday' ? 'yesterday' : salesActivePeriod);
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--color-text-muted); padding: 36px 16px;">
      <div style="font-size: 15px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 6px;">No transactions found for ${periodLabel}</div>
      <div style="font-size: 13px; color: var(--color-text-muted); max-width: 480px; margin: 0 auto 16px auto;">
        ${salesActivePeriod === 'today' ? 'No new counter bills were created today. If you imported old bills from Marg/Excel or want to see past bills, click below.' : 'Try selecting "All Time", adjusting your date range, or clearing search.'}
      </div>
      <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
        <button class="btn btn-primary btn-sm" onclick="selectSalesPeriod('all_time')" style="padding: 6px 14px; font-weight: 600;">📅 View All Time Sales & Imported Bills</button>
        ${salesActiveType !== 'all' ? `<button class="btn btn-secondary btn-sm" onclick="onSalesTypeChange('all'); const sel = document.getElementById('sales-type-select'); if (sel) sel.value='all';" style="padding: 6px 14px;">Show All Sales (Live + Imported)</button>` : ''}
      </div>
    </td></tr>`;
    return;
  }

  tbody.innerHTML = sales.map(s => {
    // Preserve original bill date formatting
    const d = new Date(s.created_at);
    const dateStr = !isNaN(d.getTime()) ? d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : (s.created_at || '-');
    const timeStr = !isNaN(d.getTime()) ? d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '';
    
    // Display original bill number if historical, or internal bill_number
    const displayBillNo = s.original_bill_number || s.bill_number;
    const isHist = Boolean(s.is_historical);

    const typeBadge = isHist
      ? `<span class="badge" style="background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; font-size: 11px; font-weight: 600; padding: 2px 8px;">📜 Historical</span>`
      : `<span class="badge" style="background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; font-size: 11px; font-weight: 600; padding: 2px 8px;">⚡ Live POS</span>`;

    return `
      <tr onclick="openBillDetailModal(${s.id})" style="cursor: pointer;">
        <td>
          <div style="display: flex; flex-direction: column;">
            <strong class="num-tabular" style="font-size: 13.5px; color: var(--color-text-primary);">${displayBillNo}</strong>
            ${isHist && s.original_bill_number && s.original_bill_number !== s.bill_number ? `<span style="font-size: 10px; color: var(--color-text-muted); font-family: monospace;">${s.bill_number}</span>` : ''}
          </div>
        </td>
        <td>
          <div style="font-weight: 600; color: var(--color-text-primary);">${s.customer_name || 'Walk-in Customer'}</div>
          ${s.customer_phone ? `<div style="font-size: 11.5px; color: var(--color-text-muted);">${s.customer_phone}</div>` : ''}
        </td>
        <td>${s.doctor_name ? `Dr. ${s.doctor_name}` : '-'}</td>
        <td class="num-date">
          <div style="font-weight: 500;">${dateStr}</div>
          <div style="font-size: 11px; color: var(--color-text-muted);">${timeStr}</div>
        </td>
        <td><strong class="num-currency" style="font-size: 14.5px; color: var(--color-brand-deep, #10B981);">₹${Number(s.total_amount || 0).toFixed(2)}</strong></td>
        <td><span class="badge badge-info" style="font-size: 11px;">${s.payment_method || 'CASH'}</span></td>
        <td>${typeBadge}</td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px; display: inline-flex; align-items: center; gap: 4px;" onclick="event.stopPropagation(); window.open('${api.getInvoicePdfUrl(s.id)}', '_blank')">
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
    let sale = window.salesCache ? window.salesCache.get(saleId) : null;
    if (!sale) {
      sale = await api.getSale(saleId);
      if (sale && window.salesCache) {
        window.salesCache.set(sale.id, sale);
      }
    }
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
        <td class="num-currency">₹${Number(i.unit_price || 0).toFixed(2)}</td>
        <td class="num-currency">₹${Number(i.taxable_value || i.total_price || 0).toFixed(2)}</td>
        <td><strong class="num-currency">₹${Number(i.total_with_tax || i.total_price || 0).toFixed(2)}</strong></td>
      </tr>
    `).join('');

    const displayBillNo = sale.original_bill_number || sale.bill_number;
    const isHist = Boolean(sale.is_historical);
    const d = new Date(sale.created_at);
    const formattedDate = !isNaN(d.getTime()) 
      ? d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
      : sale.created_at;

    const histBadgeHtml = isHist 
      ? `<span class="badge" style="background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; font-size: 11.5px; font-weight: 600; padding: 3px 10px; margin-left: 8px;">📜 Imported · Historical Sale</span>` 
      : `<span class="badge" style="background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; font-size: 11.5px; font-weight: 600; padding: 3px 10px; margin-left: 8px;">⚡ Live POS Invoice</span>`;

    modal.innerHTML = `
      <div class="modal-card" style="max-width: 680px;">
        <div class="modal-header">
          <div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <h3 class="panel-title" style="margin-bottom: 2px;">GST Tax Invoice #${displayBillNo}</h3>
              ${histBadgeHtml}
            </div>
            <span style="font-size: 12px; color: var(--color-text-muted);">Standardized DawaiFlow GST Tax Invoice</span>
          </div>
          <button class="close-btn" onclick="document.getElementById('bill-detail-modal').classList.remove('active')">&times;</button>
        </div>
        
        <div style="background-color: #F8FAFC; border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 12px 16px; margin-bottom: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12.5px;">
          <div><strong style="color: var(--color-text-muted);">Patient / Customer:</strong> ${sale.customer_name || 'Walk-in Customer'} ${sale.customer_phone ? `(${sale.customer_phone})` : ''}</div>
          <div><strong style="color: var(--color-text-muted);">Doctor Prescribed:</strong> ${sale.doctor_name ? `Dr. ${sale.doctor_name}` : 'Over The Counter'}</div>
          <div><strong style="color: var(--color-text-muted);">Payment Mode:</strong> <span class="badge badge-info" style="font-size: 11px;">${sale.payment_method || 'CASH'}</span></div>
          <div><strong style="color: var(--color-text-muted);">Original Sale Date:</strong> <span class="num-date" style="font-weight: 600;">${formattedDate}</span></div>
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
            <tbody>${itemsHtml || '<tr><td colspan="6" style="text-align: center; color: var(--muted-text);">No medicine items recorded</td></tr>'}</tbody>
          </table>
        </div>

        <div style="background-color: #F8FAFC; border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 14px 18px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 4px; font-size: 13px;">
          <div style="display: flex; justify-content: space-between; color: var(--color-text-muted);">
            <span>Subtotal (Taxable):</span>
            <span class="num-currency">₹${Number(sale.subtotal || 0).toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; color: var(--color-text-muted);">
            <span>Discount Applied:</span>
            <span class="num-currency">₹${Number(sale.discount_amount || 0).toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; color: var(--color-text-muted);">
            <span>GST Tax (CGST + SGST):</span>
            <span class="num-currency">₹${Number(sale.tax_amount || 0).toFixed(2)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 17px; font-weight: 700; color: var(--color-brand-deep, #10B981); border-top: 1px solid var(--color-border); padding-top: 8px; margin-top: 4px;">
            <span>Grand Total:</span>
            <span class="num-currency" style="font-size: 20px;">₹${Number(sale.total_amount || 0).toFixed(2)}</span>
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

async function handleExportSalesClick() {
  const btn = document.getElementById('btn-export-sales');
  const label = document.getElementById('export-sales-label');
  const originalHtml = label ? label.innerHTML : 'Export Live Bills CSV';

  try {
    if (btn) btn.disabled = true;
    if (label) label.textContent = 'Exporting...';

    const res = await api.exportSalesCsv(false);
    const count = res.count || 0;
    if (count === 0) {
      alert('No unexported sales bills found to export.');
    } else {
      alert(`Successfully exported ${count} bill(s) to CSV! These bills are now archived from the live sales counter feed.`);
    }
  } catch (err) {
    console.error('Export sales error:', err);
    alert('Failed to export sales: ' + (err.message || 'Unknown error'));
  } finally {
    if (btn) btn.disabled = false;
    if (label) label.innerHTML = originalHtml;
  }
}

/* ==========================================================================
   4. RETURNS PAGE LOGIC
   ========================================================================== */

function initReturns() {
  // Load cached returns immediately for 0ms visual delay from AppDataPreloader or cache
  try {
    const preloaderReturns = window.AppDataPreloader ? window.AppDataPreloader.get('/billing/returns/today') : null;
    if (preloaderReturns && Array.isArray(preloaderReturns)) {
      renderReturnsList(preloaderReturns);
    } else if (preloaderReturns && typeof preloaderReturns === 'object') {
      const refundEl = document.getElementById('returns-total-refund');
      if (refundEl && preloaderReturns.refund_total !== undefined) {
        refundEl.textContent = `₹${Number(preloaderReturns.refund_total || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      }
      const countEl = document.getElementById('returns-count');
      if (countEl && preloaderReturns.count !== undefined) {
        countEl.textContent = preloaderReturns.count || 0;
      }
    } else {
      const memCached = window.api && typeof window.api.getCached === 'function' ? window.api.getCached('/returns/today') : null;
      if (Array.isArray(memCached) && memCached.length > 0) {
        renderReturnsList(memCached);
      } else {
        const cachedReturns = localStorage.getItem('expiryguard_cached_returns');
        if (cachedReturns) {
          renderReturnsList(JSON.parse(cachedReturns));
        }
      }
    }
  } catch (e) {
    console.warn('Failed to parse cached returns:', e);
  }

  // Re-fetch immediately on returns mutations
  window.addEventListener('dawaiflow:mutate', (e) => {
    if (e.detail && e.detail.tag === 'returns') {
      loadReturns();
    }
  });

  const loadReturns = async () => {
    if (typeof window.loadTodayReturns === 'function') {
      await window.loadTodayReturns();
      return;
    }
    try {
      const returns = await api.getTodaysReturns();
      renderReturnsList(returns);
    } catch (err) {
      console.error('Returns load error:', err);
      const container = document.getElementById('returns-list-body');
      if (container && !container.innerHTML.trim()) {
        container.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--status-danger); padding: 24px;">Failed to load returns log: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  };

  loadReturns();
  api.startPolling(loadReturns, 5000);
}

function renderReturnsList(returnsData) {
  const container = document.getElementById('returns-list-body');
  if (!container) return;

  let returnsList = [];
  let totalRefund = 0;
  let returnsCount = 0;
  let totalItems = 0;

  if (Array.isArray(returnsData)) {
    returnsList = returnsData;
    returnsCount = returnsList.length;
    returnsList.forEach(r => {
      totalRefund += (r.refund_amount || r.return_amount || 0);
      totalItems += (r.returned_quantity || r.quantity || 1);
    });
  } else if (returnsData && typeof returnsData === 'object') {
    returnsList = returnsData.returns || [];
    returnsCount = returnsData.total_returns_count || returnsList.length;
    totalRefund = returnsData.total_return_value || 0;
    totalItems = returnsData.total_items_returned_count || 0;
  }

  const refundEl = document.getElementById('returns-total-refund');
  if (refundEl) {
    refundEl.textContent = `₹${totalRefund.toFixed(2)}`;
  }
  const countEl = document.getElementById('returns-count');
  if (countEl) {
    countEl.textContent = returnsCount;
  }
  const itemsCountEl = document.getElementById('returns-items-count');
  if (itemsCountEl) {
    itemsCountEl.textContent = `${totalItems} items`;
  }

  if (!returnsList || returnsList.length === 0) {
    container.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 36px 16px;">
      <div style="font-size: 24px; margin-bottom: 6px;">🔄</div>
      <div style="font-weight: 600; font-size: 14px; color: var(--color-text-primary);">No returned items recorded today</div>
      <div style="font-size: 12.5px; color: var(--color-text-muted); margin-top: 2px;">Patient returns and stock adjustments will be listed here.</div>
    </td></tr>`;
    return;
  }

  container.innerHTML = returnsList.map(r => {
    const returnId = r.return_id || r.id || 'N/A';
    const rawBill = r.bill_number ? String(r.bill_number) : (r.sale_id ? `BILL-${r.sale_id}` : 'N/A');
    const billNo = rawBill.toLowerCase().startsWith('bill') ? rawBill : `Bill #${rawBill}`;
    const customer = r.customer_name || 'Walk-in Customer';
    const medName = r.product_name || 'Medicine Item';
    const batchNo = r.batch_number;
    const qty = r.returned_quantity || r.quantity || 1;
    const refundAmt = r.refund_amount || r.return_amount || 0;
    const reasonText = r.reason || 'Customer Return';
    const pharmacist = r.processed_by || 'Pharmacist';
    const dateStr = (r.returned_at || r.created_at) ? new Date(r.returned_at || r.created_at).toLocaleString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true
    }) : '-';

    return `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 12.5px; font-weight: 700; color: var(--color-text-primary);">
          #RET-${returnId}
        </td>
        <td>
          <div style="font-family: var(--font-mono); font-weight: 700; color: var(--color-brand-deep,#0D9488); font-size: 13px;">
            ${escapeHtml(billNo)}
          </div>
          <div style="font-size: 11.5px; color: var(--color-text-muted);">${escapeHtml(customer)}</div>
        </td>
        <td>
          <div style="font-weight: 700; color: var(--color-text-primary); font-size: 13.5px;">${escapeHtml(medName)}</div>
          ${batchNo ? `<span style="font-size: 11px; background: rgba(13,148,136,0.1); color: #0D9488; padding: 2px 6px; border-radius: 4px; font-weight: 600;">Batch: ${escapeHtml(batchNo)}</span>` : ''}
        </td>
        <td style="font-family: var(--font-mono); font-weight: 800; font-size: 14px; text-align: center; color: #DC2626;">
          ${qty}
        </td>
        <td style="font-family: var(--font-mono); font-weight: 800; font-size: 14px; color: #DC2626;">
          ₹${Number(refundAmt).toFixed(2)}
        </td>
        <td style="font-size: 12.5px; color: var(--color-text-secondary);">
          ${escapeHtml(reasonText)}
        </td>
        <td style="font-size: 12px; color: var(--color-text-muted);">
          ${dateStr}<br>
          <span style="font-size: 11px; color: var(--color-text-secondary);">By ${escapeHtml(pharmacist)}</span>
        </td>
      </tr>
    `;
  }).join('');
}

/* ==========================================================================
   6. REPORTS PAGE LOGIC
   ========================================================================== */

function initReports() {
  if (window.ReportsApp && typeof window.ReportsApp.init === 'function') {
    return;
  }
  const renderReportsUI = (reports, dashSummary) => {
    // Render KPIs
    const todayRevEl = document.getElementById('rep-kpi-today-rev');
    const sevenDayRevEl = document.getElementById('rep-kpi-7d-rev');
    const ordersEl = document.getElementById('rep-kpi-orders');
    const expiringEl = document.getElementById('rep-kpi-expiring');

    if (todayRevEl && dashSummary) {
      todayRevEl.textContent = `₹${Number(dashSummary.today_revenue || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    }

    if (sevenDayRevEl && reports && reports.daily_sales) {
      const sum7d = reports.daily_sales.reduce((acc, d) => acc + (d.revenue || 0), 0);
      sevenDayRevEl.textContent = `₹${Number(sum7d).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    }

    if (ordersEl && dashSummary) {
      ordersEl.textContent = dashSummary.today_sales_count || 0;
    }

    if (expiringEl && reports) {
      expiringEl.textContent = (reports.expiring_products || []).length;
    }

    // Render Top Selling
    const topTbody = document.getElementById('top-selling-body');
    if (topTbody && reports) {
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
    if (expTbody && reports) {
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
  };

  // Load cached reports immediately for 0ms visual delay
  try {
    const cachedReports = localStorage.getItem('expiryguard_cached_reports');
    const cachedDashSummary = localStorage.getItem('expiryguard_cached_dash_summary');
    if (cachedReports) {
      renderReportsUI(JSON.parse(cachedReports), cachedDashSummary ? JSON.parse(cachedDashSummary) : {});
    }
  } catch (e) {
    console.warn('Failed to parse cached reports:', e);
  }

  const loadReports = async () => {
    try {
      const [reports, dashSummary] = await Promise.all([
        api.getReportsSummary(),
        api.getDashboardSummary().catch(() => ({}))
      ]);
      localStorage.setItem('expiryguard_cached_reports', JSON.stringify(reports));
      localStorage.setItem('expiryguard_cached_dash_summary', JSON.stringify(dashSummary));
      renderReportsUI(reports, dashSummary);
    } catch (err) {
      console.error('Reports load error:', err);
      const topTbody = document.getElementById('top-selling-body');
      if (topTbody && !topTbody.innerHTML.trim()) {
        topTbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--status-danger); padding: 24px;">Failed to load sales reports: ${escapeHtml(err.message)}</td></tr>`;
      }
      const expTbody = document.getElementById('expiring-report-body');
      if (expTbody && !expTbody.innerHTML.trim()) {
        expTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--status-danger); padding: 24px;">Failed to load expiring stock: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  };

  loadReports();
}

