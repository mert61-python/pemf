import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import {DIL, t} from './i18n';

// I18N (Y159): sekme başlığı katalogdan (sayfa dili `?dil=` / tarayıcı dili; bayrak kapalıyken tr).
// Y162 (sahip, 2026-10-20): <html lang> SAYFA DİLİNİ taşır — CSS `uppercase` dile göre büyütür; Türkçe sayfada `tr` olmazsa
// "Kare sinyali" → "KARE SINYALI", "Deri" → "DERI" yazılıyordu (göç öncesi `lang="en"`). Artık "KARE SİNYALİ" / "DERİ".
document.documentElement.lang = DIL;
document.title = t('baslik.belge');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
