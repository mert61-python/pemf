// Author: mertaygn, cglrgrkn
import { useEffect } from "react";
import { AppState } from "react-native";

/**
 * Uygulama ÖN PLANA gelince `onReconnect` tetikler (audit B-2.4: LiveDataContext'ten çıkarıldı).
 * Arka plandayken OS, WS soketini/sayaçları dondurmuş/koparmış olabilir → dönünce yeniden keşif/bağlan;
 * yoksa kullanıcı uygulamaya döndüğünde DONMUŞ "canlı" veri görürdü.
 *
 * BE 1(d) · Y229: `onArkaPlandanDonus` YALNIZ "background" → "active" geçişinde (ör. iOS bildirim perdesinin "inactive"i değil)
 * `onReconnect`ten ÖNCE çağrılır — çağıran soketi doğrulanana dek "bağlı" saymaz.
 */
export function useForegroundReconnect(onReconnect: () => void, onArkaPlandanDonus?: () => void): void {
  useEffect(() => {
    let onceki: string = AppState.currentState ?? "active";
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        if (onceki === "background") onArkaPlandanDonus?.();
        onReconnect();
      }
      onceki = state;
    });
    return () => {
      try {
        sub.remove();
      } catch {
        /* ignore */
      }
    };
  }, [onReconnect, onArkaPlandanDonus]);
}
