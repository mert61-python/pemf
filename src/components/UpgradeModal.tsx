/**
 * UpgradeModal — gated bir özelliğe (real-time / research / üst-plan) dokununca gösterilen
 * BİLGİLENDİRİCİ modal. A1 + Apple 3.1.1: uygulama İÇİNDE satın-alma linki/CTA YOK — yalnız
 * "bu özellik X plan gerektirir, hesabınızdan yönetebilirsiniz" der. Satış web'de.
 */
import React from "react";
import { Modal, View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, typography, rf, rs } from "@/theme/tokens";
import { Sparkles, X, Zap, FlaskConical } from "lucide-react-native";
import { useEntitlement } from "@/context/EntitlementContext";
import { TIER_LABEL } from "@/config/entitlement";

export type UpgradeFeature = "realtime" | "research" | "tier";

const COPY: Record<UpgradeFeature, { title: string; desc: string; Icon: typeof Zap }> = {
  realtime: {
    title: "Gerçek-zamanlı işlem",
    desc: "Anlık, kuyruksuz AI Pro kapalı-döngü tedavi Pro+ planında sunulur. Pro planında istekler paylaşımlı kuyruğa girer.",
    Icon: Zap,
  },
  research: {
    title: "Araştırma Modu",
    desc: "Kanser-araştırma modelleri (fantom tümör, petri kuyu, böbrek RNA · CT · patoloji · hastalık) Araştırma eklentisiyle açılır.",
    Icon: FlaskConical,
  },
  tier: {
    title: "Bu özellik üst plan gerektirir",
    desc: "Aboneliğinizi yükselttiğinizde bu özellik otomatik açılır.",
    Icon: Sparkles,
  },
};

export function UpgradeModal({
  visible,
  onClose,
  feature = "tier",
}: {
  visible: boolean;
  onClose: () => void;
  feature?: UpgradeFeature;
}) {
  const { tier } = useEntitlement();
  const { title, desc, Icon } = COPY[feature];

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <TouchableOpacity
            style={styles.close}
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="Kapat"
          >
            <X size={20} color={colors.textMuted} />
          </TouchableOpacity>

          <View style={styles.iconRing}>
            <Icon size={30} color={colors.primary} />
          </View>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.desc}>{desc}</Text>

          <View style={styles.planRow}>
            <Text style={styles.planLabel}>Mevcut plan</Text>
            <Text style={styles.planVal}>{TIER_LABEL[tier]}</Text>
          </View>

          {/* A1 / Apple 3.1.1 uyumu: satın-alma linki/CTA YOK. */}
          <Text style={styles.note}>Aboneliğinizi hesabınızdan yönetebilirsiniz.</Text>

          <TouchableOpacity style={styles.btn} onPress={onClose} accessibilityRole="button">
            <Text style={styles.btnText}>Anladım</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.55)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  card: {
    width: "100%",
    maxWidth: rs(420),
    backgroundColor: colors.bgAlt,
    borderRadius: rs(20),
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xxl,
    alignItems: "center",
    gap: spacing.md,
  },
  close: { position: "absolute", top: spacing.md, right: spacing.md, padding: rs(6) },
  iconRing: {
    width: rs(64),
    height: rs(64),
    borderRadius: rs(20),
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(79,140,255,0.12)",
    borderWidth: 1,
    borderColor: "rgba(79,140,255,0.40)",
  },
  title: { fontSize: typography.title, fontWeight: "800", color: colors.text, textAlign: "center" },
  desc: {
    fontSize: typography.body,
    color: colors.textMuted,
    textAlign: "center",
    lineHeight: rf(22),
  },
  planRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    alignSelf: "stretch",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bg,
  },
  planLabel: { color: colors.textMuted, fontSize: typography.small },
  planVal: { color: colors.primary, fontWeight: "800", fontSize: typography.body },
  note: { color: colors.textMuted, fontSize: typography.small, textAlign: "center" },
  btn: {
    alignSelf: "stretch",
    marginTop: spacing.sm,
    paddingVertical: spacing.md,
    borderRadius: 12,
    backgroundColor: colors.primary,
    alignItems: "center",
  },
  btnText: { color: "#fff", fontWeight: "800", fontSize: typography.body },
});
