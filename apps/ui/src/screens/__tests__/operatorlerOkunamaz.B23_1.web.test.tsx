/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * B2-3.1 (2-B bağımsız incelemesi, A3) — `/operators` OKUNAMAZSA arayüz Kural 2'ye DÜŞER (Y103 · A-61 · D2.72 · İG-6.26 delinir).
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR: `OperatorContext` operatör listesini açılışta BİR KEZ okur; okuma düşerse (backend henüz hazır değil, mobilde
 * keşif bitmeden, 5xx, ağ hatası) liste `[]` kalır ve `operatorEmail = active?.email || (operators.length === 0 ? session.email
 * : "")` türetimi KAYITLI operatörlü klinikte de oturum (giriş) e-postasına düşer. Pencere açılınca yapılan yenileme düşerse de
 * dolu liste `[]`'e SIFIRLANIR (aktif operatör durur) → `silinebilir` Kural 2'yi uygular.
 *  · Y103: kimse seçili değilken üç liste kayıt göstermemeli → oturum e-postasının "Benim" kapsamı (+ sahipsizler) görünür.
 *  · A-61: kimliksiz hasta ekleme isteği gitmemeli → `operator_email: <giriş e-postası>` ile gider (backend: kayıtlıysa SAHİPSİZ).
 *  · İG-6.26 (arayüz katmanı): kimliksiz değerlendirme gitmemeli → `reviewed_by: <giriş e-postası>` ile, jetonsuz gider.
 *  · D2.72 (arayüz katmanı): A seçiliyken liste yenilemesi düşerse "Tüm Klinik → Tümünü Seç → Sil" başka hekimin + sahipsiz
 *    kayıtları isteğe koyar (backend 403 der → A KENDİ kaydını da silemez).
 * KARŞIT (Kural 2): kayıtlı operatörü OLMAYAN klinikte liste okununca kayıtlar görünür, ekleme gider (geçici okuma hatasından
 * sonra da TOPARLANIR).
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher (PIN), AppNavProvider, PatientScreen,
 * TreatmentHistoryScreen, AiHistoryScreen, AiReviewControls, apiClient. Sahte yalnız `fetch` (kaydedici; `/operators` durumu
 * ayarlanabilir: 200 / 503 / ağ hatası / gecikme), Supabase istemcisi, toast, `window.confirm` ve cihaz modülleri.
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
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ documentDirectory: "file:///", writeAsStringAsync: jest.fn() }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { useEffect } from "react";
import { View } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { PatientScreen } from "@/screens/PatientScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { EKLEME_KIMLIK_ISTEMI, KIMLIK_ISTEMI } from "@/utils/patientScope";
import { aktifOperator, cipEtiketi, pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const TARIH = "2026-10-01 10:00:00";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];

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
    id: 200 + i, created_at: TARIH, timestamp: TARIH, mode: "veterinarian", module_id: "m", module_label: `Modul${ad}`,
    patient_name: "Ortak", input_type: "image", result_summary: `Ozet${ad}`, result_detail: {}, confidence: 0.9,
    operator_email: e, review_status: "",
  }));
  return { hastalar, seanslar, analizler };
}

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

type OpDurum = 200 | 503 | "ag";
const ag = { operatorler: 200 as OpDurum, gecikmeMs: 0, operatorIstegi: 0 };

let s: Sahne;
let kayit: Istek[];
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
  ag.operatorler = 200;
  ag.gecikmeMs = 0;
  ag.operatorIstegi = 0;
  jest.spyOn(window, "confirm").mockImplementation(() => true);
});
afterEach(async () => {
  await s.sok();
  (window.confirm as jest.Mock).mockRestore?.();
  jest.useRealTimers();
});

async function kur(mod: UserMode, oturum: string, operatorler: SahteOperator[], sahipler: Record<string, string>,
                   ekranlar: Array<"hasta" | "seans" | "ai"> = ["hasta", "seans", "ai"]) {
  mockOturum.eposta = oturum;
  mockToast.mockClear();
  const { hastalar, seanslar, analizler } = veri(sahipler);
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/operators" && ag.operatorler === 503) return [503, { detail: "hazir degil (taklit)" }];
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yontem === "GET" && yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : seanslar];
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, { status: "success", data: yol.includes("before_id") ? [] : analizler }];
    }
    if (yontem === "POST" && yol === "/ai/log/review") return [200, { status: "success" }];
    if (yontem === "POST" && /delete/.test(yol)) return [200, { status: "success", silinen: 1 }];
    if (yontem === "POST" && yol === "/patients") return [200, { status: "success" }];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = (async (url: unknown, init?: unknown) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    if (yol === "/operators" && (!init || !(init as { method?: string }).method)) {
      ag.operatorIstegi += 1;
      if (ag.gecikmeMs) await new Promise((r) => setTimeout(r, ag.gecikmeMs));
      if (ag.operatorler === "ag") throw new TypeError("Network request failed (taklit)");
    }
    return sunucu.fetchSahte(url, init as never);
  }) as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <OperatorSwitcher />
              {ekranlar.includes("hasta") ? <View><PatientScreen /></View> : null}
              {ekranlar.includes("seans") ? <View><TreatmentHistoryScreen /></View> : null}
              {ekranlar.includes("ai") ? <View><AiHistoryScreen /></View> : null}
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

function gorunen(): string[] {
  const m = s.metin();
  return ["HastaA", "HastaB", "HastaS", "SeansA", "SeansB", "SeansS", "OzetA", "OzetB", "OzetS"].filter((ad) => m.includes(ad));
}
const istemSayisi = () => s.metin().split(KIMLIK_ISTEMI).length - 1;
const istekler = (yontem: string, yol: string | RegExp) =>
  kayit.filter((k) => k.yontem === yontem && (typeof yol === "string" ? k.yol === yol : yol.test(k.yol)));

describe("B2-3.1 — /operators okunamazsa kayıtlı operatörlü klinikte kimliksiz arayüz Kural 2'ye DÜŞMEMELİ", () => {
  it.each([503, "ag"] as OpDurum[])(
    "KRİTİK (Y103, hekim profili, /operators %s): kimse seçili değilken üç listede kayıt YOK, istem ×3",
    async (durum) => {
      ag.operatorler = durum;
      await kur("veterinarian", A, IKI_HEKIM, { A, B, S: "" });
      expect(aktifOperator()).toBeNull(); // ARA DOĞRULAMA: kimse seçili değil
      expect(gorunen()).toEqual([]);
      expect(istemSayisi()).toBe(3);
    },
  );

  it("KRİTİK (Y103, ev sahibi, /operators ağ hatası): kayıt YOK (sahipsiz kayıtlar da)", async () => {
    ag.operatorler = "ag";
    await kur("pet_owner", "sahip@ev.com", IKI_HEKIM, { A, B, S: "" });
    expect(gorunen()).toEqual([]);
  });

  it("KRİTİK (A-61, /operators 503): kimliksiz hasta ekleme isteği GİTMEZ, operatör seçmesi söylenir", async () => {
    ag.operatorler = 503;
    await kur("veterinarian", A, IKI_HEKIM, {}, ["hasta"]);
    await s.metneTikla("Yeni Hasta Kayıt");
    await s.yaz("Hasta adı", "YeniKedi");
    await s.yaz("Hayvan türü", "Kedi");
    await s.metneTikla("Kaydet");
    expect(istekler("POST", "/patients")).toEqual([]);
    expect(mockToast.mock.calls.map((c) => c[0])).toContain(EKLEME_KIMLIK_ISTEMI);
  });

  it("KRİTİK (İG-6.26 arayüz katmanı, /operators 503): kimliksiz değerlendirme isteği GİTMEZ", async () => {
    ag.operatorler = 503;
    await kur("veterinarian", A, IKI_HEKIM, { A }, ["ai"]);
    const kart = document.querySelector('[aria-label^="ModulA kaydi"]');
    if (kart) {
      await s.tikla(kart.getAttribute("aria-label")!);
      await s.tikla("AI sonucunu onayla");
    }
    expect(istekler("POST", "/ai/log/review")).toEqual([]);
    expect(s.metin()).not.toContain("Hekim onayladı");
  });

  it.each(["hasta", "seans"] as const)(
    // Y104 (2-B2): sahipsiz kayıt (S) da silinebilir; kolun konusu BAŞKA (kayıtlı) hekimin kaydının (B) isteğe GİRMEMESİ.
    "KRİTİK (D2.72 arayüz katmanı, %s): A seçiliyken pencere yenilemesi 503 → 'Tüm Klinik → Tümünü Seç → Sil' B'nin kaydı YOK (A + sahipsiz)",
    async (ekran) => {
      await kur("veterinarian", A, IKI_HEKIM, { A, B, S: "" }, [ekran]);
      await pinleSec(s, "Dr. A");
      await s.bosalt(10);
      expect(aktifOperator()).toBe("Dr. A");
      ag.operatorler = 503;
      await s.tikla(cipEtiketi()); // pencere açılır → liste yenilenir (B2B-1 sonrası bir kez) → 503
      await s.bosalt(10);
      await s.tikla("Kapat");
      expect(aktifOperator()).toBe("Dr. A"); // ARA DOĞRULAMA: kimlik duruyor, jeton A
      const e = ekran === "hasta"
        ? { tum: "Tüm klinik hastaları", cubuk: "hasta-secim-cubugu", yol: "/patients/delete_bulk", alan: "patient_ids", kendi: ["p0", "p2"] }
        : { tum: "Tüm klinik seansları", cubuk: "gecmis-secim-cubugu", yol: "/history/delete_bulk", alan: "session_ids", kendi: [100, 102] };
      await s.tikla(e.tum);
      if (ekran === "hasta") await s.metneTikla("Seç");
      else await s.tikla("Toplu seçim kipini aç veya kapat");
      await s.testIdTikla(`${e.cubuk}-tumunu`);
      await s.testIdTikla(`${e.cubuk}-sil`);
      await s.bosalt(10);
      const t = istekler("POST", e.yol);
      expect(t.length).toBe(1);
      expect(t[0].operator).toBe(`JETON-${A}`);
      expect([...((t[0].govde as Record<string, unknown[]>)[e.alan])].sort()).toEqual(e.kendi);
    },
  );

  it("KRİTİK (geçici pencere): /operators yanıtı 3 sn gecikirken kayıtlı klinikte kimliksiz listeler kayıt GÖSTERMEZ", async () => {
    ag.gecikmeMs = 3000;
    await kur("veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    const ilk = gorunen();
    await s.ilerlet(3500);
    await s.bosalt(10);
    expect(gorunen()).toEqual([]); // ARA DOĞRULAMA: liste gelince kapanıyor
    expect(ilk).toEqual([]);
  });
});

describe("B2-3.1 — KARŞIT (Kural 2): operatörsüz tek hekimli klinik kilitlenmez", () => {
  const T = "tek@klinik.com";

  it("KARŞIT: liste okununca ([]) kayıtlar görünür, istem yok, hasta eklenir", async () => {
    await kur("veterinarian", T, [], { T, S: "" });
    const m = s.metin();
    for (const ad of ["HastaT", "HastaS", "SeansT", "SeansS", "OzetT", "OzetS"]) expect(m).toContain(ad);
    expect(istemSayisi()).toBe(0);
    await s.metneTikla("Yeni Hasta Kayıt");
    await s.yaz("Hasta adı", "YeniKedi");
    await s.yaz("Hayvan türü", "Kedi");
    await s.metneTikla("Kaydet");
    expect(istekler("POST", "/patients").length).toBe(1);
  });

  it("KARŞIT (toparlanma): açılışta /operators 503, sonra 200 [] → en geç 30 sn içinde kayıtlar görünür, ekleme gider", async () => {
    ag.operatorler = 503;
    await kur("veterinarian", T, [], { T, S: "" });
    ag.operatorler = 200;
    for (let t = 0; t < 30_000; t += 5_000) await s.ilerlet(5_000);
    await s.bosalt(10);
    const m = s.metin();
    for (const ad of ["HastaT", "SeansT", "OzetT"]) expect(m).toContain(ad);
    expect(istemSayisi()).toBe(0);
  });

  it("KARŞIT (kayıtlı klinik toparlanma): açılışta 503, sonra 200 → PIN'le seçilen hekim kendi kayıtlarını görür", async () => {
    ag.operatorler = 503;
    await kur("veterinarian", A, IKI_HEKIM, { A, B, S: "" });
    ag.operatorler = 200;
    for (let t = 0; t < 30_000; t += 5_000) await s.ilerlet(5_000);
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    expect(aktifOperator()).toBe("Dr. A");
    expect(gorunen()).toEqual(["HastaA", "HastaS", "SeansA", "SeansS", "OzetA", "OzetS"]);
  });
});
