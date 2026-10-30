import { defineConfig } from 'vitest/config'

// Unit tests live next to the source. End-to-end specs run under Playwright.
export default defineConfig({
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
