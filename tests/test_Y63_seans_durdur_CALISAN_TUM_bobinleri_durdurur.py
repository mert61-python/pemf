# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y63 (sahip, 1-F S-F3) — "Seansı Durdur" çalışan TÜM bobinlere STOP gönderir; seans dışı bobinin koşu kaydı o anda kapanır.

ÖLÇÜLEN KUSUR (1-F açık madde 1; 1-G önce-kırmızı `f65402b`): `/api/session/stop` yalnız SEANSIN bobin listesine STOP
gönderiyordu. Seans sürerken tekil kontrol (`/api/coil/{id}/control`), toplu uç ya da eski `/api/hardware/command` ile
AYRICA başlatılan bobin (STM 6-7 dahil; ESP açıksa 8) seans durdurulduktan sonra keep-alive ile SÜRMEYE devam ediyordu;
koşu kaydı açık kalıyor, bitişi ancak bir sonraki başlatmada "bu an" diye yazılıyordu.

SÖZLEŞME (sahip Y63): STOP yalnız ARTAR (Ö.4-Y8) — seansın bobinleri + çalıştığı BİLİNEN seans dışı bobinler (HC
`is_running`, açık koşu kaydı, ESP canlı durumu). Seans kaydı yalnız seansın bobinlerini "seans" diye yazar (değişmez);
seans dışı bobinin koşu kaydı STOP anında KAPANIR. KARŞIT: ÇALIŞMAYAN bobine STOP gönderilmez — ESP açık + broker ölüyken
hiç sürülmemiş bobin 8 için sahte "STOP DOĞRULANAMADI" (409) alarmı üretilmez (alarm körlüğü). Ölçüt HTTP değil TEL
(gerçek `HardwareController`, kayıtçı kuyruk; firmware aynasıyla çözülür), MQTT yayını ve DB koşu kaydı.
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest

_SEANS = {"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]}
_TEKIL = {"freq": 100, "duty": 40, "phase": 0, "duration": 600, "start": True}


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.ls, "esp_etkin", lambda: True)  # ESP dönüşü: bobin 8 de sürülebilir
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _son_duty(o):
    from kayitci_donanim import paket_coz

    return paket_coz(o.hc.core._hw_send_queue.paketler[-1])[0]


def _acik_kosular(o, sid):
    with o.db._get_connection() as conn:
        return sorted(
            r[0]
            for r in conn.execute(
                "SELECT coil_id FROM session_coil_runs WHERE session_id = ? AND ended_epoch IS NULL", (sid,)
            ).fetchall()
        )


def _seans_ve_seans_disi_bobinler(o):
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    with o.api._session_lock:
        sid = o.api._active_session.get("db_session_id")
    assert sid, "aparat: seans DB satırı yok"
    for b in (3, 6, 8):  # seans DIŞI: STM 3, STM 6 (6-7 STM'de), ESP 8
        rb = o.c.post(f"/api/coil/{b}/control", json=_TEKIL)
        assert rb.status_code == 200 and rb.json().get("status") == "success", f"aparat: bobin {b} {rb.text[:160]}"
    assert sorted(ap.calisan(o)) == [1, 2, 3, 6], f"aparat: telde çalışan {ap.calisan(o)}"
    assert _acik_kosular(o, sid) == [1, 2, 3, 6, 8], f"aparat: açık koşular {_acik_kosular(o, sid)}"
    return sid


def test_KRITIK_Y63_seans_durdur_SEANS_DISI_calisan_STM_bobinlerini_de_DURDURUR(o):
    _seans_ve_seans_disi_bobinler(o)
    r = o.c.post("/api/session/stop")
    assert r.status_code == 200, r.text[:200]
    duty = _son_duty(o)
    assert not ap.calisan(o) and all(x == 0 for x in duty), (
        f"'Seansı Durdur'dan sonra seans DIŞI bobinler hâlâ SÜRÜLÜYOR: çalışan={ap.calisan(o)} son paket duty={duty}"
    )


def test_KRITIK_Y63_seans_durdur_SEANS_DISI_ESP_bobinine_STOP_yayinlar(o):
    _seans_ve_seans_disi_bobinler(o)
    n = len(o.yayin)
    o.c.post("/api/session/stop")
    stoplar = [t for t, p in o.yayin[n:] if p.get("command") == "stop"]
    assert "pemf/coil/8/control" in stoplar, f"seans dışı ESP bobini 8'e STOP yayınlanmadı: {o.yayin[n:]}"


def test_KRITIK_Y63_seans_disi_bobinin_KOSU_KAYDI_durdurma_aninda_KAPANIR(o):
    sid = _seans_ve_seans_disi_bobinler(o)
    o.c.post("/api/session/stop")
    assert _acik_kosular(o, sid) == [], f"seans durdurulduktan sonra AÇIK kalan koşu kaydı: {_acik_kosular(o, sid)}"
    with o.api._active_coil_runs_lock:
        assert not o.api._active_coil_runs, f"bellekte açık koşu kaldı: {o.api._active_coil_runs}"


def test_KARSIT_Y8_ek_bobin_tespiti_HATA_verse_de_seansin_KENDI_STOPu_gider(o, monkeypatch):
    """Y63'ün eki (seans dışı çalışan bobinleri bulma) fırlatırsa `/session/stop` STOP'tan ÖNCE düşmemeli — seansın kendi
    bobinlerine STOP her koşulda gider (Ö.4-Y8). (1-G'de ilk taslak `dict` üzerinde yanlış yineleme yapıp `AttributeError`
    ile ucu 500'e düşürmüştü: STOP HİÇ gitmedi — bu kol o sınıfı kilitler.)"""
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200, r.text[:200]

    def _patlak(*_a, **_k):
        raise RuntimeError("test: ek bobin tespiti patladi")

    monkeypatch.setattr(o.api, "_seans_disi_calisan_bobinler", _patlak)
    r = o.c.post("/api/session/stop")
    assert r.status_code == 200, f"ek tespit hatası seans durdurmayı düşürdü: {r.status_code} {r.text[:200]}"
    assert not ap.calisan(o) and all(x == 0 for x in _son_duty(o)), "ek tespit hatasında seansın bobinleri DURMADI"


def test_KARSIT_Y63_CALISMAYAN_bobine_STOP_yok_broker_oluyken_SAHTE_alarm_yok(o, monkeypatch):
    """ESP açık + broker ölü: seans yalnız 1-2'yi sürer; bobin 8 hiç çalışmadı → STOP denenmez, teyitsiz sayılmaz (409 yok)."""
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200, r.text[:200]
    denenen = []

    def _olu_broker(topic, payload):
        denenen.append((topic, dict(payload)))
        return False

    monkeypatch.setattr(o.api, "_mqtt_publish", _olu_broker)
    r = o.c.post("/api/session/stop")
    assert r.status_code == 200, (
        f"çalışmamış bobin için sahte 'STOP DOĞRULANAMADI' alarmı ({r.status_code}): {r.text[:240]} denenen={denenen}"
    )
    assert not [t for t, p in denenen if t == "pemf/coil/8/control"], f"çalışmayan bobin 8'e STOP denendi: {denenen}"
    assert all(x == 0 for x in _son_duty(o)) and not ap.calisan(o), "seansın kendi bobinleri durmadı"


# ── 1-G inceleme G-2.1: üç kaynağın HER BİRİ tek başına belirleyici ─────────────────────────────────────────────────────
# Yukarıdaki senaryoda seans dışı bobinler seans SÜRERKEN başlatıldığı için üçünün de açık koşu kaydı var → HC ve ESP
# canlı-durum kaynakları o kayıtla MASKELİ: ikisini ayrı ayrı söken mutant 5/5 yeşil kaldı (ölçüldü).


def test_KRITIK_Y63_HC_TEK_kaynak_SEANS_ONCESI_tekil_baslatilan_bobin_de_DURUR(o):
    """Seans yokken tekil başlatılan bobinin koşu kaydı AÇILMAZ (`_begin_coil_run` seans satırı ister); seans [1,2] sonra
    başlar. Bobin 3'ün çalıştığını yalnız HC (`coils_state.is_running`) bilir."""
    rb = o.c.post("/api/coil/3/control", json=_TEKIL)
    assert rb.status_code == 200 and rb.json().get("status") == "success", f"aparat: bobin 3 {rb.text[:160]}"
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    assert sorted(ap.calisan(o)) == [1, 2, 3], f"aparat: telde çalışan {ap.calisan(o)}"
    with o.api._active_coil_runs_lock:
        assert 3 not in o.api._active_coil_runs, (
            f"aparat: bobin 3'ün koşu kaydı VAR (HC tek kaynak değil): {o.api._active_coil_runs}"
        )
    o.c.post("/api/session/stop")
    assert not ap.calisan(o) and all(x == 0 for x in _son_duty(o)), (
        f"seans ÖNCESİ tekil başlatılan bobin 3 'Seansı Durdur'dan sonra hâlâ SÜRÜLÜYOR: çalışan={ap.calisan(o)}"
    )


def test_KRITIK_Y63_ESP_CANLI_DURUM_TEK_kaynak_NVS_devamindaki_bobin_8_STOP_alir(o):
    """ESP durum iletisi bobin 8'i çalışıyor bildiriyor (NVS devamı — backend komutu da koşu kaydı da YOK). Bunu yalnız
    ESP canlı durumu (`_live_state["coils"][7]["running"]`) bilir."""
    r = o.c.post("/api/session/start", json=_SEANS)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]
    with o.api._live_state_lock:
        c8 = o.api._live_state["coils"][7]
        assert int(c8.get("id") or 0) == 8, f"aparat: live_state dizini {c8}"
        c8["running"] = True
    try:
        with o.api._active_coil_runs_lock:
            assert 8 not in o.api._active_coil_runs, "aparat: bobin 8'in koşu kaydı VAR (ESP kaynağı tek değil)"
        n = len(o.yayin)
        o.c.post("/api/session/stop")
        stoplar = [t for t, p in o.yayin[n:] if p.get("command") == "stop"]
        assert "pemf/coil/8/control" in stoplar, f"ESP durumuna göre çalışan bobin 8'e STOP yayınlanmadı: {o.yayin[n:]}"
    finally:
        with o.api._live_state_lock:
            o.api._live_state["coils"][7]["running"] = False  # modül geneli canlı durum sonraki testlere sızmasın
