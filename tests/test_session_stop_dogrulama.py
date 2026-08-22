# Author: mertaygn, cglrgrkn
"""SEANS DURDURMADA DONANIM TEYİDİ — 2. tur denetimi bulgu [1.1] yan kalemi (2026-08-20).

ÖLÇÜLEN DURUM: `/api/session/stop`, `_stop_session_coils`in MQTT publish'leri TAMAMEN düşse bile
(broker ölü/yetim) KOŞULSUZ `{"status":"success"}` dönüyordu. `useSessionControl.stopSession`in
"Durdurma onaylanamadı — ACİL DURDUR'a basın" uyarısı yalnız `!res || status==="error"`e baktığı
için bu senaryoda HİÇ tetiklenmiyordu: STOP hiçbir bobine ulaşmamışken UI seansı "durdu" gösterir.

DÜZELTME SÖZLEŞMESİ: üst-seviye `status` DEĞİŞMEZ ("success" kalır — seans kaydı gerçekten
kapatıldı; mevcut çağıranlar kırılmasın). Donanım STOP'u DOĞRULANAMAYAN bobinler AYRI alanda
(`hardware_stop_unconfirmed`) açıkça listelenir; istemci bu alanı görünce operatörü uyarır.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app)


class _SahteStm:
    """`update_coil` çağrılarını sayan ve yapılandırılabilir sonuç dönen STM taklidi."""

    def __init__(self, sonuc: bool = True):
        self.sonuc = sonuc
        self.cagrilar: list = []

    def update_coil(self, coil_id, freq, duty, phase, dur_min, start=True, **kw):
        self.cagrilar.append((coil_id, start))
        return self.sonuc


@pytest.fixture()
def aktif_seans(api, monkeypatch):
    """DB'siz sentetik aktif seans kur; test sonrası _active_session eski hâline döner."""
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    with api._session_lock:
        eski = dict(api._active_session)

    def _kur(coil_ids):
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(
                {
                    "is_active": True,
                    "session_id": "test-stop-dogrulama",
                    "coil_ids": list(coil_ids),
                    "db_session_id": None,  # DB yolu test dışı (best-effort dal)
                    "started_epoch": None,
                }
            )

    yield _kur
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(eski)


def test_KRITIK_broker_ulasilmazken_yanit_teyitsiz_bobinleri_soyler(api, client, aktif_seans, monkeypatch):
    """Broker ölü → ESP STOP publish'leri düşer → yanıt bunu AÇIKÇA söylemeli."""
    aktif_seans([6, 7])
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)  # broker ölü
    monkeypatch.setattr(api.state, "hardware", None)

    r = client.post("/api/session/stop", json={})

    # ⚠️ SÖZLEŞME DEĞİŞTİ (2026-08-22) — GEVŞETME DEĞİL, SIKILAŞTIRMA.
    # Bu satır eskiden `status_code == 200` ve `status == "success"` bekliyordu; gerekçe
    # "seans kaydı kapandı, mevcut çağıranların sözleşmesi bozulmasın" idi. Sürüm kayması
    # senaryosu ÖLÇÜLDÜ ve o gerekçeyi çürüttü: telefon eski sürümde kalabilir (Android'de
    # kurulumu işletim sistemi sorar → güncelleme zorunlu kılınamaz) ve ESKİ istemci
    # `hardware_stop_unconfirmed` alanını TANIMAZ; kontrolü `res.status === "error"` olduğu
    # için 2xx'i koşulsuz BAŞARI sayar. Sonuç: bobinler hâlâ çalışırken operatöre düz
    # "seans durduruldu" gösteriliyordu — yani [1.1] düzeltmesi, ona en çok ihtiyacı olan
    # istemciye HİÇ ulaşmıyordu.
    # Uyarı artık eski istemcinin de YUTAMAYACAĞI kanaldan gider: 2xx DIŞI yanıt.
    # (207 Multi-Status DA 2xx'tir → `response.ok` true → kullanılamaz.)
    assert r.status_code == 409, (
        f"teyitsiz durdurma {r.status_code} döndü — 2xx ise eski istemci sessizce başarı sayar "
        "ve bobinler çalışırken 'durduruldu' gösterir (bulgu [1.1]'in nüksü)"
    )
    gövde = r.json()
    assert gövde.get("hardware_stop_unconfirmed") == [6, 7], (
        f"STOP hiçbir bobine ulaşmadı ama yanıt bunu söylemiyor: {gövde!r}"
    )
    # Eski istemcinin ekrana basabildiği TEK alan (apiClient: showError('Sunucu Hatası', detail)).
    assert "ACİL DURDUR" in (gövde.get("detail") or ""), (
        f"`detail` operatöre ne yapacağını söylemiyor: {gövde.get('detail')!r}"
    )
    # Seans KAYDI gerçekten kapandı — yeni istemci UI'da seansı yeniden 'açık' göstermemeli.
    assert gövde.get("session_closed") is True, "seans kaydının kapandığı yanıtta belirtilmiyor"


def test_KRITIK_stm_donanimi_yokken_stm_bobinleri_de_teyitsiz(api, client, aktif_seans, monkeypatch):
    """STM kontrolcüsü yoksa 1-5'e STOP HİÇ denenmez — 'sessizce atlandı' da teyitsizdir."""
    aktif_seans([1, 6])
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setattr(api.state, "hardware", None)

    gövde = client.post("/api/session/stop", json={}).json()
    assert gövde.get("hardware_stop_unconfirmed") == [1, 6], f"beklenen [1, 6], gelen: {gövde!r}"


def test_KARSIT_KANIT_hepsi_dogrulaninca_alan_hic_yok(api, client, aktif_seans, monkeypatch):
    """Mutlu yol: publish PUBACK'li, STM update_coil True → alan YOK (yanlış alarm üretme)."""
    aktif_seans([1, 6])
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api.state, "hardware", _SahteStm(sonuc=True))

    gövde = client.post("/api/session/stop", json={}).json()
    assert gövde["status"] == "success"
    assert "hardware_stop_unconfirmed" not in gövde, (
        f"her şey doğrulandı ama yanıt teyitsizlik bildiriyor: {gövde!r} — alarm yorgunluğu"
    )


def test_KARSIT_KANIT_stm_stop_gercekten_denenir(api, client, aktif_seans, monkeypatch):
    """Teyit alanı STM stop'unu ATLAYARAK 'temiz' kalmamalı: update_coil GERÇEKTEN çağrılır."""
    aktif_seans([2, 3])
    sahte = _SahteStm(sonuc=True)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)
    monkeypatch.setattr(api.state, "hardware", sahte)

    client.post("/api/session/stop", json={})
    assert [(2, False), (3, False)] == sorted(sahte.cagrilar), f"STM bobinlerine stop denenmedi: {sahte.cagrilar!r}"


def test_birim_stop_session_coils_teyitsiz_listesi(api, monkeypatch):
    """Birim düzeyi: karışık sonuçlarda liste tam olarak başarısız olanları içerir."""
    sonuc = {"pemf/coil/6/control": True, "pemf/coil/7/control": False, "pemf/coil/8/control": False}
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: sonuc[topic])
    monkeypatch.setattr(api.state, "hardware", _SahteStm(sonuc=False))

    teyitsiz = api._stop_session_coils([4, 6, 7, 8])
    assert teyitsiz == [4, 7, 8], f"beklenen [4, 7, 8], gelen: {teyitsiz!r}"


# ── ADVERSARYAL REVIEW TAMAMLAMALARI (2026-08-20) ────────────────────────────────────────────
# Review #1: STM "teyidi" fiilen koşulsuzdu — update_coil, STOP paketi donanım kuyruğuna HİÇ
# girmemişken bile True dönüyordu (dönüşü yalnız stop_all_coils/E-stop yolu okuyordu).
# Review #2: süre-watchdog ve AI durdurma yolları teyitsiz listeyi YUTUYORDU — broker ölüyken
# seans "süre doldu" ile biterse operatöre hiçbir uyarı gitmiyordu.

import queue as _q


class _DoluKuyruk:
    """put_nowait HEP Full atar; get_nowait HEP Empty (boşaltma da işe yaramaz) → 3 deneme de düşer."""

    def put_nowait(self, pkt):
        raise _q.Full

    def get_nowait(self):
        raise _q.Empty


class _AcikKuyruk:
    def __init__(self):
        self.paketler = []

    def put_nowait(self, pkt):
        self.paketler.append(pkt)

    def get_nowait(self):
        raise _q.Empty


class _StubCore:
    def __init__(self, kuyruk):
        self._hw_send_queue = kuyruk


def _controller(kuyruk):
    from controllers.hardware_controller import HardwareController

    return HardwareController(_StubCore(kuyruk))


def test_KRITIK_stm_STOP_kuyruga_giremezse_update_coil_False_doner():
    """STOP paketi donanım kuyruğuna VERİLEMEDİYSE dönüş False olmalı — stop_all_coils'in
    (E-stop yolu, 2026-08-09 denetimi) zaten taşıdığı sözleşmenin AYNISI. Aksi hâlde
    _stop_session_coils bobini 'teyitli' sayar ve hardware_stop_unconfirmed uyarısı STM
    tarafında yalnız 'donanım hiç yok' durumunda çalışır."""
    hc = _controller(_DoluKuyruk())
    assert hc.update_coil(1, 0.0, 0.0, 0.0, 0, start=False) is False, (
        "kuyruk dolu (paket kesin GÖNDERİLMEDİ) ama update_coil True döndü — sahte teyit"
    )


def test_KARSIT_KANIT_stm_stop_kuyruga_girince_True_ve_start_semantigi_DEGISMEDI():
    """(a) STOP kuyruğa girdiyse True. (b) START yolunda dönüş BİLEREK değişmedi: state atomik
    uygulandı + keep-alive her turda tam durumu tazeler; kuyruk-dolu START'ta False dönmek
    'parametre reddedildi' ile 'geçici doluluk'u karıştırırdı (bkz. update_coil normalize dalı)."""
    hc = _controller(_AcikKuyruk())
    assert hc.update_coil(1, 0.0, 0.0, 0.0, 0, start=False) is True

    hc2 = _controller(_DoluKuyruk())
    assert hc2.update_coil(1, 50.0, 25.0, 0.0, 10, start=True) is True, (
        "START semantiği değişmemeli (belgeli karar) — keep-alive dolu kuyruğu sonraki turda telafi eder"
    )
    # ve state gerçekten uygulanmış olmalı (atomiklik korunuyor)
    assert hc2.coils_state[1]["is_running"] is True


def _teyitsiz_uyarilari(uyarilar):
    return [m for m, _sev in uyarilar if "DOĞRULANAMADI" in m]


def test_KRITIK_sure_watchdog_teyitsiz_stopta_operatoru_uyarir(api, monkeypatch):
    """Broker ölüyken seans SÜRE DOLARAK biterse: watchdog STOP'ları düşer, seans 'bitti'
    görünür, bobinler ESP'de kendi süresi bitene dek enerjili kalabilir. Operatör AÇIKÇA
    uyarılmalı — /session/stop yolundaki [1.1] düzeltmesinin watchdog ayağı."""
    import time as _t

    uyarilar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: False)  # broker ölü
    monkeypatch.setattr(api.state, "hardware", None)
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    with api._session_lock:
        eski = dict(api._active_session)
    from fastapi.testclient import TestClient as _TC

    try:
        with _TC(api.app):  # lifespan → background threads (watchdog dahil)
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(
                    {
                        "is_active": True,
                        "session_id": "wd_teyitsiz",
                        "coil_ids": [6, 7],
                        "duration_minutes": 1,
                        "start_time": _t.time() - 120,  # süresi çoktan dolmuş
                        "db_session_id": None,
                    }
                )
            bulundu = []
            for _ in range(40):  # watchdog 1 sn'de bir bakar → ~4 sn tavan
                _t.sleep(0.1)
                bulundu = _teyitsiz_uyarilari(uyarilar)
                if bulundu:
                    break
            assert bulundu, (
                f"süre-watchdog teyitsiz STOP'ta operatörü uyarmadı (uyarilar={uyarilar!r}) — "
                "broker ölüyken 'süre doldu' bitişi sessizce 'bitti' görünür"
            )
            assert "6" in bulundu[0] and "7" in bulundu[0], f"hangi bobinler olduğu söylenmiyor: {bulundu[0]!r}"
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


def test_KARSIT_KANIT_sure_watchdog_teyitli_stopta_uyari_yok(api, monkeypatch):
    """Mutlu yol: publish'ler doğrulanıyor → teyitsizlik uyarısı YOK (alarm yorgunluğu üretme)."""
    import time as _t

    uyarilar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api.state, "hardware", None)  # seans yalnız ESP bobinli
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    with api._session_lock:
        eski = dict(api._active_session)
    from fastapi.testclient import TestClient as _TC

    try:
        with _TC(api.app):
            with api._session_lock:
                api._active_session.clear()
                api._active_session.update(
                    {
                        "is_active": True,
                        "session_id": "wd_teyitli",
                        "coil_ids": [6, 7],
                        "duration_minutes": 1,
                        "start_time": _t.time() - 120,
                        "db_session_id": None,
                    }
                )
            durdu = False
            for _ in range(40):
                _t.sleep(0.1)
                with api._session_lock:
                    if not api._active_session.get("is_active"):
                        durdu = True
                        break
            assert durdu, "watchdog süresi dolan seansı durdurmadı"
            assert not _teyitsiz_uyarilari(uyarilar), (
                f"teyitli durdurma YANLIŞ teyitsizlik uyarısı üretti: {uyarilar!r}"
            )
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


def test_KRITIK_ai_pro_stop_teyitsizken_operatoru_uyarir(api, client, monkeypatch):
    """AI Pro durdurma da aynı teyit sözleşmesini taşımalı: broker ölüyken /api/ai/pro/stop
    'success' derken bobinlerin durmadığını operatör bilmeli."""
    uyarilar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: False)
    monkeypatch.setattr(api.state, "hardware", None)
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    r = client.post("/api/ai/pro/stop")
    assert r.status_code == 200
    bulundu = _teyitsiz_uyarilari(uyarilar)
    assert bulundu, f"AI Pro stop teyitsizken uyarı yok (uyarilar={uyarilar!r})"
