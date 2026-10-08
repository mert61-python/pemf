/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * B2-3.7 (2-B bağımsız incelemesi, A3) — KÖR KAPI: "seans bitince sayaç YENİDEN işler" (Y89 sınırı) kapısız.
 * ======================================================================================================
 * `OperatorContext` hareketsizlik aralığı seans SÜRERKEN sayacı her tikte sıfırlar (`sonEtkilesim = Date.now()`); böylece
 * 25 dk'lık etkileşimsiz bir seans bitince kimlik ANINDA değil, 10 dk sonra düşer (ölçüldü: 600 sn). Bu sıfırlama silinince
 * (mutant `k4_o18`) seans bitiminden 30 sn sonra kimlik ve JETON düşer — hekim STOP'tan hemen sonra gözlem notunu/değerlendirmeyi
 * sahipsiz yazar — ama 2-B'nin D2.32/E13/E14 kapıları 55/55 YEŞİL kalıyor (yalnız "seans sürerken" ölçülüyor).
 * GERÇEK: AuthProvider, OperatorProvider (sessionActive dışarıdan), OperatorSwitcher (PIN), apiClient (kilit isteği).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("./operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React, { act, useState } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type Istek } from "./operatorAparati";

let s: Sahne;
let kayit: Istek[];
let seansAyarla: (v: boolean) => void = () => undefined;
function Kabuk({ children }: { children: React.ReactNode }) {
  const [seans, setSeans] = useState(false);
  seansAyarla = setSeans;
  return <OperatorProvider sessionActive={seans}>{children}</OperatorProvider>;
}
beforeEach(() => {
  jest.useFakeTimers();
  const sunucu = sahteSunucu([{ email: "dr.a@klinik.com", display_name: "Dr. A" }]);
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  s = new Sahne();
});
afterEach(async () => { await s.sok(); jest.useRealTimers(); });

async function seansSonrasi(seansDk: number) {
  await s.ciz(<AuthProvider><Kabuk><OperatorSwitcher /></Kabuk></AuthProvider>);
  await s.ilerlet(50);
  await pinleSec(s, "Dr. A");
  expect(aktifOperator()).toBe("Dr. A");
  await act(async () => seansAyarla(true));
  for (let t = 0; t < seansDk * 60_000; t += 30_000) await s.ilerlet(30_000);
  expect(aktifOperator()).toBe("Dr. A"); // Y89: seans sürerken kilit yok (ARA DOĞRULAMA)
  await act(async () => seansAyarla(false));
  await s.bosalt(5);
}
const kilitIstekleri = () => kayit.filter((k) => k.yol === "/operators/lock");

describe("B2-3.7 — seans BİTİNCE hareketsizlik sayacı baştan başlar (biriken süre anında kilitlemez)", () => {
  it("KRİTİK: 25 dk etkileşimsiz seans biter → 5 dk sonra kimlik ve jeton HÂLÂ duruyor (sunucu kilidi yok)", async () => {
    await seansSonrasi(25);
    for (let t = 0; t < 5 * 60_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBe("Dr. A");
    expect(kilitIstekleri()).toEqual([]);
  });

  it("KARŞIT: seans bittikten sonra etkileşim olmazsa 10 dk eşiğinde kimlik DÜŞER (kural korunur)", async () => {
    await seansSonrasi(25);
    for (let t = 0; t < AUTO_LOCK_MS + 31_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBeNull();
    expect(kilitIstekleri().length).toBe(1);
  });
});
