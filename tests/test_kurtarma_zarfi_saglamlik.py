# Author: mertaygn, cglrgrkn
"""KURTARMA ZARFI — sağlamlık `.exists()` ile ölçülemez; BOZUK zarf onarılmalı.

DENETİM BULGUSU (2026-08-17). `utils/backup_recovery.refresh_recovery_material` şu kapıyı
kullanıyordu:

    missing = [d for d in dests if not (d / ENVELOPE_NAME).exists()]
    if unchanged and not missing:
        return True

`_fingerprint` yalnız `code` + `keys`'in fonksiyonudur (yedek içeriğinden bağımsız), anahtarlar da
sabit olduğu için `unchanged` sonsuza dek `True`. Dolayısıyla zarf bir kez **bozulursa** (yazım
sırasında güç kesintisi / kısa dosya) dosya VAR olduğu için `missing` boş kalır ve zarf **BİR DAHA
ASLA yeniden yazılmaz.** Ölçüldü: bozuk zarf 5 tur boyunca onarılmadı ve fonksiyon her turda `True`
döndü.

Sonuç: anakart/disk arızasından sonra `open_envelope` → "Zarf okunamadi (bozuk dosya?)" →
şifreli yedeklerin **tek off-machine anahtar escrow'u** okunamaz (`docs/RUNBOOK.md`:
`pemf_secrets.json` DPAPI ile makineye bağlı, `utils/support_bundle.py` zarfı bilerek dışlıyor).
Asıl sivri uç kaybın kendisi değil **sessizliği**: hiçbir log/health "zarfım bozuk" demiyor, tersine
`services/headless_db_maintenance._copy_offsite` kararını yalnız `.exists()`'ten verip
*"Kurtarma zarfi yerinde → KURTARMA KODU ile baska makinede geri yuklenebilir"* diye YANLIŞ GÜVENCE
logluyor.

⚠️ "DEĞİŞMEDİYSE YENİDEN YAZMA" KASITLI ve testle kilitli (`tests/test_backup_recovery.py`:
*"Operatörün doğruladığı zarf her gün değişip şüphe uyandırmasın."*) — bu davranış KORUNUR.
Değişen tek şey: "var mı?" yerine "GERÇEKTEN AÇILIYOR MU?" sorulması.

⚠️ `write_bytes` atomik değildi; aynı yazar `utils/secrets_manager._save`'de tmp+fsync+replace
kullanıp yorumda NTFS yarım-dosya tehlikesini açıkça anlatıyor. Bu da düzeltiliyor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def br(monkeypatch):
    """Gerçek modül; at-rest anahtarı ve kurtarma kodu sahte ama GERÇEKÇİ."""
    from utils import backup_recovery as _br

    monkeypatch.setattr(_br, "_collect_keys", lambda: {"sqlcipher_key": "TEST-SQLCIPHER-ANAHTARI"})
    monkeypatch.setattr(_br, "get_or_create_code", lambda: "TEST-KURTARMA-KODU-1234")
    return _br


def test_KRITIK_BOZUK_zarf_sonraki_turda_ONARILIR(br, tmp_path):
    """Bozuk zarf, sonraki bakım turunda yeniden yazılmalı — sonsuza dek bozuk kalmamalı."""
    veri = tmp_path / "veri"
    hedef = tmp_path / "yedek"
    veri.mkdir()
    hedef.mkdir()

    assert br.refresh_recovery_material(veri, [hedef]) is True, "on-kosul: ilk zarf yazilmali"
    zarf = hedef / br.ENVELOPE_NAME
    saglam_boyut = zarf.stat().st_size
    assert saglam_boyut > 0

    # Yazım sırasında güç kesintisinin diskteki SONUCU: kırpılmış zarf.
    zarf.write_bytes(zarf.read_bytes()[:20])
    with pytest.raises(Exception):
        br.open_envelope("TEST-KURTARMA-KODU-1234", zarf.read_bytes())

    br.refresh_recovery_material(veri, [hedef])

    icerik = zarf.read_bytes()
    assert br.open_envelope("TEST-KURTARMA-KODU-1234", icerik), (
        "bozuk zarf ONARILMADI → felaket kurtarmanin tek off-machine anahtar escrow'u okunamaz "
        "kalir ve hicbir yerde uyari cikmaz (log tersine 'kurtarilabilir' der)."
    )


def test_SAGLAM_zarf_HER_TUR_yeniden_YAZILMAZ_karsit_kanit(br, tmp_path):
    """Karşı-kanıt: kasıtlı davranış korunmalı — sağlam zarf her gün değişmemeli.

    `tests/test_backup_recovery.py` bunu zaten kilitliyor ("operatörün doğruladığı zarf her gün
    değişip şüphe uyandırmasın"); burada düzeltmenin onu BOZMADIĞINI doğruluyoruz."""
    veri = tmp_path / "veri"
    hedef = tmp_path / "yedek"
    veri.mkdir()
    hedef.mkdir()

    assert br.refresh_recovery_material(veri, [hedef]) is True
    zarf = hedef / br.ENVELOPE_NAME
    once = zarf.read_bytes()
    mtime_once = zarf.stat().st_mtime_ns

    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert zarf.read_bytes() == once, "saglam zarf yeniden yazildi (icerik degisti)"
    assert zarf.stat().st_mtime_ns == mtime_once, "saglam zarf yeniden yazildi (mtime degisti)"


def test_EKSIK_zarf_hala_tamamlanir_karsit_kanit(br, tmp_path):
    """Karşı-kanıt: eksik zarfın tamamlanması davranışı korunmalı."""
    veri = tmp_path / "veri"
    hedef = tmp_path / "yedek"
    veri.mkdir()
    hedef.mkdir()

    assert br.refresh_recovery_material(veri, [hedef]) is True
    (hedef / br.ENVELOPE_NAME).unlink()

    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert (hedef / br.ENVELOPE_NAME).exists(), "eksik zarf tamamlanmadi"


def test_zarf_yazimi_ATOMIK_yarim_dosya_birakmaz(br, tmp_path):
    """Yazım ortasında çökme yarım bir zarf BIRAKMAMALI (tmp + replace deseni).

    Aynı depoda `utils/secrets_manager._save` bu deseni kullanıp yorumda NTFS yarım-dosya
    tehlikesini açıkça anlatıyor; felaket kurtarmanın tek dayanağı olan dosya o korumadan yoksundu."""
    veri = tmp_path / "veri"
    hedef = tmp_path / "yedek"
    veri.mkdir()
    hedef.mkdir()

    gercek_replace = __import__("os").replace
    patladi = {"oldu": False}

    def _replace_patlat(src, dst):
        patladi["oldu"] = True
        raise OSError("guc kesintisi (taklit)")

    import os as _os

    monkey = pytest.MonkeyPatch()
    monkey.setattr(_os, "replace", _replace_patlat)
    try:
        br.refresh_recovery_material(veri, [hedef])
    finally:
        monkey.undo()

    assert patladi["oldu"], (
        "zarf yazimi `os.replace` KULLANMIYOR → atomik degil, yarim dosya diskte kalabilir "
        "(ve `.exists()` onu 'saglam' sayar)."
    )
    zarf = hedef / br.ENVELOPE_NAME
    assert not zarf.exists(), "atomik-olmayan yazim yarim/bozuk zarf birakti"
    assert gercek_replace is _os.replace, "monkeypatch geri alinmadi"


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
