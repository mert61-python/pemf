// Author: mertaygn, cglrgrkn
/**
 * A-47 / Y2 · 1-D inceleme i2-F-2 + i2-F-6 — bobin paneli: 48 °C bandı ve ZAMANLA geri gelen otomatik STOP.
 * Ölçülen körlük: A-47 kapısı yalnız 47,9 / 48,0 (uyarı yok) ve 50,2 / 63 °C (uyarı var) dener ve `act()` sonrası hemen
 * bakar: karşılaştırma +2 °C kaydırılsa (gerçek 49 °C'de uyarı yanmaz) ya da "48 °C'yi 3 sn aşarsa durdur" (debounce'lu
 * kesme) geri eklense ilgili bütün suite'ler yeşil kalıyordu.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => ({ status: "success" })) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => ({ values: p, warnings: [] }),
}));

import { act, render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const { apiPost } = jest.requireMock("@/services/apiClient");

const temel = {
  coilId: 6, connected: true, running: true, objectTemp: 50.2, frequencyHz: 100, dutyCycle: 40,
  magneticMt: 1.8, currentA: 0, stm32Driven: true, stmConnected: true, measuredFields: ["objectTemp"] as string[],
};

it("KRİTİK (i2-F-6): gerçek 48,1 / 48,5 / 49 °C ölçümünde görsel uyarı VAR", async () => {
  for (const t of [48.1, 48.5, 49.0]) {
    const u = render(<CoilParameterPanel {...temel} objectTemp={t} />);
    await act(async () => {});
    expect(u.queryByTestId("sicaklik-uyarisi")).not.toBeNull();
    u.unmount();
  }
});

it("KRİTİK (i2-F-2): 60 sn boyunca 48 °C üstünde kalsa da panel kendiliğinden istek ATMAZ (gecikmeli otomatik STOP yok)", async () => {
  jest.useFakeTimers();
  try {
    (apiPost as jest.Mock).mockClear();
    const u = render(<CoilParameterPanel {...temel} />);
    for (let s = 0; s < 60; s++) {
      await act(async () => {
        jest.advanceTimersByTime(1000);
      });
    }
    expect(apiPost).not.toHaveBeenCalled();
    u.unmount();
  } finally {
    jest.useRealTimers();
  }
});
