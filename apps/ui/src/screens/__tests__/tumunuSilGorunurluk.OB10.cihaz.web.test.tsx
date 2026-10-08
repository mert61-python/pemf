/**
 * @jest-environment jsdom
 * @jest-environment-options {"url": "http://127.0.0.1:8000/"}
 */
// Author: mertaygn, cglrgrkn
/**
 * O-B.10 (2-B §6) — Hastalar ekranındaki "Tümünü Sil" (kliniğin TÜM hasta defteri) YALNIZ cihazın kendi ekranında görünür.
 * A-03 / D2.11: arka uç `/api/patients/delete_all`'u cihaz dışından (telefon, LAN, tünel) 403 ile reddeder; düğme yine de
 * görünüyordu → operatör basıp "yalnız cihazın kendi ekranından" hatası alıyordu (ölü eylem). Bu dosya sayfayı cihazın kendisi (launcher'ın açtığı loopback)
 * adresinden açar (`@jest-environment-options` url — gerçek `window.location`; cihazın kendisi `isDesktopHost()` = loopback).
 * KARŞIT (cihazın kendisi): tumunuSilGorunurluk.OB10.cihaz.web.test.tsx.
 *
 * GERÇEK: AuthProvider, UserModeProvider (veteriner), OperatorProvider (Kural 2), AppNavProvider, PatientScreen, apiClient.
 * Sahte yalnız `fetch`, Supabase istemcisi, toast.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => {
  const aparat = require("../../context/__tests__/operatorAparati");
  return {
    ...aparat.supabaseSahte(""),
    getCurrentSession: async () => ({ access_token: "x", user: { email: "tek@klinik.com", user_metadata: {} } }),
  };
});
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("expo-haptics", () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(), selectionAsync: jest.fn(),
  ImpactFeedbackStyle: {}, NotificationFeedbackType: {} }));
jest.mock("expo-linear-gradient", () => {
  const R = require("react");
  const { View } = require("react-native-web");
  return { LinearGradient: ({ children, style }: { children?: unknown; style?: unknown }) => R.createElement(View, { style }, children) };
});

import React, { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { PatientScreen } from "@/screens/PatientScreen";
import { Sahne, sahteSunucu } from "../../context/__tests__/operatorAparati";

function Veteriner({ children }: { children: React.ReactNode }) {
  const { setUserMode, userMode } = useUserMode();
  useEffect(() => { setUserMode("veterinarian"); }, [setUserMode]);
  return userMode ? <>{children}</> : null;
}

let s: Sahne;
beforeEach(() => { jest.useFakeTimers(); s = new Sahne(); });
afterEach(async () => { await s.sok(); jest.useRealTimers(); });

it("ARAÇ KANITI: sayfa cihazın kendisi (launcher'ın açtığı loopback) adresinden açık", () => {
  expect(window.location.hostname).toBe("127.0.0.1");
});

it("KARŞIT: cihazın kendi ekranında 'Tümünü Sil' GÖRÜNÜR", async () => {
  const sunucu = sahteSunucu([], (yol, _g, yontem) => {
    if (yontem === "GET" && yol === "/patients") return [200, { status: "success", data: [{ id: "p0", name: "HastaT", species: "Kedi" }] }];
    return undefined;
  });
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <UserModeProvider>
        <Veteriner>
          <OperatorProvider>
            <AppNavProvider navigateTo={() => undefined}>
              <PatientScreen />
            </AppNavProvider>
          </OperatorProvider>
        </Veteriner>
      </UserModeProvider>
    </AuthProvider>,
  );
  await s.ilerlet(50);
  await s.bosalt(10);
  expect(s.metin()).toContain("HastaT"); // ARA DOĞRULAMA: ekran çizildi (veteriner, Kural 2)
  expect(s.metin().includes("Tümünü Sil")).toBe(true);
});
