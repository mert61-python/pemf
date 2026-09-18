// Author: mertaygn
/**
 * YOĞUNLUK ÇİPİ — REÇETE mi ÖLÇÜM mü, ETİKET SÖYLER  [sahip kararı 2026-09-11]
 * ========================================================================================
 * Sahip: "aktif seans kısmı var en üstte manuel modu başlatınca frekans var süre var yoğunluk
 * var ordaki yoğunluk değeri stm e bağlı olan SENSÖRDEN GELSİN".
 *
 * ⚠️ KARTTA İKİ FARKLI BÜYÜKLÜK YARIŞIYOR:
 *   · REÇETE (`intensityMt`)          — operatörün yazdığı sayı. Cihaza GÖNDERİLMEZ (STM/ESP
 *     paketi mT taşımaz), yalnız DB'ye girer. Denetim 2026-09-03'te (M3) operatörlerin bunu
 *     UYGULANAN doz sandığı ölçüldü; "(kayıt)" etiketi tam bu yanlış beklentiyi düzeltmek için var.
 *   · ÖLÇÜM (`measuredIntensityMt`)   — MLX90393'ün seans boyunca gördüğü TEPE |B|.
 *
 * SÖZLEŞME:
 *  1. Ölçüm VARSA gösterilen sayı ölçümdür ve etiket "(ölçülen)" olur.
 *  2. Ölçüm YOKSA (null) reçeteye düşülür ve etiket "(kayıt)" KALIR.
 *  3. ⚠️ Ölçüm yokken **0 mT gösterilmez**: "0 ölçtük" demek, ölçmediğimizi ölçtük demektir —
 *     bu deponun tekrarlayan arızası (PDF'e "0.0 °C ölçüldü" yazdıran desen).
 *
 * ⚠️ MUTASYON: `measuredIntensityMt != null ?` koşulunu `measuredIntensityMt != undefined ?`
 * (null geçer) ya da doğrudan ölçüm dalına sabitle → 2. ve 3. vaka KIRILIR.
 */
import React from "react";
import { render } from "@testing-library/react-native";

import { SessionProgressCard } from "../SessionProgressCard";

const temel = {
  isActive: true,
  mode: "manual" as const,
  elapsedSec: 60,
  remainingSec: 540,
  durationSec: 600,
  frequencyHz: 10,
  intensityMt: 1.5,
  onStop: () => {},
  onEmergencyStop: () => {},
};

describe("yoğunluk çipi — reçete / ölçüm ayrımı", () => {
  it("KRİTİK: ölçüm varsa SENSÖR değeri ve '(ölçülen)' etiketi gösterilir", () => {
    const u = render(<SessionProgressCard {...temel} measuredIntensityMt={7.253} />);
    expect(u.queryByText("YOĞUNLUK (ölçülen)")).toBeTruthy();
    expect(u.queryByText("7.25 mT")).toBeTruthy();
    // Reçete sayısı çipte GÖRÜNMEMELİ — iki sayı yan yana operatörü yanıltır.
    expect(u.queryByText("1.5 mT")).toBeNull();
  });

  it("KRİTİK: ölçüm YOKSA reçeteye düşülür ve etiket '(kayıt)' KALIR", () => {
    const u = render(<SessionProgressCard {...temel} measuredIntensityMt={null} />);
    expect(u.queryByText("YOĞUNLUK (kayıt)")).toBeTruthy();
    expect(u.queryByText("1.5 mT")).toBeTruthy();
    expect(u.queryByText("YOĞUNLUK (ölçülen)")).toBeNull();
  });

  it("KRİTİK: prop hiç verilmezse de '(kayıt)' — eski çağrı yerleri sessizce 'ölçüldü' demez", () => {
    const u = render(<SessionProgressCard {...temel} />);
    expect(u.queryByText("YOĞUNLUK (kayıt)")).toBeTruthy();
    expect(u.queryByText("YOĞUNLUK (ölçülen)")).toBeNull();
  });

  it("KARŞIT-KANIT: ölçülen 0 mT ise bu GERÇEK bir ölçümdür ve öyle gösterilir", () => {
    // ⚠️ `!= null` ile `!` arasındaki fark tam burada: `0` düşürücü bir değerdir. Gerçekten
    // 0 mT ölçüldüyse (bobin kapalı) bunu "ölçüm yok" sayıp reçeteyi göstermek YALAN olur —
    // operatör alan olmadığını göremez ve reçeteye bakıp "veriliyor" sanır.
    const u = render(<SessionProgressCard {...temel} measuredIntensityMt={0} />);
    expect(u.queryByText("YOĞUNLUK (ölçülen)")).toBeTruthy();
    expect(u.queryByText("0.00 mT")).toBeTruthy();
    expect(u.queryByText("1.5 mT")).toBeNull();
  });
});


// ============================================================================
// ANLIK vs SEANS TEPESI (sahip istegi 2026-09-11: "ANLIK yazdirmali")
// ============================================================================

test("KRITIK: ANLIK ile SEANS TEPESI AYRI rozetlerde gosterilir", () => {
  // ⚠️ Tek rozette birlestirmek operatoru yanıltır: tepe ASLA DUSMEZ, yani frekansi/
  // duty'yi/kipi degistirip etkisini gormek isteyen operator hicbir degisim goremezdi.
  // Sahip "anlik yazdirmali" derken tam olarak bunu istedi.
  //
  // MUTASYON: `measuredPeakMt` rozetini sil → KIRMIZI.
  const u = render(<SessionProgressCard {...temel} measuredIntensityMt={1.84} measuredPeakMt={3.26} />);
  expect(u.getByText("YOĞUNLUK (ölçülen)")).toBeTruthy();
  expect(u.getByText("1.84 mT")).toBeTruthy();
  expect(u.getByText("TEPE (seans)")).toBeTruthy();
  expect(u.getByText("3.26 mT")).toBeTruthy();
});

test("KRITIK: tepe YOKKEN rozet HIC cizilmez (0 gosterilmez)", () => {
  // "0.00 mT tepe" demek "olctuk, sifir cikti" demektir — olcmedigimiz halde.
  // MUTASYON: `measuredPeakMt != null &&` kapısını kaldır → KIRMIZI.
  const u = render(<SessionProgressCard {...temel} measuredIntensityMt={1.84} measuredPeakMt={null} />);
  expect(u.queryByText("TEPE (seans)")).toBeNull();
  expect(u.queryByText("0.00 mT")).toBeNull();
});

test("tepe 0.0 ise (gercekten olculmus sifir) rozet CIZILIR", () => {
  // Karsit kanit: kapı `null` ile `0`u ayirt etmeli, `!measuredPeakMt` ile degil.
  // MUTASYON: kapiyi `measuredPeakMt &&` yap → KIRMIZI.
  const u = render(<SessionProgressCard {...temel} measuredIntensityMt={0.5} measuredPeakMt={0} />);
  expect(u.getByText("TEPE (seans)")).toBeTruthy();
});
