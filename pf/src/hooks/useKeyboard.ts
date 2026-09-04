// Author: mertaygn, cglrgrkn
/**
 * KLAVYE DURUMU + KeyboardAvoidingView davranışı — tek kaynak  [S4, 2026-09-04 denetimi]
 * =====================================================================================
 * ÖLÇÜLEN DURUM: `KeyboardAvoidingView` uygulamada YALNIZ AuthScreen'de vardı (grep). Hasta formu,
 * seans gözlem notu, CKD formu (14 alan), ayarlar ve bobin parametrelerinde klavye açılınca
 * odaklanılan giriş ve onun "Kaydet/Başlat" düğmesi klavyenin altında kalıyordu.
 *
 * İKİ FARKLI DAVRANIŞ, TEK KAYNAK:
 *  · KAV_BEHAVIOR_PENCERE — normal ekranlar. iOS'ta ve Android 11+ (API 30) edge-to-edge
 *    pencerede aktivite klavyeyle DARALMAZ → 'padding' gerekir.
 *  · KAV_BEHAVIOR_MODAL — RN `Modal` içindekiler. Android'de Modal KENDİ penceresini açar ve
 *    adjustResize ile zaten daralır; üstüne padding eklemek ÇİFT boşluk yapar → yalnız iOS.
 *
 * Web'de (RNW) Keyboard olayı yayılmaz ve KAV no-op'tur → masaüstü/LAN yüzeyleri etkilenmez.
 *
 * ⚠️ HASTA GÜVENLİĞİ: klavye açıkken ACİL DURDUR GİZLENMEZ; kabuk düğmeyi klavyenin ÜSTÜNE taşır
 * (sahip kararı 2026-09-04). `yukseklik` bunun için vardır.
 */
import { useEffect, useState } from "react";
import { Keyboard, Platform } from "react-native";

/** Normal ekranlar (AppShell içeriği, Auth) için KAV davranışı. */
export const KAV_BEHAVIOR_PENCERE: "padding" | undefined =
  Platform.OS === "ios"
    ? "padding"
    : Platform.OS === "android" && typeof Platform.Version === "number" && Platform.Version >= 30
      ? "padding"
      : undefined;

/** RN `Modal` içindeki alt-sayfa/diyaloglar için KAV davranışı (Android kendi penceresini daraltır). */
export const KAV_BEHAVIOR_MODAL: "padding" | undefined = Platform.OS === "ios" ? "padding" : undefined;

export interface KlavyeDurumu {
  acik: boolean;
  /** Klavyenin kapladığı yükseklik (px). Web'de her zaman 0. */
  yukseklik: number;
}

/** Klavye açık mı ve ne kadar yer kaplıyor? (native; web'de sabit kapalı) */
export function useKeyboard(): KlavyeDurumu {
  const [durum, setDurum] = useState<KlavyeDurumu>({ acik: false, yukseklik: 0 });

  useEffect(() => {
    if (Platform.OS === "web") return; // RNW Keyboard olayı yaymaz → abone olma
    const gosterOlay = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const gizleOlay = Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";
    const acilis = Keyboard.addListener(gosterOlay as "keyboardDidShow", (e) =>
      setDurum({ acik: true, yukseklik: Math.round(e?.endCoordinates?.height ?? 0) })
    );
    const kapanis = Keyboard.addListener(gizleOlay as "keyboardDidHide", () =>
      setDurum({ acik: false, yukseklik: 0 })
    );
    return () => {
      acilis.remove();
      kapanis.remove();
    };
  }, []);

  return durum;
}
