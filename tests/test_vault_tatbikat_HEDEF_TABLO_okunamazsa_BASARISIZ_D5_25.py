# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.25 (B-10.102) — `vault_emanet.py --tatbikat`: emanet anahtarıyla AÇILAN veritabanında hedef tablo SAYILAMAZSA tatbikat BAŞARISIZ.

ÖLÇÜLEN KUSUR: `tatbikat()` hedef tablo (`patients` / `treatment_sessions`) sayımı hata verirse satırı "HATA" yazıp durumu yine
"ACILDI" sayıyordu → yanlış / boş / bozuk dosyada da "TATBIKAT BASARILI — emanet gercekten kurtariyor" + çıkış 0.
Yardımcı kollar (plan V1 / V2): karşıt kanıt (yanlış anahtar reddi) KARARA girer — anahtarı yok sayan bir bağlama BAŞARISIZ;
tatbikat gerçek veri kökündeki dosyayı DEĞİL geçici KOPYASINI açar.

Aparat (D2.E05 ile aynı): betiğin KENDİ `main()`i, loopback rastgele portta SAHTE Vault, sentetik veri kökü (klon TEMP'i) ve sentetik
anahtarlı GERÇEK SQLCipher veritabanları. Gerçek `~/pemf-vault-kurtarma.json`, gerçek kök ve kasa okunmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sahte_vault_sunucusu import sentetik_veri_koku
from test_vault_emanet_KUR_rc_ve_TATBIKAT_kurtarma_tokeni_D2E05 import (  # noqa: F401  (fikstür)
    KURTARMA,
    ON_YIL_SN,
    SQL_ANAHTARI,
    _kos,
    _sqlcipher,
    _vault,
    ortam,
)

pytestmark = pytest.mark.skipif(_sqlcipher() is None, reason="sqlcipher3 yok — tatbikat zinciri ölçülemez")


def _yalniz_baska_tablo(veri: Path, ad: str) -> None:
    """`ad` dosyasını emanet anahtarıyla şifreli ama hedef tablosu OLMAYAN (yalnız `baska_tablo`) bir DB ile değiştir."""
    from database.sqlcipher_util import open_encrypted_conn

    (veri / ad).unlink()
    c = open_encrypted_conn(veri / ad, SQL_ANAHTARI, _sqlcipher())
    try:
        c.execute("CREATE TABLE baska_tablo (id INTEGER PRIMARY KEY)")
        c.commit()
    finally:
        c.close()


@pytest.mark.parametrize("ad", ["patients.db", "pemf_treatment_history.db"])
def test_KRITIK_D5_25_hedef_tablo_SAYILAMAZSA_tatbikat_BASARISIZ(ortam, monkeypatch, capsys, ad):
    ve, tmp = ortam
    veri = sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    _yalniz_baska_tablo(veri, ad)
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", KURTARMA)
    assert "TATBIKAT BASARISIZ" in cikti and rc != 0, (
        f"{ad}: hedef tablo okunamadı ama tatbikat BASARILI / çıkış {rc} — emanetin kurtardığı KANITLANMADI\n{cikti[-700:]}"
    )
    assert "HEDEF TABLO OKUNAMADI" in cikti, f"neden satırı (hedef tablo okunamadı) basılmadı: {cikti[-700:]}"


def test_KRITIK_D5_25_V1_anahtari_YOK_SAYAN_baglama_ile_tatbikat_BASARISIZ(ortam, monkeypatch, capsys):
    """Karşıt kanıt karara girer: bağlama anahtarı yok sayıp her anahtarla açıyorsa (yanlış anahtar REDDEDİLMEZ) BAŞARILI denmez."""
    import database.sqlcipher_util as su

    ve, tmp = ortam
    sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    gercek = su.open_encrypted_conn
    monkeypatch.setattr(su, "open_encrypted_conn", lambda yol, _anahtar, mod: gercek(yol, SQL_ANAHTARI, mod))
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", KURTARMA)
    assert "YANLIS ANAHTARLA ACILDI" in cikti, f"aparat: karşıt kanıt koşmadı: {cikti[-600:]}"
    assert "TATBIKAT BASARISIZ" in cikti and rc != 0, (
        f"yanlış anahtar reddedilmedi ama tatbikat BASARILI:\n{cikti[-600:]}"
    )


def test_KRITIK_D5_25_V2_tatbikat_GERCEK_dosyayi_degil_KOPYAYI_acar(ortam, monkeypatch, capsys):
    import database.sqlcipher_util as su

    ve, tmp = ortam
    veri = sentetik_veri_koku(tmp / "veri", SQL_ANAHTARI, Fernet.generate_key().decode())
    acilan: list[Path] = []
    gercek = su.open_encrypted_conn

    def _kaydeden(yol, anahtar, mod):
        acilan.append(Path(yol).resolve())
        return gercek(yol, anahtar, mod)

    monkeypatch.setattr(su, "open_encrypted_conn", _kaydeden)
    with _vault(kurtarma_ttl=ON_YIL_SN) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", KURTARMA)
    assert rc == 0 and "TATBIKAT BASARILI" in cikti, cikti[-600:]
    assert len(acilan) >= 3, f"aparat: açma çağrısı sayısı beklenenden az: {acilan}"
    gercek_kok = veri.resolve()
    dokunulan = [y for y in acilan if gercek_kok in y.parents]
    assert not dokunulan, f"tatbikat GERÇEK veri kökündeki dosyayı açtı (kopya değil): {dokunulan}"
