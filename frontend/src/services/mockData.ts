import { DashboardSnapshot } from "@/types/domain";

export const mockSnapshot: DashboardSnapshot = {
  gateway: "online",
  mqtt: "online",
  stm: "warning",
  patient: {
    name: "Mia",
    species: "Kedi",
    breed: "British Shorthair",
    owner: "Demo Sahip"
  },
  activeTreatment: {
    mode: "Sistem Hazır",
    frequencyHz: 0,
    intensityMt: 0,
    remainingMin: 0,
    elapsedSec: 0,
    durationSec: 0,
    isActive: false  // Uygulama açılışında sahte aktif seans gösterilmemeli
  },
  notifications: [],
  system: {
    softwareVersion: "1.0.0",
    hardwareVersion: "v1.2",
    deviceId: "PEMF-MOCK",
    totalSessions: 124,
    uptime: "02:15:43",
    startTime: "2024-03-20T08:00:00Z"
  },
  coils: Array.from({ length: 8 }, (_, index) => ({
    id: index + 1,
    connected: index !== 6,
    running: index < 4,
    frequencyHz: index < 4 ? 42 : 0,
    dutyCycle: index < 4 ? 55 + index * 4 : 0,
    magneticMt: 1.2 + index * 0.18,
    objectTemp: 32.4 + index * 0.2,
    ambientTemp: 24.7,
    currentA: 0.42 + index * 0.04
  })),
  sessions: [
    { id: "S-1024", date: "2026-06-01 09:42", patientName: "Mia", mode: "Auto", target: "Doku", durationMin: 20, status: "completed" },
    { id: "S-1023", date: "2026-05-31 17:10", patientName: "Pamuk", mode: "Manual", target: "Eklem", durationMin: 15, status: "completed" },
    { id: "S-1022", date: "2026-05-31 12:35", patientName: "Leo", mode: "AI", target: "Ağrı", durationMin: 12, status: "stopped" }
  ]
};
