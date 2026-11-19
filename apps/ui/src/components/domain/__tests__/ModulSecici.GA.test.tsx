// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — modül seçicisi + panel yuvası: GİZLİYKEN hiç çizilmez; "PEMF cihazı" + modüller (etkin dilde ad); bozuk modül
 * seçilemez ve nedeni yazılır; seçim sunucuya → başarılıysa üst bileşene, başarısızsa eylem metni; sunucuda zaten etkin modül varsa
 * açılışta seçilir; panel tembel yüklenir, kaydı yoksa eylem metni.
 */
const mockApi = { listele: jest.fn(), sec: jest.fn(), birak: jest.fn() };
jest.mock("@/services/moduller", () => {
  const gercek = jest.requireActual("@/services/moduller");
  return {
    modulAdi: gercek.modulAdi,
    modulHataMetni: gercek.modulHataMetni,
    get modulApi() {
      return mockApi; // getter: fabrika hoist edilir (KP-8 dersi)
    },
  };
});
jest.mock("@/moduller/kayit", () => {
  const R = jest.requireActual("react");
  const { Text } = jest.requireActual("react-native");
  return { PANELLER: { ornek: R.lazy(async () => ({ default: () => R.createElement(Text, { testID: "sahte-panel" }, "panel") })) } };
});

import React from "react";
import i18n from "i18next";
import { act, fireEvent, render } from "@testing-library/react-native";
import { ModulPaneli, ModulSecici } from "@/components/domain/ModulSecici";

const T = (k: string, o?: object): string => (i18n.t as unknown as (a: string, b?: object) => string)(k, o);
const LISTE = {
  gorunur: true,
  etkin: null,
  canli: false,
  hata: null,
  moduller: [
    { kimlik: "ornek", ad: { tr: "Örnek modül", en: "Example module" } },
    { kimlik: "bozuk", hata: "semaUyumsuz", alan: "sema" },
  ],
};

describe("GA ModulSecici", () => {
  beforeEach(async () => {
    for (const f of Object.values(mockApi)) f.mockReset();
    await i18n.changeLanguage("tr");
  });

  it("gizliyken / liste alınamazken HİÇ çizilmez", async () => {
    mockApi.listele.mockResolvedValue({ tamam: true, veri: { ...LISTE, gorunur: false } });
    const u = render(<ModulSecici etkin={null} onSec={jest.fn()} />);
    await act(async () => {});
    expect(u.queryByTestId("modul-secici")).toBeNull();
    mockApi.listele.mockResolvedValue({ tamam: false, hata: { kod: "baglanti", alan: "" } });
    const u2 = render(<ModulSecici etkin={null} onSec={jest.fn()} />);
    await act(async () => {});
    expect(u2.queryByTestId("modul-secici")).toBeNull();
    u2.unmount();
    mockApi.listele.mockReturnValue(new Promise(() => {}));
    render(<ModulSecici etkin={null} onSec={jest.fn()} />).unmount();
  });

  it("seçim: başarı → üst bileşen; hata → metin; bozuk seçilemez; PEMF → bırak", async () => {
    mockApi.listele.mockResolvedValue({ tamam: true, veri: LISTE });
    const onSec = jest.fn();
    const u = render(<ModulSecici etkin={null} onSec={onSec} />);
    await act(async () => {});
    expect(u.getByText(T("kontrol.modul.secici.pemf"))).toBeTruthy();
    expect(u.getByText("Örnek modül")).toBeTruthy();
    expect(u.getByTestId("modul-sec-bozuk").props.accessibilityState.disabled).toBe(true);
    await act(async () => fireEvent.press(u.getByTestId("modul-sec-bozuk")));
    expect(mockApi.sec).not.toHaveBeenCalled(); // bozuk modül SEÇİLEMEZ
    expect(u.getByTestId("modul-bozuk-bozuk").props.children).toBe(T("kontrol.modul.secici.bozuk", { kimlik: "bozuk", hata: "semaUyumsuz" }));
    mockApi.sec.mockResolvedValueOnce({ tamam: false, hata: { kod: "baglanamadi", alan: "kartBulunamadi" } });
    await act(async () => fireEvent.press(u.getByTestId("modul-sec-ornek")));
    expect(onSec).not.toHaveBeenCalled();
    expect(u.getByTestId("modul-secici-hata").props.children).toBe(T("kontrol.modul.hata.baglanamadi", { neden: "kartBulunamadi" }));
    mockApi.sec.mockResolvedValueOnce({ tamam: true, veri: {} });
    await act(async () => fireEvent.press(u.getByTestId("modul-sec-ornek")));
    expect(onSec).toHaveBeenLastCalledWith("ornek");
    expect(u.queryByTestId("modul-secici-hata")).toBeNull();
    await act(async () => fireEvent.press(u.getByTestId("modul-sec-pemf"))); // zaten PEMF (etkin=null) → istek yok
    expect(mockApi.birak).not.toHaveBeenCalled();
    u.rerender(<ModulSecici etkin="ornek" onSec={onSec} />);
    await act(async () => fireEvent.press(u.getByTestId("modul-sec-ornek"))); // zaten seçili → istek yok
    expect(mockApi.sec).toHaveBeenCalledTimes(2);
    let coz: (v: unknown) => void = () => {};
    mockApi.birak.mockReturnValue(new Promise((r) => (coz = r)));
    act(() => fireEvent.press(u.getByTestId("modul-sec-pemf")));
    act(() => fireEvent.press(u.getByTestId("modul-sec-pemf"))); // istek sürerken ikinci basış yok sayılır
    expect(mockApi.birak).toHaveBeenCalledTimes(1);
    await act(async () => coz({ tamam: true, veri: {} }));
    expect(onSec).toHaveBeenLastCalledWith(null);
  });

  it("sunucuda zaten etkin modül → açılışta seçilir; EN adlar", async () => {
    await i18n.changeLanguage("en");
    mockApi.listele.mockResolvedValue({ tamam: true, veri: { ...LISTE, etkin: "ornek" } });
    const onSec = jest.fn();
    const u = render(<ModulSecici etkin={null} onSec={onSec} />);
    await act(async () => {});
    expect(onSec).toHaveBeenCalledWith("ornek");
    expect(u.getByText("Example module")).toBeTruthy();
  });

  it("panel yuvası: tembel yüklenir; kaydı yoksa eylem metni", async () => {
    const u = render(<ModulPaneli kimlik="ornek" />);
    expect(u.getByText(T("kontrol.modul.panel.yukleniyor"))).toBeTruthy();
    await act(async () => {});
    expect(u.getByTestId("sahte-panel")).toBeTruthy();
    const y = render(<ModulPaneli kimlik="yok" />);
    expect(y.getByTestId("modul-panel-yok").props.children).toBe(T("kontrol.modul.panel.yok"));
  });
});
