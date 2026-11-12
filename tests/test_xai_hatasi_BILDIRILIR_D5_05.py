# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.05 (B-5.15) KAPISI — XAI hatası yanıtta `xai_error` ile SÖYLENİR ve günlüğe TAM ZİNCİRLE yazılır.

ARIZA (DENETİM-05 B-5.15): `em_fantom`, `em_petri` ve `/api/ai/pro/propose` uçlarında "dozu ne belirledi" açıklaması
(`xai_hizli_sensitivity` / sağlayıcının `xai_sensitivity`si) patlayınca `logger.warning("… %s", xe)` — `exc_info`suz — basılıyor
ve yanıtta HİÇBİR iz kalmıyordu: hekim onay ekranında / araştırma panelinde açıklama satırı sessizce yok, kök neden günlükte
yok. Öteki XAI uçları (termal, CT, histopat, RNA, CKD, ses, retikülosit) zaten `exc_info=True` + `xai_error` sözleşmesindeydi.

KAPI (davranış — gerçek uç, TestClient, sahte model; gerçek kamera / ağırlık YOK): açıklama işlevi `RuntimeError` fırlatır →
(1) uç 200 döner ve analiz alanları DOLU (açıklama ikincil; zarif düşüş korunur), (2) yanıtta `xai_error` = katalog metni
`ai.sonuc.aciklamaUretilemedi` (TR + EN katalogda; yeni metin YOK), `xaiSensitivity` YOK, (3) günlük kaydında `exc_info` dolu
ve biçimlenmiş kayıt kök hatayı (traceback) taşır.
MUTASYON: üç uçtan birinde `exc_info=True`yu kaldırmak ya da `xai_error` atamasını silmek → KIRMIZI.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest
from kd_kalibrasyon_yardimci import (
    odak_tahminci,  # noqa: F401  ODK5: kedi önerisi de ODAK'tan — sahte, eski doz kanıtına bağlar
)

# Aparat (gerçek uç + sahte hat): mevcut kapılardan — kopyalanmaz, aynı sahte model / ArUco yaması.
from test_em_ongorucu_SONLU_OLMAYAN_girdi_PIKSEL_kipi_ve_TOPLAM_sure import (  # noqa: F401 — aparat
    _KayitciDoz,
    fantom_hatti,
    fantom_ucu,
    petri_hatti,
)
from test_em_xai_entegrasyon import propose_env  # noqa: F401 — aparat
from test_koordinat_donusumu_FIZIKSEL_poz_DOGRULUK_ve_RED import _aruco_yamala, petri_ucu_d100  # noqa: F401 — aparat

_KOK_HATA = "D505 XAI SIMULE ARIZA"


def _beklenen_metin() -> str:
    from utils import ceviri

    metin = ceviri.t("ai.sonuc.aciklamaUretilemedi")
    assert metin and metin != "ai.sonuc.aciklamaUretilemedi", "aparat: katalog anahtarı çözülmedi"
    return metin


def _zincirli_kayit(caplog, parca: str) -> logging.LogRecord:
    ilgili = [r for r in caplog.records if parca in r.getMessage()]
    assert ilgili, f"'{parca}' uyarısı HİÇ basılmadı: {[r.getMessage()[:70] for r in caplog.records]}"
    kayit = ilgili[-1]
    assert kayit.levelno >= logging.WARNING, f"seviye {kayit.levelname} — normal günlükte görünmez"
    assert kayit.exc_info and kayit.exc_info[0] is not None, (
        f"'{parca}' kaydında exc_info YOK — kök neden (traceback) kayıp"
    )
    metin = logging.Formatter().format(kayit)
    assert "Traceback" in metin and _KOK_HATA in metin, "biçimlenmiş kayıtta traceback / kök hata yok:\n" + metin[:400]
    return kayit


def _patlayan(cagrildi: list):
    def _p(*a, **k):
        cagrildi.append(1)
        raise RuntimeError(_KOK_HATA)

    return _p


def test_KRITIK_em_fantom_XAI_hatasi_yanitta_xai_error_ve_TAM_ZINCIR(fantom_ucu, fantom_hatti, monkeypatch, caplog):
    from ai_hub.inference_em_fantom import inference_em_fantom as ief
    from ai_hub.inference_em_fantom.phantom_cv_v3.color_segment import Region

    c, _ef, kutu, govde = fantom_ucu
    pl, _kos = fantom_hatti
    maske = np.zeros((480, 640), np.uint8)
    bolge = Region(
        organ_id=1,
        label="tumor",
        centroid_px=(300.0, 250.0),
        area_px=120,
        bbox_px=(290, 240, 20, 20),
        contour_px=np.zeros((4, 1, 2), np.int32),
        mask=maske,
    )
    monkeypatch.setattr(pl, "segment_phantom", lambda *a, **k: {"tumor": [bolge], "healthy": []})
    _aruco_yamala(pl, monkeypatch, [])
    kutu["ong"] = _KayitciDoz()
    cagrildi: list = []
    monkeypatch.setattr(ief, "xai_hizli_sensitivity", _patlayan(cagrildi))
    with caplog.at_level(logging.WARNING):
        r = c.post("/api/ai/vision/em_fantom", data={"image_base64": govde})
    assert r.status_code == 200, f"XAI hatası ANALİZİ düşürdü: {r.text[:200]}"
    assert cagrildi, "aparat: açıklama yoluna HİÇ girilmedi (sürülebilir konumlu bölge yok) — kapı vakumda"
    j = r.json()
    assert j.get("tumor_regions") and j["tumor_regions"][0].get("centroid_cabin_mm") is not None, "analiz alanları boş"
    assert "xaiSensitivity" not in j
    assert j.get("xai_error") == _beklenen_metin(), f"em_fantom yanıtında xai_error yok/yanlış: {j.get('xai_error')!r}"
    _zincirli_kayit(caplog, "em_fantom XAI meta")


def test_KRITIK_em_petri_XAI_hatasi_yanitta_xai_error_ve_TAM_ZINCIR(petri_ucu_d100, monkeypatch, caplog):
    from ai_hub.inference_em_petri import inference_em_petri as iep

    c, govde, _xai, pp = petri_ucu_d100
    _aruco_yamala(pp, monkeypatch, [])
    cagrildi: list = []
    monkeypatch.setattr(iep, "xai_hizli_sensitivity", _patlayan(cagrildi))
    with caplog.at_level(logging.WARNING):
        r = c.post("/api/ai/vision/em_petri", data={"image_base64": govde})
    assert r.status_code == 200, f"XAI hatası ANALİZİ düşürdü: {r.text[:200]}"
    assert cagrildi, "aparat: açıklama yoluna HİÇ girilmedi (sürülebilir konumlu kuyu yok) — kapı vakumda"
    j = r.json()
    assert j.get("wells") and j["wells"][0].get("centroid_cabin_mm") is not None, "analiz alanları boş"
    assert "xaiSensitivity" not in j
    assert j.get("xai_error") == _beklenen_metin(), f"em_petri yanıtında xai_error yok/yanlış: {j.get('xai_error')!r}"
    _zincirli_kayit(caplog, "em_petri XAI meta")


def test_KRITIK_ODK5_propose_ODAK_onerisinde_XAI_CAGRILMAZ_xai_error_YOK(propose_env, monkeypatch):
    """ODK5: AI Pro önerisi (kedi dahil) ODAK'tan — hoca XAI'si HİÇ çağrılmaz (dozu açıklamaz), bu yüzden "açıklama üretilemedi" uyarısı
    da çıkmaz; öneri 200. (XAI hatasının yutulmaması AI Hub analiz uçlarında — yukarıdaki fantom / petri testleri.)"""
    import ai_hub.em_kedi.inference_em_kedi as iek

    _air, client = propose_env
    cagrildi: list = []
    monkeypatch.setattr(iek, "xai_hizli_sensitivity", _patlayan(cagrildi))
    r = client.post("/api/ai/pro/propose", json={"organ_id": 3, "duration_minutes": 20})
    assert r.status_code == 200, f"öneri düştü: {r.text[:200]}"
    meta = r.json().get("meta") or {}
    assert not cagrildi and "xaiSensitivity" not in meta and "xai_error" not in meta, meta


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_xai_error_metni_IKI_dilde_katalogda(dil):
    """Yanıta giden metin YENİ değil: `ai.sonuc.aciklamaUretilemedi` TR + EN katalogda (Y157)."""
    import json
    from pathlib import Path

    kat = json.loads(
        (Path(__file__).resolve().parents[1] / "apps" / "backend" / "i18n" / f"{dil}.json").read_text(encoding="utf-8")
    )
    assert kat["ai"]["sonuc"]["aciklamaUretilemedi"].strip(), f"{dil} katalogda boş"
