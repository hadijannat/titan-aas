import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for Titan Dashboard E2E tests.
 *
 * Run tests with:
 *   npx playwright test              # Run all tests
 *   npx playwright test --ui         # Run with UI mode
 *   npx playwright test --headed     # Run with browser visible
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],

  use: {
    // Base URL for all tests - can be overridden via env
    baseURL: process.env.DASHBOARD_URL || 'http://localhost:5173',

    // Collect trace on first retry
    trace: 'on-first-retry',

    // Take screenshot on failure
    screenshot: 'only-on-failure',

    // Record video on failure
    video: 'on-first-retry',
  },

  // Configure projects for different browsers
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Web server configuration - starts Vite dev server before tests
  webServer: process.env.CI
    ? undefined // In CI, dashboard runs via Docker
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },

  // Global timeout for each test
  timeout: 30 * 1000,

  // Expect timeout
  expect: {
    timeout: 10 * 1000,
  },
})
