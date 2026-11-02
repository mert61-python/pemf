# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-2 · apps/backend/servers/live_state.py · sözleşmeler: kuyrukta yalnız TEK SEFERLİK ileti varken sınırda gelen YENİ
periyodik ileti düşer (sayılır + uyarı), ardından gelen tek seferlik ileti yine KABUL edilir ve sağlıklı istemci periyodiği hiç
almaz · ölü istemcinin `close()`u da hata verse öbür ölü istemciler 1011 ile kapatılır, hepsi listeden çıkar · kapanmış olay
döngüsüne yayın sayacı / kuyruğu SIZDIRMAZ; planlama başarısız olurken ileti sınırda zaten düşürüldüyse sayaç İKİ KEZ geri
sayılmaz · bobin kipi / etkin duty: aralık dışı bobin ve değişmeyen değer YAYIN YAPMAZ, değişen değer TEK yayın · E-alanı
modülü yüklenemezse anlık görüntü yine kurulur (`eField` None).

GERÇEK: `live_state._ws_broadcast_sync` (asyncio gönderim kilidi, geri-basınç). Sahte EN ALT katta: WS istemcileri (send_text /
close), olay döngüsü (gerçek `asyncio` döngüsü test iş parçacığında adım adım; planlamada yarışan iş parçacığını taklit eden
döngü nesnesi), `servers.efield_live` modül kaydı (`sys.modules` + paket özniteliği birlikte, monkeypatch geri koyar).
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import sys

import pytest


class _Kaydeden:
    def __init__(self):
        self.alinan: list[dict] = []

    async def send_text(self, data):
        self.alinan.append(json.loads(data))

    async def close(self, code=None):
        pass


class _Olu:
    def __init__(self, kapatma_hatasi=None):
        self.kapatmalar: list = []
        self.kapatma_hatasi = kapatma_hatasi

    async def send_text(self, data):
        raise ConnectionResetError("kp2: istemci öldü")

    async def close(self, code=None):
        self.kapatmalar.append(code)
        if self.kapatma_hatasi is not None:
            raise self.kapatma_hatasi


@pytest.fixture()
def ls(monkeypatch):
    from servers import live_state as ls

    monkeypatch.setattr(ls, "_ws_send_lock", None)
    monkeypatch.setattr(ls, "_ws_pending", 0)
    monkeypatch.setattr(ls, "_ws_bekleyenler", collections.deque())
    monkeypatch.setattr(ls, "_ws_dropped_total", 0)
    monkeypatch.setattr(ls, "_ws_clients", [])
    yedek = {k: dict(v) for k, v in ls._live_state["coils"].items()}
    yield ls
    for k, y in yedek.items():
        ls._live_state["coils"][k].clear()
        ls._live_state["coils"][k].update(y)


@pytest.fixture()
def dongu(ls, monkeypatch):
    d = asyncio.new_event_loop()
    monkeypatch.setattr(ls, "_event_loop", d)
    yield d
    for _ in range(200):
        if ls._ws_pending <= 0:
            break
        d.run_until_complete(asyncio.sleep(0.002))
    d.close()


def _bosalt(ls, d):
    for _ in range(400):
        d.run_until_complete(asyncio.sleep(0.001))
        if ls._ws_pending == 0:
            return
    raise AssertionError(f"kuyruk boşalmadı: {ls._ws_pending}")


# ── geri-basınç sınırı ────────────────────────────────────────────────────────────────────────────────────────────────


def test_kuyrukta_yalniz_TEK_SEFERLIK_varken_YENI_periyodik_duser_tek_seferlik_yine_KABUL(
    ls, dongu, monkeypatch, caplog
):
    istemci = _Kaydeden()
    monkeypatch.setattr(ls, "_ws_clients", [istemci])
    sinir = ls._WS_MAX_PENDING_BROADCASTS
    for i in range(sinir):
        ls._ws_broadcast_sync({"type": "stm_status", "n": i})
    assert ls._ws_pending == sinir
    with caplog.at_level(logging.WARNING, logger=ls.__name__):
        ls._ws_broadcast_sync({"type": "sensor_data", "n": "periyodik"})
    assert ls._ws_pending == sinir and ls._ws_dropped_total == 1, "sınırda gelen periyodik ileti düşürülüp sayılmadı"
    assert any("yalniz tek-seferlik" in r.getMessage() for r in caplog.records)
    ls._ws_broadcast_sync({"type": "emergency_stop", "n": "acil"})
    assert ls._ws_pending == sinir + 1, "tek seferlik ileti sınırda REDDEDİLDİ"
    _bosalt(ls, dongu)
    turler = [m["type"] for m in istemci.alinan]
    assert turler.count("stm_status") == sinir and turler[-1] == "emergency_stop"
    assert "sensor_data" not in turler


def test_olu_istemcinin_CLOSE_hatasi_ob_ur_olu_istemcinin_kapatilmasini_ENGELLEMEZ(ls, dongu, monkeypatch):
    a = _Olu(kapatma_hatasi=RuntimeError("kp2: soket zaten kapalı"))
    b = _Olu()
    saglam = _Kaydeden()
    monkeypatch.setattr(ls, "_ws_clients", [a, b, saglam])
    ls._ws_broadcast_sync({"type": "session_update", "n": 1})
    _bosalt(ls, dongu)
    assert a.kapatmalar == [1011] and b.kapatmalar == [1011], (a.kapatmalar, b.kapatmalar)
    assert ls._ws_clients == [saglam], "ölü istemciler listeden çıkmadı"
    assert [m["type"] for m in saglam.alinan] == ["session_update"]


# ── kapanmış döngü ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_KAPANMIS_donguye_yayin_sayaci_ve_kuyrugu_SIZDIRMAZ(ls, monkeypatch):
    kapali = asyncio.new_event_loop()
    kapali.close()
    monkeypatch.setattr(ls, "_event_loop", kapali)
    monkeypatch.setattr(ls, "_ws_clients", [_Kaydeden()])
    for i in range(3):
        ls._ws_broadcast_sync({"type": "sensor_data", "n": i})
        ls._ws_broadcast_sync({"type": "stm_status", "n": i})
    assert ls._ws_pending == 0 and len(ls._ws_bekleyenler) == 0


class _YarisanKapaliDongu:
    """Kapanmış döngü (`call_soon_threadsafe` RuntimeError) — İLK planlama sırasında BAŞKA bir iş parçacığı aynı sınırda
    yeni bir periyodik yayın yapar (ürünün kendi `_ws_broadcast_sync`'i) ve ilk iletiyi düşürür."""

    def __init__(self, ls):
        self.ls, self.cagri = ls, 0

    def call_soon_threadsafe(self, cb, *a):
        self.cagri += 1
        if self.cagri == 1:
            self.ls._ws_broadcast_sync({"type": "sensor_data", "n": "yarisan"})
        raise RuntimeError("Event loop is closed")


def test_planlama_basarisizken_ileti_SINIRDA_zaten_dusurulduyse_sayac_IKI_KEZ_geri_sayilmaz(ls, monkeypatch):
    sinir = ls._WS_MAX_PENDING_BROADCASTS
    sahte = _YarisanKapaliDongu(ls)
    monkeypatch.setattr(ls, "_event_loop", sahte)
    monkeypatch.setattr(ls, "_ws_clients", [_Kaydeden()])
    monkeypatch.setattr(ls, "_ws_pending", sinir - 1)
    ls._ws_broadcast_sync({"type": "sensor_data", "n": "ilk"})
    assert sahte.cagri == 2, "aparat: yarışan yayın planlanmadı"
    assert ls._ws_dropped_total == 1, "aparat: ilk ileti sınırda düşürülmedi"
    assert ls._ws_pending == sinir - 1, (
        f"sayaç bozuldu: {ls._ws_pending} (beklenen {sinir - 1}; çift geri sayım / sızıntı)"
    )
    assert len(ls._ws_bekleyenler) == 0


# ── bobin kipi / etkin duty ───────────────────────────────────────────────────────────────────────────────────────────


def test_bobin_kipi_ARALIK_DISI_ve_DEGISMEYEN_deger_yayin_YAPMAZ_degisen_TEK_yayin(ls, dongu, monkeypatch):
    istemci = _Kaydeden()
    monkeypatch.setattr(ls, "_ws_clients", [istemci])
    ls._live_state["coils"][0]["unipolar"] = None
    once = {k: dict(v) for k, v in ls._live_state["coils"].items()}
    ls.update_live_coil_kip(0, True)
    ls.update_live_coil_kip(9, True)
    assert {k: dict(v) for k, v in ls._live_state["coils"].items()} == once and ls._ws_pending == 0
    ls.update_live_coil_kip(1, True)
    ls.update_live_coil_kip(1, True)
    _bosalt(ls, dongu)
    assert [(m["type"], m["coilId"], m["data"]["unipolar"]) for m in istemci.alinan] == [("coil_status", 1, True)]


def test_etkin_duty_ARALIK_DISI_ve_DEGISMEYEN_deger_yayin_YAPMAZ_degisen_TEK_yayin(ls, dongu, monkeypatch):
    istemci = _Kaydeden()
    monkeypatch.setattr(ls, "_ws_clients", [istemci])
    ls._live_state["coils"][1]["dutyEtkin"] = None
    once = {k: dict(v) for k, v in ls._live_state["coils"].items()}
    ls.update_live_coil_etkin_duty(0, 30.0)
    ls.update_live_coil_etkin_duty(9, 30.0)
    assert {k: dict(v) for k, v in ls._live_state["coils"].items()} == once and ls._ws_pending == 0
    ls.update_live_coil_etkin_duty(2, 42.5)
    ls.update_live_coil_etkin_duty(2, 42.5)
    _bosalt(ls, dongu)
    assert [(m["coilId"], m["data"]["dutyEtkin"]) for m in istemci.alinan] == [(2, 42.5)]


# ── E-alanı modülü yüklenemezse ───────────────────────────────────────────────────────────────────────────────────────


def test_efield_modulu_YUKLENEMEZSE_anlik_goruntu_kurulur_eField_None(ls, monkeypatch):
    import servers

    monkeypatch.delattr(servers, "efield_live", raising=False)
    monkeypatch.setitem(sys.modules, "servers.efield_live", None)
    assert ls._efield_snapshot() is None
    snap = ls._build_ws_snapshot()
    assert snap["eField"] is None and len(snap["coils"]) == 8 and "stm" in snap
