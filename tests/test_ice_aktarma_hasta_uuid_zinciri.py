# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HASTA UUID ZİNCİRİ — içe aktarma `patients.db` ↔ tedavi-DB bağını KORUMALI.

DENETİM BULGUSU (2026-08-17). `database/patient_database.add_patient` gelen `id`'yi **yok sayıp**
her çağrıda `uuid.uuid4()` üretiyordu. `/api/data/import` hasta satırlarını doğrudan bu fonksiyona
verdiği için zincir **HER içe aktarımda** kopuyordu — `REPLACE_ALL` şartı YOK, boş bir hedefe
normal cihaz taşımasında da oluyordu:

    KAYNAK patients.db id        : 1295eb8f-...
    HEDEF  patients.db id        : ec1ced28-...   ← yeni uuid4
    HEDEF  treatment patient_uuid: 1295eb8f-...   ← eski uuid (paketle birlikte DOĞRU taşındı)
    ZINCIR SAGLAM MI             : False

Somut sonuç (sessiz): `servers/api_server.py` günlük bakımında
`_pdb.anonymize_inactive_patients(1825)` → `db.anonymize_patients_by_uuid(...)` zinciri, taşınmış
hastaların **tedavi geçmişindeki ad kopyalarına ulaşamaz**. 5 yıl inaktif hastada `patients.db`
anonimleşir ama tedavi geçmişindeki hasta adı `[REDACTED]` OLMAZ → **KVKK boşluğu**, hiçbir yerde
görünmez.

⚠️ Tedavi DB'sinin kendi tarafı DOĞRU çalışıyor: `_DOGAL_ANAHTAR = {"patients": "patient_uuid"}`
ile dedup ediliyor ve `tests/test_device_migration_integrity.py` bunu kilitliyor. Kopan halka
yalnız AYRI `patients.db` tarafıydı.

⚠️ Bu testler `id` KORUMASINI kilitler; hasta satırlarını GÜNCELLEMEYİ (upsert) getirmez —
paketten gelen değerin yerel olarak düzeltilmiş bir kaydı ezmesi ayrı bir sahip kararıdır. Aynı
paket iki kez alınırsa satır ATLANIR (ve sayılır), sessizce ÇOĞALTILMAZ.
"""

import base64
import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

PAROLA = "klinik-yedek-2026"


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


@pytest.fixture()
def pdb():
    from database.patient_database import get_patient_database

    return get_patient_database()


# ── 1) Veri katmanı: `add_patient` verilen id'yi ONURLANDIRMALI ───────────────


def test_KRITIK_add_patient_VERILEN_idyi_korur(pdb):
    """İçe aktarma yolunun ihtiyacı: paketteki `id` aynen yazılmalı."""
    hedef_id = "11111111-2222-3333-4444-555555555555"
    donen = pdb.add_patient({"name": "ZincirTest"}, patient_id=hedef_id)

    assert donen == hedef_id, f"verilen id korunmadi (donen: {donen})"
    kayit = pdb.get_patient(hedef_id)
    assert kayit is not None, "verilen id ile kayit BULUNAMADI → zincir kopuk"


def test_id_VERILMEZSE_yeni_uretilir_karsit_kanit(pdb):
    """Karşı-kanıt: normal hasta ekleme davranışı DEĞİŞMEMELİ."""
    a = pdb.add_patient({"name": "NormalEkleme1"})
    b = pdb.add_patient({"name": "NormalEkleme2"})
    assert a and b and a != b, "id verilmeyince yeni uuid uretilmeli"
    assert pdb.get_patient(a) is not None


def test_GECERSIZ_id_ice_aktarmayi_DUSURMEZ_karsit_kanit(pdb):
    """Karşı-kanıt: bozuk/eksik `id` taşıyan bir satır yüzünden taşıma DURMAMALI.

    Eski yedeklerde ya da elle düzenlenmiş paketlerde `id` bozuk olabilir. O satır yeni bir id ile
    yazılır (zinciri o satır için kurtaramayız) ama içe aktarma devam eder — tek bir bozuk satırın
    tüm klinik geçmişinin taşınmasını engellemesi daha kötü olurdu."""
    donen = pdb.add_patient({"name": "BozukIdli"}, patient_id="bu-bir-uuid-degil")
    assert donen, "gecersiz id ice aktarmayi dusurdu"
    assert donen != "bu-bir-uuid-degil", "gecersiz id oldugu gibi yazildi"
    assert pdb.get_patient(donen) is not None


# ── 2) Uçtan uca: gerçek dışa/içe aktarma zinciri korumalı ───────────────────


def _api_hasta_idleri(client) -> set:
    """Hasta id'lerini **API üzerinden** oku — modül singleton'ına GÜVENME.

    Tam süit koşusunda `get_patient_database()`'in bu testte ve uç noktada AYNI örneği döndürmediği
    ölçüldü; API sorgusu uç noktanın gerçekten kullandığı veritabanını hedefler."""
    r = client.get("/api/patients")
    assert r.status_code == 200, r.text[:300]
    return {str(h.get("id")) for h in r.json().get("data") or []}


def _hasta_ekle(client, ad: str) -> str:
    r = client.post("/api/patients", json={"name": ad, "species": "Kedi", "owner": "Sahip"})
    assert r.status_code == 200, r.text[:300]
    pid = r.json().get("patient_id") or r.json().get("id")
    assert pid, f"hasta id donmedi: {r.json()}"
    return str(pid)


def test_KRITIK_UCTAN_UCA_tasima_hasta_idsini_KORUR(client):
    """Gerçek `/api/data/export` → `/api/data/import` turu; `patients.db` id'si AYNI kalmalı.

    Bu, zincirin uçtan uca kanıtıdır: tedavi DB'si `patient_uuid`i zaten doğru taşıyor, dolayısıyla
    `patients.db` id'si korunursa iki taraf yeniden eşleşir ve KVKK anonimleştirmesi hedefine ulaşır.
    """
    kaynak_id = _hasta_ekle(client, "ZincirUctanUca")

    r = client.post("/api/data/export", json={"passphrase": PAROLA})
    assert r.status_code == 200, r.text[:300]
    blob = r.json()["data_b64"]

    # ⚠️ HEDEF SATIR SİLİNİR — bu testin DÜRÜST olması için şart.
    # `REPLACE_ALL` `patients.db`'yi temizlemiyor (bulgunun ikinci, daha hafif yüzü), dolayısıyla
    # aynı cihaza geri yüklerken ESKİ satır yerinde kalıyor ve sorgu onu bulup testi YANLIŞ-YEŞİL
    # yapıyordu. Gerçek senaryo (ve KVKK boşluğunun oluştuğu yer) hedefte o satırın OLMAMASIDIR.
    #
    # ⚠️ SİLME ve DOĞRULAMA **API ÜZERİNDEN** yapılır, modül singleton'ı üzerinden DEĞİL:
    # tam süit koşusunda `get_patient_database()` bu testin gördüğü örnekle uç noktanın gördüğü
    # örnek AYNI olmayabiliyor (ölçüldü: singleton temizlendi ama içe aktarma
    # "UNIQUE constraint failed: patients.id" ile düştü → başka bir dosyaya yazılıyordu).
    # API kullanmak, uç noktanın GERÇEKTEN kullandığı veritabanını hedeflemeyi garanti eder.
    assert client.delete(f"/api/patients/{kaynak_id}").status_code == 200
    assert kaynak_id not in _api_hasta_idleri(client), "on-kosul: hedeften silinmeli"

    r = client.post(
        "/api/data/import",
        json={"passphrase": PAROLA, "blob_b64": blob, "confirm": "REPLACE_ALL"},
    )
    assert r.status_code == 200, r.text[:300]

    assert kaynak_id in _api_hasta_idleri(client), (
        "ice aktarmadan sonra hasta ESKI id ile bulunamiyor → patients.db ↔ tedavi-DB "
        "(patient_uuid) zinciri KOPTU. Sonuc: 5 yil inaktif hastada tedavi gecmisindeki ad "
        "kopyasi [REDACTED] OLMAZ (sessiz KVKK boslugu)."
    )


def test_AYNI_paket_iki_kez_alinirsa_COGALTMAZ(client):
    """Aynı yedek iki kez geri yüklenirse hasta listesi bir kat daha uzamamalı.

    `id` korunduğu için ikinci tur aynı birincil anahtara çarpar ve satır ATLANIR. (Bu, bulgunun
    ikinci ve daha hafif yüzü olan "görünür mükerrer kayıt"ı da kapatır.)"""
    _hasta_ekle(client, "MukerrerTest")
    blob = client.post("/api/data/export", json={"passphrase": PAROLA}).json()["data_b64"]

    once = len(_api_hasta_idleri(client))

    for _ in range(2):
        r = client.post(
            "/api/data/import",
            json={"passphrase": PAROLA, "blob_b64": blob, "confirm": "REPLACE_ALL"},
        )
        assert r.status_code == 200, r.text[:300]

    sonra = len(_api_hasta_idleri(client))
    assert sonra == once, f"hasta sayisi {once} → {sonra}: ayni paket kayitlari COGALTTI"


def test_ZATEN_VAR_ile_BASARISIZ_ayri_sayilir(client, monkeypatch):
    """ "Zaten vardı" ile "İÇE AKTARILAMADI" aynı kovaya konmamalı.

    ⚠️ Bu test, düzeltmenin İLK hâlinde bulduğum kusur için var: her istisna tek bir
    "zaten vardı/atlandı" sayacını artırıyordu. O hâlde operatör "0 hasta [+50 zaten vardı]"
    görüp "sorun yok" diye okuyabilirdi — oysa 50 satır da GERÇEKTEN başarısız olmuş olabilirdi.
    Tıbbi kayıt taşımada bu kabul edilemez bir belirsizliktir.

    ⚠️ DOĞRULAMA `caplog` YERİNE **API YANITI** üzerinden: `caplog` tam süit koşusunda güvenilmezdi
    (izole geçip süitte düşüyordu). Sayaçları yanıta koymak hem testi deterministik yapar hem de
    üç sonucu operatöre GÖRÜNÜR kılar.

    ⚠️ YAMA HEDEFİ = uç noktanın GERÇEKTEN okuduğu sembol (`api_server.get_patient_database`).
    Önce `PatientDatabase` SINIFINI yamalamıştım: izole geçti, tam süitte düştü
    (`zaten_vardi: 3, basarisiz: 0` → yama hiç uygulanmamış). Ölçülen sebep, modülün süit içinde
    iki ayrı isimle yüklenip İKİ AYRI sınıf nesnesi doğurması. Uç noktanın adıyla çağırdığı
    fonksiyonu yamalamak bu belirsizliği tümden ortadan kaldırır."""
    from servers import api_server

    _hasta_ekle(client, "SayacTesti")
    blob = client.post("/api/data/export", json={"passphrase": PAROLA}).json()["data_b64"]

    gercek = api_server.get_patient_database()
    assert gercek is not None, "on-kosul: hasta veritabani hazir olmali"

    class _DiskDolu:
        """Yalnız iki çağrıyı sabote eder, gerisini gerçek nesneye devreder."""

        def __getattr__(self, ad):
            return getattr(gercek, ad)

        def get_patient(self, *a, **k):
            return None  # "zaten var" DEĞİL → gerçek bir başarısızlık senaryosu

        def add_patient(self, *a, **k):
            raise RuntimeError("disk dolu (taklit)")

    monkeypatch.setattr(api_server, "get_patient_database", lambda: _DiskDolu())

    r = client.post(
        "/api/data/import",
        json={"passphrase": PAROLA, "blob_b64": blob, "confirm": "REPLACE_ALL"},
    )
    assert r.status_code == 200, r.text[:200]
    c = r.json()["counts"]

    assert "patient_db_basarisiz" in c and "patient_db_zaten_vardi" in c, f"yanit iki sonucu AYRI raporlamiyor: {c}"
    assert c["patient_db_basarisiz"] > 0, (
        f"gercek basarisizlik hic sayilmadi (muhtemelen 'zaten vardi' kovasina gitti): {c}"
    )
    assert c["patient_db_zaten_vardi"] == 0, f"basarisizlik yanlislikla 'zaten vardi' olarak raporlandi: {c}"
    assert c["patient_db"] == 0, f"add_patient patlarken 'eklendi' sayildi: {c}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
