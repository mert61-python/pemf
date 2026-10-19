import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import {DIL, t} from './i18n';

// I18N (Y159): sayfa dili `?dil=` / tarayıcı dilinden (bayrak kapalıyken tr) — <html lang> ve sekme başlığı katalogdan.
document.documentElement.lang = DIL;
document.title = t('baslik.belge');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
