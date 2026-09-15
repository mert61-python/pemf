# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI ANALİZİ ↔ HASTA KİMLİĞİ BAĞI — ad bazlı eşlemeden kimliğe taşıma (2026-09-12).

===============================================================================
NEDEN
===============================================================================
`ai_analyses` hastaya YALNIZ ADLA bağlıydı. Üç ayrı kırılganlığı vardı:

  1) AYNI ADLI İKİ HAYVAN: "Mia" adlı iki kedinin analizleri KARIŞIYORDU.
  2) AD DEĞİŞİKLİĞİ: hasta kaydında ad düzeltilince eski analizler KOPUYORDU.
  3) PII MASKELEMESİ: `PEMF_MASK_HISTORY_PII=1` açıkken ad `[SIFRELENMEMIS-DB]` yazılır →
     TÜM analizler aynı "ada" düşer ve eşleme BÜTÜNÜYLE çöker.

`patient_uuid` PII DEĞİLDİR (opak kimlik) → maskelenmez, şifrelemeden bağımsız çalışır.

===============================================================================
TAŞIMANIN ASIL KURALI — BELİRSİZ ADI TAHMİN ETME
===============================================================================
Geri doldurma YALNIZ adı TEK BİR hastaya çözülen kayıtlara kimlik yazar. Aynı ada sahip
iki hayvan varsa o kayıtlar KİMLİKSİZ kalır ve eskisi gibi ada bağlı çalışır.

Yanlış kimlik yazmak, taşımanın çözmeye çalıştığı sorunu KALICI hâle getirirdi: bir
hayvanın analizi başka bir hayvanın kaydına gömülür ve ad belirsizliğinin aksine bu
GERİ ALINAMAZDI (ad hâlâ orada ama kimlik artık "kesin" görünür).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")

_PF = KOK / "pf" / "src"


@pytest.fixture
def db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB

    kok = tmp_path / "ai_kimlik"
    kok.mkdir(parents=True, exist_ok=True)
    return TreatmentHistoryDB(kok)


# ============================================================================
# 1. ⚠️ ASIL KAPI — AYNI ADLI İKİ HAYVAN AYRIŞIR
# ============================================================================


def test_KRITIK_AYNI_ADLI_iki_hayvan_KARISMAZ(db):
    """Ada göre süzme ikisini de getirirdi; kimliğe göre süzme AYIRIR.

    MUTASYON: `get_ai_analyses`taki `patient_uuid = ?` koşulunu sil → KIRMIZI.
    """
    db.add_ai_analysis(module_id="m", patient_name="Mia", patient_uuid="kedi-A", result_summary="A")
    db.add_ai_analysis(module_id="m", patient_name="Mia", patient_uuid="kedi-B", result_summary="B")

    a = db.get_ai_analyses(patient_uuid="kedi-A")
    assert [k["result_summary"] for k in a] == ["A"], f"kimlik suzgeci AYIRMADI: {a}"
    b = db.get_ai_analyses(patient_uuid="kedi-B")
    assert [k["result_summary"] for k in b] == ["B"]
    # ⚠️ KARŞIT KANIT: ad hâlâ ikisini birden getirir — kimliğin çözdüğü şey tam da budur.
    assert len(db.get_ai_analyses(patient_name="Mia")) == 2


def test_KRITIK_kimlik_MASKELEMEDEN_etkilenmez(tmp_path, monkeypatch):
    """⚠️ `PEMF_MASK_HISTORY_PII=1` açıkken TÜM adlar aynı maskeye düşer ve ad bazlı eşleme
    bütünüyle çöker. Kimlik PII olmadığı için maskelenmez — bağ AYAKTA kalır.

    MUTASYON: `add_ai_analysis`ta `patient_uuid`yi de `_redact_pii`den geçir → KIRMIZI.
    """
    from database.treatment_history_db import TreatmentHistoryDB

    monkeypatch.setenv("PEMF_MASK_HISTORY_PII", "1")
    kok = tmp_path / "maskeli"
    kok.mkdir(parents=True, exist_ok=True)
    d = TreatmentHistoryDB(kok)
    d.add_ai_analysis(module_id="m", patient_name="Mia", patient_uuid="kedi-A", result_summary="A")
    d.add_ai_analysis(module_id="m", patient_name="Boncuk", patient_uuid="kedi-B", result_summary="B")

    kayitlar = d.get_ai_analyses(limit=10)
    assert len(kayitlar) == 2
    # Adlar maskelenmiş OLABİLİR; kimlikler HER HÂLDE ayırt edici kalmalı.
    assert {k["patient_uuid"] for k in kayitlar} == {"kedi-A", "kedi-B"}
    assert [k["result_summary"] for k in d.get_ai_analyses(patient_uuid="kedi-A")] == ["A"]


def test_KRITIK_kimlik_VE_ad_birlikte_VEYA_ile_baglanir(db):
    """⚠️ Taşıma günü geçmiş İKİYE BÖLÜNMÜŞ görünmemeli: kimliği yazılmış YENİ kayıtlar ile
    aynı hastanın ESKİ (kimliksiz) kayıtları TEK listede gelmeli.

    MUTASYON: `" OR ".join` yerine `" AND ".join` yap → KIRMIZI (eski kayıtlar kaybolur).
    """
    db.add_ai_analysis(module_id="m", patient_name="Mia", patient_uuid="kedi-A", result_summary="YENI")
    db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="ESKI")  # kimliksiz

    hepsi = db.get_ai_analyses(patient_uuid="kedi-A", patient_name="Mia")
    assert {k["result_summary"] for k in hepsi} == {"YENI", "ESKI"}, hepsi


# ============================================================================
# 2. ⚠️ GERİ DOLDURMA — BELİRSİZ ADI TAHMİN ETMEZ
# ============================================================================


def test_KRITIK_BELIRSIZ_ad_TAHMIN_EDILMEZ(db):
    """⚠️ BU TAŞIMANIN EN ÖNEMLİ KURALI. Aynı ada sahip iki hayvan varsa harita o adı HİÇ
    içermez; kayıt kimliksiz kalır. Tahmin edilseydi bir hayvanın analizi başka bir hayvanın
    kaydına GÖMÜLÜRDÜ ve bu geri alınamazdı.

    MUTASYON: `_ai_hasta_kimliklerini_tasi_bir_kez`teki `if len(k) == 1` kısıtını kaldır
    (çakışanlardan birini seç) → KIRMIZI.
    """
    db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="belirsiz")
    db.add_ai_analysis(module_id="m", patient_name="Boncuk", result_summary="tekil")

    # "mia" haritada YOK (iki hastaya çözülüyordu → çağıran elemiş); "boncuk" var.
    sonuc = db.ai_analiz_kimliklerini_doldur({"boncuk": "kedi-B"})
    assert sonuc["guncellenen"] == 1, sonuc
    assert sonuc["kimliksiz_kalan"] == 1, sonuc

    kimlikler = {k["patient_name"]: k["patient_uuid"] for k in db.get_ai_analyses(limit=10)}
    assert kimlikler["Boncuk"] == "kedi-B"
    assert kimlikler["Mia"] == "", f"BELIRSIZ ad TAHMIN EDILMIS: {kimlikler}"


def test_KRITIK_geri_doldurma_IDEMPOTENT_ve_elle_kimligi_EZMEZ(db):
    """Tekrar çalıştırmak güvenli olmalı; zaten yazılmış bir kimlik DEĞİŞMEMELİ.

    MUTASYON: `UPDATE ... AND COALESCE(patient_uuid,'') = ''` koşulunu kaldır → KIRMIZI.
    """
    db.add_ai_analysis(module_id="m", patient_name="Mia", patient_uuid="ELLE-YAZILMIS", result_summary="x")
    db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="y")

    ilk = db.ai_analiz_kimliklerini_doldur({"mia": "otomatik"})
    assert ilk["guncellenen"] == 1, ilk
    ikinci = db.ai_analiz_kimliklerini_doldur({"mia": "otomatik"})
    assert ikinci["guncellenen"] == 0, f"idempotent DEGIL: {ikinci}"

    kimlikler = sorted(k["patient_uuid"] for k in db.get_ai_analyses(limit=10))
    assert kimlikler == ["ELLE-YAZILMIS", "otomatik"], kimlikler


def test_KRITIK_TURKCE_ad_katlamasi_TEK_KAYNAKTAN(db):
    """⚠️ Harita anahtarları `arama_katla` ile üretilir; doldurma da AYNI fonksiyonu
    kullanmalı. Ayrışırsa "İpek" kaydı "ipek" anahtarıyla EŞLEŞMEZ ve taşıma sessizce
    hiçbir şey yapmaz.

    MUTASYON: `ai_analiz_kimliklerini_doldur`da `arama_katla(ad)` yerine `ad.lower()` → KIRMIZI.
    """
    from utils.turkce_metin import arama_katla

    db.add_ai_analysis(module_id="m", patient_name="İpek", result_summary="x")
    sonuc = db.ai_analiz_kimliklerini_doldur({arama_katla("İPEK"): "kedi-I"})
    assert sonuc["guncellenen"] == 1, sonuc
    assert db.get_ai_analyses(patient_uuid="kedi-I"), "Turkce ad katlamasi AYRISMIS"


def test_bos_harita_ve_bozuk_girdi_COKERTMEZ(db):
    db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="x")
    assert db.ai_analiz_kimliklerini_doldur({})["guncellenen"] == 0
    assert db.ai_analiz_kimliklerini_doldur(None)["guncellenen"] == 0
    assert db.ai_analiz_kimliklerini_doldur({"": "k", "a": ""})["guncellenen"] == 0


# ============================================================================
# 3. UÇTAN UCA — YAZMA YOLU KİMLİĞİ GERÇEKTEN TAŞIYOR MU
# ============================================================================


def test_KRITIK_log_ucu_patient_id_YAZIYOR(tmp_path, monkeypatch):
    """MUTASYON: `/api/ai/log` çağrısından `payload.patient_id` argümanını çıkar → KIRMIZI.

    Sahadaki etki: yeni analizler de kimliksiz kalır, taşıma ileriye dönük ÇALIŞMAZ.
    """
    from fastapi.testclient import TestClient

    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server

    kok = tmp_path / "uc_kimlik"
    kok.mkdir(parents=True, exist_ok=True)
    d = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)

    with TestClient(api_server.app) as c:
        y = c.post(
            "/api/ai/log",
            json={
                "patient_name": "Mia",
                "module": "Test",
                "summary": "ozet",
                "module_id": "m",
                "patient_id": "kedi-A",
            },
        )
    assert y.status_code == 200, y.text[:200]
    kayitlar = d.get_ai_analyses(limit=5)
    assert kayitlar and kayitlar[0]["patient_uuid"] == "kedi-A", kayitlar


def test_KRITIK_patient_id_GONDERMEYEN_eski_istemci_BOZULMAZ(tmp_path, monkeypatch):
    """⚠️ GERİYE UYUMLULUK: kimlik göndermeyen bir istemcide kayıt DÜŞMEMELİ; eskisi gibi
    ada bağlı çalışmalı."""
    from fastapi.testclient import TestClient

    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server

    kok = tmp_path / "eski_istemci"
    kok.mkdir(parents=True, exist_ok=True)
    d = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)

    with TestClient(api_server.app) as c:
        y = c.post("/api/ai/log", json={"patient_name": "Mia", "module": "T", "summary": "s"})
    assert y.status_code == 200, y.text[:200]
    kayitlar = d.get_ai_analyses(limit=5)
    assert kayitlar, "kimliksiz kayit DUSTU -> eski istemci bozuldu"
    assert kayitlar[0]["patient_uuid"] == ""


# ============================================================================
# 4. KAYNAK ÇIPASI — ARAYÜZ KİMLİĞİ GÖNDERİYOR VE KULLANIYOR MU
# ============================================================================


@pytest.mark.skipif(not (_PF / "screens").exists(), reason="pf/ kaynak agaci yok")
def test_KRITIK_arayuz_patient_id_GONDERIYOR():
    """Saf hesap doğru olsa bile arayüz kimliği göndermiyorsa taşıma ileriye dönük çalışmaz.

    MUTASYON: `logAiResult`taki `patient_id` alanını kaldır → KIRMIZI.
    """
    from c_soyucu import c_soy

    src = c_soy((_PF / "screens" / "AiHubScreen.tsx").read_text(encoding="utf-8"))
    assert "patient_id: currentPatientId" in src, "analiz kaydi hasta KIMLIGINI gondermiyor"
    assert "currentPatientId = selectedPatient?.id" in src, "secili hasta kimligi HIC yazilmiyor"


@pytest.mark.skipif(not (_PF / "utils").exists(), reason="pf/ kaynak agaci yok")
def test_KRITIK_AD_YEDEGI_kaldirilmadi():
    """⚠️ Ad yedeği KALDIRILAMAZ: taşıma, adı birden çok hastaya çözülen kayıtları BİLEREK
    kimliksiz bıraktı. Yedek kaldırılırsa o kayıtlar ekrandan SESSİZCE kaybolur.

    MUTASYON: `hastaAnahtarlari`ndan `adAnahtari(...)`yı çıkar → KIRMIZI.
    """
    from c_soyucu import c_soy

    src = c_soy((_PF / "utils" / "sonAnaliz.ts").read_text(encoding="utf-8"))
    assert "kimlikAnahtari(hasta?.id), adAnahtari(hasta?.name)" in src, (
        "kimlik->ad yedek sirasi bozulmus: kimliksiz ESKI kayitlar ekrandan kaybolur"
    )


# ============================================================================
# 5. ⚠️ BELİRSİZLİK KURALI — HARİTAYI KURAN KATMANDA ÖLÇÜLÜR
# ============================================================================
#
# ⚠️ Yukarıdaki `test_KRITIK_BELIRSIZ_ad_TAHMIN_EDILMEZ` DB metodunu ELLE kurulmuş bir
# haritayla çağırır; yani "verileni uygular" davranışını ölçer. Belirsizlik kuralının
# KENDİSİ (`len(k) == 1`) API katmanındadır ve mutasyonla ölçüldü: o kısıt kaldırıldığında
# DB testi YEŞİL kalıyordu. Bu bölüm haritayı KURAN kodu çalıştırır.


@pytest.fixture
def hasta_defteri(tmp_path, monkeypatch):
    """İçinde AYNI ADLI iki hayvan + tekil bir hayvan olan izole hasta defteri."""
    from database import patient_database as pdb

    kok = tmp_path / "defter"
    kok.mkdir(parents=True, exist_ok=True)
    d = pdb.PatientDatabase(str(kok / "patients.db"))
    kimlikler = {
        "mia1": d.add_patient({"name": "Mia", "species": "Kedi"}),
        "mia2": d.add_patient({"name": "MİA", "species": "Kedi"}),  # Türkçe katlamada AYNI ad
        "boncuk": d.add_patient({"name": "Boncuk", "species": "Kedi"}),
    }
    monkeypatch.setattr(pdb, "get_patient_database", lambda *a, **k: d)
    import servers.api_server as api

    monkeypatch.setattr(api, "_ai_kimlik_tasindi", False, raising=False)
    return d, kimlikler


def test_KRITIK_HARITA_cakisan_adi_ELER(db, hasta_defteri, monkeypatch):
    """⚠️ TAŞIMANIN EN ÖNEMLİ KURALI, KURULDUĞU YERDE ÖLÇÜLÜR.

    "Mia" ve "MİA" Türkçe katlamada AYNI ada iner ve İKİ FARKLI hayvana çözülür → harita o
    adı HİÇ içermemeli, o analizler kimliksiz kalmalı. "Boncuk" tekildir → taşınmalı.

    MUTASYON: `_ai_hasta_kimliklerini_tasi_bir_kez`teki `if len(k) == 1` kısıtını kaldır
    → KIRMIZI (bir hayvanın analizi ÖBÜRÜNÜN kaydına gömülür; geri alınamaz).
    """
    from servers import api_server

    db.add_ai_analysis(module_id="m", patient_name="Mia", result_summary="belirsiz")
    db.add_ai_analysis(module_id="m", patient_name="Boncuk", result_summary="tekil")

    sonuc = api_server._ai_hasta_kimliklerini_tasi_bir_kez(db)
    assert sonuc.get("guncellenen") == 1, f"tekil ad tasinmadi: {sonuc}"
    assert sonuc.get("kimliksiz_kalan") == 1, f"belirsiz ad TAHMIN EDILMIS: {sonuc}"

    kimlikler = {k["patient_name"]: k["patient_uuid"] for k in db.get_ai_analyses(limit=10)}
    assert kimlikler["Mia"] == "", f"cakisan ad icin kimlik YAZILMIS: {kimlikler}"
    assert kimlikler["Boncuk"], "tekil ad icin kimlik yazilmamis"


def test_KRITIK_tasima_TEK_SEFERLIK(db, hasta_defteri):
    """İkinci çağrı hiçbir şey yapmamalı (bayrak + kilit).

    MUTASYON: `_ai_kimlik_tasindi = True` atamasını sil → KIRMIZI (her POST'ta tüm tabloyu tarar).
    """
    from servers import api_server

    db.add_ai_analysis(module_id="m", patient_name="Boncuk", result_summary="x")
    ilk = api_server._ai_hasta_kimliklerini_tasi_bir_kez(db)
    assert ilk.get("guncellenen") == 1, ilk
    ikinci = api_server._ai_hasta_kimliklerini_tasi_bir_kez(db)
    assert ikinci == {}, f"tasima TEKRAR kostu: {ikinci}"
