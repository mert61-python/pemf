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
// ⚠️ KAMERA MOCK'U REF TAŞIR (2026-08-24): AI Pro mobilde artık ÖNCE hazırlık aşamasına girer
// (kedi → organ → öneri). Hazırlık kare akışına dayanır; ref taşımayan bir mock'ta
// `cameraRef.current` null kalır, kare hiç çekilmez ve akış ilerlemez. Gerçek akışı sınamak için
// mock `takePictureAsync` sunar; `global.fetch` de LOKALİZE bir kare yanıtı döndürür.
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return {
    CameraView: React2.forwardRef((_p: unknown, ref: unknown) => {
      React2.useImperativeHandle(ref, () => ({
        takePictureAsync: async () => ({ base64: "AAAA" }),
      }));
      return null;
    }),
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { AiProPanel } from "../AiProPanel";

const stopCagrilari = () =>
  (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop");

// Hazırlık karesi: organ LOKALİZE döner → panel öneriyi otomatik ister.
const gercekFetch = global.fetch;
beforeAll(() => {
  // Hazirlik kare akisi 400 ms'lik interval — sahte zamanlayici olmadan ilerletilemez.
  jest.useFakeTimers();
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ status: "success", detected: true, catDetected: true, reliability: 0.9 }),
  })) as unknown as typeof fetch;
});
afterAll(() => { global.fetch = gercekFetch; jest.useRealTimers(); });

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
  mockDurum = { active: false };
});

/** Hazırlık aşamasını ilerlet: kare yakalama 400 ms'lik interval'de → zamanlayıcıyı akıt. */
async function hazirligiIlerlet() {
  // ⚠️ Hazirlik kare araligi 1500 ms VE oneri icin ARDISIK_ONAY (2) dogrulanmis olcum gerekir
  // (tek sansli kare tedavi parametresi uretmesin). Yeterli tur at.
  for (let i = 0; i < 30; i++) {
    await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
  }
}

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
  // 🔴 2026-08-24: mobilde "Başlat" artık doğrudan öneri üretmez; ÖNCE hazırlık (kedi → organ)
  // koşar, lokalizasyon oluşunca öneri OTOMATİK istenir. Bu ara adım olmadan propose taze
  // lokalizasyon bulamıyor ve akış "Organ henüz lokalize edilmedi" hatasında kilitleniyordu.
  await hazirligiIlerlet();
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

// ── F2 (denetim 2026-08-24): ARDISIK "iki tutarlı ölçüm" eko-karelerle boşa düşmemeli ──
const proposeCagrilari = () =>
  (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/propose");

/** Her kare AYNI localizedAt (tek ölçümün ekosu) → ardisik 2'ye ULAŞMAMALI → propose YOK. */
it("🔴 F2: AYNI lokalizasyon damgalı eko kareler öneriyi TETİKLEMEZ (sahte sertleşme değil)", async () => {
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ status: "success", detected: true, catDetected: true, reliability: 0.9, localizedAt: 100 }),
  })) as unknown as typeof fetch;
  mockDurum = { active: false };
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await hazirligiIlerlet();
  // Tek gerçek ölçümün ~20 eko karesi: damga sabit → sayaç 1'de kalır → öneri istenmez.
  expect(proposeCagrilari()).toHaveLength(0);
});

/** localizedAt her karede DEĞİŞİRSE (iki AYRI ölçüm) sayaç 2'ye ulaşır → propose istenir. */
it("F2 KARŞIT-KANIT: YENİ lokalizasyon damgaları öneriyi tetikler (gerçek iki ölçüm)", async () => {
  let at = 100;
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ status: "success", detected: true, catDetected: true, reliability: 0.9, localizedAt: (at += 1) }),
  })) as unknown as typeof fetch;
  mockDurum = { active: false };
  const u = await panel();
  await act(async () => { fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat")); });
  await hazirligiIlerlet();
  expect(proposeCagrilari().length).toBeGreaterThan(0);
});
