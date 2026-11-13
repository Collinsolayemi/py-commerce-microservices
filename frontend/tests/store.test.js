import test from 'node:test';
import assert from 'node:assert/strict';
import { cartTotal, addToCart, reconcileCart, sanitizeCart, filterProducts, escapeHTML, artwork, demoProducts } from '../store.js';

test('cart totals use integer cents rather than accumulating binary rounding errors', () => {
  assert.equal(cartTotal([{ price: 0.1, quantity: 3 }, { price: 0.2, quantity: 1 }]), 0.5);
  assert.equal(cartTotal([]), 0);
});
test('adding items respects available stock and never mutates the previous cart', () => {
  const product = { id: 'p1', name: 'Lamp', price: 89, stock_quantity: 2 };
  const first = addToCart([], product);
  const second = addToCart(first, product);
  assert.equal(first[0].quantity, 1);
  assert.equal(second[0].quantity, 2);
  assert.throws(() => addToCart(second, product), /available stock/);
  assert.throws(() => addToCart([], { ...product, stock_quantity: 0 }));
});
test('persisted cart rejects duplicates, invalid prices and unsafe quantities', () => {
  const item = { id: 'p1', name: 'Lamp', price: 89, quantity: 1, untrusted: 'discard' };
  assert.deepEqual(sanitizeCart([item, item, { ...item, id: 'bad', quantity: -1 }, { ...item, id: 'bad2', price: '1' }, null]), [{ id: 'p1', name: 'Lamp', price: 89, quantity: 1 }]);
  assert.deepEqual(sanitizeCart({}), []);
});
test('checkout refreshes prices, clamps stock and removes deleted products', () => {
  const cart = [{ id: 'p1', name: 'Lamp', price: 89, quantity: 3 }, { id: 'removed', name: 'Gone', price: 10, quantity: 1 }];
  const result = reconcileCart(cart, [{ id: 'p1', name: 'Lamp', price: 95, stock_quantity: 2 }]);
  assert.equal(result.changed, true);
  assert.deepEqual(result.items, [{ id: 'p1', name: 'Lamp', price: 95, quantity: 2 }]);
  assert.equal(cart[0].quantity, 3);
});
test('unchanged inventory does not block checkout and unavailable stock is removed', () => {
  const cart = [{ id: 'p1', name: 'Lamp', price: 89, quantity: 1 }];
  assert.equal(reconcileCart(cart, [{ ...cart[0], stock_quantity: 5 }]).changed, false);
  assert.deepEqual(reconcileCart(cart, [{ ...cart[0], stock_quantity: 0 }]).items, []);
});
test('catalog combines category, search, sort and saved favorites', () => {
  const result = filterProducts(demoProducts, { selected: 'Tech & audio', sort: 'price-asc' });
  assert.deepEqual(result.map(p => p.id), ['demo-speaker', 'demo-headphones']);
  assert.equal(filterProducts(demoProducts, { search: '  LAMP ' })[0].id, 'demo-lamp');
  assert.equal(filterProducts(demoProducts, { favorites: ['demo-chair'] })[0].id, 'demo-chair');
  assert.equal(filterProducts(demoProducts, { favorites: [] }).length, 0);
});
test('API text is escaped before inserting it into markup', () => {
  assert.equal(escapeHTML('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(escapeHTML("Bob's & Co"), 'Bob&#39;s &amp; Co');
});
test('unrecognized products get a neutral placeholder rather than an unrelated illustration', () => {
  assert.equal(artwork({ name: 'USB cable' }), null);
  assert.equal(artwork({ name: 'Oak lounge chair' }), 'chair');
});
