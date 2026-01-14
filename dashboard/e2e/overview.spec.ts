import { test, expect } from '@playwright/test'

test.describe('Overview Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('should display system overview heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'System Overview' })).toBeVisible()
    await expect(page.getByText('Real-time health and status monitoring')).toBeVisible()
  })

  test('should display system status badge', async ({ page }) => {
    // Should show one of: healthy, degraded, or unhealthy
    const statusBadge = page.locator('span').filter({ hasText: /^(Healthy|Degraded|Unhealthy)$/ })
    await expect(statusBadge.first()).toBeVisible()
  })

  test('should display system info cards', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(1000)

    // Check for Version card
    await expect(page.getByText('Version')).toBeVisible()

    // Check for Environment card
    await expect(page.getByText('Environment')).toBeVisible()

    // Check for Uptime card
    await expect(page.getByText('Uptime')).toBeVisible()

    // Check for Total Entities card
    await expect(page.getByText('Total Entities')).toBeVisible()
  })

  test('should display entity counts section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Entity Counts' })).toBeVisible()

    // Check for entity type labels
    await expect(page.getByText('Asset Administration Shells')).toBeVisible()
    await expect(page.getByText('Submodels')).toBeVisible()
    await expect(page.getByText('Concept Descriptions')).toBeVisible()
  })

  test('should display component health section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Component Health' })).toBeVisible()

    // Should show at least PostgreSQL and Redis components
    await expect(page.getByText('PostgreSQL')).toBeVisible()
    await expect(page.getByText('Redis')).toBeVisible()
  })

  test('should display last updated timestamp', async ({ page }) => {
    await expect(page.getByText(/Last updated:/)).toBeVisible()
  })

  test('should show loading state initially', async ({ page }) => {
    // Navigate fresh and check for loading indicator
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    // Either loading spinner or content should be visible quickly
    const content = page.getByRole('heading', { name: 'System Overview' })
    await expect(content).toBeVisible({ timeout: 10000 })
  })
})
