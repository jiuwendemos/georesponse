import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function expectNoSeriousViolations(page: import('@playwright/test').Page) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const serious = results.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
  expect(serious, JSON.stringify(serious.map((item) => ({ id: item.id, nodes: item.nodes.length })))).toEqual([])
}

test.describe('shell', () => {
  test.setTimeout(90_000)

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.topbar')).toBeVisible()
  })

  test('loads the map-first stage with a real Sentinel basemap', async ({ page }) => {
    await expect(page.getByRole('main')).toBeVisible()
    await expect(page.locator('svg.map-canvas')).toBeVisible()
    const href = await page.locator('svg.map-canvas image').first().getAttribute('href')
    expect(href).toContain('data/real/')
    await expect(page.locator('.topbar')).toContainText('GeoResponse')
  })

  test('command palette opens with Ctrl+K and runs an action', async ({ page }) => {
    await expect(page.locator('svg.map-canvas')).toBeVisible()
    await page.keyboard.press('Control+k')
    const palette = page.getByRole('dialog', { name: 'Command palette' })
    await expect(palette).toBeVisible()
    await expect(palette.getByRole('option').first()).toBeVisible()
    await palette.getByRole('textbox', { name: 'Search commands' }).fill('watch')
    await page.keyboard.press('Enter')
    await expect(palette).toBeHidden()
    await expect(page.locator('.watch-page')).toBeVisible()
  })

  test('theme and density switch without breaking the shell', async ({ page }) => {
    for (const theme of ['light', 'dark', 'contrast']) {
      await page.getByRole('button', { name: /^Theme:/ }).click()
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    }
    await page.getByRole('button', { name: 'Settings' }).click()
    const dialog = page.getByRole('dialog', { name: 'Settings' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('radio', { name: 'Compact' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-density', 'compact')
  })

  test('deep links restore the view', async ({ page }) => {
    await page.goto('/#view=watch&scenario=ahr-2021-flood')
    await expect(page.locator('.watch-page')).toBeVisible()
  })

  test('German locale applies to the shell', async ({ page }) => {
    await page.getByRole('button', { name: 'Settings' }).click()
    await page.getByRole('dialog', { name: 'Settings' }).getByRole('radio', { name: 'Deutsch' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-language', 'de')
    await expect(page.locator('nav.nav')).toContainText('Überwachung')
  })

  test('map exposes an accessible data table', async ({ page }) => {
    await page.getByRole('button', { name: 'Accessible map table' }).click()
    const table = page.getByRole('dialog', { name: 'Map data table' })
    await expect(table).toBeVisible()
    await expect(table.getByRole('table')).toBeVisible()
    await table.getByRole('button', { name: 'Close table' }).click()
    await expect(table).toBeHidden()
  })

  test('has no serious accessibility violations on the stage', async ({ page }) => {
    await expect(page.locator('svg.map-canvas')).toBeVisible()
    await expectNoSeriousViolations(page)
  })

  test('has no serious accessibility violations in Watch', async ({ page }) => {
    await page.getByRole('button', { name: 'Watch' }).click()
    await expect(page.locator('.watch-page')).toBeVisible()
    await expectNoSeriousViolations(page)
  })
})
