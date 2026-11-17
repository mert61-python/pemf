/**
 * KP-8 · src/components/ui/ErrorBoundary.tsx kalan dallar (düzen ErrorBoundary.AP18 / KP3-ErrorBoundary-genel-ag ile AYNI: sahte pencere +
 * ErrorUtils, modül `isolateModules` ile yeniden yüklenir; ağ sınırı `apiPost` sahte):
 *  - Pencere hata olayı iletisiz / hatasız gelirse rapor "window.onerror", yığın boş; rota hash yoksa YOL (pathname), o da yoksa boş.
 *  - İşlenmeyen ret nedeni YOKSA rapor "unhandledrejection: " (çökmez).
 *  - Pencere YOKKEN (yerel) genel işleyici raporu boş rotayla gönderir; hata nesnesi YOKSA ileti boş; önceki işleyici yoksa zincir
 *    çağrılmaz (çökmez).
 *  - ErrorUtils YOKSA genel işleyici kurulmaz (yükleme çökmez).
 *  - Sınır, Error OLMAYAN bir değer fırlatılırsa: rapora değerin kendisi, ekranda "bilinmeyen hata" metni; YIĞIN gelmezse rapor boş yığın.
 */
const mockPost = jest.fn((..._a: unknown[]) => Promise.resolve(null));
jest.mock("@/services/apiClient", () => ({ apiPost: (...a: unknown[]) => mockPost(...a) }));

import React from "react";
import { render } from "@testing-library/react-native";
import i18n from "i18next";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";

type Dinleyici = (e: unknown) => void;
const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);

let geriAl: (() => void) | undefined;
function kurVeYukle(pencere: "var" | "yok", konum: Record<string, unknown> | undefined, eu: "var" | "yok", onceki?: unknown) {
  const dinleyiciler: Record<string, Dinleyici> = {};
  const g = global as unknown as { window?: unknown; ErrorUtils?: unknown };
  const ilkWindowVar = "window" in g;
  const ilkWindow = g.window;
  const ilkEU = g.ErrorUtils;
  let yeni: ((e: unknown, f?: boolean) => void) | undefined;
  if (pencere === "var") g.window = { addEventListener: (t: string, f: Dinleyici) => { dinleyiciler[t] = f; }, location: konum };
  else delete g.window;
  const kur = jest.fn((f: (e: unknown, x?: boolean) => void) => { yeni = f; });
  if (eu === "var") g.ErrorUtils = { getGlobalHandler: () => onceki, setGlobalHandler: kur };
  else delete g.ErrorUtils;
  geriAl = () => {
    if (ilkWindowVar) g.window = ilkWindow; else delete g.window;
    g.ErrorUtils = ilkEU;
  };
  jest.isolateModules(() => { require("@/components/ui/ErrorBoundary"); });
  return { dinleyiciler, yeni, kur };
}
const govde = (i = 0) => mockPost.mock.calls[i][1] as { message: string; stack: string; route: string };

beforeEach(() => mockPost.mockClear());
afterEach(() => { geriAl?.(); geriAl = undefined; });

it("pencere hata olayı iletisiz / hatasız → 'window.onerror', boş yığın; hash yoksa rota YOL, o da yoksa boş", () => {
  const { dinleyiciler } = kurVeYukle("var", { pathname: "/hasta" }, "yok");
  dinleyiciler.error({});
  expect(govde()).toEqual({ message: "window.onerror", stack: "", route: "[global] /hasta" });
  geriAl?.();
  mockPost.mockClear();
  const ikinci = kurVeYukle("var", {}, "yok");
  ikinci.dinleyiciler.error({ message: "KP8" });
  expect(govde().route).toBe("[global] ");
});

it("işlenmeyen ret nedensiz → 'unhandledrejection: ' (çökmez)", () => {
  const { dinleyiciler } = kurVeYukle("var", { hash: "#/x" }, "yok");
  dinleyiciler.unhandledrejection({});
  expect(govde().message).toBe("unhandledrejection: ");
  expect(govde().route).toBe("[global] #/x");
});

it("pencere YOK (yerel): genel işleyici boş rotayla raporlar; hata nesnesi yoksa ileti boş; önceki işleyici yoksa zincir yok", () => {
  const { yeni, kur } = kurVeYukle("yok", undefined, "var", undefined);
  expect(kur).toHaveBeenCalledTimes(1);
  expect(() => yeni!(undefined, false)).not.toThrow();
  expect(govde()).toEqual({ message: "[non-fatal] ", stack: "", route: "[global] " });
});

it("ErrorUtils YOKSA genel işleyici kurulmaz, yükleme çökmez", () => {
  const { dinleyiciler } = kurVeYukle("yok", undefined, "yok");
  expect(Object.keys(dinleyiciler)).toEqual([]);
  expect(mockPost).not.toHaveBeenCalled();
});

it("sınır (pencere YOKKEN): Error OLMAYAN değer fırlatılırsa rapora değerin kendisi + boş rota, ekranda 'bilinmeyen hata'", () => {
  const g = global as unknown as { window?: unknown };
  const varMi = "window" in g;
  const ilk = g.window;
  const Patlayan = (): React.ReactElement => { throw "KP8 düz metin hata"; };
  const sus = jest.spyOn(console, "error").mockImplementation(() => {});
  delete g.window;
  try {
    const u = render(<ErrorBoundary><Patlayan /></ErrorBoundary>);
    expect(u.getByText(T("ortak.hata.bilinmeyen"))).toBeTruthy();
    const son = govde(mockPost.mock.calls.length - 1);
    expect(son.message).toBe("KP8 düz metin hata");
    expect(son.route).toBe("");
    u.unmount();
  } finally {
    if (varMi) g.window = ilk;
    sus.mockRestore();
  }
});

it("sınır: `null` fırlatılırsa rapor iletisi boş, ekranda 'bilinmeyen hata' (çökmez)", () => {
  // eslint-disable-next-line no-throw-literal
  const Patlayan = (): React.ReactElement => { throw null; };
  const sus = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    const u = render(<ErrorBoundary><Patlayan /></ErrorBoundary>);
    expect(u.getByText(T("ortak.hata.bilinmeyen"))).toBeTruthy();
    expect(govde(mockPost.mock.calls.length - 1).message).toBe("");
    u.unmount();
  } finally {
    sus.mockRestore();
  }
});
