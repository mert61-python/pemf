// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A3 — "Alan haritası" kartı: varsayılan KAPALI (abonelik yok); açınca abone + "Model tahmini, ölçüm değil" HER ZAMAN;
 * durum kodları eylem söyleyen metin; harita: katman seçimi, kesit yüksekliği, dokunuşla nokta değeri (tablo dışı ayrı metin), en yüksek
 * değer + yeri, renk ölçeği üstü, uyarılar; sensör (MLX) ölçümü yalnız GERÇEKTEN ölçülen STM bobininden.
 */
import i18n from "i18next";

const mockCtx: { snapshot: Record<string, unknown>; alanHaritasi: unknown; alanAbone: jest.Mock } = {
  snapshot: {},
  alanHaritasi: null,
  alanAbone: jest.fn(),
};
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCtx }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { AlanHaritasiKarti, sensorOlcumu } from "@/components/domain/AlanHaritasiKarti";

/** Dinamik anahtarlı test yardımcısı (katalog türü literal anahtar ister). */
const t = (k: string, o?: Record<string, unknown>): string => (i18n.t as unknown as (a: string, b?: object) => string)(k, o);

/** nx=3, ny=3, nz=2: değer = 10*ix + 3*iy + iz (mT × 0,01); (0,0,0) tablo dışı. */
function harita(ek: Record<string, unknown> = {}) {
  const kod: number[] = [];
  for (let ix = 0; ix < 3; ix++) for (let iy = 0; iy < 3; iy++) for (let iz = 0; iz < 2; iz++) kod.push(10 * ix + 3 * iy + iz);
  kod[0] = 255;
  return {
    surum: 1,
    durum: "tamam",
    zaman: 1,
    modelTahmini: true,
    kalibrasyon: "k1",
    izgara: { kok: [-20, -170, -10], adim: 20, boyut: [3, 3, 2], cerceve: "kabin", camIc: [70, 350, 40] },
    deger: Buffer.from(kod).toString("base64"),
    olcek: 0.01,
    yok: 255,
    enYuksek: { mT: 0.27, konum: [20.4, -130, 9.6] },
    bobinler: [{ bobin: 1, frekans: 100, duty: 0.5, faz: 0 }],
    uyarilar: [] as string[],
    ...ek,
  };
}

function ac(u: ReturnType<typeof render>) {
  fireEvent(u.getByTestId("alan-haritasi-ac"), "valueChange", true);
}

function cizdir(u: ReturnType<typeof render>, genislik = 300) {
  fireEvent(u.getByTestId("alan-haritasi-svg-kutu"), "layout", { nativeEvent: { layout: { width: genislik, height: 10, x: 0, y: 0 } } });
}

describe("GA AlanHaritasiKarti", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("tr");
    mockCtx.snapshot = {};
    mockCtx.alanHaritasi = null;
    mockCtx.alanAbone = jest.fn();
  });

  it("varsayılan KAPALI: abonelik yok, açıklama; açınca abone + 'model tahmini' + bekleniyor; kapatınca çıkar", () => {
    mockCtx.alanHaritasi = harita();
    const u = render(<AlanHaritasiKarti />);
    expect(u.getByText(t("kontrol.alanHaritasi.baslik"))).toBeTruthy();
    expect(u.getByText(t("kontrol.alanHaritasi.kapali"))).toBeTruthy();
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    expect(u.queryByTestId("alan-haritasi-model-tahmini")).toBeNull();
    mockCtx.alanHaritasi = null;
    ac(u);
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true]]);
    expect(u.getByTestId("alan-haritasi-model-tahmini").props.children).toBe(t("kontrol.alanHaritasi.modelTahmini"));
    expect(u.getByText(t("kontrol.alanHaritasi.bekleniyor"))).toBeTruthy();
    fireEvent(u.getByTestId("alan-haritasi-ac"), "valueChange", false);
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true], [false]]);
  });

  it.each([
    ["sifir", "kontrol.alanHaritasi.durum.sifir"],
    ["kalibrasyonYok", "kontrol.alanHaritasi.durum.kalibrasyonYok"],
    ["kalibrasyonBozuk", "kontrol.alanHaritasi.durum.kalibrasyonBozuk"],
    ["kalibrasyonEski", "kontrol.alanHaritasi.durum.kalibrasyonEski"],
    ["eslemeDogrulanmadi", "kontrol.alanHaritasi.durum.eslemeDogrulanmadi"],
    ["modelYok", "kontrol.alanHaritasi.durum.modelYok"],
    ["modelBozuk", "kontrol.alanHaritasi.durum.modelBozuk"],
    ["hata", "kontrol.alanHaritasi.durum.hata"],
    ["bilinmeyen", "kontrol.alanHaritasi.durum.hata"],
  ])("durum %s → eylem söyleyen metin (model tahmini etiketi yine görünür)", (durum, anahtar) => {
    mockCtx.alanHaritasi = { surum: 1, durum, zaman: 1, modelTahmini: true };
    const u = render(<AlanHaritasiKarti />);
    ac(u);
    expect(u.getByTestId("alan-haritasi-durum").props.children).toBe(t(anahtar));
    expect(u.getByTestId("alan-haritasi-model-tahmini")).toBeTruthy();
    expect(u.queryByTestId("alan-haritasi-svg")).toBeNull();
  });

  it("'tamam' ama değerler tutarsız → hata metni (harita çizilmez)", () => {
    mockCtx.alanHaritasi = harita({ deger: "$$$$" });
    const u = render(<AlanHaritasiKarti />);
    ac(u);
    expect(u.getByTestId("alan-haritasi-durum").props.children).toBe(t("kontrol.alanHaritasi.durum.hata"));
  });

  it("harita: taban kesiti, ölçek, en yüksek, dokunuşla nokta, katman değişimi, uyarılar", async () => {
    mockCtx.alanHaritasi = harita({ uyarilar: ["dutyKirpildi", "frekansKalibrasyonDisi", "bilinmeyenUyari"] });
    const u = render(<AlanHaritasiKarti />);
    ac(u);
    expect(u.queryByTestId("alan-haritasi-svg")).toBeNull(); // genişlik ölçülmeden çizilmez
    cizdir(u);
    expect(u.getByTestId("alan-haritasi-svg")).toBeTruthy();
    expect(u.getByTestId("alan-haritasi-kesit").props.children).toBe(t("kontrol.alanHaritasi.kesitYuksekligi", { mm: 5 }));
    expect(u.getByTestId("alan-haritasi-olcek-ust").props.children).toBe(t("kontrol.alanHaritasi.olcekUst", { deger: "0,27" }));
    expect(u.getByTestId("alan-haritasi-en-yuksek").props.children).toBe(
      t("kontrol.alanHaritasi.enYuksek", { deger: "0,27", x: 20, y: -130, z: 10 }),
    );
    // taban (iy 0) en büyüğü: ix 2, iz 1 → 21 × 0,01
    expect(u.getByTestId("alan-haritasi-katman-en-yuksek").props.children).toBe(
      t("kontrol.alanHaritasi.katmanEnYuksek", { deger: "0,21" }),
    );
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(t("kontrol.alanHaritasi.noktaIpucu"));
    // satır 0 = arka (iz 1), sütun 0 = sol (ix 2) → 21
    fireEvent.press(u.getByTestId("alan-hucre-0-0"));
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(
      t("kontrol.alanHaritasi.nokta", { x: 20, z: 10, deger: "0,21" }),
    );
    expect(u.getByTestId("alan-hucre-0-0").props.strokeWidth).toBe(2); // seçili hücre çerçeveli
    expect(u.getByTestId("alan-hucre-0-1").props.strokeWidth).toBe(0);
    // satır 1 = ön (iz 0), sütun 2 = sağ (ix 0) → tablo dışı
    fireEvent.press(u.getByTestId("alan-hucre-1-2"));
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(t("kontrol.alanHaritasi.noktaYok", { x: -20, z: -10 }));
    // katman: tavan (iy 2) → seçim sıfırlanır, kesit 45 mm
    fireEvent.press(u.getByTestId("alan-katman-tavan"));
    expect(u.getByTestId("alan-haritasi-kesit").props.children).toBe(t("kontrol.alanHaritasi.kesitYuksekligi", { mm: 45 }));
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(t("kontrol.alanHaritasi.noktaIpucu"));
    expect(u.getByTestId("alan-haritasi-katman-en-yuksek").props.children).toBe(
      t("kontrol.alanHaritasi.katmanEnYuksek", { deger: "0,27" }),
    );
    fireEvent.press(u.getByTestId("alan-katman-orta"));
    expect(u.getByTestId("alan-haritasi-kesit").props.children).toBe(t("kontrol.alanHaritasi.kesitYuksekligi", { mm: 25 }));
    expect(u.getByTestId("alan-haritasi-uyari-dutyKirpildi").props.children).toBe(t("kontrol.alanHaritasi.uyari.dutyKirpildi"));
    expect(u.getByTestId("alan-haritasi-uyari-frekansKalibrasyonDisi").props.children).toBe(
      t("kontrol.alanHaritasi.uyari.frekansKalibrasyonDisi"),
    );
    expect(u.queryByTestId("alan-haritasi-uyari-bilinmeyenUyari")).toBeNull();
    // EN: aynı değerler İngilizce biçimle
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    expect(u.getByTestId("alan-haritasi-olcek-ust").props.children).toBe(t("kontrol.alanHaritasi.olcekUst", { deger: "0.27" }));
  });

  it("en yüksek / cam ölçüsü / uyarı yoksa o satırlar çizilmez; alan sıfırken renk ölçeği 0", () => {
    mockCtx.alanHaritasi = harita({ enYuksek: null, uyarilar: undefined, olcek: 0, izgara: { kok: [-20, -170, -10], adim: 20, boyut: [3, 3, 2], cerceve: "kabin" } });
    const u = render(<AlanHaritasiKarti />);
    ac(u);
    cizdir(u);
    expect(u.queryByTestId("alan-haritasi-en-yuksek")).toBeNull();
    expect(u.queryByTestId("alan-haritasi-kesit")).toBeNull();
    expect(u.getByTestId("alan-haritasi-olcek-ust").props.children).toBe(t("kontrol.alanHaritasi.olcekUst", { deger: "0,00" }));
    fireEvent.press(u.getByTestId("alan-hucre-0-0"));
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(t("kontrol.alanHaritasi.nokta", { x: 20, z: 10, deger: "0,00" }));
  });

  it("seçili hücre yeni haritada YOKSA (ızgara küçüldü) ipucuna döner", () => {
    mockCtx.alanHaritasi = harita();
    const u = render(<AlanHaritasiKarti />);
    ac(u);
    cizdir(u);
    fireEvent.press(u.getByTestId("alan-hucre-1-2"));
    // 1 sütun × 2 satır: satır 1 var, sütun 2 yok
    mockCtx.alanHaritasi = harita({ izgara: { kok: [0, -170, -10], adim: 20, boyut: [1, 3, 2], cerceve: "kabin" }, deger: Buffer.from([1, 2, 3, 4, 5, 6]).toString("base64") });
    u.rerender(<AlanHaritasiKarti />);
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(t("kontrol.alanHaritasi.noktaIpucu"));
    // 2 sütun × 1 satır: satır 1 yok
    mockCtx.alanHaritasi = harita({ izgara: { kok: [0, -170, 0], adim: 20, boyut: [2, 3, 1], cerceve: "kabin" }, deger: Buffer.from([1, 2, 3, 4, 5, 6]).toString("base64") });
    u.rerender(<AlanHaritasiKarti />);
    expect(u.getByTestId("alan-haritasi-nokta").props.children).toBe(t("kontrol.alanHaritasi.noktaIpucu"));
  });

  it("sensör (MLX): yalnız ölçülen + doğrulanmış STM bobini; en büyüğü; karta yazılır", () => {
    expect(sensorOlcumu(undefined)).toBeNull();
    expect(sensorOlcumu("x")).toBeNull();
    const c = (id: number, mT: unknown, ek: Record<string, unknown> = {}) => ({ id, magneticMt: mT, measuredFields: ["magneticMt"], ...ek });
    expect(
      sensorOlcumu([
        c(8, 9.9), // ESP slotu — değil
        c(2, 5.5, { alanDogrulanamadi: true }), // kazanç doğrulanamadı
        c(3, 4.4, { measuredFields: undefined }), // ölçüm bilgisi yok (eski backend) — gösterilmez
        c(4, 3.3, { measuredFields: ["objectTemp"] }), // alan ölçülmüyor
        c(5, "x"),
        c(1, 0.92),
        c(6, 1.07),
      ]),
    ).toBeCloseTo(1.07, 10);
    mockCtx.snapshot = { coils: [c(1, 0.92)] };
    mockCtx.alanHaritasi = harita();
    const u = render(<AlanHaritasiKarti />);
    expect(u.queryByTestId("alan-haritasi-mlx")).toBeNull(); // kapalıyken yok
    ac(u);
    expect(u.getByTestId("alan-haritasi-mlx").props.children).toBe(t("kontrol.alanHaritasi.mlx", { deger: "0,92" }));
    mockCtx.snapshot = { coils: [] };
    u.rerender(<AlanHaritasiKarti />);
    expect(u.queryByTestId("alan-haritasi-mlx")).toBeNull();
    mockCtx.snapshot = null as unknown as Record<string, unknown>;
    u.rerender(<AlanHaritasiKarti />);
    expect(u.queryByTestId("alan-haritasi-mlx")).toBeNull();
  });
});
