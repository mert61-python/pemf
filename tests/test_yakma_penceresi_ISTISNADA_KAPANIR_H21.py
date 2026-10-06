# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-2.1 (1-H bağımsız incelemesi) — D1.114 oto-firmware YAKMA PENCERESİ yakma akışı İSTİSNAYLA bitse de KAPANIR.

KÖR KAPI (ölçüldü, inceleme `kayit/h21eski_mutasyon.txt`): `utils.firmware_yakma_penceresi.ac()`'ın `try/finally`'si
kaldırılıp pencere yalnız normal çıkışta kapatılınca firmware zincirinin 8 kapı dosyası (D1.108/111, D1.112, D1.113, D1.114,
D1.115, D1.120, D1.121, `test_firmware_manager`) 87/87 YEŞİL kaldı — istisna yolu hiç ölçülmüyordu. O mutantta yakma
akışı fırlatırsa (ör. `firmware_yedek` dizini yazılamıyor → `yedek_al` `mkdir` PermissionError) pencere SÜREÇ SONUNA DEK
açık kalır: her STM bobin başlatması "firmware YAZILIYOR" ile reddedilir, `is_update_in_progress()` True → seans / AI Pro
409 — yeniden başlatılana dek cihaz tedavi veremez (ACİL DURDUR yine çalışır).

KAPI: GERÇEK `firmware_manager._firmware_uygula` → GERÇEK `stm_yakma.yakma_akisi`; yedek alma PermissionError fırlatır
(yazılamayan yedek dizini). Sonra: pencere KAPALI, HC başlatma engeli YOK, `is_update_in_progress()` False; karşıt kol akış
SÜRERKEN pencerenin AÇIK olduğunu ölçer (aparat pencereyi gerçekten görüyor). Gerçek seri port / yakıcı YOK.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def zincir(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import live_state as ls

    fm = importlib.import_module("servers.firmware_manager")
    sy = importlib.import_module("utils.stm_yakma")
    ikili = tmp_path / "indir" / "pemf_fw.bin"
    ikili.parent.mkdir()
    ikili.write_bytes(b"PEMF-FW-2.4" * 97)
    girdi = {"version": "2.4", "sha256": hashlib.sha256(ikili.read_bytes()).hexdigest(), "url": "x"}
    monkeypatch.setattr(fm, "firmware_indir", lambda url, sha: (ikili, ""))
    monkeypatch.setattr(fm, "_yedek_dizini", lambda: tmp_path / "firmware_yedek")
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_yakici.exe"))
    monkeypatch.setattr(sy, "_kos", lambda *a, **k: (_ for _ in ()).throw(AssertionError("yakıcı çağrılmamalı")))
    monkeypatch.setitem(api._active_session, "is_active", False)
    monkeypatch.setattr(api.state, "hardware", None)
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
    try:
        yield {"fm": fm, "sy": sy, "girdi": girdi, "mp": monkeypatch}
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)


def test_KRITIK_H21_yakma_akisi_FIRLATIRSA_pencere_KAPANIR_baslatma_ve_seans_ENGELLENMEZ(zincir):
    from servers import update_manager as um
    from utils import firmware_yakma_penceresi as pencere
    from utils import surum_uyumu as su

    z = zincir
    gorulen = {}

    def _yedek_yazilamaz(cli, hedef, boyut):
        gorulen["pencere_akista"] = pencere.acik_mi()
        gorulen["engel_akista"] = pencere.baslatma_engeli()
        raise PermissionError(13, "firmware_yedek dizini yazılamıyor (sahte)")

    z["mp"].setattr(z["sy"], "yedek_al", _yedek_yazilamaz)
    plan = su.Plan(su.FIRMWARE_GUNCELLE, "2.4", "test")
    with pytest.raises(PermissionError):
        z["fm"]._firmware_uygula(z["girdi"], plan)
    # Aparat karşıtı: akış SÜRERKEN pencere gerçekten açıktı (kapı pencereyi görüyor).
    assert gorulen.get("pencere_akista") is True and gorulen.get("engel_akista"), f"aparat: pencere açılmadı {gorulen}"
    assert pencere.acik_mi() is False, (
        "yakma akışı istisnayla bitti ama YAKMA PENCERESİ AÇIK KALDI — süreç sonuna dek bobin başlatma reddedilir"
    )
    assert pencere.baslatma_engeli() == "", "pencere kapanmadı: HC başlatma engeli sürüyor"
    assert um.is_update_in_progress() is False, "pencere kapanmadı: seans / AI Pro başlatma 409 sürüyor"
