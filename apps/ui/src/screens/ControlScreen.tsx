// Author: mertaygn, cglrgrkn
/**
 * ControlScreen — Tam Tedavi Kontrol Ekranı
 *
 * Python unified_control_window.py'nin React karşılığı.
 * Sekmeler: Otomatik Mod | Manuel Mod | AI Pro
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
import { colors, spacing, typography, rf, rs, layoutMax, touch } from "@/theme/tokens";
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
import { modelleriAl } from "@/components/domain/aiProProfilleri";
import { useUserMode } from "@/context/UserModeContext";
import { EFieldBar } from "@/components/domain/EFieldBar";
import { PatientGate } from "@/components/domain/PatientGate";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { SurusKipiSecici } from "@/components/domain/SurusKipiSecici";
import { gorunurBobinler, espSlotuGorunur } from "@/services/bobinGorunurlugu";

// ─── Tab types ────────────────────────────────────────────────────────────────
type TabKey = "automatic" | "manual" | "aipro";

/**
 * ⚠️ "AI MODU" SEKMESİ KALDIRILDI (sahip kararı 2026-09-12):
 * "ai modu ve otomatik mod temelde aynı prensiple çalışıyor. otomatik mod kalsın bence
 *  diğerini silelim. literatürden öneriyi atsın. kullanıcı isterse parametre güncelleyebilsin."
 *
 * ÖLÇÜLDÜ — SAHİP HAKLIYDI: iki sekme de AYNI uca gidiyordu (`/hardware/auto_preset`,
 * gövde `{target_condition}`) ve aynı kaynağı raporluyordu (`literature_exact`). Tek fark,
 * AI Modu'nun sonucu SALT-OKUNUR bir kartta gösterip fazladan bir "Analiz Başlat" tıklaması
 * istemesiydi; Otomatik ise aynı öneriyi DÜZENLENEBİLİR alanlara yazıyor.
 *
 * Yani sahibin istediği üç şeyin üçü de Otomatik'te ZATEN vardı:
 *   · literatürden öneri  → hedefe tıklayınca `applyAutoPreset()` çeker
 *   · kullanıcı parametreyi güncelleyebilsin → alanlar `ParamField` (düzenlenebilir)
 *   · doz kaynağı görünür → "📖 Literatür protokolü uygulandı" / wellness uyarısı
 *
 * ⚠️ AI PRO AYRI KALIR: o, kameradan organ lokalizasyonu yapan ve bobin başına doz üreten
 * KAPALI-DÖNGÜ sistemdir — `auto_preset` ile hiçbir ortak yolu yoktur.
 */
const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "automatic", label: "Otomatik", icon: "🤖" },
  { key: "manual",    label: "Manuel",   icon: "🎛" },
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
  // AI Pro hedef modelleri PROFİLE göre — tek kaynak `aiProProfilleri.MODELLER_PROFILE_GORE`
  // (sahip kararı #13: kedi araştırmacıda, fantom/petri veterinerde HİÇ görünmez).
  // ⚠️ Bazı testler `useUserMode`u yalnız `{ userMode }` ile mock'lar; liste bilinmeyen profilde
  // kediye düşer → ESKİ veteriner davranışı korunur.
  const { userMode } = useUserMode();
  const aiProModelleri = modelleriAl(userMode);
  const aiProBaslik = aiProModelleri.includes("kedi")
    ? "AI Pro — Kamera Kapalı-Döngü"
    : "AI Pro — Fantom / Petri Kapalı-Döngü";

  // ── Otomatik Mod state ─────────────────────────────────────────────────
  const [autoTarget, setAutoTarget] = useState(AUTO_TARGETS[0]);
  const [autoFreq, setAutoFreq] = useState("50");
  const [autoDuty, setAutoDuty] = useState("25");
  const [autoDuration, setAutoDuration] = useState("20");
  const [autoIntensity, setAutoIntensity] = useState("1.0");
  const [autoLoading, setAutoLoading] = useState(false);
  // auto_preset yanıtındaki "source": "literature_exact" | "default_wellness" (denetim #01 rozeti).
  const [autoKaynak, setAutoKaynak] = useState<string | null>(null);

  // ── Manuel Mod state ───────────────────────────────────────────────────
  const [masterFreq, setMasterFreq] = useState("100");
  const [masterDuty, setMasterDuty] = useState("25");
  const [masterPhase, setMasterPhase] = useState("0");
  const [masterDuration, setMasterDuration] = useState("20");
  const [selectedCoils, setSelectedCoils] = useState<Set<number>>(
    new Set([1, 2, 3, 4, 5, 6, 7, 8])
  );

  // ── AI Mod state ───────────────────────────────────────────────────────

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
      // Faz 4 (2026-09-10): bobin 1-7 STM → bağlılık STM'in kendi durumundan gelir.
      // Slot 8 ESP (cihaz yok) → kendi `connected` alanına bakar.
      coil.id <= 7 ? isStmConnected : Boolean(coil.connected),
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
        // Denetim 2026-08-28 #01: literatürde karşılığı olmayan hedef SESSİZCE genel wellness
        // dozuna düşüyordu — ekranda hiçbir fark yoktu, vet hedefe özel doz aldığını sanıyordu.
        setAutoKaynak(typeof p.source === "string" ? p.source : null);
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

  /**
   * SEANS ORTASINDA PARAMETRE GÜNCELLE (sahip isteği 2026-09-11).
   *
   * "100 Hz ile başlattım 20 dk, 10. dakikada 150 Hz yapmak istiyorum; hem toplu hem tek
   * bobin için, faz/duty/süre hepsi için değişiklik yapma özgürlüğü istiyorum."
   *
   * ⚠️ SEANSI YENİDEN BAŞLATMAZ. `handleStartManual` `/session/start` çağırır ve aktif
   * seans varken 409 döner; ayrıca seansı yeniden başlatmak geçmişte İKİNCİ bir kayıt
   * açar ve süre sayacını sıfırlardı. Bu yol yalnız ÇALIŞAN bobinlere yeni parametreyi
   * yollar (`/coil/batch` + `start: true` — firmware çalışan bobinde parametreyi
   * kesintisiz günceller) ve ardından seans kartı + doz kaydını tazeler.
   *
   * ⚠️ HEDEF = GERÇEKTEN ÇALIŞANLAR: "seçili ama durmuş" bir bobini bu düğmeyle
   * BAŞLATMAYIZ. Güncelleme düğmesinin bobin enerjilendirmesi, operatörün beklemediği
   * bir sürüş olurdu.
   */
  const handleParametreGuncelle = async () => {
    const calisanlar = (snapshot.coils ?? []).filter((c) => c?.running).map((c) => c.id);
    if (calisanlar.length === 0) {
      platformAlert("Çalışan bobin yok", "Parametre güncelleme yalnız ÇALIŞAN bobinlere uygulanır.");
      return;
    }
    const raw = readParams({
      freq: [masterFreq, 100], duty: [masterDuty, 25], phase: [masterPhase, 0],
    });
    if (!raw) return;
    const p = clampWithAlert({
      freq: raw.freq, duty: raw.duty, phase: raw.phase, duration: parseDurationMin(masterDuration),
    });

    const stm = calisanlar.filter((id) => id <= 7);
    const esp = calisanlar.filter((id) => id > 7);
    const istekler: Promise<{ status?: string; results?: ({ status?: string } | null)[] } | null>[] = [];
    if (stm.length > 0) {
      istekler.push(apiPost("/coil/batch", {
        coil_ids: stm, freq: p.freq, duty: p.duty, phase: p.phase, duration: p.duration * 60, start: true,
      }, null));
    }
    for (const id of esp) {
      istekler.push(apiPost(`/coil/${id}/control`, {
        freq: p.freq, duty: p.duty, phase: p.phase, duration: p.duration * 60, start: true,
      }, null));
    }
    const sonuclar = await Promise.all(istekler);
    // ⚠️ TEYİT ZORUNLU (durdurma yolundaki ile AYNI kural): `/coil/batch` üst seviyede HEP
    // "success" der ve satır sonuçlarını `results[]` içinde taşır. Yalnız üst seviyeye
    // bakmak, hiçbir bobine ulaşmamış bir güncellemeyi "uygulandı" göstermek olurdu.
    const satirOk = (r: { status?: string } | null | undefined) => !!r && r.status === "success";
    const hepsiOk = sonuclar.every((r) => {
      if (!satirOk(r)) return false;
      const satirlar = r?.results;
      return !Array.isArray(satirlar) || satirlar.every(satirOk);
    });
    if (!hepsiOk) {
      platformAlert(
        "Parametre güncellenemedi",
        "Bir veya daha fazla bobine yeni parametre ULAŞMADI — bobinler ESKİ parametrelerle sürülmeye devam ediyor olabilir.",
      );
      return;
    }
    // Kart + doz kaydı. ⚠️ Donanım zaten güncellendi; bu adım başarısız olursa sürüş
    // ETKİLENMEZ, yalnız kart eski frekansı gösterir → operatöre açıkça söylenir.
    const kayit = await apiPost<{ status?: string } | null>("/session/parametre_guncelle", {
      frequency: p.freq, duty: p.duty, phase: p.phase, duration_minutes: p.duration, coil_ids: calisanlar,
    }, null, { silent: true });
    if (kayit?.status === "success") {
      platformAlert(
        "Parametreler uygulandı",
        `${calisanlar.length} bobin güncellendi: ${p.freq} Hz · %${p.duty} · ${p.phase}° · ${p.duration} dk`,
      );
    } else {
      // ⚠️ DONANIM GÜNCELLENDİ ama kayıt tazelenemedi — bu SESSİZ GEÇİLMEZ: üstteki kart
      // eski frekansı gösterir ve operatör uygulanan dozu yanlış okur.
      platformAlert(
        "Uygulandı — kart tazelenemedi",
        `Bobinler ${p.freq} Hz'e geçti, ancak seans kartı/kaydı güncellenemedi. ` +
          "Üstteki özet eski değeri gösteriyor olabilir; bobin kartlarındaki değerler doğrudur.",
      );
    }
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
    const stmCoils = targets.filter((id) => id <= 7);
    const espCoils = targets.filter((id) => id > 7);
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
        measuredIntensityMt={treatment?.measuredIntensityMt ?? null}
        measuredPeakMt={treatment?.measuredPeakMt ?? null}
        onStop={stopSession}
        onEmergencyStop={emergencyStop}
        loading={loading}
        stopping={stopping}
        stale={isActive && telemetryStale}
      />

      {/* CANLI E-ALANI (2026-08-06): yalnız analiz bağlamı + aktif seans varken görünür;
          aksi halde bileşen kendini render ETMEZ (bkz. EFieldBar). */}
      <EFieldBar />

      {/* ── ACİL DURDUR — sekme İÇERİĞİNDEN ÖNCE ────────────────────────────────
          ⚠️ HASTA GÜVENLİĞİ [ekranB-2, 2026-09-04]: bu düğme sayfanın SONUNDAYDI; Manuel
          sekmesinde 8 bobin kartının altında ~3000 px derinde kalıyordu. Kayan
          `GlobalEmergencyStop` bunu telafi ediyor sanılıyordu ama o da yalnız
          `running || activeTreatment` iken çizilir ve STM çevrimdışıyken bobin durumu
          BİLİNMEDİĞİ için gizleniyordu. Düğme artık sekme çubuğunun ÜSTÜNDE: hangi sekme
          açık olursa olsun, kaydırmadan erişilir. AŞAĞI TAŞIMA. */}
      <TouchableOpacity style={styles.emergencyBtn} onPress={emergencyStop}
        accessibilityRole="button"
        accessibilityLabel="Tüm bobinleri acil durdur"
        accessibilityHint="Tüm bobinleri anında durdurur ve aktif seansı sonlandırır">
        <Text style={styles.emergencyBtnText} numberOfLines={2} adjustsFontSizeToFit>🚨 TÜM BOBİNLERİ ACİL DURDUR</Text>
      </TouchableOpacity>

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
          {/* Denetim #01: doz kaynağı görünür olmalı. "default_wellness" = seçilen hedefin
              literatürde karşılığı yok, genel dozla devam ediliyor — operatör bunu bilmeli. */}
          {!autoLoading && autoKaynak === "default_wellness" && (
            <Text style={styles.kaynakUyari}>
              ⚠️ Bu hedef için literatür protokolü yok — genel (wellness) dozu uygulanıyor.
              Hedefe özel doz istiyorsanız parametreleri elle ayarlayın.
            </Text>
          )}
          {!autoLoading && autoKaynak === "literature_exact" && (
            <Text style={styles.kaynakBilgi}>📖 Literatür protokolü uygulandı.</Text>
          )}

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} gorunur={gorunurBobinler} />

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
            <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} gorunur={gorunurBobinler} />
            {/* Sürüş kipi TOPLU panelde: bobin başına kip seçilir ama tek bir pakette
                gider (protokolde tek maske alanı var) → tek yer, tek kaynak. Seans
                aktifken kilitli: koşan sürüşün kipini ortasında değiştirmek doz
                tanımını bozar. */}
            <SurusKipiSecici coils={coils} stmConnected={isStmConnected} disabled={isActive} />
            <View style={styles.manualBtnRow}>
              <View style={{ flex: 1 }}>
                <StartButton
                  label="▶ Başlat"
                  onPress={handleStartManual}
                  disabled={isActive || loading}
                />
              </View>
              {/* PARAMETRE GÜNCELLE — yalnız donanım ÇALIŞIRKEN görünür.
                  ⚠️ Seans kapalıyken göstermek anlamsız (güncellenecek sürüş yok) ve
                  operatörü "başlat" ile karıştırırdı. */}
              {hardwareRunningOutOfSession && (
                <View style={{ flex: 1 }}>
                  <StartButton
                    label="🔄 Parametreleri Uygula"
                    onPress={handleParametreGuncelle}
                    disabled={loading}
                    color="#0ea5e9"
                  />
                </View>
              )}
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

          {/* ── BOBİNLER (1–7) — FAZ 4, sahip kararı 2026-09-10 ──────────────────
              Eskiden İKİ grup vardı: "🔌 STM32 Bobinler (1–5)" ve "📶 WiFi ESP
              Bobinler (6–8)". Bobin 6-7 ESP8266'dan STM32'ye taşındı (PE13 / PE15,
              firmware NUM_COILS=7, paket 120 bayt) → ayrım kalktı, TEK grup.

              ⚠️ Slot 8 KOŞULLU çizilir (bkz. `gorunurBobinler`): cihaz yokken hayalet
              bir kart göstermemek için gizli, ama ESP bağlandığında ya da o slot
              ÇALIŞIYORKEN mutlaka görünür — görünmeyen bobin durdurulamıyordu
              (2026-09-11 saha arızası).

              ⚠️ TERMAL: bobin 6-7'de artık CİHAZ-TARAFLI termal kesme YOK (sahip
              kararı). Sensörler henüz bağlı değil → `objectTemp` gelmiyor → paneldeki
              48 °C istemci interlock'u bu bobinlerde TETİKLENEMEZ ve rozet "ölçüm yok"
              gösterir. Bu, bobin 1-5'in bugünkü durumuyla AYNI; bilinçli. */}
          <Text style={styles.subTitle}>
            {espSlotuGorunur(coils) ? "🔌 Bobinler (1–8)" : "🔌 Bobinler (1–7)"}
          </Text>
          <ResponsiveGrid minItemWidth={320}>
            {gorunurBobinler(coils).map((coil) => (
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
                measuredFields={coil.measuredFields}
                defaultFreq={parseFloat(masterFreq) || 100}
                defaultDuty={parseFloat(masterDuty) || 25}
                defaultPhase={parseFloat(masterPhase) || 0}
                defaultDuration={parseDurationMin(masterDuration)}
                // ⚠️ SABİT `true` DEĞİL: slot 8 ESP/MQTT ile sürülür. Sabit kalsaydı panel
                // o bobini `stmConnected`e kapatır ve ESP ACK'ini (`command_id`) hiç
                // beklemezdi → STM kopukken ESP bobini başlatılamaz, başlatılınca da
                // onayı doğrulanmazdı.
                stm32Driven={coil.stm32Driven ?? coil.id <= 7}
                stmConnected={isStmConnected}
                disabled={isActive}
              />
            ))}
          </ResponsiveGrid>
        </View>
      )}

      {/* ── TAB: AI ───────────────────────────────────────────── */}
      {/* ── TAB: AI Pro ───────────────────────────────────────── */}
      {activeTab === "aipro" && (
        <View style={styles.section}>
          <SectionTitle text={aiProBaslik} />
          <AiProPanel
            patientName={patientName}
            secilebilirModeller={aiProModelleri}
            kullaniciKipi={userMode || ""}
          />
        </View>
      )}

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
  coils, selected, onToggle, stmConnected, gorunur,
}: {
  coils: CoilStatus[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  stmConnected: boolean;
  /** Ekranın geri kalanıyla AYNI görünürlük kuralı (tek kaynak) — bkz. `gorunurBobinler`. */
  gorunur: (liste: CoilStatus[]) => CoilStatus[];
}) {
  return (
    <View style={styles.coilSelector}>
      <Text style={styles.formLabel}>Bobin Seçimi</Text>
      <View style={styles.coilSelectorGrid}>
        {/* Faz 4: 7 fiziksel STM bobini. Slot 8 (ESP) YALNIZ ortaya çıkınca listelenir —
            `gorunur` süzgeci ekranın geri kalanıyla AYNI kuralı uygular, yoksa seçilemeyen
            ama çizilen (ya da çizilen ama seçilemeyen) bir bobin olurdu.
            Yedek liste 7 üretir: hiç snapshot yokken ESP'nin varlığı BİLİNMEZ. */}
        {(coils.length > 0
          ? gorunur(coils)
          : Array.from({ length: 7 }, (_, i) => ({ id: i + 1, connected: false, running: false }))
         ).map((c) => {
          const connected = c.id <= 7 ? stmConnected : Boolean(c.connected);
          return (
            <TouchableOpacity
              key={c.id}
              style={[
                styles.coilSelectorBtn,
                selected.has(c.id) && styles.coilSelectorBtnActive,
                !connected && styles.coilSelectorBtnOffline,
              ]}
              onPress={() => onToggle(c.id)}
              // ⚠️ [S3 adım 6 / ekranB-15] hitSlop ≤ gap/2. Eski 8 px tampon + 4 px ızgara boşluğu
              // ile komşu kutuların dokunma alanları ÜST ÜSTE biniyordu: aralığa yapılan dokunuş
              // sağdaki bobine gidiyor, operatör YANLIŞ BOBİNİ seansa sokabiliyordu.
              hitSlop={touch.slopFor(spacing.sm)}
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
    // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı veriyor (mobil rs(160)+güvenli
    // alan / masaüstü rs(84)); ekranın kendi dolgusu üstüne binip ~200 px ölü alan bırakıyordu.
    width: "100%",
    maxWidth: layoutMax.icerik,
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
  // Doz kaynağı rozetleri (denetim #01) — sessiz düşüşü görünür kılar.
  kaynakUyari: {
    color: colors.warning,
    fontSize: typography.small,
    lineHeight: rf(20),
    marginTop: spacing.xs,
  },
  kaynakBilgi: {
    color: colors.textMuted,
    fontSize: typography.small,
    lineHeight: rf(20),
    marginTop: spacing.xs,
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
  // [S1/ekranB-12] Tavan ÖLÇEKSİZ: PC'de rs() ile çarpılırsa 260 px kabul ölçütü aşılır.
  paramField: { flex: 1, minWidth: rs(140), maxWidth: layoutMax.alan },
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
  // Boşluk 4 → 8: hitSlop kuralının ön koşulu (4 px boşlukta güvenli tampon 2 px kalırdı).
  coilSelectorGrid: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  coilSelectorBtn: {
    // Ölçekle AŞAĞI inmez: 320 px'te rs(40) = 34 px'ti (erişilebilirlik tabanı 44).
    width: touch.min,
    height: touch.min,
    borderRadius: 10,
    backgroundColor: "#1e293b",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#334155",
  },
  // Seçili durum yalnız RENKLE anlatılmıyor: çerçeve kalınlığı da değişiyor (renk körlüğü).
  coilSelectorBtnActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6", borderWidth: 2 },
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
