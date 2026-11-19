// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — geliştirici modülleri istemcisi (`/api/moduller`, sunucu `servers/modul_router.py`).
 * ======================================================================================================
 * Modüller varsayılan GİZLİ (Y299); bir anda TEK etkin modül; sınırlar SUNUCUDA zorlanır. Sunucu hatayı `{"detail": {"kod", "alan"}}`
 * gövdesiyle döner → `modulHataMetni` iki dilde eylem söyler. ACİL DURDUR modüllere SUNUCUDA yayılır (bu istemciden bağımsız).
 */
import type { TFunction } from "i18next";
import { apiGet, apiPost } from "@/services/apiClient";

export interface ModulOzeti {
  kimlik: string;
  ad?: { tr: string; en: string };
  surum?: string;
  baglanti?: string;
  sinirlar?: Record<string, [number, number]>;
  bekci_ms?: number;
  hata?: string;
  alan?: string;
}

export interface ModulListesi {
  gorunur: boolean;
  moduller: ModulOzeti[];
  etkin: string | null;
  canli: boolean;
  hata: string | null;
}

export interface ModulHata {
  kod: string;
  alan: string;
}

export type ModulSonuc<T> = { tamam: true; veri: T } | { tamam: false; hata: ModulHata };

async function cagir<T>(yol: string, govde: unknown | undefined, oku: boolean): Promise<ModulSonuc<T>> {
  let hata: ModulHata | null = null;
  const opts = {
    silent: true,
    onHttpError: (_d: number, _m?: string, ham?: unknown) => {
      const det = (ham as { detail?: { kod?: unknown; alan?: unknown } } | undefined)?.detail;
      hata = {
        kod: typeof det?.kod === "string" ? det.kod : "baglanti",
        alan: typeof det?.alan === "string" ? det.alan : "",
      };
    },
  };
  const veri = oku ? await apiGet<T | null>(yol, null, opts) : await apiPost<T | null>(yol, govde, null, opts);
  if (hata) return { tamam: false, hata };
  if (veri === null) return { tamam: false, hata: { kod: "baglanti", alan: "" } };
  return { tamam: true, veri };
}

export const modulApi = {
  listele: () => cagir<ModulListesi>("/moduller", undefined, true),
  gorunurlukYaz: (gorunur: boolean) => cagir<{ gorunur: boolean }>("/moduller/gorunurluk", { gorunur }, false),
  sec: (kimlik: string) => cagir<Record<string, unknown>>(`/moduller/${encodeURIComponent(kimlik)}/sec`, {}, false),
  birak: () => cagir<Record<string, unknown>>("/moduller/birak", {}, false),
  uygula: (ayar: Record<string, number>) => cagir<{ uygulandi: Record<string, number> }>("/moduller/uygula", { ayar }, false),
  baslat: () => cagir<Record<string, unknown>>("/moduller/baslat", {}, false),
  durdur: () => cagir<Record<string, unknown>>("/moduller/durdur", {}, false),
  durum: () => cagir<{ etkin: string | null; canli: boolean; hata: string | null; surucu?: Record<string, unknown> }>("/moduller/durum", undefined, true),
};

/** Modülün görünen adı (kişinin adı) etkin dilde; ad yoksa kimlik. */
export function modulAdi(m: ModulOzeti, dil: string): string {
  return (dil === "en" ? m.ad?.en : m.ad?.tr) || m.kimlik;
}

/** Sunucu hata kodu → eylem söyleyen metin (TR + EN). */
export function modulHataMetni(t: TFunction, h: ModulHata): string {
  switch (h.kod) {
    case "gizli":
      return t("kontrol.modul.hata.gizli");
    case "modulYok":
      return t("kontrol.modul.hata.modulYok");
    case "etkinModulYok":
      return t("kontrol.modul.hata.etkinModulYok");
    case "baglanamadi":
      return t("kontrol.modul.hata.baglanamadi", { neden: h.alan });
    case "surucuOldu":
      return t("kontrol.modul.hata.surucuOldu");
    case "surucuYanitsiz":
      return t("kontrol.modul.hata.surucuYanitsiz");
    case "surucuHatasi":
      return t("kontrol.modul.hata.surucuHatasi", { neden: h.alan });
    case "ayarSinirDisi":
      return t("kontrol.modul.hata.ayarSinirDisi", { alan: h.alan });
    case "ayarBilinmeyen":
    case "ayarSayiDegil":
    case "ayarGecersiz":
      return t("kontrol.modul.hata.ayarGecersiz", { alan: h.alan });
    default:
      return t("kontrol.modul.hata.baglanti");
  }
}
