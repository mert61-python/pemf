// Author: mertaygn, cglrgrkn
import { Platform } from "react-native";
import type { UserMode } from "@/context/UserModeContext";

/* Masaüstü client kurulumda hangi profilleri indirdiyse app'e `?profiles=home,vet` ile bildirir
   (client launch/kısayol URL'i). WelcomeScreen yalnız KURULU profilleri gösterir.
   - Yalnız WEB/desktop (localhost:8000). Mobilde (App Store) param yok → null = TÜM modlar (mevcut davranış).
   - İlk okumada localStorage'a yazılır → SPA gezinme/yenilemede korunur. */
const PROFILE_TO_MODE: Record<string, Exclude<UserMode, null>> = {
  home: "pet_owner",
  vet: "veterinarian",
  research: "researcher",
};
const KEY = "pemf_installed_profiles";

export function installedModes(): Set<Exclude<UserMode, null>> | null {
  if (Platform.OS !== "web" || typeof window === "undefined") return null;
  try {
    const q = new URLSearchParams(window.location.search).get("profiles");
    let raw = q;
    if (q) window.localStorage.setItem(KEY, q);
    else raw = window.localStorage.getItem(KEY);
    if (!raw) return null; // bilgi yok → tüm modlar
    const modes = raw
      .split(",")
      .map((p) => PROFILE_TO_MODE[p.trim().toLowerCase()])
      .filter(Boolean) as Exclude<UserMode, null>[];
    return modes.length ? new Set(modes) : null;
  } catch {
    return null;
  }
}
