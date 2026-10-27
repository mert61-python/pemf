# -*- coding: utf-8 -*-
"""YLI-A2.2 — `publish_release.ps1`'in BELGELİ iki dilli not kullanımı (`-Notes (python scripts\\surum_notlari.py goster … tr)`) varsayılan
konsol kod sayfasında Türkçe / İngilizce notu BOZAR: `goster` UTF-8 bayt basar, PowerShell yerel komut çıktısını `[Console]::OutputEncoding`
(bu makinede OEM 857) ile çözer → "İngilizce dil seçeneği" → "─░ngilizce dil se├ğene─şi", "›" → "ÔÇ║". Betikte kodlama denetimi yoktu →
bozuk metin süite (~1,5 sa), kimliğe ve manifest `notes`una / release gövdesine ilerliyordu (ölçüldü, YLI A2).

Kural: bozuk kodlamalı (UTF-8'in OEM / ANSI ile okunmuş izi) `-Notes` / `-NotesEn` süit / kimlik / ağdan ÖNCE reddedilir; gerçek notlar korumaya
takılmaz; belgeli kullanım varsayılan kod sayfasında ya doğru metni taşır ya da korumaya takılır.

⚠️ Yayın betiği bu kapıda KOŞULMAZ (kopyası da): `Test-BozukKodlama` AST'den çıkarılıp YALNIZ fonksiyon tanımı yüklenir; sıra AST konumuyla ölçülür.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parent.parent
BETIK = KOK / "scripts" / "publish_release.ps1"
NOTLAR = KOK / "docs" / "surum_notlari.json"
_PWSH = shutil.which("pwsh")
_GIZLI = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: ölçülen bozuk biçimler: cp857'de okunmuş UTF-8 (Türkçe), cp1254'te okunmuş UTF-8, cp857'de okunmuş "›" (İngilizce not)
BOZUK = ["─░ngilizce dil se├ğene─şi", "AÃ§Ä±lÄ±ÅŸ", "Settings ÔÇ║ Language"]

#: AST'den YALNIZ fonksiyon tanımını yükler (betik gövdesi koşmaz); girdileri JSON'dan okur, sonucu JSON'a yazar (konsol kodlamasından bağımsız).
_ARAC = r"""
param([string]$Betik, [string]$Girdi, [string]$Cikti, [string]$Py = '', [string]$Notlar = '', [string]$Surum = '')
$ErrorActionPreference = 'Stop'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$null, [ref]$null)
$f = $ast.Find({ param($a) $a -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -eq 'Test-BozukKodlama' }, $true)
$sonuc = [ordered]@{ fonksiyon = [bool]$f; yargi = @(); belgeli = @() }
if ($f) {
  . ([scriptblock]::Create($f.Extent.Text))
  foreach ($m in @(Get-Content -LiteralPath $Girdi -Raw -Encoding UTF8 | ConvertFrom-Json)) { $sonuc.yargi += [bool](Test-BozukKodlama $m) }
}
if ($Py) {
  foreach ($dil in 'tr', 'en') {
    $alinan = ((& $Py $Notlar goster mobile $Surum $dil) -join "`n")
    $sonuc.belgeli += [ordered]@{ dil = $dil; alinan = $alinan; bozuk = $(if ($f) { [bool](Test-BozukKodlama $alinan) } else { $null }) }
  }
}
Set-Content -LiteralPath $Cikti -Value ($sonuc | ConvertTo-Json -Depth 5) -Encoding utf8NoBOM
"""


def _arac(tmp_path: Path, girdiler: list[str], belgeli: bool = False) -> dict:
    if not _PWSH:
        capraz.atla("pwsh (PowerShell 7) yok")
    a = tmp_path / "arac.ps1"
    a.write_bytes(b"\xef\xbb\xbf" + _ARAC.encode("utf-8"))
    g, c = tmp_path / "girdi.json", tmp_path / "cikti.json"
    g.write_text(json.dumps(girdiler, ensure_ascii=False), encoding="utf-8")
    komut = [
        _PWSH,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(a),
        "-Betik",
        str(BETIK),
        "-Girdi",
        str(g),
        "-Cikti",
        str(c),
    ]
    if belgeli:
        surum = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))["mobile"]["name"]
        komut += ["-Py", sys.executable, "-Notlar", str(KOK / "scripts" / "surum_notlari.py"), "-Surum", surum]
    # PYTHONIOENCODING boş: `goster` kendi UTF-8 çıktısını basar; konsol kod sayfası DEĞİŞTİRİLMEZ (belgeli kullanımın aynısı).
    r = subprocess.run(
        komut,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**__import__("os").environ, "PYTHONIOENCODING": ""},
        creationflags=_GIZLI,
    )
    assert r.returncode == 0 and c.exists(), f"araç koşmadı (rc={r.returncode}):\n{(r.stdout + r.stderr)[-600:]}"
    return json.loads(c.read_text(encoding="utf-8-sig"))


def _gercek_notlar() -> list[str]:
    n = json.loads(NOTLAR.read_text(encoding="utf-8"))
    return [
        v[a]
        for k, kanal in n.items()
        if not k.startswith("_")
        for v in kanal.values()
        for a in ("notes", "notes_en")
        if v.get(a)
    ]


def test_KRITIK_bozuk_kodlamali_not_TANINIR_gercek_notlar_TAKILMAZ(tmp_path):
    gercek = _gercek_notlar()
    assert len(gercek) >= 12, len(gercek)
    s = _arac(tmp_path, BOZUK + gercek)
    assert s["fonksiyon"], "publish_release.ps1'de Test-BozukKodlama YOK — bozuk kodlamalı not denetlenmiyor"
    assert s["yargi"][: len(BOZUK)] == [True] * len(BOZUK), list(zip(BOZUK, s["yargi"]))
    yanlis = [m for m, y in zip(gercek, s["yargi"][len(BOZUK) :]) if y]
    assert not yanlis, f"gerçek sürüm notu bozuk sayıldı: {yanlis}"


#: Üst düzeyde iki notu denetleyen koruma deyimi (`foreach (… @($Notes, $NotesEn))` + Test-BozukKodlama + throw) AST'den bulunur; YALNIZ o deyim
#: (ve fonksiyon tanımı) verilen not çiftleriyle çalıştırılır — betiğin geri kalanı koşmaz. Konumu süit çağrısı ve `git credential`la kıyaslanır.
_SIRA = r"""
param([string]$Betik, [string]$Girdi, [string]$Cikti)
$ErrorActionPreference = 'Stop'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$null, [ref]$null)
$f = $ast.Find({ param($a) $a -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -eq 'Test-BozukKodlama' }, $true)
$fe = $ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.ForEachStatementAst] -and
  $_.Body.Extent.Text -match 'Test-BozukKodlama' -and $_.Body.Extent.Text -match '\bthrow\b' } | Select-Object -First 1
$k = $ast.FindAll({ param($a) $a -is [System.Management.Automation.Language.CommandAst] }, $true)
$sonuc = [ordered]@{
  koruma = $(if ($fe) { $fe.Extent.StartOffset } else { -1 })
  suit = ($k | Where-Object { $_.Extent.Text -match 'yayin_oncesi_suit\.ps1' } | Select-Object -First 1).Extent.StartOffset
  kimlik = ($k | Where-Object { $_.Extent.Text -match '^git credential' } | Select-Object -First 1).Extent.StartOffset
  durdu = @()
}
if ($f -and $fe) {
  . ([scriptblock]::Create($f.Extent.Text))
  $deyim = [scriptblock]::Create($fe.Extent.Text)
  foreach ($c in @(Get-Content -LiteralPath $Girdi -Raw -Encoding UTF8 | ConvertFrom-Json)) {
    $Notes = $c[0]; $NotesEn = $c[1]
    try { & $deyim; $sonuc.durdu += $false } catch { $sonuc.durdu += [bool]($_.Exception.Message -match 'kodlama') }
  }
}
Set-Content -LiteralPath $Cikti -Value ($sonuc | ConvertTo-Json -Depth 4) -Encoding utf8NoBOM
"""


def test_KRITIK_koruma_iki_notu_da_SUITTEN_ve_KIMLIKTEN_ONCE_durdurur(tmp_path):
    if not _PWSH:
        capraz.atla("pwsh (PowerShell 7) yok")
    n = json.loads(NOTLAR.read_text(encoding="utf-8"))["mobile"]
    gercek = n[next(iter(n))]
    ciftler = [
        [BOZUK[0], "English note"],
        [BOZUK[1], "English note"],
        ["Türkçe not", BOZUK[2]],
        [gercek["notes"], gercek["notes_en"]],
    ]
    a, g, c = tmp_path / "sira.ps1", tmp_path / "ciftler.json", tmp_path / "sira.json"
    a.write_bytes(b"\xef\xbb\xbf" + _SIRA.encode("utf-8"))
    g.write_text(json.dumps(ciftler, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(
        [
            _PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(a),
            "-Betik",
            str(BETIK),
            "-Girdi",
            str(g),
            "-Cikti",
            str(c),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        creationflags=_GIZLI,
    )
    assert r.returncode == 0 and c.exists(), f"sıra aracı koşmadı (rc={r.returncode}):\n{(r.stdout + r.stderr)[-600:]}"
    o = json.loads(c.read_text(encoding="utf-8-sig"))
    assert o["suit"] and o["kimlik"], f"süit / kimlik çağrısı bulunamadı (ölçüm aracı kör): {o}"
    assert o["koruma"] >= 0, "üst düzeyde bozuk kodlamalı notu denetleyip throw eden koruma YOK"
    assert o["koruma"] < o["suit"] < o["kimlik"], f"koruma süitten / kimlikten ÖNCE değil: {o}"
    # bozuk TR (OEM) · bozuk TR (ANSI) · bozuk YALNIZ EN → durur; gerçek iki dilli not → durmaz
    assert o["durdu"] == [True, True, True, False], dict(zip(["OEM-tr", "ANSI-tr", "OEM-en", "gercek"], o["durdu"]))


def test_KRITIK_belgeli_kullanim_VARSAYILAN_kod_sayfasinda_ya_dogru_ya_KORUMAYA_takilir(tmp_path):
    s = _arac(tmp_path, [], belgeli=True)
    surum = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))["mobile"]["name"]
    n = json.loads(NOTLAR.read_text(encoding="utf-8"))["mobile"][surum]
    for b in s["belgeli"]:
        beklenen = n["notes" if b["dil"] == "tr" else "notes_en"]
        if b["alinan"].strip() == beklenen:
            continue  # konsol zaten UTF-8 — metin doğru taşındı
        assert b["bozuk"] is True, (
            f"{b['dil']}: komut ikamesi notu BOZDU ({b['alinan'][:40]!r} ≠ {beklenen[:40]!r}) ve koruma tanımadı"
        )


def test_baslik_kullanim_satiri_UTF8_on_adimini_soyler():
    bas = BETIK.read_text(encoding="utf-8").split("param(", 1)[0]
    assert "[Console]::OutputEncoding = [Text.Encoding]::UTF8" in bas, "belgeli kullanımın UTF-8 ön adımı başlıkta yok"
