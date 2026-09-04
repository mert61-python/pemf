// Author: mertaygn, cglrgrkn
/**
 * KABUK DÜZENİ SÖZLEŞMESİ — getShellKind / kenar çubuğu genişliği / içerik tahmini
 * [S2+S5, 2026-09-04 responsive denetimi]
 *
 * ÖLÇÜLEN DURUM: kabuk seçimi `isDesktop || isTablet` (yalnız genişlik) idi; 768 px tablet
 * dikeyde 240 px'lik tam kenar çubuğu açılıp içeriğe 352 px kalıyordu (ekranA-3), yatay
 * telefonda ise alt bar dikey alanın %17'sini yiyordu (ekranB-3 / sahip kararı: ikon rayı).
 *
 * ⚠️ MUTASYON: `SIDEBAR_MIN` 900 → 768 yapılırsa "tablet dikeyde ray" satırı KIRILIR;
 * yükseklik parametresi kaldırılırsa "yatay telefon" satırı KIRILIR.
 */
import {
  COMPACT_CONTENT,
  RAIL_WIDTH,
  SIDEBAR_WIDTH,
  SIDEBAR_WIDTH_TABLET,
  estimateContentWidth,
  getShellKind,
  shellSidebarWidth,
} from "@/theme/layout";

describe("getShellKind — cihaz tablosu", () => {
  const tablo: [string, number, number, boolean, string][] = [
    // ad,                        genişlik, yükseklik, web?, beklenen
    ["dar telefon dikey", 320, 568, false, "bottom"],
    ["telefon dikey", 390, 844, false, "bottom"],
    ["yatay telefon (küçük)", 640, 360, false, "bottom"],
    ["yatay telefon (büyük, çentikli)", 926, 428, false, "rail"],
    ["tablet dikey", 768, 1024, false, "rail"],
    ["tablet yatay", 1024, 768, false, "sidebar"],
    ["PC penceresi (launcher min)", 700, 540, true, "rail"],
    // 911×512: kenar çubuğu DİKEY alan yemez ve içeriğe 609 px kalır → tam kenar çubuğu doğru.
    ["PC penceresi 1366@%150", 911, 512, true, "sidebar"],
    ["PC geniş", 1280, 720, true, "sidebar"],
    ["PC 4K", 2560, 1440, true, "sidebar"],
  ];
  it.each(tablo)("%s (%ix%i) → %s", (_ad, w, h, web, beklenen) => {
    expect(getShellKind(w as number, web as boolean, h as number)).toBe(beklenen);
  });

  it("KRİTİK: yatay telefonda (926×428) tam kenar çubuğu YERİNE ray — dikey alan yenmez", () => {
    expect(getShellKind(926, false, 428)).toBe("rail");
    // Aynı genişlik dikey tablette (yükseklik uzun) tam kenar çubuğu olur:
    expect(getShellKind(926, false, 1200)).toBe("sidebar");
  });

  it("yükseklik verilmezse yalnız genişliğe bakar (geriye uyum)", () => {
    expect(getShellKind(1280, true)).toBe("sidebar");
    expect(getShellKind(700, true)).toBe("rail");
    expect(getShellKind(400, false)).toBe("bottom");
  });
});

describe("shellSidebarWidth — ölçeksiz yapısal genişlik", () => {
  it("ray 72, tablet 200, masaüstü 240, alt bar 0", () => {
    expect(shellSidebarWidth("rail", false)).toBe(RAIL_WIDTH);
    expect(shellSidebarWidth("sidebar", true)).toBe(SIDEBAR_WIDTH_TABLET);
    expect(shellSidebarWidth("sidebar", false)).toBe(SIDEBAR_WIDTH);
    expect(shellSidebarWidth("bottom", false)).toBe(0);
  });

  it("KRİTİK: genişlikler ölçeksiz sabit (PC'de %30 büyümez)", () => {
    expect(SIDEBAR_WIDTH).toBe(240);
    expect(RAIL_WIDTH).toBe(72);
  });
});

describe("estimateContentWidth — ızgara kararının dayanağı", () => {
  it("kenar çubuğunu ve iki kat boşluğu düşer", () => {
    expect(estimateContentWidth(1280, "sidebar", false, 24)).toBe(1280 - 240 - 48);
    expect(estimateContentWidth(768, "rail", false, 24)).toBe(768 - 72 - 48);
    expect(estimateContentWidth(390, "bottom", false, 20)).toBe(390 - 40);
  });

  it("KRİTİK: tablet dikeyde içerik kolonu kompakt eşiğinin ÜSTÜNDE kalır (ray sayesinde)", () => {
    // Eski davranış: 768 − 240(tam kenar çubuğu) − 48 = 480 < 560 → sıkışık 2 sütun.
    // Yeni: ray (72) → 648 ≥ 560 → gerçek 2 sütun sığar.
    const yeni = estimateContentWidth(768, "rail", false, 24);
    expect(yeni).toBeGreaterThanOrEqual(COMPACT_CONTENT);
    const eski = estimateContentWidth(768, "sidebar", false, 24);
    expect(eski).toBeLessThan(COMPACT_CONTENT);
  });

  it("negatif genişlik üretmez", () => {
    expect(estimateContentWidth(100, "sidebar", false, 24)).toBe(0);
  });
});
