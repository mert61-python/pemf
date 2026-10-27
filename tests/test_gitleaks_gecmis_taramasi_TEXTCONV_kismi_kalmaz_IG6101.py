# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-6.101 — gitleaks geçmiş (`gitleaks git`) ve `--pre-commit --staged` taraması git TEXTCONV yüzünden KISMİ kalmaz.

ARIZA (ölçüldü, 2026-10-27, gitleaks v8.24.0, git 2.55.0.windows.3): Git for Windows'un SİSTEM gitattributes'u
(`<Git>\\etc\\gitattributes`) `*.doc[x] / *.pdf / *.rtf / *.od[tfs]` türlerini `diff=astextplain` textconv'una bağlar. Textconv
aracı yoksa (`docx2txt.exe: command not found`) ya da dosyayı açamazsa (`E: unsupported filetype` → `fatal: unable to read files
to diff`) gitleaks'in çağırdığı `git log -p` / `git diff --staged` stderr'e yazar ya da DÜŞER:
  * bu deponun kendi geçmişi: "failed to scan Git repository … partial scan … 1 leaks found in partial scan" (16 textconv hatası);
  * içinde bozuk .docx olan küçük depo: `git log -p` .docx commit'inde DÜŞER, daha ESKİ commit'ler HİÇ taranmaz → geçmişe konmuş
    bilinen sahte sızıntı KAÇAR: "no leaks found in partial scan" (aynı depo `--no-textconv` ile: 4/4 commit, sızıntı BULUNDU).
B-6.24 (sızıntının geçmişte durduğunu ölçen kapı) ve yerel geçmiş denetimleri bu aracı kullanır.

ÇÖZÜM: depo kökünde `.gitattributes` bu türleri `-diff` (ikili) yapar — depo içi öznitelik sistemin `diff=astextplain`ini EZER;
satır sonu özniteliği verilmez (checkout değişmez).

ÖLÇÜM (ortamdan bağımsız): sentetik depo geçici dizinde; "sistem" düzeyi Git for Windows'un davranışı `core.attributesFile` +
DÜŞEN bir textconv (`false`) ile ortam yapılandırmasından (GIT_CONFIG_COUNT) kurulur, gerçek sistem/global yapılandırma kapatılır
(GIT_CONFIG_NOSYSTEM / GIT_ATTR_NOSYSTEM / GIT_CONFIG_GLOBAL). Depoya ÜRÜN deposunun `.gitattributes`'u kopyalanır. Sahte sızıntı
çalışma anında parçalardan kurulur (bu dosyada sabit bir belirteç YOK — kendi pre-commit kapımızı tetiklemez); çıktıda değer basılmaz.
KARŞIT: aynı depo `.gitattributes`'suz → KISMİ + sızıntı KAÇAR (aparat düşen textconv'u gerçekten kuruyor).
MUTASYON: `.gitattributes`'tan `*.docx -diff` satırını silmek → KIRMIZI.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import subprocess
from pathlib import Path

import gitleaks_ikili
import pytest

KOK = Path(__file__).resolve().parents[1]
_GIT = shutil.which("git")
#: Git for Windows'un sistem gitattributes'unda textconv'a bağlı türler (ölçüldü) — burada PİNLİ.
SISTEM_TEXTCONV_TURLERI = ("doc", "docx", "docm", "dot", "dotx", "dotm", "pdf", "rtf", "ods", "odf", "odt")

pytestmark = pytest.mark.skipif(_GIT is None, reason="git yok")


def _sahte_belirtec() -> str:
    """GitHub PAT biçiminde YÜKSEK entropili SAHTE değer (gerçek değil) — kaynakta sabit belirteç olmasın diye parçalardan."""
    r = random.SystemRandom()
    return "gh" + "p_" + "".join(r.choice(string.ascii_letters + string.digits) for _ in range(36))


def _ortam(tmp: Path) -> dict:
    sistem_attr = tmp / "sistem_gitattributes"
    sistem_attr.write_text(
        "".join(f"*.{t}\tdiff=astextplain\n*.{t.upper()}\tdiff=astextplain\n" for t in SISTEM_TEXTCONV_TURLERI),
        encoding="utf-8",
    )
    bos_global = tmp / "bos_global_gitconfig"
    bos_global.write_text("", encoding="utf-8")
    ortam = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    ortam.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(bos_global),
            "GIT_CONFIG_COUNT": "4",
            "GIT_CONFIG_KEY_0": "core.attributesFile",
            "GIT_CONFIG_VALUE_0": sistem_attr.as_posix(),
            "GIT_CONFIG_KEY_1": "diff.astextplain.textconv",
            "GIT_CONFIG_VALUE_1": "false",  # textconv aracı düşer (docx2txt yok / dosyayı açamıyor)
            "GIT_CONFIG_KEY_2": "core.autocrlf",
            "GIT_CONFIG_VALUE_2": "false",
            # Öznitelik eşleşmesi BÜYÜK/küçük harf DUYARLI (Linux / CI gibi): Windows'ta `*.DOCX` satırı `*.docx`i de
            # örttüğü için tek satırın silinmesi görünmezdi; her tür her iki yazımıyla ayrıca ölçülür.
            "GIT_CONFIG_KEY_3": "core.ignorecase",
            "GIT_CONFIG_VALUE_3": "false",
        }
    )
    return ortam


def _git(depo: Path, ortam: dict, *arg: str) -> None:
    subprocess.run(
        [_GIT, "-c", "user.name=k5", "-c", "user.email=k5@ornek.invalid", "-c", "commit.gpgsign=false", *arg],
        cwd=str(depo),
        env=ortam,
        check=True,
        capture_output=True,
        timeout=60,
    )


def _depo(tmp: Path, ortam: dict, gitattributes: bool) -> tuple[Path, str]:
    """Eski commit'te sahte sızıntı, YENİ commit'te textconv'a bağlı HER türden (küçük ve BÜYÜK uzantı) bozuk birer belge
    (git log -p en yeniden başlar → düşüş eskiyi gizler)."""
    depo = tmp / ("depo_attr" if gitattributes else "depo_attrsiz")
    depo.mkdir()
    _git(depo, ortam, "init", "-q", "-b", "main", ".")
    kaynak = KOK / ".gitattributes"
    if gitattributes and kaynak.is_file():
        shutil.copyfile(kaynak, depo / ".gitattributes")
    (depo / "a.txt").write_text("ilk\n", encoding="utf-8")
    _git(depo, ortam, "add", "-A")
    _git(depo, ortam, "commit", "-q", "-m", "ilk")
    (depo / "sir.py").write_text(f'TOKEN = "{_sahte_belirtec()}"\n', encoding="utf-8")
    _git(depo, ortam, "add", "sir.py")
    _git(depo, ortam, "commit", "-q", "-m", "eski commit: sahte sizinti")
    belgeler = [f"k_{t}.{t}" for t in SISTEM_TEXTCONV_TURLERI] + [f"b_{t}.{t.upper()}" for t in SISTEM_TEXTCONV_TURLERI]
    for ad in belgeler:
        (depo / ad).write_bytes(b"PK\x03\x04 bozuk belge " + ad.encode())
    _git(depo, ortam, "add", *belgeler)
    _git(depo, ortam, "commit", "-q", "-m", "belge")
    (depo / "a.txt").write_text("ilk\nson\n", encoding="utf-8")
    _git(depo, ortam, "add", "a.txt")
    _git(depo, ortam, "commit", "-q", "-m", "son")
    return depo, "sir.py"


def _tara(ikili: str, depo: Path, ortam: dict, tmp: Path, *ek: str) -> tuple[str, list]:
    rapor = tmp / f"rapor_{depo.name}_{len(ek)}.json"
    r = subprocess.run(
        [
            ikili,
            "git",
            str(depo),
            "--no-banner",
            "--no-color",
            "--redact",
            "--report-format",
            "json",
            "--report-path",
            str(rapor),
            *ek,
        ],
        env=ortam,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    bulgular = json.loads(rapor.read_text(encoding="utf-8")) if rapor.is_file() and rapor.stat().st_size else []
    return (r.stdout + r.stderr), bulgular


def test_KRITIK_gecmis_taramasi_TEXTCONV_ile_KISMI_kalmaz_ve_eski_sizintiyi_BULUR(tmp_path):
    ikili = gitleaks_ikili.gerekli()
    ortam = _ortam(tmp_path)

    # KARŞIT: öznitelik dosyası olmadan aynı depo KISMİ kalır ve eski sızıntıyı KAÇIRIR (aparat kör değil).
    depo0, _ = _depo(tmp_path, ortam, gitattributes=False)
    cikti0, bulgu0 = _tara(ikili, depo0, ortam, tmp_path)
    assert "partial scan" in cikti0 and not bulgu0, (
        "aparat: düşen textconv kısmi taramayı ÜRETMEDİ — ölçüm kör "
        f"(bulgu={len(bulgu0)}; çıktı sonu: {cikti0[-400:]!r})"
    )

    depo, sir_dosyasi = _depo(tmp_path, ortam, gitattributes=True)
    cikti, bulgu = _tara(ikili, depo, ortam, tmp_path)
    assert "partial scan" not in cikti, (
        "gitleaks geçmiş taraması depo .gitattributes'u ile de KISMİ kaldı — ikili belge türleri textconv'a gidiyor; "
        "düşüşten ESKİ commit'ler taranmaz (İG-6.101). Depo kökünde `*.docx -diff` vb. gerekli. "
        f"Çıktı sonu: {cikti[-400:]!r}"
    )
    assert [b.get("File") for b in bulgu] == [sir_dosyasi], (
        f"eski commit'teki sahte sızıntı tam taramada bulunmadı: {[(b.get('RuleID'), b.get('File')) for b in bulgu]}"
    )


def test_KRITIK_pre_commit_staged_taramasi_bozuk_belgeyle_KISMI_kalmaz(tmp_path):
    """pre-commit kancası `gitleaks git --pre-commit --staged`: sahnede bozuk .docx + sahte sızıntı → sızıntı BULUNUR (kısmi değil)."""
    ikili = gitleaks_ikili.gerekli()
    ortam = _ortam(tmp_path)
    depo, _ = _depo(tmp_path, ortam, gitattributes=True)
    (depo / "yeni_sir.py").write_text(f'P2 = "{_sahte_belirtec()}"\n', encoding="utf-8")
    (depo / "ikinci.docx").write_bytes(b"PK\x03\x04 baska bozuk docx")
    _git(depo, ortam, "add", "yeni_sir.py", "ikinci.docx")
    cikti, bulgu = _tara(ikili, depo, ortam, tmp_path, "--pre-commit", "--staged")
    assert "partial scan" not in cikti, f"--staged taraması KISMİ (İG-6.101): {cikti[-400:]!r}"
    assert [b.get("File") for b in bulgu] == ["yeni_sir.py"], (
        f"sahnedeki sahte sızıntı bulunmadı: {[(b.get('RuleID'), b.get('File')) for b in bulgu]}"
    )
