# -*- coding: utf-8 -*-
"""18K K1 · NSIS İG-8.27 ikizi (+ K2 kalan kolu, S-YLI.3): Ayarlar ▸ Uygulamalar'dan kaldırmada bobin STOP HER kill'den ÖNCE.

Launcher yolu LN L6 (`e487bb77`, `backend::orphan_durdurma_hedefleri`) ile kapandı: port dosyası + varsayılan porttaki PEMF backend'i
STOP hedefidir. NSIS PREUNINSTALL ise `backend.port` YOK / bozukken `pemf_estop_done`'a atlıyor, bayatken yalnız ölü porta STOP
deniyordu → hemen ardından `taskkill /F /IM PEMF_Backend.exe` varsayılan portta (8000) çalışan backend'i STOP'SUZ öldürür (ESP
bobinleri 6-8'in link-watchdog'u YOK).

İki kat kapı:
  * statik: PREUNINSTALL'da varsayılan port yoklamasından ÖNCE STOP'u atlayan sıçrama yok; NSIS varsayılan portu = launcher
    `install::DEFAULT_PORT`; yoklama satırı NSIS_MAX_STRLEN (1024) altında.
  * uçtan uca: GERÇEK `hooks.nsi`'nin KOPYASI (öldürme satırları → sıra kaydı, `$LOCALAPPDATA` / `$APPDATA` → sahte dizin, varsayılan
    port → geçici loopback portu) gerçek `makensis` ile sessiz bir sınama kurucusuna derlenir ve koşturulur; GERÇEK PowerShell
    satırları GERÇEK HTTP yığınıyla sahte sunuculara (127.0.0.1, geçici port) gider. Sahte EN ALT katta: soket / HTTP.
    ⚠️ Kopya koşmadan ÖNCE denetlenir: `taskkill` / `Stop-Process` / `$LOCALAPPDATA` / `$APPDATA` / `8000` kalırsa test HİÇBİR ŞEY
    KOŞTURMADAN düşer (sahibin kurulu backend'i 8000'de ve port dosyası gerçek LOCALAPPDATA'da — ona istek gitmemeli).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"
INSTALL_RS = KOK / "launcher" / "core" / "src" / "install.rs"

_PEMF_SAGLIK = {"service": "PEMF-Vet", "status": "ok"}
_PEMF_DURDUR = {"status": "success", "confirmed": True, "stmStopped": True, "mqttResults": []}
_ESKI_DURDUR = {"status": "success", "stmStopped": True, "mqttResults": [], "reason": "manual"}


def _yorumsuz(satir: str) -> str:
    """NSIS satır yorumu (`;` / `#`) atılır; tırnak (`'` `"` `` ` ``) içindekiler korunur (test_kaldirma_yetim_surec_temizligi ile aynı)."""
    tirnak = None
    for i, ch in enumerate(satir):
        if tirnak:
            if ch == tirnak:
                tirnak = None
            continue
        if ch in "'\"`":
            tirnak = ch
        elif ch in ";#":
            return satir[:i].strip()
    return satir.strip()


def _preuninstall(metin: str) -> list[str]:
    m = re.search(r"!macro\s+NSIS_HOOK_PREUNINSTALL\b(.*?)!macroend", metin, re.DOTALL)
    assert m, "NSIS_HOOK_PREUNINSTALL yok"
    return [_yorumsuz(s) for s in m.group(1).splitlines()]


def _sonda_satiri(kod: list[str]) -> int | None:
    return next((i for i, s in enumerate(kod) if s.startswith("nsExec::") and "/api/health" in s), None)


# ─────────────────────────────── statik ───────────────────────────────


def test_KRITIK_18K_K1_varsayilan_port_yoklamasindan_ONCE_STOPu_atlayan_sicrama_yok():
    """`backend.port` YOK / boş / geçersizken eski kod `pemf_estop_done`'a atlıyordu (STOP yok → taskkill)."""
    kod = _preuninstall(HOOKS.read_text(encoding="utf-8"))
    sonda = _sonda_satiri(kod)
    blok = next((i for i, s in enumerate(kod) if s == "pemf_estop_varsayilan:"), None)
    assert sonda is not None and blok is not None, (
        "PREUNINSTALL varsayılan portu (launcher install::DEFAULT_PORT) HİÇ yoklamıyor — port dosyası yok / bozuk / bayatken "
        "varsayılan portta çalışan backend STOP almadan `taskkill /F` ile ölür (İG-8.27 NSIS ikizi)"
    )
    # Varsayılan port bloğundan ÖNCE hiçbir yol STOP'u atlayıp kill'e gidemez (blok içindeki "aynı port / ikinci tur" atlamaları meşru).
    erken = [s for s in kod[:blok] if re.match(r"(IfErrors|Goto|StrCmp|IntCmp|IntOp)\b.*\bpemf_estop_done\b", s)]
    assert not erken, f"varsayılan port bloğundan ÖNCE STOP'u atlayan sıçrama: {erken}"
    ilk_kill = next(i for i, s in enumerate(kod) if "taskkill" in s)
    assert blok < sonda < ilk_kill, "varsayılan port yoklaması bloğun içinde ve taskkill'den ÖNCE değil"
    estop = next(i for i, s in enumerate(kod) if s.startswith("nsExec::") and "kapanis_durdur" in s)
    geri = [s for s in kod[sonda:ilk_kill] if re.match(r"Goto\s+pemf_estop_gonder\b", s)]
    assert estop < blok and geri, "yoklama PEMF / yanıtsız dediğinde AYNI STOP satırına dönülmüyor"


def test_18K_K1_NSIS_varsayilan_portu_launcher_DEFAULT_PORT_ile_AYNI():
    nsis = re.search(r"^!define\s+PEMF_VARSAYILAN_PORT\s+(\d+)\s*$", HOOKS.read_text(encoding="utf-8"), re.M)
    rust = re.search(r"pub const DEFAULT_PORT: u16 = (\d+);", INSTALL_RS.read_text(encoding="utf-8"))
    assert nsis and rust, "PEMF_VARSAYILAN_PORT / DEFAULT_PORT bulunamadı"
    assert nsis.group(1) == rust.group(1), f"NSIS {nsis.group(1)} ≠ launcher {rust.group(1)}"


def test_18K_K1_satirlar_NSIS_azami_dizge_uzunlugunu_asmaz():
    """NSIS_MAX_STRLEN = 1024 (ölçüldü: Tauri NSIS 3.11 `makensis -HDRINFO`); aşılırsa makensis sessizce keser."""
    kod = _preuninstall(HOOKS.read_text(encoding="utf-8"))
    for s in kod:
        if s.startswith("nsExec::") and ("/api/health" in s or "kapanis_durdur" in s):
            arguman = re.search(r"'(.*)'\s*$", s).group(1).replace("$$", "$").replace("$2", "65535")
            assert len(arguman) < 1000, (len(arguman), s[:80])


# ─────────────────────────────── sahte sunucular (EN ALT kat: soket / HTTP) ───────────────────────────────


class _Kayit:
    def __init__(self, yol: Path):
        self.yol = yol
        self._kilit = threading.Lock()

    def yaz(self, satir: str) -> None:
        with self._kilit, open(self.yol, "a", encoding="ascii") as f:
            f.write(satir + "\n")

    def satirlar(self) -> list[str]:
        return [s.strip() for s in self.yol.read_text(encoding="ascii", errors="replace").splitlines() if s.strip()]


def _http_sunucu(kayit: _Kayit, davranis: dict):
    """davranis: {"saglik": (kod, govde) | None, "kapanis": (kod, govde, gecikme_sn), "estop": (kod, govde)}."""

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # sessiz
            pass

        def _yanit(self, kod: int, govde) -> None:
            ham = (json.dumps(govde) if not isinstance(govde, str) else govde).encode()
            self.send_response(kod)
            self.send_header("Content-Type", "application/json" if not isinstance(govde, str) else "text/html")
            self.send_header("Content-Length", str(len(ham)))
            self.end_headers()
            self.wfile.write(ham)

        def do_GET(self):
            kayit.yaz(f"REQ {self.server.server_port} GET {self.path}")
            kod, govde = davranis.get("saglik") or (404, {"detail": "Not Found"})
            self._yanit(kod, govde)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            kayit.yaz(f"REQ {self.server.server_port} POST {self.path}")
            if self.path.endswith("/kapanis_durdur"):
                kod, govde, gecikme = davranis.get("kapanis", (200, _PEMF_DURDUR, 0))
                time.sleep(gecikme)
            else:
                kod, govde = davranis.get("estop", (200, _PEMF_DURDUR))
            self._yanit(kod, govde)

    class _S(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):  # PowerShell bağlantıyı kapatınca 10054 — gürültü
            pass

    s = _S(("127.0.0.1", 0), _H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def _sessiz_dinleyici(kayit: _Kayit):
    """TCP kabul eder, isteği okur ve KAYDEDER, ama HİÇ yanıt vermez (yük altında asılı backend — S-YLI.3)."""
    ls = socket.socket()
    ls.bind(("127.0.0.1", 0))
    ls.listen(8)
    port = ls.getsockname()[1]
    tutulan: list[socket.socket] = []

    def _dongu():
        while True:
            try:
                c, _ = ls.accept()
            except OSError:
                return
            tutulan.append(c)
            try:
                c.settimeout(5)
                ilk = c.recv(4096).split(b"\r\n", 1)[0].decode("ascii", "replace")
                kayit.yaz(f"REQ {port} RAW {ilk}")
            except OSError:
                pass

    threading.Thread(target=_dongu, daemon=True).start()
    return port, ls, tutulan


def _kapali_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ─────────────────────────────── uçtan uca: derlenmiş kanca kopyası ───────────────────────────────


def _makensis() -> str | None:
    if sys.platform != "win32":
        return None
    adaylar = [os.environ.get("PEMF_MAKENSIS", "")]
    if os.environ.get("LOCALAPPDATA"):
        adaylar.append(str(Path(os.environ["LOCALAPPDATA"]) / "tauri" / "NSIS" / "makensis.exe"))
    return next((a for a in adaylar if a and Path(a).is_file()), None)


_OLDURME = re.compile(r"^(\s*)nsExec::Exec\b.*\b(taskkill|Stop-Process)\b.*$", re.M)


def _kanca_kopyasi(hedef: Path, varsayilan: int, sahte_yerel: Path, sahte_dolasan: Path, sira: Path) -> None:
    metin = HOOKS.read_text(encoding="utf-8")
    metin = re.sub(
        r"^!define\s+PEMF_VARSAYILAN_PORT\s+\d+\s*$", f"!define PEMF_VARSAYILAN_PORT {varsayilan}", metin, flags=re.M
    )

    def _kayitci(m: re.Match) -> str:
        ad = (
            "PEMF_Backend"
            if "PEMF_Backend" in m.group(0)
            else ("mosquitto" if "Stop-Process" in m.group(0) else "cloudflared")
        )
        g = m.group(1)
        return f'{g}FileOpen $R9 "{sira}" a\n{g}FileSeek $R9 0 END\n{g}FileWrite $R9 "KILL {ad}$\\r$\\n"\n{g}FileClose $R9\n{g}Push 0'

    metin = _OLDURME.sub(_kayitci, metin)
    metin = metin.replace("$LOCALAPPDATA", str(sahte_yerel)).replace("$APPDATA", str(sahte_dolasan))
    # GÜVENLİK ÖN DENETİMİ — koşturulacak gövde (PREUNINSTALL) gerçek kaynağa dokunamaz.
    govde = "\n".join(_preuninstall(metin))
    yasak = [
        y
        for y in ("taskkill", "Stop-Process", "$LOCALAPPDATA", "$APPDATA", "$PROFILE", "8000", "RMDir", "Delete")
        if y in govde
    ]
    if yasak:
        pytest.fail(f"kanca kopyası GÜVENLİ DEĞİL, koşturulmadı: {yasak}")
    hedef.write_text(metin, encoding="utf-8")


def _kos(
    tmp: Path, *, varsayilan: int, port_dosyasi: str | None, yerel_port: str | None = None
) -> tuple[list[str], str]:
    mk = _makensis()
    if not mk:
        capraz.atla("makensis yok (PEMF_MAKENSIS / LOCALAPPDATA\\tauri\\NSIS)")
    kur, veri, yerel, dolasan = tmp / "kur", tmp / "veri", tmp / "yerel", tmp / "dolasan"
    for d in (kur, veri, yerel / "PEMF Vet Client", dolasan):
        d.mkdir(parents=True, exist_ok=True)
    (kur / "veri_koku.txt").write_bytes(str(veri).encode("utf-16-le"))
    if port_dosyasi is not None:
        (kur / "backend.port").write_text(port_dosyasi, encoding="ascii")
    if yerel_port is not None:
        (yerel / "PEMF Vet Client" / "backend.port").write_text(yerel_port, encoding="ascii")
    kayit_yolu = tmp / "sira.txt"
    kayit_yolu.touch()
    _kanca_kopyasi(tmp / "hooks_kopya.nsi", varsayilan, yerel, dolasan, kayit_yolu)
    nsi = tmp / "k1_kosu.nsi"
    nsi.write_text(
        "Unicode true\n"
        f'OutFile "{tmp / "k1_kosu.exe"}"\n'
        'Name "18K K1"\nRequestExecutionLevel user\nSilentInstall silent\n'
        '!include "LogicLib.nsh"\nVar UpdateMode\nVar DeleteAppDataCheckboxState\n'
        f'!include "{tmp / "hooks_kopya.nsi"}"\n'
        "Section\n  !insertmacro NSIS_HOOK_PREUNINSTALL\nSectionEnd\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [mk, "/V2", str(nsi)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180
    )
    assert r.returncode == 0, r.stdout + r.stderr
    k = subprocess.run(
        [str(tmp / "k1_kosu.exe"), "/S", f"/D={kur}"], capture_output=True, timeout=180, creationflags=0x08000000
    )
    assert k.returncode == 0, k.returncode
    gunluk = veri / "logs" / "uninstall_estop.log"
    return _Kayit(kayit_yolu).satirlar(), (
        gunluk.read_text(encoding="mbcs", errors="replace") if gunluk.exists() else ""
    )


def _ilk_kill(sira: list[str]) -> int:
    return next(i for i, s in enumerate(sira) if s.startswith("KILL PEMF_Backend"))


def _postlar(sira: list[str], port: int) -> list[str]:
    """KILL'den ÖNCE bu porta gelen POST yolları (HTTP sunucusu: `REQ <p> POST <yol>` · sessiz dinleyici: `REQ <p> RAW POST <yol> HTTP/1.1`)."""
    yollar = []
    for s in sira[: _ilk_kill(sira)]:
        p = s.split()
        if s.startswith(f"REQ {port} ") and "POST" in p:
            yollar.append(p[p.index("POST") + 1])
    return yollar


uctan_uca = pytest.mark.skipif(sys.platform != "win32", reason="Windows NSIS + PowerShell")


@uctan_uca
def test_KRITIK_18K_K1_port_dosyasi_YOKKEN_varsayilan_porttaki_backend_STOP_alir_sonra_kill(tmp_path):
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, _PEMF_SAGLIK)})
    try:
        sira, gunluk = _kos(tmp_path, varsayilan=s.server_port, port_dosyasi=None)
    finally:
        s.shutdown()
    print("K1OLC|yok|", sira, "|", gunluk)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur"], (
        f"port dosyası yokken varsayılan porttaki backend STOP almadan öldürüldü: {sira}"
    )


@uctan_uca
def test_KRITIK_18K_K1_port_dosyasi_BOZUKKEN_varsayilan_porttaki_backend_STOP_alir(tmp_path):
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, _PEMF_SAGLIK)})
    try:
        sira, _ = _kos(tmp_path, varsayilan=s.server_port, port_dosyasi="abc")
    finally:
        s.shutdown()
    print("K1OLC|bozuk|", sira)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur"], sira


@uctan_uca
def test_KRITIK_18K_K1_port_dosyasi_BAYATKEN_varsayilan_porttaki_backend_STOP_alir(tmp_path):
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, _PEMF_SAGLIK)})
    try:
        sira, gunluk = _kos(tmp_path, varsayilan=s.server_port, port_dosyasi=str(_kapali_port()))
    finally:
        s.shutdown()
    print("K1OLC|bayat|", sira, "|", gunluk)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur"], sira


@uctan_uca
def test_KRITIK_18K_SYLI3_varsayilan_portta_YANITSIZ_dinleyici_de_STOP_alir(tmp_path):
    """S-YLI.3: yük altındaki backend kimlik yoklamasına 2 sn'de yanıt veremez → "yok" sayılmaz; STOP yine gönderilir (Ö.4-Y8)."""
    kayit = _Kayit(tmp_path / "sira.txt")
    port, ls, tutulan = _sessiz_dinleyici(kayit)
    try:
        sira, gunluk = _kos(tmp_path, varsayilan=port, port_dosyasi=None)
    finally:
        ls.close()
        for c in tutulan:
            c.close()
    print("K1OLC|sessiz|", sira, "|", gunluk)
    # KARŞIT (2 sn eşiği): YANITSIZ kapanış isteğinden sonra ikinci istek YOK (kaldırma nsExec sınırına uzamasın) — kill yine koşar.
    assert _postlar(sira, port) == ["/api/hardware/kapanis_durdur"], (
        f"yanıtsız varsayılan backend STOP'suz öldürüldü: {sira}"
    )


@uctan_uca
def test_18K_K1_KARSIT_varsayilanda_YABANCI_servis_STOP_almaz_kill_surer(tmp_path):
    """Launcher L6 ile aynı: kimliği PEMF OLMADIĞI açıkça görülen servise STOP POST'u gönderilmez."""
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, {"status": "ok", "service": "baska"})})
    try:
        sira, _ = _kos(tmp_path, varsayilan=s.server_port, port_dosyasi=None)
    finally:
        s.shutdown()
    print("K1OLC|yabanci|", sira)
    assert _postlar(sira, s.server_port) == [], sira
    assert any(x.startswith("KILL PEMF_Backend") for x in sira)


@uctan_uca
def test_18K_K1_KARSIT_port_dosyasindaki_backend_tek_STOP_varsayilan_bos(tmp_path):
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, _PEMF_SAGLIK)})
    kapali = _kapali_port()
    try:
        sira, gunluk = _kos(tmp_path, varsayilan=kapali, port_dosyasi=f"{s.server_port}\r\n")
    finally:
        s.shutdown()
    print("K1OLC|dosya|", sira, "|", gunluk)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur"], sira
    assert not any(x.startswith(f"REQ {kapali} ") for x in sira)
    assert f"port={s.server_port} nsExec=0 OK uc=1" in gunluk, gunluk


@uctan_uca
def test_18K_K1_KARSIT_port_dosyasi_VARSAYILANLA_ayniyken_tek_STOP(tmp_path):
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, _PEMF_SAGLIK)})
    try:
        sira, _ = _kos(tmp_path, varsayilan=s.server_port, port_dosyasi=str(s.server_port))
    finally:
        s.shutdown()
    print("K1OLC|ayni|", sira)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur"], sira


@uctan_uca
def test_18K_K1_KARSIT_LOCALAPPDATA_yedek_port_dosyasi_STOP_alir(tmp_path):
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(kayit, {"saglik": (200, _PEMF_SAGLIK)})
    try:
        sira, _ = _kos(tmp_path, varsayilan=_kapali_port(), port_dosyasi=None, yerel_port=str(s.server_port))
    finally:
        s.shutdown()
    print("K1OLC|yerel|", sira)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur"], sira


@uctan_uca
def test_KRITIK_18K_K2_YAVAS_HTTP_hatasi_405_ACIL_DURDUR_ucuna_duser(tmp_path):
    """K2 kalan kolu (launcher L4 ile AYNI): kapanış ucu HTTP HATASI dönerse (eski backend 405) — ne kadar sürerse sürsün — uç yok
    sayılır → ACİL DURDUR. Eski satır 2 sn'yi aşan her istisnayı zaman aşımı sayıp ACİL DURDUR'u atlıyordu (yük altında eski backend)."""
    kayit = _Kayit(tmp_path / "sira.txt")
    s = _http_sunucu(
        kayit,
        {
            "saglik": (200, _PEMF_SAGLIK),
            "kapanis": (405, {"detail": "Method Not Allowed"}, 2.6),
            "estop": (200, _ESKI_DURDUR),
        },
    )
    try:
        sira, gunluk = _kos(tmp_path, varsayilan=_kapali_port(), port_dosyasi=str(s.server_port))
    finally:
        s.shutdown()
    print("K1OLC|yavas405|", sira, "|", gunluk)
    assert _postlar(sira, s.server_port) == ["/api/hardware/kapanis_durdur", "/api/hardware/emergency_stop"], sira
