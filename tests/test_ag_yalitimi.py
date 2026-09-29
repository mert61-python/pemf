# Author: mertaygn, cglrgrkn
"""D0Ö.07 (B-10.9) KAPISI — test süiti AĞA ÇIKMAZ; E-stop bulut aynası süitte gerçek broker'a uzanmaz.

ARIZA (ölçüldü, DENETIM-10 B-10.9): `data/cloud_mqtt_provision.json` (git'e girmez) bu makinede
VAR. Aynayı stub'lamayan E-stop testleri (`test_mqtt_publish_confirmation.py:154-214`,
`test_live_state.py`, `test_mqtt_client_id.py`) `_emergency_stop_all` → `_estop_cloud_mirror`
thread'ini başlatıyordu → `_bundled_cloud` GERÇEK kimliği okuyor → GERÇEK (üretim) bulut
broker'ına TLS + `pemf/coil/<id>/control` STOP yayını DENENİYORDU (yerel sahte broker ile 4+4 TLS
ClientHello ölçüldü). conftest'in ağ ayağı yoktu.

ÇÖZÜM yalnız test aparatında (E-stop aynasının ÜRÜN kodu DEĞİŞMEZ — Ö.4-Y8, sahip kararı HG-5):
  1. `PEMF_CLOUD_PROVISION_PATH` süreç başında var olmayan bir tmp yola yönlenir; `PEMF_MQTT_CLOUD_*`
     env'leri silinir.
  2. Ağ bekçisi (`tests/conftest.py`): loopback dışı connect/connect_ex/sendto/DNS ENGELLENİR; loopback'te
     yalnız bu süreçte bind edilmiş portlara izin; sahibin servis portları ne bağlanılır ne bind
     edilir. Katlar: Python sarmalayıcıları + audit hook + (Windows) IocpProactor.connect/sendto.

KOLLAR (her biri ayrı mutasyonla kırmızı):
  (1) Depoda provizyon dosyası VARKEN de `_bundled_cloud` süitte boş döner (yönlendirme); ayrı bir
      süreçte conftest İÇE AKTARILINCA yönlendirme kurulur ve `PEMF_MQTT_CLOUD_*` silinir (modül düzeyi).
  (2) Davranış: sahte provizyon (TEST-NET 192.0.2.1) görünürken gerçek `_emergency_stop_all`
      çağrılır; ayna koşar ama loopback dışı ağ denemesi 0 olmalı. Bu testin kendi sayacı
      denemeyi KAYDEDER ve DÜŞÜRÜR — bekçi yoksa bile paket dışarı çıkmaz.
  (3) Bekçi: her katı ayrı ayrı engeller VE sayar. Sahibin portlarına (8000/1883/…) GERÇEK soketle
      hiç dokunulmaz: saf ön-kontrol + sahte soketle bind; gerçek denemeler yalnız TEST-NET ve
      açılmamış loopback portuna. Testin kendi açtığı loopback portu serbest.
  (4) Provizyon yolunda dosya belirirse o testi KIRMIZI yapan bekçi, alt süreçteki bir sondayla kanıtlanır.

MUTASYON: yönlendirmeyi silmek → (1),(2); bir katı (sarmalayıcı / audit hook / IOCP / bind yasağı /
açılmamış-port dalı) silmek → (3); env temizliğini ya da modül-düzeyi yönlendirmeyi kaldırmak → (1);
provizyon bekçisini silmek → (4) KIRMIZI.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_BU_DOSYA = "tests/test_ag_yalitimi.py"
_SONDA_ORTAMI = "D0O07_PROVIZYON_SONDASI"
#: Sahibin makinesinde canlı olabilecek servisler (backend, AI servisi, broker, web dev, build kapısı, Vault).
_BEKLENEN_SAHIP_PORTLARI = {8000, 8100, 1883, 5173, 8177, 8200}

_SAHTE_PROVIZYON = {
    "mqtt_cloud_host": "192.0.2.1",  # TEST-NET-1: yönlendirilemez belge adresi
    "mqtt_cloud_port": "8883",
    "mqtt_cloud_user": "d0o07-sahte-kullanici",
    "mqtt_cloud_pass": "d0o07-sahte-parola",
}


def _kayitli_conftest():
    """pytest'in YÜKLEDİĞİ conftest (`import conftest` ikinci kopya yaratabilir → kör kayıt)."""
    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (_KOK / "tests" / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı (içe aktarma kipi değişmiş olabilir) — ağ kapısı ölçemez"
    )
    return c


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


def test_KRITIK_conftest_ICE_AKTARILINCA_yonlendirir_ve_bulut_envlerini_siler():
    """Modül düzeyi: yönlendirme conftest İÇE AKTARILIRKEN kurulmalı (bir fixture'a taşınırsa teardown'dan
    sonra koşan ayna thread'i gerçek ortamı görür) ve provizyondan ÖNCE okunan `PEMF_MQTT_CLOUD_*` silinmeli."""
    kod = (
        "import json, os, sys\n"
        f"sys.path.insert(0, r'{_KOK / 'tests'}')\n"
        "import conftest\n"
        "print(json.dumps({k: os.environ.get(k) for k in ('PEMF_CLOUD_PROVISION_PATH', 'PEMF_MQTT_CLOUD_HOST',"
        " 'PEMF_MQTT_CLOUD_PASS')}))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PEMF_CLOUD_PROVISION_PATH"}
    env["PEMF_MQTT_CLOUD_HOST"] = "d0o07-gercek-host-sahtesi.invalid"
    env["PEMF_MQTT_CLOUD_PASS"] = "d0o07-sahte"
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-c", kod], env=env, capture_output=True, text=True, encoding="utf-8", timeout=180
    )
    assert r.returncode == 0, f"conftest ayrı süreçte içe aktarılamadı:\n{r.stderr[-1500:]}"
    degerler = json.loads(r.stdout.strip().splitlines()[-1])
    yol = degerler["PEMF_CLOUD_PROVISION_PATH"]
    assert yol and not os.path.exists(yol), f"conftest içe aktarılınca provizyon YÖNLENDİRİLMEDİ: {yol!r}"
    assert degerler["PEMF_MQTT_CLOUD_HOST"] is None and degerler["PEMF_MQTT_CLOUD_PASS"] is None, (
        f"PEMF_MQTT_CLOUD_* env'leri SİLİNMEDİ — ayna gerçek kimliği env'den okur: {degerler}"
    )


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


class _SahteSoket:
    """Bind yasağını sınamak için: gerçek bir soket DEĞİL — yasak kalkmış olsa bile gerçek bind OLMAZ
    (özgün `bind` bu nesneyi reddeder); sahibin portu bir an bile gölgelenmez."""

    family = socket.AF_INET


def test_KRITIK_ag_bekcisi_her_KATI_ENGELLER_ve_SAYAR():
    _c = _kayitli_conftest()
    kayit = getattr(_c, "_AG_ENGELLENEN", None)
    # Bekçi yoksa ya da bir kat takılı değilse HİÇBİR bağlantı denenmeden kırmızı.
    assert kayit is not None, "conftest ağ bekçisi YOK (D0Ö.07)"
    takili = {
        "socket.connect": (socket.socket.connect, getattr(_c, "_ag_connect", None)),
        "socket.connect_ex": (socket.socket.connect_ex, getattr(_c, "_ag_connect_ex", None)),
        "socket.sendto": (socket.socket.sendto, getattr(_c, "_ag_sendto", None)),
        "socket.getaddrinfo": (socket.getaddrinfo, getattr(_c, "_ag_getaddrinfo", None)),
        "socket.gethostbyname": (socket.gethostbyname, getattr(_c, "_ag_gethostbyname", None)),
        "socket.gethostbyaddr": (socket.gethostbyaddr, getattr(_c, "_ag_gethostbyaddr", None)),
    }
    eksik = [ad for ad, (simdiki, bekci) in takili.items() if bekci is None or simdiki is not bekci]
    assert not eksik, f"ağ bekçisinin şu katları TAKILI DEĞİL: {eksik}"
    # Saf ön-kontrol: karar fonksiyonu sahibin portlarını ve loopback dışını reddediyor mu (soket YOK).
    for hedef in (("127.0.0.1", 8000), ("127.0.0.1", 1883), ("192.0.2.1", 443)):
        with pytest.raises(ConnectionRefusedError):
            _c._ag_denetle(hedef, "on-kontrol")
    assert set(_c._AG_SAHIP_PORTLARI) >= _BEKLENEN_SAHIP_PORTLARI, (
        f"sahip port listesi eksik: {_BEKLENEN_SAHIP_PORTLARI - set(_c._AG_SAHIP_PORTLARI)}"
    )

    def _dilimde(n, beklenen):
        return beklenen in kayit[n:]

    # TCP connect (TEST-NET ve açılmamış loopback portu — ikisi de zararsız hedef)
    for host, port in (("192.0.2.1", 443), ("127.0.0.1", 1)):
        n = len(kayit)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            with pytest.raises(ConnectionRefusedError):
                s.connect((host, port))
        finally:
            s.close()
        assert _dilimde(n, ("connect", host, port)), f"{host}:{port} engellendi ama SAYILMADI: {kayit[n:]}"
    # connect_ex
    n = len(kayit)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert s.connect_ex(("192.0.2.1", 443)) == 10061
    finally:
        s.close()
    assert _dilimde(n, ("connect_ex", "192.0.2.1", 443)), kayit[n:]
    # UDP sendto (mDNS dahil)
    for host, port in (("192.0.2.1", 9), ("224.0.0.251", 5353)):
        n = len(kayit)
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(ConnectionRefusedError):
                u.sendto(b"d0o07", (host, port))
        finally:
            u.close()
        assert _dilimde(n, ("sendto", host, port)), f"UDP {host}:{port} engellendi ama SAYILMADI: {kayit[n:]}"
    # DNS
    n = len(kayit)
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("d0o07-kapi.invalid", 443)
    with pytest.raises(socket.gaierror):
        socket.gethostbyname("d0o07-kapi.invalid")
    assert _dilimde(n, ("dns", "d0o07-kapi.invalid", -1)) and _dilimde(
        n, ("gethostbyname", "d0o07-kapi.invalid", -1)
    ), kayit[n:]
    # Audit hook: KAYITLI mı (yoklama olayı) ve C düzeyi olayı reddediyor mu (karar mantığı)
    yoklama = getattr(_c, "_AG_KANCA_YOKLAMA", None)
    assert yoklama is not None, "audit-hook yoklama kaydı yok"
    isaret = object()
    sys.audit("pemf.ag_bekcisi.yoklama", isaret)
    assert yoklama and yoklama[-1] == (isaret,), "conftest audit hook'u KAYITLI DEĞİL (sys.addaudithook yok)"
    n = len(kayit)
    with pytest.raises(ConnectionRefusedError):
        _c._ag_denetim_kancasi("socket.connect", (_SahteSoket(), ("192.0.2.1", 443)))
    with pytest.raises(ConnectionRefusedError):
        _c._ag_denetim_kancasi("socket.sendto", (_SahteSoket(), ("192.0.2.1", 9)))
    assert _dilimde(n, ("audit:connect", "192.0.2.1", 443)) and _dilimde(n, ("audit:sendto", "192.0.2.1", 9)), kayit[n:]
    # Bind yasağı — her sahip portu, SAHTE soketle (gerçek bind asla olmaz)
    for port in sorted(_BEKLENEN_SAHIP_PORTLARI):
        n = len(kayit)
        with pytest.raises(PermissionError):
            _c._ag_bind(_SahteSoket(), ("127.0.0.1", port))
        assert _dilimde(n, ("bind", "127.0.0.1", port)), f"bind {port} engellendi ama SAYILMADI: {kayit[n:]}"

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


@pytest.mark.skipif(
    sys.platform != "win32", reason="IocpProactor yalnız Windows'ta (Linux'ta Selector yolu socket.*'tan geçer)"
)
def test_KRITIK_ag_bekcisi_WINDOWS_PROACTOR_yolunu_ENGELLER():
    """Proactor ConnectEx/WSASendTo `socket.*`'a uğramaz ve audit olayı üretmez: tek kat IOCP yamasıdır."""
    _c = _kayitli_conftest()
    kayit = _c._AG_ENGELLENEN
    dongu = asyncio.ProactorEventLoop()
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        tcp.setblocking(False)
        n = len(kayit)
        with pytest.raises(ConnectionRefusedError):
            dongu.run_until_complete(asyncio.wait_for(dongu.sock_connect(tcp, ("192.0.2.1", 443)), 3))
        assert ("iocp.connect", "192.0.2.1", 443) in kayit[n:], f"Proactor connect SAYILMADI: {kayit[n:]}"
        n = len(kayit)
        with pytest.raises(ConnectionRefusedError):
            dongu._proactor.sendto(udp, b"d0o07", 0, ("192.0.2.1", 9))
        assert ("iocp.sendto", "192.0.2.1", 9) in kayit[n:], f"Proactor sendto SAYILMADI: {kayit[n:]}"
    finally:
        tcp.close()
        udp.close()
        dongu.close()


@pytest.mark.skipif(os.environ.get(_SONDA_ORTAMI) != "1", reason="yalnız kol 4 alt sürecinde koşar")
def test_SONDA_provizyon_yolunda_dosya_uretir():
    """Kol 4'ün sondası: yönlendirilmiş provizyon yoluna dosya yazar (üretici betiğin yaptığı gibi)."""
    Path(os.environ["PEMF_CLOUD_PROVISION_PATH"]).write_text("{}", encoding="utf-8")


def test_KRITIK_provizyon_yolunda_dosya_belirirse_test_KIRMIZI():
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env[_SONDA_ORTAMI] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
            "-q",
            "-rE",
            f"{_BU_DOSYA}::test_SONDA_provizyon_yolunda_dosya_uretir",
        ],
        cwd=str(_KOK),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    cikti = (r.stdout or "")[-3000:] + (r.stderr or "")[-1500:]
    assert r.returncode != 0 and "1 error" in (r.stdout or ""), (
        f"provizyon yolunda dosya üreten test KIRMIZI olmadı — bekçi kör (rc={r.returncode}):\n{cikti}"
    )
    assert "yönlendirilmiş bulut provizyon yolunda DOSYA" in (r.stdout or ""), cikti
