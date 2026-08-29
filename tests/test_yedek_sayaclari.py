# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YEDEK SAYAÇLARI — arayüzün OKUDUĞU anahtar, backend'in YAZDIĞI anahtarla aynı olmalı.

DENETİM BULGUSU 2026-08-28 #05 (sessiz ölüm, veri kaybı YOK):
    * `/api/data/export` → `counts` içinde `patient_db` vardı, `patients` **hiç yoktu**;
    * arayüz (`SettingsScreen`, masaüstü + yayınlanmış APK'lar) `counts.patients ?? 0` okuyor;
    * sonuç: 300 hastalık yedek alan operatör **"Yedek oluşturuldu: 0 hasta"** görüyordu.
    * `/api/data/import` daha ters: yanıttaki `patients` gerçek hasta sayısı DEĞİL, tedavi
      DB'sindeki **FK hasta kopyasının** satır sayısıydı — arayüz yanlış olanı okuyordu.

Veri her iki durumda da doğru taşınıyordu; YALAN SÖYLEYEN SAYIYDI. Operatör yedeğine güvenmiyor
ya da işlemi tekrarlıyordu — ikisi de tıbbi kayıt taşımada kötü.

⚠️ Bu dosyanın varlık sebebi: eski test yalnız BACKEND anahtarlarını kilitliyordu; sayacı
TÜKETEN tarafı kimse kontrol etmemişti. Buradaki kapı sözleşmenin iki ucunu da tutar —
`SettingsScreen.tsx`'in gerçekten hangi anahtarı okuduğu kaynaktan doğrulanır (kopya değil).
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

PAROLA = "sayac-kapisi-2026"
_AYAR_TSX = Path(__file__).resolve().parents[1] / "pf" / "src" / "screens" / "SettingsScreen.tsx"


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51235))


def _hasta_ekle(client, ad: str) -> str:
    r = client.post("/api/patients", json={"name": ad, "species": "Kedi", "owner": "Sahip"})
    assert r.status_code == 200, r.text[:300]
    return str(r.json().get("patient_id") or r.json().get("id"))


def _mevcut_hasta_sayisi(client) -> int:
    r = client.get("/api/patients")
    assert r.status_code == 200, r.text[:300]
    return len(r.json().get("data") or [])


def _disa_aktar(client) -> dict:
    r = client.post("/api/data/export", json={"passphrase": PAROLA})
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ── 1) Arayüzün okuduğu anahtarlar (kaynaktan, kopyasız) ──────────────────────


def _arayuzun_okudugu_anahtarlar() -> set[str]:
    """SettingsScreen.tsx'te `c.<anahtar> ?? 0` biçiminde okunan sayaç adları."""
    assert _AYAR_TSX.exists(), f"Arayüz kaynağı yok: {_AYAR_TSX}"
    metin = _AYAR_TSX.read_text(encoding="utf-8")
    anahtarlar = set(re.findall(r"\bc\.([A-Za-z_][A-Za-z0-9_]*)\s*\?\?", metin))
    assert anahtarlar, "SettingsScreen.tsx'te 'c.<anahtar> ??' okuması bulunamadı (çıpa kaydı mı?)"
    return anahtarlar


def test_arayuz_sayac_okumasi_bulunabiliyor():
    """Kapının kendisi çalışıyor mu: en azından hasta sayacı okunuyor olmalı."""
    assert "patients" in _arayuzun_okudugu_anahtarlar(), (
        "Arayüz artık 'patients' okumuyor — sözleşme değiştiyse bu testi ve backend'i BİRLİKTE güncelleyin"
    )


# ── 2) Export: arayüzün okuduğu her anahtar yanıtta OLMALI ───────────────────


def test_KRITIK_export_sayaci_gercek_hasta_sayisini_verir(client):
    """Ana bulgu: `counts.patients` var VE gerçek hasta sayısına eşit."""
    onceki = _mevcut_hasta_sayisi(client)
    _hasta_ekle(client, "SayacTest-A")
    _hasta_ekle(client, "SayacTest-B")
    beklenen = onceki + 2

    c = _disa_aktar(client)["counts"]

    assert "patients" in c, f"'patients' anahtarı yanıtta YOK → arayüz 0 gösterir. Gelen: {sorted(c)}"
    assert c["patients"] == beklenen, f"yanlış hasta sayısı: {c['patients']} ≠ {beklenen}"
    # Geriye uyum: eski anahtar da kalmalı ve AYNI değeri taşımalı.
    assert c.get("patient_db") == c["patients"], "patient_db ile patients uyuşmuyor"


def test_export_arayuzun_OKUDUGU_her_anahtari_dondurur(client):
    """Sözleşmenin iki ucu: arayüz hangi sayacı okuyorsa backend onu yazmalı."""
    c = _disa_aktar(client)["counts"]
    eksik = _arayuzun_okudugu_anahtarlar() - set(c)
    # Yalnız içe-aktarmaya özgü alanlar export yanıtında beklenmez.
    eksik -= {"patient_db_zaten_vardi", "patient_db_basarisiz"}
    assert not eksik, f"Arayüz bu sayaçları okuyor ama export dönmüyor → sessizce 0 gösterilir: {sorted(eksik)}"


# ── 3) Import: `patients` FK kopyası DEĞİL, gerçekten eklenen hasta ──────────


def _fk_kopyasi_olustur(client, adet: int = 3) -> None:
    """Tedavi DB'sinin hasta KOPYASINA satır yaz (normalde seans kaydedilirken oluşur).

    Bu olmadan iki sayaç (FK kopyası / gerçekten eklenen hasta) tesadüfen EŞİT kalır ve test
    aradaki farkı göremez — kapı, yakalaması gereken hatayı kaçırır. Ölçülerek eklendi:
    bu kurulum olmadan 'FK sayacı yine sızsın' mutasyonu YEŞİL geçiyordu.
    """
    from servers.api_server import _get_treatment_db

    thdb = _get_treatment_db()
    for i in range(adet):
        thdb.upsert_patient(
            {
                "id": f"fk-kopya-{i}-8888-4444-aaaa-{i:012d}",
                "name": f"FkKopya{i}",
                "species": "Kedi",
                "owner_name": "Sahip",
            }
        )


def test_KRITIK_import_sayaci_FK_kopyasini_DEGIL_eklenen_hastayi_verir(client):
    """`n['patients']` (tedavi DB'sinin hasta KOPYASI) arayüze sızmamalı.

    Senaryo BİLEREK iki sayacın ayrıştığı noktada kurulur: hedef DOLU olduğu için gerçekten
    eklenen hasta 0 iken, REPLACE_ALL sonrası FK kopyası tablosu yeniden dolar (>0). Eski kod
    bu durumda arayüze FK sayısını gösteriyordu — "N hasta geri yüklendi" diye okunan sayı,
    aslında geri yüklenen hasta sayısı değildi.
    """
    _hasta_ekle(client, "SayacTest-Import")
    _fk_kopyasi_olustur(client)
    paket = _disa_aktar(client)

    r = client.post(
        "/api/data/import",
        json={"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"},
    )
    assert r.status_code == 200, r.text[:300]
    c = r.json()["counts"]

    assert "patients" in c, "import yanıtında 'patients' yok"
    assert c["patients"] == c["patient_db"], (
        f"'patients' gerçekten eklenen hasta sayısını taşımıyor: {c['patients']} ≠ {c['patient_db']} "
        f"(FK kopyası sızmış olabilir: patients_fk_kopya={c.get('patients_fk_kopya')})"
    )
    # Senaryonun gerçekten ayrıştığını DOĞRULA — aksi hâlde test hiçbir şey kanıtlamaz.
    assert c.get("patients_fk_kopya", 0) != c["patient_db"], (
        f"kurulum ayrışmadı (FK={c.get('patients_fk_kopya')}, eklenen={c['patient_db']}) — "
        f"bu koşuda test FK sızmasını AYIRT EDEMEZ, senaryoyu düzeltin"
    )
    # Üç-sonuç ayrımı KORUNMALI: arayüz "0 hasta"nın anlamını bu alanlardan çözer.
    for alan in ("patient_db_zaten_vardi", "patient_db_basarisiz"):
        assert alan in c, f"üç-sonuç ayrımı kayboldu: '{alan}' yok"


def test_import_FK_kopyasi_ayri_ADLA_hala_raporlanir(client):
    """Karşı-kanıt: FK sayacı SİLİNMEDİ, yalnız yanıltıcı adından kurtarıldı (tanı değeri korunur)."""
    paket = _disa_aktar(client)
    r = client.post(
        "/api/data/import",
        json={"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"},
    )
    assert r.status_code == 200, r.text[:300]
    assert "patients_fk_kopya" in r.json()["counts"], "FK sayacı büsbütün kayboldu (tanı bilgisi kaybı)"


def test_base64_paketi_gercekten_cozulebiliyor_karsit_kanit(client):
    """Karşı-kanıt: sayaç düzeltmesi yedek DOSYASINA dokunmadı."""
    ham = base64.b64decode(_disa_aktar(client)["data_b64"])
    assert len(ham) > 100, "yedek blob'u anlamsız derecede küçük"
