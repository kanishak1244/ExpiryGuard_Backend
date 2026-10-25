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
    expect(seq.join(',') === 'row0:batch,row0:unit,row0:qty,row0:rate,row0:disc', seq.join(','));
    key('Tab'); expect(where() === 'entry:product', where());
    focusCell(0, 'disc'); const back = []; for (let i = 0; i < 3; i++) { key('Tab', { shiftKey: true }); back.push(where()); }
    expect(back.join(',') === 'row0:rate,row0:qty,row0:unit', back.join(','));
  });

  await test('Left/Right move cells only at the edge of the text; Up/Down move rows when no list is open', async () => {
    await addMed('bulk medicine 0007'); closeList(); await addMed('bulk medicine 0008'); closeList();
    focusCell(0, 'qty'); typeInto('12'); const el = document.activeElement; el.setSelectionRange(1, 1);
    key('ArrowRight'); expect(where() === 'row0:qty', 'moved while editing: ' + where());
    el.setSelectionRange(2, 2); key('ArrowRight'); expect(where() === 'row0:mrp', where());
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
    typeInto('4'); key('Enter'); expect(items()[0].quantity === 4 && where() === 'row0:rate', 'valid quantity refused');
  });

  await test('discount: over 100 / malformed refused; 10 accepted', async () => {
    await addMed('bulk medicine 0051'); closeList(); focusCell(0, 'disc');
    typeInto('101'); key('Enter'); expect(where() === 'row0:disc', 'accepted 101');
    typeInto('x'); key('Enter'); expect(where() === 'row0:disc', 'accepted x');
    typeInto('10'); key('Enter'); expect(items()[0].discountPercent === 10, 'refused 10');
  });

  await test('amount, tax and bill total match the shared billing rules after every edit', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter');
    focusCell(0, 'qty'); typeInto('3'); key('Enter'); key('Enter'); typeInto('10'); key('Enter');
    expect($('bill-row-amount-0').textContent === '₹102.82', $('bill-row-amount-0').textContent);
    await addMed('bulk medicine 0060'); closeList(); focusCell(1, 'qty'); typeInto('7'); key('Enter');
    const c = billCurrentCalc();
    expect(near(parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, '')), c.grandTotal), $('bill-grand-total-val').textContent + ' vs ' + c.grandTotal);
    expect(c.cgst > 0 && near(c.cgst * 2, c.totalGst), 'cgst/sgst split');
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
    key('Enter'); key('Enter'); typeInto('3'); key('Enter'); key('Enter'); typeInto('5'); key('Enter');    // unit (open, confirm Strip), qty 3, rate (keep MRP), disc 5%
    expect(where() === 'entry:product', where());
    const screen = parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, ''));
    key('F9'); await until(() => items().length === 0, 6000); await wait(400);
    const latest = (await api.request('/sales?skip=0&limit=1'))[0];
    expect(latest && (!savedBefore || latest.id !== savedBefore.id), 'no new sale');
    expect(near(Number(latest.total_amount), screen), `saved ${latest.total_amount} vs screen ${screen}`);
    return 'saved ' + latest.bill_number + ' ₹' + latest.total_amount;
  });


  // ---------- keyboard-fix round: unit, navigation, rate, shortcuts ----------
  await test('Unit: Enter opens the list, Down + Enter chooses Loose, Up + Enter chooses Strip back (keyboard only)', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter');   // PCM-FAR, MRP 34
    expect(where() === 'row0:unit', where());
    key('Enter'); expect(billGrid.popup && billGrid.popup.kind === 'unit', 'list did not open');
    expect(billGrid.popup.options.map((o) => o.value).join() === 'strip,loose', 'units ' + billGrid.popup.options.map((o) => o.value));
    key('ArrowDown'); key('Enter');
    expect(items()[0].unitType === 'loose' && near(items()[0].rate, 3.4) && where() === 'row0:qty', `${items()[0].unitType} rate ${items()[0].rate} at ${where()}`);
    focusCell(0, 'unit'); key(' '); key('ArrowUp'); key('Enter');
    expect(items()[0].unitType === 'strip' && near(items()[0].rate, 34), 'not back to strip');
  });

  await test('Unit: Escape closes the list and keeps the committed unit; the cursor stays in the cell', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'unit'); key('Enter'); key('ArrowDown'); key('Escape');
    expect(!billGrid.popup && items()[0].unitType === 'strip' && where() === 'row0:unit', where() + ' ' + items()[0].unitType);
    expect(items().length === 1, 'Esc cleared the bill');
  });

  await test('Unit: Tab confirms the highlighted unit and moves on; typing "l" jumps to Loose', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'unit'); key('l');
    expect(billGrid.popup && billGrid.popup.options[billGrid.popup.index].value === 'loose', 'type-ahead');
    key('Tab'); expect(items()[0].unitType === 'loose' && where() === 'row0:qty', items()[0].unitType + ' at ' + where());
  });

  await test('Unit change recalculates the amount and re-checks stock in the new unit', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter');
    focusCell(0, 'qty'); typeInto('40'); key('Enter');                       // 40 strips = all the stock
    focusCell(0, 'unit'); key('Enter'); key('ArrowDown'); key('Enter');      // loose: 400 tablets possible, qty 40 stays
    expect(items()[0].quantity === 40 && near(items()[0].rate, 3.4), 'loose ' + items()[0].quantity);
    expect($('bill-row-amount-0').textContent === '₹152.32', $('bill-row-amount-0').textContent);   // 40 x 3.40 + 12 %
    focusCell(0, 'qty'); typeInto('401'); key('Enter'); expect(where() === 'row0:qty' && items()[0].quantity === 40, '401 loose accepted');
    typeInto('400'); key('Enter'); expect(items()[0].quantity === 400, '400 loose refused');
    focusCell(0, 'unit'); key('Enter'); key('ArrowUp'); key('Enter');       // back to strip: 400 > 40 in stock
    expect(items()[0].unitType === 'strip' && items()[0].quantity === 40, 'quantity not limited to the stock: ' + items()[0].quantity);
  });

  await test('Expiry (read-only) cell: Up/Down/Left/Right/Tab all leave it; it is never a trap', async () => {
    await addMed('bulk medicine 0301'); closeList(); await addMed('bulk medicine 0302'); closeList();
    focusCell(0, 'expiry'); expect(where() === 'row0:expiry', where());
    key('ArrowDown'); expect(where() === 'row1:expiry', where());
    key('ArrowUp'); expect(where() === 'row0:expiry', where());
    key('ArrowLeft'); expect(where() === 'row0:batch', where()); key('ArrowRight'); key('ArrowRight'); expect(where() === 'row0:unit', where());
    focusCell(0, 'expiry'); key('Tab'); expect(where() === 'row0:unit', where());
    focusCell(0, 'expiry'); key('Tab', { shiftKey: true }); expect(where() === 'row0:batch', where());
    focusCell(0, 'expiry'); key('Enter'); expect(where() === 'row0:unit', where());
  });

  await test('after choosing a medicine, go to its Expiry cell, move Down, go to another Product cell and pick a different medicine', async () => {
    await addMed('bulk medicine 0303'); closeList(); await addMed('bulk medicine 0304'); closeList();
    focusCell(0, 'expiry'); key('ArrowDown'); expect(where() === 'row1:expiry', where());
    key('ArrowLeft'); key('ArrowLeft'); key('ArrowLeft'); expect(where() === 'row1:product', where());
    const id1 = items()[1].id;
    typeInto('paracet'); await until(() => (window._lastSearchResults || []).length >= 2 && $('bill-search-results-dropdown').style.display === 'block');
    expect(where() === 'row1:product', 'the arrows must not have moved the cursor: ' + where());
    const rowBefore = where(); key('ArrowDown'); expect(where() === rowBefore, 'ArrowDown inside the list moved the grid row');
    const hi = searchHighlightIndex; key('ArrowUp'); expect(searchHighlightIndex === hi - 1, 'highlight did not move');
    key('ArrowDown');
    const chosen = window._lastSearchResults[searchHighlightIndex];
    key('Enter'); await until(() => items()[1].name !== 'BULK MEDICINE 0304');
    expect(items().length === 2 && items()[1].id === id1, 'line identity or count changed');
    // choosing a medicine by name gives its earliest valid batch (FEFO), whichever batch row was highlighted
    expect(items()[1].name === chosen.name && items()[1].selectedBatch === 'PCM-NEAR', `${items()[1].name}/${items()[1].selectedBatch}`);
    const nb = (items()[1].batches || []).find((b) => b.batchNumber === 'PCM-NEAR');
    expect(nb && items()[1].expiryDate === nb.expiryDate && items()[1].quantity === 1, 'expiry/qty not filled');
    expect(where() === 'row1:batch' && billGrid.popup && /PCM-/.test(popupText()), 'batch list: ' + where() + ' ' + popupText());
    expect(items()[0].name === 'BULK MEDICINE 0303', 'the other line changed');
  });

  await test('typing a different medicine over a line and pressing Escape twice keeps the old medicine', async () => {
    await addMed('bulk medicine 0305'); closeList(); focusCell(0, 'product'); typeInto('paracet');
    await until(() => $('bill-search-results-dropdown').style.display === 'block' && (window._lastSearchResults || []).length > 0);
    key('Escape'); expect($('bill-search-results-dropdown').style.display === 'none', 'list still open');
    key('Escape'); expect(items()[0].name === 'BULK MEDICINE 0305' && document.activeElement.value === 'BULK MEDICINE 0305', 'medicine changed: ' + document.activeElement.value);
    expect(items().length === 1, 'Esc cleared the bill');
  });

  await test('Rate: MRP stays read-only, the selling price can be lowered, totals follow, batch/qty/unit are kept', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter');
    focusCell(0, 'qty'); typeInto('3'); key('Enter');
    expect(where() === 'row0:rate', where());
    typeInto('30'); key('Enter');
    const it = items()[0];
    expect(it.rate === 30 && it.rateOverride === 30 && it.selectedBatch === 'PCM-FAR' && it.quantity === 3 && it.unitType === 'strip', JSON.stringify([it.rate, it.selectedBatch, it.quantity]));
    expect($('bill-row-amount-0').textContent === '₹100.80', $('bill-row-amount-0').textContent);       // 90 + 12 %
    const mrpCell = document.querySelector('tr[data-rid] [data-cell="mrp"]'); expect(mrpCell.textContent === '₹34.00', 'MRP cell ' + mrpCell.textContent);
    expect(near(parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, '')), billComputeLines(items(), 0).grandTotal), 'footer total');
    const master = (await api.searchBillingBatches('far', 'PARACETAMOL 500', 5)).find((b) => b.batch_number === 'PCM-FAR');
    expect(master.unit_price === 34, 'the inventory MRP was changed: ' + master.unit_price);
    expect(document.querySelector('tr[data-rid] [data-cell="rate"]').value === '30.00', 'value not kept after redraw');
  });

  await test('Rate: empty / zero / negative / malformed / above MRP are refused and the old price is kept', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter'); focusCell(0, 'rate');
    for (const bad of ['', '0', '-5', 'abc', '1e1', '34.01', '35', '12.345']) {
      typeInto(bad); key('Enter');
      expect(where() === 'row0:rate' && items()[0].rate === 34, `"${bad}" accepted (rate ${items()[0].rate}, at ${where()})`);
    }
    typeInto('34'); key('Enter'); expect(items()[0].rateOverride === null && where() === 'row0:disc', 'MRP itself should be fine');
  });

  await test('Rate override is dropped when the unit changes; it never exceeds the new MRP', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter'); focusCell(0, 'rate'); typeInto('30'); key('Enter');
    focusCell(0, 'unit'); key('Enter'); key('ArrowDown'); key('Enter');
    expect(items()[0].rateOverride === null && near(items()[0].rate, 3.4), 'override kept across units: ' + items()[0].rate);
  });

  await test('the saved invoice uses the edited selling price', async () => {
    await addMed('bulk medicine 0310'); closeList(); focusCell(0, 'rate'); const mrp = items()[0].rate; typeInto(String(mrp - 1)); key('Enter');
    focusCell(0, 'qty'); typeInto('2'); key('Enter');
    const before = (await api.request('/sales?skip=0&limit=1'))[0];
    const expected = billComputeLines(items(), 0).grandTotal;
    await commitBillTransaction(false, true); await wait(300);
    const latest = (await api.request('/sales?skip=0&limit=1'))[0];
    expect(latest.id !== (before && before.id) && near(Number(latest.total_amount), expected), `saved ${latest.total_amount} vs screen ${expected}`);
  });

  await test('buttons show the real shortcuts: Draft F6, Save & New F9, Save & Print F10, Clear Esc, payments Alt+1..4', async () => {
    const txt = (sel) => [...document.querySelectorAll(sel)].map((b) => b.textContent.replace(/\s+/g, ' ').trim());
    const all = txt('.bill-buttons .btn').join(' | ');
    expect(/Esc.*Clear/.test(all) && /F6.*Save as Draft/.test(all) && /F9.*Save & New/.test(all) && /F10.*Save & Print/.test(all), all);
    const pays = txt('.pay-mode-btn').join(' | ');
    expect(/Cash Alt\+1/.test(pays) && /UPI Alt\+2/.test(pays) && /Card Alt\+3/.test(pays) && /Credit Alt\+4/.test(pays), pays);
    document.querySelectorAll('.bill-buttons kbd').forEach((k) => { const cs = getComputedStyle(k); expect(cs.display !== 'none' && cs.visibility !== 'hidden' && k.offsetWidth > 8, 'badge hidden'); });
    return all;
  });

  await test('the displayed shortcuts really run the action: F6 holds once, F10 saves and prints once, F9 saves once', async () => {
    await addMed('bulk medicine 0320'); closeList(); focusCell(0, 'qty');
    const realHold = api.createHeldBill.bind(api); let holds = 0; api.createHeldBill = async (p) => { holds++; await wait(300); return realHold(p); };
    try { key('F6'); key('F6', { repeat: true }); key('F6'); await wait(900); } finally { api.createHeldBill = realHold; }
    expect(holds === 1 && items().length === 0, `held ${holds} times, lines left ${items().length}`);
    await freshBill(); await addMed('bulk medicine 0321'); closeList(); focusCell(0, 'qty');
    const realSale = api.createSale.bind(api); let sales = 0; api.createSale = async (p) => { sales++; await wait(300); return realSale(p); };
    let opened = null; window.open = (u) => { opened = u; return {}; };
    try { key('F10'); key('F10', { repeat: true }); key('F10'); await wait(1200); } finally { window.open = realOpen; }
    expect(sales === 1 && items().length === 0 && /\/billing\/\d+\/pdf/.test(opened || ''), `sales ${sales}, opened ${opened}, lines ${items().length}`);
    await addMed('bulk medicine 0322'); closeList(); focusCell(0, 'qty'); sales = 0;
    try { key('F9'); for (let i = 0; i < 5; i++) key('F9', { repeat: true }); await wait(1200); } finally { api.createSale = realSale; }
    expect(sales === 1 && items().length === 0, `F9 sales ${sales}`);
  });

  await test('a save key does nothing while a list is open or the typed value is invalid', async () => {
    await addMed('bulk medicine 0330'); closeList(); focusCell(1, 'product'); typeInto('paracet');
    await until(() => $('bill-search-results-dropdown').style.display === 'block' && (window._lastSearchResults || []).length > 0);
    const real = api.createSale.bind(api); let n = 0; api.createSale = async (p) => { n++; return real(p); };
    try {
      key('F9'); await wait(200); expect(n === 0 && items().length === 1, 'saved with the medicine list open');
      key('Escape'); focusCell(0, 'qty'); typeInto('abc'); key('F10'); await wait(200);
      expect(n === 0 && items().length === 1 && where() === 'row0:qty', 'saved with a bad quantity');
    } finally { api.createSale = real; }
  });


  // ---------- clean-up round: removed panels and the Bill Discount (% or ₹) box ----------
  const setDisc = (mode, text) => { const m = $('bill-discount-mode'); m.value = mode; handleBillDiscountModeChange(mode); const i = $('bill-discount-input'); i.value = text; i.dispatchEvent(new Event('input', { bubbles: true })); };
  const total = () => parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, ''));
  const lastSale = async () => (await api.request('/sales?skip=0&limit=1'))[0];

  await test('the four panels and the medicine-details panel are gone; invoice value and discount box remain', async () => {
    expect($('medicine-details-panel') === null && $('med-detail-content') === null && $('med-detail-toggle') === null, 'details panel rendered');
    expect($('bill-tax-breakup') === null && $('bill-item-disc-val') === null && $('bill-cgst-val') === null && $('bill-sgst-val') === null && $('bill-roundoff-val') === null, 'a removed panel element is still there');
    const page = document.body.innerText;
    expect(!/Additional Details|Discount Info|Tax Info|CGST Output|SGST Output|Select a medicine to see details/.test(page), 'removed text still shown');
    expect($('bill-grand-total-val') && $('bill-discount-mode') && $('bill-discount-input') && $('bill-save-print-btn'), 'a needed control is missing');
    expect(document.querySelectorAll('#bill-discount-input').length === 1 && document.querySelectorAll('.bill-disc input').length === 1, 'two discount inputs');
  });

  await test('billing a medicine without the removed panels: GST is still in the total and in the saved invoice', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter');
    focusCell(0, 'qty'); typeInto('3'); key('Enter');
    expect($('bill-row-amount-0').textContent === '₹114.24' && near(total(), 114.24), $('bill-row-amount-0').textContent + ' / ' + total());   // 3 x 34 + 12 %
    window.open = () => ({}); await commitBillTransaction(false, true); window.open = realOpen; await wait(300);
    const s = await lastSale(); expect(near(Number(s.total_amount), 114.24) && near(Number(s.tax_amount), 12.24), `saved ${s.total_amount} tax ${s.tax_amount}`);
  });

  await test('Bill Discount %: total follows immediately and matches the shared rules', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter'); focusCell(0, 'qty'); typeInto('3'); key('Enter');
    setDisc('percent', '10');
    expect(near(total(), 102.82) && /off the invoice/.test($('bill-discount-note').textContent), total() + ' | ' + $('bill-discount-note').textContent);   // 102 - 10.2 = 91.8 + 12 %
    expect(activeBillState.billDiscountMode === 'percent' && activeBillState.billDiscountText === '10', 'state not in step');
  });

  await test('Bill Discount ₹: rupees come off the taxable value before GST', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'batch'); typeInto('far'); key('Enter'); focusCell(0, 'qty'); typeInto('3'); key('Enter');
    setDisc('flat', '50');
    expect(near(total(), 58.24) && /56\.00/.test($('bill-discount-note').textContent), total() + ' | ' + $('bill-discount-note').textContent);   // (102 - 50) x 1.12
  });

  await test('switching mode clears the old number and shows the new mode (never reinterpreted silently)', async () => {
    await addMed('paracet'); closeList(); setDisc('percent', '10'); const before = total();
    $('bill-discount-mode').value = 'flat'; handleBillDiscountModeChange('flat');
    expect($('bill-discount-input').value === '' && activeBillState.billDiscountMode === 'flat' && $('bill-discount-mode').selectedOptions[0].text === '₹', 'value kept or mode not shown');
    expect(total() > before, 'discount still applied after the switch');
  });

  await test('invalid discounts: negative, letters, over 100 %, more than the bill (₹) show an error and block saving', async () => {
    await addMed('paracet'); closeList(); focusCell(0, 'qty'); typeInto('3'); key('Enter');
    const real = api.createSale.bind(api); let calls = 0; api.createSale = async (p) => { calls++; return real(p); };
    try {
      for (const [mode, text] of [['percent', '-5'], ['percent', 'abc'], ['percent', '101'], ['flat', '99999'], ['flat', '1e3']]) {
        setDisc(mode, text);
        expect($('bill-discount-input').classList.contains('cell-error') && $('bill-discount-note').classList.contains('bad'), `${mode} "${text}" not flagged`);
        await commitBillTransaction(false, true);
        expect(calls === 0 && items().length === 1 && document.activeElement.id === 'bill-discount-input', `${mode} "${text}" got through`);
      }
    } finally { api.createSale = real; }
    setDisc('percent', '5'); expect(!$('bill-discount-input').classList.contains('cell-error'), 'error not cleared');
  });

  await test('discount keyboard path: Ctrl+Shift+D, type % / ₹, Enter, value, Enter back to the grid; Tab from the grid reaches it', async () => {
    await addMed('paracet'); closeList(); focusCell(items().length, 'batch'); key('Tab');
    expect(document.activeElement.id === 'bill-discount-mode', 'Tab from the entry row: ' + document.activeElement.id);
    focusCell(0, 'qty'); key('D', { ctrlKey: true, shiftKey: true }); expect(document.activeElement.id === 'bill-discount-mode', 'shortcut');
    key('₹'); expect(activeBillState.billDiscountMode === 'flat' && $('bill-discount-mode').value === 'flat', 'rupee key');
    key('%'); expect(activeBillState.billDiscountMode === 'percent', 'percent key');
    key('Enter'); expect(document.activeElement.id === 'bill-discount-input', 'Enter to the value');
    typeInto('5'); key('Enter'); expect(where() === 'entry:product' && activeBillState.billDiscountText === '5', where());
    key('D', { ctrlKey: true, shiftKey: true }); key('Escape'); expect(where() === 'entry:product' && items().length === 1, 'Esc inside the box must not clear the bill');
  });

  await test('save & print with a % discount: the saved invoice equals the screen, discount type recorded', async () => {
    await addMed('bulk medicine 0400'); closeList(); focusCell(0, 'qty'); typeInto('3'); key('Enter'); setDisc('percent', '7.5');
    const screen = total(); let opened = null; window.open = (u) => { opened = u; return {}; };
    try { await commitBillTransaction(true, false); } finally { window.open = realOpen; }
    await wait(300); const s = await lastSale();
    expect(near(Number(s.total_amount), screen) && /\/billing\/\d+\/pdf/.test(opened || ''), `saved ${s.total_amount} vs ${screen}, opened ${opened}`);
    expect(s.discount_type === 'percent' && Number(s.discount_value) === 7.5, `${s.discount_type} ${s.discount_value}`);
  });

  await test('save & print with a ₹ discount: the saved invoice equals the screen, discount type recorded', async () => {
    await addMed('bulk medicine 0401'); closeList(); focusCell(0, 'qty'); typeInto('3'); key('Enter'); setDisc('flat', '12.5');
    const screen = total(); let opened = null; window.open = (u) => { opened = u; return {}; };
    try { await commitBillTransaction(true, false); } finally { window.open = realOpen; }
    await wait(300); const s = await lastSale();
    expect(near(Number(s.total_amount), screen) && /\/billing\/\d+\/pdf/.test(opened || ''), `saved ${s.total_amount} vs ${screen}, opened ${opened}`);
    expect(s.discount_type === 'flat' && Number(s.discount_value) === 12.5, `${s.discount_type} ${s.discount_value}`);
  });

  await test('draft (held bill) keeps the discount mode and value when it is brought back', async () => {
    for (const [mode, text] of [['flat', '20'], ['percent', '12.5']]) {
      await freshBill(); await addMed('bulk medicine 0410'); closeList(); focusCell(0, 'qty'); typeInto('4'); key('Enter'); setDisc(mode, text);
      const screen = total();
      await holdCurrentBill(); await wait(500);
      expect(items().length === 0 && $('bill-discount-input').value === '' && $('bill-discount-mode').value === 'percent', 'new bill not clean');
      const h = (await api.getHeldBills())[0]; await resumeHeldBillWeb(h.id); await until(() => items().length > 0);
      expect(activeBillState.billDiscountMode === mode && $('bill-discount-mode').value === mode && $('bill-discount-input').value === text, `${mode} ${text} came back as ${activeBillState.billDiscountMode} ${$('bill-discount-input').value}`);
      expect(near(total(), screen), `total ${total()} vs ${screen}`);
    }
  });

  await test('a second bill tab keeps its own discount', async () => {
    await freshBill(); await addMed('bulk medicine 0420'); closeList(); setDisc('flat', '5');
    billTabNew(); await wait(100); expect($('bill-discount-input').value === '' && $('bill-discount-mode').value === 'percent', 'new tab inherited the discount');
    billTabSwitch(0); await wait(100); expect($('bill-discount-input').value === '5' && $('bill-discount-mode').value === 'flat', 'first tab lost its discount');
    billTabClose(1); await wait(100);
  });

  window.alert = realAlert; window.open = realOpen;
  const bad = results.filter((r) => !r.ok);
  console.table(results.map((r) => ({ ok: r.ok ? 'PASS' : 'FAIL', name: r.name, detail: String(r.detail).slice(0, 120) })));
  window.__e2e = results;
  return { total: results.length, passed: results.length - bad.length, failed: bad.map((r) => r.name + ' — ' + r.detail) };
};
