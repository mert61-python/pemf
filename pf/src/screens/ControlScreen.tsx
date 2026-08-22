// Author: mertaygn, cglrgrkn
/**
 * ControlScreen — Tam Tedavi Kontrol Ekranı
 *
 * Python unified_control_window.py'nin React karşılığı.
 * 3 sekme: Otomatik Mod | Manuel Mod | AI Modu
 */
import { useState, useCallback, useEffect, useRef } from "react";
import { useOperator } from "@/context/OperatorContext";
import {
  Text,
  View,
  StyleSheet,
  TouchableOpacity,
  TextInput,
} from "react-native";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import type { CoilStatus } from "@/types/domain";
import { useLiveData } from "@/context/LiveDataContext";
import { useSessionControl } from "@/hooks/useSessionControl";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { CoilParameterPanel } from "@/components/domain/CoilParameterPanel";
import { apiPost, platformAlert, platformConfirm } from "@/services/apiClient";
import { clampTherapyParams } from "@/services/therapyLimits";
import { useAppNav } from "@/context/AppNavContext";
import { useAuth } from "@/context/AuthContext";
import { AiProPanel } from "@/components/domain/AiProPanel";
import { EFieldBar } from "@/components/domain/EFieldBar";
import { PatientGate } from "@/components/domain/PatientGate";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";

// ─── Tab types ────────────────────────────────────────────────────────────────
type TabKey = "automatic" | "manual" | "ai" | "aipro";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "automatic", label: "Otomatik", icon: "🤖" },
  { key: "manual",    label: "Manuel",   icon: "🎛" },
  { key: "ai",        label: "AI Modu",  icon: "🧠" },
  { key: "aipro",     label: "AI Pro",   icon: "🎯" },
];

// ─── Target conditions ─────────────────────────────────────────────────────
const AUTO_TARGETS = [
  "Doku İyileşmesi", "Eklem Ağrısı", "Kas Spazmı",
  "Kırık İyileşmesi", "Enflamasyon Azaltma", "Sinir Rejenerasyonu",
  "Bağ Dokusu Tamiri", "Ödem Azaltma",
];

// ─── Component ────────────────────────────────────────────────────────────────
export function ControlScreen() {
  const { snapshot, telemetryStale } = useLiveData();
  const { selectedPatient } = useAppNav();
  const { session } = useAuth();
  const { operatorEmail } = useOperator();
  const {
    isActive, treatment, elapsedSec, remainingSec,
    // `error` state'i YERİNE `lastError()`: state, onu tetikleyen `await startSession(...)`
    // satırının hemen ardından bu render'ın closure'ında HENÜZ güncel değildi → uyarı kutusu
    // bir ÖNCEKİ hatayı (ilk denemede de null) gösteriyordu.
    loading, stopping, lastError, startSession, stopSession, emergencyStop,
  } = useSessionControl();

  const [activeTab, setActiveTab] = useState<TabKey>("manual");

  // ── Otomatik Mod state ─────────────────────────────────────────────────
  const [autoTarget, setAutoTarget] = useState(AUTO_TARGETS[0]);
  const [autoFreq, setAutoFreq] = useState("50");
  const [autoDuty, setAutoDuty] = useState("25");
  const [autoDuration, setAutoDuration] = useState("20");
  const [autoIntensity, setAutoIntensity] = useState("1.0");
  const [autoLoading, setAutoLoading] = useState(false);

  // ── Manuel Mod state ───────────────────────────────────────────────────
  const [masterFreq, setMasterFreq] = useState("100");
  const [masterDuty, setMasterDuty] = useState("25");
  const [masterPhase, setMasterPhase] = useState("0");
  const [masterDuration, setMasterDuration] = useState("20");
  const [selectedCoils, setSelectedCoils] = useState<Set<number>>(
    new Set([1, 2, 3, 4, 5, 6, 7, 8])
  );

  // ── AI Mod state ───────────────────────────────────────────────────────
  const [aiTarget, setAiTarget] = useState(AUTO_TARGETS[0]);
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<any>(null);

  // ─── Helpers ─────────────────────────────────────────────────────────────
  const toggleCoil = useCallback((id: number) => {
    setSelectedCoils((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }, []);

  const patientName = selectedPatient?.name || snapshot.patient?.name || "";
  const isStmConnected = snapshot.stm === "online";
  const isCoilConnected = useCallback(
    (coil: { id: number; connected?: boolean }) =>
      coil.id <= 5 ? isStmConnected : Boolean(coil.connected),
    [isStmConnected]
  );

  // Güvenlik: parametreleri aralığa çek, düzeltme olduysa kullanıcıyı uyar.
  const clampWithAlert = useCallback((input: Parameters<typeof clampTherapyParams>[0]) => {
    const { values, warnings } = clampTherapyParams(input);
    if (warnings.length) platformAlert("Parametre güvenliği", warnings.join("\n"));
    return values;
  }, []);

  // ORTA fix: süre girişini normalize et — NaN/boş/≤0 (ör. "-5" → parseInt=-5 TRUTHY, `||20`'yi ATLAR →
  // clampTherapyParams min=0'a çeker → süresiz-seans körlüğüne sızar) yerine 20dk varsayılan (backend ge=1).
  const parseDurationMin = (s: string): number => {
    const n = parseInt(s, 10);
    return Number.isFinite(n) && n >= 1 ? n : 20;
  };

  // Hedef seçilince literatür-tabanlı parametreleri backend'den çek (auto_preset).
  const applyAutoPreset = useCallback(async (target: string) => {
    setAutoTarget(target);
    setAutoLoading(true);
    try {
      const rec = await apiPost<any>("/hardware/auto_preset", { target_condition: target }, null);
      const p = rec?.parameters;
      if (p) {
        if (p.freq != null) setAutoFreq(String(p.freq));
        if (p.duty != null) setAutoDuty(String(p.duty));
        if (p.duration != null) setAutoDuration(String(Math.round(p.duration)));
        if (p.intensity != null) setAutoIntensity(String(p.intensity));
      }
    } catch {
      /* öneri alınamadı — kullanıcı elle ayarlar */
    } finally {
      setAutoLoading(false);
    }
  }, []);

  // ─── Session start handlers ───────────────────────────────────────────────
  // YÜKSEK fix: Seçili bobinlerden bağlı OLANLARı döndür (STM 1-5 isStmConnected + ESP 6-8 coil.connected);
  // hiç seçilmemiş/hiçbiri bağlı değilse uyarıp null döner. Manuel + Auto + AI AYNI filtreyi kullansın →
  // offline bobinin seansa girip "sahte aktif tedavi" göstermesi (ve "en az bir bobin" guard eksikliği) önlenir.
  const resolveEffectiveCoils = (): number[] | null => {
    if (selectedCoils.size === 0) {
      platformAlert("Uyarı", "En az bir bobin seçin.");
      return null;
    }
    const requested = Array.from(selectedCoils);
    // `?? []` — aynı dosyanın render'ı zaten bunu kullanıyordu; başlatma yolu guard'sızdı ve
    // `coils` alanı olmayan bir snapshot geldiğinde "Seans Başlat" ekranı çökertiyordu.
    const coilsById = new Map((snapshot.coils ?? []).map((c) => [c.id, c]));
    const effective = requested.filter((id) => isCoilConnected(coilsById.get(id) ?? { id }));
    if (effective.length === 0) {
      platformAlert("Bağlantı yok", "Seçili bobinler için aktif bağlantı yok (STM32/WiFi çevrimdışı).");
      return null;
    }
    if (effective.length < requested.length) {
      platformAlert("Bazı bobinler çevrimdışı", "Bağlı olmayan bobinler atlandı; yalnızca aktif bobinlere komut gönderiliyor.");
    }
    return effective;
  };

  /** Hasta seçili değilse onay iste. Eskiden hiç kontrol yoktu: seans ve seans-sonrası gözlem
   *  notu BOŞ hasta kimliğiyle kaydediliyor, tedavi geçmişinde hiçbir hayvana bağlanamayan
   *  kayıtlar oluşuyordu (klinik izlenebilirlik + KVKK açısından da sorunlu). Akışı bloklamıyoruz
   *  (acil/demo kullanım olabilir) ama artık BİLİNÇLİ bir karar. */
  // ⚠️ 2026-08-07 (SAHİP KARARI — SERT KAPI): eskiden onay sorup "Hastasız başlat"a izin
  // veriyordu. Artık VERMİYOR: hasta seçilmeden tedavi başlamaz. Gerekçe, aşağıdaki eski
  // notun kendi tespiti — sahipsiz seans "bu tedavi hangi hayvana uygulandı?" sorusunu
  // sonradan cevaplanamaz kılıyor. Ekran zaten PatientGate ile sarılı olduğundan buraya
  // normalde HİÇ düşülmez; bu SON SAVUNMA hattıdır (ör. seçim oturum ortasında düşerse).
  const requirePatient = async (): Promise<boolean> => {
    if (selectedPatient?.id || (patientName ?? "").trim()) return true;
    platformAlert(
      "Hasta seçilmedi",
      "Seansı başlatmadan önce yukarıdan hasta seçin. Seans, geçmişe hasta bilgisiyle birlikte kaydedilir."
    );
    return false;
  };

  /** Sayısal alan okuma. `parseFloat(x) || varsayılan` deseni kullanıcının yazdığı **0**'ı (geçerli
   *  bir değer: "duty 0", "faz 0") sessizce varsayılana çeviriyordu; geçersiz metin de fark
   *  edilmeden varsayılana dönüşüyor, operatör başka bir parametreyle tedavi başlattığını
   *  bilmiyordu. Boş alan → varsayılan (kasıtlı), geçersiz metin → `null` (çağıran uyarır). */
  const readNum = (raw: string, fallback: number): number | null => {
    const s = (raw ?? "").trim().replace(",", ".");   // TR klavye ondalık virgülü
    if (s === "") return fallback;
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : null;
  };
  /** Birden çok alanı oku; herhangi biri geçersizse uyar ve null dön. */
  const readParams = (
    fields: Record<string, [string, number]>
  ): Record<string, number> | null => {
    const out: Record<string, number> = {};
    for (const [key, [raw, dflt]] of Object.entries(fields)) {
      const v = readNum(raw, dflt);
      if (v === null) {
        platformAlert("Geçersiz değer", `"${raw}" sayı olarak okunamadı. Lütfen ${key} alanını kontrol edin.`);
        return null;
      }
      out[key] = v;
    }
    return out;
  };

  const handleStartAuto = async () => {
    if (!(await requirePatient())) return;
    const effective = resolveEffectiveCoils();
    if (!effective) return;
    const raw = readParams({
      freq: [autoFreq, 50], duty: [autoDuty, 25], intensity: [autoIntensity, 1.0],
    });
    if (!raw) return;
    const p = clampWithAlert({
      freq: raw.freq,
      duty: raw.duty,
      intensity: raw.intensity,
      duration: parseDurationMin(autoDuration),
    });
    const ok = await startSession({
      patientId: selectedPatient?.id,
      patientName,
      mode: "Otomatik",
      targetCondition: autoTarget,
      frequency: p.freq,
      duty: p.duty,
      intensity: p.intensity,  // Yoğunluk (mT) — ayrı alan
      durationMinutes: p.duration,
      coilIds: effective,
      operatorEmail: operatorEmail,
    });
    if (!ok) platformAlert("Hata", lastError() ?? "Seans başlatılamadı.");
  };

  // Manuel "Toplu Uygulama" → SEANS olarak başlat (ilerleme/timer/gözlem-notu/history +
  // 409 interlock kazanır). /session/start STM+ESP'yi faz dahil sürer.
  const handleStartManual = async () => {
    if (!(await requirePatient())) return;
    const effective = resolveEffectiveCoils();
    if (!effective) return;
    const raw = readParams({
      freq: [masterFreq, 100], duty: [masterDuty, 25], phase: [masterPhase, 0],
    });
    if (!raw) return;
    const p = clampWithAlert({
      freq: raw.freq,
      duty: raw.duty,
      phase: raw.phase,
      duration: parseDurationMin(masterDuration),
    });
    const ok = await startSession({
      patientId: selectedPatient?.id,
      patientName,
      mode: "Manuel",
      frequency: p.freq,
      duty: p.duty,
      intensity: 0, // Manuel'de hedef mT yok (parametre-temelli sürüş)
      phase: p.phase,
      durationMinutes: p.duration,
      coilIds: effective,
      operatorEmail: operatorEmail,
    });
    if (!ok) platformAlert("Hata", lastError() ?? "Manuel seans başlatılamadı (zaten aktif seans olabilir).");
  };

  // Manuel "Durdur": aktif seansı durdur (timer/not/history) + seçili bobinleri sıfırla.
  const handleStopManual = async () => {
    // ⚠️ IN-FLIGHT KAPISI (denetim 2026-08-17): AYNI durdurma turu iki kez BAŞLAMAZ.
    // Ağ kopukken tur 5 × 8 sn = ~40 sn sürüyordu ve buton `loading` yalnız `stopSession`
    // süresince true olduğu için ~8 sn'de yeniden basılabiliyordu → her basış 5 zaman aşımı daha
    // ekliyor, istemci ~48 sn meşgul kalıyordu.
    // ⚠️ REF, STATE DEĞİL: iki hızlı basış aynı React batch'inde state'i hâlâ `false` görür.
    // ⚠️ YENİ BASIŞ ATLANIR, uçuştaki tur İPTAL EDİLMEZ: abort komutu geri almaz, yalnız #74
    // teyidini yok eder ve durdurmayı sıfırdan başlatıp GECİKTİRİR.
    // ⚠️ BUTON DEVRE DIŞI BIRAKILMIYOR (sahip kararı): bir durdurma kontrolü kilitlenmez ve
    // ACİL DURDUR her zaman erişilebilir kalır.
    if (stopRoundRef.current) return;
    stopRoundRef.current = true;
    setStopRound(true);
    try {
    if (isActive) await stopSession().catch(() => {});
    // DURDURULACAK KÜME: "o an SEÇİLİ olanlar" DEĞİL, "gerçekten ÇALIŞANLAR + seçili olanlar".
    // Kullanıcı bir bobini başlattıktan sonra seçimden çıkarırsa (ör. başka bobinlere geçmek için),
    // "Durdur" o bobine hiç komut göndermiyordu → hayvanın üzerinde sessizce enerjili kalıyordu.
    // Çalışmayan bobine STOP göndermek idempotent ve zararsızdır; eksik göndermek değildir.
    const runningIds = (snapshot.coils ?? []).filter((c) => c?.running).map((c) => c.id);
    const targets = Array.from(new Set<number>([...Array.from(selectedCoils), ...runningIds]));
    const stmCoils = targets.filter((id) => id <= 5);
    const espCoils = targets.filter((id) => id >= 6);
    // #74: durdurma yanıtlarını DOĞRULA — apiPost hata/timeout'ta null döner (throw etmez); eskiden
    // yanıt yutuluyordu → STOP düşse bile kullanıcı bobinin durduğunu sanıyordu (per-coil panelle tutarsız).
    // ⚠️ PARALEL (denetim 2026-08-17): batch + ESP istekleri ESKİDEN seri `await` idi, yani
    // 4 istek 4 × 8 sn = 32 sn sürüyordu. Artık TOPLAM 8 sn.
    // Backend tarafı güvenli: `_mqtt_publish` çağrı başına benzersiz `client_id` kullanıyor
    // (sabit client_id KASITLI OLARAK yasak) ve `_emergency_stop_all` zaten aynı konulara
    // eşzamanlı publish yapıyor. `/session/stop` BİLEREK SERİ kaldı: donanıma dokunmadan önce
    // dakika-ortalamalarını yazıyor; bobin koşuları eşzamanlı kapatılırsa o kısmi dakika
    // sensör-özetinden düşer.
    // `Promise.all` reject ETMEZ: `apiPost` throw etmiyor, hata/timeout'ta null dönüyor.
    const istekler: Promise<{ status?: string; results?: ({ status?: string } | null)[] } | null>[] = [];
    if (stmCoils.length > 0) {
      istekler.push(
        apiPost<{ status?: string } | null>("/coil/batch", {
          coil_ids: stmCoils, freq: 0, duty: 0, phase: 0, duration: 0, start: false,
        }, null),
      );
    }
    for (const coilId of espCoils) {
      istekler.push(
        apiPost<{ status?: string } | null>(`/coil/${coilId}/control`, {
          freq: 0, duty: 0, phase: 0, duration: 0, start: false,
        }, null),
      );
    }
    const sonuclar = await Promise.all(istekler);
    // Denetim 2. tur [1.1] (2026-08-20): "hata değil" ≠ "teyit". Backend, publish broker'a
    // ulaşamayınca HTTP 200 + {status:"mqtt_unavailable"} döner (tek bobin) ve /coil/batch
    // ÜST-SEVİYEDE HEP "success" deyip satır-başı sonuçları results[] içinde taşır
    // (stm_unavailable/mqtt_unavailable/invalid). Eski yüklem (`status !== "error"`) ikisini de
    // teyit sayıyordu → broker ölüyken STOP hiçbir bobine ulaşmamışken aşağıdaki uyarı HİÇ
    // çıkmıyordu. Teyit yalnız AÇIK "success"tir; batch'te satırlar da tek tek sayılır.
    const satirOnaylandi = (r: { status?: string } | null | undefined): boolean =>
      !!r && r.status === "success";
    const allOk = sonuclar.every((r) => {
      if (!satirOnaylandi(r)) return false;
      const satirlar = r?.results;
      return !Array.isArray(satirlar) || satirlar.every(satirOnaylandi);
    });
    if (!allOk && istekler.length > 0) {
      platformAlert(
        "Durdurma onaylanamadı",
        "Bir veya daha fazla bobinin durduğu teyit edilemedi — bobinler HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın.",
      );
    }
    } finally {
      stopRoundRef.current = false;
      setStopRound(false);
    }
  };

  const handleAiAnalyze = async () => {
    setAiAnalyzing(true);
    setAiResult(null);
    try {
      // apiPost ASLA throw etmez: hata/timeout'ta fallback döner. Bu yüzden fallback olarak
      // bir sentinel hata nesnesi veriyoruz (null değil) → başarısızlıkta da kart görünür.
      // silent:true → apiClient'ın jenerik pop-up'ı yerine aiResult.error kartını gösteriyoruz.
      // (AI Pro biofeedback CPU'yu doyurup isteği yavaşlatsa/başarısız etse bile net geri bildirim.)
      const rec = await apiPost<any>(
        "/hardware/auto_preset",
        { target_condition: aiTarget },
        { error: "AI analizi başarısız — sunucuya ulaşılamadı veya zaman aşımı (AI Pro çalışıyorsa tekrar deneyin)." },
        { silent: true },
      );
      if (rec?.parameters) {
        // AI sekmesindeki analiz, GÖRÜNMEYEN "Otomatik" sekmesinin frekans/duty/süre alanlarını
        // SESSİZCE üzerine yazıyordu: kullanıcı Otomatik sekmesine elle girdiği değerleri kaybediyor,
        // sonra oradan "Seans Başlat"a bastığında beklemediği parametrelerle tedavi başlıyordu.
        // AI sonucu artık YALNIZ kendi kartında durur; Otomatik alanlarına dokunulmaz.
        setAiResult(rec);
      } else {
        // Boş/parametresiz yanıt da sessiz kalmasın → net uyarı göster.
        setAiResult(rec?.error ? rec : { error: "AI analizi sonuç döndürmedi. Lütfen tekrar deneyin." });
      }
    } catch {
      setAiResult({ error: "AI analizi başarısız" });
    } finally {
      setAiAnalyzing(false);
    }
  };

  const handleStartAi = async () => {
    if (!aiResult?.parameters) {
      platformAlert("Uyarı", "Önce AI analizi yapın.");
      return;
    }
    if (!(await requirePatient())) return;
    const effective = resolveEffectiveCoils();
    if (!effective) return;
    const src = aiResult.parameters;
    const p = clampWithAlert({
      freq: src.freq ?? 50,
      duty: src.duty ?? 25,
      // ORTA fix: AI-önerilen intensity'yi kullan; GÖRÜNMEYEN Otomatik-sekme autoIntensity'sini DEĞİL
      // (AI sekmesinde yoğunluk alanı yok → kullanıcı görmeden başka sekmenin değeriyle başlıyordu).
      intensity: src.intensity ?? 1.0,
      duration: Math.round(src.duration ?? 20),
    });
    const ok = await startSession({
      patientId: selectedPatient?.id,
      patientName,
      mode: "AI",
      targetCondition: aiTarget,
      frequency: p.freq,
      duty: p.duty,
      intensity: p.intensity,
      durationMinutes: p.duration,
      coilIds: effective,
      operatorEmail: operatorEmail,
    });
    if (!ok) platformAlert("Hata", lastError() ?? "Seans başlatılamadı.");
  };

  // ── Seans-sonrası gözlem notu prompt'u (PyQt observation-notes) ──
  type ObsSess = { patientName?: string; mode?: string; frequency?: number; intensity?: number; durationMinutes?: number; obsKey?: number };
  const [obsSession, setObsSession] = useState<ObsSess | null>(null);
  // Durdurma turu KAPISI. Ref senkron (iki hızlı basış aynı batch'te state'i görmez); state
  // YALNIZ etiket için. ⚠️ Butonun `disabled`ına EKLENMEZ (sahip kararı: durdurma kontrolü
  // kilitlenmez) — kullanıcı sessizce yutulan bir dokunuş yerine "⏳ Durduruluyor…" görür.
  const stopRoundRef = useRef(false);
  const [stopRound, setStopRound] = useState(false);
  const lastSessionRef = useRef<ObsSess | null>(null);
  const prevActiveRef = useRef(isActive);

  // Denetim 2. tur [4.1]: her seansa (isActive YÜKSELEN kenarı) benzersiz obsKey — modal'ın
  // sıfırlama anahtarı; aynı isimli iki hastada A'nın notu B'ye bulaşmasın (modal sözleşmesi
  // ObservationNotesModal'da). Sayaç ref'te: aynı seansın treatment tick'leri anahtarı DEĞİŞTİRMEZ.
  const seansSayacRef = useRef(0);
  const sayacOncekiAktifRef = useRef(false);
  useEffect(() => {
    if (isActive && !sayacOncekiAktifRef.current) seansSayacRef.current += 1;
    sayacOncekiAktifRef.current = isActive;
    if (isActive && treatment) {
      lastSessionRef.current = {
        obsKey: seansSayacRef.current,
        patientName,
        mode: treatment.mode,
        frequency: treatment.frequencyHz,
        intensity: treatment.intensityMt,
        durationMinutes: Math.round((treatment.durationSec ?? 0) / 60),
      };
    }
  }, [isActive, treatment, patientName]);

  useEffect(() => {
    if (prevActiveRef.current && !isActive && lastSessionRef.current) {
      setObsSession(lastSessionRef.current);
    }
    prevActiveRef.current = isActive;
  }, [isActive]);

  // ─── Render ───────────────────────────────────────────────────────────────
  const coils = snapshot.coils ?? [];
  const runningCount = coils.filter((c) => c?.running).length;
  /** Seans bayrağından BAĞIMSIZ donanım durumu (bkz. yukarıdaki uyarı bandı). */
  const hardwareRunningOutOfSession = runningCount > 0;

  return (
    <View style={styles.container}>
      {/* HASTA KAPISI — `soft` (2026-08-07): seçim kartı üstte durur ama EKRAN GİZLENMEZ.
          ⚠️ Sert kapı burada TEHLİKELİ olurdu: hasta seçili değilken ACİL DURDUR butonu da
          gizlenir, bobinler çalışırken operatör onlara ULAŞAMAZDI. Seansı asıl engelleyen
          şey başlatma yolundaki `requirePatient` sert kontrolüdür. */}
      <PatientGate soft>
      {/* ── Active Session Progress ────────────────────────────── */}
      {/* DONANIM UYARISI: kart yalnız KENDİ seans state'ine (useSessionControl) bakıyordu. AI Pro,
          AI-Auto, fiziksel kontrol veya başka bir istemci bobinleri enerjileyebilir ama session_*
          yayınlamaz → `isActive` false kalır ve ekran "Seans Bekleniyor" derken hayvanın üzerinde
          bobinler çalışıyor olabilir. DashboardScreen'de bu koruma vardı, burada yoktu. */}
      {!isActive && hardwareRunningOutOfSession && (
        <View style={styles.hwWarnBanner}>
          <Text style={styles.hwWarnText}>
            ⚠️ DONANIM ÇALIŞIYOR — {runningCount} bobin enerjili, seans bağlamı dışında.
            Aşağıdaki ACİL DURDUR ile durdurabilirsiniz.
          </Text>
        </View>
      )}
      <SessionProgressCard
        isActive={isActive}
        mode={treatment?.mode ?? "Sistem Hazır"}
        elapsedSec={elapsedSec}
        remainingSec={remainingSec}
        durationSec={treatment?.durationSec ?? 0}
        frequencyHz={treatment?.frequencyHz ?? 0}
        intensityMt={treatment?.intensityMt ?? 0}
        onStop={stopSession}
        onEmergencyStop={emergencyStop}
        loading={loading}
        stopping={stopping}
        stale={isActive && telemetryStale}
      />

      {/* CANLI E-ALANI (2026-08-06): yalnız analiz bağlamı + aktif seans varken görünür;
          aksi halde bileşen kendini render ETMEZ (bkz. EFieldBar). */}
      <EFieldBar />

      {/* ── Tab bar ───────────────────────────────────────────── */}
      <View style={styles.tabBar}>
        {TABS.map((tab) => (
          <TouchableOpacity
            key={tab.key}
            style={[styles.tab, activeTab === tab.key && styles.tabActive]}
            onPress={() => setActiveTab(tab.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: activeTab === tab.key }}
            accessibilityLabel={tab.label}
          >
            <Text style={styles.tabIcon}>{tab.icon}</Text>
            <Text style={[styles.tabLabel, activeTab === tab.key && styles.tabLabelActive]} numberOfLines={1} adjustsFontSizeToFit>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── TAB: Otomatik ─────────────────────────────────────── */}
      {activeTab === "automatic" && (
        <View style={styles.section}>
          <SectionTitle text="Otomatik Mod — Hedefe Göre Protokol" />
          <Text style={styles.hint}>
            Hedef durumu seçin, sistem literatür tabanlı parametreleri otomatik ayarlar.
          </Text>

          <FormLabel text="Seans Hedefi" />
          <View style={styles.targetGrid}>
            {AUTO_TARGETS.map((t) => (
              <TouchableOpacity
                key={t}
                style={[styles.targetChip, autoTarget === t && styles.targetChipActive]}
                onPress={() => applyAutoPreset(t)}
              >
                <Text style={[styles.targetChipText, autoTarget === t && styles.targetChipTextActive]}>
                  {t}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={styles.paramRow}>
            <ParamField label="Frekans (Hz)" value={autoFreq} onChangeText={setAutoFreq} />
            <ParamField label="Duty (%)" value={autoDuty} onChangeText={setAutoDuty} />
            {/* ⚠️ DENETİM 2026-08-09 (Tier 2): bu değer CİHAZA GÖNDERİLMEZ. STM binary paketi
                (duty/phase/freq/duration) ve ESP MQTT komutu (freq/duty/phase/duration) mT alanı
                TAŞIMAZ — girilen sayı yalnız kayda yazılır. Etiket bunu söylemezse operatör
                yoğunluğu ayarladığını sanır ve gerçek doz beklediğinden farklı olur.
                Gerçek çözüm firmware'dedir (paketi genişlet + osiloskopla doğrula). */}
            <ParamField label="Yoğunluk (mT, yalnız kayıt)" value={autoIntensity}
              onChangeText={setAutoIntensity} />
            <ParamField label="Süre (dk)" value={autoDuration} onChangeText={setAutoDuration} />
          </View>
          {autoLoading && <Text style={styles.hint}>Literatür önerisi alınıyor…</Text>}

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} />

          <StartButton
            label="🤖 Otomatik Seansı Başlat"
            onPress={handleStartAuto}
            disabled={isActive || loading}
          />
        </View>
      )}

      {/* ── TAB: Manuel ───────────────────────────────────────── */}
      {activeTab === "manual" && (
        <View style={styles.section}>
          <SectionTitle text="Manuel Mod — Bobin Bazlı Kontrol" />

          {/* Master controls */}
          <View style={styles.masterCard}>
            <Text style={styles.masterTitle}>📡 Toplu Uygulama</Text>
            <View style={styles.paramRow}>
              <ParamField label="Frekans (Hz)" value={masterFreq} onChangeText={setMasterFreq} />
              <ParamField label="Duty (%)" value={masterDuty} onChangeText={setMasterDuty} />
              <ParamField label="Faz (°)" value={masterPhase} onChangeText={setMasterPhase} />
              <ParamField label="Süre (dk)" value={masterDuration} onChangeText={setMasterDuration} />
            </View>
            <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} />
            <View style={styles.manualBtnRow}>
              <View style={{ flex: 1 }}>
                <StartButton
                  label="▶ Başlat"
                  onPress={handleStartManual}
                  disabled={isActive || loading}
                />
              </View>
              <View style={{ flex: 1 }}>
                {/* ⚠️ `disabled` DEĞİŞMEDİ: durdurma kontrolü kilitlenmez (sahip kararı).
                    Etiket, sessizce yutulan dokunuş yerine geri bildirim verir —
                    `SessionProgressCard`'daki emsalin aynısı. */}
                <StartButton
                  label={stopRound ? "⏳ Durduruluyor…" : "⏹ Durdur"}
                  onPress={handleStopManual}
                  disabled={loading}
                  color="#ef4444"
                />
              </View>
            </View>
          </View>

          {/* STM32 Bobinler (1-5) */}
          <Text style={styles.subTitle}>🔌 STM32 Bobinler (1–5)</Text>
          <ResponsiveGrid minItemWidth={320}>
            {coils.filter(c => c.id <= 5).map((coil) => (
              <CoilParameterPanel
                key={coil.id}
                coilId={coil.id}
                connected={isCoilConnected(coil)}
                running={coil.running}
                objectTemp={coil.objectTemp}
                frequencyHz={coil.frequencyHz}
                dutyCycle={coil.dutyCycle}
                magneticMt={coil.magneticMt}
                currentA={coil.currentA}
                defaultFreq={parseFloat(masterFreq) || 100}
                defaultDuty={parseFloat(masterDuty) || 25}
                defaultPhase={parseFloat(masterPhase) || 0}
                defaultDuration={parseDurationMin(masterDuration)}
                stm32Driven={true}
                stmConnected={isStmConnected}
                disabled={isActive}
              />
            ))}
          </ResponsiveGrid>

          {/* ESP Bobinler (6-8) */}
          <Text style={styles.subTitle}>📶 WiFi ESP Bobinler (6–8)</Text>
          <ResponsiveGrid minItemWidth={320}>
            {coils.filter(c => c.id >= 6).map((coil) => (
              <CoilParameterPanel
                key={coil.id}
                coilId={coil.id}
                connected={coil.connected}
                running={coil.running}
                objectTemp={coil.objectTemp}
                frequencyHz={coil.frequencyHz}
                dutyCycle={coil.dutyCycle}
                magneticMt={coil.magneticMt}
                currentA={coil.currentA}
                defaultFreq={parseFloat(masterFreq) || 50}
                defaultDuty={parseFloat(masterDuty) || 25}
                defaultPhase={parseFloat(masterPhase) || 0}
                defaultDuration={parseDurationMin(masterDuration)}
                stm32Driven={false}
                stmConnected={false}
                disabled={isActive}
              />
            ))}
          </ResponsiveGrid>
        </View>
      )}

      {/* ── TAB: AI ───────────────────────────────────────────── */}
      {activeTab === "ai" && (
        <View style={styles.section}>
          <SectionTitle text="AI Modu — Yapay Zeka Destekli Seans" />
          <Text style={styles.hint}>
            AI, hasta durumuna göre optimal frekans, duty ve süre parametrelerini önerir.
          </Text>

          <FormLabel text="Hedef Durum" />
          <View style={styles.targetGrid}>
            {AUTO_TARGETS.map((t) => (
              <TouchableOpacity
                key={t}
                style={[styles.targetChip, aiTarget === t && styles.targetChipActive]}
                onPress={() => setAiTarget(t)}
              >
                <Text style={[styles.targetChipText, aiTarget === t && styles.targetChipTextActive]}>
                  {t}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity
            style={[styles.btnAnalyze, aiAnalyzing && { opacity: 0.5 }]}
            onPress={handleAiAnalyze}
            disabled={aiAnalyzing}
          >
            <Text style={styles.btnAnalyzeText}>
              {aiAnalyzing ? "🧠 Analiz Ediliyor..." : "🧠 AI Analizi Başlat"}
            </Text>
          </TouchableOpacity>

          {aiResult && (
            <View style={styles.aiResultCard}>
              {aiResult.error ? (
                <Text style={styles.aiError}>{aiResult.error}</Text>
              ) : (
                <>
                  <Text style={styles.aiResultTitle}>✅ AI Önerisi</Text>
                  <View style={styles.paramRow}>
                    <StatChip label="Frekans" value={`${aiResult.parameters?.freq ?? "—"} Hz`} />
                    <StatChip label="Duty" value={`${aiResult.parameters?.duty ?? "—"}%`} />
                    <StatChip label="Süre" value={`${Math.round(aiResult.parameters?.duration ?? 0)} dk`} />
                  </View>
                  <Text style={styles.aiSource}>
                    Kaynak: {aiResult.parameters?.source ?? "Literatür"}
                  </Text>
                </>
              )}
            </View>
          )}

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} />

          <StartButton
            label="🧠 AI Seansını Başlat"
            onPress={handleStartAi}
            disabled={isActive || loading || !aiResult?.parameters}
            color="#7c3aed"
          />
        </View>
      )}

      {/* ── TAB: AI Pro ───────────────────────────────────────── */}
      {activeTab === "aipro" && (
        <View style={styles.section}>
          <SectionTitle text="AI Pro — Kamera Kapalı-Döngü" />
          <AiProPanel patientName={patientName} />
        </View>
      )}

      {/* ── Emergency Stop (always visible) ──────────────────── */}
      <TouchableOpacity style={styles.emergencyBtn} onPress={emergencyStop}
        accessibilityRole="button"
        accessibilityLabel="Tüm bobinleri acil durdur"
        accessibilityHint="Tüm bobinleri anında durdurur ve aktif seansı sonlandırır">
        <Text style={styles.emergencyBtnText} numberOfLines={2} adjustsFontSizeToFit>🚨 TÜM BOBİNLERİ ACİL DURDUR</Text>
      </TouchableOpacity>

      {/* Gözlem notu modalı seans BİTİNCE otomatik açılır ve tam ekranı kaplar → o sırada donanım
          hâlâ enerjiliyse (yerel sayaç bitti ama backend/bobin durmadıysa) ACİL DURDUR'a erişimi
          kapatıyordu. Bobin çalışırken modalı AÇMA; önce durdurma erişimi kalsın, not sonra alınır. */}
      <ObservationNotesModal
        visible={obsSession !== null && !hardwareRunningOutOfSession}
        session={obsSession}
        onClose={() => setObsSession(null)}
      />
      </PatientGate>
    </View>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function SectionTitle({ text }: { text: string }) {
  return <Text style={styles.sectionTitle}>{text}</Text>;
}

function FormLabel({ text }: { text: string }) {
  return <Text style={styles.formLabel}>{text}</Text>;
}

function ParamField({
  label, value, onChangeText,
}: {
  label: string; value: string; onChangeText: (v: string) => void;
}) {
  return (
    <View style={styles.paramField}>
      <Text style={styles.paramFieldLabel}>{label}</Text>
      {/* TR klavyede ondalık ayırıcı VİRGÜLDÜR. `parseFloat("1,5")` → 1 döndüğü için "1,5 mT"
          yazan operatör sessizce 1 mT ile seans başlatıyordu. Girişte virgülü noktaya çevir
          (ekranda da düzeltilmiş görünür → operatör ne gönderdiğini görür).
          `keyboardType="decimal-pad"`: iOS'ta "numeric" ondalık tuşu göstermiyordu. */}
      <TextInput
        style={styles.paramFieldInput}
        value={value}
        onChangeText={(t) => onChangeText(t.replace(",", "."))}
        keyboardType="decimal-pad"
        selectTextOnFocus
        accessibilityLabel={label}
      />
    </View>
  );
}

function CoilSelector({
  coils, selected, onToggle, stmConnected,
}: {
  coils: CoilStatus[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  stmConnected: boolean;
}) {
  return (
    <View style={styles.coilSelector}>
      <Text style={styles.formLabel}>Bobin Seçimi</Text>
      <View style={styles.coilSelectorGrid}>
        {(coils.length > 0 ? coils : Array.from({ length: 8 }, (_, i) => ({ id: i + 1, connected: false }))).map((c) => {
          const connected = c.id <= 5 ? stmConnected : Boolean(c.connected);
          return (
            <TouchableOpacity
              key={c.id}
              style={[
                styles.coilSelectorBtn,
                selected.has(c.id) && styles.coilSelectorBtnActive,
                !connected && styles.coilSelectorBtnOffline,
              ]}
              onPress={() => onToggle(c.id)}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              accessibilityRole="button"
              accessibilityState={{ selected: selected.has(c.id) }}
              accessibilityLabel={`Bobin ${c.id}, ${selected.has(c.id) ? "seçili" : "seçili değil"}, ${connected ? "çevrimiçi" : "çevrimdışı"}`}
            >
              <Text style={[styles.coilSelectorText, selected.has(c.id) && styles.coilSelectorTextActive]}>
                {c.id}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

function StartButton({
  label, onPress, disabled, color = "#22c55e",
}: {
  label: string; onPress: () => void; disabled: boolean; color?: string;
}) {
  return (
    <TouchableOpacity
      style={[styles.startBtn, { backgroundColor: color }, disabled && styles.startBtnDisabled]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={styles.startBtnText} numberOfLines={2}>{label}</Text>
    </TouchableOpacity>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.statChip}>
      <Text style={styles.statChipLabel}>{label}</Text>
      <Text style={styles.statChipValue}>{value}</Text>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    padding: spacing.md,
    gap: spacing.md,
    paddingBottom: spacing.xxl,
    width: "100%",
    maxWidth: rs(1100),
    alignSelf: "center",
  },
  tabBar: {
    flexDirection: "row",
    backgroundColor: "#0f172a",
    borderRadius: 12,
    padding: 4,
    gap: 4,
  },
  tab: {
    flex: 1,
    alignItems: "center",
    padding: spacing.sm,
    borderRadius: 10,
    gap: 2,
  },
  tabActive: { backgroundColor: "#1e3a5f" },
  tabIcon: { fontSize: rf(18) },
  tabLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
  tabLabelActive: { color: colors.primary, fontWeight: "700" },

  section: { gap: spacing.md },
  sectionTitle: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "700",
  },
  subTitle: {
    color: colors.textMuted,
    fontSize: typography.body,
    fontWeight: "600",
    marginTop: spacing.xs,
  },
  hint: {
    color: colors.textMuted,
    fontSize: typography.small,
    lineHeight: rf(20),
  },
  formLabel: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "700",
    marginBottom: spacing.xs,
  },
  targetGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  targetChip: {
    backgroundColor: "#1e293b",
    borderRadius: 20,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderWidth: 1,
    borderColor: "#334155",
  },
  targetChipActive: {
    backgroundColor: "#1d4ed8",
    borderColor: "#3b82f6",
  },
  targetChipText: { color: colors.textMuted, fontSize: typography.small },
  targetChipTextActive: { color: "#fff", fontWeight: "700" },

  paramRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  paramField: { flex: 1, minWidth: rs(140) },
  paramFieldLabel: { color: colors.textMuted, fontSize: rf(11), fontWeight: "600", marginBottom: 4 },
  paramFieldInput: {
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    borderWidth: 1,
    borderColor: "#334155",
    textAlign: "center",
  },

  masterCard: {
    backgroundColor: "#0f172a",
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: "#1e3a5f",
    gap: spacing.md,
  },
  masterTitle: { color: colors.text, fontWeight: "700", fontSize: typography.body },

  coilGrid: { gap: spacing.sm },

  coilSelector: { gap: spacing.xs },
  coilSelectorGrid: { flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" },
  coilSelectorBtn: {
    width: rs(40),
    height: rs(40),
    borderRadius: 10,
    backgroundColor: "#1e293b",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#334155",
  },
  coilSelectorBtnActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  coilSelectorBtnOffline: { opacity: 0.4 },
  coilSelectorText: { color: colors.textMuted, fontWeight: "700" },
  coilSelectorTextActive: { color: "#fff" },

  startBtn: {
    borderRadius: 12,
    padding: spacing.md,
    alignItems: "center",
    marginTop: spacing.xs,
  },
  startBtnDisabled: { opacity: 0.4 },
  manualBtnRow: { flexDirection: "row", gap: spacing.sm },
  startBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.body, textAlign: "center", alignSelf: "stretch" },

  btnAnalyze: {
    backgroundColor: "#6d28d9",
    borderRadius: 12,
    padding: spacing.md,
    alignItems: "center",
  },
  btnAnalyzeText: { color: "#fff", fontWeight: "700", fontSize: typography.body, textAlign: "center", alignSelf: "stretch" },

  aiResultCard: {
    backgroundColor: "#0f172a",
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: "#7c3aed44",
    gap: spacing.sm,
  },
  aiResultTitle: { color: "#a78bfa", fontWeight: "700", fontSize: typography.body },
  aiError: { color: "#ef4444", fontSize: typography.small },
  aiSource: { color: colors.textMuted, fontSize: typography.small },

  statChip: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
  },
  statChipLabel: { color: colors.textMuted, fontSize: rf(10), fontWeight: "700" },
  statChipValue: { color: colors.primary, fontSize: typography.body, fontWeight: "800" },

  emergencyBtn: {
    backgroundColor: "#7f1d1d",
    borderRadius: 14,
    padding: spacing.lg,
    alignItems: "center",
    marginTop: spacing.md,
    borderWidth: 2,
    borderColor: "#ef4444",
  },
  emergencyBtnText: { color: "#fff", fontWeight: "800", fontSize: typography.body, letterSpacing: 0.3, textAlign: "center", alignSelf: "stretch" },
  // Seans bağlamı DIŞINDA donanım çalışıyor uyarısı (bkz. hardwareRunningOutOfSession).
  hwWarnBanner: {
    backgroundColor: "#7f1d1d",
    borderColor: "#ef4444",
    borderWidth: 1,
    borderRadius: 12,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  hwWarnText: { color: "#fecaca", fontWeight: "700", fontSize: typography.small, textAlign: "center" },
});
