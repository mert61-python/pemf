# -*- coding: utf-8 -*-
"""I18N-P1 · ACİL DURDUR MANDALI — bantta "Sıfırla" adımının söylenip söylenmediği MAKİNE-OKUR alan (`eylemSifirlaSoyler`).

Arayüz (`EstopMandalBandi`) eskiden `/Sıfırla/.test(eylem)` ile SUNUCUNUN eylem METNİNE bakıyordu; sunucu İngilizce yanıtlayınca eşleşme düşer
(bant "Sıfırla"yı iki kez yazar). Sözleşme (13 §2-d): `eylem` metni, `neden` kodu, sıfırlama ucu ve onay akışı DEĞİŞMEZ; `durum()` yalnız bir
makine-okur alan KAZANIR; arayüz önce ona bakar, yoksa (eski sunucu) eski metin eşleşmesine düşer.
MUTASYON: `eylem_birak` bayrağı saklamazsa / `mandalla` taşımazsa / `durum()` alanı vermezse KIRMIZI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _temiz():
    from utils import estop_mandali

    estop_mandali.sifirla("test")
    return estop_mandali


def test_varsayilan_alan_false_ve_mevcut_alanlar_ayni():
    em = _temiz()
    try:
        d = em.durum()
        assert d["eylemSifirlaSoyler"] is False
        assert set(d) >= {
            "aktif",
            "neden",
            "zaman",
            "sifirlamaZamani",
            "nesil",
            "oncekiOturum",
            "eylem",
        }  # eski alanlar KALDI
    finally:
        em.sifirla("test")


def test_sifirla_soyler_bayragi_ayni_nedenli_mandala_gider_ve_eylem_metni_DEGISMEZ():
    em = _temiz()
    try:
        em.eylem_birak("stm_komut_reddi", "EYLEM-DUTY", sifirla_soyler=True)
        em.mandalla("stm_komut_reddi")
        d = em.durum()
        assert d["eylem"] == "EYLEM-DUTY" and d["eylemSifirlaSoyler"] is True
        em.sifirla("test")
        d = em.durum()
        assert d["eylem"] == "" and d["eylemSifirlaSoyler"] is False
    finally:
        em.sifirla("test")


def test_bayrak_verilmezse_false_baska_nedenli_mandal_almaz_ve_bir_kez_kullanilir():
    em = _temiz()
    try:
        em.eylem_birak("stm_komut_reddi", "EYLEM-KART")  # kart uyumsuzluğu: "Sıfırla" demez
        em.mandalla("manual")
        assert em.durum()["eylemSifirlaSoyler"] is False and em.durum()["eylem"] == ""
        em.mandalla("stm_komut_reddi")
        assert em.durum()["eylem"] == "EYLEM-KART" and em.durum()["eylemSifirlaSoyler"] is False
        em.sifirla("test")
        em.eylem_birak("stm_komut_reddi", "X", sifirla_soyler=True)
        em.mandalla("stm_komut_reddi")
        em.sifirla("test")
        em.mandalla("stm_komut_reddi")
        assert em.durum()["eylemSifirlaSoyler"] is False, "bayrak bir kez kullanılır (bayat bayrak taşınmaz)"
    finally:
        em.sifirla("test")


def test_durum_JSON_uyumlu_ve_arayuz_alan_adi_ayni():
    em = _temiz()
    try:
        em.eylem_birak("stm_komut_reddi", "E", sifirla_soyler=True)
        em.mandalla("stm_komut_reddi")
        json.dumps(em.durum())
        ts = (KOK / "apps/ui/src/types/domain.ts").read_text(encoding="utf-8")
        assert "eylemSifirlaSoyler?: boolean" in ts, "arayüz tipi alanı tanımıyor"
        bant = (KOK / "apps/ui/src/components/ui/EstopMandalBandi.tsx").read_text(encoding="utf-8")
        assert "eylemSifirlaSoyler" in bant and "/Sıfırla/.test(eylem)" in bant  # önce alan, yoksa eski metin eşleşmesi
    finally:
        em.sifirla("test")
