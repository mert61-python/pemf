// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — ACİL DURDURMA MANDALI bandı iki dilde: metin görünür, EYLEM AYNI (13 §2-d).
 *   · TR: göç öncesiyle aynı bant / neden / "Sıfırla" düğmesi; EN: "EMERGENCY STOP LATCHED …" + "Reset" düğmesi;
 *   · sıfırlama ucu (`/hardware/estop_mandali/sifirla`), onay akışı ve `{ onay: true }` gövdesi dilden bağımsız — yalnız o uç çağrılır;
 *   · SUNUCU METNİNE göre dallanma YOK: `eylemSifirlaSoyler` makine-okur alanı varsa eylem metni ne olursa olsun ("Press Reset …" İngilizce de)
 *     bant "Sıfırla"yı ikinci kez yazmaz; alan YOKSA (eski sunucu) eski `/Sıfırla/` eşleşmesi aynen çalışır.
 */
let mockSnapshot: Record<string, unknown> = { coils: [], activeTreatment: { isActive: false } };
const mockPost = jest.fn();
const mockConfirm = jest.fn();
const mockAlert = jest.fn();
const mockToast = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => mockPost(...a),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  platformAlert: (...a: unknown[]) => mockAlert(...a),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: (...a: unknown[]) => mockToast(...a) }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnapshot }) }));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { EstopMandalBandi, SIFIRLA_YOLU, mandalEylemi, mandalNedeni } from "@/components/ui/EstopMandalBandi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const mandal = (m: Record<string, unknown>) => ({ coils: [], activeTreatment: { isActive: false }, estopMandali: { aktif: true, neden: "manual", ...m } });

beforeEach(() => {
  mockPost.mockReset().mockResolvedValue({ status: "success" });
  mockConfirm.mockReset().mockResolvedValue(true);
  mockAlert.mockReset();
  mockToast.mockReset();
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

it("Türkçe: bant, neden ve 'Sıfırla' göç öncesiyle aynı", () => {
  mockSnapshot = mandal({});
  const u = render(<EstopMandalBandi />);
  expect(u.getByText("ACİL DURDURMA MANDALLI — yeni başlatma kapalı")).toBeTruthy();
  expect(
    u.getByText('Neden: ACİL DURDUR düğmesi. Bobinlerin durduğunu cihazda kontrol edin. Yeniden başlatmak için önce "Sıfırla"; sıfırlama bobinleri başlatmaz.'),
  ).toBeTruthy();
  expect(u.getByLabelText("Acil durdurma mandalını sıfırla")).toBeTruthy();
  expect(u.getByText("Sıfırla")).toBeTruthy();
});

it("İngilizce: bant / neden / düğme İngilizce; sıfırlama AYNI uç + AYNI gövde, onay metni İngilizce", async () => {
  await enYap();
  mockSnapshot = mandal({});
  const u = render(<EstopMandalBandi />);
  expect(u.getByText("EMERGENCY STOP LATCHED — new starts are disabled")).toBeTruthy();
  expect(
    u.getByText('Reason: EMERGENCY STOP button. Check on the device that the coils have stopped. To start again, press "Reset" first; resetting does not start the coils.'),
  ).toBeTruthy();
  expect(u.getByText("Reset")).toBeTruthy();
  fireEvent.press(u.getByLabelText("Reset the emergency stop latch"));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(String(mockConfirm.mock.calls[0][0])).toBe("Reset the emergency stop latch?");
  expect(String(mockConfirm.mock.calls[0][1])).toMatch(/does NOT start the coils/);
  expect(mockPost.mock.calls.map((c) => c[0])).toEqual([SIFIRLA_YOLU]);
  expect(mockPost.mock.calls[0][1]).toEqual({ onay: true });
  expect(mockToast).toHaveBeenCalledWith("Latch reset — starting is possible again (the coils were not started)", "success");
});

it("makine-okur alan (eylemSifirlaSoyler) önce: İngilizce sunucu eylem metni 'Sıfırla' İÇERMESE de bant ikinci 'Sıfırla' yazmaz", async () => {
  await enYap();
  mockSnapshot = mandal({ neden: "stm_komut_reddi", eylem: "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir. Then press Reset.", eylemSifirlaSoyler: true });
  const u = render(<EstopMandalBandi />);
  expect(u.getByText(/Resetting does not start the coils\.$/)).toBeTruthy();
  expect(u.queryByText(/To start again, press "Reset" first/)).toBeNull();
});

it("alan YOKSA (eski sunucu): eski metin eşleşmesi aynen — 'Sıfırla' geçen eylem ikinci cümleyi bastırır, geçmeyen basar", () => {
  mockSnapshot = mandal({ neden: "stm_komut_reddi", eylem: "…sonra 'Sıfırla'ya basın." });
  const u = render(<EstopMandalBandi />);
  expect(u.queryByText(/Yeniden başlatmak için önce "Sıfırla"/)).toBeNull();
  u.unmount();
  mockSnapshot = mandal({ neden: "stm_komut_reddi", eylem: "Kartı kontrol edin." });
  const v = render(<EstopMandalBandi />);
  expect(v.getByText(/Yeniden başlatmak için önce "Sıfırla"/)).toBeTruthy();
});

it("neden kodları iki dilde (kod → metin eşlemesi; bilinmeyen kod ham gösterilmez)", async () => {
  expect(mandalNedeni("stm_disconnected")).toBe("STM32 bağlantı kaybı");
  expect(mandalNedeni("onceki_oturum:dosya_okunamadi")).toBe("önceki oturumda ACİL DURDUR — sıfırlanmadı (mandal dosyası okunamadı)");
  expect(mandalEylemi("stm_watchdog_timeout")).toBe("USB kablosunu kontrol edin.");
  await enYap();
  expect(mandalNedeni("stm_disconnected")).toBe("STM32 connection lost");
  expect(mandalNedeni("esp_alarm_xyz")).toBe("ESP safety alarm");
  expect(mandalNedeni("bilinmeyen_kod")).toBe("emergency stop");
  expect(mandalNedeni("onceki_oturum:dosya_okunamadi")).toBe("EMERGENCY STOP in a previous session — not reset (latch file could not be read)");
  expect(mandalEylemi("stm_watchdog_timeout")).toBe("Check the USB cable.");
});
