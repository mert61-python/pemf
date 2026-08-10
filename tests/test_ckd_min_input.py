# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CKD (böbrek hastalığı) — ASGARİ GİRDİ KURALI (2026-08-07, sahip bildirimi).

ARIZA: "Hiçbir veri girmeden analiz yaptığımda %78 çıkıyor." Tüm alanlar opsiyonel olduğu
için boş istek preprocessor tarafından impute ediliyor ve model eğitim setinin ÖN-OLASILIĞINI
döndürüyordu. Kullanıcı bunu hasta verisinden çıkmış bir teşhis sanıyor.

Aynı sınıf hata `/api/ai/disease` (kedi) ucunda daha önce kapatılmıştı; bu uç atlanmıştı.
"""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


TAM = {
    "age": 48,
    "bp": 80,
    "sg": 1.02,
    "al": 1,
    "su": 0,
    "bgr": 121,
    "bu": 36,
    "sc": 1.2,
    "sod": 137,
    "pot": 4.4,
    "hemo": 15.4,
    "pcv": 44,
    "wc": 7800,
    "rc": 5.2,
    "rbc": "normal",
    "pc": "normal",
    "pcc": "notpresent",
    "ba": "notpresent",
    "htn": "yes",
    "dm": "no",
    "cad": "no",
    "appet": "good",
    "pe": "no",
    "ane": "no",
}


# ── ASIL ARIZA ──────────────────────────────────────────────────────────────
def test_BOS_istek_sonuc_URETMEZ(client):
    r = client.post("/api/ai/disease/kidney", json={})
    assert r.status_code == 422, f"boş formla sonuç üretildi: {r.text[:200]}"
    d = r.json().get("detail", "")
    assert "yeterli klinik veri yok" in d
    assert "yanıltıcı" in d, "kullanıcıya NEDEN reddedildiği açıklanmalı"


def test_bos_istekte_olasilik_DONMEZ(client):
    """Yanıt gövdesinde hiçbir olasılık sayısı olmamalı — kullanıcı %78 görmemeli."""
    r = client.post("/api/ai/disease/kidney", json={})
    assert "prob_ckd" not in r.text and "prob_pct" not in r.text


def test_COK_AZ_alanla_reddedilir(client):
    r = client.post("/api/ai/disease/kidney", json={"age": 48, "bp": 80})
    assert r.status_code == 422


def test_cekirdek_belirtec_YOKSA_reddedilir(client):
    """6 alan dolu ama hiçbiri böbrek işleviyle ilgili değil → tahminde renal sinyal yok."""
    r = client.post("/api/ai/disease/kidney", json={"age": 48, "bp": 80, "su": 0, "sod": 137, "pot": 4.4, "wc": 7800})
    assert r.status_code == 422
    assert "böbrek işlevine dair" in r.json().get("detail", "")


# ── MEŞRU KULLANIM ENGELLENMEMELİ ───────────────────────────────────────────
def test_TAM_form_calisir(client):
    r = client.post("/api/ai/disease/kidney", json=TAM)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d["status"] == "success" and "prob_ckd" in d
    assert d["imputed_fields"] == 0
    assert d["low_evidence"] is False


def test_asgari_gecerli_form_calisir(client):
    """6 alan + çekirdek belirteç → geçmeli (model eksikleri zaten impute etmek üzere tasarlı)."""
    r = client.post("/api/ai/disease/kidney", json={"age": 60, "bp": 90, "sc": 3.1, "bu": 90, "hemo": 9.8, "al": 3})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["filled_fields"] == 6


# ── ŞEFFAFLIK ───────────────────────────────────────────────────────────────
def test_AZ_veriyle_uretilen_sonuc_ISARETLENIR(client):
    """6/24 alanla üretilen tahmin, 24/24 ile aynı güvenle sunulmamalı."""
    r = client.post("/api/ai/disease/kidney", json={"age": 60, "bp": 90, "sc": 3.1, "bu": 90, "hemo": 9.8, "al": 3})
    d = r.json()
    assert d["low_evidence"] is True, "az veriyle üretilen sonuç işaretlenmedi"
    assert d["imputed_fields"] == 18


def test_bos_metin_dolu_SAYILMAZ(client):
    """'   ' gibi boş metinler alan doldurmuş sayılıp kuralı atlatmamalı."""
    r = client.post(
        "/api/ai/disease/kidney", json={"rbc": "  ", "pc": "  ", "pcc": " ", "ba": " ", "htn": " ", "dm": " "}
    )
    assert r.status_code == 422
