// Author: mertaygn, cglrgrkn
/**
 * useSessionControl — Seans başlatma/durdurma/izleme iş mantığı.
 *
 * /api/session/start ve /api/session/stop endpointlerini kullanır.
 * Kalan süreyi sayar (WS session_update mesajıyla senkronize edilir).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiPost, apiGet, platformAlert } from "@/services/apiClient";
import { emitToast } from "@/services/toastBridge";
import {
  performEmergencyStop,
  EMERGENCY_STOP_UNCONFIRMED_TITLE,
  EMERGENCY_STOP_UNCONFIRMED_BODY,
} from "@/services/emergencyStop";
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
  /** Acil durdurma komutu uçuşta mı — buton "Durduruluyor…" gösterebilsin (~21sn sürebilir). */
  stopping: boolean;
  /** SON hatayı SENKRON okur. `error` state'i, onu tetikleyen `await startSession(...)` satırının
   *  hemen ardından HENÜZ güncellenmemiş olur (aynı render'ın closure'ı okunur) → çağıranlar
   *  bir ÖNCEKİ hatayı, ilk denemede de `null` görüyordu. Ref her zaman günceldir. */
  lastError: () => string | null;
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
  /** Denetim 2. tur [1.1]: /session/stop, donanım STOP'u DOĞRULANAMAYAN bobinleri listeler
   *  (broker ölü / STM erişilemez). Üst-seviye status "success" kalır — seans kaydı kapandı. */
  hardware_stop_unconfirmed?: number[];
}

export function useSessionControl(): SessionControlResult {
  const [isActive, setIsActive] = useState(false);
  const [treatment, setTreatment] = useState<ActiveTreatment | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [remainingSec, setRemainingSec] = useState(0);
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // `error` state'inin SENKRON ikizi (stale-closure okumaları için — bkz. lastError).
  const lastErrorRef = useRef<string | null>(null);
  const setErrorBoth = useCallback((e: string | null) => {
    lastErrorRef.current = e;
    setError(e);
  }, []);

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
    setErrorBoth(null);
    // ⚠️ 2026-08-09: sunucunun REDDETME GEREKÇESİ. En kritik hâli, tıbbi kayıt DB'si açılamadığında
    // dönen 503'tür: eskiden ekranda yalnız "Seans başlatılamadı." yazıyordu ve veteriner, hasta
    // masadayken sebebi anlayamıyordu. Gerekçe varsa AYNEN gösterilir.
    let sunucuGerekce = "";
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
      }, null, { onHttpError: (_s, detail) => { sunucuGerekce = detail || ""; } });

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
      setErrorBoth(sunucuGerekce || "Seans başlatılamadı.");
      return false;
    } catch (e) {
      setErrorBoth(e instanceof Error ? e.message : "Hata oluştu.");
      return false;
    } finally {
      setLoading(false);
    }
  }, [startTimer, setErrorBoth]);

  const stopSession = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    try {
      // P1 audit 2026-06-28: apiPost ağ-hatası/non-2xx'te THROW ETMEZ → fallback(null) döner.
      // Eskiden yanıt kontrol edilmeden 'durduruldu' deniyordu → backend erişilemezken UI seansı
      // bitmiş gösterir ama STM'ye STOP ULAŞMAMIŞ olabilir (donanım çalışmaya devam). Yanıtı DOĞRULA.
      // ⚠️ GÜVENLİK SİNYALİ SÖZLEŞMESİ (2026-08-22): backend, donanım STOP'u doğrulanamayan
      // bobin varsa artık **409** döndürür — 2xx DIŞI olması KASITLIDIR. Sebebi sürüm kayması:
      // telefon eski sürümde kalabilir (Android'de kurulumu işletim sistemi sorar) ve eski
      // istemci tanımadığı bir yanıt ALANINI sessizce yutar, ama 2xx-dışı yanıtı YUTAMAZ.
      // Bu istemci 409'u AYIRT EDER: seans kaydı gerçekten kapandığı için UI'da seansı kapatır,
      // sonra spesifik bobin listesini gösterir. `silent: true` → apiClient'ın genel "Sunucu
      // Hatası" kutusu çıkmaz; aşağıdaki NET uyarı onun yerine geçer.
      let teyitsizHttp: number[] | null = null;
      const res = await apiPost<SessionActionResponse | null>("/session/stop", {}, null, {
        silent: true,
        onHttpError: (kod, _detail, govde) => {
          if (kod === 409) {
            const g = govde as { hardware_stop_unconfirmed?: unknown } | undefined;
            teyitsizHttp = Array.isArray(g?.hardware_stop_unconfirmed)
              ? (g!.hardware_stop_unconfirmed as number[])
              : [];
          }
        },
      });
      if (teyitsizHttp === null && (!res || res.status === "error")) {
        platformAlert(
          "Durdurma onaylanamadı",
          "Sunucuya ulaşılamadı — donanım HÂLÂ ÇALIŞIYOR olabilir. Lütfen ACİL DURDUR'a basın ya da cihazın fiziksel güç düğmesini kullanın."
        );
        return false;
      }
      // Denetim 2. tur [1.1] (2026-08-20): backend seans KAYDINI kapattı ama bazı bobinlerin
      // donanım STOP'u doğrulanamadı (broker ölü/yetim, STM erişilemez). Eskiden /session/stop
      // koşulsuz "success" döndüğü için yukarıdaki uyarı bu senaryoda HİÇ tetiklenemiyordu.
      // Seans UI'da kapanır (kayıt gerçekten kapandı — null/error'dan farkı bu) ama operatör
      // hangi bobinlerin teyitsiz kaldığını AÇIKÇA görür.
      // 409 yolundan geldiyse `res` null'dır — liste HTTP hata gövdesinden gelir. 200 yolunda
      // (eski backend ile konuşuluyorsa) eski alan hâlâ okunur → iki yön de çalışır.
      const teyitsiz: number[] =
        teyitsizHttp ?? (Array.isArray(res?.hardware_stop_unconfirmed) ? res.hardware_stop_unconfirmed : []);
      if (teyitsiz.length > 0) {
        platformAlert(
          "Durdurma onaylanamadı",
          `Bobin(ler) ${teyitsiz.join(", ")} için donanım STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR ` +
            "olabilirler. ACİL DURDUR'a basın ya da cihazın fiziksel güç düğmesini kullanın."
        );
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
    // GERİ BİLDİRİM (#17): en kötü durumda bridge 5sn + iki yedek istek 8+8sn = ~21sn sürebilir.
    // Eskiden bu sürenin TAMAMI boyunca ekranda HİÇBİR şey olmuyordu → operatör butonun çalışmadığını
    // sanıp tekrar tekrar basıyordu. Komut gider gitmez durumu bildir.
    setStopping(true);
    emitToast("Acil durdurma gönderiliyor…", "info");
    // Durdurma mantığı services/emergencyStop.ts'te (tek kaynak) — çıkış/profil-değiştirme kapıları
    // da aynı fonksiyonu çağırır, böylece davranış hiçbir yerde ayrışmaz.
    const { confirmed } = await performEmergencyStop();
    stopTimer();
    setIsActive(false);
    setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
    setElapsedSec(0);
    setRemainingSec(0);
    setStopping(false);
    if (!confirmed) {
      // Güvenlik: donanımın durduğu teyit edilemedi — web dahil HER platformda göster (Alert.alert web'de no-op).
      platformAlert(EMERGENCY_STOP_UNCONFIRMED_TITLE, EMERGENCY_STOP_UNCONFIRMED_BODY);
    } else {
      emitToast("Tüm bobinler durduruldu ✓", "success");
    }
  }, [stopTimer]);

  return {
    isActive,
    treatment,
    elapsedSec,
    remainingSec,
    loading,
    stopping,
    error,
    lastError: () => lastErrorRef.current,
    startSession,
    stopSession,
    emergencyStop,
  };
}
