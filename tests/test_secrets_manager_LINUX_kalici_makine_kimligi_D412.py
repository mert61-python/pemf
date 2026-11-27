# -*- coding: utf-8 -*-
"""D4.12 (B-3.49) + 4B-1.6 — `secrets_manager` Linux dalı: kritik sır KALICI makine kimliğiyle sarılır, kimlik yoksa fail-closed,
kimlik değişince ileti DOĞRU kurtarma yolunu söyler.

`secrets_manager` Linux'ta kritik anahtarları (`sqlcipher_key`, `patient_fernet_key`) makine kimliğinden (`MAKINE_KIMLIGI_YOLLARI`:
`/etc/machine-id`, `/var/lib/dbus/machine-id` — ilk DOLU olan) türetilen anahtarla sarar (`MKEY:`); kimlik yoksa `critical=True` →
RuntimeError (fail-closed). Kimlik değişirse (birim / dosya kayboldu) depolanmış sır çözülemez → yeni anahtar ÜRETİLMEZ, ileti kimlik
dosyasını geri yüklemeyi söyler (`pemf_secrets.json`'u geri yüklemek ÇÖZMEZ — aynı kimlikle sarılı).

Y344 (sahip 27-11, istem 66 CT2 f3): Docker dağıtımı emekli — bu dosya `test_docker_KALICI_makine_kimligi_D412.py` (+ 4B-1.6
`test_docker_KIMLIK_birimi_belgede_ve_iletide_4B16.py`) idi; giriş betiği / Dockerfile / compose / DOCKER_README kolları dosyalarla
birlikte kaldırıldı (git geçmişinde). Kalan kollar ÜRÜN kodunu (`utils/secrets_manager.py` Linux dalı) ölçer — kimlik dosyası artık
giriş betiği yerine testin kendisi tarafından yazılır.
"""

from __future__ import annotations

import json
import re
import secrets

import pytest


@pytest.fixture
def linux_sm(monkeypatch, tmp_path):
    """Linux dalındaki GERÇEK SecretsManager; makine kimliği yalnız testin verdiği yollardan okunur."""
    from utils import file_acl
    from utils import secrets_manager as sm

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: True)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(sm, "_is_windows", lambda: False)
    sm._cache = None
    yield sm
    sm._cache = None


def test_KRITIK_ikinci_yoldaki_KALICI_kimlik_kritik_siri_sarar_ve_yeniden_acilista_AYNI_cozer_B3_49(
    linux_sm, monkeypatch, tmp_path
):
    sm = linux_sm
    assert "/var/lib/dbus/machine-id" in sm.MAKINE_KIMLIGI_YOLLARI, (
        "çapa: ikinci kimlik kaynağı (kalıcı dizin) okunmuyor"
    )
    kimlik = tmp_path / "kalici" / "machine-id"
    kimlik.parent.mkdir()
    kimlik.write_text(secrets.token_hex(16) + "\n", encoding="utf-8")
    # İlk kaynak (/etc/machine-id) YOK — kimlik yalnız ikinci (kalıcı) yoldan okunmalı.
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "etc_machine-id_YOK"), str(kimlik)))
    assert re.fullmatch(r"[0-9a-f]{32}", kimlik.read_text(encoding="utf-8").strip())

    v1 = sm.get_secret("sqlcipher_key")
    assert v1, "kritik sır üretilmedi"
    sakli = json.loads(sm.secrets_path().read_text(encoding="utf-8"))["auto"]["sqlcipher_key"]
    assert sakli.startswith(sm._MKEY_PREFIX), "kritik sır makineye-bağlı sarılmadı (düz-metin?)"

    # Yeniden açılış: kimlik dosyası kalır → sır AYNI çözülür.
    sm._cache = None
    assert sm.get_secret("sqlcipher_key") == v1, "yeniden açılışta kritik sır FARKLI döndü"


def test_KARSIT_kimlik_YOKKEN_fail_closed_KORUNUR(linux_sm, monkeypatch, tmp_path):
    sm = linux_sm
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok1"), str(tmp_path / "yok2")))
    with pytest.raises(RuntimeError):
        sm.get_secret("sqlcipher_key")
    assert not sm.secrets_path().exists() or "sqlcipher_key" not in sm.secrets_path().read_text(encoding="utf-8"), (
        "kimlik yokken kritik anahtar diske YAZILDI (fail-closed delindi)"
    )


def test_KRITIK_kimlik_degisince_ileti_DOGRU_kurtarma_yolunu_soyler(linux_sm, monkeypatch, tmp_path):
    sm = linux_sm
    a, b = tmp_path / "A" / "machine-id", tmp_path / "B" / "machine-id"
    for p, c in ((a, "a"), (b, "b")):
        p.parent.mkdir()
        p.write_text(c * 32, encoding="utf-8")
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok"), str(a)))
    sm.get_secret("sqlcipher_key")
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok"), str(b)))  # kimlik dosyası değişti
    sm._cache = None
    with pytest.raises(RuntimeError) as e:
        sm.get_secret("sqlcipher_key")
    ileti = str(e.value)
    assert "ÜRETİLMEDİ" in ileti, "fail-closed ileti değişti (aparat)"
    assert "/var/lib/dbus" in ileti or "kimlik birim" in ileti.lower(), (
        f"Linux'ta kimlik değişince ileti kimlik dosyasını geri yüklemeyi söylemiyor; yalnız: {ileti[-160:]!r}"
    )
