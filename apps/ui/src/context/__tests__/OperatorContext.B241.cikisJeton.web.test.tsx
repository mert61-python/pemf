/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * B2-4.1 (2-B bağımsız incelemesi, D2.32'nin çıkış yolu ikizi) — ÇIKIŞ / OTURUM DÜŞMESİ operatör jetonunu da düşürür.
 * =============================================================================================================
 * ÖLÇÜLEN KUSUR: operatör jetonu `apiClient`'ta MODÜL düzeyinde (`setOperatorToken`) tutuluyor; yalnız `lock()` siliyordu.
 * Çıkışta (ya da Supabase oturumu düşünce) `PemfApp.AuthGate` uygulama ağacını — `OperatorProvider` dahil — SÖKER; yeniden
 * girişte yeni sağlayıcı "aktif operatör yok" ile başlar (çip "Operatör seç"), ama modüldeki jeton ÖNCEKİ hekimin
 * kalıyordu → kimliksiz ekranda başlatılan seans / yazılan AI kaydı o hekime atfediliyordu (backend jetonu beyana
 * üstün tutar). Ölçüldü: Dr. B seçili → çıkış → giriş → `/session/start` `X-PEMF-Operator: JETON-dr.b…`, gövde
 * `operator_email: ""`.
 *
 * GERÇEK: AuthProvider (logout + onAuthStateChange), OperatorProvider, OperatorSwitcher (PIN), `useSessionControl`,
 * `apiClient`. Sahte yalnız `fetch` (kaydedici) ve Supabase istemcisi. Kapı ağacı `PemfApp.AuthGate` ile aynı biçimde:
 * oturum yoksa uygulama ağacı sökülür.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
const mockAuth: { cb: ((olay: string, oturum: unknown) => void) | null; eposta: string } = { cb: null, eposta: "dr.a@klinik.com" };
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: {
    auth: {
      onAuthStateChange: (cb: (olay: string, oturum: unknown) => void) => {
        mockAuth.cb = cb;
        return { data: { subscription: { unsubscribe: () => undefined } } };
      },
      setSession: async () => ({ data: { session: null }, error: null }),
    },
  },
  getCurrentSession: async () => ({ access_token: "x", user: { email: mockAuth.eposta, user_metadata: {} } }),
  signOutUser: async () => { mockAuth.cb?.("SIGNED_OUT", null); },
}));

import React from "react";
import { Pressable, Text } from "react-native";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { OperatorProvider, useOperator } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { useSessionControl } from "@/hooks/useSessionControl";
import { setOperatorToken } from "@/services/apiClient";
import { aktifOperator, pinleSec, Sahne, sahteSunucu, type Istek } from "./operatorAparati";

let s: Sahne;
let kayit: Istek[];

function Probu() {
  const { startSession } = useSessionControl();
  const op = useOperator();
  const { logout } = useAuth();
  return (
    <>
      <Pressable accessibilityLabel="Seans baslat" onPress={() => void startSession({
        mode: "Manuel", frequency: 10, duty: 50, intensity: 1, durationMinutes: 1, operatorEmail: op.operatorEmail,
      })}><Text>Başlat</Text></Pressable>
      <Pressable accessibilityLabel="Cikis yap" onPress={() => void logout()}><Text>Çıkış</Text></Pressable>
    </>
  );
}

/** `PemfApp.AuthGate` ile aynı biçim: oturum yoksa uygulama ağacı (OperatorProvider dahil) SÖKÜLÜR. */
function Kapi() {
  const { session, loading } = useAuth();
  if (loading) return <Text>yükleniyor</Text>;
  if (!session) {
    return (
      <Pressable accessibilityLabel="Giris yap" onPress={() => mockAuth.cb?.("SIGNED_IN", {
        access_token: "y", user: { email: mockAuth.eposta, user_metadata: {} } })}><Text>Giriş</Text></Pressable>
    );
  }
  return (
    <OperatorProvider>
      <OperatorSwitcher />
      <Probu />
    </OperatorProvider>
  );
}

beforeEach(() => {
  jest.useFakeTimers();
  setOperatorToken(null); // önceki dosya/testten taşınan jeton bu ölçüme karışmasın
  const sunucu = sahteSunucu([{ email: "dr.a@klinik.com", display_name: "Dr. A" }, { email: "dr.b@klinik.com", display_name: "Dr. B" }]);
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  s = new Sahne();
});
afterEach(async () => {
  await s.sok();
  jest.useRealTimers();
});

const sonBaslatma = () => [...kayit].reverse().find((k) => k.yol === "/session/start");

async function kurBSecCikGir() {
  await s.ciz(<AuthProvider><Kapi /></AuthProvider>);
  await s.ilerlet(50);
  await s.bosalt(10);
  await pinleSec(s, "Dr. B");
  expect(aktifOperator()).toBe("Dr. B");
  await s.tikla("Seans baslat");
  expect(sonBaslatma()?.operator).toBe("JETON-dr.b@klinik.com"); // ARAÇ KANITI: seçili hekimin jetonu gider
  await s.tikla("Cikis yap");
  await s.bosalt(10);
  expect(s.varMi("Giris yap")).toBe(true); // ağaç SÖKÜLDÜ (AuthGate)
  await s.tikla("Giris yap");
  await s.ilerlet(50);
  await s.bosalt(10);
}

describe("B2-4.1 — çıkış / oturum düşmesi operatör jetonunu düşürür", () => {
  it("KRİTİK: çıkış + yeniden girişten sonra 'Operatör seç' iken giden /session/start ÖNCEKİ hekimin jetonunu TAŞIMAZ", async () => {
    await kurBSecCikGir();
    expect(aktifOperator()).toBeNull(); // ekranda kimlik yok
    await s.tikla("Seans baslat");
    const istek = sonBaslatma();
    expect(istek).toBeDefined();
    expect(istek!.operator).toBeNull();
    expect((istek!.govde as { operator_email?: string }).operator_email).toBe("");
  });

  it("KARŞIT: yeniden girişten sonra PIN'le seçilen hekimin jetonu gider (normal akış bozulmaz)", async () => {
    await kurBSecCikGir();
    await pinleSec(s, "Dr. A");
    expect(aktifOperator()).toBe("Dr. A");
    await s.tikla("Seans baslat");
    expect(sonBaslatma()?.operator).toBe("JETON-dr.a@klinik.com");
  });
});
