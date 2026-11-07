/**
 * KP-3 C · i18n/kritik — ACİL DURDUR gibi kritik metinlerin "ASLA boş dönmez, ASLA atmaz" sözleşmesinin kapsanmayan kolları:
 *  - Etkin dil okunamazsa (i18n nesnesi bozuk) ve katalog sorgusu da atarsa TÜRKÇE sabit yedek döner (İngilizce sanılmaz, boş değil).
 *  - Dil değişimi aboneliği kurulamazsa kanca çökmez, o anki dili döndürmeye devam eder; söküm de güvenli.
 * GERÇEK: kritik modülü + i18next örneği (yalnız bozulma anı spy / özellik tanımıyla taklit edilir).
 */
import { renderHook } from "@testing-library/react-native";
import i18n from "i18next";
import { KRITIK_YEDEK, kritikMetin, useKritikDil } from "@/i18n/kritik";

afterEach(() => jest.restoreAllMocks());

it("dil okunamaz + katalog atar → Türkçe sabit yedek", () => {
  const ozgun = Object.getOwnPropertyDescriptor(i18n, "language");
  Object.defineProperty(i18n, "language", { configurable: true, get: () => { throw new Error("bozuk örnek"); } });
  jest.spyOn(i18n, "exists").mockImplementation(() => { throw new Error("katalog bozuk"); });
  try {
    const tr = KRITIK_YEDEK.tr as Record<string, string>;
    const en = KRITIK_YEDEK.en as Record<string, string>;
    // TR ile EN'i FARKLI olan bir anahtar — yoksa "Türkçe mi döndü" ölçülemez
    const anahtar = Object.keys(tr).find((k) => !k.endsWith("_one") && !k.endsWith("_other") && tr[k] !== en[k])!;
    const m = kritikMetin(anahtar as never);
    expect(m).toBe((KRITIK_YEDEK.tr as Record<string, string>)[anahtar]);
    expect(m.trim()).not.toBe("");
  } finally {
    if (ozgun) Object.defineProperty(i18n, "language", ozgun);
    else delete (i18n as unknown as { language?: string }).language;
  }
});

it("dil değişimi aboneliği kurulamazsa kanca çökmez ve dili döndürür; söküm güvenli", () => {
  jest.spyOn(i18n, "on").mockImplementation(() => { throw new Error("olay yayıcı yok"); });
  const h = renderHook(() => useKritikDil());
  expect(["tr", "en"]).toContain(h.result.current);
  expect(() => h.unmount()).not.toThrow();
});
