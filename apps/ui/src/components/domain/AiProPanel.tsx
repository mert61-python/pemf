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
import { useAppNav } from "@/context/AppNavContext";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { View, Text, StyleSheet, TouchableOpacity, Image, TextInput, Platform } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { kabinKamerasiKullanilir, KosulSecici } from "@/components/domain/AnalizKosulu";
import { KabinKamerasiKarti } from "@/components/domain/KabinKamerasiKarti";
import { colors, spacing, typography, rf, rs, touch } from "@/theme/tokens";
import { kameraKutusu, kareOrani } from "@/utils/kameraKutusu";
import { type HedefModeli, MODUL_GEREKSINIMI, modelProfili } from "@/components/domain/aiProProfilleri";
import { AdimGostergesi, type Adim } from "@/components/domain/aipro/AdimGostergesi";
import { ModelSecimKartlari, type KurulumDurumu } from "@/components/domain/aipro/ModelSecimKartlari";
import { HedefHalkalari, HedefListesi, type HedefAdayi } from "@/components/domain/aipro/HedefSecici";
import { KalibrasyonRozeti } from "@/components/domain/aipro/KalibrasyonRozeti";
import { useResponsive } from "@/hooks/useResponsive";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet, apiPost, platformAlert, platformConfirm } from "@/services/apiClient";
import { getClientInstanceId, serviceConfig } from "@/services/config";
import { useAuth } from "@/context/AuthContext";
import { AiSpecApprovalModal, type AiProposalMeta, type AiProposalSpecs } from "@/components/domain/AiSpecApprovalModal";
import { GenisletilebilirMetin } from "@/components/ui/GenisletilebilirMetin";
import { degerAdi } from "@/utils/aiDetail";
import { useTranslation } from "react-i18next";
import i18n, { type TFunction } from "i18next";

const organListesi = (t: TFunction) => [
  { id: 0, name: t("ai.organ.ad.tumVucut") }, { id: 1, name: t("ai.organ.ad.mide") }, { id: 2, name: t("ai.organ.ad.bobrek") },
  { id: 3, name: t("ai.organ.ad.karaciger") }, { id: 4, name: t("ai.organ.ad.mesane") }, { id: 5, name: t("ai.organ.ad.pankreas") }, { id: 6, name: t("ai.organ.ad.bagirsak") },
];

/** Ondalık ayırıcı dile uyar: TR "0,13", EN "0.13" (kodda nokta). */
const ondalik = (n: number, basamak: number): string => n.toFixed(basamak).replace(".", i18n.language === "en" ? "." : ",");

const IS_WEB = Platform.OS === "web";

/** Y142 (sahip 2026-10-13): kedi AI Pro sürüşü kapalıyken gösterilen NEDEN + EYLEM (backend `KEDI_AIPRO_SURUS_KAPALI_MESAJI`
 *  ile aynı metin; öneri yanıtı kendi metnini taşırsa o gösterilir). */
const kediSurusKapaliMetni = (): string => i18n.t("ai.pro.kediSurusKapali");

/** Y142: bu öneriyle sürüş başlatılabilir mi? Öneri yanıtı (`surusAcik: false`) YA DA durum ucu (`kediAiProSurusAcik: false`,
 *  kedi önerisi) kapalı diyorsa kapalı (ikisinden biri yeter). Alanlar yoksa (eski backend) "" = eski davranış. → neden metni. */
function oneriSurusuKapali(oneri: AiProposeResponse | null, kediSurusAcik: boolean | null): string {
  if (!oneri) return "";
  if (oneri.surusAcik === false) return oneri.surusKapaliNedeni || kediSurusKapaliMetni();
  if (String(oneri.specs?.model || "kedi") === "kedi" && kediSurusAcik === false) return kediSurusKapaliMetni();
  return "";
}

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

// D1.84 (B-5.2 · Y25): `suruldu` — bobin telde GERÇEKTEN sürüldü mü (backend `update_coil` kabulü). Opsiyonel: eski backend
// göndermez → eski gösterim (sürüm kayması). `false` → "sürülmedi" (plan değeri parantezde).
// Y54 (sahip): `planDisi` — operatör bu bobini AI Pro sürerken durdurdu; seans sonuna dek AI Pro onu SÜRMEZ.
type Coil = { id: number; freq: number; duty: number; phase: number; suruldu?: boolean; planDisi?: boolean };
type FrameResult = {
  image_base64?: string;
  /** [S7 adım 4] Kodlanan karenin gerçek boyutu (oran kilidi). Eski backend göndermez. */
  image_w?: number;
  image_h?: number;
  detected?: boolean;
  /** Karede hayvan var mı — organ lokalizasyonundan AYRI (bkz. ai_router::_extract_organ_target).
   *  ⚠️ Opsiyonel: eski backend bu alanı göndermez → hazırlık metni "hayvan aranıyor"da kalır,
   *  akış BOZULMAZ (alan yokluğu "kedi yok" gibi davranır ve kullanıcı yine yönlendirilir). */
  catDetected?: boolean;
  /** Lokalizasyon damgası (cache 'at') — panel ardisik sayacını EKO karelerden ayırır (F2, denetim
   *  2026-08-24). ⚠️ Opsiyonel: eski backend göndermezse damga-kapısı devre dışı, kare-başı sayıma
   *  düşülür (geriye-uyum; kilitlenme yok — catDetected/ownerClientId sürüm-kayması deseni). */
  localizedAt?: number;
  perCoil?: Coil[];
  target?: { x: number; y: number; z: number };
  eField?: number;
  organId?: number;
  organName?: string;
  reliability?: number;
  /** Sunum-katmanı XAI (2026-08-26): güvenin bileşen dökümü — "Güven %X"in NEDENİ.
   *  ⚠️ Opsiyonel: eski backend göndermez → satır gizlenir (sürüm-kayması geriye-uyumu). */
  guvenDokumu?: GuvenDokumu | null;
  /** [B1] Bu istemci AKTİF seansın sahibi DEĞİL (başka operatör başlattı) → kareleri bobin SÜRMEZ,
   *  panel "yalnız görüntüleme" gösterir. ⚠️ Opsiyonel: eski backend göndermez → undefined = eski
   *  davranış (sürüm-kayması geriye-uyumu). */
  foreignViewer?: boolean;
  /** [B1] Bu kare gerçekten bobin sürdü mü (sahip + localized + aktif seans). */
  driven?: boolean;
};

/**
 * ARAŞTIRMA hazırlık şeridi (fantom / petri) — kedi bloğundan AYRI tutulur.
 *
 * ⚠️ NEDEN AYRI FONKSİYON: kedi `asamaMetni` bloğu, dört aşamanın birbirinden ayırt edilebilir
 * kaldığını kanıtlayan bir kaynak-regex kapısına bağlıdır (tests/test_ai_pro_asamali_akis.py:362 —
 * blokta TAM 4 aşama anahtarı çağrısı sayar). Araştırma dallarını o bloğa eklemek kapıyı kırar ve
 * kedinin doğrulama/konumlandı ayrımının korunduğunu kimse ölçmez olurdu.
 *
 * Aşamalar kediyle AYNI mantıkta ama özneyi ve eylemi model adıyla söyler: özne yok → yerleşim,
 * özne var/hedef yok → ışık ve işaret, hedef var/konum ölçülemedi → kabin işareti, konumlandı →
 * öneri hesaplanıyor.
 */
function asamaMetniArastirma(a: {
  ozne: string;
  ozneIpucu: string;
  hedefEtiketi: string;
  hedefEtiketiKucuk: string;
  ozneVar: boolean;
  localized: boolean;
  hedefSayisi: number;
  yontem: string;
  guvenYuzde: number;
  gecikmeIpucu: string;
}): string {
  if (a.localized) {
    return i18n.t("ai.pro.asamaArastirma.konumlandi", { hedefEtiketi: a.hedefEtiketi, guvenYuzde: a.guvenYuzde });
  }
  if (!a.ozneVar) {
    return i18n.t("ai.pro.asamaArastirma.ozneAraniyor", { ozne: a.ozne, ozneIpucu: a.ozneIpucu, gecikmeIpucu: a.gecikmeIpucu });
  }
  if (a.hedefSayisi > 0 && a.yontem && a.yontem !== "aruco_pnp") {
    return i18n.t("ai.pro.asamaArastirma.konumOlculemedi", { hedefEtiketi: a.hedefEtiketi });
  }
  return i18n.t("ai.pro.asamaArastirma.hedefAraniyor", {
    ozne: a.ozne,
    hedefEtiketiKucuk: a.hedefEtiketiKucuk,
    gecikmeIpucu: a.gecikmeIpucu,
  });
}

function fmtSec(sec: number): string {
  const s0 = Math.max(0, Math.floor(sec));
  const m = Math.floor(s0 / 60);
  return `${m}:${String(s0 % 60).padStart(2, "0")}`;
}

/** Sunum-katmanı XAI (2026-08-26): pipeline guven_dokumu_hesapla bileşenleri.
 *  reliability = pose_confidence × depth_factor × mask_factor × uncertainty_factor,
 *  kalibrasyonsuzken min(·, calibration_cap=0.25). */
interface GuvenDokumu {
  pose_confidence?: number;
  depth_factor?: number;
  mask_factor?: number;
  uncertainty_factor?: number;
  calibration_cap?: number | null;
  /** AI1.K3 (hoca kedi organ v2 ara çıktıları): hattın kalite göstergeleri — alan yoksa (eski backend) gösterilmez. */
  poz_turu?: string | null;
  pnp_hata_px?: number | null;
  /** AII-2.7: PnP uyum hatası kedi gövdesi biriminde (residual_px / scale_px_per_cm) — çözünürlükten bağımsız. px GÖSTERİLMEZ
   *  (aynı kedi 4032 / 1008 px'te 231 / 49 px: sayı kamerayı ölçüyordu); ölçek yoksa (eski servis) sayı yok. */
  pnp_hata_cm?: number | null;
  ayna_uyarisi?: boolean;
  anatomik_gecti?: boolean | null;
  anatomik_skor?: number | null;
}

/** AI1.K3: güven dökümünün hat-kalitesi eki. Sorun varsa operatöre NE YAPACAĞINI söyler; yalnız gösterim (güven/sürüş değişmez). */
function hatKalitesiMetni(g: GuvenDokumu): string {
  return (
    (g.poz_turu ? i18n.t("ai.pro.guven.pozTuru", { tur: degerAdi(g.poz_turu) }) : "") +
    (typeof g.pnp_hata_cm === "number" ? i18n.t("ai.pro.guven.pnpHata", { cm: ondalik(g.pnp_hata_cm, 1) }) : "") +
    (g.ayna_uyarisi ? i18n.t("ai.pro.guven.ayna") : "") +
    (g.anatomik_gecti === false
      ? i18n.t("ai.pro.guven.anatomikTutarsiz")
      : g.anatomik_gecti === true
        ? i18n.t("ai.pro.guven.anatomikGecti")
        : "")
  );
}

// Backend yanıt sözleşmeleri (audit B-10.1) — AI-Pro otonom tedavi uçları.
interface AiProStatus {
  active?: boolean;
  localized?: boolean;
  organId?: number;
  remainingSec?: number;
  /** Sunum-katmanı XAI (2026-08-26): güven dökümü — alan yoksa (eski backend) satır gizlenir. */
  guvenDokumu?: GuvenDokumu | null;
  /** Seansı BAŞLATAN istemcinin kimliği. ALAN YOKSA = onay/sahiplik öncesi backend (bkz. sync). */
  ownerClientId?: string;
  /** Karede hayvan var mı (cache) — B3: web hazırlık metni WS yerine BURADAN da beslenir. */
  catDetected?: boolean;
  /** B3 (siyah ekran): sunucu önizleme thread'i canlı mı. ⚠️ Opsiyonel: eski backend göndermez. */
  hazirlikActive?: boolean;
  /** B3: önizleme kamera/model hatasıyla öldüyse NEDENİ (boş = hata yok). Doluysa panel hazırlığı
   *  sonlandırıp operatöre gösterir — 120 sn "Hazırlanıyor…" kör bekleyişi yerine. */
  hazirlikHata?: string;
  // ── Araştırma hattı (Faz 2/3 yalnız-ek alanları; kedi hattında boş/varsayılan) ──
  /** Aktif hedef modeli ("kedi" | "fantom" | "petri"). */
  model?: string;
  /** Kare üstünde seçilebilir hedef adayları (kalıcı kimlikli). */
  targets?: HedefAdayi[];
  /** 3B konum yöntemi — "aruco_pnp" = kabin işaretiyle ölçüldü. */
  method?: string;
  /** Seçili hedefin adı ("Tümör 1", "Kuyu 3 · Kanserli"). */
  targetLabel?: string;
  /** Konum modelin eğitim aralığı dışında mı (onay ekranı uyarısı). */
  ood?: boolean;
  /** Kadrajda aranan öznenin adı ("fantom", "petri plakası"). */
  subjectLabel?: string;
  /** Özne kadrajda mı (kedi hattındaki `catDetected`in model-bağımsız adı). */
  subjectDetected?: boolean;
  /** Araştırma modelleriyle SÜRÜŞ açık mı (`PEMF_ARASTIRMA_AIPRO`). Alan yoksa bilinmiyor. */
  arastirmaAiProAcik?: boolean;
  /** T-f (Y195): FANTOM AI Pro sürüşü açık mı (`PEMF_ARASTIRMA_AIPRO_FANTOM`, ayrı bayrak). Alan yoksa (eski backend) `arastirmaAiProAcik`. */
  arastirmaAiProFantomAcik?: boolean;
  /** Hazırlık hatasının SINIFI (kamera / model_paketi / model_yukleme / zaman_asimi). */
  hazirlikHataKodu?: string;
  /** Y142: kedi AI Pro kapalı döngü sürüşü açık mı (`PEMF_KEDI_AIPRO_SURUS`). Alan yoksa bilinmiyor → eski davranış. */
  kediAiProSurusAcik?: boolean;
  /** T3 · Y189: etkin sağlayıcı KOŞULSUZ kipte mi. Alan yoksa (eski backend) koşullu. */
  kosulsuz?: boolean;
}
interface AiProAction {
  status?: string;
  message?: string;
  /** [B1] /start yanıtı: seansın SAHİBİNİN kimliği (taze başlatımda BİZ, "Already running"da MEVCUT
   *  sahip). Panel ownedRef'i YALNIZ bu===kendi kimliğimiz ise true yapar → başkasının seansını
   *  unmount'ta durdurmaz. ALAN YOKSA = eski backend → eski davranış (başarı=sahip). */
  ownerClientId?: string;
}
/** `/api/ai/pro/propose` yanıtı — hekime gösterilecek ve onaylanınca uygulanacak parametreler. */
interface AiProposeResponse {
  proposalId?: string;
  specs?: AiProposalSpecs;
  meta?: AiProposalMeta;
  expiresAt?: number;
  /** Y142: bu öneriyle sürüş başlatılabilir mi (false = kapalı; alan yoksa eski backend). */
  surusAcik?: boolean;
  /** Y142: kapalıysa NEDEN + EYLEM metni (backend tek kaynak). */
  surusKapaliNedeni?: string;
}

/**
 * @param patientName Aktif hasta adı — seansın kime uygulandığının denetim izi için backend'e taşınır.
 * @param secilebilirModeller Profilin seçebileceği hedef modelleri (ControlScreen'den gelir; tek
 *   kaynak `aiProProfilleri.MODELLER_PROFILE_GORE`). Varsayılan `["kedi"]` → prop geçilmese bile
 *   VETERİNER davranışı BİREBİR korunur (mevcut jest dosyaları mock'suz geçer).
 *   ⚠️ Panele bilinçli olarak `useUserMode` SOKULMADI: profil ControlScreen'de okunur, panel yalnız
 *   listeyi alır — böylece 5 panel testine provider mock'u eklemek gerekmez.
 */
export function AiProPanel({
  patientName = "",
  secilebilirModeller = ["kedi"],
  kullaniciKipi = "",
}: {
  patientName?: string;
  secilebilirModeller?: HedefModeli[];
  kullaniciKipi?: string;
}) {
  const { t } = useTranslation();
  const ORGANS = organListesi(t);
  const { width: pencereX, height: pencereY } = useResponsive();
  const { aiVisionData: v } = useLiveData();

  const [organId, setOrganId] = useState(0);
  // D1.60 (A-16): reddedilen/ulaşmayan organ değişiminde seçimi GERİ almak için son değer (boş bağımlılıklı
  // `changeOrgan` state'i kapanışta bayat görür → ref).
  const organIdRef = useRef(0);
  useEffect(() => {
    organIdRef.current = organId;
  }, [organId]);
  // AKTİF HEDEF MODELİ: liste tek elemanlıysa (veteriner → "kedi") doğrudan o; araştırma modunda
  // araştırmacı Adım 1'de kartlardan seçer (seçilmeden hazırlık başlatılamaz).
  const [hedefModeli, setHedefModeli] = useState<HedefModeli | "">(
    secilebilirModeller.length === 1 ? secilebilirModeller[0] : "",
  );
  // ⚠️ REF ŞART: modeli istek gövdelerine `hedefModeli` STATE'i ile koymak, öneri efektinin
  // bağımlılık dizisini ([hazirlik, mobileResult, organId, duration]) değiştirmeyi gerektirirdi —
  // o dizi kaynak-regex kapısıdır (tests/test_ai_pro_asamali_akis.py). `clientIdRef` deseni.
  const hedefModeliRef = useRef<HedefModeli | "">(hedefModeli);
  useEffect(() => {
    hedefModeliRef.current = hedefModeli;
  }, [hedefModeli]);
  /** T3 · Y189: Koşullu | Koşulsuz (yalnız araştırma modelleri — petri / fantom). Varsayılan koşullu, hatırlanmaz. Ref:
   *  `hedefModeliRef` ile AYNI gerekçe (öneri efektinin bağımlılık dizisi kaynak-regex kapısıdır). Backend kipi hazırlıkta alır,
   *  öneri MÜHRÜNE yazar; `/start` mühürden okur. */
  const [kosulsuz, setKosulsuz] = useState(false);
  const kosulsuzRef = useRef(false);
  useEffect(() => {
    kosulsuzRef.current = kosulsuz;
  }, [kosulsuz]);
  /** Denetim izi için taşınan profil — `hedefModeliRef` ile AYNI gerekçe (öneri efektinin
   *  bağımlılık dizisi kaynak-regex kapısıdır, prop'u diziye sokmak onu kırardı). */
  const kullaniciKipiRef = useRef(kullaniciKipi);
  useEffect(() => {
    kullaniciKipiRef.current = kullaniciKipi;
  }, [kullaniciKipi]);
  /** ⚠️ D2.E15 (İG-5.14): seansın HASTASI öneriyle birlikte gider ve ONAY MÜHRÜNE yazılır (`/start` hastayı mühürden okur;
   *  eskiden yalnız `/start` gövdesinde `patient_name` vardı ve backend onu ATIYORDU — AI Pro seansı hastaya bağlanmıyordu).
   *  Kimlik + ad AYNI kaynaktan (seçili hasta); seçili hasta yoksa ad (seans ekranının yedeği), kimlik boş. Ref:
   *  `hedefModeliRef` ile aynı gerekçe (öneri efektinin bağımlılık dizisi kaynak-regex kapısıdır). */
  const { selectedPatient: seciliHasta } = useAppNav();
  const hastaRef = useRef({ id: "", name: "" });
  hastaRef.current = seciliHasta?.id
    ? { id: String(seciliHasta.id), name: seciliHasta.name || "" }
    : { id: "", name: patientName || "" };
  /** Araştırma kipi: listede kedi YOK → model kartları gösterilir, kedi organ çipleri gizlenir. */
  const arastirmaKipi = !secilebilirModeller.includes("kedi");
  /**
   * ⚠️ ARAŞTIRMA HATTI YALNIZ KABİN KAMERASIYLA (sahip kararı #15): fantom/petri 3B konumu kabin
   * işaretine (arka duvardaki ArUco) ve ölçülmüş kabin geometrisine dayanır. Telefon kamerası o
   * çerçevenin dışındadır → konum ölçülemez. Telefonda panel görüntülenir ama seans başlatılamaz;
   * sebebi peşinen yazılır (kör "öneri gelmiyor" bekleyişi yerine).
   */
  const arastirmaMobilKapali = arastirmaKipi && !IS_WEB;
  /** Kare üstü hedef adayları + kalibrasyon/ood alanları (status poll ve WS aynı kaynağı besler). */
  const [hedefler, setHedefler] = useState<HedefAdayi[]>([]);
  const [yontem, setYontem] = useState("");
  const [hedefEtiket, setHedefEtiket] = useState("");
  const [ood, setOod] = useState(false);
  /** T3 · Y189: backend'in ETKİN kipi (rozet bunu gösterir — panelin seçimi değil, sürülen kip). */
  const [sunucuKosulsuz, setSunucuKosulsuz] = useState(false);
  const [ozneVar, setOzneVar] = useState(false);
  /** `PEMF_ARASTIRMA_AIPRO`: null = bilinmiyor (alan yok / durum okunamadı). */
  const [arastirmaAcik, setArastirmaAcik] = useState<boolean | null>(null);
  /** T-f `PEMF_ARASTIRMA_AIPRO_FANTOM`: null = bilinmiyor (eski backend) → kart `arastirmaAcik`e düşer. */
  const [fantomAcik, setFantomAcik] = useState<boolean | null>(null);
  /** Y142 `PEMF_KEDI_AIPRO_SURUS`: null = bilinmiyor (alan yok / durum okunamadı) → eski davranış. */
  const [kediSurusAcik, setKediSurusAcik] = useState<boolean | null>(null);
  /** Model kurulum durumu — `GET /api/ai/hazirlik` envanterinden BİR KEZ okunur (poll YOK). */
  const [kurulum, setKurulum] = useState<Partial<Record<HedefModeli, KurulumDurumu>>>({});
  const [duration, setDuration] = useState("20");
  const [running, setRunning] = useState(false);
  const [localized, setLocalized] = useState(false);
  /** Sunum-katmanı XAI (2026-08-26): web yolunda güven dökümü status poll'dan gelir. */
  const [webGuvenDokumu, setWebGuvenDokumu] = useState<GuvenDokumu | null>(null);
  /**
   * B3 (siyah ekran, 2026-09-03): web'de "kedi var mı" YALNIZ WS `ai_vision`tan okunuyordu; sunucu
   * önizlemesi (eski backend) hiç `ai_vision` yayınlamadığından hazırlık şeridi backend kediyi
   * GÖRMÜŞKEN bile "Hayvan aranıyor…"da kalıyordu. /status `catDetected` zaten bunu taşıyor → ikinci kaynak.
   */
  const [webCatDetected, setWebCatDetected] = useState(false);
  /** B3: sunucu önizlemesinin bildirdiği hata (kamera açılamadı / model yüklenemedi) — kamera kutusunda. */
  const [hazirlikHata, setHazirlikHata] = useState("");
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
  /** `/ai/pro/status` en az bir kez okundu mu — mount'taki "seans yok" varsayımını önler. */
  const [durumOkundu, setDurumOkundu] = useState(false);
  const hazirlikRef = useRef(false);
  useEffect(() => { hazirlikRef.current = hazirlik; }, [hazirlik]);
  /**
   * AI HUB'DAN GELEN ÖN-SEÇİM: araştırmacı fantom/petri ANALİZİNDEN "Bu hedefe AI Pro seansı"
   * ile geldiyse model kartı zaten seçili gelir. TEK KULLANIMLIK: uygulanınca temizlenir, yoksa
   * kullanıcının sonraki kendi seçimini her dönüşte EZERDİ.
   *
   * ⚠️ Sağlayıcı YOKSA (jest testleri, tek başına render) context varsayılanı boş dizge döndürür
   * → davranış değişmez.
   */
  const { aiProModeli: onSecim, setAiProModeli: onSecimTemizle } = useAppNav();
  useEffect(() => {
    if (!onSecim) return;
    // ⚠️ DURUM OKUNANA KADAR BEKLE: `running` mount'ta false'tur; beklemeden uygulamak, SÜREN bir
    // seansın üzerine gelindiğinde (sekme değişimi) kartı mühürlenen modelden BAŞKASINA çevirir —
    // ekran yanlış modeli seçili gösterir ve hedef değişimi backend'de 422'ye çarpar (ölçüldü).
    if (!durumOkundu) return;
    if (running || hazirlik) return;   // seans/hazırlık sürerken hedef değiştirilmez
    if ((secilebilirModeller as string[]).includes(onSecim)) setHedefModeli(onSecim as HedefModeli);
    onSecimTemizle("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onSecim, running, hazirlik, durumOkundu]);
  /** Hazırlık sırasında öneri BİR KEZ istenir (kareler periyodik geliyor). */
  const oneriIstendiRef = useRef(false);
  /** WEB hazırlık: ardışık kaç status-poll'da `localized` görüldü (tek şanslı kareyi elemek). */
  const webLokalizeSayacRef = useRef(0);
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
  /** F2: son SAYILAN lokalizasyon damgası — aynı damga (eko kare) yeniden sayılmaz. */
  const sonDamgaRef = useRef<number | null>(null);
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

  /**
   * MODEL KURULUM DURUMU — araştırma kartlarındaki "Model kurulu ✓" rozeti.
   *
   * ⚠️ POLL YOK: envanter taraması gerçek dosya/import kontrolü yapar (pahalı). Kart ekranı
   * açılınca BİR KEZ okunur; yanıt gelmezse rozet "okunamadı" der ve seçim ENGELLENMEZ (kapı
   * backend'de: model yüklenemezse hazırlık sınıflı hata döndürür).
   */
  useEffect(() => {
    if (!arastirmaKipi) return;   // veteriner ekranı bu isteği HİÇ atmaz
    let alive = true;
    (async () => {
      const h = await apiGet<{ moduller?: { modul?: string; hazir?: boolean }[] } | null>(
        "/ai/hazirlik",
        null,
        { silent: true },
      );
      if (!alive) return;
      if (!h || !Array.isArray(h.moduller)) { setKurulum({}); return; }
      const hazirAdlar = new Set(h.moduller.filter((m) => m?.hazir).map((m) => String(m?.modul || "")));
      const sonuc: Partial<Record<HedefModeli, KurulumDurumu>> = {};
      for (const m of secilebilirModeller) {
        sonuc[m] = MODUL_GEREKSINIMI[m].every((mod) => hazirAdlar.has(mod)) ? "hazir" : "eksik";
      }
      setKurulum(sonuc);
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arastirmaKipi]);

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
      setDurumOkundu(true);
      setLocalized(Boolean(st.localized));
      setWebGuvenDokumu(st.guvenDokumu ?? null); // sunum-katmanı XAI (web: status poll'dan)
      setWebCatDetected(Boolean(st.catDetected)); // B3: hazırlık metni için ikinci kaynak
      // Araştırma hattı yalnız-ek alanları. ⚠️ Alan YOKSA eski davranış: boş liste / boş yöntem →
      // halkalar ve rozet çizilmez, kedi ekranı BİREBİR aynı kalır.
      setHedefler(Array.isArray(st.targets) ? st.targets : []);
      setYontem(typeof st.method === "string" ? st.method : "");
      setHedefEtiket(typeof st.targetLabel === "string" ? st.targetLabel : "");
      setOod(Boolean(st.ood));
      setSunucuKosulsuz(st.kosulsuz === true);  // T3 · Y189
      setOzneVar(Boolean(st.subjectDetected ?? st.catDetected));
      setArastirmaAcik(typeof st.arastirmaAiProAcik === "boolean" ? st.arastirmaAiProAcik : null);
      setFantomAcik(typeof st.arastirmaAiProFantomAcik === "boolean" ? st.arastirmaAiProFantomAcik : null);
      setKediSurusAcik(typeof st.kediAiProSurusAcik === "boolean" ? st.kediAiProSurusAcik : null);
      // B3 (siyah ekran): sunucu önizlemesi kamera/model hatasıyla öldüyse panel bunu ÖĞRENSİN.
      // Eskiden /baslat "success" diyor, thread anında ölüyor ve panel 120 sn "Hazırlanıyor…"da
      // takılıp sonra "hayvan bulunamadı" (YANLIŞ teşhis) diyordu. ⚠️ Yalnız hata METNİ doluysa
      // (salt `hazirlikActive:false` değil): propose→/durdur→setHazirlik(false) arasındaki poll
      // ve eski backend (alan yok) yanlış tetiklemesin.
      if (IS_WEB && hazirlikRef.current && typeof st.hazirlikHata === "string" && st.hazirlikHata) {
        setHazirlik(false);
        oneriIstendiRef.current = false;
        setHazirlikHata(st.hazirlikHata);
        platformAlert(i18n.t("ai.pro.uyari.sunucuKamerasi"), st.hazirlikHata);
      }
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
    // ARAŞTIRMA KAPISI 1: model seçilmeden hazırlık başlatılamaz. Backend boş `model`i "kedi"
    // sayar (eski istemci uyumu) → seçim yapılmadan başlatmak SESSİZCE kedi hattını açardı.
    if (arastirmaKipi && !hedefModeliRef.current) {
      platformAlert(i18n.t("ai.pro.uyari.modelSecilmedi"), i18n.t("ai.pro.uyari.modelSecilmediGovde"));
      return;
    }
    // ARAŞTIRMA KAPISI 2 (sahip kararı #15): fantom/petri konumu KABİN çerçevesinde ölçülür;
    // telefon kamerası o çerçevenin dışındadır → konum ölçülemez, öneri hiç üretilmez.
    if (arastirmaMobilKapali) {
      platformAlert(i18n.t("ai.pro.uyari.kabinKamerasi"), i18n.t("ai.pro.uyari.kabinKamerasiGovde"));
      return;
    }
    // DENETİM İZİ: AI Pro otonom tedavisi hiçbir hastaya BAĞLANMADAN başlatılabiliyordu —
    // seans kaydı sahipsiz kalıyor, tedavi geçmişinde hangi hayvana uygulandığı bilinmiyordu
    // (klinik izlenebilirlik). ControlScreen'deki `requirePatient` ile aynı yaklaşım: bloklamıyoruz,
    // ama BİLİNÇLİ karar hâline getiriyoruz ve hasta bilgisini backend'e taşıyoruz.
    if (!patientName?.trim()) {
      // Terminoloji (karar #12): araştırmacının önünde bir HASTA değil bir ÖRNEK vardır. Kapının
      // kendisi ve denetim izi AYNI; yalnız arayüz dili role uyar (sözlük: utils/profilSozlugu).
      const S = profilSozlugu({ researcher: arastirmaKipi });
      const go = await platformConfirm(
        i18n.t("ai.pro.uyari.hastasizBaslik", { tekilKisa: S.tekilKisa }),
        arastirmaKipi
          ? i18n.t("ai.pro.uyari.hastasizGovdeDeney", { belirtme: S.belirtme })
          : i18n.t("ai.pro.uyari.hastasizGovdeOtonom", { belirtme: S.belirtme }),
        S.sizBaslat
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
      sonDamgaRef.current = null;   // F2: her hazırlık taze damgayla sayar
      setArdisik(0);
      setOneriHatasi("");
      await apiPost<AiProAction | null>("/ai/pro/calibrate", { client_id: clientIdRef.current }, null);  // taze lokalizasyon iste
      setHazirlik(true);   // kareler akmaya başlar → kedi → organ → öneri (otomatik)
      return;
    }
    // 🔴 WEB KAPALI-DÖNGÜ DÜZELTMESİ (2026-08-25): eskiden web DOĞRUDAN propose çağırıyordu ve
    // "organ henüz konumlandırılmadı" (409) alıyordu — sunucu kamerası ancak SEANS sürerken
    // lokalize ediyor, seans öncesi hiçbir şey lokalize etmiyordu (telefonda 1.9.22'de çözülen
    // kapalı-döngünün web hâli). Artık web de telefondaki gibi ÖNCE hazırlık: sunucu kamerasını
    // önizlemede ısıtır (lokalize eder, bobin SÜRMEZ), organ konumlanınca öneri OTOMATİK gelir.
    setBusy(false);
    oneriIstendiRef.current = false;
    oneriBeklemeRef.current = 0;
    ardisikRef.current = 0;
    sonDamgaRef.current = null;
    webLokalizeSayacRef.current = 0;
    setArdisik(0);
    setOneriHatasi("");
    setHazirlikHata("");   // B3: yeni deneme taze
    setLocalized(false);   // bayat lokalizasyondan öneri tetiklenmesin (backend cache'i de sıfırlar)
    oneriBeklemeRef.current = 0;
    const hz = await apiPost<AiProAction | null>(
      "/ai/pro/hazirlik/baslat",
      { organ_id: organId, client_id: clientIdRef.current, model: hedefModeliRef.current, kosulsuz: kosulsuzRef.current },
      null
    );
    // B3: komut sunucuya ULAŞMADIYSA hazırlığa girme — aksi hâlde düğme 120 sn "Hazırlanıyor…"da
    // takılır, kamera kutusu kapkara kalır ve operatör sebebi göremez.
    if (!hz) {
      setHazirlikHata(i18n.t("ai.pro.hata.hazirlikKomutu"));
      return;
    }
    setHazirlik(true);   // status /localized görününce web-öneri efekti propose'u tetikler
  }, [organId, duration, permission, requestPermission, arastirmaKipi, arastirmaMobilKapali]);

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
      sonDamgaRef.current = null;  // F2: ölçüm koptu → damga da sıfırla (sonraki taze sayar)
      setArdisik(0);
      return;
    }
    // ⚠️ ARDIŞIK DOĞRULAMA: tek bir şanslı kare tedavi parametrelerini tetiklemesin.
    // F2 (denetim 2026-08-24): sayaç yalnız YENİ LOKALİZASYONDA artar. Kareler 1,5 sn'de, sunucu
    // lokalizasyonu ≤10 sn'de bir → aynı ölçümün ekosu AYNI localizedAt'i taşır; eko'yu saymak
    // "iki tutarlı ölçüm"ü tek ölçüme indirir (sahte sertleştirme). Damga eşitse ARTIRMA — ama
    // SIFIRLAMA da yapma (streak korunur; yoksa eko'yla bölünmüş iki gerçek ölçüm asla 2'ye ulaşmaz).
    const damga = mobileResult?.localizedAt;
    if (typeof damga === "number") {
      if (damga === sonDamgaRef.current) return; // eko kare
      sonDamgaRef.current = damga;
    }
    // (damga undefined = eski backend → her detected karede say; geriye-uyum, kilitlenme yok.)
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
        {
          organ_id: organId,
          duration_minutes: parseInt(duration) || 20,
          // ⚠️ REF (state DEĞİL): bu efektin bağımlılık dizisi kaynak-regex kapısıdır
          // (tests/test_ai_pro_asamali_akis.py) — modeli diziye sokmak kapıyı kırardı.
          model: hedefModeliRef.current,
          // DENETİM İZİ: hangi profil bu dozu onaylattı (backend yetki VERMEZ, yalnız mühre yazar).
          client_mode: kullaniciKipiRef.current,
          // D2.E15: hasta mühre yazılır (onay penceresi gösterir, `/start` buradan okur).
          patient_id: hastaRef.current.id,
          patient_name: hastaRef.current.name,
          // T3 · Y189: panelin kipi — önizleme konumu farklı kipte bulunduysa backend 409 (mühür karışmaz).
          kosulsuz: kosulsuzRef.current,
        },
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
        setOneriHatasi(i18n.t("ai.pro.hata.oneriDenenecek"));
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
   * WEB HAZIRLIK → öneri (2026-08-25 kapalı-döngü düzeltmesi). Sunucu kamerası önizlemede organı
   * lokalize edince (`/ai/pro/status` → `localized`) öneriyi OTOMATİK ister. Telefondaki
   * `mobileResult` yerine web `localized` state'ini izler; İKİ ardışık gözlem (webLokalizeSayacRef)
   * tek şanslı lokalizasyonu eler (mobil ARDISIK_ONAY paritesi). Öneri gelince önizleme durdurulur
   * (kamera bırakılır; `/ai/pro/start` seans loop'uyla yeniden açar).
   */
  useEffect(() => {
    if (!IS_WEB || !hazirlik || oneriIstendiRef.current || !localized) return;
    if (Date.now() < oneriBeklemeRef.current) return;   // başarısız denemeden sonra aralıklı bekle
    // ⚠️ `localized` KARARLI bir boolean (false→true bir kez değişir, sonra sabit) → efekt bir
    // kez koşar. Bu yüzden web'de sayaç-tabanlı "iki ölçüm" İŞLEMEZ (mobildeki `mobileResult`
    // her karede yeni nesne olduğu için oradaki sayaç çalışır). Sunucu önizlemesi organı güvenilir
    // lokalize eder ve propose ucu tazeliği (localized + ≤120sn) AYRICA doğrular → ilk `localized`
    // gözleminde öneri istenir (web'in ESKİ davranışı da buydu; fark: artık ÖNCE kamera ısıtılıyor).
    oneriIstendiRef.current = true;
    (async () => {
      const prop = await apiPost<AiProposeResponse | null>(
        "/ai/pro/propose",
        {
          organ_id: organId,
          duration_minutes: parseInt(duration) || 20,
          // ⚠️ REF (state DEĞİL): bu efektin bağımlılık dizisi kaynak-regex kapısıdır
          // (tests/test_ai_pro_asamali_akis.py) — modeli diziye sokmak kapıyı kırardı.
          model: hedefModeliRef.current,
          // DENETİM İZİ: hangi profil bu dozu onaylattı (backend yetki VERMEZ, yalnız mühre yazar).
          client_mode: kullaniciKipiRef.current,
          // D2.E15: hasta mühre yazılır (onay penceresi gösterir, `/start` buradan okur).
          patient_id: hastaRef.current.id,
          patient_name: hastaRef.current.name,
          // T3 · Y189: panelin kipi — önizleme konumu farklı kipte bulunduysa backend 409 (mühür karışmaz).
          kosulsuz: kosulsuzRef.current,
        },
        null,
        { silent: true }
      );
      if (prop?.proposalId) {
        setOneriHatasi("");
        await apiPost<AiProAction | null>("/ai/pro/hazirlik/durdur", {}, null); // önizlemeyi bırak
        setProposal(prop);
        setHazirlik(false);
      } else {
        // Model bu konum için sürülebilir parametre üretmedi (ya da anlık sunucu hıçkırığı). `localized`
        // sabit boolean olduğundan efekt kendiliğinden yeniden koşmaz → localized'ı sıfırla: sonraki 3sn'lik
        // status poll (backend cache hâlâ localized) onu tekrar true yapar ve efekt ARALIKLI (bekleme)
        // yeniden dener. (Adversaryal inceleme MINOR: mobil retry paritesi.)
        setOneriHatasi(i18n.t("ai.pro.hata.oneriDeneniyor"));
        oneriBeklemeRef.current = Date.now() + ONERI_BEKLEME_MS;
        oneriIstendiRef.current = false;
        setLocalized(false);
      }
    })();
  }, [hazirlik, localized, organId, duration]);

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
        sonDamgaRef.current = null;   // F2
        webLokalizeSayacRef.current = 0;
        if (IS_WEB) apiPost<AiProAction | null>("/ai/pro/hazirlik/durdur", {}, null); // sunucu önizlemesini bırak
        setOneriHatasi("");
        platformAlert(i18n.t("ai.pro.uyari.konumlandirmaTamamlanamadi"), i18n.t("ai.pro.uyari.konumlandirmaTamamlanamadiGovde"));
      }
    }, 1000);
    return () => clearInterval(id);
  }, [hazirlik]);

  /** Hekim ONAYLADI → onayı işaretle, sonra mühürlenmiş parametrelerle tedaviyi başlat. */
  const approveAndStart = useCallback(async () => {
    if (!proposal?.proposalId) return;
    // Y142: sürüş kapalıyken onay seans BAŞLATMAZ — /approve ve /start GÖNDERİLMEZ (düğme zaten pasif; klavye/otomasyon yolu).
    const kapali = oneriSurusuKapali(proposal, kediSurusAcik);
    if (kapali) {
      platformAlert(i18n.t("ai.pro.uyari.surusKapali"), kapali);
      return;
    }
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
      // [B1]: ownedRef'i YALNIZ backend BİZİ sahip gösteriyorsa true yap. "Already running" yanıtı
      // MEVCUT sahibi (A) döndürür → B ownedRef=false kalır ve panelini kapatınca A'nın onaylı
      // seansına /stop GÖNDERMEZ (ownedRef <3sn drift kapanır). Alan yoksa (eski backend) eski
      // davranış: başarı=sahip (sürüm-kayması geriye-uyumu).
      // ⚠️ `!!res.ownerClientId`: status-poll (satır ~199) ile AYNI formül — boş ownerClientId'yi
      // İKİSİ de "sahip değil" sayar. Aksi halde boş-owner'da start=true / poll=false ıraksar ve
      // sahibin unmount /stop'u atlanabilirdi (adversaryal kod-inceleme minor tutarlılık).
      ownedRef.current =
        res.ownerClientId === undefined
          ? true
          : !!res.ownerClientId && res.ownerClientId === clientIdRef.current;
      setRunning(true);
      setProposal(null);
    }
    // Başlatma başarısızsa modal AÇIK kalır: onay tüketilmiş olabilir, hekim yeni öneri alır.
  }, [proposal, operatorEmail, patientName, kediSurusAcik]);

  /** Hekim REDDETTİ → gerekçeyle kaydet; tedavi BAŞLAMAZ. */
  const rejectProposal = useCallback(async (reason: string) => {
    if (!proposal?.proposalId) return;
    setApprovalBusy(true);
    const r = await apiPost<{ status?: string; gerekceKaydedildi?: boolean } | null>("/ai/pro/reject",
      { proposal_id: proposal.proposalId, operator_email: operatorEmail || "", reason },
      null);
    setApprovalBusy(false);
    setProposal(null);
    // S-F2-1.2 (2-F incelemesi · Y123 · C2-1.14): pencere "Red gerekçesi (kayda geçer)" diyor — sunucu yazamadıysa hekim bilmeli.
    if (r && r.gerekceKaydedildi === false) {
      platformAlert(i18n.t("ai.pro.uyari.gerekceKaydedilemedi"), i18n.t("ai.pro.uyari.gerekceKaydedilemediGovde"));
    }
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
      platformAlert(i18n.t("ai.pro.uyari.durdurulamadi"), i18n.t("ai.pro.uyari.durdurulamadiGovde"));
    }
    setBusy(false);
  }, []);

  const changeOrgan = useCallback(async (id: number) => {
    const onceki = organIdRef.current;
    setOrganId(id);
    // DÜŞÜK fix: sessiz yutma yerine başarısızlıkta uyar (komut ulaşmadıysa kullanıcı bilsin).
    // [B1]: client_id ile → backend YABANCI (sahip dışı) istemcinin mid-seans organ değişimini
    // (onaylanmamış organa enerji) reddeder. Sahip kendi id'siyle çağırır → izin.
    // ⚠️ D1.60 (A-16, İG-6.10): seans sürerken MÜHÜRDE OLMAYAN organa geçiş backend'de 409 (yeni onay gerekir).
    // Seçim istekten ÖNCE değiştiği için red sonrası ekran yeni organı gösteriyordu (bobinler onaylı organı sürerken)
    // ve "sunucuya ulaşmadı" deniyordu. Artık her başarısızlıkta seçim GERİ alınır; HTTP reddinde sunucunun
    // gerekçesi (eylem söyler) gösterilir — genel "Sunucu Hatası" kutusu ikinci kez açılmasın diye `silent`.
    let red: { durum: number; detay?: string } | null = null;
    const res = await apiPost<AiProAction | null>(
      "/ai/pro/organ",
      { organ_id: id, client_id: clientIdRef.current, model: hedefModeliRef.current },
      null,
      { silent: true, onHttpError: (durum, detay) => { red = { durum, detay }; } }
    );
    if (!res) {
      setOrganId(onceki);
      // Araştırmada "Organ" kelimesi yanıltıcıdır (hedef bir tümör odağı / kuyudur). Ref'ten
      // okunur ki bu callback'in boş bağımlılık dizisi korunsun.
      const hedefMi = hedefModeliRef.current && hedefModeliRef.current !== "kedi";
      const r = red as { durum: number; detay?: string } | null;
      platformAlert(
        hedefMi ? i18n.t("ai.pro.uyari.hedefDegistirilemedi") : i18n.t("ai.pro.uyari.organDegistirilemedi"),
        r ? r.detay || i18n.t("ai.pro.uyari.sunucuReddetti", { durum: r.durum }) : i18n.t("ai.pro.uyari.komutUlasmadi")
      );
    }
  }, []);

  const relocalize = useCallback(async () => {
    // Bir sonraki karede cat_organ organ-lokalizasyonunu zorla tazele (avuç-Z kalibrasyonu KALKTI).
    const res = await apiPost<AiProAction | null>("/ai/pro/calibrate", { client_id: clientIdRef.current }, null);
    if (!res) {
      platformAlert(i18n.t("ai.pro.uyari.yenidenKonumlanamadi"), i18n.t("ai.pro.uyari.komutUlasmadi"));
      return;
    }
    // 🔴 2026-08-24: bu düğme YALNIZ sunucuda bayrak set ediyordu. Mobilde kareler seans
    // başlamadan akmadığı için bayrağı işleyecek kare HİÇ gelmiyordu → düğme görsel olarak
    // çalışıyor ama lokalizasyon hiç olmuyordu. Üstelik kullanıcıya hata mesajında tam da bu
    // düğmeye basması söyleniyordu. Artık kare akışını da başlatır.
    if (!running) {
      oneriIstendiRef.current = false;
      if (IS_WEB) {
        // WEB: "Yeniden Konumla" sunucu-kamera önizlemesini (yoksa) başlatır → lokalize → öneri.
        // Zaten hazırlıktaysa yukarıdaki /calibrate önizlemenin yeniden-lokalize etmesini sağlar.
        webLokalizeSayacRef.current = 0;
        ardisikRef.current = 0;
        setArdisik(0);
        setHazirlikHata("");   // B3: yeni deneme taze — bayat "⚠️ …" metni kutuda kalmasın
        const hz = await apiPost<AiProAction | null>(
          "/ai/pro/hazirlik/baslat",
          { organ_id: organId, client_id: clientIdRef.current, model: hedefModeliRef.current, kosulsuz: kosulsuzRef.current },
          null
        );
        // B3: start() ile AYNI kapı — komut sunucuya ULAŞMADIYSA hazırlığa girme; aksi hâlde bu
        // düğmeyle de eski kör 120 sn "Hazırlanıyor…" davranışı geri gelirdi.
        if (!hz) {
          setHazirlikHata(i18n.t("ai.pro.hata.hazirlikKomutu"));
          return;
        }
      }
      setHazirlik(true);
    }
  }, [running, organId]);

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
        // ⚠️ shutterSound: false — SAHA BİLDİRİMİ (2026-08-27): AI Pro tedavi sürerken kare
        // her ~3 sn'de bir alınıyor ve sistem HER karede deklanşör sesi çalıyordu. Klinikte
        // hasta üzerinde süren bir seansta bu hem rahatsız edici hem de hayvanı ürkütür.
        // Yakalama SESSİZ olmalı: bu bir fotoğraf çekimi değil, ölçüm karesidir.
        const photo = await cameraRef.current.takePictureAsync({
          quality: 0.5, base64: true, skipProcessing: true, shutterSound: false,
        });
        if (photo?.base64) {
          const fd = new FormData();
          fd.append("image_base64", photo.base64);
          // [B1]: kare sahipliği → backend YABANCI istemcinin karesini bobin SÜRMEZ. Sahip kendi
          // id'sini taşır (start'takiyle aynı). Boşsa (id henüz yüklenmedi / hazırlık) backend
          // sahip-yokken zaten bastırmaz — güvenli.
          fd.append("client_id", clientIdRef.current);
          const ctrl = new AbortController();
          const zamanAsimi = setTimeout(() => ctrl.abort(), 15000);
          const headers: Record<string, string> = { Accept: "application/json" };
          if (serviceConfig.apiToken) headers["X-API-Key"] = serviceConfig.apiToken;
          const r = await fetch(serviceConfig.apiBaseUrl + "/ai/ai_pro/frame", {
            method: "POST", body: fd, headers, signal: ctrl.signal,
          });
          clearTimeout(zamanAsimi);
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

  /**
   * HAZIRLIKTAN VAZGEÇ — şeritteki "Vazgeç" düğmesi ve sihirbazın "Geri" düğmesi AYNI eylemi
   * çağırır (iki ayrı satır-içi kopya, ikisinden birinin sessizce ayrışmasına açıktı).
   * Davranış DEĞİŞMEDİ: sayaçlar sıfırlanır, web'de sunucu önizlemesi bırakılır.
   */
  const vazgec = useCallback(() => {
    setHazirlik(false);
    oneriIstendiRef.current = false;
    oneriBeklemeRef.current = 0;
    ardisikRef.current = 0;
    sonDamgaRef.current = null;
    webLokalizeSayacRef.current = 0;
    setArdisik(0);
    setOneriHatasi("");
    if (IS_WEB) apiPost<AiProAction | null>("/ai/pro/hazirlik/durdur", {}, null);
  }, []);

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
    // WEB hazırlık önizlemesi açıkken panel kapanırsa sunucu kamerasını bırak (backend 120 sn'de
    // kendisi de durur; bu yalnız kamerayı erken serbest bırakır).
    if (IS_WEB && hazirlikRef.current) {
      apiPost<AiProAction | null>("/ai/pro/hazirlik/durdur", {}, null).catch(() => {});
    }
  }, []);

  // ── Görüntülenecek değerler: web = WS (aiVisionData), mobil = HTTP yanıtı ──
  // B3: web hazırlıkta lokalizasyon /status'tan gelir (WS yoksa da) → şerit "konumlandı"ya geçebilsin.
  const detected = IS_WEB ? Boolean(v?.detected) || (hazirlik && localized) : Boolean(mobileResult?.detected);
  const reliability = IS_WEB ? (v as any)?.reliability : mobileResult?.reliability;
  const targetX = IS_WEB ? v?.target?.x : mobileResult?.target?.x;
  const targetY = IS_WEB ? v?.target?.y : mobileResult?.target?.y;
  const targetZ = IS_WEB ? v?.target?.z : mobileResult?.target?.z;
  const overlayB64 = IS_WEB ? v?.imageBase64 : mobileResult?.image_base64;

  /**
   * [S7 adım 6 / aihub-2] KAMERA KUTUSU ORAN KİLİDİ.
   * Kutu SABİT rs(200) yükseklikteydi ve içerik `resizeMode="contain"` ile sığdırılıyordu:
   * canlı önizleme ile ÜZERİNE çizilen organ overlay'i farklı ölçeklerde oturuyor, işaretler
   * görüntüyle KAYIYORDU. Kutu artık karenin GERÇEK oranında açık px olarak hesaplanıyor →
   * contain ≡ cover, kayma yok. Boyut yoksa cihaz yönü varsayılanına düşer.
   */
  const [kutuW, setKutuW] = useState(0);
  const kareOran = IS_WEB
    ? kareOrani({ image_w: v?.imageW, image_h: v?.imageH }, false)
    : kareOrani(mobileResult, pencereY > pencereX);
  const kutu = kutuW > 0 ? kameraKutusu(kutuW, kareOran, pencereY, 0.5) : null;
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
  // B3: web'de WS karesi (yeni backend önizlemesi) VEYA /status cache'i (eski backend / WS kopuk).
  const catDetected = IS_WEB
    ? Boolean((v as any)?.catDetected) || webCatDetected
    : Boolean(mobileResult?.catDetected);
  /** Sunum-katmanı XAI (2026-08-26): web = status poll'dan, mobil = /frame yanıtından. */
  const guvenDokumu: GuvenDokumu | null = (IS_WEB ? webGuvenDokumu : mobileResult?.guvenDokumu) ?? null;
  const organAdi = ORGANS.find((o) => o.id === organId)?.name ?? "";
  /** Güven yüzdesi — ⚠️ eşik 0,3 olduğu için "konumlandı" %30 da olabilir; operatör SAYIYI görmeli. */
  const guvenYuzde = Math.round((Number(reliability) || 0) * 100);
  const dusukGuven = detected && (Number(reliability) || 0) < DUSUK_GUVEN;
  /** Gecikmede SOMUT yönlendirme (yalnız "tekrar deneyin" demek işe yaramaz). */
  const gecikmeIpucu =
    hazirlik && hazirlikGecen >= HAZIRLIK_UYARI_MS
      ? t("ai.pro.gecikmeIpucu")
      : "";
  const asamaMetni = !hazirlik
    ? ""
    : detected
      // B3: web'de ardisik sayaci HİÇ artmaz (mobil efekti); detected artık hazırlıkta web'de de true
      // olabildiğinden şerit "doğrulanıyor (0/2) · ikinci ölçüm bekleniyor…" derdi — oysa web öneriyi ilk
      // localized anında zaten ister. (Yorumda anahtar çağrısı YOK: test_ai_pro_asamali_akis kaynak-regex kapısı
      // bu bloktaki aşama anahtarı çağrılarını asama sayar — tam 4 olmalı.)
      ? (!IS_WEB && ardisik < ARDISIK_ONAY)
        ? t("ai.pro.asama.dogrulaniyor", { organAdi, ardisik, onay: ARDISIK_ONAY })
        : t("ai.pro.asama.konumlandi", { organAdi, guvenYuzde, sinirda: dusukGuven ? t("ai.pro.asama.sinirda") : "" })
      : catDetected
        ? t("ai.pro.asama.hayvanGorunuyor", { organAdi, gecikmeIpucu })
        : t("ai.pro.asama.hayvanAraniyor", { gecikmeIpucu });

  // ── ARAŞTIRMA SUNUMU (kedi hattı yukarıda BİREBİR korunur) ────────────────────────────────
  const modelProf = modelProfili(hedefModeli || "kedi");
  /** Kare üstü hedef adayları: seans/önizleme WS'i (taze) yoksa status poll'u. */
  const hedefAdaylari: HedefAdayi[] = (IS_WEB && v?.targets?.length ? v.targets : hedefler) as HedefAdayi[];
  const yontemAktif = (IS_WEB && v?.method ? v.method : yontem) || "";
  /** Şerit metni: araştırmada özneyi/hedefi model adıyla söyler. */
  const seritMetni = !hazirlik
    ? ""
    : arastirmaKipi
      ? asamaMetniArastirma({
          ozne: modelProf.ozne,
          ozneIpucu: modelProf.ozneIpucu,
          hedefEtiketi: modelProf.hedefEtiketi,
          hedefEtiketiKucuk: modelProf.hedefEtiketiKucuk,
          ozneVar: IS_WEB ? ozneVar || catDetected : catDetected,
          localized: detected,
          hedefSayisi: hedefAdaylari.length,
          yontem: yontemAktif,
          guvenYuzde,
          gecikmeIpucu,
        })
      : asamaMetni;
  /**
   * SİHİRBAZ ADIMI — ayrı bir state DEĞİL, gerçek durumdan TÜRETİLİR. Ayrı state tutmak
   * göstergenin gerçekle ayrışmasına (ekran "Adım 3" derken hazırlık ölmüş olması) açıktı.
   */
  const adim: Adim = running
    ? 5
    : proposal
      ? 4
      : hazirlik && hedefAdaylari.length > 0
        ? 3
        : hazirlik
          ? 2
          : hedefModeli
            ? 2   // model seçili, kamera henüz açılmadı → "Hazırlığı Başlat" adımı
            : 1;
  /** Seans ya da hazırlık sürerken model değiştirilemez (backend de 409 döndürür). */
  const modelKilitli = running || hazirlik;
  /**
   * BAŞLAT KAPISI — düğme pasifse SEBEBİ erişilebilirlik ipucunda söylenir. `start()` içindeki
   * kapılar KALDIRILMADI: düğme pasif olsa da (klavye/otomasyon) çağrı gelebilir.
   */
  const baslatKapali = !running && (arastirmaMobilKapali || (arastirmaKipi && !hedefModeli));
  /** Y142: kedi panelinde sürüş KAPALI (durum ucu söyledi) → başlatma düğmesi yalnız analiz + öneri yapar ve bunu SÖYLER. */
  const kediSurusKapali = !arastirmaKipi && kediSurusAcik === false;
  const baslatKapaliNedeni = arastirmaMobilKapali
    ? t("ai.pro.baslatKapali.mobil")
    : t("ai.pro.baslatKapali.modelYok");

  return (
    <View style={styles.wrap}>
      {/* SERT ONAY KAPISI (2026-08-06): AI önerisi hekime gösterilir; onaylanmadan seans
          BAŞLAMAZ. Kapatmak reddetmek DEĞİLdir — öneri süresi dolunca kendiliğinden düşer.
          D2.E10 (İG-6.27): pencere ÖNERİ KİMLİĞİYLE anahtarlı → her yeni öneride TEMİZ açılır; önceki önerinin red formu
          ve gerekçesi yeni öneriye taşınmaz (tek dokunuş p2'yi p1'in gerekçesiyle reddediyordu). */}
      <AiSpecApprovalModal
        key={proposal?.proposalId ?? "oneri-yok"}
        visible={!!proposal}
        specs={proposal?.specs ?? null}
        meta={proposal?.meta ?? null}
        organName={
          arastirmaKipi
            ? hedefEtiket || modelProf.hedefEtiketi
            : ORGANS.find((o) => o.id === (proposal?.specs?.organ_id ?? organId))?.name
        }
        busy={approvalBusy}
        surusKapali={oneriSurusuKapali(proposal, kediSurusAcik)}
        onApprove={approveAndStart}
        onReject={rejectProposal}
        onDismiss={() => setProposal(null)}
      />
      {/* SİHİRBAZ (yalnız araştırma): neredeyim + geri nasıl dönerim. Veterinerde RENDER EDİLMEZ →
          bugünkü ekran birebir korunur. */}
      {arastirmaKipi ? (
        <AdimGostergesi adim={adim} onGeri={hazirlik ? vazgec : undefined} geriEtiketi={t("ai.pro.adim.geri")} />
      ) : null}

      {/* GİRİŞ CÜMLESİ: bir iddia değil KURAL — bu ekran onay olmadan bobin çalıştırmaz. */}
      <Text style={styles.note}>
        {arastirmaKipi
          ? arastirmaMobilKapali
            ? t("ai.pro.not.arastirmaMobil")
            : t("ai.pro.not.arastirmaGiris")
          : kediSurusKapali
            ? IS_WEB
              ? t("ai.pro.not.kediWebOneri")
              : t("ai.pro.not.kediMobilOneri")
            : IS_WEB
            ? t("ai.pro.not.kediWebSeans")
            : t("ai.pro.not.kediMobilSeans")}
      </Text>

      {/* ADIM 1 — MODEL: yalnız araştırma kipinde (karar #13: gizleme SİMETRİK). */}
      {arastirmaKipi ? (
        <ModelSecimKartlari
          modeller={secilebilirModeller}
          secili={hedefModeli}
          onSec={setHedefModeli}
          kilitli={modelKilitli}
          kilitNedeni={t("ai.pro.modelKilitli")}
          kurulum={kurulum}
          arastirmaAcik={arastirmaAcik}
          fantomAcik={fantomAcik}
        />
      ) : null}

      {/* T3 · Y189: araştırma modelinde Koşullu | Koşulsuz (hazırlık / seans sürerken kilitli — kip mühürdedir). */}
      {arastirmaKipi && (hedefModeli === "petri" || hedefModeli === "fantom") ? (
        <KosulSecici kosulsuz={kosulsuz} onDegis={setKosulsuz} kilitli={modelKilitli} testID="ai-pro-kosul" />
      ) : null}
      {arastirmaKipi && sunucuKosulsuz && (hazirlik || running) ? (
        <Text testID="ai-pro-kosulsuz-rozeti" style={[styles.note, { color: colors.warning, fontWeight: "bold" }]}>
          {t("ai.pro.kosulsuzEtkin")}
        </Text>
      ) : null}

      {/* T3 · Y190: kabin kamerası seçimi burada (Ayarlar'dan kalktı) — bu makinede; hazırlık / seans kamerayı tutarken kilitli. */}
      {kabinKamerasiKullanilir() ? <KabinKamerasiKarti kilitli={modelKilitli} /> : null}

      {/* Kamera görüntüsü: web = sunucudan (Image), mobil = telefon kamerası (CameraView) */}
      <View
        testID="ai-pro-kamera-kutusu"
        style={[styles.camBox, kutu ? { width: kutu.width, height: kutu.height, alignSelf: "center" } : null]}
        onLayout={(e) => {
          const w = Math.round(e.nativeEvent.layout.width);
          // Kutu kendi genişliğini de değiştirdiği için yalnız BÜYÜK sapmalarda yeniden ölç
          // (aksi hâlde ölç → daralt → ölç döngüsü kurulur).
          setKutuW((eski) => (eski > 0 ? eski : w));
        }}
      >
        {IS_WEB ? (
          overlayB64 ? (
            <Image source={{ uri: `data:image/jpeg;base64,${overlayB64}` }} style={styles.cam} resizeMode="contain" />
          ) : (
            // B3 (siyah ekran): `hazirlik` burada YOK SAYILIYORDU → önizleme açıkken kutu "AI Pro durdu."
            // yazarken hemen altındaki şerit "Hayvan aranıyor…" diyordu (çelişki). Hata varsa NEDENİ göster.
            <Text style={styles.camPlaceholder}>
              {hazirlikHata
                ? `⚠️ ${hazirlikHata}`
                : running
                  ? t("ai.pro.kamera.goruntuBekleniyor")
                  : hazirlik
                    ? t("ai.pro.kamera.sunucuAciliyor")
                    : t("ai.pro.kamera.durdu")}
            </Text>
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
              accessibilityRole="button" accessibilityLabel={t("ai.pro.kamera.cevirEtiketi")}>
              <Text style={styles.flipText}>🔄</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <Text style={styles.camPlaceholder}>
            {running || hazirlik ? t("ai.pro.kamera.izinBekleniyor") : t("ai.pro.kamera.durduBaslat")}
          </Text>
        )}
        {/* ADIM 3 — hedefi KARE ÜSTÜNDEN seç (yalnız araştırma; kedide hedef organ çiplerinden).
            ⚠️ Halkalar kutunun İÇİNDE mutlak konumlanır ve `pxn` (kare oranı) ile yerleşir. */}
        {arastirmaKipi ? (
          <HedefHalkalari
            hedefler={hedefAdaylari}
            seciliId={organId}
            onSec={changeOrgan}
            kutu={kutu}
            kilitli={false}
          />
        ) : null}
      </View>

      {/* Canlı metrikler */}
      <View style={styles.metricRow}>
        <Metric label={arastirmaKipi ? modelProf.hedefEtiketi : t("ai.pro.metrik.organ")} value={detected ? t("ai.pro.metrik.bulundu") : "—"} />
        <Metric label={t("ai.pro.metrik.guven")} value={typeof reliability === "number" ? t("ai.ortak.yuzde", { deger: Math.round(reliability * 100) }) : "—"} />
        <Metric label="X (mm)" value={`${targetX ?? "—"}`} />
        <Metric label="Y (mm)" value={`${targetY ?? "—"}`} />
        <Metric label="Z (mm)" value={`${targetZ ?? "—"}`} />
      </View>

      {/* Sunum-katmanı XAI (2026-08-26): "Güven %X"in NEDENİ — operatör düşük güvenin poz mu,
          maske-dışı mı, kalibrasyonsuzluk mu olduğunu görür. Eski backend alanı göndermez → gizli. */}
      {/* ⚠️ Sahip 2026-09-12: "üç nokta sorunu ve devamını göremeyiş" — güven dökümü bir
          CÜMLEDİR ve iki satırda kesildiğinde gerekçenin yarısı (kalibrasyon uyarısı dahil)
          okunamıyordu. Artık dokunuşla açılıyor. */}
      {guvenDokumu && typeof guvenDokumu.pose_confidence === "number" ? (
        <GenisletilebilirMetin style={styles.guvenDokumu} satir={2} testID="aipro-guven-dokumu">
          {t("ai.pro.guven.dokum", {
            poz: Math.round((guvenDokumu.pose_confidence ?? 0) * 100),
            derinlik: ondalik(guvenDokumu.depth_factor ?? 1, 2),
            maske: (guvenDokumu.mask_factor ?? 1) < 1 ? t("ai.pro.guven.maskeDisi") : "",
            belirsizlik: ondalik(guvenDokumu.uncertainty_factor ?? 1, 2),
            kalibrasyon:
              guvenDokumu.calibration_cap != null
                ? t("ai.pro.guven.kalibrasyonsuz", { tavan: Math.round(guvenDokumu.calibration_cap * 100) })
                : "",
          }) +
            hatKalitesiMetni(guvenDokumu)}
        </GenisletilebilirMetin>
      ) : null}

      {/* 3B KONUM ROZETİ + HEDEF LİSTESİ (yalnız araştırma). Rozet, işaret görünmediğinde önerinin
          NEDEN gelmediğini peşinen söyler; liste halkaların ZORUNLU erişilebilir yedeğidir. */}
      {arastirmaKipi ? (
        <>
          <KalibrasyonRozeti yontem={yontemAktif} gorunur={hazirlik || running} />
          {ood ? (
            <Text style={styles.note}>
              {t("ai.pro.konumEgitimDisi")}
            </Text>
          ) : null}
          <HedefListesi
            hedefler={hedefAdaylari}
            seciliId={organId}
            onSec={changeOrgan}
            otomatikMi
          />
        </>
      ) : null}

      {/* HAZIRLIK ŞERİDİ — aşamayı ve çıkış yolunu gösterir (2026-08-24). */}
      {hazirlik ? (
        <View style={[styles.hazirlikKutu, dusukGuven && styles.hazirlikKutuUyari]}>
          <GenisletilebilirMetin style={styles.hazirlikMetin} satir={3} testID="aipro-hazirlik-metni">
            {oneriHatasi || seritMetni}
          </GenisletilebilirMetin>
          <TouchableOpacity
            style={styles.hazirlikIptal}
            onPress={vazgec}
            accessibilityRole="button"
            accessibilityLabel={t("ai.pro.hazirlikIptal")}
          >
            <Text style={styles.hazirlikIptalMetin}>{t("ortak.vazgec")}</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* Organ seçimi — KEDİ hattı. Araştırmada GİZLİ: fantom/petri hedefi kare üstünden seçilir. */}
      {arastirmaKipi ? null : (
        <>
      <Text style={styles.label}>{t("ai.pro.hedefOrgan")}</Text>
      <View style={styles.organGrid}>
        {ORGANS.map((o) => (
          <TouchableOpacity
            key={o.id}
            style={[styles.organChip, organId === o.id && styles.organChipActive]}
            onPress={() => changeOrgan(o.id)}
            accessibilityRole="button"
            accessibilityState={{ selected: organId === o.id }}
            accessibilityLabel={t("ai.pro.hedefOrganEtiket", { name: o.name })}
          >
            <Text style={[styles.organText, organId === o.id && styles.organTextActive]}>{o.name}</Text>
          </TouchableOpacity>
        ))}
      </View>
        </>
      )}

      {/* Süre + kalibrasyon */}
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>{t("ai.pro.sure")}</Text>
          <TextInput style={styles.input} value={duration} onChangeText={setDuration} keyboardType="numeric" editable={!running} selectTextOnFocus />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>{t("ai.pro.kalan")}</Text>
          <Text style={styles.countdown}>{running ? fmtSec(remaining) : "—"}</Text>
        </View>
        <View style={{ flex: 1, justifyContent: "flex-end" }}>
          <TouchableOpacity
          style={[styles.calBtn, localized && styles.calBtnDone]}
          onPress={relocalize}
          accessibilityRole="button"
          accessibilityLabel={localized ? t("ai.pro.yenidenKonumla.konumlandiEtiket") : t("ai.pro.yenidenKonumla.etiket")}
        >
            <Text style={styles.calBtnText} numberOfLines={1} adjustsFontSizeToFit>{localized ? t("ai.pro.yenidenKonumla.konumlandi") : t("ai.pro.yenidenKonumla.dugme")}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Start / Stop */}
      {/* a11y: otonom TEDAVİ başlatan/durduran düğmede rol ve etiket yoktu → ekran okuyucu
          kullanan operatör butonu ayırt edemiyordu. Durum da `accessibilityState` ile bildirilir. */}
      <TouchableOpacity
        style={[
          styles.toggle,
          running ? styles.toggleStop : styles.toggleStart,
          (busy || baslatKapali) && { opacity: 0.5 },
        ]}
        onPress={running ? stop : start}
        disabled={busy || baslatKapali}
        accessibilityRole="button"
        accessibilityState={{ busy, selected: running, disabled: busy || baslatKapali }}
        accessibilityLabel={
          running
            ? t("ai.pro.dugme.durdurEtiket")
            : kediSurusKapali
              ? t("ai.pro.dugme.analizOneriEtiket")
              : t("ai.pro.dugme.baslatEtiket")
        }
        accessibilityHint={
          running
            ? t("ai.pro.dugme.durdurIpucu")
            : baslatKapali
              ? baslatKapaliNedeni
              : kediSurusKapali
                ? t("ai.pro.dugme.analizOneriIpucu")
                : t("ai.pro.dugme.baslatIpucu")
        }
      >
        <Text style={styles.toggleText} numberOfLines={1} adjustsFontSizeToFit>{running ? t("ai.pro.dugme.durdur") : hazirlik ? t("ai.pro.dugme.hazirlaniyor") : arastirmaKipi ? t("ai.pro.dugme.hazirligiBaslat") : kediSurusKapali ? t("ai.pro.dugme.analizOneri") : t("ai.pro.dugme.baslat")}</Text>
      </TouchableOpacity>
      {/* Y142: neden + eylem GÖRÜNÜR (yalnız erişilebilirlik ipucuna yazmak "düğme bozuk" izlenimi verirdi). */}
      {kediSurusKapali && !running ? (
        <Text style={styles.note} testID="ai-pro-kedi-surus-kapali">{kediSurusKapaliMetni()}</Text>
      ) : null}
      {/* ⚠️ Pasif düğmenin SEBEBİ GÖRÜNÜR olmalı: yalnız `accessibilityHint`e yazmak, ekran
          okuyucu kullanmayan operatöre "düğme çalışmıyor" (yazılım arızası) izlenimi verirdi. */}
      {baslatKapali ? <Text style={styles.note}>{baslatKapaliNedeni}</Text> : null}

      {/* Per-coil diagnostik tablo (7 bobin; bobin 8 kapalı) */}
      <Text style={styles.label}>{t("ai.pro.bobinDiagnostigi")}</Text>
      {/* Y54 (sahip): operatörün durdurduğu bobin otomasyona yenilmez — neden AÇIKÇA yazılır ("sürülmedi" yetmez). */}
      {perCoil.some((c) => c.planDisi) ? (
        <Text style={styles.note} testID="ai-pro-plan-disi">
          {perCoil
            .filter((c) => c.planDisi)
            .map((c) => t("ai.pro.planDisiBobin", { id: c.id }))
            .join(" · ")}
        </Text>
      ) : null}
      <View style={styles.table}>
        <View style={styles.tr}>
          <Text style={[styles.th, { flex: 1 }]}>{t("ai.pro.tablo.bobin")}</Text>
          <Text style={[styles.th, { flex: 1 }]}>{t("kontrol.bobin.frekans")}</Text>
          <Text style={[styles.th, { flex: 1 }]}>{t("kontrol.bobin.duty")}</Text>
          <Text style={[styles.th, { flex: 1 }]}>{t("kontrol.sinir.faz")}</Text>
        </View>
        {(perCoil.length ? perCoil : Array.from({ length: 7 }, (_, i): Coil => ({ id: i + 1, freq: 0, duty: 0, phase: 0 }))).map((c) => (
          <View key={c.id} style={styles.tr}>
            <Text style={[styles.td, { flex: 1 }]}>{c.id}</Text>
            <Text style={[styles.td, { flex: 1 }]}>{c.freq} Hz</Text>
            <Text style={[styles.td, { flex: 1 }]}>
              {c.planDisi
                ? t("ai.pro.tablo.planDisi")
                : c.suruldu === false
                  ? c.duty > 0
                    ? t("ai.pro.tablo.surulmediPlan", { duty: c.duty })
                    : t("ai.pro.tablo.surulmedi")
                  : `${c.duty}%`}
            </Text>
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
  // Sunum-katmanı XAI (2026-08-26): güven dökümü satırı — küçük, sessiz, metrik altına.
  guvenDokumu: { color: colors.textMuted, fontSize: typography.small, marginTop: 4 },
  camBox: {
    // Yükseklik artık ÖLÇÜLEN kutudan (oran kilidi); bu yalnız ölçüm gelene kadarki taban.
    width: "100%", minHeight: rs(200), backgroundColor: "#000", borderRadius: 12,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
    borderWidth: 1, borderColor: "#1e3a5f",
  },
  cam: { width: "100%", height: "100%" },
  camOverlay: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, width: "100%", height: "100%" },
  camPlaceholder: { color: colors.textMuted, fontSize: typography.small },
  // [S3/S7] 32 px dokunma hedefi 320 px'te 27 px'e düşüyordu; taban ölçekle küçülmeyen touch.min.
  flipBtn: {
    position: "absolute", top: 8, right: 8, backgroundColor: "rgba(0,0,0,0.5)",
    borderRadius: 22, width: touch.min, height: touch.min, alignItems: "center", justifyContent: "center",
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
