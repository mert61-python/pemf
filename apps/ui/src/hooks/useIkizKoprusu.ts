// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A4 — dijital ikiz köprüsü kancası (`services/ikizKoprusu.ts`). `gonder` (çerçeve yüklenince dolu, yeniden yüklemede null)
 * verildikçe 2 Hz `pemf.ikiz.durum`; ikiz `pemf.ikiz.hazir` deyince alan haritasına abone olur ve her yeni haritada `pemf.ikiz.alan`.
 * Çerçeve değişince (yeniden yükleme / dil) `hazir` sıfırlanır → abonelik biter. Gönderim hatası (çerçeve gitmiş) yutulur.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useLiveData } from "@/context/LiveDataContext";
import { useAlanHaritasi } from "@/hooks/useAlanHaritasi";
import { DURUM_ARALIK_MS, alanIletisi, durumIletisi, hazirMi } from "@/services/ikizKoprusu";

export function useIkizKoprusu(gonder: ((metin: string) => void) | null): { gelen: (veri: unknown) => void; hazir: boolean } {
  const { snapshot } = useLiveData();
  const anlikRef = useRef(snapshot);
  anlikRef.current = snapshot;
  const [hazir, setHazir] = useState(false);
  const harita = useAlanHaritasi(hazir && gonder !== null);

  const guvenliGonder = useCallback(
    (o: object) => {
      try {
        gonder?.(JSON.stringify(o));
      } catch {
        /* çerçeve gitmiş / yeniden yükleniyor — sonraki turda yeni çerçeve */
      }
    },
    [gonder],
  );

  useEffect(() => {
    setHazir(false);
    if (!gonder) return undefined;
    guvenliGonder(durumIletisi(anlikRef.current));
    const id = setInterval(() => guvenliGonder(durumIletisi(anlikRef.current)), DURUM_ARALIK_MS);
    return () => clearInterval(id);
  }, [gonder, guvenliGonder]);

  useEffect(() => {
    if (hazir && harita) guvenliGonder(alanIletisi(harita));
  }, [hazir, harita, guvenliGonder]);

  const gelen = useCallback((veri: unknown) => {
    if (hazirMi(veri)) setHazir(true);
  }, []);
  return { gelen, hazir };
}
