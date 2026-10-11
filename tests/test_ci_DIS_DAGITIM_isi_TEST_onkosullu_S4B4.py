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
    r"xcrun\s+altool|--upload-app|gh\s+release\s+(?:create|upload)|action-gh-release|vercel\s+(?:deploy|--prod)|fastlane\s+(?:pilot|deliver)"
)
TEST_ADIMI = re.compile(r"\bpytest\b|yayin_oncesi_suit")


def _adim_metni(adim: dict) -> str:
    return f"{adim.get('uses', '')}\n{adim.get('run', '')}"


def korumasiz_dagitim_isleri(belge: dict) -> list[str]:
    isler = (belge or {}).get("jobs") or {}
    test_isleri = {
        ad for ad, j in isler.items() if any(TEST_ADIMI.search(_adim_metni(a)) for a in (j or {}).get("steps") or [])
    }
    out = []
    for ad, j in isler.items():
        if not any(DAGITIM.search(_adim_metni(a)) for a in (j or {}).get("steps") or []):
            continue
        needs = (j or {}).get("needs") or []
        needs = [needs] if isinstance(needs, str) else list(needs)
        if not set(needs) & test_isleri:
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
