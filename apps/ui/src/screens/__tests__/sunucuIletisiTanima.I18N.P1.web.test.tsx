/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 (S-I18N-P1.1) · SUNUCU İLETİSİNİ METNİNE BAKARAK SINIFLAYAN ARAYÜZ YERLERİ İNGİLİZCEDE DE ÇALIŞIR.
 *
 * Sunucu 503 / 422 gövdesi İSTEK DİLİNDE gelir (`X-PEMF-Dil`). Arayüz üç yerde iletinin METNİNE bakar:
 *   1) `OperatorContext` — `/operators` 503 "Cihazın kimlik veritabanı okunamıyor …" → arıza + çare (yoksa "operatörünüzü seçin" denirdi);
 *   2) `ObservationNotesModal` — aynı ön ek istemde → operatör seçici GİZLENİR;
 *   3) `canliKareDurumu` — termal 422 "… termal kamera görüntüsüne benzemiyor" → "termal kamerayı seçin" ipucu;
 *   4) `aiDetayCumlesi` — Türkçe sezgisi "saf-ASCII = teknik" İngilizce dostu sunucu iletilerini GİZLERDİ.
 * ⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz). TR davranış göç öncesiyle AYNI.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockOturum = { eposta: "dr.a@klinik.com" };
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: mockOturum.eposta, user_metadata: {} } }),
  };
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import { readFileSync } from "fs";
import { join } from "path";
import React, { act, useEffect } from "react";
import { View } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { PatientScreen } from "@/screens/PatientScreen";
import { Sahne, sahteSunucu, type SahteOperator } from "../../context/__tests__/operatorAparati";
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";
import { canliKareDurumu } from "@/utils/canliKare";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { kimlikDbArizaMi } from "@/utils/patientScope";

const depo = { setItem: async () => undefined };
const A = "dr.a@klinik.com";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: "dr.b@klinik.com", display_name: "Dr. B" }];

// Arka ucun (servers.auth.kimlik_db_okunamiyor_metni) 503 gövdesinin BAŞI — iki dilde.
const SUNUCU_TR = "Cihazın kimlik veritabanı okunamıyor — kayıtların hangi hekime ait olduğu doğrulanamıyor; (arka uç).";
const SUNUCU_EN = "The device's identity database cannot be read — it cannot be verified which veterinarian the records belong to; (server).";
const ARIZA_TR = "Cihazın kimlik veritabanı okunamıyor —";
const ARIZA_EN = "The device's identity database cannot be read —";
const ISTEM_TR = "Kayıtları görmek için operatörünüzü seçin";
const ISTEM_EN = "Select your operator to see the records";
const TERMAL_TR = "Bu görüntü termal kamera görüntüsüne benzemiyor (renk paleti / sıcaklık eşlemesi yok). Termal kameradan çekin ya da termal görüntü yükleyin.";
const TERMAL_EN = "This image does not look like a thermal camera image (no color palette / temperature mapping). Capture it with a thermal camera or upload a thermal image.";

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

describe("kimlikDbArizaMi (birim)", () => {
  it("sunucu iletisi iki dilde TANINIR; başka 503 metni / boş TANINMAZ", () => {
    expect(kimlikDbArizaMi(SUNUCU_TR)).toBe(true);
    expect(kimlikDbArizaMi(SUNUCU_EN)).toBe(true);
    for (const baska of ["hazir degil (taklit)", "Service Unavailable", "", "Cihaz hazır değil", "The device is not ready"]) {
      expect(kimlikDbArizaMi(baska)).toBe(false);
    }
  });
});

// ── OperatorContext (gerçek sağlayıcılar, sahte yalnız ağ sınırı) ──
function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

describe("OperatorContext: /operators 503 iletisi İSTEK DİLİNDE", () => {
  let s: Sahne;
  const kur = async (gövde: string) => {
    mockOturum.eposta = A;
    const sunucu = sahteSunucu(IKI_HEKIM, (yol, _g, yontem) => {
      if (yontem === "GET" && yol === "/operators") return [503, { detail: gövde }];
      if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: [] }];
      return undefined;
    });
    global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
    await s.ciz(
      <AuthProvider>
        <UserModeProvider>
          <Mod mod="veterinarian">
            <OperatorProvider>
              <AppNavProvider navigateTo={() => undefined}>
                <OperatorSwitcher />
                <View><PatientScreen /></View>
              </AppNavProvider>
            </OperatorProvider>
          </Mod>
        </UserModeProvider>
      </AuthProvider>,
    );
    await s.ilerlet(50);
    await s.bosalt(10);
  };
  const say = (metin: string) => s.metin().split(metin).length - 1;
  const cip = () => document.querySelector('[aria-label="Select operator"], [aria-label^="Active operator:"], [aria-label^="Identity database cannot be read"], [aria-label="Operatör seç"], [aria-label^="Kimlik veritabanı okunamıyor"]');

  beforeEach(() => {
    jest.useFakeTimers();
    s = new Sahne();
  });
  afterEach(async () => {
    await s.sok();
    jest.useRealTimers();
  });

  it("TR: arıza + çare söylenir, 'operatörünüzü seçin' DENMEZ (göç öncesiyle aynı)", async () => {
    await kur(SUNUCU_TR);
    expect(say(ARIZA_TR)).toBeGreaterThanOrEqual(1);
    expect(say(ISTEM_TR)).toBe(0);
    expect(cip()?.getAttribute("aria-label")).toMatch(/^Kimlik veritabanı okunamıyor/);
  });

  it("KRİTİK EN: sunucu İNGİLİZCE 503 iletisi de TANINIR → arıza + çare İngilizce; 'Select your operator' DENMEZ", async () => {
    await enYap();
    await kur(SUNUCU_EN);
    expect(say(ARIZA_EN)).toBeGreaterThanOrEqual(1);
    expect(say("close and reopen the app")).toBeGreaterThanOrEqual(1);
    expect(say(ISTEM_EN)).toBe(0);
    expect(cip()?.getAttribute("aria-label")).toMatch(/^Identity database cannot be read/);
  });

  it("KARŞIT EN: başka nedenle 503 (hazır değil) → arıza DENMEZ, istem 'Select your operator …'", async () => {
    await enYap();
    await kur("The server is not ready yet (mock).");
    expect(say(ARIZA_EN)).toBe(0);
    expect(say(ISTEM_EN)).toBeGreaterThanOrEqual(1);
  });
});

// ── canliKareDurumu: termal makullik ipucu ──
describe("canliKareDurumu: termal 422 iletisi İSTEK DİLİNDE", () => {
  it("TR: 'termal kamerayı seçin' ipucu (göç öncesiyle aynı)", () => {
    const d = canliKareDurumu("/vision/thermal", false, 422, { detail: TERMAL_TR });
    expect(d.tur).toBe("red");
    expect(d.metin.startsWith("Seçili kamera termal görüntü vermiyor — termal kamerayı seçin.")).toBe(true);
  });

  it("KRİTİK EN: İngilizce sunucu iletisi de TANINIR → 'select the thermal camera' ipucu", async () => {
    await enYap();
    const d = canliKareDurumu("/vision/thermal", false, 422, { detail: TERMAL_EN });
    expect(d.tur).toBe("red");
    expect(d.metin.startsWith("The selected camera is not giving a thermal image — select the thermal camera.")).toBe(true);
    expect(d.metin).toContain("does not look like a thermal camera image"); // sunucunun gerekçesi gösterilir
  });

  it("KARŞIT EN: başka 422 → genel 'could not be analyzed' (ipucu YOK)", async () => {
    await enYap();
    const d = canliKareDurumu("/vision/thermal", false, 422, { detail: "The image is too small (min 64 px)." });
    expect(d.metin.startsWith("Last frame could not be analyzed:")).toBe(true);
    expect(d.metin).not.toContain("select the thermal camera");
  });
});

// ── aiDetayCumlesi: İngilizcede sunucunun dostu iletisi GİZLENMEZ ──
describe("aiDetayCumlesi: İngilizce arayüz", () => {
  it("EN: sunucunun dostu iletisi AYNEN; teknik / çerçeve metni modül varsayılanına", async () => {
    await enYap();
    for (const dostu of [
      "The image is too large (> 25 MB limit).",
      "Select a patient before running the analysis.",
      TERMAL_EN,
    ]) {
      expect(aiDetayCumlesi(dostu, "VARSAYILAN")).toBe(dostu);
    }
    for (const teknik of [
      "NoneType object has no attribute foo",
      "'str' object has no attribute 'get'", // yalnız "object has no attribute" kolu
      "NoneType is not iterable", // yalnız "nonetype" kolu
      "Internal Server Error",
      "Not Found",
      "Traceback (most recent call last):",
      "Unhandled exception in handler", // yalnız "exception" kolu
      "stack trace: frame 3", // yalnız "stack trace" kolu
      "KeyError: 'abc'",
      "[Errno 2] No such file or directory",
    ]) {
      expect(aiDetayCumlesi(teknik, "VARSAYILAN")).toBe("VARSAYILAN");
    }
    expect(aiDetayCumlesi("", "VARSAYILAN")).toBe("VARSAYILAN");
    expect(aiDetayCumlesi(null, "VARSAYILAN")).toBe("VARSAYILAN");
  });

  it("EN: Starlette boyut hatası hâlâ EYLEM söyleyen cümleye çevrilir (ham metin sızmaz)", async () => {
    await enYap();
    const c = aiDetayCumlesi("Part exceeded maximum size of 1024KB.", "VARSAYILAN");
    expect(c).not.toContain("exceeded");
    expect(c).not.toBe("VARSAYILAN");
  });

  it("TR: sezgi DEĞİŞMEDİ — saf-ASCII teknik metin gizlenir, Türkçe iletiye dokunulmaz", () => {
    expect(aiDetayCumlesi("NoneType object has no attribute foo", "Y")).toBe("Y");
    expect(aiDetayCumlesi("The image is too large (> 25 MB limit).", "Y")).toBe("Y"); // TR arayüzde İngilizce metin gösterilmez
    expect(aiDetayCumlesi("Görüntü çok büyük (> 25 MB sınırı).", "Y")).toBe("Görüntü çok büyük (> 25 MB sınırı).");
  });
});

describe("kaynak kapıları", () => {
  const kaynak = (rel: string) => readFileSync(join(__dirname, "..", "..", rel), "utf8");
  it("OperatorContext · ObservationNotesModal ham TR ön ek karşılaştırması KULLANMAZ", () => {
    expect(kaynak("context/OperatorContext.tsx")).toContain("kimlikDbArizaMi(detay)");
    expect(kaynak("context/OperatorContext.tsx")).not.toContain("detay.startsWith(KIMLIK_DB_ARIZA_ONEKI)");
    expect(kaynak("components/domain/ObservationNotesModal.tsx")).toContain("kimlikDbArizaMi(kimlikIstemi)");
    expect(kaynak("components/domain/ObservationNotesModal.tsx")).not.toContain("kimlikIstemi.startsWith(KIMLIK_DB_ARIZA_ONEKI)");
  });
});
