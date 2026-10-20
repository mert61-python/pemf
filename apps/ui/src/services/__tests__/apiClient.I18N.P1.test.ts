// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · apiClient kullanıcı iletileri iki dilde: HTTP hata kutuları (sunucu hatası, güvensiz bağlantı, jeton / internet reddi, zaman aşımı)
 * ve `aiHataMesaji` sınıfları. TR göç öncesiyle BAYT BAYT aynı; EN doğru ve eylem söyler (seans ve acil durdurma güvencesi aynı anlam).
 * ⚠️ Beklenen metinler BURADA sabittir. VERİ: sunucu `detail` metni ve istek yolu dilden bağımsız (AYNEN).
 */
import { act } from "@testing-library/react-native";

import { aiHataMesaji, apiPost, jetonRedBasligi } from "../apiClient";
import * as toastBridge from "../toastBridge";

import { serviceConfig } from "@/services/config";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

beforeEach(() => {
  serviceConfig.apiBaseUrl = "http://192.168.1.147:8000/api";
  serviceConfig.apiToken = "";
});
afterEach(async () => {
  jest.restoreAllMocks();
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});
async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

async function cagri(durum: number, detail: string | null, basliklar: Record<string, string> = {}, opts: object = {}) {
  const toasts: string[] = [];
  jest.spyOn(toastBridge, "emitToast").mockImplementation((msg: string) => {
    toasts.push(msg);
    return true;
  });
  const kucuk = Object.fromEntries(Object.entries(basliklar).map(([k, v]) => [k.toLowerCase(), v]));
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: durum,
    headers: { get: (ad: string) => kucuk[ad.toLowerCase()] ?? null },
    json: async () => (detail === null ? {} : { detail }),
  }) as unknown as typeof fetch;
  await apiPost("/ai/vision/landmark", {}, null, opts);
  return toasts;
}

describe("HTTP hata kutuları", () => {
  it("TR: sunucu hatası, jeton / internet reddi (sunucu metni yokken yedek), başlıklar göç öncesiyle aynı", async () => {
    expect(await cagri(500, null)).toEqual(["Sunucu Hatası: Sunucuya veri gönderilirken bir hata oluştu."]);
    expect(await cagri(500, "iç hata (sunucu metni)")).toEqual(["Sunucu Hatası: iç hata (sunucu metni)"]);
    expect(await cagri(402, null, { "X-PEMF-Jeton-Sebep": "cevrimdisi" })).toEqual([
      "İnternet bağlantısı gerekli: Yapay zekâ analizi için internet gerekir. Seans ve acil durdurma etkilenmez.",
    ]);
    expect(await cagri(402, null, { "X-PEMF-Jeton-Sebep": "yetersiz" })).toEqual(["Jeton hakkı: Jeton hakkınız yetersiz. Seans ve acil durdurma etkilenmez."]);
    expect(jetonRedBasligi("cevrimdisi")).toBe("İnternet bağlantısı gerekli");
    expect(jetonRedBasligi(null)).toBe("Jeton hakkı");
  });

  it("KRİTİK EN: sunucu hatası, jeton / internet reddi — 'seans ve acil durdurma etkilenmez' güvencesi korunur", async () => {
    await enYap();
    expect(await cagri(500, null)).toEqual(["Server Error: An error occurred while sending data to the server."]);
    expect(await cagri(500, "iç hata (sunucu metni)")).toEqual(["Server Error: iç hata (sunucu metni)"]); // sunucu metni AYNEN
    expect(await cagri(402, null, { "X-PEMF-Jeton-Sebep": "cevrimdisi" })).toEqual([
      "Internet connection required: AI analysis requires the internet. Sessions and emergency stop are not affected.",
    ]);
    expect(await cagri(402, null, { "X-PEMF-Jeton-Sebep": "yetersiz" })).toEqual([
      "Credit allowance: Your credit allowance is insufficient. Sessions and emergency stop are not affected.",
    ]);
    expect(jetonRedBasligi("cevrimdisi")).toBe("Internet connection required");
    expect(jetonRedBasligi(undefined)).toBe("Credit allowance");
  });

  it("zaman aşımı + cihaza ulaşılamadı + güvensiz bağlantı kutuları TR ve EN", async () => {
    const hatali = async (ad: string, opts: object) => {
      const toasts: string[] = [];
      jest.spyOn(toastBridge, "emitToast").mockImplementation((msg: string) => {
        toasts.push(msg);
        return true;
      });
      const e = new Error("x");
      e.name = ad;
      global.fetch = jest.fn().mockRejectedValue(e) as unknown as typeof fetch;
      await apiPost("/ai/vision/landmark", {}, null, opts);
      return toasts;
    };
    expect(await hatali("AbortError", {})).toEqual([
      "İşlem zaman aşımına uğradı: Sunucu zamanında yanıt vermedi. Tekrar deneyin — ilk analiz model yüklemesi nedeniyle uzun sürebilir.",
    ]);
    expect(await hatali("TypeError", { agHatasiMesaji: "Özel ağ iletisi" })).toEqual(["Cihaza ulaşılamadı: Özel ağ iletisi"]);
    serviceConfig.apiBaseUrl = "http://ornek.com/api";
    expect(await cagri(500, null)).toEqual(["Güvensiz bağlantı: Cihaz adresi şifresiz (http) ve yerel ağda değil — istek gönderilmedi."]);
    serviceConfig.apiBaseUrl = "http://192.168.1.147:8000/api";
    await enYap();
    expect(await hatali("AbortError", {})).toEqual([
      "The operation timed out: The server did not respond in time. Try again — the first analysis may take a long time because of model loading.",
    ]);
    expect(await hatali("TypeError", { agHatasiMesaji: "Özel ağ iletisi" })).toEqual(["Device unreachable: Özel ağ iletisi"]);
    serviceConfig.apiBaseUrl = "http://ornek.com/api";
    expect(await cagri(500, null)).toEqual([
      "Insecure connection: The device address is unencrypted (http) and not on the local network — the request was not sent.",
    ]);
  });
});

describe("aiHataMesaji", () => {
  const adli = (ad: string, m: string) => {
    const e = new Error(m);
    e.name = ad;
    return e;
  };

  it("TR: zaman aşımı / gönderilemedi / geçersiz yanıt / varsayılan göç öncesiyle aynı", () => {
    expect(aiHataMesaji(adli("AbortError", "x"))).toBe(
      "Analiz zaman aşımına uğradı. Bir modelin İLK çalıştırılması ~30 saniye sürebilir; aynı anda başka analizler çalışıyorsa daha da uzar. Tekrar deneyin — model artık hazır olduğu için bu kez hızlı sonuçlanır.",
    );
    expect(aiHataMesaji(new TypeError("Failed to fetch"))).toBe(
      "İstek cihaz yazılımına GÖNDERİLEMEDİ (tarayıcı isteği kesti: bağlantı koptu, ağ değişti ya da seçilen dosya okunamadı). Üstteki gösterge 'Çevrimdışı' ise önce bağlantıyı düzeltin; değilse dosyayı yeniden seçip tekrar deneyin. Sürerse uygulamayı yeniden başlatın.",
    );
    expect(aiHataMesaji(adli("SyntaxError", "x"))).toBe("Cihaz yazılımı geçersiz yanıt döndürdü (JSON değil). Tekrar deneyin; sürerse uygulama günlüklerini destek ekibine iletin.");
    expect(aiHataMesaji(new Error("diğer"))).toBe("Ağ veya sunucu hatası.");
    expect(aiHataMesaji(new Error("diğer"), "Bağlama özel")).toBe("Bağlama özel");
  });

  it("EN: aynı sınıflar İngilizce; 'Offline' göstergesi gerçek bağlantı rozetiyle aynı sözcük", async () => {
    await enYap();
    expect(aiHataMesaji(adli("TimeoutError", "x"))).toBe(
      "The analysis timed out. The FIRST run of a model can take ~30 seconds; it takes even longer if other analyses are running at the same time. Try again — the model is ready now, so this time it will finish quickly.",
    );
    expect(aiHataMesaji(new TypeError("Network request failed"))).toBe(
      "The request could NOT BE SENT to the device software (the browser cut the request: the connection dropped, the network changed or the selected file could not be read). If the indicator above says 'Offline', fix the connection first; otherwise select the file again and try again. If it continues, restart the application.",
    );
    expect(aiHataMesaji(adli("SyntaxError", "x"))).toBe("The device software returned an invalid response (not JSON). Try again; if it continues, send the application logs to the support team.");
    expect(aiHataMesaji(new Error("diğer"))).toBe("Network or server error.");
    expect(aiHataMesaji(new Error("diğer"), "Context specific")).toBe("Context specific");
  });
});
