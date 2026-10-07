/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D2.32 · B-6.8 — HAREKETSİZLİK KİLİDİ operatör JETONUNU da düşürür (elle "Kilitle" ile aynı).
 * ==========================================================================================
 * ÖLÇÜLEN KUSUR (DENETIM-06 g2a/g2b; aday İG-6.4/İG-6.18 ölçümleri): otomatik kilit yalnız `setActive(null)` yapıyordu →
 * ekranda "Operatör seçin" yazarken `apiClient` önceki hekimin jetonunu (`X-PEMF-Operator`) göndermeye devam ediyor,
 * seans ve AI kayıtları ve silme istekleri o hekime atfediliyordu (aday ölçümü: kilitten sonra 18 istekte önceki jeton).
 *
 * GERÇEK: AuthProvider, OperatorProvider, OperatorSwitcher (PIN'le seçim), `useSessionControl`, `apiClient` (başlığı ürün
 * kurar). Sahte yalnız `fetch` (her isteği jetonla kaydeder) ve Supabase istemcisi; sahte zamanlayıcı.
 * ⚠️ Önkoşul D2.E13 (etkileşim sayacı sıfırlar) — yoksa çalışan hekimin kayıtları her 10 dk'da sahipsiz yazılırdı.
 * ⚠️ Y89: seans sürerken kilit (ve jeton düşürme) ERTELENİR — "seans sürerken jeton ölmesin".
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("./operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React from "react";
import { Pressable, Text } from "react-native";
import { AuthProvider } from "@/context/AuthContext";
import { AUTO_LOCK_MS, OperatorProvider, useOperator } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { useSessionControl } from "@/hooks/useSessionControl";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type Istek } from "./operatorAparati";

let s: Sahne;
let kayit: Istek[];

function SeansProbu() {
  const { startSession } = useSessionControl();
  const op = useOperator();
  return (
    <Pressable
      accessibilityLabel="Seans baslat"
      onPress={() => void startSession({
        mode: "Manuel", frequency: 10, duty: 50, intensity: 1, durationMinutes: 1, operatorEmail: op.operatorEmail,
      })}
    >
      <Text>Başlat</Text>
    </Pressable>
  );
}

beforeEach(() => {
  jest.useFakeTimers();
  const sunucu = sahteSunucu([{ email: "dr.a@klinik.com", display_name: "Dr. A" }]);
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

async function kurVeSec(sessionActive = false) {
  await s.ciz(
    <AuthProvider>
      <OperatorProvider sessionActive={sessionActive}>
        <OperatorSwitcher />
        <SeansProbu />
      </OperatorProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await pinleSec(s, "Dr. A");
  expect(aktifOperator()).toBe("Dr. A");
}

const sonBaslatma = () => [...kayit].reverse().find((k) => k.yol === "/session/start");

describe("D2.32 · B-6.8 — hareketsizlik kilidi jetonu düşürür", () => {
  it("KONTROL (araç kanıtı): seçili hekimin başlattığı seans isteği ONUN jetonunu taşır", async () => {
    await kurVeSec();
    await s.tikla("Seans baslat");
    expect(sonBaslatma()?.operator).toBe("JETON-dr.a@klinik.com");
  });

  it("KRİTİK: hareketsizlik kilidinden SONRA giden /session/start önceki hekimin jetonunu TAŞIMAZ", async () => {
    await kurVeSec();
    await s.ilerlet(AUTO_LOCK_MS + 31_000);
    expect(aktifOperator()).toBeNull(); // ekranda kimlik düştü
    await s.tikla("Seans baslat");
    const istek = sonBaslatma();
    expect(istek).toBeDefined();
    expect(istek!.operator).toBeNull();
    expect((istek!.govde as { operator_email?: string }).operator_email).toBe("");
  });

  it("KARŞIT (Y89): seans SÜRERKEN hareketsizlik kilidi ve jeton düşürme ERTELENİR", async () => {
    await kurVeSec(true);
    await s.ilerlet(AUTO_LOCK_MS * 2);
    expect(aktifOperator()).toBe("Dr. A");
    await s.tikla("Seans baslat");
    expect(sonBaslatma()?.operator).toBe("JETON-dr.a@klinik.com");
  });
});
