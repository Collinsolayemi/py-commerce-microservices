import { test, expect } from '@playwright/test';

const products = [
  { id: 'lamp-1', name: 'Milo table lamp', description: 'A warm light for your everyday.', price: 89, stock_quantity: 8 },
  { id: 'chair-1', name: 'Sunday lounge chair', description: 'A softer place to land.', price: 249, stock_quantity: 4 },
  { id: 'headphones-1', name: 'Studio wireless headphones', description: 'A quieter everyday.', price: 129, stock_quantity: 12 },
];
async function mockServices(page, { updatedPrice = false } = {}) {
  const orders = [];
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    let body; let status = 200;
    if (path === '/api/products') body = products;
    else if (path.startsWith('/api/products/')) {
      body = products.find(p => p.id === path.split('/').pop());
      if (updatedPrice && body) body = { ...body, price: 95 };
    } else if (path === '/api/users/register') { status = 201; body = { id: 'alice', full_name: 'Alice Morgan', email: 'alice@example.com' }; }
    else if (path === '/api/users/login') body = { access_token: 'test-session-token', user_id: 'alice', email: 'alice@example.com' };
    else if (path === '/api/users/me') body = { id: 'alice', full_name: 'Alice Morgan', email: 'alice@example.com' };
    else if (path === '/api/orders' && method === 'GET') body = orders;
    else if (path === '/api/orders' && method === 'POST') {
      const payload = route.request().postDataJSON();
      expect(route.request().headers().authorization).toBe('Bearer test-session-token');
      expect(payload.user_id).toBeUndefined();
      body = { id: 'order-123456789', user_id: 'alice', status: 'PENDING', total_price: 89, created_at: '2026-11-06T12:00:00', items: payload.items.map(item => ({ ...item, price: item.unit_price })) };
      orders.push(body); status = 201;
    } else if (path.endsWith('/cancel')) { orders[0].status = 'CANCELLED'; body = orders[0]; }
    else { status = 404; body = { detail: 'Not found' }; }
    await route.fulfill({ status, json: body });
  });
}
async function signIn(page) {
  await page.getByLabel('Email address', { exact: true }).fill('alice@example.com');
  await page.getByLabel('Password', { exact: true }).fill('secure-password');
  await page.getByRole('button', { name: 'Sign in ↗', exact: true }).click();
}

test('desktop offline preview is explicit and checkout cannot submit fake orders', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.route('**/api/**', route => route.fulfill({ status: 502, json: { detail: 'Service unavailable' } }));
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.product-card')).toHaveCount(6);
  await expect(page.locator('#connection-notice')).toContainText('sample objects');
  await expect(page.getByRole('heading', { name: 'Everyday, considered.' })).toBeVisible();
  await page.screenshot({ path: 'test-results/forme-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Add Milo table lamp to bag', exact: true }).click();
  await page.getByRole('button', { name: 'Open shopping bag' }).click();
  await expect(page.locator('#checkout-button')).toBeDisabled();
  await expect(page.locator('#cart-content')).toContainText('$89.00');
  expect(errors).toEqual([]);
});

test('mobile catalog supports search, filters, favorites, details and persistent bag without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockServices(page); await page.goto('/');
  await expect(page.locator('.product-card')).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/forme-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Search products' }).click();
  await page.getByLabel('Find something you love').fill('lamp');
  await expect(page.locator('.product-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Save Milo table lamp', exact: true }).click();
  await page.getByRole('button', { name: 'Clear & close' }).click();
  await page.getByRole('button', { name: 'Saved favorites' }).click();
  await expect(page.locator('.product-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'View Milo table lamp', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Milo table lamp' })).toBeVisible();
  await page.getByRole('button', { name: 'Add to bag +' }).click();
  await page.getByRole('button', { name: 'Close product details' }).click();
  await page.reload();
  await page.getByRole('button', { name: 'Open shopping bag' }).click();
  await expect(page.locator('.cart-item')).toHaveCount(1);
  await page.getByRole('button', { name: 'Increase quantity of Milo table lamp' }).click();
  await expect(page.locator('.cart-total')).toContainText('$178.00');
  await page.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(page.locator('#cart-content')).toContainText('Good things are waiting');
});

test('login, authenticated checkout, order tracking, cancellation and sign out work together', async ({ page }) => {
  await mockServices(page); await page.goto('/');
  await page.getByRole('button', { name: 'Add Milo table lamp to bag', exact: true }).click();
  await page.getByRole('button', { name: 'Open shopping bag' }).click();
  await page.getByRole('button', { name: 'Sign in to place order' }).click();
  await signIn(page);
  await expect(page.getByRole('dialog', { name: /Your bag/ })).toBeVisible();
  await page.getByRole('button', { name: 'Place order ↗', exact: true }).click();
  await expect(page.locator('.order-card')).toHaveCount(1);
  await expect(page.locator('.status')).toHaveText('PROCESSING');
  page.on('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Cancel order' }).click();
  await expect(page.locator('.status')).toHaveText('CANCELLED');
  await page.getByRole('button', { name: 'Account for Alice Morgan' }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.locator('#shop-view')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('forme:token'))).toBeNull();
});

test('checkout refreshes stock and prices and asks the customer to review before submission', async ({ page }) => {
  let posts = 0;
  await mockServices(page, { updatedPrice: true });
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/orders' && request.method() === 'POST') posts++; });
  await page.goto('/');
  await page.getByRole('button', { name: 'Add Milo table lamp to bag', exact: true }).click();
  await page.getByRole('button', { name: 'Open shopping bag' }).click();
  await page.getByRole('button', { name: 'Sign in to place order' }).click();
  await signIn(page);
  await page.getByRole('button', { name: 'Place order ↗', exact: true }).click();
  await expect(page.locator('#checkout-error')).toContainText('Review it before placing your order');
  await expect(page.locator('.cart-total')).toContainText('$95.00');
  expect(posts).toBe(0);
});

test('registration uses the real user API contract and logs the customer in', async ({ page }) => {
  await mockServices(page); await page.goto('/');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('button', { name: 'Create an account', exact: true }).click();
  await page.getByLabel('Full name', { exact: true }).fill('Alice Morgan');
  await page.getByLabel('Email address', { exact: true }).fill('alice@example.com');
  await page.getByLabel('Password', { exact: true }).fill('secure-password');
  await page.getByRole('button', { name: 'Create account ↗', exact: true }).click();
  await expect(page.locator('#auth-dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Account for Alice Morgan' })).toBeVisible();
});

test('studio motion loads, tilts, pauses, and respects reduced motion', async ({ page }) => {
  await mockServices(page);
  await page.goto('/');
  const toggle = page.locator('#motion-toggle');
  await expect(toggle).toHaveText(/Pause motion/);
  const hero = page.locator('.hero-art');
  const box = await hero.boundingBox();
  await page.mouse.move(box.x + box.width * .8, box.y + box.height * .3);
  await expect(hero).toHaveClass(/is-tilting/);
  await toggle.click();
  await expect(page.locator('body')).toHaveClass(/motion-paused/);
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(toggle).toBeDisabled();
  await expect(page.locator('.hero-chair')).toHaveCSS('animation-name', 'none');
});
