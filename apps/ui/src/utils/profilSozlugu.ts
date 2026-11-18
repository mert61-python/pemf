import i18n from "i18next";
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
  /** ODD B-4 (ODK-B keşfi 18-11): adı olmayan (sahipsiz) seans kaydının geçmişteki adı — araştırmada "Sahipsiz örnek", klinikte
   *  bugünkü "Bilinmeyen Hasta" (petri seansı geçmişte "Bilinmeyen Hasta" görünüyordu). */
  sahipsizKayit: string;
  /** ODD K-2 (ODK-B keşfi 18-11): araştırmada menü "Hastalar", arama "Hasta veya Sahip Ara…", boş liste "Henüz hasta kaydı yok.",
   *  Ana Ekran "Hasta Özeti", geçmiş araması "Hasta, Not veya Tarih ara…" — sayfa ise "Örnek / Denek Kayıtları". Klinik / ev sahibi AYNEN. */
  menuAd: string;
  araYer: string;
  araEtiketi: string;
  bosListe: string;
  ozetBaslik: string;
  gecmisAraYer: string;
}

/** SGI-4.1: veteriner ve ev sahibi profillerinde bugünkü (değişmeyen) ekran içi metinler. */
const klinikEkranMetinleri = () =>
  ({
    sahipsizKayit: i18n.t("seans.gecmis.bilinmeyenHasta"),
    menuAd: i18n.t("kabuk.menu.hastalar"),
    araYer: i18n.t("hasta.liste.araYer"),
    araEtiketi: i18n.t("hasta.liste.araEtiketi"),
    bosListe: i18n.t("hasta.liste.bos"),
    ozetBaslik: i18n.t("ana.hastaOzeti"),
    gecmisAraYer: i18n.t("seans.gecmis.araPlaceholder"),
    veritabani: i18n.t("hasta.sozluk.klinikEkran.veritabani"),
    yeniKayit: i18n.t("hasta.sozluk.klinikEkran.yeniKayit"),
    seansGecmisiGiris: i18n.t("hasta.sozluk.klinikEkran.seansGecmisiGiris"),
    tumListeCipi: i18n.t("hasta.sozluk.klinikEkran.tumListeCipi"),
  }) as const;

export function profilSozlugu({
  petOwner = false,
  researcher = false,
}: {
  petOwner?: boolean;
  researcher?: boolean;
}): ProfilSozlugu {
  if (researcher) {
    return {
      tekil: i18n.t("hasta.sozluk.arastirma.tekil"),
      tekilKisa: i18n.t("hasta.sozluk.arastirma.tekilKisa"),
      belirtme: i18n.t("hasta.sozluk.arastirma.belirtme"),
      sizBaslat: i18n.t("hasta.sozluk.arastirma.sizBaslat"),
      secKisa: i18n.t("hasta.sozluk.arastirma.secKisa"),
      bos: i18n.t("hasta.sozluk.arastirma.bos"),
      ekle: i18n.t("hasta.sozluk.arastirma.ekle"),
      uyari: i18n.t("hasta.sozluk.arastirma.uyari"),
      benimListe: i18n.t("hasta.sozluk.arastirma.benimListe"),
      tumKapsam: i18n.t("hasta.sozluk.arastirma.tumKapsam"),
      tumKapsamKucuk: i18n.t("hasta.sozluk.arastirma.tumKapsamKucuk"),
      kayitlarAd: i18n.t("hasta.sozluk.arastirma.kayitlarAd"),
      kpiBaslik: i18n.t("hasta.sozluk.arastirma.kpiBaslik"),
      veritabani: i18n.t("hasta.sozluk.arastirma.veritabani"),
      yeniKayit: i18n.t("hasta.sozluk.arastirma.yeniKayit"),
      seansGecmisiGiris: i18n.t("hasta.sozluk.arastirma.seansGecmisiGiris"),
      tumListeCipi: i18n.t("hasta.sozluk.arastirma.tumListeCipi"),
      sahipsizKayit: i18n.t("hasta.sozluk.arastirma.sahipsizKayit"),
      menuAd: i18n.t("hasta.sozluk.arastirma.menuAd"),
      araYer: i18n.t("hasta.sozluk.arastirma.araYer"),
      araEtiketi: i18n.t("hasta.sozluk.arastirma.araEtiketi"),
      bosListe: i18n.t("hasta.sozluk.arastirma.bosListe"),
      ozetBaslik: i18n.t("hasta.sozluk.arastirma.ozetBaslik"),
      gecmisAraYer: i18n.t("hasta.sozluk.arastirma.gecmisAraYer"),
    };
  }
  if (petOwner) {
    return {
      tekil: i18n.t("hasta.sozluk.sahip.tekil"),
      tekilKisa: i18n.t("hasta.sozluk.sahip.tekilKisa"),
      belirtme: i18n.t("hasta.sozluk.sahip.belirtme"),
      sizBaslat: i18n.t("hasta.sozluk.sahip.sizBaslat"),
      secKisa: i18n.t("hasta.sozluk.sahip.secKisa"),
      bos: i18n.t("hasta.sozluk.sahip.bos"),
      ekle: i18n.t("hasta.sozluk.sahip.ekle"),
      uyari: i18n.t("hasta.sozluk.sahip.uyari"),
      benimListe: i18n.t("hasta.sozluk.sahip.benimListe"),
      tumKapsam: i18n.t("hasta.sozluk.sahip.tumKapsam"),
      tumKapsamKucuk: i18n.t("hasta.sozluk.sahip.tumKapsamKucuk"),
      kayitlarAd: i18n.t("hasta.sozluk.sahip.kayitlarAd"),
      kpiBaslik: i18n.t("hasta.sozluk.sahip.kpiBaslik"),
      ...klinikEkranMetinleri(),
    };
  }
  return {
    tekil: i18n.t("hasta.sozluk.klinik.tekil"),
    tekilKisa: i18n.t("hasta.sozluk.klinik.tekilKisa"),
    belirtme: i18n.t("hasta.sozluk.klinik.belirtme"),
    sizBaslat: i18n.t("hasta.sozluk.klinik.sizBaslat"),
    secKisa: i18n.t("hasta.sozluk.klinik.secKisa"),
    bos: i18n.t("hasta.sozluk.klinik.bos"),
    ekle: i18n.t("hasta.sozluk.klinik.ekle"),
    uyari: i18n.t("hasta.sozluk.klinik.uyari"),
    benimListe: i18n.t("hasta.sozluk.klinik.benimListe"),
    tumKapsam: i18n.t("hasta.sozluk.klinik.tumKapsam"),
    tumKapsamKucuk: i18n.t("hasta.sozluk.klinik.tumKapsamKucuk"),
    kayitlarAd: i18n.t("hasta.sozluk.klinik.kayitlarAd"),
    kpiBaslik: i18n.t("hasta.sozluk.klinik.kpiBaslik"),
    ...klinikEkranMetinleri(),
  };
}
