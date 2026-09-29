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
import threading
import time
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
    (WS'ye HİÇ bağlanılamaz)."""

    def __init__(self, ws_davranis: str):
        self.ws_davranis = ws_davranis
        self.istekler: list[tuple[str, dict]] = []
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
        return sum(1 for _yol, b in self.istekler if b.get("upgrade", "").lower() == "websocket")

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
            if basliklar.get("upgrade", "").lower() == "websocket" and self.ws_davranis == "reddet":
                c.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            if basliklar.get("upgrade", "").lower() == "websocket":
                kabul = base64.b64encode(
                    hashlib.sha1((basliklar["sec-websocket-key"] + _GUID).encode("ascii")).digest()
                ).decode("ascii")
                c.sendall(
                    (
                        "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {kabul}\r\n\r\n"
                    ).encode("ascii")
                )
                c.sendall(_metin_cercevesi('{"type":"snapshot"}'))
                if self.ws_davranis == "kes":
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


def sahte_psutil(ad: str, rss_mb: float):
    """`process_iter` tek bir süreç döndürür: `ad` PEMF_Backend değilse RSS ÖLÇÜLEMEZ."""
    surec = SimpleNamespace(info={"name": ad, "memory_info": SimpleNamespace(rss=int(rss_mb * 1024 * 1024))})
    return SimpleNamespace(process_iter=lambda attrs=None: iter([surec]))


def soak_modulu(monkeypatch):
    """Betiği yükle; ısınma beklemesini (5 sn aralık, 180 sn'ye kadar) anında döndür — ayrı kapıda ölçülür."""
    m = betik_modulu("soak_http_ws")
    monkeypatch.setattr(m, "_rss_oturmasini_bekle", lambda *a, **k: m._backend_rss_mb())
    return m


def kos(m, monkeypatch, capsys, port: int, dakika: float = 0.06, aralik: float = 1.0) -> tuple[int, str]:
    monkeypatch.setattr(
        sys, "argv", ["soak_http_ws.py", "--port", str(port), "--dakika", str(dakika), "--aralik", str(aralik)]
    )
    rc = m.main()
    return rc, capsys.readouterr().out
