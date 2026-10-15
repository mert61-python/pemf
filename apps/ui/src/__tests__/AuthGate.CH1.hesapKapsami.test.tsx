// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — hesap geçişinde uygulama ağacı YENİDEN KURULUR, profil seçimi KORUNUR.
 * ==================================================================================
 * SÖZLEŞME (`PemfApp.AuthGate`): etkin e-posta A → B değişince operatör sağlayıcısı + ekranlar + kabuk YENİDEN KURULUR (jeton rozeti,
 * listeler, "Benim" kapsamı, seçili hekim, ekran önbellekleri A'nın verisini taşımaz); profil sağlayıcısı (`UserModeProvider`)
 * SÖKÜLMEZ — profil seçimi hesaptan bağımsız, kalıcı değil (sahip 07-07), geçiş onu sıfırlamaz. "Hesap ekle" giriş ekranı profil
 * sağlayıcısının İÇİNDE: ekleme bitince (ya da vazgeçilince) profil yine korunur. KARŞIT: tam çıkış (session null) profili sıfırlar.
 * GERÇEK: `AuthGate`, `UserModeProvider`, `MainRouter`, `AppNavProvider`; sahte olan bağlamlar, kabuk ve ekranlar (bağlama sayaçlı).
 * ⚠️ MUTASYON: anahtar kaldırılırsa (yeniden kurulmaz) ya da `UserModeProvider` anahtarın İÇİNE alınırsa (profil sıfırlanır) KIRMIZI.
 */
import React, { useEffect } from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Pressable, Text } from "react-native";

let mockAuth: any;
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => mockAuth,
  AuthProvider: ({ children }: any) => children,
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: { activeTreatment: { isActive: false }, coils: [] } }),
  LiveDataProvider: ({ children }: any) => children,
}));
jest.mock("@/context/EntitlementContext", () => ({ EntitlementProvider: ({ children }: any) => children }));
const mockSayac = { operator: 0, pano: 0 };
jest.mock("@/context/OperatorContext", () => {
  const R = require("react");
  return {
    useOperatorOptional: () => null,
    OperatorProvider: ({ children }: any) => {
      R.useEffect(() => { mockSayac.operator += 1; }, []);
      return children;
    },
  };
});
jest.mock("@/components/ui/AppShell", () => ({ AppShell: ({ children }: any) => children }));
jest.mock("@/screens/DashboardScreen", () => {
  const R = require("react");
  const { Text: T } = require("react-native");
  return {
    DashboardScreen: () => {
      R.useEffect(() => { mockSayac.pano += 1; }, []);
      return R.createElement(T, null, "pano");
    },
  };
});
jest.mock("@/screens/WelcomeScreen", () => {
  const R = require("react");
  const { Pressable: P, Text: T } = require("react-native");
  const { useUserMode } = require("@/context/UserModeContext");
  return {
    WelcomeScreen: () => {
      const { setUserMode } = useUserMode();
      return R.createElement(P, { onPress: () => setUserMode("veterinarian"), accessibilityLabel: "Veteriner seç" },
        R.createElement(T, null, "profil-secimi"));
    },
  };
});
jest.mock("@/screens/AuthScreen", () => {
  const R = require("react");
  const { Text: T } = require("react-native");
  return { AuthScreen: (p: any) => R.createElement(T, null, p.hesapEkleme ? "giris-ekleme-kipi" : "giris-ekrani") };
});

import { AuthGate } from "@/PemfApp";

void React; void useEffect; void Pressable; void Text;

function oturum(email: string | null, ek: Record<string, unknown> = {}) {
  mockAuth = { session: email ? { email, token: "t" } : null, loading: false, hesapEkleniyor: false, hesapEklemeVazgec: jest.fn(), ...ek };
}

async function profilSecilmisAgac() {
  oturum("a@klinik.com");
  const u = render(<AuthGate />);
  fireEvent.press(u.getByLabelText("Veteriner seç"));
  await act(async () => {});
  expect(u.queryByText("pano")).not.toBeNull();
  return u;
}

beforeEach(() => {
  mockSayac.operator = 0;
  mockSayac.pano = 0;
});

it("KRİTİK: A → B geçişte operatör + ekranlar YENİDEN KURULUR, profil seçimi KORUNUR (karşılama ekranı çıkmaz)", async () => {
  const u = await profilSecilmisAgac();
  const once = { ...mockSayac };
  oturum("b@klinik.com");
  await act(async () => { u.rerender(<AuthGate />); });
  expect(u.queryByText("profil-secimi")).toBeNull();
  expect(u.queryByText("pano")).not.toBeNull();
  expect(mockSayac.operator).toBe(once.operator + 1);
  expect(mockSayac.pano).toBe(once.pano + 1);
});

it("KARŞIT: aynı hesapta oturum nesnesi yenilenince (jeton yenileme) ağaç yeniden KURULMAZ", async () => {
  const u = await profilSecilmisAgac();
  const once = { ...mockSayac };
  oturum("A@klinik.com"); // aynı e-posta (büyük harf), yeni nesne
  await act(async () => { u.rerender(<AuthGate />); });
  expect(mockSayac).toEqual(once);
});

it("KRİTİK: 'Hesap ekle' giriş ekranı profil sağlayıcısının İÇİNDE — ekleme bitince profil KORUNUR", async () => {
  const u = await profilSecilmisAgac();
  oturum("a@klinik.com", { hesapEkleniyor: true });
  await act(async () => { u.rerender(<AuthGate />); });
  expect(u.queryByText("giris-ekleme-kipi")).not.toBeNull();
  oturum("b@klinik.com"); // B ile giriş yapıldı → ekleme bitti
  await act(async () => { u.rerender(<AuthGate />); });
  expect(u.queryByText("profil-secimi")).toBeNull();
  expect(u.queryByText("pano")).not.toBeNull();
});

it("KARŞIT: tam çıkış (oturum yok) profil seçimini SIFIRLAR (bugünkü davranış)", async () => {
  const u = await profilSecilmisAgac();
  oturum(null);
  await act(async () => { u.rerender(<AuthGate />); });
  expect(u.queryByText("giris-ekrani")).not.toBeNull();
  oturum("a@klinik.com");
  await act(async () => { u.rerender(<AuthGate />); });
  expect(u.queryByText("profil-secimi")).not.toBeNull();
});
