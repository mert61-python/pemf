# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10a — yönlendirici iletileri istek dilinde: kimlik / silme / jeton / geçmiş (CSV) / sistem. Başlıksız istek = BUGÜNKÜ Türkçe
(bayt bayt); `X-PEMF-Dil: en` → İngilizce. Kritik güvenceler ("seans, acil durdurma ve sensör izleme etkilenmez") İKİ dilde aynı anlamı taşır.

GERÇEK: modül işlevleri + `ceviri` bağlam değişkeni + gerçek uç (CSV dışa aktarma, TestClient) ; sahte yalnız geçici geçmiş DB'si.
⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz). MUTASYON: katalog TR değeri değişirse / `ceviri.t` çağrısı ham metne dönerse KIRMIZI.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _dilde(dil):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(dil)
    return jeton


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = _dilde(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _t(tr, en, dil):
    return tr if dil == "tr" else en


def test_silme_ve_kimlik_istemleri_iki_dilde(dil):
    from servers import auth, silme_yetkisi

    assert silme_yetkisi.kimliksiz_detay() == _t(
        "Operatör seçin — silmek için önce üst bardan hangi hekim olduğunuzu seçin.",
        "Select an operator — to delete, first choose which veterinarian you are from the top bar.",
        dil,
    )
    assert silme_yetkisi.yabanci_detayi(1) == _t(
        "Yalnız kendi ve sahipsiz kayıtları silebilirsiniz — seçimdeki 1 kayıt başka bir hekime ait; hiçbir kayıt silinmedi.",
        "You can only delete your own and ownerless records — 1 of the selected records belongs to another veterinarian; no records were deleted.",
        dil,
    )
    assert silme_yetkisi.yabanci_detayi(3) == _t(
        "Yalnız kendi ve sahipsiz kayıtları silebilirsiniz — seçimdeki 3 kayıt başka bir hekime ait; hiçbir kayıt silinmedi.",
        "You can only delete your own and ownerless records — 3 of the selected records belong to another veterinarian; no records were deleted.",
        dil,
    )
    # kimlik DB arızası: ARIZA + ÇARE + ACİL DURDUR güvencesi iki dilde
    m = auth.kimlik_db_okunamiyor_metni()
    assert ("ACİL DURDUR ve STOP etkilenmez" in m) if dil == "tr" else ("EMERGENCY STOP and STOP are not affected" in m)
    assert "auth_users.db" in m
    # GÜNLÜK her zaman Türkçe (istek dili EN iken de)
    assert "ACİL DURDUR ve STOP etkilenmez" in auth.kimlik_db_okunamiyor_metni("tr")


def test_jeton_retleri_seans_ve_acil_durdurma_guvencesini_iki_dilde_soyler(dil):
    from servers import jeton

    for metin in (jeton._yetersiz_mesaj(), jeton._kimlik_gerekli_mesaj(), jeton._cevrimdisi_mesaj()):
        if dil == "tr":
            assert "Seans, acil durdurma ve sensör izleme" in metin and "ETKİLENMEZ" in metin
        else:
            assert "Sessions, emergency stop and sensor monitoring are NOT affected" in metin
    assert jeton._cevrimdisi_mesaj().startswith(_t("İnternet bağlantısı yok", "No internet connection", dil))
    assert jeton._yetersiz_mesaj().startswith(_t("Jeton hakkınız bitti", "Your credit allowance has run out", dil))


def test_gecmis_ve_sistem_iletileri_iki_dilde(dil):
    from servers import history_router, system_router

    assert history_router._suruyor_detay() == _t(
        "Seans sürüyor — süren tedavinin kaydı silinemez; önce seansı durdurun.",
        "The session is running — the record of an ongoing session cannot be deleted; stop the session first.",
        dil,
    )
    assert history_router._csv_geri_yukleme_suruyor().startswith(
        _t(
            "Seans geçmişi okunurken bu cihazda geri yükleme yapıldı",
            "A restore was performed on this device while the session history was being read",
            dil,
        )
    )
    assert system_router._db_yanitsiz() == _t(
        "Tıbbi kayıt veritabanı yanıt vermiyor", "The medical record database is not responding", dil
    )


def test_auth_router_json_govdeleri_TR_bayt_bayt_ayni_EN_ingilizce(dil):
    from servers import auth_router
    from utils import ceviri

    g = auth_router._json_govde(ceviri.t("oturum.hata.tokenYerel"))
    k = auth_router._json_govde(ceviri.t("oturum.hata.cokFazlaBasarisiz"), "error", ok=False)
    if dil == "tr":
        assert g == '{"detail":"Token yalniz yerel agdan alinabilir"}'
        assert k == '{"ok":false,"error":"Cok fazla basarisiz deneme. Lutfen biraz bekleyin."}'
    else:
        assert g == '{"detail":"The token can only be obtained from the local network"}'
        assert k == '{"ok":false,"error":"Too many failed attempts. Please wait a moment."}'


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


@pytest.fixture
def dolu_db(tmp_path):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server
    from servers.history_router import get_db

    kok = tmp_path / "i18n_gecmisi"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    sid = db.start_session(treatment_mode="Manuel", patient_name="Mia")
    db.end_session(sid, session_status="completed")
    api_server.app.dependency_overrides[get_db] = lambda: db
    yield db
    api_server.app.dependency_overrides.pop(get_db, None)


def test_CSV_basliklari_istek_dilinde_TR_bayt_bayt_ayni(istemci, dolu_db):
    tr = istemci.get("/api/history/export_csv")
    assert tr.status_code == 200, tr.text
    satirlar = list(csv.reader(io.StringIO(tr.content.decode("utf-8-sig"))))
    assert satirlar[0] == [
        "ID",
        "Hasta",
        "Hedef",
        "Mod",
        "Sure(dk)",
        "Frekans(Hz)",
        "Ayarlanan(mT)",
        "Tarih",
        "Baslangic",
        "Durum",
        "Notlar",
        "Duty(%)",  # T-d (Tezgâh-2 #9): SONA eklendi — ilk 11 sütun bayt bayt aynı
    ]
    en = istemci.get("/api/history/export_csv", headers={"X-PEMF-Dil": "en"})
    assert en.status_code == 200, en.text
    satirlar_en = list(csv.reader(io.StringIO(en.content.decode("utf-8-sig"))))
    assert satirlar_en[0] == [
        "ID",
        "Patient",
        "Target",
        "Mode",
        "Duration(min)",
        "Frequency(Hz)",
        "Set(mT)",
        "Date",
        "Start",
        "Status",
        "Notes",
        "Duty(%)",  # T-d
    ]
    # VERİ: satır sayısı ve kimlik / hasta adı değerleri dilden bağımsız
    assert len(satirlar_en) == len(satirlar)
    assert satirlar_en[1][0] == satirlar[1][0] and satirlar_en[1][1] == satirlar[1][1]
