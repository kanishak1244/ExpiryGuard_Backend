// Run with:  node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('../../web/js/doc_review.js');

const line = (o) => Object.assign({
  row: 1, product_name: 'DOLO 650', hsn_code: '3004', gst_rate: 12, batch_number: 'D1', expiry_date: '2028-01-31', quantity: 10, free_qty: 0,
  purchase_price: 50, mrp: 90, discount_percent: 0, total_price: 500, blocking: [], warnings: [], match: { status: 'inventory', text: 'In your inventory (1 batch)' },
}, o);

test('table renders structured rows with all critical columns', () => {
  const html = m.drLinesTableHtml([line({}), line({ row: 2, product_name: 'AZEE 500' })]);
  for (const h of ['Medicine', 'GST %', 'Batch', 'Expiry', 'Qty', 'Rate', 'MRP', 'Taxable', 'Amount']) assert.ok(html.includes('>' + h + '<'), h);
  assert.equal((html.match(/<tr/g) || []).length, 3);                       // header + 2 rows
  assert.ok(html.includes('500.00'));
  assert.ok(html.includes('HSN 3004'));
  assert.ok(!html.includes('Disc 0'), 'no discount text when there is none');
  assert.ok(m.drLinesTableHtml([line({ discount_percent: 10 })]).includes('Disc 10%'));
  assert.ok(html.includes('01/2028'), 'expiry shown as MM/YYYY');
});

test('missing critical fields are marked, optional ones show a dash, nothing is invented', () => {
  const l = line({ batch_number: null, mrp: null, expiry_date: null, hsn_code: null, total_price: null,
    blocking: [{ field: 'batch_number', message: 'Batch: batch is empty.' }, { field: 'mrp', message: 'MRP is missing.' }, { field: 'expiry_date', message: 'Expiry: expiry missing.' }] });
  const html = m.drLinesTableHtml([l]);
  assert.equal((html.match(/dr-miss/g) || []).length, 3);                   // batch, mrp, expiry
  assert.ok(html.includes('dr-rowbad'));
  assert.ok(html.includes('Batch: batch is empty.'));
  assert.ok(html.includes('dr-na'));                                        // HSN / amount are optional: a dash
});

test('line text is escaped', () => {
  const html = m.drLinesTableHtml([line({ product_name: '<img src=x onerror=alert(1)>' })]);
  assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;img'));
});

test('empty extraction points to Edit Bill Details', () => {
  assert.ok(m.drLinesTableHtml([]).includes('Edit Bill Details'));
});

test('supplier block: linked shows name, unlinked warns and offers a link action (never auto-links)', () => {
  const linked = m.drSummaryHtml({ supplier: { id: 1, name: 'Alpha Pharma', gstin: '07AAA' }, status: 'Needs Review', line_count: 2, invoice_number: 'I-1', invoice_date: '2026-10-26', printed_total: 1000, computed: { total: 1000 }, notes: [] });
  assert.ok(linked.includes('Alpha Pharma') && linked.includes('Linked'));
  const open = m.drSummaryHtml({ supplier: null, supplier_status: 'needs_matching', extracted_supplier_name: 'ALPHA PHARMA LTD', status: 'Needs Review', line_count: 0, notes: [] });
  assert.ok(open.includes('Needs supplier matching') && open.includes('Link or create supplier') && open.includes('ALPHA PHARMA LTD'));
  assert.ok(m.drSummaryHtml({ supplier: null, supplier_status: 'unlinked', status: 'Failed', line_count: 0, notes: [] }).includes('Unlinked'));
});

test('summary is read-only: no inputs or editable fields', () => {
  const html = m.drSummaryHtml({ supplier: null, supplier_status: 'unlinked', status: 'Needs Review', line_count: 1, invoice_number: 'X', notes: [], corrected: true }) + m.drLinesTableHtml([line({})]);
  assert.ok(!/<input|<select|<textarea|contenteditable/i.test(html));
});

test('problems list shows the count and the first problems', () => {
  const v = { blocking_count: 7, verified: false, blocking: Array.from({ length: 7 }, (_, i) => ({ field: 'row ' + i, message: 'bad ' + i })) };
  const html = m.drProblemsHtml(v);
  assert.ok(html.includes('7 problems') && html.includes('and 2 more'));
  assert.equal(m.drProblemsHtml({ blocking_count: 0, blocking: [] }), '');
  assert.equal(m.drProblemsHtml(Object.assign({}, v, { verified: true })), '');
});

test('actions follow the document status', () => {
  assert.deepEqual(m.drActions({ status: 'Needs Review', can_edit: true, verified: false, failed: false }), { edit: true, draft: true, confirm: true, ocr: false, back: true });
  assert.deepEqual(m.drActions({ status: 'Verified', can_edit: false, verified: true, failed: false }), { edit: false, draft: false, confirm: false, ocr: false, back: true });
  assert.deepEqual(m.drActions({ status: 'Failed', can_edit: true, verified: false, failed: true }), { edit: true, draft: true, confirm: false, ocr: true, back: true });
  assert.equal(m.drActions({ status: 'Processing', can_edit: true, verified: false, failed: false }).confirm, false);
});

test('taxable is calculated from quantity, rate and discount only when both exist', () => {
  assert.equal(m.drTaxable(line({ quantity: 10, purchase_price: 50, discount_percent: 10 })), 450);
  assert.equal(m.drTaxable(line({ quantity: null })), null);
});

test('a saved draft is shown on the review with its reference and the no-stock reminder', () => {
  const html = m.drSummaryHtml({ supplier: null, supplier_status: 'unlinked', status: 'Needs Review', line_count: 1, notes: [], draft: { reference: 'DRAFT-00007' } });
  assert.ok(html.includes('DRAFT-00007') && html.includes('Nothing has been added to stock'));
  assert.ok(!m.drSummaryHtml({ supplier: null, supplier_status: 'unlinked', status: 'Needs Review', line_count: 1, notes: [] }).includes('Saved as draft'));
});
