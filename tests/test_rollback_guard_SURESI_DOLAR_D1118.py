# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.118 · B-4.4 — `update_manager.rollback()` de `_applying_since` damgasını yazar; başarısız bir geri alma kurulumundan
sonra "güncelleme sürüyor" bayrağı `_APPLYING_GRACE_S` (300 sn) içinde SÖNER.

ÖLÇÜLEN KUSUR: `apply_update` bayrağı damgalıyor (2026-08-04 düzeltmesi), `rollback` damgalamıyordu: installer başlatıldıktan
sonra `_applying` AÇIK kalır (doğru — B-10.151) ama `_applying_since` None'dır → `is_update_in_progress()`'in süre dolumu
HİÇ işlemez. Kurulum tamamlanmazsa (Inno "başka kurulum sürüyor", AV bloğu, iptal) cihaz `/session/start` ve
`/ai/pro/start`'ı SÜRESİZ reddeder — tek çare servisi elle yeniden başlatmak (apply yolunda kapatılan arızanın kardeşi).
Eski kanal varsayılan KAPALI → sahada uykuda.

KAPI: GERÇEK `rollback()` başarı yolu (ağ = yamalı `_pinli_ac`, Popen SAHTE), ardından monotonik saat 301 sn ileri →
`is_update_in_progress()` False. Karşıt: hemen ardından (saat ilerlemeden) True (guard yine açık — B-10.151).
"""

from __future__ import annotations

import hashlib
import io
import time
import types

URL = "https://github.com/mert61-python/pemf-update/releases/download/exe-v1.0.0/PEMF_Setup.exe"
GOVDE = b"MZ-sahte-installer"


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_KRITIK_basarisiz_geri_alma_kurulumundan_sonra_guard_SURESI_DOLAR(monkeypatch):
    from servers import update_manager as um

    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    monkeypatch.setattr(um, "_applying", False)
    monkeypatch.setattr(um, "_applying_since", None)
    monkeypatch.setattr(
        um,
        "_status",
        {
            "checked": True,
            "currentVersion": "1.1.0",
            "previousStable": {"version": "1.0.0", "installerUrl": URL, "sha256": hashlib.sha256(GOVDE).hexdigest()},
            "error": "",
        },
    )
    monkeypatch.setattr(um, "_has_active_treatment", lambda: False)
    monkeypatch.setattr(um, "_pinli_ac", lambda url, timeout, headers=None: _Yanit(GOVDE))
    monkeypatch.setattr(um, "_verify_authenticode", lambda p: "valid")
    monkeypatch.setattr(um, "subprocess", types.SimpleNamespace(Popen=lambda argv, **k: None))
    simdi = [1000.0]

    class _Saat:
        """Yalnız update_manager'ın `time` adı: monotonic test saatinden, geri kalanı gerçek `time` (küresel yama YOK)."""

        def __getattr__(self, ad):
            return getattr(time, ad)

        def monotonic(self):
            return simdi[0]

    monkeypatch.setattr(um, "time", _Saat())

    assert um.rollback().get("ok") is True, "aparat: rollback başarı yoluna ulaşmadı"
    assert um.is_update_in_progress() is True, "karşıt: installer başladıktan hemen sonra guard AÇIK olmalı (B-10.151)"
    simdi[0] += um._APPLYING_GRACE_S + 1
    assert um.is_update_in_progress() is False, (
        "başarısız geri alma kurulumundan sonra 'güncelleme sürüyor' SÖNMEDİ — rollback `_applying_since` yazmıyor; cihaz "
        "seans/AI Pro başlatmayı SÜRESİZ reddeder"
    )
