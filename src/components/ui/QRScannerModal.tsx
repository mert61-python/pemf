/**
 * QR Kod Tarayıcı Ekranı (Modal)
 * ================================
 * Kullanıcı "QR Tara" butonuna bastığında açılır.
 * LattePanda'nın GUI'sinde gösterilen QR kodu tarar
 * ve server adresini otomatik olarak kaydeder.
 *
 * Alternatif olarak, kamera izni yoksa manuel giriş yapılabilir.
 */

import React, { useState, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  Alert,
  Dimensions,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { X, QrCode, Wifi, Globe } from "lucide-react-native";
import { colors, spacing, typography, radius } from "@/theme/tokens";
import { updateServiceConfig } from "@/services/config";
import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "@pemf_server_address";
const { width: SCREEN_W } = Dimensions.get("window");

interface QRScannerModalProps {
  visible: boolean;
  onClose: () => void;
  onConnected: (address: string) => void;
}

export function QRScannerModal({ visible, onClose, onConnected }: QRScannerModalProps) {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [statusText, setStatusText] = useState("");

  const handleBarCodeScanned = async ({ data }: { data: string }) => {
    if (scanned) return;
    setScanned(true);
    setStatusText("Bağlantı test ediliyor...");

    try {
      // QR kod içeriği: https://xxxx.trycloudflare.com veya 192.168.1.100
      const base = data.startsWith("http") ? data.replace(/\/$/, "") : `http://${data}:8000`;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const res = await fetch(`${base}/api/health`, { signal: controller.signal });
      clearTimeout(timeout);

      if (res.ok) {
        updateServiceConfig(data);
        await AsyncStorage.setItem(STORAGE_KEY, data).catch(() => {});
        setStatusText("✅ Bağlantı başarılı!");
        onConnected(data);
        setTimeout(onClose, 1500);
      } else {
        setStatusText("❌ Sunucuya ulaşılamadı. Tekrar deneyin.");
        setTimeout(() => setScanned(false), 2000);
      }
    } catch {
      setStatusText("❌ Bağlantı hatası. QR kodu kontrol edin.");
      setTimeout(() => setScanned(false), 2000);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="fullScreen" onRequestClose={onClose}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>QR Kod Tara</Text>
            <Text style={styles.subtitle}>LattePanda ekranındaki QR kodu tarayın</Text>
          </View>
          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <X color={colors.text} size={24} />
          </TouchableOpacity>
        </View>

        {/* Bilgi Kartları */}
        <View style={styles.infoRow}>
          <View style={styles.infoCard}>
            <Wifi color={colors.primary} size={18} />
            <Text style={styles.infoText}>Aynı Wi-Fi{"\n"}Yerel IP QR</Text>
          </View>
          <View style={styles.infoCard}>
            <Globe color={colors.warning} size={18} />
            <Text style={styles.infoText}>Farklı Ağ{"\n"}Tünel URL QR</Text>
          </View>
        </View>

        {/* Kamera */}
        {!permission?.granted ? (
          <View style={styles.permissionBox}>
            <QrCode color={colors.textMuted} size={48} />
            <Text style={styles.permText}>Kamera iznine ihtiyaç var</Text>
            <TouchableOpacity style={styles.permBtn} onPress={requestPermission}>
              <Text style={styles.permBtnText}>İzin Ver</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.cameraBox}>
            <CameraView
              style={StyleSheet.absoluteFill}
              facing="back"
              onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            />
            {/* Tarama çerçevesi */}
            <View style={styles.scanFrame} />
          </View>
        )}

        {/* Durum mesajı */}
        {statusText ? (
          <View style={styles.statusBox}>
            <Text style={styles.statusText}>{statusText}</Text>
          </View>
        ) : (
          <Text style={styles.hintText}>
            📍 LattePanda'da main.py çalışırken GUI'de veya konsolda QR kodu görünür.{"\n"}
            QR'yi kamera çerçevesine getirin, otomatik taranacak.
          </Text>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: spacing.lg,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: spacing.lg,
    paddingTop: spacing.xl,
  },
  title: { color: colors.text, fontSize: typography.title, fontWeight: "800" },
  subtitle: { color: colors.textMuted, fontSize: typography.small, marginTop: 2 },
  closeBtn: {
    backgroundColor: colors.bgAlt,
    borderRadius: radius.full,
    padding: spacing.sm,
  },
  infoRow: {
    flexDirection: "row",
    gap: spacing.md,
    marginBottom: spacing.lg,
  },
  infoCard: {
    flex: 1,
    backgroundColor: colors.bgAlt,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: "center",
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  infoText: {
    color: colors.textMuted,
    fontSize: typography.caption,
    textAlign: "center",
  },
  cameraBox: {
    flex: 1,
    borderRadius: radius.lg,
    overflow: "hidden",
    position: "relative",
    backgroundColor: "#000",
    maxHeight: 420,
  },
  scanFrame: {
    position: "absolute",
    top: "50%",
    left: "50%",
    width: 200,
    height: 200,
    marginTop: -100,
    marginLeft: -100,
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: radius.md,
  },
  permissionBox: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.lg,
  },
  permText: { color: colors.textMuted, fontSize: typography.body },
  permBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
  },
  permBtnText: { color: "#fff", fontWeight: "bold" },
  statusBox: {
    backgroundColor: colors.bgAlt,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  statusText: {
    color: colors.text,
    fontSize: typography.body,
    textAlign: "center",
    fontWeight: "600",
  },
  hintText: {
    color: colors.textMuted,
    fontSize: typography.small,
    textAlign: "center",
    lineHeight: 20,
    marginTop: spacing.lg,
  },
});
