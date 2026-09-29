# Author: mertaygn, cglrgrkn
"""D0Ö.08 (B-10.21 · B-10.22) KAPISI — e2e araçlarının backend ALT SÜRECİ gerçek sisteme dokunamaz.

ARIZA (DENETIM-10 B-10.21/B-10.22; plan orkestratör notu: onaysız sürüş sınıfı): `tools/e2e_smoke.py`
backend'i `PEMF_STM_PORT` VERMEDEN başlatıyordu → varsayılan COM10: gerçek kart takılıysa seans senaryosu
bobin 1, 2, 7'ye %25 / 50 Hz paket gönderebilirdi. İki araç da GERÇEK ProgramData cihaz sırrını okuyup
yazıyor, gömülü Supabase adresiyle üretim `devices` tablosuna e2e kaydı upsert ediyordu; E-stop
senaryoları bulut aynasıyla depo içindeki provizyonla GERÇEK broker'a STOP yayınlayabilirdi.

KAPI: her aracın `main()`'i GERÇEKTEN çağrılır — `Popen` sahte (backend BAŞLATILMAZ, ortam yakalanır);
sahte süreç hemen "çıkmış" görünür → araç "backend açılmadı" dalından döner, HTTP isteği yapılmaz
(e2e_full'ün kapanıştaki E-stop isteği de sahte `req`e düşer). Dış yalıtım değişkenleri ÖNCE silinir,
PROGRAMDATA/APPDATA/LOCALAPPDATA "gerçek" gibi tmp nöbetçiye çevrilir (koşucu kendisi verebilir →
sahte-yeşil olmasın). İddialar: PEMF_STM_PORT gerçek COM değil; PEMF_DEVICE_IDENTITY_DIR, PROGRAMDATA,
APPDATA aracın tmp veri kökü altında; SUPABASE_URL loopback kara-delik; hasta bulut senkronu kapalı;
bulut MQTT provizyonu var olmayan bir yolda; hotspot kapalı (backend kaynaktan koşar, betik bulunabilir).
MUTASYON: ortak kurucudan `PEMF_STM_PORT` satırını silmek → iki araç da KIRMIZI.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from exe_kapisi_surucusu import YALITIM_DEGISKENLERI, AltSurecVekili

KOK = Path(__file__).resolve().parents[1]


def _gercek_com_mu(port: str) -> bool:
    p = (port or "").strip().lower()
    return p == "" or p in ("auto", "otomatik") or re.fullmatch(r"com\d+", p) is not None


def _istek_yok(*a, **k):
    raise ConnectionRefusedError("e2e kapısı: HTTP isteği yapılmaz")


#: Dış ortamda (sahibin kabuğu) bulunabilecek, GERÇEK kaynaklara işaret eden değişkenler (nöbetçi değerler).
#: D0Ö.08 ek (tur 3): backend alt süreci bunları MİRAS ALMAMALI — PEMF_BACKUP_DIR ilk yedek turunda kurtarma
#: zarfını gerçek off-site dizine AYNI ADLA yazar; PEMF_MQTT_CLOUD_* E-stop'u gerçek broker'a aynalar.
_MIRAS_NOBETCILERI = {
    "PEMF_BACKUP_DIR": "GERCEK_offsite_yedek",
    "PEMF_MQTT_CLOUD_HOST": "gercek-broker.invalid",
    "PEMF_SENTRY_DSN": "https://gercek@sentry.invalid/1",
    "PEMF_REQUIRE_AUTH": "1",
    "SUPABASE_KEY": "gercek-anahtar",
}


def _arac_ortami(ad: str, tmp_path: Path, monkeypatch) -> tuple[dict, Path]:
    """Aracın `main()`i backend'e hangi ortamı verirdi — backend BAŞLATILMADAN."""
    for d in YALITIM_DEGISKENLERI:
        monkeypatch.delenv(d, raising=False)
    for d in ("PROGRAMDATA", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        monkeypatch.setenv(d, str(tmp_path / f"GERCEK_{d}"))
    for d, deger in _MIRAS_NOBETCILERI.items():
        monkeypatch.setenv(d, str(tmp_path / deger) if deger.startswith("GERCEK_") else deger)
    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    monkeypatch.setenv("PEMF_FW_AUTO_UPDATE", "1")
    # Koşucu/conftest dış ortamda null arka uç verir → araç onu MİRAS alıp kapıyı maskelerdi.
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.Windows.WinVaultKeyring")
    monkeypatch.setattr(sys, "path", list(sys.path))  # araç kökü eklerse test sonunda geri gelir
    spec = importlib.util.spec_from_file_location(f"e2e_kapisi_{ad}", KOK / "tools" / f"{ad}.py")
    arac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arac)
    yakalanan = {}

    class _SahteSurec:
        def __init__(self, argv, env=None, **kw):
            yakalanan["env"] = {k.upper(): v for k, v in (env or {}).items()}

        def poll(self):
            return 0  # hemen "çıktı" → araç sağlık beklemeden "açılmadı" dalına düşer

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    veri = tmp_path / "e2e_veri"
    veri.mkdir()
    monkeypatch.setattr(arac, "subprocess", AltSurecVekili(Popen=_SahteSurec))
    monkeypatch.setattr(arac, "tempfile", SimpleNamespace(mkdtemp=lambda *a, **k: str(veri)))
    monkeypatch.setattr(arac, "req", _istek_yok)
    assert arac.main() == 1, f"{ad}: sahte süreç 'çıkmışken' araç 'backend açılmadı' dalından dönmedi"
    assert "env" in yakalanan, f"{ad}: backend Popen ile başlatılmadı (çıpa kaymış)"
    return yakalanan["env"], veri


@pytest.mark.parametrize("ad", ["e2e_smoke", "e2e_full"])
def test_KRITIK_e2e_backend_ortami_GERCEK_sisteme_DOKUNAMAZ(ad, tmp_path, monkeypatch):
    env, veri = _arac_ortami(ad, tmp_path, monkeypatch)
    assert not _gercek_com_mu(env.get("PEMF_STM_PORT", "")), (
        f"{ad} backend'i gerçek STM portuna bağlanabilir: PEMF_STM_PORT={env.get('PEMF_STM_PORT')!r} — "
        "takılı karta onaysız bobin paketi gidebilir (B-10.21)"
    )
    disarida = {
        d: env.get(d)
        for d in ("PEMF_DEVICE_IDENTITY_DIR", "PROGRAMDATA", "APPDATA")
        if not (env.get(d) and "GERCEK_" not in env[d] and Path(env[d]).resolve().is_relative_to(veri.resolve()))
    }
    assert not disarida, f"{ad} backend'i gerçek makine köklerine / cihaz sırrına dokunabilir: {disarida} (B-10.22)"
    assert urlparse(env.get("SUPABASE_URL", "")).hostname in ("127.0.0.1", "localhost", "::1"), (
        f"{ad} backend'i üretim devices tablosuna e2e kaydı gönderebilir: SUPABASE_URL={env.get('SUPABASE_URL')!r}"
    )
    assert env.get("PEMF_CLOUD_PATIENT_SYNC") == "0", f"{ad}: hasta bulut senkronu açık kalabilir"
    # Backend KAYNAKTAN koşar → `scripts/start_hotspot.ps1` bulunabilir; etkileşimli oturumda Mobile Hotspot açılırdı.
    assert env.get("PEMF_HOTSPOT") == "0", (
        f"{ad}: backend hotspot başlatabilir: PEMF_HOTSPOT={env.get('PEMF_HOTSPOT')!r}"
    )
    saglama = env.get("PEMF_CLOUD_PROVISION_PATH", "")
    assert saglama and Path(saglama).resolve().is_relative_to(veri.resolve()) and not Path(saglama).exists(), (
        f"{ad}: E-stop bulut aynası GERÇEK broker'a uzanabilir: PEMF_CLOUD_PROVISION_PATH={saglama!r}"
    )
    # EK (tur 3): oto-firmware, ev/masaüstü, kasa ve dış ortam mirası.
    assert env.get("PEMF_FW_AUTO_UPDATE") == "0", f"{ad}: PEMF_FW_AUTO_UPDATE={env.get('PEMF_FW_AUTO_UPDATE')!r}"
    ev_disarida = {
        d: env.get(d)
        for d in ("USERPROFILE", "HOME", "LOCALAPPDATA")
        if not (env.get(d) and "GERCEK_" not in env[d] and Path(env[d]).resolve().is_relative_to(veri.resolve()))
    }
    assert not ev_disarida, f"{ad} backend'i GERÇEK ev/masaüstü köküne yazabilir: {ev_disarida}"
    assert (Path(env["USERPROFILE"]) / "Desktop").is_dir(), (
        f"{ad}: sahte evin Desktop klasörü yok — masaüstü bulunamazsa ürün DEPO dizinine (cwd) yazar"
    )
    assert env.get("PYTHON_KEYRING_BACKEND") == "keyring.backends.null.Keyring", (
        f"{ad} backend'i sahibin GERÇEK kimlik kasasını okuyabilir: PYTHON_KEYRING_BACKEND="
        f"{env.get('PYTHON_KEYRING_BACKEND')!r}"
    )
    sizan = {d: env[d] for d in _MIRAS_NOBETCILERI if d in env}
    assert not sizan, f"{ad} backend'i dış ortamın GERÇEK kaynak değişkenlerini MİRAS aldı: {sizan}"
