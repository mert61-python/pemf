// Author: mertaygn, cglrgrkn
/**
 * DOKUNMA İLKELLERİ — Chip ve IconButton tabanları  [S3 adım 3/4/10, 2026-09-04 denetimi]
 * ======================================================================================
 * ÖLÇÜLEN DURUM:
 *  · İkon-only düğmeler (kapat X, zil, bağlantı yenile) yalnız ikon + 4-6 px padding kadardı:
 *    24-32 px. Erişilebilirlik tabanı 44 px.
 *  · 11 ayrı çip stili `paddingVertical: spacing.xs` ile kuruluydu → 320 px'te 26-30 px yükseklik.
 *
 * SÖZLEŞMENİN ASIL YARISI: taban ÖLÇEKLE AŞAĞI İNMEZ. 320 px telefonda ölçek 0,85 olduğu için
 * `rs(44)` = 37 px'e düşüyordu; `Math.max(44, rs(44))` bunu keser. Bu dosya cihazı 320 px'e
 * sabitleyip tabanın GERÇEKTEN devreye girdiğini ölçer — varsayılan jest cihazında ölçek 1,1
 * olduğundan orada mutasyon yakalanmaz.
 *
 * ⚠️ MUTASYON: tokens.ts'te `Math.max(44, rs(44))` → `rs(44)` yapılırsa 1. ve 4. vaka KIRILIR;
 * ilkellerde taban stili diziden çıkarılırsa (ya da çağıranın stilinin ÖNÜNE alınırsa) 3. ve 6. KIRILIR.
 */
import { cihaziKur } from "@/theme/__tests__/olcek";

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

type Agac = { root: { findAll: (f: (n: Dugum) => boolean) => Dugum[] } };
type Dugum = { props: Record<string, unknown> };

/** Bileşeni verilen cihazda taze yükleyip düzleştirilmiş kök stilini döndürür. */
function olc(
  width: number,
  height: number,
  ciz: (mod: {
    React: typeof import("react");
    Chip: typeof import("@/components/ui/Chip");
    IconButton: typeof import("@/components/ui/IconButton");
  }) => unknown,
  etiket: string
) {
  cihaziKur({ width, height, os: "android" });
  /* eslint-disable @typescript-eslint/no-require-imports */
  const React = require("react");
  const TestRenderer = require("react-test-renderer");
  const { StyleSheet } = require("react-native");
  const Chip = require("@/components/ui/Chip");
  const IconButton = require("@/components/ui/IconButton");
  const { touch } = require("@/theme/tokens") as typeof import("@/theme/tokens");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const tut: { agac?: Agac } = {};
  TestRenderer.act(() => {
    tut.agac = TestRenderer.create(ciz({ React, Chip, IconButton }) as never);
  });
  const dugum = tut.agac!.root.findAll(
    (n) => n.props?.accessibilityLabel === etiket && n.props?.style !== undefined
  )[0];
  if (!dugum) throw new Error(`"${etiket}" bulunamadı`);
  return { stil: StyleSheet.flatten(dugum.props.style) as Record<string, number>, props: dugum.props, touch };
}

const cipCiz = (m: { React: typeof import("react"); Chip: typeof import("@/components/ui/Chip") }, ek = {}) =>
  m.React.createElement(m.Chip.Chip, { label: "Uyudu", onPress: () => {}, ...ek });

const ikonCiz = (
  m: { React: typeof import("react"); IconButton: typeof import("@/components/ui/IconButton") },
  ek = {}
) => m.React.createElement(m.IconButton.IconButton, { label: "Kapat", onPress: () => {}, children: null, ...ek });

describe("IconButton", () => {
  it("KRİTİK: dar telefonda (ölçek 0,85) kutu 44 px'in altına inmez", () => {
    const { stil } = olc(320, 568, (m) => ikonCiz(m), "Kapat");
    expect(stil.minWidth).toBeGreaterThanOrEqual(44);
    expect(stil.minHeight).toBeGreaterThanOrEqual(44);
  });

  it("tablette taban yukarı ölçeklenir (küçülmez, büyür)", () => {
    const dar = olc(320, 568, (m) => ikonCiz(m), "Kapat");
    const tablet = olc(768, 1024, (m) => ikonCiz(m), "Kapat");
    expect(tablet.stil.minHeight).toBeGreaterThanOrEqual(dar.stil.minHeight);
  });

  it("KRİTİK: çağıranın stili rengi ezer ama dokunma tabanını EZEMEZ", () => {
    const { stil } = olc(
      320,
      568,
      (m) => ikonCiz(m, { style: { minWidth: 20, minHeight: 20, backgroundColor: "#123456" } }),
      "Kapat"
    );
    expect(stil.backgroundColor).toBe("#123456");
    expect(stil.minHeight).toBeGreaterThanOrEqual(44);
  });

  it("varsayılan hitSlop verilir ve sıkı ızgarada daraltılabilir", () => {
    const varsayilan = olc(320, 568, (m) => ikonCiz(m), "Kapat");
    expect(varsayilan.props.hitSlop).toEqual({ top: 8, bottom: 8, left: 8, right: 8 });
    const sikisik = olc(
      320,
      568,
      (m) => ikonCiz(m, { hitSlop: { top: 3, bottom: 3, left: 3, right: 3 } }),
      "Kapat"
    );
    expect(sikisik.props.hitSlop).toEqual({ top: 3, bottom: 3, left: 3, right: 3 });
  });
});

describe("Chip", () => {
  it("KRİTİK: dar telefonda çip 40 px'in altına inmez", () => {
    const { stil } = olc(320, 568, (m) => cipCiz(m), "Uyudu");
    expect(stil.minHeight).toBeGreaterThanOrEqual(40);
  });

  it("KRİTİK: geçilen stil rengi taşır, tabanı düşüremez (görsel değişiklik yok ilkesi)", () => {
    const { stil } = olc(
      320,
      568,
      (m) => cipCiz(m, { style: { backgroundColor: "#1e293b", paddingVertical: 2, minHeight: 24 } }),
      "Uyudu"
    );
    expect(stil.backgroundColor).toBe("#1e293b");
    expect(stil.minHeight).toBeGreaterThanOrEqual(40);
  });

  it("seçili durum ekran okuyucuya bildirilir (renk tek başına yetmez)", () => {
    const pasif = olc(320, 568, (m) => cipCiz(m), "Uyudu");
    const aktif = olc(320, 568, (m) => cipCiz(m, { active: true }), "Uyudu");
    expect((pasif.props.accessibilityState as { selected: boolean }).selected).toBe(false);
    expect((aktif.props.accessibilityState as { selected: boolean }).selected).toBe(true);
  });

  it("aktif stil yalnız aktifken uygulanır", () => {
    const ek = { style: { backgroundColor: "#111" }, activeStyle: { backgroundColor: "#1d4ed8" } };
    expect(olc(320, 568, (m) => cipCiz(m, ek), "Uyudu").stil.backgroundColor).toBe("#111");
    expect(olc(320, 568, (m) => cipCiz(m, { ...ek, active: true }), "Uyudu").stil.backgroundColor).toBe("#1d4ed8");
  });
});
