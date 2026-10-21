# -*- coding: utf-8 -*-
"""I18NI-A3.8 — İngilizce bayrağı AÇILINCA (`bayrak.py --ac`) K-2 kapısı `hooks.nsi`'nin ÜRETİLMİŞ İngilizce LangString satırlarını (1033)
"sabit metin" sayar → `test_K2_tamam_dosyalarda_sabit_metin_yok_python_rust_html_nsis` 13 satırla KIRMIZI; bayrağı açan commit kapıda durur.
(Defterdeki `muaf` listesi yalnız 13 TÜRKÇE üretilmiş satırı taşır.)

Sonda depo bayrağını DEĞİŞTİRMEZ: kataloğu + `tauri.conf.json`'u geçici köke kopyalar, dil listesini iki dile çevirir, üretilmiş hooks metnini
GERÇEK `launcher_uret.hooks_metni` ile kurar ve K-2'nin GERÇEK çıkarıcı + muaf kuralından (`cikar.nsis_adaylari` + `kapsam.muaf_mi`) geçirir.
Bugün KIRMIZI (13 ihlal); düzeltilince YEŞİL. Bayrak kapalı dal (bugünkü repo) YEŞİL kalmalı.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))
from scripts.i18n import cikar, kapsam, launcher_uret  # noqa: E402

DEFTER = json.loads((KOK / "i18n" / "kapsam.json").read_text(encoding="utf-8"))


def _gecici_kok(tmp_path: Path, diller: list[str]) -> Path:
    kok = tmp_path / "kok"
    shutil.copytree(KOK / "launcher" / "i18n", kok / "launcher" / "i18n")
    (kok / "launcher" / "app" / "windows").mkdir(parents=True)
    shutil.copyfile(KOK / launcher_uret.HOOKS_YOLU, kok / launcher_uret.HOOKS_YOLU)
    conf = json.loads((KOK / launcher_uret.TAURI_CONF).read_text(encoding="utf-8"))
    conf["bundle"]["windows"]["nsis"]["languages"] = diller
    (kok / launcher_uret.TAURI_CONF).write_text(json.dumps(conf, ensure_ascii=False), encoding="utf-8")
    return kok


@pytest.mark.parametrize("diller", [["Turkish"], ["Turkish", "English"]], ids=["bayrak_kapali", "bayrak_acik"])
def test_K2_hooks_uretilmis_blok_bayraktan_bagimsiz_temiz(tmp_path, diller):
    kok = _gecici_kok(tmp_path, diller)
    metin = launcher_uret.hooks_metni(kok)
    if len(diller) == 2:
        assert " 1033 " in metin, "iki dilli üretim İngilizce LangString yazmadı (sonda geçersiz)"
    adaylar = cikar.nsis_adaylari(launcher_uret.HOOKS_YOLU, metin)
    ihlal = [
        f"{a['satir']}: {a['metin'][:70]}"
        for a in adaylar
        if not kapsam.muaf_mi(DEFTER, launcher_uret.HOOKS_YOLU, a["metin"])
    ]
    assert not ihlal, f"bayrak {diller}: K-2 üretilmiş LangString'i sabit metin sayıyor ({len(ihlal)}):\n" + "\n".join(
        ihlal
    )


def test_K2_elle_yazilmis_TEK_dilli_LangString_yine_taranir():
    """Orkestratör (14): atlama YALNIZ Türkçe (1055) eşi olan üretilmiş çifte uygulanır — elle eklenmiş tek dilli satır (ör. 1033 etiketli
    Türkçe metin) K-2'den kaçmaz."""
    metin = (
        'LangString PEMF_uret 1055 "Türkçe üretilmiş"\n'
        'LangString PEMF_uret 1033 "Generated English"\n'
        'LangString PEMF_elle 1033 "Elle yazılmış Türkçe ileti"\n'
    )
    adaylar = [a["metin"] for a in cikar.nsis_adaylari(launcher_uret.HOOKS_YOLU, metin)]
    assert "Generated English" not in adaylar
    assert "Türkçe üretilmiş" in adaylar and "Elle yazılmış Türkçe ileti" in adaylar, adaylar
