// Author: mertaygn, cglrgrkn
/**
 * AĞ TANISI — "cihaz bulunamadı" dendiğinde SEBEBİ söyler.
 *
 * SAHA BİLDİRİMİ (2026-08-14, sahip): telefon ve cihaz aynı Wi-Fi'deydi, cihaz çalışıyordu,
 * mDNS doğru arayüzde yayındaydı, güvenlik duvarı açıktı — ama uygulama bağlanamıyordu. Sebep
 * MODEMDE açılmış **istemci izolasyonu** (AP Isolation) idi: cihazlar internete çıkar ama
 * birbirini göremez. Bunu bulmak ürünü yazan kişinin bir saatini aldı; sahadaki veteriner hiç
 * bulamaz — ürünü arızalı sanar.
 *
 * ⚠️ Bu modül TAHMİN ETMEZ, KANIT arar. İzolasyonun kesin bir imzası vardır:
 *
 *   cihaza İNTERNET üzerinden ulaşılıyor  +  cihazın yerel adresi telefonla AYNI alt ağda
 *   +  o yerel adrese DOĞRUDAN ulaşılamıyor
 *
 * Üçü birden doğruysa paketler modemde durduruluyor demektir; başka makul açıklaması yoktur.
 * Üçünden biri eksikse `bilinmiyor` döner — yanlış teşhis, teşhissizlikten kötüdür (kullanıcıyı
 * modem ayarlarında boşuna gezdirir).
 *
 * ⚠️ YAN ETKİSİZ: burada `discovery.checkHealth` KULLANILMAZ. O fonksiyon başarılı her yanıtta
 * `device_id` saklar ve token çeker; bir TANI sırasında kalıcı durum değiştirmek istemiyoruz.
 * Kendi salt-okur yoklamamız var.
 */
import { getStoredDeviceId } from "@/services/config";
import { uzakCihaziKimlikleCoz, type UzakCozumleme } from "@/services/deviceRegistry";

const YOKLAMA_TIMEOUT_MS = 2500;

/** Tanı sonucu — her durumun AYRI bir kullanıcı eylemi vardır. */
export type AgTanisi =
  /** Modemde istemci izolasyonu (ya da telefon misafir ağında): kapat / ana ağa geç / kodla bağlan. */
  | { durum: "izolasyon"; cihazIp: string }
  /** Telefon gerçekten başka bir ağda: kod yolu ZATEN doğru cevap. */
  | { durum: "farkli_ag"; cihazIp: string }
  /** Cihaz kayıtlı ama çevrimdışı / uzaktan erişim kapalı: cihazın kendisine bakılmalı. */
  | { durum: "cihaz_kapali" }
  /** Kanıt yetersiz — SUSMAK doğru davranış. */
  | { durum: "bilinmiyor" };

/** Sağlık yanıtının tanı için gereken tek alanı. */
interface Saglik {
  localIp?: string;
}

/** SALT-OKUR sağlık yoklaması (kimlik/token YAZMAZ). */
async function saglikSor(adres: string): Promise<Saglik | null> {
  try {
    const base = adres.startsWith("http") ? adres.replace(/\/$/, "") : `http://${adres}:8000`;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), YOKLAMA_TIMEOUT_MS);
    const res = await fetch(`${base}/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) return null;
    const d = await res.json();
    // Rastgele bir :8000 sunucusunu cihaz sanma (keşif merdiveniyle AYNI kesinlik kuralı).
    if (d?.service !== "PEMF-Vet") return null;
    return { localIp: d?.localIp ? String(d.localIp) : undefined };
  } catch {
    return null;
  }
}

/** Telefonun kendi Wi-Fi adresi (yoksa null). */
async function telefonIp(): Promise<string | null> {
  try {
    // @ts-ignore - opsiyonel native modül (yalnızca native platformda mevcut)
    const NetInfo = require("@react-native-community/netinfo").default;
    const st = await NetInfo.fetch();
    const ip: unknown = st?.details?.ipAddress;
    return typeof ip === "string" && ip.includes(".") ? ip : null;
  } catch {
    return null;
  }
}

/** IPv4'ün /24 alt ağı ("192.168.1.44" → "192.168.1"); biçim bozuksa null. */
export function altAg(ip: string): string | null {
  const p = String(ip || "").split(".");
  if (p.length !== 4) return null;
  if (!p.every((o) => /^\d{1,3}$/.test(o) && Number(o) <= 255)) return null;
  return p.slice(0, 3).join(".");
}

export interface TaniBagimliliklari {
  kimlikOku?: () => Promise<string | null>;
  uzakCoz?: (id: string) => Promise<UzakCozumleme>;
  saglikSor?: (adres: string) => Promise<Saglik | null>;
  telefonIp?: () => Promise<string | null>;
}

/**
 * Bağlanılamama sebebini KANITA dayanarak belirle.
 *
 * Sıra kasıtlı: önce cihazın internetten ayakta olduğunu doğrularız (aksi halde yerel erişimsizlik
 * "cihaz kapalı"dan ayırt edilemez), sonra alt ağları karşılaştırırız, en son yerel erişimi deneriz.
 */
export async function agTanisiYap(deps: TaniBagimliliklari = {}): Promise<AgTanisi> {
  const kimlikOku = deps.kimlikOku ?? getStoredDeviceId;
  const uzakCoz = deps.uzakCoz ?? uzakCihaziKimlikleCoz;
  const sor = deps.saglikSor ?? saglikSor;
  const benimIp = deps.telefonIp ?? telefonIp;

  const id = await kimlikOku();
  if (!id) return { durum: "bilinmiyor" }; // hiç eşleşilmemiş → söyleyecek bir şey yok

  const c = await uzakCoz(id);
  if (c.durum === "adres_yok" || c.durum === "bayat") return { durum: "cihaz_kapali" };
  if (c.durum !== "bulundu") return { durum: "bilinmiyor" }; // "yok"/"hata" → buluta ulaşılamadı

  // (1) Cihaz internetten AYAKTA mı? Değilse yerel erişimsizlik izolasyon KANITI değildir.
  const uzak = await sor(c.url);
  if (!uzak) return { durum: "cihaz_kapali" };

  const cihazIp = uzak.localIp;
  if (!cihazIp || !altAg(cihazIp)) return { durum: "bilinmiyor" };

  // (2) Telefon cihazla AYNI alt ağda mı?
  const ip = await benimIp();
  const benimAltAg = ip ? altAg(ip) : null;
  if (!benimAltAg) return { durum: "bilinmiyor" }; // adres okunamadı → tahmin YOK
  if (benimAltAg !== altAg(cihazIp)) return { durum: "farkli_ag", cihazIp };

  // (3) Aynı alt ağdayız: yerel adres GERÇEKTEN ulaşılmaz mı?
  const yerel = await sor(`http://${cihazIp}:8000`);
  if (yerel) return { durum: "bilinmiyor" }; // ulaşılıyor → izolasyon yok, arıza başka yerde

  return { durum: "izolasyon", cihazIp };
}

/** Kullanıcıya gösterilecek metin — TEK KAYNAK. */
export function taniMesaji(t: AgTanisi): { baslik: string; metin: string } | null {
  switch (t.durum) {
    case "izolasyon":
      return {
        baslik: "Modeminiz cihazları birbirinden ayırıyor",
        metin:
          `Cihaza internet üzerinden ulaşılıyor ama aynı Wi-Fi'de doğrudan ulaşılamıyor ` +
          `(${t.cihazIp}). Modeminizde "istemci izolasyonu" (AP Isolation) açık olabilir ya da ` +
          `telefonunuz misafir ağında olabilir. Modem ayarlarından bu seçeneği kapatın veya ` +
          `telefonu ana Wi-Fi ağına alın. Dilerseniz aşağıdaki kodla internet üzerinden de bağlanabilirsiniz.`,
      };
    case "farkli_ag":
      return {
        baslik: "Farklı bir ağdasınız",
        metin:
          `Telefonunuz cihazla aynı Wi-Fi'de değil. Bu normaldir — aşağıdaki eşleştirme kodu ` +
          `tam bunun içindir; cihaza internet üzerinden bağlanırsınız.`,
      };
    case "cihaz_kapali":
      return {
        baslik: "Cihaz şu an çevrimdışı görünüyor",
        metin:
          `Cihaz kayıtlı ama yanıt vermiyor. Cihazın açık ve internete bağlı olduğundan emin olun; ` +
          `uzaktan erişim cihazın kendi ekranından kapatılmış da olabilir.`,
      };
    default:
      return null; // bilinmiyor → SUS (yanlış teşhis, teşhissizlikten kötüdür)
  }
}
