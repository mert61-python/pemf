# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ALT SÜREÇ AĞ BEKÇİSİ — ürün modüllerini içe aktaran ÇOCUK süreçte, ürün importundan ÖNCE yüklenir (D1.14).

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (`topoloji.py` deseni): adı `test_*` olmadığı için pytest
onu TOPLAMAZ.

NEDEN: süitin ağ bekçisi (`tests/conftest.py`, D0Ö.07) alt sürece GEÇMEZ (`betik_alt_sureci.py`
uyarısı). Çocukta conftest'i içe aktarmak da çözüm değil: ortamı (PEMF_* yönlendirmeleri) değiştirir,
ölçülen şey bozulur. Bu modül YALNIZ ağı keser, ortama dokunmaz.

KURAL (conftest ile aynı): IPv4/IPv6 soketlerde loopback DIŞI connect / connect_ex / sendto / DNS (ters DNS dahil)
ENGELLENİR; loopback'te yalnız BU SÜREÇTE bind edilmiş portlar serbest (asyncio öz-borusu) — sahibin
servis portlarına (8000/1883/…) bağlanılamaz. Her engel `ENGELLENEN`'e yazılır; çağıran sonunda
listenin BOŞ olduğunu ölçer. Katlar: Python sarmalayıcıları + audit hook (C düzeyi `_socket`) +
(Windows) `IocpProactor.connect/sendto` (Proactor `socket.*`'ı ve audit olaylarını ATLAR).
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys

#: (katman, adres, port) — engellenen her deneme.
ENGELLENEN: list[tuple[str, str, int]] = []
#: Sahibin servis portları (conftest `_AG_SAHIP_PORTLARI` ile aynı) — ne bağlanılır ne bind edilir.
SAHIP_PORTLARI = frozenset({8000, 8100, 1883, 5173, 8177, 8200})
_ACILAN: set[int] = set()
#: Çocuğun başlattığı alt süreçler (TORUNLAR bekçisizdir) — ENGELLENMEZ, kaydedilir; çağıran izin listesine
#: bakar (bağımsız inceleme r3: torun süreçler kapsam dışıydı).
ALT_SURECLER: list[str] = []
#: Kaydı yapılmış ama `_winapi.CreateProcess` olayı henüz gelmemiş `subprocess.Popen` sayısı (eşleştirme).
_POPEN_BEKLEYEN = [0]
_AILELER = (socket.AF_INET, socket.AF_INET6)
try:
    _YEREL_AD = socket.gethostname().lower()
except OSError:
    _YEREL_AD = ""


def _loopback(ad) -> bool:
    ad = ad.decode() if isinstance(ad, bytes) else str(ad)
    if ad.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(ad.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _denetle(adres, tur: str) -> None:
    if not (isinstance(adres, tuple) and len(adres) >= 2):
        return
    try:
        port = int(adres[1])
    except (TypeError, ValueError):
        port = -1
    if _loopback(adres[0]) and port in _ACILAN and port not in SAHIP_PORTLARI:
        return
    ENGELLENEN.append((tur, str(adres[0]), port))
    raise ConnectionRefusedError(f"ALT SÜREÇ AĞ BEKÇİSİ: {tur} {adres[0]}:{port} engellendi")


def _dns_denetle(ad, tur: str) -> None:
    if ad is None:
        return
    ad = ad.decode() if isinstance(ad, bytes) else str(ad)
    if _loopback(ad) or (_YEREL_AD and ad.lower() == _YEREL_AD):
        return
    ENGELLENEN.append((tur, ad, -1))
    raise socket.gaierror(11001, f"ALT SÜREÇ AĞ BEKÇİSİ: {tur} {ad} engellendi")


_orj_connect = socket.socket.connect
_orj_connect_ex = socket.socket.connect_ex
_orj_sendto = socket.socket.sendto
_orj_bind = socket.socket.bind
_orj_getaddrinfo = socket.getaddrinfo
_orj_gethostbyname = socket.gethostbyname
_orj_gethostbyname_ex = socket.gethostbyname_ex
_orj_gethostbyaddr = socket.gethostbyaddr
_orj_getnameinfo = socket.getnameinfo


def _connect(self, adres):
    if self.family in _AILELER:
        _denetle(adres, "connect")
    return _orj_connect(self, adres)


def _connect_ex(self, adres):
    if self.family in _AILELER:
        try:
            _denetle(adres, "connect_ex")
        except ConnectionRefusedError:
            return 10061  # WSAECONNREFUSED
    return _orj_connect_ex(self, adres)


def _sendto(self, veri, *args):
    if self.family in _AILELER and args:
        _denetle(args[-1], "sendto")
    return _orj_sendto(self, veri, *args)


def _bind(self, adres):
    if self.family in _AILELER and isinstance(adres, tuple) and len(adres) >= 2:
        try:
            port = int(adres[1])
        except (TypeError, ValueError):
            port = -1
        if port in SAHIP_PORTLARI:
            ENGELLENEN.append(("bind", str(adres[0]), port))
            raise PermissionError(f"ALT SÜREÇ AĞ BEKÇİSİ: bind {adres[0]}:{port} — sahibin servis portu")
    sonuc = _orj_bind(self, adres)
    try:
        _ACILAN.add(int(self.getsockname()[1]))
    except Exception:
        pass
    return sonuc


def _getaddrinfo(host, *args, **kwargs):
    _dns_denetle(host, "dns")
    return _orj_getaddrinfo(host, *args, **kwargs)


def _gethostbyname(ad):
    _dns_denetle(ad, "gethostbyname")
    return _orj_gethostbyname(ad)


def _gethostbyname_ex(ad):
    _dns_denetle(ad, "gethostbyname_ex")
    return _orj_gethostbyname_ex(ad)


def _gethostbyaddr(ad):
    _dns_denetle(ad, "gethostbyaddr")
    return _orj_gethostbyaddr(ad)


def _getnameinfo(sockaddr, flags):
    _dns_denetle(sockaddr[0] if isinstance(sockaddr, tuple) and sockaddr else sockaddr, "getnameinfo")
    return _orj_getnameinfo(sockaddr, flags)


def _kanca(olay, arg):
    if olay in ("socket.connect", "socket.sendto"):
        if getattr(arg[0], "family", None) in _AILELER:
            _denetle(arg[1], "audit:" + olay.split(".", 1)[1])
    elif olay == "socket.getaddrinfo":
        _dns_denetle(arg[0], "audit:dns")
    elif olay == "socket.gethostbyaddr":  # ters DNS (getfqdn dahil) — bağımsız inceleme r3
        _dns_denetle(arg[0], "audit:gethostbyaddr")
    elif olay == "socket.getnameinfo":
        sa = arg[0]
        _dns_denetle(sa[0] if isinstance(sa, tuple) and sa else sa, "audit:getnameinfo")
    elif olay == "socket.bind":  # ham `_socket` ile sahip portuna bind (sarmalayıcıyı atlar)
        adres = arg[1]
        if getattr(arg[0], "family", None) in _AILELER and isinstance(adres, tuple) and len(adres) >= 2:
            try:
                port = int(adres[1])
            except (TypeError, ValueError):
                port = -1
            if port in SAHIP_PORTLARI:
                ENGELLENEN.append(("audit:bind", str(adres[0]), port))
                raise PermissionError(f"ALT SÜREÇ AĞ BEKÇİSİ: bind {adres[0]}:{port} — sahibin servis portu")
    elif olay in ("subprocess.Popen", "os.system", "os.spawn", "os.posix_spawn", "os.startfile", "os.exec"):
        program = arg[0] if arg and arg[0] else (arg[1] if len(arg) > 1 else "")
        # YS1g (GitHub windows-latest, Python 3.10.11): gh-101283 (3.10.10+) `shell=True`da `executable`a cmd.exe'nin TAM yolunu
        # koyar; komut satırı (`…\cmd.exe /c "ver"`) `args`tadır → yalnız `executable` kaydedilince izin listesi (`cmd.exe /c "ver"`)
        # eşleşmiyor, platform sürüm sorgusu "izin listesi dışı alt süreç" sayılıyordu (22 test). `args` dizeyse TAM komut satırı kaydedilir
        # (3.10.2'de `executable` None → zaten bu kullanılıyordu).
        if olay == "subprocess.Popen" and len(arg) > 1 and isinstance(arg[1], str) and arg[1]:
            program = arg[1]
        if isinstance(program, (list, tuple)):
            program = program[0] if program else ""
        ALT_SURECLER.append(f"{olay}:{program}")
        if olay == "subprocess.Popen":
            _POPEN_BEKLEYEN[0] += 1
    elif olay == "_winapi.CreateProcess":
        # 1-B inceleme (i6): multiprocessing'in Windows süreç başlatma yolu (`_winapi.CreateProcess`)
        # `subprocess.Popen` olayını HİÇ üretmez. ⚠️ Python 3.10.2'de bu olayın komut satırı argümanı BOZUK
        # gelir (ölçüldü: `(None, '\x03', None)`) — komut satırı kaydedilemez. Bu yüzden EŞLEŞTİRME: her
        # `subprocess.Popen` olayının ardından gelen tek CreateProcess o Popen'ındır (kaydı zaten var); Popen'sız
        # CreateProcess izin listesine UYMAYAN bir kayıt olarak yazılır.
        if _POPEN_BEKLEYEN[0] > 0:
            _POPEN_BEKLEYEN[0] -= 1
        else:
            ALT_SURECLER.append(f"{olay}:EŞLENMEMİŞ (Popen'sız süreç başlatma)")


socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.socket.sendto = _sendto
socket.socket.bind = _bind
socket.getaddrinfo = _getaddrinfo
socket.gethostbyname = _gethostbyname
socket.gethostbyname_ex = _gethostbyname_ex
socket.gethostbyaddr = _gethostbyaddr
socket.getnameinfo = _getnameinfo
sys.addaudithook(_kanca)
if os.name == "nt":
    import asyncio.windows_events as _we

    _orj_iocp_connect = _we.IocpProactor.connect
    _orj_iocp_sendto = _we.IocpProactor.sendto

    def _iocp_connect(self, conn, address):
        if getattr(conn, "family", None) in _AILELER:
            _denetle(address, "iocp.connect")
        return _orj_iocp_connect(self, conn, address)

    def _iocp_sendto(self, conn, buf, flags=0, addr=None):
        if addr is not None and getattr(conn, "family", None) in _AILELER:
            _denetle(addr, "iocp.sendto")
        return _orj_iocp_sendto(self, conn, buf, flags, addr)

    _we.IocpProactor.connect = _iocp_connect
    _we.IocpProactor.sendto = _iocp_sendto
