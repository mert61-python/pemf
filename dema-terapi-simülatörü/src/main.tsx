import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import {t} from './i18n';

// I18N (Y159): sekme başlığı katalogdan (sayfa dili `?dil=` / tarayıcı dili; bayrak kapalıyken tr).
// <html lang> DEĞİŞMEZ (index.html'deki göç öncesi değer): CSS `uppercase` dile göre büyütür — `tr` yapmak Türkçe görünümü
// değiştiriyordu ("KARE SINYALI" → "KARE SİNYALİ", I18N-0 A12'de ölçüldü). Düzeltme sahip kararı (DUZELTME-I18N.md [SAHİBE]).
document.title = t('baslik.belge');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
