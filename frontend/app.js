import { request, ApiError } from './api.js';
import { money, escapeHTML as e, category, artwork, filterProducts, sanitizeCart, cartTotal, addToCart, reconcileCart, demoProducts } from './store.js';

const $ = selector => document.querySelector(selector);
const icons = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="10.7" cy="10.7" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="12" cy="8" r="3.5"/><path d="M4.5 21v-2a7.5 7.5 0 0 1 15 0v2"/></svg>',
};
$('#search-toggle').innerHTML = icons.search;
$('#account-button').innerHTML = icons.user;
const storage = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem(`forme:${key}`)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(`forme:${key}`, JSON.stringify(value)); } catch { /* Browsing still works when storage is disabled. */ } },
};
let token = null;
try { token = sessionStorage.getItem('forme:token'); } catch { /* Session persistence is optional. */ }
const storedFavorites = storage.get('favorites', []);
const state = { products: [], cart: sanitizeCart(storage.get('cart', [])), favorites: Array.isArray(storedFavorites) ? storedFavorites.filter(id => typeof id === 'string') : [], selected: 'All objects', search: '', sort: 'featured', favoritesOnly: false, demo: false, loading: true, token, user: null, orders: [], authMode: 'login', checkout: false, checkoutIntent: false };
let toastTimer;
let ordersTimer;
let orderGeneration = 0;
function toast(message) {
  $('#toast').textContent = message; $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 5000);
}
function openDialog(id) { const dialog = $(`#${id}`); if (!dialog.open) dialog.showModal(); }
function closeDialog(id) { $(`#${id}`).close(); }
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => closeDialog(button.dataset.close)));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => {
  if (event.target !== dialog || state.checkout) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
}));
function productImage(product, className = '') {
  const art = artwork(product);
  if (art) return `<img class="${className}" src="assets/${art}.svg" alt="Illustration of ${e(product.name)}" loading="lazy">`;
  return `<div class="generic-product" aria-label="${e(product.name)}"><span>f.</span><small>${e(category(product))}</small></div>`;
}
function saveCart() { storage.set('cart', state.cart); $('#cart-count').textContent = state.cart.reduce((sum, item) => sum + item.quantity, 0); }
function addProduct(id) {
  const product = state.products.find(item => item.id === id);
  if (!product) return;
  try { state.cart = addToCart(state.cart, product); saveCart(); renderCart(); toast(`${product.name} added to your bag.`); }
  catch (error) { toast(error.message); }
}
function renderCategories() {
  const options = ['All objects', ...new Set(state.products.map(category))];
  $('#categories').innerHTML = options.map(label => `<button class="${state.selected === label ? 'active' : ''}" data-category="${e(label)}" aria-pressed="${state.selected === label}">${e(label)}</button>`).join('');
  $('#categories').querySelectorAll('button').forEach(button => button.addEventListener('click', () => { state.selected = button.dataset.category; renderCategories(); renderProducts(); }));
}
function renderProducts() {
  if (state.loading) { $('#product-grid').innerHTML = Array.from({ length: 6 }, () => '<div class="loading-card" aria-hidden="true"></div>').join(''); return; }
  const products = filterProducts(state.products, { search: state.search, selected: state.selected, sort: state.sort, favorites: state.favoritesOnly ? state.favorites : null });
  $('#results-count').textContent = `${products.length} ${products.length === 1 ? 'object' : 'objects'}${state.demo ? ' in the preview collection' : ' in the collection'}`;
  $('#favorites-toggle').setAttribute('aria-pressed', state.favoritesOnly);
  if (!products.length) { $('#product-grid').innerHTML = '<div class="empty"><h3>A little room for something good.</h3><p>No objects match this selection.</p><button id="reset-filter" class="button outline">Explore all objects ↗</button></div>'; $('#reset-filter').onclick = () => { state.search = ''; state.selected = 'All objects'; state.favoritesOnly = false; $('#search-input').value = ''; renderCategories(); renderProducts(); }; return; }
  const colors = { headphones: '#e9eae2', lamp: '#ece7de', bag: '#e9e6df', chair: '#e6e9df', watch: '#e8e9e1', speaker: '#e9e8df' };
  $('#product-grid').innerHTML = products.map(product => `<article class="product-card"><div class="product-art" style="background:${colors[artwork(product)] || '#e9eae2'}"><button class="product-open" data-detail="${e(product.id)}" aria-label="View ${e(product.name)}">${productImage(product)}</button>${product.stock_quantity === 0 ? '<span class="product-tag">OUT OF STOCK</span>' : product.stock_quantity <= 5 ? '<span class="product-tag">JUST A FEW LEFT</span>' : ''}<button class="favorite-button ${state.favorites.includes(product.id) ? 'saved' : ''}" data-favorite="${e(product.id)}" aria-label="${state.favorites.includes(product.id) ? 'Unsave' : 'Save'} ${e(product.name)}" aria-pressed="${state.favorites.includes(product.id)}">${state.favorites.includes(product.id) ? '♥' : '♡'}</button></div><div class="card-bottom"><div><div class="product-category">${e(category(product))}</div><h3 class="product-name">${e(product.name)}</h3></div><span class="price">${money(product.price)}</span></div><div class="product-meta"><span>${product.stock_quantity ? `${product.stock_quantity} available` : 'Back soon'}</span><button class="add-button" data-add="${e(product.id)}" aria-label="Add ${e(product.name)} to bag" ${product.stock_quantity ? '' : 'disabled'}>+</button></div></article>`).join('');
  $('#product-grid').querySelectorAll('[data-detail]').forEach(button => button.onclick = () => showProduct(button.dataset.detail));
  $('#product-grid').querySelectorAll('[data-add]').forEach(button => button.onclick = () => addProduct(button.dataset.add));
  $('#product-grid').querySelectorAll('[data-favorite]').forEach(button => button.onclick = () => {
    const id = button.dataset.favorite;
    state.favorites = state.favorites.includes(id) ? state.favorites.filter(item => item !== id) : [...state.favorites, id];
    storage.set('favorites', state.favorites); renderProducts();
  });
}
async function loadProducts() {
  state.loading = true; renderProducts();
  try {
    const products = []; let skip = 0;
    // Fetch paginated catalog instead of silently dropping everything beyond the first page.
    for (;;) {
      const page = await request(`/products?skip=${skip}&limit=100`);
      if (!Array.isArray(page)) throw new Error('Unexpected catalog response.');
      products.push(...page); if (page.length < 100) break; skip += 100;
      if (skip >= 10000) break;
    }
    state.products = products; state.demo = false;
    const reconciled = reconcileCart(state.cart, products);
    state.cart = reconciled.items;
    if (reconciled.changed) toast('Your bag was updated to match the current catalog.');
    $('#connection-notice').hidden = true;
  } catch {
    state.products = demoProducts; state.demo = true;
    $('#connection-notice').hidden = false;
    $('#connection-notice').innerHTML = 'Preview collection · We couldn’t connect to the store. These are sample objects; checkout is unavailable. <button class="text-button" id="retry-catalog">Reconnect ↻</button>';
    $('#retry-catalog').onclick = loadProducts;
  } finally { state.loading = false; renderCategories(); renderProducts(); renderCart(); }
}
function showProduct(id) {
  const product = state.products.find(p => p.id === id); if (!product) return;
  $('#product-detail').innerHTML = `<div class="product-detail-grid"><div class="detail-art">${productImage(product)}</div><div class="detail-copy"><div class="eyebrow">${e(category(product))}</div><h2 id="detail-title">${e(product.name)}</h2><span class="price">${money(product.price)}</span><p>${e(product.description || 'An everyday object from the FORME collection. Explore the details and make it your own.')}</p><div class="muted">${product.stock_quantity} available${state.demo ? ' · Preview object' : ''}</div><button class="button dark" id="detail-add" ${product.stock_quantity ? '' : 'disabled'}>${product.stock_quantity ? 'Add to bag +' : 'Out of stock'}</button><p class="detail-illustration-note">Product illustration. Appearance may vary.</p></div></div>`;
  $('#detail-add').onclick = () => addProduct(id); openDialog('product-dialog');
}
function renderCart() {
  saveCart(); $('#bag-count').textContent = `(${state.cart.reduce((s, i) => s + i.quantity, 0)})`;
  if (!state.cart.length) { $('#cart-content').innerHTML = '<div class="empty"><h3>Good things are waiting.</h3><p>Your bag is taking a little breather.</p><button class="button dark" id="continue-shopping">Explore the collection ↗</button></div>'; $('#continue-shopping').onclick = () => { closeDialog('cart-dialog'); location.hash = '#collection'; }; return; }
  $('#cart-content').innerHTML = state.cart.map(item => `<div class="cart-item">${productImage(item)}<div class="cart-item-copy"><h3>${e(item.name)}</h3><small>${money(item.price)} each</small><div class="quantity"><button data-quantity="${e(item.id)}" data-delta="-1" aria-label="Decrease quantity of ${e(item.name)}" ${state.checkout ? 'disabled' : ''}>−</button><span>${item.quantity}</span><button data-quantity="${e(item.id)}" data-delta="1" aria-label="Increase quantity of ${e(item.name)}" ${state.checkout ? 'disabled' : ''}>+</button></div><button class="remove text-button" data-remove="${e(item.id)}" ${state.checkout ? 'disabled' : ''}>Remove</button></div><span class="cart-item-price">${money(item.price * item.quantity)}</span></div>`).join('') + `<div class="cart-total"><span>Subtotal</span><strong>${money(cartTotal(state.cart))}</strong></div><p class="cart-note">${state.demo ? 'Preview bag. Reconnect to shop the live collection.' : 'Your order will be placed in USD and submitted for confirmation. No card details are collected on this page.'}</p><p id="checkout-error" class="form-error" role="alert"></p><button id="checkout-button" class="button dark full" ${state.demo || state.checkout || state.loading ? 'disabled' : ''}>${state.checkout ? 'Placing your order…' : state.token ? 'Place order ↗' : 'Sign in to place order ↗'}</button>`;
  $('#cart-content').querySelectorAll('[data-quantity]').forEach(button => button.onclick = () => {
    const item = state.cart.find(i => i.id === button.dataset.quantity); if (!item) return;
    const delta = Number(button.dataset.delta);
    const product = state.products.find(p => p.id === item.id);
    if (delta > 0 && (!product || item.quantity >= Math.min(product.stock_quantity, 99))) { toast('No more stock is available.'); return; }
    state.cart = state.cart.map(i => i.id === item.id ? { ...i, quantity: i.quantity + delta } : i).filter(i => i.quantity > 0); renderCart();
  });
  $('#cart-content').querySelectorAll('[data-remove]').forEach(button => button.onclick = () => { state.cart = state.cart.filter(i => i.id !== button.dataset.remove); renderCart(); });
  $('#checkout-button').onclick = checkout;
}
function setToken(value) { state.token = value; try { if (value) sessionStorage.setItem('forme:token', value); else sessionStorage.removeItem('forme:token'); } catch { /* Keep the current session in memory. */ } }
function signOut(message = 'You’re signed out.') {
  setToken(null); state.user = null; state.orders = []; state.checkoutIntent = false; orderGeneration++; clearInterval(ordersTimer);
  $('#orders-list').innerHTML = ''; $('#account-button').setAttribute('aria-label', 'Sign in');
  renderCart(); if (location.hash === '#orders') location.hash = '#shop'; toast(message);
}
function handleAuthError(error) { if (error.status === 401) signOut('Your session expired. Please sign in again.'); }
async function restoreUser() {
  if (!state.token) return;
  const currentToken = state.token;
  try {
    const user = await request('/users/me', { token: currentToken });
    if (state.token !== currentToken) return;
    state.user = user; $('#account-button').setAttribute('aria-label', `Account for ${user.full_name}`);
  } catch (error) { if (state.token === currentToken) { if (error.status === 401 || error.status === 403 || error.status === 404) signOut('Please sign in to continue.'); else toast('We couldn’t reach your account. Please try again shortly.'); } }
}
function showAuth() { state.authMode = 'login'; updateAuth(); $('#auth-error').textContent = ''; openDialog('auth-dialog'); }
function updateAuth() {
  const register = state.authMode === 'register';
  $('#auth-title').textContent = register ? 'A little more you.' : 'Welcome back.';
  $('#auth-description').textContent = register ? 'Create your account and find your everyday favorites.' : 'Your favorites. Your orders. All in one place.';
  $('#name-label').hidden = !register; $('#auth-name').required = register;
  $('#auth-password').autocomplete = register ? 'new-password' : 'current-password';
  $('#auth-submit').textContent = register ? 'Create account ↗' : 'Sign in ↗';
  $('#auth-switch-copy').textContent = register ? 'Already part of the collection?' : 'New around here?';
  $('#auth-switch').textContent = register ? 'Sign in' : 'Create an account';
  $('#auth-error').textContent = '';
}
$('#auth-switch').onclick = () => { state.authMode = state.authMode === 'login' ? 'register' : 'login'; updateAuth(); };
$('#auth-form').onsubmit = async event => {
  event.preventDefault(); const submit = $('#auth-submit'); submit.disabled = true; $('#auth-error').textContent = '';
  const payload = { email: $('#auth-email').value.trim(), password: $('#auth-password').value };
  try {
    if (state.authMode === 'register') {
      await request('/users/register', { method: 'POST', body: { ...payload, full_name: $('#auth-name').value.trim() } });
      state.authMode = 'login'; updateAuth();
    }
    const response = await request('/users/login', { method: 'POST', body: payload });
    setToken(response.access_token); await restoreUser();
    if (!state.token) return;
    closeDialog('auth-dialog'); $('#auth-form').reset(); renderCart(); toast('Welcome to your everyday.');
    if (state.checkoutIntent) { state.checkoutIntent = false; renderCart(); openDialog('cart-dialog'); }
    if (location.hash === '#orders') await loadOrders();
  } catch (error) { $('#auth-error').textContent = error.message; }
  finally { submit.disabled = false; }
};
async function checkout() {
  if (state.demo || state.checkout || !state.cart.length) return;
  if (!state.token) { state.checkoutIntent = true; closeDialog('cart-dialog'); showAuth(); return; }
  state.checkout = true; renderCart();
  let message = '';
  let posted = false;
  try {
    const products = await Promise.all(state.cart.map(item => request(`/products/${encodeURIComponent(item.id)}`)));
    const result = reconcileCart(state.cart, products);
    if (result.changed) { state.cart = result.items; throw new Error('Availability or pricing changed. Your bag has been updated. Review it before placing your order.'); }
    const order = await request('/orders', { token: state.token, method: 'POST', body: { items: state.cart.map(item => ({ product_id: item.id, quantity: item.quantity, unit_price: item.price })) } });
    posted = true; state.cart = []; saveCart(); closeDialog('cart-dialog');
    toast(`Order ${order.id.slice(0, 8).toUpperCase()} placed. We’re following its progress.`);
    location.hash = '#orders';
    if (location.hash === '#orders') await loadOrders();
  } catch (error) {
    handleAuthError(error);
    message = error.message + (error instanceof ApiError && !error.status ? ' Check My orders before placing another order.' : '');
    if (posted) toast('Order placed. Refresh My orders to see its latest status.');
  } finally {
    state.checkout = false; renderCart();
    if (message && $('#checkout-error')) $('#checkout-error').textContent = message;
  }
}
function showAccount() {
  if (!state.token) { showAuth(); return; }
  $('#account-content').innerHTML = `<div class="account-details">${e(state.user?.full_name || 'Your FORME account')}<small>${e(state.user?.email || 'Signed in')}</small></div><div class="account-actions"><button id="account-orders" class="button dark">View my orders ↗</button><button id="signout" class="button outline">Sign out</button></div>`;
  $('#account-orders').onclick = () => { closeDialog('account-dialog'); location.hash = '#orders'; if (location.hash === '#orders') loadOrders(); };
  $('#signout').onclick = () => { closeDialog('account-dialog'); signOut(); }; openDialog('account-dialog');
}
function renderOrders() {
  if (!state.orders.length) { $('#orders-list').innerHTML = '<div class="empty"><h3>Your next favorite is out there.</h3><p>Your orders will appear here once you place one.</p><a class="button dark" href="#collection">Discover the collection ↗</a></div>'; return; }
  const names = new Map(state.products.map(p => [p.id, p.name]));
  $('#orders-list').innerHTML = [...state.orders].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).map(order => {
    const status = ['PENDING', 'CONFIRMED', 'CANCELLED'].includes(order.status) ? order.status : 'PENDING';
    const date = new Date(order.created_at.endsWith('Z') || /[+-]\d\d:\d\d$/.test(order.created_at) ? order.created_at : `${order.created_at}Z`);
    return `<article class="order-card"><div class="order-heading"><div><h3>Order ${e(order.id.slice(0, 8).toUpperCase())}</h3><small>${e(date.toLocaleString())} · ${e(order.id)}</small></div><span class="status ${status}">${status === 'PENDING' ? 'PROCESSING' : status}</span></div><div class="order-items">${order.items.map(item => `<div>${e(names.get(item.product_id) || `Product ${item.product_id.slice(0, 8)}`)} × ${item.quantity} <span>· ${money(item.price * item.quantity)}</span></div>`).join('')}</div><div class="order-bottom"><strong>${money(order.total_price)}</strong>${status === 'PENDING' ? `<button class="text-button" data-cancel-order="${e(order.id)}">Cancel order</button>` : `<span class="muted">${status === 'CONFIRMED' ? 'Payment confirmed' : 'This order was cancelled'}</span>`}</div><div class="order-progress" aria-hidden="true"><span class="done"></span><span class="${status === 'CONFIRMED' ? 'done' : ''}"></span><span class="${status === 'CONFIRMED' ? 'done' : ''}"></span></div></article>`;
  }).join('');
  $('#orders-list').querySelectorAll('[data-cancel-order]').forEach(button => button.onclick = async () => {
    if (!confirm('Cancel this order? This action cannot be undone.')) return;
    button.disabled = true;
    try { await request(`/orders/${encodeURIComponent(button.dataset.cancelOrder)}/cancel`, { token: state.token, method: 'POST' }); toast('Order cancelled.'); await loadOrders(); }
    catch (error) { handleAuthError(error); toast(error.message); }
    finally { button.disabled = false; }
  });
}
async function loadOrders(quiet = false) {
  if (!state.token) { $('#orders-list').innerHTML = '<div class="empty"><h3>A little hello goes a long way.</h3><p>Sign in to view your orders.</p><button id="orders-signin" class="button dark">Sign in ↗</button></div>'; $('#orders-signin').onclick = showAuth; return; }
  const generation = ++orderGeneration;
  if (!quiet) $('#orders-list').innerHTML = '<p class="muted">Finding your orders…</p>';
  try {
    const orders = [];
    for (let skip = 0; ; skip += 100) {
      const page = await request(`/orders?skip=${skip}&limit=100`, { token: state.token });
      orders.push(...page); if (page.length < 100 || skip >= 9900) break;
    }
    if (generation !== orderGeneration) return;
    state.orders = orders; renderOrders();
  } catch (error) {
    if (generation !== orderGeneration) return;
    handleAuthError(error);
    if (!quiet) { $('#orders-list').innerHTML = `<div class="empty"><h3>We couldn’t load your orders.</h3><p>${e(error.message)}</p><button id="retry-orders" class="button outline">Try again ↻</button></div>`; $('#retry-orders').onclick = () => loadOrders(); }
  }
}
function route() {
  const orders = location.hash === '#orders';
  $('#shop-view').hidden = orders; $('#orders-view').hidden = !orders;
  document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.hash === location.hash || link.hash === '#shop' && !location.hash));
  clearInterval(ordersTimer);
  if (orders) { window.scrollTo(0, 0); loadOrders(); ordersTimer = setInterval(() => { if (!document.hidden && state.token && !document.querySelector('[data-cancel-order]:disabled')) loadOrders(true); }, 8000); }
  else if (location.hash === '#collection' || location.hash === '#about') requestAnimationFrame(() => $(location.hash)?.scrollIntoView({ behavior: 'smooth' }));
}
$('#search-toggle').onclick = () => { location.hash = '#collection'; $('#search-row').hidden = false; $('#search-input').focus(); };
$('#search-close').onclick = () => { state.search = ''; $('#search-input').value = ''; $('#search-row').hidden = true; renderProducts(); };
$('#search-input').oninput = event => { state.search = event.target.value; renderProducts(); };
$('#sort').onchange = event => { state.sort = event.target.value; renderProducts(); };
$('#favorites-toggle').onclick = () => { state.favoritesOnly = !state.favoritesOnly; renderProducts(); };
$('#cart-toggle').onclick = () => { renderCart(); openDialog('cart-dialog'); };
$('#account-button').onclick = showAccount;
$('#footer-orders').onclick = () => { location.hash = '#orders'; };
$('#refresh-orders').onclick = () => loadOrders();
window.addEventListener('hashchange', route);
window.addEventListener('pagehide', () => clearInterval(ordersTimer));
saveCart(); renderProducts(); route(); loadProducts(); restoreUser();
