/*
 * Browser regression run for the Create New Bill spreadsheet grid.
 *
 * It drives the real page (real keyboard events, real search endpoints, the real save endpoint), so it needs:
 *   - the web app open on /web/billing.html, signed in to a TEST pharmacy (never real data: it saves real bills and takes stock);
 *   - this seed data (tests/browser/README.md): PARACETAMOL 500 with batches PCM-OLD (expired, stock 5), PCM-NEAR (30 days, stock 12),
 *     PCM-FAR (400 days, stock 40, MRP 34, GST 12); and BULK MEDICINE 0000..1199 with batch B0000..B1199, 10+ in stock.
 * Run:  paste the file into the page console (or load it as a script), then   await runBillingGridE2E()
 * Returns [{ name, ok, detail }]; also prints a table.
 */
window.runBillingGridE2E = async function () {
  const results = [];
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const until = async (fn, ms = 4000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (fn()) return true; await wait(40); } return false; };
  const $ = (id) => document.getElementById(id);
  const items = () => activeBillState.items;
  const key = (k, o = {}) => { const el = document.activeElement; return !el.dispatchEvent(new KeyboardEvent('keydown', Object.assign({ key: k, bubbles: true, cancelable: true }, o))); };
  const typeInto = (txt) => { const el = document.activeElement; el.value = txt; el.dispatchEvent(new Event('input', { bubbles: true })); };
  const where = () => {
    const a = document.activeElement; const tr = a.closest && a.closest('tr');
    return tr ? (tr.hasAttribute('data-entry') ? 'entry' : 'row' + tr.dataset.row) + ':' + a.dataset.cell : a.id;
  };
  const popupText = () => { const p = $('bill-cell-popup'); return p && p.style.display !== 'none' ? p.innerText.replace(/\n/g, ' | ') : null; };
  const focusCell = (row, col) => billGridFocusPos({ row, col });
  const freshBill = async () => { resetBillForm(); await wait(60); };
  const addMed = async (q) => {
    focusCell(items().length, 'product'); typeInto(q);
    await until(() => (window._lastSearchResults || []).length > 0 && $('bill-search-results-dropdown').style.display === 'block');
    key('Enter'); await until(() => where().endsWith(':batch') && !where().startsWith('entry'));
  };
  const closeList = () => { if (billGrid.popup) key('Escape'); };
  const near = (a, b) => Math.abs(a - b) < 0.005;
  const savedAlert = []; const realAlert = window.alert; window.alert = (m) => savedAlert.push(m);
  const realOpen = window.open;

  async function test(name, fn) {
    try { await freshBill(); const d = await fn(); results.push({ name, ok: true, detail: d || '' }); }
    catch (e) { results.push({ name, ok: false, detail: String(e && e.message || e) }); }
  }
  const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

  await test('new bill starts in Party Name; Enter on the party goes straight to the first Product cell', async () => {
    expect(where() === 'bill-party-input', 'start was ' + where());
    key('Enter'); expect(where() === 'entry:product', 'after party: ' + where());
    expect(activeBillState.customer.name === 'Walk-in Customer', 'default party');
  });

  await test('party search: typing opens the list, Walk-in/Cash Sale is offered, picking it leads to Product', async () => {
    typeInto('cash'); expect(popupText() && /Walk-in/.test(popupText()), 'list: ' + popupText());
    key('Enter'); expect(where() === 'entry:product', where());
  });

  await test('product: typing + arrows + Enter picks the highlighted medicine and moves to its Batch cell', async () => {
    key('Enter'); focusCell(0, 'product'); typeInto('bulk medicine 000');
    await until(() => (window._lastSearchResults || []).length >= 2);
    const second = window._lastSearchResults[1];
    key('ArrowDown');
    expect(where() === 'entry:product', 'arrow inside the list must not leave the cell: ' + where());
    key('Enter'); await until(() => items().length === 1);
    expect(items()[0].name === second.name, `picked ${items()[0].name}, wanted ${second.name}`);
    expect(where() === 'row0:batch' && billGrid.popup, 'focus ' + where());
    return second.name;
  });

  await test('product list is anchored under the cell, outside the grid box, and highlights the typed text', async () => {
    focusCell(0, 'product'); typeInto('paracet'); await until(() => (window._lastSearchResults || []).length > 0 && $('bill-search-results-dropdown').style.display === 'block');
    const dd = $('bill-search-results-dropdown'); const inp = $('bill-medicine-search-input');
    const a = inp.getBoundingClientRect(); const b = dd.getBoundingClientRect();
    expect(dd.parentElement === document.body, 'not attached to body');
    expect(Math.abs(b.left - a.left) < 2 && b.top >= a.bottom - 1, `box ${JSON.stringify([a.left, a.bottom, b.left, b.top])}`);
    expect(b.bottom <= window.innerHeight + 1, 'popup runs off the bottom of the screen');
    expect(dd.querySelectorAll('mark').length > 0, 'no highlighted match');
    key('Escape'); expect($('bill-search-results-dropdown').style.display === 'none', 'Esc did not close');
  });

  await test('product list flips above the cell near the bottom of the screen', async () => {
    const p = gridPopupPlacement({ left: 100, top: window.innerHeight - 60, bottom: window.innerHeight - 30, width: 250 }, { width: 580, height: 400 }, { width: window.innerWidth, height: window.innerHeight });
    expect(p.placement === 'above' && p.top + p.maxHeight <= window.innerHeight - 60, JSON.stringify(p));
  });

  await test('batch cell, medicine chosen first: lists its batches (earliest valid first), expired shown but not selectable', async () => {
    await addMed('paracet');
    const t = popupText();
    expect(/PCM-NEAR/.test(t) && /PCM-FAR/.test(t) && /PCM-OLD/.test(t) && /EXPIRED/.test(t), t);
    const opts = billGrid.popup.options;
    expect(opts[0].value.batchNumber === 'PCM-NEAR' && opts[0].selectable, 'FEFO default');
    expect(opts.find((o) => o.value.batchNumber === 'PCM-OLD').selectable === false, 'expired selectable');
    return t.slice(0, 120);
  });

  await test('expired batch cannot be chosen (Enter is refused, the confirmed batch stays)', async () => {
    await addMed('paracet'); const before = items()[0].selectedBatch;
    const n = billGrid.popup.options.length; for (let i = 0; i < n; i++) key('ArrowDown');
    expect(billGrid.popup.options[billGrid.popup.index].value.batchNumber === 'PCM-OLD', 'not on PCM-OLD');
    key('Enter'); expect(items()[0].selectedBatch === before && billGrid.popup, 'expired batch got selected');
    const forced = items().length; billAddMedicine(Object.assign({}, window._lastSearchResults && window._lastSearchResults[0] || {}), { forceProductId: -1 });
    expect(items().length === forced, 'forced add of unknown batch created a line');
  });

  await test('typing in the Batch cell filters; Enter picks and fills expiry / MRP; never silently changes the batch before that', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch');
    expect(items()[0].selectedBatch === 'PCM-NEAR', 'changed by focusing');
    typeInto('far'); expect(billGrid.popup.options.length === 1 && billGrid.popup.options[0].value.batchNumber === 'PCM-FAR', popupText());
    key('Enter');
    expect(items()[0].selectedBatch === 'PCM-FAR' && items()[0].rate === 34 && /2027|2028/.test(items()[0].expiryDate), JSON.stringify(items()[0].selectedBatch));
    expect(where() === 'row0:unit', where());
  });

  await test('batch number typed WITHOUT a medicine: partial search shows batch + medicine; picking fills the whole line', async () => {
    focusCell(0, 'batch'); typeInto('B001');
    await until(() => popupText() && /BULK MEDICINE 0010/.test(popupText()));
    const t = popupText(); expect(/B0010/.test(t) && /BULK MEDICINE 0010/.test(t), t.slice(0, 200));
    typeInto('B0123'); await until(() => billGrid.popup && billGrid.popup.options.length === 1);
    key('Enter'); await until(() => items().length === 1);
    const it = items()[0];
    expect(it.name === 'BULK MEDICINE 0123' && it.selectedBatch === 'B0123' && it.expiryDate && it.packPrice > 0, JSON.stringify([it.name, it.selectedBatch, it.expiryDate]));
  });

  await test('expired batch found by its batch number is not selectable', async () => {
    focusCell(0, 'batch'); typeInto('PCM-OLD'); await until(() => billGrid.popup && billGrid.popup.options.length === 1);
    expect(billGrid.popup.options[0].selectable === false, 'selectable');
    key('Enter'); expect(items().length === 0, 'added an expired batch');
  });

  await test('Tab / Shift+Tab walk the editable cells and commit on the way', async () => {
    await addMed('paracet'); closeList();
    const seq = []; focusCell(0, 'product');
    for (let i = 0; i < 5; i++) { key('Tab'); seq.push(where()); }
    expect(seq.join(',') === 'row0:batch,row0:unit,row0:qty,row0:disc,entry:product', seq.join(','));
    const back = []; for (let i = 0; i < 3; i++) { key('Tab', { shiftKey: true }); back.push(where()); }
    expect(back.join(',') === 'row0:disc,row0:qty,row0:unit', back.join(','));
  });

  await test('Left/Right move cells only at the edge of the text; Up/Down move rows when no list is open', async () => {
    await addMed('bulk medicine 0007'); closeList(); await addMed('bulk medicine 0008'); closeList();
    focusCell(0, 'qty'); typeInto('12'); const el = document.activeElement; el.setSelectionRange(1, 1);
    key('ArrowRight'); expect(where() === 'row0:qty', 'moved while editing: ' + where());
    el.setSelectionRange(2, 2); key('ArrowRight'); expect(where() === 'row0:disc', where());
    key('ArrowLeft'); expect(where() === 'row0:qty', where());
    key('ArrowDown'); expect(where() === 'row1:qty', where()); key('ArrowUp'); expect(where() === 'row0:qty', where());
  });

  await test('Enter on the last field (Disc) goes to the next empty Product cell and creates NO row; repeated Enter adds nothing', async () => {
    await addMed('bulk medicine 0009'); closeList(); focusCell(0, 'disc');
    const n = items().length; key('Enter'); expect(where() === 'entry:product', where());
    key('Enter'); key('Enter'); key('Enter'); expect(items().length === n, 'rows ' + n + ' -> ' + items().length);
  });

  await test('picking a medicine with Enter three times quickly adds exactly one line', async () => {
    focusCell(0, 'product'); typeInto('bulk medicine 0030'); await until(() => (window._lastSearchResults || []).length > 0);
    key('Enter'); key('Enter'); key('Enter'); await wait(300);
    expect(items().filter((i) => i.name === 'BULK MEDICINE 0030').length === 1, 'duplicates');
  });

  await test('the same product + batch is never added twice; the cursor goes to the existing line quantity', async () => {
    await addMed('bulk medicine 0040'); closeList(); await wait(500); focusCell(1, 'product'); typeInto('bulk medicine 0040');
    await until(() => (window._lastSearchResults || []).length > 0); key('Enter'); await wait(300);
    expect(items().length === 1, 'rows ' + items().length); expect(where() === 'row0:qty', where());
  });

  await test('quantity: zero / negative / malformed / more than stock are refused and the cursor stays', async () => {
    await addMed('bulk medicine 0050'); closeList(); focusCell(0, 'qty');
    const stock = items()[0].availableStock;
    for (const bad of ['0', '-3', '2.5', '1e2', 'abc', '', String(stock + 1)]) {
      typeInto(bad); key('Enter');
      expect(where() === 'row0:qty' && items()[0].quantity === 1, `"${bad}" accepted: ${where()} qty=${items()[0].quantity}`);
    }
    typeInto('4'); key('Enter'); expect(items()[0].quantity === 4 && where() === 'row0:disc', 'valid quantity refused');
  });

  await test('discount: over 100 / malformed refused; 10 accepted', async () => {
    await addMed('bulk medicine 0051'); closeList(); focusCell(0, 'disc');
    typeInto('101'); key('Enter'); expect(where() === 'row0:disc', 'accepted 101');
    typeInto('x'); key('Enter'); expect(where() === 'row0:disc', 'accepted x');
    typeInto('10'); key('Enter'); expect(items()[0].discountPercent === 10, 'refused 10');
  });

  await test('amount, tax and bill total match the shared billing rules after every edit', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter');
    focusCell(0, 'qty'); typeInto('3'); key('Enter'); typeInto('10'); key('Enter');
    expect($('bill-row-amount-0').textContent === '₹102.82', $('bill-row-amount-0').textContent);
    await addMed('bulk medicine 0060'); closeList(); focusCell(1, 'qty'); typeInto('7'); key('Enter');
    const c = billComputeLines(items(), activeBillState.billDiscountPercent);
    expect(near(parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, '')), c.grandTotal), $('bill-grand-total-val').textContent + ' vs ' + c.grandTotal);
    expect(near(parseFloat($('bill-cgst-val').textContent.replace(/[^0-9.]/g, '')), c.cgst), 'cgst');
  });

  await test('deleting a line (Ctrl+Delete) removes only that line and leaves the others untouched', async () => {
    await addMed('bulk medicine 0070'); closeList(); await addMed('bulk medicine 0071'); closeList(); await addMed('bulk medicine 0072'); closeList();
    focusCell(0, 'qty'); typeInto('2'); key('Enter'); focusCell(2, 'qty'); typeInto('3'); key('Enter');
    const ids = items().map((i) => i.id);
    focusCell(1, 'qty'); key('Delete', { ctrlKey: true });
    expect(items().length === 2 && items()[0].id === ids[0] && items()[1].id === ids[2], 'ids ' + items().map((i) => i.id));
    expect(items()[0].quantity === 2 && items()[1].quantity === 3, 'quantities changed');
  });

  await test('Delete and Backspace never remove a row', async () => {
    await addMed('bulk medicine 0080'); closeList(); focusCell(0, 'batch'); key('Delete'); key('Backspace'); focusCell(0, 'product'); key('Delete'); key('Backspace');
    expect(items().length === 1, 'row removed');
  });

  await test('stale autocomplete: a slow older answer never replaces a newer one', async () => {
    const real = api.searchBillingProducts.bind(api); let calls = 0;
    api.searchBillingProducts = async (q, m, l, s) => { calls++; if (/0001/.test(q)) await wait(900); return real(q, m, l, s); };
    try {
      focusCell(0, 'product'); typeInto('bulk medicine 0001'); await wait(260);
      typeInto('bulk medicine 0002'); await wait(1500);
      const names = (window._lastSearchResults || []).map((r) => r.name);
      expect(names.length && names.every((n) => /0002/.test(n)), names.join(','));
    } finally { api.searchBillingProducts = real; }
  });

  await test('large catalogue: a search returns at most 15 rows and does not download the catalogue', async () => {
    const real = api.searchBillingProducts.bind(api); let limit = null; let bytes = 0;
    api.searchBillingProducts = async (q, m, l, s) => { limit = l; const r = await real(q, m, l, s); bytes = JSON.stringify(r).length; return r; };
    try {
      focusCell(0, 'product'); typeInto('bulk'); await until(() => (window._lastSearchResults || []).length > 0);
      expect(window._lastSearchResults.length <= 15 && limit === 15, 'rows ' + window._lastSearchResults.length + ' limit ' + limit);
      return bytes + ' bytes for 1200 medicines in stock';
    } finally { api.searchBillingProducts = real; }
  });

  await test('stock is checked again on the server: a quantity above stock is refused when saving', async () => {
    await addMed('bulk medicine 0090'); closeList();
    const it = items()[0]; let refused = false;
    try { await api.createSale({ items: [{ product_id: it.productId, quantity: 100000, unit_price: it.rate, unit_type: 'strip', discount: 0, gst_percentage: it.gstRate, batch_number: it.selectedBatch }], payment_method: 'CASH', customer_name: 'Walk-in Customer' }); }
    catch (e) { refused = true; }
    expect(refused, 'server accepted more than the stock');
  });

  await test('save twice quickly: only one sale is sent', async () => {
    await addMed('bulk medicine 0100'); closeList();
    const real = api.createSale.bind(api); let n = 0;
    api.createSale = async (p) => { n++; await wait(400); return real(p); };
    try { const a = commitBillTransaction(false, true); const b = commitBillTransaction(false, true); await Promise.all([a, b]); } finally { api.createSale = real; }
    expect(n === 1, 'sale requests: ' + n);
  });

  await test('network failure while saving: the bill stays on screen, same idempotency key, retry saves it once', async () => {
    await addMed('bulk medicine 0110'); closeList(); focusCell(0, 'qty'); typeInto('2'); key('Enter');
    const real = api.createSale.bind(api); const keyBefore = activeBillState.idempotencyKey; const snapshot = items().map((i) => i.id + ':' + i.quantity).join();
    savedAlert.length = 0; api.createSale = async () => { throw new Error('Failed to fetch'); };
    try { await commitBillTransaction(false, true); } finally { api.createSale = real; }
    expect(items().length === 1 && items().map((i) => i.id + ':' + i.quantity).join() === snapshot, 'bill was cleared after a failed save');
    expect(savedAlert.length === 1, 'user not told'); expect(activeBillState.idempotencyKey === keyBefore, 'key changed');
    await commitBillTransaction(false, true); expect(items().length === 0, 'retry did not save');
  });

  await test('printer / pop-up blocked after saving: the sale is saved once, the bill closes, the user is told', async () => {
    await addMed('bulk medicine 0120'); closeList();
    const real = api.createSale.bind(api); let n = 0; api.createSale = async (p) => { n++; return real(p); };
    window.open = () => null;
    try { await commitBillTransaction(true, false); } finally { api.createSale = real; window.open = realOpen; }
    expect(n === 1 && items().length === 0, `sales ${n}, lines left ${items().length}`);
  });

  await test('hold a bill (draft) and bring it back: lines, quantities and batches are restored', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'qty'); typeInto('2'); key('Enter');
    const before = items().map((i) => [i.name, i.selectedBatch, i.quantity].join('/')).join('|');
    await holdCurrentBill(); await wait(500);
    expect(items().length === 0, 'bill not cleared after hold');
    const held = await api.getHeldBills(); expect(held.length > 0, 'no held bill'); const h = held[0];
    await resumeHeldBillWeb(h.id); await until(() => items().length > 0);
    const after = items().map((i) => [i.name, i.selectedBatch, i.quantity].join('/')).join('|');
    expect(before === after, before + ' vs ' + after);
  });

  await test('keyboard only, party to saved bill: the invoice equals the screen', async () => {
    const savedBefore = (await api.request('/sales?skip=0&limit=1'))[0];
    key('Enter');                                                       // party (Walk-in) -> Product
    focusCell(0, 'product'); typeInto('bulk medicine 0130'); await until(() => (window._lastSearchResults || []).length > 0);
    key('Enter'); await until(() => where() === 'row0:batch'); key('Enter');   // product, batch
    key('Enter'); typeInto('3'); key('Enter'); typeInto('5'); key('Enter');    // unit, qty 3, disc 5%
    expect(where() === 'entry:product', where());
    const screen = parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, ''));
    key('F9'); await until(() => items().length === 0, 6000); await wait(400);
    const latest = (await api.request('/sales?skip=0&limit=1'))[0];
    expect(latest && (!savedBefore || latest.id !== savedBefore.id), 'no new sale');
    expect(near(Number(latest.total_amount), screen), `saved ${latest.total_amount} vs screen ${screen}`);
    return 'saved ' + latest.bill_number + ' ₹' + latest.total_amount;
  });

  window.alert = realAlert; window.open = realOpen;
  const bad = results.filter((r) => !r.ok);
  console.table(results.map((r) => ({ ok: r.ok ? 'PASS' : 'FAIL', name: r.name, detail: String(r.detail).slice(0, 120) })));
  window.__e2e = results;
  return { total: results.length, passed: results.length - bad.length, failed: bad.map((r) => r.name + ' — ' + r.detail) };
};
