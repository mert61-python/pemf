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
import { serviceConfig } from "@/services/config";
import { useAuth } from "@/context/AuthContext";
import { AiSpecApprovalModal, type AiProposalMeta, type AiProposalSpecs } from "@/components/domain/AiSpecApprovalModal";

const ORGANS = [
  { id: 0, name: "Tüm Vücut" }, { id: 1, name: "Mide" }, { id: 2, name: "Böbrek" },
  { id: 3, name: "Karaciğer" }, { id: 4, name: "Mesane" }, { id: 5, name: "Pankreas" }, { id: 6, name: "Bağırsak" },
];

const IS_WEB = Platform.OS === "web";

type Coil = { id: number; freq: number; duty: number; phase: number };
type FrameResult = {
  image_base64?: string;
  detected?: boolean;
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
interface AiProStatus { active?: boolean; localized?: boolean; organId?: number; remainingSec?: number }
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

  // Backend durumunu senkronla (özellikle süre dolup auto-stop olduğunda).
  useEffect(() => {
    let alive = true;
    const sync = async () => {
      const st = await apiGet<AiProStatus | null>("/ai/pro/status", null, { silent: true });
      if (!alive || !st) return;
      const active = Boolean(st.active);
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
    // SERT ONAY KAPISI (2026-08-06): artık doğrudan başlatMIYORUZ. Önce backend'den öneri
    // alınır (donanıma dokunmaz), hekim modalda görüp onaylar, ancak sonra /start çağrılır.
    const prop = await apiPost<AiProposeResponse | null>(
      "/ai/pro/propose",
      { organ_id: organId, duration_minutes: parseInt(duration) || 20 },
      null
    );
    setBusy(false);
    if (!prop?.proposalId) return;   // apiPost hata mesajını zaten gösterdi (409/422 dahil)
    setProposal(prop);
  }, [organId, duration, permission, requestPermission]);

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
      { proposal_id: proposal.proposalId, patient_name: patientName || "" },
      null
    );
    setApprovalBusy(false);
    if (res?.status === "success") {
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
    if (!res) platformAlert("Yeniden konumlandırılamadı", "Komut sunucuya ulaşmadı — tekrar deneyin.");
  }, []);

  // ── Mobil: telefon kamerasından periyodik kare yakala → /ai/ai_pro/frame ──
  useEffect(() => {
    if (IS_WEB || !running) return;
    const capture = async () => {
      if (inFlightRef.current || !cameraRef.current || !runningRef.current) return;
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
    captureIntervalRef.current = setInterval(capture, 400);
    return () => {
      if (captureIntervalRef.current) {
        clearInterval(captureIntervalRef.current);
        captureIntervalRef.current = null;
      }
    };
  }, [running]);

  // Unmount'ta: interval'i temizle + ÇALIŞAN otonom tedaviyi DURDUR.
  // YÜKSEK fix: panel kapanınca (tab/modül değişimi) backend bobinleri BAŞSIZ sürmeye devam ediyordu
  // (operatör göremez/kontrol edemez = güvenlik riski). runningRef güncel durumu tutar (cleanup closure'u
  // stale 'running' yakalamasın). Best-effort fire-and-forget stop (unmount'ta await edilemez).
  useEffect(() => () => {
    if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
    if (runningRef.current) {
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
        ) : running && permission?.granted ? (
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
            {running ? "Kamera izni bekleniyor…" : "AI Pro durdu. Başlat → kamera açılır."}
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
        <Text style={styles.toggleText} numberOfLines={1} adjustsFontSizeToFit>{running ? "⏹ AI Pro'yu Durdur" : "🚀 AI Pro Başlat (1Hz DDS)"}</Text>
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
