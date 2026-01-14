import { test, expect } from '@playwright/test'

test.describe('Database Page', () => {
  test.beforeEach(async ({ page }) => {
    const statsResponse = page.waitForResponse((response) =>
      response.url().includes('/dashboard/database/stats')
    )
    await page.goto('/database')
    await statsResponse
  })

  test('should display database heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Database', exact: true })).toBeVisible()
    await expect(page.getByText('PostgreSQL connection pool and table statistics')).toBeVisible()
  })

  test('should display connection pool stats cards', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(1000)

    // Check for pool stat labels
    await expect(page.getByText('Pool Size', { exact: true })).toBeVisible()
    await expect(page.getByText('Active Connections', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Available', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Overflow', { exact: true }).first()).toBeVisible()
  })

  test('should display connection pool utilization section', async ({ page }) => {
    const utilization = page
      .getByRole('heading', { name: 'Connection Pool Utilization', exact: true })
      .locator('..')
    await expect(utilization).toBeVisible()

    // Check for pool status labels
    await expect(utilization.getByText('Idle', { exact: true })).toBeVisible()
    await expect(utilization.getByText('In Use', { exact: true })).toBeVisible()
  })

  test('should display table statistics section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Table Statistics' })).toBeVisible()

    // Check for table headers
    await expect(page.getByRole('columnheader', { name: 'Table Name' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Row Count' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Size' })).toBeVisible()
  })

  test('should display last updated timestamp', async ({ page }) => {
    // Wait for data
    await page.waitForTimeout(2000)
    await expect(page.getByText(/Last updated:/)).toBeVisible()
  })
})
