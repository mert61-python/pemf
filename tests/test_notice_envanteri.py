# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ATIF (NOTICE) ENVANTERI EKSIKSIZ — ve bu kapi CI'DA DA KOSAR (2026-09-16).

OLCULEN ARIZA. `THIRD_PARTY_LICENSES.md` 2026-08-10'da donmustu: 50 sevk edilen
bagimliliktan **36'si** envanterde YOKTU — `shap`, `grad-cam`, `timm`, `captum`,
`celldetection` gibi sonradan eklenenler bir yana, `numpy`, `fastapi`, `pillow`,
`opencv-python` gibi TEMEL paketler de eksikti. Envanter yalniz 26 satirdi.

Sebep: liste `base-deps.zip` icindeki `dist-info/METADATA`dan uretilmisti ve PyInstaller
cogu paketin metadata'sini AYIKLIYOR. Yani envanter bayat degil, YAPISAL OLARAK EKSIKTI.

⚠️ NEDEN AYRI DOSYA — VE BU BIR DUZELTME. Bu testler once `test_license_surface.py`ye
eklenmisti. O dosyanin BASINDA modul-duzeyi `pytestmark = skipif(not PAKET.exists())`
var: `base-deps.zip` yoksa dosyadaki TUM testler atlanir. Temiz checkout'ta — yani
CI'da — paket YOKTUR. Dolayisiyla "CI'da kossun" diye yazilan kapi, tam da CI'da
atlanacakti. Ayri dosyaya alindi; burada skip YOK.

⚠️ Bu ayni zamanda bir bulgu: mevcut KOPYLEFT kapilari da CI'da hic kosmuyor. Onlar
paketten okumak ZORUNDA (lisans metinleri orada), ama bu envanter kapisinin kaynagi
`requirements.txt` — her yerde okunur.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _req_calisma_zamani() -> set[str]:
    from scripts.lisans_envanteri_uret import _SEVK_EDILMEYEN, _req_paketleri

    return {a for a in _req_paketleri() if a not in _SEVK_EDILMEYEN}


def test_KRITIK_NOTICE_her_SEVK_EDILEN_bagimliligi_LISTELER():
    """⚠️ BU TEST DÜZELTMEDEN ÖNCE KIRMIZIYDI (36 paket eksikti, 50'de).

    Atıf (NOTICE) yükümlülüğü dağıtılan HER bileşeni kapsar. Eksik envanter, ticari
    satışta doğrudan risktir.
    """
    metin = (KOK / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8").lower()
    eksik = sorted(a for a in _req_calisma_zamani() if a not in metin)
    assert not eksik, (
        f"NOTICE'ta {len(eksik)} sevk edilen bağımlılık YOK: {eksik}\n"
        "Çözüm: `python scripts/lisans_envanteri_uret.py` (envanter ÜRETİLİR, elle yazılmaz)."
    )


def test_KARSIT_KANIT_NOTICE_kapisi_GERCEKTEN_eksik_yakalar():
    """⚠️ Kapının kendi kapısı: `_req_calisma_zamani` boş dönerse test sessizce yeşil kalır."""
    adlar = _req_calisma_zamani()
    assert len(adlar) >= 20, f"requirements'tan yalnız {len(adlar)} paket okundu — ayrıştırıcı bozuk"
    assert "numpy" in adlar and "fastapi" in adlar, "bilinen çalışma-zamanı paketleri okunamadı"
    assert "pytest" not in adlar, "sevk EDİLMEYEN araç envantere sızıyor → yanlış atıf beyanı"


def test_KARSIT_KANIT_NOTICE_ureteci_KENDI_ciktisiyla_UYUMLU():
    """Üreteç ile dosya ayrışmamalı: `--kontrol` farkı bildirirse envanter bayat demektir."""
    from scripts.lisans_envanteri_uret import envanter

    satirlar = envanter()
    assert len(satirlar) >= 40, f"üreteç yalnız {len(satirlar)} bileşen buldu — kaynaklar okunamıyor"
    metin = (KOK / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8").lower()
    ornek = [a for a, _, _ in satirlar[:25] if a not in metin]
    assert not ornek, f"üretecin bulduğu ama dosyada olmayan bileşenler: {ornek}"


# ── PEP 639 ayrıştırıcısı ────────────────────────────────────────────────────


def test_KRITIK_License_Expression_OKUNUR():
    """⚠️ Bu kapı olmadan `License-Expression` desteğini silmek HİÇBİR testi kırmazdı.

    Ölçüldü (2026-09-16): sevk edilen pakette 100 paketin **30'unun** lisansı, yalnız
    `License:` okuyan eski ayrıştırıcıyla BOŞ görünüyordu. Bugün bu bir ihlal gizlemiyor
    (kopyleft kümesi iki okuyucuda da `{ultralytics}`), ama `License-Expression: AGPL-3.0`
    diyen YENİ bir paket kopyleft kapısına görünmez olurdu.
    """
    from scripts.lisans_envanteri_uret import metadata_lisansi

    modern = "Metadata-Version: 2.4\nName: ornek\nLicense-Expression: AGPL-3.0\nLicense-File: LICENSE\n"
    assert metadata_lisansi(modern) == "AGPL-3.0", (
        "`License-Expression` okunmuyor → modern paketlerin lisansı BOŞ görünür ve kopyleft kapısı onları kaçırır"
    )


def test_KARSIT_KANIT_eski_License_alani_HALA_okunur():
    """Yeni alanı eklemek eskisini düşürmenin bahanesi değil: iki biçim de sahada."""
    from scripts.lisans_envanteri_uret import metadata_lisansi

    klasik = "Name: ornek\nLicense: BSD-3-Clause\n"
    assert metadata_lisansi(klasik) == "BSD-3-Clause", "klasik `License:` alanı artık okunmuyor"
    sinif = "Name: ornek\nClassifier: License :: OSI Approved :: MIT License\n"
    assert "MIT" in metadata_lisansi(sinif), "`Classifier` yedeği kayboldu"
    assert metadata_lisansi("Name: ornek\n") == "", "lisansı olmayan metadata boş dönmeli"


def test_KARSIT_KANIT_License_Expression_ONCELIKLI():
    """İki alan birden varsa PEP 639 alanı kazanmalı — eski alan bayat olabilir."""
    from scripts.lisans_envanteri_uret import metadata_lisansi

    ikisi = "Name: ornek\nLicense: UNKNOWN\nLicense-Expression: Apache-2.0\n"
    assert metadata_lisansi(ikisi) == "Apache-2.0", "eski `License:` alanı PEP 639'u eziyor"
