/**
 * PROFİL SÖZLÜĞÜ — "hasta / örnek / evcil hayvanım" terimlerinin TEK KAYNAĞI.
 *
 * Sahip kararı #12 (terminoloji): araştırma modunda ekranda "hasta" ve "hekim onayı" yazmaz —
 * araştırmacının önünde bir hasta değil bir ÖRNEK (fantom, petri plakası) vardır ve onaylayan
 * kişi bir hekim değildir. Klinik metinler ve HUKUKİ metinler ile kod/DB adları AYNEN kalır
 * (bkz. "Tedavi→Seans Terminoloji" kararı: yalnız ARAYÜZ dili değişir).
 *
 * ⚠️ Buradan önce bu tablo `PatientGate` içinde yerel bir fonksiyondu; AI Pro paneli de aynı
 * terimlere ihtiyaç duyunca ikinci bir kopya yazmak yerine TAŞINDI (kopya iki metnin sessizce
 * ayrışmasına açık kapı bırakırdı). Metinler taşınırken DEĞİŞTİRİLMEDİ.
 */
export interface ProfilSozlugu {
  /** Uzun tekil ad — seçim kartı başlığı ("Örnek / Denek"). */
  tekil: string;
  /** Kısa tekil ad — cümle içinde ("Örnek seçilmedi"). */
  tekilKisa: string;
  /** Belirtme hâli — "…hiçbir örneğe bağlanmadan". */
  belirtme: string;
  /**
   * "…-sız başlat" onay düğmesinin TAM metni.
   *
   * ⚠️ EK ÜRETİLMEZ: Türkçe ünlü uyumu yüzünden `${tekilKisa}siz` yazmak "Hastasiz" (ı yerine i)
   * üretiyordu — ölçüldü. Çekimli biçimler tabloda TAM yazılır.
   */
  sizBaslat: string;
  secKisa: string;
  bos: string;
  ekle: string;
  uyari: string;
}

export function profilSozlugu({
  petOwner = false,
  researcher = false,
}: {
  petOwner?: boolean;
  researcher?: boolean;
}): ProfilSozlugu {
  if (researcher) {
    return {
      tekil: "Örnek / Denek",
      tekilKisa: "Örnek",
      belirtme: "örneğe",
      sizBaslat: "Örneksiz başlat",
      secKisa: "Örnek seçin",
      bos: "Kayıtlı örnek yok.",
      ekle: "Örnek Ekle",
      uyari: "Analiz için önce bir örnek seçin — sonuç o kayda işlenecek.",
    };
  }
  if (petOwner) {
    return {
      tekil: "Evcil Hayvanım",
      tekilKisa: "Hayvanınız",
      belirtme: "hayvanınıza",
      sizBaslat: "Hayvansız başlat",
      secKisa: "Hayvanınızı seçin",
      bos: "Henüz kayıtlı hayvanınız yok.",
      ekle: "Hayvan Ekle",
      uyari: "Analiz için önce hayvanınızı seçin — sonuç onun geçmişine işlenecek.",
    };
  }
  return {
    tekil: "Hasta",
    tekilKisa: "Hasta",
    belirtme: "hastaya",
    sizBaslat: "Hastasız başlat",
    secKisa: "Hasta seçin",
    bos: "Kayıtlı hasta yok.",
    ekle: "Hasta Ekle",
    uyari: "İşlem için önce hasta seçin — sonuç hasta geçmişine işlenecek.",
  };
}
