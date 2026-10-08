/**
 * @jest-environment jsdom
 */
/**
 * C2-2.2 (2-C inceleme A2 · Y116 ce5437d · Ö.4-Y8) — not penceresi ACİL DURDUR için GİZLENİNCE pencerenin İÇİNDEKİ operatör
 * seçicinin PIN penceresi de ANINDA kalkar.
 * ===========================================================================================================================
 * ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_y116_ui.txt` [iv]): ControlScreen not penceresini bobin çalışınca gizler
 * (`visible={obsSession !== null && !hardwareRunningOutOfSession}` — ACİL DURDUR'a erişim). Y116 pencerenin içine `OperatorSwitcher`
 * koydu; onun PIN penceresi AYRI bir portaldır (body düzeyi, z-index 9999). `visible=false` sonrası RN-web dış pencereyi kayarak
 * kapatır (250 ms, `pointer-events: none`) ve çocuklarını ancak `animationend`de söker → PIN penceresi o süre boyunca TAM EKRAN
 * örtü olarak kalır, ControlScreen'in sayfa içi ACİL DURDUR'unu örter (ControlScreen'de kayan GlobalEmergencyStop gizli —
 * `kendiDurdurmasiVar`). Android'de RN Modal `visible=false`ta çocukları hemen söker (Modal.js `_shouldShowModal`).
 * Düzeltme: seçici yalnız pencere GÖRÜNÜRKEN çizilir; istem ve not KORUNUR (pencere yeniden açılınca seçici geri gelir).
 * GERÇEK: AuthProvider, UserModeProvider, OperatorProvider, OperatorSwitcher, ObservationNotesModal, apiClient. Sahte: fetch, Supabase.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("klinik@ortak.com");
});
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import React, { act, useEffect, useState } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { Sahne, sahteSunucu, type SahteOperator } from "../../../context/__tests__/operatorAparati";
import KIMLIKSIZ from "./__fixtures__/notKimliksiz.Y116.json";

const AYSE: SahteOperator = { email: "dr.ayse@klinik.com", display_name: "Dr Ayşe" };

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let gorunurAyarla: (v: boolean) => void = () => undefined;
function Kap() {
  const [v, setV] = useState(true);
  gorunurAyarla = setV;
  return <ObservationNotesModal visible={v} onClose={() => undefined}
    session={{ patientName: "Boncuk", mode: "Manuel", obsKey: 1, dbSessionId: 1 }} />;
}

let s: Sahne;
let uyari: jest.SpyInstance;
beforeEach(() => {
  s = new Sahne();
  uyari = jest.spyOn(window, "alert").mockImplementation(() => undefined);
});
afterEach(async () => {
  await s.sok();
  uyari.mockRestore();
});

async function pinPenceresiAcik() {
  const sunucu = sahteSunucu([AYSE], (yol, _g, yontem, operator) =>
    yontem === "POST" && yol === "/session/notes"
      ? (operator ? [200, { status: "success", session_id: 1 }] : [KIMLIKSIZ.durum, KIMLIKSIZ.govde])
      : undefined);
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider><UserModeProvider><Mod mod="veterinarian"><OperatorProvider><Kap /></OperatorProvider></Mod></UserModeProvider></AuthProvider>,
  );
  await s.yaz("Gözlem notları", "taslak not");
  await s.metneTikla("💾 Kaydet");
  expect(s.metin()).toContain("Operatör seçin"); // ARA: 428 → pencere içi seçici
  const cip = document.querySelector('[aria-label="Operatör seç"]') as HTMLElement;
  await act(async () => { cip.click(); });
  await s.bosalt();
  await s.tikla("Seç: Dr Ayşe");
  expect(s.varMi("PIN")).toBe(true); // ARA: PIN penceresi açık
}

it("KRİTİK C2-2.2: not penceresi gizlenince (bobin çalışıyor) PIN penceresi ANINDA kalkar — ACİL DURDUR'u örtmez", async () => {
  await pinPenceresiAcik();
  await act(async () => { gorunurAyarla(false); });
  await s.bosalt();
  expect(s.varMi("PIN")).toBe(false);
});

it("KARŞIT C2-2.2: pencere yeniden açılınca not ve 'Operatör seçin' istemi KORUNUR, seçici geri gelir", async () => {
  await pinPenceresiAcik();
  await act(async () => { gorunurAyarla(false); });
  await s.bosalt();
  await act(async () => { gorunurAyarla(true); });
  await s.bosalt();
  expect((s.etiket("Gözlem notları") as HTMLTextAreaElement).value).toBe("taslak not");
  expect(s.metin()).toContain("Operatör seçin");
  expect(document.querySelectorAll('[aria-label="Operatör seç"]').length).toBe(1);
});
