# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.121 · B-1.5 (+ D1.120 · B-4.2 · Y1 · Y17) — açılış donanım güncellemesi kararı STM EL SIKIŞMASINDAN SONRA
(`hardware.stm.connected`), banner sürümü ayrıştırılarak verilir; yakma YALNIZ "bayrak 1 + STM var + kural var" hâlinde.

ÖLÇÜLEN KUSUR (1-H (a)0, `kayit/once_acilis_sonda.txt`): `main()` `_donanim_guncellemesi_safe`'i HeadlessCore kurulduktan
~0,9 sn sonra SENKRON çağırıyordu; el sıkışma ~2,4 sn'de bitiyordu → karar her açılışta `stm_bagli=False`,
`firmware_surum=''` (kanca el sıkışmadan ~1,2 sn ÖNCE).

KAPI: GERÇEK `backend_service.main()` ÇOCUK süreçte (launcher argv'si + `--no-headless-services`): çocukta
`alt_surec_ag_bekcisi` ürün importundan ÖNCE (yalnız süreç içinde açılan portlar); gerçek seri port açma (serialwin32)
ENGELLİ ve sayılı; "STM var" kolunda çocuk İÇİNDE sahte STM (loopback rastgele port, `PEMF_STM_PORT=socket://…`) firmware
biçim dizesindeki saha banner'ını basar; "STM yok" kolunda port KAPALI; uyum varlığı YAMALI (kural var = firmwareMin <bir sonraki sürüm> +
`firmware.stm32` <bir sonraki sürüm> (YH D7: main.c'den türer) · kural yok = `{}`, varlık yayınlanmamış); indirme geçici dosya, yakıcı SAHTE (`yakma_akisi` kayıtçı,
`programmer_cli`→None, `_kos`→AssertionError); `acilis_denetimi` kayıtçıyla sarılır; yedek ölçüm süresi kısaltılır.
TABLO: bayrak (yok / 0 / 1) × STM (yok / var) × kural (yok / var) — 12 koşu; yalnız `1+var+var` yakar. ⚠️ Gerçek kart, seri
port, ST-Link YOK; ağ YOK.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam
from test_firmware_SURUM_banner_ve_UYUM_VARLIGI_D1120 import KAYNAK_SURUM, KURALLI, saha_banneri

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent

_SURUCU = r'''
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json, logging, os, socket, tempfile, threading, time, traceback
sys.path[:0] = [{kok!r}, {backend!r}]
T0 = time.monotonic()
sonuc = {{"run": False}}
SERI = []
try:
    import serial.serialwin32 as _sw
    def _seri_engel(self):
        SERI.append(str(getattr(self, "portstr", "") or getattr(self, "_port", "")))
        raise OSError("1H aparat: gercek seri port engellendi")
    _sw.Serial.open = _seri_engel
except Exception as e:
    sonuc["seri_bekci_hata"] = repr(e)

STM = {{"baglanti": 0, "banner_t": []}}
if {stm_var!r}:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    def _istemci(c):
        try:
            time.sleep(0.5)  # kart acilisi: banner porttan SONRA
            c.sendall({banner!r}.encode("ascii") + b"\r\n")
            STM["banner_t"].append(round(time.monotonic() - T0, 3))
            tampon = b""
            while True:
                v = c.recv(4096)
                if not v:
                    return
                tampon += v
                while len(tampon) >= 121:
                    tampon = tampon[121:]
                    c.sendall(b"-> STM_OK: D=0,0,0,0,0,0,0 P=0,0,0,0,0,0,0 F=0,0,0,0,0,0,0 T=0,0,0,0,0,0,0 K=96 E=0,0,0,0,0,0,0\r\n")
        except OSError:
            return
    def _stm():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            STM["baglanti"] += 1
            threading.Thread(target=_istemci, args=(c,), daemon=True).start()
    threading.Thread(target=_stm, daemon=True).start()
    port = srv.getsockname()[1]
else:
    s0 = socket.socket(); s0.bind(("127.0.0.1", 0)); port = s0.getsockname()[1]; s0.close()  # KAPALI port
os.environ["PEMF_STM_PORT"] = "socket://127.0.0.1:%d" % port

import backend_service as bs
import servers.firmware_manager as fm
import utils.stm_yakma as sy
yan = []
bs._start_cloud_sync = lambda logger: yan.append("cloud_sync")
bs._start_update_checker_safe = lambda logger: yan.append("update_checker")
bs._harden_secret_file_acls = lambda d, logger: yan.append("acl")
import utils.agir_import as _ai
_ai.torch_isit = lambda *a, **k: yan.append("torch")
import servers.auto_discovery as _ad
_ad._get_local_ip = lambda: "127.0.0.1"
bs.DONANIM_KARAR_YEDEK_S = 1.0  # yedek (STM yok) ölçüm süresi — testte kısa

MANIFEST = json.loads({manifest!r})
fm.manifest_oku = lambda timeout=15.0: json.loads(json.dumps(MANIFEST))
GECICI = tempfile.mkdtemp(prefix="d1121_")
IKILI = os.path.join(GECICI, "pemf_fw.bin")
open(IKILI, "wb").write(b"\x00" * 64)
INDIR = []
fm.firmware_indir = lambda url, sha: (INDIR.append(url) or (__import__("pathlib").Path(IKILI), ""))
fm._yedek_dizini = lambda: __import__("pathlib").Path(GECICI) / "yedek"
fm._gecici_sil = lambda yol: None
YAKMA = []
def _sahte_yakma(ikili, **k):
    YAKMA.append({{"t": round(time.monotonic() - T0, 3), "ikili": str(ikili)}})
    return sy.Sonuc(sy.TAMAM, "sahte", adimlar=["sahte"])
sy.yakma_akisi = _sahte_yakma
sy.programmer_cli = lambda: None
def _kos_yasak(*a, **k):
    raise AssertionError("1H aparat: GERCEK yakici cagrildi")
sy._kos = _kos_yasak

CORE = {{}}
_o_hc = bs.HeadlessCore
def _el_sikisma(_olay):
    sonuc.setdefault("el_sikisma_t", round(time.monotonic() - T0, 3))
def _hc(*a, **k):
    c = _o_hc(*a, **k)
    CORE["c"] = c
    from event_bus import get_event_bus
    get_event_bus().subscribe("hardware.stm.connected", _el_sikisma, "d1121-sonda")
    return c
bs.HeadlessCore = _hc
KARARLAR = []
_o_acilis = fm.acilis_denetimi
def _kayitci(**k):
    an = {{"t": round(time.monotonic() - T0, 3), "firmware_surum": k.get("firmware_surum"),
          "stm_bagli": k.get("stm_bagli"), "uygula": k.get("uygula")}}
    d = _o_acilis(**k)
    an.update({{"eylem": d.get("eylem"), "gerekce": d.get("gerekce"), "uygulandi": d.get("uygulandi")}})
    KARARLAR.append(an)
    return d
fm.acilis_denetimi = _kayitci

class _Casus:
    should_exit = False
    force_exit = False
    def run(self):
        sonuc["run"] = True
        c = CORE["c"]
        son = time.monotonic() + 14
        while time.monotonic() < son:
            if ({stm_var!r} and any(x["stm_bagli"] for x in KARARLAR)) or (not {stm_var!r} and KARARLAR):
                break
            time.sleep(0.05)
        time.sleep(1.5)  # ikinci (yinelenen) karar olursa görülsün
        sonuc["bagli"] = c.stm_is_connected

bs._build_server = lambda app, args: _Casus()
try:
    sonuc["rc"] = bs.main({argv!r})
except BaseException as e:
    sonuc["kacan"] = type(e).__name__ + ": " + str(e)[:300]
    sonuc["iz"] = traceback.format_exc()[-1500:]
sonuc.update({{"kararlar": KARARLAR, "yakma": YAKMA, "indir": INDIR, "stm": STM, "seri": SERI, "yan": yan,
              "ag": _ag.ENGELLENEN, "alt": _ag.ALT_SURECLER}})
print("SONUC " + json.dumps(sonuc, default=str))
sys.stdout.flush()
os._exit(0)
'''


def _bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _kos(tmp_path: Path, bayrak, stm_var: bool, kural_var: bool) -> dict:
    veri = tmp_path / "veri"
    (veri / "PEMF_GUI").mkdir(parents=True, exist_ok=True)
    env = yalitik_ortam(tmp_path / "ev")
    env.update(
        {
            "PEMF_DATA_DIR": str(veri),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "provizyon.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "SUPABASE_URL": "http://127.0.0.1:9",
            "PEMF_LOG_DIR": str(tmp_path / "log"),
            "PEMF_ESP_ENABLED": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_AI_WARMUP": "0",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_ENCRYPT_AT_REST": "0",
        }
    )
    env.pop("PEMF_FW_AUTO_UPDATE", None)
    if bayrak is not None:
        env["PEMF_FW_AUTO_UPDATE"] = bayrak
    kod = _SURUCU.format(
        testler=str(TESTLER),
        kok=str(KOK),
        backend=str(KOK / "apps" / "backend"),
        banner=saha_banneri(),
        manifest=json.dumps(KURALLI if kural_var else {}),
        stm_var=stm_var,
        argv=["--host", "127.0.0.1", "--port", str(_bos_port()), "--no-headless-services"],
    )
    (tmp_path / "surucu.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "surucu.py")], cwd=tmp_path, env=env, sure=240)
    for satir in p.stdout.splitlines():
        if satir.startswith("SONUC "):
            return json.loads(satir[len("SONUC ") :])
    raise AssertionError(f"çocuk sonuç basmadı (rc={p.returncode}); stderr sonu: {p.stderr[-2500:]}")


TABLO = [(b, s, k) for b in (None, "0", "1") for s in (False, True) for k in (False, True)]


@pytest.mark.parametrize(
    "bayrak,stm_var,kural_var",
    TABLO,
    ids=[f"bayrak_{b or 'yok'}-stm_{'var' if s else 'yok'}-kural_{'var' if k else 'yok'}" for b, s, k in TABLO],
)
def test_KRITIK_karar_tablosu_YALNIZ_1_var_var_YAKAR_karar_EL_SIKISMADAN_SONRA(tmp_path, bayrak, stm_var, kural_var):
    from utils import surum_uyumu as su

    s = _kos(tmp_path, bayrak, stm_var, kural_var)
    assert "kacan" not in s, s.get("iz")
    assert s["run"] is True and s["ag"] == [] and s["seri"] == [], (s.get("ag"), s.get("seri"))
    yakmali = bayrak == "1" and stm_var and kural_var
    assert bool(s["yakma"]) is yakmali, (
        f"bayrak={bayrak!r} STM={'var' if stm_var else 'yok'} kural={'var' if kural_var else 'yok'}: yakma {s['yakma']} — "
        f"yalnız '1+var+var' yakabilir · kararlar {s['kararlar']}"
    )
    gercek = [k for k in s["kararlar"] if k["stm_bagli"]]
    if stm_var:
        assert len(gercek) == 1, (
            f"STM bağlıyken tam BİR karar beklenirdi: {s['kararlar']} (el sıkışma {s.get('el_sikisma_t')})"
        )
        k = gercek[0]
        assert k["t"] >= (s.get("el_sikisma_t") or 0) - 0.06, f"karar el sıkışmadan ÖNCE: {k} / {s.get('el_sikisma_t')}"
        assert k["firmware_surum"] == KAYNAK_SURUM, f"banner sürümü ayrıştırılmadı: {k}"
        assert k["eylem"] == (su.FIRMWARE_GUNCELLE if kural_var else su.EYLEM_YOK), k
        assert k["uygula"] is (bayrak == "1"), k
    else:
        assert gercek == [] and s["kararlar"], (
            f"STM yokken yedek YALNIZ ÖLÇÜM yapılmadı / bağlı karar üretildi: {s['kararlar']}"
        )
        assert all(k["uygula"] is False and k["eylem"] in (su.EYLEM_YOK, su.BEKLE) for k in s["kararlar"]), s[
            "kararlar"
        ]


# ── Süreç içi kollar: tetik sözleşmesi ───────────────────────────────────────────────────────────────────────────────
class _Bus:
    def __init__(self):
        self.geri = {}

    def subscribe(self, olay, geri, abone, **_k):
        self.geri[olay] = geri
        return True


class _Cekirdek:
    def __init__(self, bagli=False, kimlik=None):
        self.stm_is_connected = bagli
        self.stm_kimlik = kimlik


@pytest.fixture
def tetik(monkeypatch):
    import threading
    import time

    import backend_service as bs

    cagrilar: list = []
    kilit = threading.Lock()
    davranis = {"olcum_sure": 0.0}

    def _kayitci(core, logger, *, yalniz_olcum=False):
        bas = time.monotonic()
        if yalniz_olcum and davranis["olcum_sure"]:
            time.sleep(davranis["olcum_sure"])
        with kilit:
            cagrilar.append({"olcum": yalniz_olcum, "bas": bas, "son": time.monotonic()})

    monkeypatch.setattr(bs, "_donanim_guncellemesi_safe", _kayitci)
    return bs, cagrilar, davranis


def _bekle(kosul, sure=3.0):
    import time

    son = time.monotonic() + sure
    while time.monotonic() < son and not kosul():
        time.sleep(0.02)


def test_KRITIK_yeniden_baglanma_IKINCI_karar_URETMEZ(tetik, monkeypatch):
    import logging
    import time

    bs, cagrilar, _ = tetik
    monkeypatch.setattr(bs, "DONANIM_KARAR_YEDEK_S", 30.0)
    bus = _Bus()
    bs._donanim_guncellemesi_kur(_Cekirdek(), logging.getLogger("d1121"), bus)
    assert "hardware.stm.connected" in bus.geri, "karar STM bağlantı olayına bağlanmadı"
    assert cagrilar == [], f"karar el sıkışmadan ÖNCE verildi: {cagrilar}"
    for _ in range(3):  # el sıkışma + iki yeniden bağlanma
        bus.geri["hardware.stm.connected"](object())
    _bekle(lambda: cagrilar)
    time.sleep(0.3)
    assert [c["olcum"] for c in cagrilar] == [False], f"süreç başına BİR karar beklenirdi: {cagrilar}"


def test_KRITIK_kurulumdan_ONCE_baglanmissa_HEMEN_karar(tetik, monkeypatch):
    import logging

    bs, cagrilar, _ = tetik
    monkeypatch.setattr(bs, "DONANIM_KARAR_YEDEK_S", 30.0)
    bs._donanim_guncellemesi_kur(_Cekirdek(bagli=True), logging.getLogger("d1121"), _Bus())
    _bekle(lambda: cagrilar)
    assert [c["olcum"] for c in cagrilar] == [False], f"olay kaçtıysa karar verilmedi: {cagrilar}"


def test_KRITIK_yedek_YALNIZ_OLCUM_suruyorken_gelen_gercek_karar_SONRA_kosar(tetik, monkeypatch):
    import logging
    import time

    bs, cagrilar, davranis = tetik
    monkeypatch.setattr(bs, "DONANIM_KARAR_YEDEK_S", 0.1)
    davranis["olcum_sure"] = 0.6
    bus = _Bus()
    bs._donanim_guncellemesi_kur(_Cekirdek(), logging.getLogger("d1121"), bus)
    time.sleep(0.3)  # yedek ölçüm başladı ve sürüyor
    bus.geri["hardware.stm.connected"](object())
    _bekle(lambda: len(cagrilar) >= 2)
    assert [c["olcum"] for c in cagrilar] == [True, False], f"sıra: yedek ölçüm sonra gerçek karar: {cagrilar}"
    assert cagrilar[1]["bas"] >= cagrilar[0]["son"] - 0.01, (
        f"gerçek karar yedek ölçüm BİTMEDEN koştu — son durum yedeğin sonucu olabilir: {cagrilar}"
    )


def test_KRITIK_gercek_karar_VERILDIYSE_yedek_KOSMAZ(tetik, monkeypatch):
    import logging
    import time

    bs, cagrilar, _ = tetik
    monkeypatch.setattr(bs, "DONANIM_KARAR_YEDEK_S", 0.2)
    bus = _Bus()
    bs._donanim_guncellemesi_kur(_Cekirdek(), logging.getLogger("d1121"), bus)
    bus.geri["hardware.stm.connected"](object())
    time.sleep(0.6)
    assert [c["olcum"] for c in cagrilar] == [False], f"gerçek karardan sonra yedek ölçüm koştu: {cagrilar}"


def test_KRITIK_sessiz_el_sikismada_banner_BEKLENIR_surum_okunur(monkeypatch):
    import logging
    import time

    import backend_service as bs
    from servers import firmware_manager as fm
    from utils import stm32_kimlik

    class _Sessiz(_Cekirdek):
        sayac = 0

        def stm_banner_isareti(self):
            return self.sayac

        def stm_banner_bekle(self, isaret, sure):
            time.sleep(0.2)  # banner el sıkışmadan SONRA gelir
            self.stm_kimlik = stm32_kimlik.banner_ayristir(saha_banneri())
            self.sayac = 1
            return saha_banneri()

    gorulen: list = []
    monkeypatch.setattr(fm, "acilis_denetimi", lambda **k: gorulen.append(k) or {"eylem": "yok", "gerekce": "kayitci"})
    bs._donanim_guncellemesi_safe(_Sessiz(bagli=True), logging.getLogger("d1121"))
    assert gorulen and gorulen[0]["firmware_surum"] == KAYNAK_SURUM, f"sessiz el sıkışmada banner beklenmedi: {gorulen}"
