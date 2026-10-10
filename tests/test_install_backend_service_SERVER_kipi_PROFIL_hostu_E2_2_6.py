# -*- coding: utf-8 -*-
"""E2-2.6 (2-E incelemesi, A2) — `install_backend_service.ps1 -Mode server` (D2.73'ün YENİ kipi) profilin `PEMF_API_HOST=127.0.0.1`'ini
(server.env: "yalnız reverse-proxy arkası") servis komut satırındaki SABİT `--host 0.0.0.0` ile EZER → demo sunucusunun backend'i TÜM
arabirimlerde dinler (betik ayrıca TCP 8000 inbound `-Profile Any` güvenlik duvarı kuralı açar); ters vekil (TLS, `PEMF_TRUSTED_PROXIES`)
atlanabilir ve aynı özel ağdaki istemci A-01 "LAN" muafiyetiyle doğrudan bağlanır.

`setup_services.ps1` aynı profili okur ama host/port'u CLI'da SABİTLEMEZ (setup_services.ps1:437-438 notu); `backend_service.build_arg_parser`
`--host` VARSAYILANINI `PEMF_API_HOST`'tan alır, açık CLI argümanı ise ortamı EZER (argparse — bu kapıda GERÇEK ayrıştırıcıyla ölçülür).

⛔ Betik GERÇEKTEN koşmaz: D2.73'ün KANITLANMIŞ gölge aparatı (`_APARAT`; yalnız izin listesindeki üst düzey ifadeler koşar) METİN olarak
alınır; YALNIZ `$Mode` senaryodan gelir ve `$CommonArgs` çıktıya eklenir. ARAÇ kolu (D2.73'ün öz-denetimi) aynı koşuda önce.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_install_backend_service_PROFIL_ORTAMI_D273 import (  # noqa: F401  (pytestmark: win32 + pwsh)
    _APARAT,
    _PWSH,
    BETIK,
    KOK,
    SETUP,
    pytestmark,
)


def _degistir(metin: str, eski: str, yeni: str) -> str:
    assert metin.count(eski) == 1, f"aparat çapası {metin.count(eski)} kez: {eski!r}"
    return metin.replace(eski, yeni)


_APARAT_E226 = _degistir(
    _APARAT,
    "$UsingExe = $true; $Mode = 'device'",
    "$UsingExe = $true; $Mode = $(if ($Senaryo -like '*server*') { 'server' } else { 'device' })",
)
_APARAT_E226 = _degistir(
    _APARAT_E226,
    "$sonuc.koruma = $koruma;",
    "$sonuc.cli = @($CommonArgs | ForEach-Object { [string]$_ }); $sonuc.koruma = $koruma;",
)


def _kos(tmp_path: Path, senaryo: str) -> dict:
    aparat = tmp_path / "aparat.ps1"
    aparat.write_text(_APARAT_E226, encoding="utf-8-sig")
    (tmp_path / "kok" / "dist").mkdir(parents=True, exist_ok=True)
    cikti = tmp_path / "cikti.json"
    p = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(aparat),
         "-Betik", str(BETIK), "-Setup", str(SETUP), "-Depo", str(KOK), "-Kok", str(tmp_path / "kok"),
         "-Senaryo", senaryo, "-Girdi", str(KOK / "deploy" / "device.env"), "-Cikti", str(cikti)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )  # fmt: skip
    assert p.returncode == 0 and cikti.exists(), (
        f"aparat düştü (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8-sig"))


def _profil(ad: str) -> dict:
    d = {}
    for ln in (KOK / "deploy" / f"{ad}.env").read_text(encoding="utf-8").splitlines():
        t = ln.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _etkin(monkeypatch, s: dict) -> tuple[str, int]:
    """Servisin GERÇEKTE bağlanacağı host/port: NSSM ortamı + NSSM argümanları → backend'in kendi ayrıştırıcısı."""
    import backend_service as bs

    ortam = dict(x.split("=", 1) for x in s["ortam"])
    for k in ("PEMF_API_HOST", "PEMF_API_PORT"):
        if k in ortam:
            monkeypatch.setenv(k, ortam[k])
        else:
            monkeypatch.delenv(k, raising=False)
    args = bs.build_arg_parser().parse_args(s["cli"])
    port = args.port if args.port is not None else bs.ortam_portu()[0]
    return args.host, port


@pytest.mark.parametrize("kip", ["server", "device"])
def test_KRITIK_servis_PROFILIN_host_ve_portunda_dinler_CLI_ezmez_E2_2_6(tmp_path, monkeypatch, kip):
    s = _kos(tmp_path, kip)
    assert s["ortam"], f"aparat: ortam kurulmadı (profil bulunamadı?): {s}"
    p = _profil(kip)
    host, port = _etkin(monkeypatch, s)
    assert (host, port) == (p["PEMF_API_HOST"], int(p["PEMF_API_PORT"])), (
        f"-Mode {kip}: servis {host}:{port} dinler, profil {p['PEMF_API_HOST']}:{p['PEMF_API_PORT']} diyor "
        f"(NSSM argümanları {s['cli']} profili EZİYOR)"
    )
