/*
 * Counter Sale: the pure rules (no page, no network), so they can be tested with Node.
 *
 * One Counter Sale tab holds many CUSTOMER transactions. Lines of every draft customer sit in one list (the grid) and
 * each line carries its customerId. Lifecycle of a customer: draft (this screen only) -> ready (saved on the server,
 * no stock deducted) -> converted (one regular invoice, linked) | cancelled. See counter_sale.py.
 * Loaded after billing_math.js. Globals in the browser, exports in Node.
 */
(function (root, factory) {
  const M = typeof require === 'function' && typeof module === 'object' ? require('./billing_math.js') : root;
  const api = factory(M);
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function (M) {
  const R2 = M.billR2;

  // Stable ids (never a position): 24 hex characters, valid as the server's transaction id.
  function counterNewId() {
    let s = '';
    for (let i = 0; i < 6; i++) s += Math.floor(Math.random() * 0x10000).toString(16).padStart(4, '0');
    return s;
  }

  function counterNewCustomer(ref, id) {
    return { id: id || counterNewId(), ref: String(ref), name: '', phone: '', status: 'draft', heldId: null, replacesId: null };
  }

  // A fresh counter session. Reference numbers restart each day (1, 2, 3 ...).
  function counterBlank(today) {
    const c = counterNewCustomer('1');
    return { customers: [c], activeId: c.id, nextRef: 2, date: today || '' };
  }

  // Next customer reference; the numbering starts again at 1 on a new day.
  function counterNextRef(counter, today) {
    if (today && counter.date && counter.date !== today) { counter.date = today; counter.nextRef = 1; }
    if (today && !counter.date) counter.date = today;
    const ref = String(counter.nextRef || 1);
    counter.nextRef = (Number(counter.nextRef) || 1) + 1;
    return ref;
  }

  const counterLinesOf = (items, customerId) => (items || []).filter((i) => i.customerId === customerId);

  // New lines of a customer go right after that customer's last line (the grid stays grouped by customer).
  function counterInsertIndex(items, customerId) {
    let last = -1;
    (items || []).forEach((it, i) => { if (it.customerId === customerId) last = i; });
    return last >= 0 ? last + 1 : (items || []).length;
  }

  // One customer's own totals, with the same arithmetic as the invoice (billing_math.js = server rules).
  function counterTotals(items, customerId) {
    const lines = counterLinesOf(items, customerId);
    const c = M.billComputeLines(lines, 0);
    return {
      count: lines.length,
      units: lines.reduce((a, l) => a + (Math.floor(Number(l.quantity)) || 0), 0),
      taxable: c.netTaxable, gst: c.totalGst, total: c.grandTotal, discount: c.lineDiscTotal,
    };
  }

  // Why a line cannot be turned into an invoice yet (null when it can). The server checks all of this again.
  function counterLineProblem(it, today) {
    const name = it.name || 'line';
    if (!it.productId) return `${name}: medicine reference is missing. Remove the line and add it again.`;
    const q = Number(it.quantity);
    if (!(q >= 1) || Math.floor(q) !== q) return `${name}: quantity must be a whole number of 1 or more.`;
    if (!(Number(it.rate) > 0)) return `${name}: no price, so it cannot be billed.`;
    if (M.billBatchState({ expiryDate: it.expiryDate, stock: it.availableStock }, today) === 'expired') {
      return `${name}: batch ${it.selectedBatch || '-'} is expired. Choose another batch or remove the line.`;
    }
    if (it.unitType !== 'loose' && q > Number(it.availableStock)) return `${name}: only ${Number(it.availableStock)} in stock for batch ${it.selectedBatch || '-'}.`;
    return null;
  }
  function counterCustomerProblem(items, customerId, today) {
    const lines = counterLinesOf(items, customerId);
    if (!lines.length) return { message: 'Add at least one medicine for this customer first.', index: -1 };
    for (const l of lines) {
      const msg = counterLineProblem(l, today);
      if (msg) return { message: msg, index: items.indexOf(l) };
    }
    return null;
  }

  // The line as the server stores it. discount is RUPEES (what the invoice uses); discount_percent is what was typed.
  function counterHoldLine(it) {
    const qty = Math.floor(Number(it.quantity)) || 1;
    const gross = R2(qty * Number(it.rate || 0));
    const pct = M.billDiscPct(it);
    return {
      product_id: it.productId,
      product_name: it.name || 'Medicine',
      quantity: qty,
      unit_type: it.unitType === 'loose' ? 'loose_tablet' : 'strip',
      unit_price: Number(it.rate),
      discount: R2(Math.round(gross * pct) / 100),
      discount_percent: pct,
      tablets_per_strip: it.unitsPerPack || null,
      batch_number: it.selectedBatch || null,
      expiry_date: it.expiryDate || null,
      hsn_code: it.hsnCode || null,
      gst_percentage: Number(it.gstRate),
    };
  }

  // A line of a transaction read back from the server (GET /billing/counter/{id}) -> a grid line.
  function counterLineFromServer(it, customerId, newRowId) {
    const live = it.live || {};
    const loose = it.unit_type === 'loose_tablet' || it.unit_type === 'loose';
    const mrp = Number(live.mrp) > 0 ? Number(live.mrp) : (loose ? Number(it.unit_price) * (Number(it.tablets_per_strip) || 10) : Number(it.unit_price));
    const per = Number(live.units_per_pack || it.tablets_per_strip) || null;
    const loosePrice = Number(live.price_per_unit) > 0 ? Number(live.price_per_unit) : (per ? R2(mrp / per) : null);
    const line = {
      id: newRowId, customerId, productId: it.product_id, name: it.product_name, brand: live.brand || '', composition: live.composition || '',
      hsnCode: it.hsn_code || '3004', selectedBatch: it.batch_number || '', expiryDate: live.expiry_date || it.expiry_date || '',
      availableStock: live.stock !== undefined && live.stock !== null ? Number(live.stock) : 0,
      unitType: loose ? 'loose' : 'strip', packPrice: mrp, unitsPerPack: per, packSize: live.pack_size_label || '', loosePrice,
      rate: Number(it.unit_price), quantity: it.quantity, freeQuantity: 0,
      discountPercent: it.discount_percent !== null && it.discount_percent !== undefined ? Number(it.discount_percent) : 0,
      gstRate: Number(it.gst_percentage), batches: [],
    };
    const base = loose ? loosePrice : mrp;
    line.rateOverride = base && Number(line.rate) < base - 0.005 ? Number(line.rate) : null;
    if (live.is_expired) line.expiryDate = live.expiry_date || line.expiryDate;
    return line;
  }

  // Draft transactions survive a page reload / closing the tab: saved in this browser only, per pharmacy, same day.
  function counterSerialize(counter, items) {
    return JSON.stringify({ v: 1, counter, items });
  }
  function counterRestore(text, today) {
    try {
      const d = JSON.parse(text);
      if (!d || d.v !== 1 || !d.counter || !Array.isArray(d.counter.customers)) return null;
      const keep = d.counter.customers.filter((c) => c.status === 'draft');
      if (!keep.length) return null;
      const ids = new Set(keep.map((c) => c.id));
      const items = (d.items || []).filter((i) => ids.has(i.customerId));
      const counter = Object.assign({}, d.counter, { customers: keep });
      if (!ids.has(counter.activeId)) counter.activeId = keep[0].id;
      return { counter, items, sameDay: !d.counter.date || d.counter.date === today };
    } catch (e) {
      return null;
    }
  }

  const COUNTER_STATUS_LABEL = { draft: 'In progress', ready: 'Ready', converted: 'Converted', cancelled: 'Cancelled' };
  const counterStatusLabel = (s) => COUNTER_STATUS_LABEL[String(s || '').toLowerCase()] || s;

  return {
    counterNewId, counterNewCustomer, counterBlank, counterNextRef, counterLinesOf, counterInsertIndex, counterTotals,
    counterLineProblem, counterCustomerProblem, counterHoldLine, counterLineFromServer, counterSerialize, counterRestore,
    counterStatusLabel,
  };
});
