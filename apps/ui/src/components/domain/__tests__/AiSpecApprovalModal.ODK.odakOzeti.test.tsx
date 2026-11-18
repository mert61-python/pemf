// Author: mertaygn, cglrgrkn
/**
 * ODK (istem 45 · Y273 / Y274) — AI Pro onay penceresi ODAK planını gösterir: seçilen DOZ ± konum payı, beklenen + TAVAN, çevre ortalaması
 * + oran (ya da düzgünlük), PETRİDE ZORUNLU 24 kuyu KÜÇÜK HARİTASI (kameradaki yön, seçili kuyu işaretli, her kuyuda mT, renk ölçeği +
 * "komşu kuyular da alan alır"), DOZ SEÇİCİ (üst sınır tavan) + petri kipi → "Yeniden hesapla". Eski "hedefte · çevrede · oran" satırı
 * (hoca modelinin birimsiz E'si) ODAK önerisinde GÖSTERİLMEZ. TR + EN. ⚠️ Beklenen metinler BURADA sabittir.
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { AiSpecApprovalModal } from "../AiSpecApprovalModal";
import { colors } from "@/theme/tokens";

import { dozCoz, kuyuKonumlari, kuyuRengi, sayi } from "../aipro/OdakOzeti";

const KUYULAR = Array.from({ length: 24 }, (_, i) => ({
  etiket: `${"ABCD"[Math.floor(i / 6)]}${(i % 6) + 1}`,
  px: [100 + 40 * (i % 6), 60 + 40 * Math.floor(i / 6)],
  mT: 0.5 + 0.01 * i,
  secili: i === 8,
}));

const ODAK = {
  kip: "KUYUCUK",
  doz_mT: 0.6,
  beklenen_mT: 0.61,
  tavan_mT: 1.25,
  cevre_mT: 0.48,
  oran: 1.27,
  pay_yuzde: 7.4,
  sapma_yuzde: 1.2,
  kuyular: KUYULAR,
};

const SPECS = {
  organ_id: 9,
  duration_minutes: 5,
  coil_ids: [1, 2, 3, 4, 5, 6, 7],
  D: [0.2, 0.1, 0.3, 0, 0, 0.1, 0.2],
  P: [108, 0, 36, 0, 0, 72, 180],
  e_field: 0,
  model: "petri",
  target_label: "Kuyu B3",
  e_cancer: 0.9,
  e_healthy: 0.1,
};
const bos = () => {};

function ac(odak?: Record<string, unknown>, onYenidenHesapla?: (d: number, k: string) => void) {
  return render(
    <AiSpecApprovalModal
      visible
      specs={{ ...SPECS, ...(odak ? { odak } : {}) } as never}
      meta={{ reliability: 0.9, method: "aruco_pnp" }}
      onApprove={bos}
      onReject={bos}
      onDismiss={bos}
      onYenidenHesapla={onYenidenHesapla}
    />,
  );
}

function metin(u: ReturnType<typeof render>): string {
  return JSON.stringify(u.toJSON());
}

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK ODK: ODAK önerisinde doz ± pay, beklenen + tavan, çevre + oran; eski 'hedefte · çevrede' satırı YOK", () => {
  const u = ac(ODAK);
  const m = metin(u);
  expect(m).toContain("Doz: 0,60 mT (± %7 konum payı)");
  expect(m).toContain("Beklenen (fizik denetimi): 0,61 mT · tavan 1,25 mT");
  expect(m).toContain("Çevre ortalaması 0,48 mT · oran 1,3×");
  expect(m).toContain("Faz / duty: ODAK modeli");
  expect(m).not.toContain("Tahmini alan (göreli, birimsiz)");
});

it("KRİTİK ODK: petride 24 kuyu HARİTASI — her kuyuda mT, seçili kuyu TEK ve işaretli, renk ölçeği + komşu uyarısı", () => {
  const u = ac(ODAK);
  expect(u.getByTestId("odak-kuyu-haritasi")).toBeTruthy();
  expect(u.getAllByTestId("odak-kuyu-secili")).toHaveLength(1);
  expect(u.getByTestId("odak-kuyu-secili").props.accessibilityLabel).toBe("B3: 0,58 mT (seçili kuyu)");
  expect(u.getByTestId("odak-kuyu-A1").props.accessibilityLabel).toBe("A1: 0,50 mT");
  const digerleri = KUYULAR.filter((k) => !k.secili).map((k) => u.getByTestId(`odak-kuyu-${k.etiket}`));
  expect(digerleri).toHaveLength(23);
  const m = metin(u);
  expect(m).toContain("24 kuyu — beklenen tepe alan (mT), plaka kameradaki yönüyle");
  expect(m).toContain("Renk: 0,50 – 0,73 mT (mavi düşük, kırmızı yüksek)");
  expect(m).toContain("Komşu kuyular da alan alır — bu bobinlerle tek kuyu ayrılamaz.");
});

it("KRİTİK ODK: İngilizce ekranda aynı bilgiler İngilizce", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  const m = metin(ac(ODAK));
  expect(m).toContain("Dose: 0.60 mT (± 7% position margin)");
  expect(m).toContain("Expected (physics check): 0.61 mT · ceiling 1.25 mT");
  expect(m).toContain("Neighbouring wells also receive field");
  expect(m).toContain("24 wells — expected peak field (mT), plate as seen by the camera");
});

it("KRİTİK ODK: doz seçici — geçerli doz + TÜM PETRİ ile yeniden hesap ister; tavan üstü doz düğmeyi KAPATIR ve söyler", () => {
  const cagri: [number, string][] = [];
  const u = ac(ODAK, (d, k) => cagri.push([d, k]));
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0,5");
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  fireEvent.press(u.getByTestId("odak-yeniden-hesapla"));
  expect(cagri).toEqual([[0.5, "TUM_PETRI"]]);
  // ODD B-2: tavan YALNIZ hesaplandığı kipte denetlenir (TÜM PETRİ'nin tavanı yeniden hesaplanınca gelir) → tavan üstü red aynı kipte.
  fireEvent.press(u.getByTestId("odak-kip-KUYUCUK"));
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "9");
  expect(u.getByTestId("odak-yeniden-hesapla").props.accessibilityState.disabled).toBe(true);
  expect(metin(u)).toContain("0'dan büyük ve en çok 1,25 mT bir doz girin.");
  fireEvent.press(u.getByTestId("odak-yeniden-hesapla"));
  expect(cagri).toHaveLength(1);
});

it("KARŞIT ODK: düzgünlük kipinde (TÜM PETRİ) çevre yerine düzgünlük; fantomda kip seçici YOK; haritasız; işleyici yoksa seçici YOK", () => {
  const u = ac({ ...ODAK, kip: "TUM_PETRI", cevre_mT: null, oran: 0.91, kuyular: KUYULAR.map((k) => ({ ...k, secili: false })) }, bos);
  expect(metin(u)).toContain("Düzgünlük (en zayıf / en güçlü): 0,91");
  expect(u.queryAllByTestId("odak-kuyu-secili")).toHaveLength(0);
  const f = ac({ kip: "FANTOM", doz_mT: 0.4, beklenen_mT: 0.4, tavan_mT: 1.1, cevre_mT: 0.2, oran: 2, pay_yuzde: 5 }, bos);
  expect(f.queryByTestId("odak-kip-TUM_PETRI")).toBeNull();
  expect(f.queryByTestId("odak-kuyu-haritasi")).toBeNull();
  expect(ac(ODAK).queryByTestId("odak-doz-girdi")).toBeNull();
});

it("KARŞIT ODK: ODAK alanı olmayan (eski) öneride eski göreli alan satırı KALIR, ODAK özeti YOK", () => {
  const u = ac(undefined);
  expect(u.queryByTestId("odak-ozeti")).toBeNull();
  expect(metin(u)).toContain("Tahmini alan (göreli, birimsiz)");
});

it("YAPISAL ODK: harita KAMERADAKİ yönü korur; px yoksa etiketten ızgara; renk ve sayı yardımcıları", () => {
  const ters = KUYULAR.map((k) => ({ ...k, px: [1000 - k.px[0], 1000 - k.px[1]] }));
  const a = kuyuKonumlari(KUYULAR);
  const b = kuyuKonumlari(ters);
  expect(a[0]).toEqual({ x: 0, y: 0 });
  expect(b[0]).toEqual({ x: 1, y: 1 }); // plaka kamerada 180° dönükse A1 sağ altta
  const c = kuyuKonumlari(KUYULAR.map((k) => ({ ...k, px: null })));
  expect(c[0]).toEqual({ x: 0, y: 0 });
  expect(c[23]).toEqual({ x: 1, y: 1 });
  expect(kuyuKonumlari([{ etiket: "W1", px: null, mT: 1 }])[0]).toEqual({ x: 0.5, y: 0.5 });
  expect(kuyuKonumlari([{ etiket: "A1", px: [5, 5], mT: 1 }])[0]).toEqual({ x: 0.5, y: 0.5 });
  expect(kuyuRengi(0, 0, 1)).toBe("#2563eb");
  expect(kuyuRengi(1, 0, 1)).toBe("#dc2626");
  expect(kuyuRengi(1, 1, 1)).toBe("#dc2626");
  expect(kuyuRengi(null, 0, 1)).toBe(colors.bgAlt);
  expect(dozCoz("1,25")).toBe(1.25);
  expect(dozCoz(" 2.5 ")).toBe(2.5);
  expect(Number.isNaN(dozCoz("abc"))).toBe(true);
  expect(sayi(null)).toBe("—");
});
