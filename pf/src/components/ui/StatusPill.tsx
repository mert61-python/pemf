// Author: mertaygn, cglrgrkn
import { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { radius, spacing, typography, rs } from "@/theme/tokens";
import { ConnectionState } from "@/types/domain";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface StatusPillProps {
  label: string;
  state: ConnectionState;
}

const STATE_COLORS: Record<ConnectionState, { bg: string; fg: string; bd: string }> = {
  online: { bg: "rgba(34,197,94,0.10)", fg: "#22c55e", bd: "rgba(34,197,94,0.42)" },
  warning: { bg: "rgba(245,158,11,0.10)", fg: "#f59e0b", bd: "rgba(245,158,11,0.42)" },
  offline: { bg: "rgba(239,68,68,0.10)", fg: "#ef4444", bd: "rgba(239,68,68,0.42)" },
  // DÜŞÜK fix: error (cihaz-FAULT) ile offline (bağlantı-yok) görsel olarak AYRI ton (rose).
  error: { bg: "rgba(244,63,94,0.10)", fg: "#fb7185", bd: "rgba(244,63,94,0.45)" },
};

export function StatusPill({ label, state }: StatusPillProps) {
  // Beklenmeyen status string'inde çökmeyi önle (harici cihaz 'connecting'/'degraded' yayınlayabilir).
  const palette = STATE_COLORS[state] ?? STATE_COLORS.offline;
  const pulse = useRef(new Animated.Value(0)).current;

  // #118 "hareketi azalt" tercihi diğer primitiflere (Button vb.) uygulanmıştı, buraya değil:
  // StatusPill her ekranın üstünde 3-4 adet bulunduğundan sonsuz nabız, vestibüler duyarlılığı
  // olan kullanıcılar için en rahatsız edici animasyondu.
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    if (state !== "online" || reduceMotion) {
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.timing(pulse, { toValue: 1, duration: 1900, useNativeDriver: true }),
    );
    loop.start();
    return () => loop.stop();
  }, [state, pulse, reduceMotion]);

  const ringStyle = {
    opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] }),
    transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 2.6] }) }],
  };

  return (
    <View style={[styles.pill, { backgroundColor: palette.bg, borderColor: palette.bd }]}>
      <View style={styles.dotWrap}>
        {state === "online" ? (
          <Animated.View style={[styles.ring, ringStyle, { backgroundColor: palette.fg }]} />
        ) : null}
        <View style={[styles.dot, { backgroundColor: palette.fg }]} />
      </View>
      <Text style={[styles.label, { color: palette.fg }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignItems: "center",
    borderRadius: radius.md,
    borderWidth: 1,
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: rs(32),
    paddingHorizontal: spacing.md,
  },
  dotWrap: { width: rs(8), height: rs(8), alignItems: "center", justifyContent: "center" },
  ring: { position: "absolute", width: rs(8), height: rs(8), borderRadius: rs(4) },
  dot: { borderRadius: rs(4), height: rs(8), width: rs(8) },
  label: {
    fontSize: typography.caption,
    fontWeight: "700",
  },
});
