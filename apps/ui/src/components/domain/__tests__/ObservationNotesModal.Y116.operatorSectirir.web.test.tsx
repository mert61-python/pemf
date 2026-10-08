/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * Y116 (S-B2B2.1) — seans sonu gözlem notu kayıtlı operatörlü klinikte KİMLİK ister: not ekranı 428'de notu KAYBETMEDEN
 * operatörü KENDİ İÇİNDE seçtirir; seçimden sonra aynı not operatör jetonuyla gider.
 * ===========================================================================================================================
 * NEDEN EKRANIN İÇİNDE: not penceresi tam ekran örtüdür — üst bardaki operatör çipine ulaşılamaz; 428 iletisi "Operatör seçin"
 * deyip seçtirmezse hekim ya notu bırakır ya pencereyi kapatıp NOTU KAYBEDER (kimliksiz başlatılmış seansın notu — Y109).
 * `/session/notes` 428 yanıtı GERÇEK backend'den üretilen fikstürdür (`tests/test_seans_sonu_NOTU_kimlik_ister_DOZ_degismez_Y116.py`).
 * GERÇEK: AuthProvider, UserModeProvider (veterinarian), OperatorProvider, OperatorSwitcher, ObservationNotesModal, apiClient
 * (`X-PEMF-Operator` başlığını ürün kurar). Sahte: fetch (ağ sınırı — jetonsuz not isteğine fikstürdeki 428, jetonluya 200),
 * Supabase, güvenli alan kancası, `window.alert`.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../../context/__tests__/operatorAparati");
  return aparat.supabaseSahte("klinik@ortak.com");
});
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import React, { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { Sahne, sahteSunucu, pinleSec, aktifOperator, type Istek, type SahteOperator } from "../../../context/__tests__/operatorAparati";
import KIMLIKSIZ from "./__fixtures__/notKimliksiz.Y116.json";

const NOT = "Uyudu — kulaklar gevşek";
const AYSE: SahteOperator = { email: "dr.ayse@klinik.com", display_name: "Dr Ayşe" };

function Mod({ mod, children }: { mod: UserMode; children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode(mod); }, [mod, setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
let kayit: Istek[];
let uyari: jest.SpyInstance;
beforeEach(() => {
  s = new Sahne();
  uyari = jest.spyOn(window, "alert").mockImplementation(() => undefined);
});
afterEach(async () => {
  await s.sok();
  uyari.mockRestore();
});

async function kur(operatorler: SahteOperator[]) {
  const sunucu = sahteSunucu(operatorler, (yol, _g, yontem, operator) => {
    if (yontem === "POST" && yol === "/session/notes") {
      return operator || !operatorler.length ? [200, { status: "success", session_id: 1, updated: true }] : [KIMLIKSIZ.durum, KIMLIKSIZ.govde];
    }
    return undefined;
  });
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  const kapat = jest.fn();
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Mod mod="veterinarian">
          <OperatorProvider>
            <ObservationNotesModal visible session={{ patientName: "Boncuk", mode: "Manuel", obsKey: 1, dbSessionId: 1 }} onClose={kapat} />
          </OperatorProvider>
        </Mod>
      </UserModeProvider>
    </AuthProvider>,
  );
  return kapat;
}

const notIstekleri = () => kayit.filter((i) => i.yontem === "POST" && i.yol === "/session/notes");

it("KRİTİK Y116: 428'de not ekranı AÇIK kalır, not DURUR ve operatör EKRANIN İÇİNDE seçilir; aynı not jetonla gider", async () => {
  const kapat = await kur([AYSE]);
  await s.yaz("Gözlem notları", NOT);
  await s.metneTikla("💾 Kaydet");
  expect(notIstekleri().map((i) => i.operator)).toEqual([null]); // ARA: jetonsuz ilk deneme 428 aldı
  expect(kapat).not.toHaveBeenCalled();
  expect((s.etiket("Gözlem notları") as HTMLTextAreaElement).value).toBe(NOT);
  expect(s.metin()).toContain("Operatör seçin");
  await pinleSec(s, "Dr Ayşe"); // pencerenin İÇİNDEKİ operatör çipi
  expect(aktifOperator()).toBe("Dr Ayşe");
  expect((s.etiket("Gözlem notları") as HTMLTextAreaElement).value).toBe(NOT); // seçim notu silmedi
  await s.metneTikla("💾 Kaydet");
  const istekler = notIstekleri();
  expect(istekler.map((i) => i.operator)).toEqual([null, `JETON-${AYSE.email}`]);
  expect((istekler[1].govde as { notes?: string }).notes).toBe(NOT);
  expect(kapat).toHaveBeenCalledTimes(1);
});

it("KARŞIT Y116 · Kural 2: operatörsüz klinikte not jetonsuz kaydedilir, operatör sorulmaz", async () => {
  const kapat = await kur([]);
  await s.yaz("Gözlem notları", NOT);
  await s.metneTikla("💾 Kaydet");
  expect(notIstekleri().map((i) => i.operator)).toEqual([null]);
  expect(kapat).toHaveBeenCalledTimes(1);
  expect(s.metin()).not.toContain("Operatör seçin");
});
