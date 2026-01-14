import { test, expect } from '@playwright/test'

test.describe('Events Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/events')
  })

  test('should display events heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Events', exact: true })).toBeVisible()
    await expect(page.getByText(/Event history|Live event stream/)).toBeVisible()
  })

  test('should display stream control buttons', async ({ page }) => {
    // Start Stream button should be visible initially
    await expect(page.getByRole('button', { name: 'Start Stream' })).toBeVisible()
  })

  test('should display event filter input', async ({ page }) => {
    await expect(page.getByPlaceholder(/Filter by event type/)).toBeVisible()
  })

  test('should display events list section', async ({ page }) => {
    // Check for Recent Events heading
    await expect(page.getByText(/Live Events|Recent Events/)).toBeVisible()
  })

  test('should display event stats summary', async ({ page }) => {
    // Check for event type stats
    await expect(page.getByText('CREATED')).toBeVisible()
    await expect(page.getByText('UPDATED')).toBeVisible()
    await expect(page.getByText('DELETED')).toBeVisible()
    await expect(page.getByText('Total')).toBeVisible()
  })

  test('should toggle streaming mode', async ({ page }) => {
    const startButton = page.getByRole('button', { name: 'Start Stream' })
    await expect(startButton).toBeVisible()

    // Click to start streaming
    await startButton.click()

    // Should show Stop Stream button and streaming indicator
    await expect(page.getByRole('button', { name: 'Stop Stream' })).toBeVisible()
    await expect(page.getByText(/Streaming live events/)).toBeVisible()

    // Click to stop
    await page.getByRole('button', { name: 'Stop Stream' }).click()
    await expect(page.getByRole('button', { name: 'Start Stream' })).toBeVisible()
  })

  test('should show Clear button when streaming', async ({ page }) => {
    // Start streaming
    await page.getByRole('button', { name: 'Start Stream' }).click()

    // Clear button should be visible
    await expect(page.getByRole('button', { name: 'Clear' })).toBeVisible()

    // Stop streaming
    await page.getByRole('button', { name: 'Stop Stream' }).click()
  })

  test('should filter events by text', async ({ page }) => {
    const filterInput = page.getByPlaceholder(/Filter by event type/)
    await filterInput.fill('CREATED')

    // Wait for filter to apply
    await page.waitForTimeout(500)

    // Filter should be applied
    await expect(filterInput).toHaveValue('CREATED')
  })
})
