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
    """Broker ölü → ESP STOP publish'leri düşer → yanıt bunu AÇIKÇA söylemeli.

    ⚠️ D1.09 (B-10.255): bu test eskiden seansı `[6, 7]` ile kuruyordu. Faz 4'te (2026-09-10)
    bobin 6-7 STM'e geçti → test ESP dalını HİÇ koşmuyordu ve sonucu broker'dan BAĞIMSIZDI
    (`hardware=None` yüzünden STM dalı "teyitsiz" diyordu). `_stop_session_coils`'in ESP
    teyitsizlik dalını etkisizleştiren mutantta bu test YEŞİL kalıyordu. Artık seans ESP
    bobinleriyle kurulur ve ESP alt sistemi AÇIKTIR; seansta STM bobini yok → teyitsizliğin
    tek kaynağı broker. ESP bilerek KAPALIYKEN slot 8'in nasıl sayılacağı ayrı karar
    (A-63 → D1.98); bu test onu ölçmez."""
    from topoloji import TUM_ESP, TUM_STM

    esp = sorted(TUM_ESP)
    assert esp and not set(esp) & TUM_STM, f"senaryo: seans bobinleri ESP yolunda olmalı, gelen {esp}"
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    aktif_seans(esp)
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
    assert gövde.get("hardware_stop_unconfirmed") == esp, (
        f"STOP hiçbir ESP bobinine ulaşmadı ama yanıt bunu söylemiyor: {gövde!r}"
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
    # FAZ 4: bobin 6-7 ARTIK STM (batch) yolunda; MQTT yolunda yalniz ESP_COIL_IDS var.
    # Iddia AYNI: karisik sonuclarda liste TAM OLARAK basarisiz olanlari icerir.
    # 4 → STM (sahte donanim False dondurur) · ESP_BOBIN → MQTT False.
    sonuc = {f"pemf/coil/{ESP_BOBIN}/control": False}
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: sonuc.get(topic, True))
    monkeypatch.setattr(api.state, "hardware", _SahteStm(sonuc=False))

    _beklenen = [4, ESP_BOBIN]
    teyitsiz = api._stop_session_coils([4, ESP_BOBIN])
    assert teyitsiz == _beklenen, f"beklenen {_beklenen}, gelen: {teyitsiz!r}"


# ── ADVERSARYAL REVIEW TAMAMLAMALARI (2026-08-20) ────────────────────────────────────────────
# Review #1: STM "teyidi" fiilen koşulsuzdu — update_coil, STOP paketi donanım kuyruğuna HİÇ
# girmemişken bile True dönüyordu (dönüşü yalnız stop_all_coils/E-stop yolu okuyordu).
# Review #2: süre-watchdog ve AI durdurma yolları teyitsiz listeyi YUTUYORDU — broker ölüyken
# seans "süre doldu" ile biterse operatöre hiçbir uyarı gitmiyordu.

import queue as _q

from topoloji import ESP_BOBIN, TUM_ESP  # faz 4: literal bobin numarasi YASAK


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

    # ⚠️ STM "bağlı" ÖN KOŞULU (2026-09-11): başlatma artık STM kopukken reddediliyor;
    # bu iddia START'ın DÖNÜŞ SEMANTİĞİNİ ölçüyor, bağlantıyı değil.
    from stm_baglanti import stm_bagli

    hc2 = _controller(_DoluKuyruk())
    with stm_bagli():
        _start_sonuc = hc2.update_coil(1, 50.0, 25.0, 0.0, 10, start=True)
    assert _start_sonuc is True, (
        "START semantiği değişmemeli (belgeli karar) — keep-alive dolu kuyruğu sonraki turda telafi eder"
    )
    # ve state gerçekten uygulanmış olmalı (atomiklik korunuyor)
    assert hc2.coils_state[1]["is_running"] is True


def _teyitsiz_uyarilari(uyarilar):
    return [m for m, _sev in uyarilar if "DOĞRULANAMADI" in m]


class _TurBitti(BaseException):
    """Süre-watchdog döngüsünü tek tur sonra durdurur (BaseException: döngünün `except Exception`ı yakalamaz)."""


def _watchdog_tek_tur(api, monkeypatch, seans: dict) -> dict:
    """Süresi dolmuş seansı kur, süre-watchdog döngüsünü TEST THREAD'İNDE TEK TUR koştur, sonraki hâli döndür.

    ⚠️ D0Ö.10 (B-10.104): bu testler eskiden `with TestClient` lifespan'ıyla GERÇEK `session-watchdog`
    daemon'ını başlatıp beklerdi; o daemon süreç sonuna dek yaşayıp SONRAKİ testlerin seanslarını
    durdurabiliyordu. Artık conftest lifespan'ın arka plan başlatıcısını engelliyor; aynı üretim döngüsü
    burada sınırlı turla koşar (`sleep` yalnız bu thread'de kesilir)."""
    import threading
    import time as _time

    ana = threading.current_thread()
    gercek_uyku = _time.sleep

    def _uyku(sn):
        if threading.current_thread() is ana:
            raise _TurBitti
        return gercek_uyku(sn)

    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(seans)
    monkeypatch.setattr(_time, "sleep", _uyku)  # watchdog `import time as _t` → `_t.sleep` buraya düşer
    try:
        with pytest.raises(_TurBitti):
            api._session_duration_watchdog()
    finally:
        monkeypatch.setattr(_time, "sleep", gercek_uyku)
    with api._session_lock:
        return dict(api._active_session)


def _suresi_dolmus(session_id: str) -> dict:
    import time as _t

    return {
        "is_active": True,
        "session_id": session_id,
        "coil_ids": sorted(TUM_ESP),
        "duration_minutes": 1,
        "start_time": _t.time() - 120,  # süresi çoktan dolmuş
        "db_session_id": None,
    }


def test_KRITIK_sure_watchdog_teyitsiz_stopta_operatoru_uyarir(api, monkeypatch):
    """Broker ölüyken seans SÜRE DOLARAK biterse: watchdog STOP'ları düşer, seans 'bitti'
    görünür, bobinler ESP'de kendi süresi bitene dek enerjili kalabilir. Operatör AÇIKÇA
    uyarılmalı — /session/stop yolundaki [1.1] düzeltmesinin watchdog ayağı."""
    uyarilar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: False)  # broker ölü
    monkeypatch.setattr(api.state, "hardware", None)
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    with api._session_lock:
        eski = dict(api._active_session)
    try:
        _watchdog_tek_tur(api, monkeypatch, _suresi_dolmus("wd_teyitsiz"))
        bulundu = _teyitsiz_uyarilari(uyarilar)
        assert bulundu, (
            f"süre-watchdog teyitsiz STOP'ta operatörü uyarmadı (uyarilar={uyarilar!r}) — "
            "broker ölüyken 'süre doldu' bitişi sessizce 'bitti' görünür"
        )
        # FAZ 4: uyari, kapsamdaki ESP bobinlerini adiyla saymali (elle 6/7 DEGIL).
        assert all(str(c) in bulundu[0] for c in TUM_ESP), f"hangi bobinler olduğu söylenmiyor: {bulundu[0]!r}"
    finally:
        with api._session_lock:
            api._active_session.clear()
            api._active_session.update(eski)


def test_KARSIT_KANIT_sure_watchdog_teyitli_stopta_uyari_yok(api, monkeypatch):
    """Mutlu yol: publish'ler doğrulanıyor → teyitsizlik uyarısı YOK (alarm yorgunluğu üretme)."""
    uyarilar: list = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api.state, "hardware", None)  # seans yalnız ESP bobinli
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": uyarilar.append((msg, sev)))

    with api._session_lock:
        eski = dict(api._active_session)
    try:
        sonra = _watchdog_tek_tur(api, monkeypatch, _suresi_dolmus("wd_teyitli"))
        assert not sonra.get("is_active"), "watchdog süresi dolan seansı durdurmadı"
        assert not _teyitsiz_uyarilari(uyarilar), f"teyitli durdurma YANLIŞ teyitsizlik uyarısı üretti: {uyarilar!r}"
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


@pytest.fixture(autouse=True)
def _aktif_seans_SIZMAZ():
    """D1.41 (B-10.243): bu dosyanın testleri seansı AKTİF bırakıyordu (tam süitte ölçüldü) — sonraki dosyanın
    ilk seans testi 409 alır, çalışan bir süre-watchdog'u başka testin seansını durdururdu. Test sonrası
    seans durumu temizlenir; `conftest._seans_ve_watchdog_nobeti` bunu doğrular."""
    yield
    from servers import api_server as _api

    with _api._session_lock:
        _api._active_session.clear()
