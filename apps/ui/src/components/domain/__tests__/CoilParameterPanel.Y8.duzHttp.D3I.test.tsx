// Author: mertaygn, cglrgrkn
/**
 * D3I çapraz (C2) · Ö.4-Y8 — bobin panelinin "⏹ Durdur"u düz-HTTP kapısına BAĞLI DEĞİL; "Başlat" kapıda KALIR.
 * ==========================================================================================================
 * ÖLÇÜLEN KUSUR (doğrulayıcı D, okuma + A1.3 kapısının karşıt ölçümü): panelin Başlat ve Durdur'u TEK `apiPost` çağrısını
 * paylaşıyordu (`start` değişkeni); D3I-A1.3 (`ab21fdb8`) `durdurma` bayrağını ACİL DURDUR yedeklerine, seans Durdur'una ve
 * Kontrol ekranının bobin STOP'larına vermişti ama bu paneli kaçırmıştı → genel (özel ağ DIŞI) `http://` tabanında bobin
 * Durdur'u HİÇ istek göndermiyordu (önceden var).
 *
 * GERÇEK: `CoilParameterPanel` + `apiClient` (kapı dahil). Sahte YALNIZ `fetch` ve sınır kıskacı (ilgisiz). Taban genel http.
 * ⚠️ MUTASYON: Durdur dalından `durdurma: true` silinirse KIRMIZI; bayrak Başlat dalına da verilirse KARŞIT KIRMIZI.
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://203.0.113.5:8000/api", bridgeBaseUrl: "http://203.0.113.5:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: Record<string, number>) => ({ values: p, warnings: [] }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const istekler: { url: string; start?: boolean }[] = [];
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

beforeEach(() => {
  istekler.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  (global as any).fetch = jest.fn((url: string, init?: any) => {
    const govde = init?.body ? JSON.parse(init.body) : {};
    istekler.push({ url, start: govde.start });
    return yanit({ status: "success", transport: "stm32" });
  });
});
afterEach(() => jest.restoreAllMocks());

const bobin = {
  coilId: 1, connected: true, running: true, objectTemp: 0, frequencyHz: 50, dutyCycle: 25, magneticMt: 0, currentA: 0,
  stm32Driven: true, stmConnected: true,
};

it("KRİTİK: genel http tabanında 'Bobini durdur' STOP (start:false) GÖNDERİR — Ö.4-Y8 durdurma kapıya bağlanmaz", async () => {
  const u = render(<CoilParameterPanel {...bobin} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini durdur"));
  });
  expect(istekler).toEqual([{ url: "http://203.0.113.5:8000/api/coil/1/control", start: false }]);
});

it("KARŞIT: genel http tabanında 'Bobini başlat' kapıda KALIR (istek YOK) — bayrak başlatmaya sızmaz", async () => {
  const u = render(<CoilParameterPanel {...bobin} running={false} />);
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini başlat"));
  });
  expect(istekler).toEqual([]);
});
