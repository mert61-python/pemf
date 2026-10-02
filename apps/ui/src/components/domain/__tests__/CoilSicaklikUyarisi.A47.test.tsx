// Author: mertaygn, cglrgrkn
/**
 * A-47 + Y2 + Y6 (SAHİP KARARI, 2026-09-29) — 48 °C'de OTOMATİK DURDURMA YOK, YALNIZ GÖRSEL UYARI.
 *
 * Sahibin sözleri: "kapalı karar + bobin 6 7 için zaten stm e bağlı olacağı için hepsi 48 c leri de
 * kaldır. istersek sonradan ekleriz." Uygulama: hiçbir katmanda (firmware, backend, istemci) otomatik
 * termal engelleme ya da kesme yok (bobin 1–7). 48 °C'yi geçince YALNIZ görsel uyarı; seans
 * engellenmez, durdurulmaz. Ölçüm yoksa '—' (Y6); bayat değer canlı gösterilmez (D1.67: backend
 * `measuredFields`ten düşürür).
 *
 * ESKİ DAVRANIŞ (kaldırılan): `objectTemp > SAFE_TEMP_CUTOFF (48)` iken panel kendiliğinden
 * `/coil/{id}/control {start:false}` gönderiyordu. Bu dosya ürünün o isteği ARTIK hiç atmadığını
 * DAVRANIŞLA ölçer: gerçek bileşen çizilir, `apiPost` kaydedilir.
 *
 * ⚠️ Operatörün kendi "⏹ Durdur"u ve ACİL DURDUR DEĞİŞMEZ (Ö.4-Y8) — karşıt kol.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => ({ status: "success" })) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => ({ values: p, warnings: [] }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const { apiPost } = jest.requireMock("@/services/apiClient");
const mockApiPost = apiPost as jest.Mock;

const temel = {
  coilId: 7,
  connected: true,
  running: true,
  objectTemp: 50.2,
  frequencyHz: 50,
  dutyCycle: 25,
  magneticMt: 1,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
  measuredFields: ["objectTemp"] as string[],
};

beforeEach(() => {
  mockApiPost.mockReset();
  mockApiPost.mockResolvedValue({ status: "success" });
});

async function ciz(ek: Partial<typeof temel> = {}) {
  const u = render(<CoilParameterPanel {...temel} {...ek} />);
  await act(async () => {}); // (eski) async otomatik durdurma tamamlansın — artık olmamalı
  return u;
}

// Bobin 1–7 STM (A-47 kapsamı); slot 8 ESP — 8266'nın KENDİ 100 °C kesmesi firmware'de (Y40), istemci yine durdurmaz.
const BOBINLER = [
  { coilId: 2, stm32Driven: true },
  { coilId: 6, stm32Driven: true },
  { coilId: 7, stm32Driven: true },
  { coilId: 8, stm32Driven: false },
];

describe.each(BOBINLER)("bobin $coilId", (b) => {
  it("KRİTİK (A-47): ölçülen 50,2 °C'de panel OTOMATİK STOP GÖNDERMEZ", async () => {
    const u = await ciz(b);
    expect(mockApiPost).not.toHaveBeenCalled();
    // Sıcaklık daha da artsa da (yeni episode) istek yok.
    u.rerender(<CoilParameterPanel {...temel} {...b} objectTemp={63.0} />);
    await act(async () => {});
    expect(mockApiPost).not.toHaveBeenCalled();
    expect(u.queryByText(/otomatik durduruldu/i)).toBeNull();
  });

  it("KRİTİK (A-47): 48 °C üstünde GÖRSEL UYARI çıkar ve durdurulmadığını söyler", async () => {
    const u = await ciz(b);
    expect(u.getByText(/48 °C üstünde/)).toBeTruthy();
    expect(u.getByText(/otomatik durdurma yok/i)).toBeTruthy();
  });
});

it("KRİTİK (A-47): bobin çalışmıyorken de 48 °C üstü uyarı görünür, istek gitmez", async () => {
  const u = await ciz({ running: false });
  expect(u.getByText(/48 °C üstünde/)).toBeTruthy();
  expect(mockApiPost).not.toHaveBeenCalled();
});

it("KRİTİK (Y6): ölçüm YOKSA (bayat değer gelse bile) sayı ve uyarı gösterilmez, '—'", async () => {
  // Backend susan sensörün alanını measuredFields'ten düşürür (D1.67); live_state'te donmuş 50,2 kalır.
  const u = await ciz({ measuredFields: [] });
  expect(u.queryByText(/50\.2/)).toBeNull();
  expect(u.queryByText(/48 °C üstünde/)).toBeNull();
  expect(u.getAllByText("-").length).toBeGreaterThanOrEqual(1);
  expect(mockApiPost).not.toHaveBeenCalled();
});

it("KARŞIT: 48,0 °C ve altında 48 uyarısı YOK (eşik 'geçince')", async () => {
  for (const t of [47.9, 48.0]) {
    const u = await ciz({ objectTemp: t });
    expect(u.queryByText(/48 °C üstünde/)).toBeNull();
    u.unmount();
  }
});

it("KARŞIT (Ö.4-Y8): operatörün ⏹ Durdur'u sıcaklıktan bağımsız STOP gönderir", async () => {
  const u = await ciz();
  mockApiPost.mockClear(); // yalnız operatörün basışı sayılsın (otomatik istek ayrı kolda ölçülür)
  await act(async () => {
    fireEvent.press(u.getByLabelText("Bobini durdur"));
  });
  expect(mockApiPost).toHaveBeenCalledTimes(1);
  const [yol, govde] = mockApiPost.mock.calls[0];
  expect(yol).toBe("/coil/7/control");
  expect(govde.start).toBe(false);
});
