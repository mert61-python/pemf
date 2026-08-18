// Author: mertaygn, cglrgrkn
/**
 * useTeardownGuard — "Çıkış Yap" / "Farklı Profile Geç" gibi uygulama KABUĞUNU söken eylemlerin
 * hasta-güvenliği kapısı. Denetim bulgusu (P1 ×3): bu eylemler tedavi sürerken tek dokunuşla,
 * onaysız çalışıyor ve ACİL DURDUR'un yaşadığı ağacı komple söküyordu → bobinler hayvanın üzerinde
 * çalışırken operatörün elinde hiçbir durdurma kontrolü kalmıyordu.
 *
 * Kilitlenen sözleşme:
 *   1. Donanım BOŞTA  → soru sorma, doğrudan izin ver
 *   2. Bobin çalışıyor VEYA seans aktif → ONAY iste
 *   3. Onay verilmezse → eylem İPTAL
 *   4. Onay verilir + durdurma TEYİT EDİLEMEZSE → eylem yine İPTAL (kabuk sökülmez)
 *   5. `activeTreatment.isActive` false olsa da çalışan bobin varsa kapı DEVREDE
 *      (AI Pro / fiziksel / başka istemci session_* yayınlamaz)
 */
jest.mock("@/services/apiClient", () => ({
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "UYARI",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "gövde",
}));

import React from "react";
import { renderHook } from "@testing-library/react-native";
import { platformAlert, platformConfirm } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";

const mockConfirm = platformConfirm as jest.Mock;
const mockAlert = platformAlert as jest.Mock;
const mockStop = performEmergencyStop as jest.Mock;

// LiveDataContext'i sahte snapshot'la besle (gerçek provider WS/discovery başlatır).
let mockSnap: any;   // jest kuralı: mock fabrikasından erişilen değişken 'mock' ile başlamalı
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap }),
}));

const coils = (runningIds: number[]) =>
  Array.from({ length: 8 }, (_, i) => ({ id: i + 1, running: runningIds.includes(i + 1) }));

beforeEach(() => {
  mockConfirm.mockReset();
  mockAlert.mockReset();
  mockStop.mockReset();
  mockSnap = { coils: coils([]), activeTreatment: { isActive: false } };
});

const run = async (label = "Çıkış yapmak") => {
  const { result } = renderHook(() => useTeardownGuard());
  return result.current(label);
};

it("donanım boştayken SORU SORMAZ, doğrudan izin verir", async () => {
  await expect(run()).resolves.toBe(true);
  expect(mockConfirm).not.toHaveBeenCalled();
  expect(mockStop).not.toHaveBeenCalled();
});

it("aktif seans varken ONAY ister; onaylanır + durdurma teyitliyse izin verir", async () => {
  mockSnap.activeTreatment.isActive = true;
  mockConfirm.mockResolvedValue(true);
  mockStop.mockResolvedValue({ confirmed: true });

  await expect(run()).resolves.toBe(true);
  expect(mockConfirm).toHaveBeenCalledTimes(1);
  expect(mockStop).toHaveBeenCalledTimes(1); // önce durdur, sonra sök
});

it("KRİTİK: seans bayrağı KAPALI olsa da çalışan bobin varsa kapı DEVREDE (AI Pro yolu)", async () => {
  mockSnap = { coils: coils([3, 7]), activeTreatment: { isActive: false } };
  mockConfirm.mockResolvedValue(false);

  await expect(run()).resolves.toBe(false);
  expect(mockConfirm).toHaveBeenCalledTimes(1);
});

it("kullanıcı onaylamazsa eylem İPTAL ve donanıma DOKUNULMAZ", async () => {
  mockSnap = { coils: coils([1]), activeTreatment: { isActive: false } };
  mockConfirm.mockResolvedValue(false);

  await expect(run()).resolves.toBe(false);
  expect(mockStop).not.toHaveBeenCalled();
});

it("KRİTİK: durdurma TEYİT EDİLEMEZSE eylem İPTAL — kabuk sökülmez, operatör uyarılır", async () => {
  mockSnap = { coils: coils([2]), activeTreatment: { isActive: false } };
  mockConfirm.mockResolvedValue(true);
  mockStop.mockResolvedValue({ confirmed: false });

  await expect(run()).resolves.toBe(false); // <-- E-stop erişimi KORUNUR
  expect(mockAlert).toHaveBeenCalled();
  expect(String(mockAlert.mock.calls[0][1])).toContain("iptal");
});

it("onay metni eylem adını ve çalışan bobin sayısını içerir (operatör ne kaybedeceğini bilsin)", async () => {
  mockSnap = { coils: coils([1, 2, 5]), activeTreatment: { isActive: false } };
  mockConfirm.mockResolvedValue(false);

  await run("Profil değiştirmek");
  const body = String(mockConfirm.mock.calls[0][1]);
  expect(body).toContain("3 bobin");
  expect(body).toContain("Profil değiştirmek");
});

it("snapshot bozuksa (coils yok) çökmez", async () => {
  mockSnap = {};
  await expect(run()).resolves.toBe(true);
});

// ── Opsiyonel BOŞTA-onay (2026-08-06) ────────────────────────────────────────
// "Çıkış Yap" nav'da Ayarlar'ın hemen ardına geldi → yanlış dokunuş riski arttı ve kazara çıkış
// mobilde e-posta+şifre tekrarı demek. Tıbbi kapı DEĞİŞMEDİ; bu ek onay OPSİYONEL ve yalnız
// donanım BOŞTAYKEN devrede. Yukarıdaki 7 test parametresiz çağrıyı (eski davranış) kilitler.
describe("confirmWhenIdle — kazara dokunuş koruması", () => {
  const runIdle = async (confirmLabel?: string) => {
    const { result } = renderHook(() => useTeardownGuard());
    return result.current("Çıkış yapmak", {
      confirmWhenIdle: { title: "Çıkış Yap", body: "Oturum kapatılacak.", confirmLabel },
    });
  };

  it("boştayken ONAY ister; iptal edilirse eylem YAPILMAZ", async () => {
    mockConfirm.mockResolvedValue(false);
    await expect(runIdle("Çıkış yap")).resolves.toBe(false);
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(mockConfirm.mock.calls[0][0]).toBe("Çıkış Yap");
    expect(mockConfirm.mock.calls[0][2]).toBe("Çıkış yap");
  });

  it("boşta onay verilirse izin verir ve DONANIMA DOKUNMAZ (gereksiz E-stop yok)", async () => {
    mockConfirm.mockResolvedValue(true);
    await expect(runIdle()).resolves.toBe(true);
    expect(mockStop).not.toHaveBeenCalled();
  });

  it("KRİTİK: donanım ÇALIŞIRKEN tıbbi kapı öncelikli — boşta metni DEĞİL tedavi uyarısı gösterilir", async () => {
    mockSnap = { coils: coils([4]), activeTreatment: { isActive: false } };
    mockConfirm.mockResolvedValue(false);
    await expect(runIdle()).resolves.toBe(false);
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(mockConfirm.mock.calls[0][0]).toBe("Seans sürüyor");
  });
});
