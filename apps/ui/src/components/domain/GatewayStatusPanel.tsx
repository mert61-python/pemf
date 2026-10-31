// Author: mertaygn, cglrgrkn
/**
 * GatewayStatusPanel — Python gateway_status_widget.py'nin React karşılığı.
 * Mosquitto broker, MQTT, Network, Bridge durumunu gösterir.
 */
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { useState, useEffect, useCallback } from "react";
import { colors, spacing, typography, rf, rs, radius } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import { apiGet } from "@/services/apiClient";
import type { ConnectionState } from "@/types/domain";
import { espEtkinMi } from "@/services/bobinGorunurlugu";
import { useTranslation } from "react-i18next";

interface GatewayInfo {
  mqttConnected: boolean;
  brokerRunning: boolean;
  bridgeConnected: boolean;
  networkOnline: boolean;
  hotspotActive: boolean;
  gatewayState?: ConnectionState;
  /** T-e (yalnız-ek): ağ izleme servisi yok / henüz ölçmedi → İnternet satırı "Bilinmiyor". Eski backend göndermez. */
  internetBilinmiyor?: boolean;
  /** T-e (yalnız-ek): ESP alt sistemi bilinçli kapalı mı (`PEMF_ESP_ENABLED`). Eski backend göndermez. */
  espEtkin?: boolean;
}

/** Satır durumu: bağlantı yokken bayat değeri yeşil göstermemek için "unknown" eklendi. */
type RowState = ConnectionState | "unknown";

export function GatewayStatusPanel() {
  const { t } = useTranslation();
  const { snapshot, wsConnected } = useLiveData();
  const [gwInfo, setGwInfo] = useState<GatewayInfo>({
    mqttConnected: false,
    brokerRunning: false,
    bridgeConnected: false,
    networkOnline: false,
    hotspotActive: false,
  });
  // T-e (Tezgâh-2 #8): hiç başarılı yoklama yoksa (uç yok / servis yok) değerler BAŞLANGIÇ varsayılanıdır, ölçüm değil.
  const [gwAlindi, setGwAlindi] = useState(false);

  const refresh = useCallback(async () => {
    // exhaustive-deps + hata-dayanıklılık: fallback null → başarısız poll SON İYİ değeri korur
    // (eskiden yakalanan ilk gwInfo'ya set ediyordu = hatada başlangıca sıfırlama). refresh stable kalır.
    const data = await apiGet<GatewayInfo | null>("/gateway/status", null, { silent: true });
    if (data) {
      setGwInfo(data);
      setGwAlindi(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  // YANLIŞ GÜVENCE: aşağıdaki satırların hepsi BAYAT snapshot'tan/son başarılı poll'den okunuyor.
  // WS koptuğunda bunlar son bilinen (genelde yeşil "Aktif") değerde donuyordu → operatör sistemi
  // sağlıklı sanıyordu. SystemInfoPanel'de bu koruma (#69) vardı, burada YOKTU. Bağlantı yokken
  // hiçbir alt-bileşen durumu "online" gösterilmez, "Bilinmiyor"a düşer.
  const stale = !wsConnected;
  const gated = (s: ConnectionState | undefined, dflt: ConnectionState): RowState =>
    stale ? "unknown" : (s ?? dflt);
  // Y230 (BE 3 · sahip): ESP KAPALIYKEN "Sistem Bağlantısı" (MQTT) ve "Cihaz Köprüsü" satırları HİÇ çizilmez (T-e'nin "Devre dışı"
  // gösterimini aşar). Tek kaynak backend'in ESP-etkin bilgisi (`espEtkinMi`); ESP açıkken satırlar eski davranışla.
  const espEtkin = espEtkinMi(snapshot);
  // İnternet: bağlantı yok / hiç yoklama alınmadı / servis ölçmedi → "Bilinmiyor" (eskiden "Kapalı" kırmızı — ölçülmemiş).
  const internetDurumu: RowState =
    stale || !gwAlindi || gwInfo.internetBilinmiyor ? "unknown" : gwInfo.networkOnline ? "online" : "offline";

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{t("ayarlar.sistemDurumu.baslik")}</Text>
        <TouchableOpacity
          onPress={refresh}
          style={styles.refreshBtn}
          accessibilityRole="button"
          accessibilityLabel={t("ayarlar.sistemDurumu.yenileEtiketi")}
        >
          <Text style={styles.refreshText}>↻</Text>
        </TouchableOpacity>
      </View>

      <GatewayRow label={t("ayarlar.sistemDurumu.uygulamaBaglantisi")} state={wsConnected ? "online" : "offline"} />
      {espEtkin && <GatewayRow label={t("ayarlar.sistemDurumu.sistemBaglantisi")} state={gated(snapshot.mqtt, "offline")} />}
      {espEtkin && (
        <GatewayRow
          label={t("ayarlar.sistemDurumu.cihazKoprusu")}
          state={gated(snapshot.gateway, "offline")}
          devreDisiMetni={t("ayarlar.sistemDurumu.devreDisi")}
          testID="sistem-durumu-kopru"
        />
      )}
      <GatewayRow label={t("ayarlar.sistemDurumu.donanimSurucusu")} state={gated(snapshot.stm, "warning")} />
      {/* gwInfo ayrı bir poll'den gelir; başarısız poll SON İYİ değeri korur (bilinçli) → bağlantı
          yokken o değeri de "Bilinmiyor" olarak göster, yeşil "Aktif" bırakma. */}
      <GatewayRow label={t("ayarlar.sistemDurumu.internetBaglantisi")} state={internetDurumu} testID="sistem-durumu-internet" />
      {/* ⚠️ KABLOSUZ BAĞLANTI (2026-08-10). `hotspotActive` zaten çekiliyordu ama HİÇ
          GÖSTERİLMİYORDU — yani PEMF-Gateway kapalıyken 6-8 numaralı bobinler sessizce
          bağlanamıyor, operatör sebebini hiçbir yerden göremiyordu. Backend hotspot'u açılışta
          otomatik başlatır (backend_service._start_hotspot_safe); bu satır sonucu görünür kılar.
          Y231 (BE 3b): adı ne olduğunu söyler — "Cihaz Wi-Fi'si (PEMF-Gateway)" (telefonların bağlandığı PC hotspot'u). */}
      <GatewayRow
        label={t("ayarlar.sistemDurumu.kablosuzBaglanti")}
        state={stale ? "unknown" : gwInfo.hotspotActive ? "online" : "offline"}
      />
    </View>
  );
}

function GatewayRow({
  label,
  state,
  devreDisiMetni,
  testID,
}: {
  label: string;
  state: RowState | boolean;
  /** T-e: bu satırda `devre_disi` için metin (varsayılan "Kurulu değil"); ESP bilinçli kapalıyken "Devre dışı". */
  devreDisiMetni?: string;
  testID?: string;
}) {
  const { t } = useTranslation();
  let resolvedState: RowState;
  if (typeof state === "boolean") {
    resolvedState = state ? "online" : "offline";
  } else {
    resolvedState = state;
  }

  const cfg = {
    online:  { color: "#22c55e", text: t("ayarlar.sistemDurumu.aktif"),      dot: "#22c55e" },
    warning: { color: "#f59e0b", text: t("ayarlar.sistemDurumu.uyari"),      dot: "#f59e0b" },
    offline: { color: "#ef4444", text: t("ayarlar.saklama.secenekKapali"),     dot: "#ef4444" },
    error:   { color: "#ef4444", text: t("ayarlar.sistemDurumu.hata"),       dot: "#ef4444" },
    unknown: { color: "#94a3b8", text: t("ayarlar.sistemDurumu.bilinmiyor"), dot: "#94a3b8" },
    // KURULU DEĞİL ≠ ARIZALI (ESP söküldü, 2026-09-11). Nötr gri + açık metin.
    devre_disi: { color: "#94a3b8", text: devreDisiMetni ?? t("ayarlar.sistemDurumu.kuruluDegil"), dot: "#475569" },
  }[resolvedState] ?? { color: "#475569", text: t("ayarlar.sistemDurumu.bilinmiyor"), dot: "#475569" };

  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowRight}>
        <View style={[styles.dot, { backgroundColor: cfg.dot }]} />
        <Text style={[styles.rowValue, { color: cfg.color }]} testID={testID}>
          {cfg.text}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#0a0f1e",
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: "#1e293b",
  },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  title: { color: colors.text, fontWeight: "700", fontSize: typography.body },
  refreshBtn: { padding: spacing.xs },
  refreshText: { color: colors.primary, fontSize: rf(18), fontWeight: "700" },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: rs(6),
    paddingHorizontal: spacing.sm,
    backgroundColor: "#0f172a",
    borderRadius: radius.md,
  },
  rowLabel: { flexShrink: 1, color: colors.textMuted, fontSize: typography.small },
  rowRight: { flexShrink: 0, flexDirection: "row", alignItems: "center", gap: rs(6) },
  dot: { width: rs(8), height: rs(8), borderRadius: 4 },
  rowValue: { fontSize: typography.small, fontWeight: "700" },
});
