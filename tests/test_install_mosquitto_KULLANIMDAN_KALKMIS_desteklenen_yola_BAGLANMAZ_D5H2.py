# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 H-2 (DEV-C4 / G-2 sınıfı) — `scripts/install_mosquitto.ps1` (LattePanda "ağ geçidi" kurulumu) KULLANIMDAN KALKMIŞ bir yoldur ve
desteklenen hiçbir kurulum / paket yoluna BAĞLANAMAZ.

ÖLÇÜLEN (HEAD c1aaba61, `:113-133`): betik 'Mosquitto MQTT' güvenlik duvarı kuralını YALNIZ ADIYLA arar (`$firewallRule = Get-NetFirewallRule
-DisplayName "Mosquitto MQTT"` → varsa "[✓] Firewall kuralı zaten mevcut."): aynı adlı devre dışı / Block / giden / UDP / başka port / dar profilli
ya da uzak adresi Any olan kural (Y36: sahadaki makinede TAM OLARAK bu kural var — TCP 1883, uzak adres Any) "var" sayılır, sessiz geçilir. Ayrıca
kendi "doğru" kuralı (1883 ← RFC1918, Private+Domain) P0-3 sözleşmesiyle (1883 YALNIZ hotspot alt ağından) ÇELİŞİR: desteklenen yol
(`setup_services.ps1`, D3.42) bu kuralı ESP kapalıyken SİLER, ESP etkinken uyarır; betiğin kurduğu yerel 'mosquitto' Windows servisini de "anonim
ikinci broker" diye uyarır. ROL: hiçbir desteklenen yol çağırmaz — Inno kurucusu (`build_tools/PEMF_Backend_Setup.iss`) ve launcher paketi
(`build_tools/make_base_zip.py::ADD_SCRIPTS`) taşımaz, launcher / NSIS / CI çağırmaz; tek anan `scripts/setup_gateway.ps1` (o da eski ağ geçidi
akışı — `-StartGUI` depoda olmayan `main.py`yi anaconda ortamıyla açar) ve yalnız bir günlük iletisinde ("Önce install_mosquitto.ps1 …").
KARAR (talimat): eski / ölü yol → ÜRÜN DEĞİŞMEZ, kapı yazılır, "kullanımdan kalkmış" işaretlenir. Bu kapının koruduğu davranış: adla doğrulayan bu
betik desteklenen bir yola (PowerShell betiği, Inno kurucusu, launcher paketi / Rust / NSIS, backend Python, CI) ÇAĞRI ya da PAKET girdisi olarak
geri bağlanamaz; bağlanacaksa önce güvenlik duvarı adımı içerikle doğrulanmalı (DEV-C4 / G-2 sözleşmesi) ve bu kapı bilerek güncellenmeli.
Çağrı tespiti metin değil: PowerShell dosyalarında PowerShell'in KENDİ parser'ıyla dize düğümleri bulunur, en yakın komut bir GÜNLÜK komutu değilse
(Write-Status / Log / Write-Host …) çağrı sayılır — yorumlar ve günlük iletileri sayılmaz (araç kendi kolunda KANITLANIR). Python paket listesi
`ast` ile okunur (içe aktarılmaz). Hiçbir betik ÇALIŞTIRILMAZ; yalnız ayrıştırılır.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from test_setup_services_firewall_kaniti import PWSH, _ps_lit, _pwsh_file

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — PowerShell ayrıştırıcısı koşturulamaz")

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "install_mosquitto.ps1"
HEDEF = re.compile(r"install_mosquitto\.ps1", re.IGNORECASE)

_DEDEKTOR = r"""
using namespace System.Management.Automation.Language
$Gunluk = @('Write-Status', 'Write-Host', 'Write-Output', 'Write-Warning', 'Write-Verbose', 'Write-Information', 'Write-Error', 'Write-Debug', 'Log')
$bulgu = [System.Collections.Generic.List[object]]::new()
foreach ($yol in @(@@DOSYALAR@@)) {
    $t = $null; $h = $null
    $ast = [Parser]::ParseFile($yol, [ref]$t, [ref]$h)
    if ($h.Count) { $bulgu.Add([pscustomobject]@{ dosya = $yol; satir = 0; metin = 'PARSE-ERROR' }); continue }
    $dizeler = $ast.FindAll({ param($n) ($n -is [StringConstantExpressionAst] -or $n -is [ExpandableStringExpressionAst]) -and
        $n.Value -match 'install_mosquitto\.ps1' }, $true)
    foreach ($d in $dizeler) {
        $p = $d.Parent; while ($p -and -not ($p -is [CommandAst])) { $p = $p.Parent }
        if ($p -and $Gunluk -contains "$($p.GetCommandName())") { continue }
        $bulgu.Add([pscustomobject]@{ dosya = $yol; satir = $d.Extent.StartLineNumber; metin = $d.Extent.Text })
    }
}
ConvertTo-Json -InputObject @($bulgu) -Depth 3 -Compress
"""


def ps_cagrilari(tmp_path: Path, dosyalar: list[Path]) -> list[dict]:
    """PowerShell dosyalarında install_mosquitto.ps1'i günlük iletisi DIŞINDA anan dize düğümleri (parser ile; yorumlar sayılmaz)."""
    govde = _DEDEKTOR.replace("@@DOSYALAR@@", ", ".join(_ps_lit(d) for d in dosyalar))
    r = _pwsh_file(tmp_path, "dedektor.ps1", govde)
    assert r.returncode == 0, f"dedektör düştü (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    veri = json.loads(r.stdout.strip().splitlines()[-1] or "[]")
    return [veri] if isinstance(veri, dict) else veri


def _desteklenen_ps_dosyalari() -> list[Path]:
    dosyalar = sorted(
        p
        for kok in (KOK / "scripts", KOK / "build_tools")
        for desen in ("*.ps1", "*.psm1")
        for p in kok.rglob(desen)
        if p.resolve() != BETIK.resolve()
    )
    assert len(dosyalar) >= 10 and KOK / "scripts" / "setup_services.ps1" in dosyalar, (
        f"aparat: taranacak PowerShell betikleri bulunamadı: {dosyalar}"
    )
    return dosyalar


def test_ARAC_dedektor_CAGRIYI_yakalar_GUNLUK_iletisini_ve_YORUMU_yakalamaz(tmp_path):
    """Aracın kendi kanıtı: aynı dosyada beş çağrı biçimi YAKALANIR; günlük iletisi, yorum ve kardeş servis betiği YAKALANMAZ."""
    sentetik = tmp_path / "sentetik.ps1"
    sentetik.write_text(
        "\n".join(
            [
                'Write-Status "Önce install_mosquitto.ps1 scriptini çalıştırın." "Yellow"',
                "Log \"UYARI: install_mosquitto.ps1'in 'Mosquitto MQTT' kuralı VAR\" \"Yellow\"",
                "# & .\\install_mosquitto.ps1 -SkipDownload",
                '& "$PSScriptRoot\\install_mosquitto_service.ps1"',
                '& "$PSScriptRoot\\install_mosquitto.ps1" -SkipDownload',
                ".\\install_mosquitto.ps1",
                "powershell -ExecutionPolicy Bypass -File install_mosquitto.ps1",
                "$g = Join-Path $PSScriptRoot 'install_mosquitto.ps1'; & $g",
                "Start-Process pwsh -ArgumentList '-File', \"$d\\install_mosquitto.ps1\" -Wait",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )
    bulgu = ps_cagrilari(tmp_path, [sentetik])
    assert sorted(b["satir"] for b in bulgu) == [5, 6, 7, 8, 9], (
        f"dedektör çağrı biçimlerini ayırt etmiyor (beklenen satırlar 5-9; 1-4 günlük / yorum / kardeş betik):\n{bulgu}"
    )


def test_KRITIK_desteklenen_PowerShell_betikleri_KULLANIMDAN_KALKMIS_install_mosquitto_ps1_CAGIRMAZ(tmp_path):
    bulgu = ps_cagrilari(tmp_path, _desteklenen_ps_dosyalari())
    assert not bulgu, (
        "kullanımdan kalkmış install_mosquitto.ps1 (1883 kuralını YALNIZ ADIYLA bulur; kuralı P0-3 ile çelişir) bir kurulum betiğine "
        f"BAĞLANDI — önce güvenlik duvarı adımını içerikle doğrulayın (DEV-C4 / G-2), sonra bu kapıyı bilerek güncelleyin:\n{bulgu}"
    )


def _add_scripts() -> list[str]:
    agac = ast.parse((KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8"))
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Assign) and any(
            isinstance(h, ast.Name) and h.id == "ADD_SCRIPTS" for h in dugum.targets
        ):
            return [e.value for e in dugum.value.elts if isinstance(e, ast.Constant)]
    raise AssertionError("aparat: build_tools/make_base_zip.py içinde ADD_SCRIPTS ataması bulunamadı")


def test_KRITIK_sahaya_giden_paket_KULLANIMDAN_KALKMIS_betigi_TASIMAZ():
    ekli = _add_scripts()
    assert "setup_services.ps1" in ekli, f"aparat: ADD_SCRIPTS okunamadı: {ekli}"
    assert not [s for s in ekli if HEDEF.search(s)], (
        f"launcher paketi (ADD_SCRIPTS) install_mosquitto.ps1 taşıyor: {ekli}"
    )


_YORUM = {".rs": "//", ".py": "#", ".yml": "#", ".yaml": "#", ".iss": ";", ".nsi": ";", ".nsh": ";"}


def _kod_satirlari(p: Path) -> list[tuple[int, str]]:
    """Satır yorumu (ve Inno / Rust `//`) soyulmuş satırlar — yorumdaki söz çağrı sayılmaz."""
    on = _YORUM.get(p.suffix.lower(), "#")
    cikti = []
    for i, s in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        g = s.strip()
        if g.startswith(on) or g.startswith("//"):
            continue
        cikti.append((i, s))
    return cikti


def test_KRITIK_kurucu_launcher_backend_ve_CI_KULLANIMDAN_KALKMIS_betigi_CAGIRMAZ():
    kumeler = [
        (KOK / "build_tools", ("*.iss", "*.py")),
        (KOK / "launcher" / "core" / "src", ("*.rs",)),
        (KOK / "launcher" / "app" / "src", ("*.rs",)),
        (KOK / "launcher" / "app" / "windows", ("*.nsi", "*.nsh")),
        (KOK / "apps" / "backend", ("*.py",)),
        (KOK / ".github" / "workflows", ("*.yml", "*.yaml")),
    ]
    dosyalar = sorted(
        {p for kok, desenler in kumeler for d in desenler for p in kok.rglob(d) if "node_modules" not in p.parts}
    )
    assert any(p.suffix == ".iss" for p in dosyalar) and any(p.suffix == ".rs" for p in dosyalar), (
        f"aparat: kurucu / launcher kaynakları bulunamadı ({len(dosyalar)} dosya)"
    )
    bulgu = [
        f"{p.relative_to(KOK)}:{i}: {s.strip()[:140]}"
        for p in dosyalar
        for i, s in _kod_satirlari(p)
        if HEDEF.search(s)
    ]
    assert not bulgu, (
        "kullanımdan kalkmış install_mosquitto.ps1 bir kurucuya / launcher'a / backend'e / CI'ya bağlandı — önce güvenlik duvarı adımını "
        "içerikle doğrulayın (DEV-C4 / G-2):\n" + "\n".join(bulgu)
    )
