// Author: mertaygn, cglrgrkn
/**
 * AI PRO PANELİNİ YALNIZCA GÖRÜNTÜLEYEN İSTEMCİ, BAŞKASININ SEANSINI DURDURUYORDU (bulgu 21, cid. 5).
 *
 * Panel `st.active`'i SAHİPLİK SORMADAN benimsiyor (`setRunning(Boolean(st.active))`) ve unmount
 * cleanup'ında `/ai/pro/stop` gönderiyordu. İki istemcili klinikte (klinik PC'sindeki web arayüzü +
 * telefon, ya da iki veteriner) biri otonom seansı başlatmışsa, ikinci istemcinin Kontrol → "AI Pro"
 * sekmesini yalnızca AÇIP "Manuel"e dönmesi yeterliydi: backend `_stop_session_coils(range(1,9))`
 * koşulsuz çalışıyor → **7 bobin ve seans iptal**, iki operatöre de gerekçe gösterilmeden.
 *
 * ⚠️ AYNI CİHAZDA sekme değişiminde durdurmak KASITLI ve KORUNUYOR (kod yorumu: "panel kapanınca
 * backend bobinleri BAŞSIZ sürmeye devam ediyordu"). Bastırma YALNIZ seansı bu istemci
 * başlatmadıysa geçerli — 2. test bunu kilitler.
 * ⚠️ Operatörün AÇIK "Durdur" dokunuşu (`stop()`) DEĞİŞMEDİ: her istemcinin operatörü tedaviyi
 * durdurabilmeli.
 * ⚠️ SÜRÜM KAYMASI: `ownerClientId` alanı YOKSA (sahiplik öncesi backend) ESKİ davranış korunur —
 * 3. test bunu kilitler; aksi hâlde yeni istemci + eski backend'de bobin BAŞSIZ kalırdı.
 *
 * ⚠️ Testler DAVRANIŞSAL: kaynakta desen aranmıyor.
 */
let mockDurum: Record<string, unknown> = { active: false };

jest.mock("@/services/apiClient", () => ({
  // ⚠️ ASYNC ŞART: cleanup `.catch()` çağırıyor, senkron dönen bir mock patlar.
  apiGet: jest.fn(async () => mockDurum),
  apiPost: jest.fn(async (yol: string) => {
    if (yol === "/ai/pro/propose") {
      return {
        proposalId: "p1",
        specs: {
          organ_id: 0, duration_minutes: 20, coil_ids: [1, 2, 3, 4, 5, 6, 7],
          D: [1, 1, 1, 1, 1, 1, 1], P: [0, 0, 0, 0, 0, 0, 0], e_field: 0.07,
        },
        meta: {},
        expiresAt: 0,
      };
    }
    return { status: "success" };
  }),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "benim-id"),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: null, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("expo-camera", () => ({
  CameraView: () => null,
  useCameraPermissions: () => [{ granted: true }, jest.fn()],
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const stopCagrilari = () =>
  (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop");

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
  mockDurum = { active: false };
});

/** Paneli mount et, `sync` çözülsün. */
async function panel() {
  const u = render(<AiProPanel patientName="Tekir" />);
  await act(async () => {});
  return u;
}

it("KRİTİK: BAŞKASININ seansını sadece görüntüleyip çıkmak DURDURMA göndermez", async () => {
  mockDurum = { active: true, ownerClientId: "baska-istemci" };
  const u = await panel();

  // ⚠️ ÖN-DOĞRULAMA (yanlış-yeşil kalkanı): panel gerçekten `running=true`'yu BENİMSEMİŞ olmalı.
  // Aksi hâlde stop'un gitmemesi "sahiplik" değil "sync henüz çözülmedi" anlamına gelirdi.
  expect(u.queryByLabelText("AI Pro otonom seansı durdur")).toBeTruthy();

  await act(async () => {
    u.unmount();
  });

  expect(stopCagrilari()).toHaveLength(0);
});

it("KASITLI DAVRANIŞ: KENDİ seansımızı görüntüleyip çıkmak DURDURUR (başsız bobin bırakmayız)", async () => {
  mockDurum = { active: true, ownerClientId: "benim-id" };
  const u = await panel();
  expect(u.queryByLabelText("AI Pro otonom seansı durdur")).toBeTruthy();

  await act(async () => {
    u.unmount();
  });

  expect(stopCagrilari()).toHaveLength(1);
});

it("SÜRÜM KAYMASI KİLİDİ: `ownerClientId` ALANI YOKSA eski davranış korunur", async () => {
  // Sahiplik öncesi backend. "Bilinmiyorsa durdurma" gibi bir yama, yeni istemci + eski backend
  // ikilisinde bobini BAŞSIZ bırakırdı.
  mockDurum = { active: true };
  const u = await panel();
  expect(u.queryByLabelText("AI Pro otonom seansı durdur")).toBeTruthy();

  await act(async () => {
    u.unmount();
  });

  expect(stopCagrilari()).toHaveLength(1);
});

it("seans YOKKEN unmount hiçbir şey göndermez (mevcut davranış)", async () => {
  mockDurum = { active: false };
  const u = await panel();

  await act(async () => {
    u.unmount();
  });

  expect(stopCagrilari()).toHaveLength(0);
});


it("KRİTİK: BİZ başlatınca ilk poll'dan ÖNCE çıkmak bile DURDURUR (başsız bobin bırakmayız)", async () => {
  // ⚠️ Bu test `ownedRef.current = true` atamasını (start başarısı) kilitler. 3 sn'lik durum poll'u
  // sahipliği zaten doğru kurar; ama seansı başlatıp HEMEN sekme değiştiren operatörde o poll henüz
  // koşmamıştır. Atama olmazsa bobinler BAŞSIZ kalır — tam da kasıtlı davranışın engellediği şey.
  // `apiGet` bilerek `{active:false}` döndürüyor: sahiplik SYNC'ten değil START'tan gelmek zorunda.
  mockDurum = { active: false };
  const u = await panel();

  await act(async () => {
    fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat"));
  });
  await act(async () => {
    fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat"));
  });

  // ÖN-DOĞRULAMA: start GERÇEKTEN çağrıldı ve kimliğimiz gövdede gitti.
  const start = (apiPost as jest.Mock).mock.calls.find((c) => c[0] === "/ai/pro/start");
  expect(start).toBeTruthy();
  expect(start![1]).toMatchObject({ client_id: "benim-id" });

  await act(async () => {
    u.unmount();
  });

  expect(stopCagrilari()).toHaveLength(1);
});
