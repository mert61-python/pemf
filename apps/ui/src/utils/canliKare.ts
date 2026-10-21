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
import i18n from "i18next";

/**
 * TD9 (Y148): canlı kip jetonu DAKİKA BAŞINA. Her canlı kare isteği oturum kimliğini bu başlıkla taşır; backend
 * (`servers/jeton.py`) oturumun ilk karesinden itibaren 60 sn'lik kova başına, yalnız SONUÇ teslim edilen kovada 1 jeton düşer.
 */
export const CANLI_OTURUM_BASLIGI = "X-PEMF-Canli-Oturum";

export interface CanliOturum {
  kimlik: string;
  /** Kare GÖNDERİLDİĞİ an (ms) + sonucu: sayaç backend kuralının aynası (yalnız "sonuc" kovası sayılır). */
  kareBildir(durum: CanliDurum, gonderimMs: number): void;
  jetonSayisi(): number;
}

/** Yeni canlı oturum: rastgele kimlik + ücretlenen dakika sayacı (backend kuralının AYNASI; tahmin — kesin defter sunucuda). */
export function canliOturumBaslat(): CanliOturum {
  const kimlik = `canli-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  let t0: number | null = null;
  const kovalar = new Set<number>();
  return {
    kimlik,
    kareBildir(durum, gonderimMs) {
      if (t0 === null) t0 = gonderimMs;
      if (durum.tur === "sonuc") kovalar.add(Math.floor((gonderimMs - t0) / 60000));
    },
    jetonSayisi: () => kovalar.size,
  };
}

/** [ÖNERİLEN] sayaç metni — yalnız ücretlendirme ETKİNKEN gösterilir (kapalıyken "0 jeton" yazmak yanlış bilgi olurdu). */
export function canliJetonMetni(n: number): string {
  return i18n.t("ai.canli.jetonMetni", { count: n });
}

/** Canlı karelerin başlangıçları arası en kısa süre (ms). */
export const CANLI_ASGARI_ARALIK_MS = 1000;
/** Analiz aralıktan uzun sürse de iki kare arası en az bu kadar beklenir (arayüz / kamera nefes alsın). */
export const CANLI_ASGARI_BEKLEME_MS = 250;

export type CanliDurum = { tur: "sonuc" | "bulunamadi" | "red" | "hata"; metin: string };

/** Termal makullik kapısının (`utils/image_domain.TERMAL_UYUMSUZ_MESAJI`) iletisinin değişmez parçası. */
const TERMAL_UYUMSUZ_IZI = "termal kamera görüntüsüne benzemiyor";
/** EN ikizi (S-I18N-P1.1): sunucu iletisi İSTEK DİLİNDE gelir → `ai.kapi.termal.uyumsuz` İngilizce değeri bu parçayı içerir (`tests/test_kimlik_db_oneki_iki_dilde_P1.py` kilitler). */
const TERMAL_UYUMSUZ_IZI_EN = "does not look like a thermal camera image";

/** Bir sonraki karenin ne kadar sonra alınacağı (ms): başlangıçlar arası en az `CANLI_ASGARI_ARALIK_MS`. */
export function canliSonrakiBekleme(gecenMs: number): number {
  return Math.max(CANLI_ASGARI_BEKLEME_MS, CANLI_ASGARI_ARALIK_MS - Math.max(0, gecenMs));
}

/** Son canlı karenin durumu (ekranda sürekli gösterilir). `endpoint`: "/vision/landmark" | "/vision/segmentation" | … */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function canliKareDurumu(endpoint: string, ok: boolean, httpDurum: number, data: any): CanliDurum {
  if (ok && data?.status === "success") {
    if (endpoint === "/vision/landmark" && data.detected === false) {
      return { tur: "bulunamadi", metin: i18n.t("ai.canli.durum.yuzYok") };
    }
    if (endpoint === "/vision/segmentation" && Number(data.cat_count) === 0) {
      return { tur: "bulunamadi", metin: i18n.t("ai.canli.durum.kediYok") };
    }
    if (typeof data.bulunamadi_mesaji === "string" && data.bulunamadi_mesaji) {
      return { tur: "bulunamadi", metin: i18n.t("ai.canli.durum.bulunamadi", { bulunamadi_mesaji: data.bulunamadi_mesaji }) };
    }
    const g = data.girdi_dogrulama;
    if (g && g.dogrulandi === false && typeof g.uyari === "string" && g.uyari) {
      return { tur: "sonuc", metin: i18n.t("ai.canli.durum.analizEdildiUyari", { uyari: g.uyari }) };
    }
    return { tur: "sonuc", metin: i18n.t("ai.canli.durum.analizEdildi") };
  }
  const detay = aiDetayCumlesi(data?.detail, i18n.t("ai.canli.sunucuYaniti", { httpDurum }));
  if (endpoint === "/vision/thermal" && httpDurum === 422 && (detay.includes(TERMAL_UYUMSUZ_IZI) || detay.includes(TERMAL_UYUMSUZ_IZI_EN))) {
    return { tur: "red", metin: i18n.t("ai.canli.durum.termalYok", { detay }) };
  }
  return { tur: "red", metin: i18n.t("ai.canli.durum.analizEdilemedi", { detay }) };
}
