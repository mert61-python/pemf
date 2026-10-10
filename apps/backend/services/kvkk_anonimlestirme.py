# -*- coding: utf-8 -*-
"""KVKK ANONİMLEŞTİRME TURU — 5 yıl inaktif hastalar (D2.54 · B-3.33 · B-3.34 · SAHİP KARARLARI A-06, A-09, A-27, Y125).

Günlük bakım döngüsü (`servers.api_server._daily_maintenance_loop`) bunu çağırır; kapı fonksiyon zincirine pinlidir
(tests/test_kvkk_anonimlestirme_ONAYLI_ve_EKSIKSIZ_D254.py).

⚠️ A-06: anonimleştirme OPERATÖR ONAYINA bağlıdır — sessiz ve geri dönüşsüz işlem olmaz. Onay yoksa hiçbir hastaya dokunulmaz; kaç
hastanın beklediği sayılır, günlüğe yazılır ve Ayarlar → Veri Saklama ekranı sorar (`/api/settings/retention`).
⚠️ A-09: onay ONAYLANAN EŞİĞE bağlıdır ({gün, sayı, zaman, kim} — tedavi DB'si `system_settings`). Eşik değişirse eski onay geçersizdir.
⚠️ B-3.34: kanonik taraf (`patients.db`) anonimleşince hasta bir daha SEÇİLMEZ; tedavi-DB adımı düşerse adlar süresiz kalırdı. Bu yüzden
anonimleştirilecek hastaların kimlik metinleri kanonik adımdan ÖNCE kalıcı "bekleyen" listesine yazılır; tedavi-DB adımı başarıyla
bitince listeden düşer, düşerse sonraki turda yeniden denenir.
⚠️ A-27: hekim atfı (seansın `operator_name` / `operator_email`, AI kaydının `operator_email` / `reviewed_by`) KALIR — anonimleştirme
hastayı hedefler.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 5 yıl — KVKK saklama kararı (A-06). Değişirse önceki onay geçersiz olur (A-09).
ESIK_GUN = 1825


def _aktif_adlar(pdb) -> set:
    """Kanonik DB'de anonimleşmemiş hastaların (Türkçe katlanmış) adları — kimliksiz AI kaydını ADLA bağlamanın belirsizlik denetimi."""
    from utils.turkce_metin import arama_katla

    return {
        arama_katla(str(p.get("name") or ""))
        for p in pdb.get_all_patients(kati=True)
        if str(p.get("anonymized") or 0) not in ("1", "True", "true") and p.get("name")
    }


def bekleyen_sayisi(pdb, esik: int = ESIK_GUN) -> int:
    return len(pdb.anonimlestirilecek_hastalar(esik))


def tur(pdb, tdb, esik: int = ESIK_GUN) -> dict:
    """Bir anonimleştirme turu. Dönen: {onay, bekleyen, anonimlestirilen, tedavi_bekleyen}. ASLA istisna atmaz (günlük döngü)."""
    sonuc = {"onay": False, "bekleyen": 0, "anonimlestirilen": 0, "tedavi_bekleyen": 0}
    islenen = 0
    try:
        # 0) F2-1.3: kanonik tarafı ANONİM ama tedavi-DB ayna satırı hâlâ ad taşıyan hastalar bekleyen listeye (yeniden) yazılır.
        try:
            _uzlastir(pdb, tdb)
        except Exception:
            logger.warning("KVKK uzlastirma adimi yapilamadi (sonraki turda yeniden denenecek)", exc_info=True)
        # 1) B-3.34: önceki turlardan kalan tedavi-DB adımlarını yeniden dene (onaydan bağımsız: kanonik taraf ZATEN anonim).
        islenen += _bekleyenleri_isle(pdb, tdb)
        onay = tdb.anonim_onayi_oku()
        sonuc["onay"] = bool(onay) and int(onay.get("gun") or 0) == int(esik)
        adaylar = pdb.anonimlestirilecek_hastalar(esik)
        sonuc["bekleyen"] = len(adaylar)
        if not sonuc["onay"]:
            if adaylar:
                logger.warning(
                    "KVKK: %d hasta %d gunden uzun suredir islem gormedi ve anonimlestirmeyi BEKLIYOR — operator onayi yok "
                    "(A-06; geri donussuz islem sessizce uygulanmaz). Ayarlar > Veri Saklama.",
                    len(adaylar),
                    esik,
                )
        elif adaylar and not tdb.saat_akla_yatkin_mi():
            # ⚠️ F2-1.2 · A-73: saat sıçradı / geride — "5 yıl inaktif" kesimi güvenilmez; onay olsa da hiçbir hastaya dokunulmaz.
            sonuc["saat_supheli"] = True
        elif adaylar:
            # 2) Kimlik metinleri kanonik adımdan ÖNCE kalıcı listeye (kanonik anonimleşince bir daha okunamazlar).
            tdb.anonim_bekleyen_ekle({a["id"]: [a.get("name"), a.get("owner"), a.get("owner_email")] for a in adaylar})
            yapilan = pdb.anonymize_inactive_patients(esik, yalniz=[a["id"] for a in adaylar])
            sonuc["anonimlestirilen"] = len(yapilan)
            # Kanonik adım düştüyse (yapilan boş) listedeki girdiler hasta hâlâ aday olduğu için zararsız: sonraki turda
            # yeniden yazılır; tedavi-DB adımı yalnız kanonik tarafı anonim olanlara uygulanır (aşağıda süzülür).
            if yapilan:
                tdb.denetim_yaz(
                    "kvkk.anonimlestirildi", scope="otomatik", item_count=len(yapilan), detail={"gun": int(esik)}
                )
                logger.warning(
                    "KVKK: %d inaktif hasta (>%d gun) operator onayiyla anonimlestirildi.", len(yapilan), esik
                )
            islenen += _bekleyenleri_isle(pdb, tdb)
        sonuc["tedavi_bekleyen"] = len(tdb.anonim_bekleyen_oku())
    except Exception:
        logger.warning("KVKK anonimlestirme turu hatasi (sonraki turda yeniden denenecek)", exc_info=True)
    if sonuc["anonimlestirilen"] or islenen:
        _kalinti_temizle(pdb, tdb)
    return sonuc


def _kalinti_temizle(pdb, tdb) -> None:
    """⚠️ F2-1.5 (2-F incelemesi · Y13): anonimleştirme UPDATE'lerinden SONRA iki DB'de de `wal_checkpoint(TRUNCATE)`. `secure_delete` yeni
    sayfa sürümünü sıfırlar ama WAL kipinde ESKİ sürüm denetim noktasına dek ana dosyada, önceki çerçeveler (kalıcı bekleyen listesinin düz
    ad/sahip/e-posta JSON'u dahil) -wal'da kalıyordu: tedavi DB'sinde ad, hasta DB'sinde cihaz anahtarıyla çözülen ŞİFRELİ kimlik (ölçüldü).
    Bekleyen listesi düşürüldükten SONRA koşar (yoksa listenin eski sayfası ana dosyaya kopyalanırdı). Açık okuyucu varsa tamamlanamaz →
    WARNING + kalıcı işaret (`_silme_sonrasi_denetim_noktasi`, F2-2.5 · F2-4.3); anonimleştirme sonucu DEĞİŞMEZ.
    Kapı: tests/test_anonimlestirme_ve_maskeleme_DOSYADA_kalinti_birakmaz_F2_1_5.py"""
    for db, ne in ((tdb, "KVKK anonimlestirme (tedavi DB)"), (pdb, "KVKK anonimlestirme (hasta DB)")):
        try:
            with db._get_connection() as conn:
                db._silme_sonrasi_denetim_noktasi(conn, ne)
        except Exception:
            logger.warning("%s: denetim noktasi yapilamadi.", ne, exc_info=True)


def _uzlastir(pdb, tdb) -> None:
    """⚠️ F2-1.3 (2-F incelemesi): kanonik `anonymized=1` olduktan sonra tedavi DB'sine ad GERİ gelebilir — anonimleştirmeden önce alınmış
    paketin REPLACE_ALL geri yüklemesi (`import_rows(replace=True)`; hasta kartı zaten var → atlanır), bayat istemcinin eski adla açtığı seans
    (`upsert_patient` ayna satırına eski adı yazar), bozuk okunup ezilen bekleyen listesi. Hasta artık aday olmadığı için eskiden hiçbir tur
    onu bir daha görmüyordu → ad SÜRESİZ kalıyordu (ölçüldü). Ayna satırı hâlâ ad taşıyan ve kanonik tarafı anonim olan hastalar, ayna
    satırının KENDİ kimlik metinleriyle bekleyen listeye yazılır; tedavi adımı `_bekleyenleri_isle`de uygulanır. Onaydan bağımsız (kanonik
    taraf zaten operatör onayıyla anonim — A-06); kartı yeniden adlanan hasta (`anonymized=0`) DOKUNULMAZ.
    Kapı: tests/test_anonim_hasta_GERI_GELEN_ad_UZLASTIRILIR_F2_1_3.py"""
    adli = tdb.adli_ayna_hastalar()
    if not adli:
        return
    anonim = {
        str(p.get("id"))
        for p in pdb.get_all_patients(kati=True)
        if str(p.get("anonymized") or 0) in ("1", "True", "true")
    }
    geri_gelen = {k: v for k, v in adli.items() if k in anonim}
    if geri_gelen:
        logger.warning(
            "KVKK: %d anonim hastanin adi tedavi gecmisinde yeniden bulundu (geri yukleme / bayat istemci) — yeniden anonimlestiriliyor.",
            len(geri_gelen),
        )
        tdb.anonim_bekleyen_ekle(geri_gelen)


def _bekleyenleri_isle(pdb, tdb) -> int:
    """@return tedavi adımı BAŞARIYLA uygulanan hasta sayısı."""
    bekleyen = tdb.anonim_bekleyen_oku()
    if not bekleyen:
        return 0
    # Yalnız kanonik tarafı GERÇEKTEN anonim olanlar (kanonik adım düştüyse hasta hâlâ adaydır — tedavi tarafına dokunulmaz).
    anonim = {k for k in bekleyen if str((pdb.get_patient(k) or {}).get("anonymized") or 0) in ("1", "True", "true")}
    if not anonim:
        return 0
    aktif = _aktif_adlar(pdb)
    from utils.turkce_metin import arama_katla

    kimlikler = {}
    for k in anonim:
        metinler = [m for m in (bekleyen.get(k) or []) if m and str(m).strip() and str(m) != "[ANONIM]"]
        ad = (bekleyen.get(k) or [None])[0]
        kimlikler[k] = {"metinler": metinler, "ad_ile_kimliksiz": bool(ad) and arama_katla(str(ad)) not in aktif}
    n = tdb.anonymize_patients_by_uuid(sorted(anonim), kimlikler=kimlikler)
    if n >= 0:
        tdb.anonim_bekleyen_dus(sorted(anonim))
        return len(anonim)
    return 0
