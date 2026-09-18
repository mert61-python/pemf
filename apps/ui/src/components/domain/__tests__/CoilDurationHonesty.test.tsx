// Author: mertaygn, cglrgrkn
/**
 * SÜRE UYARISI DÜRÜSTLÜĞÜ (2026-08-17 denetimi).
 *
 * ÖLÇÜLEN DURUM: bu panel 8 bobinin HEPSİNİ sürer (`ControlScreen` onu STM 1-5 ve ESP 6-8
 * bölümlerinde ayrı ayrı render eder). Süre boş/0 bırakıldığında operatöre şu yazılıyordu:
 *
 *     "Süre girilmedi — bobin donanım üst-sınırına kadar çalışır; süre belirtmeniz önerilir."
 *
 * ve yanındaki yorum "donanım watchdog'u DURATION_MAX'a kaplar (kontrolsüz kalmaz)" diyordu.
 *
 * İKİ AÇIDAN DAYANAKSIZDI:
 *   1. `DURATION_MAX_MINUTES` (9999 dk ≈ 6,9 gün) bir KLİNİK sınır değil, **STM32 protokol
 *      sabitidir** ve firmware paritesiyle kilitlidir. Gerçek klinik kapak 120 dk'dır.
 *   2. ESP bobinleri (6-8) için "donanım üst-sınırı" iddiasının dayanağı bu depoda YOK — ESP
 *      firmware'i (`CoilController.cpp`) burada değil (`firmware/README.md`).
 *
 * Yanlış güvence, korumasızlıktan tehlikelidir (aynı gerekçe: `CoilThermalHonesty.test.tsx`).
 * Bu testler uyarının VARLIĞINI korur ama **donanıma dayanan** iddiayı yasaklar. Gerçek kapağı
 * sunucu uygular (`servers/api_server.py::_esp_duration_seconds` + `HardwareController`); bkz.
 * `tests/test_esp_gozetimsiz_sure_kapagi.py`.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => ({ status: "success" })) }));

import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const temel = {
  coilId: 6,
  connected: true,
  running: false,
  objectTemp: 30,
  frequencyHz: 50,
  dutyCycle: 25,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: false,
  stmConnected: false,
  defaultDuration: 0, // "süre girilmedi"
};

const ciz = (ek: Partial<typeof temel> = {}) =>
  render(<CoilParameterPanel {...temel} {...ek} />);

async function baslatVeUyariyiAl(ek: Partial<typeof temel> = {}) {
  const u = ciz(ek);
  fireEvent.press(u.getByLabelText("Bobini başlat"));
  // Uyarı `setError` ile senkron yazılıyor ama sendCommand async; render'ı bekle.
  await waitFor(() => expect(u.queryByText(/Süre girilmedi/)).not.toBeNull());
  return u.getByText(/Süre girilmedi/).props.children as string;
}

it("KRİTİK: süre girilmediğinde operatör AÇIKÇA uyarılır (sessiz süresiz-seans olmaz)", async () => {
  const metin = await baslatVeUyariyiAl();
  expect(metin).toMatch(/Süre girilmedi/);
});

it("KRİTİK: uyarı 'donanım' üst-sınırına dayanan bir GÜVENCE VERMEZ", async () => {
  const metin = await baslatVeUyariyiAl();
  // ESP (6-8) için firmware bu depoda yok; STM (1-5) için de gerçek kapak protokol tavanı DEĞİL.
  expect(metin).not.toMatch(/donanım/i);
  expect(metin).not.toMatch(/üst-sınır/i);
});

it("uyarı, sınırın SUNUCU tarafında uygulandığını söyler (nerede olduğu belli olsun)", async () => {
  const metin = await baslatVeUyariyiAl();
  expect(metin).toMatch(/sunucu/i);
});

it("karşı-kanıt: süre VERİLDİĞİNDE bu uyarı hiç çıkmaz", async () => {
  const u = ciz({ defaultDuration: 20 });
  fireEvent.press(u.getByLabelText("Bobini başlat"));
  await waitFor(() => expect(u.queryByText(/Süre girilmedi/)).toBeNull());
});

it("karşı-kanıt: STM bobininde (1-5) de aynı dürüst metin kullanılır", async () => {
  const metin = await baslatVeUyariyiAl({ coilId: 2, stm32Driven: true, stmConnected: true });
  expect(metin).toMatch(/Süre girilmedi/);
  expect(metin).not.toMatch(/donanım/i);
});
