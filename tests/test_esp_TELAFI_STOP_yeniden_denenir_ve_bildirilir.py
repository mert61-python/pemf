# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · 1-C bağımsız inceleme i1-F4 — ESP START yayını sürerken gelen durdurmanın TELAFİ STOP'u düşerse yeniden
denenir; hepsi düşerse operatöre bildirilir.

ÖLÇÜLEN KUSUR (i1): `_esp_start_yayinla`, yayın sürerken acil durdurma / durdurma geldiyse telafi STOP'u gönderir ama
dönüşünü YOK SAYIYORDU. Telafi düşerse (geçici broker hatası) E-stop yanıtı "onaylı" iken ESP bobininde telde son başarılı
komut START kalıyor, operatöre hiçbir şey söylenmiyordu (`tel=[stop, start, stop-telafi(DÜŞTÜ)]`, yeni bildirim yok).
DÜZELTME: telafi STOP'u en çok 3 kez denenir (her deneme yeni kimlikle — 8266 tekrar önbelleği yutmasın); hepsi düşerse
`_bildir_teyitsiz_stop` → "STOP DOĞRULANAMADI — ACİL DURDUR'a basın" `error` bildirimi. Ö.4-Y8: yalnız STOP gönderimi artar.
KAPI (GERÇEK uçlar + `_emergency_stop_all`; yayın kaydedici: START yayını bir Event'te bekletilir, telafi düşürülür).
  KRİTİK (geçici) — ilk telafi düşer, ikincisi gider: telde son BAŞARILI komut STOP.
  KRİTİK (kalıcı) — telafi hep düşer: ≥3 deneme ve bobin 8 için `error` bildirimi.
  KARŞIT — yayın sırasında durdurma YOKSA telafi gönderilmez.
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.api._finish_coil_run(8)  # karşıt kolun başarılı START'ı koşu açabilir — sonraki teste SIZMAZ
        ns.geri()


def _senaryo(o, monkeypatch, *, dusen_telafi: int, durdur: bool = True):
    """Bobin 8 START'ı yayında beklerken (isteğe bağlı) E-stop; ilk `dusen_telafi` telafi STOP'u düşer."""
    gelen, birak = threading.Event(), threading.Event()
    tel: list = []  # (komut, başarılı) — bobin 8, yayın TAMAMLANMA sırası
    sayac = {"telafi": 0, "kimlikler": []}

    def _yayin(topic, payload):
        if topic != "pemf/coil/8/control":
            return True
        komut = str(payload.get("command"))
        if komut == "start":
            gelen.set()
            assert birak.wait(10), "aparat: START serbest bırakılmadı"
            tel.append(("start", True))
            return True
        if str(payload.get("command_id", "")).startswith("telafi_"):
            sayac["telafi"] += 1
            sayac["kimlikler"].append(payload.get("command_id"))
            ok = sayac["telafi"] > dusen_telafi
            tel.append(("stop-telafi", ok))
            return ok
        tel.append((komut, True))
        return True

    monkeypatch.setattr(o.api, "_mqtt_publish", _yayin)
    kutu: dict = {}
    t = threading.Thread(
        target=lambda: kutu.update(
            r=o.c.post("/api/coil/8/control", json={"start": True, "freq": 100, "duty": 40, "phase": 0, "duration": 60})
        ),
        daemon=True,
    )
    t.start()
    assert gelen.wait(10), "aparat: START yayını başlamadı"
    b0 = len(o.bildirim)
    try:
        if durdur:
            o.api._emergency_stop_all("manual")
    finally:
        birak.set()
        t.join(15)
    assert not t.is_alive(), "aparat: tekil istek bitmedi"
    hata = [m for m, tur in o.bildirim[b0:] if tur == "error" and "8" in m and "DOĞRULANAMADI" in m]
    return tel, sayac, hata


def test_KRITIK_GECICI_dusen_telafi_STOP_yeniden_denenir_telde_son_basarili_STOP(o, monkeypatch):
    tel, sayac, hata = _senaryo(o, monkeypatch, dusen_telafi=1)
    n = sayac["telafi"]
    basarili = [k for k, ok in tel if ok]
    assert n >= 2, f"telafi STOP'u düştü ve YENİDEN DENENMEDİ ({n} deneme): {tel}"
    assert basarili and basarili[-1] != "start", f"E-stop sonrası bobin 8'de telde son BAŞARILI komut START: {tel}"
    assert n == 2 and not hata, (
        f"telafi 2. denemede GİTTİ — fazladan deneme ya da yanlış 'doğrulanamadı' alarmı: {tel} {hata}"
    )


def test_KRITIK_KALICI_dusen_telafi_STOP_en_az_3_deneme_ve_OPERATORE_bildirilir(o, monkeypatch):
    tel, sayac, hata = _senaryo(o, monkeypatch, dusen_telafi=99)
    n = sayac["telafi"]
    assert n >= 3, f"telafi STOP'u {n} kez denendi (≥3 bekleniyor): {tel}"
    assert len(set(sayac["kimlikler"])) == n, (
        f"telafi denemeleri AYNI kimliği taşıyor (8266 tekrar önbelleği ikinciyi UYGULAMADAN yutar): {sayac['kimlikler']}"
    )
    assert hata, f"telafi STOP'u hiç gitmedi ama operatöre 'STOP DOĞRULANAMADI' bildirimi gitmedi: {tel}"


def test_KARSIT_durdurma_YOKKEN_telafi_GONDERILMEZ(o, monkeypatch):
    tel, sayac, hata = _senaryo(o, monkeypatch, dusen_telafi=0, durdur=False)
    n = sayac["telafi"]
    assert n == 0 and not hata and tel == [("start", True)], f"durdurma yokken telafi/bildirim: {tel} {hata}"
