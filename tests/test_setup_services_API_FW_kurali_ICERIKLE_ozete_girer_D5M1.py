# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 M-1 (H-1 kapsam dışı gözlemi; DEV-C4 / G-2 / H-1 sınıfı) — `setup_services.ps1` API / keşif güvenlik duvarı döngüsü kuralı kural
kural İÇERİKLE işler, UYAN kuralı silmez, silinemeyen kuralın yanına ikiz kurmaz, son doğrulamayı içerikle yapar ve sonuç kurulum özetine
ve `.install_verified`e (`apiFirewall=`) girer.

ÖLÇÜLEN (HEAD d38b0db5, `:613-635`): döngü İG-9.5 + 4B-3.5 içerik ölçütünü kullanıyordu ama (1) bir kural uymazsa
`Remove-NetFirewallRule -DisplayName` ile AYNI ADLI UYAN kuralı da siliyordu; (2) silme düşünce (ör. ilke deposundaki kural) yine İKİNCİ
kuralı kuruyordu; (3) `New-NetFirewallRule` "başarılı" görünüp kural içerikle uymasa / hiç oluşmasa da son doğrulama YOKTU; (4) sonuç hiçbir
değişkene, özete ya da `.install_verified`e girmiyordu (DEV-C4 1883 için `mosqFirewall=` yazar, API için yazılmıyordu) → mobil / web istemci
(ACİL DURDUR dahil) LAN'dan erişemezken kurulum "Kurulum DOĞRULANDI" ile bitiyordu.
SÖZLEŞME = `install_backend_service.ps1` `Ensure-PemfBackendFirewallKurali` (D5 H-1) ile BİREBİR (eşlik bu dosyada ölçülür): içerik =
protokol · port · program · etkin · Allow · Inbound · tüm profiller; uymayan aynı adlı kural tek tek silinir; uyan varsa yenisi kurulmaz;
silinemezse ona dokunulmaz ama doğrusu yine kurulur (TUR 2 ürün kararı — 4B-3.5 "LAN çalışsın"; ikinci koşuda birikmez) + eylemli UYARI +
`False`; son doğrulama içerikle; uzak adres VERİLMEZ (A-01). Programı farklı aynı adlı kural (İG-9.5 "taşınmış kurulum") bugünkü gibi silinir.
TUR 2 (çürütücü): aynı adlı iki doğru kural (x1) · işlev fırlatırsa dış catch sonucu (x2) · işlev tanımı çağrıdan ÖNCE (x3) · çekilen dilim /
işlev İZİN LİSTESİ (gölgesiz dış komut aparatta koşmaz).
⛔ Gerçek güvenlik duvarı YOK: işlev ve döngü dilimi PowerShell parser'ıyla çekilir; NetSecurity cmdlet'leri D5 H-1 kapısının durum tutan
gölgeleriyle (Get-Command ile İŞLEV kanıtlı, modül otomatik yükleme KAPALI) koşar. Betiğin gerçek `Log`u (C:\\ProgramData'ya yazar) ASLA
yüklenmez — kayıtçı gölge kullanılır. Özet dilimi yalnız izinli komutlarla (Log / Set-Content gölgesi / Get-Date / Join-Path) koşar.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import capraz
import pytest
from test_install_backend_service_FW_kurali_ICERIKLE_D5H1 import (
    API,
    BETIK,
    DOGRU_API,
    DOGRU_KESIF,
    FONK,
    IZIN_PS,
    IZINLI_KOMUT,
    IZINLI_UYE,
    PORT,
    PROG,
    _icerik,
    _uyari,
    betik_fonksiyonu,
    izin_disi_iletisi,
    ps_dizi,
    surucu_kos,
    tanim_cagri_sirasi,
)
from test_setup_services_firewall_kaniti import _ps_lit, _pwsh_file

KOK = Path(__file__).resolve().parents[1]
SETUP = KOK / "scripts" / "setup_services.ps1"
KESIF = "PEMF UDP Discovery"
STAGING = "PEMF Backend API (staging)"
_PWSH = shutil.which("pwsh")

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((_PWSH is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]

# setup_services.ps1'in GERÇEK API / keşif güvenlik duvarı dilimi: `$FwKurallar = …` ifadesinden `foreach ($r in $FwKurallar)` döngüsüne
# kadar (dahil) bitişik üst düzey ifadeler + dilimin çağırdığı İZİNLİ işlev tanımları. `Log` ASLA alınmaz (gerçeği ProgramData'ya yazar).
# D5 M-1 TUR 2: dilim + işlev İZİN LİSTESİNE karşı denetlenir (D5 H-1 `IZINLI_KOMUT`; dışında komut / yöntem → IZIN-DISI, çıkış 5, KOŞMAZ).
_DILIM = r"""
using namespace System.Management.Automation.Language
@@IZIN_PS@@
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { Write-Output "PARSE-ERROR"; exit 3 }
$ust = @($ast.EndBlock.Statements)
$bas = -1; $son = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($bas -lt 0 -and $ust[$i] -isnot [FunctionDefinitionAst] -and $ust[$i].Extent.Text -match '^\$FwKurallar\s*=') { $bas = $i }
    if ($ust[$i] -is [ForEachStatementAst] -and $ust[$i].Condition.Extent.Text -eq '$FwKurallar') { $son = $i }
}
if ($bas -lt 0 -or $son -lt $bas) { Write-Output "DILIM-YOK $bas $son"; exit 4 }
$izinliIslev = @('Ensure-PemfBackendFirewallKurali')
$fonklar = @($ust | Where-Object { $_ -is [FunctionDefinitionAst] -and $izinliIslev -contains $_.Name })
foreach ($s in @($fonklar) + @($ust[$bas..$son])) { $ihlal = _IzinDisi $s @@IZINLI@@ @@UYE@@; if ($ihlal) { Write-Output ("IZIN-DISI " + $ihlal); exit 5 } }
$parca = [System.Collections.Generic.List[string]]::new()
foreach ($f in $fonklar) { $parca.Add($f.Extent.Text) }
foreach ($s in $ust[$bas..$son]) { $parca.Add($s.Extent.Text) }
[System.IO.File]::WriteAllText(@@CIKTI@@, ($parca -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Output ("OK " + ($son - $bas + 1))
"""


def _dilim(tmp_path: Path) -> str:
    cikti = tmp_path / "dilim.txt"
    govde = (
        _DILIM.replace("@@IZIN_PS@@", IZIN_PS)
        .replace("@@BETIK@@", _ps_lit(SETUP))
        .replace("@@CIKTI@@", _ps_lit(cikti))
        .replace("@@IZINLI@@", ps_dizi(IZINLI_KOMUT))
        .replace("@@UYE@@", ps_dizi(IZINLI_UYE))
    )
    r = _pwsh_file(tmp_path, "dilim.ps1", govde)
    assert r.returncode != 5, izin_disi_iletisi(SETUP, "güvenlik duvarı dilimi", r.stdout)
    assert r.returncode == 0 and r.stdout.startswith("OK"), (
        f"setup_services güvenlik duvarı dilimi çekilemedi:\n{r.stdout}\n{r.stderr}"
    )
    return cikti.read_text(encoding="utf-8")


def dongu_kos(
    tmp_path: Path, kurallar: list[dict], *, staging: bool = False, port: int = PORT, **bayrak
) -> tuple[str, list[str], list[dict]]:
    """setup_services.ps1'in GERÇEK API / keşif dilimini D5 H-1 gölgeli sürücüsünde koştur → (ApiFirewallOk, olaylar, son tablo)."""
    on = (
        "function Log($m, $c = 'White') { _Olay (\"LOG \" + $m) }\n"
        "if ((Get-Command Log).CommandType -ne 'Function') { _Olay 'GOLGE-YOK Log'; exit 99 }\n"
        "$ErrorActionPreference = 'Continue'   # setup_services.ps1'in kendi tercihi\n"
        f"$StagingMi = ${'true' if staging else 'false'}\n$probePort = {port}\n$BackendExe = {_ps_lit(PROG)}\n"
    )
    son_ek = (
        "\n$v = Get-Variable -Name ApiFirewallOk -Scope Script -ErrorAction SilentlyContinue\n"
        "_Olay (\"APIOK \" + $(if ($v) { \"$($v.Value)|$($v.Value.GetType().Name)\" } else { 'TANIMSIZ' }))\n"
        "_Olay 'DILIM-BITTI'\n"
    )
    satir, son = surucu_kos(tmp_path, on + _dilim(tmp_path) + son_ek, kurallar, **bayrak)
    assert "DILIM-BITTI" in satir, f"dilim sonuna ulaşılmadı:\n{satir}"
    api = [s for s in satir if s.startswith("APIOK ")][-1].split(" ", 1)[1]
    return api, satir, son


def _yeni_satir(satir: list[str]) -> list[str]:
    return [s for s in satir if s.startswith("NEW ")]


def _kimlik(son: list[dict]) -> list[str]:
    return sorted(k["id"] for k in son)


# ── Döngü (gerçek dilim) ─────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_uyan_kuralin_IKIZI_uymuyorsa_yalniz_uymayan_silinir_UYAN_KORUNUR(tmp_path):
    """HEAD: `Remove-NetFirewallRule -DisplayName` aynı adlı UYAN kuralı da siliyordu (yenisi kurulamazsa LAN erişimi kesilir)."""
    api, satir, son = dongu_kos(tmp_path, [DOGRU_API, dict(DOGRU_API, act="Block"), DOGRU_KESIF])
    assert "k0" in _kimlik(son) and "k1" not in _kimlik(son), (
        f"içeriği UYAN kural (k0) silindi ya da uymayan ikiz (k1, Block) kaldı — adla toplu silme:\n{son}\n{satir}"
    )
    assert not _yeni_satir(satir), f"uyan kural varken yenisi kuruldu (çift kural):\n{satir}"
    assert api == "True|Boolean", f"ApiFirewallOk = {api} (beklenen True|Boolean)\n{satir}"


def test_KRITIK_uymayan_kural_SILINEMEZSE_ona_DOKUNULMAZ_DOGRUSU_yine_kurulur_False_ve_eylemli_UYARI(tmp_path):
    """D5 M-1 TUR 2 ürün kararı (4B-3.5 'LAN çalışsın' güvencesi geri; launcher I-1 ile aynı): silinemeyen uymayan kural yerinde kalır,
    yanına DOĞRU kural kurulur (yalnız bir kez — ikinci koşu 4B35 kapısında), sonuç False + eylemli UYARI → özet / apiFirewall=False."""
    kural = dict(DOGRU_API, en="False")
    api, satir, son = dongu_kos(tmp_path, [kural, DOGRU_KESIF], silduser=True)
    assert sorted(_icerik(k) for k in son if k["n"] == API) == sorted([_icerik(kural), _icerik(DOGRU_API)]), (
        f"silinemeyen kurala dokunuldu ya da yanına DOĞRU kural kurulmadı (LAN erişimi kapalı kalır):\n{son}\n{satir}"
    )
    assert _yeni_satir(satir) == [f"NEW {API}|Inbound|{PROG}|Allow|TCP|{PORT}|Any|"], (
        f"silinemeyen kuralın yanına doğru kural tam BİR kez (uzak adres verilmeden) kurulmadı:\n{satir}"
    )
    assert [
        s for s in _uyari(satir) if "silinemedi" in s and "Remove-NetFirewallRule" in s and "New-NetFirewallRule" in s
    ], f"silinemeyen kural için eylem söyleyen (elle komutlu) UYARI yok:\n{satir}"
    assert api == "False|Boolean", f"silinemeyen uymayan kural kaldı ama ApiFirewallOk = {api}\n{satir}"


def test_KARSIT_ayni_adli_IKI_DOGRU_kural_dokunulmaz_True(tmp_path):
    """Çürütücü x1 (eşik +1: `Count -gt 0` → `-eq 1`, iki betikte): aynı adlı iki doğru kural LAN'ı açar — dokunulmaz, sahte UYARI yok, True."""
    api, satir, son = dongu_kos(tmp_path, [DOGRU_API, dict(DOGRU_API), DOGRU_KESIF])
    assert not [s for s in satir if s.startswith(("SET ", "REMOVE ", "NEW "))] and not _uyari(satir), (
        f"aynı adlı iki doğru kural varken güvenlik duvarı değişti / sahte UYARI:\n{satir}"
    )
    assert len(son) == 3 and api == "True|Boolean", (
        f"aynı adlı iki DOĞRU kural varken ApiFirewallOk = {api} (beklenen True)\n{satir}"
    )


def test_KRITIK_kural_islevi_FIRLATIRSA_denetlenemedi_UYARISI_ve_False(tmp_path):
    """Çürütücü x2 (dış catch yolu): NetSecurity sorgusu fırlarsa (modül yok / MpsSvc durmuş) işlev sonuç döndürmez — döngünün dış
    `catch`i 'denetlenemedi' demeli ve sonuç (ApiFirewallOk) False olmalı; özet / .install_verified apiFirewall=False."""
    api, satir, son = dongu_kos(tmp_path, [DOGRU_API, DOGRU_KESIF], sorguduser=True)
    assert len([s for s in _uyari(satir) if "denetlenemedi" in s]) == 2, (
        f"kural denetimi fırladı ama iki kural için de 'denetlenemedi' UYARIsı yok:\n{satir}"
    )
    assert api == "False|Boolean", f"kural denetimi fırladı ama ApiFirewallOk = {api} (beklenen False)\n{satir}"


def test_KRITIK_uyanin_yaninda_SILINEMEYEN_Block_ikiz_varsa_False(tmp_path):
    """Windows güvenlik duvarında Block Allow'u ezer: uyan kural dursa da silinemeyen aynı adlı Block kuralı LAN erişimini keser."""
    api, satir, son = dongu_kos(tmp_path, [DOGRU_API, dict(DOGRU_API, act="Block"), DOGRU_KESIF], silduser=True)
    assert len([k for k in son if k["n"] == API]) == 2 and not _yeni_satir(satir), f"tablo değişti:\n{son}\n{satir}"
    assert api == "False|Boolean", f"silinemeyen Block ikizi varken ApiFirewallOk = {api}\n{satir}"


def test_KRITIK_uymayan_silindi_YENISI_kurulamadi_False_ve_kurali_YOK_uyarisi(tmp_path):
    api, satir, son = dongu_kos(tmp_path, [dict(DOGRU_API, act="Block"), DOGRU_KESIF], yeniduser=True)
    assert not [k for k in son if k["n"] == API], f"aparat: kural kurulamadığı hâlde tabloda API kuralı var:\n{son}"
    assert [s for s in _uyari(satir) if "kuralı YOK" in s and "New-NetFirewallRule" in s and str(PORT) in s], (
        f"kural kurulamadı ama 'kuralı YOK' + elle kurma komutu söyleyen UYARI yok:\n{satir}"
    )
    assert api == "False|Boolean", f"API kuralı YOK ama ApiFirewallOk = {api}\n{satir}"


def test_KRITIK_SON_DOGRULAMA_icerikle_kurulan_kural_uymuyorsa_False(tmp_path):
    """Cmdlet 'başarılı' ama ortaya çıkan kural devre dışı (ör. ilke) → son sorgu adla değil içerikle: False + UYARI."""
    api, satir, _son = dongu_kos(tmp_path, [], yenibozuk=True)
    assert [s for s in _uyari(satir) if API in s], f"içerikle doğrulanamayan kural için UYARI yok:\n{satir}"
    assert api == "False|Boolean", f"kurulan kural devre dışı ama ApiFirewallOk = {api}\n{satir}"


def test_KRITIK_yalniz_KESIF_kurali_dogrulanamazsa_da_False(tmp_path):
    api, satir, _son = dongu_kos(tmp_path, [DOGRU_API, dict(DOGRU_KESIF, en="False")], silduser=True)
    assert api == "False|Boolean", f"keşif (UDP 5051) kuralı doğrulanamadı ama ApiFirewallOk = {api}\n{satir}"


def test_KARSIT_dogru_kurallar_VARKEN_dokunulmaz_True(tmp_path):
    api, satir, son = dongu_kos(tmp_path, [DOGRU_API, DOGRU_KESIF])
    assert not [s for s in satir if s.startswith(("SET ", "REMOVE ", "NEW "))] and not _uyari(satir), satir
    assert _kimlik(son) == ["k0", "k1"] and api == "True|Boolean", f"ApiFirewallOk = {api}\n{satir}"


def test_KARSIT_kural_YOKSA_ikisi_DOGRU_icerikle_uzak_adres_VERILMEDEN_kurulur_True(tmp_path):
    api, satir, son = dongu_kos(tmp_path, [])
    assert sorted(_yeni_satir(satir)) == sorted(
        [f"NEW {API}|Inbound|{PROG}|Allow|TCP|{PORT}|Any|", f"NEW {KESIF}|Inbound|{PROG}|Allow|UDP|5051|Any|"]
    ), f"kurallar doğru argümanlarla (uzak adres VERİLMEDEN — A-01) kurulmadı:\n{satir}"
    assert sorted(_icerik(k) for k in son) == sorted([_icerik(DOGRU_API), _icerik(DOGRU_KESIF)]), son
    assert api == "True|Boolean" and not _uyari(satir), f"ApiFirewallOk = {api}\n{satir}"


def test_KARSIT_STAGING_yalniz_kendi_adli_kurali_kurar_KESIF_acmaz_D274(tmp_path):
    api, satir, son = dongu_kos(tmp_path, [], staging=True)
    assert _yeni_satir(satir) == [f"NEW {STAGING}|Inbound|{PROG}|Allow|TCP|{PORT}|Any|"], satir
    assert [k["n"] for k in son] == [STAGING] and api == "True|Boolean", f"ApiFirewallOk = {api}\n{satir}"


def test_KARSIT_tasinmis_kurulumun_PROGRAMI_farkli_kural_bugunku_gibi_DUZELTILIR_IG95(tmp_path):
    eski = dict(DOGRU_API, prog=r"D:\ESKI\PEMF_Backend\PEMF_Backend.exe")
    api, satir, son = dongu_kos(tmp_path, [eski, DOGRU_KESIF])
    assert [_icerik(k) for k in son if k["n"] == API] == [_icerik(DOGRU_API)] and api == "True|Boolean", (
        f"{son}\n{satir}"
    )


# ── Özet + .install_verified (gerçek üst düzey ifadeler) ────────────────────────────────────────────────────────────────
_OZET = r"""
using namespace System.Management.Automation.Language
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$script:Kayit = [System.Collections.Generic.List[string]]::new()
function Log($m, $c = 'White') { $script:Kayit.Add("LOG " + $m) }
function Set-Content { [CmdletBinding()] param($Path, $LiteralPath, $Value, $Encoding)
    $script:Kayit.Add("SETCONTENT " + "$Path$LiteralPath" + " :: " + (@($Value) -join ' | ')) }
foreach ($g in 'Log', 'Set-Content') { if ((Get-Command $g).CommandType -ne 'Function') { [Console]::Out.WriteLine("GOLGE-YOK " + $g); exit 99 } }
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
if ($h.Count) { [Console]::Out.WriteLine("PARSE-ERROR"); exit 3 }
$ust = @($ast.EndBlock.Statements)
$bas = -1; $son = -1
for ($i = 0; $i -lt $ust.Count; $i++) {
    if ($bas -lt 0 -and $ust[$i].Extent.Text -like 'Log "At-rest şifreleme DOĞRULANDI*') { $bas = $i }
    if ($bas -ge 0 -and $son -lt 0 -and $ust[$i].Find({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Set-Content' -and
            $n.Extent.Text -like '*.install_verified*' }, $true)) { $son = $i }
}
if ($bas -lt 0 -or $son -le $bas) { [Console]::Out.WriteLine("DILIM-YOK $bas $son"); exit 4 }
$izinli = 'Log', 'Set-Content', 'Get-Date', 'Join-Path'
foreach ($s in $ust[($bas + 1)..$son]) {
    foreach ($c in $s.FindAll({ param($n) $n -is [CommandAst] }, $true)) {
        if ($izinli -notcontains "$($c.GetCommandName())") { [Console]::Out.WriteLine("IZIN-DISI " + $c.Extent.Text); exit 5 }
    }
}
$MosqFailed = $false; $Mode = 'device'; $MosqFirewallOk = $true; $probePort = @@PORT@@; $AppDir = 'C:\PEMF_SAHTE\app'
$StagingMi = $false
$FwKurallar = @(@{ n = 'PEMF Backend API'; p = 'TCP'; port = @@PORT@@ }, @{ n = 'PEMF UDP Discovery'; p = 'UDP'; port = 5051 })
$ApiFirewallOk = @@APIOK@@
foreach ($s in $ust[($bas + 1)..$son]) { . ([ScriptBlock]::Create($s.Extent.Text)) }
[System.IO.File]::WriteAllText(@@CIKTI@@, (ConvertTo-Json -InputObject @($script:Kayit) -Compress), [System.Text.UTF8Encoding]::new($false))
"""


def _ozet(tmp_path: Path, api_ok: bool) -> list[str]:
    cikti = tmp_path / f"ozet_{api_ok}.json"
    govde = (
        _OZET.replace("@@BETIK@@", _ps_lit(SETUP))
        .replace("@@PORT@@", str(PORT))
        .replace("@@APIOK@@", "$true" if api_ok else "$false")
        .replace("@@CIKTI@@", _ps_lit(cikti))
    )
    r = _pwsh_file(tmp_path, f"ozet_{api_ok}.ps1", govde)
    assert r.returncode == 0 and cikti.exists(), (
        f"özet dilimi koşamadı (rc={r.returncode}; 4 dilim yok, 5 izin dışı komut, 99 gölge yok):\n{r.stdout}\n{r.stderr}"
    )
    return json.loads(cikti.read_text(encoding="utf-8"))


def test_KRITIK_API_kurali_DOGRULANAMAZSA_ozet_UYARIR_ve_install_verified_apiFirewall_False(tmp_path):
    k = _ozet(tmp_path, False)
    uyari = [s for s in k if s.startswith("LOG UYARI") and API in s and "LAN" in s]
    assert uyari, f"API / keşif güvenlik duvarı kuralı doğrulanamadı ama kurulum özetinde UYARI yok:\n{k}"
    bitti = [s for s in k if "Kurulum DOĞRULANDI" in s]
    assert bitti and all("apiFirewall=False" in s for s in bitti), f"özet satırı apiFirewall sonucunu söylemiyor:\n{k}"
    bayrak = [s for s in k if s.startswith("SETCONTENT") and ".install_verified" in s]
    assert len(bayrak) == 1 and "apiFirewall=False" in bayrak[0].split(" :: ", 1)[1].split(" | "), (
        f".install_verified 'apiFirewall=False' satırını taşımıyor:\n{bayrak}"
    )
    assert "mosqFirewall=True" in bayrak[0].split(" :: ", 1)[1].split(" | "), f"mosqFirewall kanıtı kayboldu:\n{bayrak}"


def test_KARSIT_API_kurali_DOGRULANDIYSA_UYARI_yok_ve_apiFirewall_True(tmp_path):
    k = _ozet(tmp_path, True)
    assert not [s for s in k if s.startswith("LOG UYARI") and API in s], f"doğrulanmış kuralda sahte UYARI:\n{k}"
    bitti = [s for s in k if "Kurulum DOĞRULANDI" in s]
    bayrak = [s for s in k if s.startswith("SETCONTENT") and ".install_verified" in s]
    assert bitti and all("apiFirewall=True" in s for s in bitti), k
    assert len(bayrak) == 1 and "apiFirewall=True" in bayrak[0].split(" :: ", 1)[1].split(" | "), bayrak


# ── AST: kurulum akışında işlev DIŞINDA NetFirewall çağrısı yok (adla arayan / adla silen eski döngü geri gelemez) ──
_AST = r"""
using namespace System.Management.Automation.Language
$t = $null; $h = $null
$ast = [Parser]::ParseFile(@@BETIK@@, [ref]$t, [ref]$h)
function _Ata($n, [type]$tur) { $p = $n.Parent; while ($p) { if ($p -is $tur) { return $p }; $p = $p.Parent }; $null }
$kaldirma = @($ast.EndBlock.Statements | Where-Object { $_ -is [IfStatementAst] -and $_.Clauses[0].Item1.Extent.Text -eq '$Uninstall' })
$disari = @($ast.FindAll({ param($n) $n -is [CommandAst] -and "$($n.GetCommandName())" -like '*-NetFirewall*' }, $true) | ForEach-Object {
    $c = $_
    $icKaldirma = [bool]@($kaldirma | Where-Object { $c.Extent.StartOffset -ge $_.Extent.StartOffset -and $c.Extent.EndOffset -le $_.Extent.EndOffset }).Count
    if (-not (_Ata $c ([FunctionDefinitionAst])) -and -not $icKaldirma) { "$($c.Extent.StartLineNumber): $($c.Extent.Text)" }
})
[pscustomobject]@{ hata = @($h | ForEach-Object { $_.Message }); kaldirma = $kaldirma.Count; disari = @($disari) } | ConvertTo-Json -Compress
"""


def test_KRITIK_islev_TANIMI_dongudan_ve_her_UST_DUZEY_cagrisindan_ONCE(tmp_path):
    """Çürütücü x3 (tanım YERİ): `Ensure-PemfBackendFirewallKurali` tanımı `foreach ($r in $FwKurallar)` döngüsünün ARKASINA taşınırsa
    metin birebir kalır ve parser ile çeken dilim aparatı yeşil kalır — gerçek betik sırayla koştuğu için çağrı anında işlev YOKTUR
    (CommandNotFound → dış catch → kural HİÇ kurulmaz, her kurulum apiFirewall=False). Genel kural: üst düzeyde çağrılan her betik işlevi
    ilk çağrısından ÖNCE tanımlı (D5 H-1'deki install_backend_service kolu ile aynı denetim)."""
    a = tanim_cagri_sirasi(tmp_path, SETUP)
    assert FONK in a["denetlenen"], f"aparat: {FONK} üst düzey çağrısı bulunamadı (kör denetim): {a}"
    assert not a["ihlal"], (
        f"setup_services.ps1: işlev ilk üst düzey çağrısından SONRA tanımlanmış — çağrı anında işlev YOK: {a['ihlal']}"
    )


def test_KRITIK_kurulum_akisinda_islev_DISINDA_NetFirewall_cagrisi_YOK(tmp_path):
    r = _pwsh_file(tmp_path, "ast.ps1", _AST.replace("@@BETIK@@", _ps_lit(SETUP)))
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    a = json.loads(r.stdout.strip().splitlines()[-1])
    assert not a["hata"] and a["kaldirma"] == 1, a
    assert not a["disari"], (
        "kurulum akışında işlev DIŞINDA NetFirewall çağrısı var — adla arayan / adla silen eski döngü geri mi geldi? "
        f"(içerik ölçütü {FONK} içinde olmalı): {a['disari']}"
    )


# ── Eşlik: install_backend_service.ps1 (D5 H-1) ile AYNI işlev ─────────────────────────────────────────────────────────
def test_KRITIK_ESLIK_islev_metni_install_backend_service_ile_BIREBIR(tmp_path):
    kurulum = betik_fonksiyonu(tmp_path, FONK, SETUP)
    servis = betik_fonksiyonu(tmp_path, FONK, BETIK)
    assert kurulum.count("Log ") > 0 and "Write-Status" not in kurulum, (
        "setup_services kopyası betiğin günlükçüsünü (Log) kullanmalı"
    )
    assert kurulum == servis.replace("Write-Status ", "Log "), (
        f"{FONK} iki betikte AYRIŞTI (günlükçü adı dışında birebir olmalı) — birini düzelttiyseniz ötekini de düzeltin"
    )


_ESLIK_SENARYO = {
    "yok": ([], {}),
    "uyan": ([DOGRU_API], {}),
    "iki_dogru": ([DOGRU_API, dict(DOGRU_API)], {}),
    "devre_disi": ([dict(DOGRU_API, en="False")], {}),
    "engelle": ([dict(DOGRU_API, act="Block")], {}),
    "baska_port": ([dict(DOGRU_API, port="8000")], {}),
    "dar_profil": ([dict(DOGRU_API, prof="Private")], {}),
    "baska_program": ([dict(DOGRU_API, prog=r"D:\ESKI\PEMF_Backend.exe")], {}),
    "harf_farki": ([dict(DOGRU_API, prog=PROG.upper())], {}),
    "ikiz": ([DOGRU_API, dict(DOGRU_API, act="Block")], {}),
    "silinemez": ([dict(DOGRU_API, en="False")], {"silduser": True}),
    "silinemez_baska_port": ([dict(DOGRU_API, port="8099")], {"silduser": True}),
    "ikiz_silinemez": ([DOGRU_API, dict(DOGRU_API, act="Block")], {"silduser": True}),
    "kurulamaz": ([dict(DOGRU_API, act="Block")], {"yeniduser": True}),
    "kurulan_bozuk": ([], {"yenibozuk": True}),
}


@pytest.mark.parametrize("senaryo", list(_ESLIK_SENARYO))
def test_KRITIK_ESLIK_davranis_install_backend_service_ile_AYNI(tmp_path, senaryo):
    kurallar, bayrak = _ESLIK_SENARYO[senaryo]
    sonuc = {}
    for ad, betik, on in (
        (
            "setup",
            SETUP,
            "function Log($m, $c = 'White') { _Olay (\"LOG \" + $m) }\n$ErrorActionPreference = 'Continue'\n",
        ),
        ("servis", BETIK, ""),
    ):
        d = tmp_path / ad
        d.mkdir()
        kod = (
            on
            + betik_fonksiyonu(d, FONK, betik)
            + (
                f"\n$r = {FONK} -Ad {_ps_lit(API)} -Protokol 'TCP' -Port {PORT} -Program {_ps_lit(PROG)}\n"
                '_Olay ("SONUC " + $r + " " + $r.GetType().Name)\n'
            )
        )
        satir, son = surucu_kos(d, kod, kurallar, **bayrak)
        sonuc[ad] = (satir, [_icerik(k) for k in son])
    assert [s for s in sonuc["setup"][0] if s.startswith("SONUC ")], sonuc["setup"][0]
    assert sonuc["setup"] == sonuc["servis"], (
        f"[{senaryo}] setup_services ile install_backend_service AYNI girdide FARKLI davrandı:\nsetup  ={sonuc['setup']}\n"
        f"servis ={sonuc['servis']}"
    )
