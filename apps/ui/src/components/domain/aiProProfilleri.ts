/**
 * AI PRO HEDEF MODELLERİ — profil ↔ model eşlemesinin TEK KAYNAĞI (Faz 3, 2026-09-09).
 *
 * Sahip isteği: araştırma modunda AI Pro'da KEDİ yerine iki model olsun (Fantom Tümör, Petri Kuyu);
 * kedi yalnız veteriner modunda kalsın. Karar #13: gizleme SİMETRİK — kedi araştırmacıda, fantom ve
 * petri veterinerde HİÇ görünmez.
 *
 * ⚠️ Bu tablo tek kaynaktır: hangi profilin hangi modelleri görebildiği başka hiçbir yerde
 * tekrarlanmaz (AI Hub'daki `modes` bölüşümünün AI Pro karşılığı). Kapı:
 * tests/test_ai_pro_arayuz_profil_tablosu.py — araştırmacı listesinde "kedi" geçerse KIRMIZI.
 *
 * ⚠️ Backend profil BİLMEZ (AI Pro uçları sahip kararıyla auth-muaf) ve bu tabloya göre yetki
 * VERMEZ; kısıt yalnız arayüzdedir. Güvenlik onay mührüyle sağlanır: `/propose` modeli mühürler,
 * `/start` onu mühürden okur (bkz. servers/ai_pro_hedef.py).
 *
 * ⚠️ Araştırma modelleriyle SÜRÜŞ ayrıca `PEMF_ARASTIRMA_AIPRO` bayrağına bağlıdır (tezgâh
 * doğrulaması bekliyor). Panel bunu `/ai/pro/status` yanıtındaki `arastirmaAiProAcik` alanından
 * okur ve kartı "Deneysel" olarak pasifleştirir.
 */

/** Tel sözleşmesindeki `model` değeri (backend `ai_pro_hedef.SAGLAYICILAR` anahtarlarıyla AYNI). */
export type HedefModeli = "kedi" | "fantom" | "petri";

/** Profilin AI Pro'da SEÇEBİLECEĞİ modeller. Bilinmeyen profil → kedi (eski davranış). */
export const MODELLER_PROFILE_GORE: Record<string, HedefModeli[]> = {
  veterinarian: ["kedi"],
  researcher: ["fantom", "petri"],
  // Evcil hayvan sahibi profili YALNIZ ANALİZ yapar (sahip kararı) — AI Pro sekmesi yok.
  pet_owner: [],
};

/**
 * Modelin ÇALIŞMASI için `GET /api/ai/hazirlik` envanterinde hazır olması gereken modüller.
 *
 * ⚠️ Petri İKİ ağırlık ister: doz modeli (`em_petri`) VE kuyucuk tespiti (`petri_yolo`, 85,5 MB).
 * İkincisi eksikken /api/ai/hazirlik eskiden yeşil kalıyor, ilk petri isteği FileNotFoundError ile
 * ölüyordu (2026-09-08 denetimi) — kart bu yüzden İKİSİNİ birlikte sorar.
 */
export const MODUL_GEREKSINIMI: Record<HedefModeli, string[]> = {
  kedi: ["cat_organ", "em_kedi"],
  fantom: ["em_fantom"],
  petri: ["em_petri", "petri_yolo"],
};

export const VARSAYILAN_MODEL: HedefModeli = "kedi";

export interface ModelProfili {
  /** Kullanıcıya görünen ad (backend `title` ile aynı). */
  baslik: string;
  /** Kart altındaki bir cümlelik açıklama — ne yaptığını kod bilmeyen birine anlatır. */
  aciklama: string;
  /** Kart simgesi (metin emoji; ikon kitaplığı bağımlılığı eklemez). */
  simge: string;
  /** Kadrajda aranan ÖZNE ("fantom", "petri plakası") — şerit metinlerinde kullanılır. */
  ozne: string;
  /** Hedeflerin adı ("Tümör", "Kuyu") — kare üstü etiketler ve onay ekranı. */
  hedefEtiketi: string;
  /** Hazırlık şeridinde özne aranırken gösterilen yönlendirme. */
  ozneIpucu: string;
}

export const MODEL_PROFILLERI: Record<HedefModeli, ModelProfili> = {
  kedi: {
    baslik: "Kedi Organ",
    aciklama: "Kameradaki hayvanın seçili organını bulur; organa doz önerir.",
    simge: "🐾",
    ozne: "hayvan",
    hedefEtiketi: "Organ",
    ozneIpucu: "Kamerayı hastaya doğrultun.",
  },
  fantom: {
    baslik: "Fantom Tümör",
    aciklama: "Silikon fantomdaki mavi tümör odaklarını bulur; odağa doz önerir.",
    simge: "🎯",
    ozne: "fantom",
    hedefEtiketi: "Tümör",
    ozneIpucu: "Fantomu tepsinin ortasına düz yerleştirin; kabin işareti de kadrajda kalsın.",
  },
  petri: {
    baslik: "Petri Kuyu",
    aciklama: "Petri plakasındaki kuyuları bulur; kanserli kuyuya doz önerir.",
    simge: "🧫",
    ozne: "petri plakası",
    hedefEtiketi: "Kuyu",
    ozneIpucu: "Plakayı tepsiye düz yerleştirin; kamerayı tepeden tam kadraja alın.",
  },
};

/** Profil için seçilebilir modeller (bilinmeyen/boş profil → kedi; eski davranış korunur). */
export function modelleriAl(userMode?: string | null): HedefModeli[] {
  if (!userMode) return [VARSAYILAN_MODEL];
  const liste = MODELLER_PROFILE_GORE[userMode];
  if (liste === undefined) return [VARSAYILAN_MODEL];
  return liste;
}

/** Model profili (bilinmeyen ad → kedi). */
export function modelProfili(model?: string | null): ModelProfili {
  return MODEL_PROFILLERI[(model as HedefModeli) ?? VARSAYILAN_MODEL] ?? MODEL_PROFILLERI[VARSAYILAN_MODEL];
}
