# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""UYGULANAN DOZ KAYDI, SENSÖR SAKLAMA SÜRESİYLE SİLİNİYORDU (denetim 2026-08-17).

`session_coil_runs` = UYGULANAN DOZ ("hangi bobin, hangi frekans/duty/faz ile, kaç saniye
çalıştı"), telemetri DEĞİL — telemetri ayrı tabloda (`sensor_samples`). Buna rağmen bu tablonun
temizliği **sensör** saklama süresine (varsayılan 90 gün) bağlıydı ve iki sonucu vardı:

  · `treatment_sessions` HİÇ silinmiyor → 90. günden sonra seans başlığı duruyor ama "hangi bobin,
    hangi duty" cevabı yok oluyor. `utils/pdf_report_generator` "Bobin Çalışmaları" tablosunu
    `if not runs: return` ile SESSİZCE atlıyor: yan etki soruşturmasında 4 ay önceki seansın
    raporu doz tablosuz çıkıyor, hiçbir uyarı yok.
  · KVKK açısından TERS TAKAS: kimliği taşıyan taraf (`patients` / `treatment_sessions`) kalıyor,
    tıbbi kanıt gidiyor. Veri minimizasyonuna sıfır katkı.

Üstüne, geri dönüşsüz PII maskelemesi denetim izine YAZILIYOR ama geri dönüşsüz DOZ silmesi
yazılmıyordu — bu asimetri de kapandı.

⚠️ ANALİZ RAPORDAN DAHA BÜYÜK BİR ŞEY BULDU: doz kaydını silen **İKİ** bağımsız üretim yolu vardı,
**farklı iki ortam değişkeniyle** — `services/headless_db_maintenance` (`PEMF_RETAIN_SENSOR_DAYS`)
ve `servers/api_server._daily_maintenance_loop` (`PEMF_SENSOR_RETAIN_DAYS`, hiçbir yerde
belgelenmemiş). Operatör birincisini `0` yapıp "silme kapalı" sansa bile ikincisi silmeye devam
ediyordu; dahası o yolda `0` = kapalı DEĞİLDİ (`max(1, ...)` yüzünden 1 GÜNLÜK saklama).
İkinci yol kaldırıldı (T4 kilitliyor).

⚠️ SAHİBİN GERÇEK KARARI KORUNDU: "bu tablo hiç temizlenmiyordu, sınırsız büyüyordu" gerekçesi
aynen geçerli — `purge_old_coil_runs` duruyor, yalnız SAATİ ayrıldı (3650 gün) ve `0 = adım kapalı`
sözleşmesi yeni parametrede de uygulanıyor. Büyümeyi sürükleyen `sensor_samples`e DOKUNULMADI.

⚠️ ONAY KAPISI (PII'daki gibi) BİLEREK EKLENMEDİ: PII kapısı çalışıyor çünkü bir arayüz yüzeyi var
(`/settings` → "acknowledge" düğmesi). Doz için böyle bir yüzey YOK; onay hiç verilemeyeceği için
adım kalıcı olarak ölü kalır ve kimsenin görmediği bir "bekleyen" sayacı üretir. Sahip gerçekten
"hiç silinmesin" isterse dürüst ifadesi `PEMF_RETAIN_DOSE_DAYS=0`dır.
"""

import ast
import os
import pathlib
import time

os.environ.pop("PEMF_SIMULATE", None)

import pytest

ESKI_GUN = 200


@pytest.fixture
def db(tmp_path):
    """İzole DB. ⚠️ `get_treatment_db()` KULLANILMAZ — o yol-anahtarlı bir singleton döndürür ve
    gerçek klinik DB'sine düşebilir (bu depoda süit bir kez tam olarak öyle bozuldu)."""
    from database.treatment_history_db import TreatmentHistoryDB

    d = TreatmentHistoryDB(tmp_path)
    yield d
    d.close_connections()


@pytest.fixture
def eski_doz(db):
    """200 gün önce uygulanmış İKİ doz kaydı + özetleri + BİR sensör örneği.

    ⚠️ İKİ satır BİLEREK: tek satırla `item_count=removed` yerine sabit `1` yazan bir mutasyon
    ayırt edilemezdi (ölçüldü — sessizce geçti)."""
    sid = db.start_session("Manuel", patient_name="Minnos")
    eski = time.time() - ESKI_GUN * 86400
    ridler = []
    for bobin in (3, 4):
        rid = db.start_coil_run(
            sid, bobin, frequency_hz=50, duty_percent=25, intensity_mt=2.0, hw_type="stm", started_epoch=eski
        )
        assert rid, "on-kosul: doz kaydi yazilamadi"
        db.end_coil_run(rid, eski + 600)
        db.add_sensor_run_summary(rid, sample_count=5, temp_max=41.0)
        ridler.append(rid)
    db.add_sensor_samples_batch(sid, [{"coil_id": 3, "temperature": 40.0, "sample_ts": eski}])
    return sid, ridler


def _ozet_satir_sayisi(db) -> int:
    """`sensor_run_summary` tablosunu DOĞRUDAN say.

    ⚠️ `get_run_summaries(sid)` KULLANILAMAZ: o, `session_coil_runs` üzerinden JOIN yapıyor, yani
    doz satırı silindiğinde ORPHAN özet GÖRÜNMEZ olur ve "özet de silindi" iddiası sahte-yeşile
    döner (ölçüldü: özet silmesini kaldıran mutasyon sessizce geçti)."""
    with db._get_connection() as conn:
        return int(conn.cursor().execute("SELECT COUNT(*) FROM sensor_run_summary").fetchone()[0])


def test_KRITIK_doz_kaydi_SENSOR_suresiyle_SILINMEZ(db, eski_doz):
    """Sensör saklama süresi 90 gün olsa da 200 günlük DOZ kaydı KALMALI."""
    sid, _ = eski_doz

    rep = db.apply_data_retention_policy(
        sensor_retain_days=90, event_retain_days=0, dead_outbox_retain_days=0, pii_retain_days=0
    )

    # ⚠️ SAHTE-YEŞİL KALKANI: sensör adımının GERÇEKTEN koştuğunu ve epoch kolonunun eşleştiğini
    # kanıtlar. Bu olmadan, kurulum bozuksa (yanlış kolona yazma) test yanlış sebeple yeşil olurdu.
    assert rep["sensor_samples_removed"] == 1, f"sensor adimi hic kosmadi: {rep}"

    runs = db.get_session_coil_runs(sid)
    assert len(runs) == 2, (
        "UYGULANAN DOZ, sensor saklama suresiyle SILINDI -> seans basligi duruyor ama 'hangi bobin, "
        "hangi duty' cevabi yok; PDF'te 'Bobin Calismalari' tablosu SESSIZCE kayboluyor"
    )
    assert runs[0]["frequency_hz"] == 50.0
    assert _ozet_satir_sayisi(db) == 2, "doza bagli sensor OZETLERI de silindi"


def test_doz_KENDI_suresiyle_temizlenir(db, eski_doz):
    """⚠️ SAHİBİN KARARI KORUNUYOR: sınırsız büyüme engeli duruyor, yalnız saat ayrıldı.

    Aynı zamanda yukarıdaki testin sahte-yeşilini kapatır: satırın 100 günlük eşikle GERÇEKTEN
    silinebildiğini gösterir, yani "satır zaten uygun değildi" açığı kalmaz."""
    sid, _ = eski_doz

    rep = db.apply_data_retention_policy(
        sensor_retain_days=0,
        event_retain_days=0,
        dead_outbox_retain_days=0,
        pii_retain_days=0,
        dose_retain_days=100,
    )

    assert rep["coil_runs_removed"] == 2, f"doz kendi suresiyle de temizlenmiyor: {rep}"
    assert db.get_session_coil_runs(sid) == []
    assert _ozet_satir_sayisi(db) == 0, (
        "bagli sensor ozeti ORPHAN kaldi (JOIN yuzunden arayuzden GORUNMEZ ama diskte buyumeye "
        "devam eder — sahibin 'sinirsiz buyume olmasin' karari delinir)"
    )


def test_doz_silme_DENETIM_izi_birakir(db, eski_doz):
    """Geri dönüşsüz doz silmesi iz bırakmalı (PII maskelemesindeki simetriyi tamamlar)."""
    db.apply_data_retention_policy(
        sensor_retain_days=0,
        event_retain_days=0,
        dead_outbox_retain_days=0,
        pii_retain_days=0,
        dose_retain_days=100,
    )

    izler = [e for e in db.denetim_oku(50) if e.get("event_type") == "retention.doz_silindi"]
    assert len(izler) == 1, f"geri donussuz doz silmesi denetim izine YAZILMADI: {izler}"
    assert izler[0].get("item_count") == 2
    assert "100" in str(izler[0].get("detail") or ""), f"silme esigi ize yazilmadi: {izler[0]}"

    # Silinecek satır kalmadı → GÜRÜLTÜ üretme (koşul `if removed:`).
    db.apply_data_retention_policy(
        sensor_retain_days=0,
        event_retain_days=0,
        dead_outbox_retain_days=0,
        pii_retain_days=0,
        dose_retain_days=100,
    )
    izler2 = [e for e in db.denetim_oku(50) if e.get("event_type") == "retention.doz_silindi"]
    assert len(izler2) == 1, "0 satir silindiginde de iz yazildi (gurultu)"


def test_dose_retain_days_SIFIR_adimi_KAPATIR(db, eski_doz):
    """⚠️ `0 = adım kapalı` sözleşmesi (sahibin kendi yazdığı ilke) DOZ adımında da geçerli olmalı.

    ⚠️ Bu kapı BURADA olmak zorunda: `tests/test_treatment_retention.py`teki "adımlar kapatılabilir"
    testinde silinecek ESKİ satır YOK, dolayısıyla koşulu tamamen kaldıran bir mutasyon orada
    sessizce geçiyordu (ölçüldü). Burada 200 günlük gerçek doz kayıtları var."""
    sid, _ = eski_doz

    rep = db.apply_data_retention_policy(
        sensor_retain_days=0,
        event_retain_days=0,
        dead_outbox_retain_days=0,
        pii_retain_days=0,
        dose_retain_days=0,
    )

    assert rep["coil_runs_removed"] == 0, f"'0 = kapali' sozlesmesi DOZ adiminda uygulanmiyor: {rep}"
    assert len(db.get_session_coil_runs(sid)) == 2, "adim KAPALIYKEN doz kaydi silindi"


def test_gunluk_bakim_dongusu_dozu_SENSOR_suresiyle_SILMEZ():
    """İKİNCİ, AYARLANAMAZ silme yolu kaldırılmış olmalı.

    ⚠️ `ast` TABANLI: `_daily_maintenance_loop` `while True` + baştaki 60 sn uyku içerdiği için
    çağrılarak sınanamaz. `ast` yorumları düğüm olarak GÖRMEZ → kapı kendi yorumuyla kandırılamaz.
    ⚠️ Kaynak, IMPORT EDİLEN dosyadan okunur (sabit yol değil) — modül taşınırsa test kör kalmaz."""
    from servers import api_server

    src = pathlib.Path(api_server.__file__).read_text(encoding="utf-8")
    mod = ast.parse(src)

    fnler = [n for n in ast.walk(mod) if isinstance(n, ast.FunctionDef) and n.name == "_daily_maintenance_loop"]
    assert len(fnler) == 1, "gunluk bakim dongusu bulunamadi (yeniden adlandirilmis?) — kapi KOR kalirdi"

    cagrilar = [
        c
        for c in ast.walk(fnler[0])
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "purge_old_coil_runs"
    ]
    assert cagrilar == [], (
        "doz kaydi IKINCI ve AYARLANAMAZ yoldan siliniyor: bu dongu `PEMF_SENSOR_RETAIN_DAYS` "
        "okuyor (headless bakimin `PEMF_RETAIN_SENSOR_DAYS`inden FARKLI, belgelenmemis bir ad) ve "
        "orada `0` = kapali DEGIL, 1 GUNLUK saklama demek"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
