// Author: mertaygn, cglrgrkn
/**
 * HASTA KAPISI (2026-08-08 sahip kararı)
 *
 * İSTEK: "akıllı teşhis kısmında hasta ekleye tıklayınca hastalar tabına yönlendirilmeli."
 * Satır-içi mini ekleme formu KALDIRILDI → hasta yönetimi TEK ekranda (Hastalar sekmesi).
 *
 * Kilitlenen davranışlar:
 *   * "Hasta Ekle" → navigateTo("patients") (satır-içi form AÇMAZ),
 *   * hasta seçilmeden sert kip içeriği GİZLER; soft kip (Kontrol ekranı) GÖSTERİR
 *     — çünkü sert kapı orada ACİL DURDUR'u da gizlerdi (hasta güvenliği),
 *   * terimler profile göre değişir (ev sahibi "hasta" demez).
 */
import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

const mockNav = { selectedPatient: null as null | { id: string; name: string },
              setSelectedPatient: jest.fn(), navigateTo: jest.fn() };
const mockMode = { isExpert: true, isResearcher: false };
const mockApiGet = jest.fn();

jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => mockNav }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => mockMode }));
jest.mock("@/services/apiClient", () => ({ apiGet: (...a: unknown[]) => mockApiGet(...a) }));

import { PatientGate } from "../PatientGate";

const Icerik = () => <Text>MODULLER</Text>;

beforeEach(() => {
  mockNav.selectedPatient = null;
  mockNav.navigateTo.mockClear();
  mockNav.setSelectedPatient.mockClear();
  mockMode.isExpert = true;
  mockMode.isResearcher = false;
  mockApiGet.mockReset().mockResolvedValue({ data: [] });
});

describe("PatientGate — yönlendirme", () => {
  it("KRİTİK: 'Hasta Ekle' HASTALAR sekmesine götürür (satır-içi form yok)", () => {
    const { getByLabelText, queryByLabelText } = render(<PatientGate><Icerik /></PatientGate>);
    fireEvent.press(getByLabelText("Hasta Ekle — Hastalar sekmesine git"));
    expect(mockNav.navigateTo).toHaveBeenCalledWith("patients");
    // Satır-içi ad alanı ARTIK YOK — iki ayrı ekleme yüzeyi tutarsızlık üretiyordu.
    expect(queryByLabelText(/Hasta adı/i)).toBeNull();
  });

  it("listedeki 'Hasta Ekle' de aynı yere götürür", async () => {
    mockApiGet.mockResolvedValue({ data: [{ id: "1", name: "Pamuk", species: "Kedi" }] });
    const { getByLabelText, getAllByLabelText } = render(<PatientGate><Icerik /></PatientGate>);
    fireEvent.press(getByLabelText("Hasta seçin"));
    await waitFor(() => getAllByLabelText("Hasta Ekle — Hastalar sekmesine git"));
    fireEvent.press(getAllByLabelText("Hasta Ekle — Hastalar sekmesine git")[0]);
    expect(mockNav.navigateTo).toHaveBeenCalledWith("patients");
  });
});

describe("PatientGate — kapı sertliği", () => {
  it("sert kip: hasta yokken modüller GİZLİ", () => {
    const { queryByText } = render(<PatientGate><Icerik /></PatientGate>);
    expect(queryByText("MODULLER")).toBeNull();
  });

  it("HASTA GÜVENLİĞİ — soft kip: hasta yokken bile içerik render edilir (ACİL DURDUR gizlenmemeli)", () => {
    const { getByText } = render(<PatientGate soft><Icerik /></PatientGate>);
    expect(getByText("MODULLER")).toBeTruthy();
  });

  it("hasta seçiliyken içerik ve ad şeridi görünür", () => {
    mockNav.selectedPatient = { id: "1", name: "Pamuk" };
    const { getByText } = render(<PatientGate><Icerik /></PatientGate>);
    expect(getByText("MODULLER")).toBeTruthy();
    expect(getByText("Pamuk")).toBeTruthy();
  });

  it("listeden seçim hastayı paylaşır (sonuç o kayda işlensin diye)", async () => {
    mockApiGet.mockResolvedValue({ data: [{ id: "7", name: "Boncuk" }] });
    const { getByLabelText } = render(<PatientGate><Icerik /></PatientGate>);
    fireEvent.press(getByLabelText("Hasta seçin"));
    await waitFor(() => getByLabelText("Seç: Boncuk"));
    fireEvent.press(getByLabelText("Seç: Boncuk"));
    expect(mockNav.setSelectedPatient).toHaveBeenCalledWith({ id: "7", name: "Boncuk" });
  });
});

describe("PatientGate — profil sözlüğü", () => {
  it("ev sahibi 'hasta' demez, 'Hayvan Ekle' der", () => {
    mockMode.isExpert = false;
    const { getByLabelText } = render(<PatientGate><Icerik /></PatientGate>);
    expect(getByLabelText("Hayvan Ekle — Hastalar sekmesine git")).toBeTruthy();
  });

  it("araştırma profili 'Örnek / Denek' terimini kullanır", () => {
    mockMode.isExpert = false;
    mockMode.isResearcher = true;
    const { getByLabelText } = render(<PatientGate><Icerik /></PatientGate>);
    expect(getByLabelText("Örnek Ekle — Hastalar sekmesine git")).toBeTruthy();
  });
});
