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
  // ⚠️ Varsayilan BOS: hicbir alan olculmemis → panel kisa cizgi gosterir. Testler
  // olcumu ACIKCA vererek (`measuredFields: ["objectTemp"]`) "olculuyor" halini kurar.
  measuredFields: [] as string[],
};

const ciz = (ek: Partial<typeof temel> = {}) =>
  render(<CoilParameterPanel {...temel} {...ek} />);

/**
 * ⚠️ SÖZLEŞME DEĞİŞTİ (2026-09-10, sahip isteği): "ölçüm yok" metni yerine KISA ÇİZGİ (—).
 * İddia AYNI KALDI: ölçüm olmayan yerde SESSİZ BOŞLUK ya da güven veren bir SAYI olmaz.
 *
 * ⚠️ İKİNCİ VE DAHA ÖNEMLİ DEĞİŞİKLİK — ÖLÇÜM KAYNAĞI: eskiden "ölçülüyor mu" sorusu
 * `objectTemp > 0` ile yanıtlanıyordu. O kural iki yönden yanlıştı:
 *   (a) GERÇEK 0.0 °C ölçümü (soğuk oda / buz paketi) "ölçüm yok" görünüyordu,
 *   (b) bobin 1-5'e ACS712 eklenince akım için de aynı soruya cevap gerekti ve
 *       duran bir bobinin GERÇEK 0.000 A ölçümü "yok" sayılırdı.
 * Artık kaynak backend'in GELEN telemetriden türettiği `measuredFields` — bobin
 * numarasından TAHMİN edilmez, topoloji değişince arayüz kendiliğinden doğru kalır.
 */
it("KRİTİK: ölçüm yoksa KISA ÇİZGİ yazar (sessiz boşluk bırakmaz)", () => {
  const u = ciz({ objectTemp: 0 });
  // ⚠️ getAllByText: panelde artik BIRDEN COK kisa cizgi var (sicaklik + mT + A) —
  // "olculmeyen her alan cizgi" kuralinin dogal sonucu. getByText coklu eslesmede PATLAR.
  expect(u.getAllByText("-").length).toBeGreaterThanOrEqual(1);
});

it("KRİTİK: DEĞER gelse bile measuredFields yoksa ölçüm SAYILMAZ", () => {
  // Sahte/bayat bir sayı paneli "ölçüyorum" göstermeye ikna edemez.
  const u = ciz({ objectTemp: 38.4 });   // measuredFields YOK
  expect(u.queryByText("38.4°C")).toBeNull();
  expect(u.getAllByText("-").length).toBeGreaterThanOrEqual(1);
});

it("KRİTİK: GERÇEK 0.0 °C ölçümü 'yok' SAYILMAZ (eski kuralın hatası)", () => {
  const u = ciz({ objectTemp: 0, measuredFields: ["objectTemp"] });
  expect(u.getByText("0.0°C")).toBeTruthy();
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
  const u = ciz({ coilId: 7, stm32Driven: false, objectTemp: 38.4, measuredFields: ["objectTemp"] });
  expect(u.getByText("38.4°C")).toBeTruthy();
  expect(u.queryByText("ölçüm yok")).toBeNull();
});

it("KRİTİK: bobin 1-5 AKIM ölçer, sıcaklık/alan KISA ÇİZGİ", () => {
  // Sahip kararı 2026-09-10: bobin 1-5'e ACS712-30A bağlanıyor, MLX sensörü YOK.
  const u = ciz({ coilId: 2, objectTemp: 0, magneticMt: 0, currentA: 0.412, measuredFields: ["currentA"] });
  expect(u.getByText("0.412")).toBeTruthy();   // akım GÖSTERİLİR
  expect(u.getAllByText("-").length).toBeGreaterThanOrEqual(2);  // sıcaklık + mT
});

it("yüksek sıcaklık uyarısı YALNIZ-RENK değil (⚠ + metin)", () => {
  const u = ciz({ coilId: 7, stm32Driven: false, objectTemp: 46.2, measuredFields: ["objectTemp"] });
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
