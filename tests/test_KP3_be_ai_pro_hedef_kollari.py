# -*- coding: utf-8 -*-
"""KP-3 C · `servers/ai_pro_hedef.py` (AI Pro hedef sağlayıcıları) kapsanmayan kolları — her test bir DAVRANIŞ iddiası. Ürün kodu
DEĞİŞMEDİ; sürüş kararı (yeni red / kıskaç) YOK — yalnız GPU→CPU geri dönüşü, gösterim ve iskelet sözleşmesi ölçülür.

- Kedi: GPU servisine devir patlarsa lokalizasyon / doz CPU-yerel yoldan YİNE üretilir (uyarıyla); bozuk lokalizasyon sonucunda OOD ve
  "kabin dışı" işaretleri KAPALI kalır (yanlış uyarı yok, istisna yok).
- Kabin denetimi: sayıya çevrilemeyen koordinat → okunur red nedeni.
- Takip yarıçapı: bozuk bbox → 1 px (bölme / eşleşme düşmez).
- Ortak iskelet: alt sınıfın vermesi gereken her kanca temel sınıfta `NotImplementedError` (sessiz varsayılan YOK); "özne yok" hata
  listesi varsayılanı boş.
- Gösterim: tanınmayan etiket AYNEN; konum ölçüldü (ArUco) ve kapı engel söylemiyorsa ipucu "hedef seçilemedi"; önizleme bindirmesi
  üretilemezse None (önizleme düşmez).
- Fantom XAI modülü gerçek `inference_em_fantom` modülüdür.
"""

from __future__ import annotations

import logging

import pytest
from servers import ai_pro_hedef as aph
from servers import ai_router as air
from utils import ceviri


def test_kedi_gpu_devri_patlarsa_cpu_yerel_yol(monkeypatch, caplog):
    monkeypatch.setattr(air, "ai_service_enabled", lambda: True)

    def _patla(*a):
        raise ConnectionError("GPU servisi yanıt vermiyor")

    em_kedi = []
    monkeypatch.setattr(air, "_localize_organ_gpu", _patla)
    monkeypatch.setattr(air, "_localize_organ_cpu", lambda kare, hid: (True, 1.0, 2.0, 3.0, 0.9))
    monkeypatch.setattr(air, "_predict_and_drive_gpu", lambda *a: em_kedi.append("gpu") or _patla())
    monkeypatch.setattr(air, "_predict_and_drive_cpu", lambda x, y, z, hid: em_kedi.append("cpu") or ("D", "P", "E"))
    monkeypatch.setattr(aph, "_kedi_egitim_araligi", lambda: ((0.0, 10.0),) * 3)
    k = aph.KediSaglayici()
    with caplog.at_level(logging.WARNING, logger=air.logger.name):
        assert k.localize("kare", 2) == (True, 1.0, 2.0, 3.0, 0.9)
        # AP-17: ODAK ayarı yoksa sürüş SIFIR — em_kedi (GPU ya da CPU) sürüş kaynağı değil
        assert k.predict(1.0, 2.0, 3.0, 2) == ([0.0] * 7, [0.0] * 7, 0.0) and em_kedi == []
    mesajlar = [r.getMessage() for r in caplog.records]
    assert any("cat_organ GPU delegasyonu başarısız → CPU-yerel" in m for m in mesajlar)
    assert k._meta == {"ood": False}


def test_bozuk_lokalizasyonda_ood_ve_kabin_disi_kapali(monkeypatch):
    monkeypatch.setattr(aph, "_kedi_egitim_araligi", lambda: ((0.0, 10.0),) * 3)
    k = aph.KediSaglayici()
    k._ood_isaretle((True, "olculmedi", 99.0, 99.0, 0.8))
    assert k._meta == {"ood": False} and k._kabin_disi is False
    k._ood_isaretle((False, 0.0, 0.0, 0.0, "guven-okunamadi"))  # konumsuz + güven OKUNAMAZ → kabin dışı DENMEZ
    assert k._kabin_disi is False
    k._ood_isaretle((False, 0.0, 0.0, 0.0, 0.8))
    assert k._kabin_disi is True, "güvenli ama konumsuz sonuç kabin dışı işaretlenmedi (karşıt kanıt)"


def test_kabin_denetimi_sayi_olmayan_koordinat_ve_bozuk_bbox():
    assert aph.hedef_kabin_disi_nedeni("x", 0, 0) == "kabin denetimi: koordinat sayı değil"
    assert aph._yaricap_px("bozuk") == 1.0
    assert aph._yaricap_px((0, 0, 40, 20)) == 20.0


def test_iskelet_kancalari_alt_sinifa_birakilir():
    s = aph._EmCvSaglayici()
    for kanca, arg in (
        ("_yukleyici", ()),
        ("_pipeline_kur", (None,)),
        ("_adaylar", (None,)),
        ("_ipucu_ozne_yok", ()),
        ("_egitim_araligi", ()),
        ("_xai_modulu", ()),
    ):
        with pytest.raises(NotImplementedError):
            getattr(s, kanca)(*arg)
    assert s._ozne_yok_hatalari() == ()


def test_gosterim_etiketi_ipucu_ve_bindirme_hatasi(caplog):
    s = aph.FantomSaglayici()
    assert s.etiket_gosterim("Kuyu 3") == "Kuyu 3"
    s._meta = {"method": "aruco_pnp", "pemf_kapisi": {"surulebilir": True}}
    assert s.ipucu(True, "Tümör 2") == ceviri.t("ai.pro.ipucu.hedefSecilemedi", hedef_adi="Tümör 2")

    class _Hat:
        def render_panels(self, ctx, result, lang=None):
            raise RuntimeError("panel çizilemedi")

    with caplog.at_level(logging.DEBUG, logger=air.logger.name):
        assert s._overlay(_Hat(), None, None) is None
    assert any("overlay üretilemedi" in r.getMessage() for r in caplog.records)


def test_fantom_xai_modulu_gercek_modul():
    from ai_hub.inference_em_fantom import inference_em_fantom as ief

    assert aph.FantomSaglayici()._xai_modulu() is ief
