// Live Inventory: keyboard focus and ticked checkboxes are independent; the newest ticked medicine (by ID) locks
// the details panel; unticking falls back to the previous ticked one, then to the focused row.
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'js', 'app.js'), 'utf8');
const block = src.match(/\/\/ The newest still-ticked medicine[\s\S]*?window\.medSyncLock = function\(\) \{ medShowPanel\(\); \};/);
assert(block, 'selection block not found in app.js');

const rendered = [];
const factory = new Function('window', 'selectedStockIds', 'medRenderPanel', 'medScheduleFetch', `
  const medDetail = { rows: new Map(), order: [], selectedId: null, lockOrder: [], lockedRows: new Map(), shownId: null };
  ${block[0]}
  return { medDetail, medShownId, medShownItem, medShowPanel };
`);
const win = {};
const selected = new Set();
const api = factory(win, selected, (p) => rendered.push(p ? p.id : null), () => {});
const { medDetail } = api;
const mk = (id, name) => ({ id, product_name: name || 'M' + id });
const shown = () => (api.medShownItem() || {}).id;
const tick = (id, on) => { if (on) selected.add(id); else selected.delete(id); win.medOnCheckChange(id, on); };
const focus = (id) => { medDetail.selectedId = id; if (api.medShownId() === id || !selected.size) api.medShowPanel(); };

medDetail.rows = new Map([1, 2, 3, 4].map(i => [i, mk(i)]));

// nothing ticked: the panel follows the focused row
focus(1); assert.strictEqual(shown(), 1);
focus(3); assert.strictEqual(shown(), 3);
// ticking locks to that exact id, even though focus is elsewhere
tick(2, true); assert.strictEqual(shown(), 2);
focus(4); focus(1); assert.strictEqual(shown(), 2, 'focus moves must not change the locked medicine');
assert.strictEqual(selected.size, 1, 'keyboard focus must never tick a checkbox');
// two ticked: the most recent wins; unticking it shows the previous one; none left -> focused row
tick(3, true); assert.strictEqual(shown(), 3);
tick(3, false); assert.strictEqual(shown(), 2);
tick(2, false); assert.strictEqual(shown(), 1, 'back to the focused row');
// ticked row that is no longer on the page (paging / filter) is still shown by its own id and data
tick(4, true);
medDetail.rows = new Map([[10, mk(10)], [11, mk(11)]]);
focus(11); assert.strictEqual(shown(), 4);
assert.strictEqual(api.medShownItem().product_name, 'M4');
// the selection cleared elsewhere (bulk delete): back to the focused row
selected.clear(); win.medSyncLock(); assert.strictEqual(shown(), 11);
// ticking the same id twice in a row never duplicates the lock entry
tick(10, true); tick(10, true); assert.strictEqual(medDetail.lockOrder.filter(x => x === 10).length, 1);
console.log('inventory_selection ok');
