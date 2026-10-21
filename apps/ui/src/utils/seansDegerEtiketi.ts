// Author: mertaygn, cglrgrkn
/**
 * SEANS DEĞERLERİ → GÖRÜNEN AD (I18N-P1 kapanış taraması).
 *
 * `mode` ("Manuel" | "Otomatik" | "AI") ve `target_condition` (`AUTO_TARGETS` değerleri) seansa / literatür aramasına GİDEN ve DB'ye yazılan
 * VERİdir — Türkçe kalır, dil değişince DEĞİŞMEZ. Ekrana basılırken (geçmiş kartı, seans detayı, aktif seans kartı, ana ekran, KPI mod
 * dağılımı) değer → katalog anahtarı ile çevrilir; bilinmeyen değer (serbest metin, eski kayıt, "AI") AYNEN gösterilir.
 * Python karşılığı: `apps/backend/utils/seans_durum.py::mod_etiketi / hedef_etiketi` (PDF + CSV) — tablolar
 * `tests/test_seans_mod_hedef_etiketi_P1.py` ile ANAHTAR ANAHTAR karşılaştırılır.
 */
import type { TFunction } from "i18next";

/** Hedef durumunun GÖRÜNEN adı. ⚠️ Değer (TR) `targetCondition` olarak seansa / literatür aramasına (auto_preset) GİDER → DEĞİŞMEZ. */
export const hedefEtiketi = (t: TFunction, hedef: string): string => {
  switch (hedef) {
    case "Doku İyileşmesi": return t("kontrol.hedef.dokuIyilesmesi");
    case "Eklem Ağrısı": return t("kontrol.hedef.eklemAgrisi");
    case "Kas Spazmı": return t("kontrol.hedef.kasSpazmi");
    case "Kırık İyileşmesi": return t("kontrol.hedef.kirikIyilesmesi");
    case "Enflamasyon Azaltma": return t("kontrol.hedef.enflamasyonAzaltma");
    case "Sinir Rejenerasyonu": return t("kontrol.hedef.sinirRejenerasyonu");
    case "Bağ Dokusu Tamiri": return t("kontrol.hedef.bagDokusuTamiri");
    case "Ödem Azaltma": return t("kontrol.hedef.odemAzaltma");
    default: return hedef;
  }
};

/**
 * I18NI-A1.5: AI Pro seans modu VERİSİ `AI Pro · <model> [· <hedef>]` (sunucu `ai_router` — `ai_pro_hedef` title / hedef adı, organ `dil="tr"`;
 * `profil.ARASTIRMA_SEANS_ONEKLERI` bu metne bakar → Türkçe SAKLANIR). Gösterimde parça parça katalogdan; tanınmayan parça AYNEN.
 * TR'de çıktı ham değerle BAYT BAYT aynı (parçaların TR değeri = sunucunun TR metni; kapı: seansModu.I18NI.A1.aiProModuEN).
 */
const AI_PRO_ONEK = "AI Pro · ";
const aiProModel = (t: TFunction, m: string): string => {
  switch (m) {
    case "Kedi Organ": return t("ai.modul.kediOrgan.ad");
    case "Fantom Tümör": return t("ai.modul.fantomTumor.ad");
    case "Petri Kuyu": return t("ai.modul.petriKuyu.ad");
    default: return m;
  }
};
const aiProHedefEtiketi = (t: TFunction, h: string): string => {
  switch (h) {
    case "Tümör": return t("ai.pro.profil.fantom.hedefEtiketi");
    case "Kuyu": return t("ai.pro.profil.petri.hedefEtiketi");
    default: return h;
  }
};
const aiProHedef = (t: TFunction, h: string): string => {
  switch (h) {
    case "Tüm Vücut": return t("ai.organ.ad.tumVucut");
    case "Mide": return t("ai.organ.ad.mide");
    case "Böbrek": return t("ai.organ.ad.bobrek");
    case "Karaciğer": return t("ai.organ.ad.karaciger");
    case "Mesane": return t("ai.organ.ad.mesane");
    case "Pankreas": return t("ai.organ.ad.pankreas");
    case "Bağırsak": return t("ai.organ.ad.bagirsak");
    case "Kalp": return t("ai.organ.ad.kalp");
    case "Dalak": return t("ai.organ.ad.dalak");
    case "Akciğer (sağ)": return t("ai.organ.ad.akciger_sag");
    case "Akciğer (sol)": return t("ai.organ.ad.akciger_sol");
    default: break;
  }
  const oto = /^(.+) \(otomatik\)$/.exec(h);
  if (oto) return t("seans.aiProMod.otomatikHedef", { hedef: aiProHedefEtiketi(t, oto[1]) });
  const no = /^(.+) (\d+)$/.exec(h);
  if (no) return `${aiProHedefEtiketi(t, no[1])} ${no[2]}`;
  return h;
};

/** Seans modunun GÖRÜNEN adı. ⚠️ Değer (`Manuel` / `Otomatik` / `AI` / `AI Pro · …`) seansa / DB'ye GİDER → DEĞİŞMEZ; "AI" iki dilde aynıdır. */
export const modEtiketi = (t: TFunction, mod: string): string => {
  switch (mod) {
    case "Manuel": return t("kontrol.sekme.manuel");
    case "Otomatik": return t("kontrol.sekme.otomatik");
    default: break;
  }
  if (typeof mod === "string" && mod.startsWith(AI_PRO_ONEK)) {
    const [model, ...hedef] = mod.slice(AI_PRO_ONEK.length).split(" · ");
    return [AI_PRO_ONEK + aiProModel(t, model), ...hedef.map((h) => aiProHedef(t, h))].join(" · ");
  }
  return mod;
};
