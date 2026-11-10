/**
 * KD · Y260 (istem 44 §2) + KD-2 çok konumlu — Kabin kalibrasyonu ekranı: Kalibre et → kare (kuyular SUNUCUDA otomatik, köşeler numaralı;
 * dokunma yok) → numaralı köşelerden ≥ 2'sinin sol / ön cm'si → Konumu ekle → ikinci konum → lens → Hesapla (2 konumdan önce kapalı) →
 * sonuç → Kaydet (lens uyarısı AÇIK onay ister) · Doğrula (≥ 1 köşe → MERKEZ farkı) · numune tabanı (lens → taban uzaklığı) · kalibre
 * etmeden devam · fantom ayarı. Kurallar ve nedenler SUNUCUDAN (arayüz uydurmaz). TR + EN. Sahte yalnız ağ sınırında.
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

let kareNo = 0;
const kare = (bulundu = true) => ({
  kareKimligi: `k${++kareNo}`,
  genislik: 1920,
  yukseklik: 1080,
  image_base64: "QUJD",
  plaka: { bulundu, kuyuSayisi: bulundu ? 24 : 0, kareSayisi: 3, metin: bulundu ? null : "SUNUCU: plaka yok" },
});
const SONUC = {
  gecerli: true,
  nedenler: [],
  izdusumHatasiPx: 1.61,
  olcumUyumuMm: 6.9,
  yayilimCm: 29.7,
  konumlar: [
    { koseSapmasiMm: [12, null, 5.6, null], kuyuIzdusumPx: 1.7, merkezCm: [13.4, 9.8] },
    { koseSapmasiMm: [0.9, 7.9, 6.3, 3.8], kuyuIzdusumPx: 1.5, merkezCm: [39.8, 21.8] },
  ],
  caprazDogrulamaCm: null,
  hesaplananLensCm: [25.1, 12.0, 38.8],
  olculenLensCm: [26, 11.5, 36.5],
  lensYatayFarkiCm: 1.0,
  lensDikeyFarkiCm: 2.3,
  lensUyarisi: false,
  gorusAlani: { onCm: 4, arkaCm: 2.5, solCm: 0, sagCm: 0 },
  sahne: { oznitelik: 3000, denetim: true },
  esikler: { izdusumPx: 3, lensCm: 2, lensDikeyCm: 3, olcumMm: 10, yayilimCm: 20, konumAsgari: 2 },
};
const GECERLI = {
  var: true,
  gecerli: true,
  tarih: "2026-11-10T15:00:00+0300",
  konumSayisi: 2,
  izdusumHatasiPx: 1.61,
  lensFarkiCm: 2.5,
  kameraAdi: "FHD Camera",
  kameraVidPid: "VID_1BCF&PID_28C4",
  olculenLensTabanCm: 36.5,
  gorusAlani: { on: 4, arka: 2.5, sol: 0, sag: 0 },
  sahneDenetimi: true,
  eski: false,
  tabanYukseltmesiCm: 0,
};

beforeEach(() => {
  kareNo = 0;
  mockGet.mockReset().mockResolvedValue({ var: false, gecerli: false, hataMetni: "SUNUCU: kalibrasyon yok" });
  mockPost.mockReset();
});
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

function olc(ekran: ReturnType<typeof render>, koseler: number[], taban = 10) {
  for (const i of koseler) {
    fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-sol-${i}`), `${taban + i},5`);
    fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-on-${i}`), `${20 + i}`);
  }
}

async function ikiKonum(ekran: ReturnType<typeof render>) {
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  olc(ekran, [0, 2]);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-konum-ekle"));
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-kare-al"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  olc(ekran, [0, 1, 2, 3], 35);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-konum-ekle"));
  await ekran.findByTestId("kabin-kalibrasyonu-konum-1");
}

it("KRİTİK: kalibrasyon yoksa SUNUCUNUN eylem metni görünür (arayüz uydurmaz)", async () => {
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  expect((await ekran.findByTestId("kabin-kalibrasyonu-durum")).props.children).toBe("SUNUCU: kalibrasyon yok");
  expect(mockGet).toHaveBeenCalledWith("/ai/pro/kalibrasyon", null, { silent: true });
  expect(ekran.queryByTestId("kabin-kalibrasyonu-taban")).toBeNull();
  expect(ekran.queryByTestId("kabin-kalibrasyonu-devam")).toBeNull();
});

it("KRİTİK: akış — iki konum (KAMERA süresi, ≥ 2 köşe olmadan EKLENMEZ) → Hesapla gövdesi → sonuç → Kaydet", async () => {
  mockPost.mockImplementation(async (yol: string) => {
    if (yol === "/ai/pro/kalibrasyon/kare") return kare();
    if (yol === "/ai/pro/kalibrasyon/hesapla") return SONUC;
    if (yol === "/ai/pro/kalibrasyon/kaydet") return { durum: GECERLI };
    return null;
  });
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  expect(mockPost.mock.calls[0][0]).toBe("/ai/pro/kalibrasyon/kare");
  expect(mockPost.mock.calls[0][3].timeoutMs).toBe(120000);
  olc(ekran, [0]);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-konum-ekle"));
  expect(ekran.queryByTestId("kabin-kalibrasyonu-konum-0")).toBeNull(); // tek köşe → eklenmez
  olc(ekran, [2]);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-konum-ekle"));
  await ekran.findByTestId("kabin-kalibrasyonu-konum-0");
  expect(ekran.getByTestId("kabin-kalibrasyonu-hesapla").props.accessibilityState?.disabled).toBe(true); // 1 konum
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kare-al"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  olc(ekran, [0, 1, 2, 3], 35);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-konum-ekle"));
  await ekran.findByTestId("kabin-kalibrasyonu-konum-1");
  for (const [a, v] of [["sol", "26"], ["on", "11,5"], ["taban", "36.5"]]) fireEvent.changeText(ekran.getByTestId(`kabin-kalibrasyonu-lens-${a}`), v);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-hesapla"));
  await ekran.findByTestId("kabin-kalibrasyonu-sonuc");
  const govde = mockPost.mock.calls.find((c) => c[0] === "/ai/pro/kalibrasyon/hesapla")![1];
  expect(govde.konumlar).toEqual([
    { kareKimligi: "k1", olcumler: [{ solCm: 10.5, onCm: 20 }, null, { solCm: 12.5, onCm: 22 }, null] },
    {
      kareKimligi: "k2",
      olcumler: [
        { solCm: 35.5, onCm: 20 },
        { solCm: 36.5, onCm: 21 },
        { solCm: 37.5, onCm: 22 },
        { solCm: 38.5, onCm: 23 },
      ],
    },
  ]);
  expect(govde.lens).toEqual({ solCm: 26, onCm: 11.5, tabanCm: 36.5 });
  expect(ekran.getByTestId("kabin-kalibrasyonu-izdusum").props.children).toBe(i18n.t("ai.kalibrasyon.sonuc.izdusum", { px: "1.61", esik: 3 }));
  expect(ekran.getByTestId("kabin-kalibrasyonu-sapma-0").props.children).toMatch(/1: 12 · 2: — · 3: 6 · 4: —/);
  expect(ekran.getByTestId("kabin-kalibrasyonu-lens").props.children).toMatch(/1\.0 cm.*2\.3 cm/);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-kaydet"));
  await waitFor(() => expect(ekran.getByTestId("kabin-kalibrasyonu-mesaj").props.children).toBe(TR["ai.kalibrasyon.kaydedildi"]));
  expect(ekran.getByTestId("kabin-kalibrasyonu-durum").props.children).toMatch(/2 konum/);
  expect(ekran.getByTestId("kabin-kalibrasyonu-gorus").props.children).toMatch(/~4\.0 cm/);
});

it("KRİTİK: plaka bulunamayan karede SUNUCUNUN eylem metni, köşe girişi ve ekleme YOK", async () => {
  mockPost.mockImplementation(async () => kare(false));
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  expect((await ekran.findByTestId("kabin-kalibrasyonu-plaka-yok")).props.children).toBe("SUNUCU: plaka yok");
  expect(ekran.queryByTestId("kabin-kalibrasyonu-sol-0")).toBeNull();
  expect(ekran.getByTestId("kabin-kalibrasyonu-konum-ekle").props.accessibilityState?.disabled).toBe(true);
});

it("KRİTİK: lens uyarısı → Kaydet ONAYSIZ kapalı; onay gövdeye yazılır", async () => {
  mockPost.mockImplementation(async (yol: string) =>
    yol === "/ai/pro/kalibrasyon/kare"
      ? kare()
      : yol === "/ai/pro/kalibrasyon/hesapla"
        ? { ...SONUC, lensYatayFarkiCm: 3.1, lensUyarisi: true }
        : { durum: GECERLI }
  );
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  await ikiKonum(ekran);
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
    if (yol === "/ai/pro/kalibrasyon/kare") return kare();
    op.onHttpError?.(422, undefined, {
      detail: {
        mesaj: "SUNUCU: kaydedilmedi",
        sonuc: { ...SONUC, gecerli: false, nedenler: [{ kod: "konum_yayilimi_az", metin: "SUNUCU: iki yana koyun" }] },
      },
    });
    return null;
  });
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  await ikiKonum(ekran);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-hesapla"));
  const neden = await ekran.findByTestId("kabin-kalibrasyonu-neden-konum_yayilimi_az");
  expect(neden.props.children).toEqual(["• ", "SUNUCU: iki yana koyun"]);
  expect(ekran.queryByTestId("kabin-kalibrasyonu-kaydet")).toBeNull();
  expect(ekran.getByTestId("kabin-kalibrasyonu-mesaj").props.children).toBe("SUNUCU: kaydedilmedi");
});

it("Doğrula: numaralı köşelerden ölçülenler → MERKEZ farkı (geçti / kaldı sunucudan)", async () => {
  mockGet.mockResolvedValue(GECERLI);
  mockPost.mockImplementation(async (yol: string) =>
    yol === "/ai/pro/kalibrasyon/kare" ? kare() : { farkCm: [0.4, null, 0.7, null], merkezFarkCm: 0.5, gecti: true, esikCm: 1 }
  );
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-dogrula-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  expect(ekran.queryByTestId("kabin-kalibrasyonu-konum-ekle")).toBeNull();
  olc(ekran, [0, 2]);
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-dogrula"));
  const s = await ekran.findByTestId("kabin-kalibrasyonu-dogrulama-sonuc");
  expect(s.props.children).toBe(i18n.t("ai.kalibrasyon.dogrulamaGecti", { merkez: "0.5", farklar: "1: 0.4 · 3: 0.7", esik: 1 }));
  expect(mockPost.mock.calls.find((c) => c[0] === "/ai/pro/kalibrasyon/dogrula")![1].olcumler).toEqual([
    { solCm: 10.5, onCm: 20 },
    null,
    { solCm: 12.5, onCm: 22 },
    null,
  ]);
});

it("KRİTİK: numune tabanı — lens yüksekliğiyle dolu alan, uzaklık gönderilir, yükseltme sunucudan", async () => {
  mockGet.mockResolvedValue(GECERLI);
  mockPost.mockResolvedValue({ durum: { ...GECERLI, tabanYukseltmesiCm: 5 } });
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  const alan = await ekran.findByTestId("kabin-kalibrasyonu-taban-uzaklik");
  await waitFor(() => expect(ekran.getByTestId("kabin-kalibrasyonu-taban-uzaklik").props.value).toBe("36.5"));
  fireEvent.changeText(alan, "31,5");
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-taban-uygula"));
  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  expect(mockPost.mock.calls[0][0]).toBe("/ai/pro/kalibrasyon/taban");
  expect(mockPost.mock.calls[0][1]).toEqual({ lensUzaklikCm: 31.5 });
  await waitFor(() =>
    expect(ekran.getByTestId("kabin-kalibrasyonu-taban-durum").props.children).toBe(i18n.t("ai.kalibrasyon.taban.durum", { cm: "5.0" }))
  );
});

it("KRİTİK: kalibre etmeden devam — KAMERA süresiyle istek, sonra kalıcı ESKİ uyarısı; sunucu reddi metni gösterilir", async () => {
  mockGet.mockResolvedValue(GECERLI);
  mockPost.mockResolvedValueOnce({ durum: { ...GECERLI, eski: true, eskiTarih: "2026-11-10T22:00:00+0300" }, kaymaPx: 31 });
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-devam-et"));
  await ekran.findByTestId("kabin-kalibrasyonu-eski");
  expect(mockPost.mock.calls[0][0]).toBe("/ai/pro/kalibrasyon/sahne-yenile");
  expect(mockPost.mock.calls[0][3].timeoutMs).toBe(120000);
  expect(ekran.getByTestId("kabin-kalibrasyonu-mesaj").props.children).toBe(i18n.t("ai.kalibrasyon.devam.tamam", { px: "31" }));
  mockPost.mockImplementation(async (_y: string, _g: unknown, _z: unknown, op: { onHttpError?: (...a: unknown[]) => void }) => {
    op.onHttpError?.(409, "SUNUCU: fazla oynamış — yeniden kalibre edin", {});
    return null;
  });
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-devam-et"));
  await waitFor(() =>
    expect(ekran.getByTestId("kabin-kalibrasyonu-mesaj").props.children).toBe("SUNUCU: fazla oynamış — yeniden kalibre edin")
  );
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

it("KRİTİK: hazırlık / seans sürerken (kilitli) kalibre et, doğrula, taban ve devam ÇALIŞMAZ", async () => {
  mockGet.mockResolvedValue(GECERLI);
  const ekran = render(<KabinKalibrasyonuKarti model="petri" kilitli />);
  fireEvent.press(await ekran.findByTestId("kabin-kalibrasyonu-baslat"));
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-dogrula-baslat"));
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-taban-uygula"));
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-devam-et"));
  expect(mockPost).not.toHaveBeenCalled();
  expect(ekran.getByText(TR["ai.kalibrasyon.kilitli"])).toBeTruthy();
});

it("TR + EN: başlık, köşe adları ve sabit metinler iki dilde (TR birebir)", async () => {
  expect(TR["ai.kalibrasyon.baslik"]).toBe("Kabin kalibrasyonu");
  expect(TR["ai.kalibrasyon.kose.onSol"]).toBe("Ön-sol");
  expect(TR["ai.kalibrasyon.devam.dugme"]).toBe("Kalibre etmeden devam et");
  expect(TR["ai.kalibrasyon.taban.uzaklik"]).toBe("Lens → numune tabanı (cm)");
  for (const k of Object.keys(TR).filter((a) => a.startsWith("ai.kalibrasyon."))) expect(EN[k]).toBeTruthy();
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  mockPost.mockResolvedValue(kare());
  const ekran = render(<KabinKalibrasyonuKarti model="petri" />);
  expect(await ekran.findByText("Cabin calibration")).toBeTruthy();
  fireEvent.press(ekran.getByTestId("kabin-kalibrasyonu-baslat"));
  await ekran.findByTestId("kabin-kalibrasyonu-kare");
  expect(ekran.getByText(/Front-left/)).toBeTruthy();
  expect(mockPost.mock.calls[0][3].zamanAsimiMesaji).toBe(EN["ai.kalibrasyon.kareZamanAsimi"]);
});
