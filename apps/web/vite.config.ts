/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Y243 (KP-2 A5): kapsam eşiği — CI `npm test -- --coverage` ile uygulanır (sağlayıcı @vitest/coverage-v8, devDependency).
  // Payda KP-1'de sabitlendi (52 dosya). Eşikler ölçülenin ~1 puan altı; yalnız YÜKSELTİLİR.
  test: {
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}', 'api/**/*.ts', 'scripts/**/*.mjs'],
      exclude: ['**/__tests__/**', '**/*.test.*', '**/*.d.ts'],
      reporter: ['text-summary', 'json-summary'],
      thresholds: { lines: 71, statements: 68, branches: 57, functions: 73 },
    },
  },
})
