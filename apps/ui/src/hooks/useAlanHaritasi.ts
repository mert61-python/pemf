// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A3 — canlı 3B alan haritası aboneliği. `acik` true iken sunucuya abone olunur (SAYAÇLI: `LiveDataContext.alanAbone`;
 * Kontrol kartı ve Simülasyon köprüsü birlikte açık olabilir), kapanınca / bileşen sökülünce çıkılır. Kapalıyken null — eski harita
 * gösterilmez. Sunucu yalnız abone varken hesaplar (`servers/canli_alan.py`).
 */
import { useEffect } from "react";
import { useLiveData } from "@/context/LiveDataContext";
import type { AlanHaritasiVerisi } from "@/services/alanHaritasi";

export function useAlanHaritasi(acik: boolean): AlanHaritasiVerisi | null {
  const { alanHaritasi, alanAbone } = useLiveData();
  useEffect(() => {
    if (!acik || !alanAbone) return undefined;
    alanAbone(true);
    return () => alanAbone(false);
  }, [acik, alanAbone]);
  return acik ? alanHaritasi ?? null : null;
}
