// Author: mertaygn, cglrgrkn
/**
 * AI HUB · HASTA BAĞI — ortak jest aparatı (2-C: D2.69 · D2.E08 · D2.E09 · O-A3.6 · D2.E11 · O-A3.3).
 *
 * GERÇEK: `AuthProvider`, `UserModeProvider`, `OperatorProvider`, `AppNavProvider`, `PatientGate`, `AiHubScreen` (+ modülleri),
 * `apiClient`. SAHTE yalnız EN ALT katta: `fetch` (ağ sınırı — her isteği yöntem + yol + gövde ile KAYDEDER; çok parçalı
 * gövde `FormData` olarak saklanır, giden DOSYA karşılaştırılabilir), Supabase istemcisi (çağıran test dosyası
 * `jest.mock("@/services/supabaseAuth", …)` ile verir), dosya seçici (web `<input type=file>`'ın `click`'i — seçilecek dosya
 * `dosyaSiradaki` ile verilir) ve `URL.createObjectURL` (jsdom'da yok).
 * Çağıran dosya ayrıca `useEntitlement`'ı (abonelik gösterimi — bu kapıların konusu değil) ve cihaz modüllerini
 * (expo-camera / expo-audio / expo-image-picker / expo-document-picker / expo-file-system) sahteler; jest.mock çağrıları
 * dosyada olmalı (hoist).
 */
import React, { act, useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { Sahne, sahteSunucu, type Istek, type SahteOperator } from "../../context/__tests__/operatorAparati";

export interface HamIstek {
  yontem: string;
  yol: string;
  govde: unknown;
}

export interface SahteHasta {
  id: string;
  name: string;
  operator_email: string;
  species?: string;
}

/** Bekletilebilir yanıt: `serbest()` çağrılana dek istek askıda kalır (uçuştaki analiz). */
export class Askida {
  private coz: ((v: [number, unknown]) => void) | null = null;
  sozu: Promise<[number, unknown]>;
  constructor() {
    this.sozu = new Promise((r) => { this.coz = r; });
  }
  serbest(durum: number, veri: unknown) {
    this.coz?.([durum, veri]);
  }
}

type Ozel = (yol: string, govde: unknown, yontem: string) => [number, unknown] | Askida | undefined;

export const aparat = {
  ham: [] as HamIstek[],
  kayit: [] as Istek[],
  dosyaSiradaki: null as File | null,
};

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let tiklamaYamasi: jest.SpyInstance | null = null;
let blobSayac = 0;

/** Dosya seçiciyi ve `URL.createObjectURL`'ı kurar (her testte `beforeEach`). */
export function cihazSahteleriniKur() {
  aparat.dosyaSiradaki = null;
  tiklamaYamasi = jest.spyOn(HTMLInputElement.prototype, "click").mockImplementation(function (this: HTMLInputElement) {
    if (this.type !== "file" || !aparat.dosyaSiradaki) return;
    const f = aparat.dosyaSiradaki;
    aparat.dosyaSiradaki = null;
    Object.defineProperty(this, "files", { value: [f], configurable: true });
    (this.onchange as ((e: unknown) => void) | null)?.({ target: this });
  });
  // Bu ortamda (expo/RN polyfill) küresel `URL` tanımsız olabilir (ölçüldü: "Cannot set properties of undefined") →
  // yalnız iki statik yöntemi taşıyan geçici nesne; testten sonra eski değer geri konur.
  const g = globalThis as unknown as { URL?: Record<string, unknown> };
  eskiUrl = { var: "URL" in globalThis, deger: g.URL };
  const U = g.URL ?? {};
  U.createObjectURL = () => `blob:sahte-${++blobSayac}`;
  U.revokeObjectURL = () => undefined;
  g.URL = U;
}

let eskiUrl: { var: boolean; deger: unknown } | null = null;

export function cihazSahteleriniSok() {
  tiklamaYamasi?.mockRestore();
  tiklamaYamasi = null;
  if (eskiUrl && !eskiUrl.deger) {
    if (eskiUrl.var) (globalThis as unknown as { URL?: unknown }).URL = eskiUrl.deger;
    else delete (globalThis as unknown as { URL?: unknown }).URL;
  }
  eskiUrl = null;
}

/** Gerçek sağlayıcılarla AiHubScreen'i çizer. `hastalar` `/patients` yanıtıdır; `ozel` önce sorulur. */
export async function kurAiHub(
  s: Sahne,
  { mod, hastalar, operatorler = [], ozel, operatorCipi = false }: {
    mod: UserMode;
    hastalar: SahteHasta[];
    operatorler?: SahteOperator[];
    ozel?: Ozel;
    operatorCipi?: boolean;
  },
) {
  aparat.ham = [];
  const askidakiler: { yontem: string; yol: string; a: Askida }[] = [];
  const sunucu = sahteSunucu(operatorler, (yol, govde, yontem) => {
    const o = ozel?.(yol, govde, yontem);
    if (o instanceof Askida) {
      askidakiler.push({ yontem, yol, a: o });
      return undefined;
    }
    if (o) return o;
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: hastalar }];
    if (yontem === "GET" && yol.startsWith("/ai/log")) return [200, { status: "success", data: [] }];
    if (yontem === "POST" && yol === "/ai/log") return [200, { status: "success", id: aparat.ham.length }];
    return undefined;
  });
  aparat.kayit = sunucu.kayit;
  const fetchSahte = jest.fn(async (url: unknown, init: { method?: string; body?: unknown; headers?: Record<string, string>;
    signal?: AbortSignal } = {}) => {
    const yol = String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
    const yontem = init.method || "GET";
    aparat.ham.push({ yontem, yol, govde: init.body });
    // Askıdaki yanıt: kaydediciyi geçir (istek kayda girsin), sonra serbest bırakılana dek beklet.
    const yanit = await sunucu.fetchSahte(url, { ...init, body: typeof init.body === "string" ? init.body : undefined });
    const bekleyen = askidakiler.find((x) => x.yol === yol && x.yontem === yontem);
    if (bekleyen) {
      askidakiler.splice(askidakiler.indexOf(bekleyen), 1);
      // İstemcinin İPTALİ (AbortController) gerçek fetch gibi uygulanır: askıdaki istek iptal edilirse AbortError ile düşer.
      const sinyal = init.signal;
      const iptal = new Promise<never>((_c, red) => {
        const at = () => red(Object.assign(new Error("The operation was aborted."), { name: "AbortError" }));
        if (sinyal?.aborted) at();
        sinyal?.addEventListener?.("abort", at);
      });
      const [durum, veri] = await Promise.race([bekleyen.a.sozu, iptal]);
      return { ok: durum < 400, status: durum, text: async () => JSON.stringify(veri), json: async () => veri,
        headers: { get: () => "application/json" } };
    }
    return yanit;
  });
  global.fetch = fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod={mod}>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              {operatorCipi ? <OperatorSwitcher /> : null}
              <AiHubScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
}

/** PatientGate'in seçili hasta şeridi (`<Hasta|Evcil Hayvanım|Örnek / Denek>: <ad>. Değiştir.`). ⚠️ Operatör çipi de ". Değiştir."
 *  ile biter ("Aktif operatör: Dr. A. Değiştir.") — genel sonek seçicisi çipi açıyordu (ölçüldü). */
export function hastaSeridi(): HTMLElement | null {
  return (Array.from(document.querySelectorAll('[role="button"]')).find((e) =>
    /^(Hasta|Evcil Hayvanım|Örnek \/ Denek): .*\. Değiştir\.$/.test(e.getAttribute("aria-label") || ""),
  ) as HTMLElement | undefined) ?? null;
}

/** PatientGate'ten hasta seç (kapı ya da üst şerit — GERÇEK akış); liste gelene dek bekler. */
export async function hastaSec(s: Sahne, ad: string, tur?: string) {
  const serit = hastaSeridi();
  if (serit) {
    await act(async () => { serit.click(); });
    await s.bosalt();
  } else {
    const kapi = Array.from(document.querySelectorAll('[role="button"]')).find((e) =>
      /^(Hasta seçin|Hayvanınızı seçin|Örnek seçin)$/.test(e.getAttribute("aria-label") || ""),
    ) as HTMLElement | undefined;
    if (!kapi) throw new Error(`hasta kapisi yok. Govde: ${document.body.textContent?.slice(0, 300)}`);
    await act(async () => { kapi.click(); });
    await s.bosalt();
  }
  for (let i = 0; i < 20 && !s.varMi(`Seç: ${ad}`); i++) await s.bosalt();
  if (!tur) {
    await s.tikla(`Seç: ${ad}`);
    return;
  }
  // Aynı adlı birden çok hasta: satırın görünen türüne göre seç (seçici satırı "ad + tür" gösterir).
  const satir = Array.from(document.querySelectorAll(`[aria-label="Seç: ${ad}"]`)).find((e) =>
    (e.textContent || "").includes(tur),
  ) as HTMLElement | undefined;
  if (!satir) throw new Error(`"${ad}" (${tur}) secici satiri yok. Govde: ${document.body.textContent?.slice(0, 300)}`);
  await act(async () => { satir.click(); });
  await s.bosalt();
}

/** Ürünün `Button`'ı AYNI etiketin 400 ms içindeki ikinci basışını yutar (çift-tık koruması, `Date.now`). Aynı düğmeye
 *  yeniden basmadan önce GERÇEK zamanla beklenir — beklenmezse basış sessizce kaybolur ve kapı yanlış nedenle yeşil kalır
 *  (2-C ölçümü: E08 ses kolunda HEAD'de istek 0 görünüyordu). */
export async function ciftTikKorumasiniBekle(s: Sahne) {
  await act(async () => { await new Promise((r) => setTimeout(r, 450)); });
  await s.bosalt();
}

/** `/ai/log` POST gövdeleri (gerçek apiPost'un gönderdiği). */
export function aiLogGovdeleri(): Record<string, unknown>[] {
  return aparat.kayit
    .filter((i) => i.yontem === "POST" && i.yol === "/ai/log")
    .map((i) => i.govde as Record<string, unknown>);
}

/** Verilen uca giden çok parçalı gövdelerdeki dosya alanları. */
export function gidenDosyalar(yol: string, alan = "file"): unknown[] {
  return aparat.ham
    .filter((i) => i.yontem === "POST" && i.yol === yol && i.govde instanceof FormData)
    .map((i) => (i.govde as FormData).get(alan));
}

/** Giden dosyaların İÇERİĞİ (metin). jsdom'da `FormData.get` YENİ bir `File` döndürür — kimlik karşılaştırması anlamsız. */
export async function gidenDosyaIcerikleri(yol: string, alan = "file"): Promise<string[]> {
  const oku = (b: unknown) =>
    new Promise<string>((coz) => {
      if (!(b instanceof Blob)) return coz(String(b));
      const r = new FileReader();
      r.onload = () => coz(String(r.result));
      r.readAsText(b);
    });
  return Promise.all(gidenDosyalar(yol, alan).map(oku));
}

/** Metni tam `metin` olan en derin elemanın (etiketsiz düğme) varlığı. */
export function metinVar(metin: string): boolean {
  return Array.from(document.querySelectorAll("*")).some(
    (e) => (e.textContent || "").trim() === metin && !Array.from(e.children).some((c) => (c.textContent || "").trim() === metin),
  );
}

export { Sahne };
