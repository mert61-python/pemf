/**
 * useSessionControl — Seans başlatma/durdurma/izleme iş mantığı.
 *
 * /api/session/start ve /api/session/stop endpointlerini kullanır.
 * Kalan süreyi sayar (WS session_update mesajıyla senkronize edilir).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiPost, apiGet } from "@/services/apiClient";
import type { ActiveTreatment } from "@/types/domain";

export interface SessionStartParams {
  patientId?: string;
  patientName?: string;
  mode: "Manuel" | "Otomatik" | "AI";
  targetCondition?: string;
  frequency: number;
  duty: number;
  intensity: number;
  durationMinutes: number;
  coilIds?: number[];
}

export interface SessionControlResult {
  isActive: boolean;
  treatment: ActiveTreatment | null;
  elapsedSec: number;
  remainingSec: number;
  loading: boolean;
  error: string | null;
  startSession: (params: SessionStartParams) => Promise<boolean>;
  stopSession: () => Promise<boolean>;
  emergencyStop: () => Promise<void>;
}

const DEFAULT_TREATMENT: ActiveTreatment = {
  mode: "Sistem Hazır",
  frequencyHz: 0,
  intensityMt: 0,
  remainingMin: 0,
  elapsedSec: 0,
  durationSec: 0,
  isActive: false,
};

export function useSessionControl(): SessionControlResult {
  const [isActive, setIsActive] = useState(false);
  const [treatment, setTreatment] = useState<ActiveTreatment | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [remainingSec, setRemainingSec] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const durationSecRef = useRef(0);

  // useCallback ile sabit referans — startSession/stopSession closure'u için gerekli
  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = (totalSec: number, alreadyElapsed = 0) => {
    stopTimer();
    durationSecRef.current = totalSec;
    let elapsed = alreadyElapsed;
    setElapsedSec(elapsed);
    setRemainingSec(Math.max(0, totalSec - elapsed));
    timerRef.current = setInterval(() => {
      elapsed += 1;
      const remaining = Math.max(0, totalSec - elapsed);
      setElapsedSec(elapsed);
      setRemainingSec(remaining);
      if (remaining === 0) {
        stopTimer();
        setIsActive(false);
        setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
      }
    }, 1000);
  };

  // Check for existing active session on mount
  useEffect(() => {
    apiGet<any>("/session/active", {}).then((sess) => {
      if (sess?.is_active) {
        setIsActive(true);
        const totalSec = (sess.duration_minutes ?? 0) * 60;
        const elapsed = sess.elapsed_sec ?? 0;
        setTreatment({
          mode: sess.mode ?? "Manuel",
          frequencyHz: sess.frequency ?? 0,
          intensityMt: sess.intensity ?? 0,
          remainingMin: Math.round((totalSec - elapsed) / 60),
          elapsedSec: elapsed,
          durationSec: totalSec,
          isActive: true,
        });
        startTimer(totalSec, elapsed);
      }
    });
    return stopTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startSession = useCallback(async (params: SessionStartParams): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiPost<any>("/session/start", {
        patient_id: params.patientId ?? "",
        patient_name: params.patientName ?? "",
        mode: params.mode,
        target_condition: params.targetCondition ?? "",
        frequency: params.frequency,
        duty: params.duty,
        intensity: params.intensity,
        duration_minutes: params.durationMinutes,
        coil_ids: params.coilIds ?? [],
      }, null);

      if (result?.status === "success" || result?.session) {
        const totalSec = params.durationMinutes * 60;
        setIsActive(true);
        setTreatment({
          mode: params.mode,
          frequencyHz: params.frequency,
          intensityMt: params.intensity,
          remainingMin: params.durationMinutes,
          elapsedSec: 0,
          durationSec: totalSec,
          isActive: true,
        });
        startTimer(totalSec);
        return true;
      }
      setError("Seans başlatılamadı.");
      return false;
    } catch (e: any) {
      setError(e?.message ?? "Hata oluştu.");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const stopSession = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    try {
      await apiPost<any>("/session/stop", {}, null);
      stopTimer();
      setIsActive(false);
      setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
      setElapsedSec(0);
      setRemainingSec(0);
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const emergencyStop = useCallback(async (): Promise<void> => {
    try {
      await apiPost<any>("/session/stop", {}, null);
      await apiPost<any>("/hardware/command", { command: "stop_all_coils", params: {} }, null);
    } catch {
      /* best effort */
    }
    stopTimer();
    setIsActive(false);
    setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
    setElapsedSec(0);
    setRemainingSec(0);
  }, []);

  return {
    isActive,
    treatment,
    elapsedSec,
    remainingSec,
    loading,
    error,
    startSession,
    stopSession,
    emergencyStop,
  };
}
