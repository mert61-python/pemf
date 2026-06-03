import { useEffect, useState } from "react";
import { AppShell } from "@/components/ui/AppShell";
import { mockSnapshot } from "@/services/mockData";
import { apiGet, apiPost } from "@/services/apiClient";
import { ControlScreen } from "@/screens/ControlScreen";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { DemaSimulatorScreen } from "@/screens/DemaSimulatorScreen";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";
import { PlaceholderScreen } from "@/screens/PlaceholderScreen";
import { SensorMonitorScreen } from "@/screens/SensorMonitorScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { PatientScreen } from "@/screens/PatientScreen";
import { AiHubScreen } from "@/screens/AiHubScreen";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";
import { RouteKey } from "@/types/domain";
import { UserModeProvider, useUserMode } from "@/context/UserModeContext";

const routeMeta: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: "Hoş Geldiniz", subtitle: "Bugün Hangi Dostumuzu Tedavi Ediyoruz?" },
  control: { title: "Tedavi Kontrol Merkezi", subtitle: "Akıllı Reçeteler ve Cihaz Yönetimi" },
  sensors: { title: "Cihaz Durumu", subtitle: "Bölgesel Isı ve Sinyal Takibi" },
  history: { title: "Tedavi Geçmişi", subtitle: "Geçmiş seansları incele ve rapor al." },
  patients: { title: "Hasta Kayıtları", subtitle: "Dostlarımızın bilgileri." },
  kpi: { title: "Performans Raporu", subtitle: "Cihaz ve klinik göstergeleri." },
  simulator: { title: "Etki Simülasyonu", subtitle: "Manyetik alanın dostumuza etkisini görselleştirin." },
  ai: { title: "Akıllı Teşhis (Kamera)", subtitle: "Kamera üzerinden otonom ağrı analizi ve tedavi." },
  settings: { title: "Ayarlar", subtitle: "Cihaz tercihleri ve gelişmiş mod." }
};

function MainRouter() {
  const { userMode, isExpert } = useUserMode();
  const [activeRoute, setActiveRoute] = useState<RouteKey>("dashboard");
  const [snapshot, setSnapshot] = useState(mockSnapshot);
  const [commandStatus, setCommandStatus] = useState("Sistem Hazır.");
  const meta = routeMeta[activeRoute];

  useEffect(() => {
    let mounted = true;

    const loadSnapshot = async () => {
      const nextSnapshot = await apiGet("/dashboard-snapshot", mockSnapshot);
      if (mounted) {
        setSnapshot(nextSnapshot);
      }
    };

    loadSnapshot();
    const interval = setInterval(loadSnapshot, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const sendHardwareCommand = async (command: string, params: unknown, successMessage: string) => {
    const result = await apiPost<{ status: string }>("/hardware/command", { command, params }, { status: "error" });
    setCommandStatus(result.status === "success" ? successMessage : "Komut cihaza iletilemedi.");
  };

  if (!userMode) {
    return <WelcomeScreen />;
  }

  return (
    <AppShell activeRoute={activeRoute} title={meta.title} subtitle={meta.subtitle} onRouteChange={setActiveRoute}>
      {activeRoute === "dashboard" ? (
        <DashboardScreen
          commandStatus={commandStatus}
          onStart={() => sendHardwareCommand("start_treatment", snapshot.activeTreatment, "Tedavi başlatılıyor...")}
          onStop={() => sendHardwareCommand("stop_treatment", {}, "Tedavi acil durduruldu.")}
          snapshot={snapshot}
        />
      ) : null}
      {activeRoute === "control" && isExpert ? (
        <ControlScreen
          commandStatus={commandStatus}
          onHardwareCommand={sendHardwareCommand}
          snapshot={snapshot}
        />
      ) : null}
      {activeRoute === "sensors" && isExpert ? <SensorMonitorScreen snapshot={snapshot} /> : null}
      {activeRoute === "history" && isExpert ? <TreatmentHistoryScreen snapshot={snapshot} /> : null}
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
      <MainRouter />
    </UserModeProvider>
  );
}
