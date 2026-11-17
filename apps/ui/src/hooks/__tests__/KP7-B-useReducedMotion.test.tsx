/**
 * KP-7 B (madde 7 · işlev ölçüsü): `useReducedMotion` — sistem "hareketi azalt" tercihi.
 *  - Tercih OKUNAMAZSA (ret) hareket açık varsayılır (false), kanca çökmez, işlenmemiş ret yok.
 *  - Tercih CANLI dinlenir: sistem ayarı değişince değer güncellenir (açık → kapalı da).
 *  - Söküldüğünde abonelik kaldırılır.
 * SAHTE (platform sınırı): AccessibilityInfo.isReduceMotionEnabled / addEventListener.
 */
import { act, renderHook } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";
import { useReducedMotion } from "@/hooks/useReducedMotion";

afterEach(() => jest.restoreAllMocks());

test("tercih okunamazsa hareket açık kalır; canlı değişim dinlenir; sökülünce abonelik kalkar", async () => {
  let dinleyici: ((v: boolean) => void) | undefined;
  const kaldir = jest.fn();
  jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockRejectedValue(new Error("tercih okunamadı"));
  jest.spyOn(AccessibilityInfo, "addEventListener").mockImplementation(((_ad: string, f: (v: boolean) => void) => {
    dinleyici = f;
    return { remove: kaldir };
  }) as never);
  const h = renderHook(() => useReducedMotion());
  await act(async () => {
    await Promise.resolve();
  });
  expect(h.result.current).toBe(false);
  act(() => dinleyici?.(true));
  expect(h.result.current).toBe(true);
  act(() => dinleyici?.(false));
  expect(h.result.current).toBe(false);
  h.unmount();
  expect(kaldir).toHaveBeenCalledTimes(1);
});
