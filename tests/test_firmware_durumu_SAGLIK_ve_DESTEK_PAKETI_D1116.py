# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.116 · B-4.11 — oto-firmware durumu (`firmware_manager.durum()`: eylem, gerekçe, son sonuç kodu) `/api/health`'te ve destek
paketinde GÖRÜNÜR; tünel (uzak) istemcisine ayrıntı SIZMAZ.

ÖLÇÜLEN KUSUR: modül başlığı "fail-quiet, fail-silent DEĞİL — durum `durum()` ile görünür kalır" diyordu ama `durum()`'u
OKUYAN tek çağıran yoktu: açılış denetiminin kararı (BEKLE "manifest okunamadı", EYLEM_YOK "kural yok"), yakma sonucu
(`[8] … geri dönüldü`, `[10] port meşgul`, `[11] geri dönüş başarısız`…) yalnız servis günlüğünde kalıyordu. Destek
mühendisi "neden yakmadı / ne oldu"yu göremezdi (zincir D1.120/121 ile uyandığında asıl ihtiyaç).

KAPI: `fm._durum_yaz(eylem='bekle', gerekce=…)` → GERÇEK `/api/health` (loopback istemci) gövdesinde `firmwareGuncelleme`
aynı eylem/gerekçe ile; GERÇEK `support_bundle.olustur` → `OZET.json`'da `firmware_guncelleme`; tünel başlıklı
(`cf-connecting-ip`) istekte alan `None` (gerekçe metni ayrıntı taşır — uzak istemciye verilmez).
"""

from __future__ import annotations

import importlib
import io
import json
import zipfile

import pytest

GEREKCE = "1H-D1116 kapisi: manifest okunamadi (sahte)"


@pytest.fixture()
def fm():
    m = importlib.import_module("servers.firmware_manager")
    onceki = m.durum()
    m._durum_yaz(kontrol_edildi=True, eylem="bekle", gerekce=GEREKCE, uygulandi=False, hata="")
    try:
        yield m
    finally:
        m._durum_yaz(**onceki)


def _saglik(api, basliklar=None):
    from fastapi.testclient import TestClient

    c = TestClient(api.app, client=("127.0.0.1", 50116))
    r = c.get("/api/health", headers=basliklar or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_KRITIK_saglik_ucu_firmware_durumunu_GOSTERIR(fm):
    from servers import api_server as api

    g = _saglik(api)
    fg = g.get("firmwareGuncelleme")
    assert isinstance(fg, dict), (
        f"/api/health firmware güncelleme durumunu VERMİYOR (alan: {fg!r}) — karar yalnız günlükte"
    )
    assert fg.get("eylem") == "bekle" and fg.get("gerekce") == GEREKCE, fg


def test_KRITIK_tunel_istemcisine_AYRINTI_SIZMAZ(fm):
    from servers import api_server as api

    g = _saglik(api, {"cf-connecting-ip": "203.0.113.7"})
    assert g.get("firmwareGuncelleme") is None, (
        f"tünel istemcisine firmware ayrıntısı sızdı: {g.get('firmwareGuncelleme')!r}"
    )


def test_KRITIK_destek_paketi_OZETinde_firmware_durumu_VAR(fm, tmp_path):
    from utils import support_bundle

    veri, ozet = support_bundle.olustur(tmp_path)
    assert (ozet.get("firmware_guncelleme") or {}).get("eylem") == "bekle", (
        f"destek paketi özetinde firmware güncelleme durumu YOK: {ozet.get('firmware_guncelleme')!r}"
    )
    with zipfile.ZipFile(io.BytesIO(veri)) as z:
        oz = json.loads(z.read("OZET.json").decode("utf-8"))
    assert oz.get("firmware_guncelleme", {}).get("gerekce") == GEREKCE, oz.get("firmware_guncelleme")
