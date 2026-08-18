// Author: mertaygn, cglrgrkn
import { useState, lazy, Suspense } from "react";
import { View, ActivityIndicator } from "react-native";
import { AppShell } from "@/components/ui/AppShell";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { colors } from "@/theme/tokens";
import { RouteKey } from "@/types/domain";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { canAccess } from "@/config/access";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { LiveDataProvider, useLiveData } from "@/context/LiveDataContext";
import { AppNavProvider } from "@/context/AppNavContext";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { EntitlementProvider } from "@/context/EntitlementContext";
import { AuthScreen } from "@/screens/AuthScreen";

// audit B-6.1: code-splitting — ilk-boyama (Welcome/Dashboard) EAGER; ağır/nadir ekranlar LAZY →
// açılış bundle'ı küçülür (özellikle web tek-bundle). Named export → default'a sar. Suspense fallback altta.
const ControlScreen = lazy(() => import("@/screens/ControlScreen").then((m) => ({ default: m.ControlScreen })));
const DemaSimulatorScreen = lazy(() => import("@/screens/DemaSimulatorScreen").then((m) => ({ default: m.DemaSimulatorScreen })));
const KpiDashboardScreen = lazy(() => import("@/screens/KpiDashboardScreen").then((m) => ({ default: m.KpiDashboardScreen })));
const SensorMonitorScreen = lazy(() => import("@/screens/SensorMonitorScreen").then((m) => ({ default: m.SensorMonitorScreen })));
const TreatmentHistoryScreen = lazy(() => import("@/screens/TreatmentHistoryScreen").then((m) => ({ default: m.TreatmentHistoryScreen })));
const PatientScreen = lazy(() => import("@/screens/PatientScreen").then((m) => ({ default: m.PatientScreen })));
const AiHubScreen = lazy(() => import("@/screens/AiHubScreen").then((m) => ({ default: m.AiHubScreen })));
const SettingsScreen = lazy(() => import("@/screens/SettingsScreen").then((m) => ({ default: m.SettingsScreen })));
const AiHistoryScreen = lazy(() => import("@/screens/AiHistoryScreen").then((m) => ({ default: m.AiHistoryScreen })));

const routeMeta: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: "Hoş Geldiniz", subtitle: "Bugün Hangi Dostumuza Seans Yapıyoruz?" },
  control: { title: "Seans Kontrol Merkezi", subtitle: "Akıllı Reçeteler ve Cihaz Yönetimi" },
  sensors: { title: "Cihaz Durumu", subtitle: "Gerçek Zamanlı Sensör İzleme" },
  history: { title: "Seans Geçmişi", subtitle: "Geçmiş seansları incele ve rapor al." },
  patients: { title: "Hasta Kayıtları", subtitle: "Dostlarımızın bilgileri." },
  kpi: { title: "Performans Raporu", subtitle: "Cihaz ve klinik göstergeleri." },
  simulator: { title: "Etki Simülasyonu", subtitle: "Manyetik alanın dostumuza etkisini görselleştirin." },
  ai: { title: "Akıllı Teşhis", subtitle: "Kamera üzerinden otonom ağrı analizi ve seans." },
  ai_history: { title: "AI Analiz Geçmişi", subtitle: "Tüm modellerin analiz sonuçları — şifreli, detaylı kayıt." },
  settings: { title: "Ayarlar", subtitle: "Cihaz tercihleri ve gelişmiş mod." },
};

function MainRouter() {
  const { userMode } = useUserMode();
  const [activeRoute, setActiveRoute] = useState<RouteKey>("dashboard");

  if (!userMode) {
    return <WelcomeScreen />;
  }

  // Profil bu rotaya erişemiyorsa dashboard'a düş. TEK KAYNAK: config/access (PemfApp + AppShell tutarlı) →
  // yanlış profile cihaz/tedavi ekranı sızmaz (ör. pet_owner control/sensors/kpi göremez).
  // (2026-08-06: örnek "researcher" idi; sahip kararıyla araştırma profiline cihaz rotaları açıldı.)
  const effectiveRoute = canAccess(userMode, activeRoute) ? activeRoute : "dashboard";

  return (
    <AppNavProvider navigateTo={setActiveRoute}>
    <AppShell activeRoute={effectiveRoute} title={routeMeta[effectiveRoute].title} subtitle={routeMeta[effectiveRoute].subtitle} onRouteChange={setActiveRoute}>
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

function AuthGate() {
  const { session, loading } = useAuth();
  if (loading) {
    // Saklı oturum kontrol edilirken kısa yükleme (splash)
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }
  // Giriş yapılmadı → login/kayıt ekranı (backend, LiveDataProvider'ın discovery'siyle erişilebilir).
  if (!session) {
    return <AuthScreen />;
  }
  // Giriş yapıldı → profil seçimi + uygulama.
  return (
    <UserModeProvider>
      {/* AKTİF OPERATÖR (2026-08-08): tek makineyi paylaşan veterinerler kendi kimlikleriyle
          çalışsın. `sessionActive` → seans sürerken hareketsizlik kilidi ERTELENİR (hasta
          güvenliği: bobinler çalışırken operatörü PIN ekranına sokma). */}
      <OperatorKapsayici>
        <MainRouter />
      </OperatorKapsayici>
    </UserModeProvider>
  );
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
