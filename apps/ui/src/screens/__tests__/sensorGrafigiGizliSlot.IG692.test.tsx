// Author: mertaygn, cglrgrkn
/**
 * İG-6.92 — Sensör Monitörü grafiği GİZLİ slot 8'in (ESP kapalı, çipi / kartı yok) serisini ÇİZMEZ.
 * =================================================================================================
 * ÖLÇÜLEN KUSUR (HEAD `ebf1c3fe`): `visibleCoils` varsayılanı `tumSlotIdleri()` = {1..8}; çip satırı ve kart ızgarası
 * `gorunurBobinler` ile süzülür (slot 8 bağlı / çalışır değilken GİZLİ), ama grafiğe süzülmemiş küme gidiyordu. `PEMF_SIMULATE=1`
 * + `PEMF_ESP_ENABLED=0` sim döngüsü slot 8 için de `sensor_data` yayınlıyor (`magneticMt` ≈ 0,0–0,05, `coil_status` connected=false,
 * running=false — gerçek `_hardware_simulation_loop` bir tur, `_inceleme/IG-6.92/kayit/sim_yayinlari.json`). Sonuç: grafikte
 * 8. bir eğri (çipi olmadığı için KAPATILAMAZ) ve mT ekseni 0'a çekiliyor (STM bobinlerinin ~2 mT eğrisi eziliyor). ESP açıkken de
 * aynısı: slot 8 bağlantısı düşünce çipi kaybolur, geçmişi grafikte kalır.
 * SÖZLEŞME: grafiğe YALNIZ çipi çizilen (görünür) VE seçili bobinler girer. Çalışan slot 8 (`running`) görünür kalır (gizlenmez).
 * GERÇEK: `LiveDataProvider` (geçmiş tamponu), `SensorMonitorScreen`, `RealtimeChart` (native SVG yolu), `bobinGorunurlugu`.
 * ⚠️ MUTASYON: grafiğe süzülmemiş `visibleCoils` geri verilirse ya da süzgeç tüm slotları geçirirse KIRMIZI.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:65530/api", websocketUrl: "ws://127.0.0.1:65530/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Polyline, Text as SvgText } from "react-native-svg";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";

// Grafik paleti (RealtimeChart COIL_COLORS ile aynı sıra) — slot 8'in rengi.
const SLOT8_RENGI = "#EAB308";
const MT_EKSEN_RENGI = "#22c55e";

type Durum = { connected: boolean; running: boolean };

/** Sim döngüsünün yayın ŞEKLİ (ESP kapalı): STM 1..7 bağlı + çalışıyor (~2 mT), slot 8 bağlı değil, boşta ≈ 0,049 mT. */
function mesajlar(slot8: Durum, tur = 4): any[] {
  const t0 = 1_793_157_918;
  const coils = Array.from({ length: 8 }, (_, i) => {
    const id = i + 1;
    const d = id <= 7 ? { connected: true, running: true } : slot8;
    return { id, ...d, frequencyHz: d.running ? 50 : 0, dutyCycle: d.running ? 25 : 0, magneticMt: 0, objectTemp: null, currentA: 0 };
  });
  const out: any[] = [
    {
      type: "snapshot",
      data: {
        gateway: "devre_disi", mqtt: "devre_disi", stm: "online",
        patient: { name: "", species: "", breed: "", owner: "" },
        activeTreatment: { isActive: true, mode: "Manuel", frequencyHz: 50, intensityMt: 1, remainingMin: 5, elapsedSec: 0, durationSec: 300 },
        notifications: [], coils, system: {}, sessions: [],
      },
    },
  ];
  for (let k = 0; k < tur; k++) {
    for (const c of coils) {
      const mt = c.id <= 7 ? 2.0 + 0.01 * k + 0.001 * c.id : 0.049;
      out.push({
        type: "sensor_data",
        coilId: c.id,
        timestamp: t0 + 0.5 * k,
        data: { magneticMt: mt, objectTemp: null, ambientTemp: null, currentA: 0.0 },
      });
    }
  }
  return out;
}

async function ekran(slot8: Durum) {
  const u = render(
    <LiveDataProvider>
      <SensorMonitorScreen />
    </LiveDataProvider>
  );
  await act(async () => {});
  await act(async () => {
    mockWs.onState?.(true);
  });
  for (const m of mesajlar(slot8)) {
    await act(async () => {
      mockWs.onMessage?.(m);
    });
  }
  // Grafik yalnız kabın GERÇEK genişliği ölçülünce çizilir (onLayout).
  const kap = u.UNSAFE_root.findAll((n: any) => typeof n.props?.onLayout === "function" && n.type === "View");
  expect(kap.length).toBeGreaterThan(0);
  await act(async () => {
    for (const k of kap) fireEvent(k, "layout", { nativeEvent: { layout: { x: 0, y: 0, width: 600, height: 300 } } });
  });
  return u;
}

const mTEgrileri = (u: ReturnType<typeof render>) =>
  u.UNSAFE_queryAllByType(Polyline).filter((p) => p.props.strokeWidth === 1.5);
const mtEkseni = (u: ReturnType<typeof render>) =>
  u.UNSAFE_queryAllByType(SvgText).filter((t) => t.props.fill === MT_EKSEN_RENGI).map((t) => Number(t.props.children));
const ciplerdeSlot8 = (u: ReturnType<typeof render>) => u.queryAllByLabelText(/Bobin 8/).length;

describe("İG-6.92 — Sensör grafiği gizli slot 8 serisini çizmez (ESP kapalı sim yayını)", () => {
  it("aparat: görünür 7 STM bobini çiziliyor (vakum değil), slot 8 çipi YOK", async () => {
    const u = await ekran({ connected: false, running: false });
    expect(ciplerdeSlot8(u)).toBe(0);
    const renkler = new Set(mTEgrileri(u).map((p) => p.props.stroke));
    expect(renkler.size).toBeGreaterThanOrEqual(7);
  });

  it("KRİTİK: gizli slot 8 (bağlı değil, boşta) için mT eğrisi ÇİZİLMEZ — görünür seri sayısı = çip sayısı (7)", async () => {
    const u = await ekran({ connected: false, running: false });
    const egriler = mTEgrileri(u);
    expect(egriler.filter((p) => p.props.stroke === SLOT8_RENGI)).toHaveLength(0);
    expect(egriler).toHaveLength(7);
  });

  it("KRİTİK: gizli slot 8'in ≈0 mT'si mT eksenini 0'a ÇEKMEZ (STM bobinleri ~2 mT)", async () => {
    const u = await ekran({ connected: false, running: false });
    const eksen = mtEkseni(u);
    expect(eksen).toHaveLength(5);
    expect(Math.min(...eksen)).toBeGreaterThan(1);
  });

  it("KARŞIT: seçim hâlâ etkili — görünür bir bobinin çipi kapatılınca o eğri grafikten ÇIKAR (süzgeç seçimi yok saymaz)", async () => {
    const u = await ekran({ connected: false, running: false });
    await act(async () => {
      fireEvent.press(u.getByLabelText("Bobin 3 grafiğini göster/gizle"));
    });
    const egriler = mTEgrileri(u);
    expect(egriler).toHaveLength(6);
    expect(egriler.filter((p) => p.props.stroke === "#22C55E")).toHaveLength(0);
  });

  it("KARŞIT: slot 8 ÇALIŞIYORSA (bağlantı düşse bile) görünür kalır ve eğrisi ÇİZİLİR — enerjili bobin gizlenmez", async () => {
    const u = await ekran({ connected: false, running: true });
    expect(ciplerdeSlot8(u)).toBe(1);
    expect(mTEgrileri(u).filter((p) => p.props.stroke === SLOT8_RENGI)).toHaveLength(1);
  });

  it("KARŞIT: slot 8 BAĞLIYKEN (ESP açık) çipi var ve eğrisi varsayılan olarak ÇİZİLİR", async () => {
    const u = await ekran({ connected: true, running: false });
    expect(ciplerdeSlot8(u)).toBe(1);
    expect(mTEgrileri(u)).toHaveLength(8);
  });
});
