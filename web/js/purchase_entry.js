/**
 * Add Manually: spreadsheet-style purchase entry (purchase_entry.html).
 * Rules and arithmetic live in purchase_entry_core.js (tested with Node); posting is done by the server
 * (POST /purchases/manual), which recalculates everything. Drafts are saved on the server (POST /purchases/drafts) and never touch stock.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const localDrafts = peDraftStore(window.localStorage);      // only used once: to move drafts saved in this browser by the earlier version to the server

  const state = {
    rows: [], header: { supplierId: null, supplierName: '', invoiceNo: '', invoiceDate: '', paymentStatus: 'UNPAID' },
    draftId: null, draftVersion: null, draftRef: '', dirty: false, saving: false, posted: false, suppliers: [], activeRow: 0, activeCol: 'name',
    pop: { kind: null, items: [], sel: 0, row: -1 }, ticket: 0, searchTimer: null, medForRow: -1,
  };

  const COL_LABEL = { name: 'Medicine', company: 'Company', packing: 'Packing', batch: 'Batch', expiry: 'Expiry', qty: 'Qty', free: 'Free', rate: 'Rate', disc: 'Disc %', gst: 'GST %', mrp: 'MRP' };
  const NUMERIC = { qty: 1, free: 1, rate: 1, disc: 1, gst: 1, mrp: 1 };

  // ---------- rendering
  function cell(r, i, col) {
    const v = esc(r[col]);
    const cls = NUMERIC[col] ? ' class="num"' : '';
    const mode = (col === 'qty' || col === 'free') ? ' inputmode="numeric"' : (NUMERIC[col] ? ' inputmode="decimal"' : '');
    const ph = col === 'expiry' ? ' placeholder="MM/YY"' : '';
    return `<td><input data-row="${i}" data-col="${col}" value="${v}"${cls}${mode}${ph} autocomplete="off" aria-label="${COL_LABEL[col]} row ${i + 1}"></td>`;
  }

  function rowHtml(r, i) {
    const detail = r.open ? `<tr class="pe-detail" data-detail="${i}"><td colspan="15"><div class="pe-detail-grid">
      <label>Composition<input data-row="${i}" data-col="composition" value="${esc(r.composition)}"></label>
      <label>Manufacturing date (MM/YY)<input data-row="${i}" data-col="mfg" value="${esc(r.mfg)}"></label>
      <label>HSN code<input data-row="${i}" data-col="hsn" value="${esc(r.hsn)}"></label>
      <label>Barcode / code<input data-row="${i}" data-col="barcode" value="${esc(r.barcode)}"></label></div></td></tr>` : '';
    return `<tr data-rowid="${r.id}">
      <td class="pe-n">${i + 1}</td>${['name', 'company', 'packing', 'batch', 'expiry'].map(c => cell(r, i, c)).join('')}
      <td class="pe-n" style="width:50px">${esc(r.unit)}</td>
      ${['qty', 'free', 'rate', 'disc', 'gst', 'mrp'].map(c => cell(r, i, c)).join('')}
      <td class="pe-amt" id="pe-amt-${i}">${money(peCalcLine(r).total)}</td>
      <td class="pe-act"><button type="button" data-act="detail" data-row="${i}" title="More details" tabindex="-1">${r.open ? '▴' : '▾'}</button>
      <button type="button" data-act="delete" data-row="${i}" title="Delete row (Ctrl+Delete)" tabindex="-1">🗑</button></td></tr>${detail}`;
  }

  function render(focus) {
    $('pe-tbody').innerHTML = state.rows.map(rowHtml).join('');
    updateTotals();
    if (focus) focusCell(focus.row, focus.col);
  }

  // Totals come from the server (POST /purchases/calc: the one calculation); the screen does not compute a competing total.
  function readInvoice() {
    state.header.invoice = { discount: $('pe-inv-disc').value, discountMode: $('pe-inv-disc-mode').value, other: $('pe-inv-other').value,
      inclusive: $('pe-inv-incl').checked, interstate: $('pe-inv-igst').checked, round: $('pe-inv-round').checked };
    return state.header.invoice;
  }

  function writeInvoice(inv) {
    inv = inv || {};
    $('pe-inv-disc').value = inv.discount || ''; $('pe-inv-disc-mode').value = inv.discountMode || 'amount'; $('pe-inv-other').value = inv.other || '';
    $('pe-inv-incl').checked = !!inv.inclusive; $('pe-inv-igst').checked = !!inv.interstate; $('pe-inv-round').checked = !!inv.round;
  }

  function paintCalc(c) {
    const t = c.totals;
    $('pe-t-count').textContent = state.rows.filter(r => !peRowEmpty(r)).length;
    $('pe-t-sub').textContent = money(t.gross);
    $('pe-t-disc').textContent = money(t.discount);
    $('pe-t-tax').textContent = money(t.taxable);
    $('pe-t-cgst').textContent = money(t.cgst);
    $('pe-t-sgst').textContent = money(t.sgst);
    $('pe-t-igst').textContent = money(t.igst);
    $('pe-t-other').textContent = money(t.other_charges);
    $('pe-t-round').textContent = money(t.round_off);
    $('pe-t-total').textContent = money(t.payable);
    let k = 0;
    state.rows.forEach((r, i) => {                       // each line's amount as the server calculated it
      const el = $('pe-amt-' + i);
      if (el && !peRowEmpty(r) && c.lines[k]) { el.textContent = money(c.lines[k].total); k++; }
    });
    $('pe-totals-card').style.opacity = '1';
  }

  let calcSeq = 0, calcTimer = null;
  async function calcNow() {
    const my = ++calcSeq;
    try {
      const c = await api.request('/purchases/calc', { method: 'POST', body: JSON.stringify(peBuildCalcBody(readInvoice(), state.rows)) });
      if (my !== calcSeq) return state.calc;               // a newer calculation is on its way
      state.calc = c;
      paintCalc(c);
      $('pe-calc-err').textContent = '';
    } catch (e) {
      if (my === calcSeq) { state.calc = null; $('pe-calc-err').textContent = 'Could not calculate the totals: ' + apiMessage(e); }
    }
    return state.calc;
  }

  function updateTotals() {
    $('pe-totals-card').style.opacity = '.55';
    clearTimeout(calcTimer);
    calcTimer = setTimeout(calcNow, 250);
  }

  function focusCell(i, col) {
    const el = document.querySelector(`#pe-tbody input[data-row="${i}"][data-col="${col}"]`);
    if (el) { el.focus(); if (el.select) el.select(); }
    state.activeRow = i; state.activeCol = col;
  }

  function markDirty() { state.dirty = true; }

  function addRow(focus, at) {
    const r = peNewRow();
    if (at == null) state.rows.push(r); else state.rows.splice(at, 0, r);
    const idx = state.rows.indexOf(r);
    render(focus ? { row: idx, col: 'name' } : null);
    return idx;
  }

  function deleteRow(i) {
    if (state.rows.length === 1) { state.rows[0] = peNewRow(); render({ row: 0, col: 'name' }); markDirty(); return; }
    state.rows.splice(i, 1);
    render({ row: Math.min(i, state.rows.length - 1), col: 'name' });
    markDirty();
  }

  // ---------- popups (medicine / batch / supplier)
  function popEl() { return state.pop.kind === 'supplier' ? $('pe-supplier-pop') : $('pe-pop'); }

  function closePop() {
    ['pe-pop', 'pe-supplier-pop'].forEach(id => { const e = $(id); e.style.display = 'none'; e.innerHTML = ''; });
    state.pop = { kind: null, items: [], sel: 0, row: -1 };
  }

  function showPop(kind, items, anchor, row, sel) {
    closePop();
    state.pop = { kind, items, sel: sel == null ? 0 : sel, row };
    const el = popEl();
    el.innerHTML = items.map((it, n) => `<div class="it${it.add ? ' add' : ''}${n === state.pop.sel ? ' sel' : ''}" data-n="${n}">${it.html}</div>`).join('');
    if (kind === 'supplier') {
      el.style.top = (anchor.offsetTop + anchor.offsetHeight + 2) + 'px'; el.style.left = anchor.offsetLeft + 'px';
    } else {
      const rect = anchor.getBoundingClientRect();
      el.style.top = (rect.bottom + window.scrollY + 2) + 'px';
      el.style.left = Math.min(rect.left + window.scrollX, window.innerWidth - 480) + 'px';
    }
    el.style.display = items.length ? 'block' : 'none';
  }

  function movePop(d) {
    const n = state.pop.items.length;
    if (!n) return;
    state.pop.sel = (state.pop.sel + d + n) % n;
    popEl().querySelectorAll('.it').forEach((e, k) => e.classList.toggle('sel', k === state.pop.sel));
    const cur = popEl().querySelector('.it.sel');
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
  }

  function medItems(list, term) {
    const items = list.map(m => ({
      med: m,
      html: `${esc(m.product_name)}${m.brand ? ' · ' + esc(m.brand) : ''}<small>${m.source === 'shop' ? 'In your inventory' : 'Medicine catalog'}` +
        `${m.composition ? ' · ' + esc(m.composition) : ''}${m.batches && m.batches.length ? ' · batches: ' + m.batches.map(b => esc(b.batch_number)).join(', ') : ''}</small>`,
    }));
    items.push({ add: true, name: term, html: `+ Add New Medicine${term ? ' “' + esc(term) + '”' : ''} (F2)` });
    return items;
  }

  function searchMedicines(i, term) {
    clearTimeout(state.searchTimer);
    if (term.trim().length < 2) { closePop(); return; }
    const ticket = ++state.ticket;
    state.searchTimer = setTimeout(async () => {
      try {
        const list = await api.request('/purchases/medicine-search?q=' + encodeURIComponent(term.trim()) + '&limit=12');
        if (ticket !== state.ticket || state.rows[i] == null || state.rows[i].name !== term) return;   // a newer search or edit won
        const anchor = document.querySelector(`#pe-tbody input[data-row="${i}"][data-col="name"]`);
        if (anchor && document.activeElement === anchor) showPop('med', medItems(list, term.trim()), anchor, i, 0);
      } catch (e) {
        if (ticket === state.ticket) closePop();
      }
    }, 180);
  }

  function showBatchPop(i) {
    const r = state.rows[i];
    const q = String(r.batch || '').trim().toLowerCase();
    const list = (r._batches || []).filter(b => !q || String(b.batch_number).toLowerCase().startsWith(q));
    const anchor = document.querySelector(`#pe-tbody input[data-row="${i}"][data-col="batch"]`);
    if (!list.length || !anchor) { closePop(); return; }
    showPop('batch', list.map(b => ({ batch: b, html: `Batch ${esc(b.batch_number)}<small>Exp ${esc(b.expiry_date || '')} · stock ${b.quantity} · MRP ${esc(b.mrp)}</small>` })), anchor, i, -1);
  }

  function pickMedicine(i, item) {
    if (item.add) { openMedicineModal(i, item.name); return; }
    const r = state.rows[i];
    const m = item.med;
    r._batches = m.batches || [];
    peApplyMedicine(r, m);
    closePop();
    markDirty();
    render({ row: i, col: 'batch' });          // the search text is gone with the popup; the next row stays empty
    showBatchPop(i);
  }

  function pickBatch(i, item) {
    const r = state.rows[i];
    const b = item.batch;
    peApplyMedicine(r, { product_name: r.name, brand: r.company, composition: r.composition, pack_size_label: r.packing, units_per_pack: r.unitsPerPack,
      hsn_code: r.hsn, barcode: r.barcode, product_id: r.productId, catalog_id: r.catalogId, gst_rate: r.gst, mrp: r.mrp }, b);
    closePop();
    markDirty();
    render({ row: i, col: 'qty' });
  }

  function pickPop(n) {
    const item = state.pop.items[n];
    if (!item) return;
    if (state.pop.kind === 'med') pickMedicine(state.pop.row, item);
    else if (state.pop.kind === 'batch') pickBatch(state.pop.row, item);
    else if (state.pop.kind === 'supplier') pickSupplier(item);
  }

  // ---------- grid events
  function onGridInput(e) {
    const el = e.target;
    if (!el.dataset || el.dataset.row == null) return;
    const i = +el.dataset.row, col = el.dataset.col;
    const r = state.rows[i];
    if (!r) return;
    r[col] = el.value;
    markDirty();
    el.classList.remove('bad');
    if (col === 'name') {
      r.productId = null; r.catalogId = null; r._batches = [];     // typing again means the old pick no longer applies
      searchMedicines(i, el.value);
    } else if (col === 'batch') {
      showBatchPop(i);
    }
    const a = $('pe-amt-' + i);
    if (a) a.textContent = money(peCalcLine(r).total);
    updateTotals();
  }

  function moveFrom(i, col, back) {
    closePop();
    const nxt = peNextCell(i, col, state.rows.length, back);
    if (nxt.newRow) {
      if (peRowEmpty(state.rows[i])) return;                      // a blank row is not followed by another blank row
      addRow(true);
      return;
    }
    focusCell(nxt.row, nxt.col);
    if (nxt.col === 'batch' && state.rows[nxt.row]._batches && state.rows[nxt.row]._batches.length) showBatchPop(nxt.row);
  }

  function onGridKey(e) {
    const el = e.target;
    if (!el.dataset || el.dataset.row == null) return;
    const i = +el.dataset.row, col = el.dataset.col;
    const popOpen = state.pop.kind && state.pop.row === i && (col === 'name' || col === 'batch');
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); peSave(); return; }
    if (e.key === 'F2') { e.preventDefault(); openMedicineModal(i, state.rows[i].name); return; }
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); closePop(); addRow(true, i + 1); return; }
    if (e.ctrlKey && e.key === 'Delete') { e.preventDefault(); closePop(); deleteRow(i); return; }
    if (e.key === 'Escape') { if (state.pop.kind) { e.preventDefault(); closePop(); } return; }
    if (popOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); movePop(e.key === 'ArrowDown' ? 1 : -1); return; }
    if (e.key === 'Enter') {
      e.preventDefault(); e.stopPropagation();
      if (e.repeat) return;                                        // a held Enter must not add rows or re-pick
      if (popOpen && state.pop.sel >= 0 && state.pop.items[state.pop.sel]) { pickPop(state.pop.sel); return; }
      if (col === 'name' && String(state.rows[i].name).trim() && !state.rows[i].productId && !state.rows[i].catalogId) {
        openMedicineModal(i, state.rows[i].name);                  // typed a name that was never picked: offer to add it, never create it silently
        return;
      }
      if (['composition', 'mfg', 'hsn', 'barcode'].includes(col)) { closePop(); focusCell(i, 'qty'); return; }
      moveFrom(i, col, false);
      return;
    }
    if (e.key === 'Tab') {
      if (el.dataset.col === 'composition' || ['mfg', 'hsn', 'barcode'].includes(col)) return;   // details row: normal browser order
      e.preventDefault();
      moveFrom(i, col, e.shiftKey);
    }
  }

  function onGridClick(e) {
    const it = e.target.closest && e.target.closest('.it');
    if (it && it.dataset.n != null && it.closest('#pe-pop')) { pickPop(+it.dataset.n); return; }
    const b = e.target.closest && e.target.closest('button[data-act]');
    if (!b) return;
    const i = +b.dataset.row;
    if (b.dataset.act === 'delete') deleteRow(i);
    else if (b.dataset.act === 'detail') { state.rows[i].open = !state.rows[i].open; render({ row: i, col: state.rows[i].open ? 'composition' : 'name' }); }
  }

  // ---------- supplier
  async function loadSuppliers() {
    try {
      const list = await api.request('/suppliers');
      state.suppliers = (Array.isArray(list) ? list : []).filter(s => String(s.status || 'Active').toLowerCase() !== 'inactive');
    } catch (e) { state.suppliers = []; }
  }

  function supplierItems(term) {
    const t = term.trim().toLowerCase();
    const list = state.suppliers.filter(s => !t || String(s.name).toLowerCase().includes(t) || String(s.gstin || '').toLowerCase().includes(t)).slice(0, 10);
    const items = list.map(s => ({ s, html: `${esc(s.name)}<small>${esc(s.gstin || '')} ${esc(s.phone || '')}</small>` }));
    items.push({ add: true, html: '+ Add supplier' });
    return items;
  }

  function pickSupplier(item) {
    if (item.add) { closePop(); peOpenSupplierModal($('pe-supplier').value); return; }
    setSupplier(item.s.id, item.s.name);
    closePop();
    $('pe-invoice-no').focus();
  }

  async function setSupplier(id, name) {
    state.header.supplierId = id; state.header.supplierName = name;
    $('pe-supplier').value = name;
    const sub = $('pe-supplier-sub');
    sub.className = 'pe-sub'; sub.textContent = '';
    try {
      const led = await api.request('/suppliers/' + id + '/ledger');
      if (state.header.supplierId === id) {
        sub.innerHTML = `Balance payable: <b>${money(led.balance_payable)}</b> · <a href="javascript:void(0)" onclick="peOpenSupplierModal()">+ Add supplier</a>`;
      }
    } catch (e) { sub.innerHTML = '<a href="javascript:void(0)" onclick="peOpenSupplierModal()">+ Add supplier</a>'; }
    checkDuplicate();
  }

  async function checkDuplicate() {
    const sub = $('pe-invoice-sub');
    const no = $('pe-invoice-no').value.trim();
    sub.className = 'pe-sub'; sub.textContent = '';
    if (!no || !state.header.supplierId) return false;
    try {
      const d = await api.request(`/purchases/check-duplicate?supplier_id=${state.header.supplierId}&invoice_number=${encodeURIComponent(no)}`);
      if (d.is_duplicate) {
        sub.className = 'pe-sub bad';
        sub.innerHTML = `Already saved as ${esc(d.voucher_no)} (${esc(d.invoice_date || '')}). <a href="purchases.html?view=${d.purchase_id}">Open it</a>`;
        return true;
      }
      sub.className = 'pe-sub ok'; sub.textContent = 'Invoice number is new for this supplier.';
    } catch (e) { /* the server checks again on save */ }
    return false;
  }

  // ---------- modals
  window.peCloseModals = function () { ['pe-supplier-modal', 'pe-med-modal'].forEach(id => $(id).classList.remove('active')); };

  window.peOpenSupplierModal = function (name) {
    closePop();
    $('ps-name').value = name || ''; $('ps-phone').value = ''; $('ps-gstin').value = ''; $('ps-err').textContent = '';
    $('pe-supplier-modal').classList.add('active');
    setTimeout(() => $('ps-name').focus(), 30);
  };

  window.peCreateSupplier = async function () {
    const name = $('ps-name').value.trim();
    if (name.length < 2) { $('ps-err').textContent = 'Enter the supplier name.'; return; }
    const body = { name };
    if ($('ps-phone').value.trim()) body.phone = $('ps-phone').value.trim();
    if ($('ps-gstin').value.trim()) body.gstin = $('ps-gstin').value.trim().toUpperCase();
    try {
      const s = await api.request('/suppliers', { method: 'POST', body: JSON.stringify(body) });
      if (!state.suppliers.some(x => x.id === s.id)) state.suppliers.push(s);
      peCloseModals();
      await setSupplier(s.id, s.name);
      markDirty();
      $('pe-invoice-no').focus();
    } catch (e) { $('ps-err').textContent = apiMessage(e); }
  };

  function openMedicineModal(i, name) {
    closePop();
    state.medForRow = i;
    ['pm-comp', 'pm-pack', 'pm-barcode'].forEach(id => { $(id).value = ''; });
    $('pm-name').value = name || ''; $('pm-company').value = state.rows[i] ? state.rows[i].company : '';
    $('pm-units').value = '10'; $('pm-hsn').value = '3004'; $('pm-gst').value = '12'; $('pm-err').textContent = '';
    $('pe-med-modal').classList.add('active');
    setTimeout(() => $('pm-name').focus(), 30);
  }

  window.peCreateMedicine = async function () {
    const name = $('pm-name').value.trim();
    const units = parseInt($('pm-units').value, 10);
    if (name.length < 2) { $('pm-err').textContent = 'Enter the medicine name.'; return; }
    if (!(units >= 1)) { $('pm-err').textContent = 'Units per pack must be 1 or more.'; return; }
    try {
      // an exact match already in the shop or the catalog is used instead of making a duplicate
      const found = await api.request('/purchases/medicine-search?q=' + encodeURIComponent(name) + '&limit=20');
      const same = (Array.isArray(found) ? found : []).find(m => m.product_name.trim().toLowerCase() === name.toLowerCase());
      const i = state.medForRow;
      const r = state.rows[i];
      if (same) {
        r._batches = same.batches || [];
        peApplyMedicine(r, same);
        peCloseModals(); markDirty(); render({ row: i, col: 'batch' });
        notice('“' + same.product_name + '” already exists, so the existing medicine was used.');
        return;
      }
      const body = { product_name: name, brand: $('pm-company').value.trim() || null, composition: $('pm-comp').value.trim() || null,
        hsn_code: $('pm-hsn').value.trim() || '3004', gst_rate: parseFloat($('pm-gst').value), tablets_per_strip: units,
        pack_size_label: $('pm-pack').value.trim() || ('strip of ' + units) };
      const c = await api.request('/catalog/create-custom', { method: 'POST', body: JSON.stringify(body) });
      r._batches = [];
      peApplyMedicine(r, { catalog_id: c.id, product_name: c.product_name, brand: c.brand, composition: c.composition, pack_size_label: c.pack_size_label,
        units_per_pack: c.units_per_pack || c.tablets_per_strip, hsn_code: c.hsn_code, gst_rate: c.gst_rate, barcode: $('pm-barcode').value.trim() });
      peCloseModals(); markDirty(); render({ row: i, col: 'batch' });
    } catch (e) { $('pm-err').textContent = apiMessage(e); }
  };

  // ---------- messages
  function apiMessage(e) {
    const t = String((e && e.message) || e || 'Something went wrong.');
    const j = t.indexOf('{');
    if (j >= 0) {
      try {
        const d = JSON.parse(t.slice(j)).detail;
        if (typeof d === 'string') return d;
        if (Array.isArray(d)) return d.map(x => (x.loc ? x.loc.slice(1).join(' › ') + ': ' : '') + x.msg).join('; ');
      } catch (_) { /* fall through */ }
    }
    return t.slice(0, 300);
  }

  function showErrors(list) {
    const box = $('pe-errors');
    if (!list || !list.length) { box.style.display = 'none'; box.innerHTML = ''; return; }
    box.innerHTML = '<b>Please fix before saving:</b><ul>' + list.map(m => '<li>' + esc(m) + '</li>').join('') + '</ul>';
    box.style.display = 'block';
    box.scrollIntoView({ block: 'nearest' });
  }

  function notice(text) { const s = $('pe-save-state'); s.textContent = text; }

  // ---------- validate + save
  function collectProblems() {
    const msgs = [];
    if (!state.header.supplierId) msgs.push('Choose a supplier from the list (or add one).');
    if (!$('pe-invoice-no').value.trim()) msgs.push('Enter the supplier invoice number.');
    if (!state.header.invoiceDate) msgs.push('Enter the invoice date.');
    document.querySelectorAll('#pe-tbody input.bad').forEach(el => el.classList.remove('bad'));
    const rowProblems = peValidateRows(state.rows);
    rowProblems.forEach(p => {
      msgs.push(p.row ? `Row ${p.row} · ${COL_LABEL[p.field] || p.field}: ${p.message}` : p.message);
      const el = document.querySelector(`#pe-tbody input[data-row="${p.row - 1}"][data-col="${p.field}"]`);
      if (el) el.classList.add('bad');
    });
    state.rows.forEach((r, i) => {
      if (!peRowEmpty(r) && String(r.name).trim() && !r.productId && !r.catalogId) {
        msgs.push(`Row ${i + 1} · Medicine: pick the medicine from the list, or use Add New Medicine (F2).`);
        const el = document.querySelector(`#pe-tbody input[data-row="${i}"][data-col="name"]`);
        if (el) el.classList.add('bad');
      }
    });
    return msgs;
  }

  function readHeader() {
    state.header.invoiceNo = $('pe-invoice-no').value;
    state.header.invoiceDate = $('pe-invoice-date').value;
    state.header.paymentStatus = $('pe-payment').value;
    readInvoice();
  }

  window.peSave = async function () {
    if (state.saving || state.posted) return;
    closePop();
    readHeader();
    clearTimeout(calcTimer);
    const calc = await calcNow();                         // the total that is saved is the one the server just calculated
    if (!calc) { showErrors(['The totals could not be calculated, so nothing was saved. Check the numbers and try again.']); return; }
    const problems = collectProblems();
    if (problems.length) { showErrors(problems); return; }
    showErrors([]);
    state.saving = true;
    setBusy(true);
    try {
      if (await checkDuplicate()) { showErrors(['This supplier invoice is already saved. Open it from Purchase Management instead of posting it again.']); return; }
      let res;
      try {
        res = await post();
      } catch (e) {
        const msg = apiMessage(e);
        if (/^MRP_BELOW_COST/.test(msg) && window.confirm(msg + '\n\nThe MRP is lower than the purchase cost. Is this correct?')) {
          state.rows.forEach(r => { r.confirmBelowCost = true; });
          res = await post();
        } else { throw e; }
      }
      state.posted = true; state.dirty = false;
      state.draftId = null;
      const ok = $('pe-ok');
      ok.innerHTML = `<b>Purchase saved.</b> ${esc(res.voucher_no)} · Invoice ${esc(res.invoice_number)} · ${esc(res.supplier_name)} · ${res.items_count} item(s) · ${money(res.total_amount)}.
        Stock was updated and the supplier balance includes this purchase.
        <div style="margin-top:8px"><a class="btn btn-primary btn-sm" href="purchases.html?view=${res.id}">View purchase</a>
        <a class="btn btn-secondary btn-sm" href="purchase_entry.html">New purchase</a>
        <a class="btn btn-secondary btn-sm" href="purchases.html">Back to Purchase Management</a></div>`;
      ok.style.display = 'block';
      ok.scrollIntoView({ block: 'start' });
      document.querySelectorAll('#pe-tbody input, .pe-head input, .pe-head select').forEach(el => { el.disabled = true; });
      ['pe-save-btn', 'pe-draft-btn', 'pe-top-save-btn', 'pe-top-draft-btn'].forEach(id => { $(id).disabled = true; });
    } catch (e) {
      const msg = apiMessage(e);
      const dup = /PUR-(\d+)/.exec(msg);
      showErrors([msg + (/DUPLICATE_INVOICE/.test(msg) && dup ? '' : '')]);
      if (/DUPLICATE_INVOICE/.test(msg)) checkDuplicate();
    } finally {
      state.saving = false;
      if (!state.posted) setBusy(false);
    }
  };

  function post() {
    const payload = peBuildPayload(Object.assign({}, state.header, { draftId: state.draftId, serverTotal: state.calc ? state.calc.totals.payable : null }), state.rows);
    return api.request('/purchases/manual', { method: 'POST', body: JSON.stringify(payload) });
  }

  function setBusy(b) {
    ['pe-save-btn', 'pe-draft-btn', 'pe-top-save-btn', 'pe-top-draft-btn'].forEach(id => { $(id).disabled = b; });
    $('pe-save-btn').textContent = b ? 'Saving…' : 'Save Purchase';
    $('pe-top-save-btn').textContent = b ? 'Saving…' : 'Save Purchase';
  }

  // ---------- drafts (saved on the server; they never change stock, balances or the purchase list)
  function showDraftRef() {
    $('pe-draft-ref').textContent = state.draftRef ? 'Editing ' + state.draftRef : '';
  }

  window.peSaveDraft = async function () {
    if (state.saving || state.posted) return;
    readHeader();
    const hasContent = state.header.supplierId || state.header.invoiceNo.trim() || state.rows.some(r => !peRowEmpty(r));
    if (!hasContent) { showErrors(['Enter a supplier, an invoice number or at least one medicine before saving a draft.']); return; }
    showErrors([]);
    state.saving = true;
    setBusy(true);
    try {
      const body = peBuildDraftBody(state.header, state.rows, state.draftId, state.draftVersion);
      const d = await api.request('/purchases/drafts', { method: 'POST', body: JSON.stringify(body) });
      state.draftId = d.id; state.draftVersion = d.version; state.draftRef = d.reference;
      state.dirty = false;
      showDraftRef();
      history.replaceState(null, '', 'purchase_entry.html?draft=' + d.id);          // reloading reopens this same draft
      notice(`Draft ${d.reference} saved at ${new Date().toLocaleTimeString()}. It is listed under Purchase Management → Drafts. Nothing was added to stock and no supplier balance changed.`);
      const ok = $('pe-ok');
      ok.innerHTML = `<b>Draft saved.</b> ${esc(d.reference)} · ${d.line_count} line(s)${d.estimated_total != null ? ' · estimate ' + money(d.estimated_total) : ''}.
        You can keep editing here, or <a href="purchases.html?tab=drafts">go to Drafts</a>.`;
      ok.style.display = 'block';
      setTimeout(() => { if (ok.innerHTML.indexOf('Draft saved') === 0) ok.style.display = 'none'; }, 6000);
    } catch (e) {
      const msg = apiMessage(e);
      showErrors([msg + (/DRAFT_CHANGED/.test(msg) ? '' : ' Your entries are still on this screen; nothing was lost.')]);
      if (/DRAFT_CHANGED/.test(msg)) {
        $('pe-errors').insertAdjacentHTML('beforeend', '<div style="margin-top:6px"><a href="javascript:void(0)" onclick="peReloadDraft()">Reload the saved draft</a> (your unsaved changes on this screen will be replaced)</div>');
      }
    } finally {
      state.saving = false;
      if (!state.posted) setBusy(false);
    }
  };

  window.peReloadDraft = function () { if (state.draftId) loadDraft(state.draftId, true); };

  async function loadDraft(id, force) {
    try {
      const d = await api.request('/purchases/drafts/' + id);
      if (d.source === 'OCR' && d.document_id) { window.location.href = 'documents.html?review=' + d.document_id; return; }
      if (d.status !== 'DRAFT') {
        showErrors([`${d.reference} was already posted as purchase ${d.purchase_voucher_no || ''}. It cannot be edited.`]);
        return;
      }
      const r = peRestoreDraft(d);
      state.draftId = d.id; state.draftVersion = d.version; state.draftRef = d.reference;
      state.header = r.header; state.rows = r.rows;
      $('pe-invoice-no').value = state.header.invoiceNo || '';
      $('pe-invoice-date').value = state.header.invoiceDate || peTodayISO();
      $('pe-payment').value = state.header.paymentStatus || 'UNPAID';
      writeInvoice(state.header.invoice);
      $('pe-supplier').value = state.header.supplierName || '';
      if (state.header.supplierId) setSupplier(state.header.supplierId, state.header.supplierName);
      render(null);
      state.dirty = false;
      showErrors([]);
      showDraftRef();
      notice(`${d.reference} reopened (saved ${new Date(d.updated_at).toLocaleString()}). Nothing is posted until you press Save Purchase.`);
    } catch (e) {
      showErrors(['Could not open this draft: ' + apiMessage(e)]);
    }
  }

  // drafts saved in this browser by the earlier version: offer to move them to the server
  function offerLocalDrafts() {
    const list = localDrafts.list();
    if (!list.length) return;
    $('pe-drafts').innerHTML = `<span class="pe-sub warn">${list.length} draft(s) saved earlier only in this browser. <a href="javascript:void(0)" id="pe-move-local">Move them to the server</a></span>`;
    $('pe-move-local').addEventListener('click', async () => {
      let moved = 0;
      for (const d of list) {
        try {
          const rows = (d.rows || []).map(r => { const c = Object.assign({}, r); delete c._batches; return c; });
          const h = d.header || {};
          await api.request('/purchases/drafts', { method: 'POST', body: JSON.stringify({ supplier_id: h.supplierId || null, invoice_number: h.invoiceNo || null,
            invoice_date: h.invoiceDate || null, payload: { header: h, rows } }) });
          localDrafts.remove(d.id); moved++;
        } catch (e) { /* a draft that cannot be saved stays in this browser */ }
      }
      $('pe-drafts').innerHTML = `<span class="pe-sub ok">${moved} draft(s) moved. See Purchase Management → Drafts.</span>`;
    });
  }

  window.peClear = function () {
    if ((state.dirty || state.rows.some(r => !peRowEmpty(r))) && !window.confirm('Clear everything on this screen?')) return;
    state.rows = [peNewRow()]; state.draftId = null; state.draftVersion = null; state.draftRef = ''; showDraftRef(); state.header = { supplierId: null, supplierName: '', invoiceNo: '', invoiceDate: peTodayISO(), paymentStatus: 'UNPAID' };
    $('pe-supplier').value = ''; $('pe-invoice-no').value = ''; $('pe-invoice-date').value = state.header.invoiceDate; $('pe-payment').value = 'UNPAID';
    $('pe-supplier-sub').innerHTML = '<a href="javascript:void(0)" onclick="peOpenSupplierModal()">+ Add supplier</a>'; $('pe-invoice-sub').textContent = '';
    state.dirty = false; showErrors([]); render({ row: 0, col: 'name' });
  };

  window.peCancel = function () {
    if (state.dirty && !window.confirm('You have unsaved changes. Leave without saving? (Use Save as Draft to keep them.)')) return;
    state.dirty = false;
    window.location.href = 'purchases.html';
  };

  window.peAddRow = function (focus) { addRow(!!focus); };

  // ---------- start
  function init() {
    $('pe-invoice-date').value = peTodayISO();
    state.header.invoiceDate = peTodayISO();
    state.rows = [peNewRow()];
    render({ row: 0, col: 'name' });
    offerLocalDrafts();
    loadSuppliers();

    const tb = $('pe-tbody');
    tb.addEventListener('input', onGridInput);
    tb.addEventListener('keydown', onGridKey);
    tb.addEventListener('focusin', (e) => {
      const el = e.target;
      if (el.dataset && el.dataset.row != null) {
        state.activeRow = +el.dataset.row; state.activeCol = el.dataset.col;
        if (state.pop.kind && (state.pop.row !== state.activeRow || (state.pop.kind === 'med' && el.dataset.col !== 'name') || (state.pop.kind === 'batch' && el.dataset.col !== 'batch'))) closePop();
        if (el.dataset.col === 'batch' && state.rows[state.activeRow] && state.rows[state.activeRow]._batches && state.rows[state.activeRow]._batches.length) showBatchPop(state.activeRow);
      }
    });
    tb.addEventListener('click', onGridClick);
    $('pe-pop').addEventListener('mousedown', (e) => { e.preventDefault(); const it = e.target.closest('.it'); if (it) pickPop(+it.dataset.n); });
    $('pe-supplier-pop').addEventListener('mousedown', (e) => { e.preventDefault(); const it = e.target.closest('.it'); if (it) pickPop(+it.dataset.n); });
    document.addEventListener('mousedown', (e) => { if (state.pop.kind && !e.target.closest('.pe-pop') && !e.target.closest('#pe-tbody') && e.target.id !== 'pe-supplier') closePop(); });
    tb.addEventListener('click', (e) => { if (e.target.closest('.it')) return; });

    const sup = $('pe-supplier');
    sup.addEventListener('input', () => {
      state.header.supplierId = null; state.header.supplierName = ''; markDirty();
      showPop('supplier', supplierItems(sup.value), sup, -1, 0);
    });
    sup.addEventListener('focus', () => showPop('supplier', supplierItems(sup.value), sup, -1, 0));
    sup.addEventListener('keydown', (e) => {
      if (state.pop.kind !== 'supplier') return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); movePop(e.key === 'ArrowDown' ? 1 : -1); }
      else if (e.key === 'Enter') { e.preventDefault(); if (!e.repeat) pickPop(state.pop.sel); }
      else if (e.key === 'Escape') { closePop(); }
    });
    $('pe-invoice-no').addEventListener('input', markDirty);
    $('pe-invoice-no').addEventListener('change', checkDuplicate);
    $('pe-invoice-no').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); $('pe-invoice-date').focus(); } });
    $('pe-invoice-date').addEventListener('change', () => { state.header.invoiceDate = $('pe-invoice-date').value; markDirty(); });
    $('pe-invoice-date').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); focusCell(0, 'name'); } });
    $('pe-payment').addEventListener('change', markDirty);
    ['pe-inv-disc', 'pe-inv-disc-mode', 'pe-inv-other', 'pe-inv-incl', 'pe-inv-igst', 'pe-inv-round'].forEach(id => {
      $(id).addEventListener('input', () => { markDirty(); updateTotals(); });
      $(id).addEventListener('change', () => { markDirty(); updateTotals(); });
    });
    document.addEventListener('keydown', (e) => { if (e.ctrlKey && e.key === 's' && !e.target.closest('#pe-tbody')) { e.preventDefault(); peSave(); } });
    window.addEventListener('beforeunload', (e) => { if (state.dirty && !state.posted) { e.preventDefault(); e.returnValue = ''; } });

    const want = new URLSearchParams(window.location.search).get('draft');
    if (want) loadDraft(parseInt(want, 10));
    // test hook (read-only view of the screen state)
    window.__pe = state;
  }

  document.addEventListener('DOMContentLoaded', init);
})();
