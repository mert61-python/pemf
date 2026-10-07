/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E13 · İG-6.18 — KULLANICI ETKİLEŞİMİ hareketsizlik sayacını sıfırlar (web/masaüstü olay yolu).
 * ==================================================================================================
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.18, gerçek web paketi + Chrome, 46 gerçek tıklama/tuş, gerçek 12 dk koşu dahil):
 * `OperatorContext.touch()` üründe HİÇ çağrılmıyordu → çalışan hekimin kimliği PIN'den tam 10 dk sonra, etkileşimden
 * BAĞIMSIZ düşüyordu. Mevcut kapı (`OperatorContext.test.tsx` "touch() sayacı sıfırlar") `touch()`'ı TESTİN KENDİSİ
 * çağırdığı için kördü.
 *
 * GERÇEK: AuthProvider, OperatorProvider, OperatorSwitcher (PIN'le seçim), apiClient; etkileşim GERÇEK DOM olayı
 * (`pointerdown`/`keydown`/`wheel`/`touchstart`) — testte `touch()` ÇAĞRILMAZ. Sahte yalnız `fetch` ve Supabase istemcisi.
 * Kural: 10 dk eşiği ve "seans sürerken kilitlenmez" DEĞİŞMEZ; `mousemove` etkileşim SAYILMAZ (fare masada kayınca kimlik
 * sonsuza dek açık kalmasın).
 * ⚠️ D2.32 (hareketsizlik kilidi jetonu da düşürür) bundan SONRA yapılır — tersi çalışan hekimin kayıtlarını her 10 dk'da
 * bir sahipsiz yazdırırdı (ADAY-DOGRULAMA-D2 §5).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("./operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React from "react";
import { View } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { aktifOperator, pinleSec, Sahne, sahteSunucu } from "./operatorAparati";

let s: Sahne;

beforeEach(() => {
  jest.useFakeTimers();
  const { fetchSahte } = sahteSunucu([{ email: "dr.a@klinik.com", display_name: "Dr. A" }]);
  global.fetch = fetchSahte as unknown as typeof fetch;
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

async function kurVeSec() {
  await s.ciz(
    <AuthProvider>
      <OperatorProvider>
        <OperatorSwitcher />
        <View accessibilityLabel="Is alani" />
      </OperatorProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await pinleSec(s, "Dr. A");
  expect(aktifOperator()).toBe("Dr. A");
}

function olay(tur: "pointerdown" | "keydown" | "wheel" | "touchstart" | "mousemove") {
  const hedef = s.etiket("Is alani");
  const ev =
    tur === "keydown" ? new KeyboardEvent("keydown", { bubbles: true, key: "a" })
    : tur === "mousemove" ? new MouseEvent("mousemove", { bubbles: true })
    : new Event(tur, { bubbles: true });
  hedef.dispatchEvent(ev);
}

/** 30 sn arayla `olaylar` sırayla, toplam `ms` boyunca. */
async function etkiles(olaylar: Parameters<typeof olay>[0][], ms: number) {
  for (let t = 0, i = 0; t < ms; t += 30_000, i++) {
    olay(olaylar[i % olaylar.length]);
    await s.ilerlet(30_000);
  }
}

describe("D2.E13 · İG-6.18 — etkileşim hareketsizlik sayacını sıfırlar (web)", () => {
  it("KRİTİK: tıklayan/yazan hekimin kimliği 11. dakikada hâlâ AKTİF", async () => {
    await kurVeSec();
    await etkiles(["pointerdown", "keydown", "wheel", "touchstart"], 11 * 60_000);
    expect(aktifOperator()).toBe("Dr. A");
  });

  it("KRİTİK: yalnız KLAVYE kullanan hekim de kilitlenmez (keydown sayılır)", async () => {
    await kurVeSec();
    await etkiles(["keydown"], 11 * 60_000);
    expect(aktifOperator()).toBe("Dr. A");
  });

  it("KARŞIT: hiç etkileşim yoksa 10 dk eşiğinde kimlik DÜŞER (kural korunur)", async () => {
    await kurVeSec();
    await s.ilerlet(AUTO_LOCK_MS + 31_000);
    expect(aktifOperator()).toBeNull();
  });

  it("KARŞIT: yalnız fare HAREKETİ (mousemove) etkileşim SAYILMAZ — kimlik düşer", async () => {
    await kurVeSec();
    await etkiles(["mousemove"], AUTO_LOCK_MS + 31_000);
    expect(aktifOperator()).toBeNull();
  });
});
