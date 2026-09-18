// Author: mertaygn, cglrgrkn
/**
 * SURUM FARKI BANDI davranis kilidi (2026-08-22; SAHADA DUZELTILDI 2026-08-23).
 *
 * SAHADAN GELEN HATA: ilk tasarim telefonun 2.3.x surumunu CIHAZIN 1.9.x surumuyle kiyasliyordu.
 * Iki ayri numaralandirma SEMASI hicbir zaman esit olamaz -> bant TAM GUNCEL sistemde de
 * "Surumler farkli" diyordu (yanlis alarm, kullanici bildirdi). Dogru olcu: yayinlanmis EN SON
 * mobil surum — guncelleme altyapisiyla (guncellemeVarMi) AYNI kaynak.
 *
 * Pazarlik-edilemez davranislar:
 *  1. Telefon GUNCELKEN bant GORUNMEZ (sahadaki yanlis alarmin kilidi).
 *  2. Telefon gercekten ESKIYKEN ve guncelleme kapida ERTELENDIYSE bant gorunur; mevcut->yeni
 *     surumu soyler. Cihazin 1.9.x surumuyle KIYAS YOKTUR.
 *  3. Erteleme YOKSA bant gorunmez — o durumda MobileUpdateBanner (indirme dugmeli) sahnededir;
 *     ayni bilgiyi iki bantla ust uste soylemeyiz (ortak olcu: atlandiMi, ayni modul durumu).
 *  4. SEANS SURERKEN gosterilmez (bobinler hastanin uzerindeyken ekran bolunmez).
 *  5. Guncelleme bilgisi ALINAMAZSA (ag yok / manifest bozuk) bant uretilmez — internetsiz
 *     klinikte sahte uyari olmaz (fail-quiet, MobileUpdateBanner ilkesi).
 */
import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";

let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: true }),
}));

const mockSetItem = jest.fn(async () => undefined);
let mockKayitliKapatma: string | null = null;
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(async () => mockKayitliKapatma),
  setItem: (...a: unknown[]) => mockSetItem(...(a as [])),
}));
jest.mock("expo-constants", () => ({ default: { expoConfig: { version: "2.3.21" } } }));

let mockDurum: unknown = { varMi: false, sebep: "guncel" };
let mockAtlandi = true;
jest.mock("@/services/mobileUpdate", () => ({
  guncellemeVarMi: jest.fn(async () => mockDurum),
  atlandiMi: jest.fn(() => mockAtlandi),
  mevcutVersionCode: jest.fn(() => 28),
}));

import { SurumFarkiBanner } from "@/components/domain/SurumFarkiBanner";

const YENI = { version: "2.3.22", versionCode: 29, url: "u", sha256: "s", size: 1 };

function kur(opts: { eski?: boolean; atlandi?: boolean; seans?: boolean; kapatilan?: string | null } = {}) {
  mockDurum = opts.eski ? { varMi: true, surum: YENI } : { varMi: false, sebep: "guncel" };
  mockAtlandi = opts.atlandi ?? true;
  mockKayitliKapatma = opts.kapatilan ?? null;
  mockSnapshot = { activeTreatment: { isActive: opts.seans ?? false } };
  return render(<SurumFarkiBanner />);
}

// Bant, async yukleme (manifest + AsyncStorage) bitene kadar ZATEN null cizer; negatif testte
// `toJSON()===null` yukleme baslamadan trivially gecmesin diye ONCE yukleme bosaltilir (M85 dersi).
async function yuklemeyiBitir() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

it("KRITIK (sahadan): telefon GUNCELKEN bant GORUNMEZ — 2.3.x/1.9.x sema farki uyari degildir", async () => {
  const { toJSON } = kur({ eski: false });
  await yuklemeyiBitir();
  expect(toJSON()).toBeNull();
});

it("KRITIK: telefon eskiyken + kapida ertelendiyse bant gorunur ve mevcut→yeni surumu soyler", async () => {
  const { findByText, queryByText } = kur({ eski: true, atlandi: true });
  expect(await findByText(/2\.3\.21.*2\.3\.22/)).toBeTruthy();
  // Cihazin 1.9.x surumu KIYASA GIRMEZ (ilk tasarimin hatasi geri gelmesin):
  expect(queryByText(/1\.9\./)).toBeNull();
});

it("KRITIK: erteleme yoksa bant null — MobileUpdateBanner sahnedeyken cift bant uretilmez", async () => {
  const { toJSON } = kur({ eski: true, atlandi: false });
  await yuklemeyiBitir();
  expect(toJSON()).toBeNull();
});

it("KRITIK: SEANS SURERKEN gosterilmez (ekran bolunmez)", async () => {
  const { toJSON } = kur({ eski: true, seans: true });
  await yuklemeyiBitir();
  expect(toJSON()).toBeNull();
});

it("KARSIT-KANIT: bilgi alinamazsa (ag/manifest yok) sahte uyari URETILMEZ", async () => {
  mockKayitliKapatma = null;
  mockAtlandi = true;
  mockSnapshot = { activeTreatment: { isActive: false } };
  mockDurum = { varMi: false, sebep: "manifest" };
  const { toJSON } = render(<SurumFarkiBanner />);
  await yuklemeyiBitir();
  expect(toJSON()).toBeNull();
});

it("kapatma SURUM CIFTINE baglidir: kayitli cift eslesirse null, yeni surumde bant geri gelir", async () => {
  // Ayni cift kapatilmis -> gorunmez:
  const a = kur({ eski: true, kapatilan: "28|29" });
  await yuklemeyiBitir();
  expect(a.toJSON()).toBeNull();
  a.unmount();
  // Eski formatta/baska ciftte kayit -> bant gorunur (yeni yayin uyariyi geri getirir):
  const b = kur({ eski: true, kapatilan: "2.3.21|1.9.19" });
  expect(await b.findByText(/2\.3\.22/)).toBeTruthy();
  // X'e basinca cift AsyncStorage'a yazilir:
  fireEvent.press(b.getByLabelText("Sürüm bildirimini kapat"));
  expect(mockSetItem).toHaveBeenCalledWith("pemf.surumFarki.kapatilan", "28|29");
});
