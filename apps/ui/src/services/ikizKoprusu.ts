// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A4 — DİJİTAL İKİZ KÖPRÜSÜ (sözleşme v1, `DENETIM\GELISTIRICI-MODULLERI\ikiz-sozlesmesi-v1.md`): Simülasyon sekmesi gömülü
 * sayfaya (web iframe / mobil WebView) SALT OKUR veri gönderir.
 * =====================================================================================================================================
 * Uygulama → ikiz (veri HER ZAMAN JSON METNİ):
 *   `pemf.ikiz.durum` (2 Hz): cihaz bağlı mı · ACİL DURDUR mandalı · 7 bobin (aktif / frekans / duty % / faz / sürüş kipi / ölçülen alan) ·
 *     sensör (MLX) ölçümü · seans türü + süresi. HASTA BİLGİSİ YOK.
 *   `pemf.ikiz.alan` (1 Hz, YALNIZ ikiz `pemf.ikiz.hazir` dedikten sonra — DEMA demez, sunucu hesabı hiç başlamaz): sunucunun kalibre
 *     alan haritası (`alan_haritasi` sürüm 1) aynen — "model tahmini" bayrağı dahil.
 * İkiz → uygulama: YALNIZ `pemf.ikiz.hazir`. Başka her ileti yok sayılır; köprüde KOMUT YOLU YOKTUR (ikiz cihaza komut gönderemez).
 */
import type { AlanHaritasiVerisi } from "@/services/alanHaritasi";
import { alanGosterilebilir } from "@/utils/olculenAlan";
import { stmBobiniMi, tumSlotIdleri } from "@/services/bobinGorunurlugu";

export const IKIZ_SURUM = 1;
/** `pemf.ikiz.durum` aralığı (2 Hz — PLAN §1.2 "saniyede 2–5"). */
export const DURUM_ARALIK_MS = 500;

type Bobin = {
  id?: number;
  running?: boolean;
  frequencyHz?: number;
  dutyCycle?: number;
  phase?: number;
  unipolar?: boolean | null;
  magneticMt?: number;
  measuredFields?: string[];
  alanDogrulanamadi?: boolean;
};
type Anlik = {
  stm?: string;
  estopMandali?: { aktif?: boolean } | null;
  coils?: Bobin[];
  activeTreatment?: { isActive?: boolean; mode?: string; durationSec?: number; elapsedSec?: number } | null;
} | null;

const sayi = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Bobin alanı GERÇEKTEN ölçülüyor mu (yalnız `measuredFields`'te bildirilen ve kazancı doğrulanmış MLX). */
function olculenMt(c: Bobin): number | null {
  if (c.alanDogrulanamadi || !Array.isArray(c.measuredFields) || !alanGosterilebilir(c, "magneticMt")) return null;
  return sayi(c.magneticMt);
}

export function durumIletisi(anlik: unknown, zaman: number = Date.now() / 1000): Record<string, unknown> {
  const snapshot = anlik as Anlik;
  const coils = Array.isArray(snapshot?.coils) ? snapshot!.coils! : [];
  const bobinler = tumSlotIdleri()
    .filter(stmBobiniMi) // bobin sayısı TEK KAYNAK (D5.42) — slot 8 ESP'dir
    .map((b) => {
    const c = coils.find((x) => Number(x?.id) === b) ?? {};
    return {
      bobin: b,
      aktif: c.running === true,
      frekansHz: sayi(c.frequencyHz),
      dutyYuzde: sayi(c.dutyCycle),
      fazDerece: sayi(c.phase),
      surusKipi: c.unipolar === true ? "tek" : c.unipolar === false ? "cift" : null,
      olculenMt: olculenMt(c),
    };
  });
  let olculen: { mT: number; bobin: number } | null = null;
  for (const b of bobinler) if (b.olculenMt !== null && (olculen === null || b.olculenMt > olculen.mT)) olculen = { mT: b.olculenMt, bobin: b.bobin };
  const at = snapshot?.activeTreatment;
  return {
    tur: "pemf.ikiz.durum",
    surum: IKIZ_SURUM,
    zaman,
    cihazBagli: snapshot?.stm === "online",
    acilDurdur: snapshot?.estopMandali?.aktif === true,
    bobinler,
    olculenAlan: olculen,
    seans: at?.isActive ? { tur: String(at.mode ?? ""), sureSn: sayi(at.durationSec), gecenSn: sayi(at.elapsedSec) } : null,
  };
}

export function alanIletisi(veri: AlanHaritasiVerisi): Record<string, unknown> {
  return { ...veri, tur: "pemf.ikiz.alan", surum: IKIZ_SURUM, haritaSurumu: veri.surum };
}

/** Gömülü sayfadan gelen ileti: YALNIZ `pemf.ikiz.hazir` tanınır (JSON metni ya da nesne); gerisi null. */
export function hazirMi(veri: unknown): boolean {
  let o: unknown = veri;
  if (typeof veri === "string") {
    try {
      o = JSON.parse(veri);
    } catch {
      return false;
    }
  }
  return !!o && typeof o === "object" && (o as { tur?: unknown }).tur === "pemf.ikiz.hazir";
}
