// Author: mertaygn, cglrgrkn
/**
 * TERMAL KORUMA DÜRÜSTLÜĞÜ (2026-08-09 denetimi, Tier 2).
 *
 * ÖLÇÜLEN DURUM:
 *   Bobin 1-5 → STM32 binary paketiyle sürülür; protokolde SICAKLIK ALANI YOKTUR, STM sıcaklık
 *               yayınlamaz → `objectTemp` hiçbir zaman gelmez (`live_state` varsayılanı 0.0).
 *   Bobin 6-8 → ESP32/MQTT `pemf/coil/<id>/sensors` → `object_temp` gelir.
 *
 * Tek termal kesme mantığı BU BİLEŞENDEDİR (`objectTemp > SAFE_TEMP_CUTOFF`). Yani 8 bobinin
 * 5'i hastanın üzerinde HİÇBİR sıcaklık koruması olmadan enerjilenir.
 *
 * ARIZA: sıcaklık yokken rozet HİÇ ÇİZİLMİYORDU → operatör bunu "sorun yok" diye okuyabiliyordu
 * ve firmware/README de "termal koruma sensör/ESP tarafındadır" diyerek yanlış güvence veriyordu.
 * Yanlış güvence, korumasızlıktan tehlikelidir: koruma var sanılınca donanım önlemi ertelenir.
 *
 * ⚠️ Bu testler korumayı EKLEMEZ (gerçek çözüm donanımdadır: 1-5 için sensör + STM telemetrisi +
 * firmware kesmesi). Sınırın GÖRÜNÜR kalmasını kilitler.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => ({ status: "success" })) }));
jest.mock("@/services/therapyLimits", () => ({
  clampTherapyParams: (p: unknown) => p,
}));

import { render } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const temel = {
  coilId: 3,
  connected: true,
  running: true,
  objectTemp: 0,
  frequencyHz: 50,
  dutyCycle: 25,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
};

const ciz = (ek: Partial<typeof temel> = {}) =>
  render(<CoilParameterPanel {...temel} {...ek} />);

it("KRİTİK: ölçüm yoksa 'ölçüm yok' AÇIKÇA yazar (sessiz boşluk bırakmaz)", () => {
  const u = ciz({ objectTemp: 0 });
  expect(u.getByText("ölçüm yok")).toBeTruthy();
});

it("KRİTİK: ölçüm yokken ekran-okuyucu 'termal durdurma uygulanmaz' der", () => {
  const u = ciz({ objectTemp: 0 });
  expect(u.getByLabelText(/sıcaklık ölçümü yok.*termal durdurma uygulanmaz/i)).toBeTruthy();
});

it("KRİTİK: ölçüm yokken SAHTE bir sıcaklık değeri gösterilmez", () => {
  // Eski davranışta rozet hiç çizilmiyordu; yeni davranışta "0.0°C" gibi güven veren bir
  // sayı GÖSTERİLMEMELİ — 0 °C "serin" diye okunur.
  const u = ciz({ objectTemp: 0 });
  expect(u.queryByText(/0\.0°C/)).toBeNull();
});

it("ölçüm VARSA sıcaklık normal gösterilir", () => {
  const u = ciz({ coilId: 7, stm32Driven: false, objectTemp: 38.4 });
  expect(u.getByText("38.4°C")).toBeTruthy();
  expect(u.queryByText("ölçüm yok")).toBeNull();
});

it("yüksek sıcaklık uyarısı YALNIZ-RENK değil (⚠ + metin)", () => {
  const u = ciz({ coilId: 7, stm32Driven: false, objectTemp: 46.2 });
  expect(u.getByText(/⚠ 46\.2°C/)).toBeTruthy();
});

/**
 * ⚠️ EN ÖNEMLİ KAPI: interlock'un kapsamı. Bu test korumanın 1-5 için ÇALIŞMADIĞINI
 * belgeler — düzeltilmiş sanılıp donanım önlemi ertelenmesin diye.
 */
it("BELGELENMİŞ SINIR: sıcaklık gelmeyen bobinde interlock tetiklenemez", () => {
  const { apiPost } = require("@/services/apiClient");
  (apiPost as jest.Mock).mockClear();
  ciz({ objectTemp: 0, running: true });     // STM bobini, ölçüm yok
  // Interlock `objectTemp > 48` ile çalışır; 0 asla geçmez → durdurma komutu GİTMEZ.
  expect(apiPost).not.toHaveBeenCalled();
});
