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
    """🔴 Mekanizma yazilip baglanmazsa sessiz no-op'tur (bu depoda jetonla yasandi)."""
    i = main_rs.find("flow::guncellemeyi_onayla(&root2, &geri)")
    assert i > 0, "onaylama dali bulunamadi — main.rs bicimi degismis olabilir"
    blok = main_rs[max(0, i - 1200) : i]
    assert "db_hazir_mi" in blok, (
        "guncelleme ONAYLANMADAN once `dbReady` OKUNMUYOR — DB'yi bozan bir yayin 'saglikli' "
        "sayilip onaylanir, runtime.old SILINIR ve klinik hicbir seans acamaz (bulgu C5)"
    )


def test_KRITIK_dbReady_FALSE_ise_GERI_ALINIR(main_rs):
    i = main_rs.find("db_hazir_mi")
    assert i > 0, "db_hazir_mi cagrisi yok"
    blok = main_rs[i : i + 900]
    assert "Some(false)" in blok, (
        "yalniz `false` degeri geri almayi tetiklemeli — `None` (bilinmiyor) tetiklerse eski "
        "backend'lere guncelleme HIC uygulanamaz"
    )
    assert "guncellemeyi_geri_al" in blok, "dbReady=false oldugunda guncelleme GERI ALINMIYOR"


def test_KRITIK_operatore_SEBEP_soylenir(main_rs):
    """Sessizce geri almak, sebebi anlasilmaz bir 'guncelleme basarisiz'a cevirir."""
    i = main_rs.find("db_hazir_mi")
    blok = main_rs[i : i + 900]
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
