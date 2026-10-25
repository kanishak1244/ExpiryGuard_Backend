/*
 * Create New Bill: COUNTER SALE mode (a tab beside the normal bill tabs, same screen, same grid).
 *
 * Many walk-in customers are entered one after another in ONE spreadsheet grid. Every line belongs to a customer
 * transaction; the summary below shows each customer's own count and total.
 *   draft      this screen only (kept in this browser too, so a reload does not lose it)
 *   ready      "Finish customer" (F9): saved on the server, still NO stock deducted and no invoice
 *   converted  "Convert to Bill" (F10): ONE regular invoice made by the normal billing code, linked to the transaction
 *   cancelled  discarded while ready
 * Retail Billing is untouched; the grid, search, batch, unit, rate and keyboard engine are shared (billing_grid.js).
 * Pure rules: billing_counter_core.js. Server rules and tests: counter_sale.py.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => escapeText(s);
  const today = () => new Date().toISOString().slice(0, 10);
  const money = (n) => '₹' + Number(n || 0).toFixed(2);

  const server = { ready: [], readyTotal: 0, converted: [], loading: false, error: null, loaded: false };
  let busy = false;                                           // one save / convert at a time
  let persistTimer = null;

  window.billIsCounter = () => typeof activeBillState !== 'undefined' && !!activeBillState && activeBillState.mode === 'counter';
  const st = () => activeBillState.counter;
  const customers = () => st().customers;
  const customerById = (id) => customers().find((c) => c.id === id) || null;
  const activeCustomer = () => customerById(st().activeId) || customers()[0];

  // ---------- state, tab, persistence ----------
  function userKey() {
    try {
      const tok = localStorage.getItem('expiryguard_token') || localStorage.getItem('token') || '';
      const payload = JSON.parse(atob(tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      return 'u' + (payload.user_id || 'x') + 's' + (payload.staff_id || '0');
    } catch (e) { return 'anon'; }
  }
  const storeKey = () => 'dawaiflow_counter_' + userKey();

  function buildState() {
    const base = {
      mode: 'counter', idempotencyKey: null,
      customer: (typeof billingCustomersCache !== 'undefined' && billingCustomersCache[0]) || { id: 'walkin', name: 'Walk-in Customer', phone: 'Cash Sale', gstin: '' },
      pendingCustomerName: '', patientPhone: '', patientName: '', doctorName: '', doctorRegNo: '', splitPayments: [],
      invoiceNumber: '', invoiceDate: today(), paymentMode: 'CASH', billDiscountMode: 'percent', billDiscountText: '',
      manualRoundOff: 0, useManualRoundOff: false, activeHeldBillId: null, activeHeldBillNumber: null, items: [],
      counter: counterBlank(today()),
    };
    try {
      const back = counterRestore(localStorage.getItem(storeKey()) || '', today());
      if (back) { base.counter = back.counter; base.items = back.items; }
    } catch (e) { console.warn('Counter Sale drafts could not be restored', e); }
    return base;
  }

  function persistNow() {
    if (!billIsCounter()) return;
    try {
      const c = st();
      const drafts = c.customers.filter((x) => x.status === 'draft');
      if (!drafts.length) { localStorage.removeItem(storeKey()); return; }
      localStorage.setItem(storeKey(), counterSerialize(Object.assign({}, c, { customers: drafts }), activeBillState.items));
    } catch (e) { console.warn('Counter Sale drafts could not be saved in this browser', e); }
  }
  window.counterPersistNow = () => persistNow();
  function persistSoon() { clearTimeout(persistTimer); persistTimer = setTimeout(persistNow, 300); }

  // The Counter Sale tab: one per screen. Opens it (or goes to it) beside the normal bill tabs.
  window.counterOpenTab = function () {
    const at = billTabs.findIndex((t) => t.mode === 'counter');
    if (at >= 0) {
      if (at !== billActiveTab) billTabSwitch(at);
      return;
    }
    billTabs[billActiveTab].state = activeBillState;           // park the bill that is in front, untouched
    billTabs.push({ name: 'Counter Sale', mode: 'counter', state: buildState() });
    billActiveTab = billTabs.length - 1;
    activeBillState = billTabs[billActiveTab].state;
    billRefreshFromState();
  };

  // Called by billRefreshFromState for whichever bill came to the front.
  window.counterApplyMode = function () {
    const page = $('billing-page');
    if (!page) return;
    const on = billIsCounter();
    page.classList.toggle('mode-counter', on);
    if (on) {
      counterRender();
      if (!server.loaded) counterLoadServer();
    }
  };

  // ---------- rendering ----------
  function statusClass(s) { return 'cs-st cs-' + String(s).toLowerCase(); }

  window.counterRender = function () {
    if (!billIsCounter()) return;
    const c = st();
    const act = activeCustomer();
    const refEl = $('counter-active-ref');
    if (refEl) refEl.textContent = '#' + (act ? act.ref : '');
    const nm = $('counter-name'), ph = $('counter-phone');
    if (nm && document.activeElement !== nm) nm.value = act ? act.name : '';
    if (ph && document.activeElement !== ph) ph.value = act ? act.phone : '';
    counterRenderSummary();
  };

  function summaryRow(kind, c, t) {
    const who = esc('#' + c.ref) + (c.name ? ' <small>' + esc(c.name) + '</small>' : '');
    const activeCls = kind === 'draft' && c.id === st().activeId ? ' cs-active' : '';
    let actions = '';
    if (kind === 'draft') actions = `<button type="button" class="cs-btn" data-act="open" data-id="${esc(c.id)}">Open</button><button type="button" class="cs-btn cs-btn-go" data-act="convert-draft" data-id="${esc(c.id)}" title="Finish and convert to a bill">Convert</button><button type="button" class="cs-btn cs-btn-x" data-act="discard" data-id="${esc(c.id)}" title="Discard this customer">✕</button>`;
    else if (kind === 'ready') actions = `<button type="button" class="cs-btn cs-btn-go" data-act="convert" data-id="${esc(c.heldId)}">Convert</button><button type="button" class="cs-btn" data-act="reopen" data-id="${esc(c.heldId)}">Reopen</button><button type="button" class="cs-btn cs-btn-x" data-act="cancel" data-id="${esc(c.heldId)}" title="Cancel this transaction">✕</button>`;
    else if (kind === 'converted') actions = c.saleId ? `<a class="cs-btn" href="/billing/${esc(c.saleId)}/pdf" target="_blank" rel="noopener">${esc(c.invoice || 'View bill')}</a>` : '';
    return `<tr class="cs-row cs-${kind}${activeCls}" data-kind="${kind}" data-id="${esc(kind === 'draft' ? c.id : c.heldId)}">
      <td class="cs-who">${who}</td><td class="cs-num">${t.count}</td><td class="cs-num">${money(t.total)}</td>
      <td><span class="${statusClass(kind === 'draft' ? 'draft' : kind)}">${esc(counterStatusLabel(kind))}</span></td><td class="cs-act">${actions}</td></tr>`;
  }

  function counterRenderSummary() {
    const body = $('counter-sum-body');
    if (!body) return;
    const items = activeBillState.items;
    const rows = [];
    customers().filter((c) => c.status === 'draft').forEach((c) => rows.push(summaryRow('draft', c, counterTotals(items, c.id))));
    server.ready.forEach((r) => rows.push(summaryRow('ready', { ref: r.ref, name: r.customer_name || '', heldId: r.id }, { count: r.items_count, total: r.total })));
    server.converted.forEach((r) => rows.push(summaryRow('converted', { ref: r.ref, name: r.customer_name || '', heldId: r.id, saleId: r.completed_sale_id, invoice: r.invoice_number }, { count: r.items_count, total: r.total })));
    body.innerHTML = rows.join('') || '<tr><td colspan="5" class="cs-empty">No customers yet.</td></tr>';
    const more = $('counter-load-more');
    if (more) more.style.display = server.ready.length < server.readyTotal ? 'inline-block' : 'none';
    const err = $('counter-sum-error');
    if (err) err.textContent = server.error ? server.error : '';
    const all = items.length ? counterTotals(items, st().activeId) : { total: 0, count: 0 };
    const tot = $('counter-active-total');
    if (tot) tot.textContent = money(counterTotals(items, st().activeId).total);
    const cnt = $('counter-active-count');
    if (cnt) cnt.textContent = String(all.count);
  }

  window.counterRenderSummary = counterRenderSummary;

  // Called by recalculateTotals in counter mode (any edit of any line).
  window.counterAfterEdit = function () {
    counterRenderSummary();
    persistSoon();
  };

  // ---------- customers: switch, new, discard ----------
  function setActive(id, focus) {
    const c = customerById(id);
    if (!c || c.status !== 'draft') return;
    st().activeId = id;
    counterRender();
    renderBillItemsTable();
    persistSoon();
    if (focus !== false) billFocusSearch();
  }
  window.counterSetActive = setActive;

  window.counterNewCustomerNow = function () {
    const c = counterNewCustomer(counterNextRef(st(), today()));
    customers().push(c);
    st().activeId = c.id;
    counterRender();
    renderBillItemsTable();
    persistSoon();
    billFocusSearch();
    return c;
  };

  function step(dir) {
    const drafts = customers().filter((c) => c.status === 'draft');
    if (drafts.length < 2) return;
    const at = drafts.findIndex((c) => c.id === st().activeId);
    setActive(drafts[(at + dir + drafts.length) % drafts.length].id);
  }

  async function discard(id) {
    const c = customerById(id);
    if (!c) return;
    const lines = counterLinesOf(activeBillState.items, id);
    if (lines.length && !(await confirmBox({ title: 'Discard customer #' + c.ref + '?', message: `${lines.length} line(s) will be removed. Nothing is saved or billed.`, confirmText: 'Discard', icon: '🗑️' }))) return;
    activeBillState.items = activeBillState.items.filter((i) => i.customerId !== id);
    st().customers = customers().filter((x) => x.id !== id);
    if (!customers().some((x) => x.status === 'draft')) {
      const n = counterNewCustomer(counterNextRef(st(), today()));
      customers().push(n);
    }
    if (!customerById(st().activeId)) st().activeId = customers().find((x) => x.status === 'draft').id;
    renderBillItemsTable(); counterRender(); persistSoon(); billFocusSearch();
  }
  // the header "Clear" button / Ctrl+Shift+X in counter mode: discards only the customer in front
  window.counterDiscardActive = function () { return discard(st().activeId); };

  // ---------- messages and confirmation ----------
  function errText(err) {
    const m = String((err && err.message) || err || '');
    const j = m.match(/API Error \((\d+)\): (.*)$/s);
    if (!j) return /Failed to fetch|NetworkError|Load failed/i.test(m) ? 'Could not reach the server. Nothing was changed; try again.' : m;
    try { const d = JSON.parse(j[2]); const det = d.detail; return typeof det === 'string' ? det : (Array.isArray(det) ? det.map((x) => x.msg).join('; ') : j[2]); } catch (e) { return j[2]; }
  }
  // Enter confirms and Esc keeps, only while the dialog is open: the listener goes away as soon as the dialog is answered
  // (clicked, Enter or Esc), so it can never swallow a later Enter in the grid.
  function confirmBox(opts) {
    return new Promise((resolve) => {
      if (typeof window.showConfirmModal !== 'function') { resolve(window.confirm(opts.title + ' - ' + opts.message)); return; }
      const done = (v) => { window.removeEventListener('keydown', onKey, true); resolve(v); };
      const onKey = (e) => {
        if (e.key !== 'Enter') return;
        const b = $('confirm-modal-confirm');
        if (!b || b.offsetParent === null) return;
        e.preventDefault(); e.stopPropagation(); b.click();
      };
      window.addEventListener('keydown', onKey, true);
      window.showConfirmModal(Object.assign({ cancelText: 'Keep', onConfirm: () => done(true), onCancel: () => done(false) }, opts));
    });
  }

  // ---------- server records ----------
  async function counterLoadServer(more) {
    if (!window.api || typeof api.counterList !== 'function') return;
    server.loading = true;
    try {
      const skip = more ? server.ready.length : 0;
      const [rd, cv] = await Promise.all([api.counterList('READY', skip, 20), more ? Promise.resolve(null) : api.counterList('CONVERTED', 0, 8)]);
      server.ready = more ? server.ready.concat(rd.items) : rd.items;
      server.readyTotal = rd.total;
      if (cv) server.converted = cv.items;
      server.error = null; server.loaded = true;
    } catch (err) {
      server.error = 'Could not load saved customers: ' + errText(err);
    } finally {
      server.loading = false;
      counterRenderSummary();
    }
  }
  window.counterReload = () => counterLoadServer(false);

  // ---------- finish customer (draft -> ready) ----------
  // Saves this customer's lines as a READY transaction. No stock is deducted, no invoice is made. Safe to retry (same id).
  async function finishCustomer(id, opts) {
    const cust = customerById(id);
    if (!cust || cust.status !== 'draft') return null;
    const problem = counterCustomerProblem(activeBillState.items, id, today());
    if (problem) {
      billToast(problem.message, true);
      if (id !== st().activeId) setActive(id, false);
      if (problem.index >= 0) billFocusQty(problem.index);
      return null;
    }
    const lines = counterLinesOf(activeBillState.items, id);
    let res;
    try {
      res = await api.counterFinish({
        txn_id: cust.id, ref: cust.ref, customer_name: cust.name || null, customer_phone: cust.phone || null,
        replaces_id: cust.replacesId || null, items: lines.map(counterHoldLine),
      });
    } catch (err) {
      billToast('Customer #' + cust.ref + ' was not saved: ' + errText(err) + ' It is still in progress.', true);
      return null;
    }
    // saved: move it out of the grid (its lines now live on the server, as READY)
    activeBillState.items = activeBillState.items.filter((i) => i.customerId !== id);
    cust.status = 'ready'; cust.heldId = res.id;
    st().customers = customers().filter((x) => x.id !== id);
    server.ready = [res].concat(server.ready.filter((r) => r.id !== res.id));
    server.readyTotal = Math.max(server.readyTotal, server.ready.length);
    if (!opts || opts.startNext !== false || !customers().some((x) => x.status === 'draft')) {
      const n = counterNewCustomer(counterNextRef(st(), today()));      // the next customer is ready to be typed
      customers().push(n);
      st().activeId = n.id;
    }
    if (!customerById(st().activeId)) st().activeId = customers().find((x) => x.status === 'draft').id;
    billToast('Customer #' + cust.ref + ' is ready (' + money(res.total) + ').', false);
    renderBillItemsTable(); counterRender(); persistNow();
    billFocusSearch();
    return res;
  }

  window.counterFinishActive = async function () {
    if (busy) return;
    busy = true;
    try { return await finishCustomer(st().activeId, { startNext: true }); } finally { busy = false; }
  };

  // ---------- convert to bill (ready -> converted) ----------
  function payMode() { const s = $('counter-pay'); return s ? s.value : 'CASH'; }

  async function convertReady(heldId, label, total, count) {
    const mode = payMode();
    const ok = await confirmBox({
      title: 'Convert customer ' + label + ' to a bill?',
      message: `${count} item(s), ${money(total)}, paid by ${mode}. Stock is deducted now, once, and one invoice is created.`,
      confirmText: 'Convert to Bill', icon: '🧾',
    });
    if (!ok) { billFocusSearch(); return null; }
    let res;
    try {
      res = await api.counterConvert(heldId, { payment_method: mode });
    } catch (err) {
      billToast('Not converted: ' + errText(err) + ' The customer is still READY; nothing was changed.', true);
      counterLoadServer(false);
      return null;
    }
    const tx = res.transaction;
    server.ready = server.ready.filter((r) => r.id !== heldId);
    server.readyTotal = Math.max(0, server.readyTotal - 1);
    server.converted = [tx].concat(server.converted.filter((r) => r.id !== heldId)).slice(0, 8);
    const link = res.pdf_url ? `<a href="${esc(res.pdf_url)}" target="_blank" rel="noopener" style="color:#fff;text-decoration:underline;margin-left:10px;">View bill</a>` : '';
    if (typeof showToastNotification === 'function') showToastNotification(`✅ Bill ${esc(res.bill_number)} created (${money(res.total_amount)})${res.already_converted ? ' — it was already converted' : ''}${link}`);
    if (window.billCatalog) setTimeout(() => billCatalog.refresh(), 50);       // the stock changed
    counterRenderSummary(); billFocusSearch();
    return res;
  }

  window.counterConvertTarget = async function (target) {
    if (busy) return;
    busy = true;
    try {
      let heldId = null, label = '', total = 0, count = 0;
      if (target && target.kind === 'ready') {
        const r = server.ready.find((x) => x.id === target.id);
        if (!r) return;
        heldId = r.id; label = '#' + r.ref; total = r.total; count = r.items_count;
      } else {
        const id = (target && target.id) || st().activeId;
        const c = customerById(id);
        if (!c || c.status !== 'draft') return;
        const t = counterTotals(activeBillState.items, id);
        const res = await finishCustomer(id, { startNext: true });
        if (!res) return;
        heldId = res.id; label = '#' + c.ref; total = res.total; count = t.count;
      }
      await convertReady(heldId, label, total, count);
    } finally { busy = false; }
  };

  // ---------- reopen / cancel a ready customer ----------
  async function reopen(heldId) {
    let d;
    try { d = await api.counterGet(heldId); } catch (err) { billToast('Could not open it: ' + errText(err), true); return; }
    if (d.status !== 'READY') { billToast('Only a ready customer can be reopened.', true); counterLoadServer(false); return; }
    const cust = counterNewCustomer(d.ref);
    cust.name = d.customer_name || ''; cust.phone = d.customer_phone || ''; cust.replacesId = d.id;
    customers().push(cust);
    d.items.forEach((it) => {
      const line = counterLineFromServer(it, cust.id, gridNewRowId());
      activeBillState.items.push(line);
    });
    st().activeId = cust.id;
    // the old READY record stays (as history) until the edited version is finished
    renderBillItemsTable(); counterRender(); persistNow();
    activeBillState.items.filter((i) => i.customerId === cust.id).forEach((i) => { if (typeof billLoadBatchesFor === 'function') billLoadBatchesFor(i.id); });
    recalculateTotals();
    billFocusSearch();
    billToast('Customer #' + d.ref + ' reopened. Press F9 to finish it again (the old version is replaced).', false);
  }
  async function cancelReady(heldId) {
    const r = server.ready.find((x) => x.id === heldId);
    if (!(await confirmBox({ title: 'Cancel customer #' + (r ? r.ref : '') + '?', message: 'It stays in the history as cancelled. No stock was deducted.', confirmText: 'Cancel it', icon: '🗑️' }))) return;
    try { await api.counterCancel(heldId); } catch (err) { billToast('Not cancelled: ' + errText(err), true); counterLoadServer(false); return; }
    server.ready = server.ready.filter((x) => x.id !== heldId);
    server.readyTotal = Math.max(0, server.readyTotal - 1);
    counterRenderSummary();
  }

  // ---------- events ----------
  function wire() {
    const body = $('counter-sum-body');
    if (!body || body.__wired) return;
    body.__wired = true;
    body.addEventListener('click', (e) => {
      const b = e.target.closest('[data-act]');
      if (b) {
        const act = b.getAttribute('data-act'), id = b.getAttribute('data-id');
        if (act === 'open') setActive(id);
        else if (act === 'discard') discard(id);
        else if (act === 'convert-draft') counterConvertTarget({ kind: 'draft', id });
        else if (act === 'convert') counterConvertTarget({ kind: 'ready', id: Number(id) });
        else if (act === 'reopen') reopen(Number(id));
        else if (act === 'cancel') cancelReady(Number(id));
        return;
      }
      const tr = e.target.closest('tr[data-kind="draft"]');
      if (tr) setActive(tr.getAttribute('data-id'));
    });
    const more = $('counter-load-more'); if (more) more.addEventListener('click', () => counterLoadServer(true));
    const nm = $('counter-name'), ph = $('counter-phone');
    if (nm) nm.addEventListener('input', () => { const c = activeCustomer(); if (c) { c.name = nm.value; counterRenderSummary(); persistSoon(); } });
    if (ph) ph.addEventListener('input', () => { const c = activeCustomer(); if (c) { c.phone = ph.value; persistSoon(); } });
    // clicking the customer cell of a line makes that customer the active one
    const tb = $('bill-items-table-body');
    if (tb) tb.addEventListener('click', (e) => {
      const td = e.target.closest && e.target.closest('td.c-cust');
      if (td && billIsCounter()) setActive(td.getAttribute('data-cust'), false);
    });
    window.addEventListener('beforeunload', persistNow);
  }

  // Keys of the Counter Sale tab. Returns true when the key was used here (the retail shortcuts then do nothing).
  window.counterKey = function (e) {
    if (!billIsCounter()) return false;
    if (e.ctrlKey && e.altKey) return false;
    const busyList = window.billGrid && billGrid.popup;
    if (e.key === 'PageDown' || e.key === 'PageUp') {
      if (busyList || (typeof productDropdownOpen === 'function' && productDropdownOpen())) return false;
      e.preventDefault(); e.stopPropagation(); step(e.key === 'PageDown' ? 1 : -1); return true;
    }
    if (e.key === 'F8') { e.preventDefault(); e.stopPropagation(); if (!e.repeat) counterNewCustomerNow(); return true; }
    const guard = () => {
      if (e.repeat) return false;
      if (busyList || (typeof productDropdownOpen === 'function' && productDropdownOpen())) { billToast('Finish choosing (Enter) or press Esc to close the list first.', true); return false; }
      if (typeof billGridCommitActive === 'function' && !billGridCommitActive()) return false;
      return true;
    };
    if (e.key === 'F9' || (e.ctrlKey && e.shiftKey && e.key === 'Enter')) { e.preventDefault(); e.stopPropagation(); if (guard()) counterFinishActive(); return true; }
    if (e.key === 'F10' || (e.ctrlKey && !e.shiftKey && e.key === 'Enter')) { e.preventDefault(); e.stopPropagation(); if (guard()) counterConvertTarget({ kind: 'draft', id: st().activeId }); return true; }
    if (e.key === 'F6') { e.preventDefault(); e.stopPropagation(); billToast('Counter Sale: F9 finishes this customer and starts the next one.', false); return true; }
    if (e.altKey && !e.ctrlKey && ['1', '2', '3', '4'].includes(e.key)) {
      e.preventDefault(); e.stopPropagation();
      const s = $('counter-pay'); if (s) s.value = ['CASH', 'UPI', 'CARD', 'CREDIT'][Number(e.key) - 1];
      return true;
    }
    return false;
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
  window.counterWire = wire;
  window.counterBusy = () => busy;
  window.counterServerState = server;        // read by the browser tests
})();
