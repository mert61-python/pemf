# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""O-16.1 (1-F inceleme §22 #6) + 1-G ölçümü — RUNBOOK'un elle ACİL DURDUR komutu Windows PowerShell 5.1'de ÇALIŞIR ve
portu `backend.port`'tan okur.

ÖLÇÜLEN KUSUR (1-G, `f65402b`): (1) RUNBOOK'un ACİL DURDUR komutu `curl -X POST http://127.0.0.1:8000/…` idi. Windows
PowerShell 5.1'de (Windows'un varsayılan "Yönetici PowerShell"i) `curl` = `Invoke-WebRequest` takma adıdır ve `-X` adlı
parametresi YOKTUR → komut "A parameter cannot be found that matches parameter name 'X'" ile DÜŞÜYOR, istek hiç gitmiyordu
(ölçüldü: 5.1.26100 `Get-Command curl` → Alias → Invoke-WebRequest). (2) Port 8000'e sabitti; launcher 8000 doluysa backend
8001..8049'dadır (`%LOCALAPPDATA%\\PEMF Vet Client\\backend.port`) — elle komut yanlış porta (ya da yabancı servise) gider.

KAPI: RUNBOOK'un "Hızlı komutlar" bloğundaki ACİL DURDUR satırı AYNEN (belgeden çıkarılır) PowerShell çocuk sürecinde koşar;
`LOCALAPPDATA` sahte köke, `backend.port` loopback RASTGELE porttaki kayıtçı sunucuya işaret eder → sunucu POST
`/api/hardware/emergency_stop` ALMALI. ⚠️ Güvenlik: koşmadan önce 127.0.0.1:8000'de dinleyen olmadığı ölçülür (komutun
dosya-yoksa yedeği 8000'dir; bir mutant bile sahibin canlı backend'ine istek gönderemesin). RUNBOOK'ta çıplak `curl -X`
KALMAZ. KARŞIT (ölçüm aracı kanıtı): eski satır (çıplak `curl`) 5.1'de sunucuya HİÇ ulaşmaz.
"""

from __future__ import annotations

import http.server
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
RUNBOOK = KOK / "docs" / "RUNBOOK.md"
_PS51 = shutil.which("powershell.exe") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell yalnız Windows'ta")


def _hizli_komut_satiri() -> str:
    metin = RUNBOOK.read_text(encoding="utf-8")
    m = re.search(r"## Hızlı komutlar[^\n]*\n+```powershell\n(.*?)```", metin, re.S)
    assert m, "RUNBOOK'ta 'Hızlı komutlar' powershell bloğu yok (çapa çürüdü)"
    satirlar = [s for s in m.group(1).splitlines() if "emergency_stop" in s and not s.lstrip().startswith("#")]
    assert len(satirlar) == 1, f"'Hızlı komutlar'da TEK ACİL DURDUR komut satırı beklenir: {satirlar}"
    return satirlar[0].strip()


class _Kayitci(http.server.BaseHTTPRequestHandler):
    istekler: list = []

    def do_POST(self):  # noqa: N802
        _Kayitci.istekler.append(self.path)
        govde = b'{"status":"success","confirmed":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *_a):
        pass


@pytest.fixture
def sunucu():
    _Kayitci.istekler = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Kayitci)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _8000_bos():
    """Güvenlik önkoşulu: 127.0.0.1:8000'de dinleyen YOK (sahibin backend'i kapalı). Ölçüm bekçili süreçten değil
    PowerShell'den (bekçi 8000'e bağlanmayı zaten engeller — onunla ölçülemez)."""
    r = subprocess.run(
        [
            _PS51,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "@(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).Count",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    sayi = (r.stdout or "").strip().splitlines()[-1:] or ["?"]
    if sayi[0] != "0":
        pytest.fail(f"127.0.0.1:8000'de dinleyen var ({sayi[0]!r}) — sahip uygulaması açık olabilir; bu kapı KOŞMAZ")


def _kos(
    kabuk: str, satir: str, tmp_path: Path, port: int | None, icerik: str | None = None
) -> subprocess.CompletedProcess:
    la = tmp_path / "la"
    (la / "PEMF Vet Client").mkdir(parents=True, exist_ok=True)
    if icerik is not None:
        (la / "PEMF Vet Client" / "backend.port").write_text(icerik, encoding="ascii")
    elif port is not None:
        (la / "PEMF Vet Client" / "backend.port").write_text(f"{port}\n", encoding="ascii")
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(la)
    for ad in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(ad, None)
    return subprocess.run(
        [kabuk, "-NoProfile", "-NonInteractive", "-Command", satir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


_KABUKLAR = [pytest.param(_PS51, id="WindowsPowerShell51")] + ([pytest.param(_PWSH, id="pwsh")] if _PWSH else [])


@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_O161_RUNBOOK_ACIL_DURDUR_satiri_KABUKTA_calisir_ve_backend_port_kullanir(sunucu, tmp_path, kabuk):
    _8000_bos()
    satir = _hizli_komut_satiri()
    r = _kos(kabuk, satir, tmp_path, sunucu.server_address[1])
    assert _Kayitci.istekler == ["/api/hardware/emergency_stop"], (
        f"RUNBOOK'un ACİL DURDUR satırı {Path(kabuk).name}'de backend'e (backend.port → {sunucu.server_address[1]}) "
        f"ULAŞMADI: istekler={_Kayitci.istekler} rc={r.returncode} çıktı={(r.stdout + r.stderr)[-400:]!r}"
    )


class _IkinciAdres(http.server.BaseHTTPRequestHandler):
    """127.0.0.2'deki kayıtçı (loopback) — "başka adres" yönlendirmesini görür."""

    istekler: list = []

    def do_POST(self):  # noqa: N802
        _IkinciAdres.istekler.append(self.path)
        govde = b'{"status":"success","confirmed":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *_a):
        pass


@pytest.mark.parametrize("tur", ["yonlendirme_at", "bozuk_noktali_virgul"])
@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_KRITIK_G141_backend_port_icerigi_SAYI_degilse_8000_denenir_BASKA_adrese_GITMEZ(sunucu, tmp_path, kabuk, tur):
    """1-G inceleme G-14.1: `backend.port` kullanıcı-yazılabilir; tek satır içeriği DOĞRULAMIYORDU (teardown doğrular,
    D1.92). Ölçüldü (5.1 ve pwsh): `<port>; KANARYA` → curl "URL rejected", ACİL DURDUR hiç gitmedi ve 8000 denenmedi;
    `1@127.0.0.2:<port>` → istek BAŞKA adrese (127.0.0.2) gitti, 127.0.0.1 almadı. Sözleşme: içerik yalnız rakamsa port
    olur, değilse 8000 denenir (dosya-yok yedeğiyle aynı); istek 127.0.0.1 dışına ÇIKMAZ. Yalnız loopback; 8000 boş."""
    _8000_bos()
    satir = _hizli_komut_satiri()
    _IkinciAdres.istekler = []
    srv2 = http.server.ThreadingHTTPServer(("127.0.0.2", 0), _IkinciAdres)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    try:
        p1, p2 = sunucu.server_address[1], srv2.server_address[1]
        icerik = {"yonlendirme_at": f"1@127.0.0.2:{p2}", "bozuk_noktali_virgul": f"{p1}; KANARYA"}[tur]
        r = _kos(kabuk, satir, tmp_path, None, icerik=icerik)
    finally:
        srv2.shutdown()
        srv2.server_close()
    cikti = (r.stdout + r.stderr)[-400:]
    assert _IkinciAdres.istekler == [], (
        f"{tur}: ACİL DURDUR BAŞKA adrese (127.0.0.2) gitti — backend.port doğrulanmıyor: {cikti!r}"
    )
    assert _Kayitci.istekler == [], f"{tur}: sayı olmayan içerikten port türetildi: {_Kayitci.istekler}"
    assert "127.0.0.1:8000" in cikti, (
        f"{tur}: geçersiz içerikte 8000 DENENMEDİ (yedek yok): rc={r.returncode} {cikti!r}"
    )


def test_KRITIK_O161_RUNBOOK_ta_ciplak_curl_X_KALMAZ():
    metin = RUNBOOK.read_text(encoding="utf-8")
    ciplak = [m.group(0) for m in re.finditer(r"(?<![\w.\\/-])curl(?!\.exe)\s+-X[^\n`]*", metin)]
    assert not ciplak, f"RUNBOOK'ta çıplak `curl -X` (Windows PowerShell 5.1'de DÜŞER): {ciplak}"


def test_KARSIT_aparat_ESKI_ciplak_curl_satiri_PS51de_sunucuya_ULASMAZ(sunucu, tmp_path):
    """Ölçüm aracı kanıtı: aparat 5.1'in davranışını gerçekten görüyor — eski satır (çıplak `curl`) istek GÖNDERMEZ."""
    port = sunucu.server_address[1]
    r = _kos(_PS51, f"curl -X POST http://127.0.0.1:{port}/api/hardware/emergency_stop", tmp_path, port)
    assert _Kayitci.istekler == [], f"aparat: çıplak curl 5.1'de istek gönderdi (takma ad değişmiş?): {r.stdout[-200:]}"
    assert "parameter" in (r.stdout + r.stderr).lower(), (r.stdout + r.stderr)[-300:]
