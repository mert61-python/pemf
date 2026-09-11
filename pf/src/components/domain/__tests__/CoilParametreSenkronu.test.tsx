// Author: mertaygn
/**
 * "TOPLU UYGULAMA" DEĞERLERİ BOBİN PANELLERİNE GEÇMİYORDU — 2026-09-11 saha arızası.
 *
 * Sahip: "76 Hz, %50 duty, 0 faz, 30 dk ile başlattım; başlatınca kutu değerleri default'a
 * dönüyor (100 Hz, %25, 0 faz, 20 dk)."
 *
 * KÖK NEDEN: panel `useState(String(defaultFreq))` ile başlangıç değerini YALNIZ İLK
 * MOUNT'ta okuyordu. Operatör master alanları değiştirince prop güncelleniyor ama panel
 * state'i ekran ilk açıldığındaki değerde donuyordu.
 *
 * ⚠️ KOZMETİK DEĞİL, DOZ HATASI: toplu başlatma master değerlerini DOĞRU gönderiyor, ama
 * operatör panelde başka bir sayı GÖRÜYOR; o panelin kendi düğmesine basarsa bobin
 * GÖRDÜĞÜ değerle değil, donmuş eski değerle sürülür.
 */
const mockApiPost = jest.fn(async () => ({ status: "success" }));
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => mockApiPost(...(a as [])),
  platformConfirm: async () => true,
  platformAlert: () => {},
}));
jest.mock("@/services/therapyLimits", () => ({ clampTherapyParams: (p: unknown) => ({ values: p, warnings: [] }) }));

import { render, fireEvent } from "@testing-library/react-native";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";

const temel = {
  coilId: 1,
  connected: true,
  running: false,
  objectTemp: 0,
  frequencyHz: 0,
  dutyCycle: 0,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
  measuredFields: [] as string[],
  defaultFreq: 100,
  defaultDuty: 25,
  defaultPhase: 0,
  defaultDuration: 20,
};

const deger = (u: ReturnType<typeof render>, etiket: string) =>
  (u.getByLabelText(etiket).props as { value?: string }).value;

beforeEach(() => mockApiPost.mockClear());

test("KRITIK: master degeri DEGISINCE panel TAKIP EDER", () => {
  // ⚠️ ASIL KAPI. MUTASYON: `useEffect` senkron bloğunu sil → KIRMIZI
  // (panel 100/25/20'de donar, saha arızası geri gelir).
  const u = render(<CoilParameterPanel {...temel} />);
  expect(deger(u, "Frekans (Hz)")).toBe("100");

  u.rerender(<CoilParameterPanel {...temel} defaultFreq={76} defaultDuty={50} defaultDuration={30} />);

  expect(deger(u, "Frekans (Hz)")).toBe("76");
  expect(deger(u, "Duty (%)")).toBe("50");
  expect(deger(u, "Süre (dk)")).toBe("30");
});

test("KRITIK: panele GONDERILEN komut da yeni degeri tasir", () => {
  // Görünen sayı ile GİDEN sayı ayrı şeyler — ikisi de ölçülür, yoksa panel doğru
  // gösterip eski değeri gönderebilirdi.
  const u = render(<CoilParameterPanel {...temel} />);
  u.rerender(<CoilParameterPanel {...temel} defaultFreq={76} defaultDuty={50} defaultDuration={30} />);
  fireEvent.press(u.getByText("▶ Başlat"));

  const [, govde] = mockApiPost.mock.calls[0] as unknown as [string, { freq: number; duty: number }];
  expect(govde.freq).toBe(76);
  expect(govde.duty).toBe(50);
});

test("KRITIK: DEGISMEYEN master alani, bobine ozel degeri EZMEZ", () => {
  // Operatör bobin 3'e özel 200 Hz girdiyse, master'ın DUTY'sini değiştirmek o bobinin
  // FREKANSINI geri almamalı.
  // MUTASYON: alan başına `sonMaster` karşılaştırmasını kaldırıp her render'da hepsini
  // yaz → KIRMIZI.
  const u = render(<CoilParameterPanel {...temel} />);
  fireEvent.changeText(u.getByLabelText("Frekans (Hz)"), "200");
  expect(deger(u, "Frekans (Hz)")).toBe("200");

  u.rerender(<CoilParameterPanel {...temel} defaultDuty={50} />);

  expect(deger(u, "Duty (%)")).toBe("50");   // değişen alan güncellendi
  expect(deger(u, "Frekans (Hz)")).toBe("200"); // ⚠️ değişmeyen alan KORUNDU
});

test("KRITIK: calisan bobinde dugme UYGULA der (Baslat degil)", () => {
  // Sahip: "parametre güncelle butonu lazım". Firmware çalışan bobinde parametreyi
  // kesintisiz günceller — düğme zaten bunu yapıyordu ama "Başlat" yazdığı için
  // operatör "tedaviyi baştan mı alır?" diye basmıyordu.
  //
  // MUTASYON: etiketi sabit "▶ Başlat" yap → KIRMIZI.
  const u = render(<CoilParameterPanel {...temel} running />);
  expect(u.getByText("🔄 Uygula")).toBeTruthy();
  expect(u.queryByText("▶ Başlat")).toBeNull();
  expect(u.getByLabelText("Bobinin parametrelerini güncelle")).toBeTruthy();
});

test("durmus bobinde etiket BASLAT kalir", () => {
  const u = render(<CoilParameterPanel {...temel} running={false} />);
  expect(u.getByText("▶ Başlat")).toBeTruthy();
});
