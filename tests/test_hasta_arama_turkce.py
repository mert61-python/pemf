# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TÜRKÇE HASTA ARAMA — saha bulgusu 2026-08-30 (Supabase/denetim turu, "olası bugları kapat").

KANITLANAN ARIZA: hasta arama indeksi `str.lower()` ile normalize ediliyordu. Python varsayılanı
Türkçe'de yanlıştır:
    'İ'.lower() → 'i̇'  (i + U+0307 BİRLEŞİK NOKTA, İKİ karakter)
    'I'.lower() → 'i'   (oysa Türkçe'de 'ı' beklenir)

Sonuç ölçüldü (uçtan uca, aşağıda): "İhsan" kaydedip "ihsan" ya da "isik" arayan Türk doktor
hastayı BULAMIYORDU. Tıbbi kayıtta bu = erişilemeyen hasta ya da mükerrer kayıt.

DÜZELTME: `_normalize_search_value` Türkçe harfleri ASCII'ye KATLIYOR (İ/I/ı/i→i, ş→s, ğ→g,
ç→c, ö→o, ü→u) + NFKD ile kalan aksanları atıyor. Görüntülenen ad DEĞİŞMEZ; yalnız arama token'ı
katlanır. `_SEARCH_NORM_VERSION` parmak-izine dahil → sahadaki indeks açılışta otomatik yeniden
kurulur.

⚠️ Bu test GERÇEK `PatientDatabase` ile uçtan uca çalışır (kaydet → ara → bul). İzole tmp DB
kullanır; gerçek klinik verisine DOKUNMAZ.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def hasta_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def _adlar(sonuc):
    return {p.get("name") for p in (sonuc or [])}


# ── Uçtan uca: kaydet → ara → bul ───────────────────────────────────────────


@pytest.mark.parametrize(
    "kayit_adi,aramalar",
    [
        # İ/I bug'ı: 'İ'.lower() birleşik nokta, 'I'.lower() 'i' — bunlar DÜZELMELİ.
        ("İhsan", ["ihsan", "İhsan", "İHSAN"]),  # noktalı İ ↔ küçük i (eskiden bulunamıyordu)
        ("İpek", ["ipek", "İpek", "İPEK"]),
        ("Işık", ["ışık", "IŞIK", "Işık"]),  # noktasız I → ı (Türkçe-doğru, kendisiyle eşleşir)
        ("Gökçe", ["gökçe", "GÖKÇE", "Gökçe"]),  # aksan KORUNUR ama kendisini bulur
        ("Çağla Öz", ["çağla", "ÇAĞLA öz", "çağla öz"]),
    ],
)
def test_KRITIK_turkce_ad_kaydet_ARA_BUL(hasta_db, kayit_adi, aramalar):
    """⚠️ Her Türkçe-doğru arama biçimi kaydı BULMALI — eskiden `str.lower()` İ/I'yı bozuyordu.

    ⚠️ AKSAN ASCII'ye KATLANMAZ (mobil ile hizalı): "Gökçe" araması "gökçe" ile bulunur ama
    "gokce" ile DEĞİL (bkz. karşıt-kanıt). ı/i de ayrı harflerdir."""
    hasta_db.add_patient({"name": kayit_adi, "owner": "Test", "species": "Kedi"})
    for terim in aramalar:
        bulunan = _adlar(hasta_db.search_patients(terim))
        assert kayit_adi in bulunan, (
            f"'{kayit_adi}' kaydı '{terim}' aramasıyla BULUNAMADI "
            f"→ Türk doktor hastasına ulaşamaz (bulunanlar: {bulunan or 'HİÇBİRİ'})"
        )


# ── Karşıt-kanıt: katlama AŞIRI GENİŞ olmamalı ──────────────────────────────


def test_KARSIT_farkli_hastalar_KARISMAZ(hasta_db):
    """Farklı adlar birbirini çekmemeli."""
    for ad in ("Ahmet", "Mehmet", "Zeynep", "Zehra"):
        hasta_db.add_patient({"name": ad, "owner": "T", "species": "Kedi"})

    ahmet = _adlar(hasta_db.search_patients("ahmet"))
    assert "Ahmet" in ahmet, "kendi kaydını bulamadı"
    assert "Mehmet" not in ahmet, "'ahmet' araması 'Mehmet'i getirdi"

    zeynep = _adlar(hasta_db.search_patients("zeynep"))
    assert "Zeynep" in zeynep and "Zehra" not in zeynep, "Zeynep/Zehra karıştı"


def test_KRITIK_AKSAN_KORUNUR_mobil_ile_hizali(hasta_db):
    """⚠️ HASTA-KİMLİĞİ GÜVENLİĞİ — mobil `aramaNormalize.ts` ile birebir aynı karar.

    Aksanı ASCII'ye katlamak "Şirin" ile "Sirin"i, "Gökçe" ile "Gokce"yi birleştirir; bir
    hasta-kimliği ekranında bu YANLIŞ KAYDA bakma riskidir. İlk düzeltme (2026-08-30) aksanı
    katlıyordu; mobil ekibin daha önce ölçtüğü kararla hizalanarak geri alındı. ı/i de AYRI."""
    for ad in ("Şirin", "Sirin", "Gökçe", "Gokce", "Işık", "Isik"):
        hasta_db.add_patient({"name": ad, "owner": "T", "species": "Kedi"})

    sirin = _adlar(hasta_db.search_patients("sirin"))
    assert "Sirin" in sirin, "ASCII 'Sirin' kendini bulmalı"
    assert "Şirin" not in sirin, "'sirin' araması 'Şirin'i getirdi → yanlış-hasta riski (aksan katlandı)"

    gokce = _adlar(hasta_db.search_patients("gokce"))
    assert "Gökçe" not in gokce, "'gokce' araması 'Gökçe'yi getirdi → aksan katlanmamalı"

    # ı/i ayrı harf: "isik" araması "Işık"ı (→ ışık) getirmemeli
    isik = _adlar(hasta_db.search_patients("isik"))
    assert "Işık" not in isik, "'isik' araması 'Işık'ı getirdi → ı/i birleşti (Türkçe'de ayrı)"


# ── Normalize sözleşmesi (birim) ────────────────────────────────────────────


def test_KRITIK_normalize_birlesik_nokta_URETMEZ(hasta_db):
    """⚠️ Bug'ın kökü: `str.lower()` 'İ' için birleşik nokta (U+0307) üretiyordu.

    Normalize çıktısı ASCII-güvenli olmalı; birleşik işaret İÇERMEMELİ."""
    import unicodedata

    for giris in ("İhsan", "IŞIK", "Çağla", "Ğöl"):
        cikti = hasta_db._normalize_search_value(giris)
        assert not any(unicodedata.combining(c) for c in cikti), (
            f"'{giris}' → '{cikti}' birleşik işaret içeriyor → arama eşleşmesi bozulur"
        )
        assert cikti == cikti.lower(), "çıktı tam düşürülmemiş"


# ── Ortak kaynak: iki yüzey de aynı katlamayı kullanmalı ────────────────────


def test_KRITIK_arama_ve_PDF_AYNI_katlamayi_kullaniyor():
    """⚠️ 'AYNI BUG BAŞKA YERDE' KORUMASI. Türkçe collation tuzağı iki yüzeyde vardı: hasta
    arama indeksi VE PDF rapor filtresi. İkisi ayrı `str.lower()` kullanırsa biri düzeltilip
    diğeri unutulur. Her ikisi de `utils.turkce_metin.arama_katla`ya bağlanmalı."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    for dosya in ("database/patient_database.py", "utils/pdf_report_generator.py"):
        src = (kok / dosya).read_text(encoding="utf-8")
        assert "arama_katla" in src, f"{dosya}: ortak Türkçe katlamayı kullanmıyor"

    # PDF filtresi artık ham `.lower()` ile hasta adı karşılaştırmamalı.
    pdf = (kok / "utils/pdf_report_generator.py").read_text(encoding="utf-8")
    i = pdf.find("patient_sessions = [")
    govde = pdf[max(0, i - 400) : i + 400]
    assert "arama_katla" in govde, "PDF hasta filtresi ortak katlamayı kullanmıyor"


def test_util_arama_katla_dogrudan():
    """Ortak util: İ/I düzelir; aksan ve ı/i KORUNUR (mobil aramaNormalize.ts ile aynı)."""
    from utils.turkce_metin import arama_katla

    # İ/I bug'ı düzelir
    assert arama_katla("İhsan") == arama_katla("ihsan") == arama_katla("İHSAN")
    assert arama_katla("İpek") == arama_katla("ipek")
    # ⚠️ Aksan KATLANMAZ (hasta-kimliği güvenliği)
    assert arama_katla("Şirin") != arama_katla("Sirin"), "aksan katlandı → yanlış-hasta riski"
    assert arama_katla("Gökçe") != arama_katla("gokce")
    # ⚠️ ı ve i AYRI harf
    assert arama_katla("Işık") != arama_katla("isik")
    # Farklı adlar
    assert arama_katla("Ahmet") != arama_katla("Mehmet")
    # Birleşik nokta üretilmemeli (bug'ın kökü)
    import unicodedata

    assert not any(unicodedata.combining(c) for c in arama_katla("İ"))


def test_KRITIK_backend_mobil_AYNI_kural(hasta_db):
    """⚠️ İKİ UÇ PARİTESİ: mobil client-side süzme (aramaNormalize.ts) ile backend arama indeksi
    AYNI hastayı AYNI terimle aynı bulmalı. Mobilin `aramaNormalize.test.ts`te kilitlediği
    vakaların backend'de de aynı sonucu vermesi, "aynı hasta iki cihazda farklı bulunuyor"
    sınıfını kapatır."""
    from utils.turkce_metin import arama_katla

    def mobil_eslesir(metin, sorgu):
        # aramaNormalize.ts::aramaEslesir'in Python ikizi (aynı token, includes).
        return arama_katla(sorgu).strip() == "" or arama_katla(sorgu).strip() in arama_katla(metin)

    # aramaNormalize.test.ts satır 52-60'ın birebir karşılığı:
    assert mobil_eslesir("İpek", "ipek") is True
    assert mobil_eslesir("Işık", "ışık") is True
    assert mobil_eslesir("İpek", "pamuk") is False
    assert mobil_eslesir("Şirin", "sirin") is False  # aksan korunur
    assert mobil_eslesir("Gökçe", "gokce") is False


def test_norm_surumu_parmak_izinde():
    """⚠️ Normalize değişikliği sahadaki indeksi otomatik tazelemeli.

    Sürüm parmak-izine katılmazsa, düzeltme yayınlansa bile MEVCUT hastalar eski (bozuk)
    indeksle kalır ve Türkçe arama onlarda çalışmaz."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "database" / "patient_database.py").read_text(encoding="utf-8")
    assert "_SEARCH_NORM_VERSION" in src, "normalize sürümü tanımlı değil"
    i = src.find("_fp = hashlib.sha256(")
    assert i != -1
    govde = src[i : i + 220]
    assert "_SEARCH_NORM_VERSION" in govde or "norm" in govde, (
        "normalize sürümü parmak-izine katılmıyor → mevcut hastalarda indeks tazelenmez"
    )
