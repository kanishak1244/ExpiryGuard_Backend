/*
 * Create New Bill: the pure rules (no page, no network), so they can be tested with Node.
 *   - money rounding: decimal-safe, half away from zero, same as the server (crud._round_half_up)
 *   - bill arithmetic: same steps and same order as the server's create_sale_transaction, so the amount on the
 *     screen is the amount on the saved invoice
 *   - batch state: expired / out of stock / near expiry / ok
 *   - "latest request wins" gate for the medicine search
 * Loaded before billing_flow.js. In the browser the functions are globals; in Node they are exported.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function () {
  // Medicines expiring within this many days get a warning (the dashboard's "expiring soon" uses the same 60 days).
  const NEAR_EXPIRY_DAYS = 60;

  // Rounds to 2 decimals using the decimal text of the number (2.675 -> 2.68), never the binary value.
  function billR2(x) {
    const n = Number(x);
    if (!isFinite(n)) return 0;
    const sign = n < 0 ? -1 : 1;
    const a = Math.abs(n);
    const s = String(a);
    const r = s.indexOf('e') !== -1 ? Math.round(a * 100) / 100 : Number(Math.round(Number(s + 'e2')) + 'e-2');
    return sign * r;
  }

  // 0% is a real GST rate: only a missing/invalid value falls back to 0 here (the screen refuses to add such a line).
  function billGstOf(item) {
    const g = Number(item.gstRate);
    return isFinite(g) ? g : 0;
  }

  // A discount is 0-100 %; anything else is pulled back into that range so a total can never go negative.
  function billDiscPct(item) {
    return Math.min(100, Math.max(0, Number(item.discountPercent) || 0));
  }

  function billDaysToExpiry(dateStr, today) {
    if (!dateStr) return null;
    const d = new Date(String(dateStr).slice(0, 10) + 'T00:00:00');
    if (isNaN(d.getTime())) return null;
    const t = today ? new Date(new Date(today).toDateString()) : new Date(new Date().toDateString());
    return Math.floor((d - t) / 86400000);
  }

  // 'expired' (expiry date before today, the server's rule) | 'out' | 'near' | 'ok'
  function billBatchState(b, today) {
    const days = billDaysToExpiry(b.expiryDate, today);
    if (days !== null && days < 0) return 'expired';
    if (!(Number(b.stock) > 0)) return 'out';
    if (days !== null && days <= NEAR_EXPIRY_DAYS) return 'near';
    return 'ok';
  }
  function billBatchSellable(b, today) {
    const st = billBatchState(b, today);
    return st === 'ok' || st === 'near';
  }

  // Line by line, like the server: line discount (a rupee amount taken off before GST), bill discount shared over
  // the lines (the last line takes the remainder), CGST and SGST each rounded per line.
  // The bill discount is one value with a mode: 'percent' (of the taxable subtotal) or 'flat' (rupees taken off the
  // taxable subtotal, before GST: the server's rule). A plain number means percent (older callers).
  function billDiscountSpec(d) {
    if (d && typeof d === 'object') return { mode: d.mode === 'flat' ? 'flat' : 'percent', value: Number(d.value) || 0 };
    return { mode: 'percent', value: Number(d) || 0 };
  }

  // Checks what was typed in the Bill Discount box. Returns { ok, value } or { ok:false, error }.
  // percent: 0-100; flat: not more than the taxable subtotal (the server refuses a bigger one). Blank means 0.
  function billCheckDiscount(mode, text, taxableSubtotal) {
    const raw = String(text === null || text === undefined ? '' : text).trim();
    if (raw === '') return { ok: true, value: 0 };
    if (!/^\d+(\.\d{1,2})?$/.test(raw)) return { ok: false, error: 'Enter a number such as 10 or 7.5 (no minus sign or letters).' };
    const n = Number(raw);
    if (mode === 'flat') {
      const max = Math.max(0, Number(taxableSubtotal) || 0);
      if (n > max + 0.0001) return { ok: false, error: 'A \u20b9 discount cannot be more than the bill value before GST (\u20b9' + max.toFixed(2) + ').' };
    } else if (n > 100) {
      return { ok: false, error: 'A % discount cannot be more than 100.' };
    }
    return { ok: true, value: n };
  }

  function billComputeLines(items, billDiscount) {
    const lines = items.map(item => {
      const qty = Math.floor(Number(item.quantity)) || 1;
      const gross = billR2(qty * Number(item.rate || 0));
      const lineDisc = billR2(Math.round(gross * billDiscPct(item)) / 100);
      return { item, gross, lineDisc, taxable: billR2(gross - lineDisc), gst: billGstOf(item) };
    });
    const lineDiscTotal = lines.reduce((a, l) => a + l.lineDisc, 0);
    const grossSubtotal = lines.reduce((a, l) => a + l.gross, 0);
    const taxableSubtotal = billR2(grossSubtotal - lineDiscTotal);
    const spec = billDiscountSpec(billDiscount);
    const billDiscountAmount = spec.mode === 'flat'
      ? Math.min(billR2(Math.max(0, spec.value)), taxableSubtotal)
      : Math.min(billR2(taxableSubtotal * Math.min(100, Math.max(0, spec.value)) / 100), taxableSubtotal);
    let allocated = 0;
    lines.forEach((l, idx) => {
      const last = idx === lines.length - 1;
      const share = last ? billR2(billDiscountAmount - allocated)
        : (taxableSubtotal > 0 ? billR2(billDiscountAmount * l.taxable / taxableSubtotal) : 0);
      if (!last) allocated += share;
      l.finalTaxable = billR2(l.taxable - share);
      l.cgst = billR2(l.finalTaxable * (billR2(l.gst / 2) / 100));
      l.sgst = l.cgst;
      l.tax = billR2(l.cgst + l.sgst);
      l.total = billR2(l.finalTaxable + l.tax);
    });
    const sum = (key) => billR2(lines.reduce((a, l) => a + l[key], 0));
    return {
      lines, taxableSubtotal, billDiscount: billDiscountAmount, lineDiscTotal: billR2(lineDiscTotal),
      netTaxable: sum('finalTaxable'), cgst: sum('cgst'), sgst: sum('sgst'), totalGst: sum('tax'), grandTotal: sum('total'),
    };
  }

  // One line's amount before any bill-level discount (shown in the Amount column).
  function billRowAmount(item) {
    const qty = Math.floor(Number(item.quantity)) || 1;
    const gross = billR2(qty * Number(item.rate || 0));
    const taxable = billR2(gross - billR2(Math.round(gross * billDiscPct(item)) / 100));
    return billR2(taxable + billR2(taxable * (billR2(billGstOf(item) / 2) / 100)) * 2);
  }

  // "Latest request wins": next() hands out a ticket; only the newest ticket is current, so a slow, older response
  // can never overwrite the results of a newer query.
  function billMakeLatestGate() {
    let latest = 0;
    return { next: () => ++latest, isCurrent: (ticket) => ticket === latest };
  }

  return {
    NEAR_EXPIRY_DAYS, billDiscountSpec, billCheckDiscount, billR2, billGstOf, billDiscPct, billDaysToExpiry, billBatchState, billBatchSellable,
    billComputeLines, billRowAmount, billMakeLatestGate,
  };
});
