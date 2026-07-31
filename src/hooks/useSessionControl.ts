/**
 * useSessionControl — Seans başlatma/durdurma/izleme iş mantığı.
 *
 * /api/session/start ve /api/session/stop endpointlerini kullanır.
 * Kalan süreyi sayar (WS session_update mesajıyla senkronize edilir).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiPost, apiGet, platformAlert } from "@/services/apiClient";
import type { ActiveTreatment } from "@/types/domain";

export interface SessionStartParams {
  patientId?: string;
  patientName?: string;
  mode: "Manuel" | "Otomatik" | "AI";
  targetCondition?: string;
  frequency: number;
  duty: number;
  intensity: number;
  phase?: number;
  durationMinutes: number;
  coilIds?: number[];
  operatorEmail?: string;  // klinik-içi sahiplik — seansı başlatan hekim
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

// Backend yanıt sözleşmeleri (audit B-10.1: apiPost/apiGet<any> yerine) — alanlar opsiyonel.
/** GET /api/session/active — aktif seans snapshot'ı. */
interface SessionActiveResponse {
  is_active?: boolean;
  mode?: string;
  frequency?: number;
  intensity?: number;
  duration_minutes?: number;
  elapsed_sec?: number;
  remaining_sec?: number;
}
/** POST /api/session/start|stop + /api/hardware/command ortak yanıt zarfı. */
interface SessionActionResponse {
  status?: string;
  session?: unknown;
  warning?: string;
}
/** POST /api/hardware/emergency_stop (bridge) yanıtı — donanım durdurma teyidi. */
interface EmergencyStopResponse {
  stmStopped?: boolean;
  mqttResults?: { mqtt?: string }[];
}

export function useSessionControl(): SessionControlResult {
  const [isActive, setIsActive] = useState(false);
  const [treatment, setTreatment] = useState<ActiveTreatment | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [remainingSec, setRemainingSec] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const durationSecRef = useRef(0);
  const elapsedRef = useRef(0); // backend mutabakatının güncelleyebilmesi için
  const reconcileRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // useCallback ile sabit referans — startSession/stopSession closure'u için gerekli
  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (reconcileRef.current) {
      clearInterval(reconcileRef.current);
      reconcileRef.current = null;
    }
  }, []);

  const startTimer = useCallback((totalSec: number, alreadyElapsed = 0) => {
    stopTimer();
    // KRİTİK fix: totalSec<=0 (süresiz/0-dk seans veya bozuk giriş) durumunda ilk tick
    // 'remaining=max(0,0-1)=0' olduğundan seansı YANLIŞLIKLA ~1sn'de bitirip UI'ı ÇALIŞAN tedaviye
    // KÖR bırakıyordu (isActive=false→reconcile durur; kart "Bekleniyor" der, bobinler enerjili).
    // Süresiz modda YALNIZ geçen süreyi say, OTOMATİK BİTİRME YOK — backend watchdog/operatör durdurur;
    // isActive=true kaldığından reconcile backend durunca UI'ı senkronlar.
    const indefinite = totalSec <= 0;
    durationSecRef.current = totalSec;
    elapsedRef.current = alreadyElapsed;
    setElapsedSec(elapsedRef.current);
    setRemainingSec(indefinite ? 0 : Math.max(0, totalSec - elapsedRef.current));
    timerRef.current = setInterval(() => {
      elapsedRef.current += 1;
      setElapsedSec(elapsedRef.current);
      if (indefinite) return; // süresiz: bitiş kontrolü YOK (kör kalma önlenir)
      const remaining = Math.max(0, totalSec - elapsedRef.current);
      setRemainingSec(remaining);
      if (remaining === 0) {
        stopTimer();
        setIsActive(false);
        setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
      }
    }, 1000);
  }, [stopTimer]);

  // Check for existing active session on mount
  useEffect(() => {
    // YÜKSEK fix: iptal-guard. Yavaş /session/active yanıtı unmount'tan SONRA çözülürse cleanup'ın
    // stopTimer'ı boşa çalışır, ardından startTimer YENİ (sahipsiz) bir interval kurar → unmount sonrası
    // setState + dakikalarca yaşayan yetim sayaç. cancelled bayrağı bunu önler.
    let cancelled = false;
    apiGet<SessionActiveResponse>("/session/active", {}, { silent: true }).then((sess) => {
      if (cancelled) return;
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
    return () => {
      cancelled = true;
      stopTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Backend ile periyodik mutabakat: timer drift'ini (arka plan/yeniden bağlanma) düzeltir
  // ve seans backend'de bittiyse (süre dolması / başka istemci durdurması) UI'ı kapatır.
  useEffect(() => {
    if (!isActive) return;
    let cancelled = false;
    const reconcile = async () => {
      const sess = await apiGet<SessionActiveResponse | null>("/session/active", null, { silent: true }).catch(() => null);
      if (cancelled) return; // unmount sonrası setState'i önle
      if (!sess) return; // bağlantı yok — yerel timer devam etsin
      if (!sess.is_active) {
        stopTimer();
        setIsActive(false);
        setTreatment((prev) => (prev ? { ...prev, isActive: false } : null));
        return;
      }
      if (typeof sess.elapsed_sec === "number") {
        const total = durationSecRef.current || (sess.duration_minutes ?? 0) * 60;
        elapsedRef.current = sess.elapsed_sec;
        setElapsedSec(sess.elapsed_sec);
        setRemainingSec(total > 0 ? Math.max(0, total - sess.elapsed_sec) : 0);
      }
    };
    reconcileRef.current = setInterval(reconcile, 2000);  // 5s→2s: acil-durdur/backend-stop UI senkronu daha hızlı
    return () => {
      cancelled = true;
      if (reconcileRef.current) {
        clearInterval(reconcileRef.current);
        reconcileRef.current = null;
      }
    };
  }, [isActive, stopTimer]);

  const startSession = useCallback(async (params: SessionStartParams): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiPost<SessionActionResponse | null>("/session/start", {
        patient_id: params.patientId ?? "",
        patient_name: params.patientName ?? "",
        mode: params.mode,
        target_condition: params.targetCondition ?? "",
        frequency: params.frequency,
        duty: params.duty,
        intensity: params.intensity,
        phase: params.phase ?? 0,
        duration_minutes: params.durationMinutes,
        coil_ids: params.coilIds ?? [],
        operator_email: params.operatorEmail ?? "",
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Hata oluştu.");
      return false;
    } finally {
      setLoading(false);
    }
  }, [startTimer]);

  const stopSession = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    try {
      // P1 audit 2026-06-28: apiPost ağ-hatası/non-2xx'te THROW ETMEZ → fallback(null) döner.
      // Eskiden yanıt kontrol edilmeden 'durduruldu' deniyordu → backend erişilemezken UI seansı
      // bitmiş gösterir ama STM'ye STOP ULAŞMAMIŞ olabilir (donanım çalışmaya devam). Yanıtı DOĞRULA.
      const res = await apiPost<SessionActionResponse | null>("/session/stop", {}, null);
      if (!res || res.status === "error") {
        platformAlert(
          "Durdurma onaylanamadı",
          "Sunucuya ulaşılamadı — donanım HÂLÂ ÇALIŞIYOR olabilir. Lütfen ACİL DURDUR'a basın ya da cihazın fiziksel güç düğmesini kullanın."
        );
        return false;
      }
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
  }, [stopTimer]);

  const emergencyStop = useCallback(async (): Promise<void> => {
    let confirmed = false;
    try {
      // Backend emergency stop hem STM32'ye hem MQTT/ESP'ye stop gönderir.
      const { serviceConfig } = require("@/services/config");
      // GÜVENLİK: ham fetch TIMEOUT'suzdu → yarı-açık tünelde (cihaz erişilir ama soket takılı)
      // ne resolve ne reject eder; catch fallback'i (/session/stop + stop_all_coils) ve
      // "DOĞRULANAMADI → fiziksel güç düğmesi" uyarısı HİÇ çalışmaz, buton sessizce asılır.
      // AbortController ile ~5sn sonra abort → deterministik olarak catch'e düşer.
      const _esCtrl = new AbortController();
      const _esTimer = setTimeout(() => _esCtrl.abort(), 5000);
      let response: Response;
      try {
        response = await fetch(`${serviceConfig.bridgeBaseUrl}/hardware/emergency_stop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: _esCtrl.signal,
        });
      } finally {
        clearTimeout(_esTimer);
      }
      if (!response.ok) throw new Error(`Emergency stop failed: ${response.status}`);
      const data = (await response.json().catch(() => null)) as EmergencyStopResponse | null;
      if (data) {
        const mqttOk = Array.isArray(data.mqttResults) && data.mqttResults.some((r) => r?.mqtt === "success");
        confirmed = Boolean(data.stmStopped) || mqttOk;
      }
    } catch {
      // Bridge'e erişilemezse API server üzerinden dene
      try {
        await apiPost<SessionActionResponse | null>("/session/stop", {}, null);
        const r = await apiPost<SessionActionResponse | null>("/hardware/command", { command: "stop_all_coils", params: {} }, null);
        confirmed = r?.status === "success";
      } catch { /* best effort */ }
    }
    stopTimer();
    setIsActive(false);
    setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
    setElapsedSec(0);
    setRemainingSec(0);
    if (!confirmed) {
      // Güvenlik: donanımın durduğu teyit edilemedi — web dahil HER platformda göster (Alert.alert web'de no-op).
      platformAlert(
        "⚠️ ACİL DURDURMA DOĞRULANAMADI",
        "Donanımın durduğu teyit edilemedi. Bobinler hâlâ çalışıyor olabilir — cihazı fiziksel güç düğmesinden kapatın."
      );
    }
  }, [stopTimer]);

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
