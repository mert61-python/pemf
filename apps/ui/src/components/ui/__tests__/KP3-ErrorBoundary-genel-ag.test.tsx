/**
 * KP-3 C · ErrorBoundary — React-DIŞI (genel) hata ağı + "Tekrar dene" (her test bir DAVRANIŞ iddiası):
 *  - Pencere `error` / `unhandledrejection` olayları ve RN `ErrorUtils` genel işleyicisi /client/error'a SESSİZ raporlanır; ileti ve
 *    yığındaki e-posta ve uzun sayılar (TC / telefon) MASKELENİR (KVKK #93); rota "[global] …" ile işaretlenir.
 *  - Önceki RN işleyicisi (kırmızı ekran / çökme raporu) KORUNUR — hata ona da iletilir; ölümcül / ölümcül değil ayrımı rapora yazılır.
 *  - Raporlama düşse (apiPost atar) akış bozulmaz.
 *  - Hata kartındaki "Tekrar dene" sınırı sıfırlar: çocuk yeniden çizilir.
 * SAHTE: apiClient.apiPost (ağ sınırı) · pencere / ErrorUtils (platform sınırı; modül YÜKLENİRKEN kurulduğu için izole yüklenir).
 */
const mockPost = jest.fn((..._a: unknown[]) => Promise.resolve(null));
jest.mock("@/services/apiClient", () => ({ apiPost: (...a: unknown[]) => mockPost(...a) }));

import React, { useState } from "react";
import { Text } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";

const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
type Dinleyici = (e: unknown) => void;

// Rota RAPOR ANINDA okunur (yükleme anında değil) → sahte pencere test bitene dek yerinde kalır, sonra geri alınır.
let geriAl: (() => void) | undefined;
function kurVeYukle() {
  const dinleyiciler: Record<string, Dinleyici> = {};
  const g = global as unknown as { window?: unknown; ErrorUtils?: unknown };
  const ilkWindow = g.window;
  const ilkEU = g.ErrorUtils;
  const onceki = jest.fn();
  let yeni: ((e: unknown, f?: boolean) => void) | undefined;
  g.window = { addEventListener: (t: string, f: Dinleyici) => { dinleyiciler[t] = f; }, location: { hash: "#/kontrol" } };
  g.ErrorUtils = { getGlobalHandler: () => onceki, setGlobalHandler: (f: (e: unknown, x?: boolean) => void) => { yeni = f; } };
  geriAl = () => { g.window = ilkWindow; g.ErrorUtils = ilkEU; };
  jest.isolateModules(() => { require("@/components/ui/ErrorBoundary"); });
  return { dinleyiciler, onceki, yeni: yeni! };
}

beforeEach(() => mockPost.mockClear());
afterEach(() => { geriAl?.(); geriAl = undefined; });

it("pencere olayları ve ErrorUtils maskelenerek sessiz raporlanır; önceki RN işleyicisi korunur", () => {
  const a = kurVeYukle();
  a.dinleyiciler.error({ message: "kayıt hatası ali@klinik.com", error: { stack: "at x (05321234567)" } });
  expect(mockPost).toHaveBeenLastCalledWith(
    "/client/error",
    { message: "kayıt hatası [email]", stack: "at x ([num])", route: "[global] #/kontrol" },
    null,
    { silent: true },
  );
  a.dinleyiciler.unhandledrejection({ reason: new Error("ağ 12345678901 düştü") });
  expect((mockPost.mock.calls.at(-1)![1] as { message: string }).message).toBe("unhandledrejection: ağ [num] düştü");
  a.dinleyiciler.unhandledrejection({ reason: "dize-ret" });
  expect((mockPost.mock.calls.at(-1)![1] as { message: string }).message).toBe("unhandledrejection: dize-ret");
  const hata = new Error("çöktü");
  a.yeni(hata, true);
  expect((mockPost.mock.calls.at(-1)![1] as { message: string }).message).toBe("[FATAL] çöktü");
  expect(a.onceki).toHaveBeenCalledWith(hata, true);
  a.yeni("düz", false);
  expect((mockPost.mock.calls.at(-1)![1] as { message: string }).message).toBe("[non-fatal] düz");
});

it("raporlama atsa da akış bozulmaz", () => {
  const a = kurVeYukle();
  mockPost.mockImplementationOnce(() => { throw new Error("apiClient yok"); });
  expect(() => a.dinleyiciler.error({ message: "x" })).not.toThrow();
});

// KP-7 B (işlev ölçüsü): rapor isteği REDDEDİLİRSE (backend kapalı / ağ yok) ret yutulur — genel işleyici de sınırın kartı da
// etkilenmez, işlenmemiş ret OLUŞMAZ (aksi halde `unhandledrejection` dinleyicisi kendi raporunu yeniden tetiklerdi).
it("rapor isteği reddedilse de genel işleyici ve hata kartı etkilenmez (ret yutulur)", async () => {
  const a = kurVeYukle();
  const ret = jest.fn();
  const dinle = (e: unknown) => ret(e);
  process.on("unhandledRejection", dinle);
  try {
    mockPost.mockImplementation(() => Promise.reject(new Error("backend kapalı")));
    expect(() => a.dinleyiciler.error({ message: "pencere hatası" })).not.toThrow();
    const { ErrorBoundary } = require("@/components/ui/ErrorBoundary");
    jest.spyOn(console, "error").mockImplementation(() => undefined);
    function Patla(): React.ReactElement {
      throw new Error("ekran çöktü");
    }
    const u = render(<ErrorBoundary><Patla /></ErrorBoundary>);
    expect(u.getByText("ekran çöktü")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    expect(mockPost).toHaveBeenCalledTimes(2);
    expect(ret).not.toHaveBeenCalled();
  } finally {
    process.off("unhandledRejection", dinle);
    mockPost.mockReset().mockImplementation(() => Promise.resolve(null));
    (console.error as jest.Mock).mockRestore?.();
  }
});

it("'Tekrar dene' sınırı sıfırlar ve çocuk yeniden çizilir", async () => {
  const { ErrorBoundary } = require("@/components/ui/ErrorBoundary");
  jest.spyOn(console, "error").mockImplementation(() => undefined);
  let at = true;
  function Cocuk() {
    const [n] = useState(0);
    if (at) throw new Error("ekran çöktü 05321234567");
    return <Text>içerik {n}</Text>;
  }
  const u = render(<ErrorBoundary><Cocuk /></ErrorBoundary>);
  expect(u.getByText("ekran çöktü [num]")).toBeTruthy(); // görünen metin de maskeli
  at = false;
  await act(async () => { fireEvent.press(u.getByText(T("ortak.tekrarDene"))); });
  expect(u.getByText("içerik 0")).toBeTruthy();
  (console.error as jest.Mock).mockRestore?.();
});
