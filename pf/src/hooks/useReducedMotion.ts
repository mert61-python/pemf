// Author: mertaygn, cglrgrkn
import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

/**
 * #118: Sistem "hareketi azalt" (Reduce Motion) tercihi açık mı?
 * Açıkken animasyonlu primitifler (Skeleton shimmer, FadeInView, Button spring) hareketi ATLAMALI
 * — vestibüler rahatsızlık/erişilebilirlik (WCAG 2.3.3). Değişimi canlı dinler.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((v) => { if (mounted) setReduced(!!v); })
      .catch(() => {});
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", (v) => setReduced(!!v));
    return () => {
      mounted = false;
      // RN sürümüne göre remove() ya da sub.remove
      (sub as any)?.remove?.();
    };
  }, []);
  return reduced;
}
