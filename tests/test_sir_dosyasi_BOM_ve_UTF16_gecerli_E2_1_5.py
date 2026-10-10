# -*- coding: utf-8 -*-
"""E2-1.5 (2-E incelemesi, A1) — GEÇERLİ ama BOM'lu (UTF-8-sig) ya da UTF-16 yazılmış `pemf_secrets.json` "BOZUK" sayılıp
`.corrupt.<zaman>` adına KENARA ALINIR; sonraki her açılış "karantina kanıtı var" ile DB'siz kalır.

D2.80 okuma İZNİ hatasını bozuk dalından ayırdı ama içerik çözümü `_ham.decode("utf-8")` kaldı (secrets_manager.py:652). Ürünün
kendi emanet geri yükleme yönergeleri operatöre bu dosyayı ELLE düzenletir (`scripts/hasta_anahtari_emanet.py:250-252`,
`scripts/vault_emanet.py:276-279, 478-480`: "<veri_koku>/pemf_secrets.json -> auto.<alan> alanlarına DÜZ METİN yazın"). Windows
PowerShell 5.1 `Set-Content -Encoding UTF8` BOM'lu, `Out-File`/`>` UTF-16LE yazar; eski Notepad "UTF-8" = BOM'lu. Geri yüklenen
anahtar(lar)ı taşıyan GEÇERLİ dosya karantinaya gider; ileti "yedekten geri yükleyin" ya da (karantina kanıtı dalında) "(2) kalıcı
kaybı KABUL ediyorsanız karantina dosyalarını kaldırın; cihaz temiz anahtarlarla açılır" der — felaket günü yanlış yola iter.

Zincir: GERÇEK `get_secret(..., generate=False)` → GERÇEK `_load` → gerçek disk. Değerler sentetik (SAHTE-…), yazdırılmaz.
"""

from __future__ import annotations

import json

import pytest

_DOC = {
    "_comment": "elle geri yukleme (emanet yonergesi)",
    "_version": 1,
    "auto": {"patient_fernet_key": "SAHTE-FERNET-E215", "sqlcipher_key": "e215-sql"},
    "operator": {},
    "embedded": {},
}
_METIN = json.dumps(_DOC, ensure_ascii=False, indent=2)


@pytest.fixture()
def sm(tmp_path, monkeypatch):
    from utils import secrets_manager as _sm

    veri = tmp_path / "PEMF_GUI"
    veri.mkdir()
    monkeypatch.setattr(_sm, "_data_dir", lambda: veri)
    monkeypatch.setattr(_sm, "_cache", None)
    monkeypatch.setattr(_sm, "_dir_hardened", True)
    monkeypatch.setattr(_sm, "_tekrar_gunluk", {})
    return _sm, veri / "pemf_secrets.json"


@pytest.mark.parametrize(
    "bicim,bayt",
    [
        ("UTF8_BOM", b"\xef\xbb\xbf" + _METIN.encode("utf-8")),  # PS 5.1 Set-Content -Encoding UTF8 / eski Notepad
        ("UTF16LE_BOM", _METIN.encode("utf-16")),  # PS 5.1 Out-File / '>' yönlendirmesi
    ],
    ids=["UTF8_BOM", "UTF16LE_BOM"],
)
def test_KRITIK_elle_geri_yuklenen_GECERLI_sir_dosyasi_KARANTINAYA_alinmaz_anahtar_okunur_E2_1_5(sm, bicim, bayt):
    _sm, p = sm
    p.write_bytes(bayt)
    try:
        deger = _sm.get_secret("patient_fernet_key", generate=False)
    except Exception as e:  # noqa: BLE001
        deger = f"<{type(e).__name__}>"
    karantina = [q.name for q in p.parent.glob("pemf_secrets.json.corrupt.*")]
    assert not karantina, f"[{bicim}] GEÇERLİ sır dosyası BOZUK sayılıp kenara alındı: {karantina}"
    assert p.exists(), f"[{bicim}] sır dosyası yerinde değil"
    assert deger == "SAHTE-FERNET-E215", (
        f"[{bicim}] elle geri yüklenen anahtar okunamadı: {deger if deger.startswith('<') else 'FARKLI DEGER'}"
    )


_ANSI = json.dumps({**_DOC, "operator": {"tunnel_hostname": "SAHTE-ÇAĞRI-ŞİŞLİ"}}, ensure_ascii=False).encode("cp1254")


@pytest.mark.parametrize(
    "bicim,bayt",
    [("yarida_kesik", _METIN.encode("utf-8")[:40]), ("bos", b""), ("ANSI_cp1254_turkce", _ANSI)],
    ids=[
        "kesik",
        "bos",
        "ANSI_cp1254",
    ],  # ANSI: hoşgörülü çözüm Türkçe harfleri SESSİZCE düşürüp bozuk değer yüklememeli
)
def test_KARSIT_gercekten_bozuk_dosya_hala_KARANTINAYA_yeni_anahtar_YOK_E2_1_5(sm, bicim, bayt):
    _sm, p = sm
    p.write_bytes(bayt)
    with pytest.raises(RuntimeError):
        _sm.get_secret("patient_fernet_key")  # generate=True: yine de ÜRETMEMELİ
    assert [q.name for q in p.parent.glob("pemf_secrets.json.corrupt.*")], f"[{bicim}] bozuk dosya karantinaya alınmadı"
    assert not p.exists(), f"[{bicim}] bozuk dosyanın yerine yeni dosya yazıldı (yeni anahtar üretildi?)"
