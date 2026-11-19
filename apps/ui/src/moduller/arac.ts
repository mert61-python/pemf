// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — MODÜL ARAÇ TAKIMI: geliştiricinin paneli (`apps/ui/src/moduller/<kimlik>/Panel.tsx`) YALNIZ bunu kullanır (ana
 * uygulamanın iç dosyalarını içe aktarmaz — kit denetimi). `useModul()` → durum (saniyede bir) · uygula · başlat · durdur · son hata.
 * Ayar sınırları sunucuda zorlanır; ACİL DURDUR panelin DIŞINDA (Kontrol sekmesindeki büyük düğme) ve her koşulda modüllere de gider.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { modulApi, type ModulHata } from "@/services/moduller";

export const DURUM_ARALIK_MS = 1000;

export interface ModulAraci {
  durum: Record<string, unknown> | null;
  hata: ModulHata | null;
  mesgul: boolean;
  uygula: (ayar: Record<string, number>) => Promise<boolean>;
  baslat: () => Promise<boolean>;
  durdur: () => Promise<boolean>;
}

export function useModul(): ModulAraci {
  const [durum, setDurum] = useState<Record<string, unknown> | null>(null);
  const [hata, setHata] = useState<ModulHata | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const canli = useRef(true);

  const yenile = useCallback(async () => {
    const r = await modulApi.durum();
    if (!canli.current) return;
    if (r.tamam) setDurum((r.veri.surucu as Record<string, unknown> | undefined) ?? {});
    else setHata(r.hata);
  }, []);

  useEffect(() => {
    canli.current = true;
    void yenile();
    const id = setInterval(() => void yenile(), DURUM_ARALIK_MS);
    return () => {
      canli.current = false;
      clearInterval(id);
    };
  }, [yenile]);

  const calistir = useCallback(
    async (f: () => Promise<{ tamam: boolean; hata?: ModulHata }>) => {
      setMesgul(true);
      const r = await f();
      if (canli.current) {
        setMesgul(false);
        setHata(r.tamam ? null : (r.hata ?? null));
      }
      if (r.tamam) void yenile();
      return r.tamam;
    },
    [yenile],
  );

  return {
    durum,
    hata,
    mesgul,
    uygula: (ayar) => calistir(() => modulApi.uygula(ayar)),
    baslat: () => calistir(modulApi.baslat),
    durdur: () => calistir(modulApi.durdur),
  };
}
