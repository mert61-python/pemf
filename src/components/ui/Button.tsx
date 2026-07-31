import { ReactNode, useRef } from "react";
import { ActivityIndicator, Animated, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { colors, radius, spacing, typography, rs, rf, gradients, motion, elevation } from "@/theme/tokens";
import { useReducedMotion } from "@/hooks/useReducedMotion";

type ButtonVariant = "primary" | "danger" | "success" | "secondary" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps {
  label: string;
  icon?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  block?: boolean;
}

// Gradyanlı varyantlar + eşleşen renkli ışıltı.
const GRAD: Partial<Record<ButtonVariant, [string, string]>> = {
  primary: gradients.primary,
  danger: gradients.danger,
  success: gradients.success,
};
const GLOW: Partial<Record<ButtonVariant, "glowPrimary" | "glowDanger" | "glowSuccess">> = {
  primary: "glowPrimary",
  danger: "glowDanger",
  success: "glowSuccess",
};

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export function Button({
  label, icon, variant = "primary", size = "md", onPress, disabled, loading, block,
}: ButtonProps) {
  // DÜŞÜK fix: çift-tık koruması — tıbbi "Başlat/Uygula/Sil" hızlı çift-dokunuşta iki kez tetiklenmesin.
  const lastPressRef = useRef(0);
  const lastFnRef = useRef<typeof onPress>(undefined);
  const scale = useRef(new Animated.Value(1)).current;
  const reduceMotion = useReducedMotion();

  const inactive = disabled || loading;
  const grad = GRAD[variant];
  const glowKey = GLOW[variant];
  const solid = variant === "secondary" || variant === "ghost";

  const springTo = (toValue: number) => {
    // #118: "hareketi azalt" açıkken bas-küçülme animasyonunu atla (statik).
    if (reduceMotion) { scale.setValue(1); return; }
    Animated.spring(scale, {
      toValue,
      useNativeDriver: true,
      damping: motion.spring.damping,
      stiffness: motion.spring.stiffness,
      mass: motion.spring.mass,
    }).start();
  };

  const handlePress = () => {
    const now = Date.now();
    // #120: çift-tık guard'ı YALNIZ AYNI eylem için (idempotent submit). onPress KİMLİĞİ değiştiyse
    // (toggle-stili buton: Başlat↔Durdur aynı instance'ta) ikinci dokunuşu YUTMA.
    if (onPress === lastFnRef.current && now - lastPressRef.current < 400) return;
    lastPressRef.current = now;
    lastFnRef.current = onPress;
    if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    onPress?.();
  };

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPress={handlePress}
      onPressIn={() => springTo(motion.pressScale)}
      onPressOut={() => springTo(1)}
      style={[
        styles.base,
        SIZE[size],
        block && styles.block,
        grad ? { backgroundColor: grad[1] } : variant === "ghost" ? styles.ghost : styles.secondary,
        !inactive && (glowKey ? elevation(glowKey) : variant === "secondary" ? elevation("sm") : null),
        { transform: [{ scale }] },
        inactive && styles.disabled,
      ]}
    >
      {grad ? (
        <>
          <LinearGradient
            colors={grad}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[StyleSheet.absoluteFill, styles.fillRadius]}
          />
          <LinearGradient
            colors={gradients.sheen}
            start={{ x: 0, y: 0 }}
            end={{ x: 0, y: 1 }}
            style={styles.sheen}
            pointerEvents="none"
          />
        </>
      ) : null}
      <View style={styles.content}>
        {loading ? (
          <ActivityIndicator color={solid ? colors.text : colors.white} size="small" />
        ) : icon ? (
          <View style={styles.icon}>{icon}</View>
        ) : null}
        <Text
          style={[styles.label, LABEL[size], variant === "ghost" && styles.ghostLabel, variant === "secondary" && styles.secondaryLabel]}
          numberOfLines={1}
        >
          {label}
        </Text>
      </View>
    </AnimatedPressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.btn,
    overflow: Platform.OS === "web" ? "hidden" : "visible", // web: gradyan köşe kırpması; native: gölge görünür
  },
  fillRadius: { borderRadius: radius.btn },
  sheen: {
    position: "absolute",
    top: 0, left: 0, right: 0, height: "58%",
    borderTopLeftRadius: radius.btn,
    borderTopRightRadius: radius.btn,
  },
  content: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  // boyutlar
  size_sm: { minHeight: rs(38), paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  size_md: { minHeight: rs(46), paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  size_lg: { minHeight: rs(54), paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  block: { alignSelf: "stretch", width: "100%" },
  // solid varyantlar
  secondary: { backgroundColor: colors.panelSoft, borderColor: colors.border, borderWidth: 1 },
  ghost: { backgroundColor: "transparent", borderColor: colors.border, borderWidth: 1 },
  disabled: { opacity: 0.45 },
  icon: { alignItems: "center", justifyContent: "center" },
  label: { color: colors.white, fontWeight: "700" },
  label_sm: { fontSize: typography.caption },
  label_md: { fontSize: rf(14.5) },
  label_lg: { fontSize: typography.subtitle },
  ghostLabel: { color: colors.text },
  secondaryLabel: { color: colors.text },
});

const SIZE = { sm: styles.size_sm, md: styles.size_md, lg: styles.size_lg };
const LABEL = { sm: styles.label_sm, md: styles.label_md, lg: styles.label_lg };
