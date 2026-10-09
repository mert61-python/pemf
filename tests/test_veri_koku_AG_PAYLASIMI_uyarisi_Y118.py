# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y118 (sahip kararı · S-B2B2.3) — veri klasörü (`PEMF_DATA_DIR` / `%APPDATA%`) AĞ PAYLAŞIMINDAYSA açılışta günlük + arayüz uyarısı.

SQLite'ın dosya kilitleri SMB / ağ sürücüsünde güvenilir değil (eşzamanlı yazımda veritabanı bozulabilir); bu kip DESTEKLENMEZ.
Eskiden hiçbir yerde söylenmiyordu: B2B2-3 UNC veri kökünü AÇILABİLİR yaptı (o düzeltme kalır) ama operatör veri kökünün ağda
olduğunu öğrenmiyordu. Uyarı açılışı DURDURMAZ ve veri kökünü DEĞİŞTİRMEZ (ACİL DURDUR yolu etkilenmez — gerçek `main()` kolu
ortak iddiaları da ölçer).

Ölçüm: UNC biçimleri dosya sistemine DOKUNMADAN (ağa çıkılmaz); yerel kollar GERÇEK `GetDriveTypeW` ile (`\\\\?\\C:\\…` uzun yol
önekli yerel yol dahil); eşlenmiş ağ sürücüsü kolunda yalnız ürünün EN ALT katı (`GetDriveTypeW` sarmalayıcısı `_surucu_turu`)
DRIVE_REMOTE döner — ağ sürücüsü EŞLENMEZ. Gerçek `main()` kolu A14 aparatının alt sürecinde (`ag_kok` senaryosu).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(os.name != "nt", reason="UNC / sürücü türü Windows'a özgü")

_UYARI = "ağ paylaşımında"


@pytest.mark.parametrize(
    "yol",
    [r"\\sunucu\pay\PEMF_System\PEMF_GUI", r"\\?\UNC\sunucu\pay\PEMF_GUI", "//sunucu/pay/PEMF_GUI"],
    ids=["unc", "uzun_onekli_unc", "egik_cizgili_unc"],
)
def test_KRITIK_UNC_veri_koku_AG_sayilir_Y118(yol):
    from utils.path_utils import veri_koku_ag_paylasiminda_mi

    assert veri_koku_ag_paylasiminda_mi(yol) is True, f"UNC veri kökü ağ paylaşımı sayılmadı: {yol}"


def test_KRITIK_eslenmis_AG_SURUCUSU_AG_sayilir_Y118(monkeypatch):
    import utils.path_utils as pu

    sorulan = []

    def _tur(kok):
        sorulan.append(kok)
        return 4 if kok.upper() == "Z:\\" else 3  # Z: = eşlenmiş ağ sürücüsü (DRIVE_REMOTE), diğerleri sabit disk

    monkeypatch.setattr(pu, "_surucu_turu", _tur)
    assert pu.veri_koku_ag_paylasiminda_mi(r"Z:\PEMF_System\PEMF_GUI") is True, "eşlenmiş ağ sürücüsü ağ sayılmadı"
    assert pu.veri_koku_ag_paylasiminda_mi(r"\\?\Z:\PEMF_GUI") is True, "uzun yol önekli ağ sürücüsü ağ sayılmadı"
    assert sorulan and all(k.upper() == "Z:\\" for k in sorulan), f"sürücü kökü yanlış soruldu: {sorulan}"


def test_KARSIT_YEREL_disk_ve_uzun_onekli_yerel_yol_AG_sayilmaz_Y118(tmp_path):
    """GERÇEK `GetDriveTypeW`: test kökü (sabit disk) ve B2B2-3'ün `\\\\?\\C:\\…` biçimi YEREL — yanlış alarm yok."""
    from utils.path_utils import veri_koku_ag_paylasiminda_mi

    assert veri_koku_ag_paylasiminda_mi(tmp_path) is False
    assert veri_koku_ag_paylasiminda_mi("\\\\?\\" + str(tmp_path)) is False


@pytest.fixture()
def saglik(monkeypatch):
    from servers import api_server

    def _al(tur: int, **baslik):
        import utils.path_utils as pu

        monkeypatch.setattr(pu, "_surucu_turu", lambda kok: tur)
        istemci = TestClient(api_server.app, client=("127.0.0.1", 51234))
        r = istemci.get("/api/health", headers=baslik)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    return _al


def test_KRITIK_saglik_ucu_AG_SURUCUSUNDEKI_veri_kokunu_bildirir_YOL_vermez_Y118(saglik):
    g = saglik(4)
    assert g.get("veriKokuAgda") is True, f"sağlık ucu ağdaki veri kökünü bildirmiyor: {g.get('veriKokuAgda')!r}"
    assert "PEMF_GUI" not in str(g.get("veriKokuAgda")), "yalnız bayrak verilmeli (yol günlükte)"


def test_KARSIT_saglik_ucu_YEREL_diskte_false_TUNELDE_None_Y118(saglik):
    assert saglik(3).get("veriKokuAgda") is False, "yerel diskte yanlış alarm"
    assert saglik(4, **{"CF-Connecting-IP": "8.8.8.8"}).get("veriKokuAgda") is None, "bayrak tünel istemcisine SIZDI"


def test_KRITIK_gercek_main_AG_SURUCUSUNDEKI_veri_koku_icin_ACILISTA_uyarir_ACIL_DURDUR_calisir_Y118(tmp_path):
    """GERÇEK `main()` (A14 aparatının alt süreci): açılış günlüğü uyarıyı yazar, sağlık ucu bayrağı verir; açılış DURMAZ,
    ACİL DURDUR / mandal / açılış STOP mutabakatı çalışır (ortak iddialar)."""
    import test_acilis_DB_acilamasa_ACIL_DURDUR_yasar as a14

    s, _app = a14._kos(tmp_path, "ag_kok")
    a14._ortak_iddialar(s)
    assert all(h.get("veriKokuAgda") is True for h in s["saglik"]), f"sağlık ucu bayrağı vermedi: {s['saglik']}"
    gunluk = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in (tmp_path / "log").rglob("*") if p.is_file()
    )
    assert _UYARI in gunluk and "yerel diske taşıyın" in gunluk, "açılış günlüğünde ağ paylaşımı uyarısı YOK"
