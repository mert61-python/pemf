# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B1 / B2 — modül yöneticisi (`servers/modul_yonetici.py`) kenar kolları, `/api/moduller` uçları (`servers/modul_router.py`),
ACİL DURDUR yayılımı (`api_server._modullere_acil_durdur`).

SÖZLEŞME:
  - Görünürlük kapalıyken seçim / uygula / başlat REDDEDİLİR (403); `durdur` görünürlükten BAĞIMSIZ (durdurma koşula bağlanmaz);
    görünürlük kapatılınca etkin modül BIRAKILIR. Bir anda TEK etkin modül (yeni seçim öncekini bırakır).
  - ACİL DURDUR: STM STOP'undan SONRA modüllere ARKA PLANDA gider; modül yayılımı TAKILSA da `_emergency_stop_all` döner; yönetici hiç
    kurulmadıysa iş YOK; yayılım hatası ACİL DURDUR'u düşürmez.
  - Süreç istemcisi: yanıt numarayla eşlenir, ölü süreçte istek None, yazım hatası takılmaz, kapatma öldürmeye düşer.
Sürücü süreci SAHTE (bellek içi); gerçek süreçlerle uçtan uca: `test_GA_B4_ornek_modul_KABUL.py`.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

MODUL = {"kimlik": "ornek", "sinirlar": {"frekans_hz": [1, 500]}}


class _SahteSurec:
    """`ModulSureci` yerine: yanıtlar tablodan; `takil` → yanıt yok."""

    ornekler: list = []

    def __init__(self, klasor):
        self.klasor = klasor
        self.cagri: list = []
        self.yanit = {
            "baglan": {"tamam": True},
            "kalp": {"tamam": True},
            "durum": {"tamam": True, "durum": {"bobin": True}},
        }
        self.canli_mi = True
        self.kapandi = False
        _SahteSurec.ornekler.append(self)

    def baslat(self):
        self.cagri.append("baslat_sureci")

    def canli(self):
        return self.canli_mi

    def oldu_mu(self, bekle_s=0.3):
        return not self.canli_mi

    def istek(self, islem, ayar=None, zaman_asimi=2.0):
        self.cagri.append(islem if ayar is None else (islem, ayar))
        return self.yanit.get(islem, {"tamam": True})

    def acil_durdur(self):
        self.cagri.append("acil")
        return True

    def kapat(self):
        self.kapandi = True


@pytest.fixture
def y(monkeypatch, tmp_path):
    from servers import modul_kayit
    from servers.modul_yonetici import ModulYoneticisi

    _SahteSurec.ornekler = []
    gorunur = {"v": True}
    monkeypatch.setattr(modul_kayit, "gorunur_mu", lambda: gorunur["v"])
    monkeypatch.setattr(modul_kayit, "bul", lambda k: (tmp_path / k, {**MODUL, "kimlik": k}))
    yon = ModulYoneticisi(surec_sinifi=_SahteSurec, kalp_aralik_s=0.01)
    yon._gorunur = gorunur
    yield yon
    yon.birak()


def test_KRITIK_GA_B1_yonetici_TEK_etkin_GIZLI_ve_KOMUTLAR(y):
    from servers.modul_kayit import ModulHatasi

    assert y.ozet() == {"etkin": None, "canli": False, "hata": None} and y.etkin_kimlik() is None
    with pytest.raises(ModulHatasi) as e:
        y.baslat()
    assert e.value.kod == "etkinModulYok"
    y._gorunur["v"] = False
    with pytest.raises(ModulHatasi) as e:
        y.sec("ornek")
    assert e.value.kod == "gizli"
    y._gorunur["v"] = True
    assert y.sec("ornek")["etkin"] == "ornek"
    a = _SahteSurec.ornekler[-1]
    assert y.uygula({"frekans_hz": 100}) == {"uygulandi": {"frekans_hz": 100}}
    assert ("uygula", {"frekans_hz": 100}) in a.cagri
    with pytest.raises(ModulHatasi):
        y.uygula({"frekans_hz": 9999})
    assert y.baslat()["etkin"] == "ornek" and y.durdur()["etkin"] == "ornek"
    assert y.durum()["surucu"] == {"bobin": True}
    time.sleep(0.05)
    assert a.cagri.count("kalp") >= 2  # kalp atışı akıyor
    y.sec("ikinci")  # TEK etkin: önceki bırakıldı
    assert a.kapandi and "durdur" in a.cagri and "kes" in a.cagri
    assert y.etkin_kimlik() == "ikinci"
    b = _SahteSurec.ornekler[-1]
    b.yanit["baslat"] = {"tamam": False, "hata": "kartYok"}
    with pytest.raises(ModulHatasi) as e:
        y.baslat()
    assert (e.value.kod, e.value.alan) == ("surucuHatasi", "kartYok")
    b.yanit["durdur"] = {"tamam": False}
    with pytest.raises(ModulHatasi) as e:
        y.durdur()
    assert (e.value.kod, e.value.alan) == ("surucuHatasi", "")
    b.yanit["baslat"] = None
    with pytest.raises(ModulHatasi) as e:
        y.baslat()
    assert e.value.kod == "surucuYanitsiz"
    b.canli_mi = False
    with pytest.raises(ModulHatasi) as e:
        y.baslat()
    assert e.value.kod == "surucuOldu" and y.ozet()["hata"] == "surucuOldu"
    assert y.birak() == {"etkin": None, "canli": False, "hata": "surucuOldu"}
    assert y.birak()["etkin"] is None  # ikinci bırakma zararsız


def test_KRITIK_GA_B1_baglanamazsa_SURECI_KAPATIR_ve_KALP_hatalari(y, monkeypatch):
    from servers import modul_yonetici
    from servers.modul_kayit import ModulHatasi

    class _Baglanmaz(_SahteSurec):
        def __init__(self, k):
            super().__init__(k)
            self.yanit["baglan"] = {"tamam": False, "hata": "kartBulunamadi"}

    y._surec_sinifi = _Baglanmaz
    with pytest.raises(ModulHatasi) as e:
        y.sec("ornek")
    assert (e.value.kod, e.value.alan) == ("baglanamadi", "kartBulunamadi")
    assert _SahteSurec.ornekler[-1].kapandi and y.etkin_kimlik() is None

    class _Yanitsiz(_SahteSurec):
        def __init__(self, k):
            super().__init__(k)
            self.yanit["baglan"] = None

    y._surec_sinifi = _Yanitsiz
    with pytest.raises(ModulHatasi) as e:
        y.sec("ornek")
    assert e.value.alan == "yanitYok"
    y._surec_sinifi = _SahteSurec
    y.sec("ornek")
    s = _SahteSurec.ornekler[-1]
    s.yanit["kalp"] = None
    time.sleep(0.05)
    assert y.ozet()["hata"] == "kalpYanitsiz" and y.ozet()["kalpHata"] >= 1
    s.yanit["kalp"] = {"tamam": True}
    time.sleep(0.05)
    assert y.ozet()["kalpHata"] == 0
    s.yanit["kalp"] = None
    s.canli_mi = False
    time.sleep(0.05)
    assert y.ozet()["hata"] == "surucuOldu"


def test_KRITIK_GA_B2_acil_durdur_hepsi_PARALEL_BUTCE_ve_TEKIL(y, monkeypatch):
    from servers import modul_yonetici

    assert y.acil_durdur_hepsi() == []  # etkin yok
    y.sec("ornek")
    assert y.acil_durdur_hepsi() == [{"kimlik": "ornek", "onay": True}]
    s = _SahteSurec.ornekler[-1]
    s.acil_durdur = lambda: time.sleep(5) or True  # takılan iletim
    t0 = time.perf_counter()
    assert y.acil_durdur_hepsi() == []  # bütçe doldu → beklemeden döner
    assert time.perf_counter() - t0 < 0.2
    s.canli_mi = False
    assert y.acil_durdur_hepsi() == []
    assert modul_yonetici.yonetici() is modul_yonetici.yonetici()
    monkeypatch.setattr(modul_yonetici, "_yonetici", None)
    assert modul_yonetici.varsa() is None
    assert isinstance(modul_yonetici.yonetici(), modul_yonetici.ModulYoneticisi)
    assert modul_yonetici.varsa() is not None


# ── süreç istemcisi (sahte Popen) ───────────────────────────────────────────────────────────────────
class _Popen:
    """Satır yanıtlayan sahte alt süreç: `yanitla(istek) → yanıt | None (sessiz)`."""

    def __init__(self, yanitla, yazma_hatasi=False, olmez=False):
        import queue

        self.q: queue.Queue = queue.Queue()
        self.donus = None
        self.oldurulme = 0
        self._olmez = olmez
        ust = self

        class _In:
            def write(self, b):
                if yazma_hatasi:
                    raise BrokenPipeError()
                i = json.loads(b.decode("utf-8"))
                r = yanitla(i)
                if r is not None:
                    ust.q.put((json.dumps({"id": i["id"], **r}) + "\n").encode("utf-8") if isinstance(r, dict) else r)

            def flush(self):
                pass

            def close(self):
                ust.bitir()

        class _Out:
            def __iter__(self):
                while True:
                    s = ust.q.get()
                    if s is None:
                        return
                    yield s

        self.stdin, self.stdout = _In(), _Out()

    def bitir(self):
        if not self._olmez:
            self.donus = 0
        self.q.put(None)

    def poll(self):
        return self.donus

    def wait(self, timeout=None):
        if self.donus is None:
            raise subprocess.TimeoutExpired("x", timeout)
        return 0

    def kill(self):
        self.oldurulme += 1
        self.donus = -9
        self.q.put(None)


def test_KRITIK_GA_B1_surec_istemcisi_YANIT_ESLEME_OLUM_ve_ACIL(tmp_path):
    from servers.modul_yonetici import ModulSureci

    p = _Popen(lambda i: {"tamam": True, "islem": i["islem"]} if i["islem"] != "sus" else None)
    s = ModulSureci(tmp_path, baslatici=lambda k: p)
    assert s.istek("kalp") is None and s.acil_durdur() is False  # başlamadan: ölü sayılır
    s.baslat()
    assert s.canli() and s.istek("kalp")["islem"] == "kalp"
    assert s.istek("uygula", {"a": 1}, 1)["tamam"] is True
    assert s.istek("sus", zaman_asimi=0.05) is None
    assert s.acil_durdur() is True and p.oldurulme == 0
    p.q.put(b"bozuk satir\n")  # bozuk yanıt yok sayılır
    p.q.put(b'"metin"\n')
    assert s.istek("kalp")["tamam"] is True
    assert s.oldu_mu(0.01) is False
    s.kapat()
    assert not s.canli() and s.oldu_mu() is True
    s.kapat()  # ikinci kapatma zararsız


def test_KRITIK_GA_B1_surec_istemcisi_ACIL_onaysiz_OLDURUR_yazim_hatasi_TAKILMAZ(tmp_path):
    from servers.modul_yonetici import ModulSureci

    p = _Popen(lambda i: None)  # hiç yanıtlamaz
    s = ModulSureci(tmp_path, baslatici=lambda k: p)
    s.baslat()
    t0 = time.perf_counter()
    assert s.acil_durdur() is False
    assert time.perf_counter() - t0 < 0.2 and p.oldurulme == 1
    s.oldur()  # ölüye öldürme zararsız
    p2 = _Popen(lambda i: {"tamam": False})
    s2 = ModulSureci(tmp_path, baslatici=lambda k: p2)
    s2.baslat()
    assert s2.acil_durdur() is False and p2.oldurulme == 1  # onaylamadı → öldürüldü
    p3 = _Popen(lambda i: {"tamam": True}, yazma_hatasi=True)
    s3 = ModulSureci(tmp_path, baslatici=lambda k: p3)
    s3.baslat()
    assert s3.istek("kalp", zaman_asimi=1) is None
    p4 = _Popen(lambda i: None, olmez=True)  # stdin kapanınca çıkmayan süreç → öldürülür
    s4 = ModulSureci(tmp_path, baslatici=lambda k: p4)
    s4.baslat()
    s4.kapat(bekle_s=0.01)
    assert p4.oldurulme == 1

    class _Kirik(_Popen):
        def kill(self):
            raise OSError("erişim")

    p5 = _Kirik(lambda i: None)
    s5 = ModulSureci(tmp_path, baslatici=lambda k: p5)
    s5.baslat()
    s5.oldur()  # öldürme hatası yutulur

    class _KirikOut(_Popen):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)

            class _O:
                def __iter__(self):
                    raise OSError("boru")

            self.stdout = _O()

    p6 = _KirikOut(lambda i: None)
    s6 = ModulSureci(tmp_path, baslatici=lambda k: p6)
    s6.baslat()
    time.sleep(0.05)
    assert s6.istek("kalp", zaman_asimi=0.05) is None


def test_KRITIK_GA_B1_varsayilan_baslatici_GIZLI_ALT_SUREC(monkeypatch, tmp_path):
    from servers import alt_surec, modul_yonetici
    from utils import gizli_surec

    gelen = {}

    def sahte(args, **kw):
        gelen.update(kw, args=args)
        return _Popen(lambda i: {"tamam": True})

    monkeypatch.setattr(gizli_surec, "baslat", sahte)
    s = modul_yonetici.ModulSureci(tmp_path)
    s.baslat()
    assert gelen["args"] == alt_surec.komut("modul-surucu", str(tmp_path))
    assert (
        gelen["stdin"] == subprocess.PIPE
        and gelen["stdout"] == subprocess.PIPE
        and gelen["stderr"] == subprocess.DEVNULL
    )
    s.kapat()


# ── HTTP uçları ─────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def c(y, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from servers import api_server, modul_kayit, modul_yonetici

    monkeypatch.setattr(modul_yonetici, "_yonetici", y)
    monkeypatch.setattr(modul_kayit, "liste", lambda: [{"kimlik": "ornek"}])
    yazilan = []

    def yaz(g):
        yazilan.append(g)
        y._gorunur["v"] = g
        return g

    monkeypatch.setattr(modul_kayit, "gorunur_yaz", yaz)
    istemci = TestClient(api_server.app)
    istemci.yazilan = yazilan
    return istemci


def test_KRITIK_GA_B1_uclar_GIZLI_varsayilan_KODLU_hatalar(c, y, monkeypatch):
    from servers import modul_kayit, modul_yonetici

    y._gorunur["v"] = False
    assert c.get("/api/moduller").json() == {
        "gorunur": False,
        "moduller": [],
        "etkin": None,
        "canli": False,
        "hata": None,
    }
    for yol in ("/api/moduller/ornek/sec", "/api/moduller/baslat"):
        r = c.post(yol, json={})  # arayüz `apiPost(…, {})` gibi JSON (D5 kapısı aşağıda)
        assert (r.status_code, r.json()["detail"]) == (403, {"kod": "gizli", "alan": ""})
    r = c.post("/api/moduller/uygula", json={"ayar": {"frekans_hz": 1}})
    assert r.status_code == 403
    r = c.post("/api/moduller/durdur")  # görünürlükten BAĞIMSIZ — etkin yok → 409
    assert (r.status_code, r.json()["detail"]["kod"]) == (409, "etkinModulYok")
    assert c.post("/api/moduller/gorunurluk", json={"gorunur": True}).json() == {"gorunur": True}
    assert c.get("/api/moduller").json()["moduller"] == [{"kimlik": "ornek"}]
    assert c.post("/api/moduller/ornek/sec", json={}).json()["etkin"] == "ornek"
    assert c.post("/api/moduller/uygula", json={"ayar": {"frekans_hz": 100}}).json() == {
        "uygulandi": {"frekans_hz": 100}
    }
    r = c.post("/api/moduller/uygula", json={"ayar": {"frekans_hz": 9999}})
    assert (r.status_code, r.json()["detail"]) == (400, {"kod": "ayarSinirDisi", "alan": "frekans_hz"})
    assert (
        c.post("/api/moduller/baslat", json={}).status_code == 200 and c.post("/api/moduller/durdur").status_code == 200
    )
    assert c.get("/api/moduller/durum").json()["surucu"] == {"bobin": True}
    assert c.post("/api/moduller/birak").json()["etkin"] is None
    c.post("/api/moduller/ornek/sec", json={})
    assert c.post("/api/moduller/gorunurluk", json={"gorunur": False}).json() == {"gorunur": False}
    assert y.etkin_kimlik() is None  # gizleyince BIRAKILDI
    monkeypatch.setattr(modul_kayit, "bul", lambda k: (_ for _ in ()).throw(modul_kayit.ModulHatasi("modulYok")))
    y._gorunur["v"] = True
    assert c.post("/api/moduller/yok/sec", json={}).status_code == 404
    monkeypatch.setattr(modul_yonetici, "_yonetici", None)
    assert c.post("/api/moduller/gorunurluk", json={"gorunur": False}).status_code == 200  # yönetici yokken kurulmaz
    assert modul_yonetici.varsa() is None

    def _yazilamaz(g):
        raise OSError("salt okunur")

    monkeypatch.setattr(modul_kayit, "gorunur_yaz", _yazilamaz)
    r = c.post("/api/moduller/gorunurluk", json={"gorunur": True})
    assert (r.status_code, r.json()["detail"]["kod"]) == (503, "ayarYazilamadi")


@pytest.mark.parametrize(
    "basliklar,govde",
    [({}, None), ({"Content-Type": "text/plain"}, "x"), ({"Content-Type": "application/x-www-form-urlencoded"}, "a=1")],
)
def test_KRITIK_OYZ_D5_modul_SECME_BASLATMA_basit_POSTla_YAPILAMAZ_durdurma_YAPILIR(c, y, basliklar, govde):
    """D5 envanteri (OYZ): çapraz kökenli basit POST (gövdesiz / text/plain / form) modülü SEÇEMEZ, BAŞLATAMAZ — 415 `jsonGerekli`,
    yöneticiye HİÇ gidilmez; JSON isteği aynı uçta sürer. `durdur` / `birak` basit POST'la da çalışır (STOP yalnız güvenliği artırır)."""
    for yol in ("/api/moduller/ornek/sec", "/api/moduller/baslat"):
        r = c.post(yol, headers={"Origin": "http://kotu.example", **basliklar}, content=govde)
        assert (r.status_code, r.json()["detail"]) == (415, {"kod": "jsonGerekli", "alan": ""}), yol
    assert y.etkin_kimlik() is None and _SahteSurec.ornekler == []  # süreç bile açılmadı
    assert c.post("/api/moduller/ornek/sec", json={}).json()["etkin"] == "ornek"
    assert c.post("/api/moduller/baslat", json={}).status_code == 200
    s = _SahteSurec.ornekler[-1]
    assert (
        c.post(
            "/api/moduller/durdur", headers={"Origin": "http://kotu.example", **basliklar}, content=govde
        ).status_code
        == 200
    )
    assert "durdur" in s.cagri
    r = c.post("/api/moduller/birak", headers={"Origin": "http://kotu.example", **basliklar}, content=govde)
    assert r.status_code == 200 and r.json()["etkin"] is None and s.kapandi


# ── B2: ACİL DURDUR yayılımı ────────────────────────────────────────────────────────────────────────
def test_KRITIK_GA_B2_ACIL_DURDUR_STM_SONRASI_arka_planda_TAKILSA_da_DONER(monkeypatch):
    from ai_pro_aparati import istemci, mandali_sifirla
    from servers import api_server, modul_yonetici

    sira: list[str] = []
    birak = threading.Event()
    basladi = threading.Event()

    class _HW:
        def stop_all_coils(self):
            sira.append("stm")
            return True

    class _Takilan:
        def acil_durdur_hepsi(self):
            sira.append("moduller")
            basladi.set()
            birak.wait(30)
            return []

    monkeypatch.setattr(api_server.state, "hardware", _HW())
    monkeypatch.setattr(modul_yonetici, "_yonetici", _Takilan())
    try:
        t0 = time.monotonic()
        api_server._emergency_stop_all(reason="ga-b2", kalici=False)
        assert time.monotonic() - t0 < 2.0
        assert basladi.wait(5)
        assert sira == ["stm", "moduller"]  # modüller STM'den SONRA
        c = istemci(api_server.app)
        t0 = time.monotonic()
        assert c.post("/api/hardware/emergency_stop").status_code == 200
        assert time.monotonic() - t0 < 5.0
    finally:
        birak.set()
        mandali_sifirla(istemci(api_server.app))


def test_KRITIK_GA_B2_yayilim_HATASI_ACIL_DURDURU_dusurmez(monkeypatch, caplog):
    from servers import api_server, modul_yonetici

    monkeypatch.setattr(modul_yonetici, "varsa", lambda: (_ for _ in ()).throw(RuntimeError("bozuk")))
    with caplog.at_level("ERROR"):
        api_server._modullere_acil_durdur()
    assert "modüllere iletilemedi" in caplog.text
    monkeypatch.setattr(modul_yonetici, "varsa", lambda: None)
    once = threading.active_count()
    api_server._modullere_acil_durdur()  # yönetici yok → iş parçacığı açılmaz
    assert threading.active_count() == once


def test_KRITIK_GA_B1_alt_surec_MODUL_SURUCU_dagitimi(monkeypatch):
    from servers import alt_surec, modul_surucu

    monkeypatch.setattr(modul_surucu, "main", lambda argv: 11 if argv == ["k"] else 0)
    assert alt_surec.calistir(["modul-surucu", "k"]) == 11


def test_KRITIK_GA_B1_kapatma_stdin_KAPANMAZSA_oldurur(tmp_path):
    from servers.modul_yonetici import ModulSureci

    p = _Popen(lambda i: None, olmez=True)

    def _kapanmaz():
        raise OSError("boru kırık")

    p.stdin.close = _kapanmaz
    s = ModulSureci(tmp_path, baslatici=lambda k: p)
    s.baslat()
    s.kapat(bekle_s=0.01)
    assert p.oldurulme == 1
