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
import { LiveDataProvider } from "@/context/LiveDataContext";

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

  return (
    <AppShell activeRoute={activeRoute} title={meta.title} subtitle={meta.subtitle} onRouteChange={setActiveRoute}>
      {activeRoute === "dashboard"  ? <DashboardScreen /> : null}
      {activeRoute === "control" && isExpert ? <ControlScreen /> : null}
      {activeRoute === "sensors" && isExpert ? <SensorMonitorScreen /> : null}
      {activeRoute === "history" && isExpert ? <TreatmentHistoryScreen /> : null}
      {activeRoute === "patients" && isExpert ? <PatientScreen /> : null}
      {activeRoute === "kpi" && isExpert ? <KpiDashboardScreen /> : null}
      {activeRoute === "simulator" ? <DemaSimulatorScreen /> : null}
      {activeRoute === "ai" ? <AiHubScreen /> : null}
      {activeRoute === "settings" ? <SettingsScreen /> : null}
    </AppShell>
  );
}

export function PemfApp() {
  return (
    <UserModeProvider>
      {/* LiveDataProvider wraps everything — all screens share one WS connection */}
      <LiveDataProvider>
        <MainRouter />
      </LiveDataProvider>
    </UserModeProvider>
  );
}
