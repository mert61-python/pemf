/**
 * i18n BAŞLATMA (T2) — i18next + react-i18next, kaynaklar PAKETİN İÇİNDE, başlatma SENKRON (ilk karede metin hazır).
 *
 * - `initAsync: false` + gömülü kaynak → `init` dönmeden çeviriler hazır; `useSuspense: false` → hiçbir ekran (özellikle ACİL DURDUR)
 *   çeviriyi BEKLEMEZ.
 * - İlk dil: bayrak kapalıyken `tr`. Açıkken web'de kayıtlı seçim eşzamanlı okunur; yoksa cihaz dili. Yerelde (Android / iOS) kayıtlı
 *   seçim AsyncStorage'tan zaman uyumsuz gelir → `kayitliDiliUygula()` (aşağıda, içe aktarmada tetiklenir) dili düzeltir.
 * - Başlatma ya da depo okuma hatası uygulamayı DÜŞÜRMEZ: dil `tr`'de kalır; kritik metinler `kritik.ts` yedeğinden gelir.
 * - Dil her değiştiğinde `durum.ts` eşzamanlı güncellenir → `apiClient` `X-PEMF-Dil` başlığını doğru taşır.
 * - Çoğul: i18next `Intl.PluralRules` yoksa kendi `dummyRule`'una düşer (`count === 1 ? one : other`) — tr / en kuralıyla aynı; şim YOK.
 * - Test (jest.setup): `globalThis.__PEMF_I18N_KATI__ = true` → eksik anahtar HATA atar (sessizce anahtarı basmaz).
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { kaynaklar } from "./kaynaklar";
import { _etkinDiliAyarla, type Dil } from "./durum";
import { DIL_DEPO_ANAHTARI, cihazYereli, etkinDil, gecerliDil, kayitliDilEszamanli } from "./dil";

export { DIL_DEPO_ANAHTARI, etkinDil, dilSecimiGorunur, bicimYereli, gecerliDil, bayrakAcik } from "./dil";
export type { Dil } from "./durum";

let _baslatmaHatasi: unknown = null;

/** Başlatma hatası (yoksa null) — tanılama ve testler için. */
export function baslatmaHatasi(): unknown {
  return _baslatmaHatasi;
}

const KATI = (globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ === true;

function baslat(): void {
  const ilk: Dil = etkinDil(kayitliDilEszamanli(), cihazYereli());
  _etkinDiliAyarla(ilk);
  try {
    void i18n.use(initReactI18next).init({
      resources: kaynaklar,
      lng: ilk,
      fallbackLng: "tr",
      supportedLngs: ["tr", "en"],
      nonExplicitSupportedLngs: false,
      load: "languageOnly",
      nsSeparator: false,
      keySeparator: ".",
      interpolation: { escapeValue: false },
      react: { useSuspense: false },
      returnNull: false,
      returnEmptyString: false,
      initAsync: false,
      saveMissing: KATI,
      missingKeyHandler: KATI
        ? (_dil: readonly string[], _ns: string, anahtar: string) => {
            throw new Error(`[i18n] katalogda olmayan anahtar: "${anahtar}"`);
          }
        : false,
    });
    i18n.on("languageChanged", (l: string) => {
      _etkinDiliAyarla(gecerliDil(l) ?? "tr");
    });
  } catch (e) {
    _baslatmaHatasi = e;
    _etkinDiliAyarla("tr");
  }
}

baslat();

type Depo = { getItem(k: string): Promise<string | null>; setItem(k: string, v: string): Promise<void> };

/**
 * AsyncStorage TEMBEL yüklenir. ⚠️ Ölçüldü (I18N-0 A2, tam jest): jest kurulumu i18n'i her test dosyasından ÖNCE yükler; AsyncStorage'ı
 * modül düzeyinde içe aktarmak kurulumun sahtesini ÖRNEKLİYOR ve kendi `jest.mock(AsyncStorage, …)` fabrikasını yazan test dosyasının
 * sahtesi artık uygulanmıyordu (`SurumFarkiBanner.test.tsx` kırmızı). Tembel yükleme + test kipinde açılış okumasının atlanması bunu önler.
 */
function varsayilanDepo(): Depo {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const m = require("@react-native-async-storage/async-storage");
  return (m.default ?? m) as Depo;
}

/**
 * Kayıtlı seçimi (AsyncStorage) uygula. Okuma hatası → seçim yok sayılır (cihaz dili / tr). Bayrak kapalıyken her zaman tr.
 * `depo` testte değiştirilebilir.
 */
export async function kayitliDiliUygula(depo: Pick<Depo, "getItem"> = varsayilanDepo()): Promise<Dil> {
  let secim: Dil | null = null;
  try {
    secim = gecerliDil(await depo.getItem(DIL_DEPO_ANAHTARI));
  } catch {
    secim = null;
  }
  const d = etkinDil(secim, cihazYereli());
  try {
    if (i18n.language !== d) await i18n.changeLanguage(d);
  } catch {
    /* başlatma bozuksa dil tr'de kalır */
  }
  _etkinDiliAyarla(d);
  return d;
}

/**
 * Kullanıcı dil seçti (Ayarlar). Bayrak kapalıyken etkin dil yine tr. Seçim cihaza yazılır (hesap / profil DEĞİL); yazılamazsa dil
 * yine değişir ve `{ kaydedildi: false }` döner (çağıran eylem söyleyen iletiyi gösterir).
 */
export async function dilSec(
  istenen: Dil,
  depo: Pick<Depo, "setItem"> = varsayilanDepo(),
): Promise<{ dil: Dil; kaydedildi: boolean }> {
  const d = etkinDil(istenen, null);
  let kaydedildi = true;
  try {
    await depo.setItem(DIL_DEPO_ANAHTARI, d);
  } catch {
    kaydedildi = false;
  }
  try {
    await i18n.changeLanguage(d);
  } catch {
    /* yok say */
  }
  _etkinDiliAyarla(d);
  return { dil: d, kaydedildi };
}

// Yerelde kayıtlı seçim zaman uyumsuz gelir; web'de zaten eşzamanlı okundu (yine de aynı sonucu verir — zararsız).
// Test kipinde (jest kurulumu) ATLANIR: testler başlangıçta tr ister; kayıtlı seçimi deneyen test bunu açıkça çağırır.
if (!KATI) void kayitliDiliUygula();

export default i18n;
