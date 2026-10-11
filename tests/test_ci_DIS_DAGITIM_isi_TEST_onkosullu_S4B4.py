# -*- coding: utf-8 -*-
"""S-4B.4 [ÖNERİLEN UYGULANDI] (4-A incelemesi A1 S1) — dış dağıtım servisine yükleyen hiçbir CI işi test süitini atlayamaz.

ARIZA: `.github/workflows/upload-testflight.yml` `upload-testflight` dalına itilince sırlarla (`APPLE_ID`, uygulamaya özel parola) `xcrun altool
--upload-app` koşturuyordu; iş akışında HİÇBİR test işi yoktu → Y30'un (yayın öncesi tam süit, `publish_release.ps1`) DIŞINDA bir dağıtım yolu.
Dal 2026-08-18'de arşivlendi (README: tek dal `production-hardening`) ve yüklenen `.ipa` izlenmiyor → iş bugün ölü ama dal yeniden açılırsa canlanır.
Karar (önerilen a): arşivle — iş akışı kaldırıldı (geçmişte durur).

KAPI: her iş akışında dış dağıtım adımı (`xcrun altool`, `--upload-app`, `gh release create|upload`, `action-gh-release`, `vercel deploy|--prod`,
`fastlane pilot|deliver`) taşıyan iş, `needs:` ile pytest ya da Y30 süitini koşan bir işe bağlı olmalı. Yalnız YAML'ın `run` / `uses` alanları
okunur (yorumlar değil).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
DAGITIM = re.compile(
    r"xcrun\s+altool|--upload-app|gh\s+release\s+(?:create|upload)|gh\s+api\b[^\n]*/releases|action-gh-release|release-action"
    r"|upload-release-asset|vercel-action|\bvercel\b(?!\.json)|fastlane\s+(?:pilot|deliver|supply)|upload_to_(?:play_store|app_store|testflight)"
    r"|\btwine\s+upload|\bnpm\s+publish|\beas(?:-cli)?\s+(?:submit|update)\b|--auto-submit|firebase\s+appdistribution"
    r"|(?m:^\s*(?:scp|rsync)\s[^\n]*:)|\bcurl\b[^\n]*(?:\s-T\s|--upload-file)|\baws\s+s3\s+(?:cp|sync|mv)|\bgsutil\s+(?:-m\s+)?(?:cp|rsync)"
)
# 4B-3.3: test ADIMI = satır başında pytest (ya da `python -m pytest`) ÇAĞRISI — `pip install pytest`, `--collect-only` ve
# `|| true` / `|| :` / `; exit 0` ile yutulan koşu test sayılmaz; Y30 betiği ayrıca kabul.
TEST_ADIMI = re.compile(
    r"(?m)^\s*(?:python\d?(?:\.\d+)?\s+-m\s+)?pytest\b(?![^\n]*(?:--collect-only|\|\|\s*(?:true|:)|;\s*exit\s+0))|yayin_oncesi_suit"
)
# İş düzeyinde `if:` bu ifadelerden birini taşıyorsa iş, `needs` ettiği iş DÜŞSE de koşar → koruma zinciri orada kopar.
HER_KOSULDA = re.compile(r"always\(\)|cancelled\(\)|failure\(\)")


def _adim_metni(adim: dict) -> str:
    return f"{adim.get('uses', '')}\n{adim.get('run', '')}"


def _yanlis_mi(deger) -> bool:
    return deger is False or str(deger).strip().lower() in ("false", "${{ false }}")


def _dogru_mu(deger) -> bool:
    return deger is True or str(deger).strip().lower() in ("true", "${{ true }}")


def _gecerli_test_isi(j: dict) -> bool:
    if _dogru_mu(j.get("continue-on-error")) or _yanlis_mi(j.get("if", True)):
        return False
    return any(
        TEST_ADIMI.search(_adim_metni(a))
        and not _dogru_mu(a.get("continue-on-error"))
        and not _yanlis_mi(a.get("if", True))
        for a in j.get("steps") or []
    )


def _needs(j: dict) -> list[str]:
    n = j.get("needs") or []
    return [n] if isinstance(n, str) else list(n)


def _test_ile_korunur(isler: dict, ad: str, test_isleri: set[str], gorulen: set[str]) -> bool:
    """`ad` işi yalnız bir test işi BAŞARIYLA bittiyse koşar mı? `needs` zinciri (dolaylı) izlenir; `always()` gibi koşul zinciri koparır."""
    j = isler.get(ad) or {}
    if HER_KOSULDA.search(str(j.get("if", ""))):
        return False
    for n in _needs(j):
        if n in gorulen:
            continue
        gorulen.add(n)
        if n in test_isleri or _test_ile_korunur(isler, n, test_isleri, gorulen):
            return True
    return False


def korumasiz_dagitim_isleri(belge: dict) -> list[str]:
    isler = (belge or {}).get("jobs") or {}
    test_isleri = {ad for ad, j in isler.items() if _gecerli_test_isi(j or {})}
    out = []
    for ad, j in isler.items():
        if not any(DAGITIM.search(_adim_metni(a)) for a in (j or {}).get("steps") or []):
            continue
        if not _test_ile_korunur(isler, ad, test_isleri, set()):
            out.append(ad)
    return out


def test_KRITIK_dis_dagitim_isi_TEST_isine_bagli_S4B4():
    bulunan = {}
    dosyalar = sorted((KOK / ".github" / "workflows").glob("*.y*ml"))
    assert len(dosyalar) >= 5, f"VAKUM: yalnız {len(dosyalar)} iş akışı"
    for p in dosyalar:
        isler = korumasiz_dagitim_isleri(yaml.safe_load(p.read_text(encoding="utf-8")))
        if isler:
            bulunan[p.name] = isler
    assert not bulunan, (
        f"test süitini ÖNKOŞUL almayan dış dağıtım işi (Y30 dışı yayın yolu): {bulunan} — `needs:` ile pytest/Y30 işine bağlayın ya da arşivleyin"
    )


def test_KARSIT_KANIT_algilayici_korumasiz_ve_korumali_isi_AYIRIR():
    korumasiz = yaml.safe_load(
        "jobs:\n  upload:\n    runs-on: macos-latest\n    steps:\n      - run: xcrun altool --upload-app -f a.ipa\n"
    )
    korumali = yaml.safe_load(
        "jobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python -m pytest tests -q\n"
        "  upload:\n    needs: [test]\n    runs-on: macos-latest\n    steps:\n      - run: xcrun altool --upload-app -f a.ipa\n"
    )
    yorumda = yaml.safe_load("jobs:\n  x:\n    steps:\n      - run: echo hazir  # xcrun altool burada degil\n")
    assert korumasiz_dagitim_isleri(korumasiz) == ["upload"]
    assert korumasiz_dagitim_isleri(korumali) == []
    assert korumasiz_dagitim_isleri(yorumda) == [], "yorum/echo içindeki ad dağıtım SAYILDI (yanlış kırmızı)"
