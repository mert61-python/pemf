// Author: mertaygn, cglrgrkn
/**
 * "BU EKRAN KENDİ ACİL DURDURMA DÜĞMESİNİ ÇİZİYOR" — kayan ACİL DURDUR'un gizlenme sinyali (D1.E02 · A-51).
 * =====================================================================================================
 * Sahip kararı A-51: kayan düğme YALNIZ ekran GERÇEKTEN kendi durdurma düğmesini çiziyorsa gizlenir; rota adına göre
 * gizleme KALKTI. Eskiden `AppShell` "control"/"dashboard" rotalarında düğmeyi koşulsuz gizliyordu: ekran hata kartına
 * düşünce (bozuk paket) ya da Ana Ekran'ın kendi düğmesi STM kopunca kaybolunca ekranda durdurma kontrolü kalmıyordu
 * (ölçüldü, İG-6.2).
 *
 * KULLANIM: `<KendiDurdurmaIsareti />` ekranın acil durdurma düğmesinin HEMEN YANINA, AYNI koşulun içine konur — düğme
 * çizilmiyorsa işaret de takılı değildir. Ekran çökerse (ErrorBoundary) işaret sökülür ve kayan düğme geri gelir.
 * ⚠️ Gizleme yalnız FAZLALIĞI giderir (sahip 2026-09-12: "zaten bir sürü var"); hiçbir koşulda erişimi kaldırmaz.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const KayitBaglami = createContext<(() => () => void) | null>(null);

/** Kabuk (AppShell) kullanır: içerikteki takılı işaret sayısını izler. */
export function useKendiDurdurmaKaydi(): { takili: boolean; Saglayici: React.FC<{ children: React.ReactNode }> } {
  const [sayi, setSayi] = useState(0);
  const kaydet = useCallback(() => {
    setSayi((n) => n + 1);
    let sokuldu = false;
    return () => {
      if (sokuldu) return;
      sokuldu = true;
      setSayi((n) => Math.max(0, n - 1));
    };
  }, []);
  const Saglayici = useMemo(() => {
    function KendiDurdurmaSaglayici({ children }: { children: React.ReactNode }) {
      return <KayitBaglami.Provider value={kaydet}>{children}</KayitBaglami.Provider>;
    }
    return KendiDurdurmaSaglayici;
  }, [kaydet]);
  return { takili: sayi > 0, Saglayici };
}

/** Ekranın acil durdurma düğmesinin yanına konur; takılı olduğu sürece kayan düğme gizlenir. */
export function KendiDurdurmaIsareti(): null {
  const kaydet = useContext(KayitBaglami);
  useEffect(() => (kaydet ? kaydet() : undefined), [kaydet]);
  return null;
}
