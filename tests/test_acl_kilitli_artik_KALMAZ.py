# Author: mertaygn, cglrgrkn
"""1-B (iii) · 1-A açık madde 13 — emanet testleri pytest tmp'sinde ACL-KİLİTLİ düz-metin yedek BIRAKMAZ.

ÖLÇÜLEN (2026-10-01, ayrı geçici kökte iki emanet dosyası koşuldu): `test_escrow_ISTENIRSE_hala_saklanir`
`pemf_treatment_history.db.plain.bak` bırakıyordu — DACL yalnız SYSTEM + Administrators (ürünün
`lock_down_file` sertleştirmesi): kullanıcı OKUYAMAZ, PowerShell `Remove-Item -Recurse -Force` dizini SİLEMEZ
(1-A oturum sonu temizliği bu yüzden `icacls /reset` istedi); `test_KARSIT_KANIT_ACL_TUTARSA_…` da bir `.plain.bak`
bırakıyordu. (Üst dizin kullanıcıya tam yetki verdiği için `os.unlink`/pytest `rm_rf` siler — "rotasyon kilitlenir"
öncülü ölçümde DOĞRULANMADI; bkz. `acl_artik_temizligi.py`.)

Kapı DAVRANIŞLA ölçer: gerçek emanet testleri ALT SÜREÇTE (`--basetemp` bu testin tmp'sinde, yalıtık ortam;
çocukta süitin ağ bekçisi conftest ile kurulur) koşulur, sonra o kökte `*.plain.bak*` aranır.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from acl_artik_temizligi import acl_kilitli_artiklari_temizle
from betik_alt_sureci import KOK, kostur, yalitik_ortam

EMANET_TESTLERI = [
    "tests/test_at_rest_encryption_rollout.py::test_escrow_ISTENIRSE_hala_saklanir",
    # D2.08: bu test sahte/gerçek bağlayıcıyla PARAMETRELİ — önek iki düğümü de seçer, ikisi de koşmalı.
    "tests/test_escrow_acl_dusunce_fail_closed.py::test_KARSIT_KANIT_ACL_TUTARSA_emanet_GERCEKTEN_saklanir",
]
# 1 + 2 (parametreli). Düğüm düşerse/atlanırsa (bir bağlayıcı değişkeni toplanmadı) kapı KÖR sayılır.
EMANET_DUGUM_SAYISI = 3


def test_KRITIK_emanet_testleri_tmpde_DUZ_METIN_YEDEK_birakmaz(tmp_path):
    bt = tmp_path / "bt"
    r = kostur(
        ["-m", "pytest", *EMANET_TESTLERI, "-q", "-p", "no:cacheprovider", "-p", "no:randomly", f"--basetemp={bt}"],
        cwd=KOK,
        env=yalitik_ortam(tmp_path / "ev"),
    )
    assert r.returncode == 0 and f"{EMANET_DUGUM_SAYISI} passed" in r.stdout, (
        f"ön koşul: emanet testleri koşmalı\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}"
    )
    kalan = sorted(str(p.relative_to(bt)) for p in bt.rglob("*.plain.bak*"))
    assert kalan == [], f"emanet testleri tmp'de düz-metin yedek BIRAKTI: {kalan}"


@pytest.mark.skipif(os.name != "nt", reason="DACL kilidi Windows'a özgü (POSIX'te 0o600 — sahibi siler)")
def test_KRITIK_yardimci_URUNUN_kilitledigi_yedegi_siler(tmp_path):
    from utils.file_acl import lock_down_file

    p = tmp_path / "PEMF_GUI" / "x.db.plain.bak"
    p.parent.mkdir()
    p.write_bytes(b"duz metin")
    assert lock_down_file(p), "ön koşul: ürün kilidi uygulanmalı"
    with pytest.raises(PermissionError):
        p.read_bytes()  # ön koşul: kilit GERÇEK — kullanıcı dosyayı okuyamıyor
    assert acl_kilitli_artiklari_temizle(tmp_path) == []
    assert not p.exists()


def test_KARSIT_yardimci_desen_DISINA_dokunmaz(tmp_path):
    korunan = [tmp_path / "pemf_treatment_history.db", tmp_path / "a" / "notlar.txt", tmp_path / "a" / "x.db.bak"]
    for k in korunan:
        k.parent.mkdir(parents=True, exist_ok=True)
        k.write_text("k", encoding="utf-8")
    (tmp_path / "a" / "y.db.plain.bak.20261001").write_text("eski", encoding="utf-8")
    assert acl_kilitli_artiklari_temizle(tmp_path) == []
    assert all(k.exists() for k in korunan), "desen dışındaki dosya silindi"
    assert not (tmp_path / "a" / "y.db.plain.bak.20261001").exists(), "kenara alınmış yedek de aynı sınıf"


def test_KARSIT_yardimci_YALNIZ_verilen_koke_bakar(tmp_path):
    dis = tmp_path / "dis.db.plain.bak"
    dis.write_text("d", encoding="utf-8")
    ic = tmp_path / "ic"
    ic.mkdir()
    assert acl_kilitli_artiklari_temizle(ic) == []
    assert dis.exists(), "verilen kökün DIŞINDAKİ dosya silindi"
    dis.unlink()
    assert Path(KOK).is_dir()
