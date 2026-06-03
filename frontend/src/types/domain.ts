export type RouteKey = "dashboard" | "control" | "sensors" | "history" | "kpi" | "simulator" | "ai" | "settings";

export type ConnectionState = "online" | "warning" | "offline";

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
}

export interface PatientSummary {
  name: string;
  species: string;
  breed: string;
  owner: string;
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

export interface DashboardSnapshot {
  gateway: ConnectionState;
  mqtt: ConnectionState;
  stm: ConnectionState;
  patient: PatientSummary;
  activeTreatment: {
    mode: string;
    frequencyHz: number;
    intensityMt: number;
    remainingMin: number;
  };
  coils: CoilStatus[];
  sessions: TreatmentSession[];
}
