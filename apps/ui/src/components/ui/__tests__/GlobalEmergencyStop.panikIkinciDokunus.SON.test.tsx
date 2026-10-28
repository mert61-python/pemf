// Author: mertaygn, cglrgrkn
/**
 * SON-A1.6 (22-SON A1a §5 · İG-6.28 farklı yöntemle) — kayan ACİL DURDUR'da PANİK İKİNCİ DOKUNUŞ YUTULMAZ.
 * =====================================================================================================
 * `GlobalEmergencyStop.tsx` "Çift-tık koruması YOK (bilinçli): panik anındaki ikinci dokunuş yutulmamalı. `busy` yalnız görsel geri
 * bildirim içindir, dokunuşu engellemez." der. ÖLÇÜLEN KÖRLÜK (uç 8b002fc0): `onPress={busy ? undefined : onPress}` mutantı (ilk
 * durdurma uçuştayken ikinci basış YUTULUR) GES / AppShell / ACİL DURDUR'u anan 36 jest dosyasında 1114 / 1114 YEŞİL. D5.E2 aynı
 * değişmezi Kontrol / Ana Ekran düğmeleri için ölçüyor ("panik çift dokunuş"), kayan düğme için kapı YOK.
 *
 * GERÇEK: `GlobalEmergencyStop` + `performEmergencyStop` + `apiClient` + `config`. Sahte EN ALT katta: `global.fetch` — ilk basışın
 * istekleri HİÇ ÇÖZÜLMEZ (köprü / yedek takıldı: tam da operatörün yeniden bastığı an); canlı durum (bobin 1 çalışıyor) sahte bağlam.
 * Ö.4-Y8: yalnız kapı — ACİL DURDUR davranışı değişmez.
 */
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("react-native-safe-area-context", () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
const mockCanli = {
  snapshot: {
    stm: "online",
    coils: [1, 2, 3].map((id) => ({ id, connected: true, running: id === 1 })),
    activeTreatment: { isActive: true, mode: "Manuel" },
  },
  donanimBelirsiz: false,
};
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCanli }));
jest.mock("@/services/apiClient", () => ({
  ...jest.requireActual("@/services/apiClient"),
  platformConfirm: jest.fn(async () => true),
  platformAlert: jest.fn(),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { serviceConfig, updateServiceConfig } from "@/services/config";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

let estopIstekleri = 0;

beforeEach(() => {
  estopIstekleri = 0;
  (global as { fetch: unknown }).fetch = jest.fn((url: string) => {
    const yol = String(url).replace(/^https?:\/\/[^/]+/, "");
    if (/\/hardware\/emergency_stop/.test(yol)) estopIstekleri += 1;
    return new Promise(() => undefined); // HİÇ çözülmez: ilk durdurma uçuşta kalır
  });
  expect(updateServiceConfig("http://192.168.1.5:8000")).toBe(true);
  serviceConfig.apiToken = "cihaz-anahtari";
  jest.spyOn(console, "error").mockImplementation(() => {});
  jest.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => {
  jest.restoreAllMocks();
});

it("KRİTİK: ilk ACİL DURDUR uçuştayken (yanıt yok) İKİNCİ basış YUTULMAZ — yeni durdurma istekleri gider", async () => {
  const u = render(<GlobalEmergencyStop />);
  const dugme = () => u.getByLabelText(/acil durdur/i);
  await act(async () => {
    fireEvent.press(dugme());
  });
  const ilk = estopIstekleri;
  expect(ilk).toBeGreaterThan(0); // aparat: ilk basış durdurma isteği gönderdi
  await act(async () => {
    fireEvent.press(dugme());
  });
  expect({ ilk, sonra: estopIstekleri, ikinciBasisGitti: estopIstekleri > ilk }).toEqual({
    ilk,
    sonra: estopIstekleri,
    ikinciBasisGitti: true,
  });
  u.unmount();
});
