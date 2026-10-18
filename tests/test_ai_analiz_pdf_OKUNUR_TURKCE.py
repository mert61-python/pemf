# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI ANALİZ PDF'i — veteriner ve hayvan sahibi için TAMAMEN TÜRKÇE ve ANLAŞILIR (sahip bildirimi 2026-10-18).

Sahip (ekrandaki `PEMF_AI_Mia_140.pdf` — Hastalık Analizi): "burda raporda ne olduğu anlaşılmıyor çok yapay zeka mühendisi
okuyacakmış gibi duruyor. ama veteriner bakmıcak mı ya da kedi sahibi ona göre tamamen türkçe ve anlaşılır olmalı".
Eski rapor HAM sözlüğü döküyordu: "results: disease: Conjunctivitis, probability: 0,7797 …", "top_probability 0,78",
"low_confidence Hayır", "xai: … feature: Eye_Discharge_bin, attribution: -3,196 …", başlıkta "AI Analiz Raporu".

SÖZLEŞME:
  · olası tanılar Türkçe adla, olasılık sırasıyla ve yüzdeyle; tanıyı etkileyen belirtiler Türkçe adla ve "olasılığını
    artırdı / azalttı" diye;
  · İngilizce anahtar / değer / model girdisi adı ve teknik alan (cihaz, ölçüm, kalibrasyon) rapora GİRMEZ;
  · tarih "13 Ekim 2026, 19:45"; güven "kesin tanı değildir" açıklamasıyla; düşük güven yalnız GERÇEKTEN düşükse uyarı;
  · sonda "kesin tanı veteriner hekime aittir"; başlık / altbilgi Türkçe ("PEMF TEDAVİ RAPORU" / İngilizce alt başlık YOK).
GERÇEK uç + GERÇEK PDF üretimi (PyMuPDF ile metin çıkarılır); kayıt izole DB'de.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

fitz = pytest.importorskip("fitz", reason="PyMuPDF yok -> PDF metni cikarilamaz")

#: Ekrandaki rapordaki kaydın birebir sonuç ayrıntısı (Mia, Hastalık Analizi, 13.10.2026 19:45:42).
HASTALIK_DETAYI = {
    "results": [
        {"disease": "Conjunctivitis", "probability": 0.7797},
        {"disease": "Ringworm", "probability": 0.1866},
        {"disease": "Gastroenteritis", "probability": 0.02495},
    ],
    "top_probability": 0.78,
    "low_confidence": False,
    "xai": {
        "disease": "Conjunctivitis",
        "top_features": [
            {"feature": "Eye_Discharge_bin", "attribution": -3.196},
            {"feature": "Duration_days", "attribution": 2.94},
            {"feature": "Body_Temperature", "attribution": 2.344},
            {"feature": "Heart_Rate", "attribution": -1.27},
            {"feature": "Diarrhea_bin", "attribution": 0.6462},
            {"feature": "Skin_Lesions_bin", "attribution": 0.1},
        ],
    },
}

#: Raporda GÖRÜNMEMESİ gereken mühendis dili (eski raporda vardı).
YASAK = (
    "results",
    "top_probability",
    "low_confidence",
    "xai",
    "top_features",
    "attribution",
    "feature",
    "disease:",
    "probability",
    "Conjunctivitis",
    "Ringworm",
    "Gastroenteritis",
    "Eye_Discharge",
    "Duration_days",
    "Body_Temperature",
    "AI Analiz",
    "Pulsed Electromagnetic",
    "TEDAVİ RAPORU",
    "2026-10-13T",
)


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app, client=("127.0.0.1", 51245)) as c:
        yield c


@pytest.fixture
def db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server

    kok = tmp_path / "veri"
    kok.mkdir(parents=True, exist_ok=True)
    d = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: d)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    return d


def _pdf_metni(istemci, db, **kayit) -> str:
    varsayilan = dict(
        mode="pet_owner",
        module_id="disease",
        module_label="Hastalık Analizi",
        patient_name="Mia",
        operator_email="sahip@ornek.com",
        input_type="clinical",
        result_summary="Konjonktivit (göz nezlesi) (%78)",
        result_detail=HASTALIK_DETAYI,
        confidence=0.78,
    )
    varsayilan.update(kayit)
    sid = db.add_ai_analysis(**varsayilan)
    with db._get_connection() as c:  # ekrandaki raporun zamanı (kayıt anı değil)
        c.execute("UPDATE ai_analyses SET created_at = ? WHERE id = ?", ("2026-10-13T19:45:42", sid))
        c.commit()  # bağlam çıkışı commit'siz işlemi geri alır
    y = istemci.get(f"/api/ai/log/{sid}/pdf")
    assert y.status_code == 200 and y.content[:4] == b"%PDF", y.text[:300]
    with fitz.open(stream=y.content, filetype="pdf") as d:
        return re.sub(r"\s+", " ", "\n".join(p.get_text() for p in d))  # PDF satır kırılımı metni bölmesin


def test_KRITIK_ekrandaki_hastalik_raporu_TURKCE_ve_ANLASILIR(istemci, db):
    metin = _pdf_metni(istemci, db)
    sizan = [y for y in YASAK if y in metin]
    assert not sizan, f"mühendis dili rapora sızdı: {sizan}\n{metin[:1500]}"
    for beklenen in (
        "YAPAY ZEKÂ ANALİZ RAPORU",
        "Hayvan sahibi ve veteriner hekim için özet",
        "Mia",
        "13 Ekim 2026, 19:45",
        "Olası tanılar",
        "1. Konjonktivit (göz nezlesi) — %78",
        "2. Saçkıran (deri mantarı, dermatofitoz) — %19",
        "3. Gastroenterit (mide-bağırsak iltihabı) — %2",
        "Sonucu en çok etkileyen belirtiler",
        "Göz akıntısı: güçlü etki — bu tanının olasılığını azalttı",
        "Şikâyetin süresi: güçlü etki — bu tanının olasılığını artırdı",
        "kesin tanı değildir",
        "Kesin tanı ve tedavi kararını veteriner hekim verir",
    ):
        assert beklenen in metin, f"raporda yok: {beklenen!r}\n{metin[:1500]}"
    assert "güveni düşük" not in metin, "düşük güven uyarısı düşük olmayan sonuçta çıktı"


def test_KRITIK_DUSUK_guvenli_sonucta_uyari_cumlesi_VAR(istemci, db):
    detay = dict(HASTALIK_DETAYI, low_confidence=True)
    metin = _pdf_metni(istemci, db, result_detail=detay, confidence=0.41)
    assert "güveni düşük" in metin and "veteriner hekiminize danışın" in metin, metin[:1200]
    assert "low_confidence" not in metin


def _ogeler_metni(detay: dict, **kayit) -> str:
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    ogeler = analiz_pdf_ogeleri({"patient_name": "Mia", "result_detail": detay, **kayit})
    return "\n".join(
        f"{o.get('etiket', '')}: {o.get('aciklama', '')} " + " | ".join(o.get("satirlar") or []) for o in ogeler
    )


#: snake_case / İngilizce teknik iz (ör. "probability_sick", "class_name").
_TEKNIK_IZ = re.compile(r"\b[a-z]+_[a-z_]+\b")


@pytest.mark.parametrize(
    ("detay", "beklenenler", "yasaklar"),
    [
        (  # termal
            {
                "prediction": {"label": "Sick", "confidence": 0.953, "probability_sick": 0.97},
                "girdi_dogrulama": {
                    "durum": "termal_paleti",
                    "dogrulandi": True,
                    "uyari": None,
                    "yon_notu": "Paletin kamera yönünde olduğundan emin olun (soğuk = siyah / mor, sıcak = sarı).",
                    "olcum": {"palet": "inferno", "palet_uyumu": 0.98},
                },
            },
            ["Hasta (riskli)", "%97", "termal kamera görüntüsü olarak doğrulandı", "Paletin kamera yönünde"],
            ["Sick", "inferno", "palet_uyumu", "termal_paleti", "dogrulandi"],
        ),
        (  # retikülosit sayımı
            {"counts": {"erythrocyte": 120, "punctate reticulocyte": 5, "aggregate reticulocyte": 3}, "device": "cuda"},
            ["Eritrosit (alyuvar): 120", "Noktalı retikülosit (genç alyuvar): 5"],
            ["erythrocyte", "reticulocyte", "cuda"],
        ),
        (  # FGS ağrı skoru
            {"fgs_total": 4, "pain_level": "moderate pain", "detected": True, "raw_fgs": {"x": 1}},
            ["ağrı skoru (FGS, 0–10): 4", "Orta ağrı", "Yüz bulundu mu: Evet"],
            ["moderate", "raw_fgs"],
        ),
        (  # bilinmeyen / teknik alanlar
            {"per_well": [1, 2, 3], "mysterious_metric": 0.5, "calibrated": True, "method": "aruco_pnp"},
            ["uygulamadaki analiz geçmişinde"],
            ["per_well", "mysterious", "aruco", "Kalibre"],
        ),
    ],
)
def test_KRITIK_moduller_TURKCE_teknik_alan_SIZMAZ(detay, beklenenler, yasaklar):
    metin = _ogeler_metni(detay)
    for b in beklenenler:
        assert b in metin, f"yok: {b!r}\n{metin}"
    for y in yasaklar:
        assert y not in metin, f"sızdı: {y!r}\n{metin}"
    assert not _TEKNIK_IZ.findall(metin), f"teknik (snake_case) iz: {_TEKNIK_IZ.findall(metin)}\n{metin}"


def test_KARSIT_bilinen_tum_alanlar_TURKCE_etiketli_ve_sonda_kesin_tani_notu():
    # Teknik iç alanlar (cihaz, model, süre) BİLEREK gizlenir — "eksik bilgi" notu doğurmaz (yalnız gerçekten bilinmeyen alan).
    metin = _ogeler_metni(
        {"closure_pct": 42.3, "n_cells": 318, "device": "cuda", "model_version": "v3", "inference_ms": 41}
    )
    assert "Yara kapanma oranı (%): 42,3" in metin and "Hücre sayısı: 318" in metin, metin
    assert "uygulamadaki analiz geçmişinde" not in metin, "bilinen / teknik alanlarda 'atlandı' notu çıktı"
    assert metin.rstrip().splitlines()[-1].startswith("Önemli: Bu rapor yapay zekâ ile hazırlanmış"), metin


def test_KRITIK_rapor_ureticisi_DIZGI_veri_yoluyla_da_kurulur(tmp_path):
    """2026-10-18: `__init__` içindeki yerel `from pathlib import Path` dizgi yolda UnboundLocalError attırıyordu (ölçüldü)."""
    from utils.pdf_report_generator import PDFReportGenerator

    u = PDFReportGenerator(str(tmp_path / "veri"))
    assert str(u.app_data_dir).endswith("veri")
