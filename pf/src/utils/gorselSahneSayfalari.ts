// Author: mertaygn
/**
 * GÖRSEL SAHNE SAYFALARI — AI yanıtını galeri sayfalarına çevirir. [AI Hub planı, ADIM 4]
 * =====================================================================================
 * ÖLÇÜLEN İKİ ARIZA (2026-09-09 sahip bildirimi):
 *
 * 1. **GİRDİ KAYBOLUYOR.** `AiHubScreen.tsx`'te BEŞ yerde birebir aynı satır vardı:
 *      `source={{ uri: result?.image_base64 ? 'data:...' : imageUri }}`
 *    Sonuç gelir gelmez kullanıcının kendi fotoğrafı ekrandan SİLİNİYOR ve bir daha
 *    erişilemiyordu. Veri kaybı yok (state + visionCache duruyor) — salt gösterim.
 *    ⚠️ Fantom/petri'de sunucu `image_base64`'ü `no_detection` yolunda da gönderdiği için
 *    ternary GİRDİ dalına **asla** düşmüyordu.
 *
 * 2. **SONUÇ OKUNMAZ.** `07_combined` 2×3 bir mozaik. Dikey telefon fotoğrafında 6048×12256'ya
 *    çıkıyor; sahne tavanına (~330 px) sığdırılınca panel başına ~81 px kalıyor, gömülü ~12 px
 *    metin ~0,35 px'e iniyor. ⚠️ Oran kilidi bunu ÇÖZMEZ (mozaik uzun-ince) — çözüm panellere
 *    bölmek + tam ekran/zoom.
 *
 * Backend (ADIM 3) artık 7 paneli de yayınlıyor (`utils/panel_yayin.py`). Bu modül o yükü
 * gezilebilir sayfalara çevirir ve İKİ arızayı da tek kuralla kapatır.
 *
 * ⚠️ `01_input` SAYFASI YEREL DOSYAYI GÖSTERİR, sunucunun kopyasını DEĞİL. Sunucunun `01_input`
 * paneli yeniden kodlanmış (kapak 1600 px + JPEG %85) bir kopyadır; kullanıcının gördüğü "Girdi"
 * ise KENDİ çektiği kare olmalı. Böylece hem 1. arıza kapanır hem de çip satırında iki ayrı
 * "Girdi" belirmez.
 *
 * ⚠️ `toLowerCase()` KULLANILMAZ — Türkçe collation (I/İ/ı) sessiz "panel yok" üretir. Anahtarlar
 * sabit ASCII literal olarak karşılaştırılır (bkz. `turkce-collation-lower-tuzagi`).
 */

/** Backend'in `paneller` öğesi (ADIM 3 sözleşmesi). */
export interface PanelYanit {
  k: string;
  ad?: string;
  image_base64?: string | null;
  image_w?: number | null;
  image_h?: number | null;
}

/** Sahnenin gezdiği tek sayfa. */
export interface SahneSayfasi {
  /** Panel anahtarı (`01_input`, `07_combined`, …) — çip `testID`'si bundan türer. */
  k: string;
  /** Çipte görünen ad. */
  ad: string;
  /** `<Image source={{uri}}>` değeri: yerel dosya yolu ya da `data:` URI. */
  uri: string;
  /** Kodlanan karenin boyutu — oran kilidi ve 1:1 zoom basamağı bunu okur. */
  image_w?: number | null;
  image_h?: number | null;
}

/** Girdi panelinin anahtarı — yerel dosyayla DEĞİŞTİRİLEN tek panel. */
export const GIRDI_ANAHTARI = "01_input";
/** Mozaik panelin anahtarı. */
export const BIRLESIK_ANAHTARI = "07_combined";

/**
 * Varsayılan açılış sayfası tercih sırası (ilk bulunan seçilir).
 *
 * ⚠️ BİLİNÇLİ KARAR (plan §8, 2026-09-12): varsayılan **`07_combined` DEĞİL**. Mozaik
 * yapısı gereği okunmazdır (6 panel tek karede); onu varsayılan yapmak, düzeltilmeye
 * çalışılan şikâyetin ilk bakışta AYNEN sürmesi demekti. `06_predictions` analizin
 * sonucunu tek başına ve okunur boyutta gösterir; "Birleşik" bir çip uzaklıkta.
 * ⚠️ GİRDİ ASLA VARSAYILAN DEĞİL: kullanıcı analiz sonucunu görmek için bastı.
 */
export const VARSAYILAN_SAYFA_SIRASI = ["06_predictions", BIRLESIK_ANAHTARI];

/** Panelsiz (tek görselli) modüllerde sonuç sayfasının adı. */
export const SONUC_ADI = "Sonuç";
/** Girdi sayfasının adı. */
export const GIRDI_ADI = "Girdi";

interface YanitBenzeri {
  paneller?: PanelYanit[] | null;
  image_base64?: string | null;
  image_w?: number | null;
  image_h?: number | null;
}

function _dataUri(b64: string): string {
  return `data:image/jpeg;base64,${b64}`;
}

/**
 * AI yanıtı + yerel görsel → galeri sayfaları.
 *
 * @param yanit     Backend yanıtı (`paneller` varsa çok panelli, yoksa tek görselli).
 * @param yerelUri  Kullanıcının seçtiği/çektiği dosyanın yerel URI'si (yoksa `null`).
 * @returns Gezilebilir sayfa listesi; hiçbir görsel yoksa **boş dizi**.
 *
 * ⚠️ ZARİF DÜŞÜŞ (G5): backend `paneller` göndermezse (eski backend ya da panelsiz modül)
 * iki sayfa üretilir: Girdi + Sonuç. `undefined`/boş `image_base64` olan panel ATLANIR —
 * aksi halde `source.uri` `"data:image/jpeg;base64,undefined"` olur ve `<Image>` sessizce
 * boş bir kutu çizerdi (kullanıcıya hiçbir şey söylemeden).
 */
export function sahneSayfalari(yanit: YanitBenzeri | null | undefined, yerelUri: string | null | undefined): SahneSayfasi[] {
  const sayfalar: SahneSayfasi[] = [];
  const paneller = yanit?.paneller;

  if (Array.isArray(paneller) && paneller.length > 0) {
    for (const p of paneller) {
      if (!p || typeof p.k !== "string") continue;
      // ⚠️ Girdi paneli YEREL dosyayla değiştirilir (yukarıdaki gerekçe) — ama SUNUCUNUN
      // BİLDİRDİĞİ BOYUT KORUNUR. Sunucunun `01_input` kopyası aynı fotoğraftır, yalnız
      // yeniden kodlanmıştır; dolayısıyla ORANI birebir aynıdır ve kutu oran kilidi onu okur.
      // ⚠️ Boyut düşürülseydi Girdi sayfası yön varsayılanına (4:3) düşerdi: dikey bir telefon
      // fotoğrafı kutunun ~%44'ünü boş bırakır ve sonuç panellerinin yanında bozuk görünürdü —
      // üstelik bu, sahibin "girdi kayboluyor" şikâyeti için açtığımız sayfanın ta kendisi.
      if (p.k === GIRDI_ANAHTARI) {
        if (yerelUri) {
          sayfalar.push({
            k: p.k,
            ad: p.ad || GIRDI_ADI,
            uri: yerelUri,
            image_w: p.image_w,
            image_h: p.image_h,
          });
        }
        continue;
      }
      if (!p.image_base64) continue; // boş panel: sessiz `undefined` uri üretme
      sayfalar.push({
        k: p.k,
        ad: p.ad || p.k,
        uri: _dataUri(p.image_base64),
        image_w: p.image_w,
        image_h: p.image_h,
      });
    }
    return sayfalar;
  }

  // Panelsiz yol: Girdi + Sonuç.
  if (yerelUri) sayfalar.push({ k: GIRDI_ANAHTARI, ad: GIRDI_ADI, uri: yerelUri });
  if (yanit?.image_base64) {
    sayfalar.push({
      k: BIRLESIK_ANAHTARI,
      ad: SONUC_ADI,
      uri: _dataUri(yanit.image_base64),
      image_w: yanit.image_w,
      image_h: yanit.image_h,
    });
  }
  return sayfalar;
}

/**
 * Açılışta gösterilecek sayfanın indeksi.
 *
 * ⚠️ "Birincil sonuç" kuralı (G3): girdi sayfası ASLA varsayılan değildir. Tercih sırası
 * `VARSAYILAN_SAYFA_SIRASI`; hiçbiri yoksa girdi DIŞINDAKİ ilk sayfa; o da yoksa 0.
 */
export function varsayilanSayfa(sayfalar: SahneSayfasi[]): number {
  if (!sayfalar.length) return 0;
  for (const tercih of VARSAYILAN_SAYFA_SIRASI) {
    const i = sayfalar.findIndex((s) => s.k === tercih);
    if (i >= 0) return i;
  }
  const ilkSonuc = sayfalar.findIndex((s) => s.k !== GIRDI_ANAHTARI);
  return ilkSonuc >= 0 ? ilkSonuc : 0;
}
