/**
 * CİHAZ ONAYI görünürlüğü (sahip, 2026-09-08): "PWM'i başlatınca ack geliyor mu? Uygulamadan
 * anlamıyorum, sadece butona dokunuyorum." ESP ack'i backend'e ms içinde geliyordu ama panel
 * yalnız broker PUBACK'ini ("success") görüyor, cihaz onayını hiç göstermiyordu.
 *
 * Bu test paneli GERÇEKTEN çizer: Başlat → HTTP success + command_id → "Cihaz onayı bekleniyor";
 * eşleşen `deviceAck` → "Cihaz onayladı (NN ms)"; NACK → REDDETTİ; timeout → onay gelmedi;
 * yabancı command_id → hâlâ bekleniyor; STM bobini / eski backend → hiç bekleme yok.
 * (Mutasyon: `setBekleyenKomut` çağrısı silinince ilk test düşer.)
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn() }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => ({ values: p, warnings: [] }),
}));

import { act, fireEvent, render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const { apiPost } = jest.requireMock("@/services/apiClient");
const mockApiPost = apiPost as jest.Mock;

const esp7 = {
  coilId: 7,
  connected: true,
  running: false,
  objectTemp: 30,
  frequencyHz: 0,
  dutyCycle: 0,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: false,
  stmConnected: false,
  defaultDuration: 5,
};

beforeEach(() => {
  mockApiPost.mockReset();
});

async function baslat(props: Record<string, unknown> = {}) {
  const u = render(<CoilParameterPanel {...esp7} {...props} />);
  await act(async () => {});
  fireEvent.press(u.getByLabelText("Bobini başlat"));
  await act(async () => {});
  return u;
}

it("KRİTİK: Başlat → success + command_id → 'Cihaz onayı bekleniyor' (PUBACK ≠ cihaz onayı)", async () => {
  mockApiPost.mockResolvedValue({ status: "success", command_id: "react_7_100", transport: "mqtt" });
  const u = await baslat();
  expect(u.getByTestId("cihaz-onayi").props.children).toMatch(/Cihaz onayı bekleniyor/);
});

it("eşleşen coil_ack ok=true → 'Cihaz onayladı' + gecikme ms", async () => {
  mockApiPost.mockResolvedValue({ status: "success", command_id: "react_7_101" });
  const u = await baslat();
  u.rerender(
    <CoilParameterPanel {...esp7} deviceAck={{ ok: true, reason: "ack", commandId: "react_7_101", latencyMs: 38, ts: 1 }} />,
  );
  const m = u.getByTestId("cihaz-onayi").props.children as string;
  expect(m).toMatch(/Cihaz onayladı/);
  expect(m).toMatch(/38 ms/);
});

it("YABANCI command_id'li ack bekleme durumunu KAPATMAZ (eski/başka komutun onayı sahte güvence olmasın)", async () => {
  mockApiPost.mockResolvedValue({ status: "success", command_id: "react_7_102" });
  const u = await baslat();
  u.rerender(
    <CoilParameterPanel {...esp7} deviceAck={{ ok: true, reason: "ack", commandId: "react_7_099", latencyMs: 5, ts: 1 }} />,
  );
  expect(u.getByTestId("cihaz-onayi").props.children).toMatch(/bekleniyor/);
});

it("NACK → 'REDDETTİ' (bobin ÇALIŞMIYOR); timeout → 'onayı gelmedi'", async () => {
  mockApiPost.mockResolvedValue({ status: "success", command_id: "react_7_103" });
  const u = await baslat();
  u.rerender(
    <CoilParameterPanel {...esp7} deviceAck={{ ok: false, reason: "nack", commandId: "react_7_103", ts: 1 }} />,
  );
  expect(u.getByTestId("cihaz-onayi").props.children).toMatch(/REDDETTİ/);
  u.rerender(
    <CoilParameterPanel {...esp7} deviceAck={{ ok: null, reason: "timeout", commandId: "react_7_103", ts: 2 }} />,
  );
  expect(u.getByTestId("cihaz-onayi").props.children).toMatch(/onayı gelmedi/);
});

it("STM bobini (ack yayınlamaz) ve eski backend (command_id yok) → bekleme metni HİÇ çıkmaz", async () => {
  mockApiPost.mockResolvedValue({ status: "success", command_id: "stm_3_1" });
  const stm = await baslat({ coilId: 3, stm32Driven: true, stmConnected: true });
  expect(stm.queryByTestId("cihaz-onayi")).toBeNull();

  mockApiPost.mockResolvedValue({ status: "success" });
  const eski = await baslat();
  expect(eski.queryByTestId("cihaz-onayi")).toBeNull();
});

it("Durdur → bekleme durumu temizlenir", async () => {
  mockApiPost.mockResolvedValue({ status: "success", command_id: "react_7_104" });
  const u = await baslat();
  expect(u.getByTestId("cihaz-onayi")).toBeTruthy();
  mockApiPost.mockResolvedValue({ status: "success", command_id: "react_7_105" });
  fireEvent.press(u.getByLabelText("Bobini durdur"));
  await act(async () => {});
  expect(u.queryByTestId("cihaz-onayi")).toBeNull();
});
