/**
 * T-f (Y195, GÜVENLİK) — FANTOM AI Pro sürüşü ayrı bayrakta: petri bayrağı açıkken fantom kartı "AI Pro sürüşü KAPALI" der (TR + EN);
 * eski backend (`arastirmaAiProFantomAcik` yok) genel bayrağa düşer. Testler ÇİZİLEN metni ölçer.
 */
import { act, render } from "@testing-library/react-native";
import i18n from "i18next";
import { ModelSecimKartlari } from "@/components/domain/aipro/ModelSecimKartlari";

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

const ciz = (p: { arastirmaAcik: boolean | null; fantomAcik?: boolean | null }) =>
  render(
    <ModelSecimKartlari
      modeller={["fantom", "petri"]}
      secili="fantom"
      onSec={() => undefined}
      kurulum={{ fantom: "hazir", petri: "hazir" }}
      arastirmaAcik={p.arastirmaAcik}
      fantomAcik={p.fantomAcik}
    />,
  );

test("KRITIK: petri acik + fantom KAPALI → fantom karti 'AI Pro sürüşü KAPALI' ve not; petri kartinda rozet YOK", () => {
  const ekran = ciz({ arastirmaAcik: true, fantomAcik: false });
  expect(ekran.getAllByText("AI Pro sürüşü KAPALI — fantom hattı doğrulanmadı")).toHaveLength(1);
  expect(ekran.getByText(/^Fantom hedefine doz ONAYLANAMAZ/)).toBeTruthy();
  expect(ekran.queryByText(/Deneysel/)).toBeNull();
});

test("KARSIT: fantom bayragi ACIK → kapali rozeti ve not YOK", () => {
  const ekran = ciz({ arastirmaAcik: true, fantomAcik: true });
  expect(ekran.queryByText(/AI Pro sürüşü KAPALI/)).toBeNull();
  expect(ekran.queryByText(/Fantom hedefine doz/)).toBeNull();
});

test("KRITIK: eski backend (fantom alani yok) genel bayraga duser", () => {
  const acik = ciz({ arastirmaAcik: true, fantomAcik: null });
  expect(acik.queryByText(/AI Pro sürüşü KAPALI/)).toBeNull();
  const kapali = ciz({ arastirmaAcik: false, fantomAcik: null });
  expect(kapali.getAllByText(/Deneysel/)).toHaveLength(2);
});

test("EN: Tumor Phantom karti 'AI Pro drive OFF'", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  const ekran = ciz({ arastirmaAcik: true, fantomAcik: false });
  expect(ekran.getByText("AI Pro drive OFF — phantom pipeline not validated")).toBeTruthy();
  expect(ekran.getByText(/^A dose CANNOT be approved for the Tumor Phantom target/)).toBeTruthy();
});
