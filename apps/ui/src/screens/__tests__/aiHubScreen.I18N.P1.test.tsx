// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI Hub (AiHubScreen) iki dilde. TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * Bölüm 1: modül ızgarası (ad / açıklama), karşılama (zengin metin), erişim etiketleri, araştırma eklentisi kapısı, semptom listesi.
 */
let mockMode: "veterinarian" | "researcher" | "pet_owner" = "veterinarian";
let mockResearch = true;
let mockFetchCevap: unknown = null;
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
