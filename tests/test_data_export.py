# Author: mertaygn, cglrgrkn
"""CİHAZ TAŞIMA — şifreli dışa/içe aktarma (2026-08-08).

BAĞLAM: kayıtlar bilerek MAKİNEDE tutuluyor (bulut senkronu yok — kişisel veri yurt dışına
çıkmasın, kayıt kliniğin olsun). Tek gerçek dezavantajı cihaz değişimiydi; çözümü bulut değil,
kliniğin kendi kontrolündeki şifreli dosya. Bu testler o dosyanın GÜVENLİ ve KAYIPSIZ olduğunu
kilitler — yanlış çalışırsa klinik geçmişi sessizce kaybolur ya da açığa çıkar.
"""

import pytest

from utils.data_export import (
    BUNDLE_VERSION,
    MAGIC,
    MIN_PAROLA,
    ExportError,
    decrypt_bundle,
    encrypt_bundle,
    parola_gecerli_mi,
)

# ⚠️ 2026-08-09 (Tier 1): yedek parolası artık asgari politikaya tabi (bkz. `parola_gecerli_mi`).
# Bu dosyanın KRİPTO testleri politikayı sınamaz → hepsi geçerli bir parola cümlesi kullanır.
PAROLA = "klinik-yedek-2026"
PAROLA2 = "baska-bir-parola-2026"


def _db(temp_app_data):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(temp_app_data)


# ───────────────────────── kripto ─────────────────────────


def test_gidis_donus_veriyi_KORUR():
    p = {
        "bundle_version": BUNDLE_VERSION,
        "patients": [{"name": "Pamuk", "owner": "Ali"}],
        "treatment_sessions": [{"id": 1}],
        "ai_analyses": [],
    }
    assert decrypt_bundle(encrypt_bundle(p, PAROLA), PAROLA) == p


def test_KRITIK_yanlis_parola_ACAMAZ():
    blob = encrypt_bundle({"bundle_version": 1, "patients": [{"name": "Pamuk"}]}, PAROLA)
    with pytest.raises(ExportError):
        decrypt_bundle(blob, PAROLA2)


def test_KRITIK_hasta_adi_dosyada_DUZ_METIN_DEGIL():
    blob = encrypt_bundle({"bundle_version": 1, "patients": [{"name": "Pamuk", "owner": "Ali Veli"}]}, PAROLA)
    assert b"Pamuk" not in blob and b"Ali Veli" not in blob, "kisisel veri sifresiz yazilmis"


def test_KRITIK_tuz_HER_DOSYADA_FARKLI():
    # Sabit tuz (source_crypto'daki gibi) burada YANLIS olurdu: onceden hesaplanmis tablolara ve
    # ayni parolayla uretilen dosyalar arasinda iliskilendirmeye acik hale gelirdi.
    a = encrypt_bundle({"bundle_version": 1}, PAROLA)
    b = encrypt_bundle({"bundle_version": 1}, PAROLA)
    tuz = lambda x: x[len(MAGIC) : len(MAGIC) + 16]
    assert tuz(a) != tuz(b), "tuz sabit — rastgele olmali"
    assert a != b


def test_bos_parola_REDDEDILIR():
    with pytest.raises(ExportError):
        encrypt_bundle({"bundle_version": 1}, "   ")


def test_kurcalanmis_dosya_ACILMAZ():
    blob = bytearray(encrypt_bundle({"bundle_version": 1, "x": "y"}, PAROLA))
    blob[-5] ^= 0xFF  # jetonun son baytini boz
    with pytest.raises(ExportError):
        decrypt_bundle(bytes(blob), PAROLA)


def test_yabanci_dosya_ANLASILIR_hata_verir():
    with pytest.raises(ExportError, match="PEMF Vet veri yedeği değil"):
        decrypt_bundle(b"rastgele bir dosya icerigi", PAROLA)


def test_daha_yeni_surum_REDDEDILIR():
    blob = encrypt_bundle({"bundle_version": BUNDLE_VERSION + 1}, PAROLA)
    with pytest.raises(ExportError, match="daha yeni"):
        decrypt_bundle(blob, PAROLA)


# ───────────────────────── DB dışa/içe aktarma ─────────────────────────


def test_export_LIMITSIZ_tum_satirlari_alir(temp_app_data):
    # get_ai_analyses limit'i 500'e sabitler; tasimada kullanilsaydi 500+ kayitli klinikte
    # SESSIZ VERI KAYBI olurdu.
    db = _db(temp_app_data)
    for i in range(120):
        db.add_ai_analysis(module_id="m", patient_name=f"H{i}", result_summary="s")
    rows = db.export_rows()
    assert len(rows["ai_analyses"]) == 120


def test_ice_aktarma_icerigi_korur(temp_app_data, tmp_path):
    kaynak = _db(temp_app_data)
    sid = kaynak.start_session("Manuel", patient_name="Pamuk")
    kaynak.add_ai_analysis(
        module_id="cat_disease", patient_name="Pamuk", result_summary="ozet", operator_email="v@x.com"
    )
    paket = kaynak.export_rows()

    hedef_dir = tmp_path / "yeni_cihaz"
    hedef_dir.mkdir()
    from database.treatment_history_db import TreatmentHistoryDB

    hedef = TreatmentHistoryDB(hedef_dir)
    n = hedef.import_rows(paket, replace=False)

    # ⚠️ 2026-08-09: `import_rows` artık TÜM taşınan tabloların sayımını döner (bobin koşuları,
    # sensör, olaylar…). Eskiden yalnız iki tablo taşınıyordu — uygulanan dozun kaydı cihaz
    # değişiminde SESSİZCE kayboluyordu. Bu testin konusu İÇERİĞİN korunması; sözlüğün tam
    # şeklini dondurmak yerine ilgili sayımlara bak.
    assert n["treatment_sessions"] == 1 and n["ai_analyses"] == 1
    analiz = hedef.get_ai_analyses(limit=10)[0]
    assert analiz["patient_name"] == "Pamuk"
    assert analiz["result_summary"] == "ozet"
    assert analiz["operator_email"] == "v@x.com"
    # id KORUNMAZ (AUTOINCREMENT, hedefte cakisabilir) — icerik korunur.
    assert hedef.get_session_history(limit=5)[0]["patient_name"] == "Pamuk"
    assert sid is not None


def test_replace_hedefi_TEMIZLER(temp_app_data, tmp_path):
    hedef_dir = tmp_path / "dolu_cihaz"
    hedef_dir.mkdir()
    from database.treatment_history_db import TreatmentHistoryDB

    hedef = TreatmentHistoryDB(hedef_dir)
    hedef.add_ai_analysis(module_id="eski", patient_name="EskiHasta", result_summary="x")

    kaynak = _db(temp_app_data)
    kaynak.add_ai_analysis(module_id="yeni", patient_name="YeniHasta", result_summary="y")

    hedef.import_rows(kaynak.export_rows(), replace=True)
    adlar = [r["patient_name"] for r in hedef.get_ai_analyses(limit=10)]
    assert adlar == ["YeniHasta"], f"replace eski kayitlari birakti: {adlar}"


def test_bilinmeyen_kolon_ICE_AKTARMAYI_KIRMAZ(temp_app_data, tmp_path):
    # Eski/yeni surum arasi tasima: kaynakta olup hedefte olmayan kolon satiri dusurmemeli.
    kaynak = _db(temp_app_data)
    kaynak.add_ai_analysis(module_id="m", patient_name="P", result_summary="s")
    paket = kaynak.export_rows()
    paket["ai_analyses"][0]["gelecekte_eklenen_kolon"] = "deger"

    hedef_dir = tmp_path / "h2"
    hedef_dir.mkdir()
    from database.treatment_history_db import TreatmentHistoryDB

    hedef = TreatmentHistoryDB(hedef_dir)
    assert hedef.import_rows(paket, replace=False)["ai_analyses"] == 1


# ── PAROLA POLİTİKASI + ROUND-TRIP (2026-08-09 denetimi, Tier 1) ─────────────
# ARIZA 1: tek kural "boş olmasın"dı — TEK KARAKTERLİK parola kabul ediliyordu. Bu dosya bir
# kliniğin TÜM hasta geçmişini taşır ve kopyası off-site'a gider; oradaki tek koruma paroladır.
# ARIZA 2: üretilen dosyanın gerçekten AÇILABİLDİĞİ hiç doğrulanmıyordu → bozuk bir yedeğin
# bozuk olduğu, ancak kullanılması gereken gün (eski makine ölmüş) anlaşılırdı.


def test_KRITIK_kisa_parola_REDDEDILIR():
    import pytest as _p

    from utils.data_export import MIN_PAROLA, ExportError, encrypt_bundle

    for kotu in ("a", "1234", "kisa", ("abcdefgh" * 3)[: MIN_PAROLA - 1]):
        with _p.raises(ExportError):
            encrypt_bundle({"x": 1}, kotu)


def test_KRITIK_tekrarli_parola_REDDEDILIR():
    """'aaaaaaaaaaaa' uzunluk kuralını geçer ama entropisi yoktur."""
    import pytest as _p

    from utils.data_export import ExportError, encrypt_bundle

    with _p.raises(ExportError):
        encrypt_bundle({"x": 1}, "aaaaaaaaaaaaaaaa")


def test_gecerli_parola_KABUL_edilir():
    from utils.data_export import decrypt_bundle, encrypt_bundle

    blob = encrypt_bundle({"x": 1}, "klinik-yedek-2026")
    assert decrypt_bundle(blob, "klinik-yedek-2026") == {"x": 1}


def test_parola_kurali_TEK_YERDE():
    """İstemci ve sunucu aynı kuralı uygulasın diye yardımcı dışa açık olmalı."""
    # NOT: yalnız uzunluk yetmez — tekrar kuralı da var, o yüzden çeşitli karakterli örnek.
    yeterli = ("abcdefgh" * 3)[:MIN_PAROLA]
    assert parola_gecerli_mi(yeterli)[0] is True
    assert parola_gecerli_mi(yeterli[:-1])[0] is False
    ok, sebep = parola_gecerli_mi("")
    assert ok is False and sebep
