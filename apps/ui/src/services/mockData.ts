// Author: mertaygn, cglrgrkn
import { DashboardSnapshot } from "@/types/domain";
import { STM_BOBIN_SAYISI } from "@/services/bobinGorunurlugu";

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
  // STM 1..7 + ESP slotu 8 — sayı TEK KAYNAKTAN (D5.42)
  coils: Array.from({ length: STM_BOBIN_SAYISI + 1 }, (_, index) => ({
    id: index + 1,
    connected: false,
    running: false,
    frequencyHz: 0,
    dutyCycle: 0,
    magneticMt: 0,
    objectTemp: 0,
    ambientTemp: 0,
    currentA: 0,
    stm32Driven: index < STM_BOBIN_SAYISI,   // Faz 4: bobin 1-7 STM32, slot 8 ESP (cihaz yok)
    // Sahte veride de GERÇEK topoloji: bobin 1-5 yalnız akım (ACS712), 6-7 yalnız
    // sıcaklık/alan (MLX). Böylece demo/geliştirme ekranı da kısa çizgileri gösterir.
    measuredFields: index < 5 ? ["currentA"] : index < 7 ? ["ambientTemp", "magneticMt", "objectTemp"] : [],
  })),
  sessions: []
};
