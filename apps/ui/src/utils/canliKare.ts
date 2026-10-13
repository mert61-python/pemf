/**
 * CANLI KAMERA KİPİ — ortak kare döngüsü kuralı (SG.G5 / G6 / G4-2, sahip gözlemleri 2026-10-13).
 *
 * Ölçülen durum (`ec5e967c`): AI Hub görüntü modülleri (FGS, Segmentasyon, Termal, Retikülosit — `VisionModule`) ve Kedi Organ
 * canlı kipte `setInterval(capture, 2500 | 3500)` ile kare gönderiyor ve HER hatayı sessiz yutuyordu (`catch {}`); yalnız
 * `r.ok && status === "success"` iken sonuç gösteriliyordu. Kurulu üründe (2026-10-13 20:00–20:08) segmentasyon canlı kipinde 63 kare
 * modalite kapısından 422 aldı → ekranda HİÇBİR şey yoktu ("canlıda analiz yapmıyor"); termalde normal kamera 422 alınca son
 * teşhis ekranda kalırdı. Bu modül: (1) son karenin durumu backend'in söylediğinden türetilir ve SÜREKLİ görünür (toast yok);
 * (2) uyarlamalı aralık — önceki analiz bitince, başlangıçlar arası en az `CANLI_ASGARI_ARALIK_MS` (hızlı makinede ~1/sn, yavaşta
 * kendi hızında; kuyruk birikmez). Kural arayüzde UYDURULMAZ: "bulunamadı" ve ret metinleri backend yanıtından gelir.
 */
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";

/** Canlı karelerin başlangıçları arası en kısa süre (ms). */
export const CANLI_ASGARI_ARALIK_MS = 1000;
/** Analiz aralıktan uzun sürse de iki kare arası en az bu kadar beklenir (arayüz / kamera nefes alsın). */
export const CANLI_ASGARI_BEKLEME_MS = 250;

export type CanliDurum = { tur: "sonuc" | "bulunamadi" | "red" | "hata"; metin: string };

/** Termal makullik kapısının (`utils/image_domain.TERMAL_UYUMSUZ_MESAJI`) iletisinin değişmez parçası. */
const TERMAL_UYUMSUZ_IZI = "termal kamera görüntüsüne benzemiyor";

/** Bir sonraki karenin ne kadar sonra alınacağı (ms): başlangıçlar arası en az `CANLI_ASGARI_ARALIK_MS`. */
export function canliSonrakiBekleme(gecenMs: number): number {
  return Math.max(CANLI_ASGARI_BEKLEME_MS, CANLI_ASGARI_ARALIK_MS - Math.max(0, gecenMs));
}

/** Son canlı karenin durumu (ekranda sürekli gösterilir). `endpoint`: "/vision/landmark" | "/vision/segmentation" | … */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function canliKareDurumu(endpoint: string, ok: boolean, httpDurum: number, data: any): CanliDurum {
  if (ok && data?.status === "success") {
    if (endpoint === "/vision/landmark" && data.detected === false) {
      return { tur: "bulunamadi", metin: "Son kare: kedi yüzü bulunamadı — kedinin yüzünü kameraya karşıdan ve yakın tutun." };
    }
    if (endpoint === "/vision/segmentation" && Number(data.cat_count) === 0) {
      return { tur: "bulunamadi", metin: "Son kare: kedi bulunamadı — kedinin tümü kadraja girsin." };
    }
    if (typeof data.bulunamadi_mesaji === "string" && data.bulunamadi_mesaji) {
      return { tur: "bulunamadi", metin: `Son kare: ${data.bulunamadi_mesaji}` };
    }
    const g = data.girdi_dogrulama;
    if (g && g.dogrulandi === false && typeof g.uyari === "string" && g.uyari) {
      return { tur: "sonuc", metin: `Son kare analiz edildi — ${g.uyari}` };
    }
    return { tur: "sonuc", metin: "Son kare analiz edildi." };
  }
  const detay = aiDetayCumlesi(data?.detail, `sunucu yanıtı ${httpDurum}`);
  if (endpoint === "/vision/thermal" && httpDurum === 422 && detay.includes(TERMAL_UYUMSUZ_IZI)) {
    return { tur: "red", metin: `Seçili kamera termal görüntü vermiyor — termal kamerayı seçin. (${detay})` };
  }
  return { tur: "red", metin: `Son kare analiz edilemedi: ${detay}` };
}
