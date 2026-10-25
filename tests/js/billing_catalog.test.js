// Run: node --test tests/js/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const c = require('../../web/js/billing_catalog.js');

const D = (offset) => { const d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); };
const COLS = ['id', 'product_name', 'brand', 'composition', 'batch_number', 'barcode', 'quantity', 'unit_price', 'tablets_per_strip', 'expiry_date'];
const row = (id, name, batch, days, qty, extra = {}) =>
  COLS.map((k) => ({ id, product_name: name, brand: extra.brand || 'Acme', composition: extra.comp || '', batch_number: batch,
    barcode: extra.barcode || '', quantity: qty, unit_price: extra.mrp || 30, tablets_per_strip: 10, expiry_date: D(days) }[k]));
const build = (rows) => c.catBuild({ columns: COLS, rows, complete: true });

const idx = build([
  row(1, 'PARACETAMOL 500 TAB', 'P-OLD', -10, 5),
  row(2, 'PARACETAMOL 500 TAB', 'P-NEAR', 20, 12),
  row(3, 'PARACETAMOL 500 TAB', 'P-FAR', 300, 40),
  row(4, 'DOLO 650', 'D1', 200, 0, { comp: 'Paracetamol 650 mg' }),
  row(5, 'CROCIN ADVANCE', 'C1', 200, 9, { comp: 'Paracetamol 500mg', barcode: '8901234567890' }),
  row(6, 'CALPOL PARA DROPS', 'CP1', 200, 3),
  row(7, 'AMOXYCILLIN 250', 'AMX9', 200, 7),
  row(8, 'ZERO STOCK PARACIP', 'Z1', 200, 0),
]);

test('one result per medicine, its first-to-sell batch (earliest VALID expiry) with the total sellable stock', () => {
  const r = c.catSearch(idx, 'paracetamol 500');
  assert.equal(r[0].product_name, 'PARACETAMOL 500 TAB');
  assert.equal(r[0].batch_number, 'P-NEAR');           // P-OLD is expired, never the default
  assert.equal(r[0].total_stock, 52);                   // 12 + 40, the expired 5 does not count
  assert.equal(r[0]._all_batches.length, 3);            // all batches go along for the batch list
  assert.equal(r.filter((x) => x.product_name === 'PARACETAMOL 500 TAB').length, 1);
});

test('prefix of the name first, then in-stock medicines, then the rest; any word of the name matches', () => {
  const names = c.catSearch(idx, 'para').map((x) => x.product_name);
  assert.equal(names[0], 'PARACETAMOL 500 TAB');        // name starts with "para"
  assert.ok(names.indexOf('CALPOL PARA DROPS') > 0);     // a later word starts with "para"
  assert.ok(names.indexOf('CALPOL PARA DROPS') < names.indexOf('DOLO 650'), 'name word before composition');
  // DOLO (out of stock) and ZERO STOCK PARACIP (out of stock) come after in-stock ones of the same match level
  const wordLevel = c.catSearch(idx, 'paracip').map((x) => x.product_name);
  assert.deepEqual(wordLevel, ['ZERO STOCK PARACIP']);
});

test('case and extra spaces do not matter; several words must all match', () => {
  assert.equal(c.catSearch(idx, '  PaRaCeTaMoL    500 ')[0].product_name, 'PARACETAMOL 500 TAB');
  assert.equal(c.catSearch(idx, 'para tab')[0].product_name, 'PARACETAMOL 500 TAB');
  assert.deepEqual(c.catSearch(idx, 'amox 250').map((x) => x.product_name), ['AMOXYCILLIN 250']);
  assert.deepEqual(c.catSearch(idx, 'amox 500'), []);
});

test('composition, company, barcode and batch number also find the medicine', () => {
  assert.ok(c.catSearch(idx, 'paracetamol 650').some((x) => x.product_name === 'DOLO 650'));
  assert.equal(c.catSearch(idx, '8901234567890')[0].product_name, 'CROCIN ADVANCE');   // exact barcode on top
  assert.equal(c.catSearch(idx, 'amx9')[0].product_name, 'AMOXYCILLIN 250');
  assert.equal(c.catSearch(idx, 'acme').length > 0, true);
});

test('empty / no match / limit', () => {
  assert.deepEqual(c.catSearch(idx, ''), []);
  assert.deepEqual(c.catSearch(idx, '   '), []);
  assert.deepEqual(c.catSearch(idx, 'zzzz'), []);
  assert.equal(c.catSearch(idx, 'a', 2).length, 2);
  assert.deepEqual(c.catSearch(null, 'para'), []);
});

test('batch search: part of the batch number, sellable first', () => {
  assert.deepEqual(c.catBatchSearch(idx, 'p-').map((r) => r.batch_number), ['P-NEAR', 'P-FAR', 'P-OLD']);
  assert.deepEqual(c.catBatchSearch(idx, 'nomatch'), []);
});

test('a saved sale lowers the stock in memory at once (strips, and loose tablets as part of a strip)', () => {
  const i2 = build([row(1, 'A', 'A1', 200, 10), row(2, 'B', 'B1', 200, 1)]);
  c.catApplySale(i2, [{ product_id: 1, quantity: 3, unit_type: 'strip' }, { product_id: 2, quantity: 10, unit_type: 'loose', tablets_per_strip: 10 }]);
  assert.equal(c.catSearch(i2, 'a')[0].quantity, 7);
  const b = c.catSearch(i2, 'b')[0];
  assert.equal(b.quantity, 0);
  assert.equal(b.total_stock, 0);                          // no longer counted as in stock
});

test('5,000 medicines: a search takes a few milliseconds', () => {
  const rows = [];
  for (let i = 0; i < 5200; i++) rows.push(row(i + 100, `MEDICINE ${['ALPHA', 'BETA', 'GAMMA', 'DELTA'][i % 4]} ${i}`, 'B' + i, 100 + (i % 400), i % 30));
  const big = build(rows);
  const t0 = process.hrtime.bigint();
  for (let k = 0; k < 50; k++) c.catSearch(big, ['me', 'medi', 'beta', 'gamma 12', 'b51'][k % 5]);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 50;
  assert.ok(ms < 50, `too slow: ${ms.toFixed(1)} ms per search`);
});
