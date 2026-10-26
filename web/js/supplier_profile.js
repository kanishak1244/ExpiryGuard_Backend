/**
 * Supplier & Vendor Management: the supplier profile, its purchase history, the purchase bill viewer and the
 * linked-medicine stock table.
 *   - A profile is always loaded from the server by the supplier's id (never read from the list that happens to be on screen).
 *   - Every request carries a ticket; an answer for a profile the user already left is dropped, so no stale data appears.
 *   - Opening a bill / a profile only reads. Stock, balances and the ledger are never touched from here.
 * Pure render helpers are exported for Node tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => (n == null || n === '' || isNaN(n) ? null : Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const rs = (n) => (money(n) == null ? '—' : '₹' + money(n));
  const NA = (why) => `<span class="sp-na"${why ? ` title="${esc(why)}"` : ''}>—</span>`;

  // ------------------------------------------------------------------ gates
  // "Latest request wins": next() hands out a ticket; only the newest ticket is current.
  function spMakeGate() {
    let latest = 0;
    return { next: () => ++latest, isCurrent: (t) => t === latest, bump: () => ++latest };
  }

  // ------------------------------------------------------------------ render helpers
  const STATUS_CLASS = { 'In Stock': 'ok', 'Partially Sold': 'info', 'Sold Out': 'muted', 'Expired': 'bad', 'Returned': 'purple', 'Unavailable': 'warn' };

  function spStockBadge(status, note) {
    return `<span class="sp-badge ${STATUS_CLASS[status] || 'muted'}"${note ? ` title="${esc(note)}"` : ''}>${esc(status)}</span>`;
  }

  function spPaymentBadge(status) {
    const s = String(status || '').toUpperCase();
    if (!s) return NA('Not recorded');
    const cls = { PAID: 'ok', UNPAID: 'bad', PARTIAL: 'warn' }[s] || 'muted';
    return `<span class="sp-badge ${cls}">${esc(s.charAt(0) + s.slice(1).toLowerCase())}</span>`;
  }

  function spStockTableHtml(items) {
    if (!items || !items.length) {
      return '<div class="sp-empty">No medicine stock is linked to this supplier.</div>';
    }
    const cell = (v, why) => (v == null ? NA(why) : esc(v));
    const head = `<tr><th>Medicine</th><th>Batch</th><th>Invoice</th><th>Purchased</th><th>Expiry</th>
      <th class="num" title="Includes free units">Received</th><th class="num">Sold</th><th class="num">Returned</th><th class="num">Available</th>
      <th>Stock Status</th><th class="num">MRP</th></tr>`;
    const rows = items.map(r => {
      const unattrib = 'Not shown: sales are not recorded per supplier, and this batch is shared or its stock movements do not add up.';
      return `<tr class="sp-row" data-stock-id="${r.product_id}" tabindex="0" title="Click for details">
        <td><b>${esc(r.product_name)}</b>${r.company ? `<small>${esc(r.company)}</small>` : ''}</td>
        <td>${cell(r.batch_number)}${r.shared_batch ? ' <span class="sp-tag" title="Other suppliers also delivered into this batch">shared</span>' : ''}</td>
        <td>${r.purchase_id ? `<a href="javascript:void(0)" data-open-purchase="${r.purchase_id}">${esc(r.invoice_number || 'Purchase')}</a>` : NA('No purchase record for this stock')}</td>
        <td>${cell(r.purchase_date)}</td>
        <td>${cell(r.expiry_date)}</td>
        <td class="num">${r.quantity_received == null ? NA('No purchase record for this stock') : r.quantity_received}</td>
        <td class="num">${r.quantity_sold == null ? NA(unattrib) : r.quantity_sold}</td>
        <td class="num">${r.quantity_returned == null ? NA(unattrib) : r.quantity_returned}</td>
        <td class="num"><b>${r.available}</b></td>
        <td>${spStockBadge(r.status, r.status_note)}</td>
        <td class="num">${r.mrp == null ? NA() : money(r.mrp)}</td></tr>
        <tr class="sp-detail" data-detail-for="${r.product_id}" style="display:none"><td colspan="11">${spStockDetailHtml(r)}</td></tr>`;
    }).join('');
    return `<table class="sp-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
  }

  function spStockDetailHtml(r) {
    const parts = [
      `Batch stock on hand: <b>${r.available}</b>`,
      r.quantity_received != null ? `received from this supplier: <b>${r.quantity_received}</b>` : 'no purchase record for this stock',
      r.batch_received_total != null && r.shared_batch ? `received into this batch from all suppliers: <b>${r.batch_received_total}</b>` : '',
      r.quantity_sold != null ? `sold: <b>${r.quantity_sold}</b>` : '',
      r.quantity_returned ? `returned to supplier: <b>${r.quantity_returned}</b>` : '',
    ].filter(Boolean).join(' · ');
    return `<div class="sp-detail-box">${parts}.<br>${r.status_note ? esc(r.status_note) + '<br>' : ''}
      <small>Movements ${r.reconciled ? 'add up to the quantity on hand' : 'do not fully add up (or are not recorded), so sold and returned quantities are not claimed'}.</small></div>`;
  }

  function spHistoryHtml(items) {
    if (!items || !items.length) return '<div class="sp-empty">No purchase documents recorded for this supplier yet.</div>';
    const rows = items.map(p => `<tr class="sp-row" data-purchase-id="${p.id}" tabindex="0">
      <td>${esc(p.voucher_no)}</td><td><b>${esc(p.invoice_number)}</b></td><td>${p.invoice_date ? esc(p.invoice_date) : NA()}</td>
      <td class="num">${p.items_count}</td><td class="num">${rs(p.total_amount)}</td><td>${spPaymentBadge(p.payment_status)}</td>
      <td><button type="button" class="btn btn-secondary btn-sm" data-open-purchase="${p.id}">View</button></td></tr>`).join('');
    return `<table class="sp-table"><thead><tr><th>Purchase no.</th><th>Supplier invoice</th><th>Date</th><th class="num">Items</th>
      <th class="num">Amount</th><th>Payment</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function spLedgerHtml(entries) {
    if (!entries || !entries.length) return '<div class="sp-empty">No ledger entries.</div>';
    const rows = entries.map(e => `<tr><td>${e.date ? esc(String(e.date).slice(0, 10)) : NA()}</td><td>${esc(e.type.charAt(0) + e.type.slice(1).toLowerCase())}</td>
      <td>${e.ref == null || e.ref === '' ? NA() : esc(e.ref)}</td><td class="num">${e.credit ? money(e.credit) : NA()}</td><td class="num">${e.debit ? money(e.debit) : NA()}</td>
      <td class="num"><b>${money(e.balance)}</b></td></tr>`).join('');
    return `<table class="sp-table"><thead><tr><th>Date</th><th>Type</th><th>Reference</th><th class="num" title="Adds to what you owe">Purchase (Cr)</th>
      <th class="num" title="Reduces what you owe">Paid / returned (Dr)</th><th class="num">Balance owed</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function spBillHtml(d) {
    const hasPay = d.paid_amount != null;
    const head = (label, value) => `<div class="sp-f"><span>${label}</span><b>${value}</b></div>`;
    const lines = (d.items || []).map((l, i) => `<tr><td class="n">${i + 1}</td>
      <td><b>${l.product_name ? esc(l.product_name) : NA('Medicine record not available')}</b>${l.company ? `<small>${esc(l.company)}</small>` : ''}</td>
      <td>${l.batch_number ? esc(l.batch_number) : NA()}</td><td>${l.expiry_date ? esc(l.expiry_date) : NA()}</td>
      <td class="num">${l.quantity == null ? NA() : l.quantity}</td><td class="num">${money(l.purchase_price) == null ? NA() : money(l.purchase_price)}</td>
      <td class="num">${money(l.mrp) == null ? NA() : money(l.mrp)}</td><td class="num">${l.gst_rate == null ? NA() : l.gst_rate + '%'}</td>
      <td class="num">${money(l.taxable) == null ? NA() : money(l.taxable)}</td><td class="num"><b>${money(l.line_total) == null ? NA() : money(l.line_total)}</b></td></tr>`).join('');
    const t = d.totals || {};
    return `<div class="sp-bill-head">
        ${head('Supplier', esc(d.supplier_name || '—'))}${head('Supplier invoice no.', esc(d.invoice_number))}${head('Purchase voucher no.', esc(d.voucher_no))}
        ${head('Invoice date', d.invoice_date ? esc(d.invoice_date) : '—')}${head('Entered on', d.entered_on ? esc(String(d.entered_on).slice(0, 10)) : '—')}
        ${head('Purchase status', `<span class="sp-badge ok">${esc(d.purchase_status || 'Posted')}</span>`)}
        ${head('Payment status', spPaymentBadge(d.payment_status))}
        ${head('Outstanding on this bill', hasPay ? rs(d.outstanding_amount) : NA('Not certain for a part-paid bill'))}
      </div>
      <div class="sp-bill-lines">${lines ? `<table class="sp-table"><thead><tr><th class="n">#</th><th>Medicine</th><th>Batch</th><th>Expiry</th><th class="num" title="Includes free units">Qty</th>
        <th class="num" title="Net cost per unit">Rate</th><th class="num">MRP</th><th class="num">GST</th><th class="num">Taxable</th><th class="num">Line total</th></tr></thead><tbody>${lines}</tbody></table>`
        : '<div class="sp-empty">This purchase has no medicine lines on record.</div>'}</div>
      <div class="sp-totals">
        <div><span>Subtotal (taxable)</span><b>${rs(t.subtotal)}</b></div>
        <div><span>Discount</span><b>${NA('Discounts are already included in the rate (not stored separately)')}</b></div>
        <div><span>GST</span><b>${rs(d.tax_amount)}</b></div>
        <div class="big"><span>Invoice total</span><b>${rs(d.total_amount)}</b></div>
        ${t.matches_stored_total === false ? `<div class="sp-warn">Lines add up to ${rs(t.calculated_total)}; the saved invoice total differs (older purchase).</div>` : ''}
      </div>`;
  }

  const exported = { spMakeGate, spStockBadge, spPaymentBadge, spStockTableHtml, spStockDetailHtml, spHistoryHtml, spLedgerHtml, spBillHtml };
  if (typeof document === 'undefined') return exported;

  // ------------------------------------------------------------------ browser part
  const $ = (id) => document.getElementById(id);
  const gate = spMakeGate();
  const P = { id: null, profile: null, tab: 'overview', loaded: {}, hist: 1, led: 1, ledType: '', stk: 1, stkStatus: '', stkQ: '', pushed: false, loading: false, bill: null };
  const PAGE = 20;

  function apiMsg(e) {
    const t = String((e && e.message) || e || '');
    const j = t.indexOf('{');
    if (j >= 0) { try { const d = JSON.parse(t.slice(j)).detail; if (typeof d === 'string') return d; } catch (_) { /* below */ } }
    return t.slice(0, 240);
  }
  const statusOf = (e) => { const m = /API Error \((\d+)\)/.exec(String((e && e.message) || '')); return m ? +m[1] : 0; };

  function showState(kind, title, text, retry) {
    const box = $('sp-state');
    box.style.display = 'block';
    box.className = 'sp-state ' + kind;
    box.innerHTML = `<b>${esc(title)}</b>${text ? '<div>' + esc(text) + '</div>' : ''}` + (retry ? '<div style="margin-top:8px"><button type="button" class="btn btn-primary btn-sm" onclick="spRetry()">Retry</button></div>' : '');
    $('sp-body').style.display = 'none';
  }

  function paintProfile(p) {
    $('prof-modal-name').textContent = p.name;
    $('prof-modal-gstin').textContent = 'GSTIN: ' + (p.gstin || 'N/A');
    $('prof-metric-total').textContent = rs(p.total_purchased);
    $('prof-metric-count').textContent = p.purchase_count;
    $('prof-metric-date').textContent = p.last_purchase_date || 'N/A';
    $('prof-metric-paid').textContent = rs(p.total_paid);
    $('prof-metric-returned').textContent = rs(p.total_returned);
    $('prof-metric-balance').textContent = rs(p.balance_payable);
    const set = (id, v, d) => { $(id).textContent = v == null || v === '' ? (d || 'N/A') : v; };
    set('prof-info-contact', p.contact_person); set('prof-info-phone', p.phone); set('prof-info-email', p.email);
    set('prof-info-state', p.state); set('prof-info-terms', p.payment_terms); set('prof-info-status', p.status); set('prof-info-address', p.address);
    $('sp-state').style.display = 'none';
    $('sp-body').style.display = 'block';
  }

  window.openSupplierProfile = async function (rawId, opts) {
    const id = parseInt(rawId, 10);
    if (!id || id < 1) return;
    opts = opts || {};
    if (P.loading && P.id === id && !opts.force) return;                 // a second click on the same row: the request is already running
    P.id = id; P.profile = null; P.loaded = {}; P.hist = 1; P.led = 1; P.stk = 1; P.tab = 'overview';
    const my = gate.next();
    P.loading = true;
    $('prof-modal-name').textContent = 'Loading supplier…';
    $('prof-modal-gstin').textContent = '';
    showState('loading', 'Loading supplier profile…', '', false);
    $('supplier-profile-modal').classList.add('active');
    if (!opts.fromPop) {
      try {
        if (!P.pushed) { history.pushState({ supplierProfile: id }, '', '#supplier=' + id); P.pushed = true; }
        else history.replaceState({ supplierProfile: id }, '', '#supplier=' + id);   // switching suppliers: the address always names the one on screen
      } catch (e) { /* history is optional */ }
    }
    try {
      const p = await api.request('/suppliers/' + id + '/profile');
      if (!gate.isCurrent(my)) return;                                    // the user moved on: this answer is stale
      P.profile = p;
      paintProfile(p);
      switchSupplierTab('overview');
    } catch (e) {
      if (!gate.isCurrent(my)) return;
      const code = statusOf(e);
      $('prof-modal-name').textContent = 'Supplier profile';
      if (code === 404) { showState('bad', 'This supplier is no longer available', 'It may have been deleted, or it does not belong to this pharmacy.', false); if (typeof loadSuppliers === 'function') loadSuppliers(); }
      else if (code === 401 || code === 403) showState('bad', 'You do not have access to this supplier', apiMsg(e), false);
      else showState('bad', 'Could not load the supplier profile', apiMsg(e) || 'Network error', true);
    } finally {
      if (gate.isCurrent(my)) P.loading = false;
    }
  };

  window.spRetry = function () { if (P.id) window.openSupplierProfile(P.id, { force: true, fromPop: true }); };

  window.closeProfileModal = function () {
    if (P.pushed) { P.pushed = false; try { history.back(); return; } catch (e) { /* fall through */ } }
    hideProfile();
  };

  function hideProfile() {
    gate.bump();                                                          // in-flight answers for this profile are dropped
    P.loading = false; P.id = null;
    $('supplier-profile-modal').classList.remove('active');
    closeBill();
  }

  window.addEventListener('popstate', function (ev) {
    const sid = ev.state && ev.state.supplierProfile;
    const typed = /^#supplier=(\d+)$/.exec(window.location.hash || '');          // the address was edited by hand / followed as a link
    if (sid || typed) { P.pushed = true; window.openSupplierProfile(sid || typed[1], { fromPop: true }); }
    else { P.pushed = false; hideProfile(); }
  });

  window.switchSupplierTab = function (tab) {
    P.tab = tab;
    document.querySelectorAll('.supplier-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.tab-content-panel').forEach(p => p.classList.toggle('active', p.id === 'sup-tab-' + tab));
    if (!P.id || !P.profile || P.loaded[tab]) return;
    if (tab === 'purchases') loadHistory();
    else if (tab === 'ledger') loadLedger();
    else if (tab === 'medicines') loadStock();
  };

  function pane(id, html) { $(id).innerHTML = html; }
  function paneError(id, e, again) {
    $(id).innerHTML = `<div class="sp-state bad"><b>Could not load this section</b><div>${esc(apiMsg(e))}</div><div style="margin-top:8px"><button type="button" class="btn btn-primary btn-sm" onclick="${again}()">Retry</button></div></div>`;
  }
  function pager(id, total, page, fn) {
    const last = Math.max(1, Math.ceil(total / PAGE));
    $(id).innerHTML = total > PAGE ? `<span>Page ${page} of ${last} · ${total} rows</span><span><button type="button" class="btn btn-secondary btn-sm" ${page <= 1 ? 'disabled' : ''} onclick="${fn}(${page - 1})">‹ Previous</button>
      <button type="button" class="btn btn-secondary btn-sm" ${page >= last ? 'disabled' : ''} onclick="${fn}(${page + 1})">Next ›</button></span>` : (total ? `<span>${total} row${total === 1 ? '' : 's'}</span>` : '');
  }

  window.loadHistory = async function (page) {
    if (page) P.hist = page;
    pane('sp-history', '<div class="sp-empty">Loading purchases…</div>');
    const sid = P.id, prof = P.profile;
    try {
      const res = await api.request(`/purchases/list?supplier_id=${sid}&page=${P.hist}&page_size=${PAGE}`);
      if (P.id !== sid || P.profile !== prof) return;
      P.loaded.purchases = true;
      pane('sp-history', spHistoryHtml(res.items));
      pager('sp-history-pager', res.total, res.page, 'loadHistory');
    } catch (e) { if (P.id === sid && P.profile === prof) paneError('sp-history', e, 'loadHistory'); }
  };

  window.loadLedger = async function (page) {
    if (page) P.led = page;
    pane('sp-ledger', '<div class="sp-empty">Loading ledger…</div>');
    const sid = P.id, prof = P.profile;
    try {
      const res = await api.request(`/suppliers/${sid}/ledger?page=${P.led}&page_size=${PAGE}&newest_first=true${P.ledType ? '&type=' + P.ledType : ''}`);
      if (P.id !== sid || P.profile !== prof) return;
      P.loaded.ledger = true;
      pane('sp-ledger', spLedgerHtml(res.entries));
      pager('sp-ledger-pager', res.entries_total, res.page, 'loadLedger');
    } catch (e) { if (P.id === sid && P.profile === prof) paneError('sp-ledger', e, 'loadLedger'); }
  };
  window.spLedgerType = function (t) { P.ledType = t; P.led = 1; loadLedger(); };

  window.loadStock = async function (page) {
    if (page) P.stk = page;
    pane('sp-stock', '<div class="sp-empty">Loading stock…</div>');
    const sid = P.id, prof = P.profile;
    try {
      const qs = `page=${P.stk}&page_size=${PAGE}${P.stkStatus ? '&status=' + encodeURIComponent(P.stkStatus) : ''}${P.stkQ ? '&q=' + encodeURIComponent(P.stkQ) : ''}`;
      const res = await api.request(`/suppliers/${sid}/stock?${qs}`);
      if (P.id !== sid || P.profile !== prof) return;
      P.loaded.medicines = true;
      pane('sp-stock', spStockTableHtml(res.items));
      pager('sp-stock-pager', res.total, res.page, 'loadStock');
      $('sp-stock-notes').innerHTML = (res.notes || []).map(n => '<li>' + esc(n) + '</li>').join('');
      const chips = Object.keys(res.counts || {}).map(k => `<button type="button" class="sp-chip${P.stkStatus === k ? ' on' : ''}" onclick="spStockFilter('${k}')">${esc(k)} <b>${res.counts[k]}</b></button>`).join('');
      $('sp-stock-chips').innerHTML = chips ? `<button type="button" class="sp-chip${P.stkStatus ? '' : ' on'}" onclick="spStockFilter('')">All</button>` + chips : '';
    } catch (e) { if (P.id === sid && P.profile === prof) paneError('sp-stock', e, 'loadStock'); }
  };
  window.spStockFilter = function (s) { P.stkStatus = s; P.stk = 1; loadStock(); };
  window.spStockSearch = function (v) { P.stkQ = v.trim(); P.stk = 1; clearTimeout(window.__spT); window.__spT = setTimeout(loadStock, 250); };

  // ------------------------------------------------------------------ purchase bill viewer (read-only)
  const billGate = spMakeGate();
  function closeBill() { billGate.bump(); if (P.bill) { URL.revokeObjectURL(P.bill); P.bill = null; } const m = $('sup-bill-modal'); if (m) m.classList.remove('active'); }
  window.closeBillModal = closeBill;

  window.openPurchaseBill = async function (rawId) {
    const pid = parseInt(rawId, 10);
    if (!pid || !P.id) return;
    const sid = P.id;
    const my = billGate.next();
    $('sup-bill-title').textContent = 'Purchase';
    $('sup-bill-body').innerHTML = '<div class="sp-empty">Loading purchase…</div>';
    $('sup-bill-orig').style.display = 'none';
    $('sup-bill-modal').classList.add('active');
    try {
      const d = await api.request(`/purchases/detail/${pid}?supplier_id=${sid}`);
      if (!billGate.isCurrent(my)) return;
      $('sup-bill-title').textContent = `${d.voucher_no} · Invoice ${d.invoice_number}`;
      $('sup-bill-body').innerHTML = spBillHtml(d);
      $('sup-bill-open').style.display = d.source_document ? '' : 'none';
      if (d.source_document) loadOriginal(d.source_document, my);
      else { $('sup-bill-orig').style.display = 'block'; $('sup-bill-orig-view').innerHTML = '<div class="sp-empty">No scanned or uploaded bill is linked to this purchase (it was entered by hand, or the link cannot be established).</div>'; }
    } catch (e) {
      if (!billGate.isCurrent(my)) return;
      const code = statusOf(e);
      $('sup-bill-body').innerHTML = `<div class="sp-state bad"><b>${code === 404 ? 'This purchase was not found for this supplier' : 'Could not load this purchase'}</b><div>${esc(apiMsg(e))}</div>
        ${code === 404 ? '' : `<div style="margin-top:8px"><button type="button" class="btn btn-primary btn-sm" onclick="openPurchaseBill(${pid})">Retry</button></div>`}</div>`;
    }
  };

  async function loadOriginal(doc, my) {
    $('sup-bill-orig').style.display = 'block';
    const view = $('sup-bill-orig-view');
    view.innerHTML = '<div class="sp-empty">Loading original bill…</div>';
    try {
      const headers = await api.getHeaders(false);
      const res = await fetch(API_BASE_URL + '/documents/' + doc.id + '/file', { headers, credentials: 'include' });
      if (!res.ok) {
        let msg = 'The original bill could not be loaded.';
        try { msg = (await res.json()).detail || msg; } catch (_) { /* default */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      if (!billGate.isCurrent(my)) return;
      if (P.bill) URL.revokeObjectURL(P.bill);
      P.bill = URL.createObjectURL(blob);
      view.innerHTML = /pdf/i.test(blob.type) ? `<iframe class="sp-pdf" title="Original supplier bill" src="${P.bill}#toolbar=1&navpanes=0&view=FitH"></iframe>`
        : `<img class="sp-img" alt="Original supplier bill" src="${P.bill}">`;
      $('sup-bill-open').onclick = () => window.open(P.bill, '_blank', 'noopener');
    } catch (e) {
      if (billGate.isCurrent(my)) view.innerHTML = `<div class="sp-state bad"><b>The original bill is not available</b><div>${esc(e.message)}</div></div>`;
    }
  }

  // ------------------------------------------------------------------ clicks (one delegated handler per area)
  document.addEventListener('click', function (e) {
    const open = e.target.closest('[data-open-purchase]');
    if (open) { e.preventDefault(); e.stopPropagation(); window.openPurchaseBill(open.dataset.openPurchase); return; }
    const hist = e.target.closest('#sp-history tr[data-purchase-id]');
    if (hist) { window.openPurchaseBill(hist.dataset.purchaseId); return; }
    const stk = e.target.closest('#sp-stock tr[data-stock-id]');
    if (stk) { const d = document.querySelector(`#sp-stock tr[data-detail-for="${stk.dataset.stockId}"]`); if (d) d.style.display = d.style.display === 'none' ? '' : 'none'; }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    const row = e.target.closest && e.target.closest('tr.sp-row');
    if (row) { e.preventDefault(); row.click(); }
  });

  // deep link: suppliers.html#supplier=12
  document.addEventListener('DOMContentLoaded', function () {
    const m = /^#supplier=(\d+)$/.exec(window.location.hash || '');
    if (m) setTimeout(function () { P.pushed = false; window.openSupplierProfile(m[1], { fromPop: true }); P.pushed = true; }, 0);
  });

  return exported;
});
