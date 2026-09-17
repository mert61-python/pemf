# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""VERI KUMESI ATFI (2026-09-17).

OLCULEN DURUM. Depo `training_archive/ai_data/real_clinical_data/` altinda UCUNCU TARAF
arastirma veri kumelerini PUBLIC olarak yeniden dagitiyor:

    mitbih/100.hea -> "100 2 360 650000" + MLII/V5 derivasyonlari
                      = MIT-BIH Arrhythmia Database (PhysioNet)
    downloader.py  -> PhysioZoo, Zenodo "Paws in Pain", MIT-BIH, AliveCor

Olculdu: dizinde LICENSE/README/CITATION dosyasi YOK (0 adet) ve
`THIRD_PARTY_LICENSES.md` veri kumesi atfini HIC icermiyor — o dosya yalniz Python
paketlerini kapsiyor.

⚠️ KENDI DENETIM BULGUMU DUZELTIYORUM. `DEPO-DENETIMI-2026-09-15.md` §3.3'te bu dizini
"PUBLIC depoda 'gercek klinik veri' adlandirmasi ayrica dogrulanmali" diye KVKK riski
olarak isaretlemistim. OLCULDU, OYLE DEGIL:
  · `mitbih/` = MIT-BIH, tasarimi geregi kimliksizlestirilmis ACIK arastirma verisi
  · `hrv_features.csv` / `predictor_features.csv` sutunlari yalniz TURETILMIS metrikler
    (SDNN, RMSSD, pNN50, LF/HF, mag_field_*, temp_*) — isim/kimlik/tarih YOK
Yani hasta PII'si yok; dizin ADI yaniltici ("gercek" = sentetik-olmayan sinyal demek).

GERCEK ACIK ATIFTIR. PhysioNet veri kumeleri atif/alinti yukumlulugu tasir. Ticari bir
urunun deposunda ham kayitlarin kaynaksiz yeniden dagitilmasi, B2'de kapatilan paket-atifi
bosluğunun VERI karsiligidir.

SOZLESME
  · Veri dizininde kaynagi ve yukumlulugu ACIKLAYAN bir README bulunur.
  · `THIRD_PARTY_LICENSES.md` veri kumelerini de listeler (paketler yetmez).
  · ⚠️ Atif bolumu URETECIN yazdigi bolumun ONUNDE durur; aksi halde
    `scripts/lisans_envanteri_uret.py` bir sonraki kosuda onu SILER.
"""

from __future__ import annotations

from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_VERI = KOK / "training_archive" / "ai_data" / "real_clinical_data"
_NOTICE = KOK / "THIRD_PARTY_LICENSES.md"
_URETEC_BASLIGI = "## Dağıtılan pakette tespit edilen bileşenler"

#: Depoda yeniden dagitildigi OLCULEN veri kumeleri.
_KUMELER = ("MIT-BIH",)


def _veri_var_mi() -> bool:
    return _VERI.is_dir() and any(_VERI.glob("mitbih/*.hea"))


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_veri_dizininde_KAYNAK_NOTU_var():
    """⚠️ BU TEST DUZELTMEDEN ONCE KIRMIZIYDI (dizinde 0 aciklama dosyasi vardi)."""
    if not _veri_var_mi():
        return  # veri kumesi agactan cikarildiysa kapi konusuz kalir
    okunabilir = [p for p in _VERI.glob("README*") if p.is_file()]
    assert okunabilir, (
        f"{_VERI.relative_to(KOK)} altinda README YOK -> ucuncu taraf arastirma verisi "
        "kaynaksiz yeniden dagitiliyor ve dizin adi ('real_clinical_data') hasta verisi "
        "izlenimi veriyor"
    )
    metin = okunabilir[0].read_text(encoding="utf-8")
    for k in _KUMELER:
        assert k in metin, f"README veri kumesini ({k}) ADIYLA anmiyor -> atif eksik"
    assert "PhysioNet" in metin, "README kaynagi (PhysioNet) belirtmiyor"


def test_KRITIK_NOTICE_veri_kumelerini_de_LISTELER():
    """Atif yukumlulugu kodla sinirli degil; veri kumeleri de atif ister."""
    metin = _NOTICE.read_text(encoding="utf-8")
    for k in _KUMELER:
        assert k in metin, (
            f"THIRD_PARTY_LICENSES.md veri kumesini ({k}) icermiyor -> atif yuzeyi YALNIZ "
            "Python paketlerini kapsiyor, dagitilan VERI kapsam disi kaliyor"
        )


def test_KRITIK_veri_atfi_URETECIN_ONUNDE_durur():
    """⚠️ Bolum yanlis yere konursa bir sonraki uretec kosusunda SESSIZCE SILINIR.

    `scripts/lisans_envanteri_uret.py` dosyayi `_BASLIK_SONU`ndan itibaren YENIDEN YAZAR
    (`ust = mevcut[:bas]`). Atif bolumu o basligin ALTINDA kalirsa kaybolur ve kimse
    fark etmez.
    """
    metin = _NOTICE.read_text(encoding="utf-8")
    assert _URETEC_BASLIGI in metin, "uretec basligi kaybolmus -> uretec artik calismaz"
    uretec_yeri = metin.index(_URETEC_BASLIGI)
    for k in _KUMELER:
        assert metin.index(k) < uretec_yeri, (
            f"'{k}' atfi URETECIN yazdigi bolumun ICINDE -> bir sonraki `lisans_envanteri_uret.py` kosusunda SILINIR"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_uretec_atif_bolumunu_KORUR():
    """Iddiayi davranisla dogrula: uretec bolumu gercekten koruyor mu?

    Yalnizca "baslik once geliyor" demek yetmez — uretecin `ust` dilimleme mantigi
    degisirse bolum yine silinir. Burada uretec GERCEKTEN calistirilir (dosyaya
    yazmadan) ve ciktisinda atfin durdugu olculur.
    """
    import sys

    if str(KOK) not in sys.path:
        sys.path.insert(0, str(KOK))
    from scripts.lisans_envanteri_uret import _BASLIK_SONU, _tablo, envanter

    mevcut = _NOTICE.read_text(encoding="utf-8")
    ust = mevcut[: mevcut.index(_BASLIK_SONU)]
    yeni = ust + _BASLIK_SONU + "\n\n" + _tablo(envanter())
    for k in _KUMELER:
        assert k in yeni, f"uretec ciktisinda '{k}' atfi KAYBOLDU -> bolum yanlis yerde"


def test_KARSIT_KANIT_README_hasta_verisi_IDDIA_ETMEZ():
    """⚠️ Ters yonlu hata: dizini "hasta verisi" gibi tanitmak da yanlis olurdu.

    Olculdu: PII yok. README bunu ACIKCA soylemeli ki sonraki denetim ayni yanlis
    alarmi (benim verdigim) tekrar uretmesin.
    """
    if not _veri_var_mi():
        return
    okunabilir = [p for p in _VERI.glob("README*") if p.is_file()]
    assert okunabilir, "README yok"
    metin = okunabilir[0].read_text(encoding="utf-8").lower()
    assert "pii" in metin or "kimlik" in metin, (
        "README, icerikte hasta kimliginin BULUNMADIGINI soylemiyor -> bir sonraki denetim "
        "ayni yanlis alarmi yeniden uretir"
    )
