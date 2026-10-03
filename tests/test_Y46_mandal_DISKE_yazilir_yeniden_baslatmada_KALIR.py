# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y46 (sahip, 1-C §9 S2) — ACİL DURDUR mandalı DİSKE yazılır; yeniden başlatmada "Sıfırla"ya basılana kadar KURULU kalır.

Kurallar (SAHIP-CEVAPLARI Y46): dosya STOP'lar gönderildikten SONRA yazılır; yazma başarısız olursa ACİL DURDUR'u asla
geciktirmez ya da engellemez (yalnız günlük); açılışta mandal kuruluysa bant nedeniyle gösterilir ("önceki oturumda ACİL
DURDUR — sıfırlanmadı").

ÖLÇÜLEN KUSUR: mandal yalnız BELLEKTEYDİ — süreç yeniden başlayınca (çökme, launcher/servis yeniden başlatması,
güncelleme) Sıfırla'sız kalkıyordu (Y4 lafzı: "bilinçli Sıfırla olmadan hiçbir START").

GERÇEK yeniden başlatma: E-stop'tan sonra AYRI bir Python süreci aynı veri kökünde ürünün açılış bağlantısını
(`backend_service._wire_api_server`) koşar ve mandalı okur. Çocukta ağ bekçisi (`alt_surec_ag_bekcisi`) ürün importundan
ÖNCE yüklenir; engellenen ağ denemesi = [] ölçülür.
"""

from __future__ import annotations

import json
import os
import stat
import threading
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
print("SONUC=" + json.dumps({{"durum": estop_mandali.durum(), "engel": estop_mandali.baslatma_engeli(),
                             "mandal_mesaji": estop_mandali.MANDAL_MESAJI, "ag": list(_ag.ENGELLENEN)}}))
"""


def _yeniden_baslat(veri: Path, tmp_path: Path) -> dict:
    """Ayrı süreçte ürünün açılış bağlantısını koş; mandal durumunu döndür."""
    betik = tmp_path / "yeniden_baslat.py"
    betik.write_text(
        _COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), veri=str(veri)), encoding="utf-8"
    )
    r = kostur([str(betik)], cwd=tmp_path, env=yalitik_ortam(tmp_path / "ev"), sure=180)
    satir = [s for s in r.stdout.splitlines() if s.startswith("SONUC=")]
    assert satir, f"cocuk surec sonuc vermedi (rc={r.returncode}): {r.stdout[-800:]} {r.stderr[-1500:]}"
    sonuc = json.loads(satir[-1][len("SONUC=") :])
    assert sonuc["ag"] == [], f"cocuk surec aga cikmaya calisti: {sonuc['ag']}"
    return sonuc


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

    class _SahteHC:
        coils_state = {b: {"is_running": False} for b in TUM_STM}

        def stop_all_coils(self):
            olaylar.append(("stop", "stm"))
            return True

        def update_coil(self, *a, **k):
            return True

        def on_disconnect(self):
            olaylar.append(("stop", "on_disconnect"))
            return True

    def _yayin(topic, payload):
        if payload.get("command") == "stop":
            olaylar.append(("stop", topic))
        return False

    orj_yaz = estop_mandali._diske_yaz

    def _kayitli_yaz():
        olaylar.append(("yaz", "disk"))
        return orj_yaz()

    monkeypatch.setattr(estop_mandali, "_diske_yaz", _kayitli_yaz)
    monkeypatch.setattr(api.state, "hardware", _SahteHC())
    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    with api._session_lock:
        api._active_session.clear()
    veri = tmp_path / "veri"
    veri.mkdir()
    estop_mandali.kalicilik_kur(veri / _DOSYA)
    yield SimpleNamespace(api=api, mandal=estop_mandali, olaylar=olaylar, veri=veri, dosya=veri / _DOSYA)
    estop_mandali.kalicilik_kapat()


def _dosya_aktif(o):
    try:
        return json.loads(o.dosya.read_text(encoding="utf-8")).get("aktif")
    except (OSError, ValueError):
        return None


def test_KRITIK_estop_mandali_STOPlardan_SONRA_diske_yazilir_ve_YENIDEN_BASLATMADA_kalir(ortam, tmp_path):
    o = ortam
    o.api._emergency_stop_all("manual")
    assert _bekle(lambda: _dosya_aktif(o) is True), "E-stop sonrasi mandal diske YAZILMADI"
    stoplar = [i for i, (t, _n) in enumerate(o.olaylar) if t == "stop"]
    yazim = [i for i, (t, _n) in enumerate(o.olaylar) if t == "yaz"]
    assert stoplar and yazim, f"aparat: olay kaydi eksik {o.olaylar}"
    assert yazim[0] > max(stoplar), f"mandal dosyasi STOP'lardan ONCE yazildi: {o.olaylar}"
    assert any(n == f"pemf/coil/{ESP_BOBIN}/control" for t, n in o.olaylar if t == "stop"), "aparat: ESP STOP yok"

    sonuc = _yeniden_baslat(o.veri, tmp_path)  # GERÇEK yeniden başlatma
    assert sonuc["durum"]["aktif"] is True, "yeniden baslatmada mandal KALKTI (Y46)"
    assert sonuc["durum"]["oncekiOturum"] is True
    assert sonuc["durum"]["neden"].startswith("onceki_oturum:manual"), sonuc["durum"]
    assert sonuc["engel"] == sonuc["mandal_mesaji"], "yeniden baslatmadan sonra START Sifirla'siz GECTI"


def test_KRITIK_Sifirla_diske_yazilir_yeniden_baslatmada_mandal_GELMEZ(ortam, tmp_path):
    o = ortam
    o.api._emergency_stop_all("manual")
    assert _bekle(lambda: _dosya_aktif(o) is True)
    c = TestClient(o.api.app)
    r = c.post("/api/hardware/estop_mandali/sifirla", json={"onay": True})
    assert r.status_code == 200, r.text
    assert _bekle(lambda: _dosya_aktif(o) is False), "Sifirla diske yazilmadi"
    sonuc = _yeniden_baslat(o.veri, tmp_path)
    assert sonuc["durum"]["aktif"] is False, "Sifirla'dan sonra yeniden baslatmada mandal GERI GELDI"
    assert sonuc["engel"] == ""


def test_KRITIK_yazma_HATASI_ve_ASILI_disk_acil_durdurmayi_GECIKTIRMEZ_ENGELLEMEZ(ortam, monkeypatch):
    o = ortam
    serbest = threading.Event()

    def _asili_yaz():
        o.olaylar.append(("yaz", "asili"))
        serbest.wait(10)  # askıdaki disk (ağ sürücüsü / kilit); gerçek `_diske_yaz` asla fırlatmaz
        return False

    monkeypatch.setattr(o.mandal, "_diske_yaz", _asili_yaz)
    t0 = time.monotonic()
    sonuc = o.api._emergency_stop_all("manual")
    sure = time.monotonic() - t0
    serbest.set()
    assert sure < 2.0, f"askidaki disk yazimi ACIL DURDUR'u {sure:.2f} sn geciktirdi"
    assert any(t == "stop" for t, _n in o.olaylar), "STOP gitmedi"
    assert o.mandal.mandalli_mi() is True, "yazma hatasi bellekteki mandali dusurdu"
    assert sonuc.get("estopMandali", {}).get("aktif") is True


def test_KRITIK_salt_okunur_dosya_yazamaz_ama_acil_durdur_ve_mandal_SURER(ortam):
    o = ortam
    o.dosya.write_text(json.dumps({"aktif": False}), encoding="utf-8")
    os.chmod(o.dosya, stat.S_IREAD)
    try:
        sonuc = o.api._emergency_stop_all("manual")
        time.sleep(0.3)
        assert any(t == "stop" for t, _n in o.olaylar)
        assert o.mandal.mandalli_mi() is True
        assert sonuc.get("estopMandali", {}).get("aktif") is True
    finally:
        os.chmod(o.dosya, stat.S_IREAD | stat.S_IWRITE)


def test_KRITIK_bozuk_mandal_dosyasi_acilista_mandal_KURULU_sayilir(tmp_path):
    from utils import estop_mandali

    veri = tmp_path / "veri"
    veri.mkdir()
    (veri / _DOSYA).write_text("{bozuk json", encoding="utf-8")
    sonuc = _yeniden_baslat(veri, tmp_path)
    assert sonuc["durum"]["aktif"] is True, "okunamayan mandal dosyasi 'mandal yok' sayildi (guvenli taraf: kurulu)"
    assert "dosya_okunamadi" in sonuc["durum"]["neden"]
    estop_mandali.kalicilik_kapat()


def test_KARSIT_dosya_YOKSA_acilista_mandal_yok(tmp_path):
    veri = tmp_path / "veri"
    veri.mkdir()
    sonuc = _yeniden_baslat(veri, tmp_path)
    assert sonuc["durum"]["aktif"] is False
    assert sonuc["engel"] == ""


def test_KRITIK_Y45_seanssiz_kopma_mandali_da_diske_yazilir(ortam):
    o = ortam
    o.api.state.hardware.coils_state[min(TUM_STM)]["is_running"] = True
    try:
        o.api._handle_backend_event(SimpleNamespace(event_type="hardware.stm.disconnected", data={}))
    finally:
        o.api.state.hardware.coils_state[min(TUM_STM)]["is_running"] = False
    assert o.mandal.mandalli_mi() is True
    assert _bekle(lambda: _dosya_aktif(o) is True), "Y45 mandali diske yazilmadi"
    yazim = next(i for i, (t, _n) in enumerate(o.olaylar) if t == "yaz")
    stop = next(i for i, (t, _n) in enumerate(o.olaylar) if t == "stop")
    assert stop < yazim, f"dosya STOP'tan ONCE yazildi: {o.olaylar}"
