import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Relative base: the app runs from /, a sub-path or a USB stick.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 1600,
  },
})
