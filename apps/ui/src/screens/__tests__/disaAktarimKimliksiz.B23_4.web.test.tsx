/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * B2-3.4 (2-B bağımsız incelemesi, A3) — Seans Geçmişi: kimlik DÜŞTÜKTEN sonra "Tümünü Excel/CSV İndir" kliniğin TÜM seans
 * geçmişini indirir (Y103 boş listesini dolanır).
 * =======================================================================================================================
 * ÖLÇÜLEN KUSUR: D2.70 kimliksizken listeyi boşaltır, ama `scope` durumu kilitten sonra "all" kalırsa `kapsamDaraltilmis`
 * (`scope === "mine" || arama`) `false` olur → CSV düğmesi "Tümünü" der ve `GET /history/export_csv` id listesiz (= tüm
 * klinik: hasta adı, not, operatör) gider. Kapsam sekmesi kimliksizken gizlendiği için "Benim"e dönüş de yoktur.
 * KARŞIT: kimlikli hekim "Tüm Klinik"te bilinçli tam dışa aktarım yapar; operatörsüz tek hekimli klinik (Kural 2) etkilenmez.
 *
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (gerçek hareketsizlik zamanlayıcısı), OperatorSwitcher (PIN),
 * AppNavProvider, TreatmentHistoryScreen, dosyaIndir, apiClient. Sahte yalnız `fetch` (kaydedici), Supabase, toast, cihaz modülleri.
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

import React, { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { aktifOperator, cipEtiketi, pinleSec, Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

const A = "dr.a@klinik.com";
const B = "dr.b@klinik.com";
const TARIH = "2026-10-01 10:00:00";
const IKI_HEKIM: SahteOperator[] = [{ email: A, display_name: "Dr. A" }, { email: B, display_name: "Dr. B" }];

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
beforeEach(() => { jest.useFakeTimers(); s = new Sahne(); });
afterEach(async () => { await s.sok(); jest.useRealTimers(); });

async function kur(oturum: string, operatorler: SahteOperator[], sahipler: Record<string, string>) {
  mockOturum.eposta = oturum;
  const seanslar = Object.entries(sahipler).map(([ad, e], i) => ({
    id: 100 + i, patient_name: `Seans${ad}`, session_date: TARIH, start_time: TARIH, end_time: TARIH,
    duration_minutes: 5, treatment_mode: "Manuel", status: "completed", operator_email: e,
  }));
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/history/export")) return [200, { status: "bos", mesaj: "taklit" }];
    if (yontem === "GET" && yol.startsWith("/history/")) return [200, yol.includes("cursor=") ? [] : seanslar];
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider><UserModeProvider><Mod><OperatorProvider><AppNavProvider navigateTo={() => undefined}>
      <OperatorSwitcher />
      <TreatmentHistoryScreen />
    </AppNavProvider></OperatorProvider></Mod></UserModeProvider></AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
}

// B2-3.4 (orkestratör sıkılaştırması): backend `export_csv` BOŞ `session_ids` için de TÜM kliniği verir ("Boş = tümü") →
// "tüm klinik dökümü" = boş OLMAYAN id listesi taşımayan her istek (yalnız `session_ids=` parametresinin varlığı yetmez).
const disaAktarimlar = () => kayit.filter((k) => k.yontem === "GET" && k.yol.startsWith("/history/export"));
/** "Tümünü/Görünenleri Excel/CSV İndir" düğmesi (etiketi kapsamı izler). */
async function csvTikla() {
  const metin = ["Tümünü Excel/CSV İndir", "Görünenleri Excel/CSV İndir"].find((m) => s.metin().includes(m));
  if (!metin) throw new Error(`CSV düğmesi yok. Govde: ${s.metin().slice(0, 300)}`);
  await s.metneTikla(metin);
  await s.bosalt(10);
}

describe("B2-3.4 — kimlik düştükten sonra dışa aktarım kliniğin tüm geçmişini İNDİRMEZ", () => {
  it("KRİTİK: A 'Tüm Klinik'teyken hareketsizlik kilidi → 'CSV İndir' tüm-klinik dökümü İSTEMEZ", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik seansları");
    for (let t = 0; t < AUTO_LOCK_MS + 31_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBeNull(); // ARA DOĞRULAMA: kilit düştü, liste boş
    expect(s.metin()).not.toContain("SeansB");
    await csvTikla();
    const tumu = disaAktarimlar().filter((k) => k.yol.startsWith("/history/export_csv") && !/session_ids=\d/.test(k.yol));
    expect(tumu).toEqual([]);
  });

  it("KRİTİK: elle 'Kilitle' sonrası da aynı (Tüm Klinik → Kilitle → CSV)", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik seansları");
    await s.tikla(cipEtiketi());
    await s.tikla("Oturumu kilitle");
    await s.bosalt(10);
    expect(aktifOperator()).toBeNull();
    await csvTikla();
    expect(disaAktarimlar().filter((k) => !/session_ids=\d/.test(k.yol))).toEqual([]);
  });

  it("KARŞIT: kimlikli hekim 'Tüm Klinik'te bilinçli TAM dışa aktarım yapar (id listesiz istek gider)", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await s.tikla("Tüm klinik seansları");
    await csvTikla();
    expect(disaAktarimlar().filter((k) => k.yol.startsWith("/history/export_csv") && !/session_ids=\d/.test(k.yol)).length).toBe(1);
  });

  it("KARŞIT (Kural 2): operatörsüz tek hekimli klinikte 'Tüm Klinik' tam dışa aktarımı gider", async () => {
    const T = "tek@klinik.com";
    await kur(T, [], { T, S: "" });
    await s.tikla("Tüm klinik seansları");
    await csvTikla();
    expect(disaAktarimlar().filter((k) => k.yol.startsWith("/history/export_csv") && !/session_ids=\d/.test(k.yol)).length).toBe(1);
  });

  it("KARŞIT: kimlikli 'Benim' kapsamında dışa aktarım YALNIZ görünen kayıtların kimlikleriyle gider", async () => {
    await kur(A, IKI_HEKIM, { A, B, S: "" });
    await pinleSec(s, "Dr. A");
    await s.bosalt(10);
    await csvTikla();
    const d = disaAktarimlar();
    expect(d.length).toBe(1);
    expect(d[0].yol).toContain("session_ids=100,102");
  });
});
