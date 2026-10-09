// Author: mertaygn, cglrgrkn
/**
 * dosyaIndir — kimlikli dosya indirme/dışa aktarma (geçmiş raporları).
 *
 * ⚠️ EKRANDAN ÇIKARILDI (2026-09-11): mantık artık üç gerçek dala sahip (yerel backend /
 * tarayıcı blob / native paylaşım) ve her dalın kendi sessiz-başarısızlık riski var.
 * Ekran dosyasının içinde kaldığı sürece test edilemiyordu — arıza da tam bu yüzden
 * sahada bulundu.
 */
import { Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { serviceConfig } from "@/services/config";

// GÜVENLİK (YÜKSEK fix): Raporu X-API-Key HEADER'ı ile indir → cihaz MASTER token'ı URL'de
// (tarayıcı geçmişi / sunucu & Cloudflare tünel erişim-logları / PDF disk-cache) SIZMASIN. Eski
// `withToken` token'ı ?token= olarak URL'e koyuyordu (Linking header gönderemediği için). Şimdi:
// Web → fetch+blob+<a> indir; Native → FileSystem.downloadAsync+header → paylaş menüsü. Token hep header'da.
import { backendBuMakinede } from "@/services/backendKonumu";

export { backendBuMakinede };

export async function downloadFileWithAuth(
  url: string,
  filename: string,
  toast?: (m: string, t?: "success" | "error" | "info") => void,
): Promise<void> {
  const headers: Record<string, string> = serviceConfig.apiToken ? { "X-API-Key": serviceConfig.apiToken } : {};
  const safeName = filename.replace(/[^\w.\-]/g, "_");
  try {
    // ── MASAÜSTÜ YOLU: dosyayı backend diske yazsın, biz yolunu söyleyelim ──────────
    if (Platform.OS === "web" && backendBuMakinede()) {
      const ayirac = url.includes("?") ? "&" : "?";
      const res = await fetch(`${url}${ayirac}kaydet=1`, { headers });
      if (!res.ok) { toast?.(`Kaydedilemedi (${res.status}).`, "error"); return; }
      const g = await res.json().catch(() => null);
      if (g?.status === "success" && g?.yol) {
        toast?.(`Masaüstüne kaydedildi: ${g.ad}`, "success");
        return;
      }
      if (g?.status === "bos") { toast?.(g.mesaj || "Dışa aktarılacak kayıt yok.", "info"); return; }
      // ⚠️ SESSİZ DÜŞME YOK: sunucu beklenmedik bir şey döndürdüyse operatöre SÖYLE.
      toast?.("Kaydedilemedi — sunucu beklenmeyen yanıt verdi.", "error");
      return;
    }
    if (Platform.OS === "web") {
      const res = await fetch(url, { headers });
      if (!res.ok) { toast?.(`İndirilemedi (${res.status}).`, "error"); return; }
      // ⚠️ "Veri bulunamadi" 200 + text/plain olarak dönüyor: eskiden bu da dosya olarak
      // indiriliyordu (içinde o metin yazan bir .csv). Kayıt yoksa TOAST göster, dosya ÜRETME.
      const tur = res.headers.get("content-type") || "";
      if (tur.startsWith("text/plain")) {
        toast?.((await res.text()).slice(0, 200) || "Dışa aktarılacak kayıt yok.", "info");
        return;
      }
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl; a.download = safeName;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(objUrl), 10000);
      // ⚠️ Başarı bildirimi ŞART: tarayıcı indirme çubuğu gizliyse (ya da bir kabuk
      // `<a download>`i yutuyorsa) operatörün elinde HİÇBİR ipucu kalmıyordu.
      toast?.(`İndirme başlatıldı: ${safeName}`, "success");
      return;
    }
    const localPath = `${FileSystem.cacheDirectory}${safeName}`;
    const { uri, status } = await FileSystem.downloadAsync(url, localPath, { headers });
    if (status !== 200) { toast?.("İndirilemedi.", "error"); return; }
    try {
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri);
      else toast?.(`İndirildi: ${safeName}`, "success");
    } finally {
      // #84 (KVKK): paylaşım/indirme SONRASI önbellekteki hasta-raporu PDF'ini SİL — aksi halde
      // hasta PII'si app cache'inde sınırsız birikir. (shareAsync resolve → share-sheet kapandı.)
      FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
    }
  } catch {
    toast?.("İndirme sırasında hata oluştu.", "error");
  }
}
