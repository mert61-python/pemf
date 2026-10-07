/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.E14 · İG-6.63 — istemcinin `lock()`'u jetonu düşürmeden ÖNCE sunucu kilit ucunu (`POST /operators/lock`) çağırır.
 * ===================================================================================================================
 * ÖLÇÜLEN KUSUR (aday İG-6.63, jest kaydı): "Kilitle" fazında sunucuya giden istek 0 — jeton yalnız istemciden siliniyor,
 * aynı jetonu tutan diğer kopyalar kilitlenen hekim adına yazmayı sürdürüyordu. Backend yarısı:
 * tests/test_operator_kilit_ucu_E14.py.
 *
 * GERÇEK: AuthProvider, OperatorProvider, OperatorSwitcher ("Oturumu kilitle"), apiClient (başlığı ürün kurar).
 * Sahte yalnız `fetch` ve Supabase istemcisi. Kural: sunucu isteğinin başarısızlığı kilidi ENGELLEMEZ; seans sürerken
 * hareketsizlik kilidi (ve dolayısıyla sunucu kilidi) ertelenir (Y89).
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("./operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React from "react";
import { Pressable, Text } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { AUTO_LOCK_MS, OperatorProvider } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { apiPost } from "@/services/apiClient";
import { aktifOperator, cipEtiketi, pinleSec, Sahne, sahteSunucu, type Istek } from "./operatorAparati";

let s: Sahne;
let kayit: Istek[];

function kur(sunucuKilitDurumu = 200) {
  const sunucu = sahteSunucu(
    [{ email: "dr.a@klinik.com", display_name: "Dr. A" }],
    (yol) => (yol === "/operators/lock" && sunucuKilitDurumu !== 200 ? [sunucuKilitDurumu, { detail: "taklit" }] : undefined),
  );
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
}

function IstekProbu() {
  return (
    <Pressable accessibilityLabel="Kayit yaz" onPress={() => void apiPost("/ai/log", { summary: "x" }, null, { silent: true })}>
      <Text>Yaz</Text>
    </Pressable>
  );
}

beforeEach(() => {
  jest.useFakeTimers();
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

async function cizVeSec(sessionActive = false) {
  await s.ciz(
    <AuthProvider>
      <OperatorProvider sessionActive={sessionActive}>
        <OperatorSwitcher />
        <IstekProbu />
      </OperatorProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await pinleSec(s, "Dr. A");
  expect(aktifOperator()).toBe("Dr. A");
}

const kilitIstekleri = () => kayit.filter((k) => k.yol === "/operators/lock" && k.yontem === "POST");
const sonYazma = () => [...kayit].reverse().find((k) => k.yol === "/ai/log");

describe("D2.E14 · İG-6.63 — kilit jetonu sunucuda da iptal eder", () => {
  it("KRİTİK: elle 'Kilitle' sunucu kilit ucunu KİLİTLENEN hekimin jetonuyla çağırır", async () => {
    kur();
    await cizVeSec();
    await s.tikla(cipEtiketi());
    await s.tikla("Oturumu kilitle");
    expect(aktifOperator()).toBeNull();
    expect(kilitIstekleri().map((k) => k.operator)).toEqual(["JETON-dr.a@klinik.com"]);
    await s.tikla("Kayit yaz");
    expect(sonYazma()?.operator).toBeNull();
  });

  it("KRİTİK: hareketsizlik kilidi de sunucu kilit ucunu jetonla çağırır", async () => {
    kur();
    await cizVeSec();
    // 30 sn'lik GERÇEK aralık adımları: tek dev `advanceTimersByTime` iki tiki arada çizim olmadan çalıştırır (gerçekte
    // tikler arasında React yeniden çizer ve aralığı temizler) — ölçüldü: tek adımda ikinci, jetonsuz bir istek görünür.
    for (let t = 0; t < AUTO_LOCK_MS + 31_000; t += 30_000) await s.ilerlet(30_000);
    expect(aktifOperator()).toBeNull();
    expect(kilitIstekleri().map((k) => k.operator)).toEqual(["JETON-dr.a@klinik.com"]);
  });

  it("KARŞIT: sunucu kilit isteği BAŞARISIZ olsa da istemci kilitlenir ve jeton düşer", async () => {
    kur(500);
    await cizVeSec();
    await s.tikla(cipEtiketi());
    await s.tikla("Oturumu kilitle");
    expect(kilitIstekleri().length).toBe(1);
    expect(aktifOperator()).toBeNull();
    await s.tikla("Kayit yaz");
    expect(sonYazma()?.operator).toBeNull();
  });

  it("KARŞIT (Y89): seans sürerken hareketsizlikte sunucu kilidi YOK", async () => {
    kur();
    await cizVeSec(true);
    await s.ilerlet(AUTO_LOCK_MS * 2);
    expect(kilitIstekleri()).toEqual([]);
    expect(aktifOperator()).toBe("Dr. A");
  });
});
