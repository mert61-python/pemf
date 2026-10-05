# Author: mertaygn, cglrgrkn
"""GERÇEK mosquitto ile yerel broker aparatı (1-G · D1.104). ⚠️ pytest TOPLAMAZ (`test_` ön eki yok).

· Broker YALNIZ 127.0.0.1 + rastgele boş portta koşar. Yapılandırma ÜRÜNÜN kurulum betiğinden (`scripts/setup_services.ps1`
  içindeki `$conf = @" … "@`) türetilir: listener satırı test portuna, `$MosqDataRoot` test dizinine, dosya günlüğü
  stderr'e çevrilir — kurulum yapılandırmasından `include_dir` düşerse kapı bunu ÖLÇER (aparat kendi yapılandırmasını
  uydurmaz).
· Ürün kodu 127.0.0.1:1883'e bağlanır (sabit). `yonlendir` YALNIZ 127.0.0.1:1883'ü test portuna çevirir: paho
  `Client.connect/connect_async` ve `socket.create_connection` (`_mqtt_publish`'in erişim yoklaması) — ürün kodu
  değişmeden; yönlendirilmeyen bir yol olursa koşucunun gözcüsü 1883'ü zaten reddeder (sahibin broker'ına sızmaz).
· İkili: Windows'ta depodaki `bin/mosquitto/mosquitto.exe` (2.0.18); Linux/mac'te sistem `mosquitto` (yoksa çağıran
  SKIP eder — Windows CI aynı kapıyı paketteki ikiliyle koşar).
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_KURULUM = KOK / "scripts" / "setup_services.ps1"


def ikili() -> Path | None:
    if sys.platform == "win32":
        p = KOK / "bin" / "mosquitto" / "mosquitto.exe"
        return p if p.is_file() else None
    bulunan = shutil.which("mosquitto") or next(
        (
            y
            for y in ("/usr/sbin/mosquitto", "/usr/local/sbin/mosquitto", "/opt/homebrew/sbin/mosquitto")
            if Path(y).is_file()
        ),
        None,
    )
    return Path(bulunan) if bulunan else None


def bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def kurulum_yapilandirmasi(port: int, veri_koku: Path, kaynak: str | None = None) -> str:
    """Kurulum betiğinin ürettiği mosquitto.conf — test portu, test veri kökü, stderr günlüğü ile."""
    metin = kaynak if kaynak is not None else _KURULUM.read_text(encoding="utf-8")
    m = re.search(r'\$conf = @"\r?\n(.*?)\r?\n"@', metin, re.S)
    assert m, "aparat: kurulum betiğinde mosquitto yapılandırma bloğu ($conf = @\"...\"@) bulunamadı"
    conf = m.group(1).replace("\r\n", "\n")
    assert "listener 1883 0.0.0.0" in conf, "aparat: kurulum yapılandırmasında listener satırı yok"
    conf = conf.replace("listener 1883 0.0.0.0", f"listener {port} 127.0.0.1")
    conf = re.sub(r"(?m)^log_dest file .*$", "log_dest stderr", conf)
    conf = conf.replace("$($MosqDataRoot -replace '\\\\','/')", Path(veri_koku).as_posix())
    assert "$" not in conf.replace("$7$", ""), f"aparat: çözülmemiş PowerShell ifadesi kaldı:\n{conf}"
    return conf


class Broker:
    def __init__(self, yapilandirma: str, dizin: Path, port: int):
        self.dizin, self.port = Path(dizin), port
        self.yol = self.dizin / "test_broker.conf"
        self.dizin.mkdir(parents=True, exist_ok=True)
        self.yol.write_text(yapilandirma, encoding="ascii", errors="replace")
        self._p = None
        self.gunluk = ""

    def basla(self) -> "Broker":
        exe = ikili()
        assert exe, "aparat: mosquitto ikilisi yok"
        self._p = subprocess.Popen([str(exe), "-c", str(self.yol)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        son = time.monotonic() + 10
        while time.monotonic() < son:
            if self._p.poll() is not None:
                break
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return self
            except OSError:
                time.sleep(0.05)
        rc = self._p.poll()
        self.dur()
        raise AssertionError(f"aparat: broker açılmadı (rc={rc}):\n{self.gunluk[-1500:]}")

    def dur(self) -> None:
        if self._p is not None:
            if self._p.poll() is None:
                self._p.kill()
            try:
                cikti, _ = self._p.communicate(timeout=10)
                self.gunluk = (cikti or b"").decode("utf-8", errors="replace")
            except Exception:
                pass
            self._p = None


def yonlendir(monkeypatch, port: int) -> None:
    """Ürün kodunun 127.0.0.1:1883 bağlantılarını test broker'ına çevir (yalnız o adres)."""
    import paho.mqtt.client as pm

    def _p(host, p):
        return port if (str(host) in ("127.0.0.1", "localhost") and int(p) == 1883) else p

    orj_connect, orj_async, orj_cc = pm.Client.connect, pm.Client.connect_async, socket.create_connection

    def connect(self, host, port_=1883, *a, **k):
        return orj_connect(self, host, _p(host, port_), *a, **k)

    def connect_async(self, host, port_=1883, *a, **k):
        return orj_async(self, host, _p(host, port_), *a, **k)

    def create_connection(address, *a, **k):
        return orj_cc((address[0], _p(address[0], address[1])), *a, **k)

    monkeypatch.setattr(pm.Client, "connect", connect)
    monkeypatch.setattr(pm.Client, "connect_async", connect_async)
    monkeypatch.setattr(socket, "create_connection", create_connection)


def istemci(port: int, kullanici: str | None = None, parola: str | None = None, ad: str = "t"):
    """paho v2 istemcisi → (istemci | None, CONNACK kodu | None). Reddedilen bağlantıda istemci kapatılır."""
    import paho.mqtt.client as pm

    c = pm.Client(pm.CallbackAPIVersion.VERSION2, client_id=f"{ad}_{time.time_ns() % 10**9}")
    if kullanici:
        c.username_pw_set(kullanici, parola)
    sonuc: dict = {}

    def on_connect(_c, _u, _f, rc, _p=None):
        sonuc["rc"] = int(getattr(rc, "value", rc))

    c.on_connect = on_connect
    try:
        c.connect("127.0.0.1", port, 10)
    except Exception:
        return None, None
    c.loop_start()
    son = time.monotonic() + 5
    while "rc" not in sonuc and time.monotonic() < son:
        time.sleep(0.02)
    rc = sonuc.get("rc")
    if rc != 0:
        c.loop_stop()
        try:
            c.disconnect()
        except Exception:
            pass
        return None, rc
    return c, rc


def kapat(*istemciler) -> None:
    for c in istemciler:
        if c is None:
            continue
        try:
            c.loop_stop()
            c.disconnect()
        except Exception:
            pass
