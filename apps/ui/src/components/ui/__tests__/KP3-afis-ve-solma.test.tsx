/**
 * KP-3 C · UpdateBanner + FadeInView kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - UpdateBanner: yeni APK varsa bant görünür ve dokununca APK adresi açılır (açma düşse de çökmez); donanım ÇALIŞIRKEN bant
 *    çizilmez (seans ortasında güncelleme teklif edilmez); adres yoksa dokunuş hiçbir şey açmaz.
 *  - FadeInView: "hareketi azalt" açıkken içerik tam opak olur (solma beklenmez); kapalıyken solma animasyonu başlar.
 * SAHTE: güncelleme denetimi (ağ sınırı), donanım-çalışıyor kancası, Linking (platform), AccessibilityInfo ayarı.
 */
const mockGuncelleme = jest.fn();
let mockCalisiyor = false;
jest.mock("@/services/updates", () => ({ checkMobileUpdate: (...a: unknown[]) => mockGuncelleme(...a) }));
jest.mock("@/hooks/useDonanimCalisiyor", () => ({ useDonanimCalisiyor: () => mockCalisiyor }));

import React from "react";
import { AccessibilityInfo, Animated, Linking, Text } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { UpdateBanner } from "@/components/ui/UpdateBanner";
import { FadeInView } from "@/components/ui/FadeInView";

afterEach(() => { jest.restoreAllMocks(); mockCalisiyor = false; });

describe("UpdateBanner", () => {
  it("yeni APK varsa dokununca adres açılır (açma düşse de çökmez)", async () => {
    mockGuncelleme.mockResolvedValue({ available: true, apkUrl: "https://indir.example/pemf-2.3.36.apk", version: "2.3.36" });
    const ac = jest.spyOn(Linking, "openURL").mockRejectedValue(new Error("tarayıcı yok"));
    const u = render(<UpdateBanner />);
    await act(async () => {});
    await act(async () => { fireEvent.press(u.getByRole("button")); });
    expect(ac).toHaveBeenCalledWith("https://indir.example/pemf-2.3.36.apk");
  });

  it("donanım çalışırken bant çizilmez; adres yoksa dokunuş hiçbir şey açmaz", async () => {
    mockGuncelleme.mockResolvedValue({ available: true, apkUrl: "https://indir.example/x.apk" });
    mockCalisiyor = true;
    let u = render(<UpdateBanner />);
    await act(async () => {});
    expect(u.queryByRole("button")).toBeNull();
    u.unmount();
    mockCalisiyor = false;
    mockGuncelleme.mockResolvedValue({ available: true });
    const ac = jest.spyOn(Linking, "openURL");
    ac.mockClear(); // ⚠️ spyOn önceki testin casusunu döndürebilir — çağrılar birikmesin
    u = render(<UpdateBanner />);
    await act(async () => {});
    await act(async () => { fireEvent.press(u.getByRole("button")); });
    expect(ac).not.toHaveBeenCalled();
  });
});

describe("FadeInView", () => {
  it("hareketi azalt açıkken içerik tam opak olur; kapalıyken solma animasyonu başlar", async () => {
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);
    const zaman = jest.spyOn(Animated, "timing");
    zaman.mockClear();
    const u = render(<FadeInView><Text>içerik</Text></FadeInView>);
    await act(async () => { await Promise.resolve(); });
    // ⚠️ toJSON animasyon değerinin SON hâlini göstermez (değer render dışından güncellenir) → Animated nesnesinden okunur.
    const opaklik = (x: ReturnType<typeof render>) => {
      const st = ([] as unknown[]).concat(x.UNSAFE_getByType(Animated.View).props.style).flat() as Array<{ opacity?: unknown }>;
      const o = st.find((y) => y && y.opacity !== undefined)?.opacity as { __getValue?: () => number } | number | undefined;
      return typeof o === "number" ? o : o?.__getValue?.();
    };
    expect(opaklik(u)).toBe(1);
    const azaltmaAcikkenCagri = zaman.mock.calls.length;
    u.unmount();
    (AccessibilityInfo.isReduceMotionEnabled as jest.Mock).mockResolvedValue(false);
    render(<FadeInView><Text>ikinci</Text></FadeInView>);
    await act(async () => { await Promise.resolve(); });
    expect(zaman.mock.calls.length).toBeGreaterThan(azaltmaAcikkenCagri);
  });
});
