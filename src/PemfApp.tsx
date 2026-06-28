import { useState } from "react";
import { AppShell } from "@/components/ui/AppShell";
import { ControlScreen } from "@/screens/ControlScreen";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { PatientScreen } from "@/screens/PatientScreen";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { RouteKey } from "@/types/domain";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { AppNavProvider } from "@/context/AppNavContext";

const routeMeta: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: "Hoş Geldiniz", subtitle: "Bugün Hangi Dostumuzu Tedavi Ediyoruz?" },
  control: { title: "Tedavi Kontrol Merkezi", subtitle: "Akıllı Reçeteler ve Cihaz Yönetimi" },
  sensors: { title: "Cihaz Durumu", subtitle: "Gerçek Zamanlı Sensör İzleme" },
  history: { title: "Tedavi Geçmişi", subtitle: "Geçmiş seansları incele ve rapor al." },
  patients: { title: "Hasta Kayıtları", subtitle: "Dostlarımızın bilgileri." },
  kpi: { title: "Performans Raporu", subtitle: "Cihaz ve klinik göstergeleri." },
  simulator: { title: "Etki Simülasyonu", subtitle: "Manyetik alanın dostumuza etkisini görselleştirin." },
  ai: { title: "Akıllı Teşhis (Kamera)", subtitle: "Kamera üzerinden otonom ağrı analizi ve tedavi." },
  settings: { title: "Ayarlar", subtitle: "Cihaz tercihleri ve gelişmiş mod." },
};

function MainRouter() {
  const { userMode, isExpert } = useUserMode();
  const [activeRoute, setActiveRoute] = useState<RouteKey>("dashboard");
  const meta = routeMeta[activeRoute];

  if (!userMode) {
    return <WelcomeScreen />;
  }

  const EXPERT_ROUTES: RouteKey[] = ["control", "sensors", "history", "patients", "kpi"];
  // Uzman olmayan kullanıcı uzman rotaya geçerse dashboard'a yönlendir
  const effectiveRoute = (!isExpert && EXPERT_ROUTES.includes(activeRoute)) ? "dashboard" : activeRoute;

  return (
    <AppNavProvider navigateTo={setActiveRoute}>
    <AppShell activeRoute={effectiveRoute} title={routeMeta[effectiveRoute].title} subtitle={routeMeta[effectiveRoute].subtitle} onRouteChange={setActiveRoute}>
      {effectiveRoute === "dashboard"  ? <DashboardScreen /> : null}
      {effectiveRoute === "control" && isExpert ? <ControlScreen /> : null}
      {effectiveRoute === "sensors" && isExpert ? <SensorMonitorScreen /> : null}
      {effectiveRoute === "history" && isExpert ? <TreatmentHistoryScreen /> : null}
      {effectiveRoute === "patients" && isExpert ? <PatientScreen /> : null}
      {effectiveRoute === "kpi" && isExpert ? <KpiDashboardScreen /> : null}
      {effectiveRoute === "simulator" ? <DemaSimulatorScreen /> : null}
      {effectiveRoute === "ai" ? <AiHubScreen /> : null}
      {effectiveRoute === "settings" ? <SettingsScreen /> : null}
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
