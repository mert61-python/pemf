# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CI KİPİ + HIZLI KÜME (istem 66 CT2 c · Y326 katman 6) — push'ta değişen alanlara göre hızlı küme, gece / yayın dalında tam süit.

KİP (`CI_KIP`, GITHUB_ENV'e yazılır):
  tam   — gece (cron) ya da çağıran iş akışı `kip: tam` · elle (`workflow_dispatch`) `kip=tam` · production-hardening / main / master
          push'u · birleşme tabanı bulunamadı · GENİŞ ETKİLİ dosya değişti (conftest, test yardımcıları, bağımlılık kilitleri, iş akışı,
          CI betikleri, defter / taban dosyaları, i18n katalogları) · değişen kaynak sayısı > SINIR
  hizli — kalan push / PR: KÜME = değişen test dosyaları + değişen her dosyanın ADINI (Python modülünde kök adı) anan testler + sabit
          kapılar (CI / i18n). Paket toplamı (fail_under, kapsam tabanı) hızlı kipte ÖLÇÜLMEZ — alt küme toplamı anlamsızdır; dalın
          değiştirdiği satırların fark kapsamı (%100) ise HER kipte zorunludur. Tam süit + toplam: production-hardening push'u ve gece.
ALAN (`alan <ad>`): launcher / firmware işleri kendi alanı değişmediyse hızlı kipte ağır adımları atlar (iş yine koşar ve yeşil biter →
gerekli durum denetimi her push'ta durum yazar).
Kullanım:
  python scripts/ci_hizli_kume.py kip --olay <github.event_name> --dal <github.ref_name> [--istek <tam|hizli|>] --github-env <dosya>
  python scripts/ci_hizli_kume.py alan <launcher|firmware> [--istek ...] [--olay ...] [--dal ...] --github-env <dosya>
Kapı: tests/test_CT2c_ci_hizli_kume_KIP.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
TAM_DALLAR = {"production-hardening", "main", "master"}
TABAN_ADAYLARI = ("origin/duzeltme/dalga-2", "origin/production-hardening")
SINIR = 80
#: Bu dosyalar değişince etkisi test adından kestirilemez → tam süit.
GENIS = [
    re.compile(p)
    for p in (
        r"^tests/conftest\.py$",
        r"^tests/(?!test_)[^/]+\.py$",  # test yardımcıları / aparatlar (capraz, xdist_grup, *_aparat …)
        r"^tests/[^/]+\.json$",  # atlanan defteri, kapsam tabanı, temel çizgiler
        r"^pyproject\.toml$",
        r"^requirements[^/]*\.txt$",
        r"^build_tools/myenv-requirements\.txt$",
        r"^\.github/workflows/tests\.yml$",
        r"^scripts/(ci_[^/]+|fark_kapsami|kapsam_tabani_kapisi|firmware_kapsam)\.py$",
        r"^scripts/ci_[^/]+\.json$",
        r"^i18n/[^/]+\.json$",
        r"^apps/backend/[^/]+\.py$",  # üst düzey backend modülleri (backend_service, headless_core, event_bus — her yere girer)
    )
]
#: Her hızlı kümede koşan sabit kapılar (CI sözleşmesi, i18n K-kapıları).
SABIT = ("tests/test_ci_*.py", "tests/test_CT1*.py", "tests/test_CT2*.py", "tests/test_i18n_*.py")
ALANLAR = {
    "launcher": [
        r"^launcher/",
        r"^scripts/fark_kapsami\.py$",
        r"^tests/kapsam_tabani\.json$",
        r"^\.github/workflows/tests\.yml$",
    ],
    "firmware": [
        r"^firmware/",
        r"^tests/firmware_",
        r"^tests/test_(firmware|Y285_firmware|CT1g|CT2f)",
        r"^scripts/(firmware_[^/]+|fark_kapsami)\.py$",
        r"^tests/kapsam_tabani\.json$",
        r"^\.github/workflows/tests\.yml$",
    ],
}


def _git(*a: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *a], cwd=KOK, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def birlesme_tabani() -> str | None:
    for aday in TABAN_ADAYLARI:
        try:
            return _git("merge-base", "HEAD", aday).strip() or None
        except subprocess.CalledProcessError:
            continue
    return None


def degisenler(taban: str) -> list[str]:
    return [s for s in _git("diff", "--name-only", taban, "HEAD").splitlines() if s.strip()]


def zorunlu_tam(olay: str, dal: str, istek: str) -> str | None:
    """Tam kip nedeni (None = değişikliğe bakılır)."""
    if istek == "tam":
        return "istenen kip: tam"
    if olay == "schedule":
        return "gece (cron) koşusu"
    if olay == "push" and dal in TAM_DALLAR:
        return f"{dal} push'u (yayın dalı — tam süit + paket toplamı)"
    return None


def genis_mi(yol: str) -> bool:
    return any(p.search(yol) for p in GENIS)


def anahtar(yol: str) -> str:
    p = Path(yol)
    if p.suffix == ".py":
        return p.parent.name if p.stem == "__init__" else p.stem
    return p.name


def kume(degisen: list[str], kok: Path = KOK) -> list[str]:
    testler = sorted(str(p.relative_to(kok)).replace("\\", "/") for p in (kok / "tests").glob("test_*.py"))
    secilen: set[str] = {d for d in degisen if d in testler}
    anahtarlar = {anahtar(d) for d in degisen if not d.startswith("tests/test_")}
    anahtarlar = {a for a in anahtarlar if len(a) >= 3}
    if anahtarlar:
        desen = re.compile("|".join(re.escape(a) for a in sorted(anahtarlar, key=len, reverse=True)))
        for t in testler:
            if t in secilen:
                continue
            if desen.search((kok / t).read_text(encoding="utf-8", errors="replace")):
                secilen.add(t)
    for d in SABIT:
        secilen.update(str(p.relative_to(kok)).replace("\\", "/") for p in kok.glob(d))
    return sorted(s for s in secilen if (kok / s).is_file())


def kip_belirle(olay: str, dal: str, istek: str) -> tuple[str, str, list[str], list[str]]:
    """→ (kip, neden, değişen dosyalar, küme)."""
    neden = zorunlu_tam(olay, dal, istek)
    if neden:
        return "tam", neden, [], []
    taban = birlesme_tabani()
    if taban is None:
        return "tam", "birleşme tabanı yok (origin/duzeltme/dalga-2 · origin/production-hardening)", [], []
    degisen = degisenler(taban)
    genis = [d for d in degisen if genis_mi(d)]
    if genis:
        return "tam", f"geniş etkili dosya değişti: {', '.join(genis[:5])}", degisen, []
    kaynak = [d for d in degisen if not d.startswith("tests/")]
    if len(kaynak) > SINIR:
        return "tam", f"{len(kaynak)} kaynak dosya değişti (> {SINIR})", degisen, []
    return "hizli", f"taban {taban[:12]} · {len(degisen)} değişen dosya", degisen, kume(degisen)


#: koşum takımı aparatlarını kullanan test dosyaları (firmware işi; CT1g sahte .gcda yazdığı için backend işinde kalır)
APARATLAR = ("firmware_host_aparat", "firmware_dongu_aparat")
APARAT_DISI = {"tests/test_CT1g_firmware_kapsam.py"}
#: yalnız aparatı İÇE AKTARAN testler (adını metin olarak anan kapı testleri — ör. CT2f sahte .gcda yazar — kümeye girmez)
_APARAT_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:" + "|".join(APARATLAR) + r")\b", re.M)


def firmware_testleri(kok: Path = KOK) -> list[str]:
    sonuc = []
    for t in sorted((kok / "tests").glob("test_*.py")):
        rel = str(t.relative_to(kok)).replace("\\", "/")
        if rel not in APARAT_DISI and _APARAT_IMPORT.search(t.read_text(encoding="utf-8", errors="replace")):
            sonuc.append(rel)
    return sonuc


def alan_degisti(ad: str, degisen: list[str]) -> bool:
    return any(re.search(p, d) for p in ALANLAR[ad] for d in degisen)


def _yaz(github_env: Path | None, satirlar: dict[str, str]) -> None:
    for k, v in satirlar.items():
        print(f"{k}={v}")
    if github_env is not None:
        with github_env.open("a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in satirlar.items())


def _konsol_utf8() -> None:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="CI kipi + hızlı küme")
    ap.add_argument("komut", choices=["kip", "alan", "firmware-testleri"])
    ap.add_argument("alan_adi", nargs="?", choices=sorted(ALANLAR))
    ap.add_argument("--olay", default="")
    ap.add_argument("--dal", default="")
    ap.add_argument("--istek", default="")
    ap.add_argument("--github-env", type=Path)
    ap.add_argument("--kume-dosyasi", type=Path, default=KOK / "ci_kume.txt")
    a = ap.parse_args(argv)
    if a.komut == "firmware-testleri":
        liste = firmware_testleri()
        a.kume_dosyasi.write_text("".join(f"{s}\n" for s in liste), encoding="utf-8")
        print(f"kart yazılımı koşum takımı testleri: {len(liste)} dosya → {a.kume_dosyasi.name}")
        return 0 if liste else 2
    kip, neden, degisen, secilen = kip_belirle(a.olay, a.dal, a.istek)
    if a.komut == "alan":
        if not a.alan_adi:
            ap.error("alan adı gerekli")
        acik = kip == "tam" or alan_degisti(a.alan_adi, degisen)
        print(f"alan {a.alan_adi}: {'KOŞAR' if acik else 'değişmedi — ağır adımlar atlanır'} ({kip}: {neden})")
        _yaz(a.github_env, {"CI_KIP": kip, "CI_ALAN": "1" if acik else "0"})
        return 0
    print(f"CI kipi: {kip} — {neden}")
    if kip == "hizli":
        a.kume_dosyasi.write_text("".join(f"{s}\n" for s in secilen), encoding="utf-8")
        print(f"hızlı küme: {len(secilen)} test dosyası → {a.kume_dosyasi.name}")
    _yaz(a.github_env, {"CI_KIP": kip})
    return 0


if __name__ == "__main__":
    sys.exit(main())
