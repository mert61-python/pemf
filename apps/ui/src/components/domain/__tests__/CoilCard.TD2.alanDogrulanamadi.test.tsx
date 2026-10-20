// Author: mertaygn, cglrgrkn
/**
 * TD2 (tezgâh Oturum 13 · K6) — kazanç ayarı doğrulanamayan alan sensörünün değeri GÖSTERİLMEZ.
 * =================================================================================================
 * ÖLÇÜLEN KUSUR: MLX90393 kazancı uygulanmadığında her okuma ~5× büyüktü (Dünya alanı 4–5×, bobin |pp| 13,3 mT ≈ gerçekte
 * 2,7–3,3) ve "Alan" kutusu bunu sessizce gösteriyordu. Backend artık işaretsiz `B=`'yi yazmaz ve bobine
 * `alanDogrulanamadi: true` koyar (tests/test_TD2_alan_dogrulanmadan_GOSTERILMEZ_KAYDEDILMEZ.py).
 * SÖZLEŞME: bayrak varken değer "—" ve kısa neden ("sensör doğrulanamadı"); `measuredFields` alanı içerse BİLE (geçiş anı)
 * sayı görünmez. Bayrak yokken ölçülen değer olduğu gibi görünür.
 * ⚠️ MUTASYON: CoilCard'daki `!coil.alanDogrulanamadi` koşulu ya da `alt` satırı kaldırılırsa KIRMIZI.
 */
import { render } from "@testing-library/react-native";
import { CoilCard } from "@/components/domain/CoilCard";
import { alanDogrulanamadiMetni } from "@/utils/olculenAlan";
import { CoilStatus } from "@/types/domain";

const temel: CoilStatus = {
  id: 6,
  connected: true,
  running: true,
  frequencyHz: 10,
  dutyCycle: 50,
  magneticMt: 13.3,
  objectTemp: 0,
  ambientTemp: 0,
  currentA: 0,
  stm32Driven: true,
  measuredFields: ["magneticMt"],
};

describe("TD2 — CoilCard: doğrulanmamış alan gösterilmez", () => {
  it("KRİTİK: bayrak varken değer kısa çizgi ve neden yazılır (measuredFields içerse bile)", () => {
    const { getByText, queryByText } = render(<CoilCard coil={{ ...temel, alanDogrulanamadi: true }} />);
    expect(queryByText("13.30 mT")).toBeNull();
    expect(queryByText(/mT$/)).toBeNull();
    expect(getByText("sensör doğrulanamadı")).toBeTruthy();
  });

  it("KARŞIT: doğrulanmış ölçüm olduğu gibi görünür, neden satırı yok", () => {
    const { getByText, queryByText } = render(<CoilCard coil={{ ...temel, alanDogrulanamadi: false }} />);
    expect(getByText("13.30 mT")).toBeTruthy();
    expect(queryByText("sensör doğrulanamadı")).toBeNull();
  });

  it("metin üç ekranda AYNI kaynaktan", () => {
    expect(alanDogrulanamadiMetni()).toBe("Alan sensörü doğrulanamadı — ölçülen değer gösterilmiyor");
  });
});
