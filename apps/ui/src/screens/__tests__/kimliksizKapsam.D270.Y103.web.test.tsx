/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.70 · B-6.19 · Y103 — KİMLİKSİZKEN kayıt listeleri FAIL-CLOSED.
 * =================================================================
 * ÖLÇÜLEN KUSUR (DENETIM-06): `inScope(_, "mine", "")` → herkes `true`. Kimlik açılışta ve kilit sonrası düşüyor; o anda
 * ev sahibi (ve "Benim" sekmesindeki hekim) kliniğin TÜM hasta, seans ve AI kayıtlarını "Benim" diye görüyordu.
 * `TreatmentHistoryScreen` ayrıca kuralın KENDİ kopyasını taşıyordu (`scope === "mine" && myEmail`) — aynı açık.
 *
 * SAHİP KARARI Y103: cihazda KAYITLI operatör varken kimse seçili değilse (ya da kilit sonrası) Hastalar, Seans Geçmişi
 * ve AI Geçmişi kayıt GÖSTERMEZ ve "Kayıtları görmek için operatörünüzü seçin" der. Kayıtlı operatörü OLMAYAN tek hekimli
 * klinikte bugünkü gibi tüm kayıtlar görünür (Kural 2). Profil / "son operatör" kalıcılığı EKLENMEZ.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (dolu operatör listesi, gerçek hareketsizlik zamanlayıcısı),
 * OperatorSwitcher (PIN), AppNavProvider, PatientScreen, TreatmentHistoryScreen, AiHistoryScreen, apiClient.
 * Sahte yalnız `fetch`, Supabase istemcisi ve toast.
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
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
// Cihaz sınırı (dosya paylaşımı/yazımı): jsdom'da yerel modül yok; bu kapı dosya indirmeyi ölçmez.
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
// ⚠️ Aparat (ölçüldü): jest-expo modülleri YEREL platform için çözer → `expo-linear-gradient` `.native` görünüm bağdaştırıcısı
// RN-web'de `findNodeHandle is not supported on web` atar. Gerçek web paketi `.web` sürümünü seçer (düz div). Görsel kütüphane.
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { useEffect } from "react";
import { View } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { PatientScreen } from "@/screens/PatientScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { eklemeKimlikIstemiMetni, kimlikIstemiMetni } from "@/utils/patientScope";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const TARIH = "2026-10-01 10:00:00";

function veri(sahipler: Record<string, string>) {
  const hastalar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: `p${i}`, name: `Hasta${ad}`, species: "Kedi", breed: "", age: 3, weight: 4, owner_name: "", owner_phone: "",
    operator_email: e, created_at: TARIH,
  }));
  const seanslar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 100 + i, patient_name: `Seans${ad}`, session_date: TARIH, start_time: TARIH, end_time: TARIH,
    duration_minutes: 5, treatment_mode: "Manuel", status: "completed", operator_email: e,
  }));
  const analizler = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 200 + i, created_at: TARIH, timestamp: TARIH, mode: "veterinarian", module_id: "m", module_label: "Modül",
    // Hasta adı ORTAK: AI Geçmişi hasta çipleri ham listeden kuruluyor (B-6.18 · D2.71, 2-C) — çip sızıntısı bu kapının
    // konusu değil; satırlar özetten (`Ozet<ad>`) tanınır.
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${ad}`, result_detail: {}, confidence: 0.9,
    operator_email: e,
  }));
  return { hastalar, seanslar, analizler };
}

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

async function kur(
  mod: UserMode,
  oturum: string,
  operatorler: SahteOperator[],
  sahipler: Record<string, string>,
): Promise<Istek[]> {
  mockOturum.eposta = oturum;
  mockToast.mockClear();
  const { hastalar, seanslar, analizler } = veri(sahipler);
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem !== "GET") return undefined;
    if (yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : seanslar];
    if (yol.startsWith("/ai/log")) return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
              <View><PatientScreen /></View>
              <View><TreatmentHistoryScreen /></View>
              <View><AiHistoryScreen /></View>
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  return sunucu.kayit;
}

/** Ekrandaki kayıt adları (üç liste). */
function gorunen(): string[] {
  const m = s.metin();
  return ["HastaA", "HastaB", "HastaS", "SeansA", "SeansB", "SeansS", "OzetA", "OzetB", "OzetS"].filter((ad) =>
    m.includes(ad),
  );
}
const istemSayisi = () => s.metin().split(kimlikIstemiMetni()).length - 1;

describe("D2.70 · Y103 — kimliksizken kayıt listeleri fail-closed", () => {
  it("KRİTİK (ev sahibi): kayıtlı operatörlü cihazda kimse seçili değilken üç listede de kayıt YOK ve istem görünür", async () => {
    await kur("pet_owner", "sahip@ev.com", [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }], {
      A, B, S: "",
    });
    expect(gorunen()).toEqual([]);
    expect(istemSayisi()).toBe(3);
  });

  it("KRİTİK (hekim, kilit sonrası): seçiliyken kendi kayıtları görünür; hareketsizlik kilidinden SONRA hiçbiri", async () => {
    await kur("veterinarian", A, [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }], {
      A, B, S: "",
    });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    expect(aktifOperator()).toBe("Dr. A");
    // ARA DOĞRULAMA (araç kanıtı): kimlik varken "Benim" kapsamı kendi + sahipsiz kayıtları gösterir.
    expect(gorunen()).toEqual(["HastaA", "HastaS", "SeansA", "SeansS", "OzetA", "OzetS"]);
    for (let t = 0; t < AUTO_LOCK_MS + 31_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBeNull();
    expect(gorunen()).toEqual([]);
    expect(istemSayisi()).toBe(3);
  });

  it("KARŞIT (Kural 2): kayıtlı operatörü OLMAYAN tek hekimli klinikte kayıtlar bugünkü gibi görünür, istem YOK", async () => {
    const T = "tek@klinik.com";
    await kur("veterinarian", T, [], { T, S: "" });
    const m = s.metin();
    for (const ad of ["HastaT", "HastaS", "SeansT", "SeansS", "OzetT", "OzetS"]) expect(m).toContain(ad);
    expect(istemSayisi()).toBe(0);
  });
});

describe("D2.70 · A-61 — hasta eklemek KİMLİK ister", () => {
  async function ekle(ad: string) {
    await s.metneTikla("Yeni Hasta Kayıt");
    await s.yaz("Hasta adı", ad);
    await s.yaz("Hayvan türü", "Kedi");
    await s.metneTikla("Kaydet");
  }
  const eklemeler = (kayit: Istek[]) => kayit.filter((k) => k.yol === "/patients" && k.yontem === "POST");

  it("KRİTİK: kayıtlı operatörlü cihazda kimse seçili değilken hasta ekleme isteği GİTMEZ, operatör seçmesi söylenir", async () => {
    const kayit = await kur("veterinarian", A, [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }], {});
    await ekle("YeniKedi");
    expect(eklemeler(kayit)).toEqual([]);
    expect(mockToast.mock.calls.map((c) => c[0])).toContain(eklemeKimlikIstemiMetni());
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte hasta eklenir, sahibi oturum e-postası", async () => {
    const T = "tek@klinik.com";
    const kayit = await kur("veterinarian", T, [], {});
    await ekle("YeniKedi");
    const e = eklemeler(kayit);
    expect(e.length).toBe(1);
    expect((e[0].govde as { operator_email?: string; name?: string })).toMatchObject({ name: "YeniKedi", operator_email: T });
  });
});
