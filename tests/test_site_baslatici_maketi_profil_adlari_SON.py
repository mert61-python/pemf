# -*- coding: utf-8 -*-
"""SON-A2.53 (22 · A2b) — sitedeki başlatıcı MAKETİ (`apps/web/src/components/LauncherMock.tsx`, ana sayfa + özellikler) gerçek başlatıcının
profil adlarını gösterir; METIN-KILAVUZU "iki yüzeyin dili ayrışmamalı" (site + launcher). D6.67 başlatıcıda "Araştırma Modu" → "Araştırma"
(EN "Research Mode" → "Research") yaptı; maket kataloğu (`baslatici.profil.*`) eski adda kaldı. Kapı: TR ve EN'de maketteki üç profil adı
başlatıcının `ui.profilMeta.<profil>.ad` değeriyle BİREBİR aynı."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ESLEME = {"ev": "home", "arastirma": "research", "veteriner": "vet"}  # site maketi anahtarı → başlatıcı profil kimliği


def _oku(yol: Path) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_site_baslatici_maketi_profil_adlari_BASLATICININ_KENDI_adlariyla_ayni(dil):
    site = _oku(KOK / "apps" / "web" / "src" / "i18n" / dil / "baslatici.json")["profil"]
    launcher = _oku(KOK / "launcher" / "i18n" / f"{dil}.json")["ui"]["profilMeta"]
    assert set(site) == set(ESLEME), f"aparat: maket profil anahtarları değişti ({sorted(site)})"
    farkli = {k: (site[k], launcher[p]["ad"]) for k, p in ESLEME.items() if site[k] != launcher[p]["ad"]}
    assert not farkli, (
        f"[{dil}] site başlatıcı maketi ↔ gerçek başlatıcı profil adı ayrışık (maket, başlatıcı): {farkli}"
    )


def test_maket_bilesen_uc_profil_anahtarini_cizer():
    """aparat: maket bileşeni bu üç anahtarı gerçekten çiziyor (kapının baktığı katalog ekranda)."""
    kaynak = (KOK / "apps" / "web" / "src" / "components" / "LauncherMock.tsx").read_text(encoding="utf-8")
    for k in ESLEME:
        assert f"t('baslatici.profil.{k}')" in kaynak, k
