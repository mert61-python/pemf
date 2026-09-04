// Author: mertaygn, cglrgrkn
/**
 * KABUK DÜZENİ — tek kaynak  [S2/S5, 2026-09-04 responsive denetimi]
 * ==================================================================
 * NEDEN: kenar çubuğu genişliği üç ayrı yerde farklı değerlerle duruyordu ve düzen kararları
 * (sütun sayısı, kompaktlık, hangi kabuk) PENCERE genişliğinden veriliyordu — kenar çubuğu
 * düşülmediği için 768 px tablet dikeyde içeriğe 352 px kalmasına rağmen ızgara 2 sütun kuruyordu.
 *
 * Bu dosya SAF'tır (react-native import ETMEZ, ölçek fabrikasına bağlı DEĞİLDİR): jest'te tablo
 * testiyle kilitlenir, döngüsel import üretmez.
 *
 * ⚠️ Genişlikler ÖLÇEKSİZ (CSS px): `rs()` ile çarpılmazlar. Ölçek fabrikası telefon içi orantı
 * içindir; kenar çubuğu bir "yapısal" boyuttur ve PC'de %30 büyümesi ekranB-1/ekranC-1'in kökeniydi.
 */
import { SHORT_HEIGHT } from "@/theme/breakpoints";

/** Kabuk türü: alt gezinme çubuğu (telefon) · ikon rayı · tam kenar çubuğu. */
export type ShellKind = "bottom" | "rail" | "sidebar";

/** Tam kenar çubuğu (masaüstü). */
export const SIDEBAR_WIDTH = 240;
/** Tablet dikeyde daraltılmış kenar çubuğu. */
export const SIDEBAR_WIDTH_TABLET = 200;
/** İkon-only ray (yatay telefon + dar PC penceresi). */
export const RAIL_WIDTH = 72;

/** Tam kenar çubuğu bu genişlikten itibaren. */
export const SIDEBAR_MIN = 900;
/** Ray eşiği — native (tablet dikey / yatay telefon). */
export const RAIL_MIN_NATIVE = 768;
/** Ray eşiği — web/PC penceresi (launcher min pencere 700 px). */
export const RAIL_MIN_WEB = 640;
/** Bu içerik genişliğinin altında düzen "kompakt" sayılır (düğme satırları sütuna iner). */
export const COMPACT_CONTENT = 560;

/**
 * Hangi kabuk çizilecek? Yükseklik verilirse KISA ekranda (yatay telefon, 500 px altı) tam kenar
 * çubuğu yerine ray seçilir — sahip kararı 2026-09-04: yatay telefonda alt bar dikey alanın
 * %17'sini yiyordu, ray 0 px yer alır.
 */
export function getShellKind(width: number, isWeb: boolean, height?: number): ShellKind {
  const kisa = typeof height === "number" && height < SHORT_HEIGHT;
  if (width >= SIDEBAR_MIN && !kisa) return "sidebar";
  return width >= (isWeb ? RAIL_MIN_WEB : RAIL_MIN_NATIVE) ? "rail" : "bottom";
}

/** Kabuk türüne göre kenar çubuğu genişliği (bottom → 0). */
export function shellSidebarWidth(kind: ShellKind, isTablet: boolean): number {
  if (kind === "rail") return RAIL_WIDTH;
  if (kind === "sidebar") return isTablet ? SIDEBAR_WIDTH_TABLET : SIDEBAR_WIDTH;
  return 0;
}

/**
 * İçerik genişliği TAHMİNİ (ölçüm gelene kadar): pencere − kenar çubuğu − 2×içerik boşluğu.
 * Gerçek değer AppShell'in `onLayout` ölçümünden gelir (ShellLayoutContext); bu tahmin ilk
 * render'da ve kabuk dışındaki ekranlarda kullanılır → "1 sütun sonra N sütun" titremesi olmaz.
 */
export function estimateContentWidth(width: number, kind: ShellKind, isTablet: boolean, pad: number): number {
  return Math.max(0, width - shellSidebarWidth(kind, isTablet) - 2 * pad);
}
