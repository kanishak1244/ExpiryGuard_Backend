// Run with:  node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('../../web/js/supplier_profile.js');

const row = (o) => Object.assign({
  product_id: 1, product_name: 'DOLO 650', company: 'Micro Labs', batch_number: 'D1', expiry_date: '2028-01-31', mrp: 90, purchase_id: 7, invoice_number: 'INV-7',
  purchase_date: '2026-10-01', quantity_received: 10, batch_received_total: 10, quantity_sold: 4, quantity_returned: 0, available: 6, status: 'Partially Sold',
  status_note: '4 sold', shared_batch: false, reconciled: true, source_recorded: true,
}, o);

test('latest request wins: a stale answer is not current', () => {
  const g = m.spMakeGate();
  const a = g.next();
  const b = g.next();
  assert.equal(g.isCurrent(a), false);
  assert.equal(g.isCurrent(b), true);
  g.bump();
  assert.equal(g.isCurrent(b), false);                       // closing the profile drops in-flight answers
});

test('stock table shows the columns and a separate stock-status badge', () => {
  const html = m.spStockTableHtml([row({})]);
  for (const h of ['Medicine', 'Batch', 'Invoice', 'Purchased', 'Expiry', 'Received', 'Sold', 'Returned', 'Available', 'Stock Status', 'MRP']) assert.ok(html.includes('>' + h + '<'), h);
  assert.ok(html.includes('Partially Sold'));
  assert.ok(html.includes('data-open-purchase="7"'));
});

test('unattributable sold/returned are shown as unavailable, never as numbers', () => {
  const html = m.spStockTableHtml([row({ quantity_sold: null, quantity_returned: null, shared_batch: true, reconciled: false, status: 'In Stock' })]);
  assert.equal((html.match(/class="sp-na"/g) || []).length >= 2, true);
  assert.ok(html.includes('shared'));
  assert.ok(html.includes('do not fully add up'));
  assert.ok(!html.includes('<td class="num">0</td>'.replace('0', 'undefined')));
});

test('each stock status has its own badge class; unknown ones are neutral', () => {
  assert.ok(m.spStockBadge('Expired').includes('bad'));
  assert.ok(m.spStockBadge('Sold Out').includes('muted'));
  assert.ok(m.spStockBadge('In Stock').includes('ok'));
  assert.ok(m.spStockBadge('Unavailable').includes('warn'));
  assert.ok(m.spStockBadge('Returned').includes('purple'));
});

test('payment status is separate from stock status and never invented', () => {
  assert.ok(m.spPaymentBadge('PAID').includes('Paid'));
  assert.ok(m.spPaymentBadge('partial').includes('Partial'));
  assert.ok(m.spPaymentBadge(null).includes('sp-na'));
  const bill = m.spBillHtml({ supplier_name: 'Alpha', invoice_number: 'A-1', voucher_no: 'PUR-00001', invoice_date: '2026-10-26', entered_on: '2026-10-26T10:00:00', purchase_status: 'Posted',
    payment_status: 'PARTIAL', paid_amount: null, outstanding_amount: null, total_amount: 560, tax_amount: 60, totals: { subtotal: 500, calculated_total: 560, matches_stored_total: true }, items: [] });
  assert.ok(bill.includes('Posted') && bill.includes('Partial'));
  assert.ok(bill.includes('Not certain for a part-paid bill'));
  assert.ok(!bill.includes('Stock Status'));
});

test('bill shows header ids, medicine lines with batch/expiry/qty/rate/MRP/GST and the totals', () => {
  const d = { supplier_name: 'Alpha Pharma', invoice_number: 'A-1', voucher_no: 'PUR-00012', invoice_date: '2026-10-26', entered_on: '2026-10-26T10:00:00', purchase_status: 'Posted',
    payment_status: 'UNPAID', paid_amount: 0, outstanding_amount: 560, total_amount: 560, tax_amount: 60, totals: { subtotal: 500, calculated_total: 560, matches_stored_total: true },
    items: [{ product_name: 'DOLO 650', company: 'Micro', batch_number: 'D1', expiry_date: '2028-01-31', quantity: 10, purchase_price: 50, mrp: 90, gst_rate: 12, taxable: 500, line_total: 560 }] };
  const html = m.spBillHtml(d);
  for (const s of ['Alpha Pharma', 'PUR-00012', 'A-1', 'DOLO 650', 'D1', '2028-01-31', '50.00', '90.00', '12%', '500.00', '560.00', 'Invoice total']) assert.ok(html.includes(s), s);
  assert.ok(!html.includes('differs'));
  assert.ok(m.spBillHtml(Object.assign({}, d, { totals: { subtotal: 500, calculated_total: 540, matches_stored_total: false } })).includes('differs'));
});

test('history rows carry the purchase id (not the invoice number) for opening the bill', () => {
  const html = m.spHistoryHtml([{ id: 41, voucher_no: 'PUR-00041', invoice_number: 'SAME-NO', invoice_date: '2026-10-01', items_count: 2, total_amount: 100, payment_status: 'UNPAID' }]);
  assert.ok(html.includes('data-purchase-id="41"') && html.includes('data-open-purchase="41"'));
  assert.ok(m.spHistoryHtml([]).includes('No purchase documents'));
});

test('ledger rows show purchase as credit and payments/returns as debit with the running balance', () => {
  const html = m.spLedgerHtml([{ date: '2026-10-26T10:00:00', type: 'PAYMENT', ref: 'CASH', credit: 0, debit: 100, balance: 460 }, { date: '2026-10-25T10:00:00', type: 'PURCHASE', ref: 'A-1', credit: 560, debit: 0, balance: 560 }]);
  assert.ok(html.includes('460.00') && html.includes('560.00') && html.includes('Payment') && html.includes('Purchase'));
});

test('text from the server is escaped', () => {
  const html = m.spStockTableHtml([row({ product_name: '<script>alert(1)</script>' })]) + m.spHistoryHtml([{ id: 1, voucher_no: '<b>', invoice_number: '<i>', items_count: 0, total_amount: 0 }]);
  assert.ok(!html.includes('<script>') && !html.includes('<i>'));
});
