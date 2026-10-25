// Author: mertaygn, cglrgrkn
/**
 * D3.19 (B-6.6): mobil indirme KAYNAK PİNİ — TEK kaynak. `mobileUpdate` (OTA) ve uykudaki ikinci yol `updates.ts`
 * (UpdateBanner) AYNI işlevi kullanır; ağır modüllerden (FileSystem / Sharing) bağımsız durur ki her tüketici içe aktarabilsin.
 */

/**
 * İNDİRME KAYNAĞI PİNİ — masaüstü `launcher/core/src/net.rs::validate_download_source` ikizi.
 *
 * ⚠️ Bu kapı olmadan manifest'in `mobile.android.url` alanını etkileyebilen herkes sahadaki tüm
 * telefonlara istediği adresten — `usesCleartextTraffic` açık olduğu için düz `http://` dahil —
 * 128 MB'lık keyfi içerik indirtebilirdi. Masaüstü tarafında bu pin 2026-08-04 denetiminde
 * konmuştu; mobil taraf o gün atlanmıştı (denetim 2026-08-23, bulgu M1).
 *
 * Kabul edilen: repo-yolu pinli `github.com` **veya** açıkça sayılmış GitHub nesne depoları.
 * ⚠️ `.githubusercontent.com` JOKERİ KABUL EDİLMEZ — oraya ücretsiz bir hesap keyfi bayt koyabilir
 * (masaüstünde joker yalnız *yönlendirme hedefleri* için geçerli, kaynak URL'ler için değil).
 */
const IZINLI_NESNE_DEPOLARI = ["objects.githubusercontent.com", "release-assets.githubusercontent.com"];
const YAYIN_REPO_YOLU = "/mert61-python/pemf-update/";

/**
 * Yol, istemci-tarafı normalizasyonuyla bizim gördüğümüzden BAŞKA bir yere çözülebilir mi?
 *
 * ⚠️ HAM METİN üzerinde çalışır, `new URL(...).pathname` üzerinde DEĞİL — ölçülerek öyle yazıldı:
 * WHATWG ayrıştırıcısı `\` karakterini sessizce `/`'a çeviriyor, yani ayrıştırılmış yolu denetlemek
 * o vakayı hiç göremez. İndiriciye giden şey zaten HAM dizedir; onu bizim ayrıştırıcımızın değil,
 * indiricinin ayrıştırıcısı çözecek. İki ayrıştırıcının aynı kararı vereceğine güvenmek yerine
 * şüpheli yazımı baştan reddediyoruz (masaüstü `net.rs::path_has_traversal` ile aynı yaklaşım).
 */
function yolKacisiVar(hamYol: string): boolean {
  const s = hamYol.split(/[?#]/)[0];
  const k = s.toLowerCase();
  if (k.includes("%2e") || k.includes("%2f") || k.includes("%5c") || s.includes("\\")) return true;
  // Baştaki '/' yüzünden ilk parça daima boştur; onu atla.
  return s.split("/").slice(1).some((p) => p === "." || p === ".." || p === "");
}

export function kaynakGuvenli(url: string): boolean {
  if (typeof url !== "string" || !url) return false;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return false;
  }
  if (u.protocol !== "https:") return false;
  // Ham yol: şemadan sonraki ilk '/'den itibaren (authority hariç).
  const semasiz = url.slice(url.indexOf("://") + 3);
  const kesme = semasiz.search(/[/?#]/);
  if (yolKacisiVar(kesme < 0 ? "" : semasiz.slice(kesme))) return false;
  if (IZINLI_NESNE_DEPOLARI.includes(u.hostname)) return true;
  // `github.com` yalnız BİZİM repo yolumuzla; "GitHub'da bir yer" yetmez.
  return u.hostname === "github.com" && u.pathname.startsWith(YAYIN_REPO_YOLU);
}
