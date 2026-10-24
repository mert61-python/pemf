# Author: mertaygn, cglrgrkn
"""D3.09 (B-3.43) — emanetten / elle geri yüklenen KRİTİK anahtar (`sqlcipher_key`, `patient_fernet_key`) dosyada DÜZ bulunursa ilk
okumada makineye bağlı yeniden SARILIR; `docs/VAULT-ANAHTAR-EMANETI.md` "backend ilk açılışta kendi sarar" talimatı gerçek olur.

ÖLÇÜLEN (HEAD): `_dec` öneksiz değeri sarmadan döndürüyor, `get_secret` dosyaya dokunmuyordu → geri yüklenen hasta DB anahtarı
süresiz düz-metin kalıyordu. Düz-metin anahtar değeri DEĞİŞMEZ (aynı değer sarılır — şifreli DB açılmaya devam eder); sarma
düşerse eski davranış (düz değerle sürülür). İzole geçici veri kökü; gerçek kasa / gerçek veri kökü AÇILMAZ; değer basılmaz.
"""

from __future__ import annotations

import json
import secrets

import pytest


@pytest.fixture
def sm(monkeypatch, tmp_path):
    import utils.secrets_manager as s

    monkeypatch.setattr(s, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(s, "_cache", None)
    yield s
    s._cache = None


def _yaz(sm, bolum: str, anahtar: str, deger: str):
    sm.secrets_path().write_text(json.dumps({bolum: {anahtar: deger}}), encoding="utf-8")
    sm._cache = None


@pytest.mark.parametrize("anahtar", ["sqlcipher_key", "patient_fernet_key"])
def test_KRITIK_D3_09_duz_kritik_anahtar_ilk_okumada_SARILIR_deger_AYNI(sm, anahtar):
    duz = secrets.token_hex(32)
    _yaz(sm, "auto", anahtar, duz)
    assert sm.get_secret(anahtar, generate=False) == duz, "geri yüklenen anahtarın DEĞERİ değişti — şifreli DB açılmaz"
    saklanan = json.loads(sm.secrets_path().read_text(encoding="utf-8"))["auto"][anahtar]
    assert saklanan.startswith(("DPAPI:", "MKEY:")), "kritik anahtar dosyada DÜZ-METİN kaldı (sarılmadı)"
    assert duz not in sm.secrets_path().read_text(encoding="utf-8")
    sm._cache = None
    assert sm.get_secret(anahtar, generate=False) == duz, "sarılan değer yeniden okunamadı"


def test_KARSIT_D3_09_kritik_olmayan_sir_DUZ_kalir(sm):
    ad = "api_token"  # operatör düz okur (kritik değil)
    deger = secrets.token_hex(8)  # sabit literal yok — sır tarayıcısı sahte değeri gerçek sanmasın
    _yaz(sm, "auto", ad, deger)
    assert sm.get_secret(ad, generate=False) == deger
    assert json.loads(sm.secrets_path().read_text(encoding="utf-8"))["auto"][ad] == deger


def test_KRITIK_D3_09_sarma_DUSERSE_duz_degerle_SURER_acilis_kirilmaz(sm, monkeypatch):
    duz = secrets.token_hex(32)
    _yaz(sm, "auto", "sqlcipher_key", duz)

    def _dus(*a, **k):
        raise RuntimeError("DPAPI yok (sahte)")

    monkeypatch.setattr(sm, "_enc", _dus)
    assert sm.get_secret("sqlcipher_key", generate=False) == duz
