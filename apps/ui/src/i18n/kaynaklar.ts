/**
 * KATALOG KAYNAKLARI — `src/i18n/{tr,en}/<ad-alanı>.json` dosyalarının PAKETE gömülü birleşimi (statik içe aktarma; ağdan yükleme YOK).
 *
 * Kural (KURALLAR.md §Adlandırma): dosya adı = anahtarın ilk parçası (`ayarlar.json` → `t("ayarlar.dil.baslik")`).
 * Yeni ad alanı: `scripts/i18n/katalog.py adalani-ekle <yuzey> <ad>` iki dilin dosyasını açar ve BU dosyayı günceller (elle de olur;
 * K-1 kapısı her `tr/*.json` için burada iki içe aktarma bekler).
 * `enKaynak` `typeof trKaynak` ile türlenir → İngilizcede EKSİK ad alanı / anahtar `npm run typecheck`te kırmızı.
 */
import trAyarlar from "./tr/ayarlar.json";
import trOrtak from "./tr/ortak.json";
import enAyarlar from "./en/ayarlar.json";
import enOrtak from "./en/ortak.json";
import trGuvenlik from "./tr/guvenlik.json";
import enGuvenlik from "./en/guvenlik.json";
import trGiris from "./tr/giris.json";
import enGiris from "./en/giris.json";
import trKabuk from "./tr/kabuk.json";
import enKabuk from "./en/kabuk.json";
import trHesap from "./tr/hesap.json";
import enHesap from "./en/hesap.json";
import trAuthSayfa from "./tr/authSayfa.json";
import enAuthSayfa from "./en/authSayfa.json";
import trBant from "./tr/bant.json";
import enBant from "./en/bant.json";
import trGuncelleme from "./tr/guncelleme.json";
import enGuncelleme from "./en/guncelleme.json";
import trHasta from "./tr/hasta.json";
import enHasta from "./en/hasta.json";
import trKontrol from "./tr/kontrol.json";
import enKontrol from "./en/kontrol.json";
import trSeans from "./tr/seans.json";
import enSeans from "./en/seans.json";
import trAna from "./tr/ana.json";
import enAna from "./en/ana.json";
import trDema from "./tr/dema.json";
import enDema from "./en/dema.json";
import trSensor from "./tr/sensor.json";
import enSensor from "./en/sensor.json";
import trAi from "./tr/ai.json";
import enAi from "./en/ai.json";

export const trKaynak = {
  ayarlar: trAyarlar,
  ortak: trOrtak,
  guvenlik: trGuvenlik,
  giris: trGiris,
  kabuk: trKabuk,
  hesap: trHesap,
  authSayfa: trAuthSayfa,
  bant: trBant,
  guncelleme: trGuncelleme,
  hasta: trHasta,
  kontrol: trKontrol,
  seans: trSeans,
  ana: trAna,
  dema: trDema,
  sensor: trSensor,
  ai: trAi,
};

export const enKaynak: typeof trKaynak = {
  ayarlar: enAyarlar,
  ortak: enOrtak,
  guvenlik: enGuvenlik,
  giris: enGiris,
  kabuk: enKabuk,
  hesap: enHesap,
  authSayfa: enAuthSayfa,
  bant: enBant,
  guncelleme: enGuncelleme,
  hasta: enHasta,
  kontrol: enKontrol,
  seans: enSeans,
  ana: enAna,
  dema: enDema,
  sensor: enSensor,
  ai: enAi,
};

export const kaynaklar = {
  tr: { translation: trKaynak },
  en: { translation: enKaynak },
} as const;
