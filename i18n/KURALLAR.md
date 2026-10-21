# I18N KURALLARI — çok dillilik (TR + EN)

Bu dosya, bu depoda kullanıcıya görünen METİN ekleyen ya da değiştiren HER işin bağlayıcı kılavuzudur (göç partileri `13-I18N-PARTI` ve
sonrası). Sahip kararları Y157–Y161. Kısa özet kökteki `CLAUDE.md`'de. Örnekler I18N-0 pilotlarından (gerçek kod).

## 0. Altın kurallar

1. **Kullanıcıya görünen her metin katalogdan gelir.** Yeni metin = `tr` + `en` anahtarı BİRLİKTE (tek dilde anahtar K-1'de kırmızı).
2. **TÜRKÇE BAYT BAYT AYNI.** Göç bir yeniden yazım değildir; TR değeri kaynaktaki metnin AYNISIDIR — yazım hatası bile. TR değerini ELLE
   YAZMA: `uygula.py` aracın `ham` değerini kopyalar; elle dönüşümde TR, göç ÖNCESİ çıkarıcı parçalarından PROGRAMLA kurulur (I18N-0'da elle
   yazılan bir yedek metin kaynaktan bir ek farklı çıktı — ölçüldü). Düzeltmek istediğin metni `S-I18N-…` önerisi olarak yaz, DEĞİŞTİRME.
3. **Davranış değişmez.** İş mantığı, güvenlik, veri, sayı ayrıştırma, sıralama sonucu, DB değerleri aynen kalır.
4. **İngilizce bayrağı (`I18N_EN_ACIK`) KAPALI** kalır; yalnız `14-I18N-INCELEME` açar (`scripts/i18n/bayrak.py --ac`). Testte
   `__bayrakTestiAyarla(true)` (arayüz / site) serbest; üretim kodu çağırmaz (K-5).
5. **Günlük iletileri (logger / console / eprintln / log_line) Türkçe KALIR** — geliştirici içindir, çevrilmez.
6. **Kararsızsan ÇEVİR.** Görünen bir metnin kaçması fazladan bir anahtardan kötüdür.

## 1. Katalog düzeni ve adlandırma

| yüzey | katalog | çağrı |
|---|---|---|
| arayüz (`apps/ui`) | `src/i18n/{tr,en}/<adAlani>.json` (+ `kaynaklar.ts`) | `const { t } = useTranslation();` → `t("adAlani.x.y")` |
| site (`apps/web`) | `src/i18n/{tr,en}/<adAlani>.json` (+ `kaynaklar.ts`) | aynı (tek tırnak, noktalı virgülsüz — sitenin biçimi) |
| sunucu (`apps/backend`) | `i18n/{tr,en}.json` | `from utils import ceviri` → `ceviri.t("alan.x", ad=deger)` |
| launcher Rust | `launcher/i18n/{tr,en}.json` → `rust.*` | `pemf_launcher_core::dil::t("rust.x")` / `t_ile("rust.x", &[("ad", &deger)])` |
| launcher arayüz | aynı katalog → `ui.*` (ÜRETİLİR: `ui/i18n_katalog.js`) | `index.html`'de `t().anahtar` — `t()` = eski sözlük + katalog (§4.11) |
| NSIS | aynı katalog → `nsis.*` (ÜRETİLİR: `hooks.nsi` LangString bloğu) | `"$(PEMF_<anahtar>)"` |
| DEMA | `dema-terapi-simülatörü/src/i18n/{tr,en}.json` | `t("baslik.uygulama")` (`src/i18n/index.ts`; i18next YOK) |
| auth sayfaları (`apps/ui/auth-pages/*.html`, uygulama DIŞINDA barınır) | arayüz kataloğu `authSayfa.*` → ÜRETİLİR: `auth-pages/i18n_katalog.js` | `data-i18n="authSayfa.x"` / `tf("authSayfa.x")` — HTML'de sabit metin YOK |

- Biçim: i18next JSON v4 — iç içe nesne, `{{ad}}` yer tutucu, çoğul `_one` / `_other` (tr ve en ikisi de). Dosyalar KANONİK (2 boşluk,
  anahtarlar alfabetik, UTF-8, LF): `katalog.py bicimle`.
- Anahtar: ASCII, camelCase parçalar, nokta ayraçlı, anlam bildirir: `ayarlar.hesap.klinik`, `giris.hata.gecersizEposta`, `ortak.iptal`.
  Metnin kendisi anahtar OLMAZ. Türkçe kökler kod tabanıyla aynı (`hasta`, `seans`, `bobin`, `jeton`).
- Ad alanları (arayüz, I18N-0'da açılanlar): `ayarlar`, `giris`, `guvenlik` (ACİL DURDUR ve kritik), `ortak` (Kaydet, İptal, Tekrar Dene… —
  AYNI metin AYNI anlamda birden çok yerde). Partiler ekran / alan bazlı açar (`hasta`, `kontrol`, `seans`, `ai`, `gecmis`, `kpi`, `jeton`,
  `kabuk`, `bildirim`, `hata`): `katalog.py adalani-ekle arayuz <ad>`. Site: `ortak`, `ana`. Sunucu: `hasta`, `pdf`, `ai`, `ayarlar`, `tarih`.
- Aynı TR metin FARKLI anlamda → ayrı anahtar ("Durdur" = seansı durdur ≠ indirmeyi durdur). Aynı anlam → VAR OLAN anahtarı kullan.
- Sunucu katalogunda `{{dil}}` ve `{{anahtar}}` yer tutucusu YASAK (`ceviri.t(anahtar, dil=…)` parametreleriyle çakışır) — `{{dilKodu}}`.
- `{{count}}` YALNIZ çoğul içindir (i18next onu çoğul seçicisi sayar).

## 2. Parti adımları (bir grup)

```
..\python.exe scripts\i18n\kapsam.py durum                                   # sıradaki grup
..\python.exe scripts\i18n\kapsam.py metin-tarayan                           # metin tarayan test listesini tazele (oturum başında)
..\python.exe scripts\i18n\cikar.py --grup <G> --cikti aday.json             # adaylar (dosya / satır / sütun / tür / ham / öneri anahtar)
..\python.exe scripts\i18n\uygula.py sablon aday.json --cikti eslem.json     # eşleme şablonu
#   eslem.json'u DÜZENLE (elle değil, (satır, sütun) → (anahtar, en) eşleme betiğiyle — Türkçe YAZILMAZ):
#     "anahtar" (§1) · "en" · "karar": "cevir" | "muaf" (+ "gerekce") | "elle" (birleşik, §4 ile elle) | "atla" (bu partide değil)
#     "yerAdlari": {"deger1": "hasta"}  — araç yer tutucusuna anlamlı ad (çağrı + katalog birlikte)
#     "cogul": true + "en": {"one": "…", "other": "…"}  — sayıya bağlı metin (yerAdlari ile sayı `count` olur)
..\python.exe scripts\i18n\uygula.py uygula eslem.json --kuru               # önce kuru: ELLE kalacakları gör
..\python.exe scripts\i18n\uygula.py uygula eslem.json                      # basit durumlar dönüşür, tr katalog dolar, muaflar deftere
#   ELLE: reddedilen / "elle" kalanları §4 örnekleriyle dönüştür (TR = göç öncesi `ham` parçalarından PROGRAMLA)
..\python.exe scripts\i18n\katalog.py parca-cikar <yuzey> --eksik-en --aday aday.json --cikti parca1.json
#   parca1.json'daki "en" alanlarını çevir (§6 terim sözlüğü, §7 üslup) — en çok 150 anahtar / parça
..\python.exe scripts\i18n\katalog.py parca-geri-al parca1.json
..\python.exe scripts\i18n\katalog.py bicimle
..\python.exe scripts\i18n\katalog.py esle                                   # K-1 ön denetim
..\python.exe scripts\i18n\katalog.py taban --grup <G> --taban <taban yolu>  # TR gerilemesi: göç öncesi her TR metni katalogda / muaf
..\python.exe scripts\i18n\kapsam.py isaretle <G> tamam                      # AYNI commit'te (kısmi dosya: `kapsam.py dosya <yol> …`)
```
- `uygula` kendiliğinden: `t` kapsamda değilse bileşen gövdesine `const { t } = useTranslation()` + içe aktarma; `useCallback` / `useMemo` /
  `useEffect` içindeki metin çevrilince bağımlılık dizisine `t` (yoksa dil değişince ileti eski dilde kalır — kalıcı jest kapısı denetler);
  dosyanın tırnak / noktalı virgül / satır sonu biçimi. Bileşen / hook DIŞI işlevde (servis / yardımcı) kendiliğinden `i18n.t("…")` + `import i18n from "i18next"` (gösterim anında
  çevirir; metni çizen bileşen `useTranslation()` ile dile abone OLMALI). Reddeder: modül düzeyi, `+` birleştirme, ifadeyle karışık JSX,
  iç içe şablon, GÖLGELEYEN `t` (bileşen içinde) (`.map((t) => …)`), `dil` / `anahtar` yer tutucusu.
- Taban dosyası depo DIŞINDA (`DENETIM\I18N\taban-tr-metinler.json`); sahte evli kafes koşucusunda `--taban` AÇIKÇA verilir.
- Arayüz / site: tür denetimi (`tsc`, anahtar türü). Kapılar §9. Commit kapısına metin tarayan testler (§5).

## 3. Muaf (çevrilmez) — gerekçeyle

Muaf: testID, anahtar / enum / kod değeri, API alan adı, günlük iletisi, kod içi karşılaştırma değeri, kullanıcı girdisi, DB'de saklanan
değerin KENDİSİ (gösterimi değil), yalnız geliştiriciye giden istisna metni ("useToast must be used within ToastProvider"), iç tanılama
(İngilizce "Patient DB not initialized"), çökme raporu etiketleri, dosya yolu, URL.
- Genel (her dosyada): `kapsam.json` → `genelMuaf` (ürün / platform adı, birim, kod belirteci) + `genelMuafDesen` (Tailwind / CSS sınıf adı,
  sınıf ekleyen `{{x}}` dahil). Tek kural yeri: `kapsam.muaf_mi` (K-2 ve `katalog.py taban` aynısını kullanır).
- Dosyanın `muaf` listesine `{"metin", "gerekce"}` (eşlemede `"karar": "muaf"` → `uygula` yazar). Dosya düzeyi muaf
  (`kapsam.py dosya <yol> muaf --gerekce "…"`) yalnız bütün dosya kullanıcıya metin göstermiyorsa (ör. i18n altyapısı).

## 4. Örnek dönüşümler (I18N-0 pilotlarından)

### 4.1 JSX metni / öznitelik (araç)
```tsx
<Text style={styles.cardTitle}>Profil Ayarları</Text>      →  <Text style={styles.cardTitle}>{t("ayarlar.profil.baslik")}</Text>
<TextInput placeholder="E-posta adresi" />               →  <TextInput placeholder={t("giris.alan.eposta")} />
```
Aynı satırdaki boşluk TR değerinde kalır (`"Zaten hesabın var mı? "`); satır sonlu boşluk kaynakta kalır (React kuralı — `cikar` `ham`ı
doğru verir). JSX HTML varlıkları (`&quot;`) React gibi ÇÖZÜLMÜŞ olarak kataloğa girer.

### 4.1b Zengin metin (iç içe kalın / bağlantı) → `<Trans>` (ELLE)
Bir cümlenin içinde ayrı biçimli parça (kalın, bağlantı) varsa parçaları AYRI anahtarlara bölme — tek cümle anahtarı + `<Trans>`:
```tsx
<Text>Cihaz bulunamadı. Telefonunuz cihazla <Text style={styles.bold}>aynı Wi-Fi'de değilse</Text> (mobil veri …) bu normaldir.</Text>
// →  TR değeri: "Cihaz bulunamadı. Telefonunuz cihazla <kalin>aynı Wi-Fi'de değilse</kalin> (mobil veri …) bu normaldir."
<Text><Trans i18nKey="ayarlar.eslestirmeRehberi.bulunamadi" components={{ kalin: <Text style={styles.bold} /> }} /></Text>
```
İngilizce söz dizimine göre `<kalin>` konumu serbesttir. `i18nKey` K-3 / `taban` / `i18n_yardimci` için KULLANIM sayılır (`ortak.ANAHTAR_KULLANIMI`,
jest / vitest `kaynakMetni`). RN'de iç içe `Text` düz metinle AYNI çıktıyı verir (jest'te ölçüldü: `getByText` hem parçayı hem bütün cümleyi bulur).

### 4.2 Şablon → yer tutucu (araç, `yerAdlari` ile)
```tsx
showToast(`Yedek oluşturuldu ve doğrulandı: ${res.yol} (${sayim}).`)   →   showToast(t("ayarlar.yedek.olusturuldu", { yol: res.yol, sayim }))
`${c.patients ?? 0} hasta, …`   →   t("ayarlar.yedek.sayim", { hasta: c.patients ?? 0, … })      // eşlemede "yerAdlari": {"deger1": "hasta"}
```

### 4.3 Birleşik (ifadeyle karışık JSX / `{'\n'}` / `+`) → tek anahtar (ELLE)
```tsx
// önce — dört JSX metni {'\n'} ile
<Text>Cihaz OTOMATİK bağlanır — …{'\n'}📡 Aynı Wi-Fi → …{'\n'}🌐 Farklı ağ → …{'\n'}Aşağısı yalnız …</Text>
// sonra — TR = dört `ham` parçası "\n" ile (React'in çizdiği metin)
<Text>{t("ayarlar.uzakErisim.aciklama")}</Text>
// "Şu anki mod: {…}"  →  {t("ayarlar.profil.suankiMod", { mod: isExpert ? t("ayarlar.profil.modVeteriner") : … })}
```
Koşullu PARÇA ("güncellendi" / "kaydedildi") → İKİ TAM CÜMLE anahtarı (parça birleştirme YOK). Taban karşılaştırması parçayı dosyanın KENDİ
anahtarının TR değerinde arar; başka biçim gerekiyorsa defterde `birlesikIstisna`: `{"once": "<cikar metni>", "sonra": [anahtarlar]}`.

### 4.4 Sayıya bağlı metin → çoğul
```tsx
{retention.pending} seans kaydı {retention.days} günlük süreyle …
// →
{t("ayarlar.saklama.maskeBekleyen", { count: retention.pending, gun: retention.days })}
// tr _one / _other: "{{count}} seans kaydı {{gun}} günlük süreyle …"  (Türkçe tekil/çoğul ayırmaz — ikisi aynı)
// en _one: "{{count}} session record is …" · _other: "{{count}} session records are …"
```

### 4.5 Modül düzeyi sabit / varsayılan argüman → anahtar saklanır, gösterimde çevrilir (`const X = t(…)` YASAK)
```ts
// site config.ts — ANAHTAR saklar
export const NAV = [{ anahtar: 'ortak.nav.ozellikler', to: '/features' }, …] as const
{NAV.map((n) => <Link …>{t(n.anahtar)}</Link>)}             // dinamik anahtar → K-3 izin listesi (kapalı küme)
```
```python
# PDF başlığı — varsayılan argüman TANIM anında değerlendirilir (dil içe aktarmada donar)
def _add_header(self, story, baslik: str | None = None, alt_baslik: str | None = None):
    if baslik is None:
        baslik = ceviri.t("pdf.baslik.varsayilan")          # "" hâlâ "yazma" demektir
```
React DIŞI kod (servis / yardımcı) `i18n.t`'yi ÇAĞRI anında çağırır (`platformConfirm(…, confirmLabel = i18n.t("ortak.onayla"))`); metni çizen
bileşen `useTranslation()` ile dile abone olmalı.

### 4.6 Sınıf bileşeni
```tsx
class ErrorBoundaryIc extends React.Component<{ children: React.ReactNode } & WithTranslation, State> {
  render() { const { t } = this.props; … t("ortak.hata.beklenmeyen") … }
}
export const ErrorBoundary = withTranslation()(ErrorBoundaryIc);
```

### 4.7 Saklanan Türkçe değer → gösterimde değer → anahtar (VERİ DEĞİŞMEZ, göç YOK)
```ts
const DURUM_ANAHTARI: Record<string, string> = { completed: "gecmis.durum.tamamlandi", stopped: "gecmis.durum.durduruldu" };
const goster = (v: string) => (DURUM_ANAHTARI[v] ? t(DURUM_ANAHTARI[v]) : v);   // eşlemesiz değer / kullanıcı girdisi aynen
```
AI etiketleri (K-7): tablo kimlik → anahtar eşlemesi (`DETAIL_LABELS = { detected: "ai.etiket.detected", … }`), değerler katalogda; sunucu
`ai_rapor_ogeleri` aynı desen; ortak kimlikte farklılık `i18n/ai-etiket-farklari.json`'da gerekçeli. Bilinmeyen etiket HAM gösterilmez.
DEMA `Waveform = 'Sinüs' | …` gibi GÖRÜNEN metni değer olarak kullanan tür → kimlik (`sinus`) + katalog etiketi.

### 4.8 Sunucu iletisi
```python
raise HTTPException(status_code=404, detail="Hasta bulunamadı — zaten silinmiş olabilir; listeyi yenileyin.")
# →
raise HTTPException(status_code=404, detail=ceviri.t("hasta.hata.bulunamadi"))
```
Dil isteğin `X-PEMF-Dil` başlığından (ara katman); başlıksız = tr (eski APK); `Accept-Language` YOK SAYILIR; istek dışında cihaz dili.
Arayüz sunucu METNİNE göre DALLANMAZ: makine-okur alan (`kod`, `X-PEMF-Jeton-Sebep` deseni) eklenir; metin eşleşmesi yalnız eski sunucu
geri uyumu için kalır. ⚠️ Yalnız stdlib kullanan YAPRAK modüller (`utils/klinik_asgari.py`, `image_domain`, `ses_kalitesi` — AI Docker
imajına tek satırla girer) `utils.ceviri` İÇE AKTARMAZ: metin `kod` döner, çağıran yönlendirici çevirir.

### 4.9 WS olayı
```python
_push_notification(ceviri.t("bildirim.bobinDurdu", dil="tr", cid=cid), "warning", kod="bildirim.bobinDurdu", parametreler={"cid": cid})
```
`kod` + `parametreler` EK alan; `message` geri uyum için KALIR (eski APK). Arayüz `kod` varsa `t(kod, parametreler)` gösterir.

### 4.10 PDF
Rapor dili = isteğin dili; başlık / bilgi / altbilgi `ceviri.t` (pilot: `pdf.*`). Var olan SAYISAL tarih biçimi (`%d/%m/%Y %H:%M`) dil
bağımsızdır ve KALIR (TR birebir); ay adlı YENİ metin `ceviri.tarih_metni` (TR "13 Ekim 2026, 19:45" · EN "13 Oct 2026, 19:45"). TR
raporda İngilizce, EN raporda Türkçe sözcük KALMAZ (kullanıcı girdisi hariç) — `tests/test_i18n_pilot_sunucu.py` deseni.

### 4.11 Launcher
```rust
return Err("Uygulama kurulu değil — önce profil seçip kurun.".to_string());
// →
return Err(pemf_launcher_core::dil::t("rust.hata.uygulamaKuruluDegil"));
```
Arayüz (`index.html`): VAR OLAN `I18N = { tr, en }` sözlüğündeki anahtar DEĞERLERİYLE (TR ve EN aynen — yayındaki İngilizce) kataloğa
`ui.*` taşınır ve sözlükten SİLİNİR (iki kaynak olmasın); `t()` = sözlük + `window.PEMF_I18N_KATALOG` (üretilmiş). İşlev değerli
anahtarlar (10) elle şablona çevrilir. Metne göre DALLANAN Rust iletileri ("İnternet bağlantısı yok", "parola hatalı") önce makine-okur
koda geçer, sonra göçer. `scripts/i18n/launcher_uret.py` `i18n_katalog.js` + `hooks.nsi` bloğunu üretir (K-1 eşliği denetler).

### 4.12 NSIS
`hooks.nsi`'de metin YOK: `DetailPrint "$(PEMF_estopDogrulandi)"`. Metin `launcher/i18n/{tr,en}.json → nsis.*`. NSIS değişkenleri (`$1`,
`$INSTDIR`) ve kaçışlar (`$\r$\n`) değerin İÇİNDE, iki dilde AYNI değişken kümesi (K-1).

### 4.13 Site / Vercel / yasal
Arayüzle aynı (`useTranslation`). Vercel işlevleri (`apps/web/api`) metni ÇEVİRMEZ: yanıt makine-okur `error` kodu taşır, istemci koddan
gösterir, `message` Türkçe yedek kalır (S-I18N.5). Yasal metinler en SON grup; EN sayfada "Türkçe metin bağlayıcıdır" notu, hukuki onay sahipte.

### 4.13b Auth sayfaları (şifre sıfırlama / e-posta onayı)
Uygulamanın dışında (GitHub Pages) barınan statik sayfalar i18next'e erişemez: metin `authSayfa.*` kataloğundan `scripts/i18n/auth_uret.py` ile
`i18n_katalog.js`'e ÜRETİLİR (elle düzenlenmez; `bayrak.py --ac|--kapat` birlikte üretir, `--denetle` ayrışmayı yakalar). HTML'de metin YOK:
`<h1 data-i18n="authSayfa.reset.baslik"></h1>`, `data-i18n-html` (yalnız `<b>` gibi yazı biçimi), `data-i18n-placeholder`; betikte `tf("…")`.
Bayrak KAPALIYKEN sayfa tarayıcı dili ne olursa olsun Türkçedir. Dağıtım (sahibin elle yaptığı GitHub Pages kopyası) `i18n_katalog.js`'i de
kopyalamalıdır — yoksa sayfa metinsiz açılır. Kapı: `tests/test_i18n_auth_sayfa.py`.

### 4.14 DEMA
`src/i18n/index.ts` (i18next YOK): sayfa dili `?dil=` > tarayıcı dili; uygulama çerçeveyi `dilParametresiEkle` ile açar. D1.91 kapısı
kataloğu da tarar (yasaklı iddia kataloğa kaçamaz); İngilizce katalog da "cihaz davranışını temsil etmez" etiketinin karşılığını taşır.

## 5. Metin tarayan kapıları dönüştürme (pytest + jest + vitest)

Değişen her dosya ve taşınan her metin için: `grep "<dosya yolu>" i18n/metin-tarayan-testler.txt` + `grep -l "<metnin ayırt edici
parçası>" tests/*.py` + jest / vitest'te kaynağı okuyanlar (`readFileSync(...tsx)`, `?raw`). Kırmızıları ÇEVİR, SİLME / GEVŞETME:
```python
assert "bağlantı yok" in _oku(_GES)                                        # önce
iy.metin_kapisi(GES, "guvenlik.acilDurdur.dugmeBaglantiYok",               # sonra — anahtar kullanılıyor + TR BİREBİR + EN dolu
                "🚨 ACİL DURDUR (bağlantı yok)")
assert iy.gorunen_metin_var(DOSYA, "…")                                    # gevşek biçim (düz metin YA DA anahtarın TR'si)
```
```ts
// jest (apps/ui/src/i18n/__tests__/kaynakMetni.ts) · vitest (apps/web/src/__tests__/_kaynakMetni.ts)
expect(SRC).toMatch(/isExpert && \(\s*<>\s*<Text style=\{styles\.label\}>\{t\("ayarlar\.hesap\.klinik"\)\}/)  // yapı anahtarda
expect(TR["ayarlar.hesap.klinik"]).toBe("Klinik / Muayenehane")                                             // TR birebir
expect(gorunenMetinler(SRC)).toContain("Üniversite / Kurum")
```
Her çevrilen kapıya İKİ mutant: (1) TR değeri değişti → kırmızı; (2) `t()` çağrısı / anahtar değişti → kırmızı. Mutant TEST İÇİNDE kırmızı
olmalı — modül düzeyinde `expect` paket çöküşüdür ("0 test"), koşucu onu kırmızı SAYMAZ.

## 6. Terim sözlüğü (K-4) — `i18n/terimler.json`, okunur: `DENETIM\I18N\TERIMLER.md`

Seans → Session (treatment / therapy YOK; TR'de "tedavi / terapi" geçiyorsa serbest) · Acil Durdur → EMERGENCY STOP (düğme) / Emergency stop ·
Bobin → Coil · Alan şiddeti → Field strength · Hasta → Patient · Hayvan sahibi → Owner · Hekim → Veterinarian (dar alanda vet) · Seans
Geçmişi → Session History · Jeton → Credit (token YOK) · Kullandıkça öde → Pay as you go · Araştırma modu → Research mode · Veteriner modu →
Veterinary mode · Termal → Thermal · Segmentasyon → Segmentation · Ana Ekran → Home · ürün adları (PEMF Vet, AI Pro, DEMA, FGS) çevrilmez.
Gerekçeli istisna: `terimler.json → istisnalar` (ör. "Pulsed Electromagnetic Field Therapy" PEMF açılımı).

## 7. Üslup (EN)

ABD İngilizcesi; sade ve kısa (okuyucu veteriner / hayvan sahibi); düğmede cümle düzeni ("Sign in", "Start session"); TR'deki BÜYÜK harf
vurgusu EN'de de büyük; hata iletisi EYLEM söyler; düğme gerçeği söyler. Emin olmadığın tıbbi terimde uydurma → yerleşik karşılık + rapora
`[İNCELE]`. Çevrilmiş metne `toUpperCase` / `toLowerCase` UYGULANMAZ (Türkçe I / İ). Sıralama `localeCompare(dil)`. Gösterim biçimi dile
göre (`bicimYereli(dil)`: tr-TR / en-GB); SAYI GİRİŞİNİN ayrıştırması DEĞİŞMEZ (T9 kilidi: `CoilParameterPanel.I18N0.sayiGirisiDildenBagimsiz`).

## 8. Güvenlik metinleri (KRİTİK) — `i18n/kritik-anahtarlar.json`

ACİL DURDUR / STOP, seans başlat / durdur, bobin ve alan uyarıları, firmware bantları (`FW-PAKET`, `FW-KIMLIK`), donanım hata / onay iletileri.
- ACİL DURDUR çeviri sisteminden BAĞIMSIZ: `kritikMetin()` + `useKritikDil()` (`apps/ui/src/i18n/kritik.ts`), sabit iki dilli `KRITIK_YEDEK`
  (katalogla AYNI — K-5; katalogdan üretilir); react-i18next / Suspense KULLANILMAZ. Ternary içinde anahtar değil, dal başına sabit anahtar
  (`kartReddetti ? kritikMetin("…kartRedBaslik") : kritikMetin("…teyitsizBaslik")` — K-3 dinamik saymaz).
- `bekleyen` listesi (354 metin): kritik grubun dosyası `tamam` olunca her bekleyen metin ya listedeki bir anahtarın TR değeri ya gerekçeli muaf
  (K-5). Parti kritik metni taşırken anahtarını `anahtarlar`'a ekler. `services/emergencyStop.ts` sabitleri (`EMERGENCY_STOP_*`) aynı
  `guvenlik.acilDurdur.*` anahtarlarına geçer (çağıranlar: `useSessionControl`, `useTeardownGuard`); geçene dek TR eşliği jest'te kilitli.
- `useTeardownGuard` cümlesi (`${actionLabel} tüm durdurma kontrollerini …`) `{{eylem}}` şablonuna geçer; eylem adları cümle başı biçimdedir
  (EN "Changing the profile").
- Anlam birebir: yumuşatma, kısaltma, eksik uyarı YOK. Her kritik anahtar için iki dilde jest testi + kum havuzunda TR + EN ekran görüntüsü.
- Sunucu METNİNE göre dallanma YASAK (kritik yolda özellikle): arayüz sunucunun metnini kalıp eşleştirmeyle yorumlamaz; sunucu makine-okur alan EKLER
  (örn. `estop_mandali.durum()["eylemSifirlaSoyler"]`), arayüz önce ona bakar, yoksa (eski sunucu) eski eşleşmeye düşer. ACİL DURDUR yazıları ve
  `kritikMetin()` kullanan her yer `useKritikDil()` ile dile abone olur; `EMERGENCY_STOP_*`-türü sabit YOK (metin tek yerde, katalogda + KRITIK_YEDEK).

## 9. Kapılar

K-1 eşlik (`test_i18n_esle_K1.py`) · K-2 sabit metin yasağı (`test_i18n_sabit_metin_K2.py` + jest `sabitMetinYasagi.test.ts` — kanca
bağımlılığı kuralı da orada) · K-3 kullanılan anahtar katalogda + dinamik anahtar izin listesi (`test_i18n_anahtar_K3.py`,
`i18n/dinamik-anahtarlar.json`) · K-4 terim (`test_i18n_terim_K4.py`) · K-5 kritik + bayrak + bekleyen (`test_i18n_kritik_K5.py`) · K-6 paket
(`test_i18n_paket_K6.py`) · K-7 AI etiket eşliği (`test_i18n_ai_etiket_K7.py`) · araçlar (`test_i18n_araclar.py`,
`test_i18n_parti_araclari.py`) · yardımcı (`test_i18n_yardimci.py`) · altyapı (`test_i18n_sunucu_altyapi.py`, `test_i18n_launcher_altyapi.py`,
`test_i18n_dema_altyapi.py`, `test_i18n_auth_sayfa.py`) · mandal bandı makine-okur alanı (`test_i18n_estop_mandali_eylem_kodu.py`) · ACİL DURDUR yazıları HER bileşende `kritikMetin` + `useKritikDil` (`test_i18n_acil_durdur_kritik_desen_her_yerde.py`) · pilot (`test_i18n_pilot_sunucu.py`) · TR gerilemesi (`test_i18n_tr_taban.py`; taban depo dışında → `PEMF_I18N_TABAN` / `varsayilan_taban()`, yoksa atlar). Arayüz jest: `src/i18n/__tests__`, site vitest: `src/i18n/__tests__`.

## 10. Sık hatalar (ÖLÇÜLMÜŞ — I18N-0)

- TR değerini elle yazmak → kaynaktan farklı (ACİL DURDUR gövdesinde bir ek). TR'yi `ham`dan / parçalardan PROGRAMLA kur.
- `t` adlı parametre (`.map((t) => …)`, `onChange={(t) => …}`) çevirmeni gölgeler → araç reddeder; değişkeni yeniden adlandır.
- `useCallback` / `useMemo` / `useEffect` bağımlılığında `t` unutulursa ileti dil değişince ESKİ dilde kalır (araç ekler, jest kapısı yakalar).
- Python varsayılan argümanı ve modül / sınıf gövdesi içe aktarmada değerlendirilir → `ceviri.t` orada YASAK (araç modül düzeyi sayar).
- Python 3.10: çok satırlı f-string içi ifade konumları yanlış (araç `ast.unparse` kullanır); f-string iç sabitleri f-string'in konumunu taşır.
- autocrlf: çalışma kopyası CRLF; eklenen satır dosyanın satır sonunu izlemeli. Yalnız satır sonu farkı olan dosya git'te değişiklik
  DEĞİLDİR (commit listesinden düşer).
- i18next `init({resources})` nesnesini KOPYALAMADAN tutar: testte `removeResourceBundle` dışa aktarılan `kaynaklar`'ı da siler.
- jest kurulumu i18n'i her test dosyasından ÖNCE yükler: i18n katmanına modül düzeyinde YENİ içe aktarma ekleme (tembel `require`).
- node ≥ 21: `globalThis.navigator` salt-okur — testte `Object.defineProperty` (düz atama sessizce düşer, makinenin tr-TR yereli sızar).
- `<html lang>` / `lang` özniteliğini DEĞİŞTİRME: CSS `text-transform: uppercase` dile göre büyütür — DEMA'da `lang="tr"` yapmak
  "KARE SINYALI"yi "KARE SİNYALİ" yaptı (TR görünümü değişti; A12 ekran farkıyla ölçüldü, geri alındı). Göç öncesi değer korunur;
  Türkçe büyük harf düzeltmesi ayrı bir SAHİP kararıdır. Metin aynı kalsa da görünüm değişebilir → TR ekranını göç öncesiyle KARŞILAŞTIR.
- Kaynak tarayan kapı dizgiyi YORUMDA da bulur; `//.*`'ı `re.S` ile koşmak DOSYA SONUNA kadar yutar → blok / satır yorumunu ayrı soy, ya da AST.
- gitleaks `generic-api-key`: tanımlayıcı / grup adında `api` parçası kullanma (`sunucu-10b-ana-sunucu`); muafiyet genişletme, `--no-verify` YOK.
- Bash heredoc ters bölüyü bozar → JSON / betik / commit iletisi Write ile yazılır.
- Elle depo kökü çıpası (`Path(__file__).parents[N]`) yasak → `utils.path_utils.kaynak_kokunu_bul` (var olan kapı yakalar).

## 11. Büyük dosya, kısmi dosya, bayrak

- Tek dosyalı büyük gruplar (AiHubScreen ~770, launcher `index.html` ~420, `Legal.tsx` ~250, `aiDetail.ts` ~220): bölüm bölüm, birden çok
  commit; dosya EN SONDA `tamam` (yarım dosya `bekliyor` + defter notu). KESİNTİ'de `kapsam.py durum` + `git log` nerede kalındığını söyler.
- `tamam` yalnız dosyada kullanıcıya görünen sabit metin kalmadığında (K-2 denetler). Pilotun kısmi dosyaları (PDF, ai_router, launcher,
  site Home / NotFound / config, apiClient) defter notunda.
- Bayrak: `bayrak.py --ac` (yalnız `14-I18N-INCELEME`) üç TS sabiti + Rust sabiti + NSIS dil listesi + LangString bloğunu birlikte açar;
  `--kapat` BAYT BAYT geri getirir; `--denetle` (K-5) ayrışmayı yakalar.
