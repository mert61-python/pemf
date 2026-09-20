# Author: mertaygn, cglrgrkn
r"""DÜZ-METİN DB KARANTİNAYA ALINMAZ — göç bekliyor, anahtar uyuşmazlığı DEĞİL.

SAHİP KARARI 2026-09-20 (ölçüm sunuldu, seçim yapıldı).

NE OLUYORDU. Göç geçici bir dosya kilidine takılıp iptal olunca DB **şifresiz** kalıyor ve
at-rest anahtarıyla açılamıyor. Çağıran bunu *"anahtar uyuşmazlığı"* sayıp karantinaya
alıyordu:

    .db  →  .db.acilamadi-20260919_214641      (veri kenara itilir)
    sonra `_semayi_kur(conn)` → YERİNE BOŞ ŞEMA kurulur

Yani klinik geçmişi **boş** görür **ve** yeni seanslar boş DB'ye yazılmaya başlar. Kurtarma
artık "geri adlandır" değil **BİRLEŞTİRME** işidir. Oysa göçün kendi mesajı bile
*"sonraki açılışta yeniden denenecek"* diyor.

YENİ DAVRANIŞ: dosyaya **dokunulmaz**, açılmaz, çağırana `GocBekliyorHatasi` verilir.
Sonraki açılış göçü yeniden dener; başarılı olunca **tüm geçmiş kendiliğinden** geri gelir.

⚠️ CİHAZ AÇILMAYA DEVAM EDER: istisna `RuntimeError` türevidir ve üstteki sarmallar
(`api_server._get_treatment_db` — *"DB hatasi seansi/donanimi DURDURMAZ"* ·
`backend_service._initialize_database_safe`) onu zaten yakalar.

⚠️ KORUMA `karantinaya_al`IN İÇİNE KONDU — çağıran başına DEĞİL. İki çağıran var
(`patient_database.py:239` · `treatment_history_db.py:537`) ve bu depo "aynı kural iki
yerde → sessizce ayrıştı" arızasını **dört kez** yaşadı ([[pemf-yarim-goc-db-kaybolmasi]]).
Üçüncü kopyanın açılmaması için karar tek yerde.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "apps" / "backend"))

from database import sqlcipher_util as su  # noqa: E402

#: SQLite dosya başlığı — şifreli dosyada BULUNMAZ.
_BASLIK = b"SQLite format 3\x00"


def _duz_metin_db(yol: Path, kayit: str = "Hasta") -> Path:
    c = sqlite3.connect(yol)
    c.execute("CREATE TABLE seans(ad TEXT)")
    c.execute("INSERT INTO seans VALUES (?)", (kayit,))
    c.commit()
    c.close()
    return yol


# ═════════════════════════════════════════════════════════════════════════════════════════
# 1. ASIL SÖZLEŞME
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_duz_metin_KARANTINAYA_ALINMAZ(tmp_path):
    """🔴 ASIL REGRESYON: karantina, kliniğin geçmişini kenara itip BOŞ DB kurduruyordu."""
    db = _duz_metin_db(tmp_path / "pemf_treatment_history.db", "GocenHasta")
    once = db.read_bytes()

    with pytest.raises(su.GocBekliyorHatasi):
        su.karantinaya_al(db)

    assert db.exists(), "düz-metin DB kenara alındı — karar bu DEĞİL"
    assert db.read_bytes() == once, "dosyaya DOKUNULDU (içerik değişti)"
    assert not list(tmp_path.glob("*.acilamadi-*")), (
        f"karantina kopyası oluşmuş: {[p.name for p in tmp_path.glob('*.acilamadi-*')]}"
    )


def test_KRITIK_veri_OKUNABILIR_kaliyor(tmp_path):
    """Dosya yerinde kalmakla yetinmez — İÇERİĞİ de sağlam olmalı (sonraki açılış göçü denesin)."""
    db = _duz_metin_db(tmp_path / "x.db", "GocenHasta")
    with pytest.raises(su.GocBekliyorHatasi):
        su.karantinaya_al(db)

    c = sqlite3.connect(db)
    try:
        assert c.execute("SELECT ad FROM seans").fetchall() == [("GocenHasta",)], "veri bozuldu"
    finally:
        c.close()


def test_KRITIK_istisna_RUNTIMEERROR_turevi():
    """⚠️ Cihaz açılmaya devam etmeli: üstteki `except Exception` sarmalları yakalayabilmeli.

    Yeni bir taban sınıf seçilirse (ör. `BaseException`) backend AÇILMAZ — sessiz değil,
    tam tersi: cihaz hiç gelmez. Bu yüzden tür sözleşmesi kilitlenir.
    """
    assert issubclass(su.GocBekliyorHatasi, RuntimeError)
    assert issubclass(su.GocBekliyorHatasi, Exception)


def test_KRITIK_hata_mesaji_EYLEM_soyluyor(tmp_path, caplog):
    """Sahadaki operatör ne yapacağını bilmeli — 'açılamadı' tek başına eylem değildir."""
    import logging

    db = _duz_metin_db(tmp_path / "y.db")
    lg = logging.getLogger("duz_metin_testi")
    with caplog.at_level(logging.ERROR, logger="duz_metin_testi"), pytest.raises(su.GocBekliyorHatasi):
        su.karantinaya_al(db, lg)

    metin = " ".join(r.getMessage() for r in caplog.records)
    assert "KARANTINAYA ALINMADI" in metin, "kararın kendisi log'da yok"
    assert "YAPILACAK" in metin, "operatöre EYLEM söylenmiyor"
    assert "yeniden baslatin" in metin.lower(), "kurtarma adımı yazılmamış"


# ═════════════════════════════════════════════════════════════════════════════════════════
# 2. KARŞIT-KANITLAR — koruma FAZLA geniş olmamalı
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_SIFRELI_dosya_HALA_karantinaya_alinir(tmp_path):
    """⚠️ Asıl risk bu: koruma fazla genişlerse GERÇEK anahtar uyuşmazlığı da karantinaya
    alınmaz ve cihaz açılamayan bir DB'yle kilitlenir."""
    db = tmp_path / "sifreli.db"
    db.write_bytes(bytes(range(256)) * 8)  # SQLite başlığı YOK
    assert db.read_bytes()[: len(_BASLIK)] != _BASLIK

    sonuc = su.karantinaya_al(db)
    assert sonuc is not None, "şifreli/bozuk dosya karantinaya ALINMADI — koruma fazla geniş"
    assert not db.exists(), "dosya kenara alınmadı"


def test_KARSIT_KANIT_BOS_dosya_karantinaya_alinir(tmp_path):
    """⚠️ 0 baytlık dosyayı `sqlite3.connect` SORUNSUZ açar ve `sqlite_master` BOŞ döner —
    istisna ATMAZ. Yalnız sqlite3 probu kullanılsaydı boş dosya 'düz-metin' sayılır ve
    cihaz hiç toparlanamazdı. Bu yüzden BAŞLIK kontrolü de şart."""
    db = tmp_path / "bos.db"
    db.write_bytes(b"")
    assert su.duz_metin_sqlite_mi(db) is False, "boş dosya düz-metin sayıldı — cihaz kilitlenir"
    assert su.karantinaya_al(db) is not None, "boş dosya karantinaya alınmadı"


def test_KARSIT_KANIT_dosya_YOKSA_None(tmp_path):
    """Var olmayan dosya için davranış DEĞİŞMEMELİ (istisna değil, None)."""
    assert su.karantinaya_al(tmp_path / "hic-yok.db") is None


def test_KARSIT_KANIT_prob_IKI_kosulu_da_ariyor(tmp_path):
    """Başlık doğru ama içerik bozuksa düz-metin SAYILMAZ (yarım yazılmış dosya)."""
    db = tmp_path / "yarim.db"
    db.write_bytes(_BASLIK + b"\x00" * 40)  # başlık var, geçerli DB değil
    assert su.duz_metin_sqlite_mi(db) is False, (
        "yalnız başlığa bakılıyor — bozuk dosya düz-metin sayılırsa karantina hiç çalışmaz"
    )


def test_KARSIT_KANIT_prob_TUTAMAGI_KAPATIYOR(tmp_path, monkeypatch):
    """⚠️ Prob bir sqlite bağlantısı açar. Kapatılmazsa Windows'ta SONRAKİ taşıma/silme
    WinError 32'ye düşer — tam da bu dosyanın konusu olan arızanın kendisi.

    ⚠️ BU TESTİN İLK HÂLİ VAKUMDU — mutasyon (G4) ortaya çıkardı. İlk yazımda probu
    çağırıp ardından taşımayı deniyordum; `close()` satırını silen mutasyon YEŞİL geçti,
    çünkü **CPython refcount'u** fonksiyon çıkışında bağlantıyı zaten kapatıyor (üstelik
    `_kilit_direncli_tasi` ayrıca `gc.collect()` çağırıyor). Yani test, ölçtüğünü sandığı
    şeyi ölçemiyordu.

    Şimdi bağlantıya DIŞARIDAN referans tutuluyor: refcount devreye giremez, geriye
    yalnız AÇIK `close()` çağrısı kalır ve gerçekten gözlemlenir.
    """
    db = _duz_metin_db(tmp_path / "tutamak.db")
    acilanlar: list[sqlite3.Connection] = []
    gercek = sqlite3.connect

    def _izle(*a, **k):
        c = gercek(*a, **k)
        acilanlar.append(c)  # ⚠️ referans BURADA tutulur → refcount kapatamaz
        return c

    monkeypatch.setattr(su.sqlite3, "connect", _izle)
    assert su.duz_metin_sqlite_mi(db) is True
    assert len(acilanlar) == 1, f"beklenen 1 bağlantı, açılan {len(acilanlar)}"

    with pytest.raises(sqlite3.ProgrammingError):
        acilanlar[0].execute("SELECT 1")  # kapalı bağlantı → ProgrammingError


def test_KARSIT_KANIT_koruma_KARANTINAYA_AL_icinde(tmp_path):
    """⚠️ Karar TEK yerde olmalı: iki çağıran (patient_database · treatment_history_db)
    otomatik almalı. Çağıran başına kopyalanırsa üçüncü ayrışma doğar."""
    import inspect

    kaynak = inspect.getsource(su.karantinaya_al)
    kod = "\n".join(s.split("#")[0] for s in kaynak.splitlines())
    assert "duz_metin_sqlite_mi(" in kod, "koruma `karantinaya_al` İÇİNDE değil"
    assert "GocBekliyorHatasi" in kod, "istisna karantina fonksiyonundan yükselmiyor"
