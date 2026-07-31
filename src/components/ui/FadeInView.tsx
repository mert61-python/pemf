import { PropsWithChildren, useEffect, useRef } from "react";
import { Animated, StyleProp, ViewStyle } from "react-native";
import { motion } from "@/theme/tokens";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface FadeInViewProps extends PropsWithChildren {
  /** Kademeli giriş için gecikme (ms) — liste öğelerinde index*60 gibi. */
  delay?: number;
  /** Başlangıç aşağı-kayması (px) — 0 = yalnız solma. */
  offset?: number;
  style?: StyleProp<ViewStyle>;
}

/** Premium giriş animasyonu: monte olurken yumuşak solma + hafif yukarı-kayma (native driver). */
export function FadeInView({ children, delay = 0, offset = 14, style }: FadeInViewProps) {
  const v = useRef(new Animated.Value(0)).current;
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    // #118: "hareketi azalt" açıkken animasyonu ATLA → içerik hemen tam-opak/yerinde görünür.
    if (reduceMotion) {
      v.setValue(1);
      return;
    }
    const anim = Animated.timing(v, {
      toValue: 1,
      duration: motion.base,
      delay,
      useNativeDriver: true,
    });
    anim.start();
    return () => anim.stop();
  }, [v, delay, reduceMotion]);

  const animStyle = {
    opacity: v,
    transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [offset, 0] }) }],
  };
  return <Animated.View style={[style, animStyle]}>{children}</Animated.View>;
}
