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
  /**
   * SG.G1 / G2 (sahip gözlemi 2026-10-13: "klinikle araştırma modunun alakası yok"): "Benim / Tüm" kapsam düğmelerinin dili.
   * Kayıtlar artık profile göre AYRI (backend `X-PEMF-Profil`); araştırmada "Tüm Klinik" değil "Tüm Ekip". Veteriner metinleri AYNEN.
   */
  benimListe: string;
  tumKapsam: string;
  /** Erişilebilirlik etiketleri için küçük harfli kapsam + kayıt adı ("Tüm klinik hastaları" / "Tüm ekip örnekleri"). */
  tumKapsamKucuk: string;
  kayitlarAd: string;
  /** Performans Raporu bölüm başlığı. */
  kpiBaslik: string;
  /**
   * SGI-4.1 (bağımsız inceleme 2026-10-17, sahip G1 "metinler de bu profillere göre uyarlanmalı"): ekran İÇİ metinler.
   * Kum havuzunda araştırma profilinde ölçüldü: Hastalar "Hasta Veritabanı" / "Yeni Hasta Kayıt", Seans Geçmişi "Hastalarınıza
   * ait …", AI Geçmişi "Tüm hastalar" çipi. Veteriner ve ev sahibi metinleri AYNEN (yalnız araştırma farklı).
   */
  veritabani: string;
  yeniKayit: string;
  seansGecmisiGiris: string;
  tumListeCipi: string;
}

/** SGI-4.1: veteriner ve ev sahibi profillerinde bugünkü (değişmeyen) ekran içi metinler. */
const KLINIK_EKRAN_METINLERI = {
  veritabani: "Hasta Veritabanı",
  yeniKayit: "Yeni Hasta Kayıt",
  seansGecmisiGiris: "Hastalarınıza ait geçmiş seans kayıtları ve raporlamalar.",
  tumListeCipi: "Tüm hastalar",
} as const;

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
      benimListe: "Benim Örneklerim",
      tumKapsam: "Tüm Ekip",
      tumKapsamKucuk: "ekip",
      kayitlarAd: "örnekleri",
      kpiBaslik: "📊 Araştırma Göstergeleri & Analitik",
      veritabani: "Örnek / Denek Veritabanı",
      yeniKayit: "Yeni Örnek Kaydı",
      seansGecmisiGiris: "Örneklerinize ait geçmiş seans kayıtları ve raporlamalar.",
      tumListeCipi: "Tüm örnekler",
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
      benimListe: "Hayvanlarım",
      tumKapsam: "Tüm Klinik",
      tumKapsamKucuk: "klinik",
      kayitlarAd: "hastaları",
      kpiBaslik: "📊 Klinik Göstergeler & Analitik",
      ...KLINIK_EKRAN_METINLERI,
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
    benimListe: "Benim Hastalarım",
    tumKapsam: "Tüm Klinik",
    tumKapsamKucuk: "klinik",
    kayitlarAd: "hastaları",
    kpiBaslik: "📊 Klinik Göstergeler & Analitik",
    ...KLINIK_EKRAN_METINLERI,
  };
}
