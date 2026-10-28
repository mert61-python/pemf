/**
 * @jest-environment jsdom
 */
/**
 * D6.22 (B-6.10 · B-6.17) + İG-6.134 — AI Geçmişi takip grafiği saklı `null` ölçümü 0 ÇİZMEZ, yönü bilinmeyen ölçütün artışını yeşil
 * "iyiye gidiş" rengiyle GÖSTERMEZ; Fantom ve Yara Kapanma (Scratch) analizlerinde seri GERÇEK yanıt şeklinden kurulur.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSURLAR (HEAD ebf1c3fe):
 *  · B-6.10: `takipSerisi.ts` `Number(ham)` → `Number(null) === 0`: güvensiz kaydedilen analiz (Böbrek CT `logAiResult`'a güven
 *    vermez → `confidence: extra?.confidence ?? null`) grafikte 0 çubuğu oluyordu.
 *  · B-6.17: `TakipGrafigi` her artışı `colors.success` ile boyuyordu (güven artışı, tümör sayısı artışı = yeşil ▲).
 *  · İG-6.134: ölçüt tablosu `n_tumors` ve düz `closure_pct` arıyordu; GERÇEK yanıt `n_tumor` (`servers/ai_router.py` em_fantom
 *    dönüşü; tests/test_ai_hub_fantom_petri_v2v3_YANIT_ve_PARITE_AI2_C3.py `j["n_tumor"] == 5`) ve İÇ İÇE `closure.closure_pct`
 *    (`ai_hub/inference_paper_dilek_hoca` `scratch_analiz` → `"closure": res.get("closure")`; tests/test_scratch_endpoint.py
 *    `b["closure"]["closure_pct"] == 29.3`) — iki modülde takip grafiği HİÇ oluşmuyordu; eski test sahte (düz) şekille yeşildi.
 * KAYIT ŞEKLİ: `logAiResult` (AiHubScreen) gövdesi `result_detail: cleanDetail(detail)`, `confidence: extra?.confidence ?? null`;
 * backend satırı GERÇEK `/api/ai/log` yanıtından (`__fixtures__/aiLog.D271.json`, tests/test_ai_log_UI_fiksturu_GERCEK_backend_D271.py
 * üretir) — güvensiz kayıt orada da `confidence: null`. Yanıt değerleri backend testlerindeki GERÇEK alan şekilleri.
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, AppNavProvider, AiHistoryScreen, takipSerisiKur, TakipGrafigi, cleanDetail,
 * apiClient. Sahte (en alt kat): fetch, Supabase, toast, cihaz modülleri. AI sonuç DEĞERİ değişmez — yalnız gösterim.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "dr.t@klinik.com", user_metadata: {} } }),
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
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { cleanDetail } from "@/utils/aiDetail";
import { takipSerisiKur } from "@/utils/takipSerisi";
import { colors } from "@/theme/tokens";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const GERCEK_YANIT = require("./__fixtures__/aiLog.D271.json");
/** GERÇEK backend satırı — anahtar kümesi ve "güven verilmedi → null" sözleşmesi buradan gelir. */
const SABLON = GERCEK_YANIT.data.find((r: { confidence: unknown }) => r.confidence === null);

/** `logAiResult` gövdesinin backend'den GERİ okunmuş hâli (`thdb_ai_gecmisi`: result_detail JSON, confidence NULL kalır). */
function kayit(id: number, gun: string, moduleId: string, etiket: string, detay: unknown, guven?: number) {
  return {
    ...SABLON,
    id,
    created_at: `2026-10-${gun} 10:00:00`,
    mode: "veterinarian",
    module_id: moduleId,
    module_label: etiket,
    patient_name: "Mia",
    patient_uuid: "b27e9d04-5c1a-4f88-8e20-7a6b1f3c9d22",
    operator_email: "dr.t@klinik.com",
    result_summary: `${etiket} #${id}`,
    result_detail: JSON.parse(JSON.stringify(cleanDetail(detay))),
    confidence: guven ?? null,
  };
}

/** Yara Kapanma — GERÇEK `scratch_analiz` yanıt şekli (tests/test_scratch_endpoint.py `_SAHTE_SONUC` alanları + `status`). */
const scratch = (kapanma: number) => ({
  status: "success",
  n_cells: 2085,
  coverage_ratio: 0.47,
  closure: { closure_pct: kapanma, mean_gap_um: 428.0, max_gap_um: 1278.4, gap_area_mm2: 1.0422, scratch_yonu: "dikey" },
  scratch_yonu: "dikey",
  pixel_mm: 0.0016,
  input_image_base64: "R".repeat(5000),
  closure_image_base64: "C".repeat(5000),
});
/** Fantom — GERÇEK em_fantom yanıt şekli (`servers/ai_router.py` dönüş sözlüğü: n_tumor / n_healthy / tumor_regions …). */
const fantom = (n: number) => ({
  status: "success",
  success: true,
  error: null,
  n_tumor: n,
  n_healthy: 2,
  method: "yolo",
  mm_per_px: 0.5,
  tumor_regions: Array.from({ length: n }, (_, i) => ({ tumor_id: `T${i + 1}`, area_mm2: 12.5, E_cancer: 0.31 })),
  image_base64: "F".repeat(5000),
});
const petri = (n: number) => ({ status: "success", n_wells: n, n_cancer: 3, image_base64: "P".repeat(5000) });

let s: Sahne;
beforeEach(() => {
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
});

function Mod({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

async function kur(satirlar: unknown[]) {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol.startsWith("/ai/log")) {
      return [200, yol.includes("before_id") ? { status: "success", data: [] } : { status: "success", data: satirlar }];
    }
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <AiHistoryScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.bosalt(10);
  expect(s.metin()).toContain(`#${(satirlar[0] as { id: number }).id}`); // ARA: gerçek yanıt yüklendi
  await s.tikla("Filtre: Mia");
}

const grafik = () => document.querySelector('[data-testid="takip-grafigi"]') as HTMLElement | null;
/** Her sütunun değer etiketi (`{deger}{birim}`), soldan sağa. */
function cubukDegerleri(): string[] {
  const kap = document.querySelector('[data-testid="takip-grafigi-cubuklar"]');
  return Array.from(kap?.children ?? []).map((sutun) => (sutun.firstElementChild?.textContent ?? "").trim());
}
function farkEl(): HTMLElement {
  const g = grafik();
  expect(g).not.toBeNull();
  return g!.children[1] as HTMLElement;
}
const rgb = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
};
const renk = (e: HTMLElement) => window.getComputedStyle(e).color;

test("KRİTİK B-6.10: güveni saklanmamış (null) Böbrek CT kayıtları 0 diye ÇİZİLMEZ — ölçüm yok, grafik yok", async () => {
  await kur([
    kayit(12, "12", "kidney_ct", "Böbrek CT", { n_detections: 0, class_counts: {} }),
    kayit(11, "11", "kidney_ct", "Böbrek CT", { n_detections: 2, class_counts: { "Kidney Stone": 2 } }),
  ]);
  expect(s.metin()).toContain("2 kayıt (filtreli)");
  expect(cubukDegerleri()).toEqual([]);
  expect(grafik()).toBeNull();
});

test("KRİTİK B-6.10: arada güveni null bir kayıt — seriden ATLANIR (62 → 81; araya 0 girmez)", async () => {
  await kur([
    kayit(23, "23", "kidney_disease", "Böbrek Hastalığı (CKD)", { label: "ckd", prob_pct: 81 }, 0.81),
    kayit(22, "22", "kidney_disease", "Böbrek Hastalığı (CKD)", { label: "ckd", prob_pct: null }),
    kayit(21, "21", "kidney_disease", "Böbrek Hastalığı (CKD)", { label: "ckd", prob_pct: 62 }, 0.62),
  ]);
  expect(cubukDegerleri()).toEqual(["62%", "81%"]);
});

test("KRİTİK B-6.17: GÜVEN artışı yeşil 'iyiye gidiş' rengi ALMAZ (nötr)", async () => {
  await kur([
    kayit(32, "22", "kidney_disease", "Böbrek Hastalığı (CKD)", { label: "ckd", prob_pct: 81 }, 0.81),
    kayit(31, "21", "kidney_disease", "Böbrek Hastalığı (CKD)", { label: "ckd", prob_pct: 62 }, 0.62),
  ]);
  const f = farkEl();
  expect(f.textContent).toBe("▲ 19%");
  expect(renk(f)).not.toBe(rgb(colors.success));
  expect(renk(f)).toBe(rgb(colors.textMuted));
});

test("KRİTİK İG-6.134: Yara Kapanma GERÇEK (iç içe closure.closure_pct) kayıtlarından seri KURULUR; kapanma artışı YEŞİL kalır", async () => {
  await kur([
    kayit(42, "14", "cell_scratch", "Yara Kapanma (Scratch)", scratch(41.62)),
    kayit(41, "13", "cell_scratch", "Yara Kapanma (Scratch)", scratch(29.3)),
  ]);
  expect(cubukDegerleri()).toEqual(["29.3%", "41.62%"]);
  const f = farkEl();
  expect(f.textContent).toBe("▲ 12.32%"); // kayan nokta artığı (12.319999999999997) gösterilmez
  expect(renk(f)).toBe(rgb(colors.success));
});

test("KARŞIT İG-6.134: kapanma AZALIRSA uyarı rengi (yön bilinen ölçüt)", async () => {
  await kur([
    kayit(52, "14", "cell_scratch", "Yara Kapanma (Scratch)", scratch(29.3)),
    kayit(51, "13", "cell_scratch", "Yara Kapanma (Scratch)", scratch(41.62)),
  ]);
  const f = farkEl();
  expect(f.textContent).toBe("▼ 12.32%");
  expect(renk(f)).toBe(rgb(colors.warning));
});

test("KRİTİK İG-6.134 + B-6.17: Fantom GERÇEK (n_tumor) kayıtlarından seri KURULUR; tümör sayısı artışı YEŞİL DEĞİL", async () => {
  await kur([
    kayit(62, "16", "em_fantom", "Fantom Tümör Analizi", fantom(6)),
    kayit(61, "15", "em_fantom", "Fantom Tümör Analizi", fantom(5)),
  ]);
  expect(cubukDegerleri()).toEqual(["5", "6"]);
  const f = farkEl();
  expect(f.textContent).toBe("▲ 1");
  expect(renk(f)).not.toBe(rgb(colors.success));
  expect(renk(f)).toBe(rgb(colors.textMuted));
});

test("SINIR (GERÇEK takipSerisiKur): null / boş metin / mantıksal / düz (iç içe olmayan) değer ölçüm DEĞİL; sayısal metin ölçümdür", () => {
  const k = (id: number, gun: string, closure: unknown) =>
    kayit(id, gun, "cell_scratch", "Yara Kapanma (Scratch)", { status: "success", closure });
  const seri = takipSerisiKur([
    k(1, "01", { closure_pct: 10 }),
    k(2, "02", { closure_pct: null }),
    k(3, "03", { closure_pct: "" }),
    k(4, "04", { closure_pct: true }),
    k(5, "05", 55), // closure sözlük değil → yol izlenemez
    { ...k(6, "06", null), result_detail: { closure_pct: 70 } }, // düz alan GERÇEK şekil değil
    k(7, "07", { closure_pct: "30.5" }),
  ] as never);
  expect(seri?.noktalar.map((n) => n.deger)).toEqual([10, 30.5]);
  expect(seri?.artisIyi).toBe(true);
  expect(takipSerisiKur([kayit(8, "08", "disease", "Hastalık Analizi", {}, 0.4), kayit(9, "09", "disease", "Hastalık Analizi", {}, 0.5)] as never)?.artisIyi).toBe(false);
});

test("KARŞIT: Petri (n_wells) eskisi gibi çizilir; değişim yoksa nötr ■ 0", async () => {
  await kur([
    kayit(72, "18", "em_petri", "Petri Kuyu Analizi", petri(24)),
    kayit(71, "17", "em_petri", "Petri Kuyu Analizi", petri(24)),
  ]);
  expect(cubukDegerleri()).toEqual(["24", "24"]);
  const f = farkEl();
  expect(f.textContent).toBe("■ 0");
  expect(renk(f)).toBe(rgb(colors.textMuted));
});
