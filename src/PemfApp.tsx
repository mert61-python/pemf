import { useState, lazy, Suspense } from "react";
import { View, ActivityIndicator } from "react-native";
import { AppShell } from "@/components/ui/AppShell";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { colors } from "@/theme/tokens";
import { RouteKey } from "@/types/domain";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { AppNavProvider } from "@/context/AppNavContext";

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

const routeMeta: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: "Hoş Geldiniz", subtitle: "Bugün Hangi Dostumuzu Tedavi Ediyoruz?" },
  control: { title: "Tedavi Kontrol Merkezi", subtitle: "Akıllı Reçeteler ve Cihaz Yönetimi" },
  sensors: { title: "Cihaz Durumu", subtitle: "Gerçek Zamanlı Sensör İzleme" },
  history: { title: "Tedavi Geçmişi", subtitle: "Geçmiş seansları incele ve rapor al." },
  patients: { title: "Hasta Kayıtları", subtitle: "Dostlarımızın bilgileri." },
  kpi: { title: "Performans Raporu", subtitle: "Cihaz ve klinik göstergeleri." },
  simulator: { title: "Etki Simülasyonu", subtitle: "Manyetik alanın dostumuza etkisini görselleştirin." },
  ai: { title: "Akıllı Teşhis", subtitle: "Kamera üzerinden otonom ağrı analizi ve tedavi." },
  settings: { title: "Ayarlar", subtitle: "Cihaz tercihleri ve gelişmiş mod." },
};

function MainRouter() {
  const { userMode, isExpert } = useUserMode();
  const [activeRoute, setActiveRoute] = useState<RouteKey>("dashboard");

  if (!userMode) {
    return <WelcomeScreen />;
  }

  const EXPERT_ROUTES: RouteKey[] = ["control", "sensors", "history", "patients", "kpi"];
  // Uzman olmayan kullanıcı uzman rotaya geçerse dashboard'a yönlendir
  const effectiveRoute = (!isExpert && EXPERT_ROUTES.includes(activeRoute)) ? "dashboard" : activeRoute;

  return (
    <AppNavProvider navigateTo={setActiveRoute}>
    <AppShell activeRoute={effectiveRoute} title={routeMeta[effectiveRoute].title} subtitle={routeMeta[effectiveRoute].subtitle} onRouteChange={setActiveRoute}>
      {/* audit B-10.3: EKRAN-bazlı ErrorBoundary — bir ekran çökse bile nav-shell hayatta kalır
          (tüm uygulama beyaz-ekrana düşmez). key={route} → route değişince boundary sıfırlanır. */}
      <ErrorBoundary key={effectiveRoute}>
        <Suspense fallback={<View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}><ActivityIndicator size="large" color={colors.primary} /></View>}>
          {effectiveRoute === "dashboard"  ? <DashboardScreen /> : null}
          {effectiveRoute === "control" && isExpert ? <ControlScreen /> : null}
          {effectiveRoute === "sensors" && isExpert ? <SensorMonitorScreen /> : null}
          {effectiveRoute === "history" && isExpert ? <TreatmentHistoryScreen /> : null}
          {effectiveRoute === "patients" && isExpert ? <PatientScreen /> : null}
          {effectiveRoute === "kpi" && isExpert ? <KpiDashboardScreen /> : null}
          {effectiveRoute === "simulator" ? <DemaSimulatorScreen /> : null}
          {effectiveRoute === "ai" ? <AiHubScreen /> : null}
          {effectiveRoute === "settings" ? <SettingsScreen /> : null}
        </Suspense>
      </ErrorBoundary>
    </AppShell>
    </AppNavProvider>
  );
}

export function PemfApp() {
  return (
    <ErrorBoundary>
      <UserModeProvider>
        {/* LiveDataProvider wraps everything — all screens share one WS connection */}
        <LiveDataProvider>
          <MainRouter />
        </LiveDataProvider>
      </UserModeProvider>
    </ErrorBoundary>
  );
}
