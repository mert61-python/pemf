// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — panel kaydı: TEMBEL yükleme: "ornek" kimliği örnek panelini yükler (modül seçilmeden yüklenmez).
 */
const mockModul = { durum: { bobin: false }, hata: null, mesgul: false, uygula: jest.fn(), baslat: jest.fn(), durdur: jest.fn() };
jest.mock("@/moduller/arac", () => ({ useModul: () => mockModul }));
// `import()` jest'te koşmaz → yükleyici aynı paneli require ile verir (gerçek yükleyici `yukleyiciler.ts`, istanbul ignore file)
jest.mock("@/moduller/yukleyiciler", () => ({ PANEL_YUKLEYICILERI: { ornek: () => Promise.resolve(require("@/moduller/ornek/Panel")) } }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { ModulPaneli } from "@/components/domain/ModulSecici";
import { PANELLER } from "@/moduller/kayit";

it("GA: kayıtlı örnek panel tembel yüklenir", async () => {
  expect(Object.keys(PANELLER)).toEqual(["ornek"]);
  const u = render(<ModulPaneli kimlik="ornek" />);
  await act(async () => {});
  expect(u.getByTestId("modul-ornek-panel")).toBeTruthy();
});
