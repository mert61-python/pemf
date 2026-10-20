// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — bobin parametre paneli: durdurma / başlatma ONAYLANAMAZSA gösterilen uyarılar iki dilde görünür, GİDEN komut AYNI.
 *   · Durdur (onaylanamadı): TR "DURDURMA ONAYLANAMADI — bobin HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın." · EN "STOP NOT CONFIRMED — the
 *     coil MAY STILL BE RUNNING. Press EMERGENCY STOP." — ve apiPost yükü (freq 0, duty 0, start false) dilden bağımsız;
 *   · Başlat (onaylanamadı): "Komut onaylanamadı — …" / "Command not confirmed — …"; yük dilden bağımsız.
 * GERÇEK: CoilParameterPanel + i18n; sahte: apiPost (null döner = ağ hatası / onaysız).
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => null) }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { apiPost } from "@/services/apiClient";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const temel = {
  coilId: 2,
  connected: true,
  running: true,
  objectTemp: 30,
  frequencyHz: 50,
  dutyCycle: 25,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
  defaultDuration: 20,
};

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function dilYap(dil: "tr" | "en") {
  if (dil === "en") __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec(dil, depo);
  });
}

const kontrolCagrilari = () => (apiPost as jest.Mock).mock.calls.filter((c) => String(c[0]).includes("/control")).map((c) => c[1]);

it("Durdur onaylanamadı: TR uyarı bayt bayt aynı, EN uyarı doğru; gönderilen STOP yükü AYNI", async () => {
  const yukler: unknown[] = [];
  for (const [dil, etiket, uyari] of [
    ["tr", "Bobini durdur", "DURDURMA ONAYLANAMADI — bobin HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın."],
    ["en", "Stop coil", "STOP NOT CONFIRMED — the coil MAY STILL BE RUNNING. Press EMERGENCY STOP."],
  ] as const) {
    (apiPost as jest.Mock).mockClear();
    await dilYap(dil);
    const u = render(<CoilParameterPanel {...temel} />);
    await act(async () => {
      fireEvent.press(u.getByLabelText(etiket));
    });
    expect(u.getByText(uyari)).toBeTruthy();
    yukler.push(kontrolCagrilari());
    u.unmount();
  }
  expect(yukler[1]).toEqual(yukler[0]);
  expect((yukler[0] as { start: boolean }[])[0].start).toBe(false);
});

it("Başlat onaylanamadı: TR / EN uyarı; başlatma yükü AYNI", async () => {
  const yukler: unknown[] = [];
  for (const [dil, etiket, uyari] of [
    ["tr", "Bobini başlat", "Komut onaylanamadı — bobin başlatılamamış olabilir, tekrar deneyin."],
    ["en", "Start coil", "Command not confirmed — the coil may not have started; try again."],
  ] as const) {
    (apiPost as jest.Mock).mockClear();
    await dilYap(dil);
    const u = render(<CoilParameterPanel {...temel} running={false} />);
    await act(async () => {
      fireEvent.press(u.getByLabelText(etiket));
    });
    expect(u.getByText(uyari)).toBeTruthy();
    yukler.push(kontrolCagrilari());
    u.unmount();
  }
  expect(yukler[1]).toEqual(yukler[0]);
});

it("durum etiketleri iki dilde (erişim adı + görünen): Aktif / Active", async () => {
  await dilYap("en");
  const u = render(<CoilParameterPanel {...temel} />);
  expect(u.getByLabelText("Status: Active, coil is running")).toBeTruthy();
  expect(u.getByText("Active")).toBeTruthy();
  u.unmount();
  await dilYap("tr");
  const v = render(<CoilParameterPanel {...temel} />);
  expect(v.getByLabelText("Durum: Aktif, bobin çalışıyor")).toBeTruthy();
});
