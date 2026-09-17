# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""URUN SENARYO TAKIMI kendi kapisi (2026-09-17).

`scripts/urun_senaryolari.py` sevk edilen EXE'yi calistirip olcer; CI'da EXE YOKTUR, bu
yuzden BU dosya senaryolari KOSTURMAZ. Koruduğu sey baska: takimin GUVENILIR kalmasi.

⚠️ NEDEN GEREKLI. Bir olcum takimi sessizce degersizlesebilir ve bunu kimse fark etmez:

  1. Senaryolar TEKER TEKER silinir -> "hepsi gecti" yazar, ama geriye uc senaryo kalmistir.
  2. KARSIT-KANIT senaryolari atilir -> geri kalan her sey BEDAVAYA yesillenir. Somut ornek:
     C1-C4 "jeton zorlamasi acikken E-stop kapilanmiyor" der. Jeton kapisi HIC calismiyor
     olsaydi da ayni yesili verirlerdi. C0 (kapi ucretli analizi GERCEKTEN 402 ile reddediyor)
     olmadan o dort senaryo bir sey kanitlamaz. Ayni sekilde A1'in "sifreli" iddiasi A0
     olmadan, B9b'nin "uydurmuyor" iddiasi C9 olmadan havada kalir.
  3. BAYAT IKILI nobeti dusurulur -> eski bir EXE olculur ve rapor "urun dogru" der. Bu tuzaga
     bu depoda saatler harcandi (bkz. build'in sahte cikis kodu olayi).
  4. Senaryo KODLARI cakisir -> rapor iki farkli seyi ayni kodla basar; ozet satirinda hangisinin
     dustugu anlasilmaz. (Ilk yazimda C0/C5/C7 hem hata yolunda hem gercek senaryoda
     kullaniliyordu; bu kapi yazilirken yakalandi.)
  5. Sabit kullanici yolu kalir -> baska makinede kosmaz, yani bir daha KOSULMAZ.

Bu kapilarin her biri MUTASYONLA kirmizi gorulmustur (2026-09-17).
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "urun_senaryolari.py"

#: ⚠️ BU SAYAC BIR KEZ ISIRMADI. Ilk yazimda 48'di ama TUM `kayit(...)` cagrilarini sayiyordu;
#: oysa besi OLCUM DEGIL, "backend acilamadi" hata yolu. Gercek senaryo 48, toplam kod 53 ->
#: bir senaryo silindiginde 52 kaliyor ve kapi YESIL doniyordu. Mutasyon yakaladi (2026-09-17).
#: Ders: sayac ankraji, saydigi seyin TANIMIYLA birlikte yazilir.
HATA_YOLU_KODLARI = {"B0", "C-ACILIS1", "C-ACILIS2", "C-ACILIS3", "D0"}

#: 2026-09-17 olcumunde 48 GERCEK senaryo vardi. Eklemek serbest, silmek KIRMIZI.
#: (Depodaki rota-sozlesmesi kapisiyla ayni desen — "sessiz kuculme" en sinsi gerilemedir.)
ASGARI_SENARYO = 48

#: Bunlar olmadan geri kalan senaryolar BEDAVAYA yesillenir.
KARSIT_KANIT_KODLARI = {
    "A0",  # sifreleme KAPALIYKEN saglik ucu "sifreli" DEMEMELI
    "B9b",  # launcher'siz acilista buildId UYDURULMAMALI
    "C0",  # jeton kapisi ucretli analizi GERCEKTEN reddedebilmeli
    "C9",  # ...ve sha gecildiginde buildId'yi RAPORLAYABILMELI
}


def _agac() -> ast.Module:
    return ast.parse(BETIK.read_text(encoding="utf-8"))


def _senaryo_kodlari() -> list[str]:
    """`kayit("KOD", ...)` cagrilarinin BIRINCI argumani — metinden degil AST'den."""
    kodlar = []
    for n in ast.walk(_agac()):
        if not isinstance(n, ast.Call):
            continue
        ad = getattr(n.func, "id", getattr(n.func, "attr", None))
        if ad != "kayit" or not n.args:
            continue
        ilk = n.args[0]
        if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
            kodlar.append(ilk.value)
    return kodlar


def test_KRITIK_betik_yerinde():
    assert BETIK.exists(), (
        "scripts/urun_senaryolari.py YOK -> urun-seviyesi dogrulama kayboldu. Suit yesilken "
        "urunun hasta gecmisini kaybettigi 2026-09-13 sinifi bir daha olculemez."
    )


def test_KRITIK_senaryo_sayisi_SESSIZCE_KUCULMEDI():
    olculen = set(_senaryo_kodlari()) - HATA_YOLU_KODLARI
    assert len(olculen) >= ASGARI_SENARYO, (
        f"OLCUM senaryosu sayisi {len(olculen)} — beklenen en az {ASGARI_SENARYO}. Takim "
        "kucultulduyse bu SABIT de bilincli olarak dusurulmeli; sessiz kuculme raporun anlamini "
        "bozar. (Hata-yolu kodlari sayilmaz: onlar olcum degil, 'backend acilamadi' dallari.)"
    )


def test_KRITIK_KARSIT_KANIT_senaryolari_DURUYOR():
    """⚠️ Bu kapinin isi: "hepsi gecti" cumlesini anlamli tutmak."""
    kodlar = set(_senaryo_kodlari())
    eksik = sorted(KARSIT_KANIT_KODLARI - kodlar)
    assert not eksik, (
        f"karsit-kanit senaryolari KAYBOLMUS: {eksik}. Bunlar olmadan olculen ozellik KAPALI olsa "
        "bile takim YESIL doner (or. jeton kapisi hic calismazken 'E-stop kapilanmiyor' demek)."
    )


def test_KRITIK_senaryo_kodlari_BENZERSIZ():
    """Ayni kod iki farkli olcumde kullanilirsa ozet satiri hangisinin dustugunu SOYLEYEMEZ."""
    kodlar = _senaryo_kodlari()
    tekrar = sorted({k for k in kodlar if kodlar.count(k) > 1})
    assert not tekrar, (
        f"senaryo kodu TEKRARLANIYOR: {tekrar}. Ilk yazimda C0/C5/C7 hem 'backend acilamadi' hata "
        "yolunda hem gercek senaryoda kullaniliyordu -> rapor iki ayri seyi ayni satirla basiyordu."
    )


def test_KRITIK_BAYAT_IKILI_nobeti_main_icinden_CAGRILIYOR():
    """⚠️ Fonksiyonun VAR OLMASI yetmez — cagrilmazsa eski EXE olculur ve rapor YALAN soyler.

    Capa `main` govdesindeki GERCEK cagriya pinli (metin aramasi docstring'e takilirdi:
    modul docstring'i zaten "BAYAT-IKILI NOBETI" diyor).
    """
    agac = _agac()
    main = next((n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    assert main is not None, "betikte `main` yok — giris noktasi degismis, kapi guncellenmeli"
    cagrilar = {getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(main) if isinstance(c, ast.Call)}
    assert "bayat_ikili_nobeti" in cagrilar, (
        "`main` artik bayat-ikili nobetini CAGIRMIYOR -> kaynaklardan eski bir EXE olculup "
        "'urun dogru' diye raporlanabilir. Bu tuzaga bu depoda daha once saatler harcandi."
    )


def test_KRITIK_nobet_BAYATSA_DURUYOR():
    """Nobet 'uyarip devam' etmemeli: olcum gecersizse KOSMAMALI."""
    agac = _agac()
    fn = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "bayat_ikili_nobeti"),
        None,
    )
    assert fn is not None, "bayat_ikili_nobeti fonksiyonu YOK"

    # ⚠️ `any(Raise in fn)` YETMEZ — MUTASYONLA olculdu (2026-09-17): fonksiyonda AYRICA
    # "EXE yok" dali da firlatiyor, bu yuzden BAYATLIK dalindaki `raise`i `print`e cevirmek
    # kapiyi YESIL birakiyordu. Capa, `bayat` listesini denetleyen DALIN KENDISINE pinli.
    bayat_dali = next(
        (
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.If) and any(isinstance(x, ast.Name) and x.id == "bayat" for x in ast.walk(n.test))
        ),
        None,
    )
    assert bayat_dali is not None, (
        "nobette `bayat` listesini denetleyen dal YOK -> kaynak/EXE zaman karsilastirmasi kalkmis"
    )
    assert any(isinstance(n, ast.Raise) for n in bayat_dali.body), (
        "bayat EXE bulundugunda artik FIRLATILMIYOR -> betik yalnizca uyarip olcmeye devam eder; "
        "urettigi rapor GECERSIZ olur ama GECERLI gorunur. Bu tuzaga bu depoda saatler harcandi."
    )


def test_KARSIT_KANIT_betikte_SABIT_kullanici_yolu_YOK():
    """Sabit yol kalirsa betik baska makinede kosmaz -> bir daha HIC kosulmaz."""
    metin = BETIK.read_text(encoding="utf-8")
    for kotu in ("C:\\Users\\", "C:/Users/"):
        assert kotu not in metin, (
            f"betikte sabit kullanici yolu var ({kotu!r}) -> yalniz yazildigi makinede kosar. "
            "EXE yolu --exe / PEMF_EXE / depo-ici varsayilan uzerinden cozulmeli."
        )


def test_KARSIT_KANIT_calisma_alani_DEPO_AGACINDA_DEGIL():
    """Senaryolar ACL-kilitli ve bozuk dosyalar uretir; bunlar depoya sizmamali."""
    agac = _agac()
    for n in ast.walk(agac):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CALISMA" for t in n.targets):
            kaynak = ast.unparse(n.value)
            assert "gettempdir" in kaynak, (
                f"CALISMA alani gecici dizinde DEGIL ({kaynak}) -> ACL-kilitli dosyalar ve bozuk "
                "sir dosyalari depo agacinda kalir."
            )
            return
    raise AssertionError("CALISMA atamasi bulunamadi — kapi bayatlamis")
