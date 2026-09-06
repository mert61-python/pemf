// Author: mertaygn, cglrgrkn
/**
 * installedProfiles — baslatici'nin `?profiles=home,research` parametresi → KURULU modlar
 * (profil kaldirma denetimi, 2026-09-06).
 *
 * Baslatici (launcher) uygulamayi HER acilista `http://127.0.0.1:<port>/?profiles=<kurulu>` ile
 * acar (bkz. launcher/app/src/main.rs `uygulama_url`). Bir profil kaldirildiginda (remove_profiles)
 * sonraki acilista parametre KISALIR; app'in onceki acilistan localStorage'da tuttugu ESKI liste
 * ("home,vet,research") parametreyi ASLA ezmemeli — yoksa kaldirilan "Veteriner" karti geri gelir
 * ve modelleri silinmis bir profile girilebilir.
 *
 * Kilitlenen sozlesme:
 *  1. ?profiles=home,research → {pet_owner, researcher}; veterinarian YOK.
 *  2. Parametre VARSA localStorage'daki bayat deger HER ZAMAN ezilir (ve yeni deger yazilir).
 *  3. Parametre YOK + depo YOK → null (mobil / bilgi yok → TUM modlar; mevcut davranis korunur).
 *  4. Parametre YOK + depo VAR → depo (SPA gezinme/yenileme parametreyi dusurur; kalici kisit).
 *  5. Native (ios/android) → parametre olsa bile null.
 *  6. Onbellek-kirici ek parametre (`?v=123&profiles=...`) ve bosluk/buyuk-harf toleransi.
 *  7. Bilinmeyen profil adlari elenir; hicbiri taninmazsa null (bozuk deger kilitlemez).
 *
 * MUTASYON: installedModes() query parametresini okumayi birakip yalniz localStorage'a bakarsa
 * 1 ve 2 KIRMIZI; depo yedegi kaldirilirsa 4 KIRMIZI; Platform kapisi kaldirilirsa 5 KIRMIZI.
 */
import { Platform } from "react-native";
import { installedModes } from "@/services/installedProfiles";

const KEY = "pemf_installed_profiles";

// window.location.search + window.localStorage'i kontrol edilebilir bir simle sabitle
// (jest-expo native ortaminda `window.location` tanimsizdir; supabaseAuthDesktopStorage ile ayni desen).
const depo = new Map<string, string>();
function pencereyiKur(search: string | null) {
  const ls = {
    getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
    setItem: (k: string, v: string) => { depo.set(k, v); },
    removeItem: (k: string) => { depo.delete(k); },
    clear: () => depo.clear(),
  };
  const g = globalThis as Record<string, unknown>;
  if (!g.window) g.window = {};
  const w = g.window as Record<string, unknown>;
  Object.defineProperty(w, "location", {
    value: search == null ? undefined : { search, hostname: "127.0.0.1" },
    configurable: true,
    writable: true,
  });
  Object.defineProperty(w, "localStorage", { value: ls, configurable: true, writable: true });
}
const setOS = (os: string) => { (Platform as unknown as { OS: string }).OS = os; };
const dizi = (s: Set<string> | null) => (s ? [...s].sort() : null);

beforeEach(() => {
  depo.clear();
  setOS("web");
  pencereyiKur("");
});
afterAll(() => setOS("ios"));

describe("installedModes — baslatici parametresi", () => {
  it("1. ?profiles=home,research → {pet_owner, researcher}; veterinarian GIZLI", () => {
    pencereyiKur("?profiles=home,research");
    const m = installedModes();
    expect(m).not.toBeNull();
    expect(dizi(m)).toEqual(["pet_owner", "researcher"]);
    expect(m!.has("veterinarian")).toBe(false);
    // Ilk okumada depoya yazilir (SPA gezinmede korunsun diye).
    expect(depo.get(KEY)).toBe("home,research");
  });

  it("2. KRITIK: parametre VARSA bayat localStorage ('home,vet,research') EZILIR — 'vet' geri gelmez", () => {
    depo.set(KEY, "home,vet,research"); // onceki acilistan (vet henuz kaldirilmamisken) kalan deger
    pencereyiKur("?profiles=home,research");
    const m = installedModes();
    expect(dizi(m)).toEqual(["pet_owner", "researcher"]);
    expect(m!.has("veterinarian")).toBe(false);
    expect(depo.get(KEY)).toBe("home,research"); // depo da guncellendi
    // Ikinci cagri (ayni sayfa) — parametre hala var, sonuc ayni.
    expect(dizi(installedModes())).toEqual(["pet_owner", "researcher"]);
  });

  it("3. parametre YOK + depo YOK → null (tum modlar; mobil davranisi korunur)", () => {
    pencereyiKur("");
    expect(installedModes()).toBeNull();
    pencereyiKur("?v=123"); // yalniz onbellek-kirici parametre
    expect(installedModes()).toBeNull();
    expect(depo.has(KEY)).toBe(false); // hicbir sey yazilmaz
  });

  it("4. parametre YOK + depo VAR → depo kullanilir (SPA gezinme parametreyi dusurunce kisit KALIR)", () => {
    pencereyiKur("?profiles=home");
    expect(dizi(installedModes())).toEqual(["pet_owner"]);
    pencereyiKur(""); // expo-router pushState → ?profiles yok
    expect(dizi(installedModes())).toEqual(["pet_owner"]);
  });

  it("5. native (ios/android): parametre olsa bile null — mobilde kisit yok", () => {
    for (const os of ["ios", "android"]) {
      setOS(os);
      pencereyiKur("?profiles=home");
      expect(installedModes()).toBeNull();
    }
  });

  it("6. onbellek-kirici ek parametre + bosluk/buyuk-harf toleransi", () => {
    pencereyiKur("?v=1725580800&profiles=Home,%20RESEARCH");
    expect(dizi(installedModes())).toEqual(["pet_owner", "researcher"]);
    pencereyiKur("?profiles=vet&v=9");
    expect(dizi(installedModes())).toEqual(["veterinarian"]);
  });

  it("7. bilinmeyen adlar elenir; hicbiri taninmazsa null (bozuk deger uygulamayi kilitlemez)", () => {
    pencereyiKur("?profiles=home,bilinmeyen");
    expect(dizi(installedModes())).toEqual(["pet_owner"]);
    pencereyiKur("?profiles=xyz");
    expect(installedModes()).toBeNull();
  });

  it("8. window.location yoksa (SSR/olcum) → null, atmaz", () => {
    pencereyiKur(null);
    expect(installedModes()).toBeNull();
  });
});
