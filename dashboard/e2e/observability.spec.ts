import { test, expect } from '@playwright/test'

test.describe('Observability Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/observability')
  })

  test('should display observability heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Observability' })).toBeVisible()
    await expect(page.getByText('Logging, tracing, and system profiling')).toBeVisible()
  })

  test('should display quick stats cards', async ({ page }) => {
    // Check for stat labels
    await expect(page.getByText('Current Log Level', { exact: true })).toBeVisible()
    await expect(page.getByText('Active Loggers', { exact: true })).toBeVisible()
    await expect(page.getByText('Tracing', { exact: true })).toBeVisible()
    await expect(page.getByText('Metrics', { exact: true })).toBeVisible()
  })

  test('should display runtime log level section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Runtime Log Level' })).toBeVisible()
    await expect(
      page.getByText(/Adjust the logging verbosity at runtime/)
    ).toBeVisible()
  })

  test('should display log level buttons', async ({ page }) => {
    const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

    for (const level of logLevels) {
      await expect(page.getByRole('button', { name: level })).toBeVisible()
    }
  })

  test('should have one log level button highlighted', async ({ page }) => {
    // One of the log level buttons should have a ring (active indicator)
    const buttons = page.getByRole('button').filter({ hasText: /DEBUG|INFO|WARNING|ERROR|CRITICAL/ })
    const count = await buttons.count()

    expect(count).toBe(5)

    // At least one should have the active class
    let hasActive = false
    for (let i = 0; i < count; i++) {
      const className = await buttons.nth(i).getAttribute('class')
      if (className && className.includes('ring-')) {
        hasActive = true
        break
      }
    }
    expect(hasActive).toBe(true)
  })

  test('should display system profile section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'System Profile' })).toBeVisible()

    // Check for CPU and Memory sections
    await expect(page.getByRole('heading', { name: 'CPU', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Memory', exact: true })).toBeVisible()
  })

  test('should display external dashboards section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'External Dashboards' })).toBeVisible()

    // Check for links to external tools
    await expect(page.getByText('Prometheus Metrics')).toBeVisible()
    await expect(page.getByText('API Documentation')).toBeVisible()
    await expect(page.getByText('GraphQL Playground')).toBeVisible()
  })

  test('should display distributed tracing section', async ({ page }) => {
    const tracingSection = page
      .getByRole('heading', { name: 'Distributed Tracing', exact: true })
      .locator('..')
    await expect(tracingSection).toBeVisible()
    await expect(tracingSection.getByText(/OpenTelemetry/)).toBeVisible()
  })

  test('external dashboard links should have correct hrefs', async ({ page }) => {
    // Check Prometheus link
    const prometheusLink = page.getByRole('link', { name: /Prometheus Metrics/ })
    await expect(prometheusLink).toHaveAttribute('href', '/metrics')

    // Check API docs link
    const docsLink = page.getByRole('link', { name: /API Documentation/ })
    await expect(docsLink).toHaveAttribute('href', '/docs')

    // Check GraphQL link
    const graphqlLink = page.getByRole('link', { name: /GraphQL Playground/ })
    await expect(graphqlLink).toHaveAttribute('href', '/graphql')
  })
})
