# -*- coding: utf-8 -*-
"""YH D1 — sürüm notları İKİ DİLDE, tek kaynaktan.

ÖLÇÜLEN (YH, 2026-10-22): telefon uygulaması güncelleme notunu manifest'in `mobile.android` bloğundan okur ve İngilizce arayüzde
Türkçe `notes`u göstermez (`mobileUpdate.ts`, I18NI-A3.5: `notes_en` yoksa katalog metni). Ama `notes_en`in hiçbir KAYNAĞI yoktu
(blok yayında elle yazılıyor) ve `publish_release.ps1` yalnız `-Notes` (Türkçe) taşıyordu → İngilizce kullanıcı sürüm notunu hiç
görmezdi. Şimdi: `docs/surum_notlari.json` (iki dil) · `scripts/surum_notlari.py` (`goster` / `mobil`) · `publish_release.ps1 -NotesEn`.

Kapı (ağ YOK; yayın betiği KOŞULMAZ — saf fonksiyonları AST'den çıkarılıp sahte girdiyle çağrılır; `-NotesEn` koruması yalnız
gölgeli kopyada, PATH boş, sahte süitle):
  · versions.json'daki her sürümün (app = backend, launcher, mobile) iki dilde notu var; İngilizcede Türkçe harf yok; tıbbi iddia yok.
  · `New-YayinManifesti`: `notes` Türkçe AYNEN, `notes_en` yalnız doluysa (eski okuyucunun biçimi aynı), exe → installerUrl,
    mobil → apkUrl, previousStable korunur. `New-YayinGovdesi`: iki dil tek gövdede.
  · `-NotesEn` tek başına → süit / kimlik / ağdan ÖNCE durur.
  · `surum_notlari.py mobil`: bloğun KENDİ sürümünün notlarını yazar, başka alana dokunmaz; notu olmayan sürümde dosyayı DEĞİŞTİRMEZ.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "publish_release.ps1"
NOTLAR = KOK / "docs" / "surum_notlari.json"
_PWSH = shutil.which("pwsh")

sys.path.insert(0, str(KOK / "scripts"))
import surum_notlari as sn  # noqa: E402

_TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
# Tıbbi iddia (site / katalog kuralıyla aynı ruh): iyileştirme / şifa / ağrı giderme vaadi YOK.
_IDDIA_TR = re.compile(r"(?i)(iyileştir|şifa|tedavi eder|tedavi sağlar|ağrıyı (giderir|azaltır|keser)|etkili tedavi)")
_IDDIA_EN = re.compile(r"(?i)\b(cures?|heals?|healing|treats?|treating|therapeutic effect|pain relief|relieves?)\b")


def _surumler() -> dict[str, str]:
    v = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))
    return {"app": v["backend"], "launcher": v["launcher"], "mobile": v["mobile"]["name"]}


# ── 1) Not dosyası: versions.json'daki her sürüm iki dilde ───────────────────


@pytest.mark.parametrize("kanal", ["app", "launcher", "mobile"])
def test_KRITIK_versions_json_surumunun_IKI_DILDE_notu_var(kanal):
    surum = _surumler()[kanal]
    notlar = sn.notlari_oku(kanal, surum)  # eksikse NotYok fırlatır
    assert _TR_HARF.search(notlar["notes"]), f"{kanal} {surum} Türkçe notu Türkçe değil: {notlar['notes']!r}"
    assert not _TR_HARF.search(notlar["notes_en"]), (
        f"{kanal} {surum} İngilizce notta Türkçe harf: {notlar['notes_en']!r}"
    )
    assert not _IDDIA_TR.search(notlar["notes"]), f"{kanal} {surum} Türkçe notta tıbbi iddia: {notlar['notes']!r}"
    assert not _IDDIA_EN.search(notlar["notes_en"]), (
        f"{kanal} {surum} İngilizce notta tıbbi iddia: {notlar['notes_en']!r}"
    )


def test_eksik_dil_NOT_YOK_sayilir(tmp_path):
    y = tmp_path / "n.json"
    y.write_text(json.dumps({"mobile": {"9.9.9": {"notes": "Türkçe", "notes_en": " "}}}), encoding="utf-8")
    with pytest.raises(sn.NotYok, match="notes_en"):
        sn.notlari_oku("mobile", "9.9.9", y)
    with pytest.raises(sn.NotYok):
        sn.notlari_oku("mobile", "1.0.0", y)


# ── 2) surum_notlari.py mobil / goster ──────────────────────────────────────

_MANIFEST = {
    "schema": 2,
    "version": "1.9.50",
    "launcher": {"version": "1.9.51"},
    "mobile": {
        "android": {
            "version": "9.9.9",
            "versionCode": 99,
            "url": "https://x/a.apk",
            "sha256": "a" * 64,
            "size": 1,
            "notes": "eski",
        }
    },
}


def _notlar(tmp_path: Path) -> Path:
    y = tmp_path / "surum_notlari.json"
    y.write_text(
        json.dumps({"mobile": {"9.9.9": {"notes": "Yeni sürüm notu ğüşı", "notes_en": "New release note"}}}),
        encoding="utf-8",
    )
    return y


def test_KRITIK_mobil_komutu_blogun_KENDI_surumunun_iki_notunu_yazar(tmp_path):
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps(_MANIFEST, indent=2), encoding="utf-8")
    assert sn.mobil_notlarini_yaz(m, _notlar(tmp_path)) == "9.9.9"
    yeni = json.loads(m.read_text(encoding="utf-8"))
    beklenen = json.loads(json.dumps(_MANIFEST))
    beklenen["mobile"]["android"].update({"notes": "Yeni sürüm notu ğüşı", "notes_en": "New release note"})
    assert yeni == beklenen, "mobil komutu notlar dışında bir alana dokundu"
    assert "ğüşı" in m.read_text(encoding="utf-8"), (
        "Türkçe karakter kaçışlı yazıldı (make_manifest biçimi: ensure_ascii=False)"
    )


def test_KRITIK_notu_olmayan_surumde_manifest_DEGISMEZ(tmp_path):
    m = tmp_path / "manifest.json"
    eski = json.loads(json.dumps(_MANIFEST))
    eski["mobile"]["android"]["version"] = "9.9.8"
    m.write_text(json.dumps(eski, indent=2), encoding="utf-8")
    once = m.read_bytes()
    with pytest.raises(sn.NotYok):
        sn.mobil_notlarini_yaz(m, _notlar(tmp_path))
    assert m.read_bytes() == once, "notu olmayan sürümde manifest yine de yazıldı (eski not yeni APK'ya taşınabilir)"


def test_goster_komutu_metni_UTF8_basar_ve_bilinmeyende_sifirdan_farkli_doner():
    surum = _surumler()["mobile"]
    env = {**os.environ, "PYTHONIOENCODING": ""}
    r = subprocess.run(
        [sys.executable, str(KOK / "scripts" / "surum_notlari.py"), "goster", "mobile", surum, "tr"],
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert r.stdout.decode("utf-8").strip() == sn.notlari_oku("mobile", surum)["notes"]
    r2 = subprocess.run(
        [sys.executable, str(KOK / "scripts" / "surum_notlari.py"), "goster", "mobile", "0.0.1", "en"],
        capture_output=True,
        timeout=60,
    )
    assert r2.returncode == 1 and not r2.stdout.strip()


# ── 3) publish_release.ps1: saf fonksiyonlar (AST) + -NotesEn koruması (gölge) ─


def _pwsh() -> str:
    if not _PWSH:
        capraz.atla("pwsh (PowerShell 7) yok")
    return _PWSH


_AST_CAGIR = r"""param([string]$Betik, [string]$Girdi)
$ErrorActionPreference = 'Stop'
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Betik, [ref]$t, [ref]$e)
if ($e.Count) { throw "ayristirma hatasi: $($e.Count)" }
foreach ($ad in 'New-YayinManifesti', 'New-YayinGovdesi') {
  $f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $ad }, $true)
  if (-not $f) { throw "fonksiyon yok: $ad" }
  Invoke-Expression $f.Extent.Text
}
$g = Get-Content -LiteralPath $Girdi -Raw -Encoding UTF8 | ConvertFrom-Json
$sonuc = foreach ($d in $g) {
  $prev = $null; if ($d.prev) { $prev = @{ version = $d.prev; installerUrl = 'https://x/eski'; sha256 = 'b' } }
  @{ manifest = (New-YayinManifesti -Branch $d.branch -Version '9.9.9' -Notes $d.tr -NotesEn $d.en -Url 'https://x/u' -Sha 'c' -Mandatory $false -PrevStable $prev)
     govde = (New-YayinGovdesi -Notes $d.tr -NotesEn $d.en) }
}
[IO.File]::WriteAllText($env:YH_D1_CIKTI, (ConvertTo-Json -InputObject @($sonuc) -Depth 6), (New-Object Text.UTF8Encoding $false))
"""


def _fonksiyonlari_cagir(tmp_path: Path, durumlar: list[dict]) -> list[dict]:
    (tmp_path / "cagir.ps1").write_bytes(b"\xef\xbb\xbf" + _AST_CAGIR.encode("utf-8"))
    (tmp_path / "girdi.json").write_text(json.dumps(durumlar, ensure_ascii=False), encoding="utf-8")
    cikti = tmp_path / "cikti.json"
    r = subprocess.run(
        [
            _pwsh(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / "cagir.ps1"),
            "-Betik",
            str(BETIK),
            "-Girdi",
            str(tmp_path / "girdi.json"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ, "YH_D1_CIKTI": str(cikti)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(cikti.read_text(encoding="utf-8"))


def test_KRITIK_manifest_notes_TURKCE_kalir_notes_en_yalniz_doluysa(tmp_path):
    exe_iki, mobil_tek, exe_prev = _fonksiyonlari_cagir(
        tmp_path,
        [
            {"branch": "exe", "tr": "Türkçe not ğüşıöç", "en": "English note", "prev": ""},
            {"branch": "mobil", "tr": "Yalnız Türkçe", "en": "", "prev": ""},
            {"branch": "exe", "tr": "T", "en": "E", "prev": "1.0.0"},
        ],
    )
    m = exe_iki["manifest"]
    assert m["notes"] == "Türkçe not ğüşıöç" and m["notes_en"] == "English note", m
    assert (
        m["installerUrl"] == "https://x/u" and "apkUrl" not in m and m["sha256"] == "c" and m["mandatory"] is False
    ), m
    assert exe_iki["govde"] == "Türkçe not ğüşıöç\n\n---\nEnglish:\nEnglish note", exe_iki["govde"]
    t = mobil_tek["manifest"]
    assert set(t) == {"version", "notes", "apkUrl", "sha256", "mandatory"}, (
        f"notes_en boşken anahtar eklendi / biçim değişti: {t}"
    )
    assert mobil_tek["govde"] == "Yalnız Türkçe"
    assert exe_prev["manifest"]["previousStable"]["version"] == "1.0.0", "rollback hedefi (previousStable) düştü"


def test_KRITIK_NotesEn_TEK_BASINA_suitten_ve_kimlikten_ONCE_durur(tmp_path):
    pwsh = _pwsh()
    d = tmp_path / "g"
    (d / "scripts").mkdir(parents=True)
    (d / "bos_path").mkdir()
    shutil.copy2(BETIK, d / "scripts" / "publish_release.ps1")
    kayit = d / "kayit.txt"
    kayit.write_text("", encoding="utf-8")
    (d / "scripts" / "yayin_oncesi_suit.ps1").write_bytes(
        b"\xef\xbb\xbf" + b"Add-Content -LiteralPath $env:Y30_KAYIT -Value 'SUIT'\nexit 0\n"
    )
    sarmal = (
        "param([string]$Publish, [string]$Asset)\n$ErrorActionPreference = 'Stop'\n"
        "function global:git { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'GIT'; }\n"
        "function global:Invoke-RestMethod { Add-Content -LiteralPath $env:Y30_KAYIT -Value 'IRM'; throw 'golge' }\n"
        "try { & $Publish -Branch mobil -Version 9.9.9 -AssetPath $Asset -NotesEn 'only english'; exit 0 }\n"
        "catch { Write-Host ('PUBLISH-HATA: ' + $_.Exception.Message); exit 9 }\n"
    )
    (d / "sarmal.ps1").write_bytes(b"\xef\xbb\xbf" + sarmal.encode("utf-8"))
    (d / "asset.bin").write_bytes(b"x")
    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
    env.update(
        {
            "PATH": str(d / "bos_path"),
            "Y30_KAYIT": str(kayit),
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    r = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(d / "sarmal.ps1"),
            "-Publish",
            str(d / "scripts" / "publish_release.ps1"),
            "-Asset",
            str(d / "asset.bin"),
        ],
        cwd=d,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    cikti = r.stdout + r.stderr
    assert r.returncode == 9 and "-NotesEn tek basina" in cikti, f"rc={r.returncode}\n{cikti[-800:]}"
    assert kayit.read_text(encoding="utf-8").strip() == "", (
        "Türkçe notsuz -NotesEn ile süit / kimlik / ağ adımına geçildi"
    )
