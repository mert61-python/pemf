// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) — `useAlanHaritasi`: açıkken abone (bir kez), kapanınca / sökülünce çıkar; kapalıyken eski harita GÖSTERİLMEZ;
 * aboneliksiz sağlayıcıda (eski / sahte bağlam) çökmez.
 */
const mockCtx: { alanHaritasi?: unknown; alanAbone?: jest.Mock } = {};
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCtx }));

import { renderHook } from "@testing-library/react-native";
import { useAlanHaritasi } from "@/hooks/useAlanHaritasi";

describe("GA useAlanHaritasi", () => {
  beforeEach(() => {
    mockCtx.alanHaritasi = { surum: 1, durum: "sifir" };
    mockCtx.alanAbone = jest.fn();
  });

  it("açık → bir kez abone; kapanınca çıkar; kapalıyken null", () => {
    const { result, rerender, unmount } = renderHook(({ acik }: { acik: boolean }) => useAlanHaritasi(acik), {
      initialProps: { acik: false },
    });
    expect(result.current).toBeNull();
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    rerender({ acik: true });
    expect(result.current).toEqual({ surum: 1, durum: "sifir" });
    expect(mockCtx.alanAbone!.mock.calls).toEqual([[true]]);
    rerender({ acik: true });
    expect(mockCtx.alanAbone!.mock.calls).toEqual([[true]]);
    rerender({ acik: false });
    expect(mockCtx.alanAbone!.mock.calls).toEqual([[true], [false]]);
    expect(result.current).toBeNull();
    rerender({ acik: true });
    unmount();
    expect(mockCtx.alanAbone!.mock.calls).toEqual([[true], [false], [true], [false]]);
  });

  it("harita henüz yok → null; aboneliksiz bağlam çökmez", () => {
    mockCtx.alanHaritasi = undefined;
    const { result } = renderHook(() => useAlanHaritasi(true));
    expect(result.current).toBeNull();
    mockCtx.alanAbone = undefined;
    const r2 = renderHook(() => useAlanHaritasi(true));
    expect(r2.result.current).toBeNull();
    r2.unmount();
  });
});
