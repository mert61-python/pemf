import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

// Y211 · S-D67.8: Google AI Studio şablon artığı (Gemini anahtarı tanımı, AI Studio HMR anahtarı) kaldırıldı — simülatör Gemini'yi
// çağırmaz. `@google/genai` paket kaydı da YH-A2'de (2026-11-16) package.json + kilitten kaldırıldı.
export default defineConfig(() => {
  return {
    base: './',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
  };
});
