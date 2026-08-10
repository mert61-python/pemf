# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HEKİM ONAY KAPISI (2026-08-06, sahip kararı: 'sert kapı — onaysız tedavi başlamaz').

Bu testler HASTA GÜVENLİĞİ sözleşmesini kilitler. Hepsi YOKLUK tarafını sınar: onay
olmadan / reddedilmişken / süresi geçmişken / ikinci kez tedavi BAŞLAMAMALI.
"""

import os
import time

os.environ.pop("PEMF_SIMULATE", None)

import pytest

from servers import ai_approval as ap

SPEC = {"D": [0.1] * 7, "P": [0.0] * 7, "organ_id": 2, "duration_minutes": 20}


@pytest.fixture(autouse=True)
def _temiz():
    ap.clear()
    yield
    ap.clear()


# ── temel akış ──────────────────────────────────────────────────────────────
def test_oneri_pending_baslar():
    r = ap.create("ai_pro", SPEC)
    assert r["status"] == ap.PENDING and r["id"]
    assert r["specs"]["organ_id"] == 2


def test_onayla_sonra_tuket_parametreleri_MUHURLU_doner():
    r = ap.create("ai_pro", SPEC)
    ap.approve(r["id"], operator="dr@klinik.com")
    used = ap.consume(r["id"])
    assert used["status"] == ap.CONSUMED
    # Mühür: uygulanacak parametreler onaylananla AYNI olmalı
    assert used["specs"] == SPEC
    assert used["operator"] == "dr@klinik.com"


# ── SERT KAPI: bu beşinin hepsi tedaviyi ENGELLEMELİ ────────────────────────
def test_ONAYSIZ_tuketilemez():
    r = ap.create("ai_pro", SPEC)
    with pytest.raises(ValueError, match="onaylanmadı"):
        ap.consume(r["id"])


def test_REDDEDILMIS_tuketilemez():
    r = ap.create("ai_pro", SPEC)
    ap.reject(r["id"], operator="dr@klinik.com", reason="Organ yanlış lokalize edilmiş")
    with pytest.raises(ValueError, match="REDDEDİLDİ"):
        ap.consume(r["id"])


def test_BILINMEYEN_id_tuketilemez():
    with pytest.raises(ValueError, match="Onay bulunamadı"):
        ap.consume("olmayan-id")


def test_TEK_KULLANIMLIK_ikinci_kez_tuketilemez():
    """Bir kez onaylanan parametre tekrar tekrar başlatılamamalı."""
    r = ap.create("ai_pro", SPEC)
    ap.approve(r["id"])
    ap.consume(r["id"])
    with pytest.raises(ValueError, match="zaten kullanıldı"):
        ap.consume(r["id"])


def test_SURESI_DOLMUS_onay_tuketilemez(monkeypatch):
    """Sabahki onayla akşam tedavi başlatmak klinik olarak savunulamaz."""
    r = ap.create("ai_pro", SPEC)
    ap.approve(r["id"])
    monkeypatch.setattr(time, "time", lambda: r["created_at"] + ap.TTL_S + 1)
    with pytest.raises(ValueError, match="süresi doldu"):
        ap.consume(r["id"])


# ── karar bütünlüğü ─────────────────────────────────────────────────────────
def test_ayni_oneri_IKI_KEZ_karara_baglanamaz():
    r = ap.create("ai_pro", SPEC)
    ap.approve(r["id"])
    with pytest.raises(ValueError, match="zaten karara bağlanmış"):
        ap.reject(r["id"], reason="fikir değiştirdim")


def test_red_gerekcesi_saklanir():
    r = ap.create("ai_pro", SPEC)
    ap.reject(r["id"], operator="dr@klinik.com", reason="Duty çok yüksek")
    assert ap.get(r["id"])["reason"] == "Duty çok yüksek"
    assert ap.get(r["id"])["status"] == ap.REJECTED


def test_suresi_dolmus_oneri_ONAYLANAMAZ(monkeypatch):
    r = ap.create("ai_pro", SPEC)
    monkeypatch.setattr(time, "time", lambda: r["created_at"] + ap.TTL_S + 1)
    with pytest.raises(ValueError, match="süresi doldu"):
        ap.approve(r["id"])


def test_bilinmeyen_id_onaylanamaz():
    with pytest.raises(KeyError):
        ap.approve("yok")


# ── dayanıklılık ────────────────────────────────────────────────────────────
def test_kayitlar_sinirsiz_BIRIKMEZ():
    for i in range(ap._MAX + 20):
        ap.create("ai_pro", {**SPEC, "i": i})
    assert len(ap._store) <= ap._MAX


def test_es_zamanli_tuketimde_YALNIZ_BIRI_kazanir():
    """İki istemci aynı anda başlatmaya çalışırsa tedavi BİR kez başlamalı."""
    import concurrent.futures as cf

    r = ap.create("ai_pro", SPEC)
    ap.approve(r["id"])

    def _try():
        try:
            ap.consume(r["id"])
            return True
        except ValueError:
            return False

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        sonuc = list(ex.map(lambda _: _try(), range(8)))
    assert sum(sonuc) == 1, f"tek kullanımlık ihlal edildi: {sum(sonuc)} kez tüketildi"
