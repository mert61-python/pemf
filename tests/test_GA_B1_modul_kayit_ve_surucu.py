# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B1 — modül kayıt defteri (`servers/modul_kayit.py`) + sürücü arayüzü / alt süreç kabuğu (`servers/modul_surucu.py`).

SÖZLEŞME:
  - `modul.json` şema 1 doğrulaması (kimlik = klasör adı, iki dilli ad, bağlantı türü, sınırlar, bekçi süresi, surucu.py) — bozuk modül
    listede HATA KODUYLA görünür, seçilemez.
  - Sınırlar SUNUCUDA zorlanır: bilinmeyen alan / sayı olmayan / sınır dışı → reddedilir (karta gitmez).
  - Görünürlük varsayılan GİZLİ (Y299); yazım atomik.
  - Kabuk: `acil_durdur` takılı bir komutu BEKLEMEZ (kendi iş parçacığı); girdi kapanınca (ebeveyn gitti) ÖNCE `acil_durdur` sonra `kes`;
    sürücü hatası / bozuk istek / bilinmeyen işlem kabuğu düşürmez.
"""

from __future__ import annotations

import io
import json
import queue
import threading
import time
from pathlib import Path

import pytest

GECERLI = {
    "sema": 1,
    "kimlik": "deneme",
    "ad": {"tr": "Deneme", "en": "Trial"},
    "surum": "0.1.0",
    "baglanti": "sahte",
    "sinirlar": {"frekans_hz": [1, 500], "duty_yuzde": [0, 50]},
    "bekci_ms": 1500,
}


def _modul(kok: Path, ad: str = "deneme", m: dict | None = None, surucu: str | None = "") -> Path:
    d = kok / ad
    d.mkdir(parents=True, exist_ok=True)
    if m is not None:
        (d / "modul.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    if surucu is not None:
        (d / "surucu.py").write_text(surucu or "from servers.modul_surucu import BobinSurucusu\n", encoding="utf-8")
    return d


@pytest.mark.parametrize(
    "bozma,kod",
    [
        (lambda m: m.update(sema=2), "semaUyumsuz"),
        (lambda m: m.update(kimlik="Baska"), "kimlikGecersiz"),
        (lambda m: m.update(kimlik=7), "kimlikGecersiz"),
        (lambda m: m.update(kimlik="baska-modul"), "kimlikGecersiz"),  # biçimi geçerli ama klasör adı DEĞİL
        (lambda m: m.update(ad={"tr": "x"}), "adGecersiz"),
        (lambda m: m.update(ad={"tr": "x", "en": "  "}), "adGecersiz"),
        (lambda m: m.update(ad="x"), "adGecersiz"),
        (lambda m: m.update(surum=""), "surumGecersiz"),
        (lambda m: m.update(baglanti="tcp"), "baglantiGecersiz"),
        (lambda m: m.update(sinirlar={}), "sinirlarGecersiz"),
        (lambda m: m.update(sinirlar={"guc": [0, 1]}), "sinirlarGecersiz"),
        (lambda m: m.update(sinirlar={"frekans_hz": [5, 1]}), "sinirlarGecersiz"),
        (lambda m: m.update(sinirlar={"frekans_hz": [1, float("inf")]}), "sinirlarGecersiz"),
        (lambda m: m.update(sinirlar={"frekans_hz": [True, 3]}), "sinirlarGecersiz"),
        (lambda m: m.update(sinirlar={"frekans_hz": [1]}), "sinirlarGecersiz"),
        (lambda m: m.update(bekci_ms=10), "bekciGecersiz"),
        (lambda m: m.update(bekci_ms=True), "bekciGecersiz"),
        (lambda m: m.update(bekci_ms=1500.0), "bekciGecersiz"),
        (lambda m: m.update(bekci_ms=1499), "bekciGecersiz"),  # bekçi ≥ 3 × kalp aralığı (500 ms)
        (lambda m: m.update(bekci_ms=5001), "bekciGecersiz"),
    ],
)
def test_KRITIK_GA_B1_modul_json_DOGRULAMA(tmp_path, bozma, kod):
    from servers.modul_kayit import ModulHatasi, oku

    m = json.loads(json.dumps(GECERLI))
    bozma(m)
    with pytest.raises(ModulHatasi) as e:
        oku(_modul(tmp_path, m=m))
    assert e.value.kod == kod


def test_KRITIK_GA_B1_modul_json_YOK_BOZUK_surucusuz(tmp_path):
    from servers.modul_kayit import ModulHatasi, oku

    for d, kod in (
        (_modul(tmp_path, "a1", m=None), "modulJsonYok"),
        (_modul(tmp_path, "a2", m=None), "modulJsonBozuk"),
        (_modul(tmp_path, "a3", m=[1]), "semaUyumsuz"),
        (_modul(tmp_path, "deneme", m=GECERLI, surucu=None), "surucuYok"),
    ):
        if kod == "modulJsonBozuk":
            (d / "modul.json").write_text("{bozuk", encoding="utf-8")
        with pytest.raises(ModulHatasi) as e:
            oku(d)
        assert e.value.kod == kod
    assert str(ModulHatasi("x", "alan")) == "x:alan" and str(ModulHatasi("x")) == "x"


def test_KRITIK_GA_B1_kok_LISTE_bul(tmp_path, monkeypatch):
    kok = tmp_path / "kok"
    kok.mkdir()
    import sys

    from servers import modul_kayit

    monkeypatch.setenv("PEMF_MODULLER_KOKU", str(kok / "yok"))
    assert modul_kayit.liste() == []
    monkeypatch.setenv("PEMF_MODULLER_KOKU", str(kok))
    _modul(kok, "deneme", m=GECERLI)
    _modul(kok, "bozuk", m={"sema": 9})
    (kok / ".gizli").mkdir()
    (kok / "_ozel").mkdir()
    (kok / "dosya.txt").write_text("x", encoding="utf-8")
    assert modul_kayit.liste() == [
        {"kimlik": "bozuk", "hata": "semaUyumsuz", "alan": "sema"},
        {
            "kimlik": "deneme",
            "ad": GECERLI["ad"],
            "surum": "0.1.0",
            "baglanti": "sahte",
            "sinirlar": GECERLI["sinirlar"],
            "bekci_ms": 1500,
        },
    ]
    d, m = modul_kayit.bul("deneme")
    assert d == kok / "deneme" and m["kimlik"] == "deneme"
    for kotu in ("YOK!", 5, "olmayan"):
        with pytest.raises(modul_kayit.ModulHatasi) as e:
            modul_kayit.bul(kotu)
        assert e.value.kod == "modulYok"
    # kök çözümü: açık değişken yoksa kaynakta depo kökü / donmuşta paket
    monkeypatch.delenv("PEMF_MODULLER_KOKU")
    assert modul_kayit.kok() == Path(modul_kayit.__file__).resolve().parents[3] / "moduller"
    assert (modul_kayit.kok() / "ornek" / "modul.json").is_file()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert modul_kayit.kok() == tmp_path / "moduller"


def test_KRITIK_GA_B1_ayar_SUNUCUDA_SINIR():
    from servers.modul_kayit import ModulHatasi, ayar_dogrula

    assert ayar_dogrula(GECERLI, {"frekans_hz": 100, "duty_yuzde": 50}) == {"frekans_hz": 100, "duty_yuzde": 50}
    for ayar, kod, alan in (
        ({}, "ayarGecersiz", ""),
        ([1], "ayarGecersiz", ""),
        ({"guc": 1}, "ayarBilinmeyen", "guc"),
        ({"frekans_hz": "100"}, "ayarSayiDegil", "frekans_hz"),
        ({"frekans_hz": float("nan")}, "ayarSayiDegil", "frekans_hz"),
        ({"frekans_hz": True}, "ayarSayiDegil", "frekans_hz"),
        ({"frekans_hz": 501}, "ayarSinirDisi", "frekans_hz"),
        ({"duty_yuzde": -0.1}, "ayarSinirDisi", "duty_yuzde"),
    ):
        with pytest.raises(ModulHatasi) as e:
            ayar_dogrula(GECERLI, ayar)
        assert (e.value.kod, e.value.alan) == (kod, alan)


def test_KRITIK_GA_B1_gorunurluk_VARSAYILAN_GIZLI_atomik(tmp_path, monkeypatch):
    from servers import modul_kayit
    from utils import path_utils

    monkeypatch.setattr(path_utils, "get_app_data_directory", lambda: str(tmp_path))
    assert modul_kayit.gorunur_mu() is False  # dosya yok → GİZLİ
    assert modul_kayit.gorunur_yaz(True) is True and modul_kayit.gorunur_mu() is True
    assert modul_kayit.gorunur_yaz(False) is False and modul_kayit.gorunur_mu() is False
    (tmp_path / modul_kayit.AYAR_DOSYASI).write_text('{"gorunur": "evet"}', encoding="utf-8")
    assert modul_kayit.gorunur_mu() is False  # yalnız true açar
    (tmp_path / modul_kayit.AYAR_DOSYASI).write_text("[1]", encoding="utf-8")
    assert modul_kayit.gorunur_mu() is False
    (tmp_path / modul_kayit.AYAR_DOSYASI).write_text("{bozuk", encoding="utf-8")
    assert modul_kayit.gorunur_mu() is False
    assert list(tmp_path.glob(".gm-*")) == []

    def _patla(*a, **k):
        raise OSError("disk dolu")

    monkeypatch.setattr(modul_kayit.os, "replace", _patla)
    with pytest.raises(OSError):
        modul_kayit.gorunur_yaz(True)
    assert list(tmp_path.glob(".gm-*")) == []  # yarım geçici dosya kalmaz

    def _silinemez(*a, **k):
        raise OSError("kilitli")

    monkeypatch.setattr(modul_kayit.os, "unlink", _silinemez)
    with pytest.raises(OSError):
        modul_kayit.gorunur_yaz(True)


# ── sürücü arayüzü + kabuk ──────────────────────────────────────────────────────────────────────────
def test_KRITIK_GA_B1_arayuz_VARSAYILANLAR_ve_KLASOR_ICI_yol(tmp_path):
    from servers.modul_surucu import BobinSurucusu, SurucuHatasi

    s = BobinSurucusu({"kimlik": "x"}, str(tmp_path))
    for islem in ("baglan", "kes", "baslat", "durdur", "acil_durdur", "kalp", "durum"):
        with pytest.raises(NotImplementedError):
            getattr(s, islem)()
    with pytest.raises(NotImplementedError):
        s.uygula({})
    assert s.dosya_yolu("kayit.json") == str(tmp_path / "kayit.json")
    for kotu in ("../kacis.txt", str(tmp_path.parent / "x")):
        with pytest.raises(SurucuHatasi) as e:
            s.dosya_yolu(kotu)
        assert e.value.kod == "klasorDisi"


def test_KRITIK_GA_B1_surucu_YUKLEME(tmp_path):
    from servers.modul_kayit import ModulHatasi
    from servers.modul_surucu import SurucuHatasi, surucuyu_yukle

    d = _modul(
        tmp_path,
        m=GECERLI,
        surucu="from servers.modul_surucu import BobinSurucusu\nclass Surucu(BobinSurucusu):\n    pass\n",
    )
    s = surucuyu_yukle(str(d))
    assert type(s).__name__ == "Surucu" and s.modul["kimlik"] == "deneme" and s.klasor == str(d)
    (d / "surucu.py").write_text("class Surucu:\n    pass\n", encoding="utf-8")
    with pytest.raises(SurucuHatasi) as e:
        surucuyu_yukle(str(d))
    assert e.value.kod == "surucuSinifiYok"
    with pytest.raises(ModulHatasi):
        surucuyu_yukle(str(_modul(tmp_path, "bos", m=None)))


class _Kayitci:
    """Sahte sürücü: çağrıları kaydeder; `uygula` bir olay gelene dek TAKILIR."""

    def __init__(self):
        self.cagri: list[str] = []
        self.birak = threading.Event()

    def baglan(self):
        self.cagri.append("baglan")

    def kes(self):
        self.cagri.append("kes")

    def uygula(self, ayar):
        self.cagri.append(f"uygula:{sorted(ayar)}")
        self.birak.wait(10)

    def baslat(self):
        from servers.modul_surucu import SurucuHatasi

        raise SurucuHatasi("kartYok")

    def durdur(self):
        raise RuntimeError("bozuk")

    def acil_durdur(self):
        self.cagri.append("acil")

    def kalp(self):
        self.cagri.append("kalp")

    def durum(self):
        return {"bobin": False}


class _Girdi:
    """Satır satır beslenen girdi akışı (kabuk okurken test yazar); None = kapandı (EOF)."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()

    def __iter__(self):
        while True:
            s = self.q.get()
            if s is None:
                return
            yield s


class _Cikti(io.StringIO):
    def __init__(self):
        super().__init__()
        self.olay = threading.Event()

    def flush(self):
        self.olay.set()

    def yanitlar(self):
        return [json.loads(s) for s in self.getvalue().splitlines()]


def _bekle(cikti, kosul, sure=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < sure:
        if kosul(cikti.yanitlar()):
            return True
        time.sleep(0.005)
    return False


def test_KRITIK_GA_B1_kabuk_ACIL_takili_komutu_BEKLEMEZ_ve_EOF_ACIL_KES():
    from servers.modul_surucu import kabuk

    s, g, c = _Kayitci(), _Girdi(), _Cikti()
    t = threading.Thread(target=kabuk, args=(s, g, c), daemon=True)
    t.start()
    g.q.put('{"id": 1, "islem": "baglan"}\n')
    g.q.put('{"id": 2, "islem": "uygula", "ayar": {"frekans_hz": 100}}\n')  # TAKILIR
    g.q.put('{"id": 3, "islem": "kalp"}\n')  # sırada bekler
    g.q.put('{"id": 4, "islem": "acil_durdur"}\n')
    assert _bekle(c, lambda ys: any(y["id"] == 4 for y in ys))
    ys = c.yanitlar()
    assert {"id": 4, "tamam": True} in ys and not any(
        y["id"] == 2 for y in ys
    )  # acil, takılı uygula'dan ÖNCE yanıtlandı
    s.birak.set()
    g.q.put("\n")
    g.q.put("bozuk{\n")
    g.q.put('"metin"\n')
    g.q.put('{"id": 5, "islem": "rm -rf"}\n')
    g.q.put('{"id": 6, "islem": "baslat"}\n')
    g.q.put('{"id": 7, "islem": "durdur"}\n')
    g.q.put('{"id": 8, "islem": "durum"}\n')
    assert _bekle(c, lambda ys: any(y["id"] == 8 for y in ys))
    ys = {y["id"]: y for y in c.yanitlar()}
    assert ys[None] == {"id": None, "tamam": False, "hata": "bozukIstek"}
    assert ys[5] == {"id": 5, "tamam": False, "hata": "bilinmeyenIslem"}
    assert ys[6] == {"id": 6, "tamam": False, "hata": "kartYok"}
    assert ys[7] == {"id": 7, "tamam": False, "hata": "RuntimeError"}
    assert ys[8] == {"id": 8, "tamam": True, "durum": {"bobin": False}}
    assert ys[2]["tamam"] is True and ys[3]["tamam"] is True
    g.q.put(None)  # ebeveyn gitti
    t.join(5)
    assert not t.is_alive()
    assert s.cagri[-2:] == ["acil", "kes"]  # ÖNCE acil, sonra kes


def test_KRITIK_GA_B1_kabuk_varsayilan_AKISLAR_ve_main(monkeypatch, tmp_path):
    import sys

    from servers import modul_surucu

    s = _Kayitci()
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"id": 1, "islem": "kalp"}\n'))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert modul_surucu.kabuk(s) == 0
    assert json.loads(out.getvalue().splitlines()[0]) == {"id": 1, "tamam": True}
    # main: argüman sayısı / yükleme hatası / başarı
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert modul_surucu.main([]) == 2
    cikti = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cikti)
    assert modul_surucu.main([str(tmp_path / "yok")]) == 3
    assert json.loads(cikti.getvalue()) == {"id": None, "tamam": False, "hata": "yuklenemedi:modulJsonYok"}
    d = _modul(
        tmp_path,
        m=GECERLI,
        surucu="from servers.modul_surucu import BobinSurucusu\nclass Surucu(BobinSurucusu):\n    def acil_durdur(self):\n        pass\n    def kes(self):\n        pass\n",
    )
    cikti2 = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cikti2)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert modul_surucu.main([str(d)]) == 0
    assert sys.stdout is sys.stderr  # protokol akışı korunur
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(modul_surucu, "surucuyu_yukle", lambda k: (_ for _ in ()).throw(RuntimeError("x")))
    c3 = io.StringIO()
    monkeypatch.setattr(sys, "stdout", c3)
    assert modul_surucu.main(["x"]) == 3 and "yuklenemedi:RuntimeError" in c3.getvalue()
