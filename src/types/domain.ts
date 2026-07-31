// ─── Route ───────────────────────────────────────────────────────────────────
export type RouteKey =
  | "dashboard"
  | "control"
  | "sensors"
  | "history"
  | "patients"
  | "kpi"
  | "simulator"
  | "ai"
  | "ai_history"
  | "settings";

// ─── Connection ──────────────────────────────────────────────────────────────
export type ConnectionState = "online" | "warning" | "offline" | "error";

// ─── Coil ────────────────────────────────────────────────────────────────────
export interface CoilStatus {
  id: number;
  connected: boolean;
  running: boolean;
  frequencyHz: number;
  dutyCycle: number;
  magneticMt: number;
  objectTemp: number;
  ambientTemp: number;
  currentA: number;
  stm32Driven?: boolean;
  phase?: number;
  durationMin?: number;
}

// ─── Patient ─────────────────────────────────────────────────────────────────
export interface PatientSummary {
  name: string;
  species: string;
  breed: string;
  owner: string;
}

export interface Patient extends PatientSummary {
  id?: string;
  age?: string;
  weight?: string;
  vet_contact?: string;
  owner_email?: string;  // hasta sahibi e-postası (rapor gönderimi) — backend PatientInput ile aynı
  operator_email?: string;  // kaydı oluşturan hekim e-postası (klinik-içi "Benim Hastalarım" filtresi)
}

// ─── Session / Treatment ──────────────────────────────────────────────────────
export interface ActiveTreatment {
  mode: string;
  frequencyHz: number;
  intensityMt: number;
  remainingMin: number;
  elapsedSec: number;
  durationSec: number;
  isActive: boolean;
}

export interface TreatmentSession {
  id: string;
  date: string;
  patientName: string;
  mode: string;
  target: string;
  durationMin: number;
  status: "completed" | "running" | "stopped";
}

// ─── Notifications ────────────────────────────────────────────────────────────
export type NotificationLevel = "success" | "warning" | "error" | "info";

export interface AppNotification {
  id: number;
  message: string;
  level: NotificationLevel;
  timestamp: string;
  read?: boolean;
}

// ─── System ──────────────────────────────────────────────────────────────────
export interface SystemInfo {
  softwareVersion: string;
  hardwareVersion: string;
  deviceId: string;
  startTime: string;
  uptime: string;
  totalSessions: number;
}

// ─── Dashboard Snapshot ──────────────────────────────────────────────────────
export interface DashboardSnapshot {
  gateway: ConnectionState;
  mqtt: ConnectionState;
  stm: ConnectionState;
  patient: PatientSummary;
  activeTreatment: ActiveTreatment;
  coils: CoilStatus[];
  sessions: TreatmentSession[];
  notifications: AppNotification[];
  system: SystemInfo;
}

// ─── WebSocket live data ──────────────────────────────────────────────────────
export interface SensorDataPoint {
  magneticMt: number;
  objectTemp: number;
  ambientTemp: number;
  currentA: number;
  timestamp: number;
}

// Per-coil history: last 2000 samples
export type CoilSensorHistory = Record<number, SensorDataPoint[]>;
