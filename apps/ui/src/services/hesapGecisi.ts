// Author: mertaygn, cglrgrkn
/**
 * ÇOKLU HESAP — e-posta hesapları arasında geçiş (CH1 · Y151 / S-SG.6).
 *
 * Hesap = giriş yapılan E-POSTA (Supabase oturumu: jeton bakiyesi, abonelik, AI geçmişi "Benim" kapsamı). "Hekim Değiştir (bu cihaz)"
 * AYRI bir şeydir: aynı hesapta, bu cihazı paylaşan PIN'li kişiler arası geçiş (OperatorContext) — buradaki geçiş onu ATLATMAZ (çok
 * kullanıcılı cihazda geçişten sonra hekim yeniden seçilir: `HesapMenusu` kilitler, uygulama ağacı hesap anahtarıyla yeniden kurulur).
 *
 * Geçiş sırası (`hesabaGec`): etkin oturum park edilir → kimlik başlıkları HEMEN düşer ve hesap kuşağı artar (uçuştaki eski hesap
 * yanıtları atılır — `apiClient.hesapKusagi`) → hedefin belirteciyle `supabaseAuth.auth.setSession` → başarıda hedef parktan çıkar.
 * Düşerse önceki hesap geri kurulur; hedefin belirteci kalıcı geçersizse (oturum sona ermiş) parktan silinir ve kullanıcıya "yeniden giriş
 * yapın" denir. Geçiş Supabase doğrulaması ister (internet); çevrimdışıyken önceki hesapta kalınır.
 *
 * ⚠️ HASTA GÜVENLİĞİ: SEANS SÜRERKEN (bobin çalışırken / donanım belirsizken) geçiş KAPALI (`hesapGecisiEngeli`, teardown korumasıyla
 * AYNI koşullar — A-59 / Y55). ACİL DURDUR geçişten etkilenmez (ekran kabuğu geçiş bitene dek yerinde, sonra yeniden kurulur).
 * ⚠️ Belirteç DEĞERİ hiçbir günlüğe / iletiye yazılmaz.
 */
import type { DashboardSnapshot } from "@/types/domain";
import { hesapKusagiArtir, setAuthBearer, setEntitlementHeaders } from "@/services/apiClient";
import { supabaseAuth } from "@/services/supabaseAuth";
import {
  epostaAnahtari,
  parkEt,
  parkHesabi,
  parkHesaplari,
  parktanCikar,
  hepsiniSil,
  type ParkHesap,
} from "@/services/hesapDeposu";

export interface GecisSonucu {
  ok: boolean;
  hata?: string;
}

export const HESAP_GECIS_SEANS_ENGELI =
  "Seans sürerken (bobinler çalışırken) e-posta hesabı değiştirilemez — önce seansı bitirin. ACİL DURDUR ekranda kalır.";
export const HESAP_GECIS_BELIRSIZ_ENGELI =
  "Bobinlerin durumu bilinmiyor (cihaz bağlantısı yok) — e-posta hesabı değiştirilemez. Önce bağlantıyı ve bobinleri kontrol edin.";

/**
 * Hesap değiştirme / ekleme / etkin hesaptan çıkma ŞU AN yapılabilir mi? `null` = evet; aksi hâlde NEDEN (kullanıcıya gösterilir).
 * ⚠️ Koşullar `hooks/useTeardownGuard` ile AYNI: çalışan bobin, aktif seans, STM "belirsiz" (bir kez çalıştı, kart şimdi çevrimdışı).
 * Fark: teardown koruması onayla durdurup devam eder; hesap geçişi seansı DURDURMAZ, yalnız kapalı kalır ve nedenini söyler.
 */
export function hesapGecisiEngeli(
  snapshot: Pick<DashboardSnapshot, "coils" | "activeTreatment"> | null | undefined,
  donanimBelirsiz?: boolean,
): string | null {
  const calisan = (snapshot?.coils ?? []).some((c) => c?.running === true);
  const aktif = snapshot?.activeTreatment?.isActive === true;
  if (calisan || aktif) return HESAP_GECIS_SEANS_ENGELI;
  if (donanimBelirsiz === true) return HESAP_GECIS_BELIRSIZ_ENGELI;
  return null;
}

/** Supabase'in şu an etkin oturumu (park biçiminde) — yoksa null. */
export async function etkinOturum(): Promise<ParkHesap | null> {
  try {
    const { data } = await supabaseAuth.auth.getSession();
    const s = data?.session;
    if (!s?.user?.email || !s.refresh_token) return null;
    return { email: s.user.email, access_token: s.access_token || "", refresh_token: s.refresh_token, expires_at: s.expires_at };
  } catch {
    return null;
  }
}

/**
 * Hesap değişiyor: kimlik başlıkları (Supabase Bearer, abonelik başlıkları) HEMEN düşer, hesap kuşağı artar → bu andan sonra dönen
 * eski hesabın yanıtları atılır; yeni hesabın başlıkları `EntitlementContext` tazelemesinde kurulur.
 */
export function hesapKimliginiDusur(): void {
  hesapKusagiArtir();
  setAuthBearer(null);
  setEntitlementHeaders(null);
}

/** Supabase hatası belirtecin KALICI geçersizliği mi (oturum sona ermiş / iptal) — ağ hatası DEĞİL. */
function belirtecGecersizMi(error: unknown): boolean {
  const e = error as { status?: number; name?: string; message?: string } | null;
  if (!e) return false;
  if (e.name === "AuthRetryableFetchError") return false;
  const m = String(e.message || "").toLowerCase();
  if (m.includes("fetch") || m.includes("network") || m.includes("timeout")) return false;
  return (e.status ?? 0) === 400 || (e.status ?? 0) === 401 || m.includes("refresh token") || m.includes("invalid")
    || m.includes("expired") || m.includes("not found");
}

async function oturumKur(h: ParkHesap): Promise<unknown> {
  try {
    const r = await supabaseAuth.auth.setSession({ access_token: h.access_token, refresh_token: h.refresh_token });
    return r?.error ?? null;
  } catch (e) {
    return e ?? new Error("setSession");
  }
}

/** Park edilmiş bir hesaba geç. Etkin hesap park edilir; düşerse önceki hesapta kalınır. */
export async function hesabaGec(hedefEposta: string): Promise<GecisSonucu> {
  const hedef = await parkHesabi(hedefEposta);
  if (!hedef) return { ok: false, hata: "Bu hesap artık bu cihazda açık değil — \"Hesap ekle\" ile yeniden giriş yapın." };
  const onceki = await etkinOturum();
  if (onceki && epostaAnahtari(onceki.email) === epostaAnahtari(hedef.email)) {
    await parktanCikar(hedef.email); // zaten etkin — yinelenen park kaydı temizlenir
    return { ok: true };
  }
  if (onceki) await parkEt(onceki);
  hesapKimliginiDusur();
  const hata = await oturumKur(hedef);
  if (!hata) {
    await parktanCikar(hedef.email);
    return { ok: true };
  }
  const kalici = belirtecGecersizMi(hata);
  if (kalici) await parktanCikar(hedef.email);
  if (onceki) {
    hesapKimliginiDusur();
    if (!(await oturumKur(onceki))) await parktanCikar(onceki.email);
  }
  return {
    ok: false,
    hata: kalici
      ? `${hedef.email} hesabının oturumu sona ermiş — "Hesap ekle" ile yeniden giriş yapın.`
      : "Hesap değiştirilemedi: sunucuya ulaşılamadı (geçiş için internet gerekir). Önceki hesapta kalındı.",
  };
}

/**
 * Park edilmiş (etkin OLMAYAN) bir hesaptan çık: belirteç bu cihazdan silinir; erişim belirteci hâlâ geçerliyse oturum sunucuda da
 * iptal edilir (en-iyi-çaba, `logout?scope=local` — yalnız o oturum). Etkin hesabı ETKİLEMEZ.
 */
export async function parkHesabindanCik(eposta: string): Promise<void> {
  const h = await parkHesabi(eposta);
  await parktanCikar(eposta); // ÖNCE yerel silme — ağ asılsa da hesap cihazdan çıkmış olur
  if (h?.access_token) sunucudaIptal([h]);
}

/** Park edilmiş TÜM hesaplardan çık (Tüm hesaplardan çık'ın park kısmı; etkin hesabı çağıran kapatır). */
export async function tumParkHesaplardanCik(): Promise<void> {
  const liste = await parkHesaplari();
  await hepsiniSil();
  sunucudaIptal(liste);
}

/** En-iyi-çaba sunucu iptali — BEKLENMEZ (çıkış ağ yüzünden asılmasın); süresi dolmuş / ağ yok → yalnız yerel silme kalır. */
function sunucudaIptal(liste: ParkHesap[]): void {
  void Promise.allSettled(
    liste.filter((h) => !!h.access_token).map((h) => supabaseAuth.auth.admin.signOut(h.access_token, "local")),
  );
}
