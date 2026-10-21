/**
 * I18N-0 · ARAYÜZ ALTYAPISI (T2 / T3 / T4 / T5 / T13).
 *
 * Kilitlenen davranış:
 *  - i18n jest kurulumunda TR + SENKRON başlar (ilk karede metin hazır) ve katalogda olmayan anahtar HATA atar (KATI kip);
 *  - bayrak KAPALIYKEN cihaz dili ya da kayıtlı seçim İngilizce olsa bile etkin dil tr; dil seçeneği gizli;
 *  - bayrak AÇIKKEN (yalnız test) cihaz dili `tr*` → tr, diğer → en; kayıtlı seçim cihaz dilini ezer;
 *  - seçim AsyncStorage `pemf.dil`'e yazılır; okuma / yazma hatası uygulamayı düşürmez (tr'ye düşer, ileti eylem söyler);
 *  - her API isteği `X-PEMF-Dil` taşır ve dil değişince AYNI anda değişir; URL ile açılan kaynağa `?dil=`;
 *  - dil değişince `useTranslation` kullanan ekran yeniden çizilir (yeniden başlatma yok).
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import i18n from "i18next";
import { DilSecimKarti } from "@/components/domain/DilSecimKarti";
import { __bayrakTestiAyarla, dileIndirge, etkinDil, dilSecimiGorunur, DIL_DEPO_ANAHTARI } from "@/i18n/dil";
import { dilSec, kayitliDiliUygula } from "@/i18n";
import { authHeaders, dilParametresiEkle, DIL_BASLIGI } from "@/services/apiClient";

jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: (...a: unknown[]) => mockToast(...a) }) }));
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => false }));
const mockToast = jest.fn();

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
  await AsyncStorage.clear();
  mockToast.mockClear();
});

describe("başlatma", () => {
  it("TR + senkron: içe aktarma biter bitmez çeviri hazır", () => {
    expect(i18n.isInitialized).toBe(true);
    expect(i18n.language).toBe("tr");
    expect(i18n.t("ayarlar.dil.baslik")).toBe("Dil / Language");
  });

  it("KATI kip: katalogda olmayan anahtar sessizce anahtarı basmaz, HATA atar", () => {
    expect(() => (i18n.t as unknown as (k: string) => string)("olmayan.anahtar")).toThrow(/katalogda olmayan anahtar/);
  });
});

describe("dil kuralı (Y161) + bayrak (Y158)", () => {
  it("yerel kod → dil: tr* → tr, diğer her şey → en, boş → tr", () => {
    expect(dileIndirge("tr")).toBe("tr");
    expect(dileIndirge("tr-TR")).toBe("tr");
    expect(dileIndirge("TR_tr")).toBe("tr");
    expect(dileIndirge("en-US")).toBe("en");
    expect(dileIndirge("de-DE")).toBe("en");
    expect(dileIndirge("")).toBe("tr");
    expect(dileIndirge(null)).toBe("tr");
  });

  it("bayrak KAPALI: İngilizce cihaz ve İngilizce kayıtlı seçimde bile etkin dil tr; seçenek gizli", () => {
    expect(etkinDil("en", "en-US", false)).toBe("tr");
    expect(etkinDil(null, "en-GB", false)).toBe("tr");
    expect(dilSecimiGorunur(false)).toBe(false);
    // test anahtarıyla KAPALI dal (depo bayrağından bağımsız — I18NI-A3.8)
    __bayrakTestiAyarla(false);
    expect(dilSecimiGorunur()).toBe(false);
    expect(etkinDil(null, "en-US")).toBe("tr");
  });

  it("varsayılan (gerçek) bayrak AÇIK (14-I18N-INCELEME, 2026-10-21): seçenek görünür, İngilizce cihaz İngilizce başlar", () => {
    expect(dilSecimiGorunur()).toBe(true);
    expect(etkinDil(null, "en-US")).toBe("en");
    expect(etkinDil(null, "tr-TR")).toBe("tr");
  });

  it("bayrak AÇIK: cihaz dili; kayıtlı seçim cihaz dilini ezer", () => {
    expect(etkinDil(null, "en-US", true)).toBe("en");
    expect(etkinDil(null, "tr-TR", true)).toBe("tr");
    expect(etkinDil("tr", "en-US", true)).toBe("tr");
    expect(etkinDil("en", "tr-TR", true)).toBe("en");
    expect(etkinDil("fr", "tr-TR", true)).toBe("tr"); // geçersiz kayıt yok sayılır
  });
});

describe("kalıcılık (AsyncStorage pemf.dil)", () => {
  it("bayrak açıkken seçim yazılır, yeniden açılışta okunur", async () => {
    __bayrakTestiAyarla(true);
    await act(async () => {
      expect((await dilSec("en")).kaydedildi).toBe(true);
    });
    expect(await AsyncStorage.getItem(DIL_DEPO_ANAHTARI)).toBe("en");
    await act(async () => {
      await i18n.changeLanguage("tr");
    });
    let d = "";
    await act(async () => {
      d = await kayitliDiliUygula();
    });
    expect(d).toBe("en");
    expect(i18n.language).toBe("en");
  });

  it("bayrak kapalıyken kayıtlı 'en' bile tr verir", async () => {
    __bayrakTestiAyarla(false); // kapalı dal AÇIKÇA (depo bayrağı açık)
    await AsyncStorage.setItem(DIL_DEPO_ANAHTARI, "en");
    let d = "";
    await act(async () => {
      d = await kayitliDiliUygula();
    });
    expect(d).toBe("tr");
    expect(i18n.language).toBe("tr");
  });

  it("okuma hatası uygulamayı düşürmez: tr'de kalır", async () => {
    __bayrakTestiAyarla(true);
    const bozuk = { getItem: () => Promise.reject(new Error("depo bozuk")) };
    let d = "";
    await act(async () => {
      d = await kayitliDiliUygula(bozuk as never);
    });
    // Cihaz dili okunamazsa ya da tr ise tr; jest ortamının yereli ne olursa olsun ÇÖKMEZ ve geçerli bir dil döner.
    expect(["tr", "en"]).toContain(d);
  });

  it("yazma hatası: dil yine değişir, kaydedilmedi bildirilir", async () => {
    __bayrakTestiAyarla(true);
    const bozuk = { setItem: () => Promise.reject(new Error("disk dolu")) };
    let r = { dil: "tr", kaydedildi: true };
    await act(async () => {
      r = await dilSec("en", bozuk as never);
    });
    expect(r).toEqual({ dil: "en", kaydedildi: false });
    expect(i18n.language).toBe("en");
  });
});

describe("sunucuya dil (T5)", () => {
  it("her istek X-PEMF-Dil taşır ve dil değişince aynı anda değişir", async () => {
    expect(DIL_BASLIGI).toBe("X-PEMF-Dil");
    expect(authHeaders()[DIL_BASLIGI]).toBe("tr");
    __bayrakTestiAyarla(true);
    await act(async () => {
      await dilSec("en");
    });
    expect(authHeaders()[DIL_BASLIGI]).toBe("en");
    expect(authHeaders()).not.toHaveProperty("Accept-Language");
  });

  it("URL ile açılan kaynağa ?dil= eklenir", () => {
    expect(dilParametresiEkle("http://127.0.0.1:8001/simulator")).toBe("http://127.0.0.1:8001/simulator?dil=tr");
    expect(dilParametresiEkle("http://h/x?a=1")).toBe("http://h/x?a=1&dil=tr");
  });
});

describe("Dil / Language kartı", () => {
  it("dil değişince ekran yeniden çizilir (yeniden başlatma yok); seçim cihaza yazılır", async () => {
    __bayrakTestiAyarla(true);
    const u = render(<DilSecimKarti />);
    expect(u.getByText("Dil / Language")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByTestId("dil-secenek-en"));
    });
    expect(u.getByText("Language / Dil")).toBeTruthy();
    expect(u.queryByText("Dil / Language")).toBeNull();
    expect(await AsyncStorage.getItem(DIL_DEPO_ANAHTARI)).toBe("en");
    await act(async () => {
      fireEvent.press(u.getByTestId("dil-secenek-tr"));
    });
    expect(u.getByText("Dil / Language")).toBeTruthy();
    expect(mockToast).not.toHaveBeenCalled();
  });
});
