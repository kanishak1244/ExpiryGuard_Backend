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
    $('pm-summary').style.display = 'grid'; $('pm-summary').dataset.ready = '1';
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
      if (res.summary && res.summary.draft_count != null) setDraftCount(res.summary.draft_count);
      const hasFilter = Object.keys(f).some((k) => f[k]);
      if (!res.items.length) {
        if (state.page > 1 && res.total > 0) { state.page = Math.max(1, Math.ceil(res.total / PAGE_SIZE)); return load(); }
        showState(hasFilter ? 'empty-filtered' : 'empty',
          hasFilter ? 'No purchases match these filters' : 'No purchase documents yet',
          hasFilter ? '' : 'Use one of the options above to add stock. Purchases saved with a supplier invoice will be listed here.', false);
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
  window.pmAddManually = function () { window.location.href = 'purchase_entry.html'; };

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

  // ---------------------------------------------------------------- drafts tab (server-saved drafts)
  const D = { page: 1, seq: 0 };
  const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '');

  function setDraftCount(n) { $('pm-draft-count').textContent = n; }
  async function loadDraftCount() {
    try { setDraftCount((await api.request('/purchases/drafts?page_size=1')).draft_count); } catch (e) { /* the tab still works without the badge */ }
  }

  window.pmTab = function (which) {
    const drafts = which === 'drafts';
    $('pm-tab-all').classList.toggle('active', !drafts);
    $('pm-tab-drafts').classList.toggle('active', drafts);
    $('pm-all-view').style.display = drafts ? 'none' : '';
    $('pm-drafts-view').style.display = drafts ? '' : 'none';
    $('pm-summary').style.display = drafts ? 'none' : ($('pm-summary').dataset.ready ? 'grid' : 'none');
    if (drafts) loadDrafts(); else loadDraftCount();
  };

  function dState(title, text, retry) {
    $('pd-table-wrap').style.display = 'none'; $('pd-pager').style.display = 'none';
    const b = $('pd-state'); b.style.display = 'block';
    b.innerHTML = `<strong>${esc(title)}</strong>${esc(text || '')}` + (retry ? '<div style="margin-top:10px"><button type="button" class="btn btn-primary btn-sm" onclick="pdReload()">Retry</button></div>' : '')
      + (title === 'No drafts match these filters' ? '<div style="margin-top:10px"><button type="button" class="btn btn-secondary btn-sm" onclick="pdClear()">Clear filters</button></div>' : '');
  }

  async function loadDrafts() {
    const my = ++D.seq;
    dState('Loading drafts…', '', false);
    const p = new URLSearchParams({ page: D.page, page_size: PAGE_SIZE, status: $('pd-status').value });
    if ($('pd-q').value.trim()) p.set('q', $('pd-q').value.trim());
    if ($('pd-from').value) p.set('date_from', $('pd-from').value);
    if ($('pd-to').value) p.set('date_to', $('pd-to').value);
    try {
      const res = await api.request('/purchases/drafts?' + p.toString());
      if (my !== D.seq) return;
      setDraftCount(res.draft_count);
      if (!res.items.length) {
        if (D.page > 1 && res.total > 0) { D.page = Math.max(1, Math.ceil(res.total / PAGE_SIZE)); return loadDrafts(); }
        const filtered = $('pd-q').value || $('pd-from').value || $('pd-to').value || $('pd-status').value !== 'DRAFT';
        dState(filtered ? 'No drafts match these filters' : 'No drafts yet', filtered ? '' : 'Use Save as Draft in Add Manually or in an invoice review to keep unfinished purchases here.', false);
        return;
      }
      $('pd-state').style.display = 'none';
      $('pd-tbody').innerHTML = res.items.map(function (d) {
        const open = d.status === 'DRAFT';
        const href = d.source === 'OCR' && d.document_id ? 'documents.html?review=' + d.document_id : 'purchase_entry.html?draft=' + d.id;
        const actions = open
          ? `<a class="btn btn-primary btn-sm" style="text-decoration:none" href="${href}">Continue editing</a> <button type="button" class="btn btn-secondary btn-sm" onclick="pdDelete(${d.id}, '${esc(d.reference)}')">Delete</button>`
          : (d.purchase_invoice_id ? `<a class="btn btn-secondary btn-sm" style="text-decoration:none" href="purchases.html?view=${d.purchase_invoice_id}">View purchase</a>` : '');
        return `<tr>
          <td>${esc(d.reference)}</td>
          <td>${d.supplier_name ? esc(d.supplier_name) : '<span class="pm-na">Supplier not selected</span>'}</td>
          <td>${d.invoice_number ? esc(d.invoice_number) : '<span class="pm-na">—</span>'}</td>
          <td>${esc(fmtDate(d.created_at))}</td><td>${esc(fmtDate(d.updated_at))}</td>
          <td class="numeric">${d.line_count}</td>
          <td class="numeric">${d.estimated_total == null ? '<span class="pm-na" title="Not enough numbers entered yet">—</span>' : money(d.estimated_total) + ' <small class="pm-na">est.</small>'}</td>
          <td>${d.source === 'OCR' ? 'OCR bill' : 'Manual'}</td>
          <td><span class="pm-badge ${open ? 'PARTIAL' : 'PAID'}">${open ? 'Draft' : 'Posted'}</span></td>
          <td>${actions}</td></tr>`;
      }).join('');
      $('pd-table-wrap').style.display = 'block';
      const from = (res.page - 1) * res.page_size + 1, to = from + res.items.length - 1;
      $('pd-range').textContent = `Showing ${from}–${to} of ${res.total}`;
      $('pd-prev').disabled = res.page <= 1; $('pd-next').disabled = to >= res.total;
      $('pd-pager').style.display = 'flex';
    } catch (e) {
      if (my !== D.seq) return;
      dState('Could not load drafts', (e && e.message ? e.message : 'Network error').slice(0, 200), true);
    }
  }

  window.pdReload = loadDrafts;
  window.pdApply = function (ev) { if (ev) ev.preventDefault(); D.page = 1; loadDrafts(); };
  window.pdClear = function () { ['pd-q', 'pd-from', 'pd-to'].forEach(function (id) { $(id).value = ''; }); $('pd-status').value = 'DRAFT'; D.page = 1; loadDrafts(); };
  window.pdGoto = function (d) { D.page = Math.max(1, D.page + d); loadDrafts(); };
  window.pdDelete = async function (id, ref) {
    if (!window.confirm('Delete ' + ref + '? Only the draft is removed. A scanned bill stays in Documents, and nothing in stock changes.')) return;
    try { await api.request('/purchases/drafts/' + id, { method: 'DELETE' }); loadDrafts(); }
    catch (e) { dState('Could not delete the draft', (e && e.message ? e.message : '').slice(0, 200), true); }
  };

  // keep unsaved Add Inventory work from being lost by leaving the page
  window.addEventListener('beforeunload', function (ev) {
    if (typeof inventoryCart !== 'undefined' && inventoryCart.length) { ev.preventDefault(); ev.returnValue = ''; }
  });

  document.addEventListener('DOMContentLoaded', function () {
    loadSuppliers();
    load();
    const view = parseInt(new URLSearchParams(window.location.search).get('view'), 10);
    if (view > 0) window.pmOpenDetail(view);
    if (new URLSearchParams(window.location.search).get('tab') === 'drafts') pmTab('drafts');
    else loadDraftCount();
    const action = new URLSearchParams(window.location.search).get('action');
    if (action === 'import' || action === 'search') {
      // wait for add_inventory_flow.js (defer) before opening the window
      window.addEventListener('load', function () { if (typeof openAddInventoryWorkflow === 'function') openAddInventoryWorkflow(action); });
    }
  });
})();
