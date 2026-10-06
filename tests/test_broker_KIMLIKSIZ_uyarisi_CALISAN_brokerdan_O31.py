# Author: mertaygn, cglrgrkn
"""O-3.1 (1-G inceleme, D1.104) — "broker KİMLİKSİZ" açılış uyarısı DOSYAYA değil ÇALIŞAN broker'ın gerçek yapılandırmasına
bağlıdır.

ÖLÇÜLEN KUSUR: `_start_mqtt_for_api` uyarıyı `mqtt_kimlik.hazirlandi_mi()` ile veriyordu — o, kimlik deposuna ve
`conf.d` parçasının VARLIĞINA bakar. (1) Hazırladıktan sonra broker yeniden başlayana dek broker ANONİMDİR ama uyarı YOK;
(2) çalışma kopyası yazılamazsa (1-G inceleme Kapsam 3 hâl E) broker taban yapılandırmayla anonim açılır, uyarı YOK;
(3) tersine, hazırlanmamış sistemde broker kimlik istiyorsa (ör. kendi yapılandırmasıyla servis) "anonim" uyarısı YANLIŞ
— asıl sorun backend'in broker'a BAĞLANAMAMASI (ESP STOP yolu).

KAPI: GERÇEK `_start_mqtt_for_api` (paho istemcisi bağlanmayan sahte; ESP etkin) + GERÇEK `utils.mqtt_kimlik` sondası →
loopback rastgele portta SAHTE broker (CONNECT'i okur, CONNACK döner). Kimlik İZOLE makine deposunda hazırlanır.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import pytest


class _SahteBroker:
    """CONNECT'i okuyup `rc` ile CONNACK döner; rc=None → yanıt vermeden kapatır (ölçülemeyen broker)."""

    def __init__(self, rc: int | None):
        self.rc = rc
        self.connect = []
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind(("127.0.0.1", 0))
        self.s.listen(4)
        self.port = self.s.getsockname()[1]
        threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self):
        while True:
            try:
                c, _ = self.s.accept()
            except OSError:
                return
            with c:
                c.settimeout(2.0)
                try:
                    self.connect.append(c.recv(512))
                    if self.rc is not None:
                        c.sendall(bytes([0x20, 0x02, 0x00, self.rc]))
                        c.recv(16)
                except OSError:
                    pass

    def kapat(self):
        self.s.close()


class _SahteIstemci:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, ad):
        return lambda *a, **k: None


@pytest.fixture
def kos(monkeypatch, tmp_path, caplog):
    import paho.mqtt.client as paho
    from servers import api_server, live_state
    from utils import mqtt_kimlik

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    mqtt_kimlik._onbellek.clear()
    monkeypatch.setattr(live_state, "esp_etkin", lambda: True)
    monkeypatch.setattr(paho, "Client", _SahteIstemci)
    monkeypatch.setattr(api_server, "_mqtt_client_api", None)
    monkeypatch.setattr(api_server, "_SONDA_DENEME", 2, raising=False)
    monkeypatch.setattr(api_server, "_SONDA_ARALIK_S", 0.05, raising=False)
    brokerler = []

    def _kos(rc, hazir: bool):
        if hazir:
            mqtt_kimlik.hazirla()
            assert mqtt_kimlik.hazirlandi_mi(), "aparat: kimlik hazırlanamadı"
        b = _SahteBroker(rc)
        brokerler.append(b)
        monkeypatch.setattr(api_server, "_YEREL_BROKER", ("127.0.0.1", b.port), raising=False)
        with caplog.at_level(logging.WARNING):
            api_server._start_mqtt_for_api()
            son = time.monotonic() + 5.0
            while time.monotonic() < son and any(t.name == "BrokerKimlikSondasi" for t in threading.enumerate()):
                time.sleep(0.05)
            time.sleep(0.2)
        return b, " | ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)

    yield _kos
    for b in brokerler:
        b.kapat()
    mqtt_kimlik._onbellek.clear()


def test_KRITIK_hazirlanmis_ama_CALISAN_broker_anonim_KABUL_ediyorsa_uyari_VAR(kos):
    broker, gunluk = kos(0, hazir=True)
    assert "KIMLIKSIZ" in gunluk, (
        f"kimlik hazırlanmış ama ÇALIŞAN broker anonim bağlantıyı KABUL ediyor — açılış uyarısı YOK (O-3.1): {gunluk!r}"
    )
    assert broker.connect and broker.connect[0][0] == 0x10, f"broker'a MQTT CONNECT gitmedi: {broker.connect!r}"
    assert not (broker.connect[0][9] & 0x80), "sonda kullanıcı adıyla bağlandı — anonim kabulü ölçmüyor"


def test_KARSIT_broker_anonimi_REDDEDIYORSA_kimliksiz_uyarisi_YOK(kos):
    _broker, gunluk = kos(5, hazir=True)
    assert "KIMLIKSIZ" not in gunluk, f"broker kimlik istiyor (CONNACK 5) ama 'KIMLIKSIZ' uyarısı verildi: {gunluk!r}"


def test_KRITIK_hazirlanmamis_ve_broker_kimlik_ISTIYORSA_baglanamaz_uyarisi(kos):
    _broker, gunluk = kos(5, hazir=False)
    assert "KIMLIKSIZ" not in gunluk, f"broker anonimi reddediyor — 'anonim' uyarısı YANLIŞ: {gunluk!r}"
    assert "BAGLANAMAZ" in gunluk, (
        f"backend kimliksiz, broker kimlik istiyor → backend BAĞLANAMAZ söylenmeli: {gunluk!r}"
    )


def test_KRITIK_broker_YANITSIZSA_olculemedi_SOYLENIR(kos):
    _broker, gunluk = kos(None, hazir=True)
    assert "OLCULEMEDI" in gunluk, f"broker'ın kimlik durumu ölçülemedi ama sessiz kalındı: {gunluk!r}"
