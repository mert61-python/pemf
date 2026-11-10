/**
 * KD · Y260 (istem 44 §2) — Kabin kalibrasyonu ekranı: kare al → 4 köşeye sırayla dokun (1 px ince ayar) → köşe başına sol / ön cm +
 * lens (3 değer) → Hesapla → sonuç (izdüşüm px, hesaplanan ↔ ölçülen lens, kuyu aralığı) → Kaydet (lens farkı > 2 cm AÇIK onay ister) ·
 * Doğrula (2 köşe → fark cm) · fantom kalınlığı / tümör derinliği. Kurallar ve nedenler SUNUCUDAN (arayüz uydurmaz). TR + EN.
 * Sahte yalnız ağ sınırında (`apiGet` / `apiPost`).
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockGet(...a),
  apiPost: (...a: unknown[]) => mockPost(...a),
  KAMERA_TIMEOUT_MS: 120000,
  AI_TIMEOUT_MS: 120000,
}));
const mockGet = jest.fn();
const mockPost = jest.fn();

import { KabinKalibrasyonuKarti } from "@/components/domain/KabinKalibrasyonuKarti";
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";

const KARE = { kareKimligi: "k1", genislik: 1920, yukseklik: 1080, image_base64: "QUJD" };
const SONUC = {
  gecerli: true,
  nedenler: [],
  izdusumHatasiPx: 0.61,
  hesaplananLensCm: [2.7, 19.5, -12.2],
  olculenLensCm: [2.75, 19.5, -12.25],
  lensFarkiCm: 0.08,
  lensUyarisi: false,
  kuyuAraligi: { sutunMm: 19.29, satirMm: 19.23, beklenenMm: 19.3, sapma: 0.0034, gecti: true },
  sahne: { oznitelik: 3000, denetim: true },
  esikler: { izdusumPx: 3, lensCm: 2 },
};
const GECERLI = { var: true, gecerli: true, tarih: "2026-11-10T15:00:00+0300", izdusumHatasiPx: 0.61, lensFarkiCm: 0.1, sahneDenetimi: true };

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ var: false, gecerli: false, hataMetni: "SUNUCU: kalibrasyon yok" });
  mockPost.mockReset();
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

async function dortKose(ekran: ReturnType<typeof render>) {
  // Gösterim 320 × 180 (onLayout yok → varsayılan) → kare pikseli ×6
  const noktalar = [
    [10, 20],
    [60, 21],
    [61, 50],
    [11, 49],
  ];
  for (let i = 0; i < 4; i++) {
    fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kare"), { nativeEvent: { locationX: noktalar[i][0], locationY: noktalar[i][1] } });
    fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-sol-${i}`), `${10 + i},5`);
    fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-on-${i}`), `${20 + i}`);
    if (i < 3) fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-sonraki"));
  }
}

it("KRİTİK: kalibrasyon yoksa SUNUCUNUN eylem metni görünür (arayüz uydurmaz)", async () => {
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  expect((await ekran.findByTestId("kabin-kalibrasyonu-durum")).props.children).toBe("SUNUCU: kalibrasyon yok");
  expect(mockGet).toHaveBeenCalledWith("/ai/pro/kalibrasyon", null, { silent: true });
});

it("KRİTİK: akış — kare (KAMERA süresi) → 4 dokunuş + ince ayar → Hesapla gövdesi → sonuç → Kaydet", async () => {
  mockPost.mockImplementation(async (yol: string) => {
    if (yol === "/ai/pro/kalibrasyon/kare") return KARE;
    if (yol === "/ai/pro/kalibrasyon/hesapla") return SONUC;
    if (yol === "/ai/pro/kalibrasyon/kaydet") return { durum: GECERLI };
    return null;
  });
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  expect(mockPost.mock.calls[0][0]).toBe("/ai/pro/kalibrasyon/kare");
  expect(mockPost.mock.calls[0][3].timeoutMs).toBe(120000);
  expect(ekran.getByTestId("kabin-kalibrasyonu-hesapla").props.accessibilityState?.disabled ?? true).toBeTruthy();
  await dortKose(ekran);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-ok-sag")); // 4. köşe +1 px
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-ok-asagi"));
  for (const [a, v] of [["sol", "25"], ["on", "8"], ["taban", "37"]]) fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-lens-${a}`), v);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-hesapla"));
  await ekran.findByTestId("kabin-kalibrasyonu-sonuc");
  const govde = mockPost.mock.calls.find((c) => c[0] === "/ai/pro/kalibrasyon/hesapla")![1];
  expect(govde.kareKimligi).toBe("k1");
  expect(govde.koseler).toEqual([
    { u: 60, v: 120, solCm: 10.5, onCm: 20 },
    { u: 360, v: 126, solCm: 11.5, onCm: 21 },
    { u: 366, v: 300, solCm: 12.5, onCm: 22 },
    { u: 67, v: 295, solCm: 13.5, onCm: 23 },
  ]);
  expect(govde.lens).toEqual({ solCm: 25, onCm: 8, tabanCm: 37 });
  expect(ekran.getByTestId("kabin-kalibrasyonu-izdusum").props.children).toBe(
    i18n.t("ai.kalibrasyon.sonuc.izdusum", { px: "0.61", esik: 3 })
  );
  expect(ekran.getByTestId("kabin-kalibrasyonu-kuyu").props.children).toMatch(/19\.29 \/ 19\.23 mm/);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kaydet"));
  await waitFor(() => expect(ekran.getByTestId("kabin-kalibrasyonu-mesaj").props.children).toBe(TR["ai.kalibrasyon.kaydedildi"]));
  expect(ekran.getByTestId("kabin-kalibrasyonu-durum").props.children).toMatch(/0\.61 px/);
});

it("KRİTİK: lens farkı > 2 cm → Kaydet ONAYSIZ kapalı; onay gövdeye yazılır", async () => {
  mockPost.mockImplementation(async (yol: string) =>
    yol === "/ai/pro/kalibrasyon/kare"
      ? KARE
      : yol === "/ai/pro/kalibrasyon/hesapla"
        ? { ...SONUC, lensFarkiCm: 3.1, lensUyarisi: true }
        : { durum: GECERLI }
  );
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  await dortKose(ekran);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-hesapla"));
  await ekran.findByTestId("kabin-kalibrasyonu-lens-onay");
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kaydet"));
  expect(mockPost.mock.calls.some((c) => c[0] === "/ai/pro/kalibrasyon/kaydet")).toBe(false);
  fireEvent(ekran.getByTestId("kabin-kalibrasyonu-lens-onay"), "valueChange", true);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kaydet"));
  await waitFor(() => expect(mockPost.mock.calls.some((c) => c[0] === "/ai/pro/kalibrasyon/kaydet")).toBe(true));
  expect(mockPost.mock.calls.find((c) => c[0] === "/ai/pro/kalibrasyon/kaydet")![1].lensUyarisiniOnayla).toBe(true);
});

it("KRİTİK: sunucu reddi (422) nedenleri SUNUCUNUN metniyle gösterilir, Kaydet görünmez", async () => {
  mockPost.mockImplementation(async (yol: string, _g: unknown, _y: unknown, op: { onHttpError?: (...a: unknown[]) => void }) => {
    if (yol === "/ai/pro/kalibrasyon/kare") return KARE;
    op.onHttpError?.(422, undefined, {
      detail: { mesaj: "SUNUCU: kaydedilmedi", sonuc: { ...SONUC, gecerli: false, nedenler: [{ kod: "olcum_tutarsiz", metin: "SUNUCU: ölçü tutarsız" }] } },
    });
    return null;
  });
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  await dortKose(ekran);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-hesapla"));
  const neden = await ekran.findByTestId("kabin-kalibrasyonu-neden-olcum_tutarsiz");
  expect(neden.props.children).toEqual(["• ", "SUNUCU: ölçü tutarsız"]);
  expect(ekran.queryByTestId("kabin-kalibrasyonu-kaydet")).toBeNull();
  expect(ekran.getByTestId("kabin-kalibrasyonu-mesaj").props.children).toBe("SUNUCU: kaydedilmedi");
});

it("Doğrula: 2 köşe → fark sonucu (geçti / kaldı sunucudan)", async () => {
  mockGet.mockResolvedValue(GECERLI);
  mockPost.mockImplementation(async (yol: string) =>
    yol === "/ai/pro/kalibrasyon/kare" ? KARE : { farkCm: [0.4, 0.7], maksCm: 0.7, gecti: true, esikCm: 1 }
  );
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-dogrula-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  expect(ekran.queryByTestId("kabin-kalibrasyonu-kose-2")).toBeNull(); // yalnız 2 köşe
  for (let i = 0; i < 2; i++) {
    fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kare"), { nativeEvent: { locationX: 30 + i * 40, locationY: 30 } });
    fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-sol-${i}`), "12");
    fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-on-${i}`), "20");
    if (i === 0) fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-sonraki"));
  }
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-dogrula"));
  const s = await ekran.findByTestId("kabin-kalibrasyonu-dogrulama-sonuc");
  expect(s.props.children).toBe(i18n.t("ai.kalibrasyon.dogrulamaGecti", { farklar: "0.4 / 0.7", maks: "0.7", esik: 1 }));
  expect(mockPost.mock.calls.find((c) => c[0] === "/ai/pro/kalibrasyon/dogrula")![1].koseler).toHaveLength(2);
});

it("Fantom ayarı yalnız fantom modelinde ve geçerli kalibrasyonda; değerler cm olarak gönderilir", async () => {
  mockGet.mockResolvedValue(GECERLI);
  mockPost.mockResolvedValue({ durum: { ...GECERLI, fantom: { kalinlikCm: 3, tumorDerinligiCm: 0.5, boyCm: [10.4, 6.5] } } });
  const p = render(<KabinKalibrasyonuKarti model="petri" />);
  await p.findByTestId("kabin-kalibrasyonu-durum");
  expect(p.queryByTestId("kabin-kalibrasyonu-fantom")).toBeNull();
  const ekran = render(<KabinKalibrasyonuKarti model="fantom" />);
  await ekran.findByTestId("kabin-kalibrasyonu-fantom");
  fireEvent.changeText(ekran.getByTestId("kabin-kalibrasyonu-fantom-kalinlik"), "3");
  fireEvent.changeText(ekran.getByTestId("kabin-kalibrasyonu-fantom-derinlik"), "0,5");
  fireEvent.changeText(ekran.getByTestId("kabin-kalibrasyonu-fantom-boy"), "10.4");
  fireEvent.changeText(ekran.getByTestId("kabin-kalibrasyonu-fantom-en"), "6.5");
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-fantom-kaydet"));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][0]).toBe("/ai/pro/kalibrasyon/fantom");
  expect(mockPost.mock.calls[0][1]).toEqual({ kalinlikCm: 3, tumorDerinligiCm: 0.5, boyCm: 10.4, enCm: 6.5 });
});

it("KRİTİK: hazırlık / seans sürerken (kilitli) kalibre et ve doğrula ÇALIŞMAZ", async () => {
  mockGet.mockResolvedValue(GECERLI);
  const ekran = render(<KabinKalibrasyonuKarti model="petri" kilitli />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-dogrula-baslat"));
  expect(mockPost).not.toHaveBeenCalled();
  expect(ekran.getByText(TR["ai.kalibrasyon.kilitli"])).toBeTruthy();
});

it("TR + EN: başlık, köşe adları ve sabit metinler iki dilde (TR birebir)", async () => {
  expect(TR["ai.kalibrasyon.baslik"]).toBe("Kabin kalibrasyonu");
  expect(TR["ai.kalibrasyon.kose.onSol"]).toBe("Ön-sol");
  expect(TR["ai.kalibrasyon.sonuc.lensOnay"]).toBe("Lens farkı 2 cm'den büyük — ölçüleri kontrol ettim, yine de kaydet.");
  for (const k of Object.keys(TR).filter((a) => a.startsWith("ai.kalibrasyon."))) expect(EN[k]).toBeTruthy();
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  mockPost.mockResolvedValue(KARE);
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  expect(await ekran.findByText("Cabin calibration")).toBeTruthy();
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  expect(ekran.getByText(/Front-left/)).toBeTruthy();
  expect(mockPost.mock.calls[0][3].zamanAsimiMesaji).toBe(EN["ai.kalibrasyon.kareZamanAsimi"]);
});
