# -*- coding: utf-8 -*-
"""Y202 (S-D3I.5, sahip 2026-10-27) — yolda kalan ödeme defteri (`jeton_bekleyen.json`) paylaşılan kökten `PEMF_GUI` altına TAŞINIR.

ARIZA: defter `<PEMF_DATA_DIR>/jeton_bekleyen.json`, yani makine kökündeydi (`%ProgramData%\\PEMF_System`). Launcher köke grup hakkı
vermez (Y96 · Y202a: hak yalnız `<kök>\\PEMF_GUI`) → ikinci Windows hesabının backend'i ilk hesabın defterini GÜNCELLEYEMEZ (jeton
açıldığında yolda kalan ödeme yazılamaz / uzlaşmaz). Karar (AYNEN): "`jeton_bekleyen.json` `PEMF_GUI` altına TAŞINIR (eski konumdan bir
kez, veri kaybetmeden)" · ORTAK §10: "atomik, hedefte varsa EZME; jeton kapalı kalır — Y194".

Ölçülen: GERÇEK `servers.jeton._defter_yolu` (taşıma `os.link` + eski adın silinmesi); süreç ölümü GERÇEK alt süreçte profil kancasıyla
(`os._exit(9)` — `link` / `unlink` çağrısında ya da yeni dizindeki bir dosyaya ilk `write`'ta, bayt yazılmadan ÖNCE; deterministik),
istisnalar EN ALT katta (`os.link`). Jeton kapalı kalır: bu yol yalnız defter açılınca koşar (`JETON_SAHIP_ACIK` değişmedi)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DEFTER = "jeton_bekleyen.json"
#: Türkçe + CRLF + sondaki boşluk: taşıma BAYT AYNI olmalı (metin kipine / kodlamaya düşen bir taşıma bunu bozar).
ICERIK = (
    json.dumps(
        [
            {"istek_id": f"i{n}", "miktar": 1, "tur": "analiz", "detay": "görüntü — ş", "cihaz_id": None, "sahip": "s"}
            for n in range(3)
        ],
        ensure_ascii=False,
    ).encode("utf-8")
    + b"\r\n "
)

_COCUK = textwrap.dedent(
    r"""
    import os, sys
    sys.path.insert(0, sys.argv[1])
    os.environ["PEMF_DATA_DIR"] = sys.argv[2]
    import servers.jeton as j
    an = sys.argv[3]
    gui = os.path.normcase(os.path.abspath(os.path.join(sys.argv[2], "PEMF_GUI")))

    def _kanca(frame, olay, arg):
        if olay != "c_call":
            return
        ad = getattr(arg, "__name__", "")
        if an != "write" and ad == an:
            os._exit(9)
        if an == "write" and ad in ("write", "writelines"):
            dosya = getattr(getattr(arg, "__self__", None), "name", None)
            if isinstance(dosya, str) and os.path.normcase(os.path.dirname(os.path.abspath(dosya))) == gui:
                os._exit(9)

    sys.setprofile(_kanca)
    j._defter_yolu()
    sys.setprofile(None)
    os._exit(0)
    """
)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    veri = tmp_path / "veri"  # conftest tmp_path'e kendi yalıtım dizinlerini koyar — veri kökü AYRI
    veri.mkdir()
    monkeypatch.setenv("PEMF_DATA_DIR", str(veri))
    import servers.jeton as j

    monkeypatch.setattr(j, "_DEFTER_GOCU", {}, raising=False)  # her test YENİ bir süreç açılışı
    return j, veri, veri / DEFTER, veri / "PEMF_GUI" / DEFTER


def _uyarilar(caplog, parca: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == "servers.jeton" and r.levelno >= logging.WARNING and parca in r.getMessage()
    ]


def test_KRITIK_Y202b_eski_kokteki_defter_PEMF_GUI_altina_BAYT_AYNI_tasinir_eski_KALMAZ(ortam):
    j, veri, eski, yeni = ortam
    eski.write_bytes(ICERIK)
    yol = j._defter_yolu()
    assert yol == yeni, f"defter PEMF_GUI altında değil (ikinci hesap paylaşılan kökteki defteri güncelleyemez): {yol}"
    assert yeni.read_bytes() == ICERIK, "taşınan defter eskiyle BAYT AYNI değil"
    assert not eski.exists(), (
        "taşımadan sonra eski konumdaki defter DURUYOR (iki kopya; ikinci hesap eskisini güncelleyemez)"
    )
    assert sorted(p.name for p in veri.iterdir()) == ["PEMF_GUI"], f"kökte artık kaldı: {list(veri.iterdir())}"
    assert sorted(p.name for p in yeni.parent.iterdir()) == [DEFTER], (
        f"PEMF_GUI'de artık kaldı: {list(yeni.parent.iterdir())}"
    )
    assert j._defter_yoneticisi(sahip="s").sahibin_bekleyen_sayisi() == 3, "taşınan defterin kayıtları okunmuyor"


def test_Y202b_eski_defter_YOKKEN_yeni_konum_ve_HICBIR_dosya_islemi_YOK(ortam, monkeypatch):
    j, veri, eski, yeni = ortam

    def _yasak(*a, **k):
        raise AssertionError("eski defter yokken dosya taşıma / silme işlemi yapıldı")

    monkeypatch.setattr(os, "link", _yasak)
    monkeypatch.setattr(Path, "unlink", _yasak)
    assert j._defter_yolu() == yeni and not yeni.exists() and not eski.exists()


@pytest.mark.parametrize("nasil", ["onceden_var", "tasima_aninda_belirdi"])
def test_KRITIK_Y202b_hedefte_defter_VARKEN_EZILMEZ_eski_BIRAKILIR_uyari_BIR_KEZ(ortam, monkeypatch, caplog, nasil):
    j, veri, eski, yeni = ortam
    baska = b'[{"istek_id": "yeni-konumda", "miktar": 2, "sahip": "s"}]'
    eski.write_bytes(ICERIK)
    yeni.parent.mkdir(parents=True, exist_ok=True)
    if nasil == "onceden_var":
        yeni.write_bytes(baska)
    else:
        gercek = os.link

        def _yaris(kaynak, hedef, *a, **k):  # yarış: varlık denetiminden SONRA, bağdan ÖNCE başka bir süreç yazdı
            Path(hedef).write_bytes(baska)
            return gercek(kaynak, hedef, *a, **k)

        monkeypatch.setattr(os, "link", _yaris)
    with caplog.at_level(logging.WARNING, logger="servers.jeton"):
        ilk, ikinci = j._defter_yolu(), j._defter_yolu()
    assert ilk == ikinci == yeni, f"hedefte defter varken kullanılan yol yanlış: {ilk} / {ikinci}"
    assert yeni.read_bytes() == baska, "hedefteki defter EZİLDİ (oradaki yolda kalan ödemeler kayboldu)"
    assert eski.read_bytes() == ICERIK, (
        "eski konumdaki (taşınamayan) defter değişti / silindi — elle inceleme kaydı kayboldu"
    )
    assert len(_uyarilar(caplog, "EZİLMEDİ")) == 1, (
        f"çakışma uyarısı tam BİR kez değil: {[r.getMessage() for r in caplog.records]}"
    )


def test_KRITIK_Y202b_hedefte_AYNI_BOYUTTA_FARKLI_defter_varken_eski_SILINMEZ(ortam, caplog):
    """D67 orkestratör mutantı ("aynı defter" kıyası yalnız boyuta bakar) YAŞADI: hedefteki defter eskiyle AYNI uzunlukta ama
    farklı içerikteyse eski ad "zaten taşınmış" sanılıp SİLİNİYORDU — eski konumdaki yolda kalan ödemeler kaybolurdu."""
    j, veri, eski, yeni = ortam
    farkli = bytes([ICERIK[0] ^ 0x01]) + ICERIK[1:]  # aynı uzunluk, ilk bayt farklı
    assert len(farkli) == len(ICERIK) and farkli != ICERIK
    eski.write_bytes(ICERIK)
    yeni.parent.mkdir(parents=True, exist_ok=True)
    yeni.write_bytes(farkli)
    with caplog.at_level(logging.WARNING, logger="servers.jeton"):
        assert j._defter_yolu() == yeni
    assert eski.read_bytes() == ICERIK, (
        "hedefteki AYNI BOYUTLU farklı defter yüzünden eski defter silindi / değişti (kayıt kaybı)"
    )
    assert yeni.read_bytes() == farkli, "hedefteki defter EZİLDİ"
    assert len(_uyarilar(caplog, "EZİLMEDİ")) == 1, f"çakışma uyarısı yok: {[r.getMessage() for r in caplog.records]}"


def test_KARSIT_Y202b_PEMF_DATA_DIR_YOKKEN_defter_bugunku_gibi_hesaba_ozel_pemf_dizininde(tmp_path, monkeypatch):
    """D67 orkestratör mutantı (`PEMF_DATA_DIR` yokken yol `~/.pemf/PEMF_GUI/`) YAŞADI: Y202 yalnız paylaşılan kökü taşır; geliştirici /
    tek hesap kipinde defter BUGÜNKÜ yerinde (`~/.pemf/jeton_bekleyen.json`) kalır — ikinci bir göç yolu açılmaz."""
    import servers.jeton as j

    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.delenv("PEMF_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(j, "_DEFTER_GOCU", {}, raising=False)
    assert j._defter_yolu() == ev / ".pemf" / DEFTER


def test_KRITIK_Y202b_hedefte_AYNI_BAYTLI_ayri_kopya_varken_eski_ad_silinir_uyari_YOK(ortam, caplog):
    """Tur 2 kolu (D67 çürütme, mutant p4 `samefile or bayt` → `and`): hedefteki defter eskiyle AYNI İÇERİKLİ ama AYRI dosya
    (bağ değil — ör. kopyalayarak yarım kalmış önceki taşıma / geri yükleme) ise eski ad silinir, yeni kullanılır, çakışma uyarısı YOK
    (`_eski_defteri_tasi` belgesi: "aynı dosya / aynı içerikse … eski ad silinir")."""
    j, veri, eski, yeni = ortam
    eski.write_bytes(ICERIK)
    yeni.parent.mkdir(parents=True, exist_ok=True)
    yeni.write_bytes(ICERIK)
    assert not os.path.samefile(eski, yeni), "aparat: iki ad aynı dosya olmamalı"
    with caplog.at_level(logging.WARNING, logger="servers.jeton"):
        yol = j._defter_yolu()
    assert yol == yeni and yeni.read_bytes() == ICERIK, (
        f"aynı içerikli hedef varken kullanılan yol / içerik yanlış: {yol}"
    )
    assert not eski.exists(), (
        "hedefte AYNI içerikli defter varken eski ad silinmedi (iki kopya; gereksiz elle inceleme uyarısı)"
    )
    assert not _uyarilar(caplog, "EZİLMEDİ"), (
        f"aynı içerikte çakışma uyarısı verildi: {[r.getMessage() for r in caplog.records]}"
    )


def test_KRITIK_Y202b_ikinci_acilista_islem_YOK_idempotens(ortam, monkeypatch):
    j, veri, eski, yeni = ortam
    eski.write_bytes(ICERIK)
    assert j._defter_yolu() == yeni
    j._DEFTER_GOCU.clear()  # ikinci açılış

    def _yasak(*a, **k):
        raise AssertionError("ikinci açılışta yeniden taşıma / silme işlemi yapıldı")

    monkeypatch.setattr(os, "link", _yasak)
    monkeypatch.setattr(Path, "unlink", _yasak)
    assert j._defter_yolu() == yeni and yeni.read_bytes() == ICERIK and not eski.exists()


def test_KRITIK_Y202b_tasima_DUSERSE_eski_konum_kullanilir_KAYIT_KAYBOLMAZ_sonraki_acilista_tasinir(
    ortam, monkeypatch, caplog
):
    j, veri, eski, yeni = ortam
    eski.write_bytes(ICERIK)
    gercek = os.link

    def _dus(*a, **k):
        raise PermissionError(13, "erişim engellendi (sahte, en alt kat)")

    monkeypatch.setattr(os, "link", _dus)
    with caplog.at_level(logging.WARNING, logger="servers.jeton"):
        yol = j._defter_yolu()
    assert yol == eski, f"taşıma düşünce eski konumdaki defter BIRAKILDI — kayıtları görünmez olur: {yol}"
    assert eski.read_bytes() == ICERIK and not yeni.exists(), "taşıma düşünce defter değişti / yarım kopya kaldı"
    assert [r for r in _uyarilar(caplog, "taşınamadı") if r.exc_info], (
        "taşıma hatası nedeniyle (exc_info) günlüğe düşmedi"
    )
    assert j._defter_yoneticisi(sahip="s").sahibin_bekleyen_sayisi() == 3, "taşıma düşünce defter okunmuyor"
    monkeypatch.setattr(os, "link", gercek)
    j._DEFTER_GOCU.clear()  # sonraki açılış
    assert j._defter_yolu() == yeni and yeni.read_bytes() == ICERIK and not eski.exists(), (
        "sonraki açılışta taşıma tamamlanmadı"
    )


@pytest.mark.parametrize("an", ["link", "unlink", "write"])
def test_KRITIK_Y202b_tasima_ORTASINDA_OLUM_iki_konumdan_birinde_TAM_sonraki_acilista_tamamlanir(ortam, an):
    j, veri, eski, yeni = ortam
    eski.write_bytes(ICERIK)
    r = subprocess.run(
        [sys.executable, "-c", _COCUK, str(KOK / "apps" / "backend"), str(veri), an],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert r.returncode in (0, 9), f"çocuk süreç beklenmedik biçimde bitti (rc={r.returncode}):\n{r.stderr[-1500:]}"
    tam = [p for p in (eski, yeni) if p.exists() and p.read_bytes() == ICERIK]
    assert tam, (
        f"taşıma ortasında ölüm ({an}, rc={r.returncode}) iki konumda da TAM defter bırakmadı — yolda kalan ödeme KAYBOLDU"
    )
    j._DEFTER_GOCU.clear()  # sonraki açılış (bu süreç)
    yol = j._defter_yolu()
    assert yol == yeni and yeni.read_bytes() == ICERIK, (
        f"ölümden ({an}, rc={r.returncode}) sonraki açılışta yeni konumda TAM defter yok: "
        f"{yeni.read_bytes() if yeni.exists() else 'YOK'!r}"
    )
    assert not eski.exists(), f"ölümden ({an}) sonraki açılışta eski konumdaki defter kaldı (iki kopya)"
