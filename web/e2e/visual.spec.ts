import { test, expect } from '@playwright/test'

// Baselines are generated on the development OS (win32) and asserted there.
// CI runs the functional + axe suite; pixel baselines are intentionally not
// shared across operating systems because font rasterisation differs.
test.skip(process.env.CI === 'true', 'visual baselines are per-OS; generated on the dev workstation')

async function settle(page: import('@playwright/test').Page) {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(() => localStorage.setItem('georesponse.onboarded.v1', '1'))
  await page.goto('/')
  await expect(page.locator('svg.map-canvas')).toBeVisible()
  await page.waitForTimeout(700)
}

test.describe('visual regression', () => {
  test('stage — dark', async ({ page }) => {
    await settle(page)
    await page.locator('html').evaluate((node) => node.setAttribute('data-theme', 'dark'))
    await expect(page).toHaveScreenshot('stage-dark.png', { fullPage: false })
  })

  test('stage — light', async ({ page }) => {
    await settle(page)
    await page.locator('html').evaluate((node) => node.setAttribute('data-theme', 'light'))
    await expect(page).toHaveScreenshot('stage-light.png', { fullPage: false })
  })

  test('command palette', async ({ page }) => {
    await settle(page)
    await page.keyboard.press('Control+k')
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible()
    await expect(page).toHaveScreenshot('palette.png', { fullPage: false })
  })
})
