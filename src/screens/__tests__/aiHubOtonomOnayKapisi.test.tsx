// Author: mertaygn, cglrgrkn
/**
 * AI HUB "OTONOM BİOFEEDBACK" YAPISAL OLARAK HİÇ ÇALIŞMIYORDU (bulgu 21, cid. 5).
 *
 * 2026-08-06'da eklenen SERT ONAY KAPISI `/ai/pro/start`'ı onaylanmış bir `proposal_id` ile ZORUNLU
 * kıldı. Bu ekran gövdeyi `{}` ile gönderiyordu → istek HER ZAMAN 428 dönüyor, otonom seans HİÇ
 * başlamıyor. Üstüne üç ayrı kusur:
 *   (a) toggle AÇIK kalıyor → hekim otonom modun çalıştığını sanıyor,
 *   (b) ekranın kendi toast'ı YANLIŞ sebebi söylüyor ("kamera/model erişilemedi"),
 *   (c) aynı bloktaki watchdog `setInterval` HİÇ kurulmuyor (`startedByUsRef` yalnız `.then()`
 *       içinde atanıyor; ref ataması re-render tetiklemez, dep dizisi değişmez) → ölü koruma.
 *
 * ⚠️ ASIL GEREKÇE SÜRÜM KAYMASI: onay kapısından ÖNCEKİ bir backend EXE'sine bağlanan yeni bir
 * mobil sürümde bu start BAŞARILI olur ve ONAYSIZ otonom tedavi başlatır — kapı istemciden
 * atlatılır. Bu yüzden çağrı "düzeltilmedi", KALDIRILDI; kullanıcı onay akışının bulunduğu yere
 * (Kontrol → AI Pro) yönlendiriliyor.
 *
 * ⚠️ Testler DAVRANIŞSAL: kaynakta desen aranmıyor.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
// ⚠️ STABİL fn: `showToast` artık effect deps'inde. Her çağrıda yeni fn dönen bir mock,
// effect'i sonsuz yeniden kurup testi kilitler (ToastProvider gerçekte `useCallback(..., [])`).
jest.mock("@/components/ui/ToastProvider", () => {
  const fn = jest.fn();
  return { useToast: () => ({ showToast: fn }), __toast: fn };
});
// ⚠️ `hasAiHub` ŞART: ekran onu okur ve YOKSA ev-sahibi ekranına düşer (modül ızgarası hiç
// render edilmez). İlk denemede eksikti ve test "etiket bulunamadı" diye düşüyordu.
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
// Hasta seçili olmalı: `patientName` modül gövdelerine geçer.
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Test Hasta" } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
// Hasta kapısı: testte hasta seçimi akışı konumuz değil → çocukları doğrudan render et.
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
// Modül gövdeleri ağır (kamera/ses/dosya seçici). Konu AKORDEON DAVRANIŞI olduğu için
// gövdeler sadeleştirilir; başlıkların `expanded` durumu gerçek bileşenden gelir.
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

import { apiGet, apiPost } from "@/services/apiClient";
import { AiHubScreen } from "@/screens/AiHubScreen";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { __toast: showToast } = require("@/components/ui/ToastProvider");

const aiProCagrilari = () =>
  (apiPost as jest.Mock).mock.calls.filter((c) => String(c[0]).startsWith("/ai/pro/"));

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
  (apiGet as jest.Mock).mockClear();
  showToast.mockClear();
});

/** Otonom toggle'ı aç + canlı kamerayı başlat (gerçek akış). */
async function otonomDene() {
  const u = render(<AiHubScreen />);
  fireEvent.press(u.getAllByLabelText(/FGS/i)[0]); // akordeonu aç
  const toggle = u.getByLabelText("Otonom biofeedback");
  fireEvent.press(toggle);
  // ARA DOĞRULAMA: doğru düğmeye basıldığının kanıtı (yanlış-yeşil kalkanı).
  expect(toggle.props.accessibilityState?.checked).toBe(true);
  await act(async () => {
    fireEvent.press(u.getByText("Canlı Kamera"));
  });
  await act(async () => {}); // microtask kuyruğunu boşalt
  return u;
}

it("KRİTİK: AI Hub HİÇBİR /ai/pro/* çağrısı yapmaz (onay kapısı istemciden atlatılamaz)", async () => {
  await otonomDene();
  expect(aiProCagrilari()).toHaveLength(0);
});

it("KRİTİK: toggle AÇIK KALMAZ ve mesaj DOĞRU sebebi söyler", async () => {
  const u = await otonomDene();

  expect(u.getByLabelText("Otonom biofeedback").props.accessibilityState?.checked).toBe(false);

  const metinler = showToast.mock.calls.map((c: unknown[]) => String(c[0]));
  expect(metinler.some((m: string) => /kamera\/model/i.test(m))).toBe(false);
  expect(metinler.some((m: string) => /onay/i.test(m))).toBe(true);
});

it("REGRESYON KİLİDİ: hiçbir yol /ai/pro/stop göndermez (ölü koruma kaldırıldı)", async () => {
  await otonomDene();
  expect((apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop")).toHaveLength(0);
});
