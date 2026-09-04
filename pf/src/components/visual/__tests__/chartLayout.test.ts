// Author: mertaygn, cglrgrkn
/**
 * GRAFİK YERLEŞİM HESAPLARI  [S7 adım 2, 2026-09-04 responsive denetimi]
 * =====================================================================
 * ÖLÇÜLEN DURUM: `RealtimeChart` eksen boşlukları SABİTTİ (left 60, right 60). 320 px'lik
 * telefonda çizim alanı 200 px'e düşüyordu — ekranın %37'si eksen boşluğu. Sıcaklık ekseni
 * kapalıyken bile sağda 60 px boş duruyordu. Web tuvali mantıksal pikselle kurulduğu için
 * DPR 2-3 ekranlarda eğri bulanıktı.
 *
 * ⚠️ MUTASYON: `dar` dalı silinirse 1. vaka; `showTemp` dalı silinirse 2. vaka;
 * DPR üst sınırı kaldırılırsa 6. vaka KIRILIR.
 */
import { canvasBoyutla, cizimAlani, hesaplaPad } from "@/components/visual/chartLayout";

describe("eksen boşlukları", () => {
  it("KRİTİK: dar telefonda sol eksen daralır (320 px'te 60 → 44)", () => {
    expect(hesaplaPad(320, false).left).toBe(44);
    expect(hesaplaPad(800, false).left).toBe(60);
  });

  it("KRİTİK: sıcaklık ekseni kapalıyken sağ boşluk 12'ye iner (çizilecek etiket yok)", () => {
    expect(hesaplaPad(800, false).right).toBe(12);
    expect(hesaplaPad(800, true).right).toBe(60);
    expect(hesaplaPad(320, true).right).toBe(44);
  });

  it("dar telefonda çizim alanı ölçülebilir biçimde büyür", () => {
    const eski = 320 - 60 - 60; // denetim öncesi sabit boşluklar
    const yeni = cizimAlani(320, 200, hesaplaPad(320, false)).genislik;
    expect(yeni).toBeGreaterThan(eski);
    expect(yeni).toBe(320 - 44 - 12);
  });

  it("çizim alanı negatife düşmez (çok dar kap)", () => {
    const alan = cizimAlani(40, 20, hesaplaPad(40, true));
    expect(alan.genislik).toBe(0);
    expect(alan.yukseklik).toBe(0);
  });
});

describe("tuval ölçekleme (web keskinliği)", () => {
  const sahte = () => ({
    canvas: { width: 0, height: 0, style: { width: "", height: "" } },
    ctx: { setTransform: jest.fn() },
  });

  it("KRİTİK: iç tampon DPR katı, CSS boyutu mantıksal px kalır", () => {
    const { canvas, ctx } = sahte();
    canvasBoyutla(canvas, ctx, 360, 200, 2);
    expect(canvas.width).toBe(720);
    expect(canvas.height).toBe(400);
    expect(canvas.style.width).toBe("360px");
    expect(ctx.setTransform).toHaveBeenCalledWith(2, 0, 0, 2, 0, 0);
  });

  it("KRİTİK: DPR 3 ile sınırlanır (4x ekranda bellek bedeli okunurluğu aşar)", () => {
    const { canvas, ctx } = sahte();
    expect(canvasBoyutla(canvas, ctx, 100, 100, 4).dpr).toBe(3);
    expect(canvas.width).toBe(300);
  });

  it("geçersiz/eksik DPR 1 kabul edilir (çökme yok)", () => {
    const { canvas, ctx } = sahte();
    expect(canvasBoyutla(canvas, ctx, 100, 50, 0).dpr).toBe(1);
    expect(canvas.width).toBe(100);
  });
});
