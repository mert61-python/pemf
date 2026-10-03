# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.89 · B-6.27 (+ İNCELEME-2 §10 #5 · İG-6.47 sınıfı) — backend yarısı: kayıt görünümlerinin okuduğu veri, reçete ile
ÖLÇÜLENİ ayırır; AI Pro'nun bobin 1 duty'si mT alanına YAZILMAZ.

ÖLÇÜLEN KUSURLAR:
  1. `coil_run_tracker._finish_coil_run` hiç ölçülmemiş metriğe (yorumu "None" derken) 0.0 yazıyordu → koşunun
     ölçülen alanı gösterilince ölçülmemiş bobin "0.00 mT ölçüldü" görünürdü (plan C1b-77 UYANMA).
  2. AI Pro canlı durumu bobin 1 plan duty'sini (%) `intensityMt`e yazıyordu → Ana Ekran / seans kartı "37 mT".

Arayüz fikstürü `apps/ui/src/screens/__tests__/__fixtures__/kayitGorunumu.D189.json` GERÇEK uçlardan üretilir (elle seans:
`/api/session/start` reçete 1,5 mT → gerçek dakika birikimi `_emit_minute_averages` (bobin A alan 0,8 mT ölçer, bobin B
yalnız akım) → `/api/session/stop` → `/api/session/notes` → `/api/history/` + `/details`; AI Pro: gerçek onay akışı +
gerçek `/frame`). Bayatlarsa `test_arayuz_fiksturu_GERCEK_yanitlarla_AYNI` KIRMIZI olur; yeniden üretmek için
`D189_FIKSTUR_YAZ=1`. Sahte olan: örnekleyici döngüsünün kendisi (sonsuz döngü + 2 sn uyku) — onun her turda kurduğu
dakika birikimi aynı yapıyla doğrudan kurulur; AI Pro'da görüntü/lokalizasyon/doz modeli (aparat).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import ai_pro_aparati as ap
import pytest
from topoloji import TUM_STM

_KOK = Path(__file__).resolve().parents[1]
_FIKSTUR = _KOK / "apps" / "ui" / "src" / "screens" / "__tests__" / "__fixtures__" / "kayitGorunumu.D189.json"
_A, _B = sorted(TUM_STM)[:2]
_RECETE = 1.5
_OLCULEN = 0.8


def _kararli(v, anahtar: str = ""):
    """Zamana/kimliğe bağlı alanlar sabitlenir (fikstür karşılaştırması kararlı olsun); değer TÜRÜ korunur."""
    if isinstance(v, dict):
        return {k: _kararli(x, k) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_kararli(x, anahtar) for x in v]
    a = anahtar.lower()
    if v is None or isinstance(v, bool):
        return v
    if a in ("id", "session_id", "coil_run_id", "patient_id", "db_session_id", "surus_nesli", "onay_kimligi"):
        return 1 if isinstance(v, (int, float)) else "SABIT"
    if any(
        p in a
        for p in ("date", "time", "epoch", "_at", "sample_ts", "duration_seconds", "elapsed", "remaining", "mono")
    ):
        return 0 if isinstance(v, (int, float)) else "SABIT"
    return v


@pytest.fixture
def kayit(monkeypatch, tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import coil_run_tracker, history_router

    db = TreatmentHistoryDB(tmp_path)
    monkeypatch.setattr(api, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(coil_run_tracker, "_treatment_db_getter", lambda: db)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    import database.treatment_history_db as thdb

    monkeypatch.setattr(thdb, "get_treatment_db", lambda *_a, **_k: db)
    api.app.dependency_overrides[history_router.get_db] = lambda: db
    with api._session_lock:
        eski = dict(api._active_session)
        api._active_session.clear()
    with api._minute_acc_lock:
        api._minute_acc.clear()
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(api.state, "hardware", hc)
            monkeypatch.setattr(api.state, "core", hc.core)
            c = TestClient(api.app)
            try:
                yield api, c
            finally:
                c.post("/api/session/stop")
    finally:
        api.app.dependency_overrides.pop(history_router.get_db, None)
        with api._minute_acc_lock:
            api._minute_acc.clear()
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


def _birikim(alan: float | None, akim: float | None) -> dict:
    """`_sensor_persistence_loop`un bir bobin için kurduğu dakika birikimi (aynı anahtarlar; 3 örnek)."""
    n = 3
    return {
        "t_sum": 0.0, "t_min": None, "t_max": None, "i_sum": (akim or 0.0) * n, "b_sum": (alan or 0.0) * n,
        "amb_sum": 0.0, "n": n, "t_n": 0, "i_n": n if akim is not None else 0, "b_n": n if alan is not None else 0,
        "amb_n": 0, "freq": 100, "duty": 40.0, "phase": 0.0,
    }  # fmt: skip


def _elle_seans_kaydi(api, c) -> tuple[dict, dict, dict, dict]:
    r = c.post(
        "/api/session/start",
        json={
            "mode": "Manuel", "frequency": 100, "intensity": _RECETE, "duty": 40, "phase": 0,
            "duration_minutes": 5, "coil_ids": [_A, _B], "patient_name": "Pamuk",
        },
    )  # fmt: skip
    assert r.status_code == 200 and r.json().get("status") == "success", f"aparat: seans baslamadi {r.text[:300]}"
    # Canlı: STM sensörünün ölçtüğü alan (telemetri işleyicisinin çağırdığı GERÇEK yazıcı).
    api.update_measured_intensity(_OLCULEN, _A, _OLCULEN)
    with api._live_state_lock:
        canli = dict(api._live_state["activeTreatment"])
    aktif = c.get("/api/session/active").json()  # Kontrol ekranı açılışta bunu okur (`useSessionControl`)
    with api._minute_acc_lock:
        api._minute_acc[_A] = _birikim(alan=_OLCULEN, akim=0.4)
        api._minute_acc[_B] = _birikim(alan=None, akim=0.4)  # bobin B alan ÖLÇMEZ
    api._emit_minute_averages(time.time())
    assert c.post("/api/session/stop").status_code == 200
    n = c.post(
        "/api/session/notes",
        json={"notes": "", "patient_name": "Pamuk", "mode": "Manuel", "frequency": 100, "intensity": _RECETE},
    )
    assert n.status_code == 200, n.text[:300]
    liste = c.get("/api/history/?limit=20")
    assert liste.status_code == 200, liste.text[:300]
    oge = liste.json()[0]
    detay = c.get(f"/api/history/{oge['id']}/details")
    assert detay.status_code == 200, detay.text[:300]
    return oge, detay.json(), canli, aktif


def test_KRITIK_kosu_ozeti_OLCULMEYEN_alani_None_yazar_olculeni_yazar(kayit):
    api, c = kayit
    oge, detay, _canli, _aktif = _elle_seans_kaydi(api, c)
    assert oge.get("intensity_mt") == pytest.approx(_RECETE), f"recete kayda girmedi: {oge.get('intensity_mt')}"
    kosu = {k["coil_id"]: k for k in detay["coil_runs"]}
    assert kosu[_A]["summary"]["field_avg"] == pytest.approx(_OLCULEN), kosu[_A]["summary"]
    assert kosu[_B]["summary"]["field_avg"] is None, f"olculmemis alan 'olculdu' diye yazildi: {kosu[_B]['summary']}"
    assert kosu[_B]["summary"]["temp_avg"] is None, kosu[_B]["summary"]
    assert kosu[_B]["summary"]["current_avg"] == pytest.approx(0.4), "olculen akim kayboldu (KARSIT)"


def _ai_pro_canli(monkeypatch, tmp_path) -> tuple[dict, dict]:
    """GERÇEK onay akışı + GERÇEK `/frame` + GERÇEK `HardwareController` (sürüş kabul edilmezse canlı durum yazılmaz)."""
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            try:
                _pid, r = ap.onayli_baslat(ns, sure_dk=5)
                assert r.status_code == 200, f"aparat: AI Pro baslamadi {r.status_code} {r.text[:200]}"
                assert ap.kare(ns).status_code == 200
                assert ap.calisan(ns), "aparat: AI Pro hicbir bobini surmedi"
                return dict(ns.api._live_state["activeTreatment"]), ns.c.get("/api/session/active").json()
            finally:
                ns.c.post("/api/ai/pro/stop")
                hc.stop_all_coils()
    finally:
        ns.geri()


def test_KRITIK_AI_Pro_bobin1_dutysi_mT_alanina_YAZILMAZ(monkeypatch, tmp_path):
    at, _aktif = _ai_pro_canli(monkeypatch, tmp_path)
    assert at.get("isActive") is True and str(at.get("mode", "")).startswith("AI Pro"), at
    assert not at.get("intensityMt"), f"AI Pro duty'si mT recete alanina yazildi: intensityMt={at.get('intensityMt')}"
    assert isinstance(at.get("dutyTemsilYuzde"), (int, float)) and at["dutyTemsilYuzde"] > 0, at


def test_arayuz_fiksturu_GERCEK_yanitlarla_AYNI(kayit, monkeypatch, tmp_path):
    api, c = kayit
    oge, detay, canli, aktif = _elle_seans_kaydi(api, c)
    canli_ai, aktif_ai = _ai_pro_canli(monkeypatch, tmp_path)
    uretilen = _kararli(
        {
            "listeOgesi": oge, "detay": detay, "canliElle": canli, "aktifElle": aktif,
            "canliAiPro": canli_ai, "aktifAiPro": aktif_ai,
        }
    )  # fmt: skip
    metin = json.dumps(uretilen, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("D189_FIKSTUR_YAZ") == "1":
        _FIKSTUR.write_text(metin, encoding="utf-8")
    assert _FIKSTUR.exists(), "arayuz fiksturu yok (D189_FIKSTUR_YAZ=1 ile uret)"
    assert json.loads(_FIKSTUR.read_text(encoding="utf-8")) == json.loads(metin), (
        "arayuz fiksturu BAYAT: gercek backend yaniti degisti (D189_FIKSTUR_YAZ=1 ile yeniden uret ve jest kapisini kos)"
    )


def test_KRITIK_AI_Pro_DONGUSU_de_duty_mT_alanina_YAZMAZ(monkeypatch, tmp_path):
    """1-E incelemesi (i-10.1): D1.89 AI Pro'nun İKİ yazım noktasını düzeltti (`/frame` + masaüstü döngüsü `_ai_pro_loop`) ama
    kapı yalnız `/frame`'i koşuyordu — döngünün yazımını `intensity=rep_duty`'ye geri alan mutant 15 dosyada 133/133 YEŞİL
    kaldı. GERÇEK onay akışı + GERÇEK `_ai_pro_loop` (sahte kamera + sahte doz planı) + GERÇEK `live_state`."""
    import numpy as np
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef
    from servers import live_state as ls

    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    monkeypatch.setattr(ns.air, "_predict_and_drive", lambda *a, **k: ([0.37] * 7, [0.0] * 7, 0.5))
    monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)  # em_kedi ağırlığı depoda yok

    class _Kamera:
        def __init__(self, *a, **k):
            pass

        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
    hc_ctx = gercek_hc()
    ns.hc = hc_ctx.__enter__()
    monkeypatch.setattr(ns.api.state, "hardware", ns.hc)
    try:
        _pid, r = ap.onayli_baslat(ns, organ=2)
        assert r.status_code == 200, r.text[:200]

        def _dongu_yazdi():
            with ls._live_state_lock:
                at = dict(ls._live_state["activeTreatment"])
            return at if at.get("dutyTemsilYuzde") else None

        assert ap.bekle(lambda: _dongu_yazdi() is not None, 8), "aparat: dongu canli seans durumunu yazmadi"
        at = _dongu_yazdi()
        assert str(at.get("mode", "")).startswith("AI Pro"), at
        assert not at.get("intensityMt"), (
            f"AI Pro DONGUSU duty'yi mT recete alanina yazdi: intensityMt={at.get('intensityMt')}"
        )
    finally:
        ns.air._ai_loop_active = False
        ap.bekle(lambda: False, 1.5)
        ns.hc.stop_all_coils()
        hc_ctx.__exit__(None, None, None)
        ns.geri()
