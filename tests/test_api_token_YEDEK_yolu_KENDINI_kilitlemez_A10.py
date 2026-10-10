# -*- coding: utf-8 -*-
"""2-E incelemesi A-10 — `auth.get_api_token` yedek yolu (sır deposu düşmüşken) token dosyasını süreci çalıştıran hesaptan KİLİTLEMEZ.

ÖLÇÜLEN KUSUR: yedek yol `api_token.txt`'yi yazdıktan sonra `lock_down_file(f)` (varsayılan `keep_current_user=False`) ile YALNIZ SYSTEM +
Administrators'a kilitliyordu. Yükseltilmemiş süreç (Kural 2: başlatıcının kullanıcı-başına backend'i) yeniden başlayınca kendi dosyasını
OKUYAMIYOR, istisna dalı her açılışta YENİ rastgele token üretiyordu (diske de yazılamaz) → eşleşmiş istemcilerin token'ı her yeniden
başlatmada geçersiz. Düzeltme: `keep_current_user=True` (sürekli açılan sır dosyalarının kuralı — D2.79 / DENETİM P3). Yerel `Users` yine ERİŞEMEZ.
GERÇEK: `get_api_token` yedek yolu, gerçek `icacls` (testin kendi tmp dosyası); "yeniden başlatma" = süreç önbelleği (`_token`) sıfırlanır.
Tetik: sır deposu (`get_secret`) istisna atar — yedek yolun tek giriş koşulu.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="NTFS ACL davranışı")


def _yukseltilmis_mi() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    from servers import auth
    from utils import secrets_manager

    if _yukseltilmis_mi():
        pytest.skip("süreç YÜKSELTİLMİŞ — Administrators ACE okumaya izin verir, kendini kilitleme ölçülemez")
    dosya = tmp_path / "api_token.txt"
    monkeypatch.delenv("PEMF_API_TOKEN", raising=False)
    monkeypatch.setattr(auth, "_token", None)
    monkeypatch.setattr(auth, "_token_file", lambda: dosya)

    def _depo_yok(*a, **k):
        raise RuntimeError("sir deposu okunamadi (aparat)")

    monkeypatch.setattr(secrets_manager, "get_secret", _depo_yok)
    try:
        yield type("O", (), {"auth": auth, "dosya": dosya})
    finally:
        # üst dizin alt öğe silme hakkı verir (kilitli dosya da silinir — acl_artik_temizligi notu)
        try:
            os.unlink(dosya)
        except OSError:
            pass


def test_KRITIK_A10_yeniden_baslatmada_AYNI_token_okunur(ortam, monkeypatch):
    """MUTASYON: `keep_current_user=False`'a dönmek → KIRMIZI (ikinci açılış dosyayı okuyamaz, yeni token üretir)."""
    ilk = ortam.auth.get_api_token()
    assert ilk and ortam.dosya.exists(), "aparat: yedek yol token dosyası yazmadı"
    monkeypatch.setattr(ortam.auth, "_token", None)  # süreç yeniden başladı
    ikinci = ortam.auth.get_api_token()
    assert ikinci == ilk, "yeniden başlatmada token DEĞİŞTİ — süreç kendi token dosyasını kilitleyip okuyamadı (A-10)"


def test_KARSIT_Users_grubu_token_dosyasina_ERISEMEZ(ortam):
    """Koruma gevşemedi: dosyanın ACL'sinde yerel `Users` (S-1-5-32-545) YOK."""
    import subprocess

    ortam.auth.get_api_token()
    cikti = subprocess.run(["icacls", str(ortam.dosya)], capture_output=True, text=True, encoding="mbcs").stdout
    assert ortam.dosya.exists() and "S-1-5-32-545" not in cikti and "BUILTIN\\Users" not in cikti, cikti
