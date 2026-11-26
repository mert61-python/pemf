/**
 * KP-3 C · küçük arayüz yapı taşlarının kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - AuroraBackground: üç parıltının opaklığı `intensity` ile ölçeklenir ve [0, 1]'e SINIRLANIR (aşırı / negatif değer görüntüyü
 *    bozamaz); aynı sayfadaki iki örneğin gradyan kimlikleri ÇAKIŞMAZ (biri diğerinin rengini almaz).
 *  - MetricCard: vurgu şeridinin soluk ucu tonun %22 saydam hali — 3 haneli hex genişletilir, 8 haneli hex'in alfa çifti atılır, geçersiz
 *    renk SİYAHA değil güvenli maviye düşer; ekran okuyucu etiket + değeri tek cümlede okur.
 *  - useNetworkReachability: ağ geri gelince yeniden bağlanma 1,5 sn GECİKMELİ ve tek kez; aynı durum tekrarlanırsa yok sayılır; süre
 *    dolmadan ağ yine düşerse tetiklenmez; söküldüğünde dinleyici kaldırılır (kaldırma atsa da çökmez).
 *  - ToastProvider: görünen HATA iletisini daha düşük öncelikli (bilgi) ileti EZEMEZ, yeni hata ezer; ileti 3 sn sonra kaybolur ve
 *    ardından bilgi iletisi yeniden gösterilebilir; sağlayıcısız kullanım AÇIK hata verir.
 *  - Button: "hareketi azalt" açıkken basma küçülme animasyonu KOŞMAZ; kapalıyken yay animasyonu basma ölçeğine gider.
 * SAHTE: NetInfo (yerel modül), expo-linear-gradient (aldığı props kaydedilir), AccessibilityInfo hareket-azaltma ayarı.
 */
type NetDinleyici = (s: { isConnected: boolean }) => void;
const mockNet: { dinleyici?: NetDinleyici; sokuldu: number; sokmeAtar: boolean } = { sokuldu: 0, sokmeAtar: false };
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: {
    addEventListener: (f: NetDinleyici) => {
      mockNet.dinleyici = f;
      return () => { mockNet.sokuldu += 1; if (mockNet.sokmeAtar) throw new Error("söküm düştü"); };
    },
  },
}));
const mockGradyan: { colors: string[] }[] = [];
jest.mock("expo-linear-gradient", () => ({
  LinearGradient: (p: { colors: string[] }) => { mockGradyan.push(p); return null; },
}));

import React from "react";
import { AccessibilityInfo, Animated } from "react-native";
import { act, fireEvent, render, renderHook } from "@testing-library/react-native";
import { Stop, RadialGradient } from "react-native-svg";
import { AuroraBackground } from "@/components/ui/AuroraBackground";
import { MetricCard } from "@/components/ui/MetricCard";
import { ToastProvider, useToast } from "@/components/ui/ToastProvider";
import { Button } from "@/components/ui/Button";
import { useNetworkReachability } from "@/hooks/useNetworkReachability";
import { motion } from "@/theme/tokens";

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

describe("AuroraBackground", () => {
  const opaklar = (u: ReturnType<typeof render>) =>
    u.UNSAFE_getAllByType(Stop).filter((s) => s.props.offset === "0%").map((s) => s.props.stopOpacity);

  it("opaklık intensity ile ölçeklenir ve [0, 1]'e sınırlanır; iki örneğin gradyan kimlikleri çakışmaz", () => {
    expect(opaklar(render(<AuroraBackground />))).toEqual([0.4, 0.34, 0.16]);
    expect(opaklar(render(<AuroraBackground intensity={3} />))).toEqual([1, 1, 0.48]);
    expect(opaklar(render(<AuroraBackground intensity={-2} />))).toEqual([0, 0, 0]);
    const u = render(<><AuroraBackground /><AuroraBackground /></>);
    const kimlikler = u.UNSAFE_getAllByType(RadialGradient).map((g) => g.props.id);
    expect(new Set(kimlikler).size).toBe(6);
  });
});

describe("MetricCard", () => {
  beforeEach(() => { mockGradyan.length = 0; });
  it.each([
    ["#abc", "rgba(170, 187, 204, 0.22)"],
    ["#11223344", "rgba(17, 34, 51, 0.22)"],
    ["kırmızı", "rgba(79, 140, 255, 0.22)"],
  ])("ton %s → soluk uç %s", (ton, beklenen) => {
    render(<MetricCard label="Seans" value="12" tone={ton} />);
    expect(mockGradyan[0].colors).toEqual([ton, beklenen]);
  });
  it("ekran okuyucu etiket + değeri tek cümlede okur", () => {
    const u = render(<MetricCard label="Seans" value="12" />);
    expect(u.getByLabelText("Seans: 12")).toBeTruthy();
  });
});

describe("useNetworkReachability", () => {
  beforeEach(() => { mockNet.sokuldu = 0; mockNet.sokmeAtar = false; mockNet.dinleyici = undefined; });
  it("ağ gelince 1,5 sn sonra TEK yeniden bağlanma; aynı durum yok sayılır; süre dolmadan düşerse tetiklenmez; söküm güvenli", () => {
    jest.useFakeTimers();
    const yeniden = jest.fn();
    const h = renderHook(() => useNetworkReachability(yeniden));
    act(() => { mockNet.dinleyici!({ isConnected: true }); });
    act(() => { jest.advanceTimersByTime(1000); });
    act(() => { mockNet.dinleyici!({ isConnected: true }); }); // aynı durum tekrarı → yok sayılır (gecikmeyi UZATMAZ)
    act(() => { jest.advanceTimersByTime(499); });
    expect(yeniden).not.toHaveBeenCalled();
    act(() => { jest.advanceTimersByTime(1); });
    expect(yeniden).toHaveBeenCalledTimes(1);
    act(() => { mockNet.dinleyici!({ isConnected: false }); });
    act(() => { mockNet.dinleyici!({ isConnected: true }); });
    act(() => { jest.advanceTimersByTime(1000); });
    act(() => { mockNet.dinleyici!({ isConnected: false }); }); // gidip geldi → bekleyen tetik iptal
    act(() => { jest.advanceTimersByTime(5000); });
    expect(yeniden).toHaveBeenCalledTimes(1);
    mockNet.sokmeAtar = true;
    expect(() => h.unmount()).not.toThrow();
    expect(mockNet.sokuldu).toBe(1);
  });
});

describe("ToastProvider", () => {
  let goster: ReturnType<typeof useToast>["showToast"];
  function Tuketici() { goster = useToast().showToast; return null; }
  const metin = (u: ReturnType<typeof render>, m: string) => u.queryByText(m);

  it("hata iletisini bilgi EZEMEZ, yeni hata ezer; 3 sn sonra kaybolur ve bilgi yeniden gösterilebilir", () => {
    jest.useFakeTimers();
    const u = render(<ToastProvider><Tuketici /></ToastProvider>);
    act(() => { goster("Bobin 3 durdurulamadı", "error"); });
    act(() => { goster("Kayıt alındı", "info"); });
    expect(metin(u, "Bobin 3 durdurulamadı")).toBeTruthy();
    expect(metin(u, "Kayıt alındı")).toBeNull();
    act(() => { goster("Bağlantı koptu", "error"); });
    expect(metin(u, "Bağlantı koptu")).toBeTruthy();
    act(() => { jest.advanceTimersByTime(3000); });
    act(() => { jest.advanceTimersByTime(1000); });
    expect(metin(u, "Bağlantı koptu")).toBeNull();
    expect(u.queryByRole("alert")).toBeNull();
    act(() => { goster("Kayıt alındı", "info"); });
    expect(metin(u, "Kayıt alındı")).toBeTruthy();
  });

  it("sağlayıcısız kullanım açık hata verir", () => {
    jest.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderHook(() => useToast())).toThrow("useToast must be used within ToastProvider");
  });
});

describe("Button", () => {
  async function bas(azalt: boolean) {
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(azalt);
    const yay = jest.spyOn(Animated, "spring");
    const u = render(<Button label="Başlat" onPress={jest.fn()} />);
    await act(async () => { await Promise.resolve(); });
    const d = u.getByRole("button");
    act(() => { fireEvent(d, "pressIn"); });
    act(() => { fireEvent(d, "pressOut"); });
    return yay;
  }
  it("hareketi azalt açıkken basma animasyonu KOŞMAZ", async () => {
    expect(await bas(true)).not.toHaveBeenCalled();
  });
  it("kapalıyken yay animasyonu basma ölçeğine ve geri 1'e gider", async () => {
    const yay = await bas(false);
    expect(yay.mock.calls.map((c) => (c[1] as { toValue: number }).toValue)).toEqual([motion.pressScale, 1]);
  });
});
