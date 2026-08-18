// Author: mertaygn, cglrgrkn
import { useEffect } from "react";
import { AppState } from "react-native";

/**
 * Uygulama ÖN PLANA gelince `onReconnect` tetikler (audit B-2.4: LiveDataContext'ten çıkarıldı).
 * Arka plandayken OS, WS soketini/sayaçları dondurmuş/koparmış olabilir → dönünce yeniden keşif/bağlan;
 * yoksa kullanıcı uygulamaya döndüğünde DONMUŞ "canlı" veri görürdü.
 */
export function useForegroundReconnect(onReconnect: () => void): void {
  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") onReconnect();
    });
    return () => {
      try {
        sub.remove();
      } catch {
        /* ignore */
      }
    };
  }, [onReconnect]);
}
