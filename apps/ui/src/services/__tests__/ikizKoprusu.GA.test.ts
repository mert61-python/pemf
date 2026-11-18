// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A4 — dijital ikiz köprüsü sözleşme v1 iletileri: `pemf.ikiz.durum` alanları (HASTA BİLGİSİ YOK, ölçülmeyen alan null,
 * sürüş kipi, mandal, seans), `pemf.ikiz.alan` sunucu haritasını aynen taşır, gelen iletiden YALNIZ `pemf.ikiz.hazir` tanınır.
 */
import { DURUM_ARALIK_MS, IKIZ_SURUM, alanIletisi, durumIletisi, hazirMi } from "@/services/ikizKoprusu";

describe("GA A4 ikiz köprüsü iletileri", () => {
  it("durum: alanlar, hasta bilgisi YOK, ölçülmeyen alan null", () => {
    expect(IKIZ_SURUM).toBe(1);
    expect(DURUM_ARALIK_MS).toBe(500); // 2 Hz
    const d = durumIletisi(
      {
        stm: "online",
        estopMandali: { aktif: true },
        patient: { name: "Boncuk", owner: "Ayşe" },
        activeTreatment: { isActive: true, mode: "Manuel", durationSec: 1800, elapsedSec: 12, patientName: "Boncuk" },
        coils: [
          { id: 1, running: true, frequencyHz: 100, dutyCycle: 25, phase: 90, unipolar: false, magneticMt: 0.9, measuredFields: ["magneticMt"] },
          { id: 2, running: false, frequencyHz: Number.NaN, dutyCycle: "x", unipolar: null, magneticMt: 5, measuredFields: [] },
          { id: 6, running: true, frequencyHz: 107, dutyCycle: 40, unipolar: true, magneticMt: 1.2, measuredFields: ["magneticMt"] },
          { id: 7, running: true, magneticMt: 9, measuredFields: ["magneticMt"], alanDogrulanamadi: true },
          { id: 3, magneticMt: 3, measuredFields: undefined },
          { id: 8, running: true, frequencyHz: 50 },
        ],
      },
      123.5,
    );
    expect(Object.keys(d).sort()).toEqual(["acilDurdur", "bobinler", "cihazBagli", "olculenAlan", "seans", "surum", "tur", "zaman"]);
    expect(JSON.stringify(d)).not.toMatch(/Boncuk|Ayşe|patient/);
    expect(d).toMatchObject({ tur: "pemf.ikiz.durum", surum: 1, zaman: 123.5, cihazBagli: true, acilDurdur: true });
    expect(d.seans).toEqual({ tur: "Manuel", sureSn: 1800, gecenSn: 12 });
    const b = d.bobinler as Record<string, unknown>[];
    expect(b.map((x) => x.bobin)).toEqual([1, 2, 3, 4, 5, 6, 7]); // yalnız STM 1–7 (slot 8 ESP değil)
    expect(b[0]).toEqual({ bobin: 1, aktif: true, frekansHz: 100, dutyYuzde: 25, fazDerece: 90, surusKipi: "cift", olculenMt: 0.9 });
    expect(b[1]).toEqual({ bobin: 2, aktif: false, frekansHz: null, dutyYuzde: null, fazDerece: null, surusKipi: null, olculenMt: null });
    expect(b[2].olculenMt).toBeNull(); // ölçüm bilgisi yok
    expect(b[3]).toEqual({ bobin: 4, aktif: false, frekansHz: null, dutyYuzde: null, fazDerece: null, surusKipi: null, olculenMt: null });
    expect(b[5]).toMatchObject({ surusKipi: "tek", olculenMt: 1.2 });
    expect(b[6].olculenMt).toBeNull(); // kazanç doğrulanamadı
    expect(d.olculenAlan).toEqual({ mT: 1.2, bobin: 6 });
  });

  it("durum: boş / bağlantısız anlık görüntü; seans yokken null; zaman varsayılanı şimdi", () => {
    const d = durumIletisi(null);
    expect(d).toMatchObject({ cihazBagli: false, acilDurdur: false, olculenAlan: null, seans: null });
    expect(Math.abs((d.zaman as number) - Date.now() / 1000)).toBeLessThan(5);
    expect((d.bobinler as unknown[]).length).toBe(7);
    const e = durumIletisi({ stm: "offline", activeTreatment: { isActive: true }, coils: "x" });
    expect(e.seans).toEqual({ tur: "", sureSn: null, gecenSn: null });
    expect(durumIletisi({ activeTreatment: { isActive: false } }).seans).toBeNull();
  });

  it("alan: sunucu haritası AYNEN + tür / sürüm", () => {
    const v = { surum: 1, durum: "tamam", zaman: 9, modelTahmini: true, deger: "AAA=", olcek: 0.01 };
    expect(alanIletisi(v)).toEqual({ ...v, tur: "pemf.ikiz.alan", surum: 1, haritaSurumu: 1 });
  });

  it("gelen: YALNIZ pemf.ikiz.hazir", () => {
    expect(hazirMi('{"tur":"pemf.ikiz.hazir","surum":1}')).toBe(true);
    expect(hazirMi({ tur: "pemf.ikiz.hazir" })).toBe(true);
    expect(hazirMi('{"tur":"pemf.ikiz.komut","bobin":1}')).toBe(false);
    expect(hazirMi("1840")).toBe(false); // DEMA yükseklik iletisi
    expect(hazirMi("bozuk{")).toBe(false);
    expect(hazirMi(null)).toBe(false);
    expect(hazirMi(42)).toBe(false);
  });
});
