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
// Rehber açılınca SEBEBİ araştırır (2026-08-14). Tanı ağ isteği yapar → testte enjekte edilir.
const mockTani = jest.fn();
jest.mock("@/services/agTanisi", () => ({
  agTanisiYap: () => mockTani(),
  taniMesaji: (t: { durum: string }) =>
    t.durum === "bilinmiyor" ? null : { baslik: "SEBEP-BASLIK", metin: "SEBEP-METIN" },
}));

import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { DevicePairingGuide } from "@/components/domain/DevicePairingGuide";

// ⚠️ `await`: rehber açılışta tanıyı ASENKRON çalıştırır. Akıtmazsak `setTani` test gövdesinden
// SONRA düşer ve her testte act() uyarısı üretir — gürültü gerçek uyarıları görünmez yapar.
const setup = async (onClose = jest.fn()) => {
  const u = render(<DevicePairingGuide visible onClose={onClose} />);
  await act(async () => {});
  return { onClose, ...u };
};

beforeEach(() => {
  jest.clearAllMocks();
  mockTani.mockResolvedValue({ durum: "bilinmiyor" }); // varsayılan: sebep bilinmiyor → kutu YOK
});

describe("eşleştirme rehberi", () => {
  it("KRITIK: 'Yeniden Dene' YOLU vardır ve keşfi tetikler", async () => {
    const u = await setup();
    fireEvent.press(u.getByText("Yeniden Dene"));
    expect(mockReconnect).toHaveBeenCalled();
    expect(u.onClose).toHaveBeenCalled(); // sonucu görebilmek için kapanır
  });

  it("KRITIK: KOD girişi yolu vardır", async () => {
    const u = await setup();
    expect(u.getByLabelText("Eşleştirme kodu")).toBeTruthy();
    expect(u.getByText("Cihaza Bağlan")).toBeTruthy();
  });

  it("kodun cihazda NEREDE olduğunu söyler", async () => {
    const u = await setup();
    expect(u.getByText(/Uzaktan Erişim Bağlantısı/)).toBeTruthy();
  });

  it("kod boşken bağlanma denenmez", async () => {
    const u = await setup();
    fireEvent.press(u.getByText("Cihaza Bağlan"));
    expect(mockCihazaBaglan).not.toHaveBeenCalled();
  });

  it("başarılı eşleşmede yeniden bağlanır ve kapanır", async () => {
    mockCihazaBaglan.mockResolvedValue({ durum: "ok", url: "https://x", deviceId: "1" });
    const u = await setup();
    fireEvent.changeText(u.getByLabelText("Eşleştirme kodu"), "MVPDDN");
    fireEvent.press(u.getByText("Cihaza Bağlan"));
    await waitFor(() => expect(mockReconnect).toHaveBeenCalled());
    expect(u.onClose).toHaveBeenCalled();
  });

  it("başarısız eşleşmede KAPANMAZ (kullanıcı düzeltebilsin)", async () => {
    mockCihazaBaglan.mockResolvedValue({ durum: "adres_yok" });
    const u = await setup();
    fireEvent.changeText(u.getByLabelText("Eşleştirme kodu"), "MVPDDN");
    fireEvent.press(u.getByText("Cihaza Bağlan"));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith("mesaj", "error"));
    expect(u.onClose).not.toHaveBeenCalled();
  });

  it("kod BÜYÜK HARFE çevrilir (kullanıcı küçük yazsa da)", async () => {
    const u = await setup();
    const alan = u.getByLabelText("Eşleştirme kodu");
    fireEvent.changeText(alan, "mvpddn");
    expect(alan.props.value).toBe("MVPDDN");
  });

  // ── SEBEP KUTUSU (2026-08-14 saha bildirimi: modemde istemci izolasyonu) ────────────────
  // Cihaz çalışıyor, aynı ağ, mDNS yayında, güvenlik duvarı açık — ama bağlanmıyor. Ekran
  // yalnız "cihaz bulunamadı" diyordu; sebebi bulmak ürünü YAZAN kişinin bir saatini aldı.

  it("KRITIK: sebep teşhis edilebiliyorsa AÇIKLAMA gösterilir", async () => {
    mockTani.mockResolvedValue({ durum: "izolasyon", cihazIp: "192.168.1.44" });
    const u = await setup();
    expect(await waitFor(() => u.getByTestId("tani-kutusu"))).toBeTruthy();
    expect(u.getByText("SEBEP-BASLIK")).toBeTruthy();
  });

  it("KRITIK: sebep BİLİNMİYORSA hiçbir şey uydurulmaz", async () => {
    // Yanlış teşhis, teşhissizlikten kötüdür: kullanıcıyı modem ayarlarında boşuna gezdirir.
    const u = await setup();
    await waitFor(() => expect(u.queryByTestId("tani-kutusu")).toBeNull());
    await waitFor(() => expect(u.queryByTestId("tani-kutusu")).toBeNull());
  });

  it("tanı ÇÖKERSE rehber yine de çalışır (kod girişi kaybolmaz)", async () => {
    mockTani.mockRejectedValue(new Error("ağ yok"));
    const u = await setup();
    await waitFor(() => expect(u.getByText("Cihaza Bağlan")).toBeTruthy());
    expect(u.queryByTestId("tani-kutusu")).toBeNull();
  });

  it("rehber KAPALIYKEN tanı için ağa çıkılmaz", () => {
    render(<DevicePairingGuide visible={false} onClose={jest.fn()} />);
    expect(mockTani).not.toHaveBeenCalled();
  });

  it("KRITIK: kapanınca eski teşhis silinir — yeniden açılışta BAYAT sebep gösterilmez", async () => {
    mockTani.mockResolvedValue({ durum: "izolasyon", cihazIp: "192.168.1.44" });
    const u = render(<DevicePairingGuide visible onClose={jest.fn()} />);
    await act(async () => {});
    expect(u.getByTestId("tani-kutusu")).toBeTruthy();

    // Kullanıcı modem ayarını düzeltti ve rehberi yeniden açtı. Yeni tanı HENÜZ sonuçlanmadı:
    // bu aralıkta eski teşhis durursa kullanıcı düzelttiği sorunu hâlâ varmış gibi görür.
    mockTani.mockReturnValue(new Promise(() => {})); // hiç çözülmeyen tanı
    u.rerender(<DevicePairingGuide visible={false} onClose={jest.fn()} />);
    u.rerender(<DevicePairingGuide visible onClose={jest.fn()} />);
    await act(async () => {});
    expect(u.queryByTestId("tani-kutusu")).toBeNull();
  });
});
