/*
 * Browser regression run for COUNTER SALE (the tab beside the bill tabs on the billing page).
 * Real key events, real endpoints (it creates real invoices and takes stock): run it only on a TEST pharmacy,
 * freshly seeded (see tests/browser/README.md: PARACETAMOL 500 batches PCM-OLD/PCM-NEAR/PCM-FAR, BULK MEDICINE 0000..1199 with
 * batches B0000.., EXTRA MEDICINE rows with batches X00000..).
 * Run:  load the file, then   await runCounterSaleE2E()
 */
window.runCounterSaleE2E = async function () {
  const results = [];
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const until = async (fn, ms = 4000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (fn()) return true; await wait(40); } return false; };
  const $ = (id) => document.getElementById(id);
  const items = () => activeBillState.items;
  const cs = () => activeBillState.counter;
  const key = (k, o = {}) => document.activeElement.dispatchEvent(new KeyboardEvent('keydown', Object.assign({ key: k, bubbles: true, cancelable: true }, o)));
  const typeInto = (t) => { const el = document.activeElement; el.value = t; el.dispatchEvent(new Event('input', { bubbles: true })); };
  const where = () => { const a = document.activeElement; const tr = a.closest && a.closest('tr'); return tr ? (tr.hasAttribute('data-entry') ? 'entry' : 'row' + tr.dataset.row) + ':' + a.dataset.cell : a.id; };
  const near = (a, b) => Math.abs(a - b) < 0.005;
  const expect = (c, m) => { if (!c) throw new Error(m); };
  const refOf = (id) => (cs().customers.find((c) => c.id === id) || {}).ref;
  const linesOf = (ref) => items().filter((i) => refOf(i.customerId) === String(ref));
  const closeList = () => { if (billGrid.popup) key('Escape'); };
  const stockOf = async (batch) => Number((await api.searchBillingBatches(batch, '', 5)).find((b) => b.batch_number === batch).quantity);
  const entryEmpty = () => $('bill-medicine-search-input').value === '' && $('bill-entry-batch').value === '';
  const addMed = async (q) => {
    billGridFocusPos({ row: items().length, col: 'product' }); typeInto(q);
    await until(() => (window._lastSearchResults || []).length > 0 && $('bill-search-results-dropdown').style.display === 'block');
    const n = items().length; key('Enter'); await until(() => items().length === n + 1); closeList();
  };
  const setQty = (idx, v) => { billGridFocusPos({ row: idx, col: 'qty' }); typeInto(String(v)); key('Enter'); };
  const total = (ref) => counterTotals(items(), cs().customers.find((c) => c.ref === String(ref)).id).total;
  const sumText = () => $('counter-sum-body').innerText.replace(/\s+/g, ' ');
  const confirmDialog = async () => {
    await until(() => { const b = $('confirm-modal-confirm'); return b && b.offsetParent !== null; }, 3000);
    const b = $('confirm-modal-confirm'); expect(b, 'confirmation dialog did not appear'); b.click(); await wait(60);
  };
  const settle = async () => { await until(() => !counterBusy(), 6000); await wait(120); };       // the save / convert has fully finished
  const lastSale = async () => (await api.request('/sales?skip=0&limit=1'))[0];
  const salesCount = async () => (await api.request('/sales?skip=0&limit=500')).length;
  const alerts = []; const realAlert = window.alert; window.alert = (m) => alerts.push(m);

  // start: a fresh Counter Sale tab
  const reset = async () => {
    const at = billTabs.findIndex((t) => t.mode === 'counter');
    if (at >= 0) { if (at !== billActiveTab) billTabSwitch(at); billTabs.splice(billActiveTab, 1); billActiveTab = 0; activeBillState = billTabs[0].state; billRefreshFromState(); }
    await wait(450);                                              // a pending "save drafts in this browser" of the old tab must run first
    Object.keys(localStorage).filter((k) => k.startsWith('dawaiflow_counter_')).forEach((k) => localStorage.removeItem(k));
    counterOpenTab(); await wait(150);
    // every test starts with no READY customers on the server and an empty "recent bills" list on screen
    await counterReload();
    for (const r of counterServerState.ready.slice()) { try { await api.counterCancel(r.id); } catch (e) { /* already gone */ } }
    await counterReload(); counterServerState.converted.splice(0); counterRenderSummary();
  };
  async function test(name, fn) {
    if (window.__csOnly && !new RegExp(window.__csOnly, 'i').test(name)) return;
    try { localStorage.setItem('cs_last', name); await reset(); const d = await fn(); results.push({ name, ok: true, detail: d || '' }); }
    catch (e) { results.push({ name, ok: false, detail: String(e && e.message || e) }); }
  }
  await until(() => window.billCatalog && billCatalog.ready(), 15000);
  await billCatalog.refresh();

  await test('Counter Sale is a tab beside the bill tabs (no sidebar entry); switching modes works', async () => {
    expect(billIsCounter() && $('billing-page').classList.contains('mode-counter'), 'not in counter mode');
    expect(/Counter Sale/.test($('bill-tabs').innerText) && /Sale Bill 1/.test($('bill-tabs').innerText), 'tabs: ' + $('bill-tabs').innerText);
    expect(!document.querySelector('.sidebar a[href*="counter"], .nav-item[data-nav-id*="counter"]'), 'a sidebar entry for Counter Sale exists');
    expect(getComputedStyle($('counter-foot')).display !== 'none' && getComputedStyle($('counter-head')).display !== 'none' && getComputedStyle(document.querySelector('.bill-head')).display === 'none', 'counter layout not shown');
    billTabSwitch(0); await wait(100);
    expect(!billIsCounter() && !$('billing-page').classList.contains('mode-counter') && getComputedStyle($('counter-foot')).display === 'none', 'retail layout not restored');
    expect(getComputedStyle(document.querySelector('.bill-foot')).display !== 'none', 'retail footer hidden');
    counterOpenTab(); await wait(100); expect(billIsCounter(), 'cannot return to Counter Sale');
  });

  await test('an unsaved Retail Billing bill survives switching to Counter Sale and back', async () => {
    billTabSwitch(0); await wait(100);
    billGridFocusPos({ row: 0, col: 'product' }); await addMed('paracet'); closeList();
    setQty(0, 3); billGridFocusPos({ row: 0, col: 'rate' });
    $('bill-discount-mode').value = 'flat'; handleBillDiscountModeChange('flat'); $('bill-discount-input').value = '5'; handleBillDiscountInput('5');
    const before = JSON.stringify({ n: items().length, q: items()[0].quantity, b: items()[0].selectedBatch, d: activeBillState.billDiscountText, m: activeBillState.billDiscountMode, tot: $('bill-grand-total-val').textContent });
    counterOpenTab(); await wait(100); await addMed('bulk medicine 0200'); closeList();
    billTabSwitch(0); await wait(150);
    const after = JSON.stringify({ n: items().length, q: items()[0].quantity, b: items()[0].selectedBatch, d: activeBillState.billDiscountText, m: activeBillState.billDiscountMode, tot: $('bill-grand-total-val').textContent });
    expect(before === after && !billIsCounter(), before + ' vs ' + after);
    expect($('bill-discount-input').value === '5' && $('bill-discount-mode').value === 'flat', 'discount box not restored');
    counterOpenTab(); await wait(100);
    expect(items().length === 1 && /BULK MEDICINE 0200/.test(items()[0].name), 'counter lines lost');
    billTabSwitch(0); await wait(100); resetBillForm(); await wait(100); billTabSwitch(billTabs.findIndex((t) => t.mode === 'counter')); await wait(100);
  });

  await test('multiple customers: each line belongs to the customer in front, grouped, with its own total and count', async () => {
    await addMed('bulk medicine 0210'); await addMed('bulk medicine 0211');
    key('F8'); await wait(80); await addMed('bulk medicine 0212');
    key('F8'); await wait(80); await addMed('bulk medicine 0213'); await addMed('bulk medicine 0214'); await addMed('bulk medicine 0215');
    expect(cs().customers.length === 3, 'customers ' + cs().customers.length);
    expect([linesOf(1).length, linesOf(2).length, linesOf(3).length].join() === '2,1,3', [linesOf(1).length, linesOf(2).length, linesOf(3).length].join());
    expect(items().map((i) => refOf(i.customerId)).join('') === '112333', 'order ' + items().map((i) => refOf(i.customerId)).join(''));
    const t1 = total(1), t2 = total(2), t3 = total(3);
    expect(sumText().includes('₹' + t1.toFixed(2)) && sumText().includes('₹' + t2.toFixed(2)) && sumText().includes('₹' + t3.toFixed(2)), sumText());
    expect(new Set(cs().customers.map((c) => c.id)).size === 3 && cs().customers.every((c) => /^[0-9a-f]{24}$/.test(c.id)), 'ids');
  });

  await test('Page Up / Page Down move between customers; a new line goes to the customer in front, next to its own lines', async () => {
    await addMed('bulk medicine 0220'); key('F8'); await wait(60); await addMed('bulk medicine 0221');
    key('PageUp'); await wait(100);
    expect(cs().activeId === cs().customers[0].id, 'PageUp did not go to customer 1');
    await addMed('bulk medicine 0222');
    expect(items().map((i) => refOf(i.customerId) + ':' + i.name.slice(-4)).join(',') === '1:0220,1:0222,2:0221', items().map((i) => refOf(i.customerId) + ':' + i.name.slice(-4)).join(','));
    key('PageDown'); await wait(60); expect(cs().activeId === cs().customers[1].id, 'PageDown');
    expect(entryEmpty(), 'search text carried over to the other customer');
  });

  await test('search by medicine name and by batch number; temporary text is cleared and never reaches the next row or the next customer', async () => {
    billGridFocusPos({ row: 0, col: 'product' }); typeInto('78');
    await until(() => (window._lastSearchResults || []).length > 0 && $('bill-search-results-dropdown').style.display === 'block');
    const wanted = window._lastSearchResults[0]; key('Enter'); await until(() => items().length === 1); closeList();
    expect(items()[0].name === wanted.name && entryEmpty(), 'name search: ' + items()[0].name + ' / "' + $('bill-medicine-search-input').value + '"');
    billGridFocusPos({ row: 1, col: 'batch' }); typeInto('X00079');
    await until(() => billGrid.popup && billGrid.popup.options.length === 1);
    key('Enter'); await until(() => items().length === 2); closeList();
    expect(items()[1].selectedBatch === 'X00079' && /0079/.test(items()[1].name), items()[1].selectedBatch);
    expect($('bill-entry-batch').value === '' && entryEmpty(), 'batch text left behind');
    key('F8'); await wait(80);
    expect(entryEmpty() && where() === 'entry:product', 'next customer starts with text: ' + $('bill-medicine-search-input').value);
  });

  await test('keyboard only: type, Enter (medicine), Enter (batch), unit, quantity, rate, discount, Enter -> next empty row', async () => {
    billGridFocusPos({ row: 0, col: 'product' }); typeInto('bulk medicine 0230'); await until(() => (window._lastSearchResults || []).length > 0);
    key('Enter'); await until(() => where() === 'row0:batch'); key('Enter');            // medicine, batch
    key('Enter'); key('Enter');                                                        // unit list open, confirm Strip
    typeInto('3'); key('Enter'); key('Enter'); typeInto('10'); key('Enter');           // qty 3, rate (MRP), discount 10 %
    expect(where() === 'entry:product' && entryEmpty() && items().length === 1, where());
    expect(items()[0].quantity === 3 && items()[0].discountPercent === 10, 'qty/disc');
  });

  await test('unit change and quantity editing on a counter line: loose rate, stock re-checked, amounts follow', async () => {
    await addMed('paracet'); billGridFocusPos({ row: 0, col: 'batch' }); typeInto('far'); key('Enter');
    setQty(0, 3);
    billGridFocusPos({ row: 0, col: 'unit' }); key('Enter'); key('ArrowDown'); key('Enter');
    expect(items()[0].unitType === 'loose' && near(items()[0].rate, 3.4), items()[0].unitType + ' ' + items()[0].rate);
    setQty(0, 401); expect(items()[0].quantity === 3 && where() === 'row0:qty', 'quantity over the loose stock accepted');
    setQty(0, 400); expect(items()[0].quantity === 400, 'valid loose quantity refused');
    expect(near(total(1), 400 * 3.4 * 1.12), 'total ' + total(1));
  });

  await test('discounts and GST per customer: each total is its own lines with GST, never mixed', async () => {
    await addMed('bulk medicine 0240'); setQty(0, 3); billGridFocusPos({ row: 0, col: 'disc' }); typeInto('10'); key('Enter');
    key('F8'); await wait(80); await addMed('bulk medicine 0241'); setQty(1, 2);
    const a = linesOf(1)[0], b = linesOf(2)[0];
    const ea = billComputeLines([a], 0).grandTotal, eb = billComputeLines([b], 0).grandTotal;
    expect(near(total(1), ea) && near(total(2), eb) && ea !== eb, `${total(1)} ${ea} | ${total(2)} ${eb}`);
    expect(a.discountPercent === 10 && b.discountPercent === 0 && Number(a.gstRate) === 12, 'discount/gst');
    expect(near(counterTotals(items(), cs().customers[0].id).gst, a.rate * 3 * 0.9 * 0.12), 'gst of customer 1');
  });

  await test('an expired batch cannot be chosen, and a customer with a bad line cannot be finished', async () => {
    await addMed('paracet'); billGridFocusPos({ row: 0, col: 'batch' }); key('ArrowDown', { altKey: true });
    const n = billGrid.popup.options.length; for (let i = 0; i < n + 2; i++) key('ArrowDown');
    expect(billGrid.popup.options[billGrid.popup.index].selectable, 'highlight on an unsellable batch');
    const old = billGrid.popup.options.findIndex((o) => o.value.batchNumber === 'PCM-OLD');
    expect(old >= 0 && !billGrid.popup.options[old].selectable, 'expired batch not blocked');
    document.querySelector('#bill-cell-popup [data-i="' + old + '"]').click(); expect(items()[0].selectedBatch !== 'PCM-OLD', 'expired batch chosen');
    closeList();
    await wait(800);                                                                    // the live batch check of the server has answered by now
    items()[0].expiryDate = '2020-01-01';                                               // it expired while the customer was being served
    const before = await salesCount(), allBefore = (await api.counterList('ALL', 0, 50)).total; await counterFinishActive(); await wait(100);
    expect(cs().customers[0].status === 'draft' && items().length === 1 && counterServerState.ready.length === 0, 'an expired line was finished');
    expect((await api.counterList('ALL', 0, 50)).total === allBefore && (await salesCount()) === before, 'something reached the server');
  });

  await test('finish customer: becomes READY on the server, no stock deducted, no invoice; the next customer is ready to type', async () => {
    await addMed('bulk medicine 0250'); setQty(0, 4);
    const before = await stockOf('B0250'), sales = await salesCount();
    const expectedTotal = total(1);
    key('F9'); await until(() => counterServerState.ready.length === 1); await settle();
    expect(items().length === 0 && cs().customers.length === 1 && cs().customers[0].ref === '2' && where() === 'entry:product', 'next customer not ready: ' + cs().customers.map((c) => c.ref + c.status));
    expect(await stockOf('B0250') === before && (await salesCount()) === sales, 'stock or sales changed by finishing');
    const r = counterServerState.ready[0];
    expect(r.status === 'READY' && near(r.total, expectedTotal) && r.items_count === 1 && /Ready/i.test(sumText()), JSON.stringify(r));
    const again = await api.counterFinish({ txn_id: r.txn_id, ref: r.ref, items: [{ product_id: items().length, quantity: 1 }] }).catch(() => null);   // a retry with the same id
    expect(!again || again.id === r.id, 'retry created a second record');
  });

  await test('convert to bill: ONE invoice, stock deducted once, linked, total equals the customer total; F10 twice makes one', async () => {
    await addMed('bulk medicine 0260'); setQty(0, 2); billGridFocusPos({ row: 0, col: 'disc' }); typeInto('5'); key('Enter');
    const before = await stockOf('B0260'), sales = await salesCount(), expectedTotal = total(1);
    key('F10'); await until(() => $('confirm-modal-confirm') && $('confirm-modal-confirm').offsetParent !== null, 4000);
    key('F10', { repeat: true });                                                       // a second press must not start a second conversion
    await confirmDialog();
    await until(() => counterServerState.converted.length === 1, 6000); await settle();
    const s = await lastSale();
    expect(counterServerState.converted.length === 1 && (await salesCount()) === sales + 1, 'invoices ' + ((await salesCount()) - sales));
    expect(near(Number(s.total_amount), expectedTotal) && /Counter Sale 1/.test(s.notes || ''), `sale ${s.total_amount} vs ${expectedTotal}: ${s.notes}`);
    expect(await stockOf('B0260') === before - 2, 'stock ' + before + ' -> ' + (await stockOf('B0260')));
    const tx = counterServerState.converted[0];
    expect(tx.status === 'CONVERTED' && tx.completed_sale_id === s.id && tx.invoice_number === s.bill_number && /Converted/i.test(sumText()), JSON.stringify(tx));
    expect(items().length === 0 && counterServerState.ready.length === 0, 'converted customer still in the grid/list');
  });

  await test('convert a customer that is already converted (retry / lost answer): the same invoice, no second deduction', async () => {
    await addMed('bulk medicine 0270'); setQty(0, 3);
    const before = await stockOf('B0270'); key('F9'); await until(() => counterServerState.ready.length === 1); await settle();
    const id = counterServerState.ready[0].id;
    const a = await api.counterConvert(id, { payment_method: 'CASH' }), b = await api.counterConvert(id, { payment_method: 'CASH' });
    expect(b.already_converted && a.sale_id === b.sale_id && a.bill_number === b.bill_number, 'second convert made another invoice');
    expect(await stockOf('B0270') === before - 3, 'stock deducted ' + (before - await stockOf('B0270')));
  });

  await test('network failure while converting: nothing changes, the customer stays READY with all lines, a retry then works once', async () => {
    await addMed('bulk medicine 0280'); setQty(0, 2); const before = await stockOf('B0280'), sales = await salesCount(), convBefore = (await api.counterList('CONVERTED', 0, 1)).total;
    const real = api.counterConvert.bind(api); api.counterConvert = async () => { throw new Error('Failed to fetch'); };
    try { key('F10'); await confirmDialog(); await until(() => counterServerState.ready.length === 1 && !$('confirm-modal-confirm').offsetParent, 4000); await settle(); await wait(300); } finally { api.counterConvert = real; }
    expect(counterServerState.ready.length === 1 && counterServerState.ready[0].status === 'READY' && (await api.counterList('CONVERTED', 0, 1)).total === convBefore, 'state after failure');
    expect(await stockOf('B0280') === before && (await salesCount()) === sales, 'a failed conversion changed stock or sales');
    const d = await api.counterGet(counterServerState.ready[0].id);
    expect(d.status === 'READY' && d.items.length === 1 && d.items[0].quantity === 2, 'original transaction changed');
    { const p = counterConvertTarget({ kind: 'ready', id: counterServerState.ready[0].id }); await confirmDialog(); await p; await settle(); }
    await until(() => counterServerState.converted.length > 0 && counterServerState.converted[0].status === 'CONVERTED', 5000);
    expect(await stockOf('B0280') === before - 2 && (await salesCount()) === sales + 1, 'retry did not convert exactly once');
  });

  await test('server refuses (not enough stock for the second customer): error shown, customer stays READY, stock never negative', async () => {
    const far = (await api.searchBillingBatches('PCM-FAR', '', 5))[0], convBefore = (await api.counterList('CONVERTED', 0, 1)).total;
    await api.request('/products/' + far.id + '/quantity', { method: 'PUT', body: JSON.stringify({ quantity: 10 }) }); await billCatalog.refresh();
    await addMed('paracet'); billGridFocusPos({ row: 0, col: 'batch' }); typeInto('far'); key('Enter'); setQty(0, 8); key('F9'); await until(() => counterServerState.ready.length === 1); await settle();
    await addMed('paracet'); billGridFocusPos({ row: 0, col: 'batch' }); typeInto('far'); key('Enter'); setQty(0, 8); key('F9'); await until(() => counterServerState.ready.length === 2); await settle();
    const [second, first] = counterServerState.ready;                                  // newest first
    { const p = counterConvertTarget({ kind: 'ready', id: first.id }); await confirmDialog(); await p; }
    { const p = counterConvertTarget({ kind: 'ready', id: second.id }); await confirmDialog(); await p; }
    expect(counterServerState.ready.some((r) => r.id === second.id && r.status === 'READY') && (await api.counterList('CONVERTED', 0, 1)).total === convBefore + 1, 'second customer state');
    expect(await stockOf('PCM-FAR') === 2, 'stock ' + (await stockOf('PCM-FAR')));
    await api.request('/products/' + far.id + '/quantity', { method: 'PUT', body: JSON.stringify({ quantity: 40 }) });
  });

  await test('hold and resume: drafts survive a page reload; a READY customer can be reopened with batch, quantity, discount and price intact', async () => {
    await addMed('paracet'); billGridFocusPos({ row: 0, col: 'batch' }); typeInto('near'); key('Enter'); setQty(0, 2);
    billGridFocusPos({ row: 0, col: 'rate' }); typeInto('30'); key('Enter'); typeInto('7.5'); key('Enter');
    const snap = JSON.stringify(items().map((i) => [i.name, i.selectedBatch, i.quantity, i.rate, i.discountPercent]));
    counterPersistNow();
    const stored = localStorage.getItem(Object.keys(localStorage).find((k) => k.startsWith('dawaiflow_counter_')));
    expect(stored && JSON.parse(stored).items.length === 1, 'drafts were not kept in this browser');
    // reload simulation: drop the state, open the tab again
    const at = billTabs.findIndex((t) => t.mode === 'counter'); billTabSwitch(0); billTabs.splice(at, 1); billActiveTab = 0; billRefreshFromState();
    counterOpenTab(); await wait(200);
    expect(JSON.stringify(items().map((i) => [i.name, i.selectedBatch, i.quantity, i.rate, i.discountPercent])) === snap, 'restored lines differ');
    key('F9'); await until(() => counterServerState.ready.length === 1); await settle();
    expect(items().length === 0, 'finished customer still in the grid');
    const r = counterServerState.ready[0];
    document.querySelector(`#counter-sum-body [data-act="reopen"][data-id="${r.id}"]`).click();
    await until(() => items().length === 1, 4000); await wait(200);
    expect(JSON.stringify(items().map((i) => [i.name, i.selectedBatch, i.quantity, i.rate, i.discountPercent])) === snap, 'reopened lines differ: ' + JSON.stringify(items().map((i) => [i.name, i.selectedBatch, i.quantity, i.rate, i.discountPercent])));
    expect(items()[0].rateOverride === 30 && items()[0].batches.length >= 3, 'selling price / batches not restored');
    key('F9'); await until(() => counterServerState.ready.length === 1 && counterServerState.ready[0].id !== r.id, 4000); await settle();
    expect((await api.counterList('CANCELLED', 0, 20)).items.some((x) => x.id === r.id), 'the replaced version is not kept as history');
    expect((await api.counterList('READY', 0, 20)).total === 1, 'two READY versions');
  });

  await test('invoice numbers are unique over many conversions and the retail held-bills list is not polluted', async () => {
    const nums = new Set(); const heldBefore = (await api.getHeldBills()).length;
    for (let i = 0; i < 5; i++) {
      await addMed('bulk medicine 030' + i); await settle(); key('F10'); await confirmDialog();
      await until(() => counterServerState.converted.length > 0 && !nums.has(counterServerState.converted[0].invoice_number), 6000);
      nums.add(counterServerState.converted[0].invoice_number);
      await settle();
    }
    expect(nums.size === 5, 'invoice numbers: ' + [...nums].join());
    expect((await api.getHeldBills()).length === heldBefore, 'Counter Sale rows appear in the retail held bills');
  });

  await test('cancel a READY customer: it stays as history, stock untouched, it can no longer be converted', async () => {
    await addMed('bulk medicine 0310'); const before = await stockOf('B0310'); key('F9'); await until(() => counterServerState.ready.length === 1); await settle();
    const id = counterServerState.ready[0].id;
    document.querySelector(`#counter-sum-body [data-act="cancel"][data-id="${id}"]`).click(); await confirmDialog(); await until(() => counterServerState.ready.length === 0, 4000); await settle();
    expect((await api.counterList('CANCELLED', 0, 20)).items.some((x) => x.id === id) && await stockOf('B0310') === before, 'cancel');
    let refused = false; try { await api.counterConvert(id, {}); } catch (e) { refused = true; }
    expect(refused, 'a cancelled customer was converted');
  });

  await test('Esc never clears a Counter Sale; Clear discards only the customer in front (after asking); retail shortcuts do not touch it', async () => {
    await addMed('bulk medicine 0320'); key('F8'); await wait(60); await addMed('bulk medicine 0321');
    billGridFocusPos({ row: 1, col: 'qty' }); key('Escape'); await wait(100);
    expect(items().length === 2 && !$('confirm-modal-confirm').offsetParent, 'Esc opened a clear dialog / cleared lines');
    key('F6'); await wait(80); expect(items().length === 2 && cs().customers.length === 2, 'F6 held the counter sale');
    confirmClearBill(); await confirmDialog(); await wait(150);
    expect(items().length === 1 && /0320/.test(items()[0].name) && cs().customers.length === 2 ? true : items().length === 1, 'discard: ' + items().length + ' lines, ' + cs().customers.length + ' customers');
    expect(billIsCounter(), 'left counter mode');
  });

  await test('Retail Billing still works after all this: a normal bill is saved with the normal invoice', async () => {
    billTabSwitch(0); await wait(150);
    await addMed('bulk medicine 0330'); setQty(0, 2);
    const before = await salesCount(), expectedTotal = parseFloat($('bill-grand-total-val').textContent.replace(/[^0-9.]/g, ''));
    window.open = () => ({}); await commitBillTransaction(false, true); await wait(300);
    const s = await lastSale();
    expect((await salesCount()) === before + 1 && near(Number(s.total_amount), expectedTotal) && !/Counter Sale/.test(s.notes || ''), `sales ${before} -> ${await salesCount()}, ${s.total_amount} vs ${expectedTotal}`);
    expect(!billIsCounter() && items().length === 0, 'retail bill not reset');
  });

  window.alert = realAlert;
  const bad = results.filter((r) => !r.ok);
  window.__cs = results;
  console.table(results.map((r) => ({ ok: r.ok ? 'PASS' : 'FAIL', name: r.name, detail: String(r.detail).slice(0, 120) })));
  return { total: results.length, passed: results.length - bad.length, failed: bad.map((r) => r.name + ' — ' + r.detail) };
};
