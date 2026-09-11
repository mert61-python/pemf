// Author: mertaygn
/**
 * SÜRÜŞ KİPİ SEÇİCİ — arayüz DÜRÜSTLÜK kapısı (2026-09-11).
 *
 * Bu bileşen operatöre "bu bobin bipolar sürülüyor" diyor. Yanlış söylerse hasta
 * sanılandan farklı bir alan profili alır ve kayda geçen doz gerçeği yansıtmaz.
 * Üç yalan mümkün ve üçü de sessiz:
 *
 *   1. Bobin 6-7'ye bipolar gönderebilmek (sürücüde ikinci yarım köprü YOK).
 *   2. "Hepsi Bipolar"ın o iki bobini de çevirdiğini göstermek.
 *   3. Firmware kipi HİÇ bildirmemişken "BİP" yazmak (bildirmemek ≠ bipolar).
 *
 * Testler ÇİZİLEN metni ve GÖNDERİLEN gövdeyi ölçer — iç state'i değil.
 */
const mockApiPost = jest.fn(async () => ({ status: "success" }));
jest.mock("@/services/apiClient", () => ({ apiPost: (...a: unknown[]) => mockApiPost(...(a as [])) }));

import { render, fireEvent, waitFor } from "@testing-library/react-native";
import { SurusKipiSecici } from "@/components/domain/SurusKipiSecici";
import type { CoilStatus } from "@/types/domain";

/** 7 STM bobini; 1-5 bipolar yetenekli, 6-7 donanımsal olarak yalnız unipolar. */
const bobinler = (ek: Partial<CoilStatus>[] = []): CoilStatus[] =>
  Array.from({ length: 7 }, (_, i) => ({
    id: i + 1,
    connected: true,
    running: false,
    frequencyHz: 0,
    dutyCycle: 0,
    magneticMt: 0,
    objectTemp: 0,
    ambientTemp: 0,
    currentA: 0,
    bipolarYetenek: i < 5,
    ...(ek[i] ?? {}),
  }));

const ciz = (coils = bobinler(), props: Partial<React.ComponentProps<typeof SurusKipiSecici>> = {}) =>
  render(<SurusKipiSecici coils={coils} stmConnected {...props} />);

beforeEach(() => mockApiPost.mockClear());

// ============================================================================
// 1. YETENEK TAVANI
// ============================================================================

test("KRITIK: bobin 6-7 kutusu BASILAMAZ ve daima UNI gosterir", async () => {
  // MUTASYON: `disabled={kilitli || !yetenekli}` → `disabled={kilitli}` yap → KIRMIZI.
  const { getByLabelText } = ciz();
  const kutu = getByLabelText(/^Bobin 6, unipolar, sürücüsü yalnız unipolar/);
  fireEvent.press(kutu);
  // Basış YUTULMALI: sunucuya hiçbir şey gitmemeli.
  expect(mockApiPost).not.toHaveBeenCalled();
  expect(getByLabelText(/^Bobin 6, unipolar/)).toBeTruthy();
});

test("KRITIK: 'Hepsi Bipolar' bobin 6-7'yi UNIPOLAR birakir", async () => {
  // ⚠️ ASIL KAPI. MUTASYON: `hepsi`deki `bipolarYetenek(c) ? unipolar : true` →
  // `unipolar` yap → KIRMIZI. Saha etkisi: arayüz 7/7 "BİP" gösterir, donanım 5/7 bipolar sürer.
  const { getByLabelText } = ciz();
  fireEvent.press(getByLabelText("Yetenekli tüm bobinleri bipolar sür"));

  await waitFor(() => expect(mockApiPost).toHaveBeenCalled());
  const [yol, govde] = mockApiPost.mock.calls[0] as unknown as [string, { unipolar: boolean[] }];
  expect(yol).toBe("/coil/surus_kipi");
  expect(govde.unipolar).toEqual([false, false, false, false, false, true, true]);
});

test("'Hepsi Unipolar' 7 bobini de unipolar ister", async () => {
  const { getByLabelText } = ciz();
  fireEvent.press(getByLabelText("Tüm bobinleri unipolar sür"));
  await waitFor(() => expect(mockApiPost).toHaveBeenCalled());
  const [, govde] = mockApiPost.mock.calls[0] as unknown as [string, { unipolar: boolean[] }];
  expect(govde.unipolar).toEqual(Array(7).fill(true));
});

// ============================================================================
// 2. BİT ↔ BOBİN — tek tek
// ============================================================================

test("KRITIK: cevrilen bobin dizide DOGRU indekse dusuyor", async () => {
  // Hepsini birden çevirmek kaymayı görmez; tek bobin çevirmek görür.
  // MUTASYON: `yeni[idx] = !yeni[idx]` → `yeni[idx + 1] = ...` → KIRMIZI.
  const { getByLabelText } = ciz();
  fireEvent.press(getByLabelText(/^Bobin 3, bipolar/));
  await waitFor(() => expect(mockApiPost).toHaveBeenCalled());
  const [, govde] = mockApiPost.mock.calls[0] as unknown as [string, { unipolar: boolean[] }];
  expect(govde.unipolar).toEqual([false, false, true, false, false, true, true]);
});

// ============================================================================
// 3. "BİLDİRMEDİ" ≠ "BİPOLAR"
// ============================================================================

test("KRITIK: firmware kipi bildirmediyse UYDURULMAZ", () => {
  // MUTASYON: `typeof c.unipolar === "boolean" ? ... : null` → `Boolean(c.unipolar)` → KIRMIZI.
  const { getByText, queryByText } = ciz();
  expect(getByText(/sürüş başlayınca görünür/)).toBeTruthy();
  expect(queryByText(/Kartın uyguladığı:/)).toBeNull();
});

test("KRITIK: kart bildirince ETKIN kip satiri cizilir", () => {
  const { getByText } = ciz(bobinler([{ unipolar: false }, {}, {}, {}, {}, { unipolar: true }]));
  const satir = getByText(/Kartın uyguladığı:/);
  const metin = (Array.isArray(satir.props.children) ? satir.props.children.flat(2) : [satir.props.children])
    .join("");
  expect(metin).toContain("1:BİP");
  expect(metin).toContain("6:UNİ");
  // Bildirmeyen bobinler kısa çizgi — 0/false değil.
  expect(metin).toContain("2:—");
});

test("KRITIK: bildirmeyen bobinin erisilebilirlik etiketi de UYDURMAZ", () => {
  // ⚠️ Bu testin YOKLUĞUNDA `etkin`i `Boolean(c.unipolar)` yapan mutasyon YEŞİL kalıyordu
  // (2026-09-11 mutasyon turunda ölçüldü): metin satırı korunuyor ama ekran okuyucuya ve
  // uyuşmazlık çerçevesine "kart bipolar uyguluyor" diye YALAN gidiyordu.
  const { getByLabelText } = ciz();
  // Hiç bildirim yokken: 1-5 için "kart henüz bildirmedi", 6-7 için de aynısı.
  expect(getByLabelText(/^Bobin 1, bipolar, kart henüz bildirmedi$/)).toBeTruthy();
  expect(getByLabelText(/^Bobin 6, unipolar, sürücüsü yalnız unipolar — değiştirilemez, kart henüz bildirmedi$/))
    .toBeTruthy();
});

test("KRITIK: kart ISTEKTEN FARKLI kip uygularsa etiket bunu SOYLER", () => {
  // Karşıt kanıt: "her zaman bildirmedi de" diyerek geçilemesin.
  const { getByLabelText } = ciz(bobinler([{ unipolar: true }]));
  expect(getByLabelText(/^Bobin 1, bipolar, kartın uyguladığı unipolar$/)).toBeTruthy();
});

// ============================================================================
// 4. BAŞARISIZLIK SESSİZ KALMAZ
// ============================================================================

test("KRITIK: gonderim basarisizsa operator BILGILENDIRILIR", async () => {
  // MUTASYON: `else { setDurum("Gönderilemedi…") }` dalını sil → KIRMIZI.
  // Saha etkisi: arayüz "BİP" gösterirken kart eski kiple sürmeye devam eder.
  mockApiPost.mockResolvedValueOnce(null as never);
  const { getByLabelText, findByText } = ciz();
  fireEvent.press(getByLabelText(/^Bobin 2, bipolar/));
  expect(await findByText(/Gönderilemedi — kip DEĞİŞMEDİ/)).toBeTruthy();
});

test("STM kopukken kip degistirilemez", () => {
  const { getByText, getByLabelText } = ciz(bobinler(), { stmConnected: false });
  expect(getByText(/STM32 bağlı değil/)).toBeTruthy();
  fireEvent.press(getByLabelText(/^Bobin 1, bipolar/));
  expect(mockApiPost).not.toHaveBeenCalled();
});
