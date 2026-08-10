# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SÜRÜM GÖRÜNÜRLÜĞÜ — "hangi sürüm koşuyor?" doğru cevaplanmalı (2026-08-09 denetimi, Tier 3).

ARIZA: `X-API-Version`, FastAPI `/docs` ve keşif yanıtları sahaya **1.4.1** diyordu. O sayı
`frontendOta` kanalının sürümüdür (`frontend_version.json`); backend'in sürümü `VERSION` =
**1.9.5**. `utils.path_utils.get_app_version()` yanlış kanalı ÖNCE okuyordu — oysa
`update_manager._version_paths()` doğrusunu yapıyordu; iki yer ayrışmıştı.

Neden önemli: sürüm sessiz-otomatik güncellenen bir tıbbi cihazda olay teşhisinin ilk verisidir.
Yanlışsa destek altı sürüm geriye bakar, düzeltilmiş bir hatayı yeniden arar.

Ayrıca `buildId`: aynı sürüm numarası farklı paket içeriği çalıştırabilir (yeniden yayın, yarım
güncelleme, elle kopyalanan dosya). Launcher kurduğu paketin sha'sını `PEMF_BASE_SHA` ile
geçirir; kısaltılmışı "hangi ikili" sorusunu tek başına cevaplar.
"""

import json
import os
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


def _temiz_surum():
    """Cache'lenmiş sürümü sıfırla — sıra testleri gerçek okumayı görmeli."""
    from utils import path_utils

    path_utils._APP_VERSION = None


# ── doğru kanal ─────────────────────────────────────────────────────────────


def test_KRITIK_surum_BACKEND_kanalindan_okunur():
    _temiz_surum()
    from utils.path_utils import get_app_version

    beklenen = (KOK / "VERSION").read_text(encoding="utf-8").strip()
    assert get_app_version() == beklenen, "app surumu VERSION (backend kanali) yerine baska kanaldan okunuyor"


def test_KRITIK_frontendOta_surumu_app_surumu_SANILMAZ():
    _temiz_surum()
    from utils.path_utils import get_app_version

    fo = str(json.loads((KOK / "frontend_version.json").read_text(encoding="utf-8"))["version"])
    v = get_app_version()
    if fo != (KOK / "VERSION").read_text(encoding="utf-8").strip():
        assert v != fo, f"app surumu frontendOta kanalindan ({fo}) okunuyor"


def test_iki_surum_kaynagi_AYRISMAZ():
    """`path_utils` ile `update_manager` aynı cevabı vermeli — ayrışma bu arızanın kökeniydi."""
    _temiz_surum()
    from servers.update_manager import get_current_version
    from utils.path_utils import get_app_version

    assert get_app_version() == get_current_version(), "path_utils ve update_manager farkli surum raporluyor"


def test_VERSION_dosyasi_yoksa_frontend_version_a_DUSER(tmp_path, monkeypatch):
    """Geriye uyum: eski paketlerde `VERSION` bundle'lanmamış olabilir."""
    from utils import path_utils

    _temiz_surum()
    monkeypatch.setattr(path_utils, "packaged_resource_path", lambda *p: tmp_path / "yok")
    monkeypatch.setattr(Path, "read_text", Path.read_text)  # gerçek okuma korunur
    # gerçek depo kökündeki VERSION'ı gizle
    gercek = Path.exists

    def sahte_exists(self):
        return False if self.name == "VERSION" else gercek(self)

    monkeypatch.setattr(Path, "exists", sahte_exists)
    v = path_utils.get_app_version()
    _temiz_surum()
    assert v, "VERSION yokken hicbir surum uretilmedi"


# ── HTTP yüzeyi ─────────────────────────────────────────────────────────────


def test_X_API_Version_headeri_DOGRU(client):
    r = client.get("/api/health")
    beklenen = (KOK / "VERSION").read_text(encoding="utf-8").strip()
    assert r.headers.get("X-API-Version") == beklenen, (
        f"X-API-Version yanlis: {r.headers.get('X-API-Version')} != {beklenen}"
    )


def test_health_SURUMU_bildirir(client):
    g = client.get("/api/health").json()
    assert g.get("version"), "health surumu hic bildirmiyor — teshisin ilk verisi eksik"
    assert g["version"] == (KOK / "VERSION").read_text(encoding="utf-8").strip()


# ── buildId ─────────────────────────────────────────────────────────────────


def test_buildId_launcher_sha_sindan_TURER(monkeypatch):
    from utils import path_utils

    monkeypatch.setenv("PEMF_BASE_SHA", "ABCDEF0123456789" + "0" * 48)
    assert path_utils.get_build_id() == "abcdef012345"


def test_KRITIK_buildId_UYDURULMAZ(monkeypatch):
    """Launcher'sız çalıştırmada sahte bir kimlik üretmek, olay kaydını yanlış yönlendirir."""
    from utils import path_utils

    monkeypatch.delenv("PEMF_BASE_SHA", raising=False)
    assert path_utils.get_build_id() == ""
    monkeypatch.setenv("PEMF_BASE_SHA", "kisa")
    assert path_utils.get_build_id() == "", "gecersiz sha'dan kimlik uretildi"


def test_buildId_yokken_header_EKLENMEZ(client):
    """Boş bir `X-Build-Id` "kimlik yok" değil "kimlik boş" diye okunur."""
    from servers import api_server

    if api_server._BUILD_ID:
        pytest.skip("bu ortamda PEMF_BASE_SHA tanimli")
    assert "X-Build-Id" not in client.get("/api/health").headers


# ── CHANGELOG kapısı ────────────────────────────────────────────────────────


def test_KRITIK_CHANGELOG_guncel_surumleri_ICERIR():
    """Sessiz otomatik güncellenen bir cihazda "ne değişti" cevapsız kalmamalı: sürüm
    yükseltmek CHANGELOG'a dokunmayı ZORUNLU kılar."""
    ch = KOK / "CHANGELOG.md"
    assert ch.exists(), "CHANGELOG.md yok"
    metin = ch.read_text(encoding="utf-8")
    v = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))
    eksik = [
        f"{ad}={s}"
        for ad, s in (
            ("launcher", v["launcher"]),
            ("mobile", v["mobile"]["name"]),
            ("backend", v["backend"]),
        )
        if s not in metin
    ]
    assert not eksik, (
        f"versions.json'daki surum(ler) CHANGELOG'da gecmiyor: {eksik} — "
        "surum yukseltildiyse degisiklik kaydi da yazilmali."
    )


def test_CHANGELOG_yayindaki_paket_shasini_ICERIR():
    """`buildId` sahadan `90cf004f9fa1` gelince karşılığı burada bulunabilmeli."""
    man = KOK / "pemf-app-packages" / "manifest.json"
    if not man.exists():
        pytest.skip("manifest yok")
    m = json.loads(man.read_text(encoding="utf-8"))
    sha = (m.get("base") or {}).get("sha256", "")
    if not sha:
        pytest.skip("manifest'te base sha yok")
    metin = (KOK / "CHANGELOG.md").read_text(encoding="utf-8")
    assert sha[:12] in metin, (
        f"yayindaki paketin kimligi ({sha[:12]}) CHANGELOG'da yok — sahadan gelen buildId hicbir kayitla eslesmez"
    )
