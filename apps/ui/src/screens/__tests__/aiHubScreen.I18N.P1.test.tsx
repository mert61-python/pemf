// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI Hub (AiHubScreen) iki dilde. TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * Bölüm 1: modül ızgarası (ad / açıklama), karşılama (zengin metin), erişim etiketleri, araştırma eklentisi kapısı, semptom listesi.
 */
let mockMode: "veterinarian" | "researcher" | "pet_owner" = "veterinarian";
let mockResearch = true;
let mockFetchCevap: unknown = null;
let mockCompact: boolean | null = null; // null = gerçek kanca; true / false = düzen zorlanır
let mockHastaNo = 0; // her testte YENİ hasta kimliği → modül önbelleği (resetAiCachesForOwner) temizlenir
const mockApiPost = jest.fn(async (..._a: unknown[]): Promise<unknown> => null);
const mockShowToast = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => null),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockShowToast }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: mockMode, hasAiHub: mockMode !== "pet_owner" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operatorEmail: "v@x.com" }),
  useOperatorOptional: () => ({ operatorEmail: "v@x.com", operators: [] }),
}));
jest.mock("@/context/EntitlementContext", () => ({ useEntitlement: () => ({ research: mockResearch }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ navigate: jest.fn(), selectedPatient: { id: mockHastaNo, name: "Test Hasta" } }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionFresh: false }),
}));
jest.mock("@/components/domain/PatientGate", () => {
  const React = require("react");
  return { PatientGate: ({ children }: any) => React.createElement(React.Fragment, null, children) };
});
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-image-picker", () => ({
  MediaTypeOptions: { Images: "Images" },
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///kedi.jpg" }] })),
  launchCameraAsync: jest.fn(async () => ({ canceled: true })),
}));
jest.mock("expo-image-manipulator", () => ({
  SaveFormat: { JPEG: "jpeg" },
  manipulateAsync: jest.fn(async (uri: string) => ({ uri, base64: "QUJD" })),
}));
jest.mock("expo-document-picker", () => ({
  getDocumentAsync: jest.fn(async () => ({ canceled: false, assets: [{ name: "veri.csv", uri: "file:///veri.csv" }] })),
}));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(async () => "QUJD") }));
jest.mock("@/hooks/useResponsive", () => {
  const gercek = jest.requireActual("@/hooks/useResponsive");
  return { ...gercek, useResponsive: () => ({ ...gercek.useResponsive(), ...(mockCompact === null ? {} : { isCompact: mockCompact }) }) };
});
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
  mockHastaNo += 1;
  mockCompact = null;
  mockFetchCevap = null;
  (global as any).fetch = jest.fn(async () => ({ ok: true, status: 200, json: async () => mockFetchCevap }));
  mockApiPost.mockReset().mockResolvedValue(null);
  mockShowToast.mockReset();
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
    expect(en.getByLabelText("Tumor Phantom — research add-on required")).toBeTruthy();
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

describe("bölüm 3 — hastalık (XGBoost) modülü, AI Pro köprüsü metinleri", () => {
  const SEMPTOM_TR = ["İştah Kaybı", "Kusma", "İshal", "Öksürük", "Solunum Güçlüğü", "Topallık", "Deri Lezyonları", "Burun Akıntısı", "Göz Akıntısı", "Halsizlik / Uyuşukluk", "Kilo Kaybı", "Hapşırma", "Dehidrasyon", "Ateş"];
  const SEMPTOM_EN = ["Loss of appetite", "Vomiting", "Diarrhea", "Coughing", "Breathing difficulty", "Lameness", "Skin lesions", "Nasal discharge", "Eye discharge", "Weakness / Lethargy", "Weight loss", "Sneezing", "Dehydration", "Fever"];

  it("Türkçe: form / ipucu / semptom listesi / düğme göç öncesiyle aynı", () => {
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Hastalık"));
    expect(u.getByText("Kedi Hastalık Tahmini (XGBoost)")).toBeTruthy();
    for (const p of ["Yaş", "Kilo", "Nabız", "Ateş", "Süre"]) expect(u.getByPlaceholderText(p)).toBeTruthy();
    expect(u.getByLabelText("Kilo (kg)")).toBeTruthy();
    expect(u.getByLabelText("Nabız (atım/dk)")).toBeTruthy();
    expect(u.getByLabelText("Ateş (°C)")).toBeTruthy();
    expect(u.getByLabelText("Süre (gün)")).toBeTruthy();
    expect(
      u.getByText("En az 2 semptom seçmeniz yeterli. Nabız, ateş ve kilo girmek zorunlu değildir — ama girerseniz tahmin belirginleşir (ör. ateş/nabız yüksekse model daha spesifik hastalığa yönelir)."),
    ).toBeTruthy();
    for (const s of SEMPTOM_TR) expect(u.getByText(s)).toBeTruthy();
    expect(u.getByText("Teşhisi Başlat")).toBeTruthy();
  });

  it("İngilizce: form / ipucu / semptom listesi / düğme", async () => {
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Disease"));
    expect(u.getByText("Cat Disease Prediction (XGBoost)")).toBeTruthy();
    for (const p of ["Age", "Weight", "Heart rate", "Temperature", "Duration"]) expect(u.getByPlaceholderText(p)).toBeTruthy();
    expect(u.getByLabelText("Weight (kg)")).toBeTruthy();
    expect(u.getByLabelText("Heart rate (beats/min)")).toBeTruthy();
    expect(u.getByLabelText("Temperature (°C)")).toBeTruthy();
    expect(u.getByLabelText("Duration (days)")).toBeTruthy();
    for (const s of SEMPTOM_EN) expect(u.getByText(s)).toBeTruthy();
    expect(u.getByText("Start Diagnosis")).toBeTruthy();
  });

  it("doğrulama bildirimleri: en az 2 semptom + aralık dışı yaş — iki dilde", async () => {
    // Button aynı etikete 400 ms içinde ikinci basışı yutar (çift-tık koruması) → basışlar arası bekle
    const bas = async (u: ReturnType<typeof render>, etiket: string) => {
      await act(async () => {
        await new Promise((r) => setTimeout(r, 450));
        fireEvent.press(u.getByText(etiket));
      });
    };
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Hastalık"));
    await bas(tr, "Teşhisi Başlat");
    expect(mockShowToast).toHaveBeenLastCalledWith("Lütfen en az 2 semptom seçin.", "error");
    fireEvent.press(tr.getByText("Kusma"));
    fireEvent.press(tr.getByText("Öksürük"));
    fireEvent.changeText(tr.getByPlaceholderText("Yaş"), "99");
    await bas(tr, "Teşhisi Başlat");
    expect(mockShowToast).toHaveBeenLastCalledWith("Yaş geçersiz (0–40 aralığında olmalı).", "error");
    tr.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Disease"));
    await bas(en, "Start Diagnosis");
    expect(mockShowToast).toHaveBeenLastCalledWith("Please select at least 2 symptoms.", "error");
    fireEvent.press(en.getByText("Vomiting"));
    fireEvent.press(en.getByText("Coughing"));
    fireEvent.changeText(en.getByPlaceholderText("Age"), "99");
    await bas(en, "Start Diagnosis");
    expect(mockShowToast).toHaveBeenLastCalledWith("Age is invalid (must be between 0 and 40).", "error");
  });

  async function analizeGit(u: ReturnType<typeof render>, tani: string, semptomlar: string[], dugme: string) {
    mockApiPost.mockImplementation(async (yol: unknown) =>
      yol === "/ai/disease"
        ? { status: "success", results: [{ disease: "Panleukopenia", probability: 0.8 }], xai: { top_features: [{ feature: "Coughing_bin", attribution: 0.3 }, { feature: "Age", attribution: -0.1 }] } }
        : null,
    );
    fireEvent.press(u.getByLabelText(tani));
    for (const s of semptomlar) fireEvent.press(u.getByText(s));
    await act(async () => {
      fireEvent.press(u.getByText(dugme));
    });
  }
  const logCagrisi = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);

  it("Türkçe sonuç: başlık / yorum / XAI satırı; AI geçmişine giden kayıt TR", async () => {
    const u = render(<AiHubScreen />);
    await analizeGit(u, "Hastalık", ["Kusma", "Öksürük"], "Teşhisi Başlat");
    // getByText boşlukları tek boşluğa indirger (RNTL normalizer): ham değerdeki çift boşluk burada tek görünür
    expect(u.getByText(/En olası: Panleukopenia · %80$/)).toBeTruthy();
    expect(u.getByText("%80.0")).toBeTruthy(); // olasılık listesi: TR önek biçimi
    expect(u.getByText("🔍 Kararı sürükleyenler: Öksürük ↑ · Yaş ↓")).toBeTruthy();
    expect(u.getByText("Tüm olasılıklar (güvene göre)")).toBeTruthy();
    expect(u.getByText("ℹ️ Bu tahmin, girilmeyen vitaller için sağlıklı kedi ortalamaları (nabız ~140, ateş ~38.5°C, kilo ~4 kg) varsayılarak yapıldı. Gerçek ölçümleri girerseniz sonuç daha isabetli olur.")).toBeTruthy();
    const kayit = logCagrisi();
    expect(kayit).toHaveLength(1);
    expect(kayit[0].module).toBe("Hastalık Analizi");
    expect(String(kayit[0].summary)).toMatch(/\(%80\)$/);
  });

  it("İngilizce sonuç: yorum / XAI satırı İngilizce; AI geçmişine giden kayıt TR ile BAYT BAYT AYNI (veri dilden bağımsız)", async () => {
    const tr = render(<AiHubScreen />);
    await analizeGit(tr, "Hastalık", ["Kusma", "Öksürük"], "Teşhisi Başlat");
    const trKayit = logCagrisi()[0];
    tr.unmount();
    mockApiPost.mockReset();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await analizeGit(en, "Disease", ["Vomiting", "Coughing"], "Start Diagnosis");
    expect(en.getByText(/Most likely: Panleukopenia · 80%$/)).toBeTruthy();
    expect(en.getByText("80.0%")).toBeTruthy(); // EN sonek biçimi
    expect(en.getByText("🔍 Decision drivers: Coughing ↑ · Age ↓")).toBeTruthy();
    expect(en.getByText("All probabilities (by confidence)")).toBeTruthy();
    const enKayit = logCagrisi();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit.module);
    expect(enKayit[0].summary).toBe(trKayit.summary);
    expect(enKayit[0].module_id).toBe("disease");
  });
});

describe("bölüm 4 — görsel modüller (FGS / termal / segmentasyon / retikülosit) ve otonom biofeedback", () => {
  async function gorselAnaliz(u: ReturnType<typeof render>, modul: string, galeri: string, baslat: string, cevap: unknown) {
    mockFetchCevap = cevap;
    fireEvent.press(u.getByLabelText(modul));
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: galeri }));
    });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: baslat }));
    });
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  }
  const FGS = {
    status: "success", fgs_total: 4, detected: true, image_base64: "QUJD", hw_status: "updated", hw_params: { freq: 15, duty: 40 },
    raw_fgs: { action_units: { AU1_Ear_Position: { score: 1 }, AU2_Orbital_Tightening: { score: 0.5 }, AU3_Muzzle_Tension: { score: 0 }, AU4_Whisker_Position: { score: 1 }, AU5_Head_Position: { score: 0 } } },
  };
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);

  it("Türkçe: FGS modülü başlık / ipuçları / düğmeler / otonom anahtarı göç öncesiyle aynı", () => {
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Yüz Ağrısı (FGS)"));
    expect(u.getByText("Yüz Ağrısı Skoru (FGS)")).toBeTruthy();
    expect(u.getByText("YOLO-pose modeli ile yüzdeki kilit noktaları analiz eder.")).toBeTruthy();
    expect(u.getByText("📸 Doğru FGS analizi için fotoğraf ipuçları")).toBeTruthy();
    expect(u.getByText("• Kedinin yüzünü tam karşıdan, net ve yakın çekin")).toBeTruthy();
    expect(u.getByText("⚠️ Yanlış/bulanık fotoğraf hatalı sonuç verir. Yüz net tespit edilemezse uyarı gösterilir.")).toBeTruthy();
    expect(u.getByText("Görüntü seçilmedi")).toBeTruthy();
    for (const b of ["Galeriden Seç", "Fotoğraf Çek", "Canlı Kamera", "AI Analizini Başlat"]) expect(u.getByText(b)).toBeTruthy();
    expect(u.getByText("Otonom Biofeedback")).toBeTruthy();
    const dugme = u.getByLabelText("Otonom biofeedback");
    expect(dugme.props.accessibilityHint).toBe("Otonom sürüş yalnız Kontrol → AI Pro onay akışıyla başlar; bu ekran cihazı sürmez");
    expect(u.getByText("Kuyruklu · Pro+ anlık")).toBeTruthy();
    expect(u.getByLabelText("Kuyruklu işlem — Pro+ ile anlık")).toBeTruthy();
  });

  it("İngilizce: FGS modülü başlık / ipuçları / düğmeler / otonom anahtarı", async () => {
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Facial Pain (FGS)"));
    expect(u.getByText("Facial Pain Score (FGS)")).toBeTruthy();
    expect(u.getByText("Analyzes key facial landmarks with the YOLO-pose model.")).toBeTruthy();
    expect(u.getByText("📸 Photo tips for an accurate FGS analysis")).toBeTruthy();
    expect(u.getByText("• Photograph the cat's face straight on, close up and in focus")).toBeTruthy();
    expect(u.getByText("No image selected")).toBeTruthy();
    for (const b of ["Choose from Gallery", "Take Photo", "Live Camera", "Start AI Analysis"]) expect(u.getByText(b)).toBeTruthy();
    expect(u.getByText("Autonomous Biofeedback")).toBeTruthy();
    expect(u.getByLabelText("Autonomous biofeedback").props.accessibilityHint).toBe(
      "Autonomous drive starts only through the Control → AI Pro approval flow; this screen does not drive the device",
    );
    expect(u.getByText("Queued · instant with Pro+")).toBeTruthy();
  });

  it("FGS sonucu + cihaz sürülüyor durumu iki dilde; AI geçmişine giden kayıt TR ile BAYT BAYT AYNI", async () => {
    const tr = render(<AiHubScreen />);
    await gorselAnaliz(tr, "Yüz Ağrısı (FGS)", "Galeriden Seç", "AI Analizini Başlat", FGS);
    expect(tr.getByText(/Orta derece ağrı — FGS 4\/10$/)).toBeTruthy();
    expect(tr.getByText("• Kulak Pozisyonu: 1")).toBeTruthy();
    expect(tr.getByText("• Göz Kısma: 0.5")).toBeTruthy();
    expect(tr.getByText("⚡ Cihaz otonom olarak sürülüyor")).toBeTruthy();
    expect(tr.getByText("Frekans: 15.0 Hz · Şiddet: 40.0 %")).toBeTruthy();
    expect(tr.getByText("Durdurmak için Kontrol ekranındaki ACİL DURDUR'u kullanın.")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Yüz Ağrısı Skoru (FGS)");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await gorselAnaliz(en, "Facial Pain (FGS)", "Choose from Gallery", "Start AI Analysis", FGS);
    expect(en.getByText(/Moderate pain — FGS 4\/10$/)).toBeTruthy();
    expect(en.getByText("• Ear Position: 1")).toBeTruthy();
    expect(en.getByText("• Orbital Tightening: 0.5")).toBeTruthy();
    expect(en.getByText("⚡ The device is being driven autonomously")).toBeTruthy();
    expect(en.getByText("Frequency: 15.0 Hz · Intensity: 40.0 %")).toBeTruthy();
    expect(en.getByText("To stop, use EMERGENCY STOP on the Control screen.")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });

  it("cihaz SÜRÜLMEDİ nedenleri iki dilde (atlanan durumlar)", async () => {
    const durumlar: Array<[string, string, string]> = [
      ["skipped_session_active", "Başka bir seans zaten aktif — otonom sürüş atlandı.", "Another session is already active — autonomous drive skipped."],
      ["skipped_unauthenticated", "Uzaktan kimliksiz istekte otonom sürüş yapılmaz (güvenlik).", "Autonomous drive is not performed on a remote request without identity (security)."],
      ["skipped_no_detection", "Otonom sürüş atlandı (skipped_no_detection).", "Autonomous drive skipped (skipped_no_detection)."],
    ];
    for (const [hw, tr, en] of durumlar) {
      mockHastaNo += 1;
      const u = render(<AiHubScreen />);
      await gorselAnaliz(u, "Yüz Ağrısı (FGS)", "Galeriden Seç", "AI Analizini Başlat", { ...FGS, hw_status: hw });
      expect(u.getByText("⚠️ Cihaz SÜRÜLMEDİ")).toBeTruthy();
      expect(u.getByText(tr)).toBeTruthy();
      u.unmount();
      mockHastaNo += 1;
      await enYap();
      const v = render(<AiHubScreen />);
      await gorselAnaliz(v, "Facial Pain (FGS)", "Choose from Gallery", "Start AI Analysis", { ...FGS, hw_status: hw });
      expect(v.getByText("⚠️ Device NOT DRIVEN")).toBeTruthy();
      expect(v.getByText(en)).toBeTruthy();
      v.unmount();
      await act(async () => {
        await dilSec("tr", depo);
      });
    }
  });

  it("termal / segmentasyon / retikülosit sonuçları iki dilde", async () => {
    const termal = { status: "success", image_base64: "X", prediction: { label: "Sick", confidence: 0.953 }, girdi_dogrulama: { durum: "termal_paleti", dogrulandi: true, uyari: null } };
    const seg = { status: "success", cat_count: 2, image_base64: "X" };
    const ret = { status: "success", image_base64: "X", counts: { erythrocyte: 90, "punctate reticulocyte": 6, "aggregate reticulocyte": 4 } };
    mockHastaNo += 1;
    const tr = render(<AiHubScreen />);
    await gorselAnaliz(tr, "Termal", "Galeriden Seç", "AI Analizini Başlat", termal);
    expect(tr.getByText(/Termal anormallik · model güveni %95$/)).toBeTruthy();
    expect(tr.getByText("Termal Tespit: Hasta (Riskli) (Model güveni: %95.3 — modelin kendi tahminine güveni; doğruluk değildir)")).toBeTruthy();
    tr.unmount();
    mockHastaNo += 1;
    const tr2 = render(<AiHubScreen />);
    await gorselAnaliz(tr2, "Segmentasyon", "Galeriden Seç", "AI Analizini Başlat", seg);
    expect(tr2.getByText(/2 kedi tespit edildi$/)).toBeTruthy();
    expect(tr2.getByText("Tespit Edilen Kedi: 2")).toBeTruthy();
    tr2.unmount();
    mockHastaNo += 1;
    const tr3 = render(<AiHubScreen />);
    await gorselAnaliz(tr3, "Retikülosit", "Galeriden Seç", "AI Analizini Başlat", ret);
    expect(tr3.getByText(/Retikülosit oranı ~%10\.0$/)).toBeTruthy();
    expect(tr3.getByText("Eritrosit: 90")).toBeTruthy();
    expect(tr3.getByText("Noktalı Retikülosit: 6")).toBeTruthy();
    expect(tr3.getByText("Agrege Retikülosit: 4")).toBeTruthy();
    tr3.unmount();
    await enYap();
    mockHastaNo += 1;
    const en = render(<AiHubScreen />);
    await gorselAnaliz(en, "Thermal", "Choose from Gallery", "Start AI Analysis", termal);
    expect(en.getByText(/Thermal anomaly · model confidence 95%$/)).toBeTruthy();
    expect(en.getByText("Thermal Detection: Sick (At Risk) (Model confidence: 95.3% — the model's own confidence in its prediction; not accuracy)")).toBeTruthy();
    en.unmount();
    mockHastaNo += 1;
    const en2 = render(<AiHubScreen />);
    await gorselAnaliz(en2, "Segmentation", "Choose from Gallery", "Start AI Analysis", seg);
    expect(en2.getByText(/2 cats detected$/)).toBeTruthy();
    en2.unmount();
    mockHastaNo += 1;
    const en2b = render(<AiHubScreen />);
    await gorselAnaliz(en2b, "Segmentation", "Choose from Gallery", "Start AI Analysis", { ...seg, cat_count: 1 });
    expect(en2b.getByText(/1 cat detected$/)).toBeTruthy();
    en2b.unmount();
    mockHastaNo += 1;
    const en3 = render(<AiHubScreen />);
    await gorselAnaliz(en3, "Reticulocyte", "Choose from Gallery", "Start AI Analysis", ret);
    expect(en3.getByText(/Reticulocyte ratio ~10\.0%$/)).toBeTruthy();
    expect(en3.getByText("Erythrocytes: 90")).toBeTruthy();
  });
});

describe("bölüm 5 — Fantom Tümör modülü (araştırma)", () => {
  async function fantomAnaliz(u: ReturnType<typeof render>, modul: string, galeri: string, baslat: string, cevap: unknown) {
    mockFetchCevap = cevap;
    fireEvent.press(u.getByLabelText(modul));
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: galeri }));
    });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: baslat }));
    });
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  }
  const FANTOM = {
    status: "success", success: true, n_tumor: 2, mm_per_px: 0.5, method: "mm", image_base64: "QUJD",
    tumor_regions: [
      { tumor_id: "T1", centroid_cabin_mm: [1, 2, 3], E_cancer: 1.5, E_healthy: 0.5, D: [0.1, 0.2] },
      { centroid_cabin_mm: [4, 5, 6], D: [] },
    ],
  };
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);

  it("Türkçe: fantom modülü başlık / ipuçları / boy alanı / düğmeler göç öncesiyle aynı", () => {
    mockMode = "researcher";
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Fantom Tümör"));
    expect(u.getAllByText("Fantom Tümör Analizi").length).toBeGreaterThan(0);
    expect(u.getByText("Sentetik böbrek fantomundan mavi tümör odaklarını tespit eder; 3B konum + PEMF bobin/E-alan tahmini üretir.")).toBeTruthy();
    expect(u.getByText("📸 Fantom fotoğraf ipuçları")).toBeTruthy();
    expect(u.getByText("• Fantomu tam tepeden, net ve iyi aydınlatılmış çekin")).toBeTruthy();
    expect(u.getByText("• Yeşil bobin halkasının büyük kısmı kadrajda olsun — ölçek ondan gelir")).toBeTruthy();
    expect(u.getByText("• Fantom boyu (cm) yalnız halka ya da kabin işareti görünmüyorsa kullanılır")).toBeTruthy();
    expect(u.getByText("Fantom boyu (cm)")).toBeTruthy();
    expect(u.getByPlaceholderText("halka/işaret yoksa · ör. 10")).toBeTruthy();
    expect(u.getByText("Fantom Analizini Başlat")).toBeTruthy();
  });

  it("İngilizce: fantom modülü başlık / ipuçları / boy alanı / düğmeler", async () => {
    mockMode = "researcher";
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Tumor Phantom"));
    expect(u.getAllByText("Tumor Phantom Analysis").length).toBeGreaterThan(0);
    expect(u.getByText("Detects blue tumor foci in a synthetic kidney phantom; produces a 3D position + PEMF coil / E-field estimate.")).toBeTruthy();
    expect(u.getByText("📸 Phantom photo tips")).toBeTruthy();
    expect(u.getByText("• Photograph the phantom straight from above, sharp and well lit")).toBeTruthy();
    expect(u.getByText("• Most of the green coil ring should be in the frame — the scale comes from it")).toBeTruthy();
    expect(u.getByText("Phantom length (cm)")).toBeTruthy();
    expect(u.getByPlaceholderText("if no ring / marker · e.g. 10")).toBeTruthy();
    expect(u.getByText("Start Phantom Analysis")).toBeTruthy();
  });

  it("sonuç (mm kipi): özet / tümör başlıkları / köprü etiketi iki dilde; AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    await fantomAnaliz(tr, "Fantom Tümör", "Galeriden Seç", "Fantom Analizini Başlat", FANTOM);
    expect(tr.getByText(/2 tümör odağı bulundu$/)).toBeTruthy();
    // getByText boşlukları tek boşluğa indirger (RNTL normalizer)
    expect(tr.getByText("Tespit edilen tümör: 2 · Ölçek: 0.5 mm/px")).toBeTruthy();
    expect(tr.getByText("Tümör T1 · (1.0, 2.0, 3.0) mm")).toBeTruthy();
    expect(tr.getByText("Tümör 2 · (4.0, 5.0, 6.0) mm")).toBeTruthy();
    const kopru = tr.getByLabelText("Bu tümör için AI Pro seansı: Kontrol ekranına git");
    expect(kopru.props.accessibilityHint).toBe("Seans onaydan sonra başlar; bu düğme yalnız Kontrol ekranını açar");
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Fantom Tümör Analizi");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await fantomAnaliz(en, "Tumor Phantom", "Choose from Gallery", "Start Phantom Analysis", FANTOM);
    expect(en.getByText(/2 tumor foci found$/)).toBeTruthy();
    expect(en.getByText("Detected tumors: 2 · Scale: 0.5 mm/px")).toBeTruthy();
    expect(en.getByText("Tumor T1 · (1.0, 2.0, 3.0) mm")).toBeTruthy();
    expect(en.getByText("Tumor 2 · (4.0, 5.0, 6.0) mm")).toBeTruthy();
    const koprEn = en.getByLabelText("AI Pro session for this tumor: go to the Control screen");
    expect(koprEn.props.accessibilityHint).toBe("The session starts only after approval; this button only opens the Control screen.");
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });

  it("piksel kipi: ölçek notu ve 'piksel' iki dilde; tek tümör çoğulu", async () => {
    mockMode = "researcher";
    const piksel = { ...FANTOM, method: "pixel", n_tumor: 1, tumor_regions: [{ centroid_cabin_mm: [1, 2, 3], D: [] }] };
    const tr = render(<AiHubScreen />);
    await fantomAnaliz(tr, "Fantom Tümör", "Galeriden Seç", "Fantom Analizini Başlat", piksel);
    expect(tr.getByText("Tespit edilen tümör: 1 · Ölçek: piksel")).toBeTruthy();
    expect(
      tr.getByText("Ölçek yok (piksel kipi): koordinatlar piksel farkıdır; doz (D1–D7) ve E hesaplanmadı. Gerçek ölçek için fantom boyunu (cm) girip yeniden analiz edin."),
    ).toBeTruthy();
    tr.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await fantomAnaliz(en, "Tumor Phantom", "Choose from Gallery", "Start Phantom Analysis", piksel);
    expect(en.getByText(/1 tumor focus found$/)).toBeTruthy();
    expect(en.getByText("Detected tumors: 1 · Scale: pixel")).toBeTruthy();
    expect(
      en.getByText("No scale (pixel mode): coordinates are pixel differences; dose (D1–D7) and E were not calculated. Enter the phantom length (cm) for the real scale and re-run the analysis."),
    ).toBeTruthy();
  });
});

describe("bölüm 6 — Petri Kuyu modülü (araştırma)", () => {
  async function petriAnaliz(u: ReturnType<typeof render>, modul: string, galeri: string, baslat: string, cevap: unknown) {
    mockFetchCevap = cevap;
    fireEvent.press(u.getByLabelText(modul));
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: galeri }));
    });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: baslat }));
    });
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  }
  const PETRI = {
    status: "success", success: true, n_wells: 2, n_cancer: 1, n_healthy: 1, mm_per_px: 0.2, method: "mm", image_base64: "QUJD",
    wells: [
      { well_id: "A1", label: "cancer", centroid_cabin_mm: [1, 2, 3], cancer_reasons: ["mavi alan"], D: [0.1] },
      { well_id: "B2", label: "healthy", organ_id: 0, centroid_cabin_mm: [4, 5, 6], D: [] },
    ],
    yolo_ayar: { conf: 0.05, iou: 0.7 },
    resize: { max: 960, from: [4032, 3024], to: [960, 720] },
    plausibility: { guard: "off", thresholds: { circularity_med: 0.4 }, thresholds_default: { circularity_med: 0.55 } },
  };
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);

  it("Türkçe: petri modülü başlık / ipuçları / kip / gelişmiş ayarlar göç öncesiyle aynı", () => {
    mockMode = "researcher";
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Petri Kuyu"));
    expect(u.getAllByText("Petri Kuyu Analizi").length).toBeGreaterThan(0);
    expect(u.getByText("📸 Petri fotoğraf ipuçları")).toBeTruthy();
    expect(u.getByText("• Plakayı tam tepeden, dik ve yakın çekin — plaka karenin en az yarısını kaplasın")).toBeTruthy();
    expect(u.getByText("• Her deneyde bilinen bir boyalı ve bir sağlıklı kontrol kuyucuğu çekin (Gelişmiş ayarlar)")).toBeTruthy();
    // T3 · Y193 (sahip 2026-10-24: "sadece 24 kalsın"): kip seçici YOK
    expect(u.queryByLabelText("Petri analiz kipi")).toBeNull();
    expect(u.queryByLabelText("Tekil petri kapları")).toBeNull();
    expect(u.getByText("Ölçek plakanın kuyucuk aralığından (19,3 mm) gelir. Kabin işareti (ArUco) kadrajda değilse kuyucuk konumu PLAKA çerçevesindedir ve PEMF değerleri geçersiz sayılır.")).toBeTruthy();
    const ayar = u.getByLabelText("Gelişmiş araştırma ayarları");
    expect(ayar.props.accessibilityHint).toBe("Tespit ve denetim eşiklerini açar");
    expect(u.getByText("▸ ⚙️ Gelişmiş (araştırma) ayarları")).toBeTruthy();
    fireEvent.press(ayar);
    expect(u.getByLabelText("Gelişmiş araştırma ayarları").props.accessibilityHint).toBe("Ayarları kapatır");
    expect(u.getByText("Sağlıklı kontrol kuyucukları")).toBeTruthy();
    expect(u.getByPlaceholderText("ör. A1, D6")).toBeTruthy();
    expect(u.getByPlaceholderText("ör. B2")).toBeTruthy();
    expect(u.getByLabelText("A1 köşesi sol-üst")).toBeTruthy();
    expect(u.getByLabelText("A1 köşesi otomatik")).toBeTruthy();
    expect(u.getByText("Küçültme (uzun kenar, px)")).toBeTruthy();
    expect(u.getByPlaceholderText("varsayılan kapalı")).toBeTruthy();
    expect(u.getByLabelText("Petri değil denetimi")).toBeTruthy();
    expect(u.getByText("↺ Varsayılanlara dön")).toBeTruthy();
    expect(u.getByText("Kuyucuk yerlerini plakanın geometrisi belirler. Boş bıraktığınız alan varsayılanda kalır.")).toBeTruthy();
    expect(u.getByText("Kuyu skoru eşiği")).toBeTruthy();
    expect(u.getByLabelText("Kuyu skoru eşiği").props.placeholder).toBe("varsayılan 0.6");
    expect(u.queryByText("Tespit güveni (conf)")).toBeNull(); // T3 · Y193: plaka kipinde etkisiz alan arayüzde YOK
    expect(u.queryByText("Petri çapı (cm)")).toBeNull();
  });

  it("İngilizce: petri modülü başlık / ipuçları / kip / gelişmiş ayarlar", async () => {
    mockMode = "researcher";
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Well Plate"));
    expect(u.getAllByText("Well Plate Analysis").length).toBeGreaterThan(0);
    expect(u.getByText("📸 Well plate photo tips")).toBeTruthy();
    expect(u.getByText("• Photograph the plate from directly above, upright and close — the plate should fill at least half of the frame")).toBeTruthy();
    expect(u.getByText("• In every experiment, photograph one known stained and one healthy control well (Advanced settings)")).toBeTruthy();
    expect(u.queryByLabelText("Well plate analysis mode")).toBeNull(); // T3 · Y193
    expect(u.queryByLabelText("Single petri dishes")).toBeNull();
    const ayar = u.getByLabelText("Advanced research settings");
    expect(ayar.props.accessibilityHint).toBe("Opens the detection and verification thresholds");
    expect(u.getByText("▸ ⚙️ Advanced (research) settings")).toBeTruthy();
    fireEvent.press(ayar);
    expect(u.getByText("Healthy control wells")).toBeTruthy();
    expect(u.getByPlaceholderText("e.g. A1, D6")).toBeTruthy();
    expect(u.getByLabelText("A1 corner top-left")).toBeTruthy();
    expect(u.getByLabelText("A1 corner automatic")).toBeTruthy();
    expect(u.getByText("Downscaling (long side, px)")).toBeTruthy();
    expect(u.getByPlaceholderText("default off")).toBeTruthy();
    expect(u.getByLabelText("\"Not a petri dish\" check")).toBeTruthy();
    expect(u.getByText("↺ Reset to defaults")).toBeTruthy();
    expect(u.getByText("The plate geometry determines where the wells are. A field you leave empty stays at its default.")).toBeTruthy();
    expect(u.getByText("Well score threshold")).toBeTruthy();
    expect(u.getByLabelText("Well score threshold").props.placeholder).toBe("default 0.6");
    expect(u.queryByText("Detection confidence (conf)")).toBeNull();
  });

  it("ayar doğrulama bildirimleri iki dilde (sayı değil / aralık dışı); alan etiketi tablodan çevrilir", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Petri Kuyu"));
    fireEvent.press(tr.getByLabelText("Gelişmiş araştırma ayarları"));
    mockFetchCevap = null;
    await act(async () => {
      fireEvent.press(tr.getByRole("button", { name: "Galeriden Seç" }));
    });
    fireEvent.changeText(tr.getByLabelText("Kuyu skoru eşiği"), "abc");
    await act(async () => {
      fireEvent.press(tr.getByRole("button", { name: "Petri Analizini Başlat" }));
    });
    expect(mockShowToast).toHaveBeenLastCalledWith("Kuyu skoru eşiği: sayı girin (ör. 0.6).", "error");
    fireEvent.changeText(tr.getByLabelText("Kuyu skoru eşiği"), "5");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 450));
      fireEvent.press(tr.getByRole("button", { name: "Petri Analizini Başlat" }));
    });
    expect(mockShowToast).toHaveBeenLastCalledWith("Kuyu skoru eşiği: 0 – 1 aralığında olmalı (girilen 5).", "error");
    tr.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Well Plate"));
    fireEvent.press(en.getByLabelText("Advanced research settings"));
    await act(async () => {
      fireEvent.press(en.getByRole("button", { name: "Choose from Gallery" }));
    });
    fireEvent.changeText(en.getByLabelText("Well score threshold"), "abc");
    await act(async () => {
      fireEvent.press(en.getByRole("button", { name: "Start Well Plate Analysis" }));
    });
    expect(mockShowToast).toHaveBeenLastCalledWith("Well score threshold: enter a number (e.g. 0.6).", "error");
    fireEvent.changeText(en.getByLabelText("Well score threshold"), "5");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 450));
      fireEvent.press(en.getByRole("button", { name: "Start Well Plate Analysis" }));
    });
    expect(mockShowToast).toHaveBeenLastCalledWith("Well score threshold: must be between 0 and 1 (entered: 5).", "error");
  });

  it("sonuç: özet / kuyu satırları / gerekçe / etkin ayarlar / köprü iki dilde; AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    await petriAnaliz(tr, "Petri Kuyu", "Galeriden Seç", "Petri Analizini Başlat", PETRI);
    expect(tr.getByText(/2 kuyu · 1 kanser, 1 sağlıklı$/)).toBeTruthy();
    expect(tr.getByText(/1 kuyuda kanser sınıflandırıldı\. Her kuyu için 3B konum/)).toBeTruthy();
    expect(tr.getByText("Kuyu: 2 · Kanser: 1 · Sağlıklı: 1")).toBeTruthy();
    expect(tr.getByText("Ölçek: 0.2 mm/px")).toBeTruthy();
    expect(tr.getByText(/A1 · Kanser · \(1\.0, 2\.0, 3\.0\) mm — gerekçe: mavi alan$/)).toBeTruthy();
    expect(tr.getByText(/B2 · Sağlıklı · \(4\.0, 5\.0, 6\.0\) mm$/)).toBeTruthy();
    // T3 · Y193: tespit güveni arayüzden ayarlanmıyor → "conf" satırda YOK
    expect(tr.getByText(/^⚙️ Bu sonuç değiştirilmiş ayarlarla üretildi: küçültme 4032×3024 → 960×720 · denetim dairesellik .* · denetim KAPALI$/)).toBeTruthy();
    expect(tr.getByLabelText("Bu kuyu için AI Pro seansı: Kontrol ekranına git")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Petri Kuyu Analizi");
    expect(trKayit[0].summary).toBe("2 kuyu (1 kanser)");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await petriAnaliz(en, "Well Plate", "Choose from Gallery", "Start Well Plate Analysis", PETRI);
    expect(en.getByText(/2 wells · 1 cancer, 1 healthy$/)).toBeTruthy();
    expect(en.getByText(/Cancer was classified in 1 well\. A 3D position/)).toBeTruthy();
    expect(en.getByText("Wells: 2 · Cancer: 1 · Healthy: 1")).toBeTruthy();
    expect(en.getByText("Scale: 0.2 mm/px")).toBeTruthy();
    expect(en.getByText(/A1 · Cancer · \(1\.0, 2\.0, 3\.0\) mm — reason: mavi alan$/)).toBeTruthy();
    expect(en.getByText(/B2 · Healthy · \(4\.0, 5\.0, 6\.0\) mm$/)).toBeTruthy();
    expect(en.getByText(/^⚙️ This result was produced with changed settings: downscaling 4032×3024 → 960×720 · check circularity .* · check OFF$/)).toBeTruthy();
    expect(en.getByLabelText("AI Pro session for this well: go to the Control screen")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });
});

describe("bölüm 7 — Böbrek RNA (KIRC) ve Böbrek Hastalığı (CKD) modülleri (araştırma)", () => {
  const RNA = {
    status: "success", n_patients: 2,
    predictions: [
      { patient_id: "P1", prediction: "KIRC", confidence: 0.93, prob_KIRC: 0.93 },
      { patient_id: "P2", prediction: "other", confidence: 0.8, prob_KIRC: 0.2 },
    ],
    xai: [{ patient_id: "P1", top_genes: [{ gene: "VHL", attribution: 0.5 }, { gene: "EPAS1", attribution: -0.2 }] }],
  };
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);
  async function bos() {
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  }

  it("Türkçe: RNA modülü başlık / CSV formatı / düğmeler göç öncesiyle aynı", () => {
    mockMode = "researcher";
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Böbrek RNA"));
    expect(u.getAllByText("Böbrek RNA Analizi (KIRC)").length).toBeGreaterThan(0);
    expect(u.getByText("RNA-seq gen ekspresyon CSV'sinden böbrek renal clear cell karsinom (KIRC) sınıflandırması.")).toBeTruthy();
    expect(u.getByText("📄 CSV formatı")).toBeTruthy();
    expect(u.getByText("• Satır = hasta, sütun = 20531 gen (eğitim/TCGA sırasında)")).toBeTruthy();
    expect(u.getByText("• 1. sütun = hasta ID (metin)")).toBeTruthy();
    expect(u.getByText("CSV Seç")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Sürükleyen genleri göster (Integrated Gradients — en fazla 25 hasta)")).toBeTruthy();
    expect(u.getByText("RNA Analizini Başlat")).toBeTruthy();
  });

  it("İngilizce: RNA modülü başlık / CSV formatı / düğmeler", async () => {
    mockMode = "researcher";
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Kidney RNA"));
    expect(u.getAllByText("Kidney RNA Analysis (KIRC)").length).toBeGreaterThan(0);
    expect(u.getByText("📄 CSV format")).toBeTruthy();
    expect(u.getByText("• Row = patient, column = 20531 genes (as in training / TCGA)")).toBeTruthy();
    expect(u.getByText("• Column 1 = patient ID (text)")).toBeTruthy();
    expect(u.getByText("Choose CSV")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Show driver genes (Integrated Gradients — up to 25 patients)")).toBeTruthy();
    expect(u.getByText("Start RNA Analysis")).toBeTruthy();
  });

  it("RNA sonucu iki dilde (yüzde biçimi dile göre); AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    mockFetchCevap = RNA;
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Böbrek RNA"));
    await act(async () => {
      fireEvent.press(tr.getByRole("button", { name: "CSV Seç" }));
    });
    await act(async () => {
      fireEvent.press(tr.getByRole("button", { name: "RNA Analizini Başlat" }));
    });
    await bos();
    expect(tr.getByText(/1\/2 örnekte KIRC işareti$/)).toBeTruthy();
    expect(tr.getByText("Hasta sayısı: 2")).toBeTruthy();
    expect(tr.getByText("P1 · KIRC işareti")).toBeTruthy();
    expect(tr.getByText("P2 · KIRC değil")).toBeTruthy();
    expect(tr.getByText("Güven: %93.0 · KIRC olasılığı: %93.0")).toBeTruthy();
    expect(tr.getByText("🔍 Sürükleyen genler: VHL ↑ · EPAS1 ↓")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Böbrek RNA (KIRC)");
    expect(trKayit[0].summary).toBe("2 hasta");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Kidney RNA"));
    await act(async () => {
      fireEvent.press(en.getByRole("button", { name: "Choose CSV" }));
    });
    await act(async () => {
      fireEvent.press(en.getByRole("button", { name: "Start RNA Analysis" }));
    });
    await bos();
    expect(en.getByText(/KIRC marker in 1\/2 samples$/)).toBeTruthy();
    expect(en.getByText("Number of patients: 2")).toBeTruthy();
    expect(en.getByText("P1 · KIRC marker")).toBeTruthy();
    expect(en.getByText("P2 · Not KIRC")).toBeTruthy();
    expect(en.getByText("Confidence: 93.0% · KIRC probability: 93.0%")).toBeTruthy();
    expect(en.getByText("🔍 Driver genes: VHL ↑ · EPAS1 ↓")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });

  it("Türkçe + İngilizce: CKD formu (alan etiketleri / seçenekler / düğme) tablodan çevrilir", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Böbrek Hastalığı"));
    for (const e of ["Laboratuvar / Vital", "Bulgular", "Tansiyon (mmHg)", "İdrar öz.ağ.", "Kırmızı küre (mil/µL)", "Pus hücre kümesi", "Koroner arter hast.", "CKD Analizini Başlat"])
      expect(tr.getByText(e)).toBeTruthy();
    expect(tr.getAllByText("Hayır").length).toBe(5);
    expect(tr.getAllByText("Anormal").length).toBe(2);
    tr.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Kidney Disease"));
    for (const e of ["Laboratory / Vitals", "Findings", "Blood pressure (mmHg)", "Urine sp. gravity", "Red blood cells (mil/µL)", "Pus cell clumps", "Coronary artery dis.", "Start CKD Analysis"])
      expect(en.getByText(e)).toBeTruthy();
    expect(en.getAllByText("No").length).toBe(5);
    expect(en.getAllByText("Abnormal").length).toBe(2);
    expect(en.getAllByText("Absent").length).toBe(2);
  });

  it("CKD sonucu + SHAP satırı iki dilde; AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    const CKD = { status: "success", label: "ckd", prob_pct: 87, model: "ExtraTrees", xai: { top_features: [{ feature: "sc", attribution: 0.4 }] } };
    const doldur = async (u: ReturnType<typeof render>, modul: string, baslat: string) => {
      mockApiPost.mockImplementation(async (yol: unknown) => (yol === "/ai/disease/kidney" ? CKD : null));
      fireEvent.press(u.getByLabelText(modul));
      const girdiler = u.getAllByPlaceholderText("—");
      for (let i = 0; i < 6; i++) fireEvent.changeText(girdiler[i], String(i + 1));
      await act(async () => {
        fireEvent.press(u.getByText(baslat));
      });
      await bos();
    };
    const tr = render(<AiHubScreen />);
    await doldur(tr, "Böbrek Hastalığı", "CKD Analizini Başlat");
    expect(tr.getByText(/Kronik Böbrek Hastalığı olası · %87$/)).toBeTruthy();
    expect(tr.getByText(/Girilen klinik değerlere göre model %87 olasılıkla kronik böbrek hastalığına \(CKD\) işaret ediyor\./)).toBeTruthy();
    expect(tr.getByText("Model: ExtraTrees")).toBeTruthy();
    expect(tr.getByText("🔍 Kararı sürükleyenler: Kreatinin (mg/dL) ↑")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Böbrek Hastalığı (CKD)");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await doldur(en, "Kidney Disease", "Start CKD Analysis");
    expect(en.getByText(/Chronic kidney disease likely · 87%$/)).toBeTruthy();
    expect(en.getByText(/According to the entered clinical values, the model indicates chronic kidney disease \(CKD\) with 87% probability\./)).toBeTruthy();
    expect(en.getByText("Model: ExtraTrees")).toBeTruthy();
    expect(en.getByText("🔍 Decision drivers: Creatinine (mg/dL) ↑")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });
});

describe("bölüm 8 — Kedi Sesi modülü (veteriner)", () => {
  const SES = {
    status: "success", top_1_class: "Happy", top_1_prob: 0.7,
    top_k: [{ class: "Happy", prob: 0.7 }, { class: "Resting", prob: 0.2 }, { class: "Warning", prob: 0.1 }],
  };
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);
  async function sesAnaliz(u: ReturnType<typeof render>, modul: string, yukle: string, baslat: string) {
    mockFetchCevap = SES;
    fireEvent.press(u.getByLabelText(modul));
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: yukle }));
    });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: baslat }));
    });
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  }

  it("Türkçe: ses modülü başlık / ipuçları / düğmeler göç öncesiyle aynı", () => {
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Kedi Sesi"));
    expect(u.getAllByText("Kedi Sesi Analizi").length).toBeGreaterThan(0);
    expect(u.getByText("Kedi miyavından duygu/durum sınıflandırması (10 sınıf). Mikrofonla kaydet ya da ses dosyası yükle.")).toBeTruthy();
    expect(u.getByText("🎙️ İpuçları")).toBeTruthy();
    expect(u.getByText("• Kediye yakın, sessiz ortamda ~5 saniye kaydet")).toBeTruthy();
    expect(u.getByText("• Tek miyav/ses net olsun (arka plan gürültüsü az)")).toBeTruthy();
    expect(u.getByText("Ses seçilmedi")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Isı haritası üret (modelin dinlediği frekans/zaman bandı — analiz biraz uzar)")).toBeTruthy();
    expect(u.getByLabelText("Mel ısı haritası üret (Grad-CAM)")).toBeTruthy();
    expect(u.getByText("Ses Analizini Başlat")).toBeTruthy();
  });

  it("İngilizce: ses modülü başlık / ipuçları / düğmeler", async () => {
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Cat Sound"));
    expect(u.getAllByText("Cat Sound Analysis").length).toBeGreaterThan(0);
    expect(u.getByText("Emotion / state classification from a cat's meow (10 classes). Record with the microphone or upload an audio file.")).toBeTruthy();
    expect(u.getByText("🎙️ Tips")).toBeTruthy();
    expect(u.getByText("• Close to the cat, in a quiet place, record for ~5 seconds")).toBeTruthy();
    expect(u.getByText("No audio selected")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Generate heat map (the frequency / time band the model listened to — the analysis takes a bit longer)")).toBeTruthy();
    expect(u.getByLabelText("Generate mel heat map (Grad-CAM)")).toBeTruthy();
    expect(u.getByText("Start Sound Analysis")).toBeTruthy();
  });

  it("ses sonucu iki dilde (sınıf adı tablodan, yüzde biçimi dile göre); AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    const tr = render(<AiHubScreen />);
    await sesAnaliz(tr, "Kedi Sesi", "Ses Yükle", "Ses Analizini Başlat");
    expect(tr.getByText(/Mutlu ve Keyifli · %70$/)).toBeTruthy();
    expect(tr.getByText("En olası 3 durum")).toBeTruthy();
    expect(tr.getByText("1. Mutlu")).toBeTruthy();
    expect(tr.getByText("2. Dinlenme")).toBeTruthy();
    expect(tr.getByText("3. Uyarı")).toBeTruthy();
    expect(tr.getByText("%70")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Kedi Sesi");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await sesAnaliz(en, "Cat Sound", "Upload Audio", "Start Sound Analysis");
    expect(en.getByText(/Happy and Content · 70%$/)).toBeTruthy();
    expect(en.getByText("3 most likely states")).toBeTruthy();
    expect(en.getByText("1. Happy")).toBeTruthy();
    expect(en.getByText("2. Resting")).toBeTruthy();
    expect(en.getByText("3. Warning")).toBeTruthy();
    expect(en.getByText("70%")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });
  it("ses sonucu: dar ve geniş düzende yüzde biçimi (çubuk satırı) dile göre", async () => {
    for (const kompakt of [true, false]) {
      mockCompact = kompakt;
      mockHastaNo += 1;
      const tr = render(<AiHubScreen />);
      await sesAnaliz(tr, "Kedi Sesi", "Ses Yükle", "Ses Analizini Başlat");
      expect(tr.getByText("%70")).toBeTruthy();
      tr.unmount();
      mockHastaNo += 1;
      await enYap();
      const en = render(<AiHubScreen />);
      await sesAnaliz(en, "Cat Sound", "Upload Audio", "Start Sound Analysis");
      expect(en.getByText("70%")).toBeTruthy();
      en.unmount();
      await act(async () => {
        await dilSec("tr", depo);
      });
    }
  });
});

describe("bölüm 9 — Böbrek CT ve Böbrek Patoloji modülleri (araştırma)", () => {
  const CT = {
    status: "success", n_detections: 3, image_base64: "QUJD",
    class_counts: { "Kidney Stone": 1, "Kidney Cyst": 2, "Kidney": 2 },
    detections: [
      { class_name: "Kidney Stone", conf: 0.91, bbox_xyxy: [0, 0, 10, 10] },
      { class_name: "Kidney", conf: 0.89, bbox_xyxy: [0, 0, 5, 5] },
      { class_name: "Kidney", conf: 0.87, bbox_xyxy: [50, 0, 60, 5] },
    ],
  };
  const PATOLOJI = {
    status: "success", top_1_class: "grade2", top_1_prob: 0.6, image_base64: "QUJD",
    top_k: [{ class: "grade2", prob: 0.6 }, { class: "grade3", prob: 0.3 }, { class: "grade1", prob: 0.1 }],
  };
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);
  async function gorselAnaliz2(u: ReturnType<typeof render>, modul: string, galeri: string, baslat: string, cevap: unknown) {
    mockFetchCevap = cevap;
    fireEvent.press(u.getByLabelText(modul));
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: galeri }));
    });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: baslat }));
    });
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  }

  it("Türkçe: CT modülü başlık / ipuçları / düğmeler göç öncesiyle aynı", () => {
    mockMode = "researcher";
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Böbrek CT"));
    expect(u.getAllByText("Böbrek CT Analizi").length).toBeGreaterThan(0);
    expect(u.getByText("Böbrek CT görüntüsünde taş, kist ve böbrek dokusu tespiti (YOLOv8s).")).toBeTruthy();
    expect(u.getByText("🩻 CT görüntü ipuçları")).toBeTruthy();
    expect(u.getByText("• Kırmızı=taş, yeşil=böbrek, turuncu=kist olarak işaretlenir")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Isı haritası üret (tespit hedefli HiRes-CAM — modeli tespitlere götüren bölgeler)")).toBeTruthy();
    expect(u.getByText("CT Analizini Başlat")).toBeTruthy();
  });

  it("İngilizce: CT modülü başlık / ipuçları / düğmeler", async () => {
    mockMode = "researcher";
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Kidney CT"));
    expect(u.getAllByText("Kidney CT Analysis").length).toBeGreaterThan(0);
    expect(u.getByText("Detection of stones, cysts and kidney tissue in a kidney CT image (YOLOv8s).")).toBeTruthy();
    expect(u.getByText("🩻 CT image tips")).toBeTruthy();
    expect(u.getByText("• Red = stone, green = kidney, orange = cyst")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Generate heat map (detection-targeted HiRes-CAM — the regions that led the model to the detections)")).toBeTruthy();
    expect(u.getByText("Start CT Analysis")).toBeTruthy();
  });

  it("CT sonucu iki dilde (çoğul özet / bulgu çipi / tespit satırları / konum / yüzde); AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    await gorselAnaliz2(tr, "Böbrek CT", "Galeriden Seç", "CT Analizini Başlat", CT);
    expect(tr.getByText("Görüntüde 2 böbrek dokusu, 2 kist, 1 taş tespit edildi.")).toBeTruthy();
    expect(tr.getByText("⚠ 1 böbrek taşı + 2 kist bulgusu")).toBeTruthy();
    expect(tr.getByText("Böbrek Taşı: 1")).toBeTruthy();
    expect(tr.getByText("Böbrek Kisti: 2")).toBeTruthy();
    expect(tr.getByText("Böbrek (doku): 2")).toBeTruthy();
    expect(tr.getByText("1. Böbrek Taşı — güven %91")).toBeTruthy();
    expect(tr.getByText("2. Böbrek (görüntüde solda) — güven %89")).toBeTruthy();
    expect(tr.getByText("3. Böbrek (görüntüde sağda) — güven %87")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Böbrek CT");
    expect(trKayit[0].summary).toBe("3 tespit (taş:1 kist:2)");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await gorselAnaliz2(en, "Kidney CT", "Choose from Gallery", "Start CT Analysis", CT);
    expect(en.getByText("2 kidney tissues, 2 cysts, 1 stone detected in the image.")).toBeTruthy();
    expect(en.getByText("⚠ Finding: 1 kidney stone + 2 cysts")).toBeTruthy();
    expect(en.getByText("Kidney Stones: 1")).toBeTruthy();
    expect(en.getByText("Kidney Cysts: 2")).toBeTruthy();
    expect(en.getByText("Kidney (tissue): 2")).toBeTruthy();
    expect(en.getByText("1. Kidney Stone — confidence 91%")).toBeTruthy();
    expect(en.getByText("2. Kidney (on the left of the image) — confidence 89%")).toBeTruthy();
    expect(en.getByText("3. Kidney (on the right of the image) — confidence 87%")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });

  it("CT: tek tespit / üçten fazla aynı sınıf konumları ve boş sonuç iki dilde", async () => {
    mockMode = "researcher";
    const bos = { status: "success", n_detections: 0, class_counts: {}, detections: [], image_base64: "QUJD" };
    const uc = {
      status: "success", n_detections: 3, class_counts: { Kidney: 3 }, image_base64: "QUJD",
      detections: [{ class_name: "Kidney", conf: 0.9, bbox_xyxy: [0, 0, 2, 2] }, { class_name: "Kidney", conf: 0.8, bbox_xyxy: [10, 0, 12, 2] }, { class_name: "Kidney", conf: 0.7, bbox_xyxy: [20, 0, 22, 2] }],
    };
    const tr = render(<AiHubScreen />);
    await gorselAnaliz2(tr, "Böbrek CT", "Galeriden Seç", "CT Analizini Başlat", bos);
    expect(tr.getByText("Görüntüde böbrek yapısı tespit edilemedi.")).toBeTruthy();
    expect(tr.getByText("✓ Taş veya kist bulgusu yok")).toBeTruthy();
    tr.unmount();
    mockHastaNo += 1;
    const tr2 = render(<AiHubScreen />);
    await gorselAnaliz2(tr2, "Böbrek CT", "Galeriden Seç", "CT Analizini Başlat", uc);
    expect(tr2.getByText("2. Böbrek (soldan 2.) — güven %80")).toBeTruthy();
    tr2.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await gorselAnaliz2(en, "Kidney CT", "Choose from Gallery", "Start CT Analysis", bos);
    expect(en.getByText("No kidney structure could be detected in the image.")).toBeTruthy();
    expect(en.getByText("✓ No stone or cyst finding")).toBeTruthy();
    en.unmount();
    mockHastaNo += 1;
    const en2 = render(<AiHubScreen />);
    await gorselAnaliz2(en2, "Kidney CT", "Choose from Gallery", "Start CT Analysis", uc);
    expect(en2.getByText("2. Kidney (#2 from the left) — confidence 80%")).toBeTruthy();
  });

  it("Patoloji: TR + EN statik; sonuç (derece adı / yüzde / çubuklar); AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Böbrek Patoloji"));
    expect(tr.getAllByText("Böbrek Histopatoloji Analizi").length).toBeGreaterThan(0);
    expect(tr.getByText("• Grade 0 = en hafif, Grade 4 = en ileri histopatolojik derece")).toBeTruthy();
    expect(tr.getByText("Patoloji Analizini Başlat")).toBeTruthy();
    tr.unmount();
    mockHastaNo += 1;
    const tr2 = render(<AiHubScreen />);
    await gorselAnaliz2(tr2, "Böbrek Patoloji", "Galeriden Seç", "Patoloji Analizini Başlat", PATOLOJI);
    expect(tr2.getByText("Tahmin: Grade 2 · güven %60")).toBeTruthy();
    expect(tr2.getByText("Tüm dereceler")).toBeTruthy();
    expect(tr2.getByText("%30")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Böbrek Patoloji");
    tr2.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Kidney Pathology"));
    expect(en.getAllByText("Kidney Histopathology Analysis").length).toBeGreaterThan(0);
    expect(en.getByText("• Grade 0 = mildest, Grade 4 = most advanced histopathological grade")).toBeTruthy();
    expect(en.getByText("Start Pathology Analysis")).toBeTruthy();
    en.unmount();
    mockHastaNo += 1;
    const en2 = render(<AiHubScreen />);
    await gorselAnaliz2(en2, "Kidney Pathology", "Choose from Gallery", "Start Pathology Analysis", PATOLOJI);
    expect(en2.getByText("Prediction: Grade 2 · confidence 60%")).toBeTruthy();
    expect(en2.getByText("All grades")).toBeTruthy();
    expect(en2.getByText("30%")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });
});

describe("bölüm 10 — Yara Kapanma (Scratch) ve Kedi Organ modülleri", () => {
  const logKayitlari = () => mockApiPost.mock.calls.filter((c) => c[0] === "/ai/log").map((c) => c[1] as Record<string, unknown>);
  const bos = async () => {
    for (let i = 0; i < 12; i++)
      await act(async () => {
        await Promise.resolve();
      });
  };
  const SCRATCH = (pct: number, gap: number) => ({
    status: "success", closure: { closure_pct: pct, mean_gap_um: gap, max_gap_um: 200, gap_area_mm2: 1.5 }, n_cells: 30, coverage_ratio: 0.5, score_mean: 0.9, device: "cpu",
    closure_image_base64: "QQ==", seg_image_base64: "Qg==", input_image_base64: "Qw==",
  });
  const picker = () => (jest.requireMock("expo-document-picker") as { getDocumentAsync: jest.Mock }).getDocumentAsync;
  async function scratchAnaliz(u: ReturnType<typeof render>, dosyaAdi: string, cevap: unknown, sec: string, analiz: string) {
    mockFetchCevap = cevap;
    picker().mockResolvedValueOnce({ canceled: false, assets: [{ name: dosyaAdi, uri: "file:///" + dosyaAdi }] });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: sec }));
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 450)); // Button çift-tık koruması (aynı etikete 400 ms)
      fireEvent.press(u.getByText(analiz));
    });
    await bos();
  }

  it("Türkçe: scratch modülü başlık / yön / objektif / ısı haritası anahtarı göç öncesiyle aynı", () => {
    mockMode = "researcher";
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Yara Kapanma (Scratch)"));
    expect(u.getAllByText("Yara Kapanma (Scratch)").length).toBeGreaterThan(0);
    expect(u.getByText("CPN hücre segmentasyonu + TScratch kapanma metrikleri (araştırma verisi — hasta kaydı değildir).")).toBeTruthy();
    expect(u.getByText("Görüntü seç (.tif / .png / .jpg)")).toBeTruthy();
    expect(u.getByText("Yara yönü")).toBeTruthy();
    expect(u.getByText("Dikey")).toBeTruthy();
    expect(u.getByText("Yatay")).toBeTruthy();
    expect(u.getByText("Objektif (kalibrasyon)")).toBeTruthy();
    expect(u.getByText("pixel_mm = 0.0016 mm/px — çekimde kullanılan objektifi seçin (µm/mm² doğruluğu buna bağlı).")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Isı haritası üret (bölgesel model ilgisi — hücre-düzeyi değildir)")).toBeTruthy();
    expect(u.getByText("Analiz Et")).toBeTruthy();
  });

  it("İngilizce: scratch modülü başlık / yön / objektif / ısı haritası anahtarı", async () => {
    mockMode = "researcher";
    await enYap();
    const u = render(<AiHubScreen />);
    fireEvent.press(u.getByLabelText("Wound Closure (Scratch)"));
    expect(u.getByText("CPN cell segmentation + TScratch closure metrics (research data — not a patient record).")).toBeTruthy();
    expect(u.getByText("Choose image (.tif / .png / .jpg)")).toBeTruthy();
    expect(u.getByText("Wound direction")).toBeTruthy();
    expect(u.getByText("Vertical")).toBeTruthy();
    expect(u.getByText("Horizontal")).toBeTruthy();
    expect(u.getByText("Objective (calibration)")).toBeTruthy();
    expect(u.getByText("pixel_mm = 0.0016 mm/px — select the objective used for the capture (µm/mm² accuracy depends on it).")).toBeTruthy();
    expect(u.getByText("☐ 🔍 Generate heat map (regional model attention — not cell-level)")).toBeTruthy();
    expect(u.getByText("Analyze")).toBeTruthy();
  });

  it("scratch sonucu iki dilde (metrikler / galeri sekmeleri / karşılaştırma / yüzde); AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    mockMode = "researcher";
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Yara Kapanma (Scratch)"));
    await scratchAnaliz(tr, "a.png", SCRATCH(40, 100), "Görüntü seç (.tif / .png / .jpg)", "Analiz Et");
    expect(tr.getByText("%40")).toBeTruthy();
    expect(tr.getByText("100 µm")).toBeTruthy();
    expect(tr.getByText("Ort. gap")).toBeTruthy();
    expect(tr.getByText("Maks gap")).toBeTruthy();
    expect(tr.getByText("Hücre")).toBeTruthy();
    expect(tr.getByText("Gap alanı 1.5 mm² · coverage 0.5 · skor 0.9 · cihaz: cpu")).toBeTruthy();
    expect(tr.getAllByText("Kapanma").length).toBeGreaterThan(0);
    expect(tr.getByText("Segmentasyon")).toBeTruthy();
    expect(tr.getByText("Orijinal")).toBeTruthy();
    expect(tr.getByText("Sarı bant = ROI (yarayı içine alır) · kırmızı = maks gap hattı · mavi = ort. gap hattı")).toBeTruthy();
    expect(tr.getByText("ℹ Görsel içi sayımlar ROI bandına aittir; toplam hücre sayısı üstteki karttadır.")).toBeTruthy();
    await scratchAnaliz(tr, "b.png", SCRATCH(50, 90), "a.png", "Analiz Et");
    fireEvent.press(tr.getByText("⇄ Karşılaştır (son iki analiz)"));
    expect(tr.getByText("Δ +10.0 puan")).toBeTruthy();
    expect(tr.getByText("a %40 → b %50 · ort. gap 100→90 µm")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(2);
    expect(trKayit[0].module).toBe("Yara Kapanma (Scratch)");
    expect(trKayit[0].summary).toBe("Kapanma %40 · 30 hücre");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Wound Closure (Scratch)"));
    await scratchAnaliz(en, "a.png", SCRATCH(40, 100), "Choose image (.tif / .png / .jpg)", "Analyze");
    expect(en.getByText("40%")).toBeTruthy();
    expect(en.getByText("100 µm")).toBeTruthy();
    expect(en.getByText("Mean gap")).toBeTruthy();
    expect(en.getByText("Max gap")).toBeTruthy();
    expect(en.getByText("Cells")).toBeTruthy();
    expect(en.getByText("Gap area 1.5 mm² · coverage 0.5 · score 0.9 · device: cpu")).toBeTruthy();
    expect(en.getAllByText("Closure").length).toBeGreaterThan(0);
    expect(en.getByText("Segmentation")).toBeTruthy();
    expect(en.getByText("Original")).toBeTruthy();
    expect(en.getByText("Yellow band = ROI (encloses the wound) · red = max gap line · blue = mean gap line")).toBeTruthy();
    expect(en.getByText("ℹ The counts inside the image belong to the ROI band; the total cell count is on the card above.")).toBeTruthy();
    await scratchAnaliz(en, "b.png", SCRATCH(50, 90), "a.png", "Analyze");
    fireEvent.press(en.getByText("⇄ Compare (last two analyses)"));
    expect(en.getByText("Δ +10.0 pts")).toBeTruthy();
    expect(en.getByText("a 40% → b 50% · mean gap 100→90 µm")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(2);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });

  const ORGAN = {
    status: "success", n_organs: 2, pose_type: "epnp", pnp_residual_px: 1.2, image_base64: "QUJD",
    organs: [{ name: "kalp", reliability: 0.8, coord_cabin_cm: [1, 2, 3] }, { name: "akciger_sag", reliability: 0.3, coord_3d_cm: [4, 5, 6] }],
  };
  async function organAnaliz(u: ReturnType<typeof render>, modul: string, galeri: string, baslat: string, cevap: unknown) {
    mockFetchCevap = cevap;
    fireEvent.press(u.getByLabelText(modul));
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: galeri }));
    });
    await act(async () => {
      fireEvent.press(u.getByRole("button", { name: baslat }));
    });
    await bos();
  }

  it("Kedi Organ TR + EN statik: başlık / nasıl kullanılır (iki kalın düğme adı) / düğmeler", async () => {
    const tr = render(<AiHubScreen />);
    fireEvent.press(tr.getByLabelText("Kedi Organ"));
    expect(tr.getAllByText("Kedi Organ Lokalizasyonu").length).toBeGreaterThan(0);
    expect(tr.getByText("🐾 Nasıl kullanılır?")).toBeTruthy();
    expect(tr.getByText("• Galeriden Seç veya Fotoğraf Çek ile tek kare analiz edin")).toBeTruthy();
    expect(tr.getByText("• Canlı Kamera ile kediyi kadraja alın; organ haritası her birkaç saniyede güncellenir")).toBeTruthy();
    expect(tr.getByText("Organ Analizini Başlat")).toBeTruthy();
    tr.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    fireEvent.press(en.getByLabelText("Feline Organ"));
    expect(en.getAllByText("Feline Organ Localization").length).toBeGreaterThan(0);
    expect(en.getByText("🐾 How to use")).toBeTruthy();
    expect(en.getByText("• Analyze a single frame with Choose from Gallery or Take Photo")).toBeTruthy();
    expect(en.getByText("• Frame the cat with Live Camera; the organ map updates every few seconds")).toBeTruthy();
    expect(en.getByText("Start Organ Analysis")).toBeTruthy();
  });

  it("Kedi Organ sonucu iki dilde (çoğul başlık / organ adları / teknik satır / yüzde); AI geçmişi kaydı TR ile BAYT BAYT aynı", async () => {
    const tr = render(<AiHubScreen />);
    await organAnaliz(tr, "Kedi Organ", "Galeriden Seç", "Organ Analizini Başlat", ORGAN);
    expect(tr.getByText(/2 organ bulundu · en güvenilir: Kalp \(%80\)$/)).toBeTruthy();
    expect(tr.getByText("Teknik: poz epnp · PnP 1.2px")).toBeTruthy();
    expect(tr.getByText("Organlar (3B konum · güven)")).toBeTruthy();
    expect(tr.getByText("Kalp (1.0, 2.0, 3.0) cm")).toBeTruthy();
    expect(tr.getByText("Akciğer (sağ) (4.0, 5.0, 6.0) cm")).toBeTruthy();
    expect(tr.getByText("%80")).toBeTruthy();
    expect(tr.getByText("%30")).toBeTruthy();
    const trKayit = logKayitlari();
    expect(trKayit).toHaveLength(1);
    expect(trKayit[0].module).toBe("Kedi Organ");
    expect(trKayit[0].summary).toBe("2 organ lokalize");
    tr.unmount();
    mockApiPost.mockReset().mockResolvedValue(null);
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await organAnaliz(en, "Feline Organ", "Choose from Gallery", "Start Organ Analysis", ORGAN);
    expect(en.getByText(/2 organs found · most reliable: Heart \(80%\)$/)).toBeTruthy();
    expect(en.getByText("Technical: pose epnp · PnP 1.2px")).toBeTruthy();
    expect(en.getByText("Organs (3D position · confidence)")).toBeTruthy();
    expect(en.getByText("Heart (1.0, 2.0, 3.0) cm")).toBeTruthy();
    expect(en.getByText("Lung (right) (4.0, 5.0, 6.0) cm")).toBeTruthy();
    expect(en.getByText("80%")).toBeTruthy();
    expect(en.getByText("30%")).toBeTruthy();
    const enKayit = logKayitlari();
    expect(enKayit).toHaveLength(1);
    expect(enKayit[0].module).toBe(trKayit[0].module);
    expect(enKayit[0].summary).toBe(trKayit[0].summary);
  });

  it("Kedi Organ: tek organ çoğulu ve 'kedi bulunamadı' iki dilde; kayıt özeti TR kalır", async () => {
    const bir = { ...ORGAN, n_organs: 1, organs: [ORGAN.organs[0]] };
    const yok = { status: "success", n_organs: 0, organs: [], bulunamadi: "kedi_bulunamadi", image_base64: "QUJD" };
    const tr = render(<AiHubScreen />);
    await organAnaliz(tr, "Kedi Organ", "Galeriden Seç", "Organ Analizini Başlat", bir);
    expect(tr.getByText(/1 organ bulundu · en güvenilir: Kalp \(%80\)$/)).toBeTruthy();
    tr.unmount();
    mockHastaNo += 1;
    const tr2 = render(<AiHubScreen />);
    await organAnaliz(tr2, "Kedi Organ", "Galeriden Seç", "Organ Analizini Başlat", yok);
    expect(tr2.getByText(/Kedi bulunamadı$/)).toBeTruthy();
    const trKayit = logKayitlari().slice(-1)[0];
    expect(trKayit.summary).toBe("Kedi bulunamadı");
    tr2.unmount();
    mockHastaNo += 1;
    await enYap();
    const en = render(<AiHubScreen />);
    await organAnaliz(en, "Feline Organ", "Choose from Gallery", "Start Organ Analysis", bir);
    expect(en.getByText(/1 organ found · most reliable: Heart \(80%\)$/)).toBeTruthy();
    en.unmount();
    mockHastaNo += 1;
    const en2 = render(<AiHubScreen />);
    await organAnaliz(en2, "Feline Organ", "Choose from Gallery", "Start Organ Analysis", yok);
    expect(en2.getByText(/Cat not found$/)).toBeTruthy();
    expect(logKayitlari().slice(-1)[0].summary).toBe(trKayit.summary);
  });
});
