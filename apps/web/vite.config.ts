/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'node:fs'

// CT1 f-2 (istem 66 · Y325): kapsam eşikleri depodaki TABANDAN (tek kaynak; CLAUDE.md "Test kapsamı").
const KAPSAM_TABANI = JSON.parse(
  readFileSync(new URL('../../tests/kapsam_tabani.json', import.meta.url), 'utf-8'),
).paketler.site_vitest

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Y243 (KP-2 A5): kapsam eşiği — CI `npm test -- --coverage` ile uygulanır (sağlayıcı @vitest/coverage-v8, devDependency).
  // Payda KP-1'de sabitlendi (52 dosya). Eşikler ölçülenin ~1 puan altı; yalnız YÜKSELTİLİR. KP-2 kapanış (2026-11-03) ölçülen:
  // satır %90,22 · deyim %88,40 · dal %81,01 · fonksiyon %84,63.
  // KP-3 AŞAMA D (2026-11-08, uç 6c7d4f10) ölçülen: satır %100 · deyim %99,09 · dal %92,09 · fonksiyon %99,31 (b04f518d; site o günden beri değişmedi).
  // KP-5 F (2026-11-15, uç 97b8d61e) ölçülen: satır %100 (1 142) · deyim %100 (1 329) · dal %93,03 · fonksiyon %100 → 99 / 99 / 92 / 99
  // (Y279: erişilemez 4 deyim gerekçeli `istanbul ignore` + sayan kapı).
  // KP-8 D (2026-11-17, KP-7 ile birleşik SON tur): TAM vitest (72 dosya / 1 215 test) satır / deyim / fonksiyon %100 · dal %97,84
  // (995 / 1 017; ödeme API'leri, plan fiyatı, sayfalar + 2 SAVUNMA etiketi) → 99 / 99 / 96 / 99.
  test: {
    // YS1c · Y320 (3): testlerin dili makinenin yereline değil TR'ye sabit (GitHub ubuntu koşucusu en-US → 25-11 site-ci 12 dosya kırmızı).
    setupFiles: ['./src/__tests__/_dilTr.kurulum.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}', 'api/**/*.ts', 'scripts/**/*.mjs'],
      exclude: ['**/__tests__/**', '**/*.test.*', '**/*.d.ts'],
      // CT1 f: lcov → fark kapsamı kapısı (scripts/fark_kapsami.py). Eşik = TABAN (tests/kapsam_tabani.json; yalnız yukarı).
      reporter: ['text-summary', 'json-summary', 'lcov'],
      thresholds: {
        lines: KAPSAM_TABANI.satir,
        statements: KAPSAM_TABANI.deyim,
        branches: KAPSAM_TABANI.dal,
        functions: KAPSAM_TABANI.islev,
      },
    },
  },
})
