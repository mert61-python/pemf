// Author: mertaygn, cglrgrkn
/**
 * backendKonumu — "backend bu makinede mi?" kararı TEK kaynakta, yerel modül (expo-file-system / expo-sharing) bağımlılığı OLMADAN.
 *
 * ⚠️ 2-D (D2.E01): Ayarlar'daki şifreli yedek de bu kararı kullanır. Karar eskiden yalnız `dosyaIndir.ts`'teydi; onu Ayarlar ekranına
 * almak jest'te `expo-sharing` yerel modülünü çekip ekranı render eden süitleri YÜKLETMİYORDU (ölçüldü: "Cannot find native module
 * 'ExpoSharing'"). `dosyaIndir` bu işlevi buradan yeniden dışa aktarır — mevcut içe aktarımlar değişmez.
 */
import { serviceConfig } from "@/services/config";

/**
 * Backend BU MAKİNEDE mi koşuyor?
 *
 * ⚠️ 2026-09-11 SAHA ARIZASI: "Excel/CSV İndir" ve "Tümünü PDF İndir" düğmeleri masaüstü
 * uygulamasında HİÇBİR ŞEY YAPMIYORDU. Arayüz Tauri v2 **WebView2** penceresinde koşuyor
 * ve `<a download>` orada ancak uygulama bir indirme işleyicisi kaydederse çalışır —
 * `launcher/app/src/main.rs` hiçbir `on_download`/dialog/fs eklentisi KAYDETMİYOR.
 * Tıklama sessizce ölüyordu; üstelik kod `a.click()`ten sonra hiçbir geri bildirim
 * vermediği için "çalıştı" ile "öldü" AYNI görünüyordu.
 *
 * Backend aynı makinede koştuğunda dosyayı ONA yazdırmak sorunu Tauri'ye hiç dokunmadan
 * çözer (launcher yeniden yayınlanmak zorunda kalmaz — sahada tek makine var, yayın durdu).
 *
 * ⚠️ SADECE YEREL: uzak/LAN backend'de `kaydet=1` dosyayı KARŞI MAKİNENİN masaüstüne
 * yazardı — operatör dosyayı asla göremezdi. O yüzden yalnız localhost/127.0.0.1 kabul
 * edilir ve tarayıcı/mobil yolu olduğu gibi korunur.
 */
export function backendBuMakinede(): boolean {
  try {
    const u = new URL(serviceConfig.apiBaseUrl, "http://localhost");
    return u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "::1";
  } catch {
    return false;
  }
}
