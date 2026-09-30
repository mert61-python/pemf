# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SAHTE SOAK BACKEND'İ — `scripts/soak_http_ws.py`yi GERÇEK backend'e bağlanmadan ölçmek için.

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (`topoloji.py` deseni): adı `test_*` olmadığı için pytest
onu TOPLAMAZ. Kapılar: `test_soak_ws_OLCER.py` (D0Ö.22) · `test_soak_rss_OLCER.py` (D0Ö.15).

127.0.0.1 RASTGELE portta dinler (sahibin 8000'deki backend'ine ASLA bağlanılmaz): betiğin okuma
uçlarına 200 döner, `/ws`de RFC 6455 el sıkışmasını yapar ve her isteği (yol + başlıklar) kaydeder.
"""

from __future__ import annotations

import base64
import hashlib
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from betik_alt_sureci import betik_modulu

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _metin_cercevesi(metin: str) -> bytes:
    veri = metin.encode("utf-8")
    assert len(veri) < 126
    return bytes([0x81, len(veri)]) + veri


class SahteBackend:
    """ws_davranis: "kes" → ilk mesajdan sonra TCP'yi kapanış çerçevesiz keser (KOPMA) ·
    "tut" → bağlantıyı açık tutar ve periyodik mesaj yollar · "reddet" → yükseltmeyi 403 ile reddeder
    (WS'ye HİÇ bağlanılamaz) · "auth1008" → kabul edip hemen 1008 (politika) ile kapatır (auth açık
    profil) · "ilk_sonra_reddet" / "ilk_sonra_sessiz" → İLK bağlantı (betiğin ön-uçuşu) "kes" gibi
    davranır; sonrakiler reddedilir / açık kalıp HİÇ mesaj yollamaz.

    ⚠️ D0Ö.22 ek: yükseltme YALNIZ `/ws` yolunda kabul edilir (Starlette bilinmeyen WS yoluna 403
    döner); `ws_yukseltme_sayisi` da yalnız `/ws`i sayar — yanlış yol regresyonu kapıdan geçemez."""

    def __init__(self, ws_davranis: str):
        self.ws_davranis = ws_davranis
        self.istekler: list[tuple[str, dict]] = []
        self.ws_sirasi = 0
        self._kilit = threading.Lock()
        self.dur = threading.Event()
        self.sok = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sok.bind(("127.0.0.1", 0))
        self.sok.listen(32)
        self.sok.settimeout(0.2)
        self.port = self.sok.getsockname()[1]
        threading.Thread(target=self._dongu, name="sahte-soak-backend", daemon=True).start()

    def kapat(self) -> None:
        self.dur.set()
        self.sok.close()

    def ws_yukseltme_sayisi(self) -> int:
        return sum(1 for yol, b in self.istekler if yol == "/ws" and b.get("upgrade", "").lower() == "websocket")

    def _dongu(self) -> None:
        while not self.dur.is_set():
            try:
                c, _ = self.sok.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                break
            threading.Thread(target=self._isle, args=(c,), daemon=True).start()

    def _isle(self, c: socket.socket) -> None:
        try:
            c.settimeout(5)
            veri = b""
            while b"\r\n\r\n" not in veri:
                parca = c.recv(4096)
                if not parca:
                    return
                veri += parca
            satirlar = veri.partition(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")
            yol = satirlar[0].split(" ")[1]
            basliklar = {k.strip().lower(): v.strip() for k, v in (s.split(":", 1) for s in satirlar[1:] if ":" in s)}
            self.istekler.append((yol, basliklar))
            if basliklar.get("upgrade", "").lower() == "websocket":
                with self._kilit:
                    self.ws_sirasi += 1
                    sira = self.ws_sirasi
                davranis = self.ws_davranis
                if davranis.startswith("ilk_sonra_"):
                    davranis = "kes" if sira == 1 else davranis.removeprefix("ilk_sonra_")
                if yol != "/ws" or davranis == "reddet":
                    c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                    return
                kabul = base64.b64encode(
                    hashlib.sha1((basliklar["sec-websocket-key"] + _GUID).encode("ascii")).digest()
                ).decode("ascii")
                c.sendall(
                    (
                        "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {kabul}\r\n\r\n"
                    ).encode("ascii")
                )
                if davranis == "auth1008":  # api_server: token yoksa accept() sonra close(1008)
                    c.sendall(bytes([0x88, 2]) + (1008).to_bytes(2, "big"))
                    # D0Ö.15 ek-2 (tur 5): websockets 15 `recv()` soket KAPANINCA atar — 0,5 sn bekleme, 1 sn'lik
                    # ön-uçuş penceresinde yüklü CI'da "ilk mesaj GELMEDI"ye kayabilirdi. Hemen kapat.
                    time.sleep(0.05)
                    return
                if davranis == "sessiz":
                    while not self.dur.is_set():
                        time.sleep(0.2)
                    return
                c.sendall(_metin_cercevesi('{"type":"snapshot"}'))
                if davranis == "kes":
                    time.sleep(0.3)
                    return  # finally: TCP kapanır, kapanış çerçevesi YOK → istemci için KOPMA
                while not self.dur.is_set():
                    time.sleep(0.4)
                    c.sendall(_metin_cercevesi('{"type":"telemetri"}'))
                return
            govde = b'{"ok": true}'
            c.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(govde)).encode("ascii")
                + b"\r\nConnection: close\r\n\r\n"
                + govde
            )
        except OSError:
            pass
        finally:
            c.close()


def sahte_psutil(ad: str, rss_mb, port: int | None = None, digerleri: tuple = ()):
    """Sahte psutil. `ad` adlı süreç (pid 4242) `port`u LISTEN eder — `port` verilmezse HİÇBİR portu
    dinlemez → betik RSS'i ÖLÇEMEZ. `rss_mb`: sabit sayı ya da okuma sırasından MB veren `f(n)`.
    `digerleri`: (ad, rss_mb, port) — BAŞKA portu dinleyen süreçler (D0Ö.15 ek: yanlış-süreç senaryosu).
    Eski (ada göre seçen) `process_iter` API'si de verilir: eski betikle karşılaştırma için."""
    tanim = {4242: (ad, rss_mb, port), **{4243 + i: d for i, d in enumerate(digerleri)}}
    okuma = dict.fromkeys(tanim, 0)

    def _rss(pid: int):
        r = tanim[pid][1]
        mb = r(okuma[pid]) if callable(r) else r
        okuma[pid] += 1
        return SimpleNamespace(rss=int(mb * 1024 * 1024))

    class _Surec:
        def __init__(self, pid: int):
            if pid not in tanim:
                raise LookupError(pid)
            self.pid = pid

        def name(self) -> str:
            return tanim[self.pid][0]

        def memory_info(self):
            return _rss(self.pid)

    def _baglantilar(kind: str = "inet"):
        return [
            SimpleNamespace(laddr=SimpleNamespace(ip="127.0.0.1", port=p), status="LISTEN", pid=pid)
            for pid, (_a, _r, p) in tanim.items()
            if p
        ]

    def _process_iter(attrs=None):
        for pid, (a, _r, _p) in tanim.items():
            yield SimpleNamespace(info={"name": a, "memory_info": _rss(pid)})

    return SimpleNamespace(
        process_iter=_process_iter,
        net_connections=_baglantilar,
        Process=_Surec,
        CONN_LISTEN="LISTEN",
        NoSuchProcess=LookupError,
        AccessDenied=PermissionError,
    )


def soak_modulu(monkeypatch):
    """Betiği yükle; ısınma beklemesini (5 sn aralık, 180 sn'ye kadar) anında döndür — ayrı kapıda ölçülür.

    ⚠️ D0Ö.15 ek: `_veri_koku` yalıtılır — süreç içi `main()` aksi hâlde GERÇEK
    `C:\\ProgramData\\PEMF_System\\PEMF_GUI` kökünü seçip .db dosyalarını stat'lıyordu (conftest
    PROGRAMDATA'yı yalıtmaz). Veri kökü ayrı kapıda ölçülür (test_f4_rapor_soak_betikleri_CALISIYOR)."""
    m = betik_modulu("soak_http_ws")
    monkeypatch.setattr(m, "_rss_oturmasini_bekle", lambda *a, **k: m._backend_rss_mb(*a[:1]))
    monkeypatch.setattr(m, "WS_ON_UCUS_S", 1.0, raising=False)  # sessiz kip ön-uçuşu 5 sn beklemesin
    monkeypatch.setattr(m, "_veri_koku", lambda: Path(tempfile.gettempdir()) / "d0o_soak_veri_koku_YOK")
    return m


def kos(m, monkeypatch, capsys, port: int, dakika: float = 0.06, aralik: float = 1.0) -> tuple[int, str]:
    monkeypatch.setattr(
        sys, "argv", ["soak_http_ws.py", "--port", str(port), "--dakika", str(dakika), "--aralik", str(aralik)]
    )
    rc = m.main()
    cikti = capsys.readouterr().out
    cp1254_basilir(cikti)
    return rc, cikti


def cp1254_basilir(cikti: str) -> None:
    """D0Ö.22+15 ek-4 (tur 7): betiğin KENDİ metni cp1254'e yönlendirilen konsolda basılabilmeli — emoji'li neden
    satırı UnicodeEncodeError ile döngüyü SONUC satırından önce kesiyordu; ek-2 ASCII'ye çevirmişti ama kapısızdı
    (capsys str yakalar, kodlama hatası doğmaz). TEMP yolu çıkarılır: ASCII/cp1254 dışı bir TEMP ya da kullanıcı adı
    sahte KIRMIZI üretmesin (veri kökü yalıtımı TEMP altında)."""
    temiz = cikti.replace(tempfile.gettempdir(), "<TEMP>")
    try:
        temiz.encode("cp1254")
    except UnicodeEncodeError as e:
        raise AssertionError(
            f"soak çıktısı cp1254'te basılamaz ({e}) — yönlendirilen konsolda SONUC kesilir: "
            f"{temiz[max(0, e.start - 60) : e.end + 60]!r}"
        ) from e
