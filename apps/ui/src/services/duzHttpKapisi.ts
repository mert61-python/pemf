// Author: mertaygn, cglrgrkn
// D3.39 (B-6.1): DÜZ-HTTP KAPISI tek kaynak. Eskiden yalnız apiClient'in apiGet / apiPost / apiDelete'i kapılıydı (43 ağ çağrısından 3'ü);
// canlı veri soketi (`ws://…?token=`), AI yüklemeleri (X-API-Key), AI Pro kare akışı, kabin kamerası ve eşleştirme takası genel http
// tabanına ŞİFRESİZ gidiyordu. Bu modül apiClient'e BAĞLI DEĞİL (apiClient buradan yeniden dışa aktarır): apiClient'i sahteleyen bir
// test kapıyı sessizce silemesin. Ham ağ çağrısı sayımı: services/__tests__/duzHttpKapisi.D3_39.test.ts.
// ⚠️ ACİL DURDUR (emergencyStop.ts) bu kapıdan BİLEREK geçmez (Y8): genel http tabanında da gönderilir.
import { Alert, Platform } from "react-native";
import i18n from "i18next";
import { emitToast } from "@/services/toastBridge";

/**
 * Nokta-dörtlü IPv4'ün BAĞLANILACAK oktetleri; değilse null.
 * ⚠️ D3.17 (B-6.2): baştaki sıfırlı oktet `inet_aton` / Android ağ yığınında SEKİZLİKTİR — `010.0.0.1` = 8.0.0.1 (genel IP),
 * `172.016.0.1` = 172.14.0.1. Eskiden `Number("010")` = 10 → "özel ağ" sayılıp jeton GENEL bir adrese gidiyordu. Geçersiz sekizlik
 * (`08`) ya da > 255 → null.
 */
export function ipv4Oktetleri(host: string): number[] | null {
  const m = String(host || "").trim().match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!m) return null;
  const o = m.slice(1, 5).map((p) => (p.length > 1 && p.startsWith("0") ? (/^[0-7]+$/.test(p) ? parseInt(p, 8) : NaN) : Number(p)));
  return o.some((n) => Number.isNaN(n) || n > 255) ? null : o;
}

/** Host, RFC1918 özel aralıkta bir IPv4 mü (ya da localhost)? Yalnız GERÇEK IP kabul edilir.
 *  Eskiden `/^10\./` gibi ön-ek testleri HOSTNAME'lere de uyuyordu: `10.evil.com` "LAN" sayılıyordu. */
export function isPrivateHost(host: string): boolean {
  const h = (host || "").toLowerCase();
  if (h === "localhost") return true;
  const o = ipv4Oktetleri(h);
  if (!o) return false; // nokta-dörtlü DEĞİLSE hostname'dir → özel ağ sayma
  const [a, b] = o;
  if (a === 127 || a === 10) return true;
  if (a === 192 && b === 168) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  return false;
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

/** Aynı kural WebSocket adresine — `wss` = https, `ws` = http. */
export function soketAdresiGuvenliMi(wsUrl: string): boolean {
  const m = String(wsUrl || "").match(/^(wss?):\/\/(.*)$/i);
  if (!m) return false;
  return isCleartextAllowed((m[1].toLowerCase() === "wss" ? "https://" : "http://") + m[2]);
}

let _sonGuvensizTaban = "";

/** Engellenen düz-HTTP isteğini kullanıcıya söyler — AYNI taban için bir kez (kare akışı / yeniden bağlanma döngüsü her denemede
 *  pencere yağdırmasın). Metin apiGet'in kapısıyla aynı (`ortak.hata.guvensizBaglanti` / `sifresizAdres`). */
export function guvensizBaglantiBildir(adres: string): void {
  const taban = (String(adres || "").match(/^([a-z]+:\/\/[^/?#]+)/i) || [])[1] || String(adres || "");
  console.error("Şifresiz istek engellendi (public host, http):", taban);
  if (taban === _sonGuvensizTaban) return;
  _sonGuvensizTaban = taban;
  const baslik = i18n.t("ortak.hata.guvensizBaglanti");
  const metin = i18n.t("ortak.hata.sifresizAdres");
  if (emitToast(`${baslik}: ${metin}`, "error")) return;
  if (Platform.OS === "web") {
    if (typeof window !== "undefined") window.alert(`${baslik}\n${metin}`);
  } else {
    Alert.alert(baslik, metin);
  }
}

/** `korunanFetch` kapısının fırlattığı hata — istek GÖNDERİLMEDİ. `message` kullanıcıya gösterilebilir (TR / EN). */
export class GuvensizBaglantiHatasi extends Error {
  constructor(readonly adres: string) {
    super(i18n.t("ortak.hata.sifresizAdres"));
    this.name = "GuvensizBaglantiHatasi";
  }
}

/** Ham `fetch`in düz-HTTP kapılı biçimi. Ağ adresi (http / https) `isCleartextAllowed`dan geçmezse istek GÖNDERİLMEZ, kullanıcıya bir
 *  kez söylenir ve `GuvensizBaglantiHatasi` fırlatılır (çağıranın catch'i akışı durdurur). Yerel URI'ler (file: / blob: / data: /
 *  content:) ağ değildir — doğrudan okunur. */
export async function korunanFetch(url: string, init?: RequestInit): Promise<Response> {
  const adres = String(url);
  if (/^https?:\/\//i.test(adres) && !isCleartextAllowed(adres)) {
    guvensizBaglantiBildir(adres);
    throw new GuvensizBaglantiHatasi(adres);
  }
  return fetch(adres, init);
}
