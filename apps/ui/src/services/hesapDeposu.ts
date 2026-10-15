// Author: mertaygn, cglrgrkn
/**
 * ÇOKLU HESAP — etkin OLMAYAN e-posta hesaplarının oturum deposu (CH1 · Y151 / S-SG.6, sahip 2026-10-14: "ikisi de şimdi").
 *
 * Etkin hesabın oturumu supabase-js'in kendi anahtarında (`sb-<ref>-auth-token`) durur; diğer açık hesaplar burada "park" edilir:
 * e-posta + access / refresh belirteci. Geçişte (`services/hesapGecisi`) etkin olan park edilir, hedef supabase-js'e kurulur.
 *
 * ⚠️ GÜVENLİK DÜZEYİ: depo `supabaseAuth.oturumDeposu` — supabase-js'in KULLANDIĞI depo (native SecureStore / Keychain-Keystore parçalı ·
 * LAN-mobil web AsyncStorage · masaüstü penceresi YALNIZ BELLEK, otorite launcher). Yani park edilen yenileme belirteci bugünkü tek
 * hesabın belirteciyle AYNI yerde, AYNI korumayla durur; daha zayıf bir depoya düşmez (masaüstünde pencere kapanınca park edilenler de
 * gider — launcher yalnız kendi tek hesabını kalıcı tutar).
 * ⚠️ SIZINTI YOK: belirteç değeri hiçbir günlüğe / hata iletisine yazılmaz; okunamayan / bozuk kayıt sessizce "yok" sayılır.
 * Çıkışta (`Tüm hesaplardan çık` = mevcut "Çıkış Yap") ve uygulama verisi silinince (kaldırma) hepsi gider.
 */
import { oturumDeposu } from "@/services/supabaseAuth";

export const HESAP_DEPO_ANAHTARI = "pemf-hesaplar-v1";

export interface ParkHesap {
  email: string;
  access_token: string;
  refresh_token: string;
  /** Erişim belirtecinin bitişi (epoch sn) — yalnız bilgi; geçişte supabase-js kendisi tazeler. */
  expires_at?: number;
}

export const epostaAnahtari = (e: string | null | undefined): string => (e || "").trim().toLowerCase();

function gecerli(x: unknown): x is ParkHesap {
  const h = x as ParkHesap;
  return !!h && typeof h.email === "string" && !!h.email.trim() && typeof h.refresh_token === "string" && !!h.refresh_token
    && typeof h.access_token === "string";
}

/** Park edilmiş hesaplar (en eski önce). Bozuk / okunamayan depo → boş liste (hata FIRLATMAZ, değer yazdırmaz). */
export async function parkHesaplari(): Promise<ParkHesap[]> {
  try {
    const ham = await oturumDeposu.getItem(HESAP_DEPO_ANAHTARI);
    if (!ham) return [];
    const v: unknown = JSON.parse(ham);
    return Array.isArray(v) ? v.filter(gecerli) : [];
  } catch {
    return [];
  }
}

async function yaz(liste: ParkHesap[]): Promise<void> {
  if (liste.length === 0) {
    await oturumDeposu.removeItem(HESAP_DEPO_ANAHTARI);
    return;
  }
  await oturumDeposu.setItem(HESAP_DEPO_ANAHTARI, JSON.stringify(liste));
}

/** Hesabı park et (aynı e-posta varsa yerine yazılır — belirteç tazelenmiş olabilir). */
export async function parkEt(h: ParkHesap): Promise<void> {
  if (!gecerli(h)) return;
  const liste = (await parkHesaplari()).filter((x) => epostaAnahtari(x.email) !== epostaAnahtari(h.email));
  liste.push({ email: h.email.trim(), access_token: h.access_token, refresh_token: h.refresh_token, expires_at: h.expires_at });
  await yaz(liste);
}

export async function parkHesabi(email: string): Promise<ParkHesap | null> {
  return (await parkHesaplari()).find((x) => epostaAnahtari(x.email) === epostaAnahtari(email)) ?? null;
}

export async function parktanCikar(email: string): Promise<void> {
  const once = await parkHesaplari();
  const sonra = once.filter((x) => epostaAnahtari(x.email) !== epostaAnahtari(email));
  if (sonra.length !== once.length) await yaz(sonra);
}

/** Park edilmiş TÜM hesapları sil (Tüm hesaplardan çık). */
export async function hepsiniSil(): Promise<void> {
  try {
    await oturumDeposu.removeItem(HESAP_DEPO_ANAHTARI);
  } catch {
    /* silinemezse bir sonraki çıkışta yeniden denenir — değer yazdırılmaz */
  }
}
