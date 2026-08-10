# Author: mertaygn, cglrgrkn
"""KVKK SİLME HAKKI (2026-08-08) — AI analiz geçmişini silme.

BAĞLAM: bugüne kadar AI geçmişini silmenin HİÇBİR yolu yoktu. Uygulamayı kaldırmak da silmiyor
(tıbbi kayıt kasıtlı korunuyor, bkz. hooks.nsi), tek yol bir PowerShell script'iydi.

Kilitlenen davranışlar:
  * kullanıcı KENDİ kaydını siler, BAŞKASININKİNİ silemez (operator_email kapısı),
  * toplu silme sonrası hasta adı/özet dosyada KURTARILAMAZ (VACUUM — audit P3 kuralı),
  * seans geçmişi ve hasta kayıtları ETKİLENMEZ.
"""


def _db(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(temp_app_data)


def _ekle(db, hasta, op, ozet="ozet"):
    return db.add_ai_analysis(
        mode="veterinarian",
        module_id="cat_disease",
        module_label="Hastalik",
        patient_name=hasta,
        input_type="form",
        result_summary=ozet,
        result_detail={"x": 1},
        confidence=0.9,
        operator_email=op,
    )


def test_kendi_kaydini_siler(temp_app_data):
    db = _db(temp_app_data)
    i = _ekle(db, "Pamuk", "ben@example.com")
    assert db.delete_ai_analysis(i, "ben@example.com") is True
    assert [r["id"] for r in db.get_ai_analyses(limit=50)] == []


def test_KRITIK_baskasinin_kaydini_SILEMEZ(temp_app_data):
    db = _db(temp_app_data)
    i = _ekle(db, "Pamuk", "baskasi@example.com")
    assert db.delete_ai_analysis(i, "ben@example.com") is False, "baskasinin kaydi silindi"
    assert len(db.get_ai_analyses(limit=50)) == 1, "kayit gitmis olmamali"


def test_sahipsiz_eski_kayit_silinebilir(temp_app_data):
    # operator_email kolonu SONRADAN eklendi → eski kayitlar sahipsiz. Silinemez olsalardi
    # kullanicinin kendi eski kayitlarini kaldirmasi imkansiz olurdu.
    db = _db(temp_app_data)
    i = _ekle(db, "Pamuk", "")
    assert db.delete_ai_analysis(i, "ben@example.com") is True


def test_toplu_silme_kapsami(temp_app_data):
    db = _db(temp_app_data)
    _ekle(db, "A", "ben@example.com")
    _ekle(db, "B", "baskasi@example.com")
    _ekle(db, "C", "")  # sahipsiz → "benim" kapsamina dahil
    n = db.clear_ai_analyses("ben@example.com")
    assert n == 2, f"kapsam disi kayit silindi/kaldi: {n}"
    kalan = db.get_ai_analyses(limit=50)
    assert [r["patient_name"] for r in kalan] == ["B"]


def test_toplu_silme_tum_klinik(temp_app_data):
    db = _db(temp_app_data)
    _ekle(db, "A", "x@example.com")
    _ekle(db, "B", "y@example.com")
    assert db.clear_ai_analyses(None) == 2
    assert db.get_ai_analyses(limit=50) == []


def test_KRITIK_silinen_PII_dosyada_KURTARILAMAZ(temp_app_data):
    """VACUUM olmadan `DELETE` sayfalari SERBEST LISTEYE birakir — hasta adi/ozet dosyada
    okunabilir kalir ve kurtarilabilir. Hasta toplu-silmesinde audit P3 olarak yakalanan hatanin
    aynisi.

    ⚠️ DOSYA BOYUTU ILE OLCME YANLIS: DB WAL kipinde: veri once `-wal` dosyasina gider, ana dosya
    uzun sure 4096 baytta kalir. Mekanizmayi DOGRUDAN olcuyoruz: VACUUM tum dosyayi yeniden yazar
    → `freelist_count` SIFIR olur. VACUUM yoksa silinen sayfalar serbest listede birikir.
    """
    db = _db(temp_app_data)
    for i in range(200):
        _ekle(db, f"Hasta{i}", "ben@example.com", ozet="X" * 500)

    def _pragma(ad):
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cur.execute(f"PRAGMA {ad}")
            return int(cur.fetchone()[0] or 0)

    sayfa_once = _pragma("page_count")
    assert sayfa_once > 5, "test anlamli olsun diye veri birden fazla sayfa kaplamali"

    assert db.clear_ai_analyses(None) == 200

    assert _pragma("freelist_count") == 0, (
        "VACUUM uygulanmamis: silinen sayfalar serbest listede duruyor → hasta adlari/ozetleri "
        "dosyada kurtarilabilir kalir."
    )
    assert _pragma("page_count") < sayfa_once, "dosya yeniden yazilmamis (VACUUM etkisiz)"


def test_silme_SEANS_gecmisini_ETKILEMEZ(temp_app_data):
    # AI gecmisini silmek klinik seans kaydini silmemeli — ikisi ayri yasal kayit.
    db = _db(temp_app_data)
    sid = db.start_session("Manuel", patient_name="Pamuk")
    _ekle(db, "Pamuk", "ben@example.com")
    db.clear_ai_analyses(None)
    assert [r["id"] for r in db.get_session_history(limit=10)] == [sid], "seans gecmisi silindi"


def test_olmayan_kayit_sessizce_basarisiz(temp_app_data):
    db = _db(temp_app_data)
    assert db.delete_ai_analysis(999999, None) is False
