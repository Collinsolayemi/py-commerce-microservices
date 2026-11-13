# FORME storefront

A responsive, buildless storefront for the Python ecommerce services. Cream, sage, and oak tones; original local SVG product illustrations; mobile layouts; accessible native dialogs; reduced-motion support; and keyboard focus styles.

## Start locally

From the repository root:

```bash
python3 frontend/server.py
```

Open **http://127.0.0.1:3000**. Python 3.9+ is sufficient for the frontend server. No Node installation or production JavaScript dependencies are needed to serve the app.

Start the User, Product, and Order services at ports 8001, 8002, and 8003 for live data. Full order processing also needs the RabbitMQ, inventory, and payment services. Alternatively, `docker compose up -d --build` starts the complete stack and serves the storefront at **http://localhost:3000**.

The local server and Docker nginx gateway forward `/api/users`, `/api/products`, and `/api/orders` to their respective services. The browser needs only the storefront's URL; authentication headers pass through the gateway. For a different local setup:

```bash
PORT=3001 USER_SERVICE_URL=http://127.0.0.1:8001 PRODUCT_SERVICE_URL=http://127.0.0.1:8002 ORDER_SERVICE_URL=http://127.0.0.1:8003 python3 frontend/server.py
```

The Python server binds to loopback by default and is intended for local development. Docker uses nginx to serve the same static files and proxy API calls.

## Customer flows

- Browse the live paginated catalog, search names and descriptions, filter by inferred product categories, and sort by price or name.
- Open product details, save favorites, add available stock to the bag, change quantities, and remove items.
- Keep the bag and favorites across reloads in local storage. Access tokens are kept in session storage, not permanent local storage.
- Register, sign in, inspect the account, and sign out using the User Service.
- Refresh live prices and stock before placing an authenticated order. Changes require review before submission.
- Follow authenticated orders with automatic refresh, inspect order totals and states, and cancel pending orders.
- Show readable validation, service, and session-expiration errors.

If the Product Service is unavailable, an explicitly labeled sample catalog lets you explore the UI. **Checkout stays disabled in preview mode.** Reconnect replaces the preview with the live catalog and reconciles the bag. No sample products are written into your backend.

## API integration details

The catalog API does not provide images or categories. The UI uses original local illustrations for recognized object types, a neutral placeholder for other products, and categories inferred from names/descriptions. Product details label the artwork as illustrations. Replace these with real product media when the backend supports it. Typography uses local system fonts, so the storefront has no external font or image dependency.

Prices display in USD because the current order API has no currency field. Shipping, tax calculation, real card entry, and fulfillment statuses are not invented. Checkout uses the existing Saga and simulated Payment Service; a pending order is shown as processing until the backend confirms or cancels it. The backend still accepts client-supplied unit prices; server-side catalog pricing and checkout idempotency are needed before a production payment rollout. The frontend refreshes prices but cannot enforce those backend guarantees. Failed POST requests are never automatically retried.

## Verification

```bash
cd frontend
npm ci
npm run check
npm test
npm run test:browser
```

Browser checks use the installed Google Chrome on macOS. Override `CHROME_PATH` for another installation. On other systems, install Playwright Chromium with `npx playwright install chromium`. Tests mock the HTTP contracts to cover offline preview, mobile layout, search, saved favorites, persistent bag, login, registration, checkout, cancellation, and changed pricing. They save desktop/mobile screenshots under ignored `test-results/`.

The local gateway has real HTTP upstream tests, runnable from the repository root:

```bash
.venv/bin/python -m unittest tests.test_storefront_proxy tests.test_order_security tests.test_e2e_saga -v
```
