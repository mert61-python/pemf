# -*- coding: utf-8 -*-
"""2-A İNCELEME A2-1.2 (D2.45 · Karar 6 "TÜM anahtar yollarında" · Y9) — ALAN ANAHTARI (patient_fernet_key) İÇİN
ESKİ YOL YOK, YENİ ANAHTAR YOK.

D2.45 at-rest anahtarının (`sqlcipher_key`) eski yolunu sildi; hasta alanlarını şifreleyen `patient_fernet_key`in yolu
(`pemf_gui/config.py::_get_or_create_key`) aynı deseni taşıyordu: SecretsManager'ın `RuntimeError` OLMAYAN her hatası
(sır dizinine erişilemiyor — ikinci Windows hesabı; ilk kalıcılaştırma bir kez düştü) → keyring → `.pemf_key_v2` →
YOKSA YENİ Fernet anahtarı üretip keyring'e (GERÇEK Windows kimlik kasası) ya da dosyaya yazıyordu.
ÖLÇÜLEN (inceleme sondası, gerçek `main()`, veri kökü başka SID'e kilitli): `keyring.set_password('PEMF_GUI',
'patient_fernet_key')` çağrıldı. Kasa yazımı düşerse (yok/null) anahtar YALNIZ bellekte kalır: o süreçte şifrelenen
hasta alanları yeniden başlatmada ÇÖZÜLEMEZ (bu dosyanın 2. testi, null kasa).

SÖZLEŞME: SecretsManager'ın HER hatası fail-closed `RuntimeError` (neden ERROR ile); eski kaynakları (keyring,
`.pemf_key_v2`) SecretsManager'ın `legacy` göçü zaten okur. Sahte EN ALT katta: `Path.exists` (kilitli sır dizini),
`os.replace` (sır dosyasının kalıcılaştırılması), keyring modül işlevleri (KAYITÇI — gerçek kasaya gidilmez)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest


@pytest.fixture
def sm(monkeypatch):
    from utils import file_acl
    from utils import secrets_manager as _sm

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: True)
    _sm._cache = None
    yield _sm
    _sm._cache = None


@pytest.fixture
def kasa(monkeypatch):
    """Keyring modül işlevleri KAYITÇI (servis, ad) — DEĞER saklanmaz/okunmaz; okuma hep boş (yeni kasa)."""
    import keyring

    yazilan = []
    monkeypatch.setattr(keyring, "get_password", lambda *a, **k: None)
    monkeypatch.setattr(keyring, "set_password", lambda s, n, v: yazilan.append((s, n)))
    return yazilan


def _cfg(tmp_path: Path):
    from pemf_gui.config import ConfigManager

    return ConfigManager(config_file=str(tmp_path / "cfg" / "config.json"))


def test_KRITIK_A12_sir_dizini_OKUNAMAZSA_yeni_Fernet_anahtari_URETILMEZ_kasaya_YAZILMAZ(
    sm, kasa, tmp_path, monkeypatch, caplog
):
    """MUTASYON: `_get_or_create_key`e `except Exception → eski yol (keyring → .pemf_key_v2 → üret)` dalını geri
    koymak → KIRMIZI (yeni anahtar kasaya yazılır, fail-closed yok)."""
    sir = os.path.normcase(os.path.abspath(str(sm.secrets_path())))
    gercek_exists = Path.exists

    def _exists(self, *a, **k):
        if os.path.normcase(os.path.abspath(str(self))) == sir:
            raise PermissionError(13, "Erisim engellendi (taklit: veri koku baska Windows hesabina kilitli)", str(self))
        return gercek_exists(self, *a, **k)

    monkeypatch.setattr(Path, "exists", _exists)
    cfg = _cfg(tmp_path)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        cfg._anahtar_hazirla()
    assert kasa == [], f"sır okunamazken YENİ alan anahtarı kimlik kasasına yazıldı: {kasa}"
    assert not list(tmp_path.rglob(".pemf_key_v2")), "sır okunamazken YENİ alan anahtarı dosyaya yazıldı"
    assert "Yeni RASTGELE Fernet" not in caplog.text
    assert "OKUNAMADI/YAZILAMADI" in caplog.text and "PermissionError" in caplog.text, (
        f"fail-closed nedeni günlükte YOK:\n{caplog.text[-1200:]}"
    )


def _kalicilastirmayi_bir_kez_dusur(monkeypatch, sir: Path) -> dict:
    gercek = os.replace
    durum = {"dustu": 0}
    hedef = os.path.normcase(os.path.abspath(str(sir)))

    def _replace(src, dst, *a, **k):
        if durum["dustu"] == 0 and os.path.normcase(os.path.abspath(str(dst))) == hedef:
            if (json.loads(Path(src).read_text(encoding="utf-8")).get("auto") or {}).get("patient_fernet_key"):
                durum["dustu"] += 1
                raise PermissionError(13, "Erisim engellendi (taklit: AV/ACL sir dosyasini tuttu)")
        return gercek(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", _replace)
    return durum


def test_KRITIK_A12_ilk_alan_anahtari_DISKE_yazilamazsa_sifrelenen_alan_YENIDEN_BASLATMADA_cozulur(
    sm, kasa, tmp_path, monkeypatch
):
    """B-3.5'in alan-anahtarı ikizi (kasa yazımı da yoksa): ilk `patient_fernet_key` kalıcılaştırması bir kez düşer.
    Eskiden eski yol bellekte YENİ anahtar üretiyordu; o süreçte şifrelenen alan yeniden başlatmada ÇÖZÜLEMİYORDU.
    Şimdi ilk deneme fail-closed (hiçbir şey şifrelenmez), sonraki deneme (Y43) anahtarı DİSKE yazar, şifreler; yeniden
    başlatmada aynı anahtar çözer."""
    monkeypatch.setattr("keyring.set_password", lambda *a, **k: None)  # kasa "yazdım" der ama saklamaz (null)
    durum = _kalicilastirmayi_bir_kez_dusur(monkeypatch, sm.secrets_path())
    cfg = _cfg(tmp_path)
    sifreli = None
    for _ in range(2):  # açılış + arka plan yeniden denemesi
        try:
            sifreli = cfg._encrypt_value("A12Hasta")
            break
        except RuntimeError:
            continue
    assert durum["dustu"] == 1, "ön koşul: ilk alan anahtarı kalıcılaştırması düşürülmeli"
    assert sifreli, "ikinci denemede de alan şifrelenemedi"
    sm._cache = None  # yeniden başlatma
    cfg2 = _cfg(tmp_path / "yeniden")
    assert cfg2._decrypt_value(sifreli) == "A12Hasta", (
        "hasta alanı yeniden başlatmada ÇÖZÜLEMEDİ — DİSKE yazılmamış bir anahtarla şifrelenmişti (eski yol)"
    )
