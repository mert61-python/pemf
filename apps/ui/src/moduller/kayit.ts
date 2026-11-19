// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — modül PANEL kaydı: kimlik → TEMBEL panel bileşeni (`yukleyiciler.ts`). Panel yalnız modül SEÇİLİNCE yüklenir —
 * açılışı geciktirmez.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { PANEL_YUKLEYICILERI } from "./yukleyiciler";

export const PANELLER: Record<string, LazyExoticComponent<ComponentType>> = Object.fromEntries(
  Object.entries(PANEL_YUKLEYICILERI).map(([kimlik, yukle]) => [kimlik, lazy(yukle as () => Promise<{ default: ComponentType }>)]),
);
