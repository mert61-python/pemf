// Author: mertaygn, cglrgrkn
/**
 * D1.91 · A-37 (sahip) — ürün menüsünden açılan DEMA simülatörü ekranı "tanıtım/eğitim amaçlıdır, cihaz davranışını temsil
 * etmez" der; "canlı olarak izleyebilirsiniz" DEMEZ (simülatörün değeri ölçüm değil, frekans × yoğunluk formülü).
 * GERÇEK `DemaSimulatorScreen`; sahte: WebView ve gerçek-cihaz E barı (ayrı kapılarda).
 * ⚠️ MUTASYON: eski alt başlık geri konursa KIRMIZI.
 */
jest.mock("react-native-webview", () => ({ WebView: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));

import React from "react";
import { render } from "@testing-library/react-native";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";

it("KRİTİK: ekran tanıtım/eğitim etiketini taşır, 'canlı izleme' iddiası YOK", () => {
  const u = render(<DemaSimulatorScreen />);
  expect(u.queryByText("Tanıtım/eğitim amaçlıdır, cihaz davranışını temsil etmez.")).not.toBeNull();
  expect(u.queryByText(/canlı olarak izleyebilirsiniz/i)).toBeNull();
});
