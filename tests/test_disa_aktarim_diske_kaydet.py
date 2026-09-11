# -*- coding: utf-8 -*-
# Author: mertaygn
"""GEÇMİŞ DIŞA AKTARIMI — `kaydet=1` diske yazma yolu (2026-09-11 saha arızası).

===============================================================================
NE OLDU
===============================================================================
Sahip: "excel csv indir, tümü pdf indir butonları çalışmıyor seans geçmişi tabında."

Arayüz Tauri v2 **WebView2** penceresinde koşuyor ve indirmeyi
`fetch → blob → <a download>.click()` ile yapıyordu. Bu, WebView2'de ancak uygulama bir
indirme işleyicisi kaydederse çalışır; `launcher/app/src/main.rs` hiçbir
`on_download`/dialog/fs eklentisi KAYDETMİYOR → tıklama sessizce hiçbir şey yapmıyordu.

Rust tarafını düzeltmek launcher'ın yeniden yayınlanmasını gerektirirdi; sahada tek
makine var ve yayın DURDURULDU. Backend zaten AYNI MAKİNEDE koşuyor → `kaydet=1` ile
dosyayı o yazar, arayüz yolunu söyler.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
· `kaydet=1` gerçekten DOSYA ÜRETİYOR mu ve yolunu döndürüyor mu
· hedef dizin TEK KAYNAKTAN geliyor mu (seans CSV'siyle aynı çözücü)
· kayıt yokken "dosya" üretilmiyor mu (eskiden içinde "Veri bulunamadi" yazan bir
  .csv indiriliyordu)
· `kaydet` YOKKEN eski akış indirmesi BOZULMADI mı (web/mobil yolu)
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


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient

    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


@pytest.fixture
def bos_db(tmp_path):
    """BOŞ bir geçmiş veritabanı — FastAPI bağımlılığı geçici olarak buna yönlendirilir.

    ⚠️ NEDEN GEREKLİ: `history_router._app_data_dir` MODÜL SEVİYESİNDE çözülür, yani
    süreç boyunca TEK veritabanı paylaşılır. "Kayıt yokken" davranışını sınayan kapılar,
    daha önce koşan bir testin eklediği satırlar yüzünden SIRAYA BAĞLI hâle geliyordu
    (ölçüldü: veri ekleyen kapı eklendiğinde boş-DB kapısı kırmızıya döndü).
    Bağımlılık ezmesiyle her iki kapı da sıradan bağımsız olur.
    """
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server
    from servers.history_router import get_db

    kok = tmp_path / "bos_gecmis"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    api_server.app.dependency_overrides[get_db] = lambda: db
    yield db
    api_server.app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def masaustu():
    """conftest'in izole ettiği sahte masaüstü — üretimle AYNI çözücüden okunur."""
    import servers.seans_alan_kaydi as sak

    dizin, _ = sak.masaustu_dizini()
    return Path(dizin)


# ============================================================================
# 1. PDF — kaydet=1 gerçekten dosya üretir
# ============================================================================


def test_KRITIK_pdf_kaydet_DOSYA_uretir_ve_YOLUNU_dondurur(istemci, masaustu):
    """MUTASYON: `if kaydet:` dalını sil → KIRMIZI (FileResponse döner, JSON değil).

    Sahadaki etki: masaüstü uygulamasında düğme yine hiçbir şey yapmaz.
    """
    y = istemci.get("/api/history/export_pdf?session_ids=1&kaydet=1")
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["status"] == "success", g
    uretilen = Path(g["yol"])
    assert uretilen.exists(), f"JSON yol dondu ama DOSYA YOK: {uretilen}"
    assert uretilen.stat().st_size > 0, "bos dosya uretildi"
    assert uretilen.read_bytes()[:4] == b"%PDF", "uretilen dosya PDF DEGIL"
    assert g["ad"] == uretilen.name


def test_KRITIK_hedef_dizin_seans_CSVsi_ile_AYNI_cozucuden(istemci, masaustu):
    """⚠️ İKİ KAYNAK OLMASIN: "sahibin dosyaları nereye gider" sorusunun depoda TEK
    cevabı olmalı. Ayrışırsa seans CSV'si bir yere, raporlar başka yere düşer ve
    operatör dosyaları arar.

    MUTASYON: `_diske_kaydet`teki `masaustu_dizini()` çağrısını
    `Path(os.path.expanduser("~/Desktop"))` sabitine çevir → KIRMIZI (izole dizine
    yazmaz; ayrıca süit GERÇEK masaüstüne sızar).
    """
    g = istemci.get("/api/history/export_pdf?session_ids=1&kaydet=1").json()
    assert Path(g["yol"]).parent.resolve() == masaustu.resolve(), (
        f"rapor {Path(g['yol']).parent} altina yazildi, seans CSV'si {masaustu} altina -> IKI KAYNAK"
    )


def test_ayni_ad_iki_kez_istenirse_USTUNE_YAZILMAZ(istemci):
    """İki dışa aktarım arka arkaya yapılırsa ilki kaybolmamalı."""
    a = istemci.get("/api/history/export_pdf?session_ids=1&kaydet=1").json()
    b = istemci.get("/api/history/export_pdf?session_ids=1&kaydet=1").json()
    assert a["yol"] != b["yol"], "ikinci disa aktarim birincinin USTUNE yazdi"
    assert Path(a["yol"]).exists() and Path(b["yol"]).exists()


def test_KRITIK_gecici_PII_pdf_SILINIR(istemci):
    """Rapor tam hasta PII'si taşır; `temp_reports` altındaki geçici kopya kalmamalı.

    MUTASYON: `finally: _safe_unlink(pdf_path)` satırını sil → KIRMIZI.
    """
    from servers import history_router

    g = istemci.get("/api/history/export_pdf?session_ids=1&kaydet=1").json()
    assert g["status"] == "success"
    kalan = list(history_router._REPORTS_DIR.glob("report_*.pdf")) if history_router._REPORTS_DIR.exists() else []
    assert not kalan, f"gecici PII PDF'i diskte KALDI: {[p.name for p in kalan]}"


# ============================================================================
# 2. CSV — boş veri "dosya" üretmez
# ============================================================================


def test_KRITIK_kayit_YOKKEN_dosya_URETILMEZ(bos_db, istemci, masaustu):
    """⚠️ Eskiden içinde "Veri bulunamadi" yazan bir `PEMF_Gecmis.csv` iniyordu.

    Operatör dosyayı AÇANA KADAR kayıt olmadığını anlamıyordu.

    MUTASYON: `if kaydet: return {"status": "bos"...}` dalını sil → KIRMIZI.
    """
    once = set(masaustu.glob("*"))
    y = istemci.get("/api/history/export_csv?kaydet=1")
    assert y.status_code == 200
    g = y.json()
    assert g["status"] == "bos", f"bos veritabaninda {g} dondu"
    assert g.get("mesaj"), "operatore gosterilecek mesaj YOK"
    assert set(masaustu.glob("*")) == once, "kayit yokken DOSYA URETILDI"


def test_KRITIK_VERI_VARKEN_csv_diske_YAZILIR(istemci, masaustu):
    """⚠️ ASIL CSV KAPISI — sahibin bildirdiği düğme tam olarak budur.

    ⚠️ NEDEN AYRI BİR TEST: diğer CSV kapısı BOŞ veritabanıyla koşuyor ve akış her zaman
    "kayıt yok" dalına giriyor; `_diske_kaydet(csv_bytes, ...)` satırına HİÇ ULAŞMIYOR.
    Ölçüldü (2026-09-11 mutasyon turu): o satırı komple silen mutasyon YEŞİL kaldı.
    Veri olmadan yazma yolu test edilemez.

    MUTASYON: `if kaydet: return _diske_kaydet(csv_bytes, "PEMF_Gecmis.csv")` satırını
    sil → KIRMIZI.
    """
    from servers.history_router import get_db

    db = get_db()
    sid = db.start_session(
        treatment_mode="Manuel",
        target_condition="test",
        operator_name="op",
        patient_name="DisaAktarimTesti",
    )
    assert sid, "test seansi olusturulamadi -> kapi hicbir sey olcmuyor"

    y = istemci.get("/api/history/export_csv?kaydet=1")
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["status"] == "success", f"veri VARKEN {g} dondu -> CSV diske yazma yolu KOPUK"

    uretilen = Path(g["yol"])
    assert uretilen.exists() and uretilen.stat().st_size > 0
    assert uretilen.parent.resolve() == masaustu.resolve()
    metin = uretilen.read_text(encoding="utf-8-sig")
    assert "ID" in metin.splitlines()[0], "CSV basligi yok -> icerik bozuk"
    assert str(sid) in metin, "olusturulan seans CSV'de YOK -> yanlis veri yazildi"


def test_veri_varken_kaydet_YOKKEN_hala_CSV_akisi_doner(istemci):
    """Karşıt kanıt: veri varken de eski akış indirmesi bozulmadı."""
    from servers.history_router import get_db

    get_db().start_session(treatment_mode="Manuel", patient_name="AkisTesti")
    y = istemci.get("/api/history/export_csv")
    assert y.status_code == 200
    assert y.headers.get("content-type", "").startswith("text/csv"), (
        f"veri varken {y.headers.get('content-type')} dondu -> akis indirmesi BOZULDU"
    )
    # UTF-8 BOM: Excel (Türkçe Windows) BOM'suz UTF-8'i Windows-1254 sanıp karakterleri bozar.
    assert y.content[:3] == b"\xef\xbb\xbf", "Excel icin UTF-8 BOM kayboldu (Turkce karakterler bozulur)"


# ============================================================================
# 3. ESKİ AKIŞ İNDİRMESİ BOZULMADI (web/mobil yolu)
# ============================================================================


def test_kaydet_YOKKEN_akis_indirmesi_KORUNUR(istemci):
    """Geriye uyumluluk: tarayıcı/mobil hâlâ dosya akışı alır, JSON değil.

    MUTASYON: `kaydet` varsayılanını `1` yap → KIRMIZI (web istemcisi JSON alır ve
    indirme tamamen bozulur).
    """
    y = istemci.get("/api/history/export_pdf?session_ids=1")
    assert y.status_code == 200
    assert y.headers.get("content-type", "").startswith("application/pdf"), (
        f"kaydet YOKKEN {y.headers.get('content-type')} dondu -> akis indirmesi BOZULDU"
    )
    assert y.content[:4] == b"%PDF"


def test_bos_CSV_kaydet_YOKKEN_eski_davranisi_korur(bos_db, istemci):
    """`kaydet` yokken eski `text/plain` yanıtı DEĞİŞMEZ (istemci onu toast'a çevirir)."""
    y = istemci.get("/api/history/export_csv")
    assert y.status_code == 200
    assert y.headers.get("content-type", "").startswith("text/plain")
