// Author: mertaygn, cglrgrkn
import { serviceConfig } from "@/services/config";
import { Alert, Platform } from "react-native";
import { emitToast } from "@/services/toastBridge";

/** Web-güvenli uyarı — Alert.alert web'de no-op olduğundan window.alert'e düşer. */
export function platformAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    if (typeof window !== "undefined") window.alert(`${title}\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}

/** Web-güvenli onay diyaloğu — Alert.alert çoklu-buton web'de tetiklenmez (window.confirm'e düşer). */
export function platformConfirm(title: string, message: string, confirmLabel = "Onayla"): Promise<boolean> {
  if (Platform.OS === "web") {
    return Promise.resolve(typeof window !== "undefined" ? window.confirm(`${title}\n\n${message}`) : false);
  }
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: "İptal", style: "cancel", onPress: () => resolve(false) },
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

/** İstek opsiyonları — `silent: true` arka-plan poll'lerinde hata pop-up'ını bastırır. */
export interface ApiOpts {
  silent?: boolean;
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
}

/** AI çıkarım uçları için zaman aşımı — ilk çağrıdaki model yükleme + JIT derlemesini kapsar. */
export const AI_TIMEOUT_MS = 120000;

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

// Supabase erişim JWT'si — backend bunu Supabase'e iletip tier'ı DOĞRULAR (spoof-proof). Device
// auth X-API-Key kullandığından Authorization serbest. Bayatsa backend fail-open (tedavi bloklanmaz).
let _authBearer: string | null = null;
export function setAuthBearer(token: string | null): void {
  _authBearer = token || null;
}

/** Backend tabanı GÜVENLİ mi: https (tünel, TLS) VEYA RFC1918-LAN/localhost (yerel cihaz TLS'siz).
 * Keşfedilen/elle-girilen KEYFİ bir host'a (zehirli Supabase devices kaydı / sahte tünel) kurbanın
 * Supabase JWT'sini teslim etmemek için Authorization yalnız buraya eklenir. */
/** Host, RFC1918 özel aralıkta bir IPv4 mü (ya da localhost)? Yalnız GERÇEK IP kabul edilir.
 *  Eskiden `/^10\./` gibi ön-ek testleri HOSTNAME'lere de uyuyordu: `10.evil.com` "LAN" sayılıyordu. */
export function isPrivateHost(host: string): boolean {
  const h = (host || "").toLowerCase();
  if (h === "localhost") return true;
  const m = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!m) return false; // nokta-dörtlü DEĞİLSE hostname'dir → özel ağ sayma
  const [a, b] = [Number(m[1]), Number(m[2])];
  if ([a, b, Number(m[3]), Number(m[4])].some((n) => n > 255)) return false;
  if (a === 127 || a === 10) return true;
  if (a === 192 && b === 168) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  return false;
}

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

/** Bu tabana DÜZ HTTP ile istek atmak güvenli mi?
 *
 *  Android manifest'inde uygulama GENELİNDE `usesCleartextTraffic="true"`. Bunu manifest'ten
 *  daraltmak MÜMKÜN DEĞİL: `networkSecurityConfig` DNS ADLARIYLA çalışır, IP aralığı/CIDR
 *  ifade edemez — cihaz ise DHCP ile değişen bir LAN IP'sinde (ör. 192.168.1.147) durur, dolayısıyla
 *  "yalnız RFC1918'e cleartext izin ver" kuralı manifest'te yazılamaz ve denenirse keşif tümüyle
 *  kırılır. Kısıtlamayı bu yüzden UYGULAMA KATMANINDA uyguluyoruz: düz HTTP yalnız özel ağa
 *  (klinik cihazı, TLS'siz kabul edilen güven sınırı) izinlidir; internete çıkan her adres TLS
 *  zorunludur. Böylece bozuk/zehirli bir keşif kaydı cihaz token'ını ve hasta telemetrisini
 *  şifresiz olarak public bir host'a taşıyamaz. */
export function isCleartextAllowed(baseUrl: string): boolean {
  const m = String(baseUrl || "").match(/^(https?):\/\/([^/:]+)/i);
  if (!m) return false;
  if (m[1].toLowerCase() === "https") return true;
  return isPrivateHost(m[2]);
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
  };
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
    if (!opts?.silent) showError("Güvensiz bağlantı", "Cihaz adresi şifresiz (http) ve yerel ağda değil — istek gönderilmedi.");
    return fallback;
  }
  // audit B-10.3: GET İDEMPOTENT → geçici ağ hatasında (fetch throw/timeout) 1 kez daha dene
  // (400ms sonra). HTTP hatasında (sunucu yanıt verdi) TEKRAR DENENMEZ. POST asla denenmez.
  const MAX_ATTEMPTS = 2;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), opts?.timeoutMs ?? REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, { headers: authHeaders(), signal: ctrl.signal });
      if (!response.ok) {
        console.error(`API GET Hatası [${response.status}]: ${url}`);
        if (!opts?.silent) showError("Sunucu Hatası", "Sunucu ile iletişimde bir sorun oluştu.");
        return fallback;
      }
      return await parseJsonSafe(response, fallback);
    } catch (error) {
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
    if (!opts?.silent) showError("Güvensiz bağlantı", "Cihaz adresi şifresiz (http) ve yerel ağda değil — istek gönderilmedi.");
    return fallback;
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts?.timeoutMs ?? REQUEST_TIMEOUT_MS);
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "DELETE",
      headers: { Accept: "application/json", ...authHeaders() },
      signal: ctrl.signal,
    });
    if (!response.ok) {
      console.error(`API DELETE Hatası [${response.status}]: ${url}`);
      if (!opts?.silent) showError("Sunucu Hatası", "Sunucuda kayıt silinirken bir hata oluştu.");
      return fallback;
    }
    return await parseJsonSafe(response, fallback);
  } catch (error) {
    console.error(`API DELETE İstek Başarısız: ${path}`, error);
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}

export async function apiPost<T>(path: string, body: unknown, fallback: T, opts?: ApiOpts): Promise<T> {
  if (!isCleartextAllowed(serviceConfig.apiBaseUrl)) {
    console.error("Şifresiz istek engellendi (public host, http):", serviceConfig.apiBaseUrl);
    if (!opts?.silent) showError("Güvensiz bağlantı", "Cihaz adresi şifresiz (http) ve yerel ağda değil — istek gönderilmedi.");
    return fallback;
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts?.timeoutMs ?? REQUEST_TIMEOUT_MS);
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
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
        if (!opts?.silent) showError("Jeton hakkı", detail || "Jeton hakkınız yetersiz. Seans ve acil durdurma etkilenmez.");
        return fallback;
      }
      // Gerekçe varsa ONU göster: "veritabanı açılamadı, seans başlatılamaz" ile "bir hata oluştu"
      // arasındaki fark, veterinerin sorunu çözebilmesi ile çözememesi arasındaki farktır.
      if (!opts?.silent) showError("Sunucu Hatası", detail || "Sunucuya veri gönderilirken bir hata oluştu.");
      return fallback;
    }
    return await parseJsonSafe(response, fallback);
  } catch (error) {
    console.error(`API POST İstek Başarısız: ${path}`, error);
    // ZAMAN AŞIMI ≠ bağlantı kopması. Kopmayı global "Çevrimdışı" banner'ı zaten bildiriyor, o
    // yüzden pop-up göstermiyoruz. Ama zaman aşımında bağlantı VARDIR ve banner çıkmaz → kullanıcı
    // HİÇBİR geri bildirim almadan boş ekranla kalıyordu ("analiz boş döndü" şikâyetinin sebebi:
    // AI ilk çağrısı 8sn sınırını aşıp sessizce iptal ediliyordu). Zaman aşımını AÇIKÇA söyle.
    if ((error as { name?: string })?.name === "AbortError" && !opts?.silent) {
      showError("İşlem zaman aşımına uğradı", "Sunucu zamanında yanıt vermedi. Tekrar deneyin — ilk analiz model yüklemesi nedeniyle uzun sürebilir.");
    }
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}
