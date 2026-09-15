# -*- coding: utf-8 -*-
# Author: mertaygn
"""TOPLU SİLME — seans geçmişi + hasta veritabanı (sahip bildirimi 2026-09-12).

===============================================================================
NE İSTENDİ
===============================================================================
· "toplu sil seçeneği eksik seans geçmişi tabında kullanıcı tek tek silmek zorunda kalıyor."
· "hasta veri tabanında da toplu sil butonu lazım."

===============================================================================
TASARIM KARARI — NEDEN SUNUCUDA TOPLU, NEDEN İSTEMCİDEN N KEZ TEKİL DEĞİL
===============================================================================
İstemci N ayrı silme isteği atsaydı, dizi yarısında koptuğunda (ağ, kapanan pencere,
kilitli DB) operatör HANGİ kayıtların gittiğini bilemezdi. Geri alınamaz bir işlemde
"kısmen oldu" en kötü sonuçtur. Bu yüzden silme TEK TRANSACTION: ya hepsi ya hiçbiri.
(Hasta tarafındaki `clear_all_patients` atomikliğiyle aynı gerekçe — audit P3.)

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
· Toplu silme GERÇEKTEN siliyor mu (uçtan uca, gerçek endpoint + gerçek DB)
· ONAY alanı olmadan silme REDDEDİLİYOR mu (kazara POST koruması — audit B-8.2)
· ÇOCUK TABLOLAR da siliniyor mu (orphan bobin-çalışması/sensör satırı kalmasın)
· ATOMİK mi — geçersiz bir kimlik listesi yüzünden YARIM silme olmuyor mu
· ÜST SINIR uygulanıyor mu (tek yanlış "tümünü seç" tüm kliniği götürmesin)
· Seçilmeyen kayıtlar DURUYOR mu (en sessiz felaket: fazla silmek)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")

#: Onay parolası — arayüz ile backend AYNI dizgiyi kullanmalı, yoksa düğme sessizce 400 alır.
ONAY = "DELETE_SELECTED"


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient

    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


@pytest.fixture
def gecmis(tmp_path):
    """İçinde 4 seans (her biri bobin-çalışmalı) olan izole geçmiş DB'si."""
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server
    from servers.history_router import get_db

    kok = tmp_path / "toplu_gecmis"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    kimlikler = []
    for i in range(4):
        sid = db.start_session(treatment_mode="Manuel", patient_name=f"Hasta{i}")
        db.start_coil_run(
            sid,
            1,
            frequency_hz=100,
            duty_percent=50,
            phase=0,
            intensity_mt=0.0,
            hw_type="stm",
            started_epoch=1757000000.0 + i,
        )
        db.end_session(sid, session_status="completed")
        kimlikler.append(sid)
    api_server.app.dependency_overrides[get_db] = lambda: db
    yield db, kimlikler
    api_server.app.dependency_overrides.pop(get_db, None)


def _coil_run_sayisi(db, session_id: int) -> int:
    return len(db.get_session_coil_runs(session_id))


# ============================================================================
# 1. ⚠️ ASIL KAPI — SEANS TOPLU SİLME GERÇEKTEN SİLİYOR
# ============================================================================


def test_KRITIK_secilen_seanslar_TEK_ISTEKTE_silinir(istemci, gecmis):
    """MUTASYON: `/delete_bulk` ucunu kaldır → KIRMIZI (404).

    Sahadaki etki: sahibin bildirdiği arıza — operatör tek tek silmek zorunda kalır.
    """
    db, kimlikler = gecmis
    secili = kimlikler[:2]
    y = istemci.post("/api/history/delete_bulk", json={"session_ids": secili, "confirm": ONAY})
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["silinen"] == 2, g
    assert g["istenen"] == 2, g
    kalan = {k["id"] for k in db.get_session_history(limit=100)}
    assert kalan == set(kimlikler[2:]), f"kalan kayitlar beklenenden farkli: {kalan}"


def test_KRITIK_SECILMEYEN_kayitlar_DURUYOR(istemci, gecmis):
    """⚠️ EN SESSİZ FELAKET FAZLA SİLMEKTİR: `IN (...)` yerine koşulsuz bir DELETE, hiçbir
    hata vermeden tüm geçmişi götürürdü ve "silme çalışıyor" testi yine YEŞİL kalırdı.

    MUTASYON: `delete_sessions_bulk`taki `WHERE id IN (...)` koşulunu kaldır → KIRMIZI.
    """
    db, kimlikler = gecmis
    istemci.post("/api/history/delete_bulk", json={"session_ids": [kimlikler[0]], "confirm": ONAY})
    kalan = {k["id"] for k in db.get_session_history(limit=100)}
    assert kalan == set(kimlikler[1:]), f"secilmeyen kayitlar da silinmis: kalan={kalan}"


def test_KRITIK_COCUK_tablolar_da_silinir_orphan_kalmaz(istemci, gecmis):
    """⚠️ FK ON DELETE CASCADE YOK. Orphan `session_coil_runs` satırı, silinmiş bir seansın
    dozunu raporlarda yaşatır (P2 denetiminde bir kez oldu).

    MUTASYON: `DELETE FROM session_coil_runs ...` satırını sil → KIRMIZI.
    """
    db, kimlikler = gecmis
    hedef = kimlikler[0]
    assert _coil_run_sayisi(db, hedef) == 1, "onkosul: seansin bobin calismasi olmali"
    istemci.post("/api/history/delete_bulk", json={"session_ids": [hedef], "confirm": ONAY})
    assert _coil_run_sayisi(db, hedef) == 0, "silinen seansin bobin calismasi ORPHAN kaldi"


# ============================================================================
# 2. KAZA KORUMASI — ONAY VE ÜST SINIR
# ============================================================================


def test_KRITIK_ONAYSIZ_toplu_silme_REDDEDILIR(istemci, gecmis):
    """audit B-8.2 deseni: gövdesiz/kazara bir POST geri dönülemez silme yapmasın.

    MUTASYON: `if payload.confirm != "DELETE_SELECTED"` kapısını sil → KIRMIZI.
    """
    db, kimlikler = gecmis
    y = istemci.post("/api/history/delete_bulk", json={"session_ids": kimlikler})
    assert y.status_code == 400, y.text
    assert len(db.get_session_history(limit=100)) == len(kimlikler), "ONAYSIZ istek SILDI"


def test_bos_secim_REDDEDILIR(istemci, gecmis):
    db, kimlikler = gecmis
    y = istemci.post("/api/history/delete_bulk", json={"session_ids": [], "confirm": ONAY})
    assert y.status_code == 400, y.text
    assert len(db.get_session_history(limit=100)) == len(kimlikler)


def test_KRITIK_UST_SINIR_uygulanir(istemci, gecmis):
    """⚠️ Tek bir yanlış "tümünü seç" tıklaması kliniğin bütün geçmişini götürmesin.

    MUTASYON: `if len(kimlikler) > self.TOPLU_SILME_AZAMI` kapısını sil → KIRMIZI.
    """
    from database.treatment_history_db import TreatmentHistoryDB

    db, kimlikler = gecmis
    fazla = list(range(1, TreatmentHistoryDB.TOPLU_SILME_AZAMI + 2))
    y = istemci.post("/api/history/delete_bulk", json={"session_ids": fazla, "confirm": ONAY})
    assert y.status_code == 400, y.text
    assert len(db.get_session_history(limit=100)) == len(kimlikler), "sinir asildi ama SILDI"


def test_KRITIK_ATOMIK_yarim_silme_yok(gecmis):
    """⚠️ Sınır aşımı reddedilirken HİÇBİR kayıt gitmemeli.

    Döngüyle silen bir uygulama ilk 500'ü siler, sonra patlardı — operatör "hata aldım,
    demek ki silinmedi" sanırdı. Kapı, reddin ÖNCE geldiğini kanıtlar.
    """
    db, kimlikler = gecmis
    fazla = kimlikler + list(range(1000, 1000 + db.TOPLU_SILME_AZAMI + 1))
    with pytest.raises(ValueError):
        db.delete_sessions_bulk(fazla)
    assert len(db.get_session_history(limit=100)) == len(kimlikler), "YARIM silme oldu"


# ============================================================================
# 3. HASTA VERİTABANI — AYNI SÖZLEŞME
# ============================================================================


@pytest.fixture
def hastalar(tmp_path, monkeypatch):
    """İzole hasta DB'si + 3 kayıt."""
    from database import patient_database as pdb

    # ⚠️ `PatientDatabase` DİZİN değil DOSYA yolu bekler (`db_file`); dizin verilince
    # sqlite "unable to open database file" der.
    kok = tmp_path / "hastalar"
    kok.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pdb, "_patient_db_instance", None, raising=False)
    db = pdb.PatientDatabase(str(kok / "patients.db"))
    monkeypatch.setattr(pdb, "get_patient_database", lambda *a, **k: db)
    import servers.patient_router as pr

    monkeypatch.setattr(pr, "get_patient_database", lambda *a, **k: db)
    # ⚠️ KİMLİĞİ `add_patient`in DÖNDÜRDÜĞÜ değerden al: bu fonksiyon sözlükteki `id`yi
    # BİLEREK yok sayıp uuid4 üretir (bkz. "KOPUK UUID ZINCIRI" notu). Uydurma bir kimlikle
    # test etmek, silme hiç çalışmasa bile yeşil kalabilecek sahte bir kurulum olurdu.
    kimlikler = [db.add_patient({"name": f"Hasta{i}", "species": "Kedi", "owner": "Mert"}) for i in range(3)]
    assert all(kimlikler), "onkosul: hasta kimlikleri uretilemedi"
    return db, kimlikler


def test_KRITIK_secilen_hastalar_TEK_ISTEKTE_silinir(istemci, hastalar):
    """MUTASYON: `/api/patients/delete_bulk` ucunu kaldır → KIRMIZI (404)."""
    db, kimlikler = hastalar
    y = istemci.post("/api/patients/delete_bulk", json={"patient_ids": kimlikler[:2], "confirm": ONAY})
    assert y.status_code == 200, y.text
    assert y.json()["silinen"] == 2, y.json()
    kalan = {p["id"] for p in db.get_all_patients()}
    assert kalan == {kimlikler[2]}, f"kalan hastalar beklenenden farkli: {kalan}"


def test_KRITIK_hasta_ONAYSIZ_silinmez(istemci, hastalar):
    db, kimlikler = hastalar
    y = istemci.post("/api/patients/delete_bulk", json={"patient_ids": kimlikler})
    assert y.status_code == 400, y.text
    assert len(db.get_all_patients()) == len(kimlikler), "ONAYSIZ istek SILDI"


def test_silinen_hasta_ARAMA_indeksinden_de_gider(istemci, hastalar):
    """⚠️ `patient_search_index` orphan kalırsa silinmiş hasta aramada GÖRÜNMEYE devam eder
    (KVKK "unutulma hakkı" ihlali; kayıt gitti sanılır).

    ⚠️ DÜRÜSTLÜK NOTU — BU KAPI TEK BAŞINA `DELETE FROM patient_search_index` SATIRINI
    ÖLÇMEZ: mutasyonla ölçüldü (2026-09-12), o satır silinince bu test YEŞİL kaldı, çünkü
    indeksi asıl temizleyen `ON DELETE CASCADE` (B-7.3). Bu test SONUCU kilitler; o satırı
    ölçen kapı aşağıdaki `..._FK_KAPALIYKEN_da_...` testidir.
    """
    db, kimlikler = hastalar
    istemci.post("/api/patients/delete_bulk", json={"patient_ids": [kimlikler[0]], "confirm": ONAY})
    bulunan = {p["id"] for p in db.search_patients("Hasta0")}
    assert kimlikler[0] not in bulunan, "silinen hasta hala ARAMADA cikiyor (orphan indeks)"


def test_KRITIK_arama_indeksi_FK_KAPALIYKEN_da_temizlenir(hastalar):
    """⚠️ `foreign_keys` PRAGMA'sı BAĞLANTI BAŞINADIR ve her yeni bağlantıda tekrar
    kurulmak zorundadır. Bir gün havuz/bağlantı yolu değişip pragma düşerse CASCADE sessizce
    kaybolur ve silinen hastalar aramada yaşamaya devam eder — hiçbir hata vermeden.

    Bu kapı CASCADE'i KAPATIP açık `DELETE FROM patient_search_index` satırının tek başına
    işi bitirdiğini ölçer (savunmanın ikinci katmanı gerçekten var mı).

    MUTASYON: `delete_patients_bulk`taki `DELETE FROM patient_search_index ...` satırını sil
    → KIRMIZI.
    """
    db, kimlikler = hastalar
    hedef = kimlikler[0]
    with db._get_connection() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0, "onkosul: FK kapatilamadi"
    try:
        assert db.delete_patients_bulk([hedef]) == 1, "onkosul: hasta silinemedi"
        with db._get_connection() as conn:
            kalan = conn.execute("SELECT COUNT(*) FROM patient_search_index WHERE patient_id = ?", (hedef,)).fetchone()[
                0
            ]
    finally:
        with db._get_connection() as conn:
            conn.execute("PRAGMA foreign_keys=ON")
    assert kalan == 0, f"FK kapaliyken arama indeksinde {kalan} orphan satir KALDI -> silinen hasta aramada gorunur"


# ============================================================================
# 4. ⚠️ KAYNAK ÇIPASI — ARAYÜZ BU UÇLARI GERÇEKTEN KULLANIYOR MU
# ============================================================================
#
# `useCokluSecim.test.tsx` kancanın DAVRANIŞINI, bu bölüm ekranların onu KULLANDIĞINI ölçer.
# İkisi ayrı sorulardır ve bu depoda ikincisi ihmal edildiğinde kapı sessizce anlamını
# yitirdi (bkz. test_ai_gorsel_sahne_capalari.py dosya başlığı).

_PF = KOK / "pf" / "src"

#: Toplu silmeyi taşıyan ekranlar — sahibin iki ayrı isteği (seans + hasta).
TOPLU_SILME_EKRANLARI = ("screens/TreatmentHistoryScreen.tsx", "screens/PatientScreen.tsx")


def _tsx(bagil: str) -> str:
    """Kaynağı YORUMLARI SÖKÜLMÜŞ döndürür (string literalleri korunur).

    ⚠️ Bu depoda "yorum kapıyı kandırdı" hatası BEŞ kez tekrar etti; sayaç/varlık kapıları
    yorum metnini saymamalı.
    """
    from c_soyucu import c_soy

    return c_soy((_PF / bagil).read_text(encoding="utf-8"))


@pytest.mark.skipif(not (_PF / "screens").exists(), reason="pf/ kaynak agaci yok")
def test_KRITIK_her_iki_ekran_da_ORTAK_kancayi_kullaniyor():
    """MUTASYON: bir ekrandan `useCokluSecim(` çağrısını kaldır → KIRMIZI.

    ⚠️ İki ekrana iki ayrı seçim mantığı yazılırsa biri "hayalet seçim" korumasını taşır,
    öbürü taşımaz ve operatör GÖRMEDİĞİ kayıtları silebilir — yalnız tek ekranda.
    """
    for ekran in TOPLU_SILME_EKRANLARI:
        src = _tsx(ekran)
        # ⚠️ Çıpa "= useCokluSecim"e pinli: çağrı tip parametresi alabiliyor
        # (`useCokluSecim<number>(...)`), dolayısıyla "useCokluSecim(" aramak KIRILGAN.
        assert "= useCokluSecim" in src, f"{ekran} ortak secim kancasini KULLANMIYOR"
        assert "<SecimCubugu" in src, f"{ekran} secim seridini gostermiyor -> dugme erisilemez"


@pytest.mark.skipif(not (_PF / "screens").exists(), reason="pf/ kaynak agaci yok")
def test_KRITIK_arayuz_TOPLU_uca_gidiyor_N_istek_DEGIL():
    """⚠️ İstemci N ayrı silme isteği atarsa atomiklik KAYBOLUR: dizi yarısında koparsa
    operatör hangi kayıtların gittiğini bilemez. Kapı, toplu ucun çağrıldığını kanıtlar.

    MUTASYON: `delete_bulk` çağrısını `kimlikler.map(id => apiPost("/history/delete", ...))`
    döngüsüne çevir → KIRMIZI.
    """
    gecmis = _tsx("screens/TreatmentHistoryScreen.tsx")
    assert '"/history/delete_bulk"' in gecmis, "gecmis ekrani TOPLU uca gitmiyor"
    hasta = _tsx("screens/PatientScreen.tsx")
    assert '"/patients/delete_bulk"' in hasta, "hasta ekrani TOPLU uca gitmiyor"


@pytest.mark.skipif(not (_PF / "services").exists(), reason="pf/ kaynak agaci yok")
def test_KRITIK_onay_dizgisi_backend_ile_AYNI():
    """⚠️ Arayüz ile backend farklı dizgi taşırsa "Sil" düğmesi SESSİZCE 400 alır: kullanıcıya
    "başarısız" der, sebebini söylemez ve hata bir sürüm boyunca fark edilmez.

    MUTASYON: `topluSilme.ts`teki dizgiyi değiştir → KIRMIZI.
    """
    src = (_PF / "services" / "topluSilme.ts").read_text(encoding="utf-8")
    m = re.search(r'TOPLU_SILME_ONAYI\s*=\s*"([^"]+)"', src)
    assert m, "TOPLU_SILME_ONAYI sabiti bulunamadi -> capa bayatladi"
    assert m.group(1) == ONAY, f"arayuz onayi {m.group(1)!r}, backend {ONAY!r} bekliyor"
