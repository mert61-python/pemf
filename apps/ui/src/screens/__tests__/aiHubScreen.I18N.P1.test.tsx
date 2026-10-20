// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI Hub (AiHubScreen) iki dilde. TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * Bölüm 1: modül ızgarası (ad / açıklama), karşılama (zengin metin), erişim etiketleri, araştırma eklentisi kapısı, semptom listesi.
 */
let mockMode: "veterinarian" | "researcher" = "veterinarian";
let mockResearch = true;
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: jest.fn(async () => null),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockMode, hasAiHub: true }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "v@x.com" }) }));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: mockResearch }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: 1, name: "Test Hasta" } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

beforeEach(() => {
  mockMode = "veterinarian";
  mockResearch = true;
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

describe("bölüm 1 — modül ızgarası ve karşılama", () => {
  it("Türkçe: göç öncesiyle aynı başlık / karşılama / modül adı ve açıklaması", () => {
    const u = render(<AiHubScreen />);
    expect(u.getByText("Tanı Modülleri")).toBeTruthy();
    expect(u.getByText("👋 Nasıl çalışır?")).toBeTruthy();
    expect(
      u.getByText(
        "Bir modüle dokunun → hemen altında açılır; birden fazlasını aynı anda açık tutabilirsiniz. İhtiyaca göre fotoğraf/canlı kamera, ses ya da klinik değer girip analizi başlatın. Her modülün başında kısa bir kullanım ipucu var.",
      ),
    ).toBeTruthy();
    expect(u.getByText("ℹ️ İlk analiz model hazırlığından dolayı biraz uzun sürebilir. Sonuçlar bir ön-değerlendirmedir, kesin tanı değildir.")).toBeTruthy();
    expect(u.getByText("Yüz Ağrısı (FGS)")).toBeTruthy();
    expect(u.getByText("YOLO-pose ile yüz ağrı skoru")).toBeTruthy();
    expect(u.getByText("Organ 3B lokalizasyon (10 organ)")).toBeTruthy();
    expect(u.getByLabelText("Yüz Ağrısı (FGS)").props.accessibilityHint).toBe("Açmak için dokunun");
  });

  it("İngilizce: başlık / karşılama / modül adı ve açıklaması / erişim ipucu; açınca 'Tap to close'", async () => {
    await enYap();
    const u = render(<AiHubScreen />);
    expect(u.getByText("Diagnosis Modules")).toBeTruthy();
    expect(u.getByText("👋 How it works")).toBeTruthy();
    expect(
      u.getByText(
        "Tap a module → it opens right below; you can keep several open at the same time. Depending on what you need, use a photo or the live camera, audio or clinical values, then start the analysis. Each module begins with a short usage tip.",
      ),
    ).toBeTruthy();
    expect(u.getByText("ℹ️ The first analysis may take a little longer while the model warms up. Results are a preliminary assessment, not a definitive diagnosis.")).toBeTruthy();
    expect(u.getByText("Facial Pain (FGS)")).toBeTruthy();
    expect(u.getByText("Facial pain score using YOLO-pose")).toBeTruthy();
    expect(u.getByText("3D organ localization (10 organs)")).toBeTruthy();
    const dugme = u.getByLabelText("Facial Pain (FGS)");
    expect(dugme.props.accessibilityHint).toBe("Tap to open");
    fireEvent.press(dugme);
    expect(u.getByLabelText("Facial Pain (FGS)").props.accessibilityHint).toBe("Tap to close");
  });

  it("araştırma modu, eklenti yok: kapı etiketi ve rozet iki dilde (TR bayt bayt aynı)", async () => {
    mockMode = "researcher";
    mockResearch = false;
    const tr = render(<AiHubScreen />);
    expect(tr.getByLabelText("Fantom Tümör — araştırma eklentisi gerekli")).toBeTruthy();
    expect(tr.getAllByText("Eklenti").length).toBeGreaterThan(0);
    expect(tr.getAllByLabelText("Araştırma eklentisi gerekli").length).toBeGreaterThan(0);
    tr.unmount();
    await enYap();
    const en = render(<AiHubScreen />);
    expect(en.getByLabelText("Phantom Tumor — research add-on required")).toBeTruthy();
    expect(en.getAllByText("Add-on").length).toBeGreaterThan(0);
    expect(en.getAllByLabelText("Research add-on required").length).toBeGreaterThan(0);
  });
});
