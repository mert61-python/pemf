# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.14 · B-2.17 — BOZUK sayısal bayrak backend içe aktarımını (dolayısıyla ACİL DURDUR ucunu) ÖLDÜRMEZ.

ÖLÇÜLEN (DENETİM-02, 02-2): `jeton.py` / `entitlement.py` sayısal bayrakları modül düzeyinde
korumasız `int(os.getenv(...))` / `float(...)` ile okuyordu. Tek bir yazım hatası (`elli`, `4,5`)
`ai_router` içe aktarımında `ValueError` atar; `api_server` `ai_router`'ı modül düzeyinde içe
aktardığı için backend HİÇ açılmaz → E-stop ucu YOK (7/7 bayrak ölçüldü). Ö.4-Y8 ruhu: E-stop'un
VAR OLMASI bir ticari ayarın ayrıştırılmasına bağlı olamaz.

⚠️ Aynı sınıftan 8. bayrak bu maddede ölçülerek eklendi: `ai_client._TIMEOUT`
(`PEMF_AI_SERVICE_TIMEOUT`) — `ai_router` onu da modül düzeyinde içe aktarıyor.

Her bayrak AYRI ALT SÜREÇTE (conftest yolları ve önbellekli modüller YOK): gerçek
`import servers.api_server` → `POST /api/hardware/emergency_stop` (sahte donanım) → 200, STOP
çağrıldı, bayrak VARSAYILANA düştü, uyarı bayrağın ADIYLA yazıldı. Ortam izin listesidir
(`tests/betik_alt_sureci.py`).

⚠️ AĞ: süitin bekçisi alt sürece GEÇMEZ. Çocuk, ürün importundan ÖNCE `tests/alt_surec_ag_bekcisi.py`'yi
yükler; her koşuda "engellenen ağ denemesi = 0" ölçülür. Bekçinin kör olmadığı `test_ARAC_…` kolunda,
gerçek E-stop yolunun bekçiye görünür olduğu `test_KARSIT_…bulut_aynasi…` kolunda kanıtlanır.
Kanıt hedefleri bekçi BOZUK olsa bile makine dışına paket çıkarmaz (0.0.0.0, açılmamış loopback portu,
sahibin portlarına yalnız SAHTE soket).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent

#: (bayrak, bozuk değer, modül, öznitelik, beklenen varsayılan)
BAYRAKLAR = [
    ("PEMF_JETON_OFFLINE_TAVAN", "elli", "servers.jeton", "OFFLINE_TAVAN", 50),
    ("PEMF_JETON_BORC_TAVANI", "yuz", "servers.jeton", "BORC_TAVANI", 300),
    ("PEMF_JETON_TIMEOUT", "dort", "servers.jeton", "_SUPABASE_TIMEOUT", 4.0),
    ("PEMF_AI_QUEUE_CONCURRENCY", "bir", "servers.entitlement", "AI_QUEUE_CONCURRENCY", 1),
    ("PEMF_AI_QUEUE_MAX_WAIT", "otuz", "servers.entitlement", "AI_QUEUE_MAX_WAIT", 30.0),
    ("PEMF_ENTITLEMENT_CACHE_TTL", "altmis", "servers.entitlement", "_CACHE_TTL", 60.0),
    ("PEMF_ENTITLEMENT_TIMEOUT", "4,5", "servers.entitlement", "_SUPABASE_TIMEOUT", 4.0),
    ("PEMF_AI_SERVICE_TIMEOUT", "yuzseksen", "servers.ai_client", "_TIMEOUT", 180.0),
]

#: Çocuk sürecin ilk satırları: ağ bekçisi ürün importundan ÖNCE; `tests/` yolu hemen geri alınır.
_BEKCI_GIRIS = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
"""

_ALT_SUREC = (
    _BEKCI_GIRIS
    + r"""
import importlib, json, threading
sys.path[:0] = [{kok!r}, {backend!r}]
import servers.api_server as api
from fastapi.testclient import TestClient

class _HW:
    stop = 0
    def stop_all_coils(self):
        _HW.stop += 1
        return True

api.state.hardware = _HW()
api._mqtt_publish = lambda topic, payload: False
api._push_notification = lambda *a, **k: None
r = TestClient(api.app, client=("127.0.0.1", 50001)).post("/api/hardware/emergency_stop")
for t in threading.enumerate():
    if t.name == "estop-cloud-mirror":
        t.join(20)
deger = getattr(importlib.import_module({modul!r}), {oznitelik!r})
print("SONUC " + json.dumps({{"durum": r.status_code, "stop": _HW.stop, "deger": deger, "ag": _ag.ENGELLENEN}}))
"""
)

#: Bekçinin araç kanıtı: her kat ayrı denenir. Hedefler bekçi bozukken de makine DIŞINA çıkmaz.
_ARAC = (
    _BEKCI_GIRIS
    + r"""
import _socket, asyncio, json, socket
sonuc = {{}}

class _Sahte:
    family = socket.AF_INET

def dene(ad, fn):
    try:
        fn()
        sonuc[ad] = "GECTI"
    except Exception as e:
        sonuc[ad] = "BEKCI" if "AĞ BEKÇİSİ" in str(e) else "BASKA:" + type(e).__name__

def tcp():
    with socket.socket() as s:
        s.settimeout(1)
        s.connect(("0.0.0.0", 9))

def ham():
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect(("0.0.0.0", 9))
    finally:
        s.close()

def udp():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(b"x", ("127.0.0.1", 9))

def dns():
    socket.getaddrinfo("0.0.0.0", 9)

def sahip_connect():
    socket.socket.connect(_Sahte(), ("127.0.0.1", 1883))

def sahip_bind():
    socket.socket.bind(_Sahte(), ("127.0.0.1", 8000))

def iocp():
    async def _c():
        loop = asyncio.get_running_loop()
        with socket.socket() as s:
            s.setblocking(False)
            await asyncio.wait_for(loop.sock_connect(s, ("0.0.0.0", 9)), 2)
    asyncio.run(_c())

def oz_boru():
    a, b = socket.socketpair()
    try:
        a.sendall(b"k")
        assert b.recv(1) == b"k"
    finally:
        a.close()
        b.close()

for ad, fn in [("tcp", tcp), ("ham", ham), ("udp", udp), ("dns", dns), ("sahip_connect", sahip_connect),
               ("sahip_bind", sahip_bind), ("iocp", iocp), ("oz_boru", oz_boru)]:
    dene(ad, fn)
print("SONUC " + json.dumps({{"sonuc": sonuc, "ag": _ag.ENGELLENEN}}))
"""
)


def _ortam(tmp_path) -> dict:
    env = yalitik_ortam(tmp_path)
    env.update(
        {
            "PEMF_DATA_DIR": str(tmp_path / "veri"),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "provizyon.json"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
        }
    )
    return env


def _kos(tmp_path, bayrak: str, deger: str | None, modul: str, oznitelik: str, env: dict | None = None):
    env = env if env is not None else _ortam(tmp_path)
    if deger is not None:
        env[bayrak] = deger
    kod = _ALT_SUREC.format(
        testler=str(TESTLER), kok=str(KOK), backend=str(KOK / "apps" / "backend"), modul=modul, oznitelik=oznitelik
    )
    (tmp_path / "alt.py").write_text(kod, encoding="utf-8")
    return kostur([str(tmp_path / "alt.py")], cwd=tmp_path, env=env, sure=240)


def _sonuc(cikti: str) -> dict | None:
    for satir in cikti.splitlines():
        if satir.startswith("SONUC "):
            return json.loads(satir[len("SONUC ") :])
    return None


@pytest.mark.parametrize(
    ("bayrak", "bozuk", "modul", "oznitelik", "varsayilan"), BAYRAKLAR, ids=[b[0] for b in BAYRAKLAR]
)
def test_KRITIK_bozuk_bayrak_backendi_OLDURMEZ_ACIL_DURDUR_calisir(
    tmp_path, bayrak, bozuk, modul, oznitelik, varsayilan
):
    p = _kos(tmp_path, bayrak, bozuk, modul, oznitelik)
    s = _sonuc(p.stdout)
    assert p.returncode == 0 and s is not None, (
        f"{bayrak}={bozuk!r}: backend İÇE AKTARILAMADI (rc={p.returncode}) — ACİL DURDUR ucu YOK. "
        f"stderr sonu: {p.stderr[-600:]}"
    )
    assert s["ag"] == [], f"alt süreç AĞA çıkmayı denedi (bekçi engelledi): {s['ag']}"
    assert s["durum"] == 200 and s["stop"] >= 1, f"{bayrak}={bozuk!r}: acil durdurma {s}"
    assert s["deger"] == pytest.approx(varsayilan), f"{bayrak}={bozuk!r}: değer {s['deger']} (varsayılan {varsayilan})"
    assert bayrak in p.stderr, f"{bayrak}: bozuk değer SESSİZCE yutuldu — uyarı günlüğü yok"


#: (bayrak, geçerli değer, beklenen) — varsayılandan FARKLI ve `max()` tabanlarının üstünde.
GECERLI = {
    "PEMF_JETON_OFFLINE_TAVAN": ("7", 7),
    "PEMF_JETON_BORC_TAVANI": ("11", 11),
    "PEMF_JETON_TIMEOUT": ("7.5", 7.5),
    "PEMF_AI_QUEUE_CONCURRENCY": ("3", 3),
    "PEMF_AI_QUEUE_MAX_WAIT": ("12.5", 12.5),
    "PEMF_ENTITLEMENT_CACHE_TTL": ("90", 90.0),
    "PEMF_ENTITLEMENT_TIMEOUT": ("7.5", 7.5),
    "PEMF_AI_SERVICE_TIMEOUT": ("33", 33.0),
}


@pytest.mark.parametrize(("bayrak", "_bozuk", "modul", "oznitelik", "_v"), BAYRAKLAR, ids=[b[0] for b in BAYRAKLAR])
def test_KARSIT_gecerli_bayrak_DEGERI_kullanilir(tmp_path, bayrak, _bozuk, modul, oznitelik, _v):
    """Varsayılana düşüş "her şeyi yok say" biçiminde bozulmasın: geçerli değer AYNEN okunur. ⚠️ Bağımsız
    inceleme (r3): eskiden yalnız `OFFLINE_TAVAN` ölçülüyordu — `entitlement._sayi` geçerli değeri yok sayıp
    varsayılanı dönse (4 bayrak sessizce etkisiz) kapı yeşil kalıyordu. Artık sekiz bayrağın hepsi."""
    gecerli, beklenen = GECERLI[bayrak]
    s = _sonuc(_kos(tmp_path, bayrak, gecerli, modul, oznitelik).stdout)
    assert s and s["durum"] == 200 and s["ag"] == [], s
    assert s["deger"] == pytest.approx(beklenen), f"{bayrak}={gecerli!r} → {s['deger']} (geçerli değer YOK SAYILDI)"


def test_ARAC_alt_surec_ag_bekcisi_her_KATI_engeller_ve_KAYDEDER(tmp_path):
    """Bekçi kör olsaydı `ag == []` iddiası anlamsız kalırdı: her kat ayrı denenir (sarmalayıcı, C düzeyi
    `_socket` → audit hook, sahibin portu, bind, Windows Proactor), öz-boru (asyncio) SERBEST kalır."""
    (tmp_path / "arac.py").write_text(_ARAC.format(testler=str(TESTLER)), encoding="utf-8")
    p = kostur([str(tmp_path / "arac.py")], cwd=tmp_path, env=yalitik_ortam(tmp_path), sure=60)
    s = _sonuc(p.stdout)
    assert p.returncode == 0 and s is not None, p.stderr[-600:]
    engellenmeli = ["tcp", "ham", "udp", "dns", "sahip_connect", "sahip_bind", "iocp"]
    assert {ad: s["sonuc"][ad] for ad in engellenmeli} == dict.fromkeys(engellenmeli, "BEKCI"), s
    assert s["sonuc"]["oz_boru"] == "GECTI", f"bekçi kendi açtığı loopback portunu da kesiyor: {s}"
    katmanlar = {k for k, _, _ in s["ag"]}
    assert {"connect", "audit:connect", "sendto", "dns", "bind", "iocp.connect"} <= katmanlar, s["ag"]


def test_KARSIT_bekci_gercek_ESTOP_bulut_aynasi_denemesini_GORUR(tmp_path):
    """`ag == []` gerçek çocukta anlamlı mı: sahte provizyon (host 0.0.0.0 — bekçi bozukken de makine
    dışına çıkmaz) görünürken GERÇEK E-stop bulut aynası bağlanmayı dener → bekçi engeller ve KAYDEDER."""
    prov = tmp_path / "sahte_provizyon.json"
    prov.write_text(
        json.dumps(
            {
                "mqtt_cloud_host": "0.0.0.0",
                "mqtt_cloud_port": "8883",
                "mqtt_cloud_user": "sahte",
                "mqtt_cloud_pass": "sahte",
            }
        ),
        encoding="utf-8",
    )
    env = _ortam(tmp_path)
    env["PEMF_CLOUD_PROVISION_PATH"] = str(prov)
    p = _kos(tmp_path, "PEMF_JETON_OFFLINE_TAVAN", None, "servers.jeton", "OFFLINE_TAVAN", env=env)
    s = _sonuc(p.stdout)
    assert p.returncode == 0 and s is not None, p.stderr[-600:]
    assert s["durum"] == 200 and s["stop"] >= 1, s
    assert any(adres == "0.0.0.0" for _, adres, _ in s["ag"]), f"bekçi aynanın ağ denemesini GÖRMEDİ: {s['ag']}"
