/*
 * Add Manually (purchase entry): the pure rules, no page and no network, so they can be tested with Node.
 *   - line / bill amounts: the SAME steps as the server (purchase_entry.calc_line); the server recalculates on save and
 *     refuses a different total, so the screen is only a preview
 *   - expiry parsing (MM/YY, MM/YYYY, YYYY-MM-DD), row validation, the request body
 *   - draft store (browser storage injected, so it can be tested)
 *   - spreadsheet-style cell navigation
 * Needs billing_math.js (billR2) loaded first. In the browser the functions are globals; in Node they are exported.
 */
(function (root, factory) {
  const r2 = (typeof module === 'object' && module.exports) ? require('./billing_math.js').billR2 : root.billR2;
  const api = factory(r2);
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function (R2) {
  const num = (v) => { const n = parseFloat(String(v == null ? '' : v).replace(/,/g, '')); return isFinite(n) ? n : 0; };
  const int = (v) => { const n = parseInt(String(v == null ? '' : v), 10); return isFinite(n) ? n : 0; };

  // Visible grid columns in tab order. Everything else lives in the expandable details row.
  const PE_COLS = ['name', 'company', 'packing', 'batch', 'expiry', 'qty', 'free', 'rate', 'disc', 'gst', 'mrp'];
  const PE_DETAIL_COLS = ['composition', 'mfg', 'hsn', 'barcode'];

  function peNewRow() {
    return {
      id: 'r' + Math.random().toString(36).slice(2, 9), productId: null, catalogId: null, name: '', company: '', composition: '',
      packing: '', unitsPerPack: '', batch: '', mfg: '', expiry: '', unit: 'Strip', qty: '', free: '', rate: '', disc: '', gst: '12',
      mrp: '', hsn: '', barcode: '', confirmBelowCost: false, open: false,
    };
  }

  function peRowEmpty(r) { return !String(r.name || '').trim() && !String(r.batch || '').trim() && !num(r.qty) && !num(r.rate); }

  // The same formula as the server: taxable = qty x rate - discount%, GST on the taxable value, free units at no charge.
  function peCalcLine(r) {
    const qty = int(r.qty), free = int(r.free);
    const gross = R2(qty * num(r.rate));
    const discount = R2(gross * num(r.disc) / 100);
    const taxable = R2(gross - discount);
    const gst = R2(taxable * num(r.gst) / 100);
    const received = qty + free;
    return { gross, discount, taxable, gst, total: R2(taxable + gst), received, netUnitCost: received ? Math.round(taxable / received * 10000) / 10000 : 0 };
  }

  function peCalcTotals(rows) {
    const lines = rows.filter(r => !peRowEmpty(r)).map(peCalcLine);
    const sum = (k) => R2(lines.reduce((a, l) => a + l[k], 0));
    return { count: lines.length, subtotal: sum('gross'), discount: sum('discount'), taxable: sum('taxable'), gst: sum('gst'), total: sum('total'),
      cgst: R2(sum('gst') / 2), sgst: R2(sum('gst') - R2(sum('gst') / 2)) };
  }

  // "08/27" or "8/2027" -> last day of that month; "2027-08-31" is kept. Returns '' when it is not a valid date.
  function peParseExpiry(text) {
    const t = String(text || '').trim();
    if (!t) return '';
    let m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(t);
    if (m) { const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])); return (d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3]) ? t : ''; }
    m = /^(\d{1,2})\s*[\/\-.]\s*(\d{2}|\d{4})$/.exec(t);
    if (!m) return '';
    const month = +m[1]; let year = +m[2];
    if (month < 1 || month > 12) return '';
    if (year < 100) year += 2000;
    const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
    return year + '-' + String(month).padStart(2, '0') + '-' + String(last).padStart(2, '0');
  }

  function peTodayISO() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }

  // Problems that stop saving. Returns [{row (1-based), field, message}]. Blank rows are ignored.
  function peValidateRows(rows, todayISO) {
    const today = todayISO || peTodayISO();
    const out = [];
    const seen = {};
    let n = 0;
    rows.forEach((r, i) => {
      if (peRowEmpty(r)) return;
      n++;
      const add = (field, message) => out.push({ row: i + 1, field, message });
      if (!String(r.name || '').trim()) add('name', 'Medicine name is required.');
      if (!String(r.batch || '').trim()) add('batch', 'Batch number is required.');
      const exp = peParseExpiry(r.expiry);
      if (!exp) add('expiry', 'Enter the expiry as MM/YY or a full date.');
      else if (exp < today) add('expiry', 'This batch is already expired.');
      if (int(r.qty) <= 0) add('qty', 'Quantity must be 1 or more.');
      if (String(r.free || '').trim() && int(r.free) < 0) add('free', 'Free quantity cannot be negative.');
      if (!(num(r.rate) >= 0) || String(r.rate).trim() === '') add('rate', 'Purchase rate is required.');
      if (num(r.disc) < 0 || num(r.disc) > 100) add('disc', 'Discount must be between 0 and 100%.');
      if (num(r.gst) < 0 || num(r.gst) > 28) add('gst', 'GST must be between 0 and 28%.');
      if (!(num(r.mrp) > 0)) add('mrp', 'MRP is required.');
      if (String(r.mfg || '').trim()) {
        const mfg = peParseExpiry(r.mfg);
        if (!mfg) add('mfg', 'Manufacturing date is not valid.');
        else if (exp && mfg >= exp) add('mfg', 'Manufacturing date must be before expiry.');
      }
      const key = String(r.name || '').trim().toLowerCase() + '|' + String(r.batch || '').trim().toLowerCase();
      if (exp) {
        if (seen[key] && seen[key] !== exp) add('expiry', 'The same batch appears again with a different expiry.');
        seen[key] = exp;
      }
    });
    if (!n) out.push({ row: 0, field: 'rows', message: 'Add at least one medicine line.' });
    return out;
  }

  function peBuildPayload(header, rows) {
    const items = rows.filter(r => !peRowEmpty(r)).map(r => {
      const o = {
        product_name: String(r.name).trim(), batch_number: String(r.batch).trim(), expiry_date: peParseExpiry(r.expiry),
        quantity: int(r.qty), free_quantity: int(r.free), purchase_rate: num(r.rate), discount_percent: num(r.disc),
        gst_rate: String(r.gst).trim() === '' ? 12 : num(r.gst), mrp: num(r.mrp), confirm_mrp_below_cost: !!r.confirmBelowCost,
      };
      if (r.productId) o.product_id = r.productId;
      if (String(r.company || '').trim()) o.brand = String(r.company).trim();
      if (String(r.composition || '').trim()) o.composition = String(r.composition).trim();
      if (String(r.packing || '').trim()) o.pack_size_label = String(r.packing).trim();
      if (int(r.unitsPerPack) > 0) o.units_per_pack = int(r.unitsPerPack);
      if (String(r.hsn || '').trim()) o.hsn_code = String(r.hsn).trim();
      if (String(r.barcode || '').trim()) o.barcode = String(r.barcode).trim();
      const mfg = peParseExpiry(r.mfg);
      if (mfg) o.manufacturing_date = mfg;
      return o;
    });
    return {
      supplier_id: header.supplierId, invoice_number: String(header.invoiceNo).trim(), invoice_date: header.invoiceDate,
      payment_status: header.paymentStatus || 'UNPAID', expected_total: peCalcTotals(rows).total, items,
    };
  }

  // A medicine picked from the suggestions fills the row's medicine details only; batch, quantity and rates stay for the user.
  function peApplyMedicine(row, med, batch) {
    row.name = med.product_name || '';
    row.company = med.brand || '';
    row.composition = med.composition || '';
    row.packing = med.pack_size_label || '';
    row.unitsPerPack = med.units_per_pack || '';
    row.hsn = med.hsn_code || '';
    row.barcode = med.barcode || '';
    row.productId = med.product_id || null;
    row.catalogId = med.catalog_id || null;
    if (med.gst_rate != null) row.gst = String(med.gst_rate);
    if (med.last_purchase_rate) row.rate = String(med.last_purchase_rate);
    if (med.mrp) row.mrp = String(med.mrp);
    if (batch) {
      row.batch = batch.batch_number || '';
      row.expiry = batch.expiry_date || '';
      row.productId = batch.product_id || row.productId;
      if (batch.mrp) row.mrp = String(batch.mrp);
    }
    return row;
  }

  // Spreadsheet movement. Returns the next cell {row, col} or {newRow:true}; col is a key of PE_COLS.
  // Tab / Enter go right, then on to the next row; Shift+Tab goes back. Enter in the last cell of the last row adds a row.
  function peNextCell(rowIdx, col, rowCount, back) {
    let c = PE_COLS.indexOf(col);
    if (c < 0) c = 0;
    if (back) {
      if (c > 0) return { row: rowIdx, col: PE_COLS[c - 1] };
      return rowIdx > 0 ? { row: rowIdx - 1, col: PE_COLS[PE_COLS.length - 1] } : { row: 0, col: PE_COLS[0] };
    }
    if (c < PE_COLS.length - 1) return { row: rowIdx, col: PE_COLS[c + 1] };
    return rowIdx + 1 < rowCount ? { row: rowIdx + 1, col: PE_COLS[0] } : { newRow: true };
  }

  // Drafts: kept in this browser only (nothing is posted, no stock or balance changes).
  const PE_DRAFT_KEY = 'df_purchase_drafts_v1';
  function peDraftStore(storage) {
    const read = () => { try { const v = JSON.parse(storage.getItem(PE_DRAFT_KEY) || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; } };
    const write = (list) => { try { storage.setItem(PE_DRAFT_KEY, JSON.stringify(list)); return true; } catch (e) { return false; } };
    return {
      list: () => read().sort((a, b) => String(b.savedAt).localeCompare(String(a.savedAt))),
      get: (id) => read().find(d => d.id === id) || null,
      save(draft) {
        const list = read();
        const i = list.findIndex(d => d.id === draft.id);
        const rec = Object.assign({}, draft, { savedAt: new Date().toISOString() });
        if (i >= 0) list[i] = rec; else list.push(rec);
        return write(list) ? rec : null;
      },
      remove(id) { write(read().filter(d => d.id !== id)); },
    };
  }

  return {
    PE_COLS, PE_DETAIL_COLS, PE_DRAFT_KEY, peNewRow, peRowEmpty, peCalcLine, peCalcTotals, peParseExpiry, peTodayISO,
    peValidateRows, peBuildPayload, peApplyMedicine, peNextCell, peDraftStore,
  };
});
