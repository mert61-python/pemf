// Author: mertaygn, cglrgrkn
import { serviceConfig } from "@/services/config";
import { Alert, Platform } from "react-native";
import { emitToast } from "@/services/toastBridge";
import { uygulamaIciOnay } from "@/services/onayKoprusu";
import { etkinDilDegeri } from "@/i18n/durum";
import i18n from "i18next";
import { isCleartextAllowed, isPrivateHost } from "@/services/duzHttpKapisi";
// D3.39: düz-HTTP kapısı tek kaynak `duzHttpKapisi` — eski içe aktaranlar için buradan da dışa aktarılır.
export {
  GuvensizBaglantiHatasi,
  guvensizBaglantiBildir,
  ipv4Oktetleri,
  isCleartextAllowed,
  isPrivateHost,
  korunanFetch,
  soketAdresiGuvenliMi,
} from "@/services/duzHttpKapisi";

/** Web-güvenli uyarı — Alert.alert web'de no-op. YH-A4: web'de önce UYGULAMA İÇİ pencere (`onayKoprusu`; tarayıcı yerlisi
 *  "127.0.0.1:8000 şunu diyor:" başlığı yok); sağlayıcı takılı değilse window.alert'e düşer. */
export function platformAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    if (uygulamaIciOnay({ baslik: title, govde: message, tur: "uyari" })) return;
    if (typeof window !== "undefined") window.alert(`${title}\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}

/** Web-güvenli onay diyaloğu — Alert.alert çoklu-buton web'de tetiklenmez. YH-A4: web'de önce UYGULAMA İÇİ pencere (İptal /
 *  Esc → false); sağlayıcı takılı değilse window.confirm'e düşer (onay hiçbir yolda sessizce "evet" sayılmaz). */
export function platformConfirm(title: string, message: string, confirmLabel: string = i18n.t("ortak.onayla")): Promise<boolean> {
  if (Platform.OS === "web") {
    const icte = uygulamaIciOnay({ baslik: title, govde: message, onayEtiketi: confirmLabel, tur: "onay" });
    if (icte) return icte;
    return Promise.resolve(typeof window !== "undefined" ? window.confirm(`${title}\n\n${message}`) : false);
  }
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: i18n.t("ortak.iptal"), style: "cancel", onPress: () => resolve(false) },
      { text: confirmLabel, style: "destructive", onPress: () => resolve(true) },
    ]);
  });
}

function showError(title: string, message: string) {
  // F-6: önce non-blocking toast (medikal konsolda bloklayan window.alert kötü UX); ToastProvider
  // kayıtlı değilse (mount öncesi / native provider'sız) bloklayan alert'e fallback. platformConfirm
  // (yıkıcı-onay) DEĞİŞMEDİ — native dialog doğru.
  if (!emitToast(`${title}: ${message}`, "error")) platformAlert(title, message);
}

/** Jeton 402'sinin ret sebebi (backend `servers/jeton.py::JETON_SEBEP_BASLIGI`; CORS `expose_headers`'ta):
 *  yetersiz · borc_tavani · cevrimdisi · kimlik_yok. */
export const JETON_SEBEP_BASLIGI = "X-PEMF-Jeton-Sebep";

/** 402 penceresinin başlığı — S-4B.5 (sahip kararı 2026-10-19): ücretlendirme açıkken internetsiz AI analizi yapılmaz; bu ret
 *  "jeton bitti" DEĞİL, "internet yok"tur ve öyle söylenmeli (kullanıcı jeton almaya kalkmasın). Başlık okunamazsa (eski backend /
 *  CORS) "Jeton hakkı" kalır — `detail` metni yine nedeni söyler. */
export function jetonRedBasligi(sebep: string | null | undefined): string {
  return sebep === "cevrimdisi" ? i18n.t("ortak.hata.internetGerekli") : i18n.t("ortak.hata.jetonHakki");
}

/** İstek opsiyonları — `silent: true` arka-plan poll'lerinde hata pop-up'ını bastırır. */
export interface ApiOpts {
  silent?: boolean;
  /** ⚠️ C2-4.3 (2-C incelemesi · Y87 ilkesi): bu istek için operatör jetonu — modül düzeyindeki ŞU ANKİ jeton yerine. Uzun
   *  süren bir iş (AI analizi) BAŞLADIĞI andaki hekimin adına kaydedilsin diye; uçuşta "Geçiş yap" ile başka hekime geçilince
   *  kayıt eskiden yeni hekime imzalanıyordu. `null` → jetonsuz. Alan verilmezse davranış AYNI. Güvenli taban kapısı aynen.
   *  Yalnız `apiPost`ta uygulanır. */
  operatorJetonu?: string | null;
  /** HTTP hata durumunda (response.ok=false) durum kodunu bildirir.
   *
   *  NEDEN: `apiPost` hata halinde `fallback` döner ve durum kodunu YUTAR. Bazı uçlarda kodun
   *  KENDİSİ anlamlıdır — operatör PIN doğrulamasında 401 "PIN hatalı", 423 "kilitlendi" demek
   *  ve kullanıcıya bambaşka mesaj gösterilmeli (kilitliyken "PIN hatalı" demek, kullanıcıyı
   *  boşuna denemeye devam ettirir). EKLEMELİ ve opsiyonel: mevcut çağıranlar etkilenmez.
   *
   *  ⚠️ 2026-08-09 EKLEME — `detail`: sunucunun GEREKÇESİ. Bazı reddedişlerde durum kodu tek
   *  başına yetmez; kullanıcının NE YAPACAĞINI bilmesi gerekir. Somut olay: tıbbi kayıt DB'si
   *  açılamadığında `/api/session/start` 503 + "veritabanı açılamadı, seans başlatılamaz" döner,
   *  ama istemci bunu yutup genel "Sunucuya veri gönderilirken bir hata oluştu" gösteriyordu →
   *  veteriner hasta masadayken sebebi ANLAYAMIYORDU. Argüman EKLEMELİ: mevcut çağıranlar
   *  (tek parametreli lambda'lar) etkilenmez.
   */
  onHttpError?: (status: number, detail?: string, govde?: unknown) => void;
  /** Bu istek için zaman aşımı (ms). Verilmezse REQUEST_TIMEOUT_MS (8sn).
   *
   *  NEDEN GEREKLİ: 8sn, kontrol/telemetri uçları için doğru ama AI ÇIKARIMI için çok kısa.
   *  Modeller GECİKMELİ yüklenir (`_get_or_load_model`) → İLK çağrı modeli diskten açar, bazıları
   *  ayrıca numba/librosa JIT derlemesi yapar. Bu makinede ÖLÇÜLDÜ (2026-08-06, soğuk backend):
   *      /ai/disease    ilk 3.2 sn   → sonraki 0.01 sn
   *      /ai/sound/cat  ilk 28.0 sn  → sonraki 0.06 sn
   *  8sn sınırı, ilk çağrıyı sessizce iptal ediyordu (aşağıdaki AbortError yolu) → kullanıcı
   *  "analiz boş döndü" görüyor, ikinci denemede model artık yüklü olduğu için ANINDA çalışıyor.
   *  AI çağrıları için AI_TIMEOUT_MS kullanın. */
  timeoutMs?: number;
  /** Zaman aşımında gösterilecek metin (yalnız `apiPost`; verilmezse varsayılan "Tekrar deneyin — model yüklemesi" metni).
   *
   *  ⚠️ D2.E03 (Y84): varsayılan metin AI çıkarımı içindir; yedek alma / geri yüklemede "Tekrar deneyin" demek kayıtları
   *  ÇOĞALTIYORDU (ikinci istek ilk geri yükleme sürerken). Çağıran işine uygun metni verir (`services/veriTasima.ts`).
   *  EKLEMELİ: mevcut çağıranlar etkilenmez. */
  zamanAsimiMesaji?: string;
  /** Bağlantı reddi / kopmasında (fetch reddi — zaman aşımı DEĞİL) gösterilecek metin (yalnız `apiPost`). Verilmezse bugünkü gibi
   *  tost YOK (global "Çevrimdışı" göstergesine bırakılır).
   *
   *  ⚠️ D2-3.5 (2-D incelemesi): uzun yedek alma / geri yüklemede bağlantı koparsa işlem cihazda sürüyor olabilir; ekran HİÇBİR şey
   *  söylemiyordu (Y84 zaman aşımı metninin ikizi yoktu). EKLEMELİ: mevcut çağıranlar etkilenmez. */
  agHatasiMesaji?: string;
  /** ⚠️ D3I-A1.3 · Ö.4-Y8: YALNIZ durdurma çağrıları (ACİL DURDUR yedekleri, `stop_all_coils`, seans / bobin Durdur) — düz-HTTP
   *  kapısına BAĞLANMAZ (yalnız `apiPost`). Eskiden genel `http://` tabanında ACİL DURDUR 4 yerine 1 istek, Durdur 0 istek
   *  gönderiyordu. Başlıklar AYNI (`authHeaders`: Bearer / operatör jetonu güvenli taban kapısında kalır). Kullanım yerleri
   *  kapıda sabit: `acilDurdur.Y8.duzHttp.D3I.test.tsx`. */
  durdurma?: boolean;
}

/** AI çıkarım uçları için zaman aşımı — ilk çağrıdaki model yükleme + JIT derlemesini kapsar. */
export const AI_TIMEOUT_MS = 120000;

/** KD madde 0 (sahip 2026-11-10: "istemcideki 8 saniye sınırını kaldıralım, kamera bağlı değil zanneder kullanıcı"): kabin kamerası
 *  uçları (tarama) genel 8 sn sınırına BAĞLI DEĞİL. ÖLÇÜLDÜ: donanım dönüşümleri açıkken bir kamera 8–9 sn'de açılıp çözünürlük isteği
 *  15–24 sn sürüyordu (tarama 25 sn); sunucu düzeltmesiyle ~2 sn — üst sınır yalnız ASILI isteğe karşı (AI uçlarıyla aynı). */
export const KAMERA_TIMEOUT_MS = 120000;

/** SAHA HATASI 2026-08-12 — "signal is aborted" kullanıcıya GÖSTERİLİYORDU.
 *
 * Ev kullanıcısı fps + hastalık + ses analizlerini PEŞ PEŞE başlattı; ilk ikisi döndü, ses
 * `AbortError: signal is aborted without reason` verdi. Hemen ardından tek başına denediğinde
 * ANINDA sonuçlandı. Sebep: `cat_sound` ilk çağrıda numba/librosa JIT derler (ölçüm: tek
 * başına 28 sn) ve üç analizin CPU çekişmesinde o elle yazılmış 60 sn'lik sınırı aşıyordu.
 *
 * İki ayrı kusur vardı ve ikisi de burada kapanıyor:
 *   • Sınır tek kaynaktan gelmiyordu → 10 çağrı `AI_TIMEOUT_MS`e bağlandı.
 *   • İptal mesajı ham DOM metniydi. Zaman aşımı ile ağ hatası AYRI şeylerdir: ilkinde
 *     tekrar denemek İŞE YARAR (model artık bellekte), ikincisinde yaramaz.
 */
export const aiZamanAsimiMesaji = (): string => i18n.t("ortak.hata.aiZamanAsimi");

/** SAHA 2026-09-08 (masaüstü): her `fetch` reddi "Ağ veya sunucu hatası." diye gösteriliyordu.
 *  Gerçek sebep backend'e HİÇ ulaşmayan bir istekti (tarayıcı CSP ile `fetch(blob:)`'u kesti);
 *  kullanıcı "internet yok diye çalışmıyor" sandı, günlükte iz yoktu. Tarayıcının fetch reddi
 *  (`TypeError: Failed to fetch` / RN `Network request failed`) sunucu hatasından AYRI bir sınıftır:
 *  istek gönderilememiştir → eylem: bağlantı göstergesi + dosyayı yeniden seçme + yeniden başlatma. */
export const aiIstekGonderilemediMesaji = (): string => i18n.t("ortak.hata.aiGonderilemedi");

/** `response.json()` JSON olmayan gövdede düşer (vekil/portal sayfası, kesik yanıt). */
export const aiGecersizYanitMesaji = (): string => i18n.t("ortak.hata.aiGecersizYanit");

const _FETCH_REDDI = /failed to fetch|network request failed|networkerror|load failed/i;

/** AI isteği `catch`inden kullanıcıya gösterilecek TEK mesaj kaynağı (eylem söyler, ham metin
 *  göstermez). `varsayilan` çağıranın bağlamına özel metnidir; yalnız sınıflandırılamayan
 *  hatalarda kullanılır. */
export function aiHataMesaji(e: unknown, varsayilan = i18n.t("ortak.hata.agSunucu")): string {
  // `AbortController.abort()` → DOMException(name: "AbortError"). `instanceof DOMException`
  // React Native'de güvenilir DEĞİL (DOM yok) → ada bakılır; tarayıcı ve RN'de de aynı.
  const ad = (e as { name?: string } | null)?.name;
  const mesaj = String((e as { message?: unknown } | null)?.message ?? "");
  if (ad === "AbortError" || ad === "TimeoutError") return aiZamanAsimiMesaji();
  if (ad === "TypeError" && _FETCH_REDDI.test(mesaj)) return aiIstekGonderilemediMesaji();
  if (ad === "SyntaxError") return aiGecersizYanitMesaji();
  return varsayilan;
}

// Entitlement (abonelik tier/eklenti) header'ları — EntitlementContext günceller; backend
// tier-enforcement (PEMF_TIER_ENFORCED) AÇIKKEN kullanılır. Kapalıyken backend yok sayar (zararsız).
let _entitlementHeaders: Record<string, string> = {};
export function setEntitlementHeaders(tier: string | null, addons: string[] = []): void {
  _entitlementHeaders = tier ? { "X-PEMF-Tier": tier, "X-PEMF-Addons": addons.join(",") } : {};
}

/**
 * OPERATÖR JETONU (2026-08-09 denetimi, Tier 1) — kaydın SAHİBİ.
 *
 * PIN doğrulanınca backend kısa ömürlü bir jeton verir; yazma yollarında `operator_email`
 * gövdedeki beyandan DEĞİL bu jetondan türetilir. Eskiden beyan doğrudan yazılıyordu → cihaza
 * erişen herkes başka bir hekimin adına seans/AI/hasta kaydı açabiliyordu.
 *
 * ⚠️ `isSafeBackendBase` kapısına TABİDİR: Bearer ile aynı gerekçe — keşfedilen/zehirlenmiş bir
 * host'a operatör kimliğini teslim etmeyiz.
 */
let _operatorToken: string | null = null;
export function setOperatorToken(token: string | null): void {
  _operatorToken = token || null;
}

/**
 * ETKİN ARAYÜZ PROFİLİ (SG.G1 / G2, sahip gözlemi 2026-10-13: "raporlar seans geçmişi vs de ayrılmalı profillere göre").
 *
 * `UserModeContext.setUserMode` günceller (profil KALICI DEĞİL — yalnız bellekte). Backend liste / rapor / KPI uçları
 * `X-PEMF-Profil` VARSA o profilin kayıtlarını döndürür ve yeni kaydı profiliyle yazar (`apps/backend/utils/profil.py`);
 * başlıksız (eski) istemci bugünkü gibi süzgeçsiz görür. ERİŞİM KAPISI DEĞİL (profiller herkese açık) — kimlik / sır taşımaz,
 * bu yüzden güvenli-taban kapısına bağlı değildir.
 */
export const PROFIL_BASLIGI = "X-PEMF-Profil";
let _profilBasligi: string | null = null;
export function setProfilBasligi(profil: string | null): void {
  _profilBasligi = profil || null;
}

/**
 * ARAYÜZ DİLİ (I18N · Y157–Y161): `X-PEMF-Dil: tr|en` HER istekte — sunucu iletileri, PDF ve AI metinleri bu dilde döner
 * (`apps/backend/utils/ceviri.py`). Değer `i18n/durum.ts`'ten (i18n katmanı dil değişiminde EŞZAMANLI günceller; ayrı modül → içe
 * aktarma döngüsü yok). ⚠️ `Accept-Language` KULLANILMAZ: WebView2 / tarayıcı onu işletim sistemi dilinden kendisi doldurur; İngilizce
 * Windows'ta Türkçe seçili arayüze İngilizce yanıt dönerdi. Başlıksız eski istemci (yayındaki APK) = tr. Kimlik / sır TAŞIMAZ.
 */
export const DIL_BASLIGI = "X-PEMF-Dil";

/** `authHeaders()` + (verildiyse) isteğe özgü operatör jetonu (C2-4.3 — işin BAŞLADIĞI andaki hekim; bkz. `ApiOpts.operatorJetonu`). */
function _istekBasliklari(opts?: ApiOpts): Record<string, string> {
  const h = authHeaders();
  if (opts && "operatorJetonu" in opts) {
    delete h["X-PEMF-Operator"];
    if (opts.operatorJetonu && isSafeBackendBase(serviceConfig.apiBaseUrl)) h["X-PEMF-Operator"] = opts.operatorJetonu;
  }
  return h;
}

// Supabase erişim JWT'si — backend bunu Supabase'e iletip tier'ı DOĞRULAR (spoof-proof). Device
// auth X-API-Key kullandığından Authorization serbest. Bayatsa backend fail-open (tedavi bloklanmaz).
let _authBearer: string | null = null;
export function setAuthBearer(token: string | null): void {
  _authBearer = token || null;
}

/**
 * HESAP KUŞAĞI (CH1 · Y151, çoklu hesap) — e-posta hesabı her değiştiğinde (`hesapKusagiArtir`, `services/hesapGecisi`) artar.
 * `apiGet` / `apiPost` / `apiDelete` isteğin BAŞLADIĞI kuşağı tutar; yanıt geldiğinde kuşak değişmişse yanıt ATILIR (çağırana
 * `fallback`, hata balonu / `onHttpError` YOK). Yarış: eski hesabın belirteciyle başlamış uçuştaki bir istek (jeton bakiyesi, liste,
 * abonelik) geçişten SONRA dönüp yeni hesabın ekranına eski hesabın verisini yazamaz.
 */
let _hesapKusagi = 0;
export function hesapKusagi(): number {
  return _hesapKusagi;
}
export function hesapKusagiArtir(): number {
  _hesapKusagi += 1;
  return _hesapKusagi;
}

/** Backend tabanı GÜVENLİ mi: https (tünel, TLS) VEYA RFC1918-LAN/localhost (yerel cihaz TLS'siz).
 * Keşfedilen/elle-girilen KEYFİ bir host'a (zehirli Supabase devices kaydı / sahte tünel) kurbanın
 * Supabase JWT'sini teslim etmemek için Authorization yalnız buraya eklenir. */
export function isSafeBackendBase(baseUrl: string): boolean {
  if (!baseUrl) return false;
  const m = baseUrl.match(/^(https?):\/\/([^/:]+)/i);
  if (!m) return false;
  const scheme = m[1].toLowerCase();
  const host = m[2].toLowerCase();
  // LAN (TLS'siz kabul edilen yerel klinik cihazı) her iki şemada da güvenlidir.
  if (isPrivateHost(host)) return true;
  // https TEK BAŞINA yeterli DEĞİL: `https://` ile başlayan HERHANGİ bir host'a (zehirli Supabase
  // devices kaydı, ele geçmiş/rotasyona uğramış trycloudflare adresi, kullanıcının elle girdiği
  // yanlış adres) kurbanın ~1 saatlik RLS-kapsamlı Supabase JWT'si teslim ediliyordu. Bearer artık
  // yalnız TANINAN tünel sağlayıcılarına gider; bilinmeyen host'a X-API-Key gider, JWT GİTMEZ.
  if (scheme !== "https") return false;
  const TRUSTED_TUNNEL_SUFFIXES = [".trycloudflare.com", ".cfargotunnel.com"];
  const extra = (process.env.EXPO_PUBLIC_PEMF_TRUSTED_HOSTS ?? "")
    .split(",").map((s: string) => s.trim().toLowerCase()).filter(Boolean);
  if (extra.includes(host)) return true;
  return TRUSTED_TUNNEL_SUFFIXES.some((sfx) => host.endsWith(sfx));
}

/** Backend auth (PEMF_REQUIRE_AUTH=1) açıksa X-API-Key + entitlement + Supabase-Bearer gönder. Token boşsa geriye uyumlu. */
export function authHeaders(): Record<string, string> {
  const bearerSafe = _authBearer && isSafeBackendBase(serviceConfig.apiBaseUrl);
  return {
    ...(serviceConfig.apiToken ? { "X-API-Key": serviceConfig.apiToken } : {}),
    ..._entitlementHeaders,
    // Supabase Bearer'ı YALNIZ güvenli tabana ekle: aksi halde poisoned/sahte host kurbanın
    // ~1sa RLS-kapsamlı JWT'sini ele geçirir (public-plaintext http'de de sızmasın).
    ...(bearerSafe ? { Authorization: `Bearer ${_authBearer}` } : {}),
    // Operatör jetonu da aynı kapıdan geçer (bkz. setOperatorToken).
    ...(_operatorToken && isSafeBackendBase(serviceConfig.apiBaseUrl)
      ? { "X-PEMF-Operator": _operatorToken } : {}),
    // SG.G1 / G2: etkin profil (bkz. setProfilBasligi) — görünüm ayrımı, kimlik değil.
    ...(_profilBasligi ? { [PROFIL_BASLIGI]: _profilBasligi } : {}),
    // I18N: etkin arayüz dili (bkz. DIL_BASLIGI) — her istekte.
    [DIL_BASLIGI]: etkinDilDegeri(),
  };
}

/** URL ile açılan (başlık taşıyamayan) kaynaklara dil parametresi: `?dil=tr|en` (ör. DEMA iframe / WebView). */
export function dilParametresiEkle(url: string): string {
  const ayirac = url.includes("?") ? "&" : "?";
  return `${url}${ayirac}dil=${etkinDilDegeri()}`;
}

// Asılı bağlantı (yarı-açık tünel / backend restart / captive portal) UI'yi sonsuza dek
// DONDURMASIN diye HER isteğe zaman aşımı. (Audit P0: apiClient tek korumasız fetch yoluydu →
// pairing kodu render olmuyor / butonlar "Kaydediliyor…"de takılı kalıyordu.)
const REQUEST_TIMEOUT_MS = 8000;

// NOT: 401'de token ASLA SİLİNMEZ. Kullanıcı bir kez (LAN veya uzaktan) bağlandıysa token
// saklı kalır; bir daha uğraştırılmaz. Yanlış/eski token, telefon LAN'a girince keşifteki
// provisionToken (/api/auth/token) ile OTOMATİK ve koşulsuz tazelenir. Silmek gereksiz olduğu
// gibi tünelde "bağlı ama kalıcı 401" tuzağı yaratıyordu.

// ORTA fix: 2xx yanıt gövdesi BOŞ veya JSON-OLMAYAN (captive-portal HTML) olabilir. Ham `response.json()`
// "Unexpected end of JSON input" fırlatıp BAŞARILI isteği hata sayıyordu → POST'ta çift-submit / yanlış hata.
// Güvenli: boş gövde = başarı (boş sonuç `{}`); JSON-olmayan gövde = gerçek hata → fallback.
async function parseJsonSafe<T>(response: Response, fallback: T): Promise<T> {
  const text = await response.text();
  // KRİTİK (crash zinciri): boş gövde eskiden `{}` döndürüyordu — ÇAĞIRANIN fallback'i DEĞİL.
  // Bu, çağrı sözleşmesini sessizce bozuyordu: `apiGet<Session[]|null>("/history/", null)`
  // boş 200'de `null` değil `{}` alıyor, `data !== null` geçiyor ve `sessions.filter(...)`
  // TypeError atıp Tedavi Geçmişi'ni beyaz ekrana düşürüyordu. Aynı şekilde
  // `apiGet<DashboardSnapshot|null>("/dashboard-snapshot", null)` → snapshot `{}` olup
  // Ana Ekran'daki `snapshot.activeTreatment.isActive` patlıyor ve ACİL DURDUR butonu
  // ekrandan kayboluyordu. Boş gövde = "veri yok" → çağıranın fallback'i doğru cevaptır.
  if (!text) return fallback;
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

export async function apiGet<T>(path: string, fallback: T, opts?: ApiOpts): Promise<T> {
  const url = `${serviceConfig.apiBaseUrl}${path}`;
  if (!isCleartextAllowed(serviceConfig.apiBaseUrl)) {
    console.error("Şifresiz istek engellendi (public host, http):", serviceConfig.apiBaseUrl);
    if (!opts?.silent) showError(i18n.t("ortak.hata.guvensizBaglanti"), i18n.t("ortak.hata.sifresizAdres"));
    return fallback;
  }
  // audit B-10.3: GET İDEMPOTENT → geçici ağ hatasında (fetch throw/timeout) 1 kez daha dene
  // (400ms sonra). HTTP hatasında (sunucu yanıt verdi) TEKRAR DENENMEZ. POST asla denenmez.
  const MAX_ATTEMPTS = 2;
  const kusak = _hesapKusagi; // CH1: yanıt başka hesabın kuşağında dönerse atılır
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), opts?.timeoutMs ?? REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, { headers: authHeaders(), signal: ctrl.signal });
      if (kusak !== _hesapKusagi) return fallback; // CH1: hesap değişti — eski hesabın yanıtı ATILIR
      if (!response.ok) {
        console.error(`API GET Hatası [${response.status}]: ${url}`);
        // Y113: apiPost ile AYNI sözleşme — durum kodu ve sunucunun gerekçesi (`detail`) çağırana verilir (ör. `/operators`
        // 503 "Cihazın kimlik veritabanı okunamıyor — …" ile hazır-değil 503'ünü ayırmak için). Gövde okunamazsa akış bozulmaz.
        if (opts?.onHttpError) {
          let detail: string | undefined;
          let govdeHam: unknown;
          try {
            govdeHam = await response.json();
            const govde = govdeHam as { detail?: unknown };
            if (typeof govde?.detail === "string" && govde.detail.trim()) detail = govde.detail.trim();
          } catch {
            /* JSON değil ya da boş gövde → detail yok */
          }
          opts.onHttpError(response.status, detail, govdeHam);
        }
        if (!opts?.silent) showError(i18n.t("ortak.hata.sunucuHatasi"), i18n.t("ortak.hata.sunucuIletisim"));
        return fallback;
      }
      const veri = await parseJsonSafe(response, fallback);
      return kusak === _hesapKusagi ? veri : fallback;
    } catch (error) {
      if (kusak !== _hesapKusagi) return fallback;
      if (attempt < MAX_ATTEMPTS) {
        await new Promise((r) => setTimeout(r, 400)); // kısa geri-çekilme, sonra bir kez daha
        continue;
      }
      console.error(`API GET İstek Başarısız (${MAX_ATTEMPTS} deneme): ${path}`, error);
      // Bağlantı kopması BLOKLAYAN uyarı GÖSTERMEZ — global çevrimdışı banner durumu bildirir.
      return fallback;
    } finally {
      clearTimeout(timer);
    }
  }
  /* istanbul ignore next -- ULASILAMAZ: döngünün her yolu döner; satır TypeScript dönüş tipi için */
  return fallback;
}

/** DELETE — apiPost ile AYNI iskelet (cleartext kapısı + zaman aşımı + authHeaders + parseJsonSafe),
 *  gövde YOK ve tekrar-deneme YOK (idempotent olsa da tekrar denemek yarış üretmesin).
 *
 *  NEDEN ayrı bir yardımcı: masaüstü oturum-devri sözleşmesi (E-özelliği, 2026-08-06)
 *  `DELETE /api/auth/desktop-session` dayatıyor — POST'la taklit edilemez. Tek tüketicisi
 *  bugün desktopSession.clearDesktopSession(); çıkış yapılırken backend'in BELLEKTEKİ devir
 *  oturumu da silinmeli, aksi halde sayfa yenilenince uygulama kendini tekrar hydrate eder
 *  ve masaüstünde "çıkış yapılamıyor" tuzağı oluşur. */
export async function apiDelete<T>(path: string, fallback: T, opts?: ApiOpts): Promise<T> {
  if (!isCleartextAllowed(serviceConfig.apiBaseUrl)) {
    console.error("Şifresiz istek engellendi (public host, http):", serviceConfig.apiBaseUrl);
    if (!opts?.silent) showError(i18n.t("ortak.hata.guvensizBaglanti"), i18n.t("ortak.hata.sifresizAdres"));
    return fallback;
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts?.timeoutMs ?? REQUEST_TIMEOUT_MS);
  const kusak = _hesapKusagi; // CH1
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "DELETE",
      headers: { Accept: "application/json", ...authHeaders() },
      signal: ctrl.signal,
    });
    if (kusak !== _hesapKusagi) return fallback; // CH1: hesap değişti — eski hesabın yanıtı ATILIR
    if (!response.ok) {
      console.error(`API DELETE Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError(i18n.t("ortak.hata.sunucuHatasi"), i18n.t("ortak.hata.silmeHatasi"));
      return fallback;
    }
    const veri = await parseJsonSafe(response, fallback);
    return kusak === _hesapKusagi ? veri : fallback;
  } catch (error) {
    console.error(`API DELETE İstek Başarısız: ${path}`, error);
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}

export async function apiPost<T>(path: string, body: unknown, fallback: T, opts?: ApiOpts): Promise<T> {
  if (opts?.durdurma !== true && !isCleartextAllowed(serviceConfig.apiBaseUrl)) {
    console.error("Şifresiz istek engellendi (public host, http):", serviceConfig.apiBaseUrl);
    if (!opts?.silent) showError(i18n.t("ortak.hata.guvensizBaglanti"), i18n.t("ortak.hata.sifresizAdres"));
    return fallback;
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts?.timeoutMs ?? REQUEST_TIMEOUT_MS);
  const kusak = _hesapKusagi; // CH1
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ..._istekBasliklari(opts),
      },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (kusak !== _hesapKusagi) return fallback; // CH1: hesap değişti — eski hesabın yanıtı ATILIR
    if (!response.ok) {
      console.error(`API POST Hatası [${response.status}]: ${url}`);
      // Sunucunun gerekçesi (FastAPI `detail`). Gövde okunamazsa akış BOZULMAZ — hata yolunda
      // ikinci bir hata üretmek, asıl hatayı gizlerdi.
      let detail: string | undefined;
      // ⚠️ GÖVDE de taşınır (2026-08-22): bazı hata yanıtları YAPISAL bilgi içerir ve o bilgi
      // güvenlikle ilgilidir. Somut olay: `/session/stop` donanım STOP'u doğrulanamayan bobin
      // varsa 409 döner ve `hardware_stop_unconfirmed` listesini gövdede taşır. Yalnız `detail`
      // dizesini geçirmek, çağıranı o listeyi metinden AYRIŞTIRMAYA zorlardı.
      let govdeHam: unknown;
      try {
        govdeHam = await response.json();
        const govde = govdeHam as { detail?: unknown };
        if (typeof govde?.detail === "string" && govde.detail.trim()) detail = govde.detail.trim();
      } catch {
        /* JSON değil ya da boş gövde → detail yok */
      }
      opts?.onHttpError?.(response.status, detail, govdeHam);   // çağıran koda göre farklı davranabilsin (bkz. ApiOpts)
      // JETON-SISTEMI Adım 4.4 (2026-08-22): 402 = TİCARİ red (jeton kapısı) — genel "Sunucu
      // Hatası" kutusuna KARIŞTIRILMAZ. Karışırsa kullanıcı "cihaz bozuldu" sanır; oysa durum
      // "jeton bitti, tedavi çalışıyor" ve kapının `detail` mesajı bunu zaten Türkçe söylüyor.
      // Bayrak (PEMF_JETON_ENFORCED) kapalıyken bu dal HİÇ tetiklenmez — bugünkü canlı davranış.
      if (response.status === 402) {
        let sebep: string | null = null;
        try {
          sebep = response.headers?.get?.(JETON_SEBEP_BASLIGI) ?? null;
        } catch {
          /* başlık okunamadı → genel "Jeton hakkı" başlığı */
        }
        if (!opts?.silent) {
          showError(
            jetonRedBasligi(sebep),
            detail ||
              (sebep === "cevrimdisi"
                ? i18n.t("ortak.hata.aiInternetGerekir")
                : i18n.t("ortak.hata.jetonYetersiz")),
          );
        }
        return fallback;
      }
      // Gerekçe varsa ONU göster: "veritabanı açılamadı, seans başlatılamaz" ile "bir hata oluştu"
      // arasındaki fark, veterinerin sorunu çözebilmesi ile çözememesi arasındaki farktır.
      if (!opts?.silent) showError(i18n.t("ortak.hata.sunucuHatasi"), detail || i18n.t("ortak.hata.gondermeHatasi"));
      return fallback;
    }
    const veri = await parseJsonSafe(response, fallback);
    return kusak === _hesapKusagi ? veri : fallback;
  } catch (error) {
    if (kusak !== _hesapKusagi) return fallback; // CH1: eski hesabın zaman aşımı / ağ hatası yeni hesaba balon göstermez
    console.error(`API POST İstek Başarısız: ${path}`, error);
    // ZAMAN AŞIMI ≠ bağlantı kopması. Kopmayı global "Çevrimdışı" banner'ı zaten bildiriyor, o
    // yüzden pop-up göstermiyoruz. Ama zaman aşımında bağlantı VARDIR ve banner çıkmaz → kullanıcı
    // HİÇBİR geri bildirim almadan boş ekranla kalıyordu ("analiz boş döndü" şikâyetinin sebebi:
    // AI ilk çağrısı 8sn sınırını aşıp sessizce iptal ediliyordu). Zaman aşımını AÇIKÇA söyle.
    if ((error as { name?: string })?.name === "AbortError" && !opts?.silent) {
      showError(
        i18n.t("ortak.hata.zamanAsimiBaslik"),
        opts?.zamanAsimiMesaji ??
          i18n.t("ortak.hata.zamanAsimiGovde"),
      );
    } else if (opts?.agHatasiMesaji && !opts?.silent) {
      showError(i18n.t("ortak.hata.cihazaUlasilamadi"), opts.agHatasiMesaji);
    }
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}
