# -*- coding: utf-8 -*-
"""YS1h (site-ci 0cf83c06): görünüm alanı kapısı tarayıcıyı `--lang=tr-TR` ile açıyordu; o bayrak yalnız Windows'ta `navigator.language`'ı
belirler — GitHub ubuntu koşucusunda site İNGİLİZCE açıldı ve /pricing 320 px'te yatay taştı (EN paket kartı 331 px). Yerelde (tr-TR) İngilizce
hiç ölçülmemişti, EN bayrağı canlıda AÇIK.

KAPI: site hedefinin HER sayfası iki dilde ve dil ADRESLE sabit ölçülür — TR durumu aynı adla (`?lang=tr`; bilinen bulgu anahtarları
değişmez), EN durumu `-en` ekiyle (`?lang=en`); kritik öğe tanımları iki dilde aynı; sayfa kümesi küçülmez. (Ölçümün kendisi site-ci adımı.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "responsive_kapisi.py"
SAYFALAR = {"ana": "/", "download": "/download", "features": "/features", "pricing": "/pricing", "support": "/support"}


def _modul():
    spec = importlib.util.spec_from_file_location("responsive_kapisi_ys1h", BETIK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_KRITIK_site_her_sayfa_IKI_DILDE_adresle_sabit_olculur():
    site = _modul().HEDEFLER["site"]
    beklenen = set(SAYFALAR) | {f"{ad}-en" for ad in SAYFALAR}
    assert set(site) == beklenen, f"site durumları {sorted(site)} — beklenen {sorted(beklenen)}"
    for ad, yol in SAYFALAR.items():
        assert site[ad]["yol"] == f"{yol}?lang=tr", (
            f"{ad}: TR adresle sabit değil ({site[ad]['yol']}) — tarayıcı diline düşer"
        )
        assert site[f"{ad}-en"]["yol"] == f"{yol}?lang=en", f"{ad}-en: EN ölçülmüyor ({site[f'{ad}-en']['yol']})"
        assert site[ad]["kritik"] == site[f"{ad}-en"]["kritik"], f"{ad}: kritik öğeler iki dilde farklı"


def test_KARSIT_launcher_hedefi_DEGISMEDI_dil_eki_yok():
    launcher = _modul().HEDEFLER["launcher"]
    assert launcher and not any(ad.endswith("-en") for ad in launcher), sorted(launcher)
