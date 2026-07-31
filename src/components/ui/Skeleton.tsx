import { useEffect, useRef, useState } from "react";
import { Animated, LayoutChangeEvent, StyleSheet, View, StyleProp, ViewStyle, DimensionValue } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { colors, radius, rs } from "@/theme/tokens";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface SkeletonProps {
  width?: DimensionValue;
  height?: number;
  round?: number;
  style?: StyleProp<ViewStyle>;
}

/**
 * Premium yükleniyor placeholder'ı — sabit spinner yerine gradyan süpürme (algılanan hız artar).
 * Süpürme px-tabanlı (onLayout genişliği) → her boyutta güvenilir. Native driver (UI-thread).
 */
export function Skeleton({ width = "100%", height = rs(16), round = radius.sm, style }: SkeletonProps) {
  const x = useRef(new Animated.Value(0)).current;
  const [w, setW] = useState(0);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    // #118: "hareketi azalt" açıkken shimmer döngüsünü ÇALIŞTIRMA (statik placeholder).
    if (reduceMotion) return;
    const loop = Animated.loop(
      Animated.timing(x, { toValue: 1, duration: 1200, useNativeDriver: true }),
    );
    loop.start();
    return () => loop.stop();
  }, [x, reduceMotion]);

  const onLayout = (e: LayoutChangeEvent) => setW(e.nativeEvent.layout.width);
  const translateX = x.interpolate({ inputRange: [0, 1], outputRange: [-(w || 1), w || 1] });

  return (
    <View onLayout={onLayout} style={[styles.base, { width, height, borderRadius: round }, style]}>
      {w > 0 ? (
        <Animated.View style={[StyleSheet.absoluteFill, { transform: [{ translateX }] }]}>
          <LinearGradient
            colors={["transparent", "rgba(255,255,255,0.12)", "transparent"]}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  base: { backgroundColor: colors.panelSoft, overflow: "hidden" },
});
