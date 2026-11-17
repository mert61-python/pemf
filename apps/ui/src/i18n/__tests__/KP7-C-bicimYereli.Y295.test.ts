/**
 * KP-7 C · Y295 (17-11, sahip): İngilizce arayüzde tarih / saat / sayı biçimi DİLE uyar — İngiliz biçimi (`en-GB`: 17/11/2026, 24 saat,
 * 1,234.56); Türkçe AYNEN (17.11.2026). Testler dili AÇIKÇA kurar (bayrak + `dilSec`) — cihaz / makine yereline YASLANMAZ (jest.setup
 * cihaz yerelini tr-TR'ye sabitler; makine yereline yaslanan test CI'da en-US'te kırmızı olurdu — DUZELTME-I18N §6-a dersi).
 *  - `etkinBicimYereli`: etkin dil en → en-GB, tr → tr-TR (eşleme `bicimYereli` — tek kaynak).
 *  - Hasta kartı özeti (`sonAnalizOzeti`): EN "17/11/2026 · …", TR "17.11.2026 · …".
 *  - Takip grafiği ekseni (`takipSerisiKur`): İngilizcede en-GB, Türkçede tr-TR (CLDR'de ikisinin gün-ay kalıbı da "17/11" — Türkçe aynen).
 * ÖNCE-KIRMIZI (sabit "tr-TR"): `etkinBicimYereli` yoktu; özet İngilizcede "17.11.2026" yazıyordu, eksen İngilizcede tr-TR ile biçimleniyordu.
 */
import { act } from "@testing-library/react-native";
import { __bayrakTestiAyarla, etkinBicimYereli } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { sonAnalizOzeti, type AnalizKaydi } from "@/utils/sonAnaliz";
import { takipSerisiKur } from "@/utils/takipSerisi";

const depo = { setItem: async () => undefined };
const AN = new Date(2026, 10, 17, 14, 5, 9); // YEREL saat → saat diliminden bağımsız

async function dil(d: "tr" | "en") {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec(d, depo);
  });
}

afterEach(async () => {
  await act(async () => {
    await dilSec("tr", depo);
  });
  __bayrakTestiAyarla(null);
});

describe("KP-7 C · Y295 biçim yereli etkin dilden", () => {
  it("en → en-GB (17/11/2026, 14:05:09, 1,234.56); tr → tr-TR (17.11.2026)", async () => {
    await dil("en");
    expect(etkinBicimYereli()).toBe("en-GB");
    expect(AN.toLocaleDateString(etkinBicimYereli())).toBe("17/11/2026");
    expect(AN.toLocaleTimeString(etkinBicimYereli())).toBe("14:05:09");
    expect((1234.56).toLocaleString(etkinBicimYereli())).toBe("1,234.56");
    await dil("tr");
    expect(etkinBicimYereli()).toBe("tr-TR");
    expect(AN.toLocaleDateString(etkinBicimYereli())).toBe("17.11.2026");
    expect((1234.56).toLocaleString(etkinBicimYereli())).toBe("1.234,56");
  });

  it("hasta kartı özeti: EN '17/11/2026 · …', TR '17.11.2026 · …'", async () => {
    const k: AnalizKaydi = { created_at: "2026-11-17T14:05:09", result_summary: "Kapanma %42" } as AnalizKaydi;
    await dil("en");
    expect(sonAnalizOzeti(k)).toBe("17/11/2026 · Kapanma %42");
    await dil("tr");
    expect(sonAnalizOzeti(k)).toBe("17.11.2026 · Kapanma %42");
  });

  // ⚠️ ÖLÇÜLDÜ: CLDR Türkçe gün-ay kısa kalıbı da `dd/MM` ("17/11") — eksen etiketi iki dilde AYNI görünür; Türkçe çıktı eskisiyle BAYT
  // BAYT aynı kalır. İddia yerel ayar sözleşmesidir: İngilizcede en-GB, Türkçede tr-TR (önce-kırmızı: İngilizcede de "tr-TR").
  it("takip grafiği ekseni: İngilizcede en-GB ile, Türkçede tr-TR ile (Türkçe çıktı aynen '17/11')", async () => {
    const kayitlar = [
      { created_at: "2026-11-17T10:00:00", module_id: "kp7", confidence: 0.5 },
      { created_at: "2026-11-18T10:00:00", module_id: "kp7", confidence: 0.6 },
    ] as unknown as Parameters<typeof takipSerisiKur>[0];
    const casus = jest.spyOn(Date.prototype, "toLocaleDateString");
    try {
      await dil("en");
      expect(takipSerisiKur(kayitlar)?.noktalar.map((n) => n.etiket)).toEqual(["17/11", "18/11"]);
      expect(casus.mock.calls.map((c) => c[0])).toEqual(["en-GB", "en-GB"]);
      casus.mockClear();
      await dil("tr");
      const tr = new Date(2026, 10, 17).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" });
      casus.mockClear();
      expect(takipSerisiKur(kayitlar)?.noktalar[0].etiket).toBe(tr);
      expect(casus.mock.calls.map((c) => c[0])).toEqual(["tr-TR", "tr-TR"]);
    } finally {
      casus.mockRestore();
    }
  });
});
