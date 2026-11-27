# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS2 b · B6 + YS2 d · B7 (YG0 25-11) — seansın dilimli CSV'si uygulamadan indirilebilir; PDF dilim tablosu başlıkları üst üste
binmez; konum ondalığı detay / PDF / CSV'de AYNI.

ÖLÇÜLEN KUSURLAR (`DENETIM\\YAYIN-GUNU.md` YG0 c):
  B6 — dilimli tablo yalnız `/history/{id}/coil_runs.csv` ucundaydı; arayüzde düğme yoktu, uç masaüstü uygulamasının indirme yolunu
       (`kaydet=1` → backend diske yazar, WebView2 indirme işleyicisi yok) da desteklemiyordu.
  B7 — PDF dilim tablosu başlıkları ("Süre (sn" + "Konum…", "En yüksek (mT" + "Model tahmini") dar sütunda komşusunun üstüne
       taşıyordu (ReportLab düz metni hücrede sarmaz); yükseklik 0,75 detayda "0,8", PDF / CSV'de "0.75" (ayırıcı ve yuvarlama farklı).
APARAT: gerçek TreatmentHistoryDB (şifresiz tmp) + gerçek uç (TestClient, cihazın kendisi / LAN) + gerçek PDFReportGenerator.
Masaüstü `conftest._masaustunu_koru` ile sahte dizindir (gerçek masaüstüne YAZILMAZ).
"""

from __future__ import annotations

import time

import capraz
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server as api
    from servers import history_router as hr

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    sid = tdb.start_session(treatment_mode="AI Pro · Petri Kuyu · Kuyu D3", patient_name="Petri 1")
    tdb.end_session(sid, duration_minutes=5, session_status="completed")
    tdb.start_coil_run(sid, 1, frequency_hz=100.0, duty_percent=30.0, started_epoch=1_792_800_000.0)
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    try:
        yield type("O", (), {"tdb": tdb, "sid": sid, "api": api})
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        tdb.close()


def test_KRITIK_B6_coil_runs_csv_CIHAZ_EKRANINDAN_kaydet_1_masaustune_YAZAR(o):
    import servers.seans_alan_kaydi as sak

    c = TestClient(o.api.app, client=("127.0.0.1", 53217))
    r = c.get(f"/api/history/{o.sid}/coil_runs.csv?kaydet=1")
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("application/json"), (
        "masaüstü uygulamasının indirme yolu (kaydet=1) desteklenmiyor: uç CSV baytı döndü (WebView2 dosyayı alamaz)"
    )
    g = r.json()
    assert g["status"] == "success" and g["ad"] == f"PEMF_Session_{o.sid}_Coils.csv", g
    dizin, _ = sak.masaustu_dizini()  # conftest: sahte masaüstü
    yazilan = dizin / g["ad"]
    assert yazilan.is_file() and yazilan.read_bytes().startswith(b"\xef\xbb\xbf"), "dosya sahte masaüstüne yazılmadı"


def test_KARSIT_B6_LAN_istegi_kaydet_1_gonderse_de_dosyayi_YANITTA_alir(o):
    c = TestClient(o.api.app, client=("192.168.137.20", 53218))
    r = c.get(f"/api/history/{o.sid}/coil_runs.csv?kaydet=1")
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("text/csv"), (
        "LAN isteği sunucunun masaüstüne yazdırabildi (D3.05)"
    )
    assert r.content.startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize(
    ("deger", "tr", "en"),
    [(0.75, "0,75", "0.75"), (0.754, "0,75", "0.75"), (10.5, "10,5", "10.5"), (35.0, "35", "35"), (9, "9", "9")],
)
def test_KRITIK_B7_konum_sayisi_EN_COK_2_ondalik_ayirici_DILDE(deger, tr, en):
    from servers import sensor_konumu as sk
    from utils import ceviri

    for d, beklenen in (("tr", tr), ("en", en)):
        jeton = ceviri.istek_dili_var.set(d)
        try:
            assert sk.cm_metni(deger) == beklenen, (d, deger)
        finally:
            ceviri.istek_dili_var.reset(jeton)


def test_KRITIK_B7_konum_metni_PDF_CSV_ayni_bicim(dil):
    from servers import sensor_konumu as sk

    d = {"serbest": False, "sol_cm": 35, "on_cm": 9, "yukseklik_cm": 0.75}
    assert sk.konum_metni(d, "serbest") == ("35 / 9 / 0,75" if dil == "tr" else "35 / 9 / 0.75")


def test_KRITIK_B7_PDF_dilim_basliklari_SUTUNUNA_SIGAR_ust_uste_binmez(tmp_path, monkeypatch, dil):
    """Her başlık hücresinin çizim genişliği kendi sütununun iç genişliğini AŞMAZ (düz metin sarılmaz → taşar; Paragraph satır
    satır sarılır). İki dilde (EN başlıklar daha uzun)."""
    capraz.paket_yoksa_atla("reportlab")
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from servers import sensor_konumu as sk
    from utils import pdf_report_generator as prg

    monkeypatch.setattr(sk, "kabin_noktasi", lambda s, o_, y: None)
    g = prg.PDFReportGenerator(app_data_dir=tmp_path)
    sid = g.db.start_session(treatment_mode="Manuel", patient_name="Pamuk")
    g.db.end_session(sid, session_status="stopped")
    t0 = time.time() - 120.0
    g.db.set_session_meta(
        sid, started_epoch=t0, ended_epoch=t0 + 90.0
    )  # seans 90 sn → konum girişinden sonra bir dilim
    g.db.sensor_konumu_ekle(sid, t0 + 10.0, serbest=False, sol_cm=35, on_cm=9, yukseklik_cm=0.75)
    eklenen: list = []
    g._add_sensor_konum_table(eklenen, sid)
    tablo = next(x for x in eklenen if isinstance(x, prg.Table))
    dolgu = 12.0  # ReportLab hücre iç dolgusu: sol 6 + sağ 6
    tasan = []
    for i, (h, gen) in enumerate(zip(tablo._cellvalues[0], tablo._colWidths)):
        ic = gen - dolgu
        if isinstance(h, str):
            w = stringWidth(h, g.unicode_font_bold, 8)
            if w > ic + 0.01:
                tasan.append((i, h, round(w, 1), round(ic, 1)))
        else:
            h.wrap(ic, 10_000)
            for satir in h.blPara.lines:  # (boşluk, kelimeler) — boşluk < 0: satır (tek kelime) sütundan GENİŞ
                bosluk = satir[0] if isinstance(satir, tuple) else getattr(satir, "extraSpace", 0)
                if bosluk < -0.01:
                    tasan.append((i, getattr(h, "text", h), round(ic - bosluk, 1), round(ic, 1)))
    assert not tasan, f"PDF dilim tablosu başlığı sütununa sığmıyor (komşunun üstüne taşar): {tasan}"
    # Konum hücresi PDF'te de dile göre (detayla aynı) — ilk dilim girişten önceki "serbest" süre, son dilim girişin konumu
    assert tablo._cellvalues[-1][2] == ("35 / 9 / 0,75" if dil == "tr" else "35 / 9 / 0.75")
