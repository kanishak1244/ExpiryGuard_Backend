/* ==========================================================================
   RESTOCK SUGGESTIONS / WHAT TO BUY CONTROLLER
   Fetches and renders intelligent, demand-aware inventory reorder suggestions
   ========================================================================== */

let currentRestockData = [];
let currentFilter = 'all';
let currentSort = 'demand';
let currentSearch = '';
let currentMultiplier = 3.0;
let lastSummary = null;

async function loadRestockSuggestions() {
  const tableBody = document.getElementById('restock-table-body');
  const emptyState = document.getElementById('restock-empty-state');
  const table = document.getElementById('restock-table');

  try {
    if (!window.api || typeof window.api.getRestockSuggestions !== 'function') {
      throw new Error('API client is initializing... please click Retry.');
    }

    const res = await window.api.getRestockSuggestions(
      currentFilter,
      currentSort,
      currentSearch,
      currentMultiplier
    );

    if (!res || !res.success) {
      throw new Error(res?.message || 'Failed to calculate restock demand');
    }

    lastSummary = res.summary || null;
    currentRestockData = res.suggestions || [];
    renderRestockKPIs(res.summary);
    renderRestockTable(currentRestockData);
    updateExportCsvLink();
  } catch (err) {
    console.error('Failed to load restock suggestions:', err);
    if (table) table.style.display = 'none';
    if (emptyState) {
      emptyState.style.display = 'block';
      emptyState.innerHTML = `
        <div style="font-size: 40px; margin-bottom: 8px;">⚠️</div>
        <h3 style="font-size: 16px; font-weight: 700; color: var(--status-danger); margin-bottom: 6px;">Unable to Load Restock Suggestions</h3>
        <p style="color: var(--color-text-muted); font-size: 13.5px; max-width: 480px; margin: 0 auto 16px auto; line-height: 1.5;">
          ${escapeHtml(err.message || 'Connection or calculation issue occurred.')}
        </p>
        <button class="btn btn-primary" onclick="loadRestockSuggestions()" style="display: inline-flex; align-items: center; gap: 6px;">
          <span>🔄 Retry Calculation</span>
        </button>
      `;
    }
  }
}

function resetRestockFilters() {
  currentFilter = 'all';
  currentSearch = '';
  currentSort = 'demand';
  const searchInput = document.getElementById('restock-search-input');
  if (searchInput) searchInput.value = '';
  const sortSelect = document.getElementById('restock-sort-select');
  if (sortSelect) sortSelect.value = 'demand';
  const filterBtns = document.querySelectorAll('.filter-bar .filter-btn');
  filterBtns.forEach(b => {
    if (b.getAttribute('data-filter') === 'all') b.classList.add('active');
    else b.classList.remove('active');
  });
  loadRestockSuggestions();
}

function renderRestockKPIs(summary) {
  if (!summary) return;

  const kpiTotal = document.getElementById('kpi-total-suggestions');
  const kpiOos = document.getElementById('kpi-out-of-stock');
  const kpiExp = document.getElementById('kpi-expired-stock');
  const kpiLow = document.getElementById('kpi-low-stock');
  const kpiCost = document.getElementById('kpi-reorder-cost');
  const kpiUnits = document.getElementById('kpi-reorder-units');

  if (kpiTotal) kpiTotal.textContent = summary.total_suggestions;
  if (kpiOos) kpiOos.textContent = summary.out_of_stock_count;
  if (kpiExp) kpiExp.textContent = summary.expired_count;
  if (kpiLow) kpiLow.textContent = summary.low_stock_count;
  if (kpiCost) kpiCost.textContent = `₹${Number(summary.estimated_reorder_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  if (kpiUnits) kpiUnits.textContent = `${summary.total_reorder_units || 0} suggested packs total`;

  // Update tab counts
  const cAll = document.getElementById('count-all');
  const cOos = document.getElementById('count-out-of-stock');
  const cExp = document.getElementById('count-expired');
  const cLow = document.getElementById('count-low-stock');

  if (cAll) cAll.textContent = summary.total_suggestions;
  if (cOos) cOos.textContent = summary.out_of_stock_count;
  if (cExp) cExp.textContent = summary.expired_count;
  if (cLow) cLow.textContent = summary.low_stock_count;
}

function renderRestockTable(items) {
  const tableBody = document.getElementById('restock-table-body');
  const emptyState = document.getElementById('restock-empty-state');
  const table = document.getElementById('restock-table');

  if (!tableBody) return;

  if (!items || items.length === 0) {
    tableBody.innerHTML = '';
    if (table) table.style.display = 'none';
    if (emptyState) {
      emptyState.style.display = 'block';
      if (lastSummary && lastSummary.has_sales_history === false && (lastSummary.total_products_evaluated || 0) > 0) {
        emptyState.innerHTML = `
          <div style="font-size: 40px; margin-bottom: 8px;">📊</div>
          <h3 style="font-size: 16px; font-weight: 700; color: var(--color-text-primary); margin-bottom: 4px;">Building Sales Velocity Insights</h3>
          <p style="color: var(--color-text-muted); font-size: 13.5px; max-width: 480px; margin: 0 auto; line-height: 1.5;">
            Evaluated ${lastSummary.total_products_evaluated} inventory items. Demand-aware restock recommendations will calculate and rank medicines automatically as counter bills are recorded.
          </p>
          <a href="billing.html" class="btn btn-primary" style="margin-top: 14px; display: inline-flex; align-items: center; gap: 6px; text-decoration: none;">
            <span>+ Create New Bill</span>
          </a>
        `;
      } else if (currentSearch || currentFilter !== 'all') {
        emptyState.innerHTML = `
          <div style="font-size: 40px; margin-bottom: 8px;">🔍</div>
          <h3 style="font-size: 16px; font-weight: 700; color: var(--color-text-primary); margin-bottom: 4px;">No Matching Restock Items</h3>
          <p style="color: var(--color-text-muted); font-size: 13.5px; max-width: 440px; margin: 0 auto;">
            No medicines found matching the active filter or search query.
          </p>
          <button class="btn btn-secondary" style="margin-top: 12px;" onclick="resetRestockFilters()">Clear Filters</button>
        `;
      } else {
        emptyState.innerHTML = `
          <div style="font-size: 40px; margin-bottom: 8px;">✅</div>
          <h3 style="font-size: 16px; font-weight: 700; color: var(--color-text-primary); margin-bottom: 4px;">All Medicines Are Well Stocked</h3>
          <p style="color: var(--color-text-muted); font-size: 13.5px; max-width: 440px; margin: 0 auto;">
            No medicines currently meet the out-of-stock, expired, or demand replenishment threshold.
          </p>
        `;
      }
    }
    return;
  }

  if (table) table.style.display = 'table';
  if (emptyState) emptyState.style.display = 'none';

  let html = '';
  items.forEach(item => {
    // Reason badge styling
    let reasonBadge = '';
    if (item.reason === 'OUT_OF_STOCK') {
      reasonBadge = `<span class="badge-oos">🚨 Out of Stock</span>`;
    } else if (item.reason === 'EXPIRED') {
      reasonBadge = `<span class="badge-exp">⚠️ Expired Stock</span>`;
    } else {
      reasonBadge = `<span class="badge-low">📉 Low Stock</span>`;
    }

    // Days badge styling
    let daysBadge = '';
    if (item.sellable_stock === 0) {
      daysBadge = `<span class="days-tag critical">Stockout</span>`;
    } else if (item.days_of_stock_remaining !== null && item.days_of_stock_remaining !== undefined) {
      const d = item.days_of_stock_remaining;
      const dClass = d <= 3 ? 'critical' : (d <= 7 ? 'warning' : 'normal');
      daysBadge = `<span class="days-tag ${dClass}">~${d}d left</span>`;
    } else {
      daysBadge = `<span class="days-tag normal">No 30d sales</span>`;
    }

    const brandDisplay = item.brand ? `<span style="color: var(--color-text-muted); font-size: 12.5px; font-weight: 500;">• ${escapeHtml(item.brand)}</span>` : '';
    const compDisplay = item.composition ? `<div style="font-size: 12px; color: var(--color-text-muted); margin-top: 2px;">${escapeHtml(item.composition)}</div>` : '';
    const packDisplay = item.pack_size_label ? `<span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px; margin-top: 4px; display: inline-block;">${escapeHtml(item.pack_size_label)}</span>` : '';

    html += `
      <tr>
        <td>
          <div style="font-weight: 700; color: var(--color-text-primary); font-size: 14px;">
            ${escapeHtml(item.product_name)} ${brandDisplay}
          </div>
          ${compDisplay}
          ${packDisplay}
        </td>

        <td>
          ${reasonBadge}
          <div style="font-size: 11.5px; color: var(--color-text-muted); margin-top: 4px;">Urgency: <strong style="color: var(--color-text-primary);">${escapeHtml(item.urgency_level || 'Normal')}</strong></div>
        </td>

        <td>
          <div style="font-size: 13.5px; font-weight: 700; color: ${item.sellable_stock === 0 ? 'var(--status-danger)' : 'var(--color-text-primary)'}; font-family: var(--font-mono);">
            ${item.sellable_stock} <span style="font-size: 12px; font-weight: 500; color: var(--color-text-muted); font-family: var(--font-ui);">sellable packs</span>
          </div>
          ${item.expired_stock > 0 ? `<div style="font-size: 11.5px; color: var(--status-warning); font-weight: 600;">+${item.expired_stock} expired packs</div>` : ''}
          <div style="margin-top: 4px;">${daysBadge}</div>
        </td>

        <td>
          <div style="font-size: 13px; font-weight: 700; color: var(--color-text-primary); font-family: var(--font-mono);">
            ${item.sales_30d} packs <span style="font-weight: 400; color: var(--color-text-muted); font-family: var(--font-ui); font-size: 12px;">(30d)</span>
          </div>
          <div style="font-size: 12px; color: #475569; margin-top: 2px;">~${item.avg_weekly_sales} packs / week</div>
          <div style="font-size: 11.5px; color: var(--color-text-muted);">${item.bill_count_30d} customer orders</div>
        </td>

        <td>
          <div class="reorder-badge">
            <span>📦</span>
            <span>+${item.suggested_reorder_qty} Packs</span>
          </div>
          <div style="font-size: 12px; color: var(--color-text-muted); margin-top: 4px;">
            Est. Cost: <strong style="color: var(--color-text-primary); font-family: var(--font-mono);">₹${Number(item.estimated_reorder_cost || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
          </div>
        </td>

        <td style="text-align: right;" class="actions-col">
          <button class="btn btn-primary" style="padding: 6px 14px; font-size: 12.5px; font-weight: 600;" onclick="triggerRestockItem('${escapeJs(item.product_name)}', '${escapeJs(item.brand || '')}', ${item.suggested_reorder_qty}, ${item.unit_price || 0})">
            + Restock
          </button>
        </td>
      </tr>
    `;
  });

  tableBody.innerHTML = html;
}

function updateExportCsvLink() {
  const exportBtn = document.getElementById('restock-export-csv-btn');
  if (exportBtn) {
    const params = new URLSearchParams({
      reason_filter: currentFilter,
      sort_by: currentSort,
      search: currentSearch,
      multiplier: currentMultiplier
    });
    exportBtn.href = `/inventory/restock-suggestions/export-csv?${params.toString()}`;
  }
}

function triggerRestockItem(productName, brand, suggestedQty, mrp) {
  if (typeof window.openAddInventoryForMedicine === 'function') {
    window.openAddInventoryForMedicine(productName, brand, suggestedQty, mrp);
  } else if (typeof window.openAddInventoryModal === 'function') {
    window.openAddInventoryModal();
  } else {
    window.location.href = `inventory.html?prefill=${encodeURIComponent(productName)}&qty=${suggestedQty}`;
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeJs(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/'/g, "\'").replace(/"/g, '\"');
}

// Event Listeners Setup
function initRestockPage() {
  // 1. Filter tabs
  const filterBtns = document.querySelectorAll('.filter-bar .filter-btn');
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.getAttribute('data-filter') || 'all';
      loadRestockSuggestions();
    });
  });

  // 2. Search input with debounce
  const searchInput = document.getElementById('restock-search-input');
  let searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        currentSearch = e.target.value.trim();
        loadRestockSuggestions();
      }, 250);
    });
  }

  // 3. Sort selector
  const sortSelect = document.getElementById('restock-sort-select');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      currentSort = e.target.value;
      loadRestockSuggestions();
    });
  }

  // 4. Multiplier selector
  const multSelect = document.getElementById('restock-multiplier-select');
  if (multSelect) {
    multSelect.addEventListener('change', (e) => {
      currentMultiplier = parseFloat(e.target.value) || 3.0;
      loadRestockSuggestions();
    });
  }

  // Initial load
  loadRestockSuggestions();

  // 10-second polling for live inventory updates
  if (window.api && typeof window.api.startPolling === 'function') {
    window.api.startPolling(loadRestockSuggestions, 10000);
  }
}

// Expose globally
window.initRestockPage = initRestockPage;
window.loadRestockSuggestions = loadRestockSuggestions;

// Immediate execution if DOM is ready, otherwise on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initRestockPage);
} else {
  initRestockPage();
}
