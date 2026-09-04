// Author: mertaygn, cglrgrkn
/**
 * GÖRÜNTÜ SAHNESİ YÜKSEKLİĞİ — CANLI  [S1 adım 7 / aihub-10, 2026-09-04 responsive denetimi]
 * ==========================================================================================
 * ÖLÇÜLEN DURUM: AI Hub önizleme kutusu, ısı haritası sahnesi ve Scratch sahnesi SABİT `rs(300)`
 * yükseklikteydi. Ölçek açılışta kısa kenardan bir kez hesaplandığı için PC'de kutu HER ZAMAN
 * 390 px'ti (eski tavan 1,30). Pencere 700×540'a küçültülünce (launcher asgari penceresi) üst bar,
 * kart başlığı ve düğme satırıyla birlikte kutu ekranın tamamını yiyor, "Analiz Et" düğmesi
 * kaydırmadan görünmüyordu. Yatay telefonda (yükseklik 360-430) durum daha kötüydü.
 *
 * KURAL: sahne = clamp(pencere yüksekliği × 0,45 ; rs(180) ; rs(300))
 *  · `useWindowDimensions` CANLI güncellenir → pencere küçülünce/cihaz yan yatınca kutu daralır.
 *  · Tavan rs(300): eski davranışın üst sınırı korunur (telefon dikeyde görsel fark yok).
 *  · Taban rs(180): kutu tanınmayacak kadar küçülmesin.
 *  · Kısa ekranda (yatay telefon, `isShort`) çarpan 0,40'a iner — S5 eşiğiyle tutarlı.
 *
 * ⚠️ Stil varsayılanları (`height: rs(300)`) DEĞİŞMEDEN kalır: hook'suz kullanan bir yer
 * kırılmaz, hook yalnız inline `height` ile ezer.
 */
import { useWindowDimensions } from "react-native";
import { SHORT_HEIGHT } from "@/theme/breakpoints";
import { rs } from "@/theme/tokens";

export const SAHNE_TAVAN = 300;
export const SAHNE_TABAN = 180;
export const SAHNE_ORAN = 0.45;
export const SAHNE_ORAN_KISA = 0.4;

/** Görüntü sahnesi yüksekliği (px). Pencere yüksekliğiyle CANLI değişir. */
export function useStageHeight(): number {
  const { height } = useWindowDimensions();
  const oran = height < SHORT_HEIGHT ? SAHNE_ORAN_KISA : SAHNE_ORAN;
  return Math.min(rs(SAHNE_TAVAN), Math.max(rs(SAHNE_TABAN), Math.round(height * oran)));
}
