import test from 'node:test';
import assert from 'node:assert/strict';
import { request, ApiError, errorMessage } from '../api.js';

test('requests target the same-origin proxy and attach the bearer token', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/orders');
      assert.equal(options.headers.Authorization, 'Bearer signed-token');
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), { items: [] });
      return new Response(JSON.stringify({ id: 'order-1' }), { status: 201 });
    };
    assert.deepEqual(await request('/orders', { token: 'signed-token', method: 'POST', body: { items: [] } }), { id: 'order-1' });
  } finally { globalThis.fetch = original; }
});
test('FastAPI validation and authorization errors are readable', async () => {
  assert.equal(errorMessage([{ loc: ['body', 'email'], msg: 'Invalid email' }]), 'email: Invalid email');
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Token expired' }), { status: 401 });
    await assert.rejects(request('/orders'), error => error instanceof ApiError && error.status === 401 && error.message === 'Token expired');
  } finally { globalThis.fetch = original; }
});
test('failed checkout requests are not automatically retried', async () => {
  const original = globalThis.fetch; let calls = 0;
  try {
    globalThis.fetch = async () => { calls++; throw new TypeError('Network failure'); };
    await assert.rejects(request('/orders', { method: 'POST', body: { items: [] } }), error => error.status === 0);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});
test('invalid JSON responses fail with a useful message', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('<html>Bad gateway</html>', { status: 502 });
    await assert.rejects(request('/products'), /unexpected response/);
  } finally { globalThis.fetch = original; }
});
