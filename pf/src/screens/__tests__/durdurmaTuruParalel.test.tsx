// Author: mertaygn, cglrgrkn
/**
 * MANUEL "⏹ DURDUR" TURU SERİ VE KAPISIZDI (bulgu 25, cid. 5).
 *
 * `handleStopManual` 1 + 1 + N ardışık, her biri 8 sn zaman aşımlı POST atıyordu (ESP döngüsü SERİ
 * `await`, `Promise.all` YOK). Ağ kopukken 8 bobinli bir seansta tur 5 × 8 sn = **~40 sn** sürüyordu.
 * Buton `disabled={loading}` ve `loading` YALNIZ `stopSession` süresince true olduğu için ~8 sn'de
 * yeniden basılabiliyordu → her basış 5 zaman aşımı daha ekliyor, istemci ~48 sn meşgul kalıyordu.
 *
 * ⚠️ BUTONUN ERKEN AÇILMASI bir DURDURMA kontrolü için İSTENEN yön (sahip kararı) — bu yama butonu
 * KİLİTLEMİYOR. T3 bunu kilitler: "kolay ama YASAK" çözüm (`disabled`a guard eklemek) testi KIRAR.
 * ⚠️ `/session/stop` BİLEREK SERİ kaldı: donanıma dokunmadan önce dakika-ortalamalarını yazıyor;
 * bobin koşuları eşzamanlı kapatılırsa o kısmi dakika sensör-özetinden düşer.
 *
 * ⚠️ TESTLER TAMAMEN DAVRANIŞSAL: gerçek zamana/timer'a DEĞİL, `apiPost` çağrılarının ZAMANLAMASINA
 * bakıyor. Kaynakta desen aranmadığı için "// Promise.all ile paralel" yazan bir yorum bu kapıdan
 * GEÇEMEZ.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockCagrilar: any[] = [];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockSalStop: any = null;
const mockStopSession = jest.fn(
  () =>
    new Promise((r) => {
      mockSalStop = r;
    }),
);

jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  // ⚠️ HİÇBİRİ KENDİLİĞİNDEN ÇÖZÜLMEZ: paralellik ölçümü "hangi istekler AYNI ANDA uçuşta"
  // sorusudur. Anında çözülen bir mock seri kodu da paralel gösterirdi.
  apiPost: jest.fn(
    (yol) =>
      new Promise((res) => {
        mockCagrilar.push({ yol, res });
      }),
  ),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://x/api" } }));
// ObservationNotesModal `useSafeAreaInsets` kullaniyor; provider olmadan throw eder.
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: true,
    treatment: { mode: "Manuel", frequencyHz: 10, intensityMt: 1, durationSec: 600 },
    elapsedSec: 0,
    remainingSec: 600,
    loading: false,
    stopping: false,
    error: null,
    lastError: () => null,
    startSession: jest.fn(),
    stopSession: mockStopSession,
    emergencyStop: jest.fn(),
  }),
}));

const mockSnap = {
  gateway: "online",
  mqtt: "online",
  stm: "online",
  patient: { name: "Rex", species: "Kedi", breed: "", owner: "S" },
  activeTreatment: {
    isActive: true, mode: "Manuel", frequencyHz: 10, intensityMt: 1,
    remainingMin: 10, elapsedSec: 0, durationSec: 600,
  },
  notifications: [],
  // 1-5 STM + 6-8 ESP; hepsi ÇALIŞIYOR → durdurma kümesi 8 bobin.
  coils: Array.from({ length: 8 }, (_, i) => ({
    id: i + 1, running: true, freq: 10, duty: 0.2, temperature: 30, objectTemp: 30, magneticMt: 1,
  })),
  system: {},
  sessions: [],
};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operator: "Dr. X" }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ navigate: jest.fn(), goTo: jest.fn() }) }));
// ⚠️ `SessionProgressCard` MOCK'LANMAK ZORUNDA: onun içinde de "⏹ Durdur" metni var →
// `getByText` ÇOKLU EŞLEŞME hatası verirdi.
jest.mock("@/components/domain/SessionProgressCard", () => ({ SessionProgressCard: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/PatientGate", () => ({
  PatientGate: ({ children }: { children: React.ReactNode }) => children,
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { ControlScreen } from "@/screens/ControlScreen";

const mockYollar = () => mockCagrilar.map((c) => c.yol).sort();

beforeEach(() => {
  mockCagrilar.length = 0;
  mockSalStop = null;
  mockStopSession.mockClear();
});

async function ekran() {
  const u = render(<ControlScreen />);
  await act(async () => {});
  return u;
}

it("KRİTİK: bobin STOP istekleri PARALEL gider (seri 4×8 sn DEĞİL)", async () => {
  const u = await ekran();

  fireEvent.press(u.getByText("⏹ Durdur"));
  await act(async () => {});

  // İlk adım `/session/stop`: bilerek SERİ, hâlâ uçuşta → bobin istekleri henüz başlamadı.
  expect(mockStopSession).toHaveBeenCalledTimes(1);
  expect(mockCagrilar).toHaveLength(0);

  await act(async () => {
    mockSalStop!({ status: "success" });
  });

  // HİÇBİRİNİ ÇÖZMEDEN dördü de uçuşta olmalı → paralel.
  expect(mockYollar()).toEqual([
    "/coil/6/control",
    "/coil/7/control",
    "/coil/8/control",
    "/coil/batch",
  ]);
});

it("KRİTİK: uçuştaki tur varken ikinci basış YENİ tur BAŞLATMAZ", async () => {
  const u = await ekran();
  const btn = u.getByText("⏹ Durdur");

  fireEvent.press(btn);
  fireEvent.press(btn); // `stopSession` promise'i UÇUŞTAYKEN
  await act(async () => {});

  expect(mockStopSession).toHaveBeenCalledTimes(1);

  await act(async () => {
    mockSalStop!({ status: "success" });
  });
  expect(mockCagrilar).toHaveLength(4); // tek tur, 4 istek — iki tur olsaydı 8 olurdu
});

it("SAHİP KARARI: buton uçuştaki turda DEVRE DIŞI BIRAKILMAZ (ama geri bildirim verir)", async () => {
  // ⚠️ "Kolay ama YASAK" çözüm kapısı: guard'ı silip `disabled={loading || stopRound}` yapan bir
  // mutasyon bu testi KIRAR. Bir durdurma kontrolü kilitlenmez; kullanıcı sessizce yutulan dokunuş
  // yerine etiketten anlar.
  const u = await ekran();

  fireEvent.press(u.getByText("⏹ Durdur"));
  await act(async () => {});

  // Tur UÇUŞTA: etiket değişmiş olmalı (geri bildirim) ...
  const etiket = u.getByText("⏳ Durduruluyor…");
  expect(etiket).toBeTruthy();
  // ... ama düğme DEVRE DIŞI OLMAMALI. `accessibilityState.disabled` yalnız `disabled != null`
  // iken host View'a yazılır; `disabled={loading}` = false verildiği için falsy olmak zorunda.
  // Etiketten YUKARI yürüyüp dokunulabilir atayı bul (JSON.stringify çevrimsel yapıda patlar).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let dugum: any = etiket;
  while (dugum && dugum.props?.accessibilityState === undefined) dugum = dugum.parent;
  expect(dugum).toBeTruthy(); // dokunulabilir ata bulunamazsa test anlamsız olurdu
  expect(dugum.props.accessibilityState?.disabled).toBeFalsy();
});

it("SAHİP KARARI: guard KALICI kilit değil — tur bitince yeniden basılabilir", async () => {
  const u = await ekran();

  fireEvent.press(u.getByText("⏹ Durdur"));
  await act(async () => {
    mockSalStop!({ status: "success" });
  });
  // Tüm bobin isteklerini çöz → tur biter, `finally` guard'ı serbest bırakır.
  await act(async () => {
    for (const c of mockCagrilar) c.res({ status: "success" });
  });

  fireEvent.press(u.getByText("⏹ Durdur"));
  await act(async () => {});

  expect(mockStopSession).toHaveBeenCalledTimes(2);
});


// ── DENETİM 2. TUR [1.1] (2026-08-20): "hata değil" ≠ "teyit" ────────────────────────────────
// Backend, publish broker'a ulaşamayınca HTTP 200 + {status:"mqtt_unavailable"} döner (tek bobin)
// ve /coil/batch ÜST-SEVİYEDE HEP "success" deyip satır-başı sonuçları results[] içinde taşır.
// Eski yüklem (`r.status !== "error"`) ikisini de teyit sayıyordu → broker ölüyken STOP hiçbir
// bobine ulaşmamışken "Durdurma onaylanamadı" uyarısı HİÇ çıkmıyordu (bobinler hayvanın üzerinde
// enerjili kalırken operatör durdurduğunu sanır — bulgunun ciddiyeti 1).

const alertMock = () =>
  jest.requireMock("@/services/apiClient").platformAlert as jest.Mock;

async function turuKostur(u: Awaited<ReturnType<typeof ekran>>, cozumle: (yol: string) => unknown) {
  fireEvent.press(u.getByText("⏹ Durdur"));
  await act(async () => {
    mockSalStop!({ status: "success" });
  });
  await act(async () => {
    for (const c of mockCagrilar) c.res(cozumle(c.yol));
  });
}

it("KRİTİK: tek-bobin STOP yanıtı mqtt_unavailable → 'Durdurma onaylanamadı' uyarısı ÇIKAR", async () => {
  alertMock().mockClear();
  const u = await ekran();

  await turuKostur(u, (yol) =>
    yol === "/coil/6/control"
      ? { status: "mqtt_unavailable", transport: "mqtt" } // backend'in GERÇEK broker-ölü yanıtı
      : yol === "/coil/batch"
        ? { status: "success", results: [{ coilId: 1, status: "success" }] }
        : { status: "success" },
  );

  expect(alertMock()).toHaveBeenCalled();
  const [baslik] = alertMock().mock.calls[0];
  expect(String(baslik)).toContain("Durdurma onaylanamadı");
});

it("KRİTİK: batch SATIRINDAKİ stm_unavailable teyit SAYILMAZ (üst-seviye 'success' aldatıcı)", async () => {
  alertMock().mockClear();
  const u = await ekran();

  await turuKostur(u, (yol) =>
    yol === "/coil/batch"
      ? {
          status: "success", // backend batch'i KOŞULSUZ böyle döner — teyit satırlardadır
          results: [
            { coilId: 1, status: "success" },
            { coilId: 2, status: "stm_unavailable" },
          ],
        }
      : { status: "success" },
  );

  expect(alertMock()).toHaveBeenCalled();
});

it("KARŞIT-KANIT: tüm satırlar 'success' → uyarı YOK (yanlış alarm üretme)", async () => {
  alertMock().mockClear();
  const u = await ekran();

  await turuKostur(u, (yol) =>
    yol === "/coil/batch"
      ? {
          status: "success",
          results: Array.from({ length: 5 }, (_, i) => ({ coilId: i + 1, status: "success" })),
        }
      : { status: "success" },
  );

  expect(alertMock()).not.toHaveBeenCalled();
});

it("guard AYNI RENDER BATCH'indeki iki basışta da tutar (ref, state DEĞİL)", async () => {
  // ⚠️ Bu test `useState` tabanlı bir guard'ı REDDEDER: iki basış aynı React batch'inde işlenirse
  // state hâlâ `false` görünür ve ikinci tur başlar. `fireEvent.press` normalde kendi `act`ini
  // çalıştırıp state'i flush ettiği için ayrımı görmek üzere iki basış TEK `act` içine alınır.
  const u = await ekran();
  const btn = u.getByText("⏹ Durdur");

  await act(async () => {
    fireEvent.press(btn);
    fireEvent.press(btn);
  });

  expect(mockStopSession).toHaveBeenCalledTimes(1);
});
