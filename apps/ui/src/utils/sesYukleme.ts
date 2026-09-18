/**
 * Ses dosyasını analiz isteğine EKLEME — web ve native için TEK yer.
 *
 * ⚠️ SAHA HATASI (2026-08-15, laptop/web): "Hata: The method or property
 * expo-file-system.readAsStringAsync is not available on web".
 *
 * SEBEP: AiHubScreen'de iki ayrı yol vardı ve web'de yalnız BİRİ `webFile` üretiyordu:
 *   • Dosya seç (web)  → `<input type=file>` → gerçek `File` nesnesi → `webFile` DOLU  ✔
 *   • Canlı kayıt (web) → `recorder.uri` (bir `blob:` URL) → `webFile` BOŞ BIRAKILIYOR �’
 * `analyze()` de `Platform.OS === 'web' && webFile` diye bakıyordu; kayıt yolunda ikinci
 * koşul tutmayınca NATIVE dalına düşüp `expo-file-system` çağırıyordu — o modül web'de
 * yoktur → kullanıcı ses kaydedip "Analiz Et" deyince çöküyordu. Yani web'de canlı kayıt
 * ANALİZ EDİLEMİYORDU; sorun kaydın kendisinde değil, yükleme dalının seçiminde.
 *
 * ÇÖZÜM: platformu değil, ELDEKİ VERİYİ sor. Web'de `blob:`/`http(s):` bir URI da
 * `fetch` ile gerçek bir `Blob`a çevrilebilir — yani kayıt da tıpkı seçilen dosya gibi
 * multipart'a eklenebilir. `expo-file-system` ARTIK YALNIZ native'de çağrılır.
 */

export type SesKaynagi = {
  /** Web'de `<input type=file>`'dan gelen gerçek dosya (varsa). */
  webFile?: File | null;
  /** Kayıt/seçim sonucu URI. Web'de `blob:`, native'de `file://`. */
  uri?: string | null;
  /** Sunucuya gidecek dosya adı. */
  fileName?: string | null;
};

/** `pickAudio` web dalının `audioUri`ye koyduğu nöbetçi değer — gerçek bir URI DEĞİLDİR. */
const WEB_NOBETCI = "web";

export const VARSAYILAN_SES_ADI = "kayit.m4a";

/**
 * Web'de bir URI'yi (blob:/http:) `File`a çevir.
 *
 * MediaRecorder'ın ürettiği `blob:` URL aynı origin'dedir ve `fetch` ile okunabilir;
 * bu, tarayıcıda dosya okumanın standart yoludur (ve `expo-file-system` gerektirmez).
 */
export async function uriyiDosyayaCevir(uri: string, ad: string): Promise<File> {
  const yanit = await fetch(uri);
  if (!yanit.ok) throw new Error(`Kayıt okunamadı (HTTP ${yanit.status}).`);
  const blob = await yanit.blob();
  if (blob.size === 0) throw new Error("Kayıt boş — ses alınamamış olabilir.");
  // `type` boş kalabilir (bazı tarayıcılarda blob: URL'de MIME kaybolur); sunucu ffmpeg ile
  // formatı zaten içerikten çözüyor, bu yüzden makul bir varsayılan yeterli.
  return new File([blob], ad, { type: blob.type || "audio/mp4" });
}

/**
 * Analiz isteği için `FormData` hazırla.
 *
 * @param web        Platform.OS === 'web' mi (çağıran verir; bu modül Platform'a bağlı değil → test edilebilir).
 * @param nativeOku  Native'de URI'yi base64 okuyan fonksiyon (expo-file-system). Web'de ÇAĞRILMAZ.
 */
export async function sesFormDataHazirla(
  kaynak: SesKaynagi,
  web: boolean,
  nativeOku: (uri: string) => Promise<string>,
): Promise<FormData> {
  const ad = kaynak.fileName || VARSAYILAN_SES_ADI;
  const form = new FormData();

  if (web) {
    // Öncelik seçilen dosya; yoksa kayıt URI'sini Blob'a çevir. İkisi de yoksa hata.
    let dosya = kaynak.webFile ?? null;
    if (!dosya) {
      const uri = kaynak.uri;
      if (!uri || uri === WEB_NOBETCI) throw new Error("Analiz edilecek ses yok.");
      dosya = await uriyiDosyayaCevir(uri, ad);
    }
    form.append("file", dosya, ad);
    return form;
  }

  if (!kaynak.uri) throw new Error("Analiz edilecek ses yok.");
  // Native: RN multipart `file://` URI'sini doğrudan okuyamıyor (ağ hatası) → base64.
  const b64 = await nativeOku(kaynak.uri);
  form.append("audio_base64", b64);
  return form;
}
