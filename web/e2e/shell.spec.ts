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
    if (!test.info().title.includes('first-run')) {
      await page.addInitScript(() => localStorage.setItem('georesponse.onboarded.v1', '1'))
    }
    await page.goto('/')
    await expect(page.locator('.topbar')).toBeVisible({ timeout: 20_000 })
  })

  test('loads the map-first stage with a real Sentinel basemap', async ({ page }) => {
    await expect(page.getByRole('main')).toBeVisible()
    await expect(page.locator('svg.map-canvas')).toBeVisible()
    await expect(page.locator('svg.map-canvas image').first()).toHaveAttribute('href', /data\/real\//)
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

  test('first-run welcome tour appears and can be skipped', async ({ page }) => {
    const dialog = page.getByRole('dialog', { name: 'Welcome to GeoResponse' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Next' }).click()
    await expect(dialog).toContainText('Everything is one keystroke away')
    await dialog.getByRole('button', { name: 'Skip' }).click()
    await expect(dialog).toBeHidden()
  })

  test('saves and restores a view from the palette', async ({ page }) => {
    await page.keyboard.press('Control+k')
    await page.getByRole('textbox', { name: 'Search commands' }).fill('Save current view')
    await page.getByRole('option', { name: /Save current view/ }).click()
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeHidden()
    await page.keyboard.press('Control+k')
    await expect(page.getByRole('textbox', { name: 'Search commands' })).toBeVisible()
    await expect(page.getByRole('option', { name: /Saved view:/ }).first()).toBeVisible()
  })

  test('deep links restore the view', async ({ page }) => {
    await page.goto('/#view=watch&scenario=ahr-2021-flood')
    await expect(page.locator('.watch-page')).toBeVisible()
  })

  test('deep links open the exact alert', async ({ page }) => {
    await page.goto('/#view=watch&scenario=ahr-2021-flood&alert=ALT-1001')
    await expect(page.locator('.watch-detail')).toContainText('ALT-1001')
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

  test('map shows orientation, scale and a mini-map', async ({ page }) => {
    await expect(page.locator('svg.map-canvas')).toBeVisible()
    await expect(page.locator('.map-minimap')).toBeVisible()
    await expect(page.locator('.map-scale')).toHaveText(/km|m/)
    await expect(page.locator('.map-compass')).toContainText('N')
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

  test('has no serious accessibility violations in Pilot', async ({ page }) => {
    await page.getByRole('button', { name: 'Pilot' }).click()
    await expect(page.getByRole('main')).toBeVisible()
    await expectNoSeriousViolations(page)
  })

  test('shows what changed since the last visit', async ({ page }) => {
    await page.getByRole('button', { name: 'Watch' }).click()
    await expect(page.locator('.watch-changed')).toContainText('Since you last looked')
    await expect(page.locator('.watch-changed')).toContainText('new alert')
  })

  test('records alert quality feedback from Watch', async ({ page }) => {
    await page.getByRole('button', { name: 'Watch' }).click()
    await expect(page.locator('.watch-page')).toBeVisible()
    const group = page.getByRole('group', { name: 'Alert quality feedback' })
    await expect(group).toBeVisible()
    await group.getByRole('button', { name: 'Useful' }).first().click()
    await expect(page.locator('.watch-toast')).toContainText('feedback')
  })

  test('role selection hides surfaces it cannot act on', async ({ page }) => {
    await page.getByRole('button', { name: 'Settings' }).click()
    const dialog = page.getByRole('dialog', { name: 'Settings' })
    await dialog.getByRole('radio', { name: 'Presenter' }).click()
    await dialog.getByRole('button', { name: 'Close' }).last().click()
    await expect(page.locator('nav.nav')).not.toContainText('Watch')
    await expect(page.locator('nav.nav')).toContainText('Booth')
  })

  test('shows a mobile location indicator', async ({ page }) => {
    test.skip(test.info().project.name !== 'mobile', 'mobile-only affordance')
    await expect(page.locator('.mobile-location')).toContainText('Stage')
  })

  test('reset returns to the start in under five seconds', async ({ page }) => {
    const started = Date.now()
    await page.getByRole('button', { name: /^Reset/ }).click()
    await expect(page.locator('.topbar')).toBeVisible()
    expect(Date.now() - started).toBeLessThan(5000)
  })

  test('returning operators land on Watch', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('georesponse.lastSeen', new Date().toISOString()))
    await page.goto('/')
    await expect(page.locator('.watch-page')).toBeVisible()
  })

  test('runs the manager cut and opens the proof page', async ({ page }) => {
    await page.getByRole('button', { name: 'Manager demo' }).click()
    const rail = page.getByRole('region', { name: 'Manager demo' })
    await expect(rail).toContainText('The event')
    await rail.getByRole('button', { name: 'Next' }).click()
    await expect(rail).toContainText('The decision')
    await rail.getByRole('button', { name: 'Next' }).click()
    await expect(rail).toContainText('The human correction')
    for (let step = 0; step < 4; step += 1) {
      await rail.getByRole('button', { name: 'Next' }).click()
    }
    await expect(rail).toContainText('The proof')
    await expect(page.getByRole('dialog', { name: 'Manager proof' })).toBeVisible()
    await rail.getByRole('button', { name: 'Finish' }).click()
    await expect(rail).toBeHidden()
  })

  test('creates and undoes a scope', async ({ page }) => {
    await page.getByRole('button', { name: 'Watch' }).click()
    await expect(page.locator('.watch-page')).toBeVisible()
    await page.locator('.watch-tabs').getByRole('button', { name: 'scopes', exact: true }).click()
    await page.getByRole('button', { name: 'New scope' }).click()
    const dialog = page.getByRole('dialog', { name: 'Create scope' })
    await dialog.getByPlaceholder('Ahr corridor — north bank').fill('Test corridor')
    await dialog.getByRole('button', { name: 'Create scope' }).click()
    await expect(page.locator('.watch-toast')).toContainText('created')
    await page.getByRole('button', { name: 'Undo last scope' }).click()
    await expect(page.locator('.watch-toast')).toContainText('undone')
  })

  test('layer panel exposes opacity, order and saved sets', async ({ page }) => {
    const layers = page.locator('.layers')
    await expect(layers.getByLabel('Change opacity')).toBeVisible()
    await expect(layers.getByLabel('Roads opacity')).toBeVisible()
    await layers.getByRole('button', { name: 'Move Change up' }).click()
    await layers.getByRole('button', { name: 'Save set' }).click()
    await expect(layers.getByLabel('Saved layer sets')).toContainText('Set 1')
  })

  test('keeps product chrome at or above the 11 px floor', async ({ page }) => {
    const measure = () =>
      page.evaluate(() => {
        const small: string[] = []
        for (const element of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
          if (element.closest('svg')) continue
          if (!element.getClientRects().length) continue
          const text = (element.textContent ?? '').trim()
          if (!text || element.children.length > 0) continue
          const size = Number.parseFloat(getComputedStyle(element).fontSize)
          if (size < 11) small.push(`${element.tagName}.${element.className} ${size}px`)
        }
        return small.slice(0, 10)
      })
    expect(await measure()).toEqual([])
    for (const view of ['Watch', 'Pilot']) {
      await page.getByRole('button', { name: view }).click()
      await expect(page.getByRole('main')).toBeVisible()
      expect(await measure(), view).toEqual([])
    }
  })

  test('never scrolls horizontally', async ({ page }) => {
    await page.getByRole('button', { name: 'Watch' }).click()
    await expect(page.locator('.watch-page')).toBeVisible()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  })
})
