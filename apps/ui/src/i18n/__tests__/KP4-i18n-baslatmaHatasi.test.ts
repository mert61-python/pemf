/**
 * KP-4 B1 · src/i18n/index.ts — i18next BAŞLATILAMAZSA (init fırlatır) modülün içe aktarılması uygulamayı ÇÖKERTMEZ: hata tanı için
 * saklanır (`baslatmaHatasi`) ve etkin dil — cihaz İngilizce olsa bile — Türkçe'ye düşer (kritik metinler Türkçe yedekte).
 * SAHTE: i18next (init fırlatır; yalıtılmış modül kaydında — dıştaki i18n etkilenmez) ve cihaz yereli ("en-US").
 * ⚠️ jest.setup `@/i18n/dil`i dosya düzeyinde sahteler; o sahte nesne yalıtılmış kayıtta da AYNI nesnedir (ölçüldü: yalıtılmış
 * `doMock` ve Platform / depo yoluyla "en" vermek ETKİSİZ) → cihaz yereli o nesne üzerinde casusla verilir, sonda geri alınır.
 */
it("KRİTİK: init fırlatırsa içe aktarma çökmez, hata saklanır, etkin dil (cihaz 'en' olsa da) Türkçe'ye düşer", () => {
  const hata = new Error("i18next init patladı");
  const dilDis = require("@/i18n/dil") as typeof import("@/i18n/dil");
  const casus = jest.spyOn(dilDis, "cihazYereli").mockReturnValue("en-US");
  try {
    jest.isolateModules(() => {
      jest.doMock("i18next", () => {
        const sahte: Record<string, unknown> = { on: jest.fn(), t: (k: string) => k };
        sahte.use = () => sahte;
        sahte.init = () => { throw hata; };
        return { __esModule: true, default: sahte };
      });
      const dil = require("@/i18n/dil") as typeof import("@/i18n/dil");
      expect(dil.etkinDil(dil.kayitliDilEszamanli(), dil.cihazYereli())).toBe("en"); // ön koşul: başlatma "en" ile girer
      const i18nMod = require("@/i18n") as typeof import("@/i18n");
      const durum = require("@/i18n/durum") as typeof import("@/i18n/durum");
      expect(i18nMod.baslatmaHatasi()).toBe(hata);
      expect(durum.etkinDilDegeri()).toBe("tr");
    });
  } finally {
    casus.mockRestore();
  }
});
