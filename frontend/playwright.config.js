import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './browser-tests',
  fullyParallel: false,
  timeout: 90000,
  expect: { timeout: 15000 },
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:3100', browserName: 'chromium', launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : process.platform === 'darwin' ? { executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' } : {}, screenshot: 'only-on-failure' },
  webServer: { command: 'PORT=3100 python3 server.py', url: 'http://127.0.0.1:3100', reuseExistingServer: false, timeout: 20000 },
});
