// Run: node --test tests/js/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const c = require('../../web/js/billing_counter_core.js');
const m = require('../../web/js/billing_math.js');

const D = (offset) => { const d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); };
const line = (customerId, o = {}) => Object.assign({
  id: 'r' + Math.random(), customerId, productId: 1, name: 'DOLO', selectedBatch: 'D1', expiryDate: D(300), availableStock: 10, unitType: 'strip',
  unitsPerPack: 10, rate: 100, quantity: 2, discountPercent: 0, gstRate: 12, hsnCode: '3004',
}, o);

test('ids are 24 hex characters and never repeat', () => {
  const ids = new Set(Array.from({ length: 3000 }, () => c.counterNewId()));
  assert.equal(ids.size, 3000);
  for (const id of ids) assert.match(id, /^[0-9a-f]{24}$/);
});

test('a new counter session starts with one draft customer "1"; references count up and restart each day', () => {
  const s = c.counterBlank('2026-10-25');
  assert.equal(s.customers.length, 1);
  assert.equal(s.customers[0].ref, '1');
  assert.equal(s.customers[0].status, 'draft');
  assert.equal(s.activeId, s.customers[0].id);
  assert.equal(c.counterNextRef(s, '2026-10-25'), '2');
  assert.equal(c.counterNextRef(s, '2026-10-25'), '3');
  assert.equal(c.counterNextRef(s, '2026-10-26'), '1');          // next day: numbering restarts
  assert.equal(c.counterNextRef(s, '2026-10-26'), '2');
});

test('new lines go right after the customer\'s own last line (grid stays grouped); other customers are not touched', () => {
  const items = [line('A'), line('A'), line('B'), line('C')];
  assert.equal(c.counterInsertIndex(items, 'A'), 2);
  assert.equal(c.counterInsertIndex(items, 'B'), 3);
  assert.equal(c.counterInsertIndex(items, 'C'), 4);
  assert.equal(c.counterInsertIndex(items, 'NEW'), 4);            // a customer without lines: at the end
  assert.equal(c.counterInsertIndex([], 'A'), 0);
  assert.equal(c.counterLinesOf(items, 'A').length, 2);
});

test('customer totals are separate and equal the invoice arithmetic (discounts, GST per customer)', () => {
  const items = [
    line('A', { quantity: 3, rate: 100, discountPercent: 10 }),     // 300 - 30 = 270 + 12 % = 302.40
    line('B', { rate: 40, quantity: 5, gstRate: 5 }),               // 200 + 5 % = 210.00
    line('A', { rate: 40, quantity: 1, gstRate: 5 }),               // 40 + 5 % = 42.00
  ];
  const a = c.counterTotals(items, 'A');
  const b = c.counterTotals(items, 'B');
  assert.deepEqual([a.count, a.units, a.total], [2, 4, 344.4]);
  assert.deepEqual([b.count, b.units, b.total], [1, 5, 210]);
  assert.equal(a.total, m.billComputeLines(c.counterLinesOf(items, 'A'), 0).grandTotal);
  assert.equal(c.counterTotals(items, 'NOBODY').total, 0);
  assert.equal(R(a.total + b.total), 554.4);                      // the two are only added by the reader, never merged
});
const R = m.billR2;

test('a line that cannot become an invoice says why: expired, no stock, bad quantity, no price, no medicine', () => {
  assert.equal(c.counterLineProblem(line('A')), null);
  assert.match(c.counterLineProblem(line('A', { expiryDate: D(-2) })), /expired/);
  assert.match(c.counterLineProblem(line('A', { quantity: 11 })), /only 10 in stock/);
  assert.equal(c.counterLineProblem(line('A', { quantity: 11, unitType: 'loose' })), null);   // loose is checked by the server in tablets
  assert.match(c.counterLineProblem(line('A', { quantity: 0 })), /whole number/);
  assert.match(c.counterLineProblem(line('A', { quantity: 1.5 })), /whole number/);
  assert.match(c.counterLineProblem(line('A', { rate: 0 })), /no price/);
  assert.match(c.counterLineProblem(line('A', { productId: null })), /reference/);
});

test('customer problem: an empty customer, or the first bad line (with its position)', () => {
  const items = [line('A'), line('B', { expiryDate: D(-1) }), line('B')];
  assert.equal(c.counterCustomerProblem(items, 'A'), null);
  assert.match(c.counterCustomerProblem(items, 'C').message, /Add at least one/);
  const p = c.counterCustomerProblem(items, 'B');
  assert.equal(p.index, 1);
  assert.match(p.message, /expired/);
});

test('hold line: rupee discount for the invoice, typed % kept, loose = loose_tablet, price is the rate', () => {
  const h = c.counterHoldLine(line('A', { quantity: 3, rate: 33.33, discountPercent: 7.5, unitType: 'loose' }));
  assert.equal(h.unit_type, 'loose_tablet');
  assert.equal(h.unit_price, 33.33);
  assert.equal(h.discount, m.billR2(Math.round(99.99 * 7.5) / 100));
  assert.equal(h.discount_percent, 7.5);
  assert.equal(h.quantity, 3);
  assert.equal(h.batch_number, 'D1');
  assert.equal(h.gst_percentage, 12);
  assert.equal(c.counterHoldLine(line('A', { unitType: 'strip' })).unit_type, 'strip');
});

test('server line -> grid line keeps batch, quantity, rate, typed discount, and a lowered selling price', () => {
  const l = c.counterLineFromServer({
    product_id: 7, product_name: 'CROCIN', batch_number: 'C1', expiry_date: D(100), quantity: 4, unit_type: 'strip', unit_price: 36, discount: 7.2,
    discount_percent: 5, tablets_per_strip: 10, hsn_code: '3004', gst_percentage: 5,
    live: { mrp: 40, stock: 50, price_per_unit: 4, units_per_pack: 10, expiry_date: D(100), brand: 'Acme', is_expired: false },
  }, 'CUST', 'row1');
  assert.deepEqual([l.id, l.customerId, l.productId, l.selectedBatch, l.quantity, l.rate, l.packPrice, l.discountPercent, l.rateOverride, l.availableStock],
    ['row1', 'CUST', 7, 'C1', 4, 36, 40, 5, 36, 50]);
  assert.equal(c.counterLineFromServer({ product_id: 7, product_name: 'X', quantity: 1, unit_type: 'strip', unit_price: 40, gst_percentage: 5, live: { mrp: 40, stock: 3 } }, 'C', 'r').rateOverride, null);
  const lo = c.counterLineFromServer({ product_id: 7, product_name: 'X', quantity: 5, unit_type: 'loose_tablet', unit_price: 4, gst_percentage: 5, tablets_per_strip: 10, live: { mrp: 40, stock: 3, price_per_unit: 4, units_per_pack: 10 } }, 'C', 'r');
  assert.deepEqual([lo.unitType, lo.rate, lo.loosePrice, lo.rateOverride], ['loose', 4, 4, null]);
  assert.equal(c.counterLineFromServer({ product_id: 7, product_name: 'X', quantity: 1, unit_type: 'strip', unit_price: 40, gst_percentage: 5 }, 'C', 'r').availableStock, 0);   // medicine gone: shows no stock
});

test('saved drafts come back (only drafts, only their lines); garbage and other versions are ignored', () => {
  const s = c.counterBlank('2026-10-25');
  const ready = Object.assign(c.counterNewCustomer('2'), { status: 'ready', heldId: 9 });
  s.customers.push(ready);
  const items = [line(s.customers[0].id), line(ready.id)];
  const back = c.counterRestore(c.counterSerialize(s, items), '2026-10-25');
  assert.equal(back.counter.customers.length, 1);
  assert.equal(back.items.length, 1);
  assert.equal(back.items[0].customerId, s.customers[0].id);
  assert.equal(back.sameDay, true);
  assert.equal(c.counterRestore(c.counterSerialize(s, items), '2026-10-26').sameDay, false);
  assert.equal(c.counterRestore('not json', 'x'), null);
  assert.equal(c.counterRestore('{"v":2}', 'x'), null);
  assert.equal(c.counterRestore(JSON.stringify({ v: 1, counter: { customers: [ready] }, items: [] }), 'x'), null);
});

test('status labels', () => {
  assert.equal(c.counterStatusLabel('draft'), 'In progress');
  assert.equal(c.counterStatusLabel('READY'), 'Ready');
  assert.equal(c.counterStatusLabel('converted'), 'Converted');
});
