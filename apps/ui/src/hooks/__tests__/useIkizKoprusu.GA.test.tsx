// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A4 — `useIkizKoprusu`: çerçeve yüklenince 2 Hz `pemf.ikiz.durum`; `hazir` gelmeden alan aboneliği YOK (DEMA'da sunucu
 * hesabı başlamaz); `hazir` gelince abone + her yeni haritada `pemf.ikiz.alan`; çerçeve GİDİNCE (gonder → null: yeniden yükleme / dil)
 * `hazir` sıfırlanır (abonelik biter) — ama çerçeve yüklenmeden (gonder null iken) gelen `hazir` KORUNUR (ikiz onu load'dan önce
 * gönderir); gönderim hatası yutulur.
 */
const mockCtx: { snapshot: unknown; alanHaritasi: unknown; alanAbone: jest.Mock } = { snapshot: {}, alanHaritasi: null, alanAbone: jest.fn() };
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCtx }));

import { act, renderHook } from "@testing-library/react-native";
import { useIkizKoprusu } from "@/hooks/useIkizKoprusu";

const turler = (g: jest.Mock) => g.mock.calls.map((c) => JSON.parse(c[0]).tur);

describe("GA useIkizKoprusu", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockCtx.snapshot = { stm: "online", coils: [] };
    mockCtx.alanHaritasi = null;
    mockCtx.alanAbone = jest.fn();
  });
  afterEach(() => jest.useRealTimers());

  it("gonder yokken hiçbir şey; varken hemen + 500 ms'de bir durum", () => {
    const g = jest.fn();
    const { rerender } = renderHook(({ gonder }: { gonder: ((m: string) => void) | null }) => useIkizKoprusu(gonder), {
      initialProps: { gonder: null as ((m: string) => void) | null },
    });
    act(() => jest.advanceTimersByTime(2000));
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    rerender({ gonder: g });
    expect(turler(g)).toEqual(["pemf.ikiz.durum"]);
    act(() => jest.advanceTimersByTime(1000));
    expect(turler(g)).toEqual(["pemf.ikiz.durum", "pemf.ikiz.durum", "pemf.ikiz.durum"]);
    expect(JSON.parse(g.mock.calls[0][0]).cihazBagli).toBe(true);
    mockCtx.snapshot = { stm: "offline" };
    rerender({ gonder: g }); // bağlam değişimi yeniden çizer
    act(() => jest.advanceTimersByTime(500));
    expect(JSON.parse(g.mock.calls[3][0]).cihazBagli).toBe(false); // canlı anlık görüntü
    rerender({ gonder: null });
    const n = g.mock.calls.length;
    act(() => jest.advanceTimersByTime(2000));
    expect(g.mock.calls.length).toBe(n); // çerçeve gidince durur
  });

  it("hazir → abone + alan iletisi; başka ileti yok sayılır; çerçeve değişince hazir sıfırlanır", () => {
    const g = jest.fn();
    const { result, rerender } = renderHook(({ gonder }: { gonder: (m: string) => void }) => useIkizKoprusu(gonder), {
      initialProps: { gonder: g },
    });
    act(() => result.current.gelen('{"tur":"pemf.ikiz.komut"}'));
    act(() => result.current.gelen("1840"));
    expect(result.current.hazir).toBe(false);
    expect(mockCtx.alanAbone).not.toHaveBeenCalled();
    act(() => result.current.gelen('{"tur":"pemf.ikiz.hazir","surum":1}'));
    expect(result.current.hazir).toBe(true);
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true]]);
    expect(turler(g)).not.toContain("pemf.ikiz.alan"); // harita henüz yok
    mockCtx.alanHaritasi = { surum: 1, durum: "sifir", zaman: 1, modelTahmini: true };
    rerender({ gonder: g });
    expect(turler(g)).toContain("pemf.ikiz.alan");
    const alan = JSON.parse(g.mock.calls.find((c) => JSON.parse(c[0]).tur === "pemf.ikiz.alan")[0]);
    expect(alan).toMatchObject({ tur: "pemf.ikiz.alan", durum: "sifir", modelTahmini: true });
    rerender({ gonder: null as unknown as (m: string) => void }); // yeniden yükleme: eski çerçeve gider (ekranda gonder önce null olur)
    expect(result.current.hazir).toBe(false);
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true], [false]]);
    const g2 = jest.fn();
    rerender({ gonder: g2 }); // yeni çerçeve yüklendi — yeniden hazir beklenir
    expect(result.current.hazir).toBe(false);
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true], [false]]);
  });

  it("hazir çerçeve yüklenmeden (gonder null iken) gelirse korunur; gonder dolunca abone olunur", () => {
    const g = jest.fn();
    const { result, rerender } = renderHook(({ gonder }: { gonder: ((m: string) => void) | null }) => useIkizKoprusu(gonder), {
      initialProps: { gonder: null as ((m: string) => void) | null },
    });
    act(() => result.current.gelen('{"tur":"pemf.ikiz.hazir","surum":1}'));
    expect(result.current.hazir).toBe(true);
    expect(mockCtx.alanAbone).not.toHaveBeenCalled(); // çerçeve yokken abonelik yok
    rerender({ gonder: g });
    expect(result.current.hazir).toBe(true);
    expect(mockCtx.alanAbone.mock.calls).toEqual([[true]]);
  });

  it("gönderim hatası yutulur", () => {
    const g = jest.fn(() => {
      throw new Error("çerçeve gitti");
    });
    renderHook(() => useIkizKoprusu(g));
    act(() => jest.advanceTimersByTime(600));
    expect(g).toHaveBeenCalledTimes(2);
  });
});
