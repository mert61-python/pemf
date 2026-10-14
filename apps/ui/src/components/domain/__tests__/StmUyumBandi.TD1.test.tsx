/**
 * TD1 (tezgâh Oturum 13 — K1 / K2): kart ↔ uygulama paket uyumu arayüze ulaşır.
 *
 * ÖLÇÜLEN KUSUR: uyumsuz kartta (120 baytlık saha imajı) Ana Ekran "Donanım" YEŞİL, STM32 "Bağlı ✅"; backend'in
 * `hardware.stm.uyumsuz` olayının arayüzde abonesi yoktu, neden yalnız 409'da geliştirici diliyle çıkıyordu.
 * Kilitlenen: uyumsuz → KIRMIZI bant (sade metin + kod, teknik ayrıntı yalnız açılınca); doğrulanamadı (null + kod) → SARI
 * bant; uyumlu / bilinmiyor / alan yok (eski backend) → bant YOK; "Donanım" rozeti uyumsuzlukta YEŞİL değil;
 * WS `stm_uyum` olayı snapshot'a yazılır.
 */
let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot }),
}));

import { fireEvent, render } from "@testing-library/react-native";
import { donanimRozetDurumu, StmUyumBandi, stmUyumBandiMetni } from "@/components/domain/StmUyumBandi";

const K1 =
  "Cihaz kartının yazılımı bu uygulama sürümüyle uyumsuz — bobinler çalışmaz. Teknik desteği arayın (kod: FW-PAKET).";
const K2 = "Cihaz kartı doğrulanamadı. Kartın üzerindeki SİYAH sıfırlama düğmesine bir kez basın (mavi değil).";
const AYRINTI = "Kart uygulamanin 121 baytlik paketini SISTEMATIK reddediyor (… STM_NACK: CRC). Yapilacak: scripts/stm_yak.py";

it("KRİTİK: uyumsuz → KIRMIZI bant, sade metin + kod; teknik ayrıntı YALNIZ açılınca", () => {
  mockSnapshot = { stm: "online", stmUyum: { uyumlu: false, kod: "FW-PAKET", mesaj: K1, ayrinti: AYRINTI } };
  const { getByText, queryByText, getByTestId } = render(<StmUyumBandi />);
  expect(getByTestId("stm-uyum-bandi")).toBeTruthy();
  expect(getByText(K1)).toBeTruthy();
  expect(queryByText(/stm_yak\.py/)).toBeNull();
  expect(queryByText(/CubeIDE|7-ch/)).toBeNull();
  fireEvent.press(getByText("Teknik ayrıntı (destek için)"));
  expect(getByText(/stm_yak\.py/)).toBeTruthy();
});

it("KRİTİK: doğrulanamadı (null + FW-KIMLIK) → SARI bant, SİYAH sıfırlama düğmesi eylemi", () => {
  mockSnapshot = { stm: "online", stmUyum: { uyumlu: null, kod: "FW-KIMLIK", mesaj: K2, ayrinti: "x" } };
  expect(stmUyumBandiMetni(mockSnapshot.stmUyum as never)?.tur).toBe("sari");
  const { getByText } = render(<StmUyumBandi />);
  expect(getByText(K2)).toBeTruthy();
});

it("metin gelmese de (eski / eksik yanıt) K1 yedeği gösterilir — boş bant yok", () => {
  expect(stmUyumBandiMetni({ uyumlu: false })?.mesaj).toBe(K1);
});

it.each([
  ["uyumlu", { uyumlu: true, kod: null }],
  ["bilinmiyor (doğrulanıyor, kod yok)", { uyumlu: null, kod: null }],
  ["alan yok (eski backend)", undefined],
])("KARŞIT: %s → bant YOK", (_ad, stmUyum) => {
  mockSnapshot = { stm: "online", stmUyum };
  const { queryByTestId } = render(<StmUyumBandi />);
  expect(queryByTestId("stm-uyum-bandi")).toBeNull();
});

it("KRİTİK: 'Donanım' rozeti uyumsuzlukta YEŞİL OLMAZ; doğrulanamadıysa sarı; uyumluda bağlantıyı yansıtır", () => {
  expect(donanimRozetDurumu({ stm: "online", stmUyum: { uyumlu: false, kod: "FW-PAKET" } })).toBe("error");
  expect(donanimRozetDurumu({ stm: "online", stmUyum: { uyumlu: null, kod: "FW-KIMLIK" } })).toBe("warning");
  expect(donanimRozetDurumu({ stm: "online", stmUyum: { uyumlu: true } })).toBe("online");
  expect(donanimRozetDurumu({ stm: "online", stmUyum: undefined })).toBe("online");
  expect(donanimRozetDurumu({ stm: "warning", stmUyum: { uyumlu: false } })).toBe("warning");
});
