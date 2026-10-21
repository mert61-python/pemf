# -*- coding: utf-8 -*-
"""I18NI-A1.1 — ACİL DURDUR MANDAL bandının EYLEM metni İngilizce kullanıcıya İngilizce ulaşabilmeli.

GERÇEK yol: `api_server._stm_red_aktif_seansi_durdur` (kart duty reddi / kart uyumsuzluğu → mandal eylemi bırakılır → E-stop yolu mandallar)
+ `estop_mandali.durum()` (WS anlık görüntüsüne ve `estop_mandali` iletisine AYNEN giden sözlük). Sahte: yalnız `_emergency_stop_async`
(gerçek STOP yerine yalnız `mandalla(reason)` — E-stop yolunun mandal kurma adımı) ve bildirim yakalayıcısı.

Sorun: WS yükü dil bilmez (her istemciye aynı); `eylem` Türkçe SABİT (bilinçli: TR bant bayt bayt aynı). Ama İngilizce karşılık HİÇ taşınmıyor
→ EN arayüz (`EstopMandalBandi.mandalEylemi`) Türkçe cümleyi İngilizce bandın ORTASINA basar. Beklenen (P1.4 `mesajlar` deseni): `eylem`
TR bayt bayt AYNI kalır + ek alan `eylemler = {"tr": eylem, "en": <İngilizce>}`.
Ürün düzelince YEŞİL; bugün KIRMIZI (`eylemler` yok).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Koşum yeri: tests/ (conftest — sahte veri kökü, apps/backend yolu). Kalıcı kapı adayı olarak tests/'e kopyalanır.
KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def _nack(bobin, istenen, tavan, kip):
    return f"-> STM_NACK: RANGE coil={bobin} field=duty value_milli={istenen} max_milli={tavan} kip={kip}"


@pytest.fixture
def seans(monkeypatch):
    from servers import api_server
    from utils import estop_mandali

    estop_mandali.sifirla("test")
    with api_server._session_lock:
        eski = dict(api_server._active_session)
        api_server._active_session["is_active"] = True
        api_server._active_session["coil_ids"] = [1]
    monkeypatch.setattr(
        api_server, "_emergency_stop_async", lambda reason="manual", mode="": estop_mandali.mandalla(reason)
    )
    monkeypatch.setattr(api_server, "_bildir", lambda uret, level="info": None)
    yield api_server, estop_mandali
    estop_mandali.sifirla("test")
    with api_server._session_lock:
        api_server._active_session.clear()
        api_server._active_session.update(eski)


@pytest.mark.parametrize(
    "ham",
    [_nack(1, 800, 500, "bipolar"), "-> STM_NACK: CRC"],
    ids=["duty_reddi", "kart_uyumsuzlugu"],
)
def test_mandal_eylemi_TR_ayni_EN_karsiligi_tasinir(seans, ham):
    api_server, em = seans
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set("en")  # EN istemci varken bile WS yükü tek
    try:
        assert api_server._stm_red_aktif_seansi_durdur(ham) is True
    finally:
        ceviri.istek_dili_var.reset(jeton)
    d = em.durum()
    assert d["aktif"] is True and d["neden"] == "stm_komut_reddi"
    tr = d["eylem"]
    assert tr and TR_HARF.search(tr), "TR eylem metni (göç öncesiyle aynı) korunmalı"
    eylemler = d.get("eylemler")
    assert isinstance(eylemler, dict), (
        "mandal eyleminin İngilizce karşılığı WS yüküne HİÇ girmiyor → EN bant Türkçe cümle basar: " + tr
    )
    assert eylemler.get("tr") == tr, "TR bayt bayt aynı olmalı"
    en = eylemler.get("en") or ""
    assert en and not TR_HARF.search(en), f"EN eylem Türkçe harf taşıyor: {en!r}"
