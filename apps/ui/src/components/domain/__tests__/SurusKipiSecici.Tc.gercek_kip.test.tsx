// Author: mertaygn
/**
 * T-c (Tezgâh-2 #6, Y195) — Sürüş Kipi kutuları KARTIN / BACKEND'İN GERÇEĞİNDEN başlar; uyuşmazlık METİNLE söylenir (TR + EN).
 *
 * ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23, sahip ekran görüntüsü + backend günlüğü): "All Unipolar" → maske 0x7F → kart `K=127`
 * (tek yönlü DOĞRU uygulandı); ama sayfa / dil değişince kutular 1–5 "BİP" yazdı, "Kartın uyguladığı: 1:UNİ … 7:UNİ".
 * Bileşen her açılışta sabit varsayılandan başlıyordu; uyuşmazlık yalnız kırmızı çerçeveydi → operatör çift yönlü sanırken
 * kart tek yönlü sürebilir.
 * SÖZLEŞME: başlangıç = backend'in kayıtlı isteği (`unipolarIstek`) → yoksa kartın bildirdiği (`unipolar`) → yoksa varsayılan;
 * kayıtlı istek değişince eşitlenir; kartın uyguladığı kip seçimden farklıysa metin (bobin listesiyle). Testler ÇİZİLEN metni ve
 * erişilebilirlik etiketini ölçer — iç state'i değil.
 */
const mockApiPost = jest.fn(async () => ({ status: "success" }));
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => mockApiPost(...(a as [])),
  platformConfirm: async () => true,
}));

import { act, render } from "@testing-library/react-native";
import i18n from "i18next";
import { SurusKipiSecici } from "@/components/domain/SurusKipiSecici";
import type { CoilStatus } from "@/types/domain";

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

/** "Hepsi Unipolar"dan sonraki gerçek durum: kayıtlı istek 7/7 UNİ, kart K=127 bildirdi. */
const hepsiUni = () => bobinler(Array.from({ length: 7 }, () => ({ unipolarIstek: true, unipolar: true })));

beforeEach(() => mockApiPost.mockClear());
afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

test("KRITIK: 'Hepsi Unipolar'dan sonra YENIDEN ACILISTA kutular UNI (sabit varsayilan BIP DEGIL)", () => {
  const { getByLabelText, queryByText } = render(<SurusKipiSecici coils={hepsiUni()} stmConnected />);
  for (const id of [1, 2, 3, 4, 5]) {
    expect(getByLabelText(new RegExp(`^Bobin ${id}, unipolar, kartın uyguladığı unipolar$`))).toBeTruthy();
  }
  expect(queryByText(/seçiminizden farklı/)).toBeNull();
  expect(mockApiPost).not.toHaveBeenCalled(); // başlangıç hiçbir şey GÖNDERMEZ
});

test("KRITIK: kayitli istek yokken kutular KARTIN bildirdigi kipten baslar", () => {
  const coils = bobinler([{ unipolar: true }, { unipolar: false }, { unipolar: true }]);
  const { getByLabelText } = render(<SurusKipiSecici coils={coils} stmConnected />);
  expect(getByLabelText(/^Bobin 1, unipolar, kartın uyguladığı unipolar$/)).toBeTruthy();
  expect(getByLabelText(/^Bobin 2, bipolar, kartın uyguladığı bipolar$/)).toBeTruthy();
  expect(getByLabelText(/^Bobin 3, unipolar, kartın uyguladığı unipolar$/)).toBeTruthy();
});

test("KRITIK: kart henuz bildirmediyse kayitli istekten baslar (bir sonraki surusun kipi)", () => {
  const coils = bobinler([{ unipolarIstek: true }, { unipolarIstek: false }]);
  const { getByLabelText } = render(<SurusKipiSecici coils={coils} stmConnected />);
  expect(getByLabelText(/^Bobin 1, unipolar, kart henüz bildirmedi$/)).toBeTruthy();
  expect(getByLabelText(/^Bobin 2, bipolar, kart henüz bildirmedi$/)).toBeTruthy();
});

test("KRITIK: kartin UYGULADIGI kip secimden farkliysa METINLE soylenir (bobin listesi)", () => {
  // Kayıtlı istek BİP (değişiklik bekliyor), kart henüz eski kipte (UNİ) → çerçeve TEK BAŞINA yetmez.
  const coils = bobinler([
    { unipolarIstek: false, unipolar: true },
    { unipolarIstek: false, unipolar: true },
    { unipolarIstek: false, unipolar: false },
  ]);
  const { getByText } = render(<SurusKipiSecici coils={coils} stmConnected />);
  const metin = getByText(/seçiminizden farklı/);
  expect(metin.props.children).toBe(
    "⚠️ Kartın şu an uyguladığı kip seçiminizden farklı: bobin 1, 2. Seçim kayıtlı; karta bir sonraki sürüşte (bobin başlatılınca) gider.",
  );
});

test("EN: uyusmazlik metni Ingilizce ve cogul", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  const coils = bobinler([
    { unipolarIstek: false, unipolar: true },
    { unipolarIstek: false, unipolar: true },
  ]);
  const { getByText, getByLabelText } = render(<SurusKipiSecici coils={coils} stmConnected />);
  expect(getByText(/different mode than your selection/).props.children).toBe(
    "⚠️ The board is currently applying a different mode than your selection: coils 1, 2. Your selection is saved and reaches the board on the next drive (when a coil starts).",
  );
  expect(getByLabelText(/^Coil 1, bipolar, the board applied unipolar$/)).toBeTruthy();
});

test("KRITIK: kayitli istek degisince (baska istemci) kutular ESITLENIR", () => {
  const ekran = render(<SurusKipiSecici coils={bobinler()} stmConnected />);
  expect(ekran.getByLabelText(/^Bobin 1, bipolar, kart henüz bildirmedi$/)).toBeTruthy();
  ekran.rerender(
    <SurusKipiSecici coils={bobinler(Array.from({ length: 7 }, () => ({ unipolarIstek: true })))} stmConnected />,
  );
  expect(ekran.getByLabelText(/^Bobin 1, unipolar, kart henüz bildirmedi$/)).toBeTruthy();
});

test("KARSIT: hicbir bilgi yokken varsayilan (1-5 BIP) ve uyusmazlik metni YOK", () => {
  const { getByLabelText, queryByText } = render(<SurusKipiSecici coils={bobinler()} stmConnected />);
  expect(getByLabelText(/^Bobin 1, bipolar, kart henüz bildirmedi$/)).toBeTruthy();
  expect(getByLabelText(/^Bobin 6, unipolar, sürücüsü yalnız unipolar/)).toBeTruthy();
  expect(queryByText(/seçiminizden farklı/)).toBeNull();
});
