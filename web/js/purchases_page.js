/**
 * Purchase Management screen (purchases.html): purchase list + the three ways to add stock.
 * Read-only here: listing and opening a purchase never changes stock. Saving still goes through the existing
 * Add Inventory / OCR / import workflows (add_inventory_flow.js, documents.html).
 */
(function () {
  const PAGE_SIZE = 25;
  const state = { page: 1, total: 0, loading: false, seq: 0 };

  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => (n == null ? null : Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const na = '<span class="pm-na" title="Not recorded for this invoice">n/a</span>';

  function filters() {
    return {
      q: $('pm-f-q').value.trim(),
      supplier_id: $('pm-f-supplier').value,
      status: $('pm-f-status').value,
      date_from: $('pm-f-from').value,
      date_to: $('pm-f-to').value,
    };
  }

  function queryString(f, page) {
    const p = new URLSearchParams();
    Object.keys(f).forEach((k) => { if (f[k]) p.set(k, f[k]); });
    p.set('page', page);
    p.set('page_size', PAGE_SIZE);
    return p.toString();
  }

  function showState(kind, title, text, withRetry) {
    const box = $('pm-state');
    $('pm-table-wrap').style.display = 'none';
    $('pm-pager').style.display = 'none';
    box.style.display = 'block';
    box.innerHTML = `<strong>${esc(title)}</strong>${esc(text || '')}` +
      (withRetry ? '<div style="margin-top:10px"><button type="button" class="btn btn-primary btn-sm" onclick="pmReload()">Retry</button></div>' : '') +
      (kind === 'empty-filtered' ? '<div style="margin-top:10px"><button type="button" class="btn btn-secondary btn-sm" onclick="pmClearFilters()">Clear filters</button></div>' : '');
  }

  function renderSummary(s) {
    if (!s) { $('pm-summary').style.display = 'none'; return; }
    $('pm-summary').style.display = 'grid';
    $('pm-k-docs').textContent = s.documents;
    $('pm-k-value').textContent = '₹' + money(s.total_value);
    $('pm-k-pay').textContent = '₹' + money(s.outstanding_payables);
    $('pm-k-sup').textContent = s.suppliers_with_balance;
  }

  function renderRows(items) {
    $('pm-tbody').innerHTML = items.map((r) => {
      const st = r.payment_status ? `<span class="pm-badge ${esc(r.payment_status)}">${esc(r.payment_status)}</span>` : na;
      return `<tr>
        <td>${esc(r.voucher_no)}</td>
        <td>${esc(r.invoice_number)}</td>
        <td>${esc(r.supplier_name)}</td>
        <td>${esc(r.invoice_date || '')}</td>
        <td class="numeric">${r.items_count}</td>
        <td class="numeric">${money(r.total_amount)}</td>
        <td class="numeric">${r.paid_amount == null ? na : money(r.paid_amount)}</td>
        <td class="numeric">${r.outstanding_amount == null ? na : money(r.outstanding_amount)}</td>
        <td>${st}</td>
        <td><button type="button" class="btn btn-secondary btn-sm" onclick="pmOpenDetail(${r.id})">View</button></td>
      </tr>`;
    }).join('');
  }

  async function load() {
    const mySeq = ++state.seq;
    state.loading = true;
    showState('loading', 'Loading purchases…', '', false);
    const f = filters();
    try {
      const res = await api.request('/purchases/list?' + queryString(f, state.page));
      if (mySeq !== state.seq) return;
      state.total = res.total;
      renderSummary(res.summary);
      const hasFilter = Object.keys(f).some((k) => f[k]);
      if (!res.items.length) {
        if (state.page > 1 && res.total > 0) { state.page = Math.max(1, Math.ceil(res.total / PAGE_SIZE)); return load(); }
        showState(hasFilter ? 'empty-filtered' : 'empty',
          hasFilter ? 'No purchases match these filters' : 'No purchase documents yet',
          hasFilter ? '' : 'Use one of the three options above to add stock. Purchases saved with a supplier invoice will be listed here.', false);
        return;
      }
      $('pm-state').style.display = 'none';
      renderRows(res.items);
      $('pm-table-wrap').style.display = 'block';
      const from = (res.page - 1) * res.page_size + 1;
      const to = from + res.items.length - 1;
      $('pm-range').textContent = `Showing ${from}–${to} of ${res.total}`;
      $('pm-prev').disabled = res.page <= 1;
      $('pm-next').disabled = to >= res.total;
      $('pm-pager').style.display = 'flex';
    } catch (e) {
      if (mySeq !== state.seq) return;
      showState('error', 'Could not load purchases', (e && e.message ? e.message : 'Network error').slice(0, 200), true);
    } finally {
      if (mySeq === state.seq) state.loading = false;
    }
  }

  async function loadSuppliers() {
    try {
      const list = await api.request('/suppliers');
      const sel = $('pm-f-supplier');
      (Array.isArray(list) ? list : []).forEach((s) => {
        const o = document.createElement('option');
        o.value = s.id; o.textContent = s.name;
        sel.appendChild(o);
      });
    } catch (e) { /* filter stays "All suppliers" */ }
  }

  window.pmReload = load;
  window.pmApplyFilters = function (ev) {
    if (ev) ev.preventDefault();
    const f = filters();
    if (f.date_from && f.date_to && f.date_from > f.date_to) { showState('error', 'Check the dates', '“From” is after “To”.', false); return; }
    state.page = 1; load();
  };
  window.pmClearFilters = function () {
    ['pm-f-q', 'pm-f-supplier', 'pm-f-status', 'pm-f-from', 'pm-f-to'].forEach((id) => { $(id).value = ''; });
    state.page = 1; load();
  };
  window.pmGoto = function (dir) { state.page = Math.max(1, state.page + dir); load(); };

  // ---- the three actions: each opens an existing workflow
  window.pmScanBill = function () { window.location.href = 'documents.html'; };
  window.pmSearchMedicine = function () { openAddInventoryWorkflow('search'); };
  window.pmImportSheet = function () { openAddInventoryWorkflow('import'); };

  // ---- read-only detail
  window.pmCloseDetail = function () { $('pm-detail-modal').classList.remove('active'); };
  window.pmOpenDetail = async function (id) {
    $('pm-d-title').textContent = 'Purchase';
    $('pm-d-body').innerHTML = '<div class="pm-state">Loading…</div>';
    $('pm-detail-modal').classList.add('active');
    try {
      const d = await api.request('/purchases/detail/' + id);
      let bal = '';
      try {
        const led = await api.request('/suppliers/' + d.supplier_id + '/ledger');
        bal = `<div>Supplier balance payable: <strong>₹${money(led.balance_payable)}</strong> · <a href="suppliers.html">Open Suppliers</a></div>`;
      } catch (e) { /* balance is optional here */ }
      $('pm-d-title').textContent = `${d.voucher_no} · Invoice ${d.invoice_number}`;
      const rows = d.items.map((i) => `<tr><td>${esc(i.product_name || ('#' + i.product_id))}</td><td>${esc(i.batch_number)}</td>
        <td>${esc(i.expiry_date || '')}</td><td class="numeric">${i.quantity}</td><td class="numeric">${money(i.purchase_price)}</td>
        <td class="numeric">${money(i.mrp)}</td><td class="numeric">${i.gst_rate}%</td></tr>`).join('');
      $('pm-d-body').innerHTML = `
        <div style="display:flex;flex-wrap:wrap;gap:6px 24px;font-size:13px;margin-bottom:10px;">
          <div>Supplier: <strong>${esc(d.supplier_name)}</strong></div><div>Date: <strong>${esc(d.invoice_date || '')}</strong></div>
          <div>Status: <strong>${esc(d.payment_status || 'n/a')}</strong></div>
          <div>Total: <strong>₹${money(d.total_amount)}</strong> (GST ₹${money(d.tax_amount)})</div>${bal}
        </div>
        <div class="table-responsive"><table class="data-table"><thead><tr><th>Medicine</th><th>Batch</th><th>Expiry</th>
        <th class="numeric">Qty</th><th class="numeric">Rate</th><th class="numeric">MRP</th><th class="numeric">GST</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="7" class="pm-na">No lines</td></tr>'}</tbody></table></div>
        <p class="pm-note">Read-only. Posted purchases cannot be edited here because that would change stock already booked.</p>`;
    } catch (e) {
      $('pm-d-body').innerHTML = `<div class="pm-state"><strong>Could not load this purchase</strong>${esc((e && e.message || '').slice(0, 200))}</div>`;
    }
  };

  // keep unsaved Add Inventory work from being lost by leaving the page
  window.addEventListener('beforeunload', function (ev) {
    if (typeof inventoryCart !== 'undefined' && inventoryCart.length) { ev.preventDefault(); ev.returnValue = ''; }
  });

  document.addEventListener('DOMContentLoaded', function () {
    loadSuppliers();
    load();
    const action = new URLSearchParams(window.location.search).get('action');
    if (action === 'import' || action === 'search') {
      // wait for add_inventory_flow.js (defer) before opening the window
      window.addEventListener('load', function () { if (typeof openAddInventoryWorkflow === 'function') openAddInventoryWorkflow(action); });
    }
  });
})();
