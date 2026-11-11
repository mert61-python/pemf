/**
 * KP-4 B1 · app/index.tsx — expo-router KÖK rotası ("/") uygulama kabuğunu (PemfApp) çizer: başka bir ekran / boş sayfa değil.
 * SAHTE: PemfApp (kendi yönlendiricisi KP3-PemfApp-yonlendirici'nin konusu; burada yalnız kök rotanın neyi çizdiği).
 */
jest.mock("@/PemfApp", () => {
  const { Text } = jest.requireActual("react-native");
  return { PemfApp: () => <Text>PEMF_UYGULAMA_KOKU</Text> };
});

import React from "react";
import { render } from "@testing-library/react-native";
import Index from "../index";

it("kök rota uygulama kabuğunu çizer", () => {
  const u = render(<Index />);
  expect(u.getByText("PEMF_UYGULAMA_KOKU")).toBeTruthy();
});
