// Author: mertaygn, cglrgrkn
/**
 * 402 AYRI ELE ALINIR — JETON-SISTEMI Adim 4.4 (2026-08-22).
 *
 * Jeton kapisi (servers/jeton.py::jeton_gate) yetersiz bakiyede 402 + Turkce `detail` doner ve
 * mesaj tedavinin ETKILENMEDIGINI soyler. apiClient bunu genel "Sunucu Hatasi" kutusuna
 * karistirirsa kullanici "cihaz bozuldu" sanir — oysa durum ticari: jeton bitti, seans calisiyor.
 *
 * SOZLESME: 402'de baslik "Jeton" iceren AYRI bir bildirim cikar ve sunucunun `detail` metni
 * OLDUGU GIBI gosterilir (kapinin mesaji zaten Turkce ve eylem soyluyor).
 */
import { apiPost } from "../apiClient";
import * as toastBridge from "../toastBridge";

import { serviceConfig } from "@/services/config";

describe("402 jeton yaniti ayri ele alinir", () => {
  beforeEach(() => {
    serviceConfig.apiBaseUrl = "http://192.168.1.147:8000/api"; // guvenli-taban (mevcut suit deseni)
    serviceConfig.apiToken = "";
  });
  afterEach(() => jest.restoreAllMocks());

  async function cagriYap(status: number, detail: string) {
    const toasts: string[] = [];
    jest.spyOn(toastBridge, "emitToast").mockImplementation((msg: string) => {
      toasts.push(msg);
      return true;
    });
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status,
      json: async () => ({ detail }),
    }) as unknown as typeof fetch;
    await apiPost("/ai/vision/landmark", {}, null);
    return toasts;
  }

  it("KRITIK: 402'de baslik 'Jeton' icerir ve detail METNI AYNEN gosterilir", async () => {
    const detay = "Jeton hakkınız bitti; yeni analiz başlatılamadı. Seans ve acil durdurma ETKİLENMEZ.";
    const toasts = await cagriYap(402, detay);
    expect(toasts.length).toBe(1);
    expect(toasts[0]).toContain("Jeton");
    expect(toasts[0]).toContain("ETKİLENMEZ");
    expect(toasts[0]).not.toContain("Sunucu Hatası");
  });

  it("KARSIT-KANIT: 500 hala genel 'Sunucu Hatasi' kutusuna gider", async () => {
    const toasts = await cagriYap(500, "iç hata");
    expect(toasts.length).toBe(1);
    expect(toasts[0]).toContain("Sunucu Hatası");
  });
});
