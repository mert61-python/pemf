// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI Hub (AiHubScreen) iki dilde. TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * Bölüm 1: modül ızgarası (ad / açıklama), karşılama (zengin metin), erişim etiketleri, araştırma eklentisi kapısı, semptom listesi.
 */
let mockMode: "veterinarian" | "researcher" | "pet_owner" = "veterinarian";
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
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockMode, hasAiHub: mockMode !== "pet_owner" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "v@x.com" }),
  useOperatorOptional: () => ({ operatorEmail: "v@x.com", operators: [] }),
}));
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
import i18n from "i18next";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
// anahtar türü katı → dinamik anahtar sınaması için gevşek çağrı (yalnız testte)
const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

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

describe("bölüm 2 — evcil hayvan sahibi ekranı (FGS + ses) ve ortak metinler", () => {
  it("Türkçe: göç öncesiyle aynı başlık / ipucu / düğme / ses kartı", () => {
    mockMode = "pet_owner";
    const u = render(<AiHubScreen />);
    expect(u.getByText("Akıllı Teşhis Asistanı")).toBeTruthy();
    expect(u.getByText("Dostunuzun fotoğrafını çekin, yapay zeka anında ağrı ve stres durumunu analiz etsin. Gerekirse veteriner hekiminize danışın.")).toBeTruthy();
    expect(u.getByText("📸 Net sonuç için")).toBeTruthy();
    expect(u.getByText("• Dostunuzun yüzünü tam karşıdan, yakın ve net çekin")).toBeTruthy();
    expect(u.getByText("• İyi ışık olsun; gözler, kulaklar ve bıyıklar görünsün")).toBeTruthy();
    expect(u.getByText("Kamerayı Aç")).toBeTruthy();
    expect(u.getByText("Galeriden Seç")).toBeTruthy();
    expect(u.getByText("Sesini Dinleyelim")).toBeTruthy();
    expect(u.getByText("Ses kaydedilmedi")).toBeTruthy();
    expect(u.getByText("Ses Yükle")).toBeTruthy();
    expect(u.getByText("Sesi Analiz Et")).toBeTruthy();
  });

  it("İngilizce: başlık / ipucu (zengin metin) / düğme / ses kartı", async () => {
    mockMode = "pet_owner";
    await enYap();
    const u = render(<AiHubScreen />);
    expect(u.getByText("Smart Diagnosis Assistant")).toBeTruthy();
    expect(u.getByText("Take a photo of your furry friend and let the AI instantly analyze their pain and stress level. If needed, consult your veterinarian.")).toBeTruthy();
    expect(u.getByText("📸 For a clear result")).toBeTruthy();
    expect(u.getByText("• Photograph your furry friend's face straight on, close up and in focus")).toBeTruthy();
    expect(u.getByText("• Use good lighting; eyes, ears and whiskers should be visible")).toBeTruthy();
    expect(u.getByText("Open Camera")).toBeTruthy();
    expect(u.getByText("Choose from Gallery")).toBeTruthy();
    expect(u.getByText("Let's Listen to Their Voice")).toBeTruthy();
    expect(u.getByText("No audio recorded")).toBeTruthy();
    expect(u.getByText("Upload Audio")).toBeTruthy();
    expect(u.getByText("Analyze Audio")).toBeTruthy();
  });

  // Sonuç / hata / öneri metinleri çalışma zamanında analiz sonucuyla çizilir → anahtar değerleri TR bayt bayt + EN dolu / Türkçe harfsiz
  const TR_DEGERLER: Record<string, string> = {
    "ai.hayvanSahibi.oneri.tespitYok": "Kedinin yüzü net tespit edilemedi. Lütfen yüzü net, iyi aydınlatılmış ve tam karşıdan çekilmiş bir fotoğrafla tekrar deneyin.",
    "ai.hayvanSahibi.oneri.agriYok": "Dostunuzun yüz hatlarında herhangi bir ağrı veya stres belirtisi görülmüyor. Oldukça rahat görünüyor!",
    "ai.hayvanSahibi.oneri.hafif": "Dostunuzda hafif bir rahatsızlık veya yorgunluk belirtisi olabilir. Bu durum geçici olabilir ancak gözlemlemeye devam edin. Belirtiler sürerse veteriner hekiminize danışın.",
    "ai.hayvanSahibi.oneri.orta": "Orta derecede ağrı veya stres belirtileri tespit edildi! Yüz hatlarında belirgin bir gerginlik var. Belirtiler 1-2 günden uzun sürerse veteriner hekiminize danışın.",
    "ai.hayvanSahibi.oneri.siddetli": "ŞİDDETLİ AĞRI BELİRTİSİ! Dostumuz ciddi bir rahatsızlık yaşıyor olabilir. Lütfen vakit kaybetmeden VETERİNER HEKİMİNİZE BAŞVURUN.",
    "ai.hayvanSahibi.sonucBaslik": "Yapay Zeka Analiz Sonucu",
    "ai.hayvanSahibi.agriSkoru": "Ağrı Skoru (FGS):",
    "ai.hayvanSahibi.klinikTelefonuYokBaslik": "Klinik telefonu ayarlı değil",
    "ai.hayvanSahibi.klinikTelefonuYokGovde": "Kayıt (hesap) bilgilerinde klinik acil telefonu girilmemiş.",
    "ai.hayvanSahibi.klinigiAra": "Veteriner Kliniğini Ara",
    "ai.ses.oneri.mutlu.baslik": "Mutlu ve Keyifli",
    "ai.ses.oneri.agri.metin": "Bu ses bir ağrı ya da rahatsızlık işareti olabilir. Dostunuzu yakından gözlemleyin; belirti sürerse veteriner hekiminize danışın.",
    "ai.ses.oneri.uyari.baslik": "Tedirgin / Uyarıyor",
    "ai.ses.mikrofonIzni": "Mikrofon izni gerekli.",
    "ai.ses.kayitBaslatilamadi": "Kayıt başlatılamadı (mikrofon?).",
    "ai.ses.kayitDurdurulamadi": "Kayıt durdurulamadı.",
    "ai.ses.guvenilirDegil": "⚠️ Bu sonuç güvenilir değil — kayıtta net bir kedi sesi ayırt edilemedi. Sessiz bir ortamda, mikrofonu yaklaştırıp tekrar kaydedin.",
    "ai.hata.baglanti": "Bağlantı hatası.",
    "ai.hata.analizSirasinda": "Analiz sırasında hata oluştu.",
    "ai.hata.hataIleti": "Hata: {{ileti}}",
    "ai.ortak.tibbiSorumlulukReddi": "⚠️ Bu yapay zeka sonucu yalnızca karar-destek amaçlıdır; veteriner hekim muayenesi ve teşhisinin yerine geçmez. Nihai karar hekime aittir.",
    "ai.xai.isiHaritasiSaglikli": "🔍 Isı haritası — modeli “Sağlıklı” kararına götüren bölgeler (kırmızı = bu karara güçlü katkı)",
    "ai.xai.isiHaritasiHasta": "🔍 Isı haritası — modeli “Hasta (Riskli)” kararına götüren bölgeler (kırmızı = bu karara güçlü katkı)",
    "ai.xai.isiHaritasiGenel": "🔍 Isı haritası — modelin baktığı bölgeler (kırmızı = karara güçlü etki)",
  };

  it("sonuç / hata / öneri metinleri: TR değerleri bayt bayt aynı", () => {
    for (const [k, v] of Object.entries(TR_DEGERLER)) expect(T(k)).toBe(v);
  });

  it("aynı anahtarlar İngilizce: dolu, Türkçe harf yok, yer tutucu korunur", async () => {
    await enYap();
    for (const k of Object.keys(TR_DEGERLER)) {
      const en = T(k, { ileti: "XYZ" });
      expect(en).not.toBe(k);
      expect(en).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/);
    }
    expect(T("ai.hata.hataIleti", { ileti: "boom" })).toBe("Error: boom");
    expect(T("ai.hayvanSahibi.oneri.siddetli")).toBe("SIGNS OF SEVERE PAIN! Your furry friend may be in serious distress. Please CONTACT YOUR VETERINARIAN WITHOUT DELAY.");
    expect(T("ai.xai.isiHaritasiHasta")).toContain("“Sick (At Risk)”");
  });
});
