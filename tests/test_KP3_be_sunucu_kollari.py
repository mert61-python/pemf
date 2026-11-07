# -*- coding: utf-8 -*-
"""KP-3 C · backend sunucu modüllerinin kapsanmayan kolları — her test bir DAVRANIŞ iddiası (uçlar doğrudan çağrılır):

- `audit_log`: istemci adresi çözülemezse boş; tedavi DB'si alınamazsa / yoksa iz yazılamadı (False + hata günlüğü, fırlatmaz); yazım
  katmanı patlarsa False; kimlik çözümü patlarsa iz SAHİPSİZ yazılır ve beyan `kanitsiz_beyan` olarak saklanır.
- `update_router`: güncelleme yöneticisi yok / uygulama / geri alma patlarsa okunur yanıt (500 + çeviri), istisna sızmaz.
- `session_router`: belirsiz ad eşleşmesi uyarısı üretilemezse not akışı bozulmaz (boş sözlük); tedavi DB'si yokken not 503; aktif seans
  yokken parametre değişikliği 409.
- `seans_alan_kaydi`: sayıya çevrilemeyen ölçüm yok sayılır; satır yazılamazsa / dosya kapanamazsa seans etkilenmez (günlük).
- `kvkk_anonimlestirme`: denetim noktası yapılamazsa her DB için uyarı, anonimleştirme sonucu değişmez.
- `coil_run_tracker`: enjekte edilmemiş varsayılanlar güvenli no-op; sayıya çevrilemeyen bobin kimliği yok sayılır; DB yokken koşu
  açılmaz; DB koşu açamazsa durum kirlenmez; özet yazılamasa da koşu kapanır; DB alıcısı patlasa da fırlatmaz.
- `patient_router`: PEMF_REQUIRE_PATIENT_AUTH=1 iken kimlik altyapısı yoksa 503, jeton yanlışsa 401, doğruysa geçer; hasta DB'si yokken
  liste / ekleme / toplu silme / tümünü silme 500; boş seçim 400; DB'nin ValueError'ı 400.
- `stm32_kimlik`: boş banner → kimlik yok; çeviri katmanı patlarsa E-stop "kart yanıtsız" metni Türkçe sabite düşer.

Sahte EN ALT katta: DB nesneleri, enjekte alıcılar, sır / kimlik işlevleri (`servers.auth` öznitelikleri), CSV yazıcı.
"""

from __future__ import annotations

import asyncio
import json
import logging
import types

import pytest
from fastapi import HTTPException
from servers import api_server as api
from servers import audit_log, auth, coil_run_tracker, patient_router, seans_alan_kaydi, session_router, update_router
from utils import ceviri


class _Istek:
    def __init__(self, basliklar=None, sorgu=None, host="127.0.0.1"):
        self.headers = dict(basliklar or {})
        self.query_params = dict(sorgu or {})
        self.client = types.SimpleNamespace(host=host)


# ── audit_log ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_denetim_izi_adres_db_ve_yazim_hatalari_firlatmaz(monkeypatch, caplog):
    class _BozukIstek:
        @property
        def client(self):
            raise RuntimeError("soket kapandı")

    assert audit_log.istemci_ip(_BozukIstek()) == ""

    def _db_patla():
        raise RuntimeError("tedavi DB'si açılamadı")

    monkeypatch.setattr(api, "_get_treatment_db", _db_patla)
    assert audit_log._db() is None
    with caplog.at_level(logging.ERROR, logger=audit_log.logger.name):
        assert audit_log.yaz(None, "patient.delete") is False
    assert any("DENETIM IZI YAZILAMADI (patient.delete)" in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(audit_log, "_db", lambda: types.SimpleNamespace(denetim_yaz=lambda *a, **k: True))
    from utils import dongu_disi_yazim

    def _yazim_patla(*a, **k):
        raise OSError("disk dolu")

    monkeypatch.setattr(dongu_disi_yazim, "calistir", _yazim_patla)
    assert audit_log.yaz(None, "patient.delete") is False


def test_kimlik_cozumu_patlarsa_iz_sahipsiz_ve_beyan_ayrica_saklanir(monkeypatch):
    def _patla(*a, **k):
        raise RuntimeError("kimlik DB'si kilitli")

    monkeypatch.setattr(auth, "cozumlenmis_operator", _patla)
    yazilan: list = []
    monkeypatch.setattr(audit_log, "yaz", lambda request, event_type, **kw: yazilan.append((event_type, kw)) or True)
    assert audit_log.kimlikli_yaz(_Istek(), "patient.delete", beyan="dr.ayse@klinik.test", detail={"adet": 2}) is True
    olay, kw = yazilan[0]
    assert olay == "patient.delete" and kw["operator_email"] == ""
    assert kw["detail"] == {"adet": 2, "kanitsiz_beyan": "dr.ayse@klinik.test"}


# ── update_router ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_guncelleme_uclari_yonetici_patlarsa_okunur_yanit(monkeypatch):
    from servers import update_manager

    def _patla(*a, **k):
        raise RuntimeError("latest.json okunamadı")

    monkeypatch.setattr(update_manager, "get_status", _patla)
    monkeypatch.setattr(update_manager, "apply_update", _patla)
    monkeypatch.setattr(update_manager, "rollback", _patla)
    monkeypatch.setattr(update_router, "_yetki_kapisi", lambda request: None)
    assert asyncio.run(update_router.update_status()) == {
        "checked": False,
        "available": False,
        "error": "update_manager yok",
    }
    y = asyncio.run(update_router.update_apply(_Istek()))
    assert y.status_code == 500 and json.loads(y.body) == {"detail": ceviri.t("guncelleme.hata.uygulanamadi")}
    y = asyncio.run(update_router.update_rollback(_Istek()))
    assert y.status_code == 500 and json.loads(y.body) == {"detail": ceviri.t("guncelleme.hata.rollbackUygulanamadi")}


# ── session_router ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_belirsiz_ad_uyarisi_uretilemezse_not_akisi_bozulmaz(caplog):
    def _patla(*a, **k):
        raise RuntimeError("session_events kilitli")

    db = types.SimpleNamespace(record_session_event=_patla)
    with caplog.at_level(logging.WARNING):
        assert session_router._ad_eslesmesi_uyarisi(db, 5, 2) == {}
    assert any("belirsiz ad eslesmesi uyarisi uretilemedi" in r.getMessage() for r in caplog.records)


def test_db_yokken_not_503_aktif_seans_yokken_parametre_409(monkeypatch):
    monkeypatch.setattr(api, "_get_treatment_db", lambda: None)
    with pytest.raises(HTTPException) as e:
        session_router.save_session_notes(session_router.SessionNotesPayload(notes="not"), _Istek())
    assert e.value.status_code == 503 and e.value.detail == ceviri.t("seans.hata.dbHazirDegil")
    monkeypatch.setattr(api, "_active_session", {"is_active": False})
    with pytest.raises(HTTPException) as e:
        session_router.parametre_guncelle(session_router.ParametreGuncellePayload())
    assert e.value.status_code == 409 and e.value.detail == ceviri.t("seans.hata.aktifYok")


# ── seans_alan_kaydi ──────────────────────────────────────────────────────────────────────────────────────────────────
class _BozukYazici:
    def __init__(self):
        self.satirlar: list = []

    def writerow(self, satir):
        raise OSError("disk dolu")


class _BozukDosya:
    def flush(self):
        pass

    def close(self):
        raise OSError("tutamaç kaybedildi")


def test_alan_kaydi_gecersiz_olcum_yazim_ve_kapanis_hatalari_seansi_etkilemez(caplog):
    k = seans_alan_kaydi.SeansAlanKaydi()
    k._aktif = True
    k._yazici = _BozukYazici()
    k._dosya = _BozukDosya()
    k.olcum(1, "olculmedi")
    assert k._satir == 0, "sayıya çevrilemeyen ölçüm sayıldı"
    with caplog.at_level(logging.ERROR, logger=seans_alan_kaydi.logger.name):
        k.olcum(1, 2.5)
        assert k.zirve() == 2.5, "yazım hatası ölçümü bellekten de düşürdü"
        k._yazici = None  # özet yazıcısı yok, kapanış dosyası patlar
        k.seans_bitti("test")
    mesajlar = [r.getMessage() for r in caplog.records]
    assert "seans alan kaydı satırı yazılamadı" in mesajlar
    assert "seans alan kaydı kapatılamadı" in mesajlar
    assert k._aktif is False


# ── kvkk_anonimlestirme ───────────────────────────────────────────────────────────────────────────────────────────────
def test_kvkk_denetim_noktasi_yapilamazsa_her_db_icin_uyari(caplog):
    from services import kvkk_anonimlestirme as kv

    class _KilitliDb:
        def _get_connection(self):
            raise RuntimeError("açık okuyucu var")

    with caplog.at_level(logging.WARNING, logger=kv.logger.name):
        kv._kalinti_temizle(_KilitliDb(), _KilitliDb())
    mesajlar = [r.getMessage() for r in caplog.records if "denetim noktasi yapilamadi" in r.getMessage()]
    assert len(mesajlar) == 2 and any("hasta DB" in m for m in mesajlar) and any("tedavi DB" in m for m in mesajlar)


# ── coil_run_tracker ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def bobin_izi(monkeypatch):
    monkeypatch.setattr(coil_run_tracker, "_active_coil_runs", {})
    monkeypatch.setattr(coil_run_tracker, "_coil_run_stats", {})
    return coil_run_tracker


def test_bobin_kosusu_varsayilanlar_ve_acilis_kollari(bobin_izi, monkeypatch, caplog):
    assert bobin_izi._default_session_id() is None and bobin_izi._default_treatment_db() is None
    monkeypatch.setattr(bobin_izi, "_db_session_id_getter", lambda: 42)
    monkeypatch.setattr(
        bobin_izi, "_treatment_db_getter", lambda: pytest.fail("geçersiz bobin kimliğinde DB'ye gidildi")
    )
    bobin_izi._begin_coil_run_govde("bobin-x", 10, 50, 0, 1.0, "stm")
    monkeypatch.setattr(bobin_izi, "_treatment_db_getter", lambda: None)
    bobin_izi._begin_coil_run_govde(3, 10, 50, 0, 1.0, "stm")
    assert bobin_izi._active_coil_runs == {}, "DB yokken koşu açıldı"

    def _ac_patla(*a, **k):
        raise RuntimeError("coil_runs tablosu kilitli")

    monkeypatch.setattr(bobin_izi, "_treatment_db_getter", lambda: types.SimpleNamespace(start_coil_run=_ac_patla))
    with caplog.at_level(logging.DEBUG, logger=bobin_izi.__name__):
        bobin_izi._begin_coil_run_govde(3, 10, 50, 0, 1.0, "stm")
    assert bobin_izi._active_coil_runs == {} and bobin_izi._coil_run_stats == {}
    assert any("_begin_coil_run hatasi (coil=3)" in r.getMessage() for r in caplog.records)


def test_bobin_kosusu_kapanis_ozet_hatasi_ve_db_alici_hatasi(bobin_izi, monkeypatch, caplog):
    bobin_izi._finish_coil_run_govde("bobin-x")
    kapanan: list = []

    def _ozet_patla(*a, **k):
        raise RuntimeError("özet tablosu kilitli")

    db = types.SimpleNamespace(end_coil_run=lambda rid, bitis: kapanan.append(rid), add_sensor_run_summary=_ozet_patla)
    monkeypatch.setattr(bobin_izi, "_treatment_db_getter", lambda: db)
    bobin_izi._active_coil_runs[3] = 77
    bobin_izi._coil_run_stats[77] = {
        "n": 2,
        "t_sum": 60.0,
        "t_n": 2,
        "i_sum": 0.0,
        "i_n": 0,
        "b_sum": 0.0,
        "b_n": 0,
        "saat0": None,
    }
    with caplog.at_level(logging.DEBUG, logger=bobin_izi.__name__):
        bobin_izi._finish_coil_run_govde(3)
        assert kapanan == [77] and 77 not in bobin_izi._coil_run_stats and 3 not in bobin_izi._active_coil_runs

        def _alici_patla():
            raise RuntimeError("tedavi DB'si kapanıyor")

        monkeypatch.setattr(bobin_izi, "_treatment_db_getter", _alici_patla)
        bobin_izi._active_coil_runs[4] = 78
        bobin_izi._finish_coil_run_govde(4)
    mesajlar = [r.getMessage() for r in caplog.records]
    assert "add_sensor_run_summary hatasi" in mesajlar
    assert "_finish_coil_run hatasi (coil=4)" in mesajlar


# ── patient_router ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_hasta_ucu_zorunlu_kimlik_kipi(monkeypatch):
    monkeypatch.setenv("PEMF_REQUIRE_PATIENT_AUTH", "1")
    gercek = auth.check_token
    monkeypatch.delattr(auth, "check_token")
    with pytest.raises(HTTPException) as e:
        patient_router._enforce_patient_auth(_Istek())
    assert e.value.status_code == 503 and e.value.detail == ceviri.t("hasta.hata.kimlikAltyapisiYok")
    monkeypatch.setattr(auth, "check_token", lambda t: t == "dogru-jeton", raising=False)
    with pytest.raises(HTTPException) as e:
        patient_router._enforce_patient_auth(_Istek({"X-API-Key": "yanlis"}))
    assert e.value.status_code == 401 and e.value.detail == ceviri.t("hasta.hata.operatorJetonuGerekli")
    assert patient_router._enforce_patient_auth(_Istek(sorgu={"token": "dogru-jeton"})) is None
    assert patient_router._enforce_patient_auth(_Istek({"X-API-Key": "dogru-jeton"})) is None
    assert gercek is not None


def test_hasta_db_yokken_uclar_500_bos_secim_400_deger_hatasi_400(monkeypatch):
    monkeypatch.setenv("PEMF_REQUIRE_PATIENT_AUTH", "0")
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: None)
    for cagri in (
        lambda: patient_router.get_all_patients(_Istek()),
        lambda: patient_router.add_new_patient(patient_router.PatientInput(name="Pamuk"), _Istek()),
        lambda: patient_router.remove_patients_bulk(
            _Istek(), patient_router.BulkDeletePayload(confirm="DELETE_SELECTED", patient_ids=["p1"])
        ),
    ):
        with pytest.raises(HTTPException) as e:
            cagri()
        assert e.value.status_code == 500
    with pytest.raises(HTTPException) as e:
        patient_router.remove_patients_bulk(
            _Istek(), patient_router.BulkDeletePayload(confirm="DELETE_SELECTED", patient_ids=[" ", ""])
        )
    assert e.value.status_code == 400 and e.value.detail == ceviri.t("hasta.hata.silinecekSecilmedi")
    monkeypatch.setattr(auth, "cihazin_kendisinden_mi", lambda r: True)
    monkeypatch.setattr(auth, "kayitli_operator_var", lambda: False)
    with pytest.raises(HTTPException) as e:
        patient_router.remove_all_patients(_Istek(), patient_router.DeleteAllPayload(confirm="DELETE_ALL"))
    assert e.value.status_code == 500

    def _deger_hatasi(ids):
        raise ValueError("en fazla 500 hasta tek seferde silinebilir")

    db = types.SimpleNamespace(operator_sahipleri=lambda ids: {}, delete_patients_bulk=_deger_hatasi)
    monkeypatch.setattr(patient_router, "get_patient_database", lambda: db)
    from servers import silme_yetkisi

    monkeypatch.setattr(silme_yetkisi, "sahiplik_kapisi", lambda *a, **k: None)
    with pytest.raises(HTTPException) as e:
        patient_router.remove_patients_bulk(
            _Istek(), patient_router.BulkDeletePayload(confirm="DELETE_SELECTED", patient_ids=["p1"])
        )
    assert e.value.status_code == 400 and e.value.detail == "en fazla 500 hasta tek seferde silinebilir"


# ── stm32_kimlik ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_bos_banner_kimliksiz_ceviri_patlarsa_estop_metni_turkce(monkeypatch):
    from utils import stm32_kimlik as sk

    assert sk.banner_ayristir("") is None
    assert sk.banner_ayristir(None) is None

    def _patla(*a, **k):
        raise KeyError("katalog yüklenemedi")

    monkeypatch.setattr(ceviri, "t", _patla)
    assert sk.estop_kart_yanitsiz_metni("en") == sk.ESTOP_KART_YANITSIZ_METNI
