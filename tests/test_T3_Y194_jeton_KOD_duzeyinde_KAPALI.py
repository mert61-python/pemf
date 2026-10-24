# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T3 · Y194 (sahip, 2026-10-24) — jeton ücretlendirmesi KOD DÜZEYİNDE kapalı: hangi e-postayla girilirse girilsin AI sınırsız.

İSTEK (sahip): "jetonu kapatalım şimdilik, hangi maille girilirse girilsin ai sınırsız çalışabilsin" → "yalnız bu makine değil genel
kodda kapat".
ÖLÇÜLEN (önce, e39a3842): kapı yalnız ortamdan açılıyordu (`JETON_ENFORCED = _flag("PEMF_JETON_ENFORCED", False)`); launcher değeri
kendi ortamından backend'e geçirir (`install.rs` ENV_JETON_ENFORCED) — bu makinede kullanıcı ortamında `1` vardı ve her AI analizi
bakiyeden düşüyordu. Kod varsayılanı kapalıydı ama herhangi bir makinede `PEMF_JETON_ENFORCED=1` jetonu açabiliyordu.
KAPI: `JETON_SAHIP_ACIK = False` iken ortam `1` olsa da kapı tam no-op (karar yok, bakiye rozeti `etkin: false`); KARŞIT: ücretlendirme
mantığı SİLİNMEDİ — anahtar açılınca (testte doğrudan) kimliksiz analiz yine 402 alır.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture()
def jeton_ortam_acik(tmp_path, monkeypatch):
    """Ortamda zorlama AÇIK (`1`) — bu makinede ölçülen durum; test sonunda modül temiz ortamla yeniden yüklenir."""
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PEMF_JETON_ENFORCED", "1")
    import servers.jeton as j

    importlib.reload(j)
    yield j
    monkeypatch.delenv("PEMF_JETON_ENFORCED", raising=False)
    importlib.reload(j)


def _istek(yol: str, token: str | None = None):
    return SimpleNamespace(url=SimpleNamespace(path=yol), headers={"authorization": f"Bearer {token}"} if token else {})


def test_KRITIK_ortam_1_olsa_da_jeton_KAPALI_sahip_anahtari_tek_yerde(jeton_ortam_acik):
    j = jeton_ortam_acik
    assert j.JETON_SAHIP_ACIK is False, "sahip kararı Y194: jeton KOD düzeyinde kapalı"
    assert j.JETON_ENFORCED is False, "ortamdaki PEMF_JETON_ENFORCED=1 jetonu AÇTI (kod düzeyinde kapalı olmalı)"


def test_KRITIK_kimliksiz_ve_kimlikli_AI_analizi_UCRETSIZ_bakiye_rozeti_gizli(jeton_ortam_acik):
    j = jeton_ortam_acik
    for yol in ("/api/ai/disease", "/api/ai/vision/em_petri", "/api/ai/vision/thermal"):
        assert j._jeton_on_karari(_istek(yol)) is None, f"{yol}: kimliksiz analiz kapıya takıldı"
        assert j._jeton_on_karari(_istek(yol, "eyJhbGciOiJIUzI1NiJ9.e30.imza")) is None, (
            f"{yol}: analiz ücretlendirildi"
        )
    assert j.bakiye_ozeti(_istek("/api/jeton/bakiye")) == {"etkin": False}


def test_KARSIT_ucretlendirme_mantigi_DURUYOR_anahtar_acilinca_kimliksiz_analiz_402(jeton_ortam_acik, monkeypatch):
    j = jeton_ortam_acik
    monkeypatch.setattr(j, "JETON_ENFORCED", True)  # ileride satış açılırsa: `JETON_SAHIP_ACIK = True` + ortam
    with pytest.raises(HTTPException) as e:
        j._jeton_on_karari(_istek("/api/ai/disease"))
    assert e.value.status_code == 402
