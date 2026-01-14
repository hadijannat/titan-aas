import { test, expect } from '@playwright/test'

test.describe('Connectors Page', () => {
  test.beforeEach(async ({ page }) => {
    const statusResponse = page.waitForResponse((response) =>
      response.url().includes('/dashboard/connectors/status')
    )
    await page.goto('/connectors')
    await statusResponse
  })

  test('should display connectors heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Connectors' })).toBeVisible()
    await expect(page.getByText('Industrial protocol connectors')).toBeVisible()
  })

  test('should display summary cards', async ({ page }) => {
    // Wait for data
    await page.waitForTimeout(1000)

    // Check for summary labels
    await expect(page.getByText('Total Connectors')).toBeVisible()
    await expect(page.getByText('Connected')).toBeVisible()
    await expect(page.getByText('Failed')).toBeVisible()
  })

  test('should display connector cards for each protocol', async ({ page }) => {
    // Wait for connector data
    await page.waitForTimeout(1000)

    // Should show connector cards for OPC-UA, Modbus, and/or MQTT
    const connectorNames = ['OPC-UA', 'Modbus', 'MQTT']
    let foundCount = 0

    for (const name of connectorNames) {
      const element = page.getByText(name, { exact: true })
      if (await element.isVisible().catch(() => false)) {
        foundCount++
      }
    }

    // Should find at least one connector
    expect(foundCount).toBeGreaterThan(0)
  })

  test('should display connector state badges', async ({ page }) => {
    // Wait for a connector card to render
    const connectorHeading = page.getByRole('heading', { name: /OPC-UA|Modbus|MQTT/ })
    await expect(connectorHeading.first()).toBeVisible()

    // Should show state badges (connected, disconnected, disabled, etc.)
    const states = ['connected', 'disconnected', 'disabled', 'failed', 'connecting']
    let foundState = false

    for (const state of states) {
      const badge = page.locator('span').filter({ hasText: new RegExp(`^${state}$`, 'i') })
      if (await badge.first().isVisible().catch(() => false)) {
        foundState = true
        break
      }
    }

    expect(foundState).toBe(true)
  })

  test('should display last updated timestamp', async ({ page }) => {
    await expect(page.getByText(/Last updated:/)).toBeVisible({ timeout: 20000 })
  })

  test('should have refresh button', async ({ page }) => {
    // Look for refresh icon/button in the page
    const refreshButton = page.locator('button').filter({ has: page.locator('svg') }).first()
    await expect(refreshButton).toBeVisible()
  })
})
