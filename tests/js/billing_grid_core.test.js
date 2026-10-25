// Run: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const g = require('../../web/js/billing_grid_core.js');

const D = (offset) => { const d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); };
const batch = (n, days, stock = 10) => ({ batchNumber: n, expiryDate: D(days), stock, mrp: 10 });

test('Tab walks the editable cells Product > Batch > Unit > Qty > Rate > Disc, then to the next line, then the entry row', () => {
  assert.deepEqual(g.gridTab({ row: 0, col: 'product' }, false, 2), { row: 0, col: 'batch' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'batch' }, false, 2), { row: 0, col: 'unit' });   // Expiry is skipped
  assert.deepEqual(g.gridTab({ row: 0, col: 'qty' }, false, 2), { row: 0, col: 'rate' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'rate' }, false, 2), { row: 0, col: 'disc' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'disc' }, false, 2), { row: 1, col: 'product' });
  assert.deepEqual(g.gridTab({ row: 1, col: 'disc' }, false, 2), { row: 2, col: 'product' });   // 2 = entry row
  assert.deepEqual(g.gridTab({ row: 2, col: 'batch' }, false, 2), { row: 2, col: 'product' });   // stays in the entry row
});

test('Tab from a read-only cell (Expiry, MRP) goes on to the next editable cell, Shift+Tab to the previous one', () => {
  assert.deepEqual(g.gridTab({ row: 0, col: 'expiry' }, false, 2), { row: 0, col: 'unit' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'expiry' }, true, 2), { row: 0, col: 'batch' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'mrp' }, false, 2), { row: 0, col: 'rate' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'gst' }, false, 2), { row: 1, col: 'product' });
  assert.deepEqual(g.gridTab({ row: 1, col: 'packing' }, true, 2), { row: 1, col: 'product' });
});

test('Shift+Tab goes backwards and never leaves the grid', () => {
  assert.deepEqual(g.gridTab({ row: 1, col: 'batch' }, true, 2), { row: 1, col: 'product' });
  assert.deepEqual(g.gridTab({ row: 1, col: 'product' }, true, 2), { row: 0, col: 'disc' });
  assert.deepEqual(g.gridTab({ row: 0, col: 'product' }, true, 2), { row: 0, col: 'product' });
  assert.deepEqual(g.gridTab({ row: 2, col: 'product' }, true, 2), { row: 1, col: 'disc' });
});

test('Enter moves to the next editable cell; in the last one it goes to the next empty Product cell', () => {
  assert.deepEqual(g.gridEnter({ row: 0, col: 'product' }, 3), { row: 0, col: 'batch' });
  assert.deepEqual(g.gridEnter({ row: 0, col: 'expiry' }, 3), { row: 0, col: 'unit' });
  assert.deepEqual(g.gridEnter({ row: 0, col: 'disc' }, 3), { row: 3, col: 'product' });
  assert.deepEqual(g.gridEnter({ row: 0, col: 'amount' }, 3), { row: 3, col: 'product' });
  assert.deepEqual(g.gridEnter({ row: 3, col: 'batch' }, 3), { row: 3, col: 'product' });
});

test('Up/Down keep the column from ANY cell, read-only ones included (no trap in Expiry); entry row has Product and Batch', () => {
  assert.deepEqual(g.gridVertical({ row: 0, col: 'expiry' }, 1, 3), { row: 1, col: 'expiry' });
  assert.deepEqual(g.gridVertical({ row: 1, col: 'expiry' }, -1, 3), { row: 0, col: 'expiry' });
  assert.deepEqual(g.gridVertical({ row: 0, col: 'qty' }, 1, 2), { row: 1, col: 'qty' });
  assert.deepEqual(g.gridVertical({ row: 1, col: 'qty' }, 1, 2), { row: 2, col: 'batch' });
  assert.deepEqual(g.gridVertical({ row: 1, col: 'packing' }, 1, 2), { row: 2, col: 'product' });
  assert.deepEqual(g.gridVertical({ row: 0, col: 'qty' }, -1, 2), { row: 0, col: 'qty' });
  assert.deepEqual(g.gridVertical({ row: 2, col: 'batch' }, -1, 2), { row: 1, col: 'batch' });
});

test('Left/Right walk every cell (read-only too) but only at the edge of the text', () => {
  const pos = { row: 0, col: 'qty' };
  assert.equal(g.gridHorizontal(pos, -1, 1, { start: 2, end: 2, length: 3 }), null);
  assert.equal(g.gridHorizontal(pos, 1, 1, { start: 1, end: 1, length: 3 }), null);
  assert.deepEqual(g.gridHorizontal(pos, 1, 1, { start: 3, end: 3, length: 3 }), { row: 0, col: 'mrp' });
  assert.deepEqual(g.gridHorizontal(pos, -1, 1, { start: 0, end: 0, length: 3 }), { row: 0, col: 'unit' });
  assert.deepEqual(g.gridHorizontal({ row: 0, col: 'batch' }, 1, 1, null), { row: 0, col: 'expiry' });
  assert.equal(g.gridHorizontal({ row: 0, col: 'amount' }, 1, 1, null), null);
  assert.equal(g.gridHorizontal({ row: 0, col: 'product' }, -1, 1, null), null);
});

test('units offered: Strip always, Loose only when a per-tablet price exists; type-ahead picks by first letters', () => {
  assert.deepEqual(g.gridUnitOptions({ loosePrice: null }).map(o => o.value), ['strip']);
  assert.deepEqual(g.gridUnitOptions({ loosePrice: 0 }).map(o => o.value), ['strip']);
  const both = g.gridUnitOptions({ loosePrice: 3.2 });
  assert.deepEqual(both.map(o => o.value), ['strip', 'loose']);
  assert.equal(g.gridMatchUnit(both, 'l'), 1);
  assert.equal(g.gridMatchUnit(both, 'ST'), 0);
  assert.equal(g.gridMatchUnit(both, 'x'), -1);
  assert.equal(g.gridMatchUnit(both, ''), -1);
});

test('rate: MRP of the unit unless a lower selling price was entered; never above MRP', () => {
  const strip = { unitType: 'strip', packPrice: 34, loosePrice: 3.4 };
  assert.equal(g.gridBaseRate(strip), 34);
  assert.equal(g.gridBaseRate({ ...strip, unitType: 'loose' }), 3.4);
  assert.equal(g.gridEffectiveRate(strip), 34);
  assert.equal(g.gridEffectiveRate({ ...strip, rateOverride: 30 }), 30);
  assert.equal(g.gridEffectiveRate({ ...strip, rateOverride: 40 }), 34);       // an old override above a new MRP is ignored
  assert.equal(g.gridEffectiveRate({ ...strip, rateOverride: null }), 34);
});

test('selling price check: positive, two decimals, not above MRP', () => {
  assert.deepEqual(g.gridValidateRate('30', 34), { ok: true, value: 30 });
  assert.deepEqual(g.gridValidateRate('33.5', 34), { ok: true, value: 33.5 });
  assert.equal(g.gridValidateRate('34', 34).ok, true);
  for (const bad of ['', '0', '-5', '34.01', '1e2', 'abc', '3.456', '12,5', ' ']) assert.equal(g.gridValidateRate(bad, 34).ok, false, bad);
  assert.match(g.gridValidateRate('35', 34).error, /MRP/);
});

test('dropdown opens below the cell, flips above near the bottom, and stays on the screen', () => {
  const view = { width: 1366, height: 768 };
  const roomy = g.gridPopupPlacement({ left: 100, top: 200, bottom: 224, width: 300 }, { width: 520, height: 300 }, view);
  assert.equal(roomy.placement, 'below');
  assert.equal(roomy.top, 226);
  const low = g.gridPopupPlacement({ left: 100, top: 640, bottom: 664, width: 300 }, { width: 520, height: 300 }, view);
  assert.equal(low.placement, 'above');
  assert.ok(low.top + low.maxHeight <= 640, 'popup must end above the cell');
  const right = g.gridPopupPlacement({ left: 1300, top: 200, bottom: 224, width: 60 }, { width: 520, height: 200 }, view);
  assert.ok(right.left + right.width <= 1366);
});

test('highlight marks the typed text and escapes everything else', () => {
  assert.equal(g.gridHighlight('Paracetamol 500', 'cet'), 'Para<mark>cet</mark>amol 500');
  assert.equal(g.gridHighlight('<b>x</b>', 'x'), '&lt;b&gt;<mark>x</mark>&lt;/b&gt;');
  assert.equal(g.gridHighlight('abc', ''), 'abc');
  assert.equal(g.gridHighlight('abc', 'zz'), 'abc');
});

test('batch choices: earliest expiry first, expired and empty ones listed but never selectable', () => {
  const list = [batch('LATE', 300), batch('OLD', -5), batch('SOON', 30), batch('EMPTY', 40, 0), batch('MID', 100)];
  const opts = g.gridBatchOptions(list, '');
  assert.deepEqual(opts.map(o => o.batch.batchNumber), ['SOON', 'MID', 'LATE', 'OLD', 'EMPTY']);
  assert.deepEqual(opts.map(o => o.selectable), [true, true, true, false, false]);
  assert.equal(opts.find(o => o.batch.batchNumber === 'OLD').state, 'expired');
  assert.equal(opts.find(o => o.batch.batchNumber === 'SOON').state, 'near');       // inside 60 days
  assert.equal(opts.find(o => o.batch.batchNumber === 'MID').state, 'ok');
});

test('typing part of a batch number narrows the list', () => {
  const list = [batch('AB123', 100), batch('XY999', 100), batch('ZAB1', 200)];
  assert.deepEqual(g.gridBatchOptions(list, 'ab1').map(o => o.batch.batchNumber), ['AB123', 'ZAB1']);
  assert.deepEqual(g.gridBatchOptions(list, 'nomatch'), []);
});

test('quantity: whole numbers, at least 1, not more than the stock', () => {
  const strip = { unitType: 'strip', availableStock: 5, unitsPerPack: 10 };
  assert.deepEqual(g.gridValidateQty('3', strip), { ok: true, value: 3 });
  assert.equal(g.gridValidateQty('0', strip).ok, false);
  assert.equal(g.gridValidateQty('-2', strip).ok, false);
  assert.equal(g.gridValidateQty('2.5', strip).ok, false);
  assert.equal(g.gridValidateQty('1e3', strip).ok, false);
  assert.equal(g.gridValidateQty('', strip).ok, false);
  assert.equal(g.gridValidateQty('abc', strip).ok, false);
  const over = g.gridValidateQty('6', strip);
  assert.equal(over.ok, false);
  assert.equal(over.limit, 5);
  assert.equal(g.gridValidateQty('50', { unitType: 'loose', availableStock: 5, unitsPerPack: 10 }).ok, true);
  assert.equal(g.gridValidateQty('51', { unitType: 'loose', availableStock: 5, unitsPerPack: 10 }).ok, false);
});

test('discount: 0 to 100, at most two decimals, empty is 0', () => {
  assert.deepEqual(g.gridValidateDiscount(''), { ok: true, value: 0 });
  assert.deepEqual(g.gridValidateDiscount('7.5'), { ok: true, value: 7.5 });
  assert.equal(g.gridValidateDiscount('100').ok, true);
  assert.equal(g.gridValidateDiscount('100.5').ok, false);
  assert.equal(g.gridValidateDiscount('-1').ok, false);
  assert.equal(g.gridValidateDiscount('5.123').ok, false);
  assert.equal(g.gridValidateDiscount('x').ok, false);
});

test('same medicine row (product + batch) is detected, a different batch is not', () => {
  assert.equal(g.gridSameLine({ productId: 7, selectedBatch: 'A' }, { productId: '7', selectedBatch: 'A' }), true);
  assert.equal(g.gridSameLine({ productId: 7, selectedBatch: 'A' }, { productId: 7, selectedBatch: 'B' }), false);
  assert.equal(g.gridSameLine(null, { productId: 7 }), false);
});

test('party search by name or phone', () => {
  const parties = [{ id: 'walkin', name: 'Walk-in Customer', phone: 'Cash Sale' }, { id: 2, name: 'Ramesh Patel', phone: '98765' }, { id: 3, name: 'Sita', phone: '91234' }];
  assert.deepEqual(g.gridFilterParties(parties, 'ram').map(p => p.id), [2]);
  assert.deepEqual(g.gridFilterParties(parties, '9123').map(p => p.id), [3]);
  assert.deepEqual(g.gridFilterParties(parties, 'cash').map(p => p.id), ['walkin']);
  assert.equal(g.gridFilterParties(parties, '').length, 3);
});

test('row ids are unique and not positions', () => {
  const ids = new Set(Array.from({ length: 2000 }, () => g.gridNewRowId()));
  assert.equal(ids.size, 2000);
});
