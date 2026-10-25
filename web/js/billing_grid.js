/*
 * Create New Bill: the spreadsheet-style grid (keyboard first).
 *
 *   Party Name  ->  Product  ->  Batch  ->  Unit  ->  Qty  ->  Disc %  ->  next empty Product ...
 *
 * - The active cell is real state (billGrid.active = { key, col }); lines are found by their stable id, never by position.
 * - One dropdown at a time, placed with position:fixed under the active cell (never cut off by the grid; flips above near the bottom).
 * - The medicine search itself (debounce, latest-request-wins, scanner Enter) stays in billing_flow.js; this file draws the cells,
 *   routes the keys, and runs the Party and Batch dropdowns.
 * - Nothing here saves or deducts stock: that only happens in the existing Save workflow (and the server checks everything again).
 * Pure rules (which cell next, dropdown placement, batch order, quantity checks) live in billing_grid_core.js and are unit tested.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => escapeText(s);
  const items = () => activeBillState.items;
  const onGridPage = () => !!$('billing-page') && !!$('bill-items-table-body');

  const billGrid = { active: null, popup: null };
  window.billGrid = billGrid;

  // ---------- small helpers ----------
  function ensureIds() {
    const seen = new Set();
    items().forEach((it) => {
      if (typeof it.id !== 'string' || seen.has(it.id)) it.id = gridNewRowId();
      seen.add(it.id);
    });
  }
  const indexOfId = (id) => items().findIndex((it) => it.id === id);
  const itemOfKey = (key) => (key === 'entry' ? null : items()[indexOfId(key)] || null);
  function keyOfIndex(i) { return i >= items().length ? 'entry' : items()[i].id; }

  function rowEl(key) {
    const tb = $('bill-items-table-body');
    if (!tb) return null;
    if (key === 'entry') return tb.querySelector('tr[data-entry]');
    return [...tb.querySelectorAll('tr[data-rid]')].find((tr) => tr.getAttribute('data-rid') === key) || null;
  }
  function cellEl(key, col) {
    const tr = rowEl(key);
    return tr ? tr.querySelector('[data-cell="' + col + '"]') : null;
  }
  function posOfEl(el) {
    const tr = el.closest('tr');
    if (!tr) return null;
    const key = tr.hasAttribute('data-entry') ? 'entry' : tr.getAttribute('data-rid');
    const row = key === 'entry' ? items().length : indexOfId(key);
    return { key, row, col: el.getAttribute('data-cell') };
  }

  function setActive(key, col) {
    billGrid.active = { key, col };
    const tb = $('bill-items-table-body');
    if (!tb) return;
    tb.querySelectorAll('.cell-active').forEach((c) => c.classList.remove('cell-active'));
    tb.querySelectorAll('tr.row-selected').forEach((r) => r.classList.remove('row-selected'));
    const el = cellEl(key, col);
    if (el) { el.closest('td').classList.add('cell-active'); el.closest('tr').classList.add('row-selected'); }
  }

  // Put the cursor in a cell (position = { row, col }). Returns false when that cell does not exist.
  function focusPos(pos, opts) {
    const key = keyOfIndex(pos.row);
    const el = cellEl(key, pos.col);
    if (!el) return false;
    setActive(key, pos.col);
    el.focus();
    if (typeof el.select === 'function' && !(opts && opts.keepCaret)) el.select();
    el.scrollIntoView({ block: 'nearest' });
    return true;
  }
  function focusEntryProduct() { return focusPos({ row: items().length, col: 'product' }); }
  window.billGridFocusPos = focusPos;

  // ---------- dropdown (Party, Batch, Unit); the medicine dropdown is the older #bill-search-results-dropdown ----------
  function popupEl() {
    let p = $('bill-cell-popup');
    if (!p) {
      p = document.createElement('div');
      p.id = 'bill-cell-popup';
      p.className = 'bill-popup';
      p.setAttribute('role', 'listbox');
      p.setAttribute('tabindex', '-1');
      p.setAttribute('aria-label', 'Selection options');
      p.style.display = 'none';
      p.addEventListener('mousedown', (e) => e.preventDefault());       // keep the cursor in the cell
      p.addEventListener('click', (e) => {
        const o = e.target.closest('[data-i]');
        if (o) popupPick(Number(o.getAttribute('data-i')));
      });
      p.addEventListener('keydown', (e) => {
        if (!billGrid.popup) return;
        const kind = billGrid.popup.kind;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          e.stopPropagation();
          popupMove(e.key === 'ArrowDown' ? 1 : -1);
          return;
        }
        if (e.key === 'Enter' || (e.key === ' ' && kind === 'unit')) {
          e.preventDefault();
          e.stopPropagation();
          popupPick(billGrid.popup.index);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          e.stopPropagation();
          const anchor = billGrid.popup.anchor;
          popupClose();
          if (anchor && typeof anchor.focus === 'function') anchor.focus();
          return;
        }
        if (e.key === 'Tab') {
          e.preventDefault();
          e.stopPropagation();
          if (kind === 'unit') {
            popupPick(billGrid.popup.index);
          } else {
            const anchor = billGrid.popup.anchor;
            popupClose();
            if (anchor && typeof anchor.focus === 'function') anchor.focus();
          }
          return;
        }
      });
      document.body.appendChild(p);
    }
    return p;
  }

  function placeAt(el, anchor, width, height) {
    const r = anchor.getBoundingClientRect();
    // decide above/below with room for a normal list, so a short "Searching…" box and the full list do not jump sides
    const p = gridPopupPlacement({ left: r.left, top: r.top, bottom: r.bottom, width: r.width },
      { width, height: Math.max(height, 240) }, { width: window.innerWidth, height: window.innerHeight });
    Object.assign(el.style, { position: 'fixed', left: p.left + 'px', top: p.top + 'px', width: p.width + 'px', maxHeight: p.maxHeight + 'px', overflowY: 'auto', zIndex: 3000 });
    el.setAttribute('data-placement', p.placement);
    if (p.placement === 'above') el.style.top = Math.max(4, r.top - 2 - el.offsetHeight) + 'px';   // sits right on top of the cell
  }
  // Used by the medicine dropdown in billing_flow.js after it fills itself.
  window.billPlacePopup = function (el, anchor) {
    if (!onGridPage() || !el) return;
    const a = anchor || (billGrid.searchEl && billGrid.searchEl.isConnected ? billGrid.searchEl : null) || $('bill-medicine-search-input');
    if (!a) return;
    if (el.parentElement !== document.body) document.body.appendChild(el);
    placeAt(el, a, Math.max(580, a.getBoundingClientRect().width), Math.min(el.scrollHeight + 4, 440));
  };

  function popupDraw() {
    const p = billGrid.popup;
    const el = popupEl();
    if (!p) { el.style.display = 'none'; el.innerHTML = ''; return; }
    const rows = p.options.map((o, i) =>
      '<div class="bp-opt' + (i === p.index ? ' selected' : '') + (o.selectable ? '' : ' disabled') +
      '" data-i="' + i + '" id="bp-opt-' + i + '" role="option" aria-selected="' + (i === p.index ? 'true' : 'false') +
      '">' + o.html + '</div>').join('');
    el.innerHTML = (p.head ? '<div class="bp-head">' + p.head + '</div>' : '') +
      (p.options.length ? rows : '<div class="bp-empty">' + (p.empty || 'Nothing found') + '</div>');
    el.style.display = 'block';
    placeAt(el, p.anchor, p.width || 420, Math.min(el.scrollHeight + 4, 360));
    if (p.anchor && p.anchor.setAttribute) {
      p.anchor.setAttribute('aria-expanded', 'true');
      p.anchor.setAttribute('aria-activedescendant', 'bp-opt-' + p.index);
    }
    const sel = el.querySelector('.selected');
    if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
  function popupOpen(cfg) {
    closeProductDropdown();
    const firstOk = cfg.options.findIndex((o) => o.selectable);
    billGrid.popup = Object.assign({}, cfg, { index: cfg.index !== undefined ? cfg.index : Math.max(0, firstOk) });
    popupDraw();
  }
  function popupClose() {
    if (billGrid.popup && billGrid.popup.anchor && billGrid.popup.anchor.setAttribute) {
      billGrid.popup.anchor.setAttribute('aria-expanded', 'false');
      billGrid.popup.anchor.removeAttribute('aria-activedescendant');
    }
    billGrid.popup = null;
    const el = $('bill-cell-popup');
    if (el) { el.style.display = 'none'; el.innerHTML = ''; }
  }
  function popupRefresh(options, query) {
    if (!billGrid.popup) return;
    billGrid.popup.options = options;
    billGrid.popup.query = query;
    const firstOk = options.findIndex((o) => o.selectable);
    billGrid.popup.index = Math.max(0, firstOk);
    popupDraw();
  }
  function popupMove(dir) {
    const p = billGrid.popup;
    if (!p || !p.options.length) return;
    let next = p.index + dir;
    while (next >= 0 && next < p.options.length && !p.options[next].selectable) {
      next += dir;
    }
    if (next >= 0 && next < p.options.length && p.options[next].selectable) {
      p.index = next;
      popupDraw();
    }
  }
  function popupPick(i) {
    const p = billGrid.popup;
    if (!p) return;
    const o = p.options[i];
    if (!o) return;
    if (!o.selectable) { billToast(o.why || 'This one cannot be selected.', true); return; }
    const done = p.onPick;
    popupClose();
    done(o);
  }
  window.billGridPopupOpen = () => !!billGrid.popup;
  function closeProductDropdown() {
    const dd = $('bill-search-results-dropdown');
    if (dd && dd.style.display !== 'none') dd.style.display = 'none';
  }
  const productDropdownOpen = () => {
    const dd = $('bill-search-results-dropdown');
    return !!dd && dd.style.display === 'block' && (window._lastSearchResults || []).length > 0;
  };

  // ---------- party (customer) ----------
  function partyLabel(c) { return c ? c.name + (c.phone ? ' (' + c.phone + ')' : '') : ''; }
  function billSyncPartyInput() {
    const inp = $('bill-party-input');
    if (!inp || document.activeElement === inp) return;
    inp.value = partyLabel(activeBillState.customer || billingCustomersCache.find((c) => c.id === 'walkin') || null);
  }
  window.billSyncPartyInput = billSyncPartyInput;
  function partyOptions(query) {
    const list = gridFilterParties(billingCustomersCache, query);
    const opts = list.map((c) => ({
      selectable: true, value: c,
      html: '<span class="bp-main">' + gridHighlight(c.name, query) + '</span><span class="bp-sub">' + gridHighlight(c.phone || '', query) + (c.gstin ? ' · ' + esc(c.gstin) : '') + '</span>',
    }));
    opts.push({ selectable: true, value: 'NEW', html: '<span class="bp-main">+ Add new party…</span>' });
    return opts;
  }
  function openPartyPopup(query) {
    const inp = $('bill-party-input');
    popupOpen({ kind: 'party', anchor: inp, query, width: 440, options: partyOptions(query), onPick: (o) => choosePartyOption(o.value) });
  }
  function choosePartyOption(v) {
    if (v === 'NEW') { handleCustomerSelectChange('NEW'); return; }
    const sel = $('bill-customer-select');
    if (sel) sel.value = String(v.id);
    handleCustomerSelectChange(String(v.id));
    const inp = $('bill-party-input');
    if (inp) inp.value = partyLabel(v);
    focusEntryProduct();                          // straight to the first Product cell
  }
  window.billFocusParty = function () {
    const inp = $('bill-party-input');
    if (inp) { inp.focus(); inp.select(); return true; }
    return false;
  };
  // A new, empty bill starts in Party Name; a bill that already has lines starts in the Product cell.
  window.billFocusStart = function () {
    if (onGridPage() && items().length === 0) { if (!window.billFocusParty()) focusEntryProduct(); }
    else if (onGridPage()) focusEntryProduct();
    else billFocusSearch();
  };

  function onPartyKeydown(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const p = billGrid.popup && billGrid.popup.kind === 'party' ? billGrid.popup : null;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!p) openPartyPopup(''); else popupMove(e.key === 'ArrowDown' ? 1 : -1);
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (p) popupPick(p.index); else focusEntryProduct();
      return;
    }
    if (e.key === 'Tab' && !e.shiftKey) {
      e.preventDefault();
      popupClose();
      billSyncPartyInput();
      focusEntryProduct();
    }
  }

  // ---------- batch dropdown (committed lines: the medicine's batches; entry row: search by batch number) ----------
  function batchOptionHtml(b, st, query, withName) {
    const tag = st === 'expired' ? '<span class="bp-tag bad">EXPIRED</span>' : st === 'out' ? '<span class="bp-tag bad">NO STOCK</span>'
      : st === 'near' ? '<span class="bp-tag warn">near expiry ' + billDaysToExpiry(b.expiryDate) + 'd</span>' : '';
    return '<span class="bp-main">' + gridHighlight(b.batchNumber || '-', query) + '</span>' +
      (withName ? '<span class="bp-name">' + esc(b.name || '') + '</span>' : '') +
      '<span class="bp-sub">Exp ' + esc(b.expiryDate || '-') + '</span><span class="bp-sub">Stock ' + (Number(b.stock) || 0) + '</span>' +
      '<span class="bp-sub">₹' + Number(b.mrp || 0).toFixed(2) + '</span>' + tag;
  }
  function batchWhy(st) {
    return st === 'expired' ? 'This batch is expired and cannot be sold.' : 'This batch has no stock.';
  }
  function itemBatchOptions(item, query) {
    return gridBatchOptions(item.batches || [], query).map((o) => ({
      selectable: o.selectable, value: o.batch, why: batchWhy(o.state), html: batchOptionHtml(o.batch, o.state, query, false),
    }));
  }
  function openBatchPopupFor(key, query) {
    const item = itemOfKey(key);
    const anchor = cellEl(key, 'batch');
    if (!item || !anchor) return;
    const opts = itemBatchOptions(item, query || '');
    const cur = opts.findIndex((o) => o.value.batchNumber === item.selectedBatch && o.value.productId === item.productId);
    popupOpen({
      kind: 'batch', key, anchor, query: query || '', width: 520, options: opts, index: cur >= 0 && !query ? cur : undefined,
      head: '<span>Batch</span><span>Expiry</span><span>Stock</span><span>MRP</span>',
      empty: 'No batch matches “' + esc(query || '') + '”',
      onPick: (o) => { const i = indexOfId(key); billApplyBatch(i, o.value); if (typeof renderBillItemsTable === 'function') renderBillItemsTable(); else render(); recalculateTotals(); focusPos({ row: i, col: 'unit' }); },
    });
  }
  const entryBatchGate = billMakeLatestGate();
  let entryBatchTimer = null;
  let entryBatchAbort = null;
  function searchEntryBatch(q) {
    clearTimeout(entryBatchTimer);
    if (entryBatchAbort) entryBatchAbort.abort();
    const ticket = entryBatchGate.next();
    const anchor = $('bill-entry-batch');
    if (!q) { popupClose(); return; }
    if (q.length < 2) {
      popupOpen({ kind: 'entrybatch', anchor, query: q, width: 520, options: [], empty: 'Type at least 2 characters of the batch number', onPick: () => {} });
      return;
    }
    const showRows = (rows) => {
      const opts = rows.map((r) => {
        const f = billFormatProductRow(r);
        const b = billToBatch(f);
        const st = billBatchState(b);
        return { selectable: st === 'ok' || st === 'near', why: batchWhy(st), value: f, html: batchOptionHtml({ ...b, name: f.name }, st, q, true) };
      });
      popupOpen({
        kind: 'entrybatch', anchor, query: q, width: 640, options: opts,
        head: '<span>Batch</span><span>Medicine</span><span>Expiry</span><span>Stock</span><span>MRP</span>',
        empty: 'No batch matches “' + esc(q) + '”',
        onPick: (o) => { billAddMedicine(o.value, { forceProductId: o.value.productId }); },
      });
    };
    if (window.billCatalog && billCatalog.ready()) { showRows(billCatalog.batchSearch(q, 20)); return; }   // instant
    popupOpen({ kind: 'entrybatch', anchor, query: q, width: 520, options: [], empty: 'Searching…', onPick: () => {} });
    entryBatchTimer = setTimeout(async () => {
      entryBatchAbort = new AbortController();
      const signal = entryBatchAbort.signal;
      try {
        const rows = await window.api.searchBillingBatches(q, '', 20, signal);
        if (!entryBatchGate.isCurrent(ticket) || signal.aborted) return;      // an older answer never replaces a newer one
        const opts = rows.map((r) => {
          const f = billFormatProductRow(r);
          const b = billToBatch(f);
          const st = billBatchState(b);
          return { selectable: st === 'ok' || st === 'near', why: batchWhy(st), value: f, html: batchOptionHtml({ ...b, name: f.name }, st, q, true) };
        });
        popupOpen({
          kind: 'entrybatch', anchor, query: q, width: 640, options: opts,
          head: '<span>Batch</span><span>Medicine</span><span>Expiry</span><span>Stock</span><span>MRP</span>',
          empty: 'No batch matches “' + esc(q) + '”',
          onPick: (o) => { billAddMedicine(o.value, { forceProductId: o.value.productId }); },
        });
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        if (entryBatchGate.isCurrent(ticket)) popupOpen({ kind: 'entrybatch', anchor, query: q, width: 520, options: [], empty: '⚠️ Could not search batches. Check the connection.', onPick: () => {} });
      }
    }, 200);
  }

  // ---------- unit dropdown ----------
  function openUnitPopupFor(key, typed) {
    const item = itemOfKey(key);
    const anchor = cellEl(key, 'unit');
    if (!item || !anchor) return;
    const units = gridUnitOptions(item);
    const opts = units.map((u) => ({
      selectable: u.selectable, value: u.value, label: u.label,
      html: u.value === 'strip'
        ? '<span class="bp-main">Strip</span><span class="bp-sub">full pack · ₹' + Number(item.packPrice || item.mrp || 0).toFixed(2) + ' each</span>'
        : '<span class="bp-main">Loose</span><span class="bp-sub">per tablet · ₹' + Number(item.loosePrice).toFixed(2) + ' each</span>',
    }));
    const at = typed ? gridMatchUnit(units, typed) : -1;
    const curUnit = item.unitType === 'loose' ? 'loose' : 'strip';
    const cur = Math.max(0, units.findIndex((u) => u.value === curUnit));
    const activeIndex = at >= 0 ? at : cur;

    setActive(key, 'unit');
    if (document.activeElement !== anchor && typeof anchor.focus === 'function') {
      anchor.focus();
    }

    popupOpen({
      kind: 'unit', key, anchor, width: 300, options: opts, index: activeIndex,
      onPick: (o) => {
        const i = indexOfId(key);
        billSetUnit(i, o.value);
        if (typeof renderBillItemsTable === 'function') renderBillItemsTable(); else render();
        recalculateTotals();
        focusPos({ row: i, col: 'qty' });
      },
    });
  }
  // Switching Strip/Loose keeps the quantity inside what the stock allows.
  function billSetUnit(i, unitType) {
    const item = items()[i];
    if (!item) return;
    const changed = item.unitType !== unitType;
    item.unitType = unitType;
    if (changed && item.rateOverride) { item.rateOverride = null; billToast('The selling price was reset to the MRP of the new unit.', false); }
    item.rate = gridEffectiveRate(item);
    const v = gridValidateQty(String(item.quantity), item);
    if (!v.ok && v.limit >= 1) { item.quantity = v.limit; billToast('Quantity changed to ' + v.limit + ' (all that is in stock in this unit).', false); }
  }

  // ---------- batch apply (used by the Batch dropdown) ----------
  window.billApplyBatch = function (index, bData) {
    const item = items()[index];
    if (!item || !bData) return false;
    const st = billBatchState(bData);
    if (st === 'expired' || st === 'out') { billToast('Batch ' + (bData.batchNumber || '-') + ' ' + (st === 'expired' ? 'is expired' : 'has no stock') + ' and cannot be sold.', true); return false; }
    const clash = items().findIndex((o, j) => j !== index && gridSameLine(o, { productId: bData.productId || item.productId, selectedBatch: bData.batchNumber }));
    if (clash >= 0) { billToast('That batch is already on line ' + (clash + 1) + '. Change its quantity instead.', true); return false; }
    if (bData.productId) item.productId = bData.productId;
    item.selectedBatch = bData.batchNumber;
    item.expiryDate = bData.expiryDate;
    item.availableStock = bData.stock;
    item.packPrice = Number(bData.mrp);
    item.unitsPerPack = bData.unitsPerPack ? Number(bData.unitsPerPack) : (item.unitsPerPack || null);
    item.packSize = bData.packSize || item.packSize || '';
    item.loosePrice = bData.pricePerUnit ? Number(bData.pricePerUnit) : (item.unitsPerPack ? Number((item.packPrice / item.unitsPerPack).toFixed(2)) : null);
    if (item.unitType === 'loose' && !item.loosePrice) item.unitType = 'strip';
    if (item.rateOverride && !(Number(item.rateOverride) <= gridBaseRate(item) + 0.005)) {
      item.rateOverride = null;
      billToast('The selling price was above this batch\'s MRP, so it was reset to the MRP.', false);
    }
    item.rate = gridEffectiveRate(item);
    const v = gridValidateQty(String(item.quantity), item);
    if (!v.ok && v.limit >= 1) { item.quantity = v.limit; billToast('Quantity changed to ' + v.limit + ' (stock of this batch).', false); }
    return true;
  };

  // ---------- rendering ----------
  function rowWarn(item) { return billRowWarning(item); }

  const roCell = (col, html, cls) => '<td class="c-ro' + (cls ? ' ' + cls : '') + '"><div class="cell-ro" tabindex="-1" data-cell="' + col + '">' + html + '</div></td>';

  function lineRowHtml(item, idx) {
    const key = item.id;
    const expState = billBatchState({ expiryDate: item.expiryDate, stock: item.availableStock });
    const expClass = expState === 'expired' ? 'exp-bad' : expState === 'near' ? 'exp-warn' : '';
    const sub = [item.brand, item.composition].filter(Boolean).join(' • ');
    const mrp = gridBaseRate(item);
    return '<tr data-row="' + idx + '" data-rid="' + esc(key) + '">' +
      '<td class="c-no">' + (idx + 1) + '</td>' +
      '<td class="c-edit c-prod"><input class="cell-input" data-cell="product" autocomplete="off" spellcheck="false" value="' + esc(item.name) + '" title="' + esc(item.name + (sub ? ' — ' + sub : '') + ' · type to change the medicine') + '"><div class="cell-note" id="bill-row-warn-' + idx + '">' + rowWarn(item) + '</div></td>' +
      roCell('packing', esc(item.packSize || '-')) +
      '<td class="c-edit"><input class="cell-input" data-cell="batch" value="' + esc(item.selectedBatch || '') + '" autocomplete="off" title="Type to filter the batches · Space or Alt+↓ shows them all"></td>' +
      roCell('expiry', esc(item.expiryDate || '-'), expClass) +
      '<td class="c-edit"><input class="cell-input c-center" data-cell="unit" readonly value="' + (item.unitType === 'loose' ? 'Loose' : 'Strip') + '" title="Enter or Space opens the list" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-controls="bill-cell-popup" aria-label="Billing unit"></td>' +
      '<td class="c-edit"><input class="cell-input c-center item-qty-input" data-cell="qty" inputmode="numeric" autocomplete="off" value="' + esc(item.quantity) + '"></td>' +
      roCell('mrp', '₹' + mrp.toFixed(2), 'c-num') +
      '<td class="c-edit"><input class="cell-input c-num item-rate-input" data-cell="rate" inputmode="decimal" autocomplete="off" value="' + Number(item.rate).toFixed(2) + '" title="Selling price per unit. The MRP is the most you can charge."></td>' +
      '<td class="c-edit"><input class="cell-input c-center item-disc-input" data-cell="disc" inputmode="decimal" autocomplete="off" value="' + esc(item.discountPercent) + '"></td>' +
      roCell('gst', Number(item.gstRate) + '%', 'c-center') +
      roCell('amount', '<span id="bill-row-amount-' + idx + '">₹' + billRowAmount(item).toFixed(2) + '</span>', 'c-num c-amount') +
      '<td class="c-act"><button type="button" class="cell-del" tabindex="-1" onclick="removeBillItem(' + idx + ')" title="Remove this line (Ctrl+Delete)">🗑️</button></td>' +
      '</tr>';
  }

  function entryRowHtml(n, productText, batchText) {
    return '<tr data-entry="1" class="entry-row">' +
      '<td class="c-no">' + (n + 1) + '</td>' +
      '<td class="c-edit"><input class="cell-input" data-cell="product" id="bill-medicine-search-input" type="text" autocomplete="off" spellcheck="false" ' +
      'placeholder="Type 2–3 letters of the medicine, composition, code or barcode…" value="' + esc(productText) + '" oninput="handleMedicineSearchInput(this.value)">' +
      '<span id="bill-search-loading-spinner" class="search-spinner-inline" style="display:none;"></span></td>' +
      '<td class="c-ro"></td>' +
      '<td class="c-edit"><input class="cell-input" data-cell="batch" id="bill-entry-batch" autocomplete="off" placeholder="or batch no." value="' + esc(batchText) + '"></td>' +
      '<td class="c-ro"></td><td class="c-ro"></td><td class="c-ro"></td><td class="c-ro"></td><td class="c-ro"></td><td class="c-ro"></td><td class="c-ro"></td><td class="c-ro"></td><td class="c-act"></td></tr>';
  }

  function render() {
    const tbody = $('bill-items-table-body');
    if (!tbody) return;
    ensureIds();
    // remember where the cursor was so a redraw never loses it
    const ae = document.activeElement;
    let keep = null;
    if (ae && tbody.contains(ae) && ae.getAttribute('data-cell')) {
      const pos = posOfEl(ae);
      keep = { key: pos.key, col: pos.col, start: ae.selectionStart, end: ae.selectionEnd };
    }
    const prodInp = $('bill-medicine-search-input');
    const batchInp = $('bill-entry-batch');
    const productText = prodInp ? prodInp.value : '';
    const batchText = batchInp ? batchInp.value : '';
    const n = items().length;
    const badge = $('bill-item-count-badge');
    if (badge) badge.textContent = n + ' lines • ' + items().reduce((s, i) => s + (Number(i.quantity) || 0), 0) + ' units';
    tbody.innerHTML = items().map(lineRowHtml).join('') + entryRowHtml(n, productText, batchText);
    if (keep) {
      if (keep.key !== 'entry' && !rowEl(keep.key)) keep = { key: 'entry', col: 'product' };
      const el = cellEl(keep.key, keep.col);
      if (el) {
        setActive(keep.key, keep.col);
        el.focus();
        if (el.tagName === 'INPUT') billGrid.searchEl = el.getAttribute('data-cell') === 'product' ? el : billGrid.searchEl;
        if (keep.start !== null && keep.start !== undefined && el.setSelectionRange && !el.readOnly) { try { el.setSelectionRange(keep.start, keep.end); } catch (e) { /* not selectable */ } }
      }
    } else if (billGrid.active) {
      setActive(billGrid.active.key, billGrid.active.col);
    }
    billTabsRender();
  }
  window.billGridRender = render;

  // After a medicine is added: the cursor goes to its Batch cell with the batch list open.
  // A new / switched bill starts with an empty entry row (nothing typed carries over from another bill).
  window.billClearEntryRow = function () {
    entryBatchGate.next();                                   // a batch answer still on its way is stale
    clearTimeout(entryBatchTimer);
    if (entryBatchAbort) { entryBatchAbort.abort(); entryBatchAbort = null; }
    const b = $('bill-entry-batch');
    if (b) b.value = '';
    const p = $('bill-medicine-search-input');
    if (p) p.value = '';
    popupClose();                                            // no list of a previous bill / line stays open
    closeProductDropdown();
  };

  window.billGridAfterAdd = function (rowId) {
    const i = indexOfId(rowId);
    if (i < 0) return;
    focusPos({ row: i, col: 'batch' });
    openBatchPopupFor(rowId, '');
    billLoadBatches(rowId);
  };

  // The medicine's other batches come from the server for exactly this medicine (not the whole catalogue).
  const batchLoadTicket = new Map();
  async function billLoadBatchesImpl(rowId) {
    const item = itemOfKey(rowId);
    if (!item || !window.api || typeof window.api.searchBillingBatches !== 'function') return;
    const ticket = (batchLoadTicket.get(rowId) || 0) + 1;
    batchLoadTicket.set(rowId, ticket);
    try {
      const rows = await window.api.searchBillingBatches('', item.name, 50);
      if (batchLoadTicket.get(rowId) !== ticket) return;
      const live = itemOfKey(rowId);
      if (!live) return;
      const fresh = rows.map((r) => billToBatch(billFormatProductRow(r)));
      const byId = new Map();
      (live.batches || []).concat(fresh).forEach((b) => { if (b && b.productId !== undefined) byId.set(String(b.productId), b); });
      fresh.forEach((b) => byId.set(String(b.productId), b));
      live.batches = [...byId.values()].sort((a, b) => (a.expiryDate || '9999-12-31').localeCompare(b.expiryDate || '9999-12-31'));
      reconcileWithServer(rowId, fresh);
      const p = billGrid.popup;
      if (p && p.kind === 'batch' && p.key === rowId) {
        const q = p.query || '';
        const cur = itemBatchOptions(live, q);
        popupRefresh(cur, q);
        const at = cur.findIndex((o) => o.value.productId === live.productId);
        if (at >= 0 && !q) { billGrid.popup.index = at; popupDraw(); }
      }
    } catch (err) {
      console.warn('Could not load the batches of', item.name, err);
    }
  }
  function billLoadBatches(rowId) { return billLoadBatchesImpl(rowId); }

  // The search list is a hint; the server's batches are the truth. If the chosen batch is gone, expired or empty now,
  // say so and take the next valid batch (never silently); if none is left, the line shows the problem and saving is blocked.
  function reconcileWithServer(rowId, fresh) {
    const i = indexOfId(rowId);
    const item = items()[i];
    if (!item) return;
    const cur = fresh.find((b) => String(b.productId) === String(item.productId));
    if (cur && billBatchSellable(cur)) {
      if (Number(cur.stock) !== Number(item.availableStock) || cur.expiryDate !== item.expiryDate) {
        item.availableStock = cur.stock;
        item.expiryDate = cur.expiryDate;
        billUpdateRow(i);
        if (item.unitType !== 'loose' && Number(item.quantity) > Number(cur.stock)) billToast(item.name + ': only ' + cur.stock + ' in stock now.', true);
      }
      return;
    }
    const next = fresh.find((b) => billBatchSellable(b) && !items().some((o, j) => j !== i && gridSameLine(o, { productId: b.productId, selectedBatch: b.batchNumber })));
    const was = item.selectedBatch || '-';
    if (next) {
      billApplyBatch(i, next);
      billToast(item.name + ': batch ' + was + ' is no longer available. Batch ' + next.batchNumber + ' was taken instead.', true);
    } else {
      item.availableStock = 0;
      billToast(item.name + ': no stock left on the server. Remove this line.', true);
    }
    const keep = billGrid.active;
    popupClose();
    renderBillItemsTable();
    recalculateTotals();
    if (keep) { const r = indexOfId(keep.key); if (r >= 0) focusPos({ row: r, col: keep.col }); }
  }

  // ---------- cell commit / revert ----------
  function showCellError(el, msg) {
    el.classList.add('cell-error');
    el.title = msg;
    billToast(msg, true);
  }
  function clearCellError(el) { el.classList.remove('cell-error'); }

  // Returns true when the cell may be left.
  function commitCell(el) {
    const pos = posOfEl(el);
    if (!pos) return true;
    const item = itemOfKey(pos.key);
    if (pos.col === 'qty' && item) {
      const v = gridValidateQty(el.value, item);
      if (!v.ok) { showCellError(el, v.error); return false; }
      clearCellError(el);
      item.quantity = v.value;
      el.value = String(v.value);
    } else if (pos.col === 'disc' && item) {
      const v = gridValidateDiscount(el.value);
      if (!v.ok) { showCellError(el, v.error); return false; }
      clearCellError(el);
      item.discountPercent = v.value;
      el.value = String(v.value);
    } else if (pos.col === 'rate' && item) {
      const v = gridValidateRate(el.value, gridBaseRate(item));
      if (!v.ok) { showCellError(el, v.error); return false; }
      clearCellError(el);
      applyRate(item, v.value);
      el.value = Number(item.rate).toFixed(2);
    } else if (pos.col === 'batch' && item) {
      el.value = item.selectedBatch || '';                          // typed filter text that was not picked is dropped
    } else if (pos.col === 'product' && item) {
      if (el.value !== item.name) { el.value = item.name; billGrid.replaceKey = null; closeProductDropdown(); }   // typed but not picked: the medicine stays
    }
    if (item) { recalculateTotals(); billUpdateRow(pos.row); }
    return true;
  }
  // A selling price equal to the MRP is "no override"; a lower one is kept on the line (the master record is never touched).
  function applyRate(item, value) {
    item.rateOverride = value >= gridBaseRate(item) - 0.005 ? null : value;
    item.rate = gridEffectiveRate(item);
  }
  function revertCell(el) {
    const pos = posOfEl(el);
    if (!pos) return;
    const item = itemOfKey(pos.key);
    clearCellError(el);
    if (pos.col === 'qty' && item) el.value = String(item.quantity);
    else if (pos.col === 'disc' && item) el.value = String(item.discountPercent);
    else if (pos.col === 'rate' && item) el.value = Number(item.rate).toFixed(2);
    else if (pos.col === 'batch' && item) el.value = item.selectedBatch || '';
    else if (pos.col === 'product' && item) { el.value = item.name; billGrid.replaceKey = null; closeProductDropdown(); }
    else if (pos.col === 'batch' && pos.key === 'entry') el.value = '';
    else if (pos.col === 'product' && pos.key === 'entry') clearMedicineSearch(false);
  }

  // ---------- keyboard ----------
  function move(pos, kind, el) {
    const n = items().length;
    let next = null;
    if (kind === 'tab') next = gridTab(pos, false, n);
    else if (kind === 'shifttab') next = gridTab(pos, true, n);
    else if (kind === 'enter') next = gridEnter(pos, n);
    if (next) focusPos(next);
  }

  const isTextCell = (el) => el.tagName === 'INPUT' && !el.readOnly;
  const productDirty = (el, pos, item) => (pos.key === 'entry' ? el.value.trim() !== '' : !!item && el.value !== item.name);

  function onGridKeydown(e) {
    const el = e.target && e.target.closest ? e.target.closest('[data-cell]') : null;
    const key = e.key;
    const n = items().length;

    // ----- CRITICAL: While the Unit dropdown is open, ArrowUp and ArrowDown must control its options, not move between billing rows. -----
    // Use preventDefault() and stopPropagation() to prevent the parent grid from intercepting dropdown navigation.
    const isUnitPopupOpen = billGrid.popup && billGrid.popup.kind === 'unit';
    if (isUnitPopupOpen) {
      if (key === 'ArrowDown' || key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        popupMove(key === 'ArrowDown' ? 1 : -1);
        return;
      }
      if (key === 'Enter' || key === ' ') {
        e.preventDefault();
        e.stopPropagation();
        popupPick(billGrid.popup.index);
        return;
      }
      if (key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        const anchor = billGrid.popup.anchor;
        popupClose();
        if (anchor && typeof anchor.focus === 'function') anchor.focus();
        else if (el) { const pos = posOfEl(el); if (pos) focusPos({ row: pos.row, col: 'unit' }); }
        return;
      }
      if (key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        popupPick(billGrid.popup.index);
        return;
      }
      if (key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        e.stopPropagation();
        const at = gridMatchUnit(billGrid.popup.options, key);
        if (at >= 0) {
          billGrid.popup.index = at;
          popupDraw();
        }
        return;
      }
    }

    if (!el) return;
    const pos = posOfEl(el);
    if (!pos) return;
    setActive(pos.key, pos.col);
    const entry = pos.key === 'entry';
    const item = itemOfKey(pos.key);
    const popupHere = billGrid.popup && (billGrid.popup.anchor === el);
    const prodOpen = pos.col === 'product' && productDropdownOpen();

    // Alt+Down / F4 / Space show the list of a Batch cell; Unit also opens with Enter or Space
    if (!entry && !popupHere && (pos.col === 'batch' || pos.col === 'unit')) {
      if ((key === 'ArrowDown' && e.altKey) || key === 'F4' || (key === ' ' && pos.col === 'unit') ||
          (key === ' ' && pos.col === 'batch' && el.selectionStart === el.selectionEnd && el.value === (item ? item.selectedBatch || '' : ''))) {
        e.preventDefault();
        e.stopPropagation();
        if (pos.col === 'batch') openBatchPopupFor(pos.key, ''); else openUnitPopupFor(pos.key);
        return;
      }
      if (pos.col === 'unit' && key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        openUnitPopupFor(pos.key);
        return;
      }
      if (pos.col === 'unit' && key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey && /^[a-zA-Z]$/.test(key)) {
        e.preventDefault();
        e.stopPropagation();
        openUnitPopupFor(pos.key, key);
        return;
      }
    }
    if (e.ctrlKey || e.altKey || e.metaKey) return;                   // the screen's shortcuts handle these

    // ----- a list is open: it owns Up / Down / Enter / Tab -----
    if (popupHere || prodOpen) {
      if (key === 'ArrowDown' || key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        if (prodOpen) handleSearchKeydown(e); else popupMove(key === 'ArrowDown' ? 1 : -1);
        return;
      }
      if (key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        if (prodOpen) handleSearchKeydown(e); else popupPick(billGrid.popup.index);
        return;
      }
      if (key === 'Tab') {
        e.preventDefault();
        e.stopPropagation();
        if (popupHere && billGrid.popup.kind === 'unit') {              // a Unit choice is always a valid one: Tab confirms it
          const i = billGrid.popup.index;
          popupPick(i);
          return;
        }
        popupClose(); closeProductDropdown();                           // Tab never picks a medicine or batch: it must not choose the wrong one
        if (!commitCell(el)) return;
        focusPos(gridTab(pos, e.shiftKey, n));
        return;
      }
    }

    switch (key) {
      case 'Enter': {
        e.preventDefault();
        if (pos.col === 'product' && productDirty(el, pos, item)) {
          if (billSearchPending) { billPendingEnter = true; return; }  // scanner: add as soon as the answer arrives
          billPendingEnter = true;                                    // instant search uses it at once ...
          handleMedicineSearchInput(el.value.trim());
          billPendingEnter = billSearchPending;                       // ... the server search when its answer comes
          return;
        }
        if (entry && pos.col === 'batch') { if (!el.value.trim()) focusPos({ row: n, col: 'product' }); return; }
        if (!entry && pos.col === 'unit') {
          e.stopPropagation();
          openUnitPopupFor(pos.key);
          return;
        }
        if (!commitCell(el)) return;
        focusPos(gridEnter(pos, n));
        return;
      }
      case 'Escape': {
        if (billGrid.popup) {
          e.preventDefault();
          e.stopPropagation();
          const anchor = billGrid.popup.anchor;
          popupClose();
          if (anchor && typeof anchor.focus === 'function') anchor.focus();
          return;
        }
        break;
      }
      case 'Tab': {
        if (entry && pos.col === 'batch' && !e.shiftKey && !el.value.trim()) {
          const dm = $('bill-discount-mode');
          e.preventDefault();
          if (dm) dm.focus(); else focusPos({ row: n, col: 'product' });
          return;
        }
        if (!commitCell(el)) { e.preventDefault(); return; }
        const next = gridTab(pos, e.shiftKey, n);
        if (next.row === pos.row && next.col === pos.col) return;     // edge of the grid: let the browser go on
        e.preventDefault();
        popupClose(); closeProductDropdown();
        focusPos(next);
        return;
      }
      case 'ArrowDown':
      case 'ArrowUp': {
        if (pos.col === 'product' && key === 'ArrowDown' && productDirty(el, pos, item) && (window._lastSearchResults || []).length) {
          e.preventDefault();                                         // Down re-opens the suggestions
          const dd = $('bill-search-results-dropdown'); dd.style.display = 'block'; billPlacePopup(dd);
          return;
        }
        if (!commitCell(el)) { e.preventDefault(); return; }
        e.preventDefault();
        focusPos(gridVertical(pos, key === 'ArrowDown' ? 1 : -1, n));
        return;
      }
      case 'ArrowLeft':
      case 'ArrowRight': {
        const caret = isTextCell(el) ? { start: el.selectionStart, end: el.selectionEnd, length: el.value.length } : null;
        const next = gridHorizontal(pos, key === 'ArrowRight' ? 1 : -1, n, caret);
        if (!next) return;                                            // still editing the text
        if (!commitCell(el)) { e.preventDefault(); return; }
        e.preventDefault();
        focusPos(next);
        return;
      }
      default:
        // type-ahead in the Unit cell: "l" opens the list on Loose
        if (!entry && pos.col === 'unit' && key.length === 1 && !e.ctrlKey && !e.altKey && key !== ' ') {
          e.preventDefault();
          e.stopPropagation();
          openUnitPopupFor(pos.key, key);
        }
        break;
    }
  }

  // typing in cells
  function onGridInput(e) {
    const el = e.target;
    const col = el.getAttribute && el.getAttribute('data-cell');
    if (!col) return;
    const pos = posOfEl(el);
    if (!pos) return;
    const item = itemOfKey(pos.key);
    if (col === 'qty' && item) {
      const v = gridValidateQty(el.value, item);
      if (v.ok) { clearCellError(el); item.quantity = v.value; recalculateTotals(); billUpdateRow(pos.row); } else { el.classList.add('cell-error'); el.title = v.error; }
    } else if (col === 'disc' && item) {
      const v = gridValidateDiscount(el.value);
      if (v.ok) { clearCellError(el); item.discountPercent = v.value; recalculateTotals(); billUpdateRow(pos.row); } else { el.classList.add('cell-error'); el.title = v.error; }
    } else if (col === 'rate' && item) {
      const v = gridValidateRate(el.value, gridBaseRate(item));
      if (v.ok) { clearCellError(el); applyRate(item, v.value); recalculateTotals(); billUpdateRow(pos.row); } else { el.classList.add('cell-error'); el.title = v.error; }
    } else if (col === 'product' && item) {
      billGrid.replaceKey = pos.key; billGrid.searchEl = el;           // a different medicine for THIS line
      handleMedicineSearchInput(el.value);
    } else if (col === 'product' && pos.key === 'entry') {
      billGrid.replaceKey = null; billGrid.searchEl = el;
    } else if (col === 'batch' && item) {
      openBatchPopupFor(pos.key, el.value.trim() === (item.selectedBatch || '') ? '' : el.value.trim());
    } else if (col === 'batch' && pos.key === 'entry') {
      searchEntryBatch(el.value.trim());
    }
  }

  function onGridFocusin(e) {
    const el = e.target;
    if (!el.getAttribute || !el.getAttribute('data-cell')) return;
    const pos = posOfEl(el);
    if (!pos) return;
    setActive(pos.key, pos.col);
    if (billGrid.popup && billGrid.popup.anchor !== el) popupClose();
    if (pos.col === 'product') {
      if (billGrid.searchEl !== el) closeProductDropdown();
      billGrid.searchEl = el; billGrid.replaceKey = pos.key === 'entry' ? null : pos.key;
    }
    if (typeof el.select === 'function' && !el.readOnly) { try { el.select(); } catch (err) { /* not selectable */ } }
  }
  function onGridFocusout(e) {
    const el = e.target;
    if (!el.getAttribute || !el.getAttribute('data-cell')) return;
    setTimeout(() => {
      if (!document.hasFocus() || document.activeElement === el) return;
      const pos = posOfEl(el);
      if (billGrid.popup && billGrid.popup.anchor === el && !(document.activeElement && document.activeElement.closest && document.activeElement.closest('#bill-cell-popup'))) popupClose();
      if (pos && !el.isConnected) return;
      if (pos && (pos.col === 'qty' || pos.col === 'disc' || pos.col === 'rate')) {
        const item = itemOfKey(pos.key);
        if (item && !commitCellQuiet(el, pos, item)) revertCell(el);   // left with a bad value: put back the last good one
      } else if (pos && pos.col === 'batch') {
        const item = itemOfKey(pos.key);
        if (item) el.value = item.selectedBatch || '';
      } else if (pos && pos.col === 'product' && pos.key !== 'entry') {
        const item = itemOfKey(pos.key);
        if (item && el.value !== item.name) { el.value = item.name; billGrid.replaceKey = null; closeProductDropdown(); }
      }
    }, 0);
  }
  function commitCellQuiet(el, pos, item) {
    if (pos.col === 'qty') { const v = gridValidateQty(el.value, item); if (!v.ok) return false; item.quantity = v.value; el.value = String(v.value); }
    else if (pos.col === 'rate') { const v = gridValidateRate(el.value, gridBaseRate(item)); if (!v.ok) return false; applyRate(item, v.value); el.value = Number(item.rate).toFixed(2); }
    else { const v = gridValidateDiscount(el.value); if (!v.ok) return false; item.discountPercent = v.value; el.value = String(v.value); }
    clearCellError(el);
    recalculateTotals(); billUpdateRow(pos.row);
    return true;
  }
  function onGridClick(e) {
    const el = e.target.closest && e.target.closest('[data-cell]');
    if (!el) return;
    const pos = posOfEl(el);
    if (!pos || pos.key === 'entry') return;
    if (pos.col === 'batch') openBatchPopupFor(pos.key, '');
    else if (pos.col === 'unit') {
      if (typeof el.focus === 'function') el.focus();
      openUnitPopupFor(pos.key);
    }
  }

  // True when the cell the cursor is in holds a valid value (or nothing was being edited). A bad value keeps the cursor there.
  window.billGridCommitActive = function () {
    const el = document.activeElement;
    if (!el || !el.getAttribute || !el.getAttribute('data-cell') || !$('bill-items-table-body') || !$('bill-items-table-body').contains(el)) return true;
    return commitCell(el);
  };
  function productDropdownOpenGlobal() { return productDropdownOpen(); }
  window.productDropdownOpen = productDropdownOpenGlobal;

  // Esc: close the list / cancel an unfinished edit. Returns true when it did something (then Esc does not also clear the bill).
  window.billGridEscape = function (e) {
    if (!onGridPage()) return false;
    const consume = () => { e.preventDefault(); e.stopPropagation(); };
    const t = e.target;
    if (t && (t.id === 'bill-discount-input' || t.id === 'bill-discount-mode')) { consume(); focusEntryProduct(); return true; }
    if (billGrid.popup) {
      const wasParty = billGrid.popup.kind === 'party';
      const anchor = billGrid.popup.anchor;
      popupClose();
      if (wasParty) billSyncPartyInput();
      else if (anchor && typeof anchor.focus === 'function') anchor.focus();
      else if (t && t.getAttribute && t.getAttribute('data-cell')) revertCell(t);
      consume();
      return true;
    }
    const dd = $('bill-search-results-dropdown');
    if (dd && dd.style.display === 'block') { dd.style.display = 'none'; consume(); return true; }
    if (t && t.getAttribute && t.getAttribute('data-cell')) {
      const pos = posOfEl(t);
      const item = pos && itemOfKey(pos.key);
      const dirty = (pos.col === 'qty' && item && t.value !== String(item.quantity)) ||
        (pos.col === 'disc' && item && t.value !== String(item.discountPercent)) ||
        (pos.col === 'rate' && item && t.value !== Number(item.rate).toFixed(2)) ||
        (pos.col === 'batch' && t.value !== (item ? item.selectedBatch || '' : '')) ||
        (pos.col === 'product' && (pos.key === 'entry' ? t.value !== '' : !!item && t.value !== item.name));
      if (dirty) { revertCell(t); consume(); return true; }
    }
    return false;
  };

  // ---------- wiring ----------
  function init() {
    const tb = $('bill-items-table-body');
    if (!tb || tb.__gridWired) return;
    tb.__gridWired = true;
    if (!$('bill-search-results-dropdown')) {                 // the medicine list (filled by billing_flow.js), drawn under the Product cell
      const dd = document.createElement('div');
      dd.id = 'bill-search-results-dropdown';
      dd.className = 'billing-search-dropdown';
      dd.addEventListener('mousedown', (e) => e.preventDefault());
      document.body.appendChild(dd);
    }
    tb.addEventListener('keydown', onGridKeydown);
    tb.addEventListener('input', onGridInput);
    tb.addEventListener('focusin', onGridFocusin);
    tb.addEventListener('focusout', onGridFocusout);
    tb.addEventListener('click', onGridClick);
    const party = $('bill-party-input');
    if (party) {
      party.addEventListener('keydown', onPartyKeydown);
      party.addEventListener('input', () => openPartyPopup(party.value.trim()));
      party.addEventListener('focus', () => { party.select(); });
      party.addEventListener('blur', () => setTimeout(() => {
        if (document.activeElement !== party && billGrid.popup && billGrid.popup.kind === 'party') popupClose();
        if (document.activeElement !== party) billSyncPartyInput();
      }, 0));
      party.addEventListener('click', () => { if (!billGrid.popup) openPartyPopup(''); });
    }
    // Bill Discount box: % / ₹ by keyboard (type % or ₹, or use the arrow keys), Enter moves on, Esc goes back to the grid
    const dm = $('bill-discount-mode');
    const di = $('bill-discount-input');
    if (dm) {
      dm.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        const pick = (mode) => { e.preventDefault(); dm.value = mode; handleBillDiscountModeChange(mode); };
        if (e.key === '%') pick('percent');
        else if (e.key === '₹' || /^[rRfF]$/.test(e.key)) pick('flat');
        else if (e.key === 'Enter') { e.preventDefault(); if (di) { di.focus(); di.select(); } }
      });
    }
    if (di) {
      di.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.ctrlKey && !e.altKey) { e.preventDefault(); focusEntryProduct(); }
      });
      di.addEventListener('focus', () => di.select());
    }
    const reposition = () => {
      const p = billGrid.popup;
      if (p && p.anchor && p.anchor.isConnected) placeAt($('bill-cell-popup'), p.anchor, p.width || 420, Math.min($('bill-cell-popup').scrollHeight + 4, 360));
      const dd = $('bill-search-results-dropdown');
      if (dd && dd.style.display === 'block') billPlacePopup(dd);
    };
    window.addEventListener('resize', reposition);
    document.addEventListener('scroll', reposition, true);
    // a click anywhere else closes the lists
    document.addEventListener('mousedown', (e) => {
      if (!billGrid.popup) return;
      if (e.target.closest && (e.target.closest('#bill-cell-popup') || e.target === billGrid.popup.anchor)) return;
      popupClose();
    });
    billSyncPartyInput();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  window.billGridInit = init;
})();
