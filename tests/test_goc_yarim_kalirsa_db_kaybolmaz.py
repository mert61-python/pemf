# -*- coding: utf-8 -*-
# Author: mertaygn
"""GÖÇ YARIDA KESİLİRSE VERİTABANI KAYBOLMAMALI (2026-09-13).

===============================================================================
NASIL BULUNDU
===============================================================================
`test_ikinci_acilis_yeniden_GOCMEZ` tam süitte **bir kez** düştü ve tekrarlanmadı (izole
10/10, tam süit 2×2969). "Kararsız test" deyip geçmek yerine göç yolundaki dosya işlemleri
okundu — ve altından kararsızlıktan çok daha ciddi bir şey çıktı.

===============================================================================
ARIZA
===============================================================================
`sqlcipher_util.migrate_to_encrypted_if_needed` şifreli kopyayı yerine koyarken **iki ayrı**
taşıma yapıyor:

    shutil.move(db, backup)     # 1) orijinali .plain.bak'a al
    shutil.move(enc_tmp, db)    # 2) şifrelisini yerine koy

⚠️ 1 başarılı olup 2 düşerse (Windows'ta geçici dosya kilidi — tarayıcı, yedekleyici,
eşzamanlı süreç; bu depoda bilinen sınıf) ortaya şu HALF-STATE çıkar:

    db           → YOK
    db.plain.bak → orijinal veri
    db.enc.tmp   → şifreli kopya

Üstelik fonksiyonun tamamı `except Exception` ile sarılı ve hatayı **yutuyor**. Sonuç:
bir sonraki açılışta `os.path.exists(db)` False → göç erken döner → uygulama **YENİ BOŞ**
bir veritabanı yaratır ve klinik **hasta geçmişini BOŞ görür**. Veri diskte durur ama
kimse bakmaz.

⚠️ SINIF: "yarım kalan yer-değiştirme + yutulan hata". Bu, kararsız bir testten çok daha
kötüdür: sessizdir ve hasta verisini erişilemez yapar.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
Kararsızlığı taklit etmez — **deterministik** olarak ikinci taşımayı düşürür ve sorar:
veri hâlâ okunabiliyor mu?
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
import sahte_sqlcipher

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _duz_db_kur(yol: Path, ad: str) -> None:
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE hasta (ad TEXT)")
    c.execute("INSERT INTO hasta VALUES (?)", (ad,))
    c.commit()
    c.close()


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """İzole veri kökü + şifreleme açık."""
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    # Süreç-geneli sır önbelleği sızmasın (conftest deseni).
    try:
        from utils import secrets_manager as sm

        if hasattr(sm, "_CACHE"):
            sm._CACHE.clear()
    except Exception:
        pass
    return d


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    """D2.08 (B-10.41): göç DAVRANIŞ kapıları İKİ bağlayıcıyla koşar.

    · `sahte` — `tests/sahte_sqlcipher.py`: yalnız bağlayıcı sahte, ürün göçü BİREBİR koşar →
      sqlcipher3 YOKKEN de (Windows CI) koşar. Eskiden bu dört test orada `pytest.skip` ile
      atlanıyordu; ölçüldü (2026-10-06): sqlcipher3 yokken geri-alma satırı `pass` yapılınca küme YEŞİLDİ.
    · `gercek` — kurulu sqlcipher3; yoksa ATLANIR (atlama nedeni "sqlcipher3" içerir → A-46 / D2.07 CI
      adımı bu atlamayı sayar ve KIRMIZI yapar).
    """
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


def test_KRITIK_ikinci_tasima_DUSERSE_veritabani_YERINDE_KALIR(ortam, monkeypatch, baglayici):
    """⚠️ ASIL KAPI.

    İkinci `shutil.move` geçici bir kilitle düşerse, göç iptal edilmeli ve ORİJİNAL
    veritabanı yerine geri konmalı. Aksi halde `db` YOK olur ve uygulama boş bir DB yaratır.

    MUTASYON: `migrate_to_encrypted_if_needed` içindeki geri-alma (restore) dalını sil
    → KIRMIZI (db dosyası kaybolur) — D2.08'den beri sqlcipher3 YOKKEN de (sahte kol).
    """
    from database import sqlcipher_util as su

    db = ortam / "test_gecmis.db"
    _duz_db_kur(db, "YarimKalanHasta")

    gercek_move = shutil.move
    durum = {"sayac": 0}

    def _sahte_move(src, dst, *a, **k):
        durum["sayac"] += 1
        # ⚠️ KALICI kilit: `.enc.tmp -> db` taşıması HER denemede düşer.
        # (Sayaçla "2. çağrıda düş" demek YETMEZ — artık yeniden-deneme var ve 3. deneme
        # başarılı olur; o senaryo ayrı bir testte ölçülüyor.)
        if str(src).endswith(".enc.tmp"):
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return gercek_move(src, dst, *a, **k)

    monkeypatch.setattr(su.shutil, "move", _sahte_move)
    su.migrate_to_encrypted_if_needed(db, ortam, logger=None)

    assert durum["sayac"] >= 2, "ikinci tasima hic denenmedi -> test amacina ulasmadi"
    assert db.exists(), (
        "GOC YARIDA KESILDI ve veritabani KAYBOLDU -> uygulama bir sonraki aciliste BOS "
        "bir DB yaratir ve klinik hasta gecmisini BOS gorur (veri .plain.bak'ta kalir ama "
        "kimse bakmaz)"
    )
    # Ve içerik gerçekten okunabilir olmalı (düz-metin olarak geri konmuş).
    c = sqlite3.connect(str(db))
    try:
        assert c.execute("SELECT ad FROM hasta").fetchone()[0] == "YarimKalanHasta"
    finally:
        c.close()


def test_KARSIT_KANIT_engel_yokken_goc_NORMAL_tamamlanir(ortam, baglayici):
    """Kural "hep iptal et"e kaymasın: engel yokken göç gerçekten olmalı."""
    from database import sqlcipher_util as su

    db = ortam / "test_normal.db"
    _duz_db_kur(db, "NormalHasta")
    su.migrate_to_encrypted_if_needed(db, ortam, logger=None)

    ham = db.read_bytes()[:16]
    assert not ham.startswith(b"SQLite format 3"), (
        "goc TAMAMLANMADI -> dosya hala duz metin (kural 'hep iptal et'e kaymis olabilir)"
    )


def test_KRITIK_onceki_yarim_gocten_KENDILIGINDEN_toparlar(ortam, baglayici):
    """Süreç tam o pencerede ölürse (elektrik/kill) diskte `db` YOK, `.plain.bak` VAR kalır.
    Sonraki açılış bunu görüp ORİJİNALİ geri koymalı — yoksa boş DB yaratılır.

    MUTASYON: baştaki yarım-göç toparlama dalını sil → KIRMIZI.
    """
    from database import sqlcipher_util as su

    db = ortam / "test_yarim.db"
    yedek = Path(str(db) + ".plain.bak")
    _duz_db_kur(yedek, "KurtarilacakHasta")  # db YOK, yalnizca .plain.bak var
    assert not db.exists()

    su.migrate_to_encrypted_if_needed(db, ortam, logger=None)

    assert db.exists(), "onceki yarim goc TOPARLANMADI -> `db` yok kaldi ve uygulama BOS bir DB yaratacak"


def test_KRITIK_GECICI_kilit_yeniden_denemeyle_ASILIR(ortam, monkeypatch, baglayici):
    """⚠️ Windows'ta dosya kilitleri çoğunlukla ANLIKTIR (tarayıcı/yedekleyici/indeksleyici).
    Tek bir başarısızlıkta göçü iptal etmek, hiç göç edememeye yol açardı.

    Bu test kilidi BİR KEZ uygular: göç yine de TAMAMLANMALI.

    MUTASYON: `_tasi_yeniden_dene` içindeki döngüyü tek denemeye indir → KIRMIZI
    (geçici kilit göçü kalıcı olarak iptal ettirir).
    """
    from database import sqlcipher_util as su

    db = ortam / "test_gecici.db"
    _duz_db_kur(db, "GeciciKilitHasta")

    gercek_move = shutil.move
    durum = {"dustu": False}

    def _sahte_move(src, dst, *a, **k):
        if str(src).endswith(".enc.tmp") and not durum["dustu"]:
            durum["dustu"] = True  # YALNIZ ilk denemede düş
            raise PermissionError(32, "gecici kilit")
        return gercek_move(src, dst, *a, **k)

    monkeypatch.setattr(su.shutil, "move", _sahte_move)
    su.migrate_to_encrypted_if_needed(db, ortam, logger=None)

    assert durum["dustu"], "kilit hic uygulanmadi -> test amacina ulasmadi"
    assert db.exists()
    ham = db.read_bytes()[:16]
    assert not ham.startswith(b"SQLite format 3"), (
        "GECICI bir kilit gocu KALICI olarak iptal ettirdi -> yeniden-deneme calismiyor"
    )


def test_KRITIK_onceki_duz_metin_yedek_GOCTE_SILINMEZ_kenara_alinir(ortam, baglayici):
    """⚠️ D2.08 (B-10.41) DAVRANIŞ — "düz-metin yedek ASLA silinmez"in koşan ikizi.

    Diskte önceki bir yarım göçün TEK kopyası (`.plain.bak`) duruyor ve canlı `db` de var (toparlama
    o açılışta düşmüş, sonra DB yeniden oluşmuş — 2026-09-13 ürün ölçümü). Yeni göç bu dosyayı SİLMEMELİ:
    `.plain.bak.<zaman>` olarak KENARA almalı. Eski statik kapı yalnız `remove` adına bakıyordu;
    kenara almadan önce `os.unlink(backup)` eklenince sqlcipher3 VARKEN bile YEŞİLDİ (ölçüldü).

    MUTASYON: `backup = db + ".plain.bak"` ardına `os.unlink(backup)` → KIRMIZI (iki bağlayıcıda).
    """
    from database import sqlcipher_util as su

    db = ortam / "test_onceki_yedek.db"
    _duz_db_kur(db, "CanliHasta")
    onceki = Path(str(db) + ".plain.bak")
    _duz_db_kur(onceki, "TekKopyaHasta")

    su.migrate_to_encrypted_if_needed(db, ortam, logger=None)

    assert not db.read_bytes()[:16].startswith(b"SQLite format 3"), "goc tamamlanmadi -> test amacina ulasmadi"
    kenarda = sorted(p for p in ortam.iterdir() if p.name.startswith(db.name + ".plain.bak."))
    adlar = []
    for p in kenarda:
        c = sqlite3.connect(str(p))
        try:
            adlar += [r[0] for r in c.execute("SELECT ad FROM hasta")]
        finally:
            c.close()
    assert "TekKopyaHasta" in adlar, (
        f"onceki yarim gocun TEK kopyasi gocte SILINDI (kenara alinmadi): kenarda={[p.name for p in kenarda]} "
        "-> klinik gecmisi geri donulmez kayip"
    )


def test_KRITIK_toparlama_HATASI_LOGLANIR_davranis(tmp_path, monkeypatch, caplog):
    """⚠️ D2.08 (B-10.41) DAVRANIŞ — `test_KRITIK_toparlama_HATASI_sessizce_YUTULMAZ`ın koşan ikizi.

    `path_utils.initialize_database` (açılışta EN ÖNCE koşar, `db` yoksa ŞABLON koyar) yarım-göç
    toparlaması düşerse bunu LOGLAMALI; sessiz düşüş klinik geçmişini boş gösterir ve iz bırakmaz.
    Eski statik kapı handler gövdesinde yalnız `pass`'i arıyordu: gövde `_ = None` yapılınca YEŞİLDİ
    (ölçüldü). sqlcipher3 GEREKTİRMEZ.

    MUTASYON: handler gövdesi `_ = None` → KIRMIZI.
    """
    import logging

    from database import sqlcipher_util as su
    from utils import path_utils

    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))

    def _patla(*a, **k):
        raise PermissionError(13, "erisim reddedildi (D2.08 sahte toparlama hatasi)")

    monkeypatch.setattr(su, "_yarim_goc_toparla", _patla)
    with caplog.at_level(logging.DEBUG):
        path_utils.initialize_database()

    kayitlar = [r for r in caplog.records if r.levelno >= logging.ERROR and "toparlama" in r.getMessage().lower()]
    assert kayitlar, (
        "yarim-goc toparlamasi DUSTU ama initialize_database HICBIR hata kaydi birakmadi -> sablon "
        "kopyalanir, klinik gecmisi BOS gorunur ve teshis edilemez"
    )
    assert any(r.exc_info for r in kayitlar), "toparlama hatasi loglandi ama SEBEBI (istisna izi) yok"


# ============================================================================
# ⚠️ İKİ KOPYA AYRIŞMASIN — bu arızanın ASIL kökü buydu
# ============================================================================
# `sqlcipher_util.migrate_to_encrypted_if_needed` (hasta DB'si) ve
# `treatment_history_db._migrate_to_encrypted_if_needed` (seans/AI geçmişi) AYNI işi yapan
# İKİ AYRI kopyaydı (bu kapı yazıldığında `sqlcipher_util` modül başlığı da öyle diyordu).
# 2026-09-15'ten (A1 · 2/2) beri tedavi yolu `thdb_sema` üzerinden ORTAK gövdeye delege ediyor;
# kopya kalktı, başlık D6.10'da düzeltildi. Aşağıdaki çıpa tedavi yolunun yine toparlamayı
# ALDIĞINI ölçer (doğrudan ya da delegeyle).
#
# ⚠️ İLK DÜZELTMEMDE YALNIZ BİRİNİ onardım. Birim testler geçti (onlar paylaşılan kopyayı
# çağırıyor) ama ÜRÜNDE hasta geçmişi hâlâ kayboluyordu, çünkü o yol İKİNCİ kopyayı kullanıyor.
# Bu depoda kayıtlı ders: **"kısmi düzeltme = düzeltme değil"** ve **"aynı kural N yerde"**.
#
# Bu kapı, üç korumanın da HER İKİ yolda bulunduğunu ölçer.


def _cagri_adlari(dugum) -> set:
    """Düğümün altındaki GERÇEK çağrıların adları (AST: yorum, dize ve import satırı SAYILMAZ).

    ⚠️ D2.02 (B-3.78, 2026-10-06): bu kapı eskiden `c_soy` (C yorum sökücüsü) uygulanmış kaynakta
    ALT-DİZE arıyordu. C sökücüsü Python `#` yorumlarını sökmez: tedavi kurucusundaki göç çağrısı
    YORUMA alınınca kapı YEŞİL kalıyordu (ölçüldü). AST yorumu hiç görmez."""
    import ast

    return {getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(dugum) if isinstance(c, ast.Call)}


def _tedavi_delegesini_bul():
    """Tedavi DB'sinin `_migrate_to_encrypted_if_needed` metodunu TAŞIYAN dosyada metodun AST düğümü.

    Dosya adı SABİT YAZILMAZ (B4 bölmesi metodu `thdb_sema.py`ye taşıdı; sonraki bölme kapıyı kör
    bırakmasın) — `apps/backend/database/` altında tanım aranır."""
    import ast

    for yol in sorted((KOK / "apps" / "backend" / "database").glob("*.py")):
        agac = ast.parse(yol.read_text(encoding="utf-8"))
        for n in ast.walk(agac):
            if isinstance(n, ast.FunctionDef) and n.name == "_migrate_to_encrypted_if_needed":
                return yol, n
    raise AssertionError("`_migrate_to_encrypted_if_needed` hicbir DB modulunde yok -> kapi KOR kaldi")


def test_KRITIK_HER_IKI_goc_yolu_da_KORUNUYOR():
    """⚠️ ASIL KAPI — kısmi düzeltmeyi yakalar.

    MUTASYONLAR (hepsi KIRMIZI, D2.02 2026-10-06'da ölçüldü):
      · thdb_sema.py'deki delege çağrısı (`migrate_to_encrypted_if_needed(self.db_path, …)`) → `pass`
      · tedavi kurucusundaki `self._migrate_to_encrypted_if_needed()` YORUMA alınır
      · delege YANLIŞ DB yoluyla çağrılır (`self.app_data_dir / "patients.db"`)
    Eski biçim (alt-dize) üçünde de YEŞİLDİ. Davranış ikizi (sqlcipher3 GEREKTİRMEZ):
    `test_KRITIK_tedavi_DB_kurucusu_yarim_gocu_KENDI_yolunda_TOPARLAR`.
    """
    # ⚠️ ÇIPALAR ÇAĞRIYA PİNLİ, ADA DEĞİL. İlk yazımda düz `"_yarim_goc_toparla" in src`
    # kullandım ve mutasyon YEŞİL kaldı: çağrıyı silsen bile `from ... import _yarim_goc_toparla`
    # satırı adı taşıyor. Bu depoda tekrar eden ders — çıpayı GERÇEK çağrıya pinle.
    # ⚠️ ÜÇ YOL VAR, ÜÇÜ DE TOPARLAMAYI ÇAĞIRMALI:
    #   · sqlcipher_util            → hasta DB'si
    #   · treatment_history_db      → seans / AI geçmişi (bugün `thdb_sema` → ortak göçe delege)
    #   · path_utils.initialize_database → "0 KM" ŞABLON KOPYALAYICI
    # Üçüncüsü açılışta EN ÖNCE koşar ve `db` yok görünce ŞABLONU koyar. Ölçüldü (2026-09-13):
    # ilk iki düzeltme ürünü KURTARMADI çünkü şablon kopyalayıcı önce davranıyordu — hasta
    # geçmişi yine boş görünüyordu. Kısmi düzeltme = düzeltme değil.
    # ⚠️ ÇIPA GENİŞLETİLDİ (2026-09-15, A1·2/2): `treatment_history_db` artık göç gövdesinin
    # KENDİ kopyasını taşımıyor — `sqlcipher_util.migrate_to_encrypted_if_needed`e DELEGE
    # ediyor (157 satırlık kopya, %91 aynıydı; kalan farkların tamamı mekanikti). Korunan şey
    # değişmedi: o yol da toparlamayı ALMALI. Kabul edilen iki biçim:
    #   · toparlamayı DOĞRUDAN çağırmak, ya da
    #   · toparlamayı çağıran ORTAK göçe delege etmek.
    # İkinci biçimin gerçekten koruduğu, hemen aşağıda ayrıca ölçülüyor — yoksa "delege
    # ediyorum" demek kapıyı bedavaya geçirirdi.
    # ⚠️ D2.02 (B-3.78): ÇAĞRILAR AST'DEN okunur (alt-dize DEĞİL). Eski biçimde tedavi yolu için
    # `"migrate_to_encrypted_if_needed(" in src` aranıyordu ve bunu kurucudaki
    # `self._migrate_to_encrypted_if_needed()` (metot ADI aranan dizeyi içerir) karşılıyordu;
    # asıl delege (thdb_sema.py) HİÇ okunmuyordu.
    import ast

    for yol in ("apps/backend/database/sqlcipher_util.py", "apps/backend/utils/path_utils.py"):
        cagrilar = _cagri_adlari(ast.parse((KOK / yol).read_text(encoding="utf-8")))
        assert "_yarim_goc_toparla" in cagrilar or "migrate_to_encrypted_if_needed" in cagrilar, (
            f"{yol}: yarim-goc TOPARLAMA ne CAGRILIYOR ne de toparlamayi cagiran ortak goce "
            "DELEGE ediliyor -> o yolda `db` yok kalir ve BOS DB/SABLON yaratilir"
        )

    # TEDAVİ YOLU — iki halka, ikisi de GERÇEK çağrıya pinli:
    #   (1) kurucu göç metodunu ÇAĞIRIR (treatment_history_db.TreatmentHistoryDB.__init__),
    #   (2) metot ortak göçe KENDİ DB yolunu (`self.db_path`) verir (thdb_sema.py).
    thdb_agac = ast.parse((KOK / "apps/backend/database/treatment_history_db.py").read_text(encoding="utf-8"))
    kurucu = next(
        (
            f
            for c in ast.walk(thdb_agac)
            if isinstance(c, ast.ClassDef) and c.name == "TreatmentHistoryDB"
            for f in c.body
            if isinstance(f, ast.FunctionDef) and f.name == "__init__"
        ),
        None,
    )
    assert kurucu is not None, "TreatmentHistoryDB.__init__ bulunamadi -> kapi KOR kaldi"
    assert "_migrate_to_encrypted_if_needed" in _cagri_adlari(kurucu), (
        "TreatmentHistoryDB kurucusu goc metodunu CAGIRMIYOR -> tedavi DB'si yarim gocu hic toparlamaz; "
        "yarim kalmis bir gocte BOS DB yaratilir (yorumdaki cagri sayilmaz)"
    )
    delege_dosyasi, delege = _tedavi_delegesini_bul()
    ortak_cagrilar = [
        c
        for c in ast.walk(delege)
        if isinstance(c, ast.Call)
        and getattr(c.func, "id", getattr(c.func, "attr", None)) == "migrate_to_encrypted_if_needed"
    ]
    assert ortak_cagrilar, (
        f"{delege_dosyasi.name}: tedavi yolu ortak goce DELEGE etmiyor -> yarim-goc toparlamasi yok, "
        "kopya geri gelmis olabilir"
    )
    assert any(c.args and ast.unparse(c.args[0]) == "self.db_path" for c in ortak_cagrilar), (
        f"{delege_dosyasi.name}: ortak goc tedavi DB'sinin KENDI yoluyla (self.db_path) cagrilmiyor: "
        f"{[ast.unparse(c) for c in ortak_cagrilar]} -> toparlama baska bir dosyada kosar, tedavi DB'si korumasiz"
    )

    # Delegasyonun DEĞERİ, delege edilen şeyin gerçekten toparlamasıdır.
    # ⚠️ 2-B (Y95): HAM kaynak (C yorum sökücüsü DEĞİL). `c_soy` Python'da `'`/`"` paritesiyle dize durumunu çeviriyor;
    # docstring'deki bir kesme işareti (ör. "SSD/eMMC'de") paritesini değiştirince `migration_backups/*.db` bir C blok
    # yorumu başlatıp dosyanın kalanını boşalttı → AST "kapanmamış dize" ile düştü (ölçüldü). AST yorumu zaten görmez.
    agac = ast.parse((KOK / "apps/backend/database/sqlcipher_util.py").read_text(encoding="utf-8"))
    ortak = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "migrate_to_encrypted_if_needed"),
        None,
    )
    assert ortak is not None, "ortak goc fonksiyonu bulunamadi -> kapi KOR kaldi"
    ic_cagrilar = {
        getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(ortak) if isinstance(c, ast.Call)
    }
    assert "_yarim_goc_toparla" in ic_cagrilar, (
        "ORTAK goc toparlamayi CAGIRMIYOR -> ona delege eden TUM yollar korumasiz kalir "
        "(tek uygulamanin riski budur: bir satir, her yolu birden dusurur)"
    )
    assert "_tasi_yeniden_dene" in ic_cagrilar, (
        "ORTAK gocte yeniden-denemeli tasima CAGRILMIYOR -> gecici Windows kilidi gocu kalici "
        "olarak iptal ettirir ya da yarim birakir"
    )

    # Geri alma dalı: ikinci taşıma düşerse orijinal geri konmalı.
    # ⚠️ ÇIPA TAŞINDI (2026-09-15, A1·2/2): eskiden İKİ dosyada da aranıyordu; tedavi yolu
    # artık göç gövdesini taşımıyor, ortak uygulamaya delege ediyor. Geri-alma dalı TEK
    # uygulamada ölçülür — delegasyonun kendisi yukarıda AST ile (iki halka + `self.db_path`)
    # ve `test_KRITIK_tedavi_DB_kurucusu_yarim_gocu_KENDI_yolunda_TOPARLAR` ile davranışla kilitli.
    # (D2.02: bu satır eskiden "yukarıda kilitli" diyordu ama yukarıdaki alt-dize kördü.)
    # ⚠️ D2.08 (B-10.41): burada `"GOC GERI ALINAMADI" in ortak_src or …` vardı — LOG DİZESİ yerinde
    # kaldıkça geri-alma ÇAĞRISI `pass` yapılsa da YEŞİLDİ (ölçüldü; sqlcipher3 yokken davranış
    # ikizi de atlanıyordu). Artık gerçek çağrı düğümü aranır: `_tasi_yeniden_dene(backup, db, …)`.
    # Davranış ikizi (iki bağlayıcı, sqlcipher3'süz de): test_KRITIK_ikinci_tasima_DUSERSE_veritabani_YERINDE_KALIR.
    geri_alma = [
        c
        for c in ast.walk(ortak)
        if isinstance(c, ast.Call)
        and getattr(c.func, "id", getattr(c.func, "attr", None)) == "_tasi_yeniden_dene"
        and [ast.unparse(a) for a in c.args[:2]] == ["backup", "db"]
    ]
    assert geri_alma, (
        "ORTAK gocte ikinci tasima duserse GERI ALMA cagrisi (`_tasi_yeniden_dene(backup, db, ...)`) yok "
        "-> veritabani YOK kalir (ve artik TEK uygulama oldugu icin bu, iki veritabanini birden vurur)"
    )


def test_KRITIK_tedavi_DB_kurucusu_yarim_gocu_KENDI_yolunda_TOPARLAR(tmp_path, monkeypatch):
    """⚠️ D2.02 (B-3.78) — DAVRANIŞ KAPISI; sqlcipher3 GEREKTİRMEZ (Windows CI'da da koşar).

    Tedavi DB'sinin yarım-göç koruması iki halkalı bir zincirden geçer:
      `TreatmentHistoryDB.__init__` → `self._migrate_to_encrypted_if_needed()` (treatment_history_db.py)
      → `migrate_to_encrypted_if_needed(self.db_path, …)` (thdb_sema.py) → `_yarim_goc_toparla`.
    Eski iki "delege" kapısı alt-dize arıyordu ve şu üç mutantta YEŞİL kaldı (ölçüldü 2026-10-06):
      · thdb_sema.py'deki çağrı `pass` → `def _migrate_to_encrypted_if_needed(` satırı dizeyi taşıyor;
      · kurucudaki çağrı YORUMA alınır → C yorum sökücüsü Python `#` yorumunu sökmüyor;
      · delege hasta DB'sinin yoluyla çağrılır → ad var, değer yanlış.
    Bu kapı zinciri GERÇEKTEN koşturur: diskte yarım kalmış bir göç (db YOK, `.plain.bak` VAR) varken
    gerçek `TreatmentHistoryDB` kurulur → seans geri gelmeli, ortak göç TEDAVİ yoluyla çağrılmış olmalı.

    sqlcipher3'süz nasıl: ortak göç anahtarı okur ve toparlamayı binding sınamasından ÖNCE yapar
    (`_yarim_goc_toparla(db)` → `if sqlcipher is None or not os.path.exists(db): return`). Anahtar
    sahte bir dizeyle verilir, binding None'a çekilir → şifreleme hiç denenmez, yalnız toparlama
    koşar; tedavi DB'si düz-metin açılır (bayrak kapalı).
    """
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.delenv("PEMF_SQLCIPHER_KEY", raising=False)

    # 1) Düz-metin dönemde GERÇEK tedavi şemasıyla bir seans yaz (anahtar yok → düz-metin).
    hazirlik = tmp_path / "hazirlik" / "PEMF_GUI"
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    eski = thdb.TreatmentHistoryDB(hazirlik)
    sid = eski.start_session("YarimGocSeansi")
    eski.end_session(sid)
    eski.close_connections()
    del eski

    # 2) Yarım kalmış göç: canlı db YOK, veri `.plain.bak`ta.
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir(parents=True, exist_ok=True)
    db = kok / "pemf_treatment_history.db"
    yedek = Path(str(db) + ".plain.bak")
    shutil.move(str(hazirlik / "pemf_treatment_history.db"), str(yedek))
    assert yedek.exists() and not db.exists()

    # 3) Anahtar VAR (sahte), binding YOK → ortak göç yalnız toparlar. Ortak göç casuslanır (gerçeğine geçer).
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "SAHTE-ANAHTAR-D202")
    monkeypatch.setattr(su, "import_sqlcipher", lambda: None)
    gercek_goc = su.migrate_to_encrypted_if_needed
    cagrilan_yollar = []

    def _casus(db_path, *a, **k):
        cagrilan_yollar.append(Path(str(db_path)))
        return gercek_goc(db_path, *a, **k)

    monkeypatch.setattr(su, "migrate_to_encrypted_if_needed", _casus)

    yeni = thdb.TreatmentHistoryDB(kok)
    try:
        assert cagrilan_yollar, (
            "tedavi DB kurucusu ortak goce HIC ulasmadi -> yarim goc toparlanmaz; bir sonraki acilista "
            "BOS bir tedavi DB'si yaratilir ve klinik gecmisi BOS gorur"
        )
        assert yeni.db_path in cagrilan_yollar, (
            f"ortak goc tedavi DB'sinin KENDI yoluyla cagrilmadi: {cagrilan_yollar} (beklenen {yeni.db_path}) "
            "-> toparlama baska bir dosyada kosuyor"
        )
        assert db.exists() and not yedek.exists(), (
            "yarim kalmis goc TOPARLANMADI: tedavi DB'si yerine konmadi (veri .plain.bak'ta kaldi)"
        )
        modlar = [s.get("treatment_mode") for s in yeni.get_session_history(limit=10)]
        assert modlar == ["YarimGocSeansi"], f"yarim gocten once yazilan seans geri GELMEDI: {modlar}"
    finally:
        yeni.close_connections()


#: `sqlcipher_util`de TEK yerde tanımlı göç/karantina korumaları — tedavi DB modülleri bunları YENİDEN YAZMAZ.
_PAYLASILAN_KORUMALAR = frozenset(
    {
        "anahtar_uyusmazligi_mi",
        "karantinaya_al",
        "duz_metin_sqlite_mi",
        "migrate_to_encrypted_if_needed",
        "_yarim_goc_toparla",
        "_tasi_yeniden_dene",
        "_yedegi_kenara_al",
        "_kilit_direncli_tasi",
        "_kilit_direncli_sil",
        "goc_sonrasi_yedek_politikasi",
        "duz_metin_yedegi_emanete_al_mi",
        "get_sqlcipher_key",
        "import_sqlcipher",
    }
)


def test_ikinci_kopya_PAYLASILAN_yardimcilari_kullaniyor():
    """Kopyalar kendi ayrı implementasyonlarını yazarsa yine ayrışırlar.

    ⚠️ Bu yüzden `treatment_history_db` korumaları KENDİ yazmaz, `sqlcipher_util`den
    IMPORT eder. Böylece davranış tek yerde tanımlı kalır.

    ⚠️ D2.09 (B-10.239, 2026-10-06): eski çıpa `"from database.sqlcipher_util import" in src` idi ve
    dosyadaki İLGİSİZ yerel importlar (metot içi `import_sqlcipher` / `get_sqlcipher_key`) onu her zaman
    karşılıyordu → tedavi modülüne YEREL bir `karantinaya_al` (düz-metin koruması yok) ya da
    `anahtar_uyusmazligi_mi` (her hata uyuşmazlık) kopyası konunca YEŞİL kaldı (ölçüldü). Artık:
    (1) tedavi modülünün kullandığı iki koruma `sqlcipher_util`de TANIMLI nesne (`__module__`; yeniden
    yüklemeye dayanıklı), (2) tedavi DB modüllerinin (treatment_history_db.py + thdb_*.py) HİÇBİRİ ortak
    korumalardan birini yerel TANIMLAMAZ (AST).
    """
    import ast

    from database import treatment_history_db as thdb

    for ad in ("anahtar_uyusmazligi_mi", "karantinaya_al"):
        fn = getattr(thdb, ad, None)
        assert getattr(fn, "__module__", None) == "database.sqlcipher_util", (
            f"treatment_history_db.{ad} ortak `sqlcipher_util`den GELMIYOR ({getattr(fn, '__module__', None)}) "
            "-> tedavi DB'si kendi kopyasini kullaniyor, iki kopya ayrisir (duz-metin korumasi kaybolabilir)"
        )
    db_dizin = KOK / "apps" / "backend" / "database"
    yerel = []
    for yol in [db_dizin / "treatment_history_db.py", *sorted(db_dizin.glob("thdb_*.py"))]:
        for n in ast.walk(ast.parse(yol.read_text(encoding="utf-8"))):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _PAYLASILAN_KORUMALAR:
                yerel.append(f"{yol.name}:{n.lineno} {n.name}")
    assert not yerel, f"tedavi DB modullerinde ORTAK korumanin YEREL kopyasi var: {yerel} -> iki kopya ayrisir"


def test_KRITIK_toparlama_HATASI_sessizce_YUTULMAZ():
    """⚠️ Bugünün en pahalı dersi: `except Exception: pass` teşhisi İMKÂNSIZLAŞTIRDI.

    `initialize_database` içindeki toparlama çağrısı çapraz-paket bir import yapıyor. İlk
    yazımda etrafında `except Exception: pass` vardı. Ürün testi "kayıt KAYBOLDU" derken
    logda TEK BİR İZ yoktu; saatlerce yanlış hipotez (frozen EXE'de import düşüyor) kovaladım
    — kök neden bambaşkaydı (bayat EXE). Toparlama düşerse KLİNİK GEÇMİŞİ BOŞ görünür;
    bu, sessiz yutulacak en son şeydir.

    MUTASYON: `except Exception:` gövdesini `pass` yap → KIRMIZI.
    """
    import ast

    agac = ast.parse((KOK / "apps/backend/utils/path_utils.py").read_text(encoding="utf-8"))
    fn = next(d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef) and d.name == "initialize_database")

    def _cagiriyor(dugum):
        return any(
            isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "_yarim_goc_toparla"
            for n in ast.walk(dugum)
        )

    denemeler = [t for t in ast.walk(fn) if isinstance(t, ast.Try) and _cagiriyor(t)]
    assert denemeler, (
        "initialize_database icinde yarim-goc toparlamasi try/except ile sarilmis DEGIL "
        "-> ya cagri yok ya da hata backend'i baslatmiyor"
    )

    # ⚠️ D2.08 (B-10.41): eski ölçüt yalnız `pass`/çağrısız ifadeyi "sessiz" sayıyordu; gövde `_ = None`
    # (bir atama) yapılınca YEŞİLDİ (ölçüldü). Artık handler'da GERÇEK bir günlük çağrısı aranır.
    # Davranış ikizi: test_KRITIK_toparlama_HATASI_LOGLANIR_davranis.
    _LOG_ADLARI = {"exception", "error", "critical", "warning"}
    for t in denemeler:
        for h in t.handlers:
            loglar = [
                n
                for n in ast.walk(ast.Module(body=h.body, type_ignores=[]))
                if isinstance(n, ast.Call) and getattr(n.func, "attr", None) in _LOG_ADLARI
            ]
            assert loglar, (
                "Toparlama hatasi SESSIZCE yutuluyor (handler'da gunluk cagrisi yok) -> urunde klinik gecmisi "
                "bos gorunur ve logda HIC iz kalmaz. En az bir log cagrisi SART."
            )


def test_KRITIK_duz_metin_yedek_ASLA_SILINMEZ():
    """⚠️ Bu satır hasta geçmişini GERİ DÖNÜLMEZ siliyordu (ürün ölçümü 2026-09-13).

    Göç, yer-değiştirme penceresine girmeden önce `os.remove(backup)` yapıyordu. Normalde
    `.plain.bak` göçün kendi biraz önce yazdığı dosyadır. Ama YARIM GÖÇ kalmışsa o dosya
    kliniğin TEK kopyasıdır — ve toparlama ACL kilidi yüzünden düşmüşse hâlâ oradadır.
    Sıra şuydu: toparlama düş → yedeği SİL → şablonu koy → "güvenli silindi" diye logla.

    MUTASYON: iki göç kopyasından birinde `_yedegi_kenara_al(` yerine `os.remove(backup)`
    yaz → KIRMIZI.
    """
    # ⚠️ ÇIPA **AST**'YE PİNLİ — ve iki kez düzeltildi:
    #  1) Düz `"os.remove(backup)" not in src` fazla genişti: göç BAŞARIYLA bitince yedeği
    #     üzerine rastgele yazıp silen MEŞRU bir adım daha var (op-doğrulama #8, at-rest PII).
    #     Ayrım zamanlamadır — silme, yedeği BU KOŞU yarattıktan SONRA olmalı.
    #  2) Konum çıpası metin üzerindeydi ve `c_soy` bu satır-içi `#` yorumlarını SOYMADI:
    #     kapı, düzeltmeyi ANLATAN kendi yorumumu ihlal sandı. Metin araması bu dosyada
    #     güvenilir değil; AST yorumları hiç görmez.
    #  3) ÇIPA **FONKSİYON KAPSAMINA** ALINDI (2026-09-15). Önce modülün TAMAMI taranıyordu.
    #     Göç-sonrası yedek politikası (escrow / güvenli-sil) ortak bir fonksiyona —
    #     `goc_sonrasi_yedek_politikasi` — indirilince o fonksiyondaki MEŞRU `os.remove(backup)`
    #     dosyada `_yedegi_kenara_al`dan ÖNCE yer aldı ve kapı, kod DOĞRUYKEN kırmızıya döndü.
    #     Satır numarası bir SIRA vekilidir; gerçek sözleşme "göç akışında kenara-alma önce gelir"
    #     olduğu için ölçüm göç fonksiyonlarının KENDİ gövdelerine pinlendi. Politikadaki silme
    #     zaten tanım gereği göç BİTTİKTEN sonra çalışır ve kendi kapısı vardır
    #     (tests/test_escrow_acl_dusunce_fail_closed.py).
    import ast

    #  4) A1·2/2 (2026-09-15): tedavi yolu artık göç gövdesini TAŞIMIYOR, ortak göçe DELEGE
    #     ediyor. Sıra sözleşmesi tek uygulamada ölçülür; delegasyonun kendisi
    #     `test_KRITIK_tedavi_yolu_ORTAK_goce_DELEGE_eder` ile ayrıca kilitli.
    hedefler = (("apps/backend/database/sqlcipher_util.py", "migrate_to_encrypted_if_needed"),)
    for yol, fon_adi in hedefler:
        agac = ast.parse((KOK / yol).read_text(encoding="utf-8"))
        fon = next(
            (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == fon_adi),
            None,
        )
        assert fon is not None, f"{yol}: `{fon_adi}` bulunamadi -> kapi KOR kaldi"
        kenara, siler, politika = [], [], []
        for n in ast.walk(fon):
            if not isinstance(n, ast.Call):
                continue
            ad = getattr(n.func, "id", getattr(n.func, "attr", None))
            if ad == "_yedegi_kenara_al":
                kenara.append(n.lineno)
            elif ad == "goc_sonrasi_yedek_politikasi":
                politika.append(n.lineno)
            # ⚠️ D2.08 (B-10.41): yalnız `remove` adı aranıyordu; `os.unlink(backup)` YEŞİLDİ (ölçüldü).
            # Davranış ikizi: test_KRITIK_onceki_duz_metin_yedek_GOCTE_SILINMEZ_kenara_alinir.
            elif ad in ("remove", "unlink", "rmtree", "_kilit_direncli_sil") and any(
                getattr(a, "id", None) == "backup" for a in n.args
            ):
                siler.append(n.lineno)
        assert kenara, f"{yol}:{fon_adi}: yedek KENARA ALINMIYOR -> silme yoluna geri donulmus olabilir"
        erken = [s for s in siler if s < min(kenara)]
        assert not erken, (
            f"{yol}:{erken}: duz-metin yedek, KENARA ALINMADAN ONCE siliniyor -> yarim goc "
            "halinde klinik gecmisi YOK EDILIR (bu satir hasta verisini gercekten sildi)"
        )
        # Göç-sonrası işlem (silme ya da ortak politika) kenara-almadan SONRA gelmeli.
        erken_politika = [s for s in politika if s < min(kenara)]
        assert not erken_politika, (
            f"{yol}:{erken_politika}: goc-sonrasi yedek politikasi, yedek KENARA ALINMADAN "
            "ONCE cagriliyor -> yarim goc halinde tek kopya guvenli-silinebilir"
        )


def test_KRITIK_toparlama_ACL_kilidinden_ONCE_kosar():
    """⚠️ Açılış SIRASI bir güvenlik adımını veri-kaybına çeviriyordu.

    `_harden_secret_file_acls` `*.plain.bak`ı SYSTEM+Administrators'a kilitliyor. Yükseltilmemiş
    backend'de Administrators SID'i süzülür → süreç KENDİ yedeğini açamaz → toparlama
    `[Errno 13] Permission denied` ile düşer → şablon konur → klinik geçmişi BOŞ görünür.
    Ürün (frozen EXE) logunda BİREBİR bu ölçüldü.

    MUTASYON: iki çağrının yerini değiştir → KIRMIZI.
    """
    import ast

    agac = ast.parse((KOK / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8"))

    def _sira(govde, ad):
        for i, d in enumerate(govde):
            for n in ast.walk(d):
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == ad:
                    return i
        return None

    bulundu = False
    for fn in ast.walk(agac):
        if not isinstance(fn, ast.FunctionDef):
            continue
        i_init = _sira(fn.body, "_initialize_database_safe")
        i_acl = _sira(fn.body, "_harden_secret_file_acls")
        if i_init is None or i_acl is None:
            continue
        bulundu = True
        assert i_init < i_acl, (
            f"{fn.name}: ACL kilidi toparlamadan ONCE kosuyor -> backend KENDI yedegini acamaz "
            "ve klinik gecmisi BOS gorunur"
        )
    assert bulundu, "backend_service icinde iki cagriyi birlikte iceren fonksiyon YOK"


def test_KRITIK_plain_bak_kilidi_kullaniciyi_DISARI_ATMAZ(tmp_path, monkeypatch):
    """`.plain.bak` kilidi `keep_current_user=True` olmalı.

    Aksi hâlde sıra düzeltmesi bile yetmez: bir kez kilitlenen yedek, sonraki açılışlarda
    kalıcı olarak erişilemez kalır. Users / Authenticated Users her iki kipte de dışarıda —
    korunan şey kaybolmuyor.

    MUTASYON: `.plain.bak` için `lock_down_file(c)` (varsayılan False) → KIRMIZI.

    ⚠️ O-B.1 (2-C) kaynağı AST ile okuyup `keep_current_user=<x> in plain_yedekler` İFADESİNİ arıyordu. D2.79 (B-3.13 ikinci
    yarı) sır dosyalarını da `keep_current_user=True` ile kilitler — ifade değişti, korunan şey AYNI. Kapı artık DAVRANIŞI ölçer:
    GERÇEK `_harden_secret_file_acls`, casus `lock_down_file` (argümanlar gerçek imzaya bağlanır), `.plain.bak` ve kenara alınmış
    `.plain.bak.<zaman>` kopyası için sürecin hesabı KORUNMALI.
    """
    import inspect
    import logging

    import backend_service as bs
    import utils.file_acl as fa

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    for ad in ("patients.db.plain.bak", "pemf_treatment_history.db.plain.bak.20260101_000000"):
        (app / ad).write_text("x", encoding="utf-8")
    imza = inspect.signature(fa.lock_down_file)
    cagrilar = []

    def _casus(*a, **k):
        b = imza.bind(*a, **k)
        b.apply_defaults()
        cagrilar.append((Path(b.arguments["path"]).name, b.arguments["keep_current_user"]))
        return True

    monkeypatch.setattr(fa, "lock_down_file", _casus)
    bs._harden_secret_file_acls(app, logging.getLogger("plain_bak"))
    yedek = {ad: tut for ad, tut in cagrilar if ".plain.bak" in ad}
    assert set(yedek) == {"patients.db.plain.bak", "pemf_treatment_history.db.plain.bak.20260101_000000"}, (
        f"`.plain.bak*` dosyalari kilitlenmedi: {sorted(yedek)}"
    )
    assert all(tut is True for tut in yedek.values()), (
        "`.plain.bak` dosyalari kullaniciyi DISARI ATAN varsayilan ACL ile kilitleniyor -> "
        f"yarim-goc toparlamasi kalici olarak imkansizlasir: {yedek}"
    )
