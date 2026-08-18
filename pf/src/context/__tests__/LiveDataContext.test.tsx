// Author: mertaygn, cglrgrkn
/**
 * LiveDataContext — bu denetimde düzeltilen davranışların kilidi.
 *
 * ⚠️ BİLİNÇLİ KARAR (test bunu KORUR, geri getirmez): `connectionQuality` SALT `live|offline`.
 *    3-durumlu global "Veri gecikmeli" göstergesi KASITLI kaldırıldı. Tazelik yalnız aktif
 *    tedaviye özgü `telemetryStale` ile ölçülür.
 *
 * Kilitlenen düzeltmeler:
 *   #12 markRealData YALNIZ gerçek telemetri mesajlarıyla tazelenir (ai_vision/notification/
 *       gateway_status/session_tick telemetri yayıncısından bağımsızdır → donmuş sensör verisini
 *       maskeliyordu)
 *   #11 aiVisionData emergency_stop'ta TEMİZLENİR + `aiVisionFresh` tazelik kapısı
 *   #46 markAllRead yereldir → yeniden bağlanmada gelen snapshot okunmuşları geri DİRİLTMEZ
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (_p: string, fb: unknown) => fb),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api", websocketUrl: "ws://192.168.1.5:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));

// WS'i ele geçir: mesajları testten enjekte edip bağlantı durumunu elle sürelim.
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { render, act, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";

function Probe() {
  const { connectionQuality, telemetryStale, aiVisionFresh, aiVisionData, unreadCount, snapshot } = useLiveData();
  return (
    <>
      <Text testID="quality">{connectionQuality}</Text>
      <Text testID="stale">{String(telemetryStale)}</Text>
      <Text testID="aiFresh">{String(aiVisionFresh)}</Text>
      <Text testID="aiData">{aiVisionData ? "var" : "yok"}</Text>
      <Text testID="unread">{String(unreadCount)}</Text>
      <Text testID="running">{String((snapshot.coils ?? []).filter((c: any) => c.running).length)}</Text>
    </>
  );
}

const setup = async () => {
  const utils = render(<LiveDataProvider><Probe /></LiveDataProvider>);
  await act(async () => { await Promise.resolve(); });
  return utils;
};
const send = async (msg: any) => { await act(async () => { mockWs.onMessage?.(msg); }); };
const setConnected = async (v: boolean) => { await act(async () => { mockWs.onState?.(v); }); };

/** Aktif tedavi + çalışan bobin içeren snapshot (telemetryStale'in "beklenen telemetri" koşulu). */
const busySnapshot = {
  type: "snapshot",
  data: {
    gateway: "online", mqtt: "online", stm: "online",
    activeTreatment: { isActive: true, mode: "Manuel", frequencyHz: 50, intensityMt: 1, remainingMin: 10, elapsedSec: 0, durationSec: 600 },
    coils: [{ id: 1, connected: true, running: true, frequencyHz: 50, dutyCycle: 25, magneticMt: 1, objectTemp: 30, ambientTemp: 25, currentA: 1 }],
    notifications: [],
  },
};

beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

// ── Bilinçli karar koruması ──────────────────────────────────────────────────
it("BİLİNÇLİ KARAR: connectionQuality yalnız live|offline üretir (3. durum YOK)", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  expect(getByTestId("quality").props.children).toBe("live");
  await setConnected(false);
  expect(getByTestId("quality").props.children).toBe("offline");
});

// ── #12 telemetri tazeliği ───────────────────────────────────────────────────
it("KRİTİK #12: aktif tedavide SADECE ai_vision akarken telemetri BAYAT sayılır", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  await send(busySnapshot);
  expect(getByTestId("stale").props.children).toBe("false");

  // 25 sn boyunca telemetri YOK; yalnız AI kareleri akıyor (eski kod bunu "taze" sayıyordu).
  await act(async () => { jest.advanceTimersByTime(25_000); });
  await send({ type: "ai_vision", data: { imageBase64: "x" } });
  await act(async () => { jest.advanceTimersByTime(100); });

  expect(getByTestId("stale").props.children).toBe("true"); // <-- donmuş sensör YAKALANDI
});

it("#12: gerçek telemetri (sensor_data) tazeliği YENİLER", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  await send(busySnapshot);
  await act(async () => { jest.advanceTimersByTime(25_000); });
  await send({ type: "sensor_data", coilId: 1, data: { magneticMt: 2, objectTemp: 31, ambientTemp: 25, currentA: 1 } });
  await act(async () => { jest.advanceTimersByTime(100); });
  expect(getByTestId("stale").props.children).toBe("false");
});

it("BOŞTAYKEN telemetryStale DAİMA false (yanlış-alarm yok — kaldırılan global uyarının sebebi)", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  await send({ type: "snapshot", data: { ...busySnapshot.data, activeTreatment: { isActive: false }, coils: [{ id: 1, running: false }] } });
  await act(async () => { jest.advanceTimersByTime(120_000); });
  expect(getByTestId("stale").props.children).toBe("false");
});

// ── #11 AI Pro tazeliği + temizlik ───────────────────────────────────────────
it("#11: aiVisionFresh yayın durunca false olur (donmuş kare 'canlı' gösterilmez)", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  await send({ type: "ai_vision", data: { imageBase64: "kare" } });
  expect(getByTestId("aiFresh").props.children).toBe("true");

  await act(async () => { jest.advanceTimersByTime(7_000); }); // eşik 6sn
  expect(getByTestId("aiFresh").props.children).toBe("false");
  expect(getByTestId("aiData").props.children).toBe("var"); // kare hâlâ görünür, ama TAZE DEĞİL
});

it("KRİTİK #11: emergency_stop AI karesini TEMİZLER ve tüm bobinleri durdurur", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  await send(busySnapshot);
  await send({ type: "ai_vision", data: { imageBase64: "kare" } });
  expect(getByTestId("running").props.children).toBe("1");

  await send({ type: "emergency_stop", data: {} });
  expect(getByTestId("aiData").props.children).toBe("yok");
  expect(getByTestId("aiFresh").props.children).toBe("false");
  expect(getByTestId("running").props.children).toBe("0");
});

it("E-stop sticky: acil durdurmadan HEMEN SONRA gelen geç tick bobini yeniden çalışır göstermez", async () => {
  const { getByTestId } = await setup();
  await setConnected(true);
  await send(busySnapshot);
  await send({ type: "emergency_stop", data: {} });
  await send({ type: "stm_coil_update", coilId: 1, data: { running: true } }); // soket tamponundaki geç mesaj
  expect(getByTestId("running").props.children).toBe("0");
});

// ── #46 bildirim okundu kalıcılığı ───────────────────────────────────────────
it("#46: markAllRead sonrası yeniden bağlanma okunmamış rozetini GERİ DİRİLTMEZ", async () => {
  const withNotif = {
    type: "snapshot",
    data: { ...busySnapshot.data, notifications: [{ id: "n1", read: false }, { id: "n2", read: false }] },
  };
  const Probe2 = () => {
    const { unreadCount, markAllRead } = useLiveData();
    return <Text testID="unread" onPress={markAllRead}>{String(unreadCount)}</Text>;
  };
  const { getByTestId } = render(<LiveDataProvider><Probe2 /></LiveDataProvider>);
  await act(async () => { await Promise.resolve(); });

  await setConnected(true);
  await send(withNotif);
  expect(getByTestId("unread").props.children).toBe("2");

  await act(async () => { getByTestId("unread").props.onPress(); });
  expect(getByTestId("unread").props.children).toBe("0");

  await send(withNotif); // yeniden bağlanma → sunucu hâlâ read:false diyor
  await waitFor(() => expect(getByTestId("unread").props.children).toBe("0"));
});
