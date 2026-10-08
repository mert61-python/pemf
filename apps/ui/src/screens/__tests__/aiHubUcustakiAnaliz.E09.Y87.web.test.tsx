/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E09 (İG-6.24) · SAHİP KARARI Y87 — uçuştaki AI analizi, hasta değiştirilse bile BAŞLATILDIĞI hastaya yazılır (analiz başladığı
 * andaki `{id, name}` görüntüsüne bağlanır); atılmaz, yeni hastaya yazılmaz.
 * ===========================================================================================================================
 * ÖLÇÜLEN KUSUR (ADAY İG-6.24, gerçek backend + Chrome, yanıt 10 sn bekletildi): Hastalık Mia→Pamuk → `ai_analyses`
 * `patient_name 'Mia'` + kimlik **Pamuk** (3/3); Kedi Sesi Pamuk→Mia aynı. Kök: `logAiResult` adı çağıranın kapanışından
 * (başlangıçtaki hasta), KİMLİĞİ modül değişkeninden (tamamlanma anındaki hasta) okuyordu → satır iki hayvanın geçmişinde.
 * VisionModule ise uçuştaki analizi İPTAL edip atıyordu (S5'in reddedilen (b) seçeneği — Y87 "atılmaz").
 *
 * Kollar: davranış — yanıt ASKIDA iken GERÇEK PatientGate'ten hasta değişir, sonra yanıt gelir; `/ai/log` gövdesinde kimlik VE ad
 * başlangıçtaki hastanın (ev sahibi FGS + ses; hekim Hastalık, Kedi Sesi, Yüz Ağrısı/VisionModule). Yapısal — `logAiResult(`
 * çağıranları kaynaktan TÜRETİLİR (TypeScript AST): her çağrının ilk argümanı, aynı async işlevde İLK `await`'ten ÖNCE
 * `hastaAnligi()` ile alınmış bir ad olmalı (13 çağrının hepsi; davranış kolunun ölçmediği modüller dahil).
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider (Kural 2), AppNavProvider, PatientGate, AiHubScreen, apiClient.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("sahip@ev.com");
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ research: false, realtime: false }),
  EntitlementProvider: ({ children }: { children: unknown }) => children,
}));
// Abonelik penceresi (UpgradeModal) yerel safe-area modülünü ister (jest-expo YEREL çözer) — kapının konusu değil.
jest.mock("@/components/UpgradeModal", () => ({ UpgradeModal: () => null }));
jest.mock("expo-camera", () => ({ CameraView: () => null, useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
jest.mock("expo-audio", () => ({
  useAudioRecorder: () => ({ record: jest.fn(), stop: jest.fn(), prepareToRecordAsync: jest.fn(), uri: null }),
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
}));
jest.mock("expo-image-picker", () => ({ MediaTypeOptions: { Images: "Images" }, launchImageLibraryAsync: jest.fn(),
  launchCameraAsync: jest.fn() }));
jest.mock("expo-image-manipulator", () => ({ SaveFormat: { JPEG: "jpeg" }, manipulateAsync: jest.fn() }));
jest.mock("expo-document-picker", () => ({ getDocumentAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({ readAsStringAsync: jest.fn(), documentDirectory: "file:///" }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";
import { act } from "react";
import {
  aiLogGovdeleri, aparat, Askida, cihazSahteleriniKur, cihazSahteleriniSok, hastaSec, kurAiHub, Sahne,
} from "./aiHubAparati";
import type { UserMode } from "@/context/UserModeContext";

const SAHIP = "sahip@ev.com";
const HASTALAR = [
  { id: "u-mia", name: "Mia", operator_email: SAHIP, species: "Kedi" },
  { id: "u-pamuk", name: "Pamuk", operator_email: SAHIP, species: "Kedi" },
];
const FGS = { status: "success", detected: true, fgs_total: 1, pain_level: "Mild", raw_fgs: { action_units: {} },
  action_units: {}, hw_status: "idle", hw_params: {} };
const SES = { status: "success", top_1_class: "Happy", top_1_prob: 0.91, top_k: [], guvenilir: true };
const HASTALIK = { status: "success", results: [{ disease: "Gastroenteritis", probability: 0.71 }] };

let s: Sahne;
beforeEach(() => {
  s = new Sahne();
  cihazSahteleriniKur();
});
afterEach(async () => {
  await s.sok();
  cihazSahteleriniSok();
});

/** `uc`a giden istek ASKIDA kalır; `baslat` analizi başlatır; askıdayken Mia → Pamuk; yanıt gelir; `/ai/log` gövdesi döner. */
async function ucustaHastaDegisir(mod: UserMode, uc: string, veri: unknown, baslat: () => Promise<void>) {
  const bekle = new Askida();
  await kurAiHub(s, {
    mod, hastalar: HASTALAR,
    ozel: (yol, _g, yontem) => (yontem === "POST" && yol === uc ? bekle : undefined),
  });
  await hastaSec(s, "Mia");
  await baslat();
  expect(aparat.ham.filter((i) => i.yontem === "POST" && i.yol === uc)).toHaveLength(1); // ARA: analiz uçuşta
  expect(aiLogGovdeleri()).toHaveLength(0);
  await hastaSec(s, "Pamuk");
  expect(s.metin()).toMatch(/(Evcil Hayvanım|Hasta)\s*:\s*Pamuk/); // ARA: seçim değişti
  await act(async () => { bekle.serbest(200, veri); });
  await s.bosalt(10);
  return aiLogGovdeleri();
}

const hastaAlanlari = (g: Record<string, unknown>) => [g.patient_id, g.patient_name];

it("KRİTİK E09/Y87: ev sahibi FGS uçuştayken hasta değişirse kayıt BAŞLATILAN hastaya (kimlik + ad) yazılır", async () => {
  const g = await ucustaHastaDegisir("pet_owner", "/ai/vision/landmark", FGS, async () => {
    aparat.dosyaSiradaki = new File([new Uint8Array([1])], "mia.jpg", { type: "image/jpeg" });
    await s.metneTikla("Galeriden Seç");
    await s.metneTikla("Teşhis Et");
  });
  expect(g.map(hastaAlanlari)).toEqual([["u-mia", "Mia"]]);
});

it("KRİTİK E09/Y87: ev sahibi SES analizi uçuştayken hasta değişirse kayıt BAŞLATILAN hastaya yazılır", async () => {
  const g = await ucustaHastaDegisir("pet_owner", "/ai/sound/cat", SES, async () => {
    aparat.dosyaSiradaki = new File([new Uint8Array([2])], "mia.wav", { type: "audio/wav" });
    await s.metneTikla("Ses Yükle");
    await s.metneTikla("Sesi Analiz Et");
  });
  expect(g.map(hastaAlanlari)).toEqual([["u-mia", "Mia"]]);
});

it("KRİTİK E09/Y87: hekim HASTALIK analizi uçuştayken hasta değişirse kayıt BAŞLATILAN hastaya yazılır", async () => {
  const g = await ucustaHastaDegisir("veterinarian", "/ai/disease", HASTALIK, async () => {
    await s.metneTikla("Hastalık");
    await s.metneTikla("İştah Kaybı");
    await s.metneTikla("Kusma");
    await s.metneTikla("Teşhisi Başlat");
  });
  expect(g.map(hastaAlanlari)).toEqual([["u-mia", "Mia"]]);
});

it("KRİTİK E09/Y87: hekim KEDİ SESİ modülü uçuştayken hasta değişirse kayıt BAŞLATILAN hastaya yazılır", async () => {
  const g = await ucustaHastaDegisir("veterinarian", "/ai/sound/cat", SES, async () => {
    await s.metneTikla("Kedi Sesi");
    aparat.dosyaSiradaki = new File([new Uint8Array([3])], "mia.wav", { type: "audio/wav" });
    await s.metneTikla("Ses Yükle");
    await s.metneTikla("Ses Analizini Başlat");
  });
  expect(g.map(hastaAlanlari)).toEqual([["u-mia", "Mia"]]);
});

it("KRİTİK E09/Y87: hekim YÜZ AĞRISI (VisionModule) analizi hasta değişince ATILMAZ — başlatılan hastaya yazılır", async () => {
  const g = await ucustaHastaDegisir("veterinarian", "/ai/vision/landmark", FGS, async () => {
    await s.metneTikla("Yüz Ağrısı (FGS)");
    aparat.dosyaSiradaki = new File([new Uint8Array([4])], "mia.jpg", { type: "image/jpeg" });
    await s.metneTikla("Galeriden Seç");
    await s.metneTikla("AI Analizini Başlat");
  });
  expect(g.map(hastaAlanlari)).toEqual([["u-mia", "Mia"]]);
});

it("KARŞIT E09: hasta değişmeden yapılan analiz o anki hastaya yazılır (Pamuk seçiliyken Pamuk)", async () => {
  await kurAiHub(s, { mod: "veterinarian", hastalar: HASTALAR,
    ozel: (yol, _g, yontem) => (yontem === "POST" && yol === "/ai/disease" ? [200, HASTALIK] : undefined) });
  await hastaSec(s, "Mia");
  await hastaSec(s, "Pamuk");
  await s.metneTikla("Hastalık");
  await s.metneTikla("İştah Kaybı");
  await s.metneTikla("Kusma");
  await s.metneTikla("Teşhisi Başlat");
  expect(aiLogGovdeleri().map(hastaAlanlari)).toEqual([["u-pamuk", "Pamuk"]]);
});

// ── YAPISAL: her `logAiResult(` çağıranı hastayı analiz BAŞINDA alır (kaynaktan türetilir) ──────────────────────────────
const KAYNAK = path.join(__dirname, "..", "AiHubScreen.tsx");

function cagriDenetimi(metin: string) {
  const sf = ts.createSourceFile("AiHubScreen.tsx", metin, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const cagrilar: ts.CallExpression[] = [];
  const gez = (d: ts.Node) => {
    if (ts.isCallExpression(d) && ts.isIdentifier(d.expression) && d.expression.text === "logAiResult") cagrilar.push(d);
    ts.forEachChild(d, gez);
  };
  gez(sf);
  const ihlal: string[] = [];
  for (const c of cagrilar) {
    const satir = sf.getLineAndCharacterOfPosition(c.getStart()).line + 1;
    let fn: ts.Node | undefined = c.parent;
    while (fn && !(ts.isArrowFunction(fn) || ts.isFunctionDeclaration(fn) || ts.isFunctionExpression(fn))) fn = fn.parent;
    const ilk = c.arguments[0];
    if (!fn || !ilk || !ts.isIdentifier(ilk)) { ihlal.push(`${satir}: ilk argüman bir hasta görüntüsü adı değil`); continue; }
    let bildirim: ts.VariableDeclaration | undefined;
    let ilkAwait = Infinity;
    const icGez = (d: ts.Node) => {
      if (ts.isVariableDeclaration(d) && ts.isIdentifier(d.name) && d.name.text === ilk.text && d.initializer
          && ts.isCallExpression(d.initializer) && ts.isIdentifier(d.initializer.expression)
          && d.initializer.expression.text === "hastaAnligi") bildirim = d;
      if (ts.isAwaitExpression(d)) ilkAwait = Math.min(ilkAwait, d.getStart());
      if (d !== fn && (ts.isArrowFunction(d) || ts.isFunctionDeclaration(d) || ts.isFunctionExpression(d))) return;
      ts.forEachChild(d, icGez);
    };
    ts.forEachChild(fn, icGez);
    if (!bildirim) ihlal.push(`${satir}: '${ilk.text}' bu işlevde hastaAnligi() ile alınmamış`);
    else if (bildirim.getStart() > ilkAwait) ihlal.push(`${satir}: hasta görüntüsü İLK await'ten SONRA alınıyor (tamamlanma anındaki hasta)`);
  }
  return { sayi: cagrilar.length, ihlal };
}

it("KRİTİK E09/Y87 (yapısal): 13 logAiResult çağıranının HEPSİ hastayı analiz başında (ilk await'ten önce) alır", () => {
  const metin = fs.readFileSync(KAYNAK, "utf8");
  const { sayi, ihlal } = cagriDenetimi(metin);
  // ARA (araç kanıtı): AST'nin bulduğu çağrı sayısı ham metindeki `logAiResult(` sayısıyla aynı (tanım hariç) ve ≥ 13.
  expect(sayi).toBe((metin.match(/\blogAiResult\(/g) || []).length - 1);
  expect(sayi).toBeGreaterThanOrEqual(13);
  expect(ihlal).toEqual([]);
});

it("KARŞIT (araç kanıtı): yapısal denetim geç alınan görüntüyü ve görüntüsüz çağrıyı BULUR", () => {
  const ornek = [
    "async function logAiResult(h: any, m: string) {}",
    "const a = async () => { const hasta = hastaAnligi(); await f(); logAiResult(hasta, 'x'); };",
    "const b = async () => { await f(); const hasta = hastaAnligi(); logAiResult(hasta, 'x'); };",
    "const c = async () => { await f(); logAiResult(adi, 'x'); };",
  ].join("\n");
  const { sayi, ihlal } = cagriDenetimi(ornek);
  expect(sayi).toBe(3);
  expect(ihlal).toEqual([
    "3: hasta görüntüsü İLK await'ten SONRA alınıyor (tamamlanma anındaki hasta)",
    "4: 'adi' bu işlevde hastaAnligi() ile alınmamış",
  ]);
});
