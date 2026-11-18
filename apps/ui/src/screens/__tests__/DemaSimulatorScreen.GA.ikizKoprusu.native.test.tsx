// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A4 — Simülasyon sekmesi ikiz köprüsü (MOBİL WebView): yüklenince `WebView.postMessage` ile `pemf.ikiz.durum`; mevcut
 * yükseklik iletisi AYNEN çalışır; `pemf.ikiz.hazir` → alan aboneliği; başka ileti yok sayılır.
 */
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
const mockWV: { props: Record<string, any> | null; gonderilen: string[] } = { props: null, gonderilen: [] };
jest.mock("react-native-webview", () => {
  const R = jest.requireActual("react");
  class WebView extends R.Component<Record<string, unknown>> {
    postMessage(m: string) {
      mockWV.gonderilen.push(m);
    }
    render() {
      mockWV.props = this.props;
      return null;
    }
  }
  return { WebView };
});
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api", apiToken: "" } }));
const mockCtx: { snapshot: unknown; alanHaritasi: unknown; alanAbone: jest.Mock } = { snapshot: {}, alanHaritasi: null, alanAbone: jest.fn() };
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCtx }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";

it("GA: mobil WebView — yüklenince durum, yükseklik iletisi korunur, hazir → abonelik", () => {
  jest.useFakeTimers();
  try {
    mockCtx.snapshot = { stm: "online", coils: [] };
    const u = render(<DemaSimulatorScreen />);
    act(() => jest.advanceTimersByTime(1000));
    expect(mockWV.gonderilen).toEqual([]);
    act(() => mockWV.props!.onLoadStart());
    act(() => mockWV.props!.onLoadEnd());
    expect(mockWV.gonderilen.map((m) => JSON.parse(m).tur)).toEqual(["pemf.ikiz.durum"]);
    act(() => mockWV.props!.onMessage({ nativeEvent: { data: "1840" } })); // DEMA yükseklik iletisi
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    expect(JSON.stringify(u.toJSON())).toContain("1840");
    act(() => mockWV.props!.onMessage({ nativeEvent: { data: '{"tur":"pemf.ikiz.hazir","surum":1}' } }));
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true]]);
    u.unmount();
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true], [false]]);
  } finally {
    jest.useRealTimers();
  }
});
