// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A3 — `alan_haritasi` iletisinin çözücüsü: base64 → 8 bit, tutarsız ileti ÇİZİLMEZ, katman indeksi, kesit yönü
 * (üstten bakış: sütun 0 = önden bakanın SOLU = en büyük X, satır 0 = ARKA = en büyük Z), 255 = tablo dışı → null, renk ölçeği, Y295 biçimi.
 */
import i18n from "i18next";
import {
  KATMANLAR,
  base64Coz,
  haritayiCoz,
  katmanIndeksi,
  kesit,
  kesitEnBuyuk,
  mTBicimle,
  renk,
  type AlanHaritasiVerisi,
} from "@/services/alanHaritasi";

/** nx=3, ny=2, nz=2 — kod[(ix*ny + iy)*nz + iz] = 10*ix + 3*iy + iz, (2,0,1) tablo dışı. */
function ornek(ek: Partial<AlanHaritasiVerisi> = {}): AlanHaritasiVerisi {
  const kod: number[] = [];
  for (let ix = 0; ix < 3; ix++) for (let iy = 0; iy < 2; iy++) for (let iz = 0; iz < 2; iz++) kod.push(10 * ix + 3 * iy + iz);
  kod[(2 * 2 + 0) * 2 + 1] = 255;
  return {
    surum: 1,
    durum: "tamam",
    zaman: 1,
    modelTahmini: true,
    izgara: { kok: [-20, -170, -10], adim: 20, boyut: [3, 2, 2], cerceve: "kabin", camIc: [70, 350, 40] },
    deger: Buffer.from(kod).toString("base64"),
    olcek: 0.01,
    yok: 255,
    ...ek,
  };
}

describe("GA A3 alan haritası çözücüsü", () => {
  afterEach(async () => {
    await i18n.changeLanguage("tr");
  });

  it("base64: doğru çözer; geçersiz karakter / uzunluk → null", () => {
    expect(Array.from(base64Coz(Buffer.from([0, 1, 254, 255, 7]).toString("base64")) as Uint8Array)).toEqual([0, 1, 254, 255, 7]);
    expect(Array.from(base64Coz("") as Uint8Array)).toEqual([]);
    expect(base64Coz("ab$c")).toBeNull();
    expect(base64Coz("abcde")).toBeNull();
  });

  it("tutarsız / eksik ileti ÇİZİLMEZ (null)", () => {
    expect(haritayiCoz(null)).toBeNull();
    expect(haritayiCoz(undefined)).toBeNull();
    expect(haritayiCoz(ornek({ durum: "sifir" }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: undefined }))).toBeNull();
    expect(haritayiCoz(ornek({ deger: undefined }))).toBeNull();
    const iz = ornek().izgara!;
    expect(haritayiCoz(ornek({ izgara: { ...iz, kok: [0, 0] } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, boyut: [3, 2] } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, boyut: [3, 2, 0] } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, boyut: [3, 2, 1.5] } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, adim: 0 } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, kok: "x" as unknown as number[] } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, boyut: "x" as unknown as number[] } }))).toBeNull();
    expect(haritayiCoz(ornek({ izgara: { ...iz, boyut: [3, 2, 3] } }))).toBeNull(); // değer sayısı tutmaz
    expect(haritayiCoz(ornek({ deger: "$$$$" }))).toBeNull();
  });

  it("geçerli ileti: ölçek / yok varsayılanları", () => {
    const h = haritayiCoz(ornek())!;
    expect(h.boyut).toEqual([3, 2, 2]);
    expect(h.kok).toEqual([-20, -170, -10]);
    expect(h.olcek).toBe(0.01);
    expect(h.yok).toBe(255);
    expect(haritayiCoz(ornek({ olcek: undefined }))!.olcek).toBe(0);
    expect(haritayiCoz(ornek({ olcek: -1 }))!.olcek).toBe(0);
    expect(haritayiCoz(ornek({ yok: undefined }))!.yok).toBe(255);
    expect(haritayiCoz(ornek({ yok: 0 }))!.yok).toBe(0);
  });

  it("katman: taban = en alt (plaka), orta = alttaki orta, tavan = en üst", () => {
    expect(KATMANLAR).toEqual(["taban", "orta", "tavan"]);
    const h = haritayiCoz(ornek())!;
    expect(katmanIndeksi(h, "taban")).toBe(0);
    expect(katmanIndeksi(h, "orta")).toBe(0);
    expect(katmanIndeksi(h, "tavan")).toBe(1);
    const h18 = { ...h, boyut: [28, 18, 21] as [number, number, number] };
    expect([katmanIndeksi(h18, "taban"), katmanIndeksi(h18, "orta"), katmanIndeksi(h18, "tavan")]).toEqual([0, 8, 17]);
  });

  it("kesit: ÜSTTEN bakış — sütun 0 = SOL (+X en büyük), satır 0 = ARKA (+Z en büyük); 255 → null", () => {
    const h = haritayiCoz(ornek())!;
    const s = kesit(h, 1);
    expect(s.length).toBe(2); // nz satır
    expect(s[0].length).toBe(3); // nx sütun
    // satır 0 = iz 1 (arka), sütun 0 = ix 2 (sol)
    expect(s[0][0]).toMatchObject({ satir: 0, sutun: 0, x: 20, y: -150, z: 10 });
    expect(s[0][0].mT).toBeCloseTo((10 * 2 + 3 + 1) * 0.01, 10);
    expect(s[1][2]).toMatchObject({ x: -20, z: -10 });
    expect(s[1][2].mT).toBeCloseTo(3 * 0.01, 10);
    const t = kesit(h, 0);
    expect(t[0][0].mT).toBeNull(); // (2,0,1) tablo dışı
    expect(kesitEnBuyuk(t)).toBeCloseTo((10 * 2 + 0) * 0.01, 10);
    expect(kesitEnBuyuk([])).toBe(0);
    expect(kesitEnBuyuk([[{ satir: 0, sutun: 0, x: 0, y: 0, z: 0, mT: null }]])).toBe(0);
  });

  it("renk ölçeği: uçlar, ara değer, sınır dışı ve geçersiz kırpılır", () => {
    expect(renk(0)).toBe("rgb(30, 41, 99)");
    expect(renk(1)).toBe("rgb(220, 38, 38)");
    expect(renk(0.35)).toBe("rgb(14, 165, 233)");
    expect(renk(0.7)).toBe("rgb(250, 204, 21)");
    expect(renk(-3)).toBe(renk(0));
    expect(renk(7)).toBe(renk(1));
    expect(renk(Number.NaN)).toBe(renk(0));
    expect(renk(0.175)).toBe("rgb(22, 103, 166)");
  });

  it("Y295: mT biçimi etkin dilden (tr 1,07 · en 1.07)", async () => {
    await i18n.changeLanguage("tr");
    expect(mTBicimle(1.0712)).toBe("1,07");
    await i18n.changeLanguage("en");
    expect(mTBicimle(1.0712)).toBe("1.07");
    expect(mTBicimle(1234.5)).toBe("1,234.50");
  });
});
