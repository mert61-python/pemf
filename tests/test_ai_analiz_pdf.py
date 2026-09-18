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

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")

fitz = pytest.importorskip("fitz", reason="PyMuPDF yok -> PDF metni cikarilamaz")


@pytest.fixture
def istemci():
    """⚠️ `client=("127.0.0.1", …)`: bu uç AYRICALIKLIDIR (PII dışa aktarımı) ve LAN
    muafiyeti YOKTUR — loopback ya da geçerli token ister. TestClient varsayılanı
    "testclient" host'udur ve kapıdan GEÇMEZ. Aynı desen
    `test_operator_identity_server_side.py`de de kullanılıyor.
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
    # "Ortalama gap", "156,7" ve "cuda" YALNIZ result_detail'de var (özette geçmiyor).
    assert "Ortalama gap" in metin, f"detay ETIKETI yok:\n{metin[:500]}"
    assert "156,7" in metin, f"detay DEGERI yok (ondalik ayirac virgul olmali):\n{metin[:500]}"
    assert "cuda" in metin, "cihaz alani raporda yok"


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

    ogeler = analiz_pdf_ogeleri({"result_detail": {"seri": list(range(30))}})
    metin = next(o["aciklama"] for o in ogeler if o["etiket"] == "seri")
    assert "[" not in metin and "]" not in metin, f"Python sozdizimi sizdi: {metin[:60]}"
    assert "(30 öğe)" in metin, f"uzun liste kirpildigi SOYLENMIYOR: {metin[:80]}"
    assert metin.startswith("0, 1, 2"), metin[:40]


def test_uzun_deger_KIRPILIR_ama_SOYLENIR():
    """⚠️ Sessizce atmak yerine "… (toplam N karakter)" demek: bilginin var olduğunu söyler."""
    from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

    ogeler = analiz_pdf_ogeleri({"result_detail": {"not": "y" * 5000}})
    metin = next(o["aciklama"] for o in ogeler if o["etiket"] == "not")
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
# 4. ⚠️ AYRICALIKLI UÇ — PII DIŞA AKTARIMI LAN'A AÇIK OLAMAZ
# ============================================================================
#
# ⚠️ BU KAPI DENETİMDE DOĞDU (2026-09-12): uç ilk yazımda KORUMASIZDI. Oysa hasta ADINI ve
# analizin TÜM sayısal detayını tek dosyada dışarı verir — niteliksel olarak
# `/api/data/export` ile aynı sınıf (bkz. apps/backend/servers/auth.py "AYRICALIKLI UÇLAR" başlığı).
# Kapısız hâlde klinik WiFi'sindeki HERHANGİ bir cihaz, kimlik göstermeden id'leri gezip
# tüm AI geçmişini PDF olarak toplayabilirdi. Klinik hotspot parolası her makinede aynı ve
# pakette dağıtıldığı için "güvenli yerel ağ" varsayımı bu uç için GEÇERLİ DEĞİLDİR.


def test_KRITIK_PDF_ucu_AYRICALIKLI_kapidan_geciyor():
    """MUTASYON: `_enforce_privileged(request)` satırını sil → KIRMIZI.

    ⚠️ Çıpa AST'ye pinli: uç gövdesinin İLK ifadesi bu çağrı olmalı. Yorumda anılması
    ya da başka bir uçta bulunması yetmez (bu deponun "yorum kapıyı kandırdı" sınıfı).
    """
    import ast

    agac = ast.parse((KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8"))
    hedef = None
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == "ai_analiz_pdf":
            hedef = d
            break
    assert hedef is not None, "ai_analiz_pdf ucu bulunamadi -> capa bayatladi"

    cagrilar = [n.func.id for n in ast.walk(hedef) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "_enforce_privileged" in cagrilar, (
        "AI analiz PDF ucu AYRICALIKLI kapidan GECMIYOR -> LAN'daki kimliksiz bir cihaz "
        "tum AI gecmisini PDF olarak toplayabilir (hasta adi + tum sayisal detay)"
    )
    # ⚠️ Kapı GÖVDENİN BAŞINDA olmalı: sonra çağrılırsa, ondan önceki DB okuması zaten
    # yapılmış olur ve zamanlama/hata mesajı üzerinden kayıt varlığı sızabilir.
    # ⚠️ Gövdenin ilk ÖĞESİ docstring'dir; kapı ondan SONRAKİ ilk ifade olmalı.
    govde = [d for d in hedef.body if not (isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant))]
    assert govde, "uc govdesi bos"
    ilk = govde[0]
    ilk_ifade = ilk.value if isinstance(ilk, ast.Expr) else None
    assert (
        isinstance(ilk_ifade, ast.Call)
        and isinstance(ilk_ifade.func, ast.Name)
        and ilk_ifade.func.id == "_enforce_privileged"
    ), (
        "ayricalikli kapi govdenin BASINDA degil. Sonra cagrilirsa ondan onceki DB okumasi "
        "zaten yapilmis olur ve zamanlama/hata uzerinden kayit varligi sizabilir."
    )


def test_KRITIK_LAN_istemcisi_kimliksiz_PDF_ALAMAZ(analiz):
    """⚠️ KARŞIT KANIT — kapı GERÇEKTEN çalışıyor mu (kaynakta var olması yetmez).

    Klinik WiFi'sindeki kimliksiz bir cihaz (LAN adresi, token yok) bu ucu ÇAĞIRAMAMALI.
    LAN muafiyeti burada geçerli değildir: hotspot parolası her makinede aynı ve pakette
    dağıtılıyor, yani "güvenli yerel ağ" varsayımı bu uç için yanlıştır.

    MUTASYON: `_enforce_privileged(request)` satırını sil → KIRMIZI (200 + PDF döner).
    """
    from fastapi.testclient import TestClient
    from servers import api_server

    _, sid = analiz
    # 192.168/16 = tipik klinik LAN; loopback DEĞİL, token DA yok.
    with TestClient(api_server.app, client=("192.168.1.77", 50000)) as lan:
        y = lan.get(f"/api/ai/log/{sid}/pdf")
    assert y.status_code in (401, 403), (
        f"LAN'daki KIMLIKSIZ istemci hasta PII'si iceren PDF'i ALDI (HTTP {y.status_code}) "
        "-> tum AI gecmisi id gezilerek toplanabilir"
    )
    assert y.content[:4] != b"%PDF", "reddedildi ama PDF govdesi yine de dondu"
