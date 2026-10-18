# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Launcher KAPANIŞ durdurması — boşta kapanış "önceki oturumda ACİL DURDUR" bandı DOĞURMAZ (sahip bildirimi 2026-10-18).

Sahip: "uygulama ilk açılışta niye bu uyarıyı veriyor daha yeni açtık. bunu düzelt sürekli çıkmasın." Bant: "ACİL DURDURMA
MANDALLI … Neden: önceki oturumda ACİL DURDUR — sıfırlanmadı (ACİL DURDUR düğmesi)".
ÖLÇÜLEN KÖK NEDEN: bu makinenin mandal dosyası `{"aktif": true, "neden": "manual"}` 13.10 20:22:26'da — launcher'ın pencere
kapanışında yazıldı. Launcher (`backend.rs::safe_stop_coils`) backend'i öldürmeden önce operatörün ACİL DURDUR ucunu çağırıyordu
→ `_emergency_stop_all("manual")` mandalı kurup DİSKE yazıyor (Y46) → HER temiz kapanıştan sonraki açılışta bant + Sıfırla'sız
START reddi. Temiz kapanış acil durdurma DEĞİLDİR (D1.75 `kapanis_kur` ilkesi).

SÖZLEŞME (`POST /api/hardware/kapanis_durdur`):
  · STOP'lar ACİL DURDUR'la AYNI (STM + ESP; Ö.4-Y8) ve bellekteki mandal kurulur (öldürmeye dek START reddi);
  · BOŞTA → mandal DİSKE YAZILMAZ → GERÇEK yeniden başlatmada mandal YOK;
  · bobin çalışıyor / seans sürüyor / durum okunamıyor → DİSKE yazılır (gerçek kesinti; Y45 ilkesi) → yeniden başlatmada KURULU;
  · daha önce kurulup sıfırlanmamış operatör mandalı KORUNUR (disk değişmez);
  · yalnız loopback + `{"onay": true}` JSON; aksi hâlde STOP da mandal da YOK (launcher ACİL DURDUR ucuna düşer).
GERÇEK yeniden başlatma: ayrı Python süreci aynı veri kökünde ürünün açılış bağlantısını (`backend_service._wire_api_server`) koşar.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from betik_alt_sureci import kostur, yalitik_ortam
from fastapi.testclient import TestClient
from topoloji import ESP_BOBIN, TUM_STM

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
_DOSYA = "estop_mandali.json"
_UC = "/api/hardware/kapanis_durdur"

_COCUK = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json
sys.path[:0] = [{kok!r}, {backend!r}]
from types import SimpleNamespace
import backend_service
from utils import estop_mandali
backend_service._wire_api_server(SimpleNamespace(app_data_dir={veri!r}))
print("SONUC=" + json.dumps({{"durum": estop_mandali.durum(), "ag": list(_ag.ENGELLENEN)}}))
"""


def _yeniden_baslat(veri: Path, tmp_path: Path) -> dict:
    betik = tmp_path / "yeniden_baslat.py"
    betik.write_text(
        _COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), veri=str(veri)), encoding="utf-8"
    )
    r = kostur([str(betik)], cwd=tmp_path, env=yalitik_ortam(tmp_path / "ev"), sure=180)
    satir = [s for s in r.stdout.splitlines() if s.startswith("SONUC=")]
    assert satir, f"cocuk surec sonuc vermedi (rc={r.returncode}): {r.stdout[-800:]} {r.stderr[-1500:]}"
    sonuc = json.loads(satir[-1][len("SONUC=") :])
    assert sonuc["ag"] == [], f"cocuk surec aga cikmaya calisti: {sonuc['ag']}"
    return sonuc["durum"]


def _bekle(kosul, sure=3.0) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.02)
    return kosul()


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from servers import api_server as api
    from utils import estop_mandali

    olaylar: list = []
    calisan = {"bobin": False}

    class _SahteHC:
        @property
        def coils_state(self):
            if calisan["bobin"] == "okunamaz":
                raise RuntimeError("durum okunamadi")
            return {b: {"is_running": bool(calisan["bobin"]) and b == TUM_STM[0]} for b in TUM_STM}

        def stop_all_coils(self):
            olaylar.append(("stop", "stm"))
            return True

        def update_coil(self, *a, **k):
            return True

    def _yayin(topic, payload):
        if payload.get("command") == "stop":
            olaylar.append(("stop", topic))
        return False

    orj_yaz = estop_mandali._diske_yaz

    def _kayitli_yaz(*a, **k):
        olaylar.append(("yaz", "disk"))
        return orj_yaz(*a, **k)

    monkeypatch.setattr(estop_mandali, "_diske_yaz", _kayitli_yaz)
    monkeypatch.setattr(api.state, "hardware", _SahteHC())
    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: olaylar.append(("bildirim", a[0] if a else "")))
    with api._session_lock:
        api._active_session.clear()
    estop_mandali.sifirla("test")
    veri = tmp_path / "veri"
    veri.mkdir()
    estop_mandali.kalicilik_kur(veri / _DOSYA)
    c = TestClient(api.app, client=("127.0.0.1", 51241))
    yield SimpleNamespace(
        api=api, mandal=estop_mandali, olaylar=olaylar, veri=veri, dosya=veri / _DOSYA, c=c, calisan=calisan
    )
    estop_mandali.kalicilik_kapat()
    estop_mandali.sifirla("test")
    with api._session_lock:
        api._active_session.clear()


def _dosya_aktif(o):
    try:
        return json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif")
    except (OSError, ValueError):
        return None


def _stoplar(o) -> list:
    return [n for t, n in o.olaylar if t == "stop"]


def _kapanis(o, **k):
    return o.c.post(_UC, json={"onay": True}, **k)


def test_KRITIK_BOSTA_kapanis_STOPlari_gonderir_ama_mandal_DISKE_yazilmaz_yeniden_acilista_BANT_YOK(ortam, tmp_path):
    o = ortam
    r = _kapanis(o)
    assert r.status_code == 200, r.text
    assert r.json()["mandalKalici"] is False and "confirmed" in r.json(), r.json()
    assert "stm" in _stoplar(o) and f"pemf/coil/{ESP_BOBIN}/control" in _stoplar(o), f"STOP gitmedi: {o.olaylar}"
    assert o.mandal.mandalli_mi() is True, "kapanış durdurmasından sonra (öldürmeye dek) START REDDEDİLMİYOR"
    time.sleep(0.5)
    assert ("yaz", "disk") not in o.olaylar and not o.dosya.exists(), "boşta kapanış mandalı DİSKE yazdı"
    durum = _yeniden_baslat(o.veri, tmp_path)  # GERÇEK yeniden başlatma
    assert durum["aktif"] is False, f"boşta kapanıştan sonra açılışta mandal (bant) GELDİ: {durum}"


@pytest.mark.parametrize("hal", ["bobin", "seans", "okunamaz"])
def test_KRITIK_bobin_calisirken_ya_da_seans_surerken_kapanis_mandali_DISKE_yazar_yeniden_acilista_KURULU(
    ortam, tmp_path, hal
):
    o = ortam
    if hal == "seans":
        with o.api._session_lock:
            o.api._active_session.update(is_active=True, coil_ids=[1])
    else:
        o.calisan["bobin"] = True if hal == "bobin" else "okunamaz"
    r = _kapanis(o)
    assert r.status_code == 200, r.text
    assert r.json()["mandalKalici"] is True, r.json()
    assert "stm" in _stoplar(o)
    assert _bekle(lambda: _dosya_aktif(o) is True), f"{hal}: gerçek kesinti mandalı diske YAZILMADI"
    assert any(t == "bildirim" for t, _ in o.olaylar), "operatöre söylenmedi"
    if hal == "bobin":
        durum = _yeniden_baslat(o.veri, tmp_path)
        assert durum["aktif"] is True and durum["neden"] == "onceki_oturum:uygulama_kapanisi", durum


def test_KRITIK_SIFIRLANMAMIS_operator_mandali_bosta_kapanista_KORUNUR(ortam, tmp_path):
    o = ortam
    o.api._emergency_stop_all("manual")  # operatör ACİL DURDUR'a bastı, Sıfırla'ya basmadı
    assert _bekle(lambda: _dosya_aktif(o) is True)
    yazim_sayisi = o.olaylar.count(("yaz", "disk"))
    assert _kapanis(o).status_code == 200
    time.sleep(0.5)
    assert o.olaylar.count(("yaz", "disk")) == yazim_sayisi, "boşta kapanış diski yeniden yazdı"
    durum = _yeniden_baslat(o.veri, tmp_path)
    assert durum["aktif"] is True and durum["neden"] == "onceki_oturum:manual", f"operatörün mandalı kayboldu: {durum}"


@pytest.mark.parametrize(
    ("istemci", "govde", "baslik", "kod"),
    [
        (("192.168.1.20", 51242), {"onay": True}, None, 403),
        (("127.0.0.1", 51243), None, {"content-type": "text/plain"}, 415),
        (("127.0.0.1", 51244), {"onay": False}, None, 400),
    ],
)
def test_KRITIK_yalniz_loopback_ve_bilincli_onay_aksi_halde_STOP_da_mandal_da_YOK(ortam, istemci, govde, baslik, kod):
    o = ortam
    from fastapi.testclient import TestClient as _TC

    c = _TC(o.api.app, client=istemci)
    r = c.post(_UC, json=govde) if baslik is None else c.post(_UC, content=b"onay", headers=baslik)
    assert r.status_code == kod, (r.status_code, r.text)
    assert _stoplar(o) == [] and o.mandal.mandalli_mi() is False, (
        f"reddedilen istek durdurma / mandal yaptı: {o.olaylar}"
    )


def test_KARSIT_KANIT_operatorun_ACIL_DURDUR_ucu_DEGISMEDI_bosta_da_diske_yazar(ortam):
    o = ortam
    r = o.c.post("/api/hardware/emergency_stop")
    assert r.status_code == 200, r.text
    assert _bekle(lambda: _dosya_aktif(o) is True), "operatörün ACİL DURDUR'u artık diske yazmıyor (Y46 bozuldu)"
