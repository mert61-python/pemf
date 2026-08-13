// Author: mertaygn, cglrgrkn
/**
 * CİHAZA BAĞLANMA REHBERİ — İKİ YOL DA SUNULUR.
 *
 * Rehber, kullanıcının hangi durumda olduğunu TAHMİN ETMEZ (ilk tasarım tahmin ediyordu ve
 * yanlış sinyale dayandığı için sahada hiç açılmadı — bkz. AppShell notu). Bu yüzden İKİSİ de
 * aynı ekranda bulunmalı:
 *   • "Yeniden Dene" → aynı ağdaki geçici kopma; kod GEREKMEZ.
 *   • Kod girişi     → farklı ağ (mobil veri / başka Wi-Fi).
 * Biri kaybolursa kullanıcı yine çıkmaza girer; bu testler ikisini de kilitler.
 */
const mockCihazaBaglan = jest.fn();
jest.mock("@/services/pairing", () => ({
  cihazaBaglan: (...a: unknown[]) => mockCihazaBaglan(...a),
  eslesmeMesaji: () => "mesaj",
  KOD_MAX_UZUNLUK: 8,
}));
const mockReconnect = jest.fn();
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ reconnect: mockReconnect }),
}));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));

import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { DevicePairingGuide } from "@/components/domain/DevicePairingGuide";

const setup = (onClose = jest.fn()) => ({
  onClose,
  ...render(<DevicePairingGuide visible onClose={onClose} />),
});

beforeEach(() => jest.clearAllMocks());

describe("eşleştirme rehberi", () => {
  it("KRITIK: 'Yeniden Dene' YOLU vardır ve keşfi tetikler", async () => {
    const u = setup();
    fireEvent.press(u.getByText("Yeniden Dene"));
    expect(mockReconnect).toHaveBeenCalled();
    expect(u.onClose).toHaveBeenCalled(); // sonucu görebilmek için kapanır
  });

  it("KRITIK: KOD girişi yolu vardır", () => {
    const u = setup();
    expect(u.getByLabelText("Eşleştirme kodu")).toBeTruthy();
    expect(u.getByText("Cihaza Bağlan")).toBeTruthy();
  });

  it("kodun cihazda NEREDE olduğunu söyler", () => {
    const u = setup();
    expect(u.getByText(/Uzaktan Erişim Bağlantısı/)).toBeTruthy();
  });

  it("kod boşken bağlanma denenmez", () => {
    const u = setup();
    fireEvent.press(u.getByText("Cihaza Bağlan"));
    expect(mockCihazaBaglan).not.toHaveBeenCalled();
  });

  it("başarılı eşleşmede yeniden bağlanır ve kapanır", async () => {
    mockCihazaBaglan.mockResolvedValue({ durum: "ok", url: "https://x", deviceId: "1" });
    const u = setup();
    fireEvent.changeText(u.getByLabelText("Eşleştirme kodu"), "MVPDDN");
    fireEvent.press(u.getByText("Cihaza Bağlan"));
    await waitFor(() => expect(mockReconnect).toHaveBeenCalled());
    expect(u.onClose).toHaveBeenCalled();
  });

  it("başarısız eşleşmede KAPANMAZ (kullanıcı düzeltebilsin)", async () => {
    mockCihazaBaglan.mockResolvedValue({ durum: "adres_yok" });
    const u = setup();
    fireEvent.changeText(u.getByLabelText("Eşleştirme kodu"), "MVPDDN");
    fireEvent.press(u.getByText("Cihaza Bağlan"));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith("mesaj", "error"));
    expect(u.onClose).not.toHaveBeenCalled();
  });

  it("kod BÜYÜK HARFE çevrilir (kullanıcı küçük yazsa da)", () => {
    const u = setup();
    const alan = u.getByLabelText("Eşleştirme kodu");
    fireEvent.changeText(alan, "mvpddn");
    expect(alan.props.value).toBe("MVPDDN");
  });
});
