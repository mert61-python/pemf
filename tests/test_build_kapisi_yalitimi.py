# -*- coding: utf-8 -*-
"""D0Ö.06 (B-10.66) KAPISI — build AI kapısı gate EXE'yi YALITILMIŞ ortamda başlatır.

ARIZA (DENETIM-10 B-10.66): `scripts/build_backend_exe.ps1` AI hazırlık kapısı üretilen EXE'yi yalnız
`PEMF_SIMULATE=1` ile başlatıyordu; geri kalan ortam build makinesininkiydi → her build GERÇEK veri
kökünde göç ve ACL işlemi yapıyor, gerçek `ProgramData\\PEMF_System\\device_identity.json` bulut
sırrını okuyup yazıyor, buluta cihaz kaydı gönderiyor, STM takılıysa seri porta bağlanıyordu.

KAPI (bloğun GERÇEK metni, `Start-Process` gölgelenerek — `tests/exe_kapisi_surucusu.py`): EXE'ye
geçecek ortamda veri kökü (PEMF_DATA_DIR/APPDATA/LOCALAPPDATA/PROGRAMDATA) ve PEMF_DEVICE_IDENTITY_DIR
build'in KENDİ scratch kökü altında; build makinesinin "gerçek" değerleri (tmp nöbetçi) DEĞİL;
PEMF_HOTSPOT='0'; Supabase adresi loopback kara-delik; bulut MQTT provizyonu var olmayan scratch yol.
Blok bittikten sonra build sürecinin ortamı eski hâline döner (sonraki adımlara sızmaz) ve scratch kök
silinir (açılışın kopyaladığı eski anahtar dosyaları build ağacında kalmaz).
MUTASYON: gate ortamından PEMF_FW_AUTO_UPDATE / PEMF_DEVICE_IDENTITY_DIR satırını silmek → KIRMIZI.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
from exe_kapisi_surucusu import PWSH, build_makinesi_ortami, kapi_blogunu_kostur

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — build betiği pwsh ile koşar")

_KOK_DEGISKENLERI = ("PEMF_DATA_DIR", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PEMF_DEVICE_IDENTITY_DIR")


def _altinda(yol: str, kok: str) -> bool:
    try:
        return Path(yol).resolve().is_relative_to(Path(kok).resolve())
    except (OSError, ValueError):
        return False


def test_KRITIK_gate_EXE_veri_koku_ve_cihaz_kimligi_SCRATCH_altinda(tmp_path):
    veri = kapi_blogunu_kostur(tmp_path, build_makinesi_ortami(tmp_path))
    assert veri.get("yakalanan"), f"kapı bloğu EXE'yi başlatmadı: {veri.get('hata')}"
    env = veri["yakalanan"]["Env"]
    disarida = {ad: env.get(ad) for ad in _KOK_DEGISKENLERI if not (env.get(ad) and _altinda(env[ad], veri["kok"]))}
    assert not disarida, (
        f"gate EXE build makinesinin GERÇEK köklerine yazabilir (scratch dışı): {disarida} — "
        "göç/ACL gerçek veri kökünde, bulut sırrı gerçek ProgramData'da (B-10.66)"
    )


def test_KRITIK_gate_EXE_hotspot_KAPALI_ve_bulut_KARA_DELIK(tmp_path):
    veri = kapi_blogunu_kostur(tmp_path, build_makinesi_ortami(tmp_path))
    env = (veri.get("yakalanan") or {}).get("Env") or {}
    assert env.get("PEMF_HOTSPOT") == "0", f"gate EXE hotspot başlatabilir: PEMF_HOTSPOT={env.get('PEMF_HOTSPOT')!r}"
    adres = urlparse(env.get("SUPABASE_URL", ""))
    assert adres.hostname in ("127.0.0.1", "localhost", "::1"), (
        f"gate EXE buluta (Supabase) cihaz kaydı gönderebilir: SUPABASE_URL={env.get('SUPABASE_URL')!r}"
    )
    # Bulut MQTT: frozen EXE depo içinde koşunca `data/cloud_mqtt_provision.json`u bulup GERÇEK broker'a
    # bağlanabilir (D0Ö.07'nin süitte kestiği kanal) → provizyon var olmayan bir scratch yola yönlenmeli.
    saglama = env.get("PEMF_CLOUD_PROVISION_PATH", "")
    assert saglama and _altinda(saglama, veri["kok"]) and not Path(saglama).exists(), (
        f"gate EXE bulut MQTT provizyonunu okuyabilir: PEMF_CLOUD_PROVISION_PATH={saglama!r}"
    )


def test_KRITIK_gate_koku_blok_sonunda_SILINIR(tmp_path):
    """Açılış eski `~/.pemf_gui` anahtar dosyalarını veri köküne KOPYALAR; kök build ağacında kalmamalı.
    Sürücünün Start-Process sahtesi EXE gibi veri köküne bir iz yazar."""
    veri = kapi_blogunu_kostur(tmp_path, build_makinesi_ortami(tmp_path))
    veri_koku = ((veri.get("yakalanan") or {}).get("Env") or {}).get("PEMF_DATA_DIR", "")
    assert veri_koku and _altinda(veri_koku, veri["kok"]), f"gate veri kökü scratch altında değil: {veri_koku!r}"
    kalan = [p for p in Path(veri["kok"]).rglob("*") if p.name == "exe_izi.txt"]
    assert not kalan, f"gate EXE'nin veri kökü blok bitince build ağacında KALDI: {kalan}"


def test_KRITIK_blok_sonrasi_build_ortami_ESKI_haline_doner(tmp_path):
    veri = kapi_blogunu_kostur(tmp_path, build_makinesi_ortami(tmp_path))
    once, sonra = veri["once"], veri["sonra"]
    sizan = {
        ad: (once.get(ad), sonra.get(ad))
        for ad in (
            *_KOK_DEGISKENLERI,
            "PEMF_FW_AUTO_UPDATE",
            "PEMF_STM_PORT",
            "PEMF_HOTSPOT",
            "SUPABASE_URL",
            "PEMF_CLOUD_PROVISION_PATH",
            "PEMF_SIMULATE",
        )
        if once.get(ad) != sonra.get(ad)
    }
    assert not sizan, f"kapı ortamı build sürecine SIZDI (sonraki adımlar scratch/kapalı ortamla koşar): {sizan}"
