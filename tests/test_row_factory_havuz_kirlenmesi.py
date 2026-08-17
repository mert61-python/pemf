# Author: mertaygn, cglrgrkn
"""HAVUZ BAĞLANTISI KİRLENMESİ — `row_factory` geçici override'ı GERİ YÜKLENMELİ.

DENETİM BULGUSU (2026-08-17). `TreatmentHistoryDB.denetim_oku` havuzdaki bağlantının
`row_factory`'sini dict üreten bir lambda'ya çeviriyor ama **geri yüklemiyor**. Havuz bağlantıyı
thread-başına YENİDEN KULLANIR (kuşak yalnız migration/restore/close'da artar) → kirlenme
**süreç ömrü boyunca** sürer, kendini onarmaz.

ÖLÇÜLEN SONUÇLAR (uçtan uca, gerçek FastAPI + kalıcı event-loop):
  * `GET /api/audit/events` **bir kez** → `GET /api/settings/retention` sonsuza dek `pending: 0`
    döner → `SettingsScreen` (`retention.pending > 0 ?`) KVKK onay bloğunu bir daha ÇİZMEZ →
    operatör geri dönüşsüz maskelemeyi ONAYLAYAMAZ. Sonuç veri kaybı değil, **veri FAZLA-SAKLAMA**.
  * `POST /api/support/bundle` **bir kez** → `POST /api/data/export` **ve** `/api/data/import`
    süreç boyunca **500**. Yani "sorun yaşayınca destek paketi üret" → "yedek al / yedekten dön" BLOKE.

Sebep: `row_factory` dict döndürünce `row[0]` / `row["id"]` gibi POZİSYONEL erişimler kırılır
(`KeyError: 0`), `PRAGMA quick_check` sonucu `str(row[0])` ile okunamaz vb.

⚠️ SORUN ZATEN BİLİNİYORDU — kaynakta değil TESTTE geçici çözülmüş:
`tests/test_prod_readiness_fixes.py:95` → `c.row_factory = None  # sync_worker paylaşılan
bağlantıda dict-factory bıraktı → sıfırla`. Aynı sınıf `servers/sync_worker.py`'de de var.
Havuz commit `3f97c8c` (2026-08-03) ile geldi, `row_factory` satırı `0e2b1ed` — "havuz eklendi,
yan etki gözden kaçtı" regresyonu. `tests/test_db_connection_pool.py` havuzun 5 değişmezini
kilitliyor ama `row_factory` restore'unu kilitlemiyordu.

⚠️ RESTORE DEĞERİ SABİT OLAMAZ: havuz bağlantıyı düz SQLite'ta `sqlite3.Row`, at-rest şifreli
kurulumda `sqlcipher.Row` ile kurar. Bu yüzden ÖNCEKİ değer saklanıp geri konur, `None`a
sıfırlanmaz (aksi hâlde `row["kolon"]` erişimleri şifreli kurulumda kırılırdı).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.treatment_history_db import TreatmentHistoryDB  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    return TreatmentHistoryDB(tmp_path)


def test_KRITIK_denetim_oku_row_factoryi_GERI_YUKLER(db):
    """Yapısal çıpa: geçici override'dan sonra bağlantı ESKİ fabrikasına dönmeli."""
    with db._get_connection() as conn:
        onceki = conn.row_factory

    db.denetim_oku(10)

    with db._get_connection() as conn:
        assert conn.row_factory is onceki, (
            "denetim_oku havuz baglantisinin row_factory'sini KALICI degistirdi. Havuz baglantiyi "
            "thread-basina yeniden kullanir → surec omru boyunca kirli kalir."
        )


def test_KRITIK_denetim_okudan_SONRA_butunluk_kontrolu_hala_dogru(db):
    """`run_integrity_check` sağlam DB'yi "bozuk" raporlamamalı.

    `PRAGMA quick_check` sonucu `str(row[0])` ile okunuyor; dict fabrikası `row[0]`'ı KeyError'a
    çevirir → sonuç `{'ok': False, 'details': ['0']}` olur ve açılışta ERROR loglanır."""
    assert db.run_integrity_check()["ok"] is True, "on-kosul: temiz DB saglam olmali"

    db.denetim_oku(10)

    sonra = db.run_integrity_check()
    assert sonra["ok"] is True, f"denetim_oku'dan sonra SAGLAM DB 'bozuk' raporlaniyor: {sonra}"


def test_KRITIK_denetim_okudan_SONRA_redaksiyon_sayimi_hala_dogru(db):
    """`redaksiyon_bekleyen_sayisi` KVKK onay diyaloğunun TEK girdisidir.

    Kirlenmeden sonra KeyError yutulup `0` döner → arayüzdeki onay bloğu (`pending > 0`) bir daha
    hiç çizilmez → operatör geri dönüşsüz maskelemeyi onaylayamaz (veri FAZLA-SAKLAMA).

    ⚠️ SIFIR-OLMAYAN bir sayım ŞART: boş DB'de her iki ölçüm de 0 döner ve test kirlenmeyi
    GÖRMEZDİ (yanlış-yeşil). Retention penceresinin DIŞINDA kalan gerçek bir seans yazılır."""
    sid = db.start_session("Manuel", operator_name="Dr. Test", patient_name="Pamuk")
    assert sid, "on-kosul: seans satiri olusturulamadi"
    # Seansı 2 yıl geriye al → 365 günlük retention penceresinin dışında kalsın.
    # ⚠️ Sayım `session_date`e bakar (`start_time`e DEĞİL) — bkz. redaksiyon_bekleyen_sayisi sorgusu.
    with db._get_connection() as conn:
        conn.execute("UPDATE treatment_sessions SET session_date = date('now', '-730 day') WHERE id = ?", (sid,))
        conn.commit()

    onces = db.redaksiyon_bekleyen_sayisi(365)
    assert onces > 0, f"on-kosul: bekleyen redaksiyon SIFIR-OLMAMALI (gelen {onces})"

    db.denetim_oku(10)

    assert db.redaksiyon_bekleyen_sayisi(365) == onces, (
        "denetim_oku'dan sonra redaksiyon sayimi degisti → KVKK onay blogu gorunmez olur"
    )


def test_denetim_oku_KENDI_isini_yapmaya_devam_eder_karsit_kanit(db):
    """Karşı-kanıt: düzeltme `denetim_oku`nun sözleşmesini BOZMAMALI — dict döndürmeye devam eder."""
    # ⚠️ `record_session_event` AYRI bir tabloya (`session_events`) yazar; `denetim_oku`
    # `audit_events`'i okur. Doğru yazar `denetim_yaz`.
    assert db.denetim_yaz("test_olayi", operator_email="a@b.c", scope="test") is True

    kayitlar = db.denetim_oku(10)
    assert kayitlar, "denetim kaydi okunamadi"
    assert isinstance(kayitlar[0], dict), "denetim_oku artik dict dondurmuyor — sozlesme bozuldu"
    assert "event_type" in kayitlar[0], "kolon adlariyla erisim kayboldu"


def test_bos_tabloda_da_KIRLETMEZ_karsit_kanit(db):
    """Karşı-kanıt: satır YOKKEN de `row_factory` atanıyordu → boş tablo da zehirliyordu."""
    with db._get_connection() as conn:
        onceki = conn.row_factory

    assert db.denetim_oku(10) == [] or True  # içerik konu değil
    db.denetim_oku(10)

    with db._get_connection() as conn:
        assert conn.row_factory is onceki


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
