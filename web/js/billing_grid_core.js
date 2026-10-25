/*
 * Create New Bill, spreadsheet grid: the pure rules (no page, no network), so they can be tested with Node.
 *   - which cell the cursor goes to on Tab / Shift+Tab / Enter / Up / Down / Left / Right
 *   - where a dropdown is placed so it is never cut off by the grid or the screen edge
 *   - batch choices for a medicine (earliest expiry first, expired never selectable)
 *   - quantity / discount validation
 *   - match highlighting
 * Loaded after billing_math.js and before billing_grid.js. In the browser the functions are globals; in Node they are exported.
 */
(function (root, factory) {
  const api = factory(typeof require === 'function' && typeof module === 'object' ? require('./billing_math.js') : root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function (M) {
  // Cells the cursor visits in a bill line, left to right. Packing, Expiry, MRP, GST and Amount are read only.
  const GRID_COLS = ['product', 'batch', 'unit', 'qty', 'disc'];
  // The empty row at the bottom (where the next medicine is typed) has only these.
  const ENTRY_COLS = ['product', 'batch'];

  const colsOf = (row, n) => (row >= n ? ENTRY_COLS : GRID_COLS);

  // pos = { row, col }; row === n means the empty entry row. Returns the next position (never off the grid).
  function gridTab(pos, shift, n) {
    const cols = colsOf(pos.row, n);
    const i = cols.indexOf(pos.col);
    if (!shift) {
      if (i < cols.length - 1) return { row: pos.row, col: cols[i + 1] };
      if (pos.row >= n) return { row: n, col: 'product' };                  // end of the entry row stays in it
      return { row: pos.row + 1, col: 'product' };                          // next line's Product (the entry row after the last)
    }
    if (i > 0) return { row: pos.row, col: cols[i - 1] };
    if (pos.row === 0) return { row: 0, col: 'product' };
    const prev = pos.row - 1;
    return { row: prev, col: GRID_COLS[GRID_COLS.length - 1] };
  }

  // Enter commits the cell. In the last cell of a line the cursor goes to the next EMPTY Product cell (the entry row).
  function gridEnter(pos, n) {
    const cols = colsOf(pos.row, n);
    const i = cols.indexOf(pos.col);
    if (i < cols.length - 1) return { row: pos.row, col: cols[i + 1] };
    return { row: n, col: 'product' };
  }

  // Up / Down move between lines in the same column (the entry row only has Product and Batch).
  function gridVertical(pos, dir, n) {
    const row = Math.min(n, Math.max(0, pos.row + dir));
    const cols = colsOf(row, n);
    const col = cols.indexOf(pos.col) >= 0 ? pos.col : cols[cols.length - 1];
    return { row, col };
  }

  // Left / Right move between cells only when the caret is already at that edge of the text (so editing is not hijacked).
  function gridHorizontal(pos, dir, n, caret) {
    const cols = colsOf(pos.row, n);
    const i = cols.indexOf(pos.col);
    if (caret) {
      if (dir < 0 && caret.start > 0) return null;
      if (dir > 0 && caret.end < caret.length) return null;
    }
    const j = i + dir;
    if (j < 0 || j >= cols.length) return null;
    return { row: pos.row, col: cols[j] };
  }

  // Where to put a dropdown: under the cell, or above it when there is not enough room; kept inside the screen.
  function gridPopupPlacement(anchor, size, view) {
    const gap = 2, margin = 8;
    const below = view.height - anchor.bottom - margin;
    const above = anchor.top - margin;
    const wantsAbove = size.height > below && above > below;
    const height = Math.max(120, Math.min(size.height, wantsAbove ? above - gap : below - gap));
    const width = Math.min(Math.max(size.width, anchor.width), view.width - 2 * margin);
    let left = anchor.left;
    if (left + width > view.width - margin) left = Math.max(margin, view.width - margin - width);
    const top = wantsAbove ? anchor.top - gap - height : anchor.bottom + gap;
    return { left, top, width, maxHeight: height, placement: wantsAbove ? 'above' : 'below' };
  }

  function escapeText(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Escaped text with the typed part marked (case-insensitive). Safe to put into innerHTML.
  function gridHighlight(text, query) {
    const t = String(text === null || text === undefined ? '' : text);
    const q = String(query || '').trim();
    if (!q) return escapeText(t);
    const at = t.toLowerCase().indexOf(q.toLowerCase());
    if (at < 0) return escapeText(t);
    return escapeText(t.slice(0, at)) + '<mark>' + escapeText(t.slice(at, at + q.length)) + '</mark>' + escapeText(t.slice(at + q.length));
  }

  // Batch choices for the Batch cell. Earliest expiry first (a batch without a date last). Expired / empty batches are
  // listed (so the cashier sees why) but marked not selectable. Typed text narrows by batch number.
  function gridBatchOptions(batches, query, today) {
    const q = String(query || '').trim().toLowerCase();
    return (batches || [])
      .filter(b => !q || String(b.batchNumber || '').toLowerCase().indexOf(q) >= 0)
      .map(b => {
        const state = M.billBatchState(b, today);
        return { batch: b, state, selectable: state === 'ok' || state === 'near' };
      })
      .sort((a, b) => {
        if (a.selectable !== b.selectable) return a.selectable ? -1 : 1;
        return (a.batch.expiryDate || '9999-12-31').localeCompare(b.batch.expiryDate || '9999-12-31');
      });
  }

  // Quantity typed in the cell. Whole numbers only, at least 1, not more than what is in stock.
  // item: { unitType, availableStock, unitsPerPack }
  function gridValidateQty(raw, item) {
    const text = String(raw === null || raw === undefined ? '' : raw).trim();
    if (text === '') return { ok: false, error: 'Enter a quantity.' };
    if (!/^\d+$/.test(text)) return { ok: false, error: 'Quantity must be a whole number.' };
    const n = Number(text);
    if (!(n >= 1)) return { ok: false, error: 'Quantity must be at least 1.' };
    const stock = Number(item && item.availableStock) || 0;
    const per = Number(item && item.unitsPerPack) || 0;
    const limit = (item && item.unitType === 'loose' && per > 0) ? Math.floor(stock * per) : stock;
    if (n > limit) return { ok: false, error: 'Only ' + limit + (item && item.unitType === 'loose' ? ' loose units' : ' in stock') + '.', limit };
    return { ok: true, value: n };
  }

  // Discount % typed in the cell: 0 to 100, at most 2 decimals. Empty means 0.
  function gridValidateDiscount(raw) {
    const text = String(raw === null || raw === undefined ? '' : raw).trim();
    if (text === '') return { ok: true, value: 0 };
    if (!/^\d+(\.\d{1,2})?$/.test(text)) return { ok: false, error: 'Discount must be a number such as 5 or 7.5.' };
    const n = Number(text);
    if (n > 100) return { ok: false, error: 'Discount cannot be more than 100%.' };
    return { ok: true, value: n };
  }

  // A line is "the same" as another when medicine row (product+batch) matches. Used to merge instead of duplicating.
  function gridSameLine(a, b) {
    return !!a && !!b && String(a.productId) === String(b.productId) && String(a.selectedBatch || '') === String(b.selectedBatch || '');
  }

  // Party search: name or phone contains the text; Walk-in / Cash Sale first when nothing typed.
  function gridFilterParties(parties, query) {
    const q = String(query || '').trim().toLowerCase();
    const list = (parties || []).filter(p => !q ||
      String(p.name || '').toLowerCase().indexOf(q) >= 0 || String(p.phone || '').toLowerCase().indexOf(q) >= 0);
    return list.slice(0, 30);
  }

  // Stable ids for lines (never an index, never time-based so two quick adds cannot collide).
  let seq = 0;
  function gridNewRowId() { seq += 1; return 'r' + seq + '-' + Math.random().toString(36).slice(2, 7); }

  return {
    GRID_COLS, ENTRY_COLS, gridTab, gridEnter, gridVertical, gridHorizontal, gridPopupPlacement, gridHighlight,
    gridBatchOptions, gridValidateQty, gridValidateDiscount, gridSameLine, gridFilterParties, gridNewRowId, escapeText,
  };
});
