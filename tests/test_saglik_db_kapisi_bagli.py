# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SAGLIK KAPISI 'CIHAZ SEANS ACABILIYOR MU'YU DA OLCER (denetim 2026-08-23, bulgu C5).

OLCULEN DURUM: `wait_for_health` = HTTP 200 + `launcherNonce`. Backend AYNI yanitta `dbReady`
alanini da yayinliyor ve `/api/session/start` tam ona bakip 503 donuyor
(`api_server::_kayit_db_hazir`). Yani deps katmaninda DB tarafini bozan bir yayinda (ya da
basarisiz bir sema gocunde): backend acilir, /api/health 200 doner, launcher "saglikli" der,
sha KAYDEDILIR ve **`runtime.old` SILINIR**. Klinik artik HICBIR seans baslatamaz (503) ve
otomatik geri donus yolu kalmamistir — tek care kullanicinin elle "Onar"a basmasidir; o da ayni
bozuk paketi yeniden kurar.

⚠️ COZUM `wait_for_health`E KAPI EKLEMEK DEGILDIR — hakemlerden biri bunu hakli olarak reddetti
ve backend'in kendi yorumu da ayni seyi soyluyor: "Sagligin kendisini DUSURMEZ: backend ayakta ve
acil durdurma yolu calisiyor." DB bozukken bile E-STOP CALISMALIDIR; sagligi dusurmek onu da
dusururdu. Bu yuzden olcum AYRI bir fonksiyonda (`backend::db_hazir_mi`) ve YALNIZ guncellemeyi
ONAYLAMA kararinda kullaniliyor.

SOZLESME:
  1. Guncelleme onaylanmadan ONCE `dbReady` okunur.
  2. `false` ise guncelleme GERI ALINIR (yayin basarisiz sayilir) — cihaz ayakta ama seans
     acamiyorsa o yayin ise yaramamistir.
  3. BILINMIYORSA (eski backend / govde okunamadi) guncelleme NORMAL onaylanir — bilinmeyeni
     "bozuk" saymak sahadaki eski surumleri guncellenemez yapardi.
  4. `wait_for_health` DEGISMEZ: acil durdurma yolu hicbir kosulda dusurulmez.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from launcher_onay_karari import db_kapisi_denetle, onay_sirasi_denetle

_KOK = Path(__file__).resolve().parents[1]
_MAIN = _KOK / "launcher" / "app" / "src" / "main.rs"
_BACKEND = _KOK / "launcher" / "core" / "src" / "backend.rs"


@pytest.fixture(scope="module")
def main_rs() -> str:
    return _MAIN.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def backend_rs() -> str:
    return _BACKEND.read_text(encoding="utf-8", errors="replace")


def test_KRITIK_onaylamadan_ONCE_dbReady_okunur(main_rs):
    """🔴 Mekanizma yazilip baglanmazsa sessiz no-op'tur (bu depoda jetonla yasandi).

    ⚠️ D1.35 (B-10.47): eskiden onayin 1200 karakter oncesinde `db_hazir_mi` ADINI ariyordu —
    `if backend::db_hazir_mi(port) == Some(false) && false {` mutantinda YESIL kaliyordu. Artik
    yorumu soyulmus main.rs'te start_backend Ok kolunun UST DUZEYINDE tam kosul ifadesi, onayin o
    dalin DISINDA ve SONRASINDA oldugu aranir (`tests/launcher_onay_karari.py`)."""
    onay_sirasi_denetle(main_rs)


def test_KRITIK_dbReady_FALSE_ise_GERI_ALINIR(main_rs):
    """Yalniz `Some(false)` geri alir (`None` = bilinmiyor → onay); dal E-stop'lu sokum, deneme
    sayaci, geri alma ve GeriAlindi donusunu UST DUZEYDE tasir (D1.35)."""
    db_kapisi_denetle(main_rs)


def test_KRITIK_operatore_SEBEP_soylenir(main_rs):
    """Sessizce geri almak, sebebi anlasilmaz bir 'guncelleme basarisiz'a cevirir.

    D1.35: sebep metni dbReady=false DALININ ICINDE aranir (dosyadaki baska bir yerde degil)."""
    k, _ok, (if_bas, if_son) = db_kapisi_denetle(main_rs)
    blok = k.soy[if_bas:if_son]
    assert re.search(r"(seans|kayıt|kayit|veritaban)", blok, re.IGNORECASE), (
        "geri alma sebebi operatore anlasilir bicimde soylenmiyor (metinde seans/kayit gecmiyor)"
    )


def test_KRITIK_wait_for_health_DEGISMEDI_karsit_kanit(backend_rs):
    """⚠️ PAZARLIK EDILEMEZ: `dbReady` saglik kapisina EKLENMEZ.

    Backend'in kendi gerekcesi: "Sagligin kendisini DUSURMEZ: backend ayakta ve acil durdurma
    yolu calisiyor." DB bozukken bile E-stop calismali; sagligi dusurmek acil durdurma yolunu da
    dusururdu (kapanista `POST /api/hardware/emergency_stop` saglikli backend'e gider).
    """
    m = re.search(r"pub fn wait_for_health\(.*?\n\}", backend_rs, re.S)
    assert m, "wait_for_health bulunamadi"
    assert "dbReady" not in m.group(0) and "db_hazir" not in m.group(0), (
        "`dbReady` saglik kapisina eklenmis — DB arizasinda backend 'sagliksiz' sayilir ve "
        "ACIL DURDURMA yolu dusurulur (backend'in belgeli karari ihlal edildi)"
    )


def test_KARSIT_KANIT_bilinmiyorsa_guncelleme_DURMAZ(backend_rs):
    """Eski backend'ler alani yansitmaz; `None` donmeli ve cagiran normal onaylamali."""
    m = re.search(r"pub fn db_hazir_govdeden\(.*?\n\}", backend_rs, re.S)
    assert m, "db_hazir_govdeden bulunamadi"
    g = m.group(0)
    assert "Option<bool>" in g, "fonksiyon 'bilinmiyor' durumunu tasiyamiyor (Option degil)"
    # `?` operatoru alan yoksa None dondurur; `unwrap_or(false)` OLMAMALI.
    assert "unwrap_or(false)" not in g, (
        "alan yokken `false` varsayiliyor — eski backend'lerde her guncelleme geri alinir"
    )


def launcher_db_alani(backend_rs_kaynak: str) -> list[str]:
    """`db_hazir_govdeden` gövdesinde (yorumsuz) okunan JSON alan adları."""
    from rs_soyucu import blok_sonu, rs_soy

    soy, maske = rs_soy(backend_rs_kaynak), rs_soy(backend_rs_kaynak, dizeleri_bosalt=True)
    m = re.search(r"\bfn\s+db_hazir_govdeden\s*\([^)]*\)[^{]*\{", soy)
    assert m, "launcher `db_hazir_govdeden` (yorum dışı) bulunamadı"
    govde = soy[m.end() : blok_sonu(maske, m.end() - 1)]
    return re.findall(r'\.get\(\s*"([^"]+)"\s*\)', govde)


def test_KRITIK_launcher_okudugu_ALAN_backend_saglik_yanitinda_VAR(backend_rs):
    """1-B bağımsız inceleme (i2): zincirin iki ucu ayrı dilde — launcher `.get("dbReady")` bir harf değişse
    (`db_ready`) sonuç hep `None` olur ve launcher bilinmeyeni ONAYLAR (DB'yi bozan yayın onaylanır); Rust testi
    cargo koşmadığı için (B-8.7 → D5.41) Python'da 181 test yeşil kalıyordu. Alan adı GERÇEK sağlık yanıtından."""
    import servers.api_server as api
    from fastapi.testclient import TestClient

    alanlar = launcher_db_alani(backend_rs)
    assert len(alanlar) == 1, f"launcher dbReady okuyucusu {alanlar}"
    yanit = TestClient(api.app).get("/api/health").json()
    assert alanlar[0] in yanit and isinstance(yanit[alanlar[0]], bool), (
        f"launcher `{alanlar[0]}` okuyor ama backend sağlık yanıtında bool olarak YOK: {sorted(yanit)}"
    )


def test_ARAC_alan_cikarici_MUTANTI_gorur(backend_rs):
    assert launcher_db_alani(backend_rs.replace('.get("dbReady")', '.get("db_ready")')) == ["db_ready"]
