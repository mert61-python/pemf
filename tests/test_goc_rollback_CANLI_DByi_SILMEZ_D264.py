# -*- coding: utf-8 -*-
"""D2.64 (B-3.76) — GÖÇ ROLLBACK'İ CANLI TEDAVİ DB'SİNİ SİLMEZ.

KUSUR (`thdb_sema._run_startup_migrations_with_rollback`). Sıra şuydu:
  1) göç öncesi yedek alınır ve GEÇERLİLİĞİ sınanır (`_backup_ok`),
  2) `migration_backups` ADA GÖRE sıralanıp en yeni 5 dışındakiler silinir (rotasyon),
  3) göç patlarsa rollback: canlı DB SİLİNİR, sonra yedek kopyalanır.
Rotasyon geçerlilik denetiminden SONRA koştuğu için, adı taze yedekten sonra gelen ≥5 dosya varsa (ileri tarihli /
farklı sürüm önekli eski yedekler — v10→v11 geçişinde ada göre sıralama da kendiliğinden bozulur) TAZE yedek silinir;
rollback canlı DB'yi siler, kopya `FileNotFoundError` ile düşer → cihaz BOŞ tedavi geçmişiyle açılır (2026-09-13 sınıfı).
Aynı pencere kopyalama sırasında disk dolarsa da açıktı: canlı DB önce silindiği için kopya düşünce veri gider.

SÖZLEŞME: (a) az önce alınan yedek rotasyondan MUAFTIR; (b) yedek geçerliliği yıkıcı adımdan hemen önce YENİDEN
sınanır — yoksa canlı DB'ye DOKUNULMAZ, göç hatası yükselir; (c) yedek ÖNCE geçici dosyaya kopyalanır, canlı DB
ancak kopya tamamlanınca tek adımda (`os.replace`) değiştirilir. sqlcipher3 GEREKTİRMEZ (düz-metin kip).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def bes_seansli_db(tmp_path, monkeypatch):
    """5 seanslı GERÇEK tedavi DB'si; şema sürümü geri alınmış (göç dalı koşsun)."""
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    kok = tmp_path / "PEMF_GUI"
    db = thdb.TreatmentHistoryDB(kok)
    for i in range(5):
        db.end_session(db.start_session(f"Seans{i}"))
    db._set_system_setting("db_schema_version", "2", "test: goc dalini sur")
    db.close_connections()
    del db
    return kok


def _gocu_patlat(monkeypatch):
    from database import treatment_history_db as thdb

    def _patla(self):
        raise RuntimeError("disk dolu (taklit) — goc adimi dustu")

    gercek = thdb.TreatmentHistoryDB._ensure_schema_version
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_ensure_schema_version", _patla)
    return gercek


def _seans_sayisi(kok: Path) -> int:
    from database import treatment_history_db as thdb

    db = thdb.TreatmentHistoryDB(kok)
    try:
        return len(db.get_session_history(limit=50))
    finally:
        db.close_connections()


def test_KRITIK_rotasyon_TAZE_yedegi_silemez_rollback_canli_DByi_KORUR(bes_seansli_db, monkeypatch):
    """MUTASYON: rotasyonu yeniden ada göre ve taze yedeği dahil yapmak (geçerlilik denetimi rotasyondan ÖNCE) → KIRMIZI.
    İKİNCİ MUTASYON: sıra değişiklik zamanına göre ama taze yedek muafiyeti YOK → KIRMIZI (eski yedekler saat İLERİDEYKEN
    alınmış: hem adları hem mtime'ları taze yedekten "yeni" — saat düzeltilince olağan)."""
    import os
    import time

    from database import treatment_history_db as thdb

    kok = bes_seansli_db
    mb = kok / "migration_backups"
    mb.mkdir(exist_ok=True)
    ileri = time.time() + 30 * 86400
    for i in range(5):  # adı VE mtime'ı taze yedekten (pre_migration_v2_<şimdi>) SONRA gelen eski yedekler
        f = mb / f"pre_migration_v9_2099010{i}_000000.db"
        f.write_bytes(b"ESKI-YEDEK")
        os.utime(f, (ileri + i, ileri + i))
    gercek = _gocu_patlat(monkeypatch)

    with pytest.raises(Exception):
        thdb.TreatmentHistoryDB(kok)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_ensure_schema_version", gercek)

    # Katman A doğrudan gözlenir (yeniden-sınama katmanı veri kaybını tek başına önlese de rotasyon kusuru
    # GÖRÜNÜR kalsın — katmanlı savunmada tek katman mutantı yoksa eşdeğer kalırdı).
    assert list(mb.glob("pre_migration_v2_*.db")), "rotasyon AZ ÖNCE alınan göç yedeğini SİLDİ"
    assert (kok / "pemf_treatment_history.db").exists(), (
        "göç rollback'i CANLI tedavi DB'sini sildi ve yerine koyamadı → cihaz BOŞ geçmişle açılır"
    )
    assert _seans_sayisi(kok) == 5, "rollback sonrası tedavi geçmişi EKSİK"


def test_KRITIK_yedek_GOC_SIRASINDA_kaybolursa_canli_DBye_dokunulmaz_NEDEN_soylenir(
    bes_seansli_db, monkeypatch, caplog
):
    """Yedek göç sırasında kaybolursa (AV karantinası, elle silme, rotasyon) canlı DB'ye DOKUNULMAZ ve günlük GERÇEK
    nedeni söyler. MUTASYON: yıkıcı adımdan önceki yeniden-sınamayı kaldırmak → KIRMIZI (kopya `FileNotFoundError`
    ile düşer; veri yine yerinde ama operatör yalnız "rollback başarısız" görür)."""
    import logging

    from database import treatment_history_db as thdb

    kok = bes_seansli_db

    def _yedegi_sil_ve_patla(self):
        for p in (kok / "migration_backups").glob("pre_migration_v2_*.db"):
            p.unlink()
        raise RuntimeError("disk dolu (taklit) — goc adimi dustu")

    gercek = thdb.TreatmentHistoryDB._ensure_schema_version
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_ensure_schema_version", _yedegi_sil_ve_patla)
    with caplog.at_level(logging.ERROR), pytest.raises(Exception):
        thdb.TreatmentHistoryDB(kok)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_ensure_schema_version", gercek)

    assert any("Rollback yedegi artik YOK" in r.getMessage() for r in caplog.records), (
        "yedek kaybolunca günlük gerçek nedeni (yedek yok → canlı DB'ye dokunulmadı) SÖYLEMİYOR"
    )
    assert _seans_sayisi(kok) == 5, "yedek kaybolunca tedavi geçmişi EKSİK"


def test_KRITIK_rollback_KOPYASI_dusurse_canli_DB_YERINDE_kalir(bes_seansli_db, monkeypatch):
    """Rollback kopyalanırken disk dolarsa canlı DB YERİNDE kalmalı (kopya önce geçici dosyaya).
    MUTASYON: eski sırayı (önce canlı DB'yi sil, sonra kopyala) geri koymak → KIRMIZI."""
    from database import treatment_history_db as thdb

    kok = bes_seansli_db
    gercek_kopya = shutil.copy2

    def _disk_dolu(src, dst, *a, **k):
        if "migration_backups" in str(src):
            with open(dst, "wb") as f:  # disk kopyanın ORTASINDA doldu: hedefte yarım dosya kalır
                f.write(b"YARIM")
            raise OSError(28, "No space left on device (taklit)")
        return gercek_kopya(src, dst, *a, **k)

    monkeypatch.setattr(shutil, "copy2", _disk_dolu)
    gercek = _gocu_patlat(monkeypatch)

    with pytest.raises(Exception):
        thdb.TreatmentHistoryDB(kok)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_ensure_schema_version", gercek)
    monkeypatch.setattr(shutil, "copy2", gercek_kopya)

    assert (kok / "pemf_treatment_history.db").exists(), "rollback kopyası düşünce CANLI DB silinmiş kaldı"
    assert _seans_sayisi(kok) == 5, "rollback kopyası düştükten sonra tedavi geçmişi EKSİK"
    assert not list(kok.glob("*.rollback.tmp")), "yarım rollback geçici dosyası geride kaldı"


def test_KARSIT_gecerli_yedekle_rollback_GERCEKTEN_geri_yukler(bes_seansli_db, monkeypatch):
    """Rollback "hiç geri yükleme"ye kaymasın: göç patlarsa canlı DB YEDEKTEN geri konur (göç öncesi hâl)."""
    from database import treatment_history_db as thdb

    kok = bes_seansli_db
    gercek = _gocu_patlat(monkeypatch)
    with pytest.raises(Exception):
        thdb.TreatmentHistoryDB(kok)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_ensure_schema_version", gercek)
    yedekler = list((kok / "migration_backups").glob("pre_migration_v2_*.db"))
    assert yedekler, "göç öncesi yedek alınmadı"
    assert _seans_sayisi(kok) == 5


def test_KRITIK_A231_rotasyon_ADA_degil_DEGISIKLIK_ZAMANINA_gore_en_yeni_eskileri_TUTAR(bes_seansli_db):
    """2-A inceleme A2-3.1: D2.64 (a)'nın İKİNCİ yarısı — rotasyon sırası AD değil DEĞİŞİKLİK ZAMANI. Taze yedek muafiyeti
    ayrı ölçülüyordu; "ada göre sırala (taze yine muaf)" mutantı rollback kapılarında 34/34 YEŞİLDİ (ölçüldü). Ada göre
    sırada `pre_migration_v10_*` `…v15_*`ten önce gelir: adları ters sıralı eski yedeklerde EN YENİLER silinir, en eskiler
    kalır (v10→v11 geçişinde kendiliğinden olur)."""
    import os
    import time

    from database import treatment_history_db as thdb

    kok = bes_seansli_db
    mb = kok / "migration_backups"
    mb.mkdir(exist_ok=True)
    simdi = time.time()
    for i in range(6):  # ad sırası ↔ zaman sırası TERS: v10 en YENİ … v15 en ESKİ
        f = mb / f"pre_migration_v1{i}_20260101_000000.db"
        f.write_bytes(b"ESKI-YEDEK")
        os.utime(f, (simdi - (i + 1) * 86400, simdi - (i + 1) * 86400))
    once = {p.name: p.stat().st_mtime for p in mb.glob("pre_migration_*.db")}
    beklenen = set(sorted(once, key=lambda ad: once[ad])[-4:])  # taze HARİÇ en yeni 4 (değişiklik zamanı)

    thdb.TreatmentHistoryDB(kok).close_connections()  # göç başarılı koşar — rotasyon her durumda koşar

    sonra = {p.name for p in mb.glob("pre_migration_*.db")}
    taze = sonra - set(once)
    assert len(taze) == 1, f"taze göç yedeği yok/birden çok: {sorted(taze)}"
    assert sonra - taze == beklenen, (
        f"rotasyon DEĞİŞİKLİK ZAMANINA göre en yeni 4 eski yedeği TUTMADI: kalan {sorted(sonra - taze)}, "
        f"beklenen {sorted(beklenen)}"
    )
