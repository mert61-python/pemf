// Author: mertaygn, cglrgrkn
/**
 * YH-A4 (Tezgâh-2 listesi 4) — web'de onay / uyarı pencereleri UYGULAMANIN İÇİNDE açılır.
 * ==========================================================================
 * ÖLÇÜLEN KUSUR (tezgâh 13 Kasım 2026): masaüstü uygulama penceresinde Sürüş Kipi ve ACİL DURDUR mandalı "Sıfırla" onayı tarayıcının
 * YERLİ penceresiyle açılıyordu — başlık "127.0.0.1:8000 şunu diyor:", uygulamanın dili / görünümü yok. `platformConfirm` /
 * `platformAlert` web'de `window.confirm` / `window.alert` çağırıyordu.
 * Kilitlenen: sağlayıcı takılıyken web'de yerli pencere AÇILMAZ; başlık / gövde / düğme etiketi uygulama içi pencerede; Onay → true,
 * İptal / Esc → false; sorular SIRAYLA; uyarı tek düğme ("Kapat"). KARŞIT: sağlayıcısız ağaçta eski yerli pencere (sessiz "evet" YOK);
 * sağlayıcı sökülünce bekleyen soru false. Telefon (native) `Alert.alert` yolu DEĞİŞMEDİ (KP3-servis-kollari "native onay").
 * ⚠️ MUTASYON: apiClient'ta köprü çağrısı silinirse / pencere onay-vazgeç değerlerini karıştırırsa KIRMIZI.
 */
import React from "react";
import { Modal, Platform } from "react-native";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import i18n from "i18next";
import { platformAlert, platformConfirm } from "@/services/apiClient";
import { OnayPenceresiSaglayici } from "@/components/ui/OnayPenceresiSaglayici";
import { setOnayIsleyici } from "@/services/onayKoprusu";

const asilOS = Platform.OS;
let yerliOnay: jest.Mock;
let yerliUyari: jest.Mock;

beforeEach(() => {
  (Platform as { OS: string }).OS = "web";
  yerliOnay = jest.fn(() => true);
  yerliUyari = jest.fn();
  (window as unknown as { confirm: unknown }).confirm = yerliOnay;
  (window as unknown as { alert: unknown }).alert = yerliUyari;
});
afterEach(() => {
  (Platform as { OS: string }).OS = asilOS;
  setOnayIsleyici(null);
});

const agac = () => render(<OnayPenceresiSaglayici><></></OnayPenceresiSaglayici>);

it("KRİTİK: web'de platformConfirm YERLİ pencere açmaz; uygulama içi pencere başlık / gövde / etiket gösterir, Onay → true", async () => {
  agac();
  let sonuc: Promise<boolean>;
  await act(async () => {
    sonuc = platformConfirm("Tek yönlü sürüş", "Bobinler tek yönlü sürülecek.", "Tek yönlü yap");
  });
  expect(yerliOnay).not.toHaveBeenCalled();
  expect(screen.getByTestId("onay-penceresi-baslik").props.children).toBe("Tek yönlü sürüş");
  expect(screen.getByTestId("onay-penceresi-govde").props.children).toBe("Bobinler tek yönlü sürülecek.");
  expect(screen.getByText("Tek yönlü yap")).toBeTruthy();
  expect(screen.getByText(i18n.t("ortak.iptal"))).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId("onay-penceresi-onay")));
  await expect(sonuc!).resolves.toBe(true);
  expect(screen.queryByTestId("onay-penceresi")).toBeNull();
});

it("KRİTİK: İptal → false; Esc / geri (onRequestClose) → false — vazgeçmek hiçbir zaman 'evet' sayılmaz", async () => {
  agac();
  let a: Promise<boolean>;
  await act(async () => {
    a = platformConfirm("Sıfırla", "Mandal sıfırlansın mı?");
  });
  expect(screen.getByText(i18n.t("ortak.onayla"))).toBeTruthy(); // etiket verilmezse varsayılan "Onayla"
  await act(async () => fireEvent.press(screen.getByTestId("onay-penceresi-vazgec")));
  await expect(a!).resolves.toBe(false);
  let b: Promise<boolean>;
  await act(async () => {
    b = platformConfirm("Sil", "Kayıt silinsin mi?", "Sil");
  });
  await act(async () => screen.UNSAFE_getByType(Modal).props.onRequestClose());
  await expect(b!).resolves.toBe(false);
  expect(yerliOnay).not.toHaveBeenCalled();
});

it("iki soru SIRAYLA gösterilir — ikinci, birincinin yanıtını ezmez", async () => {
  agac();
  let a: Promise<boolean>;
  let b: Promise<boolean>;
  await act(async () => {
    a = platformConfirm("Birinci", "1");
    b = platformConfirm("İkinci", "2");
  });
  expect(screen.getByTestId("onay-penceresi-baslik").props.children).toBe("Birinci");
  await act(async () => fireEvent.press(screen.getByTestId("onay-penceresi-vazgec")));
  await expect(a!).resolves.toBe(false);
  expect(screen.getByTestId("onay-penceresi-baslik").props.children).toBe("İkinci");
  await act(async () => fireEvent.press(screen.getByTestId("onay-penceresi-onay")));
  await expect(b!).resolves.toBe(true);
});

it("web'de platformAlert uygulama içi TEK düğmeli pencere ('Kapat'); yerli uyarı yok", async () => {
  agac();
  await act(async () => platformAlert("Durdurulamadı", "Kartı denetleyin."));
  expect(yerliUyari).not.toHaveBeenCalled();
  expect(screen.getByTestId("onay-penceresi-baslik").props.children).toBe("Durdurulamadı");
  expect(screen.queryByTestId("onay-penceresi-vazgec")).toBeNull();
  expect(screen.getByText(i18n.t("ortak.kapat"))).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId("onay-penceresi-onay")));
  expect(screen.queryByTestId("onay-penceresi")).toBeNull();
});

it("KARŞIT: sağlayıcı YOKKEN eski yerli pencereye düşer (sessiz 'evet' YOK) — yerli yanıt aynen döner", async () => {
  yerliOnay.mockReturnValueOnce(false);
  await expect(platformConfirm("Sil", "Emin misiniz?")).resolves.toBe(false);
  expect(yerliOnay).toHaveBeenCalledWith("Sil\n\nEmin misiniz?");
  platformAlert("Başlık", "Gövde");
  expect(yerliUyari).toHaveBeenCalledWith("Başlık\nGövde");
});

it("sağlayıcı SÖKÜLÜNCE bekleyen soru false ile çözülür (askıda söz kalmaz) ve köprü boşalır", async () => {
  const r = agac();
  let a: Promise<boolean>;
  await act(async () => {
    a = platformConfirm("Sil", "Emin misiniz?");
  });
  r.unmount();
  await expect(a!).resolves.toBe(false);
  await expect(platformConfirm("Yeniden", "?")).resolves.toBe(true); // köprü boş → yerli pencere (sahte: true)
  expect(yerliOnay).toHaveBeenCalledTimes(1);
});

it("KRİTİK: kök düzen (app/_layout) sağlayıcıyı TAKAR — gerçek uygulamada web onayları köprüye düşer", () => {
  // KP3-RootLayout deseni: yalıtılmış kayıtta kök düzen + AYNI kayıttaki köprü (tek React örneği).
  let Kok: React.ComponentType | undefined;
  let kopru: typeof import("@/services/onayKoprusu") | undefined;
  jest.isolateModules(() => {
    jest.doMock("react", () => React);
    jest.doMock("@/theme/fonts", () => ({ useFonts: () => [true], INTER_FONTS: {}, applyGlobalInter: () => undefined }));
    jest.doMock("expo-router", () => ({ Stack: () => null }));
    jest.doMock("expo-status-bar", () => ({ StatusBar: () => null }));
    jest.doMock("react-native-safe-area-context", () => ({
      SafeAreaProvider: ({ children }: { children: unknown }) => children,
      useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    }));
    jest.doMock("@/components/domain/MobileUpdateGate", () => ({
      MobileUpdateGate: ({ children }: { children: unknown }) => children,
    }));
    Kok = require("../../../../app/_layout").default;
    kopru = require("@/services/onayKoprusu");
  });
  expect(kopru!.uygulamaIciOnay({ baslik: "x", govde: "y", tur: "onay" })).toBeNull(); // aparat: takılmadan önce boş
  const u = render(React.createElement(Kok!));
  let soz: Promise<boolean> | null = null;
  act(() => {
    soz = kopru!.uygulamaIciOnay({ baslik: "x", govde: "y", tur: "onay" });
  });
  expect(soz).not.toBeNull();
  u.unmount();
  return expect(soz).resolves.toBe(false);
});
