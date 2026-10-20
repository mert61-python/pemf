// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK bantlar — iki dilde metin görünür, davranış AYNI:
 *   · KayitDbBandi: tıbbi kayıt veritabanı hazır değil → "yeni seans BAŞLATILAMAZ" + "ACİL DURDUR ve bobin durdurma çalışır" (TR bayt bayt
 *     aynı; EN: "EMERGENCY STOP …"); koşul (dbReady === false) dilden bağımsız; backend'in `dbSebep` metni AYNEN gösterilir.
 *   · SurumFarkiBanner: "Telefon sürümü eski: <mevcut> → <yeni>" + "acil durdurma normal çalışır" cümlesi; görünürlük koşulları dilden bağımsız.
 * Banner mantığı kendi testlerinde (`KayitDbBandi.test.tsx`, `SurumFarkiBanner.test.tsx`).
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn() }));
let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: true }),
}));
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(async () => null),
  setItem: jest.fn(async () => undefined),
}));
jest.mock("expo-constants", () => ({ default: { expoConfig: { version: "2.3.21" } } }));
jest.mock("@/services/mobileUpdate", () => ({
  guncellemeVarMi: jest.fn(async () => ({ varMi: true, surum: { version: "2.3.22", versionCode: 29, url: "u", sha256: "s", size: 1 } })),
  atlandiMi: jest.fn(() => true),
  mevcutVersionCode: jest.fn(() => 28),
}));

import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { KayitDbBandi, kayitDbBandiMetni } from "@/components/domain/KayitDbBandi";
import { SurumFarkiBanner } from "@/components/domain/SurumFarkiBanner";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const mockGet = apiGet as jest.Mock;

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

describe("KayitDbBandi (tıbbi kayıt veritabanı hazır değil)", () => {
  beforeEach(() => mockGet.mockReset());

  it("Türkçe: göç öncesiyle aynı başlık / ACİL DURDUR cümlesi / varsayılan neden", () => {
    expect(kayitDbBandiMetni({ dbReady: true })).toBeNull();
    expect(kayitDbBandiMetni({ dbReady: false, dbSebep: null })).toEqual({
      baslik: "Tıbbi kayıt veritabanı hazır değil — yeni seans BAŞLATILAMAZ",
      aciklama: "Tıbbi kayıt veritabanı hazır değil; yeni seans başlatılamaz.\nACİL DURDUR ve bobin durdurma çalışır.",
    });
  });

  it("İngilizce: metin İngilizce, EMERGENCY STOP cümlesi var; koşul AYNI (dbReady=true → bant yok); backend sebep metni AYNEN", async () => {
    await enYap();
    expect(kayitDbBandiMetni({ dbReady: true })).toBeNull();
    expect(kayitDbBandiMetni({ dbReady: false, dbSebep: null })).toEqual({
      baslik: "The medical record database is not ready — a new session CANNOT BE STARTED",
      aciklama: "The medical record database is not ready; a new session cannot be started.\nEMERGENCY STOP and coil stopping still work.",
    });
    expect(kayitDbBandiMetni({ dbReady: false, dbSebep: "  sunucu nedeni  " })?.aciklama).toBe("sunucu nedeni\nEMERGENCY STOP and coil stopping still work.");
  });

  it("bileşen İngilizcede çizilir ve dil değişince yeniden çizilir", async () => {
    mockGet.mockResolvedValue({ dbReady: false, dbSebep: null });
    const u = render(<KayitDbBandi />);
    await waitFor(() => expect(u.getByText("Tıbbi kayıt veritabanı hazır değil — yeni seans BAŞLATILAMAZ")).toBeTruthy());
    await enYap();
    await waitFor(() => expect(u.getByText("The medical record database is not ready — a new session CANNOT BE STARTED")).toBeTruthy());
    expect(u.getByText(/EMERGENCY STOP and coil stopping still work/)).toBeTruthy();
  });
});

describe("SurumFarkiBanner (telefon sürümü eski)", () => {
  beforeEach(() => {
    mockSnapshot = { activeTreatment: { isActive: false } };
  });

  it("Türkçe: başlık + acil durdurma cümlesi göç öncesiyle aynı", async () => {
    const u = render(<SurumFarkiBanner />);
    expect(await u.findByText("Telefon sürümü eski: 2.3.21 → 2.3.22")).toBeTruthy();
    expect(
      u.getByText(
        "Bağlantı ve acil durdurma normal çalışır; ancak bu telefonda bazı düzeltmeler ve uyarılar eksik olabilir. Güncelleme, uygulama yeniden açıldığında tekrar önerilecek.",
      ),
    ).toBeTruthy();
    expect(u.getByLabelText("Sürüm bildirimini kapat")).toBeTruthy();
  });

  it("İngilizce: metin İngilizce; SEANS SÜRERKEN yine gösterilmez (koşul dilden bağımsız)", async () => {
    await enYap();
    const u = render(<SurumFarkiBanner />);
    expect(await u.findByText("Your phone's version is outdated: 2.3.21 → 2.3.22")).toBeTruthy();
    expect(u.getByText(/The connection and emergency stop work normally/)).toBeTruthy();
    expect(u.getByLabelText("Dismiss version notice")).toBeTruthy();
    u.unmount();
    mockSnapshot = { activeTreatment: { isActive: true } };
    const v = render(<SurumFarkiBanner />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(v.toJSON()).toBeNull();
  });
});
