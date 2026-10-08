# -*- coding: utf-8 -*-
"""O-B2B2.4 (2-B2 açık madde 10) — Y113 kapısının gerçek-ACL arıza aparatı pytest tmp'sinde OKUNAMAYAN artık BIRAKMAZ.

ÖLÇÜLEN KUSUR (2-B2 temizliği, 2026-10-08): `test_kimlik_DB_okunamazken_ileti_ARIZA_ve_CARE_Y113._Ariza` `acl` kipinde auth DB
kopyasını ürünün `utils.file_acl.lock_down_file(keep_current_user=False)` yardımcısıyla YALNIZ SYSTEM + Administrators'a
kilitliyor, blok çıkışında izni GERİ ALMIYORDU → her tam süit pytest tmp'sinde 3 adet okunamayan `acl\\auth_users.db`
kalıyordu (PowerShell `Remove-Item` "Access denied"; sahip olarak `icacls /reset` sonrası silinebildi). Süitin mevcut
temizleyicisi (`conftest._acl_kilitli_duz_metin_yedek_ARTIGI_kalmaz`) yalnız `*.plain.bak*` desenini kapsar.

Kapı DAVRANIŞLA ölçer (`test_acl_kilitli_artik_KALMAZ` deseni): Y113 dosyasının `acl` düğümleri ALT SÜREÇTE, `--basetemp` bu
testin tmp'sinde koşulur (çocukta süitin ağ bekçisi conftest ile kurulur); sonra o kökteki HER dosya okunmaya çalışılır —
`PermissionError` veren dosya artıktır. Düğüm sayısı sabit: `acl` düğümü düşer/atlanırsa (ör. Windows dışı) kapı KÖR sayılır.
Kapı kendi kırmızısında da artık bırakmaz: sonda kökün izni `icacls /reset` ile geri alınır (Windows).
"""

from __future__ import annotations

import os
import subprocess

import pytest
from betik_alt_sureci import KOK, kostur, yalitik_ortam

Y113_DOSYASI = "tests/test_kimlik_DB_okunamazken_ileti_ARIZA_ve_CARE_Y113.py"
# Y113 dosyasında `kip` parametreli üç test × "acl" = 3 düğüm. Düşerse kapı KÖR.
ACL_DUGUM_SAYISI = 3


def _okunamayanlar(kok):
    kalan = []
    for kl, _dizinler, dosyalar in os.walk(kok):
        for ad in dosyalar:
            yol = os.path.join(kl, ad)
            try:
                with open(yol, "rb") as f:
                    f.read(1)
            except PermissionError:
                kalan.append(os.path.relpath(yol, kok))
    return sorted(kalan)


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL kipi (Y113 `acl` düğümleri yalnız Windows'ta koşar)")
def test_KRITIK_Y113_acl_aparati_tmpde_OKUNAMAYAN_dosya_birakmaz(tmp_path):
    bt = tmp_path / "bt"
    try:
        r = kostur(
            [
                "-m",
                "pytest",
                Y113_DOSYASI,
                "-k",
                "acl",
                "-q",
                "-p",
                "no:cacheprovider",
                "-p",
                "no:randomly",
                f"--basetemp={bt}",
            ],
            cwd=KOK,
            env=yalitik_ortam(tmp_path / "ev"),
            sure=600,
        )
        assert r.returncode == 0 and f"{ACL_DUGUM_SAYISI} passed" in r.stdout, (
            f"ön koşul: Y113 acl düğümleri koşmalı\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}"
        )
        kalan = _okunamayanlar(bt)
        assert kalan == [], f"Y113 acl aparatı tmp'de OKUNAMAYAN dosya BIRAKTI: {kalan}"
    finally:
        if bt.exists():
            subprocess.run(["icacls", str(bt), "/reset", "/T", "/C", "/Q"], capture_output=True)


@pytest.mark.skipif(os.name != "nt", reason="DACL kilidi Windows'a özgü")
def test_KARSIT_okunamayan_dosya_olcer_GERCEK_kilidi_gorur(tmp_path):
    """Araç kanıtı: ürünün kilidi uygulanmış bir dosyayı `_okunamayanlar` BULUR; izni geri alınınca bulmaz."""
    from utils.file_acl import lock_down_file

    p = tmp_path / "acl" / "auth_users.db"
    p.parent.mkdir()
    p.write_bytes(b"x")
    assert lock_down_file(p, keep_current_user=False), "ön koşul: ürün kilidi uygulanmalı"
    try:
        assert _okunamayanlar(tmp_path) == [os.path.join("acl", "auth_users.db")]
    finally:
        subprocess.run(["icacls", str(p), "/reset", "/Q"], capture_output=True)
    assert _okunamayanlar(tmp_path) == []
    assert str(KOK)
