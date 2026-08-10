# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CİHAZ TAŞIMA — TAM VERİ + İLİŞKİ BÜTÜNLÜĞÜ (2026-08-09 denetimi, ENGEL x2).

ARIZA 1 — EKSİK VERİ: dışa aktarma YALNIZCA `treatment_sessions` + `ai_analyses` alıyordu.
Tıbbi kaydın asıl gövdesi bağlı tablolardadır:
    session_coil_runs   → hangi bobin, hangi frekans/duty ile, ne kadar süre = UYGULANAN DOZ
    sensor_samples      → sıcaklık/akım telemetrisi (yan etki soruşturmasının kanıtı)
    session_events      → acil durdurma dahil denetim izi
    session_parameters  → seansın uygulanan parametreleri
Veteriner "kliniğimin geçmişini taşıdım" diyordu; gerçekte seans BAŞLIKLARI taşınıyor, dozun
kaydı eski makinede kalıyordu. Eski makine silinince geri dönülemez kayıp.

ARIZA 2 — KOPUK İLİŞKİ: `import_rows` `id`'yi düşürüyordu. Bağlı tablolar eklense bile
`session_id` hedefte BAŞKA bir seansı gösterirdi → bir hastanın telemetrisi başka hastanın
kaydında görünürdü. Sessiz ve teşhis edilemez bir tıbbi hata.

Bu dosya gerçek bir cihaz taşımasını uçtan uca çalıştırır: kaynak makineyi doldur → dışa aktar →
BOŞ hedef makineye içe aktar → İKİ TARAFI KARŞILAŞTIR.
"""

import pytest


def _db(dizin):
    from database.treatment_history_db import TreatmentHistoryDB

    return TreatmentHistoryDB(dizin)


def _seans_kur(db, hasta_adi, freq, bobin, temp):
    """Bir hastaya tam bir seans yaz: hasta + seans + parametre + bobin koşusu + sensör + olay."""
    pid = db.upsert_patient(
        {"name": hasta_adi, "patient_uuid": f"uuid-{hasta_adi}", "owner_email": f"{hasta_adi}@sahip.com"}
    )
    sid = db.start_session(
        treatment_mode="Manuel", patient_name=hasta_adi, operator_name="Dr. Test", operator_email="vet@klinik.com"
    )
    db.set_session_meta(sid, patient_id=pid)
    db.set_session_parameter(sid, "frekans", str(freq), "Hz")
    with db._get_connection() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO session_coil_runs (session_id, coil_id, started_epoch, ended_epoch, "
            "duration_seconds, frequency_hz, duty_percent, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (sid, bobin, 1000.0, 1300.0, 300.0, freq, 25.0, 1000.0),
        )
        crid = cur.lastrowid
        cur.execute(
            "INSERT INTO sensor_run_summary (coil_run_id, sample_count, temp_max, created_at) VALUES (?,?,?,?)",
            (crid, 5, temp, 1000.0),
        )
        cur.execute(
            "INSERT INTO sensor_samples (session_id, coil_id, sample_ts, temperature_c, created_at) VALUES (?,?,?,?,?)",
            (sid, str(bobin), 1100.0, temp, 1100.0),
        )
        c.commit()
    db.record_session_event(sid, "session_started", payload={"hasta": hasta_adi}, severity="info")
    db.add_ai_analysis(
        module_id="m", patient_name=hasta_adi, result_summary=f"{hasta_adi}-analiz", operator_email="vet@klinik.com"
    )
    return pid, sid, crid


def _tam_resim(db):
    """İlişkileri İSİMLE çöz — id'ler taşımada değişir, anlam değişmemeli."""
    ham = db.export_rows()
    seans_adi = {s["id"]: s["patient_name"] for s in ham["treatment_sessions"]}
    hasta_adi = {h["id"]: h["name"] for h in ham["patients"]}
    kosu_seans = {k["id"]: seans_adi.get(k["session_id"]) for k in ham["session_coil_runs"]}
    return {
        "seanslar": sorted(seans_adi.values()),
        # her hastanın hangi seansa bağlı olduğu (patient_id ilişkisi)
        "seans_hasta": sorted(
            (s["patient_name"], hasta_adi.get(s.get("patient_id"))) for s in ham["treatment_sessions"]
        ),
        "doz": sorted(
            (seans_adi.get(k["session_id"]), k["coil_id"], k["frequency_hz"], k["duration_seconds"])
            for k in ham["session_coil_runs"]
        ),
        "sensor": sorted((seans_adi.get(x["session_id"]), x["temperature_c"]) for x in ham["sensor_samples"]),
        "ozet": sorted((kosu_seans.get(o["coil_run_id"]), o["temp_max"]) for o in ham["sensor_run_summary"]),
        "olaylar": sorted((seans_adi.get(e["session_id"]), e["event_type"]) for e in ham["session_events"]),
        "parametreler": sorted(
            (seans_adi.get(p["session_id"]), p["parameter_name"], p["parameter_value"])
            for p in ham["session_parameters"]
        ),
        "analizler": sorted(a["result_summary"] for a in ham["ai_analyses"]),
    }


def _idleri_kaydir(db, adet=17):
    """Kaynağın id'lerini 1'den BAŞLATMA.

    ⚠️ Bu, bu dosyanın en önemli kurulum ayrıntısı. Boş bir hedefe aktarımda AUTOINCREMENT
    id'ler tesadüfen kaynağınkilerle AYNI çıkar (1,2,3…) → yeniden eşleme TAMAMEN BOZUK olsa
    bile ilişkiler doğru görünür. Mutasyon turunda ölçüldü: eşleme kaldırıldığında testlerin
    yalnız 2'si düşüyordu. Kaynağı kaydırınca her ilişki testi eşlemeyi GERÇEKTEN sınar.
    (AUTOINCREMENT silinen id'leri yeniden kullanmaz — sqlite_sequence ilerler.)
    """
    with db._get_connection() as c:
        cur = c.cursor()
        for i in range(adet):
            cur.execute(
                "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode) VALUES ('x','x','x')"
            )
            cur.execute("INSERT INTO patients (name) VALUES (?)", (f"dolgu{i}",))
            cur.execute("INSERT INTO session_coil_runs (coil_id, started_epoch, created_at) VALUES (1, 0, 0)")
        cur.execute("DELETE FROM session_coil_runs")
        cur.execute("DELETE FROM treatment_sessions")
        cur.execute("DELETE FROM patients")
        c.commit()


@pytest.fixture
def kaynak(tmp_path):
    """İki hastalı, dolu bir klinik makinesi (id'leri kasten kaydırılmış — bkz. _idleri_kaydir)."""
    d = _db(tmp_path / "kaynak")
    _idleri_kaydir(d)
    _seans_kur(d, "Pamuk", 50.0, 3, 38.5)
    _seans_kur(d, "Boncuk", 20.0, 7, 41.2)
    yield d
    d.close_connections()


def test_kaynak_idleri_1den_BASLAMIYOR(kaynak):
    """Kurulumun kendisinin kapısı: kaydırma bozulursa ilişki testleri sessizce ANLAMSIZLAŞIR."""
    ham = kaynak.export_rows()
    assert min(s["id"] for s in ham["treatment_sessions"]) > 3, (
        "kaynak id'leri kaydirilmamis — yeniden esleme testleri gercek sinama yapmaz"
    )


@pytest.fixture
def hedef(tmp_path):
    d = _db(tmp_path / "hedef")
    yield d
    d.close_connections()


# ── ARIZA 1: eksik veri ──────────────────────────────────────────────────────


def test_KRITIK_disa_aktarma_DOZ_kaydini_ICERIR(kaynak):
    """`session_coil_runs` = uygulanan doz. Eskiden pakete HİÇ girmiyordu."""
    ham = kaynak.export_rows()
    assert len(ham["session_coil_runs"]) == 2, "bobin kosulari (DOZ) tasinmiyor"
    assert {k["frequency_hz"] for k in ham["session_coil_runs"]} == {50.0, 20.0}


def test_KRITIK_disa_aktarma_TUM_bagli_tablolari_ICERIR(kaynak):
    ham = kaynak.export_rows()
    for tablo in (
        "patients",
        "treatment_sessions",
        "session_parameters",
        "session_coil_runs",
        "sensor_run_summary",
        "sensor_samples",
        "session_events",
        "ai_analyses",
    ):
        assert ham.get(tablo), f"{tablo} disa aktarilmadi — tasimada SESSIZCE kaybolurdu"


def test_disa_aktarma_id_KORUR(kaynak):
    """İçe aktarma ilişkileri id'lerle yeniden kurar → id'ler pakette OLMALI."""
    ham = kaynak.export_rows()
    assert all("id" in s for s in ham["treatment_sessions"])
    assert all(k.get("session_id") is not None for k in ham["session_coil_runs"])


# ── ARIZA 2: ilişki bütünlüğü (asıl kanıt: uçtan uca taşıma) ────────────────


def test_KRITIK_tam_tasima_HICBIR_SEY_KAYBETMEZ(kaynak, hedef):
    once = _tam_resim(kaynak)
    hedef.import_rows(kaynak.export_rows(), replace=False)
    assert _tam_resim(hedef) == once, "tasima sonrasi klinik gecmisi AYNI degil"


def test_KRITIK_dozlar_DOGRU_seansa_baglanir(kaynak, hedef):
    """En tehlikeli sessiz hata: Pamuk'un dozu Boncuk'un kaydında görünmesi."""
    hedef.import_rows(kaynak.export_rows(), replace=False)
    doz = dict((s, (c, f)) for s, c, f, _d in _tam_resim(hedef)["doz"])
    assert doz["Pamuk"] == (3, 50.0), f"Pamuk'un dozu yanlis seansa bagli: {doz}"
    assert doz["Boncuk"] == (7, 20.0), f"Boncuk'un dozu yanlis seansa bagli: {doz}"


def test_KRITIK_hasta_bagi_KOPMAZ(kaynak, hedef):
    """`treatment_sessions.patient_id` hedefte doğru hasta satırını göstermeli."""
    hedef.import_rows(kaynak.export_rows(), replace=False)
    for seans_adi, hasta_adi in _tam_resim(hedef)["seans_hasta"]:
        assert seans_adi == hasta_adi, f"seans '{seans_adi}' hasta '{hasta_adi}' ile eslesti"


def test_sensor_ozeti_DOGRU_bobin_kosusuna_baglanir(kaynak, hedef):
    """İki kademeli ilişki: sensor_run_summary → session_coil_runs → treatment_sessions."""
    hedef.import_rows(kaynak.export_rows(), replace=False)
    ozet = dict(_tam_resim(hedef)["ozet"])
    assert ozet == {"Pamuk": 38.5, "Boncuk": 41.2}, f"ozet yanlis kosuya bagli: {ozet}"


def test_hedefteki_idler_CAKISMASA_da_dogru_baglanir(tmp_path, kaynak):
    """Hedefte ZATEN kayıt varsa yeni id'ler farklı aralıkta olur — eşleme yine doğru olmalı."""
    h = _db(tmp_path / "dolu_hedef")
    try:
        _seams = [_seans_kur(h, f"Yerli{i}", 10.0, 1, 30.0) for i in range(3)]
        h.import_rows(kaynak.export_rows(), replace=False)
        doz = dict((s, (c, f)) for s, c, f, _d in _tam_resim(h)["doz"])
        assert doz["Pamuk"] == (3, 50.0) and doz["Boncuk"] == (7, 20.0)
        assert doz["Yerli0"] == (1, 10.0), "yerel kayitlar bozuldu"
    finally:
        h.close_connections()


def test_replace_hedefi_TEMIZLER_sonra_dogru_baglar(tmp_path, kaynak):
    h = _db(tmp_path / "replace_hedef")
    try:
        _seans_kur(h, "Eski", 99.0, 2, 20.0)
        h.import_rows(kaynak.export_rows(), replace=True)
        resim = _tam_resim(h)
        assert resim["seanslar"] == ["Boncuk", "Pamuk"], "replace eski kayitlari birakti"
        assert dict((s, c) for s, c, _f, _d in resim["doz"]) == {"Pamuk": 3, "Boncuk": 7}
    finally:
        h.close_connections()


def test_KRITIK_ebeveynsiz_cocuk_satir_YANLIS_BAGLANMAZ(hedef):
    """Bozuk/elle düzenlenmiş bir pakette ebeveyni olmayan bir bobin koşusu, rastgele bir seansa
    bağlanmak yerine ATLANMALI — yanlış bağlamak sessiz tıbbi hatadır."""
    paket = {
        "treatment_sessions": [
            {
                "id": 1,
                "session_date": "2026-01-01",
                "start_time": "10:00",
                "treatment_mode": "Manuel",
                "patient_name": "Pamuk",
            }
        ],
        "session_coil_runs": [
            {"id": 1, "session_id": 1, "coil_id": 3, "started_epoch": 1.0, "created_at": 1.0},
            {"id": 2, "session_id": 999, "coil_id": 8, "started_epoch": 1.0, "created_at": 1.0},
        ],
    }
    n = hedef.import_rows(paket, replace=False)
    assert n["session_coil_runs"] == 1, "ebeveynsiz satir da eklendi (yanlis bagli olurdu)"
    ham = hedef.export_rows()
    assert {k["coil_id"] for k in ham["session_coil_runs"]} == {3}


def test_seanssiz_olay_NULL_ile_tasinir(hedef):
    """`session_id` NULL olan olaylar meşrudur (seans dışı sistem olayları) — atılmamalı."""
    paket = {
        "session_events": [
            {
                "id": 1,
                "event_uuid": "u1",
                "session_id": None,
                "event_type": "sistem",
                "severity": "info",
                "created_at": 1.0,
            }
        ]
    }
    assert hedef.import_rows(paket, replace=False)["session_events"] == 1


# ── geriye uyum ──────────────────────────────────────────────────────────────


def test_v1_yedegi_HALA_okunur(hedef):
    """Sahada v1 (.pemfbak) dosyaları var — yeni sürüm onları reddetmemeli."""
    v1 = {
        "bundle_version": 1,
        "treatment_sessions": [
            {
                "id": 5,
                "session_date": "2026-01-01",
                "start_time": "10:00",
                "treatment_mode": "Manuel",
                "patient_name": "Eski Hasta",
            }
        ],
        "ai_analyses": [{"id": 9, "module_id": "m", "patient_name": "Eski Hasta", "result_summary": "eski"}],
    }
    n = hedef.import_rows(v1, replace=False)
    assert n["treatment_sessions"] == 1 and n["ai_analyses"] == 1
    assert _tam_resim(hedef)["seanslar"] == ["Eski Hasta"]


def test_bos_paket_hata_vermez(hedef):
    assert hedef.import_rows({}, replace=False)["treatment_sessions"] == 0


# ── mükerrer hasta: BİRLEŞTİR, geçmişi ATMA ─────────────────────────────────
# ⚠️ Bu, düzeltmenin kendisinde bulunan bir açıktı. Hedefte AYNI `patient_uuid` varsa INSERT
# UNIQUE'ten patlar. "Atla ve devam et" demek yetmez: eşlemeye giriş yazılmazsa o hastaya bağlı
# TÜM seanslar, bobin koşuları ve telemetri "ebeveyni bulunamadı" dalına düşüp SESSİZCE ATILIR.
# Yani tek bir mükerrer hasta, o hastanın bütün geçmişini yok ederdi.


def test_KRITIK_ayni_hasta_hedefte_VARSA_gecmisi_ATILMAZ(tmp_path, kaynak):
    h = _db(tmp_path / "ayni_hasta")
    try:
        # Hedefte ZATEN "Pamuk" var (aynı uuid — ör. daha önce kısmi bir aktarım yapılmış).
        h.upsert_patient({"name": "Pamuk", "patient_uuid": "uuid-Pamuk"})
        h.import_rows(kaynak.export_rows(), replace=False)

        resim = _tam_resim(h)
        assert "Pamuk" in resim["seanslar"], "mukerrer hasta yuzunden SEANSLAR atildi"
        doz = dict((s, (c, f)) for s, c, f, _d in resim["doz"])
        assert doz.get("Pamuk") == (3, 50.0), f"Pamuk'un DOZ kaydi kayboldu: {doz}"
        assert doz.get("Boncuk") == (7, 20.0), "digler hasta da etkilendi"
    finally:
        h.close_connections()


def test_mukerrer_hasta_COGALTILMAZ(tmp_path, kaynak):
    """Birleştirme, aynı hastadan iki satır üretmemeli."""
    h = _db(tmp_path / "cogaltma")
    try:
        h.upsert_patient({"name": "Pamuk", "patient_uuid": "uuid-Pamuk"})
        h.import_rows(kaynak.export_rows(), replace=False)
        adlar = [p["name"] for p in h.export_rows()["patients"]]
        assert adlar.count("Pamuk") == 1, f"hasta cogaltildi: {adlar}"
    finally:
        h.close_connections()


def test_mukerrer_seans_olayi_gecmisi_BOZMAZ(tmp_path, kaynak):
    """`session_events.event_uuid` de UNIQUE — aynı mantık orada da geçerli."""
    h = _db(tmp_path / "mukerrer_olay")
    try:
        ham = kaynak.export_rows()
        h.import_rows(ham, replace=False)
        n = h.import_rows(ham, replace=False)  # AYNI paketi ikinci kez
        # Olaylar mükerrer eklenmemeli; seans/doz kayıtları ise append-only olduğu için çoğalır
        # (API bunu boş-hedef kuralıyla engeller) — burada önemli olan ÇÖKMEMESİ ve atmaması.
        assert n["session_events"] == 0, "mukerrer olay tekrar eklendi"
        assert len(h.export_rows()["patients"]) == 2, "hastalar cogaltildi"
    finally:
        h.close_connections()
