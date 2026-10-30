import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const dist = fileURLToPath(new URL('../dist/', import.meta.url))
const html = readFileSync(join(dist, 'index.html'), 'utf8')
const assets = [...html.matchAll(/(?:src|href)="\.?\/?(assets\/[^"]+)"/g)].map((match) => match[1])
const unique = [...new Set(assets)]
let total = 0
for (const asset of unique) {
  const path = join(dist, ...asset.split('/'))
  const gzip = gzipSync(readFileSync(path)).length
  total += gzip
  console.log(`${asset}: ${(gzip / 1024).toFixed(1)} KB gzip`)
}
const budgetKb = 250
console.log(`initial JS/CSS: ${(total / 1024).toFixed(1)} KB gzip (budget ${budgetKb} KB)`)
if (total / 1024 > budgetKb) {
  console.error('Budget exceeded')
  process.exit(1)
}
const files = readdirSync(join(dist, 'assets'))
const largest = files.map((file) => ({ file, kb: statSync(join(dist, 'assets', file)).size / 1024 })).sort((a, b) => b.kb - a.kb)[0]
console.log(`largest asset: ${largest.file} ${largest.kb.toFixed(1)} KB raw`)
