import { test, expect } from '@playwright/test'

test.describe('Security Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/security')
  })

  test('should display security heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Security' })).toBeVisible()
    await expect(page.getByText('Audit log and session management')).toBeVisible()
  })

  test('should display stats cards', async ({ page }) => {
    // Wait for data
    await page.waitForTimeout(1000)

    // Check for stat labels
    await expect(page.getByText('Total Audit Entries', { exact: true })).toBeVisible()
    await expect(page.getByText('Active Sessions', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Page', { exact: true }).first()).toBeVisible()
  })

  test('should display audit log section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Audit Log' })).toBeVisible()

    // Check for search input
    await expect(page.getByPlaceholder(/Search by action, user/)).toBeVisible()

    // Check for table headers
    await expect(page.getByRole('columnheader', { name: 'Timestamp' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'User' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Action' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Resource' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Status' })).toBeVisible()
  })

  test('should display active sessions section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Active Sessions' })).toBeVisible()
  })

  test('should allow searching audit log', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search by action, user/)
    await searchInput.fill('CREATE')

    // Wait for search to apply
    await page.waitForTimeout(500)

    await expect(searchInput).toHaveValue('CREATE')
  })

  test('should have pagination controls', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(1000)

    // Check for pagination info
    await expect(page.getByText(/Showing \d+ to \d+/)).toBeVisible()

    // Check for pagination buttons (previous/next)
    const prevButton = page.locator('button').filter({ has: page.locator('svg') }).nth(-2)
    const nextButton = page.locator('button').filter({ has: page.locator('svg') }).last()

    // At least one pagination button should be visible
    const prevVisible = await prevButton.isVisible().catch(() => false)
    const nextVisible = await nextButton.isVisible().catch(() => false)
    expect(prevVisible || nextVisible).toBe(true)
  })
})
