const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testMatch: 'pwa.check.cjs',
  workers: 1,
  timeout: 120_000,
  reporter: 'list',
  use: {
    baseURL: process.env.PHONEBOX_PWA_TEST_URL,
    launchOptions: { executablePath: process.env.PHONEBOX_TEST_CHROMIUM || '/usr/bin/chromium' },
    trace: 'retain-on-failure',
  },
});
