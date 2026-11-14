// Author: mertaygn, cglrgrkn
import { useState, lazy, Suspense } from "react";
import { View, ActivityIndicator } from "react-native";
import { AppShell } from "@/components/ui/AppShell";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { colors } from "@/theme/tokens";
import { RouteKey } from "@/types/domain";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { canAccess, varsayilanRota } from "@/config/access";
import { sayfaBasligi } from "@/config/sayfaBasliklari";
import { useTranslation } from "react-i18next";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { EntitlementProvider } from "@/context/EntitlementContext";
import { AuthScreen } from "@/screens/AuthScreen";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { tembelEkranlar } from "@/tembelEkranlar";

// audit B-6.1: code-splitting — ilk-boyama (Welcome/Dashboard) EAGER; ağır/nadir ekranlar LAZY. KP-5 (Y279): `import()` fabrikaları
// `tembelEkranlar` küçük modülünde (jest `import()` çalıştıramaz — gerekçeli etiket orada); burada yalnız `lazy` bağlanır.
const ControlScreen = lazy(tembelEkranlar.ControlScreen);
const DemaSimulatorScreen = lazy(tembelEkranlar.DemaSimulatorScreen);
const KpiDashboardScreen = lazy(tembelEkranlar.KpiDashboardScreen);
const SensorMonitorScreen = lazy(tembelEkranlar.SensorMonitorScreen);
const TreatmentHistoryScreen = lazy(tembelEkranlar.TreatmentHistoryScreen);
const PatientScreen = lazy(tembelEkranlar.PatientScreen);
const AiHubScreen = lazy(tembelEkranlar.AiHubScreen);
const SettingsScreen = lazy(tembelEkranlar.SettingsScreen);
const AiHistoryScreen = lazy(tembelEkranlar.AiHistoryScreen);

function MainRouter() {
  useTranslation(); // sayfa başlıkları (`sayfaBasligi`) çağrı anında çevrilir → dil değişince yeniden çiz
  const { userMode } = useUserMode();
  // ⚠️ `null` = rota henüz seçilmedi → profilin AÇILIŞ rotası kullanılır (aşağıda).
  // Sabit "dashboard" ile başlamak, o rotanın kapalı olduğu pet_owner profilinde
  // yedeğe düşüp yine "dashboard"a dönmek demekti (2026-09-12'de kaldırıldı).
  const [activeRoute, setActiveRoute] = useState<RouteKey | null>(null);

  if (!userMode) {
    return <WelcomeScreen />;
  }

  // Profil bu rotaya erişemiyorsa AÇILIŞ rotasına düş. TEK KAYNAK: config/access
  // (PemfApp + AppShell tutarlı) → yanlış profile cihaz/tedavi ekranı sızmaz.
  // ⚠️ YEDEK ROTA ARTIK SABİT DEĞİL: "dashboard" her profilde yok (bkz. varsayilanRota).
  // Sabit bıraksaydık pet_owner erişemediği bir rotaya düşer ve BOŞ EKRAN görürdü.
  const acilis = varsayilanRota(userMode);
  const effectiveRoute =
    activeRoute && canAccess(userMode, activeRoute) ? activeRoute : acilis;

  return (
    <AppNavProvider navigateTo={setActiveRoute}>
    <AppShell activeRoute={effectiveRoute} title={sayfaBasligi(userMode, effectiveRoute).title} subtitle={sayfaBasligi(userMode, effectiveRoute).subtitle} onRouteChange={setActiveRoute}>
      {/* audit B-10.3: EKRAN-bazlı ErrorBoundary — bir ekran çökse bile nav-shell hayatta kalır
          (tüm uygulama beyaz-ekrana düşmez). key={route} → route değişince boundary sıfırlanır. */}
      <ErrorBoundary key={effectiveRoute}>
        <Suspense fallback={<View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}><ActivityIndicator size="large" color={colors.primary} /></View>}>
          {effectiveRoute === "dashboard"  ? <DashboardScreen /> : null}
          {/* Gate TEK KAYNAK: effectiveRoute yukarıda canAccess ile kapılandı → erişilemez rota buraya
              ulaşamaz. Ekstra kontrol gereksiz + tutarsız olurdu; hepsi effectiveRoute'a güvenir. */}
          {effectiveRoute === "control" ? <ControlScreen /> : null}
          {effectiveRoute === "sensors" ? <SensorMonitorScreen /> : null}
          {effectiveRoute === "history" ? <TreatmentHistoryScreen /> : null}
          {effectiveRoute === "patients" ? <PatientScreen /> : null}
          {effectiveRoute === "kpi" ? <KpiDashboardScreen /> : null}
          {effectiveRoute === "simulator" ? <DemaSimulatorScreen /> : null}
          {effectiveRoute === "ai" ? <AiHubScreen /> : null}
          {effectiveRoute === "ai_history" ? <AiHistoryScreen /> : null}
          {effectiveRoute === "settings" ? <SettingsScreen /> : null}
        </Suspense>
      </ErrorBoundary>
    </AppShell>
    </AppNavProvider>
  );
}

/** Giriş kapısı + hesap kapsamı. Dışa açık YALNIZ test için (CH1 yeniden kurulum kapısı: `__tests__/AuthGate.CH1.hesapKapsami`). */
export function AuthGate() {
  const { session, loading, hesapEkleniyor, hesapEklemeVazgec } = useAuth();
  if (loading) {
    // Saklı oturum kontrol edilirken kısa yükleme (splash; tavan `HYDRATE_SPLASH_CEILING_MS` = 6 sn).
    // ⚠️ L1-7.11 (O-9.1 · A-58 deseni): uygulama bobinler çalışırken yeniden açılırsa splash süresince de ACİL DURDUR olmalı —
    // Karşılama / Giriş ekranlarıyla AYNI `GlobalEmergencyStop` (görünürlük yalnız donanım durumuna bağlı; oturuma / yüklemeye /
    // kataloğa BAĞLANMAZ, Ö.4-Y8). `LiveDataProvider` en dışta → anlık görüntü splash'te de canlı. Kapı: AuthGate.L1_7_11.splashAcilDurdur.test.tsx
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator size="large" color={colors.primary} />
        <GlobalEmergencyStop />
      </View>
    );
  }
  // Giriş yapılmadı → login/kayıt ekranı (backend, LiveDataProvider'ın discovery'siyle erişilebilir).
  if (!session) {
    return <AuthScreen />;
  }
  // Giriş yapıldı → profil seçimi + uygulama.
  // ⚠️ CH1 · Y151 (çoklu hesap): profil sağlayıcısı (`UserModeProvider`) hesap değişiminde SÖKÜLMEZ — profil seçimi hesaptan BAĞIMSIZ
  // ve kalıcı DEĞİL (sahip 07-07): geçiş onu sıfırlamaz, diske de yazmaz; `X-PEMF-Profil` aynen. "Hesap ekle" giriş ekranı da bu yüzden
  // sağlayıcının İÇİNDE. Altındaki ağaç (operatör + tüm ekranlar + kabuk) hesap anahtarıyla YENİDEN KURULUR: jeton rozeti, liste /
  // geçmiş / "Benim" kapsamı, operatör seçimi ve ekran önbellekleri önceki hesabın verisini bir an bile taşımaz.
  return (
    <UserModeProvider>
      {hesapEkleniyor ? (
        <AuthScreen hesapEkleme onVazgec={hesapEklemeVazgec} />
      ) : (
        /* AKTİF OPERATÖR (2026-08-08): tek makineyi paylaşan veterinerler kendi kimlikleriyle
           çalışsın. `sessionActive` → seans sürerken hareketsizlik kilidi ERTELENİR (hasta
           güvenliği: bobinler çalışırken operatörü PIN ekranına sokma). */
        <OperatorKapsayici key={hesapAnahtari(session.email)}>
          <MainRouter />
        </OperatorKapsayici>
      )}
    </UserModeProvider>
  );
}

/** CH1: uygulama ağacının hesap anahtarı — e-posta değişince (geçiş) ağaç yeniden kurulur. */
export function hesapAnahtari(eposta: string | null | undefined): string {
  return `hesap:${(eposta || "").trim().toLowerCase()}`;
}


/** `OperatorProvider`'a canlı seans durumunu geçirir (kilit ertelemesi için). */
function OperatorKapsayici({ children }: { children: React.ReactNode }) {
  const { snapshot } = useLiveData();
  const seansAktif = !!snapshot?.activeTreatment?.isActive;
  return <OperatorProvider sessionActive={seansAktif}>{children}</OperatorProvider>;
}

export function PemfApp() {
  return (
    <ErrorBoundary>
      {/* LiveDataProvider EN DIŞTA → discovery/WS login ekranında da aktif (backend erişilebilir).
          AuthProvider giriş-oturumunu yönetir; giriş yapılınca UserModeProvider + uygulama gelir. */}
      <LiveDataProvider>
        <AuthProvider>
          <EntitlementProvider>
            <AuthGate />
          </EntitlementProvider>
        </AuthProvider>
      </LiveDataProvider>
    </ErrorBoundary>
  );
}
