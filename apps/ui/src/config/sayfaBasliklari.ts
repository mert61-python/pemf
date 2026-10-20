// Author: mertaygn, cglrgrkn
/** Sayfa başlıkları (kabuk üst çubuğu) — `PemfApp` buradan okur (SG.G1 / G2: profile göre metin; test edilebilir tek kaynak). */
import i18n from "i18next";
import type { RouteKey } from "@/types/domain";

type SayfaMeta = { title: string; subtitle: string };

/** Başlıklar ÇAĞRI anında çevrilir (modül düzeyinde `i18n.t` içe aktarmada dili dondururdu); `PemfApp` `useTranslation` ile dile abone. */
function routeMeta(): Record<RouteKey, SayfaMeta> {
  return {
    dashboard: { title: i18n.t("kabuk.sayfa.hosGeldiniz"), subtitle: i18n.t("kabuk.sayfa.anaEkranAlt") },
    control: { title: i18n.t("kabuk.sayfa.kontrol"), subtitle: i18n.t("kabuk.sayfa.kontrolAlt") },
    sensors: { title: i18n.t("kabuk.sayfa.sensorler"), subtitle: i18n.t("kabuk.sayfa.sensorlerAlt") },
    history: { title: i18n.t("kabuk.menu.seansGecmisi"), subtitle: i18n.t("kabuk.sayfa.seansGecmisiAlt") },
    patients: { title: i18n.t("kabuk.sayfa.hastalar"), subtitle: i18n.t("kabuk.sayfa.hastalarAlt") },
    kpi: { title: i18n.t("kabuk.sayfa.raporlar"), subtitle: i18n.t("kabuk.sayfa.raporlarAlt") },
    simulator: { title: i18n.t("kabuk.sayfa.simulasyon"), subtitle: i18n.t("kabuk.sayfa.simulasyonAlt") },
    ai: { title: i18n.t("kabuk.menu.akilliTeshis"), subtitle: i18n.t("kabuk.sayfa.teshisAlt") },
    ai_history: { title: i18n.t("kabuk.sayfa.aiGecmisi"), subtitle: i18n.t("kabuk.sayfa.aiGecmisiAlt") },
    settings: { title: i18n.t("kabuk.menu.ayarlar"), subtitle: i18n.t("kabuk.sayfa.ayarlarAlt") },
  };
}

/**
 * SG.G1 / G2 (sahip gözlemi 2026-10-13: "metinler de bu profillere göre uyarlanmalı … klinikle araştırma modunun alakası yok"):
 * araştırma profilinde "klinik / dostumuz / ağrı" dili YOK (karar #12 — `utils/profilSozlugu`). Yalnız FARKLI olanlar; geri kalan AYNEN.
 */
function arastirmaRouteMeta(): Partial<Record<RouteKey, SayfaMeta>> {
  return {
    dashboard: { title: i18n.t("kabuk.sayfa.hosGeldiniz"), subtitle: i18n.t("kabuk.sayfa.anaEkranAltArastirma") },
    patients: { title: i18n.t("kabuk.sayfa.ornekler"), subtitle: i18n.t("kabuk.sayfa.orneklerAlt") },
    kpi: { title: i18n.t("kabuk.sayfa.raporlar"), subtitle: i18n.t("kabuk.sayfa.raporlarAltArastirma") },
    simulator: { title: i18n.t("kabuk.sayfa.simulasyon"), subtitle: i18n.t("kabuk.sayfa.simulasyonAltArastirma") },
    ai: { title: i18n.t("kabuk.menu.akilliTeshis"), subtitle: i18n.t("kabuk.sayfa.teshisAltArastirma") },
  };
}

export function sayfaBasligi(userMode: string | null, route: RouteKey): SayfaMeta {
  return (userMode === "researcher" && arastirmaRouteMeta()[route]) || routeMeta()[route];
}
