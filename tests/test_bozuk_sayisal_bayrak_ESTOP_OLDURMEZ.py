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
import re
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent

#: (bayrak, bozuk değer, modül, öznitelik, beklenen varsayılan)
BAYRAKLAR = [
    # 2026-10-19: `PEMF_JETON_OFFLINE_TAVAN` kaldırıldı (S-4B.5 — çevrimdışı analiz yok); jeton modülünün öteki sayısal bayrağı.
    ("PEMF_JETON_CANLI_KARE_TAVANI", "altmis", "servers.jeton", "CANLI_KARE_TAVANI", 60),
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
print("SONUC " + json.dumps({{"durum": r.status_code, "stop": _HW.stop, "deger": deger, "ag": _ag.ENGELLENEN, "alt": _ag.ALT_SURECLER}}))
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

# Bağımsız inceleme (r3) katmanları — kanca birimi çağrıları GERÇEK ağa hiç çıkmaz:
def ters_dns_kanca():
    _ag._kanca("socket.gethostbyaddr", ("192.0.2.1",))

def nameinfo_kanca():
    _ag._kanca("socket.getnameinfo", (("192.0.2.1", 9),))

def ham_bind_kanca():
    _ag._kanca("socket.bind", (_Sahte(), ("127.0.0.1", 8000)))

for ad, fn in [("tcp", tcp), ("ham", ham), ("udp", udp), ("dns", dns), ("sahip_connect", sahip_connect),
               ("sahip_bind", sahip_bind), ("iocp", iocp), ("oz_boru", oz_boru),
               ("ters_dns_kanca", ters_dns_kanca), ("nameinfo_kanca", nameinfo_kanca),
               ("ham_bind_kanca", ham_bind_kanca)]:
    dene(ad, fn)
sarmalayici = socket.gethostbyaddr is _ag._gethostbyaddr and socket.getnameinfo is _ag._getnameinfo
_ag._kanca("_winapi.CreateProcess", (None, "x.exe", None))  # Popen'sız (multiprocessing yolu)
_ag._kanca("subprocess.Popen", (None, ["ornek_program.exe", "/x"], None, None))
_ag._kanca("_winapi.CreateProcess", (None, "bozuk_komut_satiri", None))  # Popen'ın eşi — ikinci kayıt YOK
_ag._kanca("os.exec", ("ornek_exec.exe", ["ornek_exec.exe"], None))
print("SONUC " + json.dumps({{"sonuc": sonuc, "ag": _ag.ENGELLENEN, "sarmalayici": sarmalayici, "alt": _ag.ALT_SURECLER}}))
"""
)


#: Çocuğun başlatmasına izin verilen alt süreçler (torunlar bekçisizdir). Windows `platform` sürüm sorgusu
#: `cmd.exe /c "ver"` çalıştırır (ağ yok) — ölçüldü (bağımsız inceleme r3 sonrası, 2026-10-01).
#: 1-B inceleme (i6): desen başa çapalı değildi (`…; cmd.exe /c "ver"` ile BİTEN her komut izinliydi) → TAM eşleşme.
#: D2.79 (D-3.1) artığı: SID düzeltmesinden beri `utils.file_acl`ın veri kökü kilidi çocukta GERÇEKTEN koşar (eskiden yalıtık
#: ortamda `USERNAME` yokken `getpass` düşüyor, kilit SESSİZCE atlanıyordu) → YALNIZ onun tam komut biçimi izinli: boşluksuz yol,
#: Users / Authenticated Users kaldırılır, SYSTEM + Administrators + (isteğe bağlı) S-1-5-18 / S-1-5-21-… süreç SID'i verilir.
#: A14 aparatıyla AYNI desen (tests/test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py `_IZINLI_ALT_SUREC`) — biri değişirse öteki de.
_IZINLI_ALT_SUREC = re.compile(
    r"subprocess\.Popen:(?:"
    r'(?:[A-Za-z]:\\(?:[^"\\]+\\)*)?cmd\.exe /c "?ver"?'
    r"|icacls [A-Za-z]:\\\S+ /inheritance:r /remove:g \*S-1-5-32-545 /remove:g \*S-1-5-11"
    r"(?: /remove:g \*S-1-(?:1-0|5-4|2-0|2-1|5-32-546|5-7|5-2))*"  # E2-1.3: öbür geniş grupların açık ACE'leri de kaldırılır
    r" /grant:r \*S-1-5-18:(?:\(OI\)\(CI\))?F /grant:r \*S-1-5-32-544:(?:\(OI\)\(CI\))?F"
    r"(?: /grant:r \*S-1-5-(?:18|21-[0-9-]+):(?:\(OI\)\(CI\))?F)*"
    r")",
    re.IGNORECASE,
)


def _izinli_alt_surec(kayit: str) -> bool:
    return bool(_IZINLI_ALT_SUREC.fullmatch(kayit))


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
    assert all(_izinli_alt_surec(a) for a in s["alt"]), f"çocuk izin listesi DIŞI alt süreç başlattı: {s['alt']}"
    assert s["durum"] == 200 and s["stop"] >= 1, f"{bayrak}={bozuk!r}: acil durdurma {s}"
    assert s["deger"] == pytest.approx(varsayilan), f"{bayrak}={bozuk!r}: değer {s['deger']} (varsayılan {varsayilan})"
    assert bayrak in p.stderr, f"{bayrak}: bozuk değer SESSİZCE yutuldu — uyarı günlüğü yok"


#: bayrak → [(geçerli değer, beklenen)] — varsayılandan FARKLI, `max()` tabanlarının üstünde; 1-B inceleme (i6):
#: her bayrakta varsayılanın İKİ YANI (altı ve üstü). Tek yan ölçülünce "varsayılanda tavan/taban" mutantı
#: (`min(float(env), 180.0)`) sekiz bayrağın dördünde KÖRDÜ. `AI_QUEUE_CONCURRENCY`'de varsayılan = taban (1):
#: altı geçerli değer YOK, yalnız üstü.
GECERLI = {
    "PEMF_JETON_CANLI_KARE_TAVANI": [("7", 7), ("500", 500)],
    "PEMF_JETON_BORC_TAVANI": [("11", 11), ("900", 900)],
    "PEMF_JETON_TIMEOUT": [("2.5", 2.5), ("7.5", 7.5)],
    "PEMF_AI_QUEUE_CONCURRENCY": [("3", 3)],
    "PEMF_AI_QUEUE_MAX_WAIT": [("12.5", 12.5), ("90", 90.0)],
    "PEMF_ENTITLEMENT_CACHE_TTL": [("15", 15.0), ("90", 90.0)],
    "PEMF_ENTITLEMENT_TIMEOUT": [("2.5", 2.5), ("7.5", 7.5)],
    "PEMF_AI_SERVICE_TIMEOUT": [("33", 33.0), ("600", 600.0)],
}
_GECERLI_KOLLAR = [(b, m, o, deger, beklenen) for b, _z, m, o, _v in BAYRAKLAR for deger, beklenen in GECERLI[b]]


@pytest.mark.parametrize(
    ("bayrak", "modul", "oznitelik", "gecerli", "beklenen"),
    _GECERLI_KOLLAR,
    ids=[f"{k[0]}={k[3]}" for k in _GECERLI_KOLLAR],
)
def test_KARSIT_gecerli_bayrak_DEGERI_kullanilir(tmp_path, bayrak, modul, oznitelik, gecerli, beklenen):
    """Varsayılana düşüş "her şeyi yok say" biçiminde bozulmasın: geçerli değer AYNEN okunur. ⚠️ Bağımsız
    inceleme (r3): eskiden yalnız `OFFLINE_TAVAN` ölçülüyordu — `entitlement._sayi` geçerli değeri yok sayıp
    varsayılanı dönse (4 bayrak sessizce etkisiz) kapı yeşil kalıyordu. Artık sekiz bayrağın hepsi, iki yanda."""
    p = _kos(tmp_path, bayrak, gecerli, modul, oznitelik)
    s = _sonuc(p.stdout)
    assert s and s["durum"] == 200 and s["ag"] == [], s
    assert s["deger"] == pytest.approx(beklenen), f"{bayrak}={gecerli!r} → {s['deger']} (geçerli değer YOK SAYILDI)"
    # Ana kolun kanıtı (`bayrak in stderr`) ayırt edici kalsın: geçerli değerde uyarı YOK (her değerde uyaran mutant).
    assert bayrak not in p.stderr, f"{bayrak}={gecerli!r}: GEÇERLİ değerde uyarı basıldı: {p.stderr[-400:]}"


def test_ARAC_alt_surec_ag_bekcisi_her_KATI_engeller_ve_KAYDEDER(tmp_path):
    """Bekçi kör olsaydı `ag == []` iddiası anlamsız kalırdı: her kat ayrı denenir (sarmalayıcı, C düzeyi
    `_socket` → audit hook, sahibin portu, bind, Windows Proactor), öz-boru (asyncio) SERBEST kalır."""
    (tmp_path / "arac.py").write_text(_ARAC.format(testler=str(TESTLER)), encoding="utf-8")
    p = kostur([str(tmp_path / "arac.py")], cwd=tmp_path, env=yalitik_ortam(tmp_path), sure=60)
    s = _sonuc(p.stdout)
    assert p.returncode == 0 and s is not None, p.stderr[-600:]
    engellenmeli = [
        "tcp",
        "ham",
        "udp",
        "dns",
        "sahip_connect",
        "sahip_bind",
        "iocp",
        "ters_dns_kanca",
        "nameinfo_kanca",
        "ham_bind_kanca",
    ]
    assert {ad: s["sonuc"][ad] for ad in engellenmeli} == dict.fromkeys(engellenmeli, "BEKCI"), s
    assert s["sonuc"]["oz_boru"] == "GECTI", f"bekçi kendi açtığı loopback portunu da kesiyor: {s}"
    katmanlar = {k for k, _, _ in s["ag"]}
    assert {"connect", "audit:connect", "sendto", "dns", "bind", "iocp.connect"} <= katmanlar, s["ag"]
    assert {"audit:gethostbyaddr", "audit:getnameinfo", "audit:bind"} <= katmanlar, s["ag"]
    assert s["sarmalayici"] is True, "ters DNS sarmalayıcıları (gethostbyaddr/getnameinfo) KURULMAMIŞ"
    assert s["alt"][-3:] == [
        "_winapi.CreateProcess:EŞLENMEMİŞ (Popen'sız süreç başlatma)",
        "subprocess.Popen:ornek_program.exe",
        "os.exec:ornek_exec.exe",
    ], f"alt süreç kaydı çalışmıyor (Popen'sız CreateProcess / os.exec / eşleştirme): {s['alt']}"
    # İzin deseni TAM eşleşir: yalnız `cmd.exe /c "ver"` (yollu ya da yolsuz); sonuna/başına ek yapılmış komut DEĞİL.
    assert _izinli_alt_surec(r'subprocess.Popen:C:\WINDOWS\system32\cmd.exe /c "ver"')
    assert _izinli_alt_surec('subprocess.Popen:cmd.exe /c ver')
    # D2.79: ürünün veri kökü / sır dosyası kilidi (dizin ve dosya biçimi) izinli.
    _kilit = r"subprocess.Popen:icacls C:\t\veri\PEMF_GUI /inheritance:r /remove:g *S-1-5-32-545 /remove:g *S-1-5-11"
    assert _izinli_alt_surec(
        _kilit
        + r" /grant:r *S-1-5-18:(OI)(CI)F /grant:r *S-1-5-32-544:(OI)(CI)F /grant:r *S-1-5-21-1-2-3-1001:(OI)(CI)F"
    )
    assert _izinli_alt_surec(_kilit + r" /grant:r *S-1-5-18:F /grant:r *S-1-5-32-544:F /grant:r *S-1-5-18:F")
    for kotu in (
        'subprocess.Popen:kotu.exe; cmd.exe /c "ver"',
        r'subprocess.Popen:C:\x\cmd.exe /c "ver" & kotu.exe',
        "_winapi.CreateProcess:EŞLENMEMİŞ (Popen'sız süreç başlatma)",
        'os.exec:cmd.exe /c "ver"',
        # D2.79: kilit biçimine eklenmiş Users / Everyone erişimi, `/reset`, araya sızan seçenek İZİNLİ DEĞİL.
        _kilit + r" /grant:r *S-1-5-18:F /grant:r *S-1-5-32-544:F /grant:r *S-1-5-32-545:F",
        _kilit + r" /grant:r *S-1-5-18:F /grant:r *S-1-5-32-544:F /grant:r *S-1-1-0:F",
        r"subprocess.Popen:icacls C:\x /reset /T",
        r"subprocess.Popen:icacls C:\x /T /inheritance:r /remove:g *S-1-5-32-545 /remove:g *S-1-5-11"
        r" /grant:r *S-1-5-18:F /grant:r *S-1-5-32-544:F",
    ):
        assert not _izinli_alt_surec(kotu), kotu


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
    p = _kos(tmp_path, "PEMF_JETON_BORC_TAVANI", None, "servers.jeton", "BORC_TAVANI", env=env)
    s = _sonuc(p.stdout)
    assert p.returncode == 0 and s is not None, p.stderr[-600:]
    assert s["durum"] == 200 and s["stop"] >= 1, s
    assert any(adres == "0.0.0.0" for _, adres, _ in s["ag"]), f"bekçi aynanın ağ denemesini GÖRMEDİ: {s['ag']}"


# ── 1-A açık madde 6 · `PEMF_API_PORT` (bu sınıfın 9. bayrağı) ─────────────────────────────────────
#
# ÖLÇÜLEN (2026-10-01): port `build_arg_parser()` İÇİNDE korumasız `int(os.environ.get("PEMF_API_PORT", "8000"))`
# ile okunuyordu → bozuk değer parser KURULURKEN `ValueError`; launcher `--port` ile başlatsa bile
# (`launcher/core/src/backend.rs`) backend ve ACİL DURDUR ucu HİÇ açılmıyordu.

_PORT_COCUK = (
    _BEKCI_GIRIS
    + r"""
import json
sys.path[:0] = [{kok!r}, {backend!r}]
import backend_service as bs
sonuc = {{"ag": _ag.ENGELLENEN}}
try:
    sonuc["cli_port"] = bs.build_arg_parser().parse_args(["--port", "51998"]).port
except Exception as e:
    sonuc["kacan"] = type(e).__name__ + ": " + str(e)
try:
    sonuc["ortam"] = list(bs.ortam_portu())
except Exception as e:
    sonuc["ortam_kacan"] = type(e).__name__ + ": " + str(e)
print("SONUC " + json.dumps(sonuc))
"""
)


@pytest.mark.parametrize(
    ("deger", "beklenen", "uyari"),
    [("80O0", 8000, True), ("70000", 8000, True), ("0", 8000, True), ("8123", 8123, False), (None, 8000, False)],
    ids=["harf", "aralik_ustu", "sifir", "gecerli", "yok"],
)
def test_KRITIK_bozuk_PEMF_API_PORT_parseri_OLDURMEZ_CLI_portu_ve_ortam_portu(tmp_path, deger, beklenen, uyari):
    env = yalitik_ortam(tmp_path / "ev")
    if deger is not None:
        env["PEMF_API_PORT"] = deger
    kod = _PORT_COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(KOK / "apps" / "backend"))
    (tmp_path / "port.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "port.py")], cwd=tmp_path, env=env, sure=120)
    s = _sonuc(p.stdout)
    assert s is not None, f"çocuk sonuç basmadı (rc={p.returncode}): {p.stderr[-800:]}"
    assert "kacan" not in s, (
        f"PEMF_API_PORT={deger!r}: parser KURULAMADI — `--port` verilse de backend açılmaz: {s['kacan']}"
    )
    assert s["cli_port"] == 51998, f"`--port` ortamı EZMEDİ: {s}"
    assert "ortam_kacan" not in s, s
    port, mesaj = s["ortam"]
    assert port == beklenen, f"PEMF_API_PORT={deger!r} → {port} (beklenen {beklenen})"
    assert bool(mesaj) is uyari and (not uyari or "PEMF_API_PORT" in mesaj), (
        f"uyarı {mesaj!r} — bozuk değer bayrağın ADIYLA bildirilmeli, geçerli/eksik değerde uyarı olmamalı"
    )
    assert s["ag"] == [], s


def test_KRITIK_bozuk_PEMF_API_PORT_ile_GERCEK_acilis_ACIL_DURDUR_calisir(tmp_path):
    """Launcher biçimi: `main(["--port", …])` + ortamda bozuk `PEMF_API_PORT` → GERÇEK açılış `server.run()`'a
    ulaşır, ACİL DURDUR donanıma STOP verir (D1.37 açılış aparatı, `bozuk_port` senaryosu)."""
    from test_acilis_DB_acilamasa_ACIL_DURDUR_yasar import _kos as _acilis_kos
    from test_acilis_DB_acilamasa_ACIL_DURDUR_yasar import _ortak_iddialar

    s, _app = _acilis_kos(tmp_path, "bozuk_port")
    _ortak_iddialar(s)
    # 1-B inceleme (i1/B2): `--port` ortamı main() düzeyinde de EZER (yalnız parser değil): dinlenen ve keşfe
    # yayınlanan port launcher'ınki — bozuk ortam değeri ya da 8000 DEĞİL.
    assert (s.get("dinlenen_port"), s.get("yayinlanan_port")) == (51999, "51999"), s


def test_KRITIK_bozuk_PEMF_API_PORT_portsuz_acilista_8000_ve_UYARI_GUNLUKTE(tmp_path):
    """`--port` VERİLMEDEN (elle/servis açılışı) bozuk ortam portu → açılış sürer, ACİL DURDUR çalışır ve uyarı
    günlüğe bayrağın ADIYLA yazılır (sessiz yutma yok). Aparat sunucuyu BAĞLAMAZ (`run()` TestClient'tır)."""
    from test_acilis_DB_acilamasa_ACIL_DURDUR_yasar import _kos as _acilis_kos
    from test_acilis_DB_acilamasa_ACIL_DURDUR_yasar import _ortak_iddialar

    s, _app = _acilis_kos(tmp_path, "bozuk_port", argv=["--host", "127.0.0.1", "--no-headless-services"])
    _ortak_iddialar(s)
    assert (s.get("dinlenen_port"), s.get("yayinlanan_port")) == (8000, "8000"), s
    gunluk = (tmp_path / "log" / "backend_service.log").read_text(encoding="utf-8", errors="replace")
    assert "PEMF_API_PORT='80O0'" in gunluk and "8000" in gunluk, "bozuk port uyarısı günlükte YOK (sessiz yutma)"
