// Run with:  node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('../../web/js/purchase_entry_core.js');

const row = (o) => Object.assign(m.peNewRow(), { name: 'NEWMED', batch: 'B1', expiry: '12/30', qty: '10', rate: '50', gst: '12', mrp: '90' }, o);

test('line math matches the server (same fixtures as tests/test_manual_purchase.py)', () => {
  const c = m.peCalcLine(row({ qty: '10', free: '2', rate: '50', disc: '10', gst: '12' }));
  assert.deepEqual([c.gross, c.discount, c.taxable, c.gst, c.total, c.received, c.netUnitCost], [500, 50, 450, 54, 504, 12, 37.5]);
  const z = m.peCalcLine(row({ qty: '3', free: '', rate: '33.33', disc: '', gst: '0' }));
  assert.deepEqual([z.taxable, z.gst, z.total], [99.99, 0, 99.99]);
  assert.equal(m.peCalcLine(row({ qty: '1', rate: '2.675', gst: '0' })).taxable, 2.68);
});

test('totals skip blank rows and split GST evenly', () => {
  const t = m.peCalcTotals([row({}), m.peNewRow(), row({ qty: '4', rate: '25' })]);
  assert.equal(t.count, 2);
  assert.equal(t.taxable, 600);
  assert.equal(t.gst, 72);
  assert.equal(t.total, 672);
  assert.equal(t.cgst + t.sgst, 72);
});

test('expiry parsing', () => {
  assert.equal(m.peParseExpiry('08/27'), '2027-08-31');
  assert.equal(m.peParseExpiry('2/2028'), '2028-02-29');
  assert.equal(m.peParseExpiry('2027-08-15'), '2027-08-15');
  assert.equal(m.peParseExpiry('13/27'), '');
  assert.equal(m.peParseExpiry('2027-02-30'), '');
  assert.equal(m.peParseExpiry('soon'), '');
});

test('validation: blank rows ignored, problems listed per row', () => {
  assert.equal(m.peValidateRows([m.peNewRow()], '2026-10-26')[0].field, 'rows');
  assert.deepEqual(m.peValidateRows([row({})], '2026-10-26'), []);
  const bad = m.peValidateRows([row({ name: '', batch: '', expiry: '01/20', qty: '0', rate: '', mrp: '0', gst: '40', free: '3', disc: '5' }),
    row({ name: '', batch: '', qty: '0', rate: '', mrp: '0', gst: '40', expiry: '01/20' })], '2026-10-26');
  assert.deepEqual(bad.map(p => p.field), ['rows'], 'rows with no name, batch, qty or rate are treated as blank');
  const bad2 = m.peValidateRows([row({ name: '', batch: '', expiry: '01/20', qty: '2', rate: '', mrp: '0', gst: '40' })], '2026-10-26').map(p => p.field);
  for (const f of ['name', 'batch', 'expiry', 'rate', 'mrp', 'gst']) assert.ok(bad2.includes(f), f);
  assert.ok(m.peValidateRows([row({ qty: '0', rate: '5' })], '2026-10-26').some(p => p.field === 'qty'));
  const dup = m.peValidateRows([row({ expiry: '12/30' }), row({ expiry: '11/30' })], '2026-10-26');
  assert.ok(dup.some(p => p.row === 2 && p.field === 'expiry'));
  assert.ok(m.peValidateRows([row({ mfg: '12/31' })], '2026-10-26').some(p => p.field === 'mfg'));
});

test('payload: only filled rows, server field names, expected total', () => {
  const rows = [row({ company: 'Acme', productId: 7, free: '2', disc: '10' }), m.peNewRow()];
  const p = m.peBuildPayload({ supplierId: 3, invoiceNo: ' INV-9 ', invoiceDate: '2026-10-26', paymentStatus: 'UNPAID' }, rows);
  assert.equal(p.items.length, 1);
  assert.equal(p.invoice_number, 'INV-9');
  assert.equal(p.items[0].product_id, 7);
  assert.equal(p.items[0].brand, 'Acme');
  assert.equal(p.items[0].expiry_date, '2030-12-31');
  assert.equal(p.items[0].free_quantity, 2);
  assert.equal(p.expected_total, 504);
});

test('picking a medicine fills master data only; batch / qty stay empty; no stale text carries over', () => {
  const r = m.peNewRow();
  m.peApplyMedicine(r, { product_id: 5, product_name: 'DOLO 650', brand: 'Micro', composition: 'Paracetamol', units_per_pack: 15, hsn_code: '3004', gst_rate: 12, last_purchase_rate: 60, mrp: 100 });
  assert.equal(r.name, 'DOLO 650');
  assert.equal(r.productId, 5);
  assert.equal(r.batch, '');
  assert.equal(r.qty, '');
  const next = m.peNewRow();
  assert.equal(next.name, '');
  assert.equal(next.batch, '');
  assert.equal(next.productId, null);
  m.peApplyMedicine(r, { product_id: 5, product_name: 'DOLO 650' }, { product_id: 9, batch_number: 'D2', expiry_date: '2028-01-31', mrp: 110 });
  assert.deepEqual([r.batch, r.expiry, r.productId, r.mrp], ['D2', '2028-01-31', 9, '110']);
});

test('cell navigation: Tab/Enter right then down, Shift+Tab back, new row at the end', () => {
  const last = m.PE_COLS[m.PE_COLS.length - 1];
  assert.deepEqual(m.peNextCell(0, 'name', 2, false), { row: 0, col: 'company' });
  assert.deepEqual(m.peNextCell(0, last, 2, false), { row: 1, col: 'name' });
  assert.deepEqual(m.peNextCell(1, last, 2, false), { newRow: true });
  assert.deepEqual(m.peNextCell(1, 'name', 2, true), { row: 0, col: last });
  assert.deepEqual(m.peNextCell(0, 'name', 2, true), { row: 0, col: 'name' });
});

test('drafts: save, list newest first, restore exactly, remove; broken storage is survivable', () => {
  const mem = {}; const storage = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } };
  const s = m.peDraftStore(storage);
  const draft = { id: 'd1', header: { invoiceNo: 'A-1' }, rows: [row({ name: 'X' })] };
  s.save(draft);
  s.save({ id: 'd2', header: {}, rows: [] });
  assert.equal(s.list().length, 2);
  assert.deepEqual(s.get('d1').rows[0].name, 'X');
  s.save(Object.assign({}, draft, { header: { invoiceNo: 'A-2' } }));
  assert.equal(s.list().length, 2);
  assert.equal(s.get('d1').header.invoiceNo, 'A-2');
  s.remove('d1');
  assert.equal(s.get('d1'), null);
  const broken = m.peDraftStore({ getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); } });
  assert.deepEqual(broken.list(), []);
  assert.equal(broken.save(draft), null);
});
