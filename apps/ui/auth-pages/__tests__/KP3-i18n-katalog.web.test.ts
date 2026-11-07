/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · auth-pages/i18n_katalog.js (üretilmiş; e-posta bağlantısıyla açılan şifre sıfırlama / onay sayfalarının dil katmanı) —
 * her test bir DAVRANIŞ iddiası:
 *  - Dil: `?dil=` adres parametresi tarayıcı dilinden ÖNCE gelir; "tr" ile başlayan her değer Türkçe, diğer her şey İngilizce.
 *  - `tf`: seçili dilde yoksa Türkçe metne, o da yoksa anahtarın KENDİSİNE düşer (boş metin göstermez).
 *  - `uygulaDil`: <html lang> ayarlanır; data-i18n metin, data-i18n-html HTML, data-i18n-placeholder yer tutucu olarak doldurulur.
 * GERÇEK: üretilmiş betiğin kendisi (jsdom penceresinde yüklenir). Katalog DEĞERLERİ teste gömülmez — kaynak JSON'dan okunur.
 */
import trKaynak from "../../src/i18n/tr/authSayfa.json";
import enKaynak from "../../src/i18n/en/authSayfa.json";

type Pencere = Window & { PEMF_DIL: string; tf: (a: string) => string; uygulaDil: () => void };
const w = window as unknown as Pencere;

function duz(o: Record<string, unknown>, on = "authSayfa"): Record<string, string> {
  const c: Record<string, string> = {};
  for (const [k, v] of Object.entries(o)) {
    if (v && typeof v === "object") Object.assign(c, duz(v as Record<string, unknown>, `${on}.${k}`));
    else c[`${on}.${k}`] = String(v);
  }
  return c;
}
const TR = duz(trKaynak as Record<string, unknown>);
const EN = duz(enKaynak as Record<string, unknown>);
const ANAHTAR = "authSayfa.reset.baslik";

// jest-expo ortamı genel `URLSearchParams`'ı RN çoklu-dolgusuyla değiştirir (sorgu okunamaz — ölçüldü); sayfanın koştuğu tarayıcıda
// yerel uygulama vardır → platform sınırında Node'un standart uygulaması verilir.
const ilkUSP = (window as unknown as { URLSearchParams: unknown }).URLSearchParams;
beforeAll(() => { (window as unknown as { URLSearchParams: unknown }).URLSearchParams = require("url").URLSearchParams; });
afterAll(() => { (window as unknown as { URLSearchParams: unknown }).URLSearchParams = ilkUSP; });

function yukle(adres: string, tarayiciDili: string) {
  window.history.replaceState({}, "", adres);
  Object.defineProperty(window.navigator, "language", { value: tarayiciDili, configurable: true });
  jest.isolateModules(() => { require("../i18n_katalog.js"); });
}

it.each([
  ["/sifirla?dil=tr-TR", "en-US", "tr"],
  ["/sifirla?dil=en", "tr-TR", "en"],
  ["/sifirla", "tr", "tr"],
  ["/sifirla", "de-DE", "en"],
])("adres %s + tarayıcı %s → %s", (adres, tarayici, beklenen) => {
  yukle(adres, tarayici);
  expect(w.PEMF_DIL).toBe(beklenen);
  expect(w.tf(ANAHTAR)).toBe((beklenen === "tr" ? TR : EN)[ANAHTAR]);
});

it("tf: bilinmeyen anahtar KENDİSİNE düşer (boş metin yok)", () => {
  yukle("/sifirla?dil=en", "en");
  expect(w.tf("authSayfa.yok.boyleBirAnahtar")).toBe("authSayfa.yok.boyleBirAnahtar");
});

it("uygulaDil: lang + metin + HTML + yer tutucu doldurulur", () => {
  yukle("/sifirla?dil=en", "en");
  document.documentElement.setAttribute("lang", "tr");
  document.body.innerHTML = `
    <h1 data-i18n="${ANAHTAR}">x</h1>
    <p data-i18n-html="authSayfa.reset.aciklama">x</p>
    <input data-i18n-placeholder="${ANAHTAR}" />`;
  w.uygulaDil();
  expect(document.documentElement.getAttribute("lang")).toBe("en");
  expect(document.querySelector("h1")!.textContent).toBe(EN[ANAHTAR]);
  expect(document.querySelector("p")!.innerHTML).toBe(EN["authSayfa.reset.aciklama"]);
  expect(document.querySelector("input")!.getAttribute("placeholder")).toBe(EN[ANAHTAR]);
});
