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
import { AlanHaritasiKarti } from "@/components/domain/AlanHaritasiKarti";
import { PatientGate } from "@/components/domain/PatientGate";
import { ObservationNotesModal } from "@/components/domain/ObservationNotesModal";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { SurusKipiSecici } from "@/components/domain/SurusKipiSecici";
import { gorunurBobinler, espEtkinMi, espSlotuGorunur, STM_BOBIN_SAYISI, stmBobiniMi, tumSlotIdleri } from "@/services/bobinGorunurlugu";
import { KendiDurdurmaIsareti } from "@/components/ui/KendiDurdurmaKontrolu";
import { akimOlcumuAcik } from "@/utils/olculenAlan";
import { hedefEtiketi } from "@/utils/seansDegerEtiketi";
import { useTranslation } from "react-i18next";
import i18n from "i18next";
import { kritikMetin, useKritikDil } from "@/i18n/kritik";

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
  { key: "automatic", get label() { return i18n.t("kontrol.sekme.otomatik"); }, icon: "🤖" },
  { key: "manual",    get label() { return i18n.t("kontrol.sekme.manuel"); },   icon: "🎛" },
  { key: "aipro",     get label() { return i18n.t("kontrol.sekme.aiPro"); },   icon: "🎯" },
];

// ─── Target conditions ─────────────────────────────────────────────────────
const AUTO_TARGETS = [
  "Doku İyileşmesi", "Eklem Ağrısı", "Kas Spazmı",
  "Kırık İyileşmesi", "Enflamasyon Azaltma", "Sinir Rejenerasyonu",
  "Bağ Dokusu Tamiri", "Ödem Azaltma",
];

// Hedef çipinin GÖRÜNEN adı `hedefEtiketi` (utils/seansDegerEtiketi.ts): `AUTO_TARGETS` değeri (TR) seansa / literatür aramasına GİDER → DEĞİŞMEZ.

// ─── Component ────────────────────────────────────────────────────────────────
export function ControlScreen() {
  useKritikDil(); // ACİL DURDUR yazıları (kritikMetin) dil değişince yeniden çizilir; çeviri sisteminden BAĞIMSIZ
  const { t } = useTranslation();
  const { snapshot, telemetryStale } = useLiveData();
  // D1.89: WS'teki AKTİF seans (ölçülen yoğunluk + AI Pro duty temsili bunun alanlarıdır). Etkin değilse null.
  const wsSeans = snapshot.activeTreatment?.isActive === true ? snapshot.activeTreatment : null;
  const { selectedPatient, kontrolHafizasi } = useAppNav();
  const { session } = useAuth();
  const { operatorEmail } = useOperator();
  const {
    isActive, treatment, elapsedSec, remainingSec,
    // `error` state'i YERİNE `lastError()`: state, onu tetikleyen `await startSession(...)`
    // satırının hemen ardından bu render'ın closure'ında HENÜZ güncel değildi → uyarı kutusu
    // bir ÖNCEKİ hatayı (ilk denemede de null) gösteriyordu.
    loading, starting, sessionStopping, stopping, lastError, startSession, stopSession, emergencyStop,
    dbSessionId, benimse,
  } = useSessionControl();

  // Y212 · S-D67.11 (sahip): açılıştan SONRA başka istemcide / AI Pro'da başlatılan seans (WS'te seans YOK → VAR geçişi) kart
  // boştayken BENİMSENİR. Açılıştaki durum `/session/active`ten gelir (geçiş sayılmaz); yerel başlatma / durdurma / ACİL DURDUR
  // sürerken benimsenmez (geç gelen tik durdurulan seansı geri getirmesin). Durdur / ACİL DURDUR yolları AYNI.
  const wsSeansVardiRef = useRef(wsSeans !== null);
  useEffect(() => {
    const gecis = wsSeans !== null && !wsSeansVardiRef.current;
    wsSeansVardiRef.current = wsSeans !== null;
    if (gecis && wsSeans && !isActive && !loading && !stopping) benimse(wsSeans);
  }, [wsSeans, isActive, loading, stopping, benimse]);

  // AP-B1 (S-AP.1): son sekme Kontrol belleğinden — AI Pro seansı sürerken Sensörler'e gidip dönen kullanıcı AI Pro sekmesine döner
  // (eskiden ekran sökülüp "Manuel" ile açılıyordu). Bellek yoksa (sağlayıcısız çizim) eskisi gibi "Manuel".
  const [activeTab, setActiveTab] = useState<TabKey>(() => kontrolHafizasi?.current.sekme ?? "manual");
  useEffect(() => {
    if (kontrolHafizasi) kontrolHafizasi.current.sekme = activeTab;
  }, [activeTab, kontrolHafizasi]);
  // AI Pro hedef modelleri PROFİLE göre — tek kaynak `aiProProfilleri.MODELLER_PROFILE_GORE`
  // (sahip kararı #13: kedi araştırmacıda, fantom/petri veterinerde HİÇ görünmez).
  // ⚠️ Bazı testler `useUserMode`u yalnız `{ userMode }` ile mock'lar; liste bilinmeyen profilde
  // kediye düşer → ESKİ veteriner davranışı korunur.
  const { userMode } = useUserMode();
  const aiProModelleri = modelleriAl(userMode);
  const aiProBaslik = aiProModelleri.includes("kedi")
    ? t("kontrol.ekran.aiProKamera")
    : t("kontrol.ekran.aiProFantomPetri");

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
    new Set(tumSlotIdleri())
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
      stmBobiniMi(coil.id) ? isStmConnected : Boolean(coil.connected),
    [isStmConnected]
  );

  // Güvenlik: parametreleri aralığa çek, düzeltme olduysa kullanıcıyı uyar.
  const clampWithAlert = useCallback((input: Parameters<typeof clampTherapyParams>[0]) => {
    const { values, warnings } = clampTherapyParams(input);
    if (warnings.length) platformAlert(t("kontrol.ekran.parametreGuvenligi"), warnings.join("\n"));
    return values;
  }, [t]);

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
    // ⚠️ D1.98 · İG-6.45: BAŞLATMA seçimi GÖRÜNÜR bobinlerle sınırlıdır (`gorunurBobinler`, tek kaynak). Varsayılan
    // seçim `{1..8}` gizli slot 8'i (ESP kapalı, cihaz yok) içeriyordu: her Başlat "Bazı bobinler çevrimdışı" diyor,
    // görünür 7 bobin seçimden çıkarılınca STM çevrimiçiyken "Bağlantı yok" yanlış tanısı veriliyordu (ölçüldü).
    // STM bobinleri daima görünür (yedek: snapshot'ta bobin listesi yoksa da). Durdurma kümesi bundan ETKİLENMEZ.
    const gorunurIdler = new Set<number>([
      ...Array.from({ length: STM_BOBIN_SAYISI }, (_, i) => i + 1),
      ...gorunurBobinler(snapshot.coils ?? []).map((c) => c.id),
    ]);
    const requested = Array.from(selectedCoils).filter((id) => gorunurIdler.has(id));
    if (requested.length === 0) {
      platformAlert(t("ayarlar.sistemDurumu.uyari"), t("kontrol.ekran.bobinSecin"));
      return null;
    }
    // `?? []` — aynı dosyanın render'ı zaten bunu kullanıyordu; başlatma yolu guard'sızdı ve
    // `coils` alanı olmayan bir snapshot geldiğinde "Seans Başlat" ekranı çökertiyordu.
    const coilsById = new Map((snapshot.coils ?? []).map((c) => [c.id, c]));
    const effective = requested.filter((id) => isCoilConnected(coilsById.get(id) ?? { id }));
    if (effective.length === 0) {
      // Y230 (BE 3): ESP kapalıyken metin "WiFi" (ESP) demez — yalnız STM.
      platformAlert(
        t("kontrol.ekran.baglantiYok"),
        espEtkinMi(snapshot) ? t("kontrol.ekran.baglantiYokGovde") : t("kontrol.ekran.baglantiYokGovdeStm")
      );
      return null;
    }
    if (effective.length < requested.length) {
      platformAlert(t("kontrol.ekran.bazilariCevrimdisi"), t("kontrol.ekran.cevrimdisiAtlandi"));
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
      t("kontrol.ekran.hastaSecilmedi"),
      t("kontrol.ekran.hastaSecilmediGovde")
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
        platformAlert(t("kontrol.ekran.gecersizDeger"), t("kontrol.ekran.gecersizDegerGovde", { raw, key }));
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
    if (!ok) platformAlert(t("ayarlar.sistemDurumu.hata"), lastError() ?? t("kontrol.ekran.seansBaslatilamadi"));
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
    if (!ok) platformAlert(t("ayarlar.sistemDurumu.hata"), lastError() ?? t("kontrol.ekran.manuelBaslatilamadi"));
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
    /* istanbul ignore if -- ULASILAMAZ: Parametreleri güncelle düğmesi yalnız çalışan bobin varken çizilir */
    if (calisanlar.length === 0) {
      platformAlert(t("kontrol.ekran.calisanYok"), t("kontrol.ekran.calisanYokGovde"));
      return;
    }
    const raw = readParams({
      freq: [masterFreq, 100], duty: [masterDuty, 25], phase: [masterPhase, 0],
    });
    if (!raw) return;
    const p = clampWithAlert({
      freq: raw.freq, duty: raw.duty, phase: raw.phase, duration: parseDurationMin(masterDuration),
    });

    const stm = calisanlar.filter((id) => id <= STM_BOBIN_SAYISI);
    const esp = calisanlar.filter((id) => id > STM_BOBIN_SAYISI);
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
        t("kontrol.ekran.guncellenemedi"),
        t("kontrol.ekran.guncellenemediGovde"),
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
        t("kontrol.ekran.uygulandi"),
        t("kontrol.ekran.uygulandiGovde", { count: calisanlar.length, freq: p.freq, duty: p.duty, phase: p.phase, duration: p.duration }),
      );
    } else {
      // ⚠️ DONANIM GÜNCELLENDİ ama kayıt tazelenemedi — bu SESSİZ GEÇİLMEZ: üstteki kart
      // eski frekansı gösterir ve operatör uygulanan dozu yanlış okur.
      platformAlert(
        t("kontrol.ekran.kartTazelenemedi"),
        t("kontrol.ekran.kartTazelenemediGovde", { freq: p.freq }),
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
    // D1.82: başlatma UÇUŞTAYKEN de seans durdurulur — kanca, geç gelen başlatma yanıtından SONRA STOP'u yeniden gönderir.
    if (isActive || starting) await stopSession().catch(/* istanbul ignore next -- SAVUNMA: stopSession reddetmez (iç try / catch false döner) */ () => {});
    // DURDURULACAK KÜME: "o an SEÇİLİ olanlar" DEĞİL, "gerçekten ÇALIŞANLAR + seçili olanlar".
    // Kullanıcı bir bobini başlattıktan sonra seçimden çıkarırsa (ör. başka bobinlere geçmek için),
    // "Durdur" o bobine hiç komut göndermiyordu → hayvanın üzerinde sessizce enerjili kalıyordu.
    // Çalışmayan bobine STOP göndermek idempotent ve zararsızdır; eksik göndermek değildir.
    const runningIds = (snapshot.coils ?? []).filter((c) => c?.running).map((c) => c.id);
    // ⚠️ D1.98 (sahip kararı "slot 8 kalsın" + Ö.4-Y8): ESP slotu STOP kümesinde SEÇİMDEN BAĞIMSIZ, KOŞULSUZ kalır —
    // başlatma seçimi görünür bobinlerle sınırlandı ama durdurma gönderimi azaltılmaz.
    const espSlotlari = (snapshot.coils ?? []).map((c) => c.id).filter((id) => id > STM_BOBIN_SAYISI);
    const targets = Array.from(new Set<number>([...Array.from(selectedCoils), ...runningIds, ...espSlotlari]));
    const stmCoils = targets.filter((id) => id <= STM_BOBIN_SAYISI);
    const espCoils = targets.filter((id) => id > STM_BOBIN_SAYISI);
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
        }, null, { durdurma: true }), // D3I-A1.3 · Ö.4-Y8: STOP düz-HTTP kapısına bağlanmaz
      );
    }
    for (const coilId of espCoils) {
      istekler.push(
        apiPost<{ status?: string } | null>(`/coil/${coilId}/control`, {
          freq: 0, duty: 0, phase: 0, duration: 0, start: false,
        }, null, { durdurma: true }),
      );
    }
    const sonuclar = await Promise.all(istekler);
    // Denetim 2. tur [1.1] (2026-08-20): "hata değil" ≠ "teyit". Backend, publish broker'a
    // ulaşamayınca HTTP 200 + {status:"mqtt_unavailable"} döner (tek bobin) ve /coil/batch
    // ÜST-SEVİYEDE HEP "success" deyip satır-başı sonuçları results[] içinde taşır
    // (stm_unavailable/mqtt_unavailable/invalid). Eski yüklem (`status !== "error"`) ikisini de
    // teyit sayıyordu → broker ölüyken STOP hiçbir bobine ulaşmamışken aşağıdaki uyarı HİÇ
    // çıkmıyordu. Teyit yalnız AÇIK "success"tir; batch'te satırlar da tek tek sayılır.
    // ⚠️ D1.98 · A-63: ESP BİLEREK kapalıyken (`PEMF_ESP_ENABLED` ayarsız) backend slot 8 için `devre_disi` döner — ESP
    // alt sistemi yok, komut yayınlanmadı (denendi). Eskiden bu `mqtt_unavailable`dı ve her başarılı Durdur sahte
    // "HÂLÂ ÇALIŞIYOR" alarmı veriyordu (alarm körlüğü). Teyit A-63 gereği STM'e göre: `devre_disi` alarm SEBEBİ değildir
    // (ama "success" de sayılmaz — başka hiçbir yüklemde). ESP AÇIKKEN başarısız yayın `mqtt_unavailable` → alarm KALIR.
    const satirOnaylandi = (r: { status?: string } | null | undefined): boolean =>
      !!r && (r.status === "success" || r.status === "devre_disi");
    const allOk = sonuclar.every((r) => {
      if (!satirOnaylandi(r)) return false;
      const satirlar = r?.results;
      return !Array.isArray(satirlar) || satirlar.every(satirOnaylandi);
    });
    if (!allOk && istekler.length > 0) {
      platformAlert(
        t("kontrol.ekran.durdurmaOnaylanamadi"),
        t("kontrol.ekran.durdurmaOnaylanamadiGovde"),
      );
    }
    } finally {
      stopRoundRef.current = false;
      setStopRound(false);
    }
  };

  // ── Seans-sonrası gözlem notu prompt'u (PyQt observation-notes) ──
  type ObsSess = {
    patientName?: string; mode?: string; frequency?: number; intensity?: number; durationMinutes?: number; obsKey?: number;
    /** D1.66: notun yazılacağı seansın DB kimliği. */
    dbSessionId?: number | null;
  };
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
        dbSessionId, // D1.66: not O seansın satırına gider (sunucu son seansı TAHMİN etmez)
      };
    }
  }, [isActive, treatment, patientName, dbSessionId]);

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
          bobinler çalışıyor olabilir. DashboardScreen'de bu koruma vardı, burada yoktu.
          ⚠️ L1-7.10 · İG-6.11 (a): bant WS'te AKTİF seans varken (başka istemci / AI Pro başlattı; kart yalnız açılışta
          `/session/active` okur) "seans bağlamı dışında" diyordu — YANLIŞ. O durumda metin AKTİF SEANS'ı söyler. Yalnız METİN
          değişir: bandın görünme koşulu, ACİL DURDUR ve kartın Durdur yolu AYNI. Kapı: ControlScreen.L1_7_10.seansKartDisinda.test.tsx */}
      {!isActive && hardwareRunningOutOfSession && (
        <View style={styles.hwWarnBanner}>
          <Text style={styles.hwWarnText}>
            {wsSeans
              ? t("kontrol.ekran.seansKartDisinda", { count: runningCount })
              : t("kontrol.ekran.donanimCalisiyor", { count: runningCount })}
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
        // D1.89 · İG-6.11 (b): ölçülen yoğunluk/tepe ve AI Pro duty temsili WS `activeTreatment`ten gelir — yerel kopya
        // (`useSessionControl`) bunları HİÇ doldurmuyordu, "(ölçülen)" rozeti üretimde çizilmiyordu.
        measuredIntensityMt={treatment?.measuredIntensityMt ?? (wsSeans ? wsSeans.measuredIntensityMt ?? null : null)}
        measuredPeakMt={treatment?.measuredPeakMt ?? (wsSeans ? wsSeans.measuredPeakMt ?? null : null)}
        dutyTemsilYuzde={wsSeans ? wsSeans.dutyTemsilYuzde ?? null : null}
        odakDozMt={wsSeans ? wsSeans.odakDozMt ?? null : null}
        odakBobinSayisi={wsSeans ? wsSeans.odakBobinSayisi ?? null : null}
        onStop={stopSession}
        onEmergencyStop={emergencyStop}
        loading={sessionStopping}
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
        accessibilityLabel={kritikMetin("guvenlik.acilDurdur.tumBobinlerEtiketi")}
        accessibilityHint={kritikMetin("guvenlik.acilDurdur.erisimIpucu")}>
        <Text style={styles.emergencyBtnText} numberOfLines={2} adjustsFontSizeToFit>{kritikMetin("guvenlik.acilDurdur.tumBobinlerDugme")}</Text>
      </TouchableOpacity>
      {/* D1.E02 · A-51: bu düğme ÇİZİLDİĞİ sürece kayan ACİL DURDUR gizlenir; ekran çökerse işaret de sökülür. */}
      <KendiDurdurmaIsareti />

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
          <SectionTitle text={t("kontrol.ekran.otomatikBaslik")} />
          <Text style={styles.hint}>
            {t("kontrol.ekran.otomatikAciklama")}
          </Text>

          <FormLabel text={t("kontrol.ekran.seansHedefi")} />
          <View style={styles.targetGrid}>
            {AUTO_TARGETS.map((hedef) => (
              <TouchableOpacity
                key={hedef}
                style={[styles.targetChip, autoTarget === hedef && styles.targetChipActive]}
                onPress={() => applyAutoPreset(hedef)}
              >
                <Text style={[styles.targetChipText, autoTarget === hedef && styles.targetChipTextActive]}>
                  {hedefEtiketi(t, hedef)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={styles.paramRow}>
            <ParamField label={t("kontrol.panel.frekansHz")} value={autoFreq} onChangeText={setAutoFreq} />
            <ParamField label={t("kontrol.panel.dutyYuzde")} value={autoDuty} onChangeText={setAutoDuty} />
            {/* ⚠️ DENETİM 2026-08-09 (Tier 2): bu değer CİHAZA GÖNDERİLMEZ. STM binary paketi
                (duty/phase/freq/duration) ve ESP MQTT komutu (freq/duty/phase/duration) mT alanı
                TAŞIMAZ — girilen sayı yalnız kayda yazılır. Etiket bunu söylemezse operatör
                yoğunluğu ayarladığını sanır ve gerçek doz beklediğinden farklı olur.
                Gerçek çözüm firmware'dedir (paketi genişlet + osiloskopla doğrula). */}
            <ParamField label={t("kontrol.ekran.yogunlukKayit")} value={autoIntensity}
              onChangeText={setAutoIntensity} />
            <ParamField label={t("kontrol.panel.sureDk")} value={autoDuration} onChangeText={setAutoDuration} />
          </View>
          {autoLoading && <Text style={styles.hint}>{t("kontrol.ekran.literaturAliniyor")}</Text>}
          {/* Denetim #01: doz kaynağı görünür olmalı. "default_wellness" = seçilen hedefin
              literatürde karşılığı yok, genel dozla devam ediliyor — operatör bunu bilmeli. */}
          {!autoLoading && autoKaynak === "default_wellness" && (
            <Text style={styles.kaynakUyari}>
              {t("kontrol.ekran.literaturYok")}
            </Text>
          )}
          {!autoLoading && autoKaynak === "literature_exact" && (
            <Text style={styles.kaynakBilgi}>{t("kontrol.ekran.literaturUygulandi")}</Text>
          )}

          <CoilSelector coils={coils} selected={selectedCoils} onToggle={toggleCoil} stmConnected={isStmConnected} gorunur={gorunurBobinler} />

          <StartButton
            label={t("kontrol.ekran.otomatikBaslat")}
            onPress={handleStartAuto}
            disabled={isActive || loading}
          />
        </View>
      )}

      {/* ── TAB: Manuel ───────────────────────────────────────── */}
      {activeTab === "manual" && (
        <View style={styles.section}>
          <SectionTitle text={t("kontrol.ekran.manuelBaslik")} />

          {/* Master controls */}
          <View style={styles.masterCard}>
            <Text style={styles.masterTitle}>{t("kontrol.ekran.topluUygulama")}</Text>
            <View style={styles.paramRow}>
              <ParamField label={t("kontrol.panel.frekansHz")} value={masterFreq} onChangeText={setMasterFreq} />
              <ParamField label={t("kontrol.panel.dutyYuzde")} value={masterDuty} onChangeText={setMasterDuty} />
              <ParamField label={t("kontrol.panel.fazDerece")} value={masterPhase} onChangeText={setMasterPhase} />
              <ParamField label={t("kontrol.panel.sureDk")} value={masterDuration} onChangeText={setMasterDuration} />
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
                  label={t("kontrol.panel.baslat")}
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
                    label={t("kontrol.ekran.parametreleriUygula")}
                    onPress={handleParametreGuncelle}
                    disabled={loading}
                    color="#0ea5e9"
                  />
                </View>
              )}
              <View style={{ flex: 1 }}>
                {/* ⚠️ D1.82 · Y47 (sahip): durdurma kontrolü HİÇBİR istek sürerken kilitlenmez. Eskiden
                    `disabled={loading}` idi: `/session/start` askıdayken (≤ 8 sn) Durdur basılamıyordu (ölçüldü).
                    Etiket, sessizce yutulan dokunuş yerine geri bildirim verir. */}
                <StartButton
                  label={stopRound ? t("kontrol.ekran.durduruluyor") : t("kontrol.panel.durdur")}
                  onPress={handleStopManual}
                  disabled={false}
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

              ⚠️ TERMAL: hiçbir katmanda termal kesme YOK (sahip kararı A-47 + Y2;
              istemcideki 48 °C otomatik durdurması da 2026-10-02'de kaldırıldı). Panel
              48 °C üstünde YALNIZ görsel uyarı verir; ölçüm gelmeyen bobinde rozet
              "ölçüm yok" (—) gösterir. Bilinçli. */}
          <Text style={styles.subTitle}>
            {espSlotuGorunur(coils) ? t("kontrol.ekran.bobinler18") : t("kontrol.ekran.bobinler17")}
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
                dutyEtkin={coil.dutyEtkin}
                magneticMt={coil.magneticMt}
                currentA={coil.currentA}
                akimOlcumu={akimOlcumuAcik(snapshot)}
                measuredFields={coil.measuredFields}
                defaultFreq={parseFloat(masterFreq) || 100}
                defaultDuty={parseFloat(masterDuty) || 25}
                defaultPhase={parseFloat(masterPhase) || 0}
                defaultDuration={parseDurationMin(masterDuration)}
                // ⚠️ SABİT `true` DEĞİL: slot 8 ESP/MQTT ile sürülür. Sabit kalsaydı panel
                // o bobini `stmConnected`e kapatır ve ESP ACK'ini (`command_id`) hiç
                // beklemezdi → STM kopukken ESP bobini başlatılamaz, başlatılınca da
                // onayı doğrulanmazdı.
                stm32Driven={coil.stm32Driven ?? stmBobiniMi(coil.id)}
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

      {/* GA (istem 53): CANLI ALAN HARİTASI — varsayılan KAPALI, sekme içeriğinin ALTINDA (ACİL DURDUR'un yeri DEĞİŞMEZ); yalnız
          gösterim, açıkken sunucuya abone olur. */}
      <AlanHaritasiKarti />

      {/* Gözlem notu modalı seans BİTİNCE otomatik açılır ve tam ekranı kaplar → o sırada donanım
          hâlâ enerjiliyse (yerel sayaç bitti ama backend/bobin durmadıysa) ACİL DURDUR'a erişimi
          kapatıyordu. Bobin çalışırken modalı AÇMA; önce durdurma erişimi kalsın, not sonra alınır. */}
      <ObservationNotesModal
        visible={obsSession !== null && !hardwareRunningOutOfSession}
        session={obsSession}
        onClose={() => setObsSession(null)}
        numune={userMode === "researcher"}
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
        onChangeText={(v) => onChangeText(v.replace(",", "."))}
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
  const { t } = useTranslation();
  return (
    <View style={styles.coilSelector}>
      <Text style={styles.formLabel}>{t("kontrol.ekran.bobinSecimi")}</Text>
      <View style={styles.coilSelectorGrid}>
        {/* Faz 4: 7 fiziksel STM bobini. Slot 8 (ESP) YALNIZ ortaya çıkınca listelenir —
            `gorunur` süzgeci ekranın geri kalanıyla AYNI kuralı uygular, yoksa seçilemeyen
            ama çizilen (ya da çizilen ama seçilemeyen) bir bobin olurdu.
            Yedek liste 7 üretir: hiç snapshot yokken ESP'nin varlığı BİLİNMEZ. */}
        {(coils.length > 0
          ? gorunur(coils)
          : Array.from({ length: STM_BOBIN_SAYISI }, (_, i) => ({ id: i + 1, connected: false, running: false }))
         ).map((c) => {
          const connected = stmBobiniMi(c.id) ? stmConnected : Boolean(c.connected);
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
              accessibilityLabel={t("kontrol.ekran.bobinSecimEtiketi", { id: c.id, secim: selected.has(c.id) ? t("kontrol.ekran.secili") : t("kontrol.ekran.seciliDegil"), baglanti: connected ? t("kontrol.ekran.cevrimici") : t("kontrol.ekran.cevrimdisi") })}
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
