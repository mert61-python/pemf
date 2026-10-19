/**
 * I18N-0 · T9 DOZ GÜVENLİĞİ KİLİDİ: sayı GİRİŞİNİN ayrıştırması dil değişince DEĞİŞMEZ.
 *
 * Gösterim biçimi dile göre değişebilir (`Intl`, tr-TR / en-GB) ama operatörün yazdığı frekans / görev oranı / faz / süre metni
 * kartın aldığı sayıya HER DİLDE aynı çözülmeli. Tehlike örneği: İngilizce yerel ayarla `Intl.NumberFormat` tabanlı bir ayrıştırıcıya
 * geçilseydi "12,5" binlik ayracı sayılıp 125 Hz giderdi. Bu test aynı girdiyi TR ve EN arayüzde girer ve sunucuya giden YÜKÜN
 * birebir aynı olduğunu iddia eder (bugünkü davranış neyse o — "12,5" bu panelde 12'ye çözülür; değişiklik bu turun işi DEĞİL).
 * Öğeler dilden bağımsız bulunur (giriş sırası + erişilebilirlik etiketinin TR | EN biçimi) — göç partisi etiketleri çevirince de koşar.
 */
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(async () => ({ status: "success" })) }));

import { act, fireEvent, render } from "@testing-library/react-native";
import { TextInput } from "react-native";
import i18n from "i18next";
import { apiPost } from "@/services/apiClient";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";
import { __bayrakTestiAyarla } from "@/i18n/dil";

const temel = {
  coilId: 2,
  connected: true,
  running: false,
  objectTemp: 30,
  frequencyHz: 50,
  dutyCycle: 25,
  magneticMt: 0,
  currentA: 0,
  stm32Driven: true,
  stmConnected: true,
  defaultDuration: 20,
};

const BASLAT = /^(Bobini başlat|Start coil)$/i;

async function gonderilenYuk(dil: "tr" | "en", girdi: [string, string, string, string]) {
  (apiPost as jest.Mock).mockClear();
  await act(async () => {
    await i18n.changeLanguage(dil);
  });
  const u = render(<CoilParameterPanel {...temel} />);
  const alanlar = u.UNSAFE_getAllByType(TextInput);
  expect(alanlar.length).toBeGreaterThanOrEqual(4);
  girdi.forEach((v, i) => fireEvent.changeText(alanlar[i], v));
  await act(async () => {
    fireEvent.press(u.getByLabelText(BASLAT));
  });
  const cagri = (apiPost as jest.Mock).mock.calls.find((c) => String(c[0]).includes("/control"));
  expect(cagri).toBeTruthy();
  u.unmount();
  return cagri![1];
}

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it.each([
  [["12,5", "30,5", "0", "15"]],
  [["12.5", "30.5", "90", "15"]],
  [["7", "50", "0", "10"]],
] as [[string, string, string, string]][])("aynı girdi %j TR ve EN arayüzde AYNI yükü gönderir", async (girdi) => {
  __bayrakTestiAyarla(true);
  const tr = await gonderilenYuk("tr", girdi);
  const en = await gonderilenYuk("en", girdi);
  expect(en).toEqual(tr);
});
