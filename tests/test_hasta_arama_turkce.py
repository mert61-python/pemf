# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""TÜRKÇE HASTA ARAMA — saha bulgusu 2026-08-30 (Supabase/denetim turu, "olası bugları kapat").

KANITLANAN ARIZA: hasta arama indeksi `str.lower()` ile normalize ediliyordu. Python varsayılanı
Türkçe'de yanlıştır:
    'İ'.lower() → 'i̇'  (i + U+0307 BİRLEŞİK NOKTA, İKİ karakter)
    'I'.lower() → 'i'   (oysa Türkçe'de 'ı' beklenir)

Sonuç ölçüldü (uçtan uca, aşağıda): "İhsan" kaydedip "ihsan" ya da "isik" arayan Türk doktor
hastayı BULAMIYORDU. Tıbbi kayıtta bu = erişilemeyen hasta ya da mükerrer kayıt.

DÜZELTME: `_normalize_search_value` Türkçe harfleri ASCII'ye KATLIYOR (İ/I/ı/i→i, ş→s, ğ→g,
ç→c, ö→o, ü→u) + NFKD ile kalan aksanları atıyor. Görüntülenen ad DEĞİŞMEZ; yalnız arama token'ı
katlanır. `_SEARCH_NORM_VERSION` parmak-izine dahil → sahadaki indeks açılışta otomatik yeniden
kurulur.

⚠️ Bu test GERÇEK `PatientDatabase` ile uçtan uca çalışır (kaydet → ara → bul). İzole tmp DB
kullanır; gerçek klinik verisine DOKUNMAZ.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def hasta_db(temp_app_data, monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def _adlar(sonuc):
    return {p.get("name") for p in (sonuc or [])}


# ── Uçtan uca: kaydet → ara → bul ───────────────────────────────────────────


@pytest.mark.parametrize(
    "kayit_adi,aramalar",
    [
        # İ/I bug'ı: 'İ'.lower() birleşik nokta, 'I'.lower() 'i' — bunlar DÜZELMELİ.
        ("İhsan", ["ihsan", "İhsan", "İHSAN"]),  # noktalı İ ↔ küçük i (eskiden bulunamıyordu)
        ("İpek", ["ipek", "İpek", "İPEK"]),
        ("Işık", ["ışık", "IŞIK", "Işık"]),  # noktasız I → ı (Türkçe-doğru, kendisiyle eşleşir)
        ("Gökçe", ["gökçe", "GÖKÇE", "Gökçe"]),  # aksan KORUNUR ama kendisini bulur
        ("Çağla Öz", ["çağla", "ÇAĞLA öz", "çağla öz"]),
    ],
)
def test_KRITIK_turkce_ad_kaydet_ARA_BUL(hasta_db, kayit_adi, aramalar):
    """⚠️ Her Türkçe-doğru arama biçimi kaydı BULMALI — eskiden `str.lower()` İ/I'yı bozuyordu.

    ⚠️ AKSAN ASCII'ye KATLANMAZ (mobil ile hizalı): "Gökçe" araması "gökçe" ile bulunur ama
    "gokce" ile DEĞİL (bkz. karşıt-kanıt). ı/i de ayrı harflerdir."""
    hasta_db.add_patient({"name": kayit_adi, "owner": "Test", "species": "Kedi"})
    for terim in aramalar:
        bulunan = _adlar(hasta_db.search_patients(terim))
        assert kayit_adi in bulunan, (
            f"'{kayit_adi}' kaydı '{terim}' aramasıyla BULUNAMADI "
            f"→ Türk doktor hastasına ulaşamaz (bulunanlar: {bulunan or 'HİÇBİRİ'})"
        )


# ── Karşıt-kanıt: katlama AŞIRI GENİŞ olmamalı ──────────────────────────────


def test_KARSIT_farkli_hastalar_KARISMAZ(hasta_db):
    """Farklı adlar birbirini çekmemeli."""
    for ad in ("Ahmet", "Mehmet", "Zeynep", "Zehra"):
        hasta_db.add_patient({"name": ad, "owner": "T", "species": "Kedi"})

    ahmet = _adlar(hasta_db.search_patients("ahmet"))
    assert "Ahmet" in ahmet, "kendi kaydını bulamadı"
    assert "Mehmet" not in ahmet, "'ahmet' araması 'Mehmet'i getirdi"

    zeynep = _adlar(hasta_db.search_patients("zeynep"))
    assert "Zeynep" in zeynep and "Zehra" not in zeynep, "Zeynep/Zehra karıştı"


def test_KRITIK_AKSAN_KORUNUR_mobil_ile_hizali(hasta_db):
    """⚠️ HASTA-KİMLİĞİ GÜVENLİĞİ — mobil `aramaNormalize.ts` ile birebir aynı karar.

    Aksanı ASCII'ye katlamak "Şirin" ile "Sirin"i, "Gökçe" ile "Gokce"yi birleştirir; bir
    hasta-kimliği ekranında bu YANLIŞ KAYDA bakma riskidir. İlk düzeltme (2026-08-30) aksanı
    katlıyordu; mobil ekibin daha önce ölçtüğü kararla hizalanarak geri alındı. ı/i de AYRI."""
    for ad in ("Şirin", "Sirin", "Gökçe", "Gokce", "Işık", "Isik"):
        hasta_db.add_patient({"name": ad, "owner": "T", "species": "Kedi"})

    sirin = _adlar(hasta_db.search_patients("sirin"))
    assert "Sirin" in sirin, "ASCII 'Sirin' kendini bulmalı"
    assert "Şirin" not in sirin, "'sirin' araması 'Şirin'i getirdi → yanlış-hasta riski (aksan katlandı)"

    gokce = _adlar(hasta_db.search_patients("gokce"))
    assert "Gökçe" not in gokce, "'gokce' araması 'Gökçe'yi getirdi → aksan katlanmamalı"

    # ı/i ayrı harf: "isik" araması "Işık"ı (→ ışık) getirmemeli
    isik = _adlar(hasta_db.search_patients("isik"))
    assert "Işık" not in isik, "'isik' araması 'Işık'ı getirdi → ı/i birleşti (Türkçe'de ayrı)"


# ── Normalize sözleşmesi (birim) ────────────────────────────────────────────


def test_KRITIK_normalize_birlesik_nokta_URETMEZ(hasta_db):
    """⚠️ Bug'ın kökü: `str.lower()` 'İ' için birleşik nokta (U+0307) üretiyordu.

    Normalize çıktısı ASCII-güvenli olmalı; birleşik işaret İÇERMEMELİ."""
    import unicodedata

    for giris in ("İhsan", "IŞIK", "Çağla", "Ğöl"):
        cikti = hasta_db._normalize_search_value(giris)
        assert not any(unicodedata.combining(c) for c in cikti), (
            f"'{giris}' → '{cikti}' birleşik işaret içeriyor → arama eşleşmesi bozulur"
        )
        assert cikti == cikti.lower(), "çıktı tam düşürülmemiş"


# ── Ortak kaynak: iki yüzey de aynı katlamayı kullanmalı ────────────────────


def test_KRITIK_arama_ve_PDF_AYNI_katlamayi_kullaniyor():
    """⚠️ 'AYNI BUG BAŞKA YERDE' KORUMASI. Türkçe collation tuzağı iki yüzeyde vardı: hasta
    arama indeksi VE PDF rapor filtresi. İkisi ayrı `str.lower()` kullanırsa biri düzeltilip
    diğeri unutulur. Her ikisi de `utils.turkce_metin.arama_katla`ya bağlanmalı."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    for dosya in ("apps/backend/database/patient_database.py", "apps/backend/utils/pdf_report_generator.py"):
        src = (kok / dosya).read_text(encoding="utf-8")
        assert "arama_katla" in src, f"{dosya}: ortak Türkçe katlamayı kullanmıyor"

    # PDF filtresi artık ham `.lower()` ile hasta adı karşılaştırmamalı.
    pdf = (kok / "apps/backend/utils/pdf_report_generator.py").read_text(encoding="utf-8")
    i = pdf.find("patient_sessions = [")
    govde = pdf[max(0, i - 400) : i + 400]
    assert "arama_katla" in govde, "PDF hasta filtresi ortak katlamayı kullanmıyor"


def test_util_arama_katla_dogrudan():
    """Ortak util: İ/I düzelir; aksan ve ı/i KORUNUR (mobil aramaNormalize.ts ile aynı)."""
    from utils.turkce_metin import arama_katla

    # İ/I bug'ı düzelir
    assert arama_katla("İhsan") == arama_katla("ihsan") == arama_katla("İHSAN")
    assert arama_katla("İpek") == arama_katla("ipek")
    # ⚠️ Aksan KATLANMAZ (hasta-kimliği güvenliği)
    assert arama_katla("Şirin") != arama_katla("Sirin"), "aksan katlandı → yanlış-hasta riski"
    assert arama_katla("Gökçe") != arama_katla("gokce")
    # ⚠️ ı ve i AYRI harf
    assert arama_katla("Işık") != arama_katla("isik")
    # Farklı adlar
    assert arama_katla("Ahmet") != arama_katla("Mehmet")
    # Birleşik nokta üretilmemeli (bug'ın kökü)
    import unicodedata

    assert not any(unicodedata.combining(c) for c in arama_katla("İ"))


def test_KRITIK_backend_mobil_AYNI_kural(hasta_db):
    """⚠️ İKİ UÇ PARİTESİ: mobil client-side süzme (aramaNormalize.ts) ile backend arama indeksi
    AYNI hastayı AYNI terimle aynı bulmalı. Mobilin `aramaNormalize.test.ts`te kilitlediği
    vakaların backend'de de aynı sonucu vermesi, "aynı hasta iki cihazda farklı bulunuyor"
    sınıfını kapatır."""
    from utils.turkce_metin import arama_katla

    def mobil_eslesir(metin, sorgu):
        # aramaNormalize.ts::aramaEslesir'in Python ikizi (aynı token, includes).
        return arama_katla(sorgu).strip() == "" or arama_katla(sorgu).strip() in arama_katla(metin)

    # aramaNormalize.test.ts satır 52-60'ın birebir karşılığı:
    assert mobil_eslesir("İpek", "ipek") is True
    assert mobil_eslesir("Işık", "ışık") is True
    assert mobil_eslesir("İpek", "pamuk") is False
    assert mobil_eslesir("Şirin", "sirin") is False  # aksan korunur
    assert mobil_eslesir("Gökçe", "gokce") is False


def test_norm_surumu_parmak_izinde():
    """⚠️ Normalize değişikliği sahadaki indeksi otomatik tazelemeli.

    Sürüm parmak-izine katılmazsa, düzeltme yayınlansa bile MEVCUT hastalar eski (bozuk)
    indeksle kalır ve Türkçe arama onlarda çalışmaz."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "apps" / "backend" / "database" / "patient_database.py").read_text(
        encoding="utf-8"
    )
    assert "_SEARCH_NORM_VERSION" in src, "normalize sürümü tanımlı değil"
    i = src.find("_fp = hashlib.sha256(")
    assert i != -1
    govde = src[i : i + 220]
    # D1.20 (B-10.129): eskiden `... or "norm" in govde` idi — `b"|norm"` (sürümsüz) de geçiyordu (TOTOLOJİ).
    assert "_SEARCH_NORM_VERSION" in govde, (
        "normalize sürümü parmak-izine katılmıyor → mevcut hastalarda indeks tazelenmez"
    )


def _yeniden_ac(temp_app_data):
    import database.patient_database as pdb

    return pdb.PatientDatabase(str(temp_app_data / "patients.db"))


def _kurulum_sayaci(monkeypatch):
    import database.patient_database as pdb

    sayac: list[int] = []
    gercek = pdb.PatientDatabase._rebuild_search_index

    def say(self, cursor):
        sayac.append(1)
        return gercek(self, cursor)

    monkeypatch.setattr(pdb.PatientDatabase, "_rebuild_search_index", say)
    return sayac


def test_KRITIK_norm_surumu_ARTINCA_mevcut_indeks_acilista_YENIDEN_KURULUR(hasta_db, temp_app_data, monkeypatch):
    """D1.20 (B-10.129) DAVRANIŞ: `utils.turkce_metin.SURUM` artınca GERÇEK açılış yolu
    (`_ensure_search_index`) parmak izini değiştirmeli ve MEVCUT hastanın indeksini yeniden kurmalı;
    yoksa normalize kuralı değişse de sahadaki hastalar Türkçe aramada bulunamaz."""
    import database.patient_database as pdb

    hasta_db.add_patient({"name": "İhsan", "owner": "T", "species": "Kedi"})
    fp_dosyasi = hasta_db._key_dir / ".patient_search_keyfp"
    once = fp_dosyasi.read_text(encoding="utf-8").strip()
    sayac = _kurulum_sayaci(monkeypatch)
    monkeypatch.setattr(pdb.PatientDatabase, "_SEARCH_NORM_VERSION", pdb.PatientDatabase._SEARCH_NORM_VERSION + 1)

    yeni_db = _yeniden_ac(temp_app_data)

    assert fp_dosyasi.read_text(encoding="utf-8").strip() != once, "normalize sürümü parmak izini DEĞİŞTİRMİYOR"
    assert sayac, "sürüm artınca mevcut hastanın arama indeksi açılışta YENİDEN KURULMADI"
    assert "İhsan" in _adlar(yeni_db.search_patients("ihsan")), "yeniden kurulan indeks hastayı bulmuyor"


def test_KRITIK_ESKI_kuralla_kurulu_indeks_surum_ARTINCA_turkce_aramada_hastayi_BULUR(
    hasta_db, temp_app_data, monkeypatch
):
    """D2.05 (B-3.107) DAVRANIŞ — normalize kuralı GERÇEKTEN değişmiş bir saha indeksi.

    Yukarıdaki D1.20 kolu sürümü artırır ama kuralı DEĞİŞTİRMEZ: eski ve yeni token'lar aynı
    olduğundan yeniden kurulum hiç olmasa da arama bulur; o kolun ayırt ediciliği yalnız
    `_rebuild_search_index` sayacındadır. Ölçüldü (2026-10-06, 2-A): yeniden kurma gövdesi no-op
    yapılınca (çağrı sayılır, indeks DEĞİŞMEZ) arama/hasta kapı kümesi 22/22 YEŞİL kaldı.

    Burada indeks ESKİ kuralla kurulur — v1: `str.lower()` ('İ' → 'i' + U+0307 birleşik nokta;
    saha bulgusu 2026-08-30: "İhsan" kaydedip "ihsan" arayan hekim hastayı BULAMIYORDU). Sonra
    gerçek kural geri gelir ve sürüm artar; yeniden açılan GERÇEK `PatientDatabase` hastayı
    "ihsan" aramasında BULMALI. Bulamıyorsa sahadaki hastalar Türkçe aramada kayıp kalır.

    MUTASYONLAR (hepsi KIRMIZI): `if count == 0 or (_stored_fp and _stored_fp != _fp)` →
    `if count == 0` (plan) · parmak izinden normalize sürümü çıkar · `_rebuild_search_index` no-op.
    """
    import database.patient_database as pdb

    gercek_kural = pdb.PatientDatabase._normalize_search_value
    monkeypatch.setattr(pdb.PatientDatabase, "_normalize_search_value", lambda self, v: str(v or "").strip().lower())
    hasta_db.add_patient({"name": "İhsan", "owner": "T", "species": "Kedi"})
    # Ö.6 — araç kanıtı: eski kuralın kusuru bu kurulumda GERÇEKTEN var (yoksa kapı hiçbir şey ölçmez).
    assert "İhsan" not in _adlar(hasta_db.search_patients("ihsan")), "eski kural kurulamadı — kapı kör olurdu"

    monkeypatch.setattr(pdb.PatientDatabase, "_normalize_search_value", gercek_kural)
    monkeypatch.setattr(pdb.PatientDatabase, "_SEARCH_NORM_VERSION", pdb.PatientDatabase._SEARCH_NORM_VERSION + 1)
    yeni_db = _yeniden_ac(temp_app_data)

    assert "İhsan" in _adlar(yeni_db.search_patients("ihsan")), (
        "normalize kuralı ve sürümü değişti ama açılış ESKİ token'larla kurulu indeksi yeniden kurmadı → "
        "sahadaki hasta Türkçe aramada BULUNAMIYOR"
    )
    assert "İhsan" in _adlar(yeni_db.search_patients("İHSAN")), (
        "büyük harfli Türkçe arama yeniden kurulumdan sonra da bulmalı"
    )


def test_KRITIK_D225_kurulum_COMMIT_dusurse_parmak_izi_YENI_surume_gecmez_sonraki_acilis_YENIDEN_kurar(
    hasta_db, temp_app_data, monkeypatch
):
    """D2.25 (B-3.106) — parmak izi YALNIZ yeniden kurulumu içeren işlem COMMIT edildikten SONRA yazılır.

    Eskiden `_ensure_search_index` yeni parmak izini commit'ten ÖNCE yazıyordu: commit düşerse (disk G-Ç / dolu)
    yeniden kurma GERİ ALINIR ama dosya YENİ sürümü taşır → sonraki açılışlar "güncel" sanıp yeniden kurmaz, eski
    kurala göre kurulmuş HMAC indeksi kalır, hasta Türkçe aramada BULUNAMAZ — günlük de bir şey söylemez.

    Kurgu: indeks ESKİ kuralla kurulur (D2.05 kolu gibi); sonra gerçek kural + sürüm artışıyla açılışta COMMIT bir kez
    düşer (gerçek `_get_connection`'ın bağlantısı sarılır, yalnız `commit` patlar; geri alma gerçek). Kurulum
    `RuntimeError` vermeli; parmak izi ESKİ kalmalı; ardından normal açılış indeksi yeniden kurup hastayı bulmalı.

    MUTASYON: parmak izi yazımını commit'ten önceye (`_ensure_search_index` içine) geri almak → KIRMIZI.
    """
    import contextlib
    import sqlite3

    import database.patient_database as pdb

    gercek_kural = pdb.PatientDatabase._normalize_search_value
    monkeypatch.setattr(pdb.PatientDatabase, "_normalize_search_value", lambda self, v: str(v or "").strip().lower())
    hasta_db.add_patient({"name": "İhsan", "owner": "T", "species": "Kedi"})
    fp_dosyasi = hasta_db._key_dir / ".patient_search_keyfp"
    eski_iz = fp_dosyasi.read_text(encoding="utf-8").strip()
    assert "İhsan" not in _adlar(hasta_db.search_patients("ihsan")), "eski kural kurulamadı — kapı kör olurdu"
    hasta_db._reset_thread_conn()

    monkeypatch.setattr(pdb.PatientDatabase, "_normalize_search_value", gercek_kural)
    monkeypatch.setattr(pdb.PatientDatabase, "_SEARCH_NORM_VERSION", pdb.PatientDatabase._SEARCH_NORM_VERSION + 1)

    gercek_baglanti = pdb.PatientDatabase._get_connection
    durum = {"patlat": True}

    class _CommitDusen:
        def __init__(self, conn):
            self._conn = conn

        def commit(self):
            if durum["patlat"]:
                durum["patlat"] = False
                raise sqlite3.OperationalError("disk I/O error")
            return self._conn.commit()

        def __getattr__(self, ad):
            return getattr(self._conn, ad)

    @contextlib.contextmanager
    def _commit_bir_kez_duser(self):
        with gercek_baglanti(self) as conn:
            yield _CommitDusen(conn)

    monkeypatch.setattr(pdb.PatientDatabase, "_get_connection", _commit_bir_kez_duser)
    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    monkeypatch.setattr(pdb.PatientDatabase, "_get_connection", gercek_baglanti)
    assert not durum["patlat"], "commit hiç denenmedi — kurgu bozuk"
    assert fp_dosyasi.read_text(encoding="utf-8").strip() == eski_iz, (
        "kurulum COMMIT'i DÜŞTÜ ama parmak izi YENİ sürüme geçti → sonraki açılışlar yeniden KURMAZ"
    )

    yeni_db = _yeniden_ac(temp_app_data)
    assert "İhsan" in _adlar(yeni_db.search_patients("ihsan")), (
        "commit'i düşen kurulumdan sonra normal açılış indeksi YENİDEN KURMADI → hasta Türkçe aramada BULUNAMIYOR"
    )
    assert fp_dosyasi.read_text(encoding="utf-8").strip() != eski_iz, (
        "başarılı kurulumdan sonra parmak izi GÜNCELLENMEDİ"
    )


def test_KARSIT_surum_ayniyken_acilista_indeks_yeniden_KURULMAZ(hasta_db, temp_app_data, monkeypatch):
    """Tazeleme "her açılışta kur" biçiminde bozulmasın (dolu tabloda gereksiz yeniden kurulum)."""
    hasta_db.add_patient({"name": "İpek", "owner": "T", "species": "Kedi"})
    sayac = _kurulum_sayaci(monkeypatch)
    _yeniden_ac(temp_app_data)
    assert not sayac, "sürüm/anahtar değişmeden indeks yeniden kuruldu"


def test_KRITIK_norm_surumu_TEK_KAYNAK_turkce_metin_SURUM_izlenir(tmp_path):
    """Bağımsız inceleme (r5): yukarıdaki kol sınıf niteliğini yamalıyor — `_SEARCH_NORM_VERSION`'ın
    `utils.turkce_metin.SURUM`'a bağı koparılıp literale çevrilse (`= 3`) yeşil kalıyordu; o zaman SURUM
    artırılsa da parmak izi değişmez ve sahadaki hastalar Türkçe aramada bulunamaz (B-10.129'un zararı).
    AYRI süreçte (sınıf ilk kez yüklenir; süreç içi reload diğer testlerin sınıf kimliğini bozardı)
    SURUM artırılır → sınıf niteliği onu İZLEMELİ. Çocuk ağ bekçili."""
    import json
    from pathlib import Path

    from betik_alt_sureci import kostur, yalitik_ortam

    kok = Path(__file__).resolve().parents[1]
    testler = Path(__file__).resolve().parent
    kod = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(testler)!r})\n"
        "import alt_surec_ag_bekcisi as _ag\n"
        f"sys.path.remove({str(testler)!r})\n"
        f"sys.path[:0] = [{str(kok)!r}, {str(kok / 'apps' / 'backend')!r}]\n"
        "import utils.turkce_metin as tm\n"
        "tm.SURUM = tm.SURUM + 1\n"
        "import database.patient_database as pdb\n"
        'print("SONUC " + json.dumps({"sinif": pdb.PatientDatabase._SEARCH_NORM_VERSION, '
        '"surum": tm.SURUM, "ag": _ag.ENGELLENEN}))\n'
    )
    (tmp_path / "surum_bagi.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "surum_bagi.py")], cwd=tmp_path, env=yalitik_ortam(tmp_path), sure=120)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    assert p.returncode == 0 and satir, p.stderr[-600:]
    s = json.loads(satir[-1][len("SONUC ") :])
    assert s["ag"] == [], s
    assert s["sinif"] == s["surum"], (
        f"PatientDatabase._SEARCH_NORM_VERSION={s['sinif']} turkce_metin.SURUM={s['surum']}'ı İZLEMİYOR — "
        "tek kaynak bağı kopmuş: SURUM artışı indeksi yeniden kurdurmaz"
    )
