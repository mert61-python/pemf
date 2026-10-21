# -*- coding: utf-8 -*-
"""I18N-0 · SUNUCU ALTYAPISI (T5 / T6 / T7) — `utils/ceviri.py` + istek dili ara katmanı + cihaz dili ayarı + donmuş yol.

Kilitlenen davranış:
  * isteğin dili `X-PEMF-Dil` > `?dil=` > tr; `Accept-Language` YOK SAYILIR (İngilizce Windows'un WebView2'si onu kendisi doldurur);
    başlıksız / geçersiz = tr (yayındaki eski APK bugünkü gibi Türkçe alır);
  * eksik anahtar test koşusunda HATA (sessiz geçmez); üründe Türkçeye, o da yoksa anahtara düşer (boş ileti yok);
  * istek dışı (arka plan) üretim cihaz dili ayarını kullanır (`arayuz_dili.json`), yoksa tr;
  * donmuş EXE'de katalog `_MEIPASS/i18n` (donmuş dal ÖNCE — yukarı yürüme yok); PyInstaller `datas` + app katmanı kökü.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "apps" / "backend"))

from utils import ceviri  # noqa: E402


@pytest.fixture(autouse=True)
def _taze_katalog():
    ceviri.kataloglar(yeniden=True)
    yield
    ceviri.kataloglar(yeniden=True)


# ── dil çözümü ───────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "baslik,sorgu,beklenen",
    [
        ("en", None, "en"),
        ("EN", None, "en"),
        ("tr", "en", "tr"),  # başlık önce
        (None, "en", "en"),
        ("de", None, "tr"),  # geçersiz → tr
        ("", "", "tr"),
        (None, None, "tr"),  # başlıksız eski istemci
    ],
)
def test_dil_cozumu_baslik_sorgu_tr(baslik, sorgu, beklenen):
    assert ceviri.dil_coz(baslik, sorgu) == beklenen


# ── t(): yer tutucu, çoğul, eksik anahtar ────────────────────────────────────────────────────────────────────


def test_t_iki_dilde_ve_yer_tutucu():
    assert ceviri.t("ayarlar.arayuzDili.gecersiz", dil="tr", dilKodu="de") == ceviri.kataloglar()["tr"][
        "ayarlar.arayuzDili.gecersiz"
    ].replace("{{dilKodu}}", "de")
    en = ceviri.t("ayarlar.arayuzDili.gecersiz", dil="en", dilKodu="de")
    assert "de" in en and en != ceviri.t("ayarlar.arayuzDili.gecersiz", dil="tr", dilKodu="de")


def test_eksik_anahtar_testte_HATA():
    with pytest.raises(KeyError):
        ceviri.t("olmayan.anahtar", dil="en")


def test_eksik_yer_tutucu_testte_HATA():
    with pytest.raises(KeyError):
        ceviri.t("ayarlar.arayuzDili.gecersiz", dil="tr")


def test_uretimde_eksik_anahtar_bos_degil_anahtar_doner(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PEMF_I18N_KATI", raising=False)
    assert ceviri.t("olmayan.anahtar", dil="en") == "olmayan.anahtar"


def test_tarih_metni_iki_dilde_24_saat():
    an = datetime(2026, 10, 13, 19, 45)
    assert ceviri.tarih_metni(an, dil="tr") == "13 Ekim 2026, 19:45"
    assert ceviri.tarih_metni(an, dil="en") == "13 Oct 2026, 19:45"


# ── istek dışı (arka plan) üretim: cihaz dili ────────────────────────────────────────────────────────────────


def test_istek_disi_cihaz_dili_ayari(tmp_path, monkeypatch):
    monkeypatch.setattr(ceviri, "_veri_koku", lambda: tmp_path)
    monkeypatch.setattr(ceviri, "I18N_EN_ACIK", True)  # I18NI-A3.4: cihaz dili yalnız bayrak açıkken etkin
    assert ceviri.istek_dili_var.get() is None
    assert ceviri.etkin_dil() == "tr"  # ayar yok → tr
    assert ceviri.cihaz_dili_yaz("en") == "en"
    assert json.loads((tmp_path / "arayuz_dili.json").read_text(encoding="utf-8")) == {"dil": "en"}
    assert ceviri.etkin_dil() == "en"
    jeton = ceviri.istek_dili_var.set("tr")  # istek içinde istek dili kazanır
    try:
        assert ceviri.etkin_dil() == "tr"
    finally:
        ceviri.istek_dili_var.reset(jeton)
    (tmp_path / "arayuz_dili.json").write_text("{bozuk", encoding="utf-8")
    assert ceviri.etkin_dil() == "tr"  # bozuk dosya → tr, çökme yok
    with pytest.raises(ValueError):
        ceviri.cihaz_dili_yaz("fr")


# ── donmuş EXE ───────────────────────────────────────────────────────────────────────────────────────────────


def test_donmus_exede_katalog_MEIPASS_i18n(tmp_path, monkeypatch):
    (tmp_path / "i18n").mkdir()
    for d in ("tr", "en"):
        (tmp_path / "i18n" / f"{d}.json").write_text(json.dumps({"x": {"y": f"donmus-{d}"}}), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ceviri.katalog_dizini() == tmp_path / "i18n"
    ceviri.kataloglar(yeniden=True)
    assert ceviri.t("x.y", dil="en") == "donmus-en"


def _datas_ekleri(agac) -> set:
    """Spec'teki GERÇEK `datas.append((kaynak, hedef))` çağrıları (yorum / dizgi sayılmaz — AST)."""
    import ast

    bulunan = set()
    for n in ast.walk(agac):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "append"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "datas"
            and n.args
            and isinstance(n.args[0], ast.Tuple)
            and len(n.args[0].elts) == 2
        ):
            k, h = n.args[0].elts
            bulunan.add((ast.unparse(k), ast.unparse(h)))
    return bulunan


def test_spec_katalogu_paketler_ve_APP_katmaninda():
    import ast

    spec = ast.parse((KOK / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8"))
    assert ("_i18n_dir", "'i18n'") in _datas_ekleri(spec), "spec katalog dizinini `_internal/i18n`e paketlemiyor"
    atamalar = {
        n.targets[0].id: ast.unparse(n.value)
        for n in ast.walk(spec)
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
    }
    assert atamalar.get("_i18n_dir") == "os.path.join(backend_path, 'i18n')"
    # APP_ROOTS üst düzey atamasının liste değişmezleri (yorumdaki satır sayılmaz; `[...] + [...]` biçiminde sol taraf).
    zipb = ast.parse((KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8"))
    liste = None
    for n in zipb.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "APP_ROOTS":
            sol = n.value.left if isinstance(n.value, ast.BinOp) else n.value
            liste = [e.value for e in sol.elts if isinstance(e, ast.Constant)]
    assert liste, "make_base_zip.APP_ROOTS okunamadı"
    assert "PEMF_Backend/_internal/i18n" in liste, (
        "katalog app katmanında olmalı (deps'e düşerse her yayında 1,49 GB iner)"
    )


# ── uçtan uca: gerçek uygulama + ara katman (Accept-Language yok sayılır) ────────────────────────────────────


@pytest.fixture
def istemci(tmp_path, monkeypatch):
    monkeypatch.setattr(ceviri, "_veri_koku", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from servers.api_server import app

    with TestClient(app) as c:
        yield c


def _ileti(r):
    return r.json().get("detail")


def test_uc_baslik_EN_ingilizce_basliksiz_turkce_accept_language_yok_sayilir(istemci):
    govde = {"dil": "fr"}
    tr = istemci.post("/api/settings/arayuz-dili", json=govde)
    en = istemci.post("/api/settings/arayuz-dili", json=govde, headers={"X-PEMF-Dil": "en"})
    al = istemci.post("/api/settings/arayuz-dili", json=govde, headers={"Accept-Language": "en-US,en;q=0.9"})
    sorgu = istemci.post("/api/settings/arayuz-dili?dil=en", json=govde)
    assert tr.status_code == en.status_code == al.status_code == sorgu.status_code == 400
    assert _ileti(tr) == ceviri.t("ayarlar.arayuzDili.gecersiz", dil="tr", dilKodu="fr")
    assert _ileti(en) == ceviri.t("ayarlar.arayuzDili.gecersiz", dil="en", dilKodu="fr")
    assert _ileti(al) == _ileti(tr), "Accept-Language dili DEĞİŞTİRMEMELİ (WebView2 onu işletim sisteminden doldurur)"
    assert _ileti(sorgu) == _ileti(en)


def test_uc_cihaz_dili_yazilir_ve_okunur(istemci, tmp_path):
    assert istemci.get("/api/settings/arayuz-dili").json() == {"dil": None}
    r = istemci.post("/api/settings/arayuz-dili", json={"dil": "en"})
    assert r.status_code == 200 and r.json() == {"status": "success", "dil": "en"}
    assert istemci.get("/api/settings/arayuz-dili").json() == {"dil": "en"}
    assert json.loads((tmp_path / "arayuz_dili.json").read_text(encoding="utf-8")) == {"dil": "en"}
    # Cihaz dili EN olsa bile başlıksız İSTEK Türkçe alır (eski APK / eski arayüz bugünkü gibi) — cihaz dili yalnız istek DIŞI üretimler için.
    r = istemci.post("/api/settings/arayuz-dili", json={"dil": "xx"})
    assert r.json()["detail"] == ceviri.t("ayarlar.arayuzDili.gecersiz", dil="tr", dilKodu="xx")
