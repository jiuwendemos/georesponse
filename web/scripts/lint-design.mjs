#!/usr/bin/env node
/*
 * Design adoption lint (ratchet).
 *
 * Enforces the 2026 design-system contract for *new* work:
 *   - no raw hex colours in UI chrome (chart/canvas modules own their palette)
 *   - no bespoke <button> elements outside the primitive modules
 *   - inline spacing values sit on the 4-point grid
 *   - no type below the 11px legibility floor
 *
 * Existing debt is recorded in `design-lint-baseline.json`. The counts in that
 * file may only go down. Run `npm run lint:design:update` after a migration to
 * lower the baseline; run `npm run lint:design` in CI to block new debt.
 */
import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const srcDir = join(root, 'src')
const baselinePath = join(root, 'design-lint-baseline.json')
const update = process.argv.includes('--update')

const COLOUR_ALLOWLIST = new Set([
  'src/components/Dashboard.tsx',
  'src/components/Booth.tsx',
  'src/components/MapView.tsx',
  'src/components/WatchMap.tsx',
  'src/components/StyleGuide.tsx',
])
const BUTTON_ALLOWLIST = new Set(['src/components/ds.tsx', 'src/components/ui.tsx'])

const files = []
function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) walk(full)
    else if (/\.(tsx|ts)$/.test(entry)) files.push(full)
  }
}
walk(srcDir)

const found = []
const details = []
const HEX = /#[0-9a-fA-F]{3,8}\b/

for (const file of files) {
  const rel = relative(root, file).replaceAll('\\', '/')
  const lines = readFileSync(file, 'utf8').split('\n')
  lines.forEach((line, index) => {
    const push = (rule, message) => {
      found.push(`${rel}|${rule}`)
      details.push(`${rel}:${index + 1} ${message}`)
    }
    if (!COLOUR_ALLOWLIST.has(rel) && HEX.test(line)) push('raw-colour', 'raw colour literal; use a token (var(--…))')
    if (!BUTTON_ALLOWLIST.has(rel) && /<button[\s>]/.test(line)) push('bespoke-button', 'bespoke <button>; use <Button>/<IconButton> from ds.tsx')
    const spacing = line.match(/(?:margin|padding|gap|rowGap|columnGap)\s*:\s*['"]?(-?\d+)px/)
    if (spacing && Number(spacing[1]) % 4 !== 0) push('off-grid', `spacing ${spacing[1]}px is off the 4-point grid`)
    const size = line.match(/fontSize\s*:\s*['"]?(\d+(?:\.\d+)?)px/)
    if (size && Number(size[1]) < 11) push('tiny-type', `font size ${size[1]}px is below the 11px floor`)
  })
}

const counts = {}
for (const key of found) counts[key] = (counts[key] ?? 0) + 1

const baseline = existsSync(baselinePath) ? JSON.parse(readFileSync(baselinePath, 'utf8')) : {}

if (update) {
  writeFileSync(baselinePath, JSON.stringify(counts, null, 2) + '\n')
  console.log(`design lint: baseline updated (${found.length} known items)`)
  process.exit(0)
}

const regressions = []
for (const [key, count] of Object.entries(counts)) {
  const allowed = baseline[key] ?? 0
  if (count > allowed) regressions.push({ key, count, allowed })
}

if (regressions.length) {
  for (const item of regressions) console.error(`error: ${item.key} — ${item.count} found, baseline allows ${item.allowed}`)
  console.error(`\nNew design debt:\n${details.join('\n')}`)
  console.error('\nUse a token/primitive, or if this is an intentional migration step, run `npm run lint:design:update`.')
  process.exit(1)
}

const improved = Object.entries(baseline).filter(([key, allowed]) => (counts[key] ?? 0) < allowed)
if (improved.length) {
  console.log(`design lint: ${improved.length} baselines can be lowered — run \`npm run lint:design:update\` to lock in the win`)
}
console.log(`design lint: ${files.length} files, ${found.length} known items, no new debt`)
