// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI Pro bileşenleri (AiProPanel, AiSpecApprovalModal, AiReviewControls, PemfKapisiKutusu, TakipGrafigi, aipro/*) iki dilde.
 * TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade. ⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz).
 * Kritik: sürüş / seans / bobin metinleri (kritik-anahtarlar.json) iki dilde ölçülür; veriye giden değerler dilden bağımsız kalır.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

let mockDurum: Record<string, unknown> = { active: false, localized: false };
let mockEnvanter: unknown = { moduller: [] };
let mockOneri: unknown = { proposalId: "p1", specs: {}, meta: {} };
let mockStop: unknown = null;
let mockBos: string[] = []; // bu yollara giden komutlar sunucuya "ulaşmaz" (apiPost null döner)
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) => (yol === "/ai/hazirlik" ? mockEnvanter : mockDurum)),
  apiPost: jest.fn(async (yol: string) => {
    if (mockBos.includes(yol)) return null;
    if (yol === "/ai/pro/propose") return mockOneri;
    if (yol === "/ai/pro/stop") return mockStop;
    return { status: "success" };
  }),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => false),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: undefined, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { apiPost, platformAlert, platformConfirm } from "@/services/apiClient";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

import { AiProPanel } from "../AiProPanel";
import { AiReviewControls, ReviewBadge, kaydedilemediMetni, reviewEtiketi } from "../AiReviewControls";
import { AiSpecApprovalModal } from "../AiSpecApprovalModal";
import { PemfKapisiKutusu } from "../PemfKapisiKutusu";
import { TakipGrafigi } from "../TakipGrafigi";
import { modelProfili } from "../aiProProfilleri";
import { AdimGostergesi } from "../aipro/AdimGostergesi";
import { HedefHalkalari, HedefListesi } from "../aipro/HedefSecici";
import { KalibrasyonRozeti } from "../aipro/KalibrasyonRozeti";
import { ModelSecimKartlari } from "../aipro/ModelSecimKartlari";

const depo = { setItem: async () => undefined };
const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

beforeEach(() => {
  jest.useFakeTimers();
  mockDurum = { active: false, localized: false };
  mockEnvanter = { moduller: [] };
  mockOneri = { proposalId: "p1", specs: {}, meta: {} };
  mockStop = null;
  mockBos = [];
  (apiPost as jest.Mock).mockClear();
  (platformAlert as jest.Mock).mockClear();
  (platformConfirm as jest.Mock).mockClear();
});
afterEach(async () => {
  jest.useRealTimers();
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

/** Ağaçtaki TÜM metin düğümlerini sırayla birleştirir (iç içe <Text> / Trans parçaları tek cümle olur). */
function metin(u: ReturnType<typeof render>): string {
  const topla = (n: any): string => {
    if (n == null) return "";
    if (typeof n === "string") return n;
    if (Array.isArray(n)) return n.map(topla).join("");
    return topla(n.children);
  };
  return topla(u.toJSON());
}
async function ilerlet(n = 2) {
  for (let i = 0; i < n; i++) {
    await act(async () => {
      jest.advanceTimersByTime(3000);
      await Promise.resolve();
    });
  }
}
async function panelCiz(ekstra: Record<string, unknown> = {}) {
  const u = render(<AiProPanel patientName="Tekir" {...ekstra} />);
  await act(async () => {});
  return u;
}
async function arastirmaPanel(ekstra: Record<string, unknown> = {}) {
  mockEnvanter = {
    moduller: [
      { modul: "em_fantom", hazir: true },
      { modul: "em_petri", hazir: true },
      { modul: "petri_yolo", hazir: true },
    ],
  };
  const u = render(<AiProPanel patientName="Örnek-1" secilebilirModeller={["fantom", "petri"]} kullaniciKipi="researcher" {...ekstra} />);
  await act(async () => {});
  return u;
}

describe("AiProPanel — kedi hattı", () => {
  it("TR: göç öncesiyle aynı etiketler, şerit ve tablo başlıkları", async () => {
    const u = await panelCiz();
    for (const s of [
      "🧠 Hedef Organ",
      "Tüm Vücut",
      "Mide",
      "Böbrek",
      "Bağırsak",
      "⏱ Süre (dk)",
      "Kalan",
      "🎯 Yeniden Konumla",
      "📊 Bobin Diagnostiği",
      "Bobin",
      "Frekans",
      "Duty",
      "Faz",
      "Organ",
      "Güven",
      "X (mm)",
      "🚀 AI Pro Başlat (1Hz DDS)",
      "AI Pro durdu.",
      "📷 Sunucu kamerasından canlı otonom seans: kedi organ lokalizasyonu → em_kedi → 7 bobin.",
    ]) {
      expect(u.getAllByText(s).length).toBeGreaterThan(0);
    }
    expect(u.getByLabelText("Hedef organ: Mide")).toBeTruthy();
    expect(u.getByLabelText("AI Pro otonom seansı başlat").props.accessibilityHint).toBe("Kamera kapalı-döngüsüyle bobinleri otomatik sürer");
    expect(u.getByLabelText("Hedef organı yeniden konumla")).toBeTruthy();
  });

  it("EN: etiketler, şerit, organ adları ve düğme ipuçları", async () => {
    await enYap();
    const u = await panelCiz();
    for (const s of [
      "🧠 Target Organ",
      "Whole Body",
      "Stomach",
      "Kidney",
      "Intestine",
      "⏱ Duration (min)",
      "Remaining",
      "🎯 Re-locate",
      "📊 Coil Diagnostics",
      "Coil",
      "Frequency",
      "Duty",
      "Phase",
      "Organ",
      "Confidence",
      "X (mm)",
      "🚀 Start AI Pro (1Hz DDS)",
      "AI Pro stopped.",
      "📷 Live autonomous session from the server camera: cat organ localization → em_kedi → 7 coils.",
    ]) {
      expect(u.getAllByText(s).length).toBeGreaterThan(0);
    }
    expect(u.getByLabelText("Target organ: Stomach")).toBeTruthy();
    expect(u.getByLabelText("Start the AI Pro autonomous session").props.accessibilityHint).toBe(
      "Drives the coils automatically with the camera closed loop",
    );
    expect(u.getByLabelText("Re-locate the target organ")).toBeTruthy();
    expect(u.queryByText(/[çğıöşüÇĞİÖŞÜ]/)).toBeNull();
  });

  it("KRİTİK: sürüş kapalı — neden + eylem ve düğme etiketi iki dilde (TR birebir, EN doğru)", async () => {
    mockDurum = { active: false, kediAiProSurusAcik: false };
    let u = await panelCiz();
    expect(u.getByLabelText("AI Pro analiz ve öneri — kedi sürüşü kapalı").props.accessibilityHint).toBe(
      "Organı konumlar ve doz önerisi hazırlar; bobin sürmez",
    );
    expect(
      u.getAllByText(
        "Kedi AI Pro sürüşü, kabin konumu doğrulanana kadar kapalı. Analizi ve öneriyi inceleyebilirsiniz; seansı Kontrol ekranından elle başlatın.",
      ).length,
    ).toBeGreaterThan(0);
    expect(u.getAllByText("🔎 Analiz ve Öneri (sürüş kapalı)").length).toBeGreaterThan(0);
    u.unmount();
    await enYap();
    u = await panelCiz();
    expect(u.getByLabelText("AI Pro analysis and recommendation — cat driving is off").props.accessibilityHint).toBe(
      "Locates the organ and prepares a dose recommendation; no coil is driven",
    );
    expect(
      u.getAllByText(
        "Cat AI Pro driving is off until the cabin position is verified. You can review the analysis and the recommendation; start the session manually from the Control screen.",
      ).length,
    ).toBeGreaterThan(0);
    expect(u.getAllByText("🔎 Analysis and Recommendation (driving off)").length).toBeGreaterThan(0);
  });

  it("KRİTİK: durdurma komutu ulaşmadı → uyarı (ACİL DURDUR yönlendirmesiyle) iki dilde; istek gövdesi dilden bağımsız", async () => {
    mockDurum = { active: true, organId: 2, remainingSec: 60 };
    let u = await panelCiz();
    await ilerlet(1);
    await act(async () => {
      fireEvent.press(u.getByLabelText("AI Pro otonom seansı durdur"));
    });
    await act(async () => {});
    expect(platformAlert).toHaveBeenLastCalledWith(
      "Durdurulamadı",
      "Otonom seans durdurma komutu sunucuya ulaşmadı. Bağlantıyı kontrol edip tekrar deneyin; sorun sürerse ACİL DURDUR kullanın.",
    );
    const trCagri = (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop").map((c) => JSON.stringify(c.slice(1)));
    u.unmount();
    (apiPost as jest.Mock).mockClear();
    (platformAlert as jest.Mock).mockClear();
    await enYap();
    u = await panelCiz();
    await ilerlet(1);
    expect(u.getByLabelText("Stop the AI Pro autonomous session").props.accessibilityHint).toBe("Stops the coils");
    await act(async () => {
      fireEvent.press(u.getByLabelText("Stop the AI Pro autonomous session"));
    });
    await act(async () => {});
    expect(platformAlert).toHaveBeenLastCalledWith(
      "Could not be stopped",
      "The autonomous session stop command did not reach the server. Check the connection and try again; if the problem continues, use EMERGENCY STOP.",
    );
    const enCagri = (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/stop").map((c) => JSON.stringify(c.slice(1)));
    expect(enCagri).toEqual(trCagri); // veriye giden gövde: EN iken TR ile bayt bayt aynı
  });

  it("hastasız başlatma onayı iki dilde; sözlük terimi (Hasta / patient) cümleye girer", async () => {
    let u = render(<AiProPanel />);
    await act(async () => {});
    await act(async () => {
      fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat"));
    });
    expect(platformConfirm).toHaveBeenLastCalledWith(
      "Hasta seçilmedi",
      "Otonom seansı hiçbir hastaya bağlanmadan kaydedilecek; seans geçmişinde sahipsiz görünür.\n\nYine de başlatmak istiyor musunuz?",
      "Hastasız başlat",
    );
    u.unmount();
    (platformConfirm as jest.Mock).mockClear();
    await enYap();
    u = render(<AiProPanel />);
    await act(async () => {});
    await act(async () => {
      fireEvent.press(u.getByLabelText("Start the AI Pro autonomous session"));
    });
    expect(platformConfirm).toHaveBeenLastCalledWith(
      "Patient not selected",
      "The autonomous session will be saved without being linked to any patient; it will appear without an owner in the session history.\n\nDo you still want to start it?",
      "Start without a patient",
    );
  });

  it("güven dökümü + hat kalitesi: TR ondalık virgül, EN ondalık nokta; tavan / maske yüzdeleri", async () => {
    const bilesen = {
      pose_confidence: 0.7,
      depth_factor: 0.95,
      mask_factor: 0.8,
      uncertainty_factor: 0.93,
      calibration_cap: 0.25,
      pnp_hata_cm: 2.58,
      ayna_uyarisi: true,
      anatomik_gecti: false,
    };
    mockDurum = { active: false, localized: true, reliability: 0.62, guvenDokumu: bilesen };
    let u = await panelCiz();
    await ilerlet(2);
    const tr = String(u.getByText(/Güven dökümü:/).props.children);
    expect(tr).toBe(
      "Güven dökümü: poz %70 × derinlik 0,95 × maske-dışı ×0,6 × belirsizlik 0,93 · ⚠️ kalibrasyonsuz — tavan %25" +
        " · PnP uyum hatası ≈ 2,6 cm" +
        " · ⚠️ sağ-sol (ayna) belirsizliği — kamerayı biraz çevirip açıyı değiştirin" +
        " · ⚠️ anatomik tutarsızlık — organ yerleşimi doğrulanamadı; açıyı değiştirip yeniden konumlayın",
    );
    u.unmount();
    await enYap();
    u = await panelCiz();
    await ilerlet(2);
    const en = String(u.getByText(/Confidence breakdown:/).props.children);
    expect(en).toBe(
      "Confidence breakdown: pose 70% × depth 0.95 × outside-mask ×0.6 × uncertainty 0.93 · ⚠️ uncalibrated — cap 25%" +
        " · PnP fit error ≈ 2.6 cm" +
        " · ⚠️ left-right (mirror) ambiguity — turn the camera slightly to change the angle" +
        " · ⚠️ anatomical inconsistency — the organ placement could not be verified; change the angle and re-locate",
    );
  });

  it("hazırlık şeridi (kedi): hayvan aranıyor → hayvan görünüyor aşamaları iki dilde (organ adı dile göre)", async () => {
    const kos = async (baslatEtiketi: string) => {
      mockDurum = { active: false, localized: false };
      const u = await panelCiz();
      await act(async () => {
        fireEvent.press(u.getByLabelText(baslatEtiketi));
      });
      await ilerlet(1);
      const ilk = metin(u);
      mockDurum = { active: false, localized: false, catDetected: true };
      await ilerlet(2);
      return { ilk, ikinci: metin(u), u };
    };
    let r = await kos("AI Pro otonom seansı başlat");
    expect(r.ilk).toContain("🐾 Hayvan aranıyor… kamerayı hastaya doğrultun");
    expect(r.ikinci).toContain("🔎 Hayvan görünüyor, Tüm Vücut aranıyor… (kamerayı biraz çevirin)");
    r.u.unmount();
    await enYap();
    r = await kos("Start the AI Pro autonomous session");
    expect(r.ilk).toContain("🐾 Looking for the animal… point the camera at the patient");
    expect(r.ikinci).toContain("🔎 The animal is visible, looking for Whole Body… (turn the camera slightly)");
  });
  it("KRİTİK: organ değiştirme / yeniden konumlama / hazırlık komutu ulaşmadı → uyarılar iki dilde", async () => {
    mockBos = ["/ai/pro/organ", "/ai/pro/calibrate", "/ai/pro/hazirlik/baslat"];
    const kos = async (organEtiketi: string, konumlaEtiketi: string, baslatEtiketi: string) => {
      const u = await panelCiz();
      await act(async () => {
        fireEvent.press(u.getByLabelText(organEtiketi));
      });
      await act(async () => {});
      const organUyari = (platformAlert as jest.Mock).mock.calls.pop();
      await act(async () => {
        fireEvent.press(u.getByLabelText(konumlaEtiketi));
      });
      await act(async () => {});
      const konumUyari = (platformAlert as jest.Mock).mock.calls.pop();
      await act(async () => {
        fireEvent.press(u.getByLabelText(baslatEtiketi));
      });
      await act(async () => {});
      return { organUyari, konumUyari, m: metin(u), u };
    };
    let r = await kos("Hedef organ: Mide", "Hedef organı yeniden konumla", "AI Pro otonom seansı başlat");
    expect(r.organUyari).toEqual(["Organ değiştirilemedi", "Komut sunucuya ulaşmadı — tekrar deneyin."]);
    expect(r.konumUyari).toEqual(["Yeniden konumlandırılamadı", "Komut sunucuya ulaşmadı — tekrar deneyin."]);
    expect(r.m).toContain("⚠️ Hazırlık komutu sunucuya ulaşmadı — bağlantıyı kontrol edip tekrar deneyin.");
    r.u.unmount();
    await enYap();
    (platformAlert as jest.Mock).mockClear();
    r = await kos("Target organ: Stomach", "Re-locate the target organ", "Start the AI Pro autonomous session");
    expect(r.organUyari).toEqual(["Could not change the organ", "The command did not reach the server — try again."]);
    expect(r.konumUyari).toEqual(["Could not re-locate", "The command did not reach the server — try again."]);
    expect(r.m).toContain("⚠️ The preparation command did not reach the server — check the connection and try again.");
  });

  it("KRİTİK: sunucu kamerası başlatılamadı uyarısı (başlık dile göre; sunucunun hata metni AYNEN)", async () => {
    const dene = async (baslatEtiketi: string) => {
      mockDurum = { active: false, localized: false };
      const u = await panelCiz();
      await act(async () => {
        fireEvent.press(u.getByLabelText(baslatEtiketi));
      });
      mockDurum = { active: false, localized: false, hazirlikHata: "Kamera açılamadı (sunucu)" };
      await ilerlet(1);
      const c = (platformAlert as jest.Mock).mock.calls.pop();
      u.unmount();
      return c;
    };
    expect(await dene("AI Pro otonom seansı başlat")).toEqual(["Sunucu kamerası başlatılamadı", "Kamera açılamadı (sunucu)"]);
    await enYap();
    expect(await dene("Start the AI Pro autonomous session")).toEqual(["The server camera could not be started", "Kamera açılamadı (sunucu)"]);
  });
});

describe("AiProPanel — araştırma (fantom / petri)", () => {
  it("TR: model kartları, adım göstergesi, seçilmeden başlatma sebebi", async () => {
    const u = await arastirmaPanel();
    const m = metin(u);
    expect(m).toContain("🔬 Hedef Modeli");
    expect(m).toContain("Fantom Tümör");
    expect(m).toContain("Silikon fantomdaki mavi tümör odaklarını bulur; odağa doz önerir.");
    expect(m).toContain("Petri plakasındaki kuyuları bulur; kanserli kuyuya doz önerir.");
    expect(m).toContain("Adım 1/5 · Model");
    expect(m).toContain("Önce Adım 1'de bir hedef modeli seçin.");
    expect(m).toContain("🚀 Hazırlığı Başlat");
    expect(m).toContain("🔬 Bu ekran deney hedefini kabin kamerasıyla bulur, 7 bobin için doz önerir ve SİZ onaylamadan hiçbir bobini çalıştırmaz.");
    expect(u.getByLabelText("Adım 1 / 5: Model")).toBeTruthy();
  });

  it("EN: model kartları, adım göstergesi, seçilmeden başlatma sebebi; veriye giden `model` değeri aynı", async () => {
    await enYap();
    const u = await arastirmaPanel();
    const m = metin(u);
    expect(m).toContain("🔬 Target Model");
    expect(m).toContain("Phantom Tumor");
    expect(m).toContain("Finds the blue tumor foci in the silicone phantom; recommends a dose for the focus.");
    expect(m).toContain("Finds the wells in the Petri plate; recommends a dose for the cancerous well.");
    expect(m).toContain("Step 1/5 · Model");
    expect(m).toContain("First choose a target model in Step 1.");
    expect(m).toContain("🚀 Start Preparation");
    expect(m).toContain(
      "🔬 This screen finds the experiment target with the cabin camera, recommends a dose for the 7 coils, and does NOT run any coil until YOU approve.",
    );
    expect(u.getByLabelText("Step 1 / 5: Model")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByLabelText(/Phantom Tumor/));
    });
    await act(async () => {
      fireEvent.press(u.getByLabelText("Start the AI Pro autonomous session"));
    });
    const govde = (apiPost as jest.Mock).mock.calls.filter((c) => c[0] === "/ai/pro/hazirlik/baslat").pop()?.[1];
    expect(govde?.model).toBe("fantom");
    expect(m).not.toContain("Adım");
  });

  it("hazırlık şeridi (özne aranıyor): TR özne + ipucu; EN 'Looking for the phantom…'", async () => {
    let u = await arastirmaPanel();
    await act(async () => {
      fireEvent.press(u.getByLabelText(/Fantom Tümör/));
    });
    await act(async () => {
      fireEvent.press(u.getByLabelText("AI Pro otonom seansı başlat"));
    });
    await act(async () => {});
    expect(metin(u)).toContain("🔎 fantom aranıyor… Fantomu tepsinin ortasına düz yerleştirin; kabin işareti de kadrajda kalsın.");
    u.unmount();
    await enYap();
    u = await arastirmaPanel();
    await act(async () => {
      fireEvent.press(u.getByLabelText(/Phantom Tumor/));
    });
    await act(async () => {
      fireEvent.press(u.getByLabelText("Start the AI Pro autonomous session"));
    });
    await act(async () => {});
    expect(metin(u)).toContain("🔎 Looking for the phantom… Place the phantom flat in the middle of the tray; keep the cabin marker in the frame too.");
  });
});

describe("AiSpecApprovalModal", () => {
  const SPECS: any = {
    organ_id: 1,
    duration_minutes: 20,
    coil_ids: [1, 2, 3],
    D: [0.3, 0.125, 0],
    P: [0, 10, 20],
    e_field: 0.07,
    e_cancer: 0.5,
    e_healthy: 0.1,
    model: "fantom",
    patient_name: "",
    target_label: "Tümör 1",
  };
  const META: any = {
    x_mm: 1.5,
    y_mm: 2.5,
    z_mm: 3,
    reliability: 0.4,
    method: "aruco_pnp",
    otomatik_secim: true,
    ood: true,
    xaiSensitivity: [
      { feature: "x", etki: 0.4, surukleyen: true },
      { feature: "organ_id", etki: 0.2, egitim_disi: true },
      { feature: "duty_sum", etki: 0, ogrenilmemis: true },
    ],
  };
  const ciz = (ekstra: Record<string, unknown> = {}) =>
    render(
      <AiSpecApprovalModal visible specs={SPECS} meta={META} onApprove={jest.fn()} onReject={jest.fn()} onDismiss={jest.fn()} {...ekstra} />,
    );

  it("TR (araştırma): göç öncesiyle aynı başlık / lead / ölçüler / açıklama satırları", () => {
    const m = metin(ciz());
    for (const s of [
      "AI Seans Önerisi — Fantom Tümör · Tümör 1",
      "Araştırma amaçlı model tahmini",
      "Deney seansı onaylanmadan başlamaz. Aşağıdaki parametreleri inceleyip onaylayın veya gerekçesiyle reddedin.",
      "Örnek",
      "— seçilmedi (sahipsiz kaydedilir)",
      "Süre",
      "20 dk",
      "Sürülen bobin",
      "2/3",
      "Konum (mm): x 1,5 · y 2,5 · z 3,0",
      "Tahmini alan (göreli, birimsiz): hedefte 0,50 · çevrede 0,10 (oran 5,0×)",
      "3B konum: kabin işaretiyle doğrulandı ✓",
      "Otomatik seçim bu hedefe mühürlendi: seans boyunca yalnız «Tümör 1» sürülür; hedef kaybolursa sürüş durur.",
      "Konum, modelin eğitim aralığı dışında olabilir — sonuç araştırma amaçlıdır.",
      "Lokalizasyon güveni: %40 — DÜŞÜK, konumu doğrulayın",
      "Dozu en çok belirleyen: konum X · doku tipi (eğitim aralığı dışı)",
      "⚠ Açıklamadaki değer eğitim aralığı dışında (doku tipi) — açıklama tahmin dışı bölgeye uzanıyor; konumu ve parametreleri doğrulayın.",
      "Öğrenilmemiş girdi: güç bütçesi — model eğitiminde sabitti, dozu etkilemez; açıklamaya katılmadı.",
      "%30.0",
      "%12.5",
      "%0.0",
      "Bobin",
      "Faz",
    ]) {
      expect(m).toContain(s);
    }
  });

  it("EN (araştırma): başlık / lead (kalın parça ile) / ölçüler / ondalık nokta / yüzde sonda", async () => {
    await enYap();
    const u = ciz();
    const m = metin(u);
    for (const s of [
      "AI Session Recommendation — Phantom Tumor · Tümör 1",
      "Model estimate for research purposes",
      "An experiment session does not start without approval. Review the parameters below and approve, or reject with a reason.",
      "Sample",
      "— not selected (saved without an owner)",
      "Duration",
      "20 min",
      "Driven coils",
      "2/3",
      "Position (mm): x 1.5 · y 2.5 · z 3.0",
      "Estimated field (relative, unitless): at the target 0.50 · surroundings 0.10 (ratio 5.0×)",
      "3D position: verified with the cabin marker ✓",
      "The automatic selection was sealed to this target: only «Tümör 1» is driven during the session; if the target is lost, driving stops.",
      "The position may be outside the model's training range — the result is for research purposes.",
      "Localization confidence: 40% — LOW, verify the position",
      "Main dose determinants: position X · tissue type (outside the training range)",
      "⚠ A value in the explanation is outside the training range (tissue type) — the explanation extends into a region beyond the prediction; verify the position and the parameters.",
      "Unlearned input: power budget — it was constant in the model training, does not affect the dose, and was excluded from the explanation.",
      "30.0%",
      "12.5%",
      "0.0%",
      "Coil",
      "Phase",
    ]) {
      expect(m).toContain(s);
    }
    expect(u.getByLabelText("AI session recommendation approval dialog")).toBeTruthy();
    expect(u.getByLabelText("Reject the recommendation")).toBeTruthy();
    expect(u.getByLabelText("Approve the recommendation and start the session")).toBeTruthy();
    expect(m).toContain("Approve and Start");
  });

  it("KRİTİK: sürüş kapalı — onay düğmesi pasif ve gerçeği söyler; lead 'seans başlatılamaz' iki dilde", async () => {
    let u = ciz({ surusKapali: "Neden metni", specs: { ...SPECS, model: "kedi" }, meta: {} });
    let m = metin(u);
    expect(m).toContain("Neden metni");
    expect(m).toContain("Parametreleri inceleyebilir ya da gerekçesiyle reddedebilirsiniz; bu ekrandan seans başlatılamaz.");
    expect(m).toContain("Sürüş kapalı");
    expect(u.getByLabelText("Sürüş kapalı — onay seansı başlatmaz").props.accessibilityState?.disabled).toBe(true);
    u.unmount();
    await enYap();
    u = ciz({ surusKapali: "Neden metni", specs: { ...SPECS, model: "kedi" }, meta: {} });
    m = metin(u);
    expect(m).toContain("You can review the parameters or reject with a reason; a session cannot be started from this screen.");
    expect(m).toContain("Driving off");
    expect(u.getByLabelText("Driving is off — approval does not start a session").props.accessibilityState?.disabled).toBe(true);
  });

  it("kedi (araştırma değil): lead 'Otonom seans' ve hasta etiketi; EN 'An autonomous session' / 'Patient'", async () => {
    let m = metin(ciz({ specs: { ...SPECS, model: "kedi", patient_name: "Tekir" }, meta: {} }));
    expect(m).toContain("AI Seans Önerisi");
    expect(m).toContain("Otonom seans onaylanmadan başlamaz. Aşağıdaki parametreleri inceleyip onaylayın veya gerekçesiyle reddedin.");
    expect(m).toContain("Hasta");
    expect(m).toContain("Tekir");
    await enYap();
    m = metin(ciz({ specs: { ...SPECS, model: "kedi", patient_name: "Tekir" }, meta: {} }));
    expect(m).toContain("An autonomous session does not start without approval. Review the parameters below and approve, or reject with a reason.");
    expect(m).toContain("Patient");
  });

  it("reddetme formu: etiket (kayda geçer) + yer tutucu iki dilde; gönderilen gerekçe kullanıcı metni (değişmez)", async () => {
    const onReject = jest.fn();
    let u = ciz({ onReject });
    await act(async () => {
      fireEvent.press(u.getByLabelText("Öneriyi reddet"));
    });
    expect(u.getByText("Red gerekçesi (kayda geçer)")).toBeTruthy();
    expect(u.getByPlaceholderText("Örn. lokalizasyon hatalı, duty çok yüksek…")).toBeTruthy();
    u.unmount();
    await enYap();
    u = ciz({ onReject });
    await act(async () => {
      fireEvent.press(u.getByLabelText("Reject the recommendation"));
    });
    expect(u.getByText("Rejection reason (will be recorded)")).toBeTruthy();
    const alan = u.getByPlaceholderText("E.g. localization is wrong, duty is too high…");
    fireEvent.changeText(alan, "Deneme gerekçesi");
    await act(async () => {
      fireEvent.press(u.getByLabelText("Confirm rejection"));
    });
    expect(onReject).toHaveBeenCalledWith("Deneme gerekçesi");
  });
});

describe("AiReviewControls / ReviewBadge", () => {
  it("TR: değerlendirilmedi, düğmeler, form etiketleri; rozet etiketleri göç öncesiyle aynı", async () => {
    const u = render(<AiReviewControls onSubmit={jest.fn()} />);
    expect(u.getByText("Bu AI sonucu değerlendirilmedi. Klinik karar hekimindir.")).toBeTruthy();
    expect(u.getByLabelText("AI sonucunu onayla")).toBeTruthy();
    expect(u.getByText("Onayla")).toBeTruthy();
    expect(u.getByText("Reddet")).toBeTruthy();
    expect(u.getByText("Düzelt")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByLabelText("AI sonucunu reddet"));
    });
    expect(u.getByText("Red gerekçesi")).toBeTruthy();
    expect(u.getByPlaceholderText("Örn. klinik bulgularla uyuşmuyor")).toBeTruthy();
    expect(u.getByLabelText("Reddi kaydet")).toBeTruthy();
    expect(u.getByText("Vazgeç")).toBeTruthy();
    expect(["approved", "rejected", "corrected", "x"].map(reviewEtiketi)).toEqual(["Hekim onayladı", "Hekim reddetti", "Hekim düzeltti", ""]);
    expect(kaydedilemediMetni()).toBe("Değerlendirme kaydedilemedi — gerekçeniz korunuyor. Tekrar deneyin.");
    expect(render(<ReviewBadge status="rejected" />).getByText("Hekim reddetti")).toBeTruthy();
  });

  it("EN: değerlendirilmedi, düğmeler, form etiketleri, kayıt hatası; veteriner / hekim terimi", async () => {
    await enYap();
    const onSubmit = jest.fn(async () => false);
    const u = render(<AiReviewControls onSubmit={onSubmit} />);
    expect(u.getByText("This AI result has not been evaluated. The clinical decision belongs to the veterinarian.")).toBeTruthy();
    expect(u.getByLabelText("Approve the AI result")).toBeTruthy();
    expect(u.getByText("Approve")).toBeTruthy();
    expect(u.getByText("Reject")).toBeTruthy();
    expect(u.getByText("Correct")).toBeTruthy();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Correct the AI result"));
    });
    expect(u.getByText("Correct diagnosis / correction")).toBeTruthy();
    expect(u.getByPlaceholderText("E.g. actual diagnosis: idiopathic cystitis")).toBeTruthy();
    expect(u.getByLabelText("Correction description")).toBeTruthy();
    expect(u.getByLabelText("Save correction")).toBeTruthy();
    expect(u.getByText("Cancel")).toBeTruthy();
    fireEvent.changeText(u.getByLabelText("Correction description"), "gerçek teşhis");
    await act(async () => {
      fireEvent.press(u.getByLabelText("Save correction"));
    });
    expect(onSubmit).toHaveBeenCalledWith("corrected", "gerçek teşhis"); // veriye giden durum + not: dilden bağımsız
    expect(u.getByText("The evaluation could not be saved — your reason is preserved. Try again.")).toBeTruthy();
    expect(["approved", "rejected", "corrected"].map(reviewEtiketi)).toEqual(["Veterinarian approved", "Veterinarian rejected", "Veterinarian corrected"]);
  });
});

describe("PemfKapisiKutusu", () => {
  const KAPI = (ek: object) => ({ surulebilir: false, pemf_gecerli: true, nedenler: ["n"], mesajlar: [], varsayimlar: [], ...ek });

  it("TR: başlıklar, rozetler ve bağlam satırı göç öncesiyle aynı", () => {
    let m = metin(render(<PemfKapisiKutusu model="fantom" reliable={false} kapi={KAPI({})} />));
    expect(m).toContain("⛔ Sonuç bobin sürüşüne KULLANILAMAZ (kabin konumu geçerli — nedenler aşağıda)");
    expect(m).toContain("   ·   ⛔ tespit güvenilir DEĞİL");
    expect(m).toContain("Aşağıdaki D / P / E değerleri bobin sürüşüne ESAS ALINMAZ:");
    expect(m).toContain("Canlı E göstergesi ve “dozu en çok belirleyen” açıklaması bu sonuçtan kurulmadı — sonuç sürülebilir değil (nedenler aşağıda).");
    m = metin(render(<PemfKapisiKutusu model="petri" kapi={KAPI({ pemf_gecerli: false })} />));
    expect(m).toContain("⛔ PEMF girdisi GEÇERSİZ");
    expect(m).toContain("“Dozu en çok belirleyen” açıklaması bu sonuçtan üretilmedi — sonuç sürülebilir değil (nedenler aşağıda).");
    m = metin(render(<PemfKapisiKutusu model="fantom" reliable kapi={KAPI({ surulebilir: true, mesajlar: [{ kod: "k", metin: "Sunucu metni" }] })} />));
    expect(m).toContain("✔ PEMF girdisi geçerli");
    expect(m).toContain("   ·   ✔ tespit güvenilir");
    expect(m).toContain("• Sunucu metni"); // sunucudan gelen metin AYNEN (sunucu dil katmanı ayrı grup)
  });

  it("KRİTİK EN: başlıklar, rozetler ve bağlam satırı", async () => {
    await enYap();
    let m = metin(render(<PemfKapisiKutusu model="fantom" reliable={false} kapi={KAPI({})} />));
    expect(m).toContain("⛔ The result CANNOT BE USED for coil driving (cabin position is valid — reasons below)");
    expect(m).toContain("   ·   ⛔ detection is NOT reliable");
    expect(m).toContain("The D / P / E values below are NOT used as the basis for coil driving:");
    expect(m).toContain(
      "The live E indicator and the “main dose determinant” explanation were not built from this result — the result is not drivable (reasons below).",
    );
    m = metin(render(<PemfKapisiKutusu model="petri" kapi={KAPI({ pemf_gecerli: false })} />));
    expect(m).toContain("⛔ PEMF input is INVALID");
    expect(m).toContain("The “main dose determinant” explanation was not produced from this result — the result is not drivable (reasons below).");
    m = metin(render(<PemfKapisiKutusu model="fantom" reliable kapi={KAPI({ surulebilir: true })} />));
    expect(m).toContain("✔ PEMF input is valid");
    expect(m).toContain("   ·   ✔ detection is reliable");
    m = metin(render(<PemfKapisiKutusu model="fantom" reliable={null} kapi={KAPI({})} />));
    expect(m).not.toContain("detection is");
  });
});

describe("TakipGrafigi", () => {
  const SERI: any = {
    moduleId: "m",
    baslik: "Ağrı skoru",
    birim: "%",
    noktalar: [
      { t: 1, deger: 40, etiket: "01.10" },
      { t: 2, deger: 30, etiket: "02.10" },
    ],
    disaridaKalan: 1,
  };

  it("TR: başlık ve dışarıda kalan notu göç öncesiyle aynı", () => {
    let m = metin(render(<TakipGrafigi seri={SERI} hasta="Mia" />));
    expect(m).toContain("📈 Mia · Ağrı skoru değişimi");
    expect(m).toContain("Yalnız aynı tür analizler karşılaştırılır — 1 farklı analiz grafiğe alınmadı.");
    m = metin(render(<TakipGrafigi seri={{ ...SERI, disaridaKalan: 3 }} hasta="Mia" />));
    expect(m).toContain("3 farklı analiz grafiğe alınmadı.");
  });

  it("EN: başlık; dışarıda kalan not çoğul biçimleri (1 / 3)", async () => {
    await enYap();
    let m = metin(render(<TakipGrafigi seri={SERI} hasta="Mia" />));
    expect(m).toContain("📈 Mia · Ağrı skoru change");
    expect(m).toContain("Only analyses of the same type are compared — 1 analysis of a different type was not included in the chart.");
    m = metin(render(<TakipGrafigi seri={{ ...SERI, disaridaKalan: 3 }} hasta="Mia" />));
    expect(m).toContain("3 analyses of a different type were not included in the chart.");
  });
});

describe("aipro/* alt bileşenler ve profil tablosu", () => {
  const HEDEFLER = [
    { id: 1, label: "Tümör 1", pxn: [0.3, 0.4], reliability: 0.8 },
    { id: 2, pxn: [0.6, 0.5], reliability: 0.5, secili: false },
  ];

  it("TR: adım göstergesi, hedef halka / satır etiketleri, kalibrasyon rozeti, model kartları, profil metinleri", () => {
    expect(metin(render(<AdimGostergesi adim={3} onGeri={jest.fn()} />))).toContain("Adım 3/5 · Hedef");
    expect(render(<AdimGostergesi adim={3} onGeri={jest.fn()} />).getByLabelText("Geri: önceki adıma dön")).toBeTruthy();
    const h = render(<HedefHalkalari hedefler={HEDEFLER} seciliId={1} onSec={jest.fn()} kutu={{ width: 100, height: 100 }} />);
    expect(h.getByLabelText("Hedef 1 / 2: Tümör 1, güven yüzde 80, seçili")).toBeTruthy();
    expect(h.getByLabelText("Hedef 2 / 2: hedef, güven yüzde 50")).toBeTruthy();
    const l = render(<HedefListesi hedefler={HEDEFLER} seciliId={0} onSec={jest.fn()} />);
    const lm = metin(l);
    expect(lm).toContain("🎯 Hedefler (kare üstünden ya da buradan seçin)");
    expect(lm).toContain("Hedef 2");
    expect(lm).toContain("%80");
    expect(l.getByLabelText("Hedef 2 / 2: hedef, güven yüzde 50")).toBeTruthy();
    expect(metin(render(<KalibrasyonRozeti yontem="" />))).toBe("3B konum: henüz ölçülmedi — kamera açılınca ölçülür.");
    expect(metin(render(<KalibrasyonRozeti yontem="pixel" />))).toBe(
      "Konum ölçülemedi — kabin işareti (arka duvardaki kare kod) kadrajda görünmüyor. Kamerayı işaret ve hedef aynı karede kalacak şekilde ayarlayın.",
    );
    const k = metin(
      render(
        <ModelSecimKartlari modeller={["fantom", "petri"]} secili="petri" onSec={jest.fn()} kilitli kilitNedeni="K" kurulum={{ fantom: "hazir", petri: "eksik" }} arastirmaAcik={false} />,
      ),
    );
    for (const s of ["Model kurulu ✓", "Araştırma model paketi bu cihazda kurulu değil", "Deneysel — şimdilik yalnız görüntüleme"]) expect(k).toContain(s);
    expect(k).toContain("Bu sürümde fantom/petri hedefine doz ONAYLANAMAZ: 3B konum dönüşümü tezgâhta doğrulanmadı. Kamerayı açıp hedefi ve konumu görebilir, yerleşimi ölçebilirsiniz.");
    const p = modelProfili("petri");
    expect([p.baslik, p.ozne, p.hedefEtiketi, p.hedefEtiketiKucuk, p.ozneIpucu]).toEqual([
      "Petri Kuyu",
      "petri plakası",
      "Kuyu",
      "kuyu",
      "Plakayı tepsiye düz yerleştirin; kamerayı tepeden tam kadraja alın.",
    ]);
    expect(modelProfili("kedi").ozneIpucu).toBe("Kamerayı hastaya doğrultun.");
    expect(modelProfili("fantom").hedefEtiketiKucuk).toBe("tümör");
  });

  it("EN: adım göstergesi, hedef etiketleri, kalibrasyon rozeti, model kartları, profil metinleri", async () => {
    await enYap();
    expect(metin(render(<AdimGostergesi adim={3} onGeri={jest.fn()} />))).toContain("Step 3/5 · Target");
    expect(render(<AdimGostergesi adim={3} onGeri={jest.fn()} />).getByLabelText("Back: go back to the previous step")).toBeTruthy();
    const h = render(<HedefHalkalari hedefler={HEDEFLER} seciliId={1} onSec={jest.fn()} kutu={{ width: 100, height: 100 }} />);
    expect(h.getByLabelText("Target 1 / 2: Tümör 1, confidence 80 percent, selected")).toBeTruthy();
    expect(h.getByLabelText("Target 2 / 2: target, confidence 50 percent")).toBeTruthy();
    const l = render(<HedefListesi hedefler={HEDEFLER} seciliId={0} onSec={jest.fn()} />);
    const lm = metin(l);
    expect(lm).toContain("🎯 Targets (select on the frame or here)");
    expect(lm).toContain("Target 2");
    expect(lm).toContain("80%");
    expect(metin(render(<KalibrasyonRozeti yontem="" />))).toBe("3D position: not measured yet — it is measured once the camera opens.");
    expect(metin(render(<KalibrasyonRozeti yontem="pixel" />))).toBe(
      "The position could not be measured — the cabin marker (the square code on the back wall) is not visible in the frame. Adjust the camera so that the marker and the target stay in the same frame.",
    );
    const k = metin(
      render(
        <ModelSecimKartlari modeller={["fantom", "petri"]} secili="petri" onSec={jest.fn()} kilitli kilitNedeni="K" kurulum={{ fantom: "hazir", petri: "eksik" }} arastirmaAcik={false} />,
      ),
    );
    for (const s of ["Model installed ✓", "The research model package is not installed on this device", "Experimental — view-only for now"]) expect(k).toContain(s);
    expect(k).toContain(
      "In this version a dose for a phantom/petri target CANNOT be approved: the 3D position transform has not been verified on the bench. You can open the camera and see the target and its position, and measure the placement.",
    );
    const p = modelProfili("petri");
    expect([p.baslik, p.ozne, p.hedefEtiketi, p.hedefEtiketiKucuk, p.ozneIpucu]).toEqual([
      "Petri Well",
      "petri plate",
      "Well",
      "well",
      "Place the plate flat on the tray; frame it fully with the camera from above.",
    ]);
    expect(modelProfili("kedi").ozneIpucu).toBe("Point the camera at the patient.");
    expect(T("ai.pro.adim.model")).toBe("Model");
  });
});
