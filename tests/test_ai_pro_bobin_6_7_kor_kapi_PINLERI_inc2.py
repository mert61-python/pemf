# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.83/D1.84 incelemesi (İNCELEME-2 i1) — 6-7 STM'e geçince KÖR kalan kapıların PİNLERİ (yalnız test).

Ölçülen körlük (`60567e4`, i1'in 20 dosyalık odak kapı kümesi + kendi mutantlarım; GERÇEK HC + kayıtçı kuyruk):
  * M1 `_drive_coils_ai_pro` sürücü istisnası atan bobini "sürüldü" sayar → 330/330 YEŞİL;
  * M2 `/frame` yanıtı sürüş GEÇERLİLİĞİNİ yok sayar (sürüş sırasında gelen acil durdurmadan sonra da "sürüldü") → 330/330 YEŞİL;
  * M6 `/ai/pro/stop` STOP kapsamından 6-7 düşer (eski "6-7 ESP'de, ölü" varsayımı) → 330/330 YEŞİL.
Her pin kendi mutantında KIRMIZI ölçüldü (`kayit/i1m_*`). Ürün davranışı bugün doğru — bu dosya yalnız gerilemeyi kilitler.
Yeni durdurma/engelleme/kıskaç YOK (A-47, Ö.4-Y8, Ö.4-Y9).
"""

from __future__ import annotations

import ai_pro_aparati as ap
import pytest

D7 = [0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
P7 = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
_KAYIP = (False, 0.0, 0.0, 0.0, 0.0, None, True)


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: (list(D7), list(P7), 0.5))
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.c.post("/api/ai/pro/stop")
        if ns.hc is not None:
            ns.hc.stop_all_coils()
        ns.geri()


def _suruldu(pc) -> set:
    return {c["id"] for c in pc or [] if c.get("suruldu") is True}


def _duty(pc) -> dict:
    return {c["id"]: c["duty"] for c in pc or []}


def test_KRITIK_surucu_ISTISNASI_atan_bobin_SURULDU_sayilmaz_digerleri_surulur(o, monkeypatch):
    """İNCELEME-2 (i1 M1 mutantı mevcut 20 kapı dosyasında 330/330 YEŞİLDİ): `update_coil` bobin 6'da istisna atarsa 6
    "sürüldü" DEĞİLDİR (telde çalışmıyor), diğer 6 bobin sürülür ve kare "sürüldü" der."""
    gercek = o.hc.update_coil

    def _alti_patlar(cid, *a, **k):
        if cid == 6 and k.get("start"):
            raise RuntimeError("test: bobin 6 sürücü istisnası")
        return gercek(cid, *a, **k)

    monkeypatch.setattr(o.hc, "update_coil", _alti_patlar)
    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    j = ap.kare(o).json()
    assert sorted(ap.calisan(o)) == [1, 2, 3, 4, 5, 7], ap.calisan(o)
    assert _suruldu(j["perCoil"]) == {1, 2, 3, 4, 5, 7} and j.get("driven") is True, (
        _suruldu(j["perCoil"]),
        j.get("driven"),
    )


@pytest.mark.parametrize("k", [5, 6])
def test_KRITIK_TUR_ORTASI_acil_durdurma_sonrasi_yanit_HICBIR_bobini_SURULDU_demez(o, monkeypatch, k):
    """İNCELEME-2 (i1 M2 mutantı — `/frame` `perCoil` sürüş GEÇERLİLİĞİNİ yok sayar — 20 kapı dosyasında 330/330 YEŞİLDİ):
    sürüş bobin k'yı (5: 1-5 sınırı, 6: D1.83 ile STM'e gelen bobin) kabul ettikten SONRA gelen ACİL DURDUR'da telde paket
    yok, çalışan yok ve yanıt hiçbir bobini "sürüldü" demez."""
    import threading

    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200, r.text[:200]
    gecti, devam = threading.Event(), threading.Event()
    orj = o.hc.update_coil

    def _sarili(cid, *a, **kw):
        sonuc = orj(cid, *a, **kw)
        if cid == k and kw.get("start", True) and not gecti.is_set():
            gecti.set()
            assert devam.wait(10)
        return sonuc

    monkeypatch.setattr(o.hc, "update_coil", _sarili)
    t, kutu = ap.kare_arka_planda(o)
    assert gecti.wait(10), "aparat: sürüş bobin k'ya ulaşmadı"
    o.api._emergency_stop_all("manual")
    sonra = ap.paket_sayisi(o)
    devam.set()
    t.join(15)
    j = kutu["yanit"].json()
    assert not ap.surus_paketleri(o, sonra) and ap.calisan(o) == [], (ap.surus_paketleri(o, sonra), ap.calisan(o))
    assert j.get("driven") is not True and _suruldu(j.get("perCoil")) == set(), (
        j.get("driven"),
        _suruldu(j.get("perCoil")),
    )


@pytest.mark.parametrize("kosul", ["normal", "stm_kopuk", "mandal"])
def test_KRITIK_AI_PRO_DURDUR_yedi_bobinin_HEPSINI_6_7_dahil_durdurur(o, kosul):
    """İNCELEME-2 (i1 M6 mutantı — `/ai/pro/stop` STOP kapsamından 6-7 düşer — 20 kapı dosyasında 330/330 YEŞİLDİ): D1.83'ten
    beri 6-7 STM'de sürülüyor; operatörün AI Pro Durdur'u (STM kopukken ve mandal kuruluyken de — Ö.4-Y8: STOP kapılanmaz)
    yedi bobinin HEPSİNİ durdurur, son paket 7×0."""
    from kayitci_donanim import paket_coz
    from servers import live_state
    from utils import estop_mandali

    _pid, r = ap.onayli_baslat(o, organ=2)
    assert r.status_code == 200
    assert ap.kare(o).json().get("driven") is True and sorted(ap.calisan(o)) == list(range(1, 8))
    if kosul == "stm_kopuk":
        with live_state._live_state_lock:
            live_state._live_state["stm"] = "offline"
    elif kosul == "mandal":
        estop_mandali.mandalla("test")
    once = ap.paket_sayisi(o)
    rs = o.c.post("/api/ai/pro/stop")
    assert rs.status_code == 200, rs.text[:200]
    son = tuple(paket_coz(o.hc.core._hw_send_queue.paketler[-1])[0])[:7]
    assert ap.calisan(o) == [] and ap.paket_sayisi(o) > once and son == (0.0,) * 7, (ap.calisan(o), son)
