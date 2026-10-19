// Author: mertaygn, cglrgrkn
// I18N-0: dil katmanı İLK içe aktarılır — senkron başlar, ilk karede metin hazır, <html lang> etkin dil (bkz. src/i18n/index.ts).
import './i18n'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
