# -*- coding: utf-8 -*-
"""D2.52 (B-3.21 · B-3.28) + İG-6.5 P2u + Y12 + Y111 — "Tümünü değiştir" geri yüklemesi BÜTÜNLÜKLÜ, DÜRÜST ve yalnız CİHAZDAN.

ÖLÇÜLEN KUSURLAR:
  B-3.28 `thdb_bakim.import_rows(replace=True)` silme adımlarının hatasını `logger.debug` ile YUTUP devam ediyor ve commit ediyordu:
         kilitli / G-Ç hatalı bir DELETE'te eski ve yeni satırlar YAN YANA kalıyor, seanslar çiftleniyor, arayüz "Geri yüklendi" diyordu.
  P2u    (İG-6.5) aynı fonksiyonun EKLEME dalı her istisnayı "UNIQUE çakışması" sayıp yutuyordu: DB kilitliyken HİÇBİR satır yazılamıyor,
         yanıt 200 "success, 0 seans" dönüyordu. Yalnız `IntegrityError` birleştirme yoluna girmeli; öteki hatalar işlemi geri alır.
  B-3.21 / Y12  tedavi DB'si silinirken `patients.db`ye yalnız ekleme yapılıyor (Y12: yedekte olmayan hasta SİLİNMEZ — doğru), ama
         409 metni "hasta kayıtlarını SİLER" diyordu ve yanıt yedekte olmayan hastaları hiç raporlamıyordu (kartı kalır, seans geçmişi
         gider — operatör bunu bilmiyordu).
  Y111   REPLACE_ALL (dolu cihazın tüm tedavi kayıtlarını siler) cihaz dışından (LAN cihaz token'ı) yapılabiliyordu. Sahip: yalnız
         cihazın KENDİSİNDEN (A-03 deseni); kayıtlı operatörlü klinikte kimlikli hekimle (428). Boş cihaza ilk içe aktarma bugünkü gibi.
APARAT: gerçek DB'ler, gerçek `/api/data/export` paketi, gerçek uçlar. Arıza EN ALT katta: SQLite'ın kendisi — kalıcı tetikleyici
(`RAISE` ile silme reddi) ve ikinci bağlantının GERÇEK yazma kilidi (`BEGIN IMMEDIATE`; içe aktarma bağlantısının `busy_timeout`u
aparat süresini kısaltmak için 100 ms).
"""

from __future__ import annotations

import sqlite3

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, istekler, kapat, sayimlar, uclari_bagla

AYSE = "dr.ayse@klinik.com"


@pytest.fixture
def iki(tmp_path, monkeypatch):
    """A (kaynak, yedek alınır: Mia, Pamuk) · B (hedef, DOLU: Mia + Zeytin — Zeytin yedekte YOK)."""
    from servers import api_server as api
    from servers import auth, operator_tokens

    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN")
    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia", "Pamuk"], seans_basi=2)
    paket = disa_aktar(api.app)
    kaynak = sayimlar(ta, ha)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    kimlik_b = doldur(tb, hb, ["Zeytin"], seans_basi=1)
    operator_tokens.temizle_hepsi()
    try:
        yield type(
            "I",
            (),
            {
                "api": api,
                "paket": paket,
                "kaynak": kaynak,
                "ta": ta,
                "ha": ha,
                "tb": tb,
                "hb": hb,
                "zeytin": kimlik_b["Zeytin"],
            },
        )
    finally:
        for op in istekler(api.app, [("GET", "/api/operators", None, None)])[0].json().get("data", []):
            istekler(api.app, [("POST", "/api/operators/remove", {"email": op["email"]}, None)])
        operator_tokens.temizle_hepsi()
        kapat(ta, ha, tb, hb)


def _govde(i, confirm="REPLACE_ALL"):
    return {"passphrase": PAROLA, "blob_b64": i.paket["data_b64"], "confirm": confirm}


def _paket_satirlari(i):
    import base64

    from utils.data_export import decrypt_bundle

    return decrypt_bundle(base64.b64decode(i.paket["data_b64"]), PAROLA)


# ── B-3.28 · silme düşerse işlem geri alınır ──────────────────────────────────────────────────────────────────────


def test_KRITIK_D252_REPLACE_silme_adimi_DUSERSE_islem_GERI_alinir_eski_ve_yeni_YAN_YANA_kalmaz(iki):
    once = sayimlar(iki.tb, iki.hb)
    with iki.tb._get_connection() as c:  # SQLite'ın kendisi silmeyi reddeder (G-Ç / kilit hatasının yerine)
        c.execute(
            "CREATE TRIGGER d252_dusur BEFORE DELETE ON sensor_samples BEGIN SELECT RAISE(ABORT, 'disk I/O error (aparat)'); END;"
        )
        c.commit()
    hata = None
    try:
        iki.tb.import_rows(_paket_satirlari(iki), True)
    except Exception as e:  # noqa: BLE001
        hata = e
    sonra = sayimlar(iki.tb, iki.hb)
    assert sonra["treatment_sessions"] <= iki.kaynak["treatment_sessions"] or sonra == once, (
        f"silme adımı düştü ama içe aktarma COMMIT edildi: eski + yeni seanslar yan yana ({once['treatment_sessions']} → "
        f"{sonra['treatment_sessions']}, paket {iki.kaynak['treatment_sessions']})"
    )
    assert hata is not None, "silme adımı düştü ama import_rows istisna YÜKSELTMEDİ (yutuldu)"
    assert sonra == once, f"geri alınmadı: önce {once} → sonra {sonra}"


def test_KRITIK_D252_uc_REPLACE_silme_DUSERSE_basari_DEMEZ_kayitlar_DEGISMEZ(iki):
    once = sayimlar(iki.tb, iki.hb)
    with iki.tb._get_connection() as c:
        c.execute(
            "CREATE TRIGGER d252_dusur BEFORE DELETE ON sensor_samples BEGIN SELECT RAISE(ABORT, 'disk I/O error (aparat)'); END;"
        )
        c.commit()
    (r,) = istekler(iki.api.app, [("POST", "/api/data/import", _govde(iki), None)])
    assert r.status_code >= 500, f"silme düştü ama yanıt {r.status_code}: {r.text[:200]}"
    assert "DEĞİŞMEDİ" in r.json().get("detail", ""), r.text[:300]
    assert sayimlar(iki.tb, iki.hb) == once


# ── P2u · ekleme dalında kilit hatası yutulmaz ────────────────────────────────────────────────────────────────────


def test_KRITIK_P2u_EKLEME_kilitliyken_hata_YUTULMAZ_basari_0_seans_DONMEZ(tmp_path, monkeypatch):
    from servers import api_server as api

    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia"], seans_basi=2)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")  # BOŞ hedef
    uclari_bagla(monkeypatch, tb, hb)
    kilitci = sqlite3.connect(str(tb.db_path), timeout=0.1)
    try:
        tb._baglantiyi_birak()  # içe aktarma iş parçacığı kendi bağlantısını açar; busy_timeout aşağıda kısaltılır
        gercek = tb._create_connection

        def _kisa(*a, **k):
            c = gercek(*a, **k)
            c.execute("PRAGMA busy_timeout=100")
            return c

        monkeypatch.setattr(tb, "_create_connection", _kisa)
        kilitci.execute("BEGIN IMMEDIATE")  # GERÇEK yazma kilidi (bakım / VACUUM / ikinci süreç)
        (r,) = istekler(
            api.app, [("POST", "/api/data/import", {"passphrase": PAROLA, "blob_b64": paket["data_b64"]}, None)]
        )
        kilitci.rollback()
        g = r.json()
        assert not (r.status_code == 200 and g.get("status") == "success"), (
            f"DB kilitliyken HİÇBİR satır yazılamadı ama yanıt 200 success döndü: {g.get('counts')}"
        )
        assert r.status_code == 503, f"{r.status_code} {r.text[:300]}"
        assert sayimlar(tb, hb)["treatment_sessions"] == 0
    finally:
        try:
            kilitci.close()
        except Exception:
            pass
        kapat(ta, ha, tb, hb)


def test_KARSIT_P2u_UNIQUE_cakismasi_HALA_birlestirilir_istisna_yok(iki):
    """Yalnız `IntegrityError` (aynı hasta / olay zaten var) birleştirme yoluna girer — eskisi gibi."""
    satirlar = _paket_satirlari(iki)
    iki.tb.import_rows(satirlar, False)
    hasta_once = sayimlar(iki.tb, iki.hb)["patients"]
    iki.tb.import_rows(satirlar, False)  # aynı paket: hasta satırları UNIQUE → MEVCUT kayda bağlanır
    assert sayimlar(iki.tb, iki.hb)["patients"] == hasta_once


# ── Y12 · yedekte olmayan hasta SİLİNMEZ, RAPORLANIR; metinler gerçeği söyler ─────────────────────────────────────


def test_KRITIK_Y12_yedekte_OLMAYAN_hasta_karti_KALIR_ve_yanitta_RAPORLANIR(iki):
    (r,) = istekler(iki.api.app, [("POST", "/api/data/import", _govde(iki), None)])
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert iki.hb.get_patient(iki.zeytin) is not None, "Y12 ihlali: yedekte olmayan hasta kartı SİLİNDİ"
    assert g.get("yedekte_olmayan_hasta") == 1, f"yedekte olmayan hasta yanıtta raporlanmadı: {g}"
    assert iki.zeytin in (g.get("yedekte_olmayan_hasta_kimlikleri") or []), g
    assert "seans" in (g.get("uyari") or "") and "silindi" in (g.get("uyari") or ""), (
        f"yanıt yedekte olmayan hastanın SEANS GEÇMİŞİNİN silindiğini söylemiyor: {g.get('uyari')!r}"
    )
    assert sayimlar(iki.tb, iki.hb)["treatment_sessions"] == iki.kaynak["treatment_sessions"]


def test_KRITIK_Y12_onaysiz_409_metni_hasta_kartlarinin_SILINMEDIGINI_soyler(iki):
    (r,) = istekler(iki.api.app, [("POST", "/api/data/import", _govde(iki, confirm=""), None)])
    assert r.status_code == 409
    d = r.json()["detail"]
    assert "hasta kayıtları) SİLER" not in d and "SİLİNMEZ" in d, f"409 metni gerçeği söylemiyor: {d!r}"


# ── Y111 · dolu cihazda REPLACE_ALL yalnız cihazın kendisinden, kayıtlı klinikte kimlikle ─────────────────────────


def test_KRITIK_Y111_DOLU_cihazda_REPLACE_ALL_cihaz_DISINDAN_403_hicbir_sey_degismez(iki):
    once = sayimlar(iki.tb, iki.hb)
    (r,) = istekler(
        iki.api.app,
        [("POST", "/api/data/import", _govde(iki), {"X-API-Key": "CIHAZ-TOKEN"})],
        client=("192.168.1.80", 52001),
    )
    assert r.status_code == 403, f"cihaz dışından REPLACE_ALL kabul edildi: {r.status_code} {r.text[:200]}"
    assert sayimlar(iki.tb, iki.hb) == once


def test_KARSIT_Y111_BOS_cihaza_ilk_ice_aktarma_cihaz_disindan_BUGUNKU_gibi(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import auth

    monkeypatch.setattr(auth, "check_token", lambda t: t == "CIHAZ-TOKEN")
    ta, ha = cihaz_kur(monkeypatch, tmp_path / "A")
    uclari_bagla(monkeypatch, ta, ha)
    doldur(ta, ha, ["Mia"], seans_basi=1)
    paket = disa_aktar(api.app)
    tb, hb = cihaz_kur(monkeypatch, tmp_path / "B")
    uclari_bagla(monkeypatch, tb, hb)
    try:
        (r,) = istekler(
            api.app,
            [
                (
                    "POST",
                    "/api/data/import",
                    {"passphrase": PAROLA, "blob_b64": paket["data_b64"]},
                    {"X-API-Key": "CIHAZ-TOKEN"},
                )
            ],
            client=("192.168.1.80", 52002),
        )
        assert r.status_code == 200, r.text[:300]
        assert sayimlar(tb, hb)["treatment_sessions"] == 1
    finally:
        kapat(ta, ha, tb, hb)


def test_KRITIK_Y111_kayitli_operatorlu_klinikte_DOLU_cihaza_REPLACE_ALL_KIMLIKSIZ_428_kimlikli_200(iki):
    app = iki.api.app
    r = istekler(
        app, [("POST", "/api/operators/enroll", {"email": AYSE, "display_name": "Dr. Ayşe", "pin": "123456"}, None)]
    )[0]
    assert r.status_code == 200, r.text[:200]
    jeton = istekler(app, [("POST", "/api/operators/verify", {"email": AYSE, "pin": "123456"}, None)])[0].json()[
        "operator_token"
    ]
    once = sayimlar(iki.tb, iki.hb)
    (r1,) = istekler(app, [("POST", "/api/data/import", _govde(iki), None)])
    assert r1.status_code == 428, f"kayıtlı operatörlü klinikte kimliksiz REPLACE_ALL: {r1.status_code} {r1.text[:200]}"
    assert sayimlar(iki.tb, iki.hb) == once
    (r2,) = istekler(app, [("POST", "/api/data/import", _govde(iki), {"X-PEMF-Operator": jeton})])
    assert r2.status_code == 200, r2.text[:300]
    with iki.tb._get_connection() as c:
        iz = c.execute(
            "SELECT operator_email, outcome FROM audit_events WHERE event_type = 'data.import' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert iz and (iz[0] or "").lower() == AYSE, f"REPLACE_ALL izi yetkilendiren hekimin adına değil: {iz}"
