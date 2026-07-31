import { useEffect } from "react";
import type { NetInfoState } from "@react-native-community/netinfo";

/**
 * Ağ yeniden-erişilebilir olunca (WiFi geçişi / yeniden bağlanma) DEBOUNCE'lu `onReconnect` tetikler.
 * (audit B-2.4: LiveDataContext god-context'inden çıkarıldı → tek sorumluluk + tiplendi + test edilebilir.)
 *
 * NetInfo OPSİYONEL native modül (web'de yok) → dinamik require; paket yoksa no-op. Aynı durum sık
 * tekrarlandığında (NetInfo flapping) yalnız GERÇEK değişimde + 1.5sn debounce ile tetiklenir
 * (keşif/WS fırtınası önlenir).
 */
type NetInfoModule = {
  addEventListener: (cb: (state: NetInfoState) => void) => () => void;
};

export function useNetworkReachability(onReconnect: () => void): void {
  useEffect(() => {
    let NetInfo: NetInfoModule | undefined;
    try {
      NetInfo = require("@react-native-community/netinfo").default as NetInfoModule;
    } catch {
      return; // paket yoksa (ör. web) atla
    }
    if (!NetInfo) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let last: boolean | null = null;
    const unsub = NetInfo.addEventListener((state: NetInfoState) => {
      const connected = !!state?.isConnected;
      if (connected === last) return; // aynı durumu tekrar yayınlarsa atla
      last = connected;
      if (connected) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(onReconnect, 1500); // debounce
      } else if (timer) {
        // DÜŞÜK fix: offline'a düşünce bekleyen reconnect timer'ını İPTAL et → flapping'de 1.5sn sonra
        // OFFLINE durumdayken onReconnect (başarısız keşif) tetiklenmesin.
        clearTimeout(timer);
        timer = null;
      }
    });
    return () => {
      if (timer) clearTimeout(timer);
      try {
        unsub();
      } catch {
        /* ignore */
      }
    };
  }, [onReconnect]);
}
