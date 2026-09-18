// Author: mertaygn, cglrgrkn
/**
 * AI HUB AKORDEON — BİRDEN FAZLA MODÜL AYNI ANDA AÇIK KALABİLMELİ (saha bildirimi 2026-08-12).
 *
 * ARIZA: Veteriner ve Araştırma modlarında ikinci bir modüle dokunulduğunda BİRİNCİNİN gövdesi
 * kapanıyor, geriye yalnız başlığı kalıyordu. Sebep: durum tek bir `activeModule` tutuyordu ve
 * her dokunuş öncekinin YERİNE geçiyordu.
 *
 * NEDEN ÖNEMLİ: akış karşılaştırmalı. Hekim yüz-ağrısı skorunu ekranda tutarken ses analizini de
 * açıp iki sonuca BİRLİKTE bakmak istiyor; araştırma modunda da aynısı geçerli. Tek-açık akordeon
 * kullanıcıyı sürekli ileri-geri dokunmaya zorluyor ve önceki sonucu görünmez kılıyordu.
 *
 * Bu test DAVRANIŞI kilitler (kaynak metnini değil): iki başlığa sırayla dokunulur ve İKİSİNİN de
 * `accessibilityState.expanded` değerinin true kaldığı doğrulanır. Kapatma davranışı da sınanır —
 * "hepsi hep açık" da bir regresyon olurdu.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
// ⚠️ `hasAiHub` ŞART: ekran onu okur ve YOKSA ev-sahibi ekranına düşer (modül ızgarası hiç
// render edilmez). İlk denemede eksikti ve test "etiket bulunamadı" diye düşüyordu.
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", hasAiHub: true }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: true }) }));
// Hasta seçili olmalı: `patientName` modül gövdelerine geçer.
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Test Hasta" } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
// Hasta kapısı: testte hasta seçimi akışı konumuz değil → çocukları doğrudan render et.
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
// Modül gövdeleri ağır (kamera/ses/dosya seçici). Konu AKORDEON DAVRANIŞI olduğu için
// gövdeler sadeleştirilir; başlıkların `expanded` durumu gerçek bileşenden gelir.
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));

import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { AiHubScreen } from "@/screens/AiHubScreen"; // named export (PemfApp da böyle alıyor)

/** Başlık düğmesini erişilebilirlik etiketiyle bul.
 *
 * ⚠️ RegExp KULLANMAYIN: etiketlerde parantez var ("Yüz Ağrısı (FGS)") ve `new RegExp`
 * onu YAKALAMA GRUBU sayıp eşleşmeyi bozuyor. Etiket zaten modül adının birebir kendisi
 * (`research: true` → hiçbir modül "eklenti gerekli" ekiyle işaretlenmiyor), düz metin yeter.
 */
function baslik(utils: ReturnType<typeof render>, ad: string) {
  return utils.getAllByLabelText(ad)[0];
}

function acikMi(dugme: any): boolean {
  return dugme.props.accessibilityState?.expanded === true;
}

describe("AI Hub akordeonu", () => {
  it("KRITIK: ikinci modül açılınca BİRİNCİSİ KAPANMAZ", () => {
    const u = render(<AiHubScreen />);

    const a = baslik(u, "Yüz Ağrısı (FGS)");
    const b = baslik(u, "Kedi Sesi");

    expect(acikMi(a)).toBe(false);
    expect(acikMi(b)).toBe(false);

    fireEvent.press(a);
    expect(acikMi(baslik(u, "Yüz Ağrısı (FGS)"))).toBe(true);

    fireEvent.press(b);
    // ⚠️ ASIL REGRESYON: eskiden burada birincisi false'a düşüyordu.
    expect(acikMi(baslik(u, "Yüz Ağrısı (FGS)"))).toBe(true);
    expect(acikMi(baslik(u, "Kedi Sesi"))).toBe(true);
  });

  it("üçüncü modül de eklenebilir (sayı sınırı yok)", () => {
    const u = render(<AiHubScreen />);
    for (const ad of ["Yüz Ağrısı (FGS)", "Kedi Sesi", "Retikülosit"]) {
      fireEvent.press(baslik(u, ad));
    }
    for (const ad of ["Yüz Ağrısı (FGS)", "Kedi Sesi", "Retikülosit"]) {
      expect(acikMi(baslik(u, ad))).toBe(true);
    }
  });

  it("açık bir modüle tekrar dokunmak YALNIZ onu kapatır", () => {
    const u = render(<AiHubScreen />);
    fireEvent.press(baslik(u, "Yüz Ağrısı (FGS)"));
    fireEvent.press(baslik(u, "Kedi Sesi"));

    fireEvent.press(baslik(u, "Yüz Ağrısı (FGS)")); // kapat
    expect(acikMi(baslik(u, "Yüz Ağrısı (FGS)"))).toBe(false);
    expect(acikMi(baslik(u, "Kedi Sesi"))).toBe(true); // diğeri ETKİLENMEZ
  });
});
