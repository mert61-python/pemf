// Author: mertaygn, cglrgrkn
/**
 * desktopSession — masaüstü client'tan (Tauri) DEVREDİLEN operatör oturumu.
 * ==========================================================================
 * SÖZLEŞME (hatlar arası, 2026-08-06): Client Supabase ile giriş yapar, oturumu backend'e
 * devreder; uygulama açılışta bu oturumu alıp KENDİ login ekranını ATLAR. ÇİFT GİRİŞ YOK.
 *
 *   GET    /api/auth/desktop-session  -> {access_token, refresh_token, email, expires_at} | {}
 *   DELETE /api/auth/desktop-session  -> devredilen oturumu temizle (çıkış)
 *
 * Backend bu uçları YALNIZ 127.0.0.1/::1'e açar (uzak/tünel isteği 403) ve oturumu diske YAZMAZ.
 *
 * TASARIM KARARLARI:
 *  - Platform ayrımı ŞART: mobilde (APK/iOS) masaüstü client YOKTUR. Ayrım yapılmazsa her
 *    açılışta boşa giden bir istek + gecikme oluşur. `isDesktopHost()` yalnız web bundle'ı
 *    LOOPBACK'ten servis edildiğinde true döner (client'ın açtığı 127.0.0.1:8000). LAN'daki bir
 *    tarayıcıdan açılan aynı bundle'da backend zaten 403 döner → savunmanın ikinci katmanı.
 *  - Uç YOKSA / BOŞ dönerse / hata verirse bu NORMALDİR (mobil, eski backend, client'sız açılış):
 *    sessizce mevcut login akışına düşülür. Kullanıcı ASLA hata görmez → tüm çağrılar silent.
 *  - TOKEN HİÇBİR LOG SEVİYESİNDE YAZILMAZ (ne INFO ne DEBUG). Bu dosyada token içeren hiçbir
 *    console çağrısı bulunmamalı.
 */
import { Platform } from "react-native";
import { apiDelete, apiGet, apiPost } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";

/** Tek devir isteği için SERT zaman aşımı: backend takılırsa splash'te sonsuza dek beklenmesin. */
export const DESKTOP_SESSION_TIMEOUT_MS = 3000;

/** Devrin TOPLAM bütçesi. `apiGet` ağ hatasında (idempotent GET) bir kez daha dener → en kötü
 *  hâlde 3s + 0.4s + 3s ≈ 6.4s eder ve açılış splash'i o kadar asılı kalırdı. Devir bir KOLAYLIKTIR
 *  (başarısızsa normal login var), bu yüzden bütçe aşılırsa beklemeyi bırakırız. Geç gelen bir
 *  başarı kaybolmaz: setSession yine çalışır ve onAuthStateChange kullanıcıyı içeri alır. */
export const DESKTOP_SESSION_BUDGET_MS = 3500;

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

export interface DesktopSession {
  access_token: string;
  refresh_token: string;
  email?: string;
  expires_at?: number;
}

/** Bu çalışma ortamı masaüstü client'ın açtığı yerel sayfa mı? (mobil → her zaman false) */
export function isDesktopHost(): boolean {
  if (Platform.OS !== "web") return false;
  if (typeof window === "undefined" || !window.location) return false;
  return LOOPBACK_HOSTS.has((window.location.hostname || "").toLowerCase());
}

/**
 * Devredilen oturumu OKU. Oturum yoksa backend `{}` döner — TUZAK: `{}` truthy'dir, bu yüzden
 * "yanıt geldi mi" değil "iki token da STRING mi" diye bakılır; aksi halde setSession'a boş
 * token gider ve supabase-js anlamsız bir hata üretir.
 */
export async function fetchDesktopSession(): Promise<DesktopSession | null> {
  if (!isDesktopHost()) return null;
  const data = await apiGet<Record<string, unknown> | null>("/auth/desktop-session", null, {
    silent: true,
    timeoutMs: DESKTOP_SESSION_TIMEOUT_MS,
  });
  if (!data || typeof data !== "object") return null;
  const access = data.access_token;
  const refresh = data.refresh_token;
  if (typeof access !== "string" || !access || typeof refresh !== "string" || !refresh) return null;
  return {
    access_token: access,
    refresh_token: refresh,
    email: typeof data.email === "string" ? data.email : undefined,
    expires_at: typeof data.expires_at === "number" ? data.expires_at : undefined,
  };
}

/**
 * Devredilen oturumu supabase-js istemcisine kur. Başarıda `true` → AuthContext login'i atlar.
 * KARAR: devredilen oturum, depoda duran ESKİ oturumu EZER — masaüstünde giriş otoritesi
 * client'tır (kullanıcı orada hangi hesapla giriş yaptıysa uygulama onu görmeli).
 * Token süresi geçmiş/iptal edilmişse setSession hata döner → sessizce false (normal login).
 */
export async function hydrateFromDesktopSession(): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    // Bütçe yarışı: uzayan devir açılışı kilitlemesin (bkz. DESKTOP_SESSION_BUDGET_MS).
    const butce = new Promise<boolean>((res) => {
      timer = setTimeout(() => res(false), DESKTOP_SESSION_BUDGET_MS);
    });
    return await Promise.race([_hydrate(), butce]);
  } catch {
    return false;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function _hydrate(): Promise<boolean> {
  try {
    const s = await fetchDesktopSession();
    if (!s) return false;
    const { error } = await supabaseAuth.auth.setSession({
      access_token: s.access_token,
      refresh_token: s.refresh_token,
    });
    if (error) {
      // Token/e-posta ASLA loglanmaz — yalnız "devir kullanılamadı" bilgisi.
      console.warn("Masaüstü oturum devri kullanılamadı (normal giriş akışına düşülüyor).");
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

/**
 * DÖNDÜRÜLEN oturumu backend'e GERİ YAZ — masaüstü client'ın diskteki kopyası bayatlamasın.
 *
 * 🔴 SAHA ARIZASI (2026-08-24): "Beni hatırla" bozuluyordu ve sebebi tek bir refresh-token
 * ailesinin İKİ yerde yaşamasıydı. Client oturumu DPAPI ile diske yazar VE aynı jetonları buraya
 * devreder; supabase-js `autoRefreshToken: true` ile arka planda yeniler. Supabase yenilemede
 * refresh token'ı **DÖNDÜRÜR** (rotation) — yeni jeton tarayıcı deposunda kalır, client'ın
 * diskteki kopyası BAYATLAR. Client bir sonraki açılışta bayat jetonla yenilemeyi dener, GoTrue
 * onu açıkça reddeder, bu `SessionRevoked`a eşlenir ve kayıtlı oturum SİLİNİR → kullanıcıdan
 * yeniden e-posta+parola istenir. Güncelleme bunu güvenilir biçimde tetikler: pencere bir süre
 * açık kalıp jetonu döndürür, sonra zorunlu yeniden başlatma gelir.
 *
 * Bu fonksiyon döngüyü kapatır: her döndürmede yeni oturum backend'e yazılır, client oradan
 * okuyup diske işler (Rust tarafı: `auth_sync_from_backend`).
 *
 * ⚠️ SESSİZ ve ZORUNLU DEĞİL: başarısızlıkta kullanıcı hiçbir şey görmez ve akış değişmez —
 * bu bir kolaylıktır, kapı değil. ⚠️ TOKEN HİÇBİR LOG SEVİYESİNDE yazılmaz.
 */
export async function pushDesktopSession(s: DesktopSession): Promise<void> {
  if (!isDesktopHost()) return;
  // Eksik jeton devri BOZAR (backend boş refresh_token'ı kabul eder ve client onu diske yazardı).
  if (!s || typeof s.access_token !== "string" || !s.access_token) return;
  if (typeof s.refresh_token !== "string" || !s.refresh_token) return;
  try {
    await apiPost<null>(
      "/auth/desktop-session",
      { access_token: s.access_token, refresh_token: s.refresh_token, email: s.email ?? "", expires_at: s.expires_at ?? 0 },
      null,
      { silent: true, timeoutMs: DESKTOP_SESSION_TIMEOUT_MS },
    );
  } catch {
    /* yok say — geri yazma bir kolaylıktır */
  }
}

/**
 * Çıkışta backend'in BELLEKTEKİ devir oturumunu sil. Yapılmazsa sayfa yenilenince uygulama
 * kendini tekrar hydrate eder → masaüstünde "çıkış yapılamıyor". En-iyi-çaba: hata yutulur
 * (backend kapalıysa çıkış yine de tamamlanmalı).
 */
export async function clearDesktopSession(): Promise<void> {
  if (!isDesktopHost()) return;
  try {
    await apiDelete<null>("/auth/desktop-session", null, {
      silent: true,
      timeoutMs: DESKTOP_SESSION_TIMEOUT_MS,
    });
  } catch {
    /* yok say — yerel çıkış her hâlükârda yapılacak */
  }
}
