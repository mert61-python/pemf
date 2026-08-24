// Author: mertaygn, cglrgrkn
/**
 * AiProPanel — AI Pro kapalı-döngü kontrol yüzeyi (Kontrol sekmesi).
 * ================================================================
 * Girdi = KEDİ ORGAN LOKALİZASYONU (cat_organ: YOLOseg+DLC+RTMPose+PnP ile seçili organın
 * 3B konumu) → em_kedi (KediPredictor) → bobin 1-7 PER-COIL AI duty/phase (D1-D7 / P1-P7,
 * P bobin-1 referanslı). Bobin 8 KAPALI → 7 bobin. (El takibi TAMAMEN SÖKÜLDÜ.)
 *
 * Web   (Platform.OS === "web"): sunucu kamerası (backend VideoCapture(0)).
 *   Canlı veri: WebSocket 'ai_vision' (LiveDataContext.aiVisionData).
 * Mobil (iOS/Android): telefon kamerası kareleri → POST /ai/ai_pro/frame
 *   (backend aynı organ-lokalizasyon + em_kedi + donanım sürüşünü çalıştırır) → tablo/metrikler
 *   HTTP yanıtından gelir. cat_organ ağır → backend periyodik lokalize + cache.
 *
 * Kontrol: /api/ai/pro/start | stop | organ | calibrate(=yeniden-konumla) | status
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useOperator } from "@/context/OperatorContext";
import { View, Text, StyleSheet, TouchableOpacity, Image, TextInput, Platform } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet, apiPost, platformAlert, platformConfirm } from "@/services/apiClient";
import { getClientInstanceId, serviceConfig } from "@/services/config";
import { useAuth } from "@/context/AuthContext";
import { AiSpecApprovalModal, type AiProposalMeta, type AiProposalSpecs } from "@/components/domain/AiSpecApprovalModal";

const ORGANS = [
  { id: 0, name: "Tüm Vücut" }, { id: 1, name: "Mide" }, { id: 2, name: "Böbrek" },
  { id: 3, name: "Karaciğer" }, { id: 4, name: "Mesane" }, { id: 5, name: "Pankreas" }, { id: 6, name: "Bağırsak" },
];

const IS_WEB = Platform.OS === "web";

/** Kapalı döngü SEANSINDA kare aralığı — hayvan hareket ettikçe duty/faz güncellenmeli. */
const KARE_ARALIK_SEANS_MS = 400;
/**
 * HAZIRLIKTA kare aralığı. Sunucu organ lokalizasyonunu EN FAZLA 10 sn'de bir çalıştırır
 * (`ai_router::_ORGAN_LOCALIZE_INTERVAL_S`); hazırlıkta 400 ms'de bir kare yüklemek her işe
 * yarayan lokalizasyon başına ~25 boşa yükleme demekti (pil, ısınma, mobil veri). Seans hızı
 * DÜŞÜRÜLMEZ — tasarruf yalnız hazırlıkta.
 */
const KARE_ARALIK_HAZIRLIK_MS = 1500;
/** Öneri başarısız olduğunda en erken yeniden deneme aralığı (retry fırtınası koruması). */
const ONERI_BEKLEME_MS = 5000;
/**
 * Öneri istenmeden önce gereken ARDIŞIK doğrulanmış ölçüm.
 *
 * ⚠️ NEDEN: tek bir şanslı kare tedavi parametrelerini tetikliyordu. Konumlandırma tıbbi bir
 * karar girdisidir (faz/duty o koordinattan hesaplanır); üst üste tutarlı ölçüm istemek
 * savunulabilir ve maliyeti yalnız birkaç saniye. `_MIN_RELIABILITY` eşiği DEĞİŞTİRİLMEDİ —
 * yükseltmek yanlış-negatifleri artırır ve gerçek hastayı reddederdi.
 */
const ARDISIK_ONAY = 2;
/** Bu süre sonunda hâlâ bulunamadıysa SOMUT yönlendirme göster (ışık/mesafe/kadraj). */
const HAZIRLIK_UYARI_MS = 45000;
/** Hazırlığın ÜST SINIRI — kare akışı sonsuza kadar pil/veri yakmasın. ⚠️ YALNIZ hazırlık:
 *  süren bir seansı KESMEZ (onun kendi süre-watchdog'u var). */
const HAZIRLIK_TAVAN_MS = 120000;
/** Bu değerin altındaki güven "sınırda" sayılır ve operatöre ayrıca işaretlenir. */
const DUSUK_GUVEN = 0.5;

type Coil = { id: number; freq: number; duty: number; phase: number };
type FrameResult = {
  image_base64?: string;
  detected?: boolean;
  /** Karede hayvan var mı — organ lokalizasyonundan AYRI (bkz. ai_router::_extract_organ_target).
   *  ⚠️ Opsiyonel: eski backend bu alanı göndermez → hazırlık metni "hayvan aranıyor"da kalır,
   *  akış BOZULMAZ (alan yokluğu "kedi yok" gibi davranır ve kullanıcı yine yönlendirilir). */
  catDetected?: boolean;
  perCoil?: Coil[];
  target?: { x: number; y: number; z: number };
  eField?: number;
  organId?: number;
  organName?: string;
  reliability?: number;
};

function fmtSec(sec: number): string {
  const s0 = Math.max(0, Math.floor(sec));
  const m = Math.floor(s0 / 60);
  return `${m}:${String(s0 % 60).padStart(2, "0")}`;
}

// Backend yanıt sözleşmeleri (audit B-10.1) — AI-Pro otonom tedavi uçları.
interface AiProStatus {
  active?: boolean;
  localized?: boolean;
  organId?: number;
  remainingSec?: number;
  /** Seansı BAŞLATAN istemcinin kimliği. ALAN YOKSA = onay/sahiplik öncesi backend (bkz. sync). */
  ownerClientId?: string;
}
interface AiProAction { status?: string }
/** `/api/ai/pro/propose` yanıtı — hekime gösterilecek ve onaylanınca uygulanacak parametreler. */
interface AiProposeResponse {
  proposalId?: string;
  specs?: AiProposalSpecs;
  meta?: AiProposalMeta;
  expiresAt?: number;
}

/** @param patientName Aktif hasta adı — seansın kime uygulandığının denetim izi için backend'e taşınır. */
export function AiProPanel({ patientName = "" }: { patientName?: string }) {
  const { aiVisionData: v } = useLiveData();

  const [organId, setOrganId] = useState(0);
  const [duration, setDuration] = useState("20");
  const [running, setRunning] = useState(false);
  const [localized, setLocalized] = useState(false);
  const [busy, setBusy] = useState(false);
  /**
   * 🔴 HAZIRLIK AŞAMASI (saha bildirimi 2026-08-24) — AI Pro mobilde HİÇ BAŞLAMIYORDU.
   *
   * ÖLÇÜLEN KİLİTLENME: `/ai/pro/propose` TAZE organ lokalizasyonu ister; lokalizasyon ancak bir
   * kare işlenince oluşur; kareler ise YALNIZ `running` iken akıyordu; `running` ise propose'suz
   * başlamıyordu. Döngüsel kilit. Kullanıcıya "Kamerayı hedefe doğrultup 'Yeniden konumla' ile
   * lokalizasyonu tamamlayın" deniyordu — ama o düğme yalnızca sunucuda bir bayrak set ediyor ve
   * kare akmadığı için HİÇBİR ŞEY olmuyordu. Ekran aynı hatayı tekrar tekrar gösteriyordu.
   *
   * ÇÖZÜM: seans başlamadan ÖNCE de kare akıtan bir hazırlık aşaması. Sıra sahip isteğiyle aynı:
   * kedi tespiti → organ tespiti → seçili organ için konuma göre faz/duty önerisi → onay.
   *
   * ⚠️ TIBBİ GÜVENLİK: hazırlık karesi BOBİN SÜRMEZ. Backend sürüşü yalnız onaylanmış ve
   * süre-watchdog'u olan AKTİF seansta yapar (`ai_router::ai_pro_frame` → `session_active`).
   * Hazırlık o kapıyı GEVŞETMEZ; yalnız lokalizasyonun oluşmasını sağlar.
   */
  const [hazirlik, setHazirlik] = useState(false);
  const hazirlikRef = useRef(false);
  useEffect(() => { hazirlikRef.current = hazirlik; }, [hazirlik]);
  /** Hazırlık sırasında öneri BİR KEZ istenir (kareler periyodik geliyor). */
  const oneriIstendiRef = useRef(false);
  /**
   * Öneri BAŞARISIZ olursa bir sonraki denemenin en erken zamanı (ms).
   *
   * ⚠️ NEDEN GEREKLİ: efekt her yeni kareye bağlı. Başarısızlıkta bayrağı hemen sıfırlamak
   * ~kare hızında yeniden deneme (retry fırtınası) ve her denemede bir hata bildirimi demekti —
   * yani düzeltilen arızanın daha hızlı tekrarlayan hâli. Deneme aralıklı, istek SESSİZ, sebep
   * hazırlık şeridinde.
   */
  const oneriBeklemeRef = useRef(0);
  const [oneriHatasi, setOneriHatasi] = useState("");
  /** Ardışık doğrulanmış ölçüm sayacı (bkz. ARDISIK_ONAY). */
  const ardisikRef = useRef(0);
  const [ardisik, setArdisik] = useState(0);
  /** Hazırlığın başladığı an — gecikmede yönlendirme ve üst sınır için. */
  const hazirlikBasRef = useRef(0);
  const [hazirlikGecen, setHazirlikGecen] = useState(0);
  // SERT ONAY KAPISI (2026-08-06): bekleyen AI önerisi + onay/red işlemi sürüyor mu.
  const [proposal, setProposal] = useState<AiProposeResponse | null>(null);
  const [approvalBusy, setApprovalBusy] = useState(false);
  // Onay/red denetim izinde HANGİ HEKİM karar verdi — oturumdaki e-posta taşınır.
  const { session } = useAuth();
  // ⭐ Aktif operatör (tek makine, çoklu veteriner) — oturum e-postası DEĞİL.
  const { operatorEmail } = useOperator();

  // ── Mobil kamera state'i (web'de kullanılmaz) ──
  const [permission, requestPermission] = useCameraPermissions();
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [mobileResult, setMobileResult] = useState<FrameResult | null>(null);
  const [remainingSec, setRemainingSec] = useState(0);
  const cameraRef = useRef<any>(null);
  const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);
  const runningRef = useRef(false);
  useEffect(() => { runningRef.current = running; }, [running]);

  // ⚠️ ÇOK-İSTEMCİ SAHİPLİĞİ (denetim 2026-08-17). Panel `st.active`'i sahiplik sormadan benimsiyor
  // ve unmount cleanup'ında `/ai/pro/stop` gönderiyordu → AI Pro sekmesini yalnızca AÇIP kapatan
  // ikinci istemci (klinik PC'si + telefon, ya da iki veteriner) BAŞKASININ süren otonom seansını
  // kesiyordu: `_stop_session_coils(range(1,9))` koşulsuz → 7 bobin + seans iptal, iki operatöre de
  // gerekçe gösterilmeden.
  // ⚠️ AYNI CİHAZDA sekme değişiminde durdurmak KASITLI ve KORUNUYOR ("panel kapanınca backend
  // bobinleri BAŞSIZ sürmeye devam ediyordu") — bastırma YALNIZ seansı biz başlatmadıysak.
  const ownedRef = useRef(false);
  const clientIdRef = useRef("");
  useEffect(() => {
    getClientInstanceId().then((id) => { clientIdRef.current = id; }).catch(() => {});
  }, []);

  // Backend durumunu senkronla (özellikle süre dolup auto-stop olduğunda).
  useEffect(() => {
    let alive = true;
    const sync = async () => {
      const st = await apiGet<AiProStatus | null>("/ai/pro/status", null, { silent: true });
      if (!alive || !st) return;
      const active = Boolean(st.active);
      // ⚠️ `undefined` = alan YOK = sahiplik öncesi backend → ESKİ davranışı koru (sürüm kayması:
      // yeni istemci + eski backend'de bobinin başsız kalmasını engelle).
      ownedRef.current =
        st.ownerClientId === undefined
          ? active
          : active && !!st.ownerClientId && st.ownerClientId === clientIdRef.current;
      setRunning(active);
      setLocalized(Boolean(st.localized));
      // ORTA fix: organId'yi YALNIZ aktif seansta backend'den senkronla. Seans yokken kullanıcının seçtiği
      // organ'ı 3sn'lik poll EZMESİN (kullanıcı organ seçerken seçim geri zıplıyordu).
      if (active && typeof st.organId === "number") setOrganId(st.organId);
      if (typeof st.remainingSec === "number") setRemainingSec(st.remainingSec);
    };
    sync();
    const id = setInterval(sync, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const start = useCallback(async () => {
    // DENETİM İZİ: AI Pro otonom tedavisi hiçbir hastaya BAĞLANMADAN başlatılabiliyordu —
    // seans kaydı sahipsiz kalıyor, tedavi geçmişinde hangi hayvana uygulandığı bilinmiyordu
    // (klinik izlenebilirlik). ControlScreen'deki `requirePatient` ile aynı yaklaşım: bloklamıyoruz,
    // ama BİLİNÇLİ karar hâline getiriyoruz ve hasta bilgisini backend'e taşıyoruz.
    if (!patientName?.trim()) {
      const go = await platformConfirm(
        "Hasta seçilmedi",
        "Otonom seans hiçbir hastaya bağlanmadan kaydedilecek; seans geçmişinde sahipsiz görünür.\n\nYine de başlatmak istiyor musunuz?",
        "Hastasız başlat"
      );
      if (!go) return;
    }
    setBusy(true);
    // Mobilde önce kamera izni iste (web'de gerek yok — sunucu kamerası).
    if (!IS_WEB) {
      if (!permission?.granted) {
        const p = await requestPermission();
        if (!p?.granted) { setBusy(false); return; }
      }
    }
    // SERT ONAY KAPISI (2026-08-06): doğrudan başlatMIYORUZ. Önce backend'den öneri alınır
    // (donanıma dokunmaz), hekim modalda görüp onaylar, ancak sonra /start çağrılır.
    //
    // 🔴 SIRA DEĞİŞTİ (2026-08-24): mobilde ÖNCE hazırlık. Öneri taze lokalizasyon ister ve
    // lokalizasyon ancak kare akınca oluşur; doğrudan propose çağırmak "Organ henüz lokalize
    // edilmedi" hatasıyla dönüyordu ve kullanıcı o hatadan ÇIKAMIYORDU (bkz. `hazirlik`).
    // Web'de sunucu kamerası zaten sürekli kare üretir → eski davranış korunur.
    if (!IS_WEB) {
      setBusy(false);
      oneriIstendiRef.current = false;
      oneriBeklemeRef.current = 0;
      ardisikRef.current = 0;
      setArdisik(0);
      setOneriHatasi("");
      await apiPost<AiProAction | null>("/ai/pro/calibrate", {}, null);  // taze lokalizasyon iste
      setHazirlik(true);   // kareler akmaya başlar → kedi → organ → öneri (otomatik)
      return;
    }
    const prop = await apiPost<AiProposeResponse | null>(
      "/ai/pro/propose",
      { organ_id: organId, duration_minutes: parseInt(duration) || 20 },
      null
    );
    setBusy(false);
    if (!prop?.proposalId) return;   // apiPost hata mesajını zaten gösterdi (409/422 dahil)
    setProposal(prop);
  }, [organId, duration, permission, requestPermission]);

  /**
   * HAZIRLIK: organ lokalize edilir edilmez öneriyi OTOMATİK iste.
   *
   * Kullanıcı hazırlığı izler ("kedi aranıyor → organ aranıyor → konumlandı") ve ayrıca bir
   * düğmeye daha basmak zorunda kalmaz. ⚠️ Öneri BİR KEZ istenir: kareler 400 ms'de bir geliyor,
   * her karede propose çağırmak sunucuyu ve onay kaydını çöpe boğardı.
   */
  useEffect(() => {
    if (IS_WEB || !hazirlik || oneriIstendiRef.current) return;
    if (!mobileResult?.detected) {
      ardisikRef.current = 0;      // ölçüm koptu → sayaç sıfırlanır (ARDIŞIK olmalı)
      setArdisik(0);
      return;
    }
    // ⚠️ ARDIŞIK DOĞRULAMA: tek bir şanslı kare tedavi parametrelerini tetiklemesin.
    ardisikRef.current += 1;
    setArdisik(ardisikRef.current);
    if (ardisikRef.current < ARDISIK_ONAY) return;
    if (Date.now() < oneriBeklemeRef.current) return;   // bekleme sürüyor → sessizce geç
    oneriIstendiRef.current = true;
    (async () => {
      // ⚠️ SESSİZ: hata metnini biz hazırlık şeridinde gösteriyoruz. Sessiz olmasaydı her
      // başarısız denemede ekrana bir "Sunucu Hatası" bildirimi düşerdi.
      const prop = await apiPost<AiProposeResponse | null>(
        "/ai/pro/propose",
        { organ_id: organId, duration_minutes: parseInt(duration) || 20 },
        null,
        { silent: true }
      );
      if (prop?.proposalId) {
        setOneriHatasi("");
        setProposal(prop);
        setHazirlik(false);   // öneri hazır → hazırlık biter; kareler seans başlayınca sürer
      } else {
        // Öneri alınamadı (ör. model bu konum için sürülebilir parametre üretmedi): hazırlıkta
        // KAL ve tekrar denenebilsin — ama ARALIKLI (bkz. oneriBeklemeRef).
        setOneriHatasi("Öneri alınamadı — konumlandırma sürüyor, tekrar denenecek.");
        oneriBeklemeRef.current = Date.now() + ONERI_BEKLEME_MS;
        oneriIstendiRef.current = false;
      }
    })();
    // ⚠️ BAĞIMLILIK `mobileResult` NESNESİDİR, `.detected` DEĞİL (ölçülerek bulundu):
    // `.detected` bir boolean; `true` olduktan sonra DEĞİŞMEZ, dolayısıyla efekt bir daha
    // koşmaz, ardışık sayaç 1'de takılır ve öneri HİÇ istenmezdi — yani sertleştirme akışı
    // tamamen durdururdu. Her kare yeni bir nesne döndürdüğü için kimlik değişir ve sayaç işler.
  }, [hazirlik, mobileResult, organId, duration]);

  /**
   * HAZIRLIK SAATİ — gecikmede somut yönlendirme, üst sınırda otomatik durma.
   *
   * ⚠️ Üst sınır YALNIZ hazırlığa aittir: süren bir otonom seansı KESMEZ (onun kendi
   * süre-watchdog'u var). Amaç, hayvan hiç bulunamazken kare akışının sonsuza kadar pil/ısı/veri
   * yakmasını engellemek ve operatörü çıkışsız bırakmamak.
   */
  useEffect(() => {
    if (!hazirlik) { setHazirlikGecen(0); hazirlikBasRef.current = 0; return; }
    hazirlikBasRef.current = Date.now();
    setHazirlikGecen(0);
    const id = setInterval(() => {
      const gecen = Date.now() - hazirlikBasRef.current;
      setHazirlikGecen(gecen);
      if (gecen >= HAZIRLIK_TAVAN_MS) {
        setHazirlik(false);
        oneriIstendiRef.current = false;
        ardisikRef.current = 0;
        setOneriHatasi("");
        platformAlert(
          "Konumlandırma tamamlanamadı",
          "Hayvan iki dakikadır kadrajda bulunamadı; kamera durduruldu (pil koruması). " +
            "Ortamın ışığını artırın, telefonu 1-2 metre mesafeye getirin ve hayvanı kadraja tam alın, " +
            "sonra tekrar başlatın."
        );
      }
    }, 1000);
    return () => clearInterval(id);
  }, [hazirlik]);

  /** Hekim ONAYLADI → onayı işaretle, sonra mühürlenmiş parametrelerle tedaviyi başlat. */
  const approveAndStart = useCallback(async () => {
    if (!proposal?.proposalId) return;
    setApprovalBusy(true);
    const ok = await apiPost<{ status?: string } | null>(
      "/ai/pro/approve",
      { proposal_id: proposal.proposalId, operator_email: operatorEmail || "" },
      null
    );
    if (!ok) { setApprovalBusy(false); return; }   // onay geçmediyse BAŞLATMA
    const res = await apiPost<AiProAction | null>(
      "/ai/pro/start",
      { proposal_id: proposal.proposalId, patient_name: patientName || "", client_id: clientIdRef.current },
      null
    );
    setApprovalBusy(false);
    if (res?.status === "success") {
      ownedRef.current = true;   // seansı BİZ başlattık → unmount'ta durdurma yetkisi doğar
      setRunning(true);
      setProposal(null);
    }
    // Başlatma başarısızsa modal AÇIK kalır: onay tüketilmiş olabilir, hekim yeni öneri alır.
  }, [proposal, operatorEmail, patientName]);

  /** Hekim REDDETTİ → gerekçeyle kaydet; tedavi BAŞLAMAZ. */
  const rejectProposal = useCallback(async (reason: string) => {
    if (!proposal?.proposalId) return;
    setApprovalBusy(true);
    await apiPost("/ai/pro/reject",
      { proposal_id: proposal.proposalId, operator_email: operatorEmail || "", reason },
      null);
    setApprovalBusy(false);
    setProposal(null);
  }, [proposal, operatorEmail]);

  const stop = useCallback(async () => {
    setBusy(true);
    // apiPost hata/zaman-aşımı/non-2xx'te fallback (null) döndürür, THROW ETMEZ. Bu yüzden
    // durdurma DOĞRULANMADAN running'i false yapmak, bobinler sürerken UI'nin "durdu" göstermesine
    // yol açar. Yanıt gelmediyse durumu değiştirme (3sn status-poll gerçeği yansıtsın) + uyar.
    const res = await apiPost<AiProAction | null>("/ai/pro/stop", {}, null);
    if (res) {
      setRunning(false);
      setMobileResult(null);
    } else {
      platformAlert(
        "Durdurulamadı",
        "Otonom seans durdurma komutu sunucuya ulaşmadı. Bağlantıyı kontrol edip tekrar deneyin; sorun sürerse ACİL DURDUR kullanın."
      );
    }
    setBusy(false);
  }, []);

  const changeOrgan = useCallback(async (id: number) => {
    setOrganId(id);
    // DÜŞÜK fix: sessiz yutma yerine başarısızlıkta uyar (komut ulaşmadıysa kullanıcı bilsin).
    const res = await apiPost<AiProAction | null>("/ai/pro/organ", { organ_id: id }, null);
    if (!res) platformAlert("Organ değiştirilemedi", "Komut sunucuya ulaşmadı — tekrar deneyin.");
  }, []);

  const relocalize = useCallback(async () => {
    // Bir sonraki karede cat_organ organ-lokalizasyonunu zorla tazele (avuç-Z kalibrasyonu KALKTI).
    const res = await apiPost<AiProAction | null>("/ai/pro/calibrate", {}, null);
    if (!res) {
      platformAlert("Yeniden konumlandırılamadı", "Komut sunucuya ulaşmadı — tekrar deneyin.");
      return;
    }
    // 🔴 2026-08-24: bu düğme YALNIZ sunucuda bayrak set ediyordu. Mobilde kareler seans
    // başlamadan akmadığı için bayrağı işleyecek kare HİÇ gelmiyordu → düğme görsel olarak
    // çalışıyor ama lokalizasyon hiç olmuyordu. Üstelik kullanıcıya hata mesajında tam da bu
    // düğmeye basması söyleniyordu. Artık kare akışını da başlatır.
    if (!IS_WEB && !running) {
      oneriIstendiRef.current = false;
      setHazirlik(true);
    }
  }, [running]);

  // ── Mobil: telefon kamerasından periyodik kare yakala → /ai/ai_pro/frame ──
  useEffect(() => {
    // ⚠️ `hazirlik` ŞART: yalnız `running` iken akıtmak, propose→lokalizasyon→kare→seans
    // döngüsel kilidini yaratıyordu (bkz. `hazirlik` açıklaması).
    if (IS_WEB || (!running && !hazirlik)) return;
    const capture = async () => {
      if (inFlightRef.current || !cameraRef.current) return;
      if (!runningRef.current && !hazirlikRef.current) return;
      inFlightRef.current = true;
      try {
        const photo = await cameraRef.current.takePictureAsync({ quality: 0.5, base64: true, skipProcessing: true });
        if (photo?.base64) {
          const fd = new FormData();
          fd.append("image_base64", photo.base64);
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 15000);
          const headers: Record<string, string> = { Accept: "application/json" };
          if (serviceConfig.apiToken) headers["X-API-Key"] = serviceConfig.apiToken;
          const r = await fetch(serviceConfig.apiBaseUrl + "/ai/ai_pro/frame", {
            method: "POST", body: fd, headers, signal: ctrl.signal,
          });
          clearTimeout(t);
          const data = await r.json();
          if (r.ok && data?.status === "success") setMobileResult(data);
        }
      } catch {
        /* canlı modda kare hatalarını sessiz geç */
      } finally {
        inFlightRef.current = false;
      }
    };
    captureIntervalRef.current = setInterval(capture, running ? KARE_ARALIK_SEANS_MS : KARE_ARALIK_HAZIRLIK_MS);
    return () => {
      if (captureIntervalRef.current) {
        clearInterval(captureIntervalRef.current);
        captureIntervalRef.current = null;
      }
    };
  }, [running, hazirlik]);

  // Unmount'ta: interval'i temizle + ÇALIŞAN otonom tedaviyi DURDUR.
  // YÜKSEK fix: panel kapanınca (tab/modül değişimi) backend bobinleri BAŞSIZ sürmeye devam ediyordu
  // (operatör göremez/kontrol edemez = güvenlik riski). runningRef güncel durumu tutar (cleanup closure'u
  // stale 'running' yakalamasın). Best-effort fire-and-forget stop (unmount'ta await edilemez).
  useEffect(() => () => {
    if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
    // ⚠️ `ownedRef` ŞART: seansı biz başlatmadıysak BAŞKASININ tedavisini kesmeyiz.
    // Operatörün AÇIK "Durdur" dokunuşu (`stop()`) bu koşuldan ETKİLENMEZ — her istemcinin
    // operatörü tedaviyi durdurabilmeli.
    if (runningRef.current && ownedRef.current) {
      apiPost<AiProAction | null>("/ai/pro/stop", {}, null).catch(() => {});
    }
  }, []);

  // ── Görüntülenecek değerler: web = WS (aiVisionData), mobil = HTTP yanıtı ──
  const detected = IS_WEB ? Boolean(v?.detected) : Boolean(mobileResult?.detected);
  const reliability = IS_WEB ? (v as any)?.reliability : mobileResult?.reliability;
  const targetX = IS_WEB ? v?.target?.x : mobileResult?.target?.x;
  const targetY = IS_WEB ? v?.target?.y : mobileResult?.target?.y;
  const targetZ = IS_WEB ? v?.target?.z : mobileResult?.target?.z;
  const overlayB64 = IS_WEB ? v?.imageBase64 : mobileResult?.image_base64;
  const perCoil: Coil[] = (IS_WEB ? v?.perCoil : mobileResult?.perCoil) ?? [];
  const remaining = IS_WEB ? (v?.remainingSec ?? 0) : remainingSec;

  /**
   * HAZIRLIK AŞAMA METNİ (sahip isteği 2026-08-24: "önce kedi tespiti ardından organ tespiti").
   *
   * Üç durum AYRI şey söyler; hepsi "bulunamadı" altında birleştiğinde operatör NE YAPACAĞINI
   * bilemiyordu:
   *   · kedi yok        → kadrajda hayvan yok, kamerayı ona doğrult
   *   · kedi var, organ yok → hayvan görünüyor ama o organ (açı/okluzyon) seçilemiyor → açıyı değiştir
   *   · konumlandı      → parametreler hesaplanıyor
   */
  const catDetected = IS_WEB ? Boolean((v as any)?.catDetected) : Boolean(mobileResult?.catDetected);
  const organAdi = ORGANS.find((o) => o.id === organId)?.name ?? "";
  /** Güven yüzdesi — ⚠️ eşik 0,3 olduğu için "konumlandı" %30 da olabilir; operatör SAYIYI görmeli. */
  const guvenYuzde = Math.round((Number(reliability) || 0) * 100);
  const dusukGuven = detected && (Number(reliability) || 0) < DUSUK_GUVEN;
  /** Gecikmede SOMUT yönlendirme (yalnız "tekrar deneyin" demek işe yaramaz). */
  const gecikmeIpucu =
    hazirlik && hazirlikGecen >= HAZIRLIK_UYARI_MS
      ? " · Bulunamıyor: ortamın ışığını artırın, 1-2 metre mesafeye gelin, hayvanı kadraja tam alın."
      : "";
  const asamaMetni = !hazirlik
    ? ""
    : detected
      ? ardisik < ARDISIK_ONAY
        ? `✓ ${organAdi} görüldü — doğrulanıyor (${ardisik}/${ARDISIK_ONAY}) · ikinci ölçüm bekleniyor…`
        : `✓ ${organAdi} konumlandı — güven %${guvenYuzde}${dusukGuven ? " ⚠️ sınırda" : ""} · öneri hesaplanıyor…`
      : catDetected
        ? `🔎 Hayvan görünüyor, ${organAdi} aranıyor… (kamerayı biraz çevirin)${gecikmeIpucu}`
        : `🐾 Hayvan aranıyor… kamerayı hastaya doğrultun${gecikmeIpucu}`;

  return (
    <View style={styles.wrap}>
      {/* SERT ONAY KAPISI (2026-08-06): AI önerisi hekime gösterilir; onaylanmadan seans
          BAŞLAMAZ. Kapatmak reddetmek DEĞİLdir — öneri süresi dolunca kendiliğinden düşer. */}
      <AiSpecApprovalModal
        visible={!!proposal}
        specs={proposal?.specs ?? null}
        meta={proposal?.meta ?? null}
        organName={ORGANS.find((o) => o.id === (proposal?.specs?.organ_id ?? organId))?.name}
        busy={approvalBusy}
        onApprove={approveAndStart}
        onReject={rejectProposal}
        onDismiss={() => setProposal(null)}
      />
      <Text style={styles.note}>
        {IS_WEB
          ? "📷 Sunucu kamerasından canlı otonom seans: kedi organ lokalizasyonu → em_kedi → 7 bobin."
          : "📷 Telefon kameranızı KEDİYE doğrultun — organ lokalizasyonu (em_kedi) ile 7 bobin per-coil sürülür."}
      </Text>

      {/* Kamera görüntüsü: web = sunucudan (Image), mobil = telefon kamerası (CameraView) */}
      <View style={styles.camBox}>
        {IS_WEB ? (
          overlayB64 ? (
            <Image source={{ uri: `data:image/jpeg;base64,${overlayB64}` }} style={styles.cam} resizeMode="contain" />
          ) : (
            <Text style={styles.camPlaceholder}>{running ? "Görüntü bekleniyor…" : "AI Pro durdu."}</Text>
          )
        ) : (running || hazirlik) && permission?.granted ? (
          // ⚠️ `hazirlik` ŞART (2026-08-24): kamera YALNIZ `running` iken monte ediliyordu →
          // hazırlık aşamasında `cameraRef.current` null kalıyor ve kare HİÇ çekilemiyordu.
          // Kare akışı düzeltilse bile bu tek başına lokalizasyonu imkânsız kılardı (aynı
          // kilitlenmenin ikinci halkası).
          <View style={styles.cam}>
            <CameraView ref={cameraRef} style={styles.cam} facing={facing} />
            {overlayB64 ? (
              <Image source={{ uri: `data:image/jpeg;base64,${overlayB64}` }} style={styles.camOverlay} resizeMode="contain" />
            ) : null}
            <TouchableOpacity style={styles.flipBtn} onPress={() => setFacing((f) => (f === "back" ? "front" : "back"))}
              accessibilityRole="button" accessibilityLabel="Kamerayı çevir (ön/arka)">
              <Text style={styles.flipText}>🔄</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <Text style={styles.camPlaceholder}>
            {running || hazirlik ? "Kamera izni bekleniyor…" : "AI Pro durdu. Başlat → kamera açılır."}
          </Text>
        )}
      </View>

      {/* Canlı metrikler */}
      <View style={styles.metricRow}>
        <Metric label="Organ" value={detected ? "✓ Bulundu" : "—"} />
        <Metric label="Güven" value={typeof reliability === "number" ? `%${Math.round(reliability * 100)}` : "—"} />
        <Metric label="X (mm)" value={`${targetX ?? "—"}`} />
        <Metric label="Y (mm)" value={`${targetY ?? "—"}`} />
        <Metric label="Z (mm)" value={`${targetZ ?? "—"}`} />
      </View>

      {/* HAZIRLIK ŞERİDİ — aşamayı ve çıkış yolunu gösterir (2026-08-24). */}
      {hazirlik ? (
        <View style={[styles.hazirlikKutu, dusukGuven && styles.hazirlikKutuUyari]}>
          <Text style={styles.hazirlikMetin} numberOfLines={3}>{oneriHatasi || asamaMetni}</Text>
          <TouchableOpacity
            style={styles.hazirlikIptal}
            onPress={() => { setHazirlik(false); oneriIstendiRef.current = false; oneriBeklemeRef.current = 0; ardisikRef.current = 0; setArdisik(0); setOneriHatasi(""); }}
            accessibilityRole="button"
            accessibilityLabel="Hazırlığı iptal et"
          >
            <Text style={styles.hazirlikIptalMetin}>Vazgeç</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* Organ seçimi */}
      <Text style={styles.label}>🧠 Hedef Organ</Text>
      <View style={styles.organGrid}>
        {ORGANS.map((o) => (
          <TouchableOpacity
            key={o.id}
            style={[styles.organChip, organId === o.id && styles.organChipActive]}
            onPress={() => changeOrgan(o.id)}
            accessibilityRole="button"
            accessibilityState={{ selected: organId === o.id }}
            accessibilityLabel={`Hedef organ: ${o.name}`}
          >
            <Text style={[styles.organText, organId === o.id && styles.organTextActive]}>{o.name}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Süre + kalibrasyon */}
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>⏱ Süre (dk)</Text>
          <TextInput style={styles.input} value={duration} onChangeText={setDuration} keyboardType="numeric" editable={!running} selectTextOnFocus />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Kalan</Text>
          <Text style={styles.countdown}>{running ? fmtSec(remaining) : "—"}</Text>
        </View>
        <View style={{ flex: 1, justifyContent: "flex-end" }}>
          <TouchableOpacity
          style={[styles.calBtn, localized && styles.calBtnDone]}
          onPress={relocalize}
          accessibilityRole="button"
          accessibilityLabel={localized ? "Hedef organ konumlandırıldı, yeniden konumla" : "Hedef organı yeniden konumla"}
        >
            <Text style={styles.calBtnText} numberOfLines={1} adjustsFontSizeToFit>{localized ? "✓ Konumlandı" : "🎯 Yeniden Konumla"}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Start / Stop */}
      {/* a11y: otonom TEDAVİ başlatan/durduran düğmede rol ve etiket yoktu → ekran okuyucu
          kullanan operatör butonu ayırt edemiyordu. Durum da `accessibilityState` ile bildirilir. */}
      <TouchableOpacity
        style={[styles.toggle, running ? styles.toggleStop : styles.toggleStart, busy && { opacity: 0.5 }]}
        onPress={running ? stop : start}
        disabled={busy}
        accessibilityRole="button"
        accessibilityState={{ busy, selected: running }}
        accessibilityLabel={running ? "AI Pro otonom seansı durdur" : "AI Pro otonom seansı başlat"}
        accessibilityHint={running ? "Bobinleri durdurur" : "Kamera kapalı-döngüsüyle bobinleri otomatik sürer"}
      >
        <Text style={styles.toggleText} numberOfLines={1} adjustsFontSizeToFit>{running ? "⏹ AI Pro'yu Durdur" : hazirlik ? "🔎 Hazırlanıyor…" : "🚀 AI Pro Başlat (1Hz DDS)"}</Text>
      </TouchableOpacity>

      {/* Per-coil diagnostik tablo (7 bobin; bobin 8 kapalı) */}
      <Text style={styles.label}>📊 Bobin Diagnostiği</Text>
      <View style={styles.table}>
        <View style={styles.tr}>
          <Text style={[styles.th, { flex: 1 }]}>Bobin</Text>
          <Text style={[styles.th, { flex: 1 }]}>Frekans</Text>
          <Text style={[styles.th, { flex: 1 }]}>Duty</Text>
          <Text style={[styles.th, { flex: 1 }]}>Faz</Text>
        </View>
        {(perCoil.length ? perCoil : Array.from({ length: 7 }, (_, i) => ({ id: i + 1, freq: 0, duty: 0, phase: 0 }))).map((c) => (
          <View key={c.id} style={styles.tr}>
            <Text style={[styles.td, { flex: 1 }]}>{c.id}</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.freq} Hz</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.duty}%</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.phase}°</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md },
  note: { color: colors.textMuted, fontSize: typography.small, fontStyle: "italic" },
  camBox: {
    height: rs(200), backgroundColor: "#000", borderRadius: 12,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
    borderWidth: 1, borderColor: "#1e3a5f",
  },
  cam: { width: "100%", height: "100%" },
  camOverlay: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, width: "100%", height: "100%" },
  camPlaceholder: { color: colors.textMuted, fontSize: typography.small },
  flipBtn: {
    position: "absolute", top: 8, right: 8, backgroundColor: "rgba(0,0,0,0.5)",
    borderRadius: 16, width: rs(32), height: rs(32), alignItems: "center", justifyContent: "center",
  },
  flipText: { fontSize: rf(16) },
  metricRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  metric: { flex: 1, backgroundColor: "#0f172a", borderRadius: 8, padding: spacing.sm, alignItems: "center" },
  metricLabel: { color: colors.textMuted, fontSize: rf(10), fontWeight: "700" },
  metricValue: { color: colors.primary, fontSize: typography.body, fontWeight: "800" },
  label: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", marginBottom: spacing.xs },
  organGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  organChip: {
    backgroundColor: "#1e293b", borderRadius: 16, paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderWidth: 1, borderColor: "#334155",
  },
  organChipActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  organText: { color: colors.textMuted, fontSize: typography.small },
  organTextActive: { color: "#fff", fontWeight: "700" },
  row: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  input: {
    backgroundColor: "#1e293b", borderRadius: 8, padding: spacing.sm, color: colors.text,
    fontWeight: "700", borderWidth: 1, borderColor: "#334155", textAlign: "center",
  },
  countdown: { color: colors.primary, fontSize: typography.subtitle, fontWeight: "800", textAlign: "center", paddingVertical: spacing.xs },
  hazirlikKutu: {
    backgroundColor: "#1e3a5f", borderRadius: 10, padding: spacing.sm, marginBottom: spacing.sm,
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
  },
  hazirlikKutuUyari: { backgroundColor: "#78350f" },   // sınırda güven → görsel uyarı
  hazirlikMetin: { color: "#dbeafe", fontWeight: "700", fontSize: typography.small, flex: 1 },
  hazirlikIptal: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 6, backgroundColor: "#334155" },
  hazirlikIptalMetin: { color: "#e2e8f0", fontWeight: "700", fontSize: typography.small },
  calBtn: { backgroundColor: "#334155", borderRadius: 8, padding: spacing.sm, alignItems: "center" },
  calBtnDone: { backgroundColor: "#15803d" },
  calBtnText: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  toggle: { borderRadius: 12, padding: spacing.md, alignItems: "center" },
  toggleStart: { backgroundColor: "#7c3aed" },
  toggleStop: { backgroundColor: "#ef4444" },
  toggleText: { color: "#fff", fontWeight: "800", fontSize: typography.body },
  table: { backgroundColor: "#0f172a", borderRadius: 10, overflow: "hidden", borderWidth: 1, borderColor: "#1e293b" },
  tr: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#1e293b" },
  th: { color: colors.textMuted, fontSize: rf(11), fontWeight: "800", padding: spacing.sm },
  td: { color: colors.text, fontSize: typography.small, padding: spacing.sm },
});
