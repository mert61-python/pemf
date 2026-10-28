# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI ANALİZ RAPORU PDF — ev sahibi paylaşımı (sahip isteği 2026-09-12).

===============================================================================
NEDEN EKLENDİ
===============================================================================
Sahip: "pet owner için [4 önerinin] hepsini yap."

Ev sahibi profili analiz yapabiliyordu ama sonucu veterinerine GÖNDEREMİYORDU: PDF
üretimi yalnız SEANS kayıtları içindi. Ekran görüntüsüyle paylaşmak hem eksik (sayısal
detay kaybolur) hem de kayıtsızdı.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
· Uç GERÇEK bir PDF üretiyor mu (uçtan uca: DB kaydı → PDF baytları)
· Türkçe karakterler DOĞRU mu (İş 3'teki düzeltmeden yararlanıyor mu)
· `result_detail` HETEROJEN olduğu için çökme YOK mu (her modül kendi şeklini yazar)
· base64 GÖRSELLER rapora sızmıyor mu (40 KB'lık dizgi PDF'i kullanılamaz kılar)
· Olmayan kayıtta 404 mü (500 değil — "yok" ile "arızalı" ayrı şeyler)
· Geçici PII PDF'i diskte KALMIYOR mu
"""

from __future__ import annotations

import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

fitz = capraz.paket_yoksa_atla("fitz", sebep="PyMuPDF yok -> PDF metni cikarilamaz")


@pytest.fixture
def istemci():
    """`client=("127.0.0.1", …)`: cihazın kendi ekranı (`kaydet=1` yalnız orada masaüstüne yazar — D3.05). TestClient varsayılanı
    "testclient" host'u IP değildir (yerel sayılmaz). Erişim sınıfı A-02: LAN token'sız, uzak kimlik ister (bölüm 4).
    """
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app, client=("127.0.0.1", 51234)) as c:
        yield c


@pytest.fixture
def analiz(tmp_path, monkeypatch):
    """İzole DB + içinde Türkçe karakterli, HETEROJEN detaylı bir AI analizi."""
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server

    kok = tmp_path / "ai_gecmis"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: db)
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)

    sid = db.add_ai_analysis(
        mode="pet_owner",
        module_id="cell_scratch",
        module_label="Yara Kapanma (Scratch)",
        patient_name="Mia",
        operator_email="sahip@ornek.com",
        input_type="image",
        result_summary="Kapanma %42 · 318 hücre",
        result_detail={
            "closure_pct": 42.3,
            "mean_gap_um": 156.7,
            "n_cells": 318,
            "device": "cuda",
            # ⚠️ GÖRSEL ALANLARI: rapora SIZMAMALI (aşağıdaki kapı).
            "closure_image_base64": "A" * 5000,
            "overlay_b64": "B" * 5000,
            # ⚠️ HETEROJEN ŞEKİL: liste + iç içe sözlük — modüller böyle yazıyor.
            "per_well": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "meta": {"eşik": 0.5, "sürüm": "v3"},
        },
        confidence=0.87,
    )
    return db, sid


# ============================================================================
# 1. ⚠️ ASIL KAPI — GERÇEK PDF ÜRETİLİYOR VE OKUNABİLİYOR
# ============================================================================


def test_KRITIK_analiz_PDFi_uretilir_ve_TURKCE_dogru(istemci, analiz):
    """MUTASYON: `/api/ai/log/{id}/pdf` ucunu kaldır → KIRMIZI (404).

    Sahadaki etki: ev sahibi analiz sonucunu veterinerine gönderemez.
    """
    _, sid = analiz
    y = istemci.get(f"/api/ai/log/{sid}/pdf")
    assert y.status_code == 200, y.text[:300]
    assert y.content[:4] == b"%PDF", "uretilen dosya PDF DEGIL"

    with fitz.open(stream=y.content, filetype="pdf") as d:
        metin = "\n".join(p.get_text() for p in d)
    assert "Mia" in metin, f"hasta adi raporda yok:\n{metin[:400]}"
    assert "Yara Kapanma" in metin, "modul adi raporda yok"
    # ⚠️ İŞ 3'ÜN DEVAMI: Type1 notdef izi burada da olmamalı (aynı yazı tipi yolu).
    assert "ÇalIImalarI" not in metin and "KapanmaI" not in metin, "Turkce karakter BOZUK"


def test_KRITIK_base64_GORSELLER_rapora_SIZMAZ(istemci, analiz):
    """⚠️ `result_detail` içinde 40 KB'lık base64 görseller var. Onları "açıklama" diye
    yazdırmak raporu kilometrelerce uzatır ve OKUNAMAZ kılar — paylaşım özelliğini
    doğduğu anda öldürürdü.

    MUTASYON: `_gizli_mi` süzgecini kaldır → KIRMIZI (PDF şişer, AAAA… görünür).
    """
    _, sid = analiz
    y = istemci.get(f"/api/ai/log/{sid}/pdf")
    with fitz.open(stream=y.content, filetype="pdf") as d:
        metin = "\n".join(p.get_text() for p in d)
    assert "AAAAAAAAAA" not in metin, "base64 gorsel dizgisi rapora SIZDI"
    assert "BBBBBBBBBB" not in metin
    assert len(y.content) < 400_000, f"PDF sismis: {len(y.content)} bayt"


def test_KRITIK_sayisal_detaylar_raporda_VAR(istemci, analiz):
    """⚠️ Paylaşımın DEĞERİ sayılarda: veteriner yalnız "Kapanma %42 · 318 hücre" özetini
    görecekse, paylaşımın ekran görüntüsünden farkı kalmaz.

    ⚠️ ÇIPA YALNIZ `result_detail`DE OLAN DEĞERE PİNLİ. İlk yazımda "Kapanma"/"42"/"318"
    aranıyordu ve MUTASYONDA YEŞİL KALDI: o üçü `result_summary` metninde de geçiyor, yani
    kapı detay bölümünü değil ÖZETİ ölçüyordu.

    MUTASYON: `detay = kayit.get("result_detail")` yerine `detay = None` → KIRMIZI.
    """
    _, sid = analiz
    y = istemci.get(f"/api/ai/log/{sid}/pdf")
    with fitz.open(stream=y.content, filetype="pdf") as d:
        metin = "\n".join(p.get_text() for p in d)
    # "Ortalama yara aralığı" ve "156,7" YALNIZ result_detail'de var (özette geçmiyor).
    assert "Ortalama yara aralığı" in metin, f"detay ETIKETI yok:\n{metin[:500]}"
    assert "156,7" in metin, f"detay DEGERI yok (ondalik ayirac virgul olmali):\n{metin[:500]}"
    # 2026-10-18 (sahip: okuyucu veteriner + hayvan sahibi): teknik cihaz alanı ("cuda") rapora GİRMEZ.
    assert "cuda" not in metin, "teknik cihaz alani rapora sizdi"


# ============================================================================
# 2. HETEROJEN VERİ — HİÇBİR MODÜL ÇÖKERTMEMELİ
# ============================================================================


@pytest.mark.parametrize(
    "detay",
    [
        {},
        None,
        {"a": None},
        {"liste": list(range(500))},
        {"ic": {"derin": {"daha": {"cok": 1}}}},
        {"metin": "x" * 10000},
        {"sayi": float("nan")},
        {"karisik": [1, "iki", {"uc": 3}, None]},
    ],
)
def test_KRITIK_heterojen_detay_COKERTMEZ(detay):
    """⚠️ `result_detail` her modülde FARKLI şekildedir (petri kuyuları, CT sınıfı, ses
    sınıfları...). Tek bir şekil varsaymak, o modülde raporu 500'e düşürürdü.

    MUTASYON: `_metne_cevir`deki tip dallarından birini sil → KIRMIZI.
    """
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    ogeler = analiz_pdf_ogeleri({"patient_name": "X", "result_detail": detay})
    assert isinstance(ogeler, list)
    for o in ogeler:
        assert isinstance(o.get("etiket"), str)
        assert isinstance(o.get("aciklama"), str)
        assert len(o["aciklama"]) < 500, "kirpma uygulanmamis"


def test_KRITIK_liste_OKUNUR_bicimde_yazilir():
    """⚠️ Ham `str([1, 2, 3])` çıktısı rapora Python sözdizimi sızdırır ve 500 elemanlı bir
    dizide okunamaz bir duvar üretir. Liste dalı virgülle ayırır ve uzun listeyi
    "… (N öğe)" diye SÖYLEYEREK kırpar.

    ⚠️ İlk yazımda yalnız "çökmedi + kısa" ölçülüyordu ve MUTASYONDA YEŞİL KALDI: `str()`
    yedeği de kısa bir metin üretiyor. Kapı artık BİÇİMİ ölçer.

    MUTASYON: `if isinstance(deger, (list, tuple)):` dalını sil → KIRMIZI.
    """
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    # 2026-10-18: bilinmeyen alan adı HAM yazılmaz → bilinen bir liste alanı ("warnings" → "Uyarılar").
    ogeler = analiz_pdf_ogeleri({"result_detail": {"warnings": list(range(30))}})
    metin = next(o["aciklama"] for o in ogeler if o["etiket"] == "Uyarılar")
    assert "[" not in metin and "]" not in metin, f"Python sozdizimi sizdi: {metin[:60]}"
    assert "(30 öğe)" in metin, f"uzun liste kirpildigi SOYLENMIYOR: {metin[:80]}"
    assert metin.startswith("0, 1, 2"), metin[:40]


def test_uzun_deger_KIRPILIR_ama_SOYLENIR():
    """⚠️ Sessizce atmak yerine "… (toplam N karakter)" demek: bilginin var olduğunu söyler."""
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    ogeler = analiz_pdf_ogeleri({"result_detail": {"not": "y" * 5000}})
    metin = next(o["aciklama"] for o in ogeler if o["etiket"] == "Not")
    assert "toplam 5000 karakter" in metin, metin[-60:]


# ============================================================================
# 3. HATA YOLLARI — "YOK" İLE "ARIZALI" AYRI ŞEYLER
# ============================================================================


def test_KRITIK_olmayan_analiz_404_doner_500_DEGIL(istemci, analiz):
    """⚠️ 500 dönmek istemciye "geçici arıza, tekrar dene" dedirtir; kayıt silinmişse
    sonsuz yeniden deneme olur (bu depoda daha önce yaşandı — DENETIM P3)."""
    y = istemci.get("/api/ai/log/999999/pdf")
    assert y.status_code == 404, f"beklenen 404, gelen {y.status_code}"


def test_KRITIK_gecici_PII_pdf_SILINIR(istemci, analiz, tmp_path):
    """Rapor hasta verisi taşır; `temp_reports` altındaki geçici kopya kalmamalı."""
    _, sid = analiz
    y = istemci.get(f"/api/ai/log/{sid}/pdf?kaydet=1")
    assert y.status_code == 200, y.text[:200]
    kalan = list((tmp_path / "ai_gecmis" / "temp_reports").glob("ai_*.pdf"))
    assert not kalan, f"gecici PII PDF'i diskte KALDI: {[p.name for p in kalan]}"


# ============================================================================
# 4. ERİŞİM SINIFI — D3.04 · A-02 (sahibin kendi seçeneği, 2026-10-01): LAN TOKEN'SIZ, uzak kural DEĞİŞMEZ
# ============================================================================
#
# ⚠️ BİLİNÇLİ SÖZLEŞME DEĞİŞİKLİĞİ: bu bölüm 2026-09-12'de "PDF ucu LAN'a açık olamaz" diye kurulmuştu (`_enforce_privileged`).
# Sahip A-02 ile AI geçmişi listesi VE tek kaydın PDF'ini LAN'dan token'sız yaptı (A-01 yönünde tutarlılık: liste ucu zaten LAN'a
# açıktı, tek kaydın PDF'i ondan sıkı olamazdı). Tünel / uzak istek kimlik ister. Ayrıntılı kapı:
# tests/test_D3_04_ai_gecmisi_liste_ve_PDF_AYNI_erisim_sinifi_A02.py


def test_A02_PDF_ucu_LAN_icin_AYRICALIKLI_kapiya_BAGLANMAZ():
    """A-02 pini: uç `_enforce_privileged` çağırmaz (LAN'ı da reddederdi). Geri eklenirse sahip kararına aykırı → KIRMIZI."""
    import ast

    agac = ast.parse((KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8"))
    hedef = next(
        (
            d
            for d in ast.walk(agac)
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == "ai_analiz_pdf"
        ),
        None,
    )
    assert hedef is not None, "ai_analiz_pdf ucu bulunamadi -> capa bayatladi"
    cagrilar = [n.func.id for n in ast.walk(hedef) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "_enforce_privileged" not in cagrilar, (
        "A-02: tek kaydın PDF'i LAN'dan token'sız olmalı (liste ucuyla aynı sınıf)"
    )


def test_KRITIK_A02_LAN_kimliksiz_PDF_ALIR_tunel_kimliksiz_ALAMAZ(analiz, monkeypatch):
    import servers.auth as auth
    from fastapi.testclient import TestClient
    from servers import api_server

    monkeypatch.setattr(auth, "_require", True)  # üretim profili: device.env / launcher PEMF_REQUIRE_AUTH=1

    _, sid = analiz
    with TestClient(api_server.app, client=("192.168.1.77", 50000)) as lan:
        y = lan.get(f"/api/ai/log/{sid}/pdf")
    assert y.status_code == 200 and y.content[:4] == b"%PDF", f"A-02: LAN PDF'i alamadı (HTTP {y.status_code})"
    with TestClient(api_server.app, client=("127.0.0.1", 50001)) as tunel:
        u = tunel.get(f"/api/ai/log/{sid}/pdf", headers={"cf-connecting-ip": "203.0.113.4", "cf-ray": "9a-IST"})
    assert u.status_code == 401 and u.content[:4] != b"%PDF", f"tünelden KİMLİKSİZ PDF verildi (HTTP {u.status_code})"
