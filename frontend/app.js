import { request, ApiError } from './api.js';
import { money, escapeHTML as e, category, artwork, filterProducts, sanitizeCart, cartTotal, addToCart, reconcileCart, shippingProgress, previewPromoQuote, userInitials, demoProducts } from './store.js';

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
const storedRecent = storage.get('recent', []);
const state = { products: [], cart: sanitizeCart(storage.get('cart', [])), favorites: Array.isArray(storedFavorites) ? storedFavorites.filter(id => typeof id === 'string') : [], recentlyViewed: Array.isArray(storedRecent) ? storedRecent.filter(id => typeof id === 'string') : [], selected: 'All objects', search: '', sort: 'featured', favoritesOnly: false, inStockOnly: false, demo: false, loading: true, token, user: null, orders: [], shipments: {}, reviews: {}, promo: null, promoError: '', authMode: 'login', checkout: false, checkoutIntent: false, heroIndex: 0 };
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
  if (art) return `<img class="${className}" src="assets/${art}.jpg" alt="${e(product.name)}" loading="lazy">`;
  return `<div class="generic-product" aria-label="${e(product.name)}"><span>f.</span><small>${e(category(product))}</small></div>`;
}
function saveCart() { storage.set('cart', state.cart); $('#cart-count').textContent = state.cart.reduce((sum, item) => sum + item.quantity, 0); }
function addProduct(id, quantity = 1) {
  const product = state.products.find(item => item.id === id);
  if (!product) return;
  try {
    let nextCart = state.cart;
    for (let i = 0; i < quantity; i++) nextCart = addToCart(nextCart, product);
    state.cart = nextCart; saveCart(); renderCart();
    toast(`${product.name}${quantity > 1 ? ` (×${quantity})` : ''} added to your bag.`);
  }
  catch (error) { toast(error.message); }
}
function renderCategories() {
  const options = ['All objects', ...new Set(state.products.map(category))];
  $('#categories').innerHTML = options.map(label => `<button class="${state.selected === label ? 'active' : ''}" data-category="${e(label)}" aria-pressed="${state.selected === label}">${e(label)}</button>`).join('');
  $('#categories').querySelectorAll('button').forEach(button => button.addEventListener('click', () => { state.selected = button.dataset.category; renderCategories(); renderProducts(); }));
}
function renderProducts() {
  if (state.loading) { $('#product-grid').innerHTML = Array.from({ length: 6 }, () => '<div class="loading-card" aria-hidden="true"></div>').join(''); return; }
  const products = filterProducts(state.products, { search: state.search, selected: state.selected, sort: state.sort, favorites: state.favoritesOnly ? state.favorites : null, inStockOnly: state.inStockOnly });
  $('#results-count').textContent = `${products.length} ${products.length === 1 ? 'object' : 'objects'}${state.demo ? ' in the preview collection' : ' in the collection'}`;
  $('#favorites-toggle').setAttribute('aria-pressed', state.favoritesOnly);
  $('#instock-toggle')?.setAttribute('aria-pressed', state.inStockOnly);
  if (!products.length) { $('#product-grid').innerHTML = '<div class="empty"><h3>A little room for something good.</h3><p>No objects match this selection.</p><button id="reset-filter" class="button outline">Explore all objects ↗</button></div>'; $('#reset-filter').onclick = () => { state.search = ''; state.selected = 'All objects'; state.favoritesOnly = false; state.inStockOnly = false; $('#search-input').value = ''; renderCategories(); renderProducts(); }; return; }
  const colors = { headphones: '#e9eae2', lamp: '#ece7de', bag: '#e9e6df', chair: '#e6e9df', watch: '#e8e9e1', speaker: '#e9e8df', kettle: '#eceae2', mug: '#eae7de', 'desk-tray': '#e8eae1', throw: '#ece9e0', turntable: '#e7e9e0', folio: '#ebe8df' };
  $('#product-grid').innerHTML = products.map(product => `<article class="product-card"><div class="product-art" style="background:${colors[artwork(product)] || '#e9eae2'}"><button class="product-open" data-detail="${e(product.id)}" aria-label="View ${e(product.name)}">${productImage(product)}</button>${product.stock_quantity === 0 ? '<span class="product-tag">OUT OF STOCK</span>' : product.stock_quantity <= 5 ? '<span class="product-tag">JUST A FEW LEFT</span>' : ''}<button class="favorite-button ${state.favorites.includes(product.id) ? 'saved' : ''}" data-favorite="${e(product.id)}" aria-label="${state.favorites.includes(product.id) ? 'Unsave' : 'Save'} ${e(product.name)}" aria-pressed="${state.favorites.includes(product.id)}">${state.favorites.includes(product.id) ? '♥' : '♡'}</button><span class="quick-view-pill" aria-hidden="true">Quick view ↗</span></div><div class="card-bottom"><div><div class="product-category">${e(category(product))}</div><h3 class="product-name">${e(product.name)}</h3></div><span class="price">${money(product.price)}</span></div><div class="product-meta"><span>${product.stock_quantity ? `${product.stock_quantity} available` : 'Back soon'}</span><div class="card-actions"><span class="swatches" aria-hidden="true"><span class="swatch"></span><span class="swatch"></span><span class="swatch"></span></span><button class="add-button" data-add="${e(product.id)}" aria-label="Add ${e(product.name)} to bag" ${product.stock_quantity ? '' : 'disabled'}>+</button></div></div></article>`).join('');
  $('#product-grid').querySelectorAll('[data-detail]').forEach(button => button.onclick = () => showProduct(button.dataset.detail));
  $('#product-grid').querySelectorAll('[data-add]').forEach(button => button.onclick = () => {
    addProduct(button.dataset.add);
    button.classList.add('added'); button.textContent = '✓';
    setTimeout(() => { button.classList.remove('added'); button.textContent = '+'; }, 900);
  });
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
async function loadProductReviews(productId) {
  try {
    const summary = await request(`/reviews/${encodeURIComponent(productId)}`);
    state.reviews[productId] = summary;
  } catch {
    if (!state.reviews[productId]) {
      state.reviews[productId] = { product_id: productId, average_rating: 0, total_reviews: 0, rating_breakdown: { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 }, reviews: [], offline: true };
    }
  }
  const host = $('#detail-reviews');
  if (host && host.dataset.productId === productId) renderProductReviews(productId);
}
function renderStars(rating) {
  const filled = Math.round(Number(rating) || 0);
  return '★'.repeat(Math.max(0, Math.min(5, filled))) + '☆'.repeat(Math.max(0, 5 - filled));
}
function renderProductReviews(productId) {
  const host = $('#detail-reviews');
  if (!host) return;
  const summary = state.reviews[productId];
  if (!summary) { host.innerHTML = '<p class="muted">Loading reviews…</p>'; return; }
  const items = summary.reviews || [];
  host.innerHTML = `
    <div class="reviews-header">
      <div><strong>Reviews</strong> <span class="reviews-stars">${renderStars(summary.average_rating)}</span> <small class="muted">${summary.total_reviews ? `${summary.average_rating.toFixed(1)} (${summary.total_reviews})` : 'No reviews yet'}</small></div>
      ${state.token ? '<button type="button" class="text-button" id="toggle-review-form">Write a review</button>' : '<button type="button" class="text-button" id="review-signin">Sign in to review</button>'}
    </div>
    <form id="review-form" class="review-form" hidden>
      <div class="review-form-row">
        <label>Rating <select id="review-rating"><option value="5">5 ★</option><option value="4">4 ★</option><option value="3">3 ★</option><option value="2">2 ★</option><option value="1">1 ★</option></select></label>
        <label style="flex:1">Headline <input id="review-title" maxlength="120" placeholder="Thoughtful design…" required></label>
      </div>
      <label>Notes <input id="review-comment" maxlength="1000" placeholder="How does it feel in your space?"></label>
      <p id="review-error" class="form-error" role="alert"></p>
      <button type="submit" class="button dark">Submit review ↗</button>
    </form>
    ${items.length ? `<div class="reviews-list">${items.slice(0, 3).map(r => `<article class="review-item"><div class="review-item-top"><span class="reviews-stars">${renderStars(r.rating)}</span><strong>${e(r.title)}</strong></div>${r.comment ? `<p>${e(r.comment)}</p>` : ''}</article>`).join('')}</div>` : ''}
  `;
  const signinBtn = $('#review-signin');
  if (signinBtn) signinBtn.onclick = () => { closeDialog('product-dialog'); showAuth(); };
  const toggleBtn = $('#toggle-review-form');
  if (toggleBtn) toggleBtn.onclick = () => { $('#review-form').hidden = !$('#review-form').hidden; };
  const form = $('#review-form');
  if (form) form.onsubmit = async event => {
    event.preventDefault();
    $('#review-error').textContent = '';
    try {
      await request(`/reviews/${encodeURIComponent(productId)}`, {
        token: state.token,
        method: 'POST',
        body: { rating: Number($('#review-rating').value), title: $('#review-title').value.trim(), comment: $('#review-comment').value.trim() },
      });
      toast('Thank you — your review has been published.');
      await loadProductReviews(productId);
    } catch (error) {
      handleAuthError(error);
      if ($('#review-error')) $('#review-error').textContent = error.message;
    }
  };
}
function renderRecentlyViewed() {
  const section = $('#recently-viewed-section');
  const grid = $('#recently-viewed-grid');
  if (!section || !grid) return;
  const items = state.recentlyViewed.map(id => state.products.find(p => p.id === id)).filter(Boolean).slice(0, 4);
  section.hidden = items.length === 0;
  if (!items.length) return;
  grid.innerHTML = items.map(p => `<button type="button" class="recent-card" data-recent="${e(p.id)}">${productImage(p)}<div><strong>${e(p.name)}</strong><span>${money(p.price)}</span></div></button>`).join('');
  grid.querySelectorAll('[data-recent]').forEach(btn => btn.onclick = () => showProduct(btn.dataset.recent));
}
function showProduct(id) {
  const product = state.products.find(p => p.id === id); if (!product) return;
  state.recentlyViewed = [id, ...state.recentlyViewed.filter(item => item !== id)].slice(0, 6);
  storage.set('recent', state.recentlyViewed);
  renderRecentlyViewed();
  let qty = 1;
  let selectedFinish = 'Warm Oat';
  const maxQty = Math.min(product.stock_quantity || 0, 99);
  $('#product-detail').innerHTML = `<div class="product-detail-grid"><div class="detail-art">${productImage(product)}</div><div class="detail-copy"><div class="eyebrow">${e(category(product))}</div><h2 id="detail-title">${e(product.name)}</h2><span class="price">${money(product.price)}</span><p>${e(product.description || 'An everyday object from the FORME collection. Explore the details and make it your own.')}</p><div class="detail-finishes"><span class="muted">Finish: <strong id="detail-finish-name">${selectedFinish}</strong></span><div class="finish-pills"><button type="button" class="finish-pill active" data-finish="Warm Oat" style="--sw:#c8b69d" aria-label="Warm Oat"></button><button type="button" class="finish-pill" data-finish="Studio Sage" style="--sw:#8a967a" aria-label="Studio Sage"></button><button type="button" class="finish-pill" data-finish="Charcoal" style="--sw:#3d413b" aria-label="Charcoal"></button></div></div><div class="muted">${product.stock_quantity} available${state.demo ? ' · Preview object' : ''}</div><div class="detail-purchase-row"><div class="quantity detail-qty" ${product.stock_quantity ? '' : 'hidden'}><button type="button" id="detail-qty-dec" aria-label="Decrease quantity">−</button><span id="detail-qty-val">1</span><button type="button" id="detail-qty-inc" aria-label="Increase quantity">+</button></div><button class="button dark" id="detail-add" ${product.stock_quantity ? '' : 'disabled'}>${product.stock_quantity ? 'Add to bag +' : 'Out of stock'}</button></div><div id="detail-reviews" class="detail-reviews" data-product-id="${e(product.id)}"></div><p class="detail-illustration-note">Studio preview. Appearance may vary.</p></div></div>`;
  $('#product-detail').querySelectorAll('[data-finish]').forEach(btn => btn.onclick = () => {
    selectedFinish = btn.dataset.finish;
    $('#detail-finish-name').textContent = selectedFinish;
    $('#product-detail').querySelectorAll('[data-finish]').forEach(b => b.classList.toggle('active', b === btn));
  });
  if ($('#detail-qty-dec')) $('#detail-qty-dec').onclick = () => { if (qty > 1) { qty--; $('#detail-qty-val').textContent = qty; } };
  if ($('#detail-qty-inc')) $('#detail-qty-inc').onclick = () => { if (qty < maxQty) { qty++; $('#detail-qty-val').textContent = qty; } };
  $('#detail-add').onclick = () => { addProduct(id, qty); closeDialog('product-dialog'); };
  renderProductReviews(id);
  loadProductReviews(id);
  openDialog('product-dialog');
}
async function validatePromo(code) {
  const subtotal = cartTotal(state.cart);
  const trimmed = String(code || '').trim().toUpperCase();
  if (!trimmed) { state.promo = null; state.promoError = 'Enter a promo code.'; renderCart(); return; }
  try {
    const quote = state.demo ? previewPromoQuote(trimmed, subtotal) : await request('/coupons/validate', { token: state.token || undefined, method: 'POST', body: { code: trimmed, order_amount: subtotal } });
    if (quote.valid) { state.promo = quote; state.promoError = ''; toast(`Code ${quote.code} applied — saving ${money(quote.discount_amount)}.`); }
    else { state.promo = null; state.promoError = quote.reason || 'Coupon is not valid.'; }
  } catch {
    const fallback = previewPromoQuote(trimmed, subtotal);
    if (fallback.valid) { state.promo = fallback; state.promoError = ''; toast(`Code ${fallback.code} applied (preview).`); }
    else { state.promo = null; state.promoError = 'Could not validate promo code.'; }
  }
  renderCart();
}
function renderCart() {
  saveCart(); $('#bag-count').textContent = `(${state.cart.reduce((s, i) => s + i.quantity, 0)})`;
  if (!state.cart.length) { state.promo = null; state.promoError = ''; $('#cart-content').innerHTML = '<div class="empty"><h3>Good things are waiting.</h3><p>Your bag is taking a little breather.</p><button class="button dark" id="continue-shopping">Explore the collection ↗</button></div>'; $('#continue-shopping').onclick = () => { closeDialog('cart-dialog'); location.hash = '#collection'; }; return; }
  const subtotal = cartTotal(state.cart);
  const ship = shippingProgress(subtotal);
  const discount = state.promo?.valid ? Math.min(state.promo.discount_amount, subtotal) : 0;
  const finalTotal = Math.max(0, Math.round((subtotal - discount) * 100) / 100);
  $('#cart-content').innerHTML = `
    <div class="shipping-meter">
      <div class="shipping-meter-copy">${ship.unlocked ? 'Complimentary shipping unlocked ✓' : `Add <strong>${money(ship.remaining)}</strong> for complimentary shipping`}</div>
      <div class="shipping-meter-bar"><span style="width:${ship.percent}%"></span></div>
    </div>
  ` + state.cart.map(item => `<div class="cart-item">${productImage(item)}<div class="cart-item-copy"><h3>${e(item.name)}</h3><small>${money(item.price)} each</small><div class="quantity"><button data-quantity="${e(item.id)}" data-delta="-1" aria-label="Decrease quantity of ${e(item.name)}" ${state.checkout ? 'disabled' : ''}>−</button><span>${item.quantity}</span><button data-quantity="${e(item.id)}" data-delta="1" aria-label="Increase quantity of ${e(item.name)}" ${state.checkout ? 'disabled' : ''}>+</button></div><button class="remove text-button" data-remove="${e(item.id)}" ${state.checkout ? 'disabled' : ''}>Remove</button></div><span class="cart-item-price">${money(item.price * item.quantity)}</span></div>`).join('') + `
    <form id="promo-form" class="promo-box">
      <label class="sr-only" for="promo-input">Promo code</label>
      <input id="promo-input" type="text" placeholder="Promo code (e.g. WELCOME20)" value="${e(state.promo?.code || '')}" ${state.checkout ? 'disabled' : ''}>
      ${state.promo?.valid ? '<button type="button" id="promo-remove" class="button outline">Remove</button>' : '<button type="submit" class="button outline" ' + (state.checkout ? 'disabled' : '') + '>Apply</button>'}
    </form>
    ${state.promoError ? `<p class="form-error promo-error">${e(state.promoError)}</p>` : ''}
    <div class="cart-summary">
      <div class="cart-row"><span>Subtotal</span><span>${money(subtotal)}</span></div>
      ${discount > 0 ? `<div class="cart-row promo-row"><span>Promo (${e(state.promo.code)})</span><span>−${money(discount)}</span></div>` : ''}
      <div class="cart-row"><span>Shipping</span><span>${ship.unlocked ? 'Complimentary' : 'Calculated at dispatch'}</span></div>
      <div class="cart-total"><span>Total</span><strong>${money(finalTotal)}</strong></div>
    </div>
    <p class="cart-note">${state.demo ? 'Preview bag. Reconnect to shop the live collection.' : 'Your order will be placed in USD and submitted for confirmation. No card details are collected on this page.'}</p><p id="checkout-error" class="form-error" role="alert"></p><button id="checkout-button" class="button dark full" ${state.demo || state.checkout || state.loading ? 'disabled' : ''}>${state.checkout ? 'Placing your order…' : state.token ? 'Place order ↗' : 'Sign in to place order ↗'}</button>`;
  $('#cart-content').querySelectorAll('[data-quantity]').forEach(button => button.onclick = () => {
    const item = state.cart.find(i => i.id === button.dataset.quantity); if (!item) return;
    const delta = Number(button.dataset.delta);
    const product = state.products.find(p => p.id === item.id);
    if (delta > 0 && (!product || item.quantity >= Math.min(product.stock_quantity, 99))) { toast('No more stock is available.'); return; }
    state.cart = state.cart.map(i => i.id === item.id ? { ...i, quantity: i.quantity + delta } : i).filter(i => i.quantity > 0);
    if (state.promo?.code && state.demo) state.promo = previewPromoQuote(state.promo.code, cartTotal(state.cart));
    renderCart();
  });
  $('#cart-content').querySelectorAll('[data-remove]').forEach(button => button.onclick = () => { state.cart = state.cart.filter(i => i.id !== button.dataset.remove); renderCart(); });
  if ($('#promo-form')) $('#promo-form').onsubmit = event => { event.preventDefault(); validatePromo($('#promo-input').value); };
  if ($('#promo-remove')) $('#promo-remove').onclick = () => { state.promo = null; state.promoError = ''; renderCart(); };
  $('#checkout-button').onclick = checkout;
}
function setToken(value) { state.token = value; try { if (value) sessionStorage.setItem('forme:token', value); else sessionStorage.removeItem('forme:token'); } catch { /* Keep the current session in memory. */ } }
function updateAccountButton() {
  const btn = $('#account-button');
  if (!btn) return;
  const initials = state.user ? userInitials(state.user.full_name) : '';
  if (initials) {
    btn.classList.add('has-user');
    btn.innerHTML = `<span class="account-initials">${e(initials)}</span>`;
    btn.setAttribute('aria-label', `Account for ${state.user.full_name}`);
  } else {
    btn.classList.remove('has-user');
    btn.innerHTML = icons.user;
    btn.setAttribute('aria-label', 'Sign in');
  }
}
function signOut(message = 'You’re signed out.') {
  setToken(null); state.user = null; state.orders = []; state.shipments = {}; state.checkoutIntent = false; orderGeneration++; clearInterval(ordersTimer);
  $('#orders-list').innerHTML = ''; updateAccountButton();
  renderCart(); if (location.hash === '#orders') location.hash = '#shop'; toast(message);
}
function handleAuthError(error) { if (error.status === 401) signOut('Your session expired. Please sign in again.'); }
async function restoreUser() {
  if (!state.token) return;
  const currentToken = state.token;
  try {
    const user = await request('/users/me', { token: currentToken });
    if (state.token !== currentToken) return;
    state.user = user; updateAccountButton();
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
    const subtotal = cartTotal(state.cart);
    const activePromo = state.promo?.valid ? state.promo.code : null;
    const order = await request('/orders', { token: state.token, method: 'POST', body: { items: state.cart.map(item => ({ product_id: item.id, quantity: item.quantity, unit_price: item.price })) } });
    if (activePromo) {
      request(`/coupons/${encodeURIComponent(activePromo)}/redeem`, { token: state.token, method: 'POST', body: { order_id: order.id, order_amount: subtotal } }).catch(() => {});
    }
    posted = true; state.cart = []; state.promo = null; state.promoError = ''; saveCart(); closeDialog('cart-dialog');
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
    const shipment = state.shipments[order.id];
    const tracking = shipment ? `<div class="order-tracking"><span>Shipment: <b>${e(shipment.status.replace('_', ' '))}</b></span><span>Tracking: <code>${e(shipment.tracking_number)}</code></span><span>${e(shipment.carrier)}</span></div>` : '';
    return `<article class="order-card"><div class="order-heading"><div><h3>Order ${e(order.id.slice(0, 8).toUpperCase())}</h3><small>${e(date.toLocaleString())} · ${e(order.id)}</small></div><span class="status ${status}">${status === 'PENDING' ? 'PROCESSING' : status}</span></div><div class="order-items">${order.items.map(item => `<div>${e(names.get(item.product_id) || `Product ${item.product_id.slice(0, 8)}`)} × ${item.quantity} <span>· ${money(item.price * item.quantity)}</span></div>`).join('')}</div>${tracking}<div class="order-bottom"><strong>${money(order.total_price)}</strong>${status === 'PENDING' ? `<button class="text-button" data-cancel-order="${e(order.id)}">Cancel order</button>` : `<span class="muted">${status === 'CONFIRMED' ? 'Payment confirmed' : 'This order was cancelled'}</span>`}</div><div class="order-progress" aria-hidden="true"><span class="done"></span><span class="${status === 'CONFIRMED' ? 'done' : ''}"></span><span class="${status === 'CONFIRMED' ? 'done' : ''}"></span></div></article>`;
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
    Promise.all(orders.slice(0, 10).map(async o => {
      try { state.shipments[o.id] = await request(`/shipping/${encodeURIComponent(o.id)}`); }
      catch { /* Shipping service may be offline or order not yet dispatched. */ }
    })).then(() => { if (generation === orderGeneration) renderOrders(); });
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
if ($('#instock-toggle')) $('#instock-toggle').onclick = () => { state.inStockOnly = !state.inStockOnly; renderProducts(); };
document.querySelectorAll('[data-space-cat], [data-footer-cat]').forEach(el => el.addEventListener('click', () => {
  const cat = el.dataset.spaceCat || el.dataset.footerCat;
  if (cat) { state.selected = cat; renderCategories(); renderProducts(); }
  location.hash = '#collection';
  $('#collection')?.scrollIntoView({ behavior: 'smooth' });
}));
if ($('#shop-studio-edit')) $('#shop-studio-edit').onclick = () => {
  state.selected = 'Studio & kitchen'; renderCategories(); renderProducts();
  $('#collection')?.scrollIntoView({ behavior: 'smooth' });
};
if ($('#bundle-studio-edit')) $('#bundle-studio-edit').onclick = () => {
  const ids = ['demo-kettle', 'demo-mug', 'demo-tray'];
  let added = 0;
  for (const id of ids) {
    const match = state.products.find(p => p.id === id) || state.products.find(p => category(p) === 'Studio & kitchen');
    if (match && match.stock_quantity > 0) {
      try { state.cart = addToCart(state.cart, match); added++; } catch { /* skip if maxed */ }
    }
  }
  if (added) { saveCart(); renderCart(); openDialog('cart-dialog'); toast('Studio & kitchen edit added to your bag.'); }
};
if ($('#clear-recent')) $('#clear-recent').onclick = () => { state.recentlyViewed = []; storage.set('recent', []); renderRecentlyViewed(); };
if ($('#footer-bag')) $('#footer-bag').onclick = () => { renderCart(); openDialog('cart-dialog'); };
$('#cart-toggle').onclick = () => { renderCart(); openDialog('cart-dialog'); };
$('#account-button').onclick = showAccount;
$('#footer-orders').onclick = () => { location.hash = '#orders'; };
$('#refresh-orders').onclick = () => loadOrders();
const heroSlides = [
  { img: 'assets/chair.jpg', alt: 'Sculptural sage lounge chair with a warm oak frame', note: 'A softer place to land.', eyebrow: 'DESIGNED FOR SLOW MOMENTS', title: 'Make room for the everyday.' },
  { img: 'assets/lamp.jpg', alt: 'Milo table lamp with warm matte finish', note: 'Warm light, quiet corners.', eyebrow: 'AMBIENT LIVING', title: 'Milo table lamp.' },
  { img: 'assets/headphones.jpg', alt: 'Studio wireless headphones in charcoal matte', note: 'A quieter kind of everyday.', eyebrow: 'TECH & AUDIO', title: 'Studio wireless headphones.' },
  { img: 'assets/bag.jpg', alt: 'Structured canvas everyday tote bag', note: 'Carry what matters.', eyebrow: 'EVERYDAY CARRY', title: 'The everyday tote.' },
  { img: 'assets/watch.jpg', alt: 'Minimalist Tempo everyday watch', note: 'Time, unhurried.', eyebrow: 'CONSIDERED DETAILS', title: 'Tempo everyday watch.' },
  { img: 'assets/speaker.jpg', alt: 'Pebble portable woven speaker', note: 'Soundtrack in motion.', eyebrow: 'PORTABLE AUDIO', title: 'Pebble portable speaker.' },
];
function renderHeroSlide(index) {
  state.heroIndex = (index + heroSlides.length) % heroSlides.length;
  const slide = heroSlides[state.heroIndex];
  const img = $('#hero-image');
  if (!img) return;
  img.src = slide.img; img.alt = slide.alt;
  $('#hero-note').textContent = slide.note;
  $('#hero-eyebrow').textContent = slide.eyebrow;
  $('#hero-caption-title').textContent = slide.title;
  $('#hero-counter').textContent = `${String(state.heroIndex + 1).padStart(2, '0')} / ${String(heroSlides.length).padStart(2, '0')}`;
}
if ($('#hero-prev')) $('#hero-prev').onclick = () => renderHeroSlide(state.heroIndex - 1);
if ($('#hero-next')) $('#hero-next').onclick = () => renderHeroSlide(state.heroIndex + 1);
if ($('#newsletter-form')) $('#newsletter-form').onsubmit = event => {
  event.preventDefault();
  const email = $('#newsletter-email').value.trim();
  if (!email) return;
  toast(`You’re on the list, ${email}.`);
  $('#newsletter-form').reset();
};
window.addEventListener('scroll', () => {
  $('#site-header')?.classList.toggle('scrolled', window.scrollY > 24);
}, { passive: true });
window.addEventListener('hashchange', route);
window.addEventListener('pagehide', () => clearInterval(ordersTimer));
saveCart(); renderProducts(); renderRecentlyViewed(); route(); loadProducts().then(renderRecentlyViewed); restoreUser();
