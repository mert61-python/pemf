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
import { performEmergencyStop } from "@/services/emergencyStop";
import { kritikMetin } from "@/i18n/kritik";
import type { ActiveTreatment } from "@/types/domain";
import { useTranslation } from "react-i18next";

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
  /** Başlatma YA DA seans durdurma isteği uçuşta. ⚠️ D1.82 · Y47: YALNIZ başlatma/uygulama düğmelerini kilitler —
   *  hiçbir DURDURMA düğmesi buna (ya da başka bir isteğe) bağlanmaz. */
  loading: boolean;
  /** `/session/start` uçuşta (D1.82): Durdur bu sırada da basılabilir; başlatma yanıtından SONRA STOP yeniden gider. */
  starting: boolean;
  /** `/session/stop` uçuşta — yalnız ETİKET için ("⏳ Durduruluyor…"); düğmeyi kilitlemez. */
  sessionStopping: boolean;
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
  /** ⚠️ D1.66 (B-1.2): son seansın DB satır kimliği — seans BİTİNCE de korunur (gözlem notu bitişten SONRA yazılır).
   *  Not `/api/session/notes`'a bununla gider; sunucu YALNIZ o satıra yazar. Bilinmiyorsa null (eski sunucu). */
  dbSessionId: number | null;
  /** Y212 · S-D67.11: başka istemcide / AI Pro'da başlatılan seansı WS `activeTreatment`ten benimser (yeni ağ trafiği yok; mutabakat
   *  döngüsü `isActive` ile kurulur, backend seansı bitirince kartı kapatır). Durdur / ACİL DURDUR yolları AYNI. */
  benimse: (ws: ActiveTreatment) => void;
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
  /** D1.66: seansın DB satır kimliği (gözlem notu O satıra yazılsın). */
  db_session_id?: number | null;
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
  const { t } = useTranslation();
  const [isActive, setIsActive] = useState(false);
  const [treatment, setTreatment] = useState<ActiveTreatment | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [remainingSec, setRemainingSec] = useState(0);
  const [dbSessionId, setDbSessionId] = useState<number | null>(null);
  // ⚠️ D1.82 · Y47: başlatma ve durdurma yükü AYRI. Eskiden tek `loading` vardı ve Kontrol ekranının ana Durdur'u ile
  // seans kartının Durdur'u `disabled={loading}`du → `/session/start` askıdayken (≤ 8 sn) durdurma basılamıyordu.
  const [starting, setStarting] = useState(false);
  const [sessionStopping, setSessionStopping] = useState(false);
  const loading = starting || sessionStopping;
  // Başlatma uçuştayken durdurma istendi mi (ref: aynı render'daki basış da görülsün). Geç gelen START, durdurmadan
  // SONRA bobini başlatabilir (İG-5.3 sınıfı: istek backend'e STOP'tan sonra ulaşırsa nesil kapısı onu tanımaz) →
  // başlatma yanıtından sonra STOP YENİDEN gönderilir (STOP idempotent; gönderim yalnız ARTAR, Ö.4-Y8).
  const startUcustaRef = useRef(false);
  const startSonrasiDurdurRef = useRef(false);
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
      // D1.70 (Y5): toplam REF'ten okunur — seans ortası süre değişikliğini mutabakat günceller (kapanışta sabit DEĞİL).
      const remaining = Math.max(0, durationSecRef.current - elapsedRef.current);
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
        if (typeof sess.db_session_id === "number") setDbSessionId(sess.db_session_id); // D1.66
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

  // Y212 · S-D67.11 (sahip): başka istemcide / AI Pro'da başlatılan seansı BENİMSE — kart "Seans Bekleniyor" derken bobinler enerjili
  // kalmasın. Değerler WS `activeTreatment`ten (yeni istek yok); `isActive` mutabakat döngüsünü kurar.
  const benimse = useCallback((ws: ActiveTreatment) => {
    const totalSec = Math.max(0, Number(ws.durationSec) || 0);
    const elapsed = Math.max(0, Number(ws.elapsedSec) || 0);
    setIsActive(true);
    setTreatment({ ...ws, isActive: true });
    startTimer(totalSec, elapsed);
  }, [startTimer]);

  // Backend ile periyodik mutabakat: timer drift'ini (arka plan/yeniden bağlanma) düzeltir
  // ve seans backend'de bittiyse (süre dolması / başka istemci durdurması) UI'ı kapatır.
  useEffect(() => {
    if (!isActive) return;
    let cancelled = false;
    const reconcile = async () => {
      const sess = await apiGet<SessionActiveResponse | null>("/session/active", null, { silent: true }).catch(() => null);
      if (cancelled) return; // unmount sonrası setState'i önle
      if (!sess) return; // bağlantı yok — yerel timer devam etsin
      // Y212 · S-D67.11: benimsenen (WS'ten gelen) seansın DB satırı mutabakattan öğrenilir — gözlem notu o satıra yazılır (D1.66).
      if (sess.is_active && typeof sess.db_session_id === "number") setDbSessionId(sess.db_session_id);
      if (!sess.is_active) {
        stopTimer();
        setIsActive(false);
        setTreatment((prev) => (prev ? { ...prev, isActive: false } : null));
        return;
      }
      if (typeof sess.elapsed_sec === "number") {
        // ⚠️ D1.70 (sahip kararı Y5): seans ORTASINDA girilen süre KALAN süredir; backend bitişi taşır ve kalan süreyi
        // yeni bitişten verir. Toplam = geçen + kalan. Eskiden toplam başlangıçta sabitti → uzatmada sayaç ESKİ bitişte
        // 0'a inip süren seansı yerelde "bitti" sayıyordu (mutabakat da duruyordu), kısaltmada kalan yanlış görünüyordu.
        if (typeof sess.remaining_sec === "number" && durationSecRef.current > 0) {
          durationSecRef.current = sess.elapsed_sec + sess.remaining_sec;
        }
        const total = durationSecRef.current || (sess.duration_minutes ?? 0) * 60;
        elapsedRef.current = sess.elapsed_sec;
        setElapsedSec(sess.elapsed_sec);
        setRemainingSec(total > 0 ? Math.max(0, total - sess.elapsed_sec) : 0);
      }
    };
    reconcileRef.current = setInterval(reconcile, 2000);  // 5s→2s: acil-durdur/backend-stop UI senkronu daha hızlı
    return () => {
      cancelled = true;
      /* istanbul ignore if -- ULASILAMAZ: stopTimer aralığı sökümden ÖNCE temizler; bu dal girilmez */
      if (reconcileRef.current) {
        clearInterval(reconcileRef.current);
        reconcileRef.current = null;
      }
    };
  }, [isActive, stopTimer]);

  const stopSession = useCallback(async (): Promise<boolean> => {
    // D1.82: başlatma uçuştaysa geç gelen yanıttan sonra STOP yeniden gönderilsin (aşağıda startSession).
    if (startUcustaRef.current) startSonrasiDurdurRef.current = true;
    setSessionStopping(true);
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
        durdurma: true, // D3I-A1.3 · Ö.4-Y8: STOP düz-HTTP kapısına bağlanmaz
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
          t("kontrol.ekran.durdurmaOnaylanamadi"),
          t("seans.denetim.sunucuyaUlasilamadi")
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
          t("kontrol.ekran.durdurmaOnaylanamadi"),
          t("seans.denetim.stopDogrulanamadi", { liste: teyitsiz.join(", ") })
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
      setSessionStopping(false);
    }
  }, [stopTimer, t]);

  const startSession = useCallback(async (params: SessionStartParams): Promise<boolean> => {
    startUcustaRef.current = true;
    startSonrasiDurdurRef.current = false;
    setStarting(true);
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

      startUcustaRef.current = false;
      if (startSonrasiDurdurRef.current) {
        // ⚠️ D1.82: başlatma uçuştayken operatör DURDUR'a bastı. Yanıt ne olursa olsun (başarı, ret, zaman aşımı —
        // sunucu isteği yine işlemiş olabilir) STOP YENİDEN gider; seans açık GÖSTERİLMEZ. Son söz durdurmanındır.
        startSonrasiDurdurRef.current = false;
        await stopSession();
        setErrorBoth(t("seans.denetim.baslatmaGeriAlindi"));
        return false;
      }

      if (result?.status === "success" || result?.session) {
        // D1.66: seansın DB kimliği (yanıt `session.db_session_id`); yoksa null — eski kimlik TAŞINMAZ.
        const _db = (result?.session as { db_session_id?: unknown } | undefined)?.db_session_id;
        setDbSessionId(typeof _db === "number" ? _db : null);
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
      setErrorBoth(sunucuGerekce || t("kontrol.ekran.seansBaslatilamadi"));
      return false;
    } catch (e) {
      setErrorBoth(e instanceof Error ? e.message : t("seans.denetim.hataOlustu"));
      return false;
    } finally {
      startUcustaRef.current = false;
      setStarting(false);
    }
  }, [startTimer, setErrorBoth, stopSession, t]);

  const emergencyStop = useCallback(async (): Promise<void> => {
    // GERİ BİLDİRİM (#17): en kötü durumda bridge 5sn + iki yedek istek 8+8sn = ~21sn sürebilir.
    // Eskiden bu sürenin TAMAMI boyunca ekranda HİÇBİR şey olmuyordu → operatör butonun çalışmadığını
    // sanıp tekrar tekrar basıyordu. Komut gider gitmez durumu bildir.
    setStopping(true);
    emitToast(kritikMetin("guvenlik.acilDurdur.gonderiliyor"), "info");
    // Durdurma mantığı services/emergencyStop.ts'te (tek kaynak) — çıkış/profil-değiştirme kapıları
    // da aynı fonksiyonu çağırır, böylece davranış hiçbir yerde ayrışmaz.
    const { confirmed, kartReddetti } = await performEmergencyStop();
    stopTimer();
    setIsActive(false);
    setTreatment((prev) => prev ? { ...prev, isActive: false } : null);
    setElapsedSec(0);
    setRemainingSec(0);
    setStopping(false);
    if (!confirmed) {
      // Güvenlik: donanımın durduğu teyit edilemedi — web dahil HER platformda göster (Alert.alert web'de no-op).
      // TD3: kart STOP'u reddettiyse eylem metni (gücü kes / USB'yi çıkar).
      platformAlert(
        kartReddetti ? kritikMetin("guvenlik.acilDurdur.kartRedBaslik") : kritikMetin("guvenlik.acilDurdur.teyitsizBaslik"),
        kartReddetti ? kritikMetin("guvenlik.acilDurdur.kartRedGovde") : kritikMetin("guvenlik.acilDurdur.teyitsizGovde")
      );
    } else {
      emitToast(kritikMetin("guvenlik.acilDurdur.durduruldu"), "success");
    }
  }, [stopTimer]);

  return {
    isActive,
    treatment,
    elapsedSec,
    remainingSec,
    loading,
    starting,
    sessionStopping,
    stopping,
    error,
    lastError: () => lastErrorRef.current,
    startSession,
    stopSession,
    emergencyStop,
    dbSessionId,
    benimse,
  };
}
