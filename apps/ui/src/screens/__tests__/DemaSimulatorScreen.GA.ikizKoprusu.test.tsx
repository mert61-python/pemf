// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A4 — Simülasyon sekmesi ikiz köprüsü (WEB iframe): çerçeve YÜKLENMEDEN ileti yok; yüklenince `pemf.ikiz.durum` çerçevenin
 * KÖKENİNE (joker `*` DEĞİL); gelen ileti yalnız O çerçeveden + O kökenden ve yalnız `pemf.ikiz.hazir` → alan aboneliği; yeniden yükleme
 * köprüyü sıfırlar; ekrandan çıkınca dinleyici sökülür. Mobil WebView yolu: `DemaSimulatorScreen.GA.ikizKoprusu.native.test.tsx`.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("react-native-webview", () => ({ WebView: () => null }));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api", apiToken: "" } }));
const mockCtx: { snapshot: unknown; alanHaritasi: unknown; alanAbone: jest.Mock } = { snapshot: {}, alanHaritasi: null, alanAbone: jest.fn() };
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCtx }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const KOKEN = "http://192.168.1.5:8000";

describe("GA DEMA / ikiz köprüsü — web", () => {
  let dinleyiciler: ((e: unknown) => void)[];
  let ekle: jest.SpyInstance | undefined;
  const pencereler: { postMessage: jest.Mock }[] = [];
  beforeEach(() => {
    jest.useFakeTimers();
    mockCtx.snapshot = { stm: "online", coils: [] };
    mockCtx.alanHaritasi = null;
    mockCtx.alanAbone = jest.fn();
    dinleyiciler = [];
    pencereler.length = 0;
    const w = globalThis as unknown as { addEventListener?: unknown; removeEventListener?: unknown };
    w.addEventListener = jest.fn((tur: string, f: (e: unknown) => void) => {
      if (tur === "message") dinleyiciler.push(f);
    });
    w.removeEventListener = jest.fn((tur: string, f: (e: unknown) => void) => {
      dinleyiciler = dinleyiciler.filter((x) => x !== f);
    });
    ekle = undefined;
  });
  afterEach(() => {
    jest.useRealTimers();
    ekle?.mockRestore();
    const w = globalThis as unknown as { addEventListener?: unknown; removeEventListener?: unknown };
    delete w.addEventListener;
    delete w.removeEventListener;
  });

  const ciz = () =>
    render(<DemaSimulatorScreen />, {
      createNodeMock: (el: { type: unknown }) => {
        if (el.type !== "iframe") return null;
        const p = { postMessage: jest.fn() };
        pencereler.push(p);
        return { contentWindow: p };
      },
    });
  const cerceve = (u: ReturnType<typeof render>) => u.UNSAFE_getByType("iframe" as unknown as React.ComponentType);
  const turler = (p: { postMessage: jest.Mock }) => p.postMessage.mock.calls.map((c) => JSON.parse(c[0]).tur);

  it("yüklenmeden ileti yok; yüklenince durum ÇERÇEVE KÖKENİNE; hazir yalnız o çerçeve + köken; yeniden yükleme sıfırlar", () => {
    const u = ciz();
    act(() => jest.advanceTimersByTime(1500));
    expect(pencereler[0].postMessage).not.toHaveBeenCalled();
    act(() => cerceve(u).props.onLoad());
    expect(turler(pencereler[0])).toEqual(["pemf.ikiz.durum"]);
    expect(pencereler[0].postMessage.mock.calls[0][1]).toBe(KOKEN);
    expect(dinleyiciler.length).toBe(1);
    const hazir = JSON.stringify({ tur: "pemf.ikiz.hazir", surum: 1 });
    act(() => dinleyiciler[0]({ source: {}, origin: KOKEN, data: hazir })); // BAŞKA çerçeve
    act(() => dinleyiciler[0]({ source: pencereler[0], origin: "http://kotu.example", data: hazir })); // başka köken
    act(() => dinleyiciler[0]({ source: null, origin: KOKEN, data: hazir }));
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    act(() => dinleyiciler[0]({ source: pencereler[0], origin: KOKEN, data: '{"tur":"pemf.ikiz.komut"}' }));
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    act(() => dinleyiciler[0]({ source: pencereler[0], origin: KOKEN, data: hazir }));
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true]]);
    act(() => fireEvent.press(u.getByLabelText(T("dema.yenidenYukleEtiketi"))));
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true], [false]]); // yeni çerçeve — yeniden hazir beklenir
    const onceki = pencereler[0].postMessage.mock.calls.length;
    act(() => jest.advanceTimersByTime(1500));
    expect(pencereler[0].postMessage.mock.calls.length).toBe(onceki); // eski çerçeveye gönderim YOK
    u.unmount();
    expect(dinleyiciler.length).toBe(0);
  });

  it("API adresi çözülemezse (köken yok) gönderim de kabul de YOK", () => {
    const cfg = jest.requireMock("@/services/config") as { serviceConfig: { apiBaseUrl: string } };
    const eski = cfg.serviceConfig.apiBaseUrl;
    cfg.serviceConfig.apiBaseUrl = "bozuk adres";
    try {
      const u = ciz();
      act(() => cerceve(u).props.onLoad());
      act(() => jest.advanceTimersByTime(1000));
      expect(pencereler[0].postMessage).not.toHaveBeenCalled();
      act(() => dinleyiciler[0]({ source: pencereler[0], origin: "null", data: '{"tur":"pemf.ikiz.hazir"}' }));
      expect(mockCtx.alanAbone).not.toHaveBeenCalled();
      u.unmount();
    } finally {
      cfg.serviceConfig.apiBaseUrl = eski;
    }
  });

  it("çerçeve penceresi yoksa (sökülmüş) gönderim sessizce atlanır", () => {
    const u = render(<DemaSimulatorScreen />, { createNodeMock: () => ({ contentWindow: null }) });
    act(() => cerceve(u).props.onLoad());
    act(() => jest.advanceTimersByTime(1000));
    u.unmount();
  });
});
