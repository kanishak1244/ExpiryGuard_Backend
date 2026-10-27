// A request that never answers must end with a clear error instead of hanging the screen; writes are never auto-retried.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'js', 'api.js'), 'utf8');
const m = src.match(/  async fetchWithTimeout[\s\S]*?\n  requestTimeoutMs[\s\S]*?\n  }\n/);
assert(m, 'fetchWithTimeout / requestTimeoutMs not found in api.js');
let calls = 0;
const hang = (u, c) => { calls++; return new Promise((_, rej) => c.signal.addEventListener('abort', () => { const e = new Error('aborted'); e.name = 'AbortError'; rej(e); })); };
const Api = new Function('fetch', 'FormData', 'return class A{' + m[0] + '}')(hang, class {});
const api = new Api();
(async () => {
  await assert.rejects(api.fetchWithTimeout('x', { method: 'GET' }, 50), e => e.code === 'REQUEST_TIMEOUT' && /try again/.test(e.message));
  await assert.rejects(api.fetchWithTimeout('x', { method: 'POST' }, 50), e => e.code === 'REQUEST_TIMEOUT' && /may or may not have been saved/.test(e.message));
  assert.strictEqual(calls, 2, 'a timed-out request must not be retried');
  assert.strictEqual(api.requestTimeoutMs('/products', {}), 30000);
  assert.strictEqual(api.requestTimeoutMs('/sales', { method: 'POST' }), 60000);
  assert.strictEqual(api.requestTimeoutMs('/documents/1/ocr', { method: 'POST' }), 120000);
  console.log('api_request_timeout ok');
})().catch(e => { console.error(e); process.exit(1); });
