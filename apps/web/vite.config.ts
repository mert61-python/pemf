/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Y243 (KP-2 A5): kapsam eşiği — CI `npm test -- --coverage` ile uygulanır (sağlayıcı @vitest/coverage-v8, devDependency).
  // Payda KP-1'de sabitlendi (52 dosya). Eşikler ölçülenin ~1 puan altı; yalnız YÜKSELTİLİR. KP-2 kapanış (2026-11-03) ölçülen:
  // satır %90,22 · deyim %88,40 · dal %81,01 · fonksiyon %84,63.
  test: {
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}', 'api/**/*.ts', 'scripts/**/*.mjs'],
      exclude: ['**/__tests__/**', '**/*.test.*', '**/*.d.ts'],
      reporter: ['text-summary', 'json-summary'],
      thresholds: { lines: 89, statements: 87, branches: 80, functions: 83 },
    },
  },
})
