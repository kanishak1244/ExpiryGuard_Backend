// Run with:  node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('../../web/js/billing_math.js');

const item = (rate, qty, disc, gst) => ({ rate, quantity: qty, discountPercent: disc, gstRate: gst });
const daysFromToday = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

test('rounding is decimal-safe, half away from zero', () => {
  assert.equal(m.billR2(2.675), 2.68);
  assert.equal(m.billR2(1.005), 1.01);
  assert.equal(m.billR2(0.285), 0.29);
  assert.equal(m.billR2(-2.675), -2.68);
  assert.equal(m.billR2(10), 10);
  assert.equal(m.billR2('abc'), 0);
});

test('one medicine: taxable, CGST/SGST split and total', () => {
  const c = m.billComputeLines([item(100, 3, 0, 12)], 0);
  assert.equal(c.netTaxable, 300);
  assert.equal(c.cgst, 18);
  assert.equal(c.sgst, 18);
  assert.equal(c.grandTotal, 336);
});

test('0% GST is billed at 0%, not 12%', () => {
  const c = m.billComputeLines([item(80, 1, 0, 0)], 0);
  assert.equal(c.totalGst, 0);
  assert.equal(c.grandTotal, 80);
});

test('line discount comes off before GST, bill discount is shared over the lines', () => {
  const c = m.billComputeLines([item(100, 2, 10, 12), item(50, 2, 0, 5)], 10);
  assert.equal(c.lineDiscTotal, 20);          // 10% of 200
  assert.equal(c.taxableSubtotal, 280);       // 180 + 100
  assert.equal(c.billDiscount, 28);
  assert.equal(c.netTaxable, 252);
  assert.equal(c.grandTotal, m.billR2(c.netTaxable + c.totalGst));
  assert.equal(c.lines[0].finalTaxable + c.lines[1].finalTaxable, 252);   // the shares add up exactly
});

test('discounts are bounded and the total is never negative', () => {
  const c = m.billComputeLines([item(100, 1, 250, 12)], 500);
  assert.equal(c.lineDiscTotal, 100);          // 250% is pulled back to 100%: the line is free, never negative
  assert.equal(c.grandTotal, 0);
  const d = m.billComputeLines([item(100, 1, 0, 12)], 500);   // a bill discount above 100% is capped
  assert.equal(d.billDiscount, 100);
  assert.ok(d.grandTotal >= 0);
});

test('an empty bill totals zero', () => {
  const c = m.billComputeLines([], 0);
  assert.equal(c.grandTotal, 0);
  assert.equal(c.lines.length, 0);
});

test('changing quantity changes only that line', () => {
  const items = [item(100, 1, 0, 12), item(40, 1, 0, 5)];
  const before = m.billComputeLines(items, 0);
  items[0].quantity = 4;
  const after = m.billComputeLines(items, 0);
  assert.equal(after.lines[1].total, before.lines[1].total);
  assert.equal(after.lines[0].gross, 400);
});

test('row amount equals the line total when there is no bill discount', () => {
  const it = item(33.33, 3, 7.5, 12);
  assert.equal(m.billRowAmount(it), m.billComputeLines([it], 0).lines[0].total);
});

test('expired batch is blocked, empty batch is blocked, near expiry is allowed with a warning', () => {
  assert.equal(m.billBatchState({ expiryDate: daysFromToday(-1), stock: 10 }), 'expired');
  assert.equal(m.billBatchSellable({ expiryDate: daysFromToday(-1), stock: 10 }), false);
  assert.equal(m.billBatchState({ expiryDate: daysFromToday(300), stock: 0 }), 'out');
  assert.equal(m.billBatchState({ expiryDate: daysFromToday(20), stock: 5 }), 'near');
  assert.equal(m.billBatchSellable({ expiryDate: daysFromToday(20), stock: 5 }), true);
  assert.equal(m.billBatchState({ expiryDate: daysFromToday(m.NEAR_EXPIRY_DAYS + 1), stock: 5 }), 'ok');
  assert.equal(m.billBatchState({ expiryDate: daysFromToday(0), stock: 5 }), 'near');   // the last valid day
  assert.equal(m.billBatchState({ expiryDate: '', stock: 5 }), 'ok');
});

test('search: only the newest request may show its results (overlapping requests)', () => {
  const gate = m.billMakeLatestGate();
  const shown = [];
  const t1 = gate.next();   // "par"   (slow)
  const t2 = gate.next();   // "para"  (fast)
  if (gate.isCurrent(t2)) shown.push('para results');
  if (gate.isCurrent(t1)) shown.push('par results (stale)');   // arrives last, must be ignored
  assert.deepEqual(shown, ['para results']);
  gate.next();               // the box was cleared: everything on its way is stale
  assert.equal(gate.isCurrent(t2), false);
});
