/**
 * PEMF Otomatik Sunucu Keşif Hook'u
 * ===================================
 * Üç kademeli otomatik bağlantı:
 *
 * 1. AsyncStorage'da kayıtlı adres → direkt bağlan
 * 2. Mevcut config'deki varsayılan IP → dene
 * 3. Subnet tarama (192.168.x.x, 10.0.0.x) → PEMF-Vet servisi ara
 */

import { useState, useEffect, useCallback } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { updateServiceConfig, serviceConfig } from "@/services/config";

const STORAGE_KEY = "@pemf_server_address";
const HEALTH_TIMEOUT_MS = 2500;

export type DiscoveryState = "idle" | "searching" | "found" | "failed";

interface UseAutoDiscoveryResult {
  state: DiscoveryState;
  foundAddress: string | null;
  connectTo: (address: string) => Promise<boolean>;
  startSearch: () => void;
}

/** /api/health isteği atar, PEMF-Vet servisi mi kontrol eder */
async function checkPemfHealth(address: string): Promise<boolean> {
  try {
    const base = address.startsWith("http") ? address.replace(/\/$/, "") : `http://${address}:8000`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    const res = await fetch(`${base}/api/health`, { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return false;
    const data = await res.json();
    // Sadece PEMF-Vet servisine bağlan
    return data?.service === "PEMF-Vet" || data?.status === "online";
  } catch {
    return false;
  }
}

/** Ağdaki olası PEMF sunucularını paralel tarar */
async function scanSubnet(): Promise<string | null> {
  const currentBase = serviceConfig.apiBaseUrl
    .replace("/api", "")
    .replace(/^https?:\/\//, "")
    .split(":")[0];
  const parts = currentBase.split(".");
  const subnet = parts.length === 4 ? parts.slice(0, 3).join(".") : "192.168.1";

  const subnetsToScan = [subnet, "192.168.1", "192.168.0", "10.0.0"].filter(
    (v, i, a) => a.indexOf(v) === i  // deduplicate
  );

  for (const sub of subnetsToScan) {
    // Yaygın LattePanda/router IP'leri önce dene
    const candidates = [100, 1, 101, 2, 102, 110, 50, 200];
    const results = await Promise.allSettled(
      candidates.map(async (last) => {
        const ip = `${sub}.${last}`;
        const ok = await checkPemfHealth(ip);
        if (ok) return ip;
        throw new Error("not found");
      })
    );
    for (const r of results) {
      if (r.status === "fulfilled" && r.value) return r.value;
    }
  }
  return null;
}

export function useAutoDiscovery(): UseAutoDiscoveryResult {
  const [state, setState] = useState<DiscoveryState>("idle");
  const [foundAddress, setFoundAddress] = useState<string | null>(null);

  const connectTo = useCallback(async (address: string): Promise<boolean> => {
    const ok = await checkPemfHealth(address);
    if (ok) {
      updateServiceConfig(address);
      await AsyncStorage.setItem(STORAGE_KEY, address).catch(() => {});
      setFoundAddress(address);
      setState("found");
      return true;
    }
    return false;
  }, []);

  const startSearch = useCallback(async () => {
    setState("searching");

    // 1. AsyncStorage'daki kayıtlı adresi dene
    try {
      const saved = await AsyncStorage.getItem(STORAGE_KEY) ||
                    await AsyncStorage.getItem("@pemf_server_ip");
      if (saved) {
        const ok = await connectTo(saved);
        if (ok) return;
      }
    } catch { /* devam */ }

    // 2. Mevcut config'deki varsayılan IP'yi dene
    try {
      const currentBase = serviceConfig.apiBaseUrl.replace("/api", "");
      const ip = currentBase.replace(/^https?:\/\//, "").split(":")[0];
      const ok = await connectTo(ip);
      if (ok) return;
    } catch { /* devam */ }

    // 3. Subnet tarama
    const found = await scanSubnet();
    if (found) {
      await connectTo(found);
      return;
    }

    setState("failed");
  }, [connectTo]);

  // Uygulama açıldığında otomatik ara
  useEffect(() => {
    startSearch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { state, foundAddress, connectTo, startSearch };
}

