# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/tunnel_manager.py · sözleşmeler: paket adayı arama (frozen `_MEIPASS` / EXE yanı; stat hatası veren
aday atlanır; hiçbiri yoksa None) · arşiv önbelleği özet eki yoksa reddedilir · indirme hata kolları (önbellek dizini kurulamaz / kısa
gövde / arşivde ikili yok / arşiv üyesi tavanı aşar — hepsinde None, önbellekte iz yok) · stderr URL okuyucu (URL değişiminde geri
çağrı, aynı URL'de tekrar yok, geri çağrı hatası yutulur, çözülemeyen satır atlanır) · `start_tunnel` (zaten çalışıyorsa yeni süreç
yok; kasa düşerse ortam değişkeni; kısa token yok sayılır → QUICK; NAMED+hostname URL'yi stderr okumadan yayınlar ve stderr DEVNULL;
NAMED hostname'siz okuyucu açar; Popen hatası False) · `stop_tunnel` (terminate → wait(5) → zaman aşımında kill; durum temizlenir) ·
`_internet_up` / `_tunnel_alive` / `_tunnel_url_alive` · watchdog döngüsü (çevrimdışı bekler; başlatma hatasında 20→40→80→160→300
üstel geri çekilme; dış URL iki ARDIŞIK ölüde yeniden başlatma, arada sağlıklı tur sayacı sıfırlar; döngü hatası bildirilir, döngü
yaşar; ikinci başlatma çağrısı yeni thread açmaz).

Sahte EN ALT katta: `subprocess.Popen` (süreç YOK — komut ve argümanlar kaydedilir), `urllib.request.urlopen` (ağ YOK; [SAHİBE]
T-1 ve karşıtında bir kat daha aşağıda: yalnız https taşıyıcısı `HTTPSHandler.https_open`, üstündeki urllib zinciri GERÇEK),
`socket.create_connection` (ağ YOK), `platform.system` / `platform.machine`, `sys.frozen` / `sys._MEIPASS` / `sys.executable`
(paket kökü tmp_path'te), `utils.secrets_manager.get_secret` (kasa YOK), watchdog'un bekleme olayı `_watchdog_stop` (saat — gerçek
bekleme YOK; her `wait()` bir senaryo adımı). Modül durumu (`_tunnel_*`, `_url_callbacks`, `_watchdog_*`) her testte monkeypatch ile
eski hâline döner; açılan her thread join edilir.
"""

from __future__ import annotations

import email.message
import hashlib
import io
import logging
import os
import platform
import socket
import subprocess
import sys
import tarfile
import threading
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path

import pytest
from servers import tunnel_manager as tm

URL1 = "https://ilk-ornek.trycloudflare.com"
URL2 = "https://ikinci-ornek.trycloudflare.com"
# KP-2 A2: bekçi 4xx / 5xx testleri GERÇEK urllib zincirini kullanır (`ortam` fikstürü urlopen'u sahteler → içe aktarma anındaki gerçeği geri koy)
_GERCEK_URLOPEN = urllib.request.urlopen
UZUN_TOKEN = "eyJ" + "a" * 60  # gerçek token uzun base64 (>= 40)


# ── Sahteler ─────────────────────────────────────────────────────────────────


class _Akis:
    """cloudflared stderr'i: satır satır okunur, sonda b'' (EOF)."""

    def __init__(self, satirlar):
        self._satirlar = list(satirlar)

    def readline(self):
        return self._satirlar.pop(0) if self._satirlar else b""


class _Surec:
    """subprocess.Popen'ın döndürdüğü süreç (EN ALT kat)."""

    def __init__(self, satirlar=(), canli=True, wait_hatasi=None):
        self.stderr = _Akis(satirlar)
        self._canli = canli
        self.wait_hatasi = wait_hatasi
        self.cagrilar: list = []

    def poll(self):
        return None if self._canli else 0

    def terminate(self):
        self.cagrilar.append("terminate")

    def wait(self, timeout=None):
        self.cagrilar.append(("wait", timeout))
        if self.wait_hatasi is not None:
            raise self.wait_hatasi
        self._canli = False
        return 0

    def kill(self):
        self.cagrilar.append("kill")
        self._canli = False


class _Popen:
    """Popen sahtesi: sıradaki süreci ya da istisnayı döndürür; komut + kwargs kaydı."""

    def __init__(self):
        self.kayit: list = []
        self.sira: list = []

    def __call__(self, cmd, *a, **k):
        self.kayit.append(([str(x) for x in cmd], k))
        if not self.sira:
            raise FileNotFoundError(2, "Sistem belirtilen dosyayı bulamıyor")
        s = self.sira.pop(0)
        if isinstance(s, BaseException):
            raise s
        return s


class _Yanit:
    def __init__(self, govde=b"", status=200, kod=None):
        self._g = govde
        self._i = 0
        self.status = status
        self._kod = status if kod is None else kod

    def read(self, n=None):
        r = self._g[self._i :] if n is None else self._g[self._i : self._i + n]
        self._i += len(r)
        return r

    def getcode(self):
        return self._kod

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Urlopen:
    def __init__(self):
        self.urller: list = []
        self.sira: list = []

    def __call__(self, url, *a, **k):
        self.urller.append((str(url), k.get("timeout")))
        if not self.sira:
            raise AssertionError("beklenmeyen ağ isteği (ağ YOK)")
        s = self.sira[0] if len(self.sira) == 1 else self.sira.pop(0)  # son öğe kalıcı
        if isinstance(s, BaseException):
            raise s
        return s


class _Baglanti:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Soket:
    """socket.create_connection sahtesi: (adres, timeout) kaydı; `sonuc` OSError / başka istisna / True."""

    def __init__(self, sonuc=True):
        self.kayit: list = []
        self.sonuc = sonuc

    def __call__(self, adres, timeout=None):
        self.kayit.append((adres, timeout))
        s = self.sonuc(adres) if callable(self.sonuc) else self.sonuc
        if isinstance(s, BaseException):
            raise s
        return _Baglanti()


class _SahteOlay:
    """watchdog'un `_watchdog_stop` olayı (SAAT): wait() gerçekten beklemez, süreyi kaydeder ve senaryonun sıradaki adımını koşar.
    Adımlar bitince olay kurulur → döngü çıkar."""

    def __init__(self, adimlar):
        self._adimlar = list(adimlar)
        self._kurulu = False
        self.beklemeler: list = []
        self.temizle_sayisi = 0

    def is_set(self):
        return self._kurulu

    def set(self):
        self._kurulu = True

    def clear(self):
        self.temizle_sayisi += 1
        self._kurulu = False

    def wait(self, t=None):
        self.beklemeler.append(t)
        if self._adimlar:
            adim = self._adimlar.pop(0)
            if adim is not None:
                adim()
        if not self._adimlar:
            self._kurulu = True
        return self._kurulu


# ── Aparat ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _durum(monkeypatch):
    """Modül geneli durum bu dosyada her testte temiz başlar ve eski hâline döner."""
    monkeypatch.setattr(tm, "_tunnel_process", None)
    monkeypatch.setattr(tm, "_tunnel_url", "")
    monkeypatch.setattr(tm, "_tunnel_thread", None)
    monkeypatch.setattr(tm, "_url_callbacks", [])
    monkeypatch.setattr(tm, "_watchdog_thread", None)
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    yield


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    """Popen / urlopen / soket / kasa sahteleri + paketli ikili (frozen `_MEIPASS`)."""
    popen = _Popen()
    uo = _Urlopen()
    soket = _Soket(True)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(urllib.request, "urlopen", uo)
    monkeypatch.setattr(socket, "create_connection", soket)
    monkeypatch.setattr(tm, "_BIN_DIR", tmp_path / "onbellek")
    import utils.secrets_manager as sm

    sirlar: dict = {}
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: sirlar.get(ad, ""))
    mei = tmp_path / "meipass"
    (mei / "bin" / "cloudflared").mkdir(parents=True)
    paketli = mei / "bin" / "cloudflared" / "cloudflared.exe"
    paketli.write_bytes(b"PAKETLI-IKILI")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)

    class O:
        pass

    o = O()
    o.popen, o.urlopen, o.soket, o.sirlar, o.paketli = popen, uo, soket, sirlar, paketli
    return o


def _okuyucuyu_bekle():
    t = tm._tunnel_thread
    if t is not None:
        t.join(10)
        assert not t.is_alive(), "stderr okuyucu thread'i bitmedi"


def _watchdog_kos(olay, monkeypatch, port=48999, ci=20):
    monkeypatch.setattr(tm, "_watchdog_stop", olay)
    tm.start_tunnel_watchdog(port=port, check_interval=ci)
    t = tm._watchdog_thread
    assert t is not None and t.name == "CloudflareTunnelWatchdog"
    t.join(10)
    assert not t.is_alive(), "watchdog döngüsü olay kurulunca çıkmadı"
    _okuyucuyu_bekle()


# ── _bundled_cloudflared ─────────────────────────────────────────────────────


def test_paket_adayi_STAT_hatasi_verirse_atlanir_EXE_yanindaki_ikili_doner(monkeypatch, tmp_path):
    """frozen; `_MEIPASS` adayı stat'ta PermissionError → aday atlanır, EXE yanındaki `bin/cloudflared/cloudflared.exe` döner."""
    mei = tmp_path / "meipass"
    exe_dizin = tmp_path / "kurulum"
    (exe_dizin / "bin" / "cloudflared").mkdir(parents=True)
    hedef = exe_dizin / "bin" / "cloudflared" / "cloudflared.exe"
    hedef.write_bytes(b"EXE-YANI")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dizin / "PEMF_Backend.exe"))
    orj = Path.exists
    denenen: list = []

    def _exists(self):
        if str(self).startswith(str(mei)):
            denenen.append(str(self))
            raise PermissionError(13, "Erişim engellendi", str(self))
        return orj(self)

    monkeypatch.setattr(Path, "exists", _exists)
    sonuc = tm._bundled_cloudflared()
    assert sonuc is not None and sonuc.resolve() == hedef.resolve(), sonuc
    assert denenen and denenen[0] == str(mei / "bin" / "cloudflared" / "cloudflared.exe"), denenen


def test_paket_adayi_HICBIR_kokte_yoksa_None(monkeypatch, tmp_path):
    """frozen; ne `_MEIPASS` ne EXE yanında ikili var → None (indirme koluna düşülür)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bos_mei"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bos_exe" / "PEMF_Backend.exe"))
    assert tm._bundled_cloudflared() is None


# ── _onbellek_dogrulandi ─────────────────────────────────────────────────────


def test_arsiv_onbellegi_OZET_EKI_yoksa_reddedilir_varsa_kabul(monkeypatch, tmp_path):
    """.tgz varlığı; çıkarılmış ikilinin `.sha256` eki yok → False (istisna yutulur); doğru ek yazılınca → True."""
    ikili = tmp_path / "cloudflared-darwin"
    ikili.write_bytes(b"D" * 64)
    monkeypatch.setattr(tm, "_ASGARI_BOYUT", 10)
    assert tm._onbellek_dogrulandi(ikili, "cloudflared-darwin-arm64.tgz") is False
    tm._ozet_eki(ikili).write_text(hashlib.sha256(b"D" * 64).hexdigest().upper() + "\n", encoding="ascii")
    assert tm._onbellek_dogrulandi(ikili, "cloudflared-darwin-arm64.tgz") is True


# ── _download_cloudflared hata kolları ───────────────────────────────────────


@pytest.fixture
def indir(monkeypatch, tmp_path):
    """Paket YOK (frozen, boş `_MEIPASS` ve EXE dizini), önbellek tmp; urlopen sahte."""
    uo = _Urlopen()
    monkeypatch.setattr(urllib.request, "urlopen", uo)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bos_mei"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bos_exe" / "PEMF_Backend.exe"))
    monkeypatch.setattr(tm, "_BIN_DIR", tmp_path / "onbellek")
    return uo


def test_onbellek_DIZINI_kurulamazsa_None_ve_INDIRME_yok(indir, monkeypatch, tmp_path):
    """Önbellek dizininin üstü bir DOSYA (mkdir düşer) → None; urlopen hiç çağrılmaz."""
    engel = tmp_path / "engel"
    engel.write_text("dosya", encoding="utf-8")
    monkeypatch.setattr(tm, "_BIN_DIR", engel / "cloudflared")
    assert tm._download_cloudflared() is None
    assert indir.urller == []


def test_KISA_govde_ozeti_tutsa_bile_YERLESMEZ(indir, monkeypatch, tmp_path):
    """Pinli özeti TUTAN ama asgari boyutun altındaki gövde → None; önbellekte ikili ve geçici dosya kalmaz."""
    govde = b"K" * 1000
    monkeypatch.setattr(tm, "_CLOUDFLARED_OZET", {"cloudflared-windows-amd64.exe": hashlib.sha256(govde).hexdigest()})
    indir.sira = [_Yanit(govde)]
    assert tm._download_cloudflared() is None
    assert len(indir.urller) == 1 and indir.urller[0][1] == 60
    assert sorted(p.name for p in (tmp_path / "onbellek").iterdir()) == []


def _tgz(uyeler: dict) -> bytes:
    tamp = io.BytesIO()
    with tarfile.open(fileobj=tamp, mode="w:gz") as t:
        for ad, icerik in uyeler.items():
            bilgi = tarfile.TarInfo(ad)
            bilgi.size = len(icerik)
            bilgi.mode = 0o755
            t.addfile(bilgi, io.BytesIO(icerik))
    return tamp.getvalue()


def _darwin_arsiv(monkeypatch, arsiv: bytes):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    monkeypatch.setattr(tm, "_ASGARI_BOYUT", 100)
    monkeypatch.setattr(tm, "_CLOUDFLARED_OZET", {"cloudflared-darwin-arm64.tgz": hashlib.sha256(arsiv).hexdigest()})


def test_arsivde_cloudflared_UYESI_yoksa_None(indir, monkeypatch, tmp_path):
    """Darwin .tgz özeti tutar ama içinde `cloudflared` adlı dosya yok → None; ikili / özet eki yerleşmez, geçici kalmaz."""
    arsiv = _tgz({"README.md": os.urandom(4000)})
    _darwin_arsiv(monkeypatch, arsiv)
    indir.sira = [_Yanit(arsiv)]
    assert tm._download_cloudflared() is None
    assert "/2026.6.1/cloudflared-darwin-arm64.tgz" in indir.urller[0][0]
    assert sorted(p.name for p in (tmp_path / "onbellek").iterdir()) == []


def test_arsiv_UYESI_boyut_tavanini_asarsa_None(indir, monkeypatch, tmp_path):
    """Arşiv (sıkışık) tavanın altında ama içindeki `cloudflared` üyesi tavanı aşıyor → None; çıkarılmış ikili yerleşmez."""
    arsiv = _tgz({"pkg/cloudflared": b"\0" * 400_000})
    assert len(arsiv) < 50_000
    _darwin_arsiv(monkeypatch, arsiv)
    monkeypatch.setattr(tm, "_AZAMI_INDIRME", 100_000)
    indir.sira = [_Yanit(arsiv)]
    assert tm._download_cloudflared() is None
    assert sorted(p.name for p in (tmp_path / "onbellek").iterdir()) == []


# ── _read_url_from_output ────────────────────────────────────────────────────


def test_okuyucu_URL_degisiminde_geri_cagirir_ayni_URL_de_tekrar_etmez(monkeypatch):
    """stderr: gürültü, URL1, URL1 (yeniden), URL2 → `_tunnel_url` = URL2; geri çağrılar [URL1, URL2]; hata fırlatan geri çağrı
    sonrakileri ENGELLEMEZ."""
    gelen: list = []

    def _bozuk(u):
        raise RuntimeError("GUI kapandı")

    tm.register_url_callback(_bozuk)
    tm.register_url_callback(gelen.append)
    surec = _Surec(
        [
            b"2026-11-01T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...\n",
            b"\n",
            f"INF |  {URL1}  |\n".encode(),
            f"INF yeniden: {URL1}\n".encode(),
            f"INF reconnect -> {URL2}\n".encode(),
        ]
    )
    tm._read_url_from_output(surec, 48999)
    assert tm.get_tunnel_url() == URL2
    assert gelen == [URL1, URL2]


def test_okuyucu_COZULEMEYEN_satiri_atlar_sonrakinden_URL_yakalar():
    """stderr metin kipinde (str satır, `.decode` yok) bir satır verir → o satır atlanır; sonraki bayt satırdaki URL yakalanır."""
    surec = _Surec([f"metin satiri {URL2}", f"INF {URL1}\n".encode()])
    tm._read_url_from_output(surec, 48999)
    assert tm.get_tunnel_url() == URL1


# ── start_tunnel ─────────────────────────────────────────────────────────────


def test_start_tunnel_zaten_CALISIYORSA_yeni_surec_ACMAZ(ortam):
    """Canlı süreç varken start_tunnel → True; Popen ve indirme çağrılmaz, süreç aynı kalır."""
    eski = _Surec(canli=True)
    tm._tunnel_process = eski
    assert tm.start_tunnel(port=48999) is True
    assert ortam.popen.kayit == [] and ortam.urlopen.urller == []
    assert tm._tunnel_process is eski


def test_start_tunnel_QUICK_okuyucu_URL_yi_yakalar_ve_geri_cagirir(ortam):
    """Token yok → QUICK komutu `tunnel --url http://localhost:<port>`, stderr=PIPE, CREATE_NO_WINDOW; okuyucu URL'yi yakalar."""
    gelen: list = []
    tm.register_url_callback(gelen.append)
    surec = _Surec([f"INF {URL1}\n".encode()])
    ortam.popen.sira = [surec]
    assert tm.start_tunnel(port=48999) is True
    _okuyucuyu_bekle()
    cmd, kw = ortam.popen.kayit[0]
    assert cmd == [str(ortam.paketli), "tunnel", "--url", "http://localhost:48999"]
    assert kw["stderr"] == subprocess.PIPE and kw["stdout"] == subprocess.DEVNULL
    assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert tm._tunnel_process is surec and tm._tunnel_thread.name == "CloudflareTunnelReader"
    assert tm.get_tunnel_url() == URL1 and gelen == [URL1]


def test_start_tunnel_KISA_token_yok_sayilir_QUICK_tunele_duser(ortam):
    """Kasadaki token placeholder ('1', < 40 karakter) → yok sayılır: komutta `--token` YOK, QUICK `--url` var."""
    ortam.sirlar.update({"cloudflare_tunnel_token": " 1 ", "tunnel_hostname": "uzak.klinik.example"})
    ortam.popen.sira = [_Surec([])]
    assert tm.start_tunnel(port=48999) is True
    _okuyucuyu_bekle()
    cmd, kw = ortam.popen.kayit[0]
    assert "--token" not in cmd and cmd[1:3] == ["tunnel", "--url"]
    assert kw["stderr"] == subprocess.PIPE
    assert tm.get_tunnel_url() == ""


def test_start_tunnel_NAMED_hostname_URL_yi_stderr_OKUMADAN_yayinlar(ortam):
    """Uzun token + hostname → `tunnel run --token`, stderr=DEVNULL (okunmayan boru dolmaz), URL https://<hostname>, okuyucu thread
    YOK; hata fırlatan geri çağrı diğerini engellemez."""
    gelen: list = []

    def _bozuk(u):
        raise ValueError("bozuk geri çağrı")

    tm.register_url_callback(_bozuk)
    tm.register_url_callback(gelen.append)
    ortam.sirlar.update({"cloudflare_tunnel_token": UZUN_TOKEN, "tunnel_hostname": "uzak.klinik.example"})
    surec = _Surec([])
    ortam.popen.sira = [surec]
    assert tm.start_tunnel(port=48999) is True
    cmd, kw = ortam.popen.kayit[0]
    assert cmd == [str(ortam.paketli), "tunnel", "run", "--token", UZUN_TOKEN]
    assert kw["stderr"] == subprocess.DEVNULL
    assert tm._tunnel_thread is None
    assert tm.get_tunnel_url() == "https://uzak.klinik.example" and gelen == ["https://uzak.klinik.example"]
    assert tm._tunnel_process is surec


def test_start_tunnel_NAMED_http_hostname_AYNEN_kullanilir(ortam):
    """hostname zaten 'http' ile başlıyorsa önek eklenmez."""
    ortam.sirlar.update({"cloudflare_tunnel_token": UZUN_TOKEN, "tunnel_hostname": "http://ic.klinik.example"})
    ortam.popen.sira = [_Surec([])]
    assert tm.start_tunnel(port=48999) is True
    assert tm.get_tunnel_url() == "http://ic.klinik.example"


def test_start_tunnel_KASA_dusunce_ortam_degiskeni_kullanilir(ortam, monkeypatch):
    """get_secret fırlatır → PEMF_CLOUDFLARE_TUNNEL_TOKEN / PEMF_TUNNEL_HOSTNAME (kırpılmış) kullanılır → NAMED + hostname."""
    import utils.secrets_manager as sm

    def _kasa(*a, **k):
        raise RuntimeError("kasa kilitli")

    monkeypatch.setattr(sm, "get_secret", _kasa)
    monkeypatch.setenv("PEMF_CLOUDFLARE_TUNNEL_TOKEN", f"  {UZUN_TOKEN}  ")
    monkeypatch.setenv("PEMF_TUNNEL_HOSTNAME", " env.klinik.example ")
    ortam.popen.sira = [_Surec([])]
    assert tm.start_tunnel(port=48999) is True
    cmd, kw = ortam.popen.kayit[0]
    assert cmd[-2:] == ["--token", UZUN_TOKEN] and kw["stderr"] == subprocess.DEVNULL
    assert tm.get_tunnel_url() == "https://env.klinik.example"


def test_start_tunnel_NAMED_hostnamesiz_okuyucu_ACAR(ortam):
    """Uzun token, hostname yok → `tunnel run --token`, stderr=PIPE ve okuyucu thread başlar (URL stderr'den)."""
    ortam.sirlar.update({"cloudflare_tunnel_token": UZUN_TOKEN})
    ortam.popen.sira = [_Surec([f"INF {URL2}\n".encode()])]
    assert tm.start_tunnel(port=48999) is True
    _okuyucuyu_bekle()
    cmd, kw = ortam.popen.kayit[0]
    assert cmd[1:4] == ["tunnel", "run", "--token"] and kw["stderr"] == subprocess.PIPE
    assert tm.get_tunnel_url() == URL2


def test_start_tunnel_ikili_YOKSA_False_ve_surec_yok(ortam, monkeypatch, tmp_path):
    """Paket yok, önbellek yok, Linux (pinli özet yok) → False; Popen çağrılmaz."""
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bos"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bos2" / "x.exe"))
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert tm.start_tunnel(port=48999) is False
    assert ortam.popen.kayit == [] and ortam.urlopen.urller == []


# ── stop_tunnel / _tunnel_alive ──────────────────────────────────────────────


def test_stop_tunnel_canli_sureci_TERMINATE_wait5_ile_durdurur_durumu_temizler():
    """Canlı süreç → terminate, wait(timeout=5); kill YOK; süreç None, URL ''."""
    s = _Surec(canli=True)
    tm._tunnel_process, tm._tunnel_url = s, URL1
    assert tm._tunnel_alive() is True
    tm.stop_tunnel()
    assert s.cagrilar == ["terminate", ("wait", 5)]
    assert tm._tunnel_process is None and tm.get_tunnel_url() == ""
    assert tm._tunnel_alive() is False


def test_stop_tunnel_wait_ZAMAN_ASIMINDA_KILL():
    """terminate sonrası wait TimeoutExpired → kill çağrılır."""
    s = _Surec(canli=True, wait_hatasi=subprocess.TimeoutExpired(["cloudflared"], 5))
    tm._tunnel_process = s
    tm.stop_tunnel()
    assert s.cagrilar == ["terminate", ("wait", 5), "kill"]


def test_stop_tunnel_OLMUS_surece_dokunmaz_ama_durumu_temizler():
    """Süreç zaten bitmiş (poll() = 0) → terminate/kill YOK; URL yine '' olur; `_tunnel_alive` False."""
    s = _Surec(canli=False)
    tm._tunnel_process, tm._tunnel_url = s, URL1
    assert tm._tunnel_alive() is False
    tm.stop_tunnel()
    assert s.cagrilar == [] and tm.get_tunnel_url() == "" and tm._tunnel_process is None


# ── _internet_up / _tunnel_url_alive ─────────────────────────────────────────


def test_internet_up_ILK_host_duserse_IKINCIYI_dener(monkeypatch):
    """1.1.1.1:53 OSError, 8.8.8.8:53 bağlanır → True; ikisi de OSError → False; timeout iletilir."""
    soket = _Soket(lambda a: OSError(10065, "Ulaşılamayan ana bilgisayar") if a[0] == "1.1.1.1" else True)
    monkeypatch.setattr(socket, "create_connection", soket)
    assert tm._internet_up(timeout=1.5) is True
    assert soket.kayit == [(("1.1.1.1", 53), 1.5), (("8.8.8.8", 53), 1.5)]
    soket.sonuc = OSError(10051, "Ağa ulaşılamıyor")
    soket.kayit.clear()
    assert tm._internet_up() is False
    assert [a for a, _ in soket.kayit] == [("1.1.1.1", 53), ("8.8.8.8", 53)]


def test_tunnel_url_alive_URL_yoksa_ISTEK_ATMADAN_True(monkeypatch):
    """URL henüz yok → True (süreç denetimine bırakılır); ağ isteği yok."""
    uo = _Urlopen()
    monkeypatch.setattr(urllib.request, "urlopen", uo)
    assert tm._tunnel_url_alive() is True
    assert uo.urller == []


def test_tunnel_url_alive_saglik_200_True_ag_hatasi_False(monkeypatch):
    """URL var: `<url>/api/health` 200 → True (timeout iletilir); status yoksa getcode kullanılır; URLError / 530 → False."""
    uo = _Urlopen()
    monkeypatch.setattr(urllib.request, "urlopen", uo)
    tm._tunnel_url = URL1
    uo.sira = [_Yanit(status=200)]
    assert tm._tunnel_url_alive(timeout=2.0) is True
    assert uo.urller == [(URL1 + "/api/health", 2.0)]
    uo.sira = [_Yanit(status=None, kod=204)]
    assert tm._tunnel_url_alive() is True
    uo.sira = [urllib.error.URLError("getaddrinfo failed")]
    assert tm._tunnel_url_alive() is False
    uo.sira = [urllib.error.HTTPError(URL1 + "/api/health", 530, "Origin Unreachable", {}, None)]
    assert tm._tunnel_url_alive() is False


class _HttpsTasiyici(urllib.request.HTTPSHandler):
    """urllib'in EN ALT katı: https taşıyıcısı. Bağlantı AÇMAZ; verilen durum koduyla bellekteki yanıtı döndürür. Üstündeki GERÇEK
    zincir (urlopen → OpenerDirector → HTTPErrorProcessor → HTTPDefaultErrorHandler) olduğu gibi koşar — 4xx/5xx'te HTTPError'ı
    test değil, GERÇEK urllib üretir."""

    def __init__(self, kod: int):
        super().__init__()
        self.kod = kod
        self.istekler: list = []

    def https_open(self, req):
        self.istekler.append(req.full_url)
        yanit = urllib.response.addinfourl(
            io.BytesIO(b'{"ok":true}'), email.message.Message(), req.full_url, code=self.kod
        )
        yanit.msg = "aparat"
        return yanit


def _gercek_zincir(monkeypatch, kod):
    """`urllib.request.urlopen` GERÇEK; yalnız genel açıcının https taşıyıcısı `_HttpsTasiyici(kod)` (ağ YOK)."""
    t = _HttpsTasiyici(kod)
    monkeypatch.setattr(urllib.request, "_opener", urllib.request.build_opener(t))
    tm._tunnel_url = "https://uzak.klinik.example"
    return t


@pytest.mark.parametrize("kod,beklenen", [(200, True), (204, True), (530, False)])
def test_tunnel_url_alive_GERCEK_urllib_zinciri_2xx_CANLI_530_OLU(monkeypatch, kod, beklenen):
    """GERÇEK urllib zinciri, yalnız https taşıyıcısı sahte: 2xx → True, 530 (Cloudflare origin unreachable) → False; istek
    `<url>/api/health`'e TEK kez gider. (Aşağıdaki 4xx / 5xx testlerinin aparatı bu karşıtla doğrulanır.)"""
    t = _gercek_zincir(monkeypatch, kod)
    assert tm._tunnel_url_alive(timeout=1.0) is beklenen
    assert t.istekler == ["https://uzak.klinik.example/api/health"]


@pytest.mark.parametrize("kod", [400, 401, 403, 404, 429, 499])
def test_tunnel_url_alive_edge_4xx_dondururse_CANLI(monkeypatch, kod):
    """Y241 (KP1 T-1, KP-2 A2): dış URL'den 4xx (ör. NAMED tünel önünde Cloudflare Access 403, kenar hız sınırı 429, ingress yok
    404) → edge forward ediyor → True (aralığın üst sınırı 499 dahil). Sahte YALNIZ https taşıyıcısında: HTTPError'ı GERÇEK urllib
    üretir. Önce: urlopen'un fırlattığı HTTPError genel `except`'e düşüp False dönüyordu (bekçi tüneli ~40 sn'de bir yeniden başlatırdı)."""
    t = _gercek_zincir(monkeypatch, kod)
    assert tm._tunnel_url_alive(timeout=1.0) is True
    assert t.istekler == ["https://uzak.klinik.example/api/health"]


@pytest.mark.parametrize("kod", [500, 502, 503, 504])
def test_tunnel_url_alive_edge_5xx_dondururse_OLU(monkeypatch, kod):
    """Y241: 5xx (alt sınır 500 dahil; 502 bad gateway, 503, 504) → edge origin'e ulaşamıyor → False (yeniden başlatma adayı)."""
    t = _gercek_zincir(monkeypatch, kod)
    assert tm._tunnel_url_alive(timeout=1.0) is False
    assert t.istekler == ["https://uzak.klinik.example/api/health"]


# ── Watchdog döngüsü ─────────────────────────────────────────────────────────


def test_watchdog_CEVRIMDISI_yalniz_bekler_tunel_ACMAZ(ortam, monkeypatch):
    """İki DNS hostu da OSError → check_interval kadar bekler; Popen YOK, stop/start yok."""
    ortam.soket.sonuc = OSError(10051, "Ağa ulaşılamıyor")
    olay = _SahteOlay([None, None])
    _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20, 20]
    assert ortam.popen.kayit == []
    assert [a for a, _ in ortam.soket.kayit] == [("1.1.1.1", 53), ("8.8.8.8", 53)] * 2


def test_watchdog_baslatma_HATASINDA_ustel_geri_cekilme_300_tavanli(ortam, monkeypatch):
    """İnternet var, Popen her seferinde FileNotFoundError → beklemeler 20, 40, 80, 160, 300, 300 (tavan 300); her turda deneme."""
    olay = _SahteOlay([None] * 6)
    _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20, 40, 80, 160, 300, 300]
    assert len(ortam.popen.kayit) == 6
    assert tm._tunnel_process is None


def test_watchdog_basari_sonrasi_geri_cekilme_SIFIRLANIR(ortam, monkeypatch):
    """Başarısız, başarısız, başarılı başlatma, süreç ölür, başarısız → beklemeler 20, 40, 20, 20 (başarı geri çekilmeyi
    check_interval'e döndürür: sonraki hatada 80 DEĞİL 20 beklenir); ölmüş sürece terminate yok."""
    s = _Surec([])
    ortam.popen.sira = [FileNotFoundError(2, "yok"), FileNotFoundError(2, "yok"), s]

    def _surec_olur():
        s._canli = False

    olay = _SahteOlay([None, None, _surec_olur, None])
    _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20, 40, 20, 20]
    assert len(ortam.popen.kayit) == 4
    assert s.cagrilar == []
    assert tm._tunnel_process is None


def test_watchdog_dis_URL_iki_ARDISIK_oluyse_yeniden_baslatir_arada_saglikli_tur_sayaci_sifirlar(ortam, monkeypatch):
    """Tur 1: tünel yok → başlat (URL1). Tur 2: /api/health 200. Tur 3: ölü (1/2). Tur 4: sağlıklı (sayaç 0). Tur 5: ölü (1/2).
    Tur 6: ölü (2/2) → eski süreç terminate+wait(5), yeni süreç başlar (URL2). Toplam 2 Popen; geri çağrılar [URL1, URL2]."""
    gelen: list = []
    tm.register_url_callback(gelen.append)
    s1 = _Surec([f"INF {URL1}\n".encode()])
    s2 = _Surec([f"INF {URL2}\n".encode()])
    ortam.popen.sira = [s1, s2]
    olu = urllib.error.URLError("edge yok")

    def _saglikli():
        _okuyucuyu_bekle()
        ortam.urlopen.sira = [_Yanit(status=200)]

    def _olu():
        ortam.urlopen.sira = [olu]

    adimlar = [_saglikli, _olu, _saglikli, _olu, _olu, None]
    olay = _SahteOlay(adimlar)
    _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20] * 6
    assert len(ortam.popen.kayit) == 2, ortam.popen.kayit
    assert s1.cagrilar == ["terminate", ("wait", 5)]
    assert s2.cagrilar == []
    assert [u for u, _ in ortam.urlopen.urller] == [URL1 + "/api/health"] * 5
    assert tm._tunnel_process is s2
    assert gelen == [URL1, URL2] and tm.get_tunnel_url() == URL2


def _bekci_gercek_zincir(monkeypatch, kod):
    """Bekçi senaryosu için GERÇEK `urlopen` + yalnız https taşıyıcısı sahte (`_HttpsTasiyici(kod)`; ağ YOK)."""
    t = _HttpsTasiyici(kod)
    monkeypatch.setattr(urllib.request, "urlopen", _GERCEK_URLOPEN)
    monkeypatch.setattr(urllib.request, "_opener", urllib.request.build_opener(t))
    return t


@pytest.mark.parametrize("kod", [403, 404, 429])
def test_watchdog_dis_URL_4xx_donerse_tuneli_YENIDEN_BASLATMAZ(ortam, monkeypatch, kod):
    """Y241 (KP-2 A2): tur 1 tünel yok → başlat (URL1); tur 2–5 dış `/api/health` 4xx (GERÇEK urllib HTTPError) → edge canlı →
    ölü sayacı artmaz: tek Popen, sürece terminate / kill YOK, URL değişmez, her tur check_interval bekler. (Önce: 4xx ölü sayılıp
    2. turda tünel yeniden başlatılıyordu.)"""
    s1 = _Surec([f"INF {URL1}\n".encode()])
    ortam.popen.sira = [s1]
    t = _bekci_gercek_zincir(monkeypatch, kod)
    olay = _SahteOlay([_okuyucuyu_bekle, None, None, None, None])
    _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20] * 5
    assert len(ortam.popen.kayit) == 1
    assert s1.cagrilar == []
    assert t.istekler == [URL1 + "/api/health"] * 4
    assert tm._tunnel_process is s1 and tm.get_tunnel_url() == URL1


def test_watchdog_dis_URL_502_iki_ARDISIK_ise_yeniden_baslatir(ortam, monkeypatch):
    """Y241 karşıtı: 5xx ölü kalır — tur 1 başlat (URL1), tur 2 ve 3 dış `/api/health` 502 (GERÇEK urllib) → 2/2 → eski süreç
    terminate + wait(5), yeni süreç (URL2) başlar."""
    s1 = _Surec([f"INF {URL1}\n".encode()])
    s2 = _Surec([f"INF {URL2}\n".encode()])
    ortam.popen.sira = [s1, s2]
    t = _bekci_gercek_zincir(monkeypatch, 502)
    olay = _SahteOlay([_okuyucuyu_bekle, None, _okuyucuyu_bekle])
    _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20] * 3
    assert len(ortam.popen.kayit) == 2
    assert s1.cagrilar == ["terminate", ("wait", 5)]
    assert t.istekler == [URL1 + "/api/health"] * 2
    assert tm._tunnel_process is s2 and tm.get_tunnel_url() == URL2


def test_watchdog_dongu_HATASI_bildirilir_dongu_YASAR(ortam, monkeypatch, caplog):
    """`_internet_up` içinde OSError DIŞI istisna → `dongu_hatasini_bildir` ERROR kaydı (yığın izli) + check_interval bekleme; döngü
    ikinci turda da koşar."""
    ortam.soket.sonuc = RuntimeError("soket katmanı bozuk")
    olay = _SahteOlay([None, None])
    with caplog.at_level(logging.ERROR, logger=tm.logger.name):
        _watchdog_kos(olay, monkeypatch, ci=20)
    assert olay.beklemeler == [20, 20]
    kayitlar = [r for r in caplog.records if "Tünel watchdog döngü hatası" in r.getMessage()]
    assert len(kayitlar) == 2 and kayitlar[0].levelno == logging.ERROR
    assert kayitlar[0].exc_info and isinstance(kayitlar[0].exc_info[1], RuntimeError)


def test_watchdog_zaten_CALISIYORSA_ikinci_cagri_yeni_thread_ACMAZ(monkeypatch):
    """Canlı watchdog thread'i varken start_tunnel_watchdog → aynı thread kalır, durdurma bayrağı TEMİZLENMEZ."""
    olay = _SahteOlay([])
    olay.set()
    monkeypatch.setattr(tm, "_watchdog_stop", olay)

    class _Canli:
        def is_alive(self):
            return True

    canli = _Canli()
    tm._watchdog_thread = canli
    oncesi = {t.name for t in threading.enumerate()}
    tm.start_tunnel_watchdog(port=48999, check_interval=20)
    assert tm._watchdog_thread is canli
    assert olay.temizle_sayisi == 0 and olay.is_set() is True
    assert {t.name for t in threading.enumerate()} - oncesi == set()
