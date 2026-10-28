/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D6.27 (B-6.33 · İG-6.106) — Şifre sıfırlama sayfası (depo kopyası `apps/ui/auth-pages/reset.html`) ve uygulamanın Supabase hata çevirisi,
 * UYGULADIKLARI asgari şifre uzunluğunu söyler.
 * =================================================================================================================================
 * ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): sayfa `pw.length < 8 || …` (büyük + küçük + rakam) uygular, ama yer tutucu "Yeni şifre (en az 6 karakter)"
 * ve Supabase'in kısa-şifre iletisinin çevirisi "Şifre en az 6 karakter olmalı." diyordu; uygulamanın kopyası (`services/supabaseAuth.ts`
 * `mapError` → `giris.hata.sifreEnAz6`) aynı "6"yı söylüyordu, oysa kayıt ekranı `authApi.passwordChecks` ile ≥ 8 ister.
 * ÖLÇÜT DAVRANIŞTAN: asgari uzunluk sayfanın KENDİ doğrulayıcısına (gerçek tıklama) ve uygulamanın `passwordChecks`'ine sorularak bulunur;
 * metindeki sayı yorum soyulmuş DOM'dan / dönen iletiden okunur (sayfadaki yorumlar "en az 6"yı tarihçe olarak anar — sayılmaz).
 * GERÇEK: reset.html (DOM + satır içi betik), i18n_katalog.js (ÜRETİLMİŞ), supabaseAuth.signUpUser, authApi.passwordChecks, katalog.
 * Sahte (en alt kat): supabase-js istemcisi (sayfada `window.supabase`, uygulamada `@supabase/supabase-js`), cihaz depoları. Canlı Supabase YOK.
 */
jest.mock("@supabase/supabase-js", () => {
  const auth = {
    signUp: jest.fn(async () => ({ data: { session: null }, error: { message: "Password should be at least 6 characters." } })),
  };
  return { createClient: () => ({ auth }), __auth: auth };
});
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(async () => null), setItem: jest.fn(async () => undefined), removeItem: jest.fn(async () => undefined),
}));
jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(async () => undefined), deleteItemAsync: jest.fn(async () => undefined),
}));

import fs from "fs";
import path from "path";
import { passwordChecks } from "@/services/authApi";
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";

const SAYFA = path.resolve(__dirname, "../../../auth-pages/reset.html");
const KATALOG_JS = path.resolve(__dirname, "../../../auth-pages/i18n_katalog.js");
/** Supabase'in (varsayılan politika) kısa-şifre iletisi — `mapErr` / `mapError` bu iletiyi çevirir. */
const SUPABASE_KISA = "Password should be at least 6 characters.";

const sayilar = (s: string | null | undefined) => (String(s ?? "").match(/\d+/g) ?? []).map(Number);
const sifre = (n: number) => "Aa1" + "b".repeat(Math.max(0, n - 3));
const bekle = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

/** reset.html'i jsdom'a kurar ve betiklerini SAYFANIN SIRASIYLA çalıştırır: i18n_katalog.js → (sahte supabase-js) → satır içi betik. */
function sayfaKur(dil: "tr" | "en", updateUserHatasi: string | null) {
  const ham = fs.readFileSync(SAYFA, "utf8");
  const doc = new DOMParser().parseFromString(ham, "text/html");
  const satirIci = Array.from(doc.querySelectorAll("script")).filter((s) => !s.getAttribute("src")).map((s) => s.textContent || "");
  expect(satirIci).toHaveLength(1); // aparat: sayfanın tek satır içi betiği
  document.documentElement.innerHTML = doc.documentElement.innerHTML; // innerHTML betik ÇALIŞTIRMAZ — sıra aşağıda elle
  window.history.pushState({}, "", `/auth/reset.html?dil=${dil}`);
  // Bu ortamda (expo polyfill) `URLSearchParams` `?dil=`'i okuyamayabilir (sayfa o zaman tarayıcı diline düşer — ilk koşuda TR kolu
  // sessizce EN çiziyordu, ölçüldü) → tarayıcı dili de AYNI dile ayarlanır ve sayfanın SEÇTİĞİ dil aşağıda doğrulanır.
  Object.defineProperty(window.navigator, "language", { value: dil === "tr" ? "tr-TR" : "en-US", configurable: true });
  // Dil seçimi bayraktan bağımsız ölçülsün diye üretilmiş dosyanın bayrağı AÇIK verilir.
  const katalog = fs.readFileSync(KATALOG_JS, "utf8").replace(/var EN_ACIK = (true|false);/, "var EN_ACIK = true;");
  new Function(katalog)();
  expect((window as unknown as { PEMF_DIL?: string }).PEMF_DIL).toBe(dil); // aparat: sayfa istenen dilde
  const w = window as unknown as Record<string, unknown>;
  w.supabase = {
    createClient: () => ({
      auth: {
        onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
        updateUser: jest.fn(async () => ({ error: updateUserHatasi ? { message: updateUserHatasi } : null })),
      },
    }),
  };
  new Function(satirIci[0])();
}

async function gonder(pw: string): Promise<string> {
  (document.getElementById("pw") as HTMLInputElement).value = pw;
  (document.getElementById("pw2") as HTMLInputElement).value = pw;
  await (document.getElementById("go") as HTMLButtonElement & { onclick: () => Promise<void> }).onclick();
  await bekle();
  return document.getElementById("msg")?.textContent ?? "";
}

/** Sayfanın KENDİ doğrulayıcısının kabul ettiği en kısa şifre uzunluğu (büyük + küçük + rakamlı adaylarla, gerçek tıklama). */
async function sayfaKurali(): Promise<number> {
  sayfaKur("tr", null);
  const kurallarMetni = (window as unknown as { tf: (k: string) => string }).tf("authSayfa.reset.hata.kurallar");
  for (let n = 3; n <= 32; n++) {
    const m = await gonder(sifre(n));
    if (m !== kurallarMetni) return n;
  }
  throw new Error("sayfa hiçbir uzunluğu kabul etmedi");
}

/** Uygulamanın kayıt kuralının asgari uzunluğu (`passwordChecks().length`). */
function uygulamaKurali(): number {
  for (let n = 1; n <= 32; n++) if (passwordChecks("x".repeat(n)).length) return n;
  throw new Error("uzunluk kuralı yok");
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).supabase;
});

it("ARA: sayfa ve uygulama AYNI asgari uzunluğu uygular (8)", async () => {
  expect(await sayfaKurali()).toBe(8);
  expect(uygulamaKurali()).toBe(8);
});

it.each(["tr", "en"] as const)("KRİTİK (%s): reset.html yer tutucusu sayfanın uyguladığı asgari uzunluğu söyler", async (dil) => {
  const kural = await sayfaKurali();
  sayfaKur(dil, null);
  const yer = document.getElementById("pw")?.getAttribute("placeholder");
  expect(yer).toBeTruthy();
  expect(sayilar(yer)).toEqual([kural]);
});

it.each(["tr", "en"] as const)("KRİTİK (%s): Supabase kısa-şifre iletisinin sayfa çevirisi asgari uzunluğu söyler", async (dil) => {
  const kural = await sayfaKurali();
  sayfaKur(dil, SUPABASE_KISA);
  const m = await gonder(sifre(kural));
  expect(m).not.toBe("");
  expect(sayilar(m)).toEqual([kural]);
});

it("KRİTİK (uygulama kopyası, İG-6.106): kayıtta Supabase kısa-şifre iletisi uygulamanın kuralını söyler", async () => {
  const kural = uygulamaKurali();
  // Bu ortamda (jsdom + expo/RN polyfill) küresel `URL` kurucu değil (supabaseAuth modül düzeyinde `new URL(...)` kurar) → modül
  // düğümün `URL`'si verilerek GEÇ yüklenir, test sonunda eski değer geri konur.
  const g = globalThis as unknown as { URL?: unknown };
  const eskiUrl = g.URL;
  if (typeof g.URL !== "function") g.URL = require("url").URL;
  let r: { ok: boolean; error?: string };
  try {
    const { signUpUser } = require("@/services/supabaseAuth") as typeof import("@/services/supabaseAuth");
    r = await signUpUser("op@klinik.com", sifre(kural));
  } finally {
    g.URL = eskiUrl;
  }
  expect(r.ok).toBe(false);
  expect(sayilar(r.error)).toEqual([kural]);
});

it("KATALOG: TR birebir, EN aynı sayıyı söyler", () => {
  expect(TR["authSayfa.reset.sifreYer"]).toBe("Yeni şifre (en az 8 karakter)");
  expect(TR["authSayfa.reset.hata.en6"]).toBe("Şifre en az 8 karakter olmalı.");
  expect(TR["giris.hata.sifreEnAz6"]).toBe("Şifre en az 8 karakter olmalı.");
  for (const k of ["authSayfa.reset.sifreYer", "authSayfa.reset.hata.en6", "giris.hata.sifreEnAz6"]) {
    expect(sayilar(EN[k])).toEqual([8]);
  }
});
