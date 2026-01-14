import { test, expect } from '@playwright/test'

test.describe('Dashboard Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('should display sidebar with navigation items', async ({ page }) => {
    // Check sidebar is visible
    const sidebar = page.locator('aside')
    await expect(sidebar).toBeVisible()

    // Check Titan Control title
    await expect(page.getByText('Titan Control')).toBeVisible()
    await expect(page.getByText('System Dashboard')).toBeVisible()
  })

  test('should have all navigation links', async ({ page }) => {
    const navItems = [
      'Overview',
      'Database',
      'Cache',
      'Events',
      'Connectors',
      'Security',
      'Observability',
    ]

    for (const item of navItems) {
      await expect(page.getByRole('link', { name: item })).toBeVisible()
    }
  })

  test('should navigate to Overview page by default', async ({ page }) => {
    // Overview should be the default route
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'System Overview' })).toBeVisible()
  })

  test('should navigate to Database page', async ({ page }) => {
    await page.getByRole('link', { name: 'Database' }).click()
    await expect(page).toHaveURL('/database')
    await expect(page.getByRole('heading', { name: 'Database' })).toBeVisible()
  })

  test('should navigate to Cache page', async ({ page }) => {
    await page.getByRole('link', { name: 'Cache' }).click()
    await expect(page).toHaveURL('/cache')
    await expect(page.getByRole('heading', { name: 'Cache', exact: true })).toBeVisible()
  })

  test('should navigate to Events page', async ({ page }) => {
    await page.getByRole('link', { name: 'Events' }).click()
    await expect(page).toHaveURL('/events')
    await expect(page.getByRole('heading', { name: 'Events', exact: true })).toBeVisible()
  })

  test('should navigate to Connectors page', async ({ page }) => {
    await page.getByRole('link', { name: 'Connectors' }).click()
    await expect(page).toHaveURL('/connectors')
    await expect(page.getByRole('heading', { name: 'Connectors' })).toBeVisible()
  })

  test('should navigate to Security page', async ({ page }) => {
    await page.getByRole('link', { name: 'Security' }).click()
    await expect(page).toHaveURL('/security')
    await expect(page.getByRole('heading', { name: 'Security' })).toBeVisible()
  })

  test('should navigate to Observability page', async ({ page }) => {
    await page.getByRole('link', { name: 'Observability' }).click()
    await expect(page).toHaveURL('/observability')
    await expect(page.getByRole('heading', { name: 'Observability' })).toBeVisible()
  })

  test('should highlight active navigation item', async ({ page }) => {
    // Check Overview is active initially
    const overviewLink = page.getByRole('link', { name: 'Overview' })
    await expect(overviewLink).toHaveClass(/bg-titan-600/)

    // Navigate to Database and check it becomes active
    await page.getByRole('link', { name: 'Database' }).click()
    const databaseLink = page.getByRole('link', { name: 'Database' })
    await expect(databaseLink).toHaveClass(/bg-titan-600/)

    // Overview should no longer be active
    await expect(overviewLink).not.toHaveClass(/bg-titan-600/)
  })
})
