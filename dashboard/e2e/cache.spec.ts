import { test, expect } from '@playwright/test'

test.describe('Cache Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cache')
  })

  test('should display cache heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cache', exact: true })).toBeVisible()
    await expect(page.getByText('Redis cache statistics and key management')).toBeVisible()
  })

  test('should display cache stats cards', async ({ page }) => {
    // Wait for data
    await page.waitForTimeout(1000)

    // Check for cache stat labels
    await expect(page.getByText('Memory Used')).toBeVisible()
    await expect(page.getByText('Total Keys')).toBeVisible()
    await expect(page.getByText('Connected Clients')).toBeVisible()
  })

  test('should display cache hit ratio section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cache Hit Ratio' })).toBeVisible()

    // Check for hit/miss labels
    await expect(page.getByText('Hits')).toBeVisible()
    await expect(page.getByText('Misses')).toBeVisible()
  })

  test('should display cache invalidation section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cache Invalidation' })).toBeVisible()

    // Check for invalidation input and button
    await expect(page.getByPlaceholder('titan:aas:*')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Invalidate' })).toBeVisible()
  })

  test('should display key browser section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Key Browser' })).toBeVisible()

    // Check for search input
    await expect(page.getByPlaceholder(/Search pattern/)).toBeVisible()

    // Check for table headers
    await expect(page.getByRole('columnheader', { name: 'Key' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Type' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'TTL' })).toBeVisible()
  })

  test('should allow searching for keys', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search pattern/)
    await searchInput.fill('titan:*')

    // Wait for search results
    await page.waitForTimeout(1000)

    // Key browser should update
    await expect(page.getByRole('heading', { name: 'Key Browser' })).toBeVisible()
  })

  test('invalidate button should be disabled when pattern is empty', async ({ page }) => {
    const invalidateButton = page.getByRole('button', { name: 'Invalidate' })

    // Clear the pattern input
    const patternInput = page.getByPlaceholder('titan:aas:*')
    await patternInput.clear()

    // Button should be disabled
    await expect(invalidateButton).toBeDisabled()
  })
})
