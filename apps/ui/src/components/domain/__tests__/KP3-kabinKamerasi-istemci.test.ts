/**
 * KP-3 C · AnalizKosulu kabin kamerası istemcisi — her test bir DAVRANIŞ iddiası (operatör HER arızada eylem söyleyen tek bir hata
 * görür; ham "JSON parse" / "undefined" sızmaz):
 *  - Ağ hatası → `KabinKamerasiHatasi` (durum 0) + "kamerayı seçip yeniden deneyin" metni.
 *  - Sunucu JSON OLMAYAN hata gövdesi döndürürse (ör. 502 HTML) yine aynı eylem metni + HTTP kodu.
 *  - 200 ama görüntü YOK (tek kare / canlı kare) → hata (boş görüntü analize gönderilmez); canlı oturumda ilk kare henüz yoksa
 *    (`hazir: false`) hata DEĞİL, `null` (sonraki turda yeniden istenir).
 * SAHTE (en alt kat): fetch · yapılandırma (yerel taban). GERÇEK: korunanFetch (düz-HTTP kapısı) + apiClient başlıkları + i18n.
 */
jest.mock("@/services/config", () => ({
  get serviceConfig() { return { apiBaseUrl: "http://127.0.0.1:18080/api", bridgeBaseUrl: "http://127.0.0.1:18080/api", apiToken: "" }; },
}));

import i18n from "i18next";
import { KabinKamerasiHatasi, kabinCanliKare, kabinKaresiAl } from "@/components/domain/AnalizKosulu";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const yanit = (durum: number, govde: () => Promise<unknown>) => ({ ok: durum < 400, status: durum, json: govde });
let ag: jest.Mock;
beforeEach(() => {
  ag = jest.fn();
  (globalThis as Record<string, unknown>).fetch = ag;
});

async function hatasi(p: Promise<unknown>): Promise<KabinKamerasiHatasi> {
  try {
    await p;
  } catch (e) {
    return e as KabinKamerasiHatasi;
  }
  throw new Error("hata bekleniyordu");
}

it("ağ hatası → durum 0 + eylem metni", async () => {
  ag.mockRejectedValue(new TypeError("Failed to fetch"));
  const e = await hatasi(kabinKaresiAl());
  expect(e).toBeInstanceOf(KabinKamerasiHatasi);
  expect(e.durum).toBe(0);
  expect(e.message).toBe(T("ai.kabinKamerasi.hata"));
});

it("JSON olmayan hata gövdesi (502 HTML) → aynı eylem metni + HTTP kodu", async () => {
  ag.mockResolvedValue(yanit(502, async () => { throw new SyntaxError("Unexpected token <"); }));
  const e = await hatasi(kabinCanliKare(true));
  expect(e).toBeInstanceOf(KabinKamerasiHatasi);
  expect(e.durum).toBe(502);
  expect(e.message).toBe(T("ai.kabinKamerasi.hata"));
  expect(String(ag.mock.calls[0][0])).toContain("/settings/kabin-kamerasi/canli/kare?tam=true");
});

it("200 ama görüntü yok → hata; canlı oturumda ilk kare henüz yoksa null", async () => {
  ag.mockResolvedValue(yanit(200, async () => ({ status: "success" })));
  expect((await hatasi(kabinKaresiAl())).durum).toBe(0);
  expect((await hatasi(kabinCanliKare(false))).message).toBe(T("ai.kabinKamerasi.hata"));
  ag.mockResolvedValue(yanit(200, async () => ({ hazir: false })));
  await expect(kabinCanliKare(false)).resolves.toBeNull();
  ag.mockResolvedValue(yanit(200, async () => ({ image_base64: "QUJD" })));
  await expect(kabinKaresiAl()).resolves.toBe("QUJD");
});
