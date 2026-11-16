# -*- coding: utf-8 -*-
"""YH · S-YH.1 (sahip Y294): `/api/health` `buildId` ÇALIŞAN paketi söyler — `paketIcerigi` ile ÇELİŞMEZ.

YH-A4 çalışan runtime'ın içerik kimliğini ayrı alanda (`paketIcerigi`) verdi; `buildId` ise launcher KAYDINDAN (`PEMF_BASE_SHA`)
gelmeye devam etti → runtime kayıt dışı değiştiyse (yerel deneme kurulumu, elle kopya) iki alan ÇELİŞİYORDU: `buildId` eski paketi,
`paketIcerigi` yenisini söylüyordu. Karar: başlatıcı tarafı da düzeltilir (launcher 1.9.55) —
  * launcher kayda app katmanının içerik kimliğini de yazar (`installed_packages.json` → `app_icerik`) ve `PEMF_BASE_SHA`yı YALNIZ
    kayıt diskteki runtime'la eşleşiyorsa geçirir (Rust: `install.rs` `kayit_runtime_ile_ayni`, testleri orada);
  * geçirmezse (ya da değer geçersizse) backend `buildId` olarak çalışan paketin içerik kimliğini verir (= `paketIcerigi`).
Sözleşme [5.5] eşleşen kayıtta AYNEN: `buildId` = manifest app-katmanı sha'sı[:12] = CHANGELOG etiketi. Kaynak ağacından koşuda ikisi
de yok → boş (uydurma kimlik ÜRETİLMEZ).

Ölçüm: GERÇEK `get_build_id` / `get_paket_icerigi` donmuş-EXE benzetimiyle (`sys.frozen`, `sys.executable` tmp; YH-A4 deseni) ·
GERÇEK `/api/health` (TestClient, lifespan YOK).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ICERIK = "AB" * 32
_ICERIK12 = "abababababab"
_KAYIT = "13d967121f94" + "0" * 52


def _donmus(monkeypatch, tmp: Path) -> None:
    from utils import path_utils

    exe_dizini = tmp / "runtime" / "PEMF_Backend"
    exe_dizini.mkdir(parents=True)
    (exe_dizini / "_app_roots.json").write_text(
        json.dumps({"roots": ["PEMF_Backend/PEMF_Backend.exe"], "icerik": _ICERIK}), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dizini / "PEMF_Backend.exe"))
    monkeypatch.setattr(path_utils, "_PAKET_ICERIGI", None)


def test_KRITIK_kimlik_gecmediyse_buildId_CALISAN_paketin_icerigi_paketIcerigi_ile_AYNI(monkeypatch, tmp_path):
    """Launcher kaydı diskteki runtime'la eşleşmedi → `PEMF_BASE_SHA` GEÇMEZ → `buildId` = çalışan paketin içerik kimliği."""
    from utils import path_utils

    _donmus(monkeypatch, tmp_path)
    monkeypatch.delenv("PEMF_BASE_SHA", raising=False)
    assert path_utils.get_build_id() == _ICERIK12, "kayıt yokken buildId çalışan paketi SÖYLEMİYOR"
    assert path_utils.get_build_id() == path_utils.get_paket_icerigi(), "buildId ile paketIcerigi ÇELİŞİYOR"


@pytest.mark.parametrize("deger", ["", "   ", "kisa", "0123456789a"], ids=["bos", "bosluk", "kisa", "11-hane"])
def test_KRITIK_gecersiz_kayit_degeri_buildIdi_UYDURMAZ_icerige_duser(monkeypatch, tmp_path, deger):
    from utils import path_utils

    _donmus(monkeypatch, tmp_path)
    monkeypatch.setenv("PEMF_BASE_SHA", deger)
    assert path_utils.get_build_id() == _ICERIK12


def test_KARSIT_launcherin_DOGRULADIGI_kayit_AYNEN_sozlesme_55(monkeypatch, tmp_path):
    """Launcher kimliği yalnız kayıt diskteki runtime'la eşleşince geçirir → manifest sha'sı[:12] (CHANGELOG etiketi) AYNEN."""
    from utils import path_utils

    _donmus(monkeypatch, tmp_path)
    monkeypatch.setenv("PEMF_BASE_SHA", "  " + _KAYIT.upper() + "  ")
    assert path_utils.get_build_id() == "13d967121f94"


def test_kaynak_agacindan_kosuda_ne_kayit_ne_icerik_BOS(monkeypatch):
    from utils import path_utils

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(path_utils, "_PAKET_ICERIGI", None)
    monkeypatch.delenv("PEMF_BASE_SHA", raising=False)
    assert path_utils.get_build_id() == ""


def test_KRITIK_api_server_kimligi_get_build_idden_alir_health_iki_alan_AYNI(monkeypatch, tmp_path):
    """`api_server._BUILD_ID` modül yüklenirken `get_build_id()`den gelir; kayıt geçmediğinde health'te iki alan AYNI değeri söyler."""
    import importlib

    from fastapi.testclient import TestClient
    from servers import api_server as api
    from utils import path_utils

    kaynak = Path(api.__file__).read_text(encoding="utf-8")
    assert "_BUILD_ID = get_build_id()" in kaynak, "api_server kimliği get_build_id dışından alıyor"
    _donmus(monkeypatch, tmp_path)
    monkeypatch.delenv("PEMF_BASE_SHA", raising=False)
    monkeypatch.setattr(api, "_BUILD_ID", importlib.import_module("utils.path_utils").get_build_id())
    c = TestClient(api.app, client=("127.0.0.1", 51234))  # test_version_visibility deseni (lifespan YOK)
    j = c.get("/api/health").json()
    assert j["buildId"] == j["paketIcerigi"] == _ICERIK12 == path_utils.get_paket_icerigi()
