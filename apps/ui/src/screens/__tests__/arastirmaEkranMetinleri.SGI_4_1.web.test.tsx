/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * SGI-4.1 (SG + TD + CH bağımsız incelemesi, 2026-10-17) — ARAŞTIRMA profilinde ekran İÇİ metinler de profile uyar.
 * ==============================================================================================================
 * Sahip (G1, 2026-10-13): "metinler de bu profillere göre uyarlanmalı … klinikle araştırma modunun alakası yok". SG.G1 sayfa
 * BAŞLIKLARINI (`config/sayfaBasliklari`) ve "Benim / Tüm" kapsam düğmelerini uyarladı; ama kum havuzunda (sahte backend +
 * başsız tarayıcı) araştırma profilinde ekranların İÇİNDE klinik dili kaldığı ölçüldü: Hastalar "Hasta Veritabanı" /
 * "Yeni Hasta Kayıt", Seans Geçmişi "Hastalarınıza ait geçmiş seans kayıtları…", AI Geçmişi "Tüm hastalar" çipi.
 * Tek kaynak karar #12 sözlüğü (`utils/profilSozlugu`); veteriner (ve ev sahibi) metinleri AYNEN — yalnız araştırma farklı.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, AppNavProvider, PatientScreen / TreatmentHistoryScreen /
 * AiHistoryScreen, apiClient. Sahte yalnız `fetch` (kaydedici), Supabase istemcisi, toast ve cihaz modülleri.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "dr.a@klinik.com", user_metadata: {} } }),
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

import React, { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { PatientScreen } from "@/screens/PatientScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

const TARIH = "2026-10-01 10:00:00";
const HASTALAR = [{ id: "p0", name: "Denek-A1", species: "Fare", breed: "", age: 1, weight: 0.02, owner_name: "", owner_phone: "",
  operator_email: "", created_at: TARIH }];
const SEANSLAR = [{ id: 100, patient_name: "Denek-A1", session_date: TARIH, start_time: TARIH, end_time: TARIH, duration_minutes: 5,
  treatment_mode: "Manuel", status: "completed", operator_email: "" }];
const AI = [{ id: 1, created_at: TARIH, mode: "researcher", module_id: "em_fantom", module_label: "Fantom Tümör", patient_name: "Denek-A1",
  patient_uuid: "", operator_email: "", input_type: "image", result_summary: "Fantom (DEMO)", result_detail: {}, confidence: 0.6,
  review_status: "", review_note: "", reviewed_by: "", reviewed_at: "", review_history_count: 0 }];

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

const EKRANLAR = { hasta: PatientScreen, seans: TreatmentHistoryScreen, ai: AiHistoryScreen } as const;
type EkranAdi = keyof typeof EKRANLAR;

let s: Sahne;
beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

async function metin(ekran: EkranAdi, mod: UserMode): Promise<string> {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/patients")) return [200, { status: "success", data: HASTALAR, total: HASTALAR.length }];
    if (yontem === "GET" && yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : SEANSLAR];
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: AI }];
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const Bilesen = EKRANLAR[ekran];
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <Bilesen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  return document.body.textContent || "";
}

// [ekran, veteriner metni (AYNEN kalmalı), araştırma metni]
const BEKLENEN: [EkranAdi, string, string][] = [
  ["hasta", "Hasta Veritabanı", "Örnek / Denek Veritabanı"],
  ["hasta", "Yeni Hasta Kayıt", "Yeni Örnek Kaydı"],
  ["seans", "Hastalarınıza ait geçmiş seans kayıtları ve raporlamalar.", "Örneklerinize ait geçmiş seans kayıtları ve raporlamalar."],
  ["ai", "Tüm hastalar", "Tüm örnekler"],
];

describe("SGI-4.1 — araştırma profilinde ekran içi metinler klinik dili taşımaz; veteriner metinleri aynen", () => {
  it.each(BEKLENEN)("KRİTİK: %s ekranı — araştırmada klinik metin '%s' YOK, yerinde '%s'", async (ekran, klinik, arastirma) => {
    const t = await metin(ekran, "researcher");
    expect(t).not.toContain(klinik);
    expect(t).toContain(arastirma);
  });

  it.each(BEKLENEN)("KARŞIT: %s ekranı — veterinerde '%s' AYNEN, araştırma metni '%s' görünmez", async (ekran, klinik, arastirma) => {
    const t = await metin(ekran, "veterinarian");
    expect(t).toContain(klinik);
    expect(t).not.toContain(arastirma);
  });
});
