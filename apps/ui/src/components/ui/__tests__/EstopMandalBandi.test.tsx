// Author: mertaygn, cglrgrkn
/**
 * D1.81 · sahip kararı Y4 — ACİL DURDURMA MANDALI bandı.
 *
 * Y4: "E-stop MANDALLANIR; operatörün ayrı ve bilinçli 'sıfırla' eylemi olmadan hiçbir START kabul edilmez.
 * Sıfırlama kendi başına yeniden başlatmaz." Bant: mandal kuruluyken NEDEN + "Sıfırla"; "Sıfırla" ONAY ister ve
 * YALNIZ mandal ucunu çağırır (başlatma/seans/bobin ucu ÇAĞRILMAZ). Mandal yokken ya da alan yokken (eski backend)
 * bant ÇİZİLMEZ. Uç başarısızsa operatör SESSİZ bırakılmaz.
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
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { EstopMandalBandi, SIFIRLA_YOLU, mandalNedeni } from "@/components/ui/EstopMandalBandi";

const MANDALLI = { coils: [], activeTreatment: { isActive: false }, estopMandali: { aktif: true, neden: "manual" } };

beforeEach(() => {
  mockPost.mockReset().mockResolvedValue({ status: "success" });
  mockConfirm.mockReset().mockResolvedValue(true);
  mockAlert.mockReset();
  mockToast.mockReset();
});

describe("EstopMandalBandi — Y4 mandal ve 'Sıfırla'", () => {
  it("mandal YOKKEN bant çizilmez (alan yok — eski backend — ya da aktif:false)", () => {
    mockSnapshot = { coils: [], activeTreatment: { isActive: false } };
    expect(render(<EstopMandalBandi />).toJSON()).toBeNull();
    mockSnapshot = { ...MANDALLI, estopMandali: { aktif: false } };
    expect(render(<EstopMandalBandi />).toJSON()).toBeNull();
  });

  it("KRITIK: mandal kuruluyken NEDEN ve 'Sıfırla' görünür", () => {
    mockSnapshot = MANDALLI;
    const u = render(<EstopMandalBandi />);
    expect(u.getByText(/ACİL DURDURMA MANDALLI/)).toBeTruthy();
    expect(u.getByText(/ACİL DURDUR düğmesi/)).toBeTruthy();
    expect(u.getByLabelText("Acil durdurma mandalını sıfırla")).toBeTruthy();
  });

  it("KRITIK: 'Sıfırla' ONAY ister; onayla YALNIZ mandal ucu çağrılır — başlatma ucu YOK", async () => {
    mockSnapshot = MANDALLI;
    const u = render(<EstopMandalBandi />);
    fireEvent.press(u.getByLabelText("Acil durdurma mandalını sıfırla"));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(String(mockConfirm.mock.calls[0][1])).toMatch(/BAŞLATMAZ/);
    expect(mockPost.mock.calls.map((c) => c[0])).toEqual([SIFIRLA_YOLU]);
    expect(SIFIRLA_YOLU).toBe("/hardware/estop_mandali/sifirla");
    await waitFor(() => expect(mockToast).toHaveBeenCalled());
  });

  it("onay VERİLMEZSE uç çağrılmaz (bilinçli eylem)", async () => {
    mockSnapshot = MANDALLI;
    mockConfirm.mockResolvedValue(false);
    const u = render(<EstopMandalBandi />);
    fireEvent.press(u.getByLabelText("Acil durdurma mandalını sıfırla"));
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled());
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("uç başarısızsa operatör UYARILIR (sessiz kalmaz)", async () => {
    mockSnapshot = MANDALLI;
    mockPost.mockResolvedValue(null);
    const u = render(<EstopMandalBandi />);
    fireEvent.press(u.getByLabelText("Acil durdurma mandalını sıfırla"));
    await waitFor(() => expect(mockAlert).toHaveBeenCalled());
    expect(mockToast).not.toHaveBeenCalled();
  });

  it("neden metinleri iç adları değil operatör dilini gösterir", () => {
    expect(mandalNedeni("stm_disconnected")).toBe("STM32 bağlantı kaybı");
    expect(mandalNedeni("esp_alarm_8_overtemp")).toBe("ESP güvenlik alarmı");
    expect(mandalNedeni("stm_watchdog_timeout")).toMatch(/watchdog/);
    expect(mandalNedeni("bilinmeyen_ic_ad")).toBe("acil durdurma");
  });

  // 1-C inceleme i3-F-2: bant "Bobinler durduruldu" GÜVENCESİ vermez — mandal iletisi teyit taşımaz; E-stop teyitsiz
  // bitebilir (kablo çıkık / ölü gönderici → stmStopped=false; ESP kapalı kurulumda confirmed hep false). Ekranda
  // kalan tek durum mesajı yanlış güvence olmamalı: bant EYLEM söyler (cihazda kontrol edin).
  it.each(["manual", "stm_disconnected", "stm_komut_reddi"])(
    "KRITIK: neden=%s — bant teyitsiz 'Bobinler durduruldu' YAZMAZ, kontrol EYLEMİNİ söyler",
    (neden) => {
      mockSnapshot = { ...MANDALLI, estopMandali: { aktif: true, neden } };
      const u = render(<EstopMandalBandi />);
      expect(u.queryByText(/durduruldu/i)).toBeNull();
      expect(u.getByText(/kontrol edin/)).toBeTruthy();
      expect(u.getByLabelText("Acil durdurma mandalını sıfırla")).toBeTruthy();
    }
  );
});
