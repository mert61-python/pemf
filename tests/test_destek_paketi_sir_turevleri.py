# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DESTEK PAKETİ SIR DOSYASI TÜREVLERİNİ ENGELLEMİYORDU (denetim 2026-08-17).

İki ayrı kusur:

**(1) Yasak-ad listesi TAM AD eşliyordu.** `pemf_secrets.json` engelliydi ama `secrets_manager`ın
GERÇEKTEN ürettiği türev adlar değildi:
  · `pemf_secrets.json.<pid>.tmp`      — atomik yazımın geçici dosyası
  · `pemf_secrets.json.corrupt.<zaman>` — karantina dosyası (bu denetimin kendi eklediği mekanizma)
Ayrıca `p.suffix` yalnız SON uzantıyı verdiği için `patients.db.plain.bak` gibi DÜZ-METİN yedekleri
de pakete giriyordu; NTFS büyük/küçük harf duyarsız olduğu hâlde `PEMF_SECRETS.JSON` de geçiyordu.
Üç gerçek sır dosyası (`api_token.txt`, `.pemf_key_v2`, `.pemf_key`) listede hiç yoktu — üçü de
`utils/file_acl` ve `backend_service` tarafından ZATEN sır kabul edilip ACL ile kilitleniyor.

**(2) Maske kalıpları kripto anahtarlarını hiç yakalamıyordu** ve — asıl kilit — anahtar adından
sonra KAPANIŞ TIRNAĞINA izin vermiyordu. Sızan dosya JSON'dur (`"sqlcipher_key": "..."`), yani
tırnaklı biçim SIFIR eşleşme veriyordu: anahtar adlarını eklemek TEK BAŞINA hiçbir işe yaramazdı.

⚠️ `api_token.txt` ÇIPLAK jeton taşır — maske kalıbı onu ASLA yakalayamaz (anahtar=değer yok).
Tek koruma dosyanın pakete HİÇ girmemesidir.

⚠️ DESTEK PAKETİNİN AMACI KORUNDU: kural "yasak kök ad + NOKTA"dır, `pemf_secrets*` glob'u DEĞİL —
ileride `pemf_secrets_rehberi.log` gibi masum bir teşhis dosyası engellenmesin. Maske alternasyonu
da DAR: `sqlcipher_key` var, `sqlcipher` YOK; sürüm/durum teşhisi maskelenmiyor.
"""

import os
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest

from utils.support_bundle import Maskeleyici, _guvenli_mi

_maskele = Maskeleyici()  # cihaza-ozgu PII listesi YOK; yalniz jenerik kaliplar sinaniyor


# ── 1) Yasak ad / türev / uzantı zinciri ─────────────────────────────────────


@pytest.mark.parametrize(
    "ad",
    [
        "pemf_secrets.json",
        "pemf_secrets.json.12345.tmp",  # atomik yazım artığı
        "pemf_secrets.json.corrupt.20260817-101500",  # karantina (bu denetimin eklediği)
        "PEMF_SECRETS.JSON",  # NTFS büyük/küçük harf duyarsız
        ".sqlcipher_key",
        ".sqlcipher_key.bak",
        "api_token.txt",  # ÇIPLAK jeton — maske asla yakalayamaz
        ".pemf_key_v2",
        ".pemf_key",
        "kurtarma-zarfi.enc",
        "server.env",
        "patients.db",
        "patients.db.plain.bak",  # uzantı ZİNCİRİ: p.suffix yalnız `.bak` görüyordu
        "treatment_history.db-wal",
    ],
)
def test_KRITIK_sir_dosyalari_ve_TUREVLERI_pakete_GIRMEZ(ad):
    assert _guvenli_mi(Path("C:/veri") / ad) is False, (
        f"{ad!r} destek paketine GIRIYOR — sir dosyasi ya da duz-metin hasta yedegi disariya cikar"
    )


@pytest.mark.parametrize(
    "ad",
    [
        "backend.log",
        "backend.log.1",
        "pemf_secrets_rehberi.log",  # ⚠️ MASUM: kural glob DEĞİL, "kök ad + NOKTA"
        "sistem_durumu.json",
        "crash_2026.txt",
        "config.json",
    ],
)
def test_KARSIT_KANIT_teshis_dosyalari_pakete_GIRMEYE_devam_eder(ad):
    """Yama "her şeyi engelle"ye dönüşmemeli — destek paketi işe yaramaz hâle gelmesin."""
    assert _guvenli_mi(Path("C:/veri") / ad) is True, f"{ad!r} gereksiz yere engellendi"


# ── 2) Maske kalıpları ───────────────────────────────────────────────────────


# ⚠️ Değerler BİLEREK düşük-entropili yer tutucular: gerçekçi görünen sahte bir sır, deponun
# gitleaks kancasını tetikleyip commit'i engelliyordu (ölçüldü). Kalıbın ölçtüğü şey DEĞERİN
# İÇERİĞİ değil, anahtar-adı + tırnak + ayraç yapısıdır; yer tutucu aynı yolu koşturur.
@pytest.mark.parametrize(
    "satir, sizan",
    [
        ('  "sqlcipher_key": "SAHTE-DEGER-AAAA",', "SAHTE-DEGER-AAAA"),
        ('  "patient_fernet_key": "SAHTE-DEGER-BBBB",', "SAHTE-DEGER-BBBB"),
        ('  "mqtt_password": "SAHTE-DEGER-CCCC",', "SAHTE-DEGER-CCCC"),
        ("mqtt_pass=SAHTE-DEGER-CCCC", "SAHTE-DEGER-CCCC"),
        ('  "reset_code": "SAHTE-DEGER-DDDD",', "SAHTE-DEGER-DDDD"),
        ('  "recovery_code": "SAHTE-DEGER-EEEE",', "SAHTE-DEGER-EEEE"),
    ],
)
def test_KRITIK_kripto_anahtarlari_JSON_bicimde_de_MASKELENIR(satir, sizan):
    """⚠️ ASIL KİLİT TIRNAK: sızan dosya JSON'dur. Anahtar adından sonra kapanış tırnağına izin
    verilmezse kalıp hiç eşleşmez ve anahtar adlarını eklemek TEK BAŞINA işe yaramaz."""
    cikti = _maskele(satir)
    assert sizan not in cikti, f"gizli deger MASKELENMEDI: {cikti!r}"
    assert "MASKELENDI" in cikti


@pytest.mark.parametrize(
    "satir",
    [
        # ⚠️ DEĞER ≥4 KARAKTER OLMALI: kalıp `{4,}` istiyor; kısa değerli bir satır, alternasyonu
        # `sqlcipher`/`fernet`e genişleten bir mutasyonu AYIRT EDEMEZDİ (ölçüldü — sessizce geçti).
        "sqlcipher: kurulu-degil-surum-3.4.5",
        "fernet: modul-yuklendi-tamam",
        "at_rest_encrypted=false",
        "coil_id=3 duty=25 freq=50",
    ],
)
def test_KARSIT_KANIT_teshis_satirlari_MASKELENMEZ(satir):
    """DAR alternasyon: `sqlcipher_key` yakalanır, `sqlcipher` YAKALANMAZ — teşhis ölmemeli."""
    assert _maskele(satir) == satir, f"teshis satiri gereksiz yere maskelendi: {_maskele(satir)!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
