// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — modül istemcisi: uç yolları, sunucu hata gövdesi `{detail: {kod, alan}}` → kod, gövdesiz hata / ulaşılamama →
 * `baglanti`, ad etkin dilde, her hata kodu eylem söyleyen metin.
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn(), apiPost: jest.fn() }));

import i18n from "i18next";
import { apiGet, apiPost } from "@/services/apiClient";
import { modulAdi, modulApi, modulHataMetni } from "@/services/moduller";

const get = apiGet as jest.Mock;
const post = apiPost as jest.Mock;
const t = i18n.t.bind(i18n) as unknown as Parameters<typeof modulHataMetni>[0];

describe("GA modül istemcisi", () => {
  beforeEach(async () => {
    get.mockReset();
    post.mockReset();
    await i18n.changeLanguage("tr");
  });

  it("uç yolları ve gövdeler", async () => {
    get.mockResolvedValue({ ok: 1 });
    post.mockResolvedValue({ ok: 2 });
    expect(await modulApi.listele()).toEqual({ tamam: true, veri: { ok: 1 } });
    expect(get.mock.calls[0].slice(0, 2)).toEqual(["/moduller", null]);
    expect(get.mock.calls[0][2].silent).toBe(true);
    await modulApi.durum();
    expect(get.mock.calls[1][0]).toBe("/moduller/durum");
    await modulApi.gorunurlukYaz(true);
    await modulApi.sec("a b");
    await modulApi.birak();
    await modulApi.uygula({ frekans_hz: 100 });
    await modulApi.baslat();
    await modulApi.durdur();
    expect(post.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ["/moduller/gorunurluk", { gorunur: true }],
      ["/moduller/a%20b/sec", {}],
      ["/moduller/birak", {}],
      ["/moduller/uygula", { ayar: { frekans_hz: 100 } }],
      ["/moduller/baslat", {}],
      ["/moduller/durdur", {}],
    ]);
  });

  it("hata: sunucu kodu / gövdesiz / ulaşılamadı", async () => {
    post.mockImplementation(async (_y: string, _g: unknown, fb: unknown, o: { onHttpError: (d: number, m?: string, h?: unknown) => void }) => {
      o.onHttpError(400, undefined, { detail: { kod: "ayarSinirDisi", alan: "frekans_hz" } });
      return fb;
    });
    expect(await modulApi.uygula({ frekans_hz: 9999 })).toEqual({ tamam: false, hata: { kod: "ayarSinirDisi", alan: "frekans_hz" } });
    post.mockImplementation(async (_y: string, _g: unknown, fb: unknown, o: { onHttpError: (d: number, m?: string, h?: unknown) => void }) => {
      o.onHttpError(500, "x", "metin");
      return fb;
    });
    expect(await modulApi.baslat()).toEqual({ tamam: false, hata: { kod: "baglanti", alan: "" } });
    get.mockResolvedValue(null);
    expect(await modulApi.listele()).toEqual({ tamam: false, hata: { kod: "baglanti", alan: "" } });
  });

  it("ad etkin dilde; adsız → kimlik", () => {
    const m = { kimlik: "ornek", ad: { tr: "Örnek", en: "Example" } };
    expect(modulAdi(m, "tr")).toBe("Örnek");
    expect(modulAdi(m, "en")).toBe("Example");
    expect(modulAdi({ kimlik: "x" }, "en")).toBe("x");
  });

  it("her hata kodu eylem söyleyen metin", () => {
    const k = (kod: string, alan = "frekans_hz") => modulHataMetni(t, { kod, alan });
    expect(k("gizli")).toBe(i18n.t("kontrol.modul.hata.gizli"));
    expect(k("modulYok")).toBe(i18n.t("kontrol.modul.hata.modulYok"));
    expect(k("etkinModulYok")).toBe(i18n.t("kontrol.modul.hata.etkinModulYok"));
    expect(k("baglanamadi", "kartBulunamadi")).toBe(i18n.t("kontrol.modul.hata.baglanamadi", { neden: "kartBulunamadi" }));
    expect(k("surucuOldu")).toBe(i18n.t("kontrol.modul.hata.surucuOldu"));
    expect(k("surucuYanitsiz")).toBe(i18n.t("kontrol.modul.hata.surucuYanitsiz"));
    expect(k("surucuHatasi", "ayarYok")).toBe(i18n.t("kontrol.modul.hata.surucuHatasi", { neden: "ayarYok" }));
    expect(k("ayarSinirDisi")).toBe(i18n.t("kontrol.modul.hata.ayarSinirDisi", { alan: "frekans_hz" }));
    for (const kod of ["ayarBilinmeyen", "ayarSayiDegil", "ayarGecersiz"]) expect(k(kod)).toBe(i18n.t("kontrol.modul.hata.ayarGecersiz", { alan: "frekans_hz" }));
    expect(k("baglanti")).toBe(i18n.t("kontrol.modul.hata.baglanti"));
    expect(k("bilinmeyen")).toBe(i18n.t("kontrol.modul.hata.baglanti"));
    expect(k("gizli")).not.toBe("kontrol.modul.hata.gizli"); // anahtar katalogda
  });
});
