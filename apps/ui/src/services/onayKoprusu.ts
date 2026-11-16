// Author: mertaygn, cglrgrkn
/**
 * UYGULAMA İÇİ ONAY / UYARI PENCERESİ KÖPRÜSÜ — YH-A4 (Tezgâh-2 listesi 4, 13 Kasım 2026).
 *
 * ÖLÇÜLEN KUSUR: masaüstü uygulama penceresi (başlatıcının web görünümü) `platformConfirm` / `platformAlert`te tarayıcının YERLİ
 * `window.confirm` / `window.alert` penceresini açıyordu → başlıkta "127.0.0.1:8000 şunu diyor:" (EN "127.0.0.1:8000 says")
 * yazıyor, uygulamanın görünümünü ve dilini taşımıyordu (Sürüş Kipi, ACİL DURDUR mandalı "Sıfırla", hasta / kayıt silme …).
 *
 * Servis katmanı (apiClient) React hook'u kullanamaz → `toastBridge` deseni: `OnayPenceresiSaglayici` takılınca
 * `setOnayIsleyici` ile kaydolur; kayıtlı değilse (takılmadan önce / sağlayıcısız jest ağacı) `uygulamaIciOnay` null döner ve
 * çağıran ESKİ yerli pencereye düşer (onay sorusu hiçbir durumda sessizce "evet" sayılmaz). Telefonda (native) DEĞİŞMEZ: orada
 * `Alert.alert` zaten uygulamanın kendi penceresidir.
 */

export type OnayTuru = "onay" | "uyari";

export interface OnayIstegi {
  baslik: string;
  govde: string;
  /** Onay düğmesinin etiketi (yalnız `onay` türü); verilmezse "Onayla". */
  onayEtiketi?: string;
  tur: OnayTuru;
}

type Isleyici = (istek: OnayIstegi) => Promise<boolean>;

let _isleyici: Isleyici | null = null;

export function setOnayIsleyici(fn: Isleyici | null): void {
  _isleyici = fn;
}

/** Kayıtlı uygulama içi pencere varsa açar ve yanıtın sözünü döner (onay → true, vazgeç / kapat → false; uyarı kapanınca
 *  true); kayıtlı değilse ya da işleyici patlarsa null → çağıran yerli pencereye düşer. */
export function uygulamaIciOnay(istek: OnayIstegi): Promise<boolean> | null {
  if (!_isleyici) return null;
  try {
    return _isleyici(istek);
  } catch {
    return null;
  }
}
