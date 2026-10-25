/*
 * Create New Bill: instant medicine search on the screen itself.
 *
 * The pharmacy's batch list is downloaded ONCE when billing opens (GET /billing/catalog, about 100 KB gzip for 5,000
 * batches) and searched in memory on every keystroke, with no request and no waiting. The list is only a hint for
 * stock: when a medicine is added the screen confirms its live batches with the server, and the sale is checked again
 * on save. It is refreshed after every saved bill, every few minutes, when the window comes back to the front, and
 * with the refresh button. It lives in memory only (never stored on disk), so another pharmacy's data is never kept.
 * If the list cannot be loaded (or is too big), the screen keeps using the server search as before.
 *
 * The pure part (build / search / batch search / local stock update) has Node tests; the loader is browser-only.
 */
(function (root, factory) {
  const M = typeof require === 'function' && typeof module === 'object' ? require('./billing_math.js') : root;
  const api = factory(M);
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function (M) {
  const norm = (s) => String(s === null || s === undefined ? '' : s).toLowerCase().replace(/\s+/g, ' ').trim();
  const wordsOf = (s) => norm(s).split(/[\s,/()+-]+/).filter(Boolean);

  // { columns, rows } from the server -> search index. Each entry keeps the original row (server field names).
  function catBuild(data, today) {
    const cols = (data && data.columns) || [];
    const entries = ((data && data.rows) || []).map((vals) => {
      const row = {};
      cols.forEach((c, i) => { row[c] = vals[i]; });
      return catEntry(row, today);
    });
    return { entries, count: entries.length, complete: !(data && data.complete === false) };
  }
  function catEntry(row, today) {
    const nameL = norm(row.product_name);
    return {
      row,
      nameL,
      nameWords: wordsOf(row.product_name),
      otherWords: wordsOf(row.composition).concat(wordsOf(row.brand)),
      compL: norm(row.composition),
      batchL: norm(row.batch_number),
      barcode: norm(row.barcode),
      sellable: M.billBatchSellable({ expiryDate: row.expiry_date, stock: row.quantity }, today),
    };
  }

  // How well an entry matches (lower is better), or -1 for no match.
  //  0 exact barcode · 1 name starts with the text · 2 every typed word starts a word of the name ·
  //  3 every typed word starts a word of the name / composition / company · 4 batch or barcode starts with the text ·
  //  5 the text appears inside the name or composition
  function catRank(e, q, qTokens) {
    if (e.barcode && e.barcode === q.replace(/ /g, '')) return 0;
    if (e.nameL.indexOf(q) === 0) return 1;
    const startsSome = (words, t) => words.some((w) => w.indexOf(t) === 0);
    if (qTokens.every((t) => startsSome(e.nameWords, t))) return 2;
    if (qTokens.every((t) => startsSome(e.nameWords, t) || startsSome(e.otherWords, t))) return 3;
    const qq = q.replace(/ /g, '');
    if ((e.batchL && e.batchL.indexOf(qq) === 0) || (e.barcode && e.barcode.indexOf(qq) === 0)) return 4;
    if (e.nameL.indexOf(q) >= 0 || (e.compL && e.compL.indexOf(q) >= 0)) return 5;
    return -1;
  }

  const byExpiry = (a, b) => String(a.row.expiry_date || '9999-12-31').localeCompare(String(b.row.expiry_date || '9999-12-31'));

  // One result per medicine name: its first-to-sell batch (earliest valid expiry, in stock) with the total sellable
  // stock and all its batches. Prefix matches first, then medicines in stock, then the rest.
  function catSearch(index, query, limit) {
    const q = norm(query);
    if (!q || !index) return [];
    const qTokens = q.split(' ');
    const groups = new Map();
    for (const e of index.entries) {
      const r = catRank(e, q, qTokens);
      if (r < 0) continue;
      let g = groups.get(e.nameL);
      if (!g) { g = { rank: r, list: [] }; groups.set(e.nameL, g); }
      if (r < g.rank) g.rank = r;
      g.list.push(e);
    }
    // the other batches of a matched medicine (a batch-number match must still show the whole medicine)
    if (groups.size) {
      for (const e of index.entries) {
        const g = groups.get(e.nameL);
        if (g && g.list.indexOf(e) < 0) g.list.push(e);
      }
    }
    const out = [];
    for (const g of groups.values()) {
      g.list.sort(byExpiry);
      const ok = g.list.filter((e) => e.sellable);
      const rep = ok[0] || g.list[0];
      out.push({
        rank: g.rank, inStock: ok.length > 0, nameL: rep.nameL,
        result: Object.assign({}, rep.row, {
          total_stock: ok.reduce((a, e) => a + (Number(e.row.quantity) || 0), 0),
          _all_batches: g.list.map((e) => e.row),
        }),
      });
    }
    out.sort((a, b) => (a.rank - b.rank) || (Number(b.inStock) - Number(a.inStock)) || a.nameL.localeCompare(b.nameL));
    return out.slice(0, limit || 15).map((o) => o.result);
  }

  // Batch cell without a medicine: batch numbers containing the text, sellable first, then earliest expiry.
  function catBatchSearch(index, query, limit) {
    const q = norm(query).replace(/ /g, '');
    if (!q || !index) return [];
    return index.entries
      .filter((e) => e.batchL.indexOf(q) >= 0)
      .sort((a, b) => (Number(b.sellable) - Number(a.sellable)) || byExpiry(a, b))
      .slice(0, limit || 20)
      .map((e) => e.row);
  }

  // After a bill is saved: take the sold quantity off the batches in memory at once (strips; loose tablets as a part
  // of a strip), so the next search already shows the lower stock. The next refresh brings the server's exact numbers.
  function catApplySale(index, lines, today) {
    if (!index) return 0;
    let changed = 0;
    for (const l of lines || []) {
      const e = index.entries.find((x) => String(x.row.id) === String(l.product_id));
      if (!e) continue;
      const per = Number(l.tablets_per_strip || e.row.tablets_per_strip || e.row.units_per_pack) || 0;
      const used = String(l.unit_type || 'strip').toLowerCase().indexOf('loose') === 0 && per > 0 ? Number(l.quantity) / per : Number(l.quantity);
      e.row.quantity = Math.max(0, M.billR2((Number(e.row.quantity) || 0) - (used || 0)));
      e.sellable = M.billBatchSellable({ expiryDate: e.row.expiry_date, stock: e.row.quantity }, today);
      changed++;
    }
    return changed;
  }

  return { catNorm: norm, catBuild, catSearch, catBatchSearch, catApplySale, catRank };
});

// ---------------- browser: load / refresh / status ----------------
(function () {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const REFRESH_MS = 5 * 60 * 1000;
  const STALE_ON_FOCUS_MS = 2 * 60 * 1000;
  const state = { index: null, loadedAt: 0, loading: null, error: null, enabled: true, timer: null };

  function status() {
    const el = document.getElementById('bill-catalog-status');
    if (!el) return;
    if (state.loading && !state.index) { el.textContent = 'Loading medicine list…'; el.className = 'bill-hint'; return; }
    if (state.index) {
      const t = new Date(state.loadedAt);
      el.textContent = `Instant search: ${state.index.count.toLocaleString('en-IN')} batches · updated ${t.getHours().toString().padStart(2, '0')}:${t.getMinutes().toString().padStart(2, '0')}`;
      el.className = 'bill-hint';
      return;
    }
    el.textContent = state.error ? 'Medicine list not loaded — using live search' : '';
    el.className = 'bill-hint' + (state.error ? ' bill-hint-warn' : '');
  }

  async function load() {
    if (state.loading) return state.loading;
    if (!window.api || typeof window.api.getBillingCatalog !== 'function') return null;
    state.loading = (async () => {
      status();
      try {
        const t0 = performance.now();
        const data = await window.api.getBillingCatalog();
        const idx = catBuild(data);
        if (!idx.complete) { state.index = null; state.error = 'too big'; }   // very large pharmacy: server search
        else { state.index = idx; state.error = null; state.loadedAt = Date.now(); }
        state.lastLoadMs = Math.round(performance.now() - t0);
      } catch (err) {
        console.warn('Medicine list for instant search could not be loaded; live search is used.', err);
        state.error = String(err && err.message || err);
      } finally {
        state.loading = null;
        status();
      }
      return state.index;
    })();
    return state.loading;
  }

  window.billCatalog = {
    ready: () => !!(state.enabled && state.index),
    search: (q, limit) => catSearch(state.index, q, limit),
    batchSearch: (q, limit) => catBatchSearch(state.index, q, limit),
    applySale: (lines) => { const n = catApplySale(state.index, lines); return n; },
    load,
    refresh: () => load(),
    info: () => ({ count: state.index ? state.index.count : 0, loadedAt: state.loadedAt, lastLoadMs: state.lastLoadMs, error: state.error, enabled: state.enabled }),
    setEnabled: (on) => { state.enabled = !!on; },
  };

  function start() {
    if (!document.getElementById('billing-page')) return;
    load();
    state.timer = setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    const stale = () => { if (!document.hidden && Date.now() - state.loadedAt > STALE_ON_FOCUS_MS) load(); };
    document.addEventListener('visibilitychange', stale);
    window.addEventListener('focus', stale);
    const btn = document.getElementById('bill-catalog-refresh');
    if (btn) btn.addEventListener('click', () => load());
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
