// Author: mertaygn, cglrgrkn
/**
 * ACİL DURDUR — STM BELİRSİZLİĞİNDE GİZLENMEZ  [ekranB-2, 2026-09-04 responsive denetimi]
 * ======================================================================================
 * ÖLÇÜLEN DURUM: `LiveDataContext.normalizeStmCoils` STM seri bağlantısı koptuğunda 1-5 numaralı
 * bobinleri `running:false` yapıyor (bkz. LiveDataContext.tsx:88-92). Bu "bobin durdu" DEĞİL,
 * "durum bilinmiyor" demektir. `GlobalEmergencyStop` ise `if (!running && !active) return null`
 * ile bu belirsizliği "hiçbir şey çalışmıyor" sayıp kendini KALDIRIYORDU → operatör tam da
 * bağlantı koptuğu anda (bobinler hastanın üzerinde olabilir, WiFi bobinleri 6-8 gerçekten
 * sürülüyor olabilir) tek dokunuşluk durdurma yolunu kaybediyordu.
 *
 * SÖZLEŞME (bu test): bir kez "çalışıyor" görüldüyse, STM yeniden ÇEVRİMİÇİ olup "durdu" diyene
 * kadar düğme ekranda KALIR. Hiç çalışmamış donanımsız/demo makinede ise GÖRÜNMEZ (gürültü yok).
 *
 * ⚠️ MUTASYON: `if (!running && !active && !belirsiz)` koşulundan `!belirsiz` silinirse ya da
 * `belirsizKilit` kalıcılığı kaldırılırsa 3. senaryo KIRILIR.
 */
import React from "react";
import { render } from "@testing-library/react-native";

let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: true }),
}));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "t",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "b",
}));

import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

const bobin = (id: number, running: boolean) => ({ id, running, connected: true });

function ciz(snapshot: Record<string, unknown>) {
  mockSnapshot = snapshot;
  return render(<GlobalEmergencyStop />);
}

describe("GlobalEmergencyStop — görünürlük", () => {
  it("bobin çalışırken görünür (temel sözleşme)", () => {
    const { queryByLabelText } = ciz({ stm: "online", coils: [bobin(1, true)] });
    expect(queryByLabelText("Acil durdur")).not.toBeNull();
  });

  it("STM çevrimiçi ve hiçbir şey çalışmıyorsa GÖRÜNMEZ", () => {
    const { queryByLabelText } = ciz({ stm: "online", coils: [bobin(1, false)] });
    expect(queryByLabelText("Acil durdur")).toBeNull();
  });

  it("KRİTİK: hiç çalışmamış donanımsız makinede (STM çevrimdışı) GÖRÜNMEZ — gürültü yok", () => {
    const { queryByLabelText } = ciz({ stm: "offline", coils: [bobin(1, false)] });
    expect(queryByLabelText("Acil durdur")).toBeNull();
  });

  it("KRİTİK: çalışırken STM bağlantısı koparsa düğme EKRANDA KALIR ve nedenini söyler", () => {
    const { queryByLabelText, queryByText, rerender } = ciz({ stm: "online", coils: [bobin(1, true)] });
    expect(queryByLabelText("Acil durdur")).not.toBeNull();

    // STM koptu → normalizeStmCoils bobinleri running:false yapar (durum BİLİNMİYOR).
    mockSnapshot = { stm: "offline", coils: [bobin(1, false)] };
    rerender(<GlobalEmergencyStop />);

    expect(queryByLabelText("Acil durdur")).not.toBeNull();
    expect(queryByText(/bağlantı yok/)).not.toBeNull();
  });

  it("STM geri gelip 'durdu' derse düğme kaybolur (kilit temizlenir)", () => {
    const { queryByLabelText, rerender } = ciz({ stm: "online", coils: [bobin(1, true)] });
    mockSnapshot = { stm: "offline", coils: [bobin(1, false)] };
    rerender(<GlobalEmergencyStop />);
    expect(queryByLabelText("Acil durdur")).not.toBeNull();

    mockSnapshot = { stm: "online", coils: [bobin(1, false)] };
    rerender(<GlobalEmergencyStop />);
    expect(queryByLabelText("Acil durdur")).toBeNull();
  });

  it("seans aktifken STM koparsa da görünür (activeTreatment yolu)", () => {
    const { queryByLabelText } = ciz({ stm: "offline", coils: [], activeTreatment: { isActive: true } });
    expect(queryByLabelText("Acil durdur")).not.toBeNull();
  });
});
