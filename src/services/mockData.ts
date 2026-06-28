import { DashboardSnapshot } from "@/types/domain";

/**
 * Boş başlangıç snapshot — DEMO VERİ YOK.
 * Tüm veriler WebSocket üzerinden Python GUI backend'inden gelir.
 * Bu sadece ilk HTTP snapshot gelmeden önce UI'ın çökmemesi için kullanılır.
 */
export const mockSnapshot: DashboardSnapshot = {
  gateway: "offline",
  mqtt: "offline",
  stm: "offline",
  patient: {
    name: "",
    species: "",
    breed: "",
    owner: ""
  },
  activeTreatment: {
    mode: "Sistem Hazır",
    frequencyHz: 0,
    intensityMt: 0,
    remainingMin: 0,
    elapsedSec: 0,
    durationSec: 0,
    isActive: false
  },
  notifications: [],
  system: {
    softwareVersion: "—",
    hardwareVersion: "—",
    deviceId: "—",
    totalSessions: 0,
    uptime: "—",
    startTime: new Date().toISOString()
  },
  coils: Array.from({ length: 8 }, (_, index) => ({
    id: index + 1,
    connected: false,
    running: false,
    frequencyHz: 0,
    dutyCycle: 0,
    magneticMt: 0,
    objectTemp: 0,
    ambientTemp: 0,
    currentA: 0,
    stm32Driven: index < 5,   // Bobin 1-5 STM32, 6-8 ESP
  })),
  sessions: []
};
