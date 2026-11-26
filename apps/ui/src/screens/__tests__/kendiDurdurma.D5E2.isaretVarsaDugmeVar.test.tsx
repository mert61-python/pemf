// Author: mertaygn, cglrgrkn
/**
 * D5.E2 (İG-6.30 · K-3 · D5 3. dalga) — A-51 değişmezi: ekranın `KendiDurdurmaIsareti` TAKILIYSA (kayan ACİL DURDUR gizli) o ekran
 * KENDİ ACİL DURDUR'unu ÇİZER ve basınca durdurma GERÇEKTEN gider. Her işaret takan ekran (Ana Ekran + Kontrol) × {STM bağlı, kopuk}
 * × {seans aktif, seanssız bobin çalışıyor, boşta}.
 * ======================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (HEAD d38b0db5, çürütme r2): Kontrol ekranının kendi düğmesi `isStmConnected ? (…) : null` koşuluna girer,
 * `<KendiDurdurmaIsareti />` koşulsuz kalırsa STM kopukken ekranda durdurma kontrolü SIFIR (işaret takılı → kayan düğme gizli, ekranın
 * düğmesi yok) — 55 ilgili jest dosyası (1203 test) YEŞİL kaldı: D1E02 Kontrol rotası için `Patlayan` kullanır, `ControlScreen.*`
 * testleri hep `stm: "online"` koşar. Aynı aile k630d (Ana Ekran işareti düğmenin ÇİZİLMEDİĞİ dala takılır) yalnız D1E02 (B) ile
 * yakalanıyordu. Bu kapı değişmezi TABLO olarak ölçer (planın "rota × çalışıyor/boşta" FARKLI yönteminin işaret takan ekranlara
 * indirgenmişi).
 *
 * GERÇEK: `useKendiDurdurmaKaydi` (AppShell'in kullandığı kayıt), `KendiDurdurmaIsareti`, `DashboardScreen`, `ControlScreen`,
 * `PatientGate`, `SessionProgressCard`, `useSessionControl`, `performEmergencyStop`, `apiClient`. Sahte EN ALT katta: `global.fetch`
 * (kaydedici; `/session/active` tabloya göre) + bağlamlar (canlı veri, kimlik, gezinme) + ilgisiz ağır paneller.
 * ⚠️ Yalnız KAPI: ACİL DURDUR / STOP davranışı değişmez; bu dosya ürün koduna dokunmaz. "Kendi düğme" = ekranın içinde erişim
 * etiketi /acil durdur/i olan ve basınca `/hardware/emergency_stop` gönderen kontrol (görünür ama ölü düğme SAYILMAZ).
 *
 * ⚠️ MUTASYON: Kontrol düğmesi STM koşuluna girer, işaret koşulsuz (r2) → "control × offline × boşta" KIRMIZI; Ana Ekran işareti
 * düğmesiz dala (k630d) → "dashboard × boşta" KIRMIZI; Ana Ekran düğmesi STM koşuluna girer → "dashboard × offline × seans" KIRMIZI;
 * Kontrol düğmesi STM kopukken `disabled` ya da `onPress` boş → "control × … × boşta" KIRMIZI (çizili ama basılamaz).
 * D5.E2 TUR 3 (çürütme 2): ACİL DURDUR montaj başına TEK atış (e2d1) → tablo "ikinciBasis" + "geçiş + basış" KIRMIZI; üçüncü bir ekran
 * düğmesiz işaret takar (e2d2) → "kapalı dünya" KIRMIZI; bobin listesi boşken Kontrol düğmesi çizilmez (e2d3) → "… × bobin listesi bos"
 * KIRMIZI.
 * D5.E2 TUR 3b (çürütme 3 f1 / g1): uçuştaki durdurma bitmeden gelen basışı yutan "çift istek koruması" (`useSessionControl.emergencyStop`
 * içinde `if (acilUcustaRef.current) return;`) → "panik çift dokunuş" KIRMIZI; izinli ekran modülü işareti taşıyan bir ALT bileşeni dışa
 * aktarır ve üçüncü bir ekran onu takar → "kapalı dünya" KIRMIZI (işaret yalnız ekran bileşeninin KENDİ gövdesinde).
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockSnap: Record<string, unknown>;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
    donanimBelirsiz: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" }, logout: jest.fn() }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operator: "Dr. X" }),
  useOperatorOptional: () => null,
}));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigate: jest.fn(), goTo: jest.fn(), navigateTo: jest.fn(),
    selectedPatient: { id: "1", name: "Boncuk" }, setSelectedPatient: jest.fn(),
  }),
}));
jest.mock("@/components/ui/NotificationCenter", () => ({ NotificationCenter: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));

import { act, fireEvent, render } from "@testing-library/react-native";
import * as fs from "fs";
import * as path from "path";
import React from "react";
import { Alert, Text } from "react-native";
import * as ts from "typescript";
import { useKendiDurdurmaKaydi } from "@/components/ui/KendiDurdurmaKontrolu";
import { ControlScreen } from "@/screens/ControlScreen";
import { DashboardScreen } from "@/screens/DashboardScreen";

type Ekran = "dashboard" | "control";
type Stm = "online" | "offline";
type Durum = "seans_aktif" | "seanssiz_bobin_calisiyor" | "bosta";
/** D5.E2 TUR 3 (çürütme 2 e2d3): değişmez bobin listesinden BAĞIMSIZ — dolu (1–7), BOŞ (`coils: []`) ya da alan HİÇ yok. */
type Bobin = "dolu" | "bos" | "yok";
/** Tablonun ölçtüğü ekranların MODÜLLERİ — kapalı-dünya kolu işaret takan modül kümesinin TAM bu olduğunu doğrular (e2d2). */
const EKRAN_MODULU: Record<Ekran, string> = { dashboard: "screens/DashboardScreen.tsx", control: "screens/ControlScreen.tsx" };
/** D5.E2 TUR 3b (çürütme 3 g1): izinli modülde işaret YALNIZ bu üst düzey bileşenin gövdesinde (alt bileşenle dışa taşınamaz). */
const EKRAN_BILESENI: Record<Ekran, string> = { dashboard: "DashboardScreen", control: "ControlScreen" };

const cagrilar: string[] = [];
let seansAktif = false;
const govde = (o: unknown) => ({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });
const yanit = (o: unknown) => Promise.resolve(govde(o));
/** D5.E2 TUR 3b (f1): `true` iken `/hardware/emergency_stop` yanıtı BEKLETİLİR (durdurma uçuşta kalır); test sonunda topluca çözülür. */
let beklet = false;
const bekleyenler: (() => void)[] = [];
const durdurmaSayisi = () => cagrilar.filter((y) => y === "/hardware/emergency_stop").length;

const SEANS = { isActive: true, mode: "Manuel", frequencyHz: 50, intensityMt: 1, remainingMin: 29, elapsedSec: 10, durationSec: 1800 };
const HAZIR = { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 };

/** Tablonun bir satırının canlı durumu. STM kopukken bobin durumu BİLİNMEZ (backend `running:false`, `connected:false` bildirir). */
function kur(stm: Stm, durum: Durum, bobin: Bobin = "dolu") {
  seansAktif = durum === "seans_aktif";
  const calisan = stm === "online" ? (durum === "seans_aktif" ? [1, 2, 3, 4, 5, 6, 7] : durum === "seanssiz_bobin_calisiyor" ? [1] : []) : [];
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm, internet: "offline",
    patient: null,
    activeTreatment: seansAktif ? SEANS : HAZIR,
    notifications: [],
    coils: (bobin === "bos" ? [] : [1, 2, 3, 4, 5, 6, 7]).map((id) => ({
      id, running: calisan.includes(id), connected: stm === "online", stm32Driven: true,
      frequencyHz: calisan.includes(id) ? 50 : 0, dutyCycle: calisan.includes(id) ? 30 : 0,
      objectTemp: null, magneticMt: 0, currentA: 0, ambientTemp: null, measuredFields: [],
    })),
    system: {}, sessions: [],
  };
  if (bobin === "yok") delete mockSnap.coils;
}

function Kabuk({ ekran }: { ekran: Ekran }) {
  const { takili, Saglayici } = useKendiDurdurmaKaydi();
  return (
    <>
      <Text testID="d5e2-isaret">{takili ? "takili" : "yok"}</Text>
      <Saglayici>{ekran === "dashboard" ? <DashboardScreen /> : <ControlScreen />}</Saglayici>
    </>
  );
}

const ETIKET = /acil durdur/i;

/** `i`. ACİL DURDUR'a bas, basış durdurma (`/hardware/emergency_stop`) gönderdi mi. */
async function bas(u: ReturnType<typeof render>, i: number): Promise<boolean> {
  const d = u.queryAllByLabelText(ETIKET)[i];
  if (!d) return false;
  cagrilar.length = 0;
  await act(async () => {
    fireEvent.press(d);
  });
  await act(async () => {});
  return cagrilar.includes("/hardware/emergency_stop");
}

/** Bir satırı ölç: işaret takılı mı, ekranın kendi ACİL DURDUR'u kaç tane, kaçı basınca durdurma gönderiyor (ilk başarılıda durur);
 *  D5.E2 TUR 3 (çürütme 2 e2d1): başarılı düğmeye AYNI ağaçta İKİNCİ kez basılır — o da durdurma göndermeli (tek atışlık değil). */
async function olc(ekran: Ekran, stm: Stm, durum: Durum, bobin: Bobin = "dolu") {
  kur(stm, durum, bobin);
  const u = render(<Kabuk ekran={ekran} />);
  await act(async () => {});
  const takili = u.getByTestId("d5e2-isaret").props.children === "takili";
  const dugme = u.queryAllByLabelText(ETIKET).length;
  let basilabilir = false;
  let ikinciBasis = false;
  for (let i = 0; i < dugme && !basilabilir; i += 1) {
    basilabilir = await bas(u, i);
    if (basilabilir) ikinciBasis = await bas(u, i);
  }
  u.unmount();
  return { ekran, stm, durum, bobin, takili, dugme, basilabilir, ikinciBasis };
}

beforeEach(() => {
  cagrilar.length = 0;
  seansAktif = false;
  beklet = false;
  bekleyenler.length = 0;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  jest.spyOn(console, "error").mockImplementation(() => {});
  (global as { fetch: unknown }).fetch = jest.fn((url: string) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    cagrilar.push(yol);
    if (yol === "/session/active")
      return yanit(seansAktif ? { is_active: true, mode: "Manuel", frequency: 50, intensity: 1, duration_minutes: 30, elapsed_sec: 10 } : { is_active: false });
    if (yol === "/hardware/emergency_stop") {
      const o = { confirmed: true, status: "success", stmStopped: true, stmKartYaniti: "kabul" };
      if (beklet) return new Promise((coz) => bekleyenler.push(() => coz(govde(o))));
      return yanit(o);
    }
    return yanit({ status: "success" });
  });
});
afterEach(() => jest.restoreAllMocks());

const EKRANLAR = Object.keys(EKRAN_MODULU) as Ekran[];
const STMLER: Stm[] = ["online", "offline"];
const DURUMLAR: Durum[] = ["seans_aktif", "seanssiz_bobin_calisiyor", "bosta"];
const BOBINLER: Bobin[] = ["dolu", "bos", "yok"];
const TABLO = EKRANLAR.flatMap((e) =>
  STMLER.flatMap((s) => DURUMLAR.flatMap((d) => BOBINLER.map((b) => [e, s, d, b] as [Ekran, Stm, Durum, Bobin]))));

describe("D5.E2 (İG-6.30 · A-51) — işaret takılıysa ekranın KENDİ ACİL DURDUR'u çizili ve basılabilir", () => {
  it.each(TABLO)("KRİTİK: %s × STM %s × %s × bobin listesi %s", async (ekran, stm, durum, bobin) => {
    const r = await olc(ekran, stm, durum, bobin);
    // İhlal: kayan ACİL DURDUR gizli (işaret takılı) ama ekranda basınca durduran kendi düğmesi YOK → durdurma kontrolü SIFIR (Ö.4-Y8);
    // ya da düğme yalnız BİR kez durdurur (ikinci basış istek göndermez — seans yeniden başlasa da aynı ekranda ikinci E-stop gitmez).
    // Fark çıktısı satırın TAMAMINI gösterir (ekran / STM / durum / bobin / işaret / düğme sayısı / basılabilir / ikinci basış).
    expect({ ...r, ihlal: r.takili && !(r.basilabilir && r.ikinciBasis) }).toEqual({ ...r, ihlal: false });
  });

  // GEÇİŞ (ikinci tur): ekran AÇIKKEN canlı durum değişir — düğme kaybolunca işaret de SÖKÜLMELİ (kayıt sayacı / effect temizliği).
  // Her satırı taze çizen tablo söküm yolunu ölçmez; burada aynı ağaç yeniden çizilir ve her adımda değişmez yeniden ölçülür.
  const GECIS: [Stm, Durum][] = [
    ["online", "seans_aktif"], ["offline", "bosta"], ["online", "seanssiz_bobin_calisiyor"], ["online", "bosta"],
    ["offline", "seans_aktif"], ["offline", "seanssiz_bobin_calisiyor"], ["online", "seans_aktif"], ["online", "bosta"],
  ];
  it.each(EKRANLAR)("KRİTİK geçiş: %s açıkken STM / seans durumu değişir — her adımda işaret takılıysa kendi düğme ÇİZİLİ", async (ekran) => {
    kur(...GECIS[0]);
    const u = render(<Kabuk ekran={ekran} />);
    await act(async () => {});
    const adimlar: { stm: Stm; durum: Durum; takili: boolean; dugme: number; ihlal: boolean }[] = [];
    for (const [stm, durum] of GECIS) {
      kur(stm, durum);
      u.rerender(<Kabuk ekran={ekran} />);
      await act(async () => {});
      const takili = u.getByTestId("d5e2-isaret").props.children === "takili";
      const dugme = u.queryAllByLabelText(ETIKET).length;
      adimlar.push({ stm, durum, takili, dugme, ihlal: takili && dugme === 0 });
    }
    u.unmount();
    expect(adimlar).toEqual(adimlar.map((a) => ({ ...a, ihlal: false })));
  });

  // D5.E2 TUR 3 (çürütme 2 e2d1): ACİL DURDUR montaj başına TEK atış olursa (ilk basıştan sonra aynı ekranda ikinci basış istek
  // göndermez) tablo YEŞİLDİ — her satır taze çiziliyor ve BİR kez basılıyordu; kayan düğme performEmergencyStop'u doğrudan çağırır,
  // yani tam işaretin onu GİZLEDİĞİ ekranlarda durdurma ölür. Burada aynı ağaç açık kalır, durum değişir ve işaret takılı olan HER
  // adımda ekranın kendi düğmesine basılır: her basış `/hardware/emergency_stop` göndermeli.
  it.each(EKRANLAR)("KRİTİK geçiş + basış: %s açıkken her adımda işaret takılıysa kendi düğme BASILIR ve durdurma GİDER", async (ekran) => {
    kur(...GECIS[0]);
    const u = render(<Kabuk ekran={ekran} />);
    await act(async () => {});
    const adimlar: { stm: Stm; durum: Durum; takili: boolean; dugme: number; gonderdi: boolean | null; ihlal: boolean }[] = [];
    for (const [stm, durum] of GECIS) {
      kur(stm, durum);
      u.rerender(<Kabuk ekran={ekran} />);
      await act(async () => {});
      const takili = u.getByTestId("d5e2-isaret").props.children === "takili";
      const dugme = u.queryAllByLabelText(ETIKET).length;
      const gonderdi = takili ? await bas(u, 0) : null;
      adimlar.push({ stm, durum, takili, dugme, gonderdi, ihlal: takili && gonderdi !== true });
    }
    u.unmount();
    // vakum: en az iki adımda işaret takılı (ikinci basış gerçekten ölçüldü)
    expect(adimlar.filter((a) => a.takili).length).toBeGreaterThanOrEqual(2);
    expect(adimlar).toEqual(adimlar.map((a) => ({ ...a, ihlal: false })));
  });

  // D5.E2 TUR 3b (çürütme 3 f1): yukarıdaki kollar ikinci basışı ancak ilki TAMAMLANINCA yapıyordu — uçuştaki durdurma bitmeden gelen
  // basışı yutan bir "çift istek düzeltmesi" (`useSessionControl.emergencyStop`'ta `if (acilUcustaRef.current) return;`) 64 dosya / 1290 test
  // YEŞİL geçti (ölçüldü). Ürünün kendi kuralı (DashboardScreen: "Çift-tık koruması BİLEREK YOK — panik çift-dokunuş yutulmamalı"); en kötü
  // durumda ~21 sn süren durdurma boyunca işaret kayan ACİL DURDUR'u gizlediği için o ekranda TEK durdurma yolu bu düğmedir. Burada ilk
  // basışın yanıtı BEKLETİLİR (uçuşta) ve aynı düğmeye art arda üç kez basılır: her basış YENİ `/hardware/emergency_stop` göndermeli.
  const UCUSTA = EKRANLAR.flatMap((e) => STMLER.map((s) => [e, s] as [Ekran, Stm]));
  it.each(UCUSTA)("KRİTİK panik çift dokunuş: %s × STM %s — ilk durdurmanın yanıtı beklenirken (uçuşta) HER yeni basış durdurma gönderir", async (ekran, stm) => {
    kur(stm, "seans_aktif");
    const u = render(<Kabuk ekran={ekran} />);
    await act(async () => {});
    const takili = u.getByTestId("d5e2-isaret").props.children === "takili";
    const dugme = u.queryAllByLabelText(ETIKET).length;
    beklet = true;
    cagrilar.length = 0;
    const sayac: number[] = [];
    for (let i = 0; i < 3 && dugme > 0; i += 1) {
      await act(async () => {
        fireEvent.press(u.queryAllByLabelText(ETIKET)[0]);
      });
      sayac.push(durdurmaSayisi());
    }
    const uctaBekleyen = bekleyenler.length;
    beklet = false;
    await act(async () => {
      while (bekleyenler.length) bekleyenler.shift()!();
    });
    await act(async () => {});
    u.unmount();
    // vakum: işaret takılı, ekranın kendi düğmesi var, ilk basış durdurma gönderdi ve yanıtı GERÇEKTEN bekletildi (sonraki basışlar uçuşta)
    expect({ takili, dugmeVar: dugme > 0, ilkGonderdi: (sayac[0] ?? 0) > 0, uctaBekleyen: uctaBekleyen > 0 }).toEqual({
      takili: true, dugmeVar: true, ilkGonderdi: true, uctaBekleyen: true,
    });
    const herBasisGonderdi = sayac.length === 3 && sayac.every((n, i) => n > (i === 0 ? 0 : sayac[i - 1]));
    expect({ ekran, stm, sayac, herBasisGonderdi }).toEqual({ ekran, stm, sayac, herBasisGonderdi: true });
  });

  // D5.E2 TUR 3 (çürütme 2 e2d2): KAPALI DÜNYA — işaret takan YENİ bir ekran (kendi düğmesi olmadan) tabloya girmeden hiçbir kapıya
  // görünmüyordu (SensorMonitorScreen işaret takınca 64 dosya YEŞİLDİ). Kaynak TypeScript AST ile okunur (yorum / dize kandıramaz):
  // `KendiDurdurmaKontrolu`'ndan `KendiDurdurmaIsareti` alan üretim modülü kümesi == tablonun ölçtüğü ekran modülleri; `useKendiDurdurmaKaydi`
  // yalnız AppShell'de; modül başka yoldan (ad alanı / varsayılan / yeniden dışa aktarım / require / dinamik import) alınmaz; alınan
  // işaret YALNIZ JSX etiketi olarak kullanılır (takma adla dışa aktarılıp başka ekrana taşınamaz).
  it("KRİTİK kapalı dünya: işaret takan üretim modülleri == tablonun ölçtüğü ekranlar (yeni bir ekran işaret takarsa tabloya girmeli)", () => {
    const UI = path.resolve(__dirname, "..", "..", "..");
    const tanimDosyasi = path.join(UI, "src", "components", "ui", "KendiDurdurmaKontrolu.tsx");
    const dosyalar: string[] = [];
    const gez = (dizin: string) => {
      for (const ad of fs.readdirSync(dizin)) {
        const tam = path.join(dizin, ad);
        if (fs.statSync(tam).isDirectory()) {
          if (ad !== "__tests__" && ad !== "node_modules") gez(tam);
        } else if (/\.(ts|tsx|js|jsx)$/.test(ad) && !/\.d\.ts$/.test(ad) && !/\.test\./.test(ad)) dosyalar.push(tam);
      }
    };
    gez(path.join(UI, "src"));
    if (fs.existsSync(path.join(UI, "app"))) gez(path.join(UI, "app"));
    expect(dosyalar.length).toBeGreaterThanOrEqual(100); // vakum: tarama gerçekten üretim ağacını gezdi
    const rel = (tam: string) => path.relative(path.join(UI, "src"), tam).split(path.sep).join("/");
    const modulMu = (s: ts.Expression | undefined) =>
      !!s && ts.isStringLiteralLike(s) && /(^|\/)KendiDurdurmaKontrolu(\.tsx?)?$/.test(s.text);
    const takan = new Set<string>();
    const kaydeden = new Set<string>();
    const ihlal: string[] = [];
    const bilesen = new Map<string, string>(EKRANLAR.map((e) => [EKRAN_MODULU[e], EKRAN_BILESENI[e]]));
    let etiketSayisi = 0;
    for (const tam of dosyalar) {
      if (path.resolve(tam) === path.resolve(tanimDosyasi)) continue;
      const sf = ts.createSourceFile(tam, fs.readFileSync(tam, "utf8"), ts.ScriptTarget.Latest, true,
        /\.tsx$|\.jsx$/.test(tam) ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      const yerelAdlar = new Set<string>();
      const ziyaret = (n: ts.Node) => {
        if (ts.isImportDeclaration(n) && modulMu(n.moduleSpecifier)) {
          const b = n.importClause;
          if (!b || b.name || (b.namedBindings && ts.isNamespaceImport(b.namedBindings)))
            ihlal.push(`${rel(tam)}: modül ad alanı / varsayılan / yan etki içe aktarımıyla alınıyor`);
          if (b?.namedBindings && ts.isNamedImports(b.namedBindings)) {
            for (const e of b.namedBindings.elements) {
              const asil = (e.propertyName ?? e.name).text;
              if (asil === "KendiDurdurmaIsareti") {
                takan.add(rel(tam));
                yerelAdlar.add(e.name.text);
              } else if (asil === "useKendiDurdurmaKaydi") kaydeden.add(rel(tam));
              else ihlal.push(`${rel(tam)}: bilinmeyen sembol ${asil}`);
            }
          }
        } else if (ts.isExportDeclaration(n) && modulMu(n.moduleSpecifier)) {
          ihlal.push(`${rel(tam)}: modül yeniden dışa aktarılıyor`);
        } else if (ts.isCallExpression(n) && n.arguments.some((a) => modulMu(a))) {
          ihlal.push(`${rel(tam)}: require / dinamik import`);
        } else if (ts.isExportSpecifier(n) && (n.propertyName ?? n.name).text === "KendiDurdurmaIsareti") {
          ihlal.push(`${rel(tam)}: işaret yeniden dışa aktarılıyor`);
        }
        ts.forEachChild(n, ziyaret);
      };
      ziyaret(sf);
      // Alınan işaret YALNIZ JSX etiketi olarak kullanılır (ör. `export const X = KendiDurdurmaIsareti` / prop olarak geçmek YASAK).
      const kullanim = (n: ts.Node) => {
        if (ts.isIdentifier(n) && yerelAdlar.has(n.text)) {
          const ust = n.parent;
          const etiket = (ts.isJsxSelfClosingElement(ust) || ts.isJsxOpeningElement(ust) || ts.isJsxClosingElement(ust)) && ust.tagName === n;
          const iceAktarim = ts.isImportSpecifier(ust);
          if (!etiket && !iceAktarim) ihlal.push(`${rel(tam)}: işaret JSX etiketi dışında kullanılıyor (satır ${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1})`);
          // D5.E2 TUR 3b (çürütme 3 g1): etiket YALNIZ izinli modülün ekran bileşeninin KENDİ gövdesinde — modülün başka bir üst düzey
          // bildirimi (dışa aktarılan alt bileşen `export function DurdurmaIsaretBasligi() { return <KendiDurdurmaIsareti />; }`) işareti
          // üçüncü bir ekrana taşır: takan modül kümesi değişmez, tablo o ekranı çizmez, kayan ACİL DURDUR orada gizlenir (ölçüldü: YEŞİLDİ).
          if (etiket && !ts.isJsxClosingElement(ust)) {
            etiketSayisi += 1;
            let ata: ts.Node = ust;
            while (ata.parent && ata.parent !== sf) ata = ata.parent;
            const ad = ts.isFunctionDeclaration(ata) || ts.isClassDeclaration(ata)
              ? ata.name?.text
              : ts.isVariableStatement(ata)
                ? ata.declarationList.declarations.map((v) => (ts.isIdentifier(v.name) ? v.name.text : "?")).join(",")
                : ts.SyntaxKind[ata.kind];
            const beklenen = bilesen.get(rel(tam));
            if (ad !== beklenen)
              ihlal.push(`${rel(tam)}: işaret '${ad}' içinde (satır ${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1}) — yalnız ekran bileşeni ${beklenen ?? "(izinli modül değil)"}`);
          }
        }
        ts.forEachChild(n, kullanim);
      };
      if (yerelAdlar.size) kullanim(sf);
    }
    expect(etiketSayisi).toBeGreaterThanOrEqual(2); // vakum: iki ekranın işaret etiketi bulundu ve konumu ölçüldü
    expect({ ihlal, takan: [...takan].sort(), kaydeden: [...kaydeden].sort() }).toEqual({
      ihlal: [],
      takan: Object.values(EKRAN_MODULU).sort(),
      kaydeden: ["components/ui/AppShell.tsx"],
    });
  });

  it("aparat / vakum: işaret GERÇEKTEN kayıt oluyor (Kontrol her durumda; Ana Ekran seans sırasında) — kapı boşa ölçmüyor", async () => {
    const kontrol = await olc("control", "offline", "bosta");
    const ana = await olc("dashboard", "offline", "seans_aktif");
    expect([kontrol, ana].map((r) => [r.ekran, r.takili, r.basilabilir])).toEqual([
      ["control", true, true],
      ["dashboard", true, true],
    ]);
  });
});
