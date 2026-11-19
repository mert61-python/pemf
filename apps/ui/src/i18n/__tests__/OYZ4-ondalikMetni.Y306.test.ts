// Author: mertaygn, cglrgrkn
/**
 * Y306 (sahip 19-11, OTB [SAHİBE] 2 + tezgâh denemesi 4b): ekrandaki ondalık sayı ETKİN DİLİN biçiminde — TEK yardımcı `ondalikMetni`:
 * tr → virgül ("1,32"), en → nokta ("1.32"); binlik ayırıcı yok; sabit basamak ya da anlamlı basamak. Canlı karttaki ölçülen alan ve
 * ODAK dozu (`canliYogunluk`) bu yardımcıdan geçer.
 */
import { act } from "@testing-library/react-native";
import { __bayrakTestiAyarla, ondalikMetni } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { canliYogunluk } from "@/utils/yogunlukGosterimi";

const depo = { setItem: async () => undefined };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function dil(d: "tr" | "en") {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec(d, depo);
  });
}

it("KRİTİK: TR virgül, EN nokta; sabit basamak; binlik ayırıcı YOK", async () => {
  await dil("tr");
  expect(ondalikMetni(14.4, 2)).toBe("14,40");
  expect(ondalikMetni(1.3, 1)).toBe("1,3");
  expect(ondalikMetni(1234.5, 1)).toBe("1234,5");
  await dil("en");
  expect(ondalikMetni(14.4, 2)).toBe("14.40");
  expect(ondalikMetni(1234.5, 1)).toBe("1234.5");
});

it("anlamlı basamak (çok küçük değer) dile göre", async () => {
  await dil("tr");
  expect(ondalikMetni(0.000123456, { anlamli: 3 })).toBe("0,000123");
  await dil("en");
  expect(ondalikMetni(0.000123456, { anlamli: 3 })).toBe("0.000123");
});

it("KRİTİK canlı kart: ölçülen alan ve ODAK dozu dile göre ondalık", async () => {
  await dil("tr");
  expect(canliYogunluk({ measuredIntensityMt: 1.324 }).deger).toBe("1,32 mT");
  expect(canliYogunluk({ odakDozMt: 0.6, odakBobinSayisi: 7 }).deger).toBe("0,60 mT · 7 bobin");
  await dil("en");
  expect(canliYogunluk({ measuredIntensityMt: 1.324 }).deger).toBe("1.32 mT");
  expect(canliYogunluk({ odakDozMt: 0.6, odakBobinSayisi: 7 }).deger).toBe("0.60 mT · 7 coils");
});
