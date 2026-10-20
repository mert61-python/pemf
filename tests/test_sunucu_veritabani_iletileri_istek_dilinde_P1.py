# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10g — veritabanı katmanının OPERATÖRE giden iletileri istek dilinde.

Gerçek ekran metni yalnız dört yerde: operatör hesabı (kayıt / şifre sıfırlama) iletileri, toplu silme üst sınırı (400 gövdesi),
DİSK KRİTİK nedeni (seans başlatma 503'ü + `/api/health` `dbSebep`) ve saat şüphesi (Ayarlar > Veri Saklama). Geri kalan ~183 metin
şema / SQL / günlük etiketi / iç istisna / DB'ye yazılan veri / kurtarma malzemesi (muaf, gerekçeli).

Türkçe çıktı ESKİ kodun çıktısıyla BAYT BAYT aynıdır (beklenen metinler taşıma ÖNCESİ kaynaktan alınmış sabitlerdir).
Metne göre dallanan iki yer (`startswith("Disk boş alanı kritik")`) HER dilde eşleşir. MUTASYON: kataloğun TR değeri değişirse /
çağrı ham metne dönerse / ön ek eşleşmesi tek dile kalırsa / sağlık iş parçacığı dili taşımazsa → KIRMIZI.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
for p in (KOK, KOK / "apps" / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from utils import ceviri  # noqa: E402


@contextlib.contextmanager
def dilde(dil):
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        yield
    finally:
        ceviri.istek_dili_var.reset(jeton)


# ── operatör hesabı ─────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_hesap_kayit_ve_sifirlama_iletileri_istek_dilinde(tmp_path):
    from database.auth_db import AuthDB

    db = AuthDB(str(tmp_path))
    assert db.register("op@klinik.com", "Abc12345")[0] is True
    assert db.register("op@klinik.com", "Abc12345") == (False, "Bu e-posta ile zaten bir hesap var. Giriş yapın.")
    assert db.reset_password("yok@klinik.com", "NewPass9") == (False, "Bu e-posta ile kayıtlı bir hesap yok.")
    with dilde("en"):
        assert db.register("op@klinik.com", "Abc12345") == (
            False,
            "An account with this email already exists. Please sign in.",
        )
        assert db.reset_password("yok@klinik.com", "NewPass9") == (False, "No account is registered with this email.")


# ── toplu silme üst sınırı (400 gövdesi) ────────────────────────────────────────────────────────────
def test_KRITIK_toplu_silme_ust_siniri_iletisi_istek_dilinde(tmp_path, monkeypatch):
    from veri_tasima_aparati import cihaz_kur

    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    hasta = [str(i) for i in range(1, 502)]
    seans = list(range(1, 502))
    with pytest.raises(ValueError) as e:
        hdb.delete_patients_bulk(hasta)
    assert str(e.value) == "Tek istekte en fazla 500 hasta silinebilir."
    with pytest.raises(ValueError) as e:
        tdb.delete_sessions_bulk(seans)
    assert str(e.value) == "Tek istekte en fazla 500 seans silinebilir."
    with dilde("en"):
        with pytest.raises(ValueError) as e:
            hdb.delete_patients_bulk(hasta)
        assert str(e.value) == "At most 500 patients can be deleted in one request."
        with pytest.raises(ValueError) as e:
            tdb.delete_sessions_bulk(seans)
        assert str(e.value) == "At most 500 sessions can be deleted in one request."


# ── disk kritik: metin istek dilinde + ön ek eşleşmesi HER dilde ─────────────────────────────────────
ESKI_DISK_METNI = (
    "Disk boş alanı kritik (5 MB < 100 MB) — tıbbi kayıt yazılamaz; yeni seans başlatılamaz. Disk alanı açın."
)


def test_KRITIK_disk_kritik_nedeni_TR_bayt_bayt_EN_istek_dilinde(tmp_path, monkeypatch):
    from database.treatment_history_db import disk_kritik_sebebi_mi
    from veri_tasima_aparati import cihaz_kur

    tdb, _ = cihaz_kur(monkeypatch, tmp_path / "A")
    tdb.get_disk_space_status = lambda: {"critical": True, "free_mb": 5, "threshold_mb": 100}
    assert tdb.is_ready() == (False, ESKI_DISK_METNI)
    with dilde("en"):
        hazir, sebep = tdb.is_ready()
    assert hazir is False
    assert sebep == (
        "Free disk space is critical (5 MB < 100 MB) — the medical record cannot be written; a new session cannot be started. "
        "Free up disk space."
    )
    # çağıran farklı dilde olsa da eşleşir (metin sağlık iş parçacığında / başka dilde üretilmiş olabilir)
    assert disk_kritik_sebebi_mi(ESKI_DISK_METNI) is True
    assert disk_kritik_sebebi_mi(sebep) is True
    with dilde("en"):
        assert disk_kritik_sebebi_mi(ESKI_DISK_METNI) is True
    for diger in ("", None, "Hasta veritabanı göç bekliyor", "Disk", "database could not be opened"):
        assert disk_kritik_sebebi_mi(diger) is False, diger


def test_disk_kritik_ayrintisiz_degerde_f_dizgisiyle_ayni_None_basar(tmp_path, monkeypatch):
    """Ölçü okunamamışsa eski f-dizgisi `None` basardı; katalog çağrısı da aynı metni verir (kati kipte yer tutucu eksik DEĞİL)."""
    from veri_tasima_aparati import cihaz_kur

    tdb, _ = cihaz_kur(monkeypatch, tmp_path / "A")
    tdb.get_disk_space_status = lambda: {"critical": True}
    assert tdb.is_ready()[1].startswith("Disk boş alanı kritik (None MB < None MB)")


def test_KRITIK_sagik_is_parcacigi_istek_dilini_tasir(monkeypatch):
    """`/api/health` `dbSebep`: sorgu yeni iş parçacığında koşar (bağlam miras alınmaz) → dil AÇIKÇA taşınır; tek-uçuş anahtarı dili içerir."""
    from servers import system_router as sr

    def _sahte(_api):
        return None, False, ceviri.t("gecmis.hata.diskKritik", bos="5", esik="100")

    class _Api:
        @staticmethod
        def _app_data_dir():
            return "yok"

    monkeypatch.setattr(sr, "_saglik_db_durumu", _sahte)
    monkeypatch.setattr(sr, "_saglik_db_ucusta", None)
    with dilde("en"):
        _, _, sebep_en = asyncio.run(sr._saglik_db_durumu_dongu_disi(_Api()))
    assert sebep_en.startswith("Free disk space is critical (5 MB < 100 MB)"), sebep_en
    monkeypatch.setattr(sr, "_saglik_db_ucusta", None)
    with dilde("tr"):
        _, _, sebep_tr = asyncio.run(sr._saglik_db_durumu_dongu_disi(_Api()))
    assert sebep_tr == ESKI_DISK_METNI
    # tek-uçuş anahtarı dil içerir: iki dil birbirinin sonucunu paylaşmaz
    assert sr._saglik_db_ucusta[0] == ("yok", "tr")


# ── saat şüphesi: DB'ye yazılan Türkçe veri aynen, ekranda istek dilinde ─────────────────────────────
GERIDE = "geride: cihaz saati 2026-10-20 22:40, son gorulen 2026-10-25 22:40"
ILERI = "ileri: cihaz saati 2036-10-20 22:40, son gorulen 2026-10-20 22:40"


def test_KRITIK_saat_suphesi_metni_TR_bayt_bayt_EN_gosterimde():
    from database.thdb_bakim import saat_suphesi_metni

    assert saat_suphesi_metni(GERIDE, dil="tr") == GERIDE
    assert saat_suphesi_metni(ILERI, dil="tr") == ILERI
    assert saat_suphesi_metni(GERIDE, dil="en") == "behind: device clock 2026-10-20 22:40, last seen 2026-10-25 22:40"
    assert saat_suphesi_metni(ILERI, dil="en") == "ahead: device clock 2036-10-20 22:40, last seen 2026-10-20 22:40"
    with dilde("en"):
        assert saat_suphesi_metni(ILERI).startswith("ahead: device clock")
    # tanınmayan / eski biçimli değer kaybolmaz; boş değer boş kalır
    assert saat_suphesi_metni("başka biçim", dil="en") == "başka biçim"
    assert saat_suphesi_metni(None, dil="en") is None
    assert saat_suphesi_metni("", dil="en") == ""


def test_KRITIK_saat_suphesi_GERCEK_uretici_degeri_gosterim_desenine_uyar(tmp_path, monkeypatch):
    """Desen, kaynağın gerçekten yazdığı değere uymalı (aksi hâlde EN görünümde Türkçe parça kalırdı)."""
    from database.thdb_bakim import saat_suphesi_metni
    from veri_tasima_aparati import cihaz_kur

    tdb, _ = cihaz_kur(monkeypatch, tmp_path / "A")
    ileri_tavan = (datetime.now() + timedelta(days=5)).isoformat(timespec="seconds")
    tdb._set_system_setting(tdb.SAAT_TAVANI_ANAHTARI, ileri_tavan, "test")
    assert tdb.saat_akla_yatkin_mi() is False
    neden = tdb.saat_supheli_mi()
    assert neden and neden.startswith("geride: cihaz saati ")
    assert saat_suphesi_metni(neden, dil="tr") == neden  # veri değişmedi
    assert saat_suphesi_metni(neden, dil="en").startswith("behind: device clock ")
    tdb.saat_onayla()
    geri_tavan = (datetime.now() - timedelta(days=400)).isoformat(timespec="seconds")
    tdb._set_system_setting(tdb.SAAT_TAVANI_ANAHTARI, geri_tavan, "test")
    assert tdb.saat_akla_yatkin_mi() is False
    neden = tdb.saat_supheli_mi()
    assert neden and neden.startswith("ileri: cihaz saati ")
    assert saat_suphesi_metni(neden, dil="en").startswith("ahead: device clock ")


def test_KRITIK_ayarlar_ucu_saat_suphesini_istek_dilinde_gosterir_veri_degismez(tmp_path, monkeypatch):
    """GERÇEK uç: `GET /api/settings/retention` → `clockSuspect` başlıksız / `X-PEMF-Dil: tr` TR (veri BAYT BAYT), `en` EN; DB'deki değer değişmez."""
    from database import patient_database as pmod
    from fastapi.testclient import TestClient
    from servers import api_server as api_mod
    from servers import system_router as sr
    from veri_tasima_aparati import cihaz_kur

    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "A")
    monkeypatch.setattr(sr, "_pii_ayar_db", lambda: tdb)
    monkeypatch.setattr(pmod, "get_patient_database", lambda *a, **k: hdb)
    monkeypatch.setattr(api_mod, "_get_treatment_db", lambda: tdb)
    tdb._set_system_setting(tdb.SAAT_SUPHELI_ANAHTARI, ILERI, "test")
    istemci = TestClient(api_mod.app, client=("127.0.0.1", 51938))
    assert istemci.get("/api/settings/retention").json()["clockSuspect"] == ILERI
    assert istemci.get("/api/settings/retention", headers={"X-PEMF-Dil": "tr"}).json()["clockSuspect"] == ILERI
    en = istemci.get("/api/settings/retention", headers={"X-PEMF-Dil": "en"}).json()["clockSuspect"]
    assert en == "ahead: device clock 2036-10-20 22:40, last seen 2026-10-20 22:40"
    assert tdb.saat_supheli_mi() == ILERI, "gösterim çevirisi DB'deki veriyi değiştirdi"


def test_saat_suphesi_yardimcisi_dile_gore_cevirir_veri_degismez():
    from servers import system_router as sr

    assert sr._saat_suphesi_metni(ILERI) == ILERI
    with dilde("en"):
        assert sr._saat_suphesi_metni(ILERI) == "ahead: device clock 2036-10-20 22:40, last seen 2026-10-20 22:40"
        assert sr._saat_suphesi_metni(None) is None


# ── disk kritik: GERÇEK uçlar (seans başlatma 503 + /api/health dbSebep) istek dilinde ───────────────────
@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import api_server as _api0

    gercek_hazir = _api0._kayit_db_hazir
    ns = ap.kur(monkeypatch, tmp_path)
    monkeypatch.setattr(ns.api, "_kayit_db_hazir", gercek_hazir)  # aparatın "hep hazır" yamasını GERİ al
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            yield ns
    finally:
        ns.geri()


def _disk_kritik(o, monkeypatch):
    import types

    kritik = types.SimpleNamespace(total=500 * 2**30, used=500 * 2**30 - 100 * 2**20, free=100 * 2**20)  # 100 MB boş
    monkeypatch.setattr(o.db, "_disk_usage_provider", lambda _p: kritik)


_BASLAT = {"mode": "Manuel", "frequency": 100, "duty": 40, "phase": 0, "duration_minutes": 20, "coil_ids": [1, 2]}


def test_KRITIK_disk_kritikken_seans_503_nedeni_istek_dilinde_yonlendirme_dilden_bagimsiz(o, monkeypatch):
    """Metne göre dallanan `startswith` (api_server) HER dilde disk nedenini yakalar: EN istekte de "disk boşalt" mesajı (yeniden başlat DEĞİL)."""
    _disk_kritik(o, monkeypatch)
    tr = o.c.post("/api/session/start", json=_BASLAT)
    assert tr.status_code == 503
    assert tr.json()["detail"].startswith("Seans başlatılamaz: Disk boş alanı kritik (100 MB < 500 MB)"), tr.text[:300]
    en = o.c.post("/api/session/start", json=_BASLAT, headers={"X-PEMF-Dil": "en"})
    assert en.status_code == 503
    assert en.json()["detail"].startswith("Session cannot be started: Free disk space is critical (100 MB < 500 MB)"), (
        en.text[:300]
    )


def test_KRITIK_disk_kritikken_saglik_dbSebep_istek_dilinde(o, monkeypatch):
    _disk_kritik(o, monkeypatch)
    tr = o.c.get("/api/health").json()
    assert tr.get("dbReady") is False
    assert tr["dbSebep"].startswith("Disk boş alanı kritik (100 MB < 500 MB)"), tr.get("dbSebep")
    en = o.c.get("/api/health", headers={"X-PEMF-Dil": "en"}).json()
    assert en.get("dbReady") is False
    assert en["dbSebep"].startswith("Free disk space is critical (100 MB < 500 MB)"), en.get("dbSebep")
