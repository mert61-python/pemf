# Author: mertaygn, cglrgrkn
"""D0Ö.07 (B-10.9) KAPISI — test süiti AĞA ÇIKMAZ; E-stop bulut aynası süitte gerçek broker'a uzanmaz.

ARIZA (ölçüldü, DENETIM-10 B-10.9): `data/cloud_mqtt_provision.json` (git'e girmez) bu makinede
VAR. Aynayı stub'lamayan E-stop testleri (`test_mqtt_publish_confirmation.py:154-214`,
`test_live_state.py`, `test_mqtt_client_id.py`) `_emergency_stop_all` → `_estop_cloud_mirror`
thread'ini başlatıyordu → `_bundled_cloud` GERÇEK kimliği okuyor → GERÇEK (üretim) bulut
broker'ına TLS + `pemf/coil/<id>/control` STOP yayını DENENİYORDU (yerel sahte broker ile 4+4 TLS
ClientHello ölçüldü). conftest'in ağ ayağı yoktu.

ÇÖZÜM yalnız test aparatında (E-stop aynasının ÜRÜN kodu DEĞİŞMEZ — Ö.4-Y8, sahip kararı HG-5):
  1. `PEMF_CLOUD_PROVISION_PATH` süreç başında var olmayan bir tmp yola yönlenir.
  2. Ağ bekçisi (`tests/conftest.py`): loopback dışı connect/connect_ex/DNS ENGELLENİR; loopback'te
     yalnız bu süreçte AÇILAN (bind edilen) portlara izin; sahibin servis portları (8000, 8100,
     1883, 5173, 8177, 8200) ne bağlanılır ne bind edilir. Engellenen her deneme sayılır.

KOLLAR (her biri ayrı mutasyonla kırmızı):
  (1) Depoda provizyon dosyası VARKEN de `_bundled_cloud` süitte boş döner (yönlendirme).
  (2) Davranış: sahte provizyon (TEST-NET 192.0.2.1) görünürken gerçek `_emergency_stop_all`
      çağrılır; ayna koşar ama loopback dışı ağ denemesi 0 olmalı. Bu testin kendi sayacı
      denemeyi KAYDEDER ve DÜŞÜRÜR — bekçi yoksa bile paket dışarı çıkmaz.
  (3) Bekçi: 192.0.2.1:443, 127.0.0.1:8000, 127.0.0.1:1883, açılmamış loopback portu ve DNS
      engellenir VE sayılır; testin kendi açtığı loopback portu serbesttir.

MUTASYON: conftest'ten yönlendirmeyi silmek → (1),(2) KIRMIZI; ağ bekçisini silmek → (3) KIRMIZI.
"""

import json
import os
import socket
import threading

import pytest

_SAHTE_PROVIZYON = {
    "mqtt_cloud_host": "192.0.2.1",  # TEST-NET-1: yönlendirilemez belge adresi
    "mqtt_cloud_port": "8883",
    "mqtt_cloud_user": "d0o07-sahte-kullanici",
    "mqtt_cloud_pass": "d0o07-sahte-parola",
}


def _sahte_kok(tmp_path, monkeypatch):
    """Depo kökü `data/cloud_mqtt_provision.json` İÇERİYORMUŞ gibi: `kaynak_kokunu_bul` tmp köke döner.
    ⚠️ Gerçek depodaki dosyaya DOKUNULMAZ (guii'de gerçek provizyon durur)."""
    kok = tmp_path / "sahte_depo"
    (kok / "data").mkdir(parents=True)
    (kok / "data" / "cloud_mqtt_provision.json").write_text(json.dumps(_SAHTE_PROVIZYON), encoding="utf-8")
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "kaynak_kokunu_bul", lambda *a, **k: kok)
    return kok


def _loopback_mu(host) -> bool:
    import ipaddress

    h = str(host).strip().strip("[]").split("%")[0]
    if h.lower() in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def test_KRITIK_bulut_provizyonu_suitte_OKUNMAZ(tmp_path, monkeypatch):
    import utils.secrets_manager as sm

    _sahte_kok(tmp_path, monkeypatch)
    # Senaryo gerçekten kuruldu mu: yönlendirme OLMASAYDI sahte provizyon okunurdu.
    with monkeypatch.context() as m:
        m.delenv("PEMF_CLOUD_PROVISION_PATH", raising=False)
        assert sm._bundled_cloud("mqtt_cloud_host") == "192.0.2.1", "sahte depo kökü kurulamadı (test kör)"

    yol = os.environ.get("PEMF_CLOUD_PROVISION_PATH", "")
    assert yol and not os.path.exists(yol), f"conftest provizyonu var olmayan bir yola YÖNLENDİRMEMİŞ: {yol!r}"
    assert sm._bundled_cloud("mqtt_cloud_host") == "", "süit depodaki bulut provizyonunu OKUYOR (B-10.9)"


def test_KRITIK_estop_bulut_aynasi_suitte_AGA_UZANMAZ(tmp_path, monkeypatch):
    from servers import api_server as api

    _sahte_kok(tmp_path, monkeypatch)
    denemeler = []  # (tür, hedef, thread adı) — önceki testlerden kalan daemon'lar da yazabilir
    orj_gai, orj_connect, orj_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex

    def _kaydet(tur, hedef):
        denemeler.append((tur, str(hedef), threading.current_thread().name))

    def _gai(host, *a, **k):
        if host is not None and not _loopback_mu(host.decode() if isinstance(host, bytes) else host):
            _kaydet("dns", host)
            raise socket.gaierror(11001, f"D0Ö.07 kapısı: {host} (KAYDEDİLDİ, dışarı ÇIKMADI)")
        return orj_gai(host, *a, **k)

    def _connect(self, adres):
        if isinstance(adres, tuple) and not _loopback_mu(adres[0]):
            _kaydet("connect", adres[0])
            raise ConnectionRefusedError(f"D0Ö.07 kapısı: {adres[:2]} (KAYDEDİLDİ, dışarı ÇIKMADI)")
        return orj_connect(self, adres)

    def _connect_ex(self, adres):
        if isinstance(adres, tuple) and not _loopback_mu(adres[0]):
            _kaydet("connect_ex", adres[0])
            return 10061
        return orj_connect_ex(self, adres)

    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex)

    ayna_kostu = threading.Event()
    orj_ayna = api._estop_cloud_mirror

    def _izlenen_ayna(*a, **k):
        try:
            return orj_ayna(*a, **k)
        finally:
            ayna_kostu.set()

    monkeypatch.setattr(api, "_estop_cloud_mirror", _izlenen_ayna)
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: True)

    class _HW:
        def stop_all_coils(self):
            return True

    monkeypatch.setattr(api.state, "hardware", _HW())

    api._emergency_stop_all(reason="d0o07-kapi")
    assert ayna_kostu.wait(15), "E-stop bulut aynası KOŞMADI — senaryo kurulamadı (test kör)"
    aynanin = [d for d in denemeler if d[1] == _SAHTE_PROVIZYON["mqtt_cloud_host"] or d[2] == "estop-cloud-mirror"]
    assert aynanin == [], f"E-stop bulut aynası süitte loopback DIŞINA uzandı (B-10.9): {aynanin}"


def test_KRITIK_ag_bekcisi_ENGELLER_ve_SAYAR():
    import conftest as _c

    kayit = getattr(_c, "_AG_ENGELLENEN", None)
    # Bekçi yoksa HİÇBİR bağlantı denenmeden kırmızı (gerçek hedefe paket gitmesin).
    assert kayit is not None, "conftest ağ bekçisi YOK (D0Ö.07)"
    assert socket.socket.connect is getattr(_c, "_ag_connect", None), "socket.connect bekçiye bağlı değil"

    def _tcp(host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((host, port))
        finally:
            s.close()

    # Önceki testlerden kalan daemon'lar da kayda yazabilir → "son kayıt" değil, "bu denemeden
    # sonra eklenenler arasında" diye bakılır.
    for host, port in (("192.0.2.1", 443), ("127.0.0.1", 8000), ("127.0.0.1", 1883), ("127.0.0.1", 1)):
        n = len(kayit)
        with pytest.raises(ConnectionRefusedError):
            _tcp(host, port)
        assert ("connect", host, port) in kayit[n:], f"{host}:{port} engellendi ama SAYILMADI: {kayit[n:]}"
    n = len(kayit)
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("d0o07-kapi.invalid", 443)
    assert ("dns", "d0o07-kapi.invalid", -1) in kayit[n:], kayit[n:]

    n = len(kayit)
    b = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(PermissionError):
            b.bind(("127.0.0.1", 8000))  # sahip backend'ini ele geçirme sınıfı
    finally:
        b.close()
    assert ("bind", "127.0.0.1", 8000) in kayit[n:], kayit[n:]

    # Karşıt-kanıt: testin KENDİ açtığı loopback portu serbest (bekçi loopback'i toptan kapatmıyor).
    sunucu = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sunucu.bind(("127.0.0.1", 0))
    sunucu.listen(1)
    port = sunucu.getsockname()[1]
    try:
        n = len(kayit)
        c = socket.create_connection(("127.0.0.1", port), timeout=2)
        c.close()
        assert not [k for k in kayit[n:] if k[1:] == ("127.0.0.1", port)], f"testin açtığı port engellendi: {kayit[n:]}"
    finally:
        sunucu.close()
