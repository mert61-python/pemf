# -*- coding: utf-8 -*-
"""KP-2 · apps/backend/servers/auth.py `kimlik_db_okunamiyor` + apps/backend/utils/secrets_manager.py `_cihaz_kimlik_deposu` · sözleşmeler:

- `kimlik_db_okunamiyor`: istek bağlamında karar yoksa kimlik DB'sinde KATI okuma dener (`list_operators(kati=True)`); okuma başarılıysa
  False, istisna atarsa True (ASLA istisna sızdırmaz); bağlamda karar varsa DB'ye gitmeden onu döner. (KP-1 kalan `auth.py:509` — SBE tam
  süitinde başka bir testin ortamına bağlı koşuyordu; burada kendi sözleşmesiyle sabitlendi.)
- `_cihaz_kimlik_deposu` Windows kolu (`:428-429`, A4'te "test edilebilir" diye etiketsiz bırakıldı): yönlendirme (`PEMF_DEVICE_IDENTITY_DIR`)
  yoksa depo `%PROGRAMDATA%\\PEMF_System` olur ve oluşturulur.

Sahte EN ALT katta: kimlik DB'si nesnesi (`get_auth_db` dönüşü — çağrı argümanları kaydedilir); `PROGRAMDATA` YALNIZ tmp'ye yönlendirilir
(gerçek `C:\\ProgramData` hiçbir kolda açılmaz).
"""

from __future__ import annotations

import contextvars
import os

import pytest
from servers import auth


class _KimlikDb:
    def __init__(self, hata: Exception | None = None):
        self.hata = hata
        self.cagri: list = []

    def list_operators(self, **k):
        self.cagri.append(k)
        if self.hata:
            raise self.hata
        return []


def _bagsiz(fn):
    """İstek bağlamı TAZE (karar yok) — başka testin bağlam değişkeni sızmaz."""
    ctx = contextvars.copy_context()

    def _kos():
        auth._KIMLIK_DB_ARIZASI.set(None)
        return fn()

    return ctx.run(_kos)


def test_kimlik_db_okunamiyor_BAGLAMSIZ_kati_okuma_BASARILIYSA_False(monkeypatch):
    """Bağlamda karar yok + katı okuma başarılı → False; DB'ye `kati=True` ile TEK çağrı."""
    import database.auth_db as adb

    db = _KimlikDb()
    monkeypatch.setattr(adb, "get_auth_db", lambda: db)
    assert _bagsiz(auth.kimlik_db_okunamiyor) is False
    assert db.cagri == [{"kati": True}]


def test_kimlik_db_okunamiyor_BAGLAMSIZ_kati_okuma_DUSERSE_True_istisna_SIZMAZ(monkeypatch):
    """Bağlamda karar yok + katı okuma istisna atar → True (fail-closed yorumu), istisna dışarı çıkmaz."""
    import database.auth_db as adb

    db = _KimlikDb(hata=RuntimeError("file is not a database"))
    monkeypatch.setattr(adb, "get_auth_db", lambda: db)
    assert _bagsiz(auth.kimlik_db_okunamiyor) is True
    assert db.cagri == [{"kati": True}]


def test_kimlik_db_okunamiyor_BAGLAMDA_karar_varsa_DB_ye_GITMEZ(monkeypatch):
    """Bağlamda karar (True / False) varsa onu döner; DB çağrısı YOK."""
    import database.auth_db as adb

    db = _KimlikDb()
    monkeypatch.setattr(adb, "get_auth_db", lambda: db)
    for karar in (True, False):
        ctx = contextvars.copy_context()

        def _kos(k=karar):
            auth._KIMLIK_DB_ARIZASI.set(k)
            return auth.kimlik_db_okunamiyor()

        assert ctx.run(_kos) is karar
    assert db.cagri == []


@pytest.mark.skipif(os.name != "nt", reason="Windows makine deposu kolu (Linux / macOS kolu PLATFORM etiketli)")
def test_cihaz_kimlik_deposu_WINDOWS_yonlendirme_yoksa_PROGRAMDATA_PEMF_System_olusturulur(monkeypatch, tmp_path):
    """`PEMF_DEVICE_IDENTITY_DIR` yok + Windows → `%PROGRAMDATA%\\PEMF_System` (tmp'deki sahte PROGRAMDATA) döner ve dizin oluşturulur."""
    from utils import secrets_manager as sm

    sahte_pd = tmp_path / "ProgramData"
    monkeypatch.delenv("PEMF_DEVICE_IDENTITY_DIR", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(sahte_pd))
    d = sm._cihaz_kimlik_deposu()
    assert d == sahte_pd / "PEMF_System"
    assert d.is_dir()


def test_cihaz_kimlik_deposu_YONLENDIRME_varsa_o_dizin_olusturulur(monkeypatch, tmp_path):
    """`PEMF_DEVICE_IDENTITY_DIR` (boşluklu) verilmişse kırpılır, o dizin döner ve oluşturulur (platformdan bağımsız)."""
    from utils import secrets_manager as sm

    hedef = tmp_path / "kimlik" / "alt"
    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", f"  {hedef}  ")
    d = sm._cihaz_kimlik_deposu()
    assert d == hedef
    assert d.is_dir()
