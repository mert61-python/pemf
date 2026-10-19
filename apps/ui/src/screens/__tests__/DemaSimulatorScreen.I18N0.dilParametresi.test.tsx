// Author: mertaygn, cglrgrkn
/**
 * I18N-0 (Y159) · DEMA simülatörü ayrı bir sayfadır (iframe / WebView) — dil başlığı taşıyamaz; dili `?dil=tr|en` parametresiyle
 * alır. Bayrak kapalıyken parametre hep `tr`; dil değişince çerçeve YENİDEN yüklenir (eski dilde kalmaz). Ekranda yazan adres
 * parametresiz kalır (Türkçe görünüm göçten önceki gibi).
 * GERÇEK `DemaSimulatorScreen` + gerçek i18n; sahte: WebView (yükleme sayısını ve adresini kaydeder), gerçek-cihaz E barı.
 */
const yuklemeler: string[] = [];
jest.mock("react-native-webview", () => {
  const R = require("react");
  return {
    WebView: ({ source }: { source: { uri: string } }) => {
      R.useEffect(() => {
        yuklemeler.push(source.uri);
      }, []);
      return null;
    },
  };
});
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const ADRES = "http://127.0.0.1:8000/simulator/index.html";
const depo = { setItem: async () => undefined };

beforeEach(() => {
  yuklemeler.length = 0;
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("bayrak KAPALI: çerçeve ?dil=tr ile yüklenir; ekrandaki adres parametresiz (Türkçe görünüm aynı)", () => {
  const u = render(<DemaSimulatorScreen />);
  expect(yuklemeler).toEqual([`${ADRES}?dil=tr`]);
  expect(u.queryByText(ADRES)).not.toBeNull();
});

it("bayrak AÇIK: İngilizceye geçince çerçeve ?dil=en ile YENİDEN yüklenir", async () => {
  __bayrakTestiAyarla(true);
  render(<DemaSimulatorScreen />);
  expect(yuklemeler).toEqual([`${ADRES}?dil=tr`]);
  await act(async () => {
    await dilSec("en", depo);
  });
  expect(yuklemeler).toEqual([`${ADRES}?dil=tr`, `${ADRES}?dil=en`]);
});
