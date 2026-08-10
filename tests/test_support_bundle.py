# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DESTEK PAKETİ — teşhis, kişisel veri sızdırmadan (2026-08-09 denetimi, Tier 3).

ARIZA: saha teşhisi "telefonda operatöre ProgramData yolunu tarif etmek"ti. Log dosyaları 60 MB
ve **içlerinde hasta adı geçebiliyor** — yani "logu bana gönder" demek, kontrolsüz bir kişisel
veri aktarımı istemek demekti. Ayrıca aynı dizinde sır dosyası (`pemf_secrets.json`), SQLCipher
anahtarı ve kurtarma zarfı duruyor; panikleyen bir kullanıcının "klasörü zipleyip yollaması"
tüm klinik verisinin anahtarını göndermesi anlamına gelirdi.

Kilitlenen değişmezler:
  1) Cihazdaki GERÇEK hasta/sahip adları ve operatör e-postaları maskelenir (jenerik desen
     değil, o cihazın somut değerleri — asıl koruma budur).
  2) Sır dosyaları, veritabanları ve kurtarma zarfı pakete GİRMEZ.
  3) Paket ne alındığını/atlandığını ve kaç eşleşmenin maskelendiğini AÇIKÇA söyler.
  4) Backend çökmüşken de üretilebilir (HTTP'ye bağımlı değil).
"""

import io
import json
import os
import zipfile

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def kurulum(tmp_path, monkeypatch):
    """Gerçekçi bir veri kökü: log dizini + sır dosyaları + hasta kaydı."""
    kok = tmp_path / "PEMF_GUI"
    kok.mkdir()
    loglar = kok / "logs"
    loglar.mkdir()
    monkeypatch.setenv("PEMF_LOG_DIR", str(loglar))

    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(kok)
    with db._get_connection() as c:
        c.execute("INSERT INTO patients (name, owner_name) VALUES (?,?)", ("Pamuk Yildiz", "Ayse Demir"))
        c.execute(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, "
            "patient_name, operator_name, operator_email) VALUES (?,?,?,?,?,?)",
            ("2026-08-01", "10:00", "Manuel", "Pamuk Yildiz", "Dr. Mehmet Kaya", "mehmet@klinik.com"),
        )
        c.commit()

    (loglar / "backend_service.log").write_text(
        "INFO Seans basladi: hasta=Pamuk Yildiz operator=Dr. Mehmet Kaya\n"
        "INFO iletisim: mehmet@klinik.com\n"
        "INFO api_key=sk-canli-COK-GIZLI-DEGER\n"
        "INFO Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdef\n"
        "INFO sahibi=Ayse Demir\n"
        "INFO normal satir, maskelenmemeli\n",
        encoding="utf-8",
    )
    (loglar / "crash.log").write_text("Traceback ... hasta Pamuk Yildiz\n", encoding="utf-8")

    # Pakete ASLA girmemesi gerekenler — gerçek dosya adlarıyla.
    (loglar / "pemf_secrets.json").write_text('{"api_token":"CANLI-SIR"}', encoding="utf-8")
    (loglar / "hasta.db").write_bytes(b"SQLite format 3\x00GIZLI")
    (loglar / "kurtarma-zarfi.enc").write_bytes(b"ZARF")

    from database import treatment_history_db as thm

    monkeypatch.setattr(thm, "get_treatment_db", lambda _d: db)
    yield kok, db
    db.close_connections()


def _ac(veri):
    z = zipfile.ZipFile(io.BytesIO(veri))
    return z, {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()}


# ── maskeleme ───────────────────────────────────────────────────────────────


def test_KRITIK_gercek_hasta_adi_MASKELENIR(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    veri, _ozet = olustur(kok)
    _z, icerik = _ac(veri)
    hepsi = "\n".join(icerik.values())
    for pii in ("Pamuk Yildiz", "Ayse Demir", "Dr. Mehmet Kaya"):
        assert pii not in hepsi, f"gercek PII pakete sizdi: {pii}"
    assert "[PII]" in hepsi, "maskeleme hic calismamis"


def test_KRITIK_sir_ve_jeton_MASKELENIR(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    veri, _ = olustur(kok)
    _z, icerik = _ac(veri)
    hepsi = "\n".join(icerik.values())
    assert "sk-canli-COK-GIZLI-DEGER" not in hepsi, "API anahtari sizdi"
    assert "eyJhbGciOiJIUzI1NiJ9" not in hepsi, "Bearer jetonu sizdi"
    assert "mehmet@klinik.com" not in hepsi, "e-posta sizdi"


def test_maskeleme_NORMAL_satiri_bozmaz(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    _z, icerik = _ac(olustur(kok)[0])
    assert "normal satir, maskelenmemeli" in icerik["logs/backend_service.log"], (
        "maskeleme teshis bilgisini de yok etti"
    )


def test_DB_okunamazsa_paket_YINE_uretilir(tmp_path, monkeypatch):
    """PII listesi okunamıyorsa (bozuk DB) paket üretilmeye devam etmeli — teşhis tam da o an
    gerekir. Jenerik maskeleme devrede kalır."""
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()
    # SAHTE jeton; testin amacı maskeleyicinin bunu YAKALADIĞINI kanıtlamak. Sır tarayıcısının
    # da bulması aslında doğru davranış — muafiyet AYNI SATIRA yazılmalı (gitleaks kuralı).
    (tmp_path / "logs" / "a.log").write_text("token=ABCDEF123456\n", encoding="utf-8")  # gitleaks:allow
    from database import treatment_history_db as thm

    monkeypatch.setattr(thm, "get_treatment_db", lambda _d: (_ for _ in ()).throw(RuntimeError("bozuk DB")))
    from utils.support_bundle import olustur

    veri, ozet = olustur(tmp_path)
    _z, icerik = _ac(veri)
    assert "ABCDEF123456" not in "\n".join(icerik.values()), "jenerik maskeleme de calismamis"
    assert ozet["alinan_dosyalar"] == ["a.log"]


def test_KRITIK_maskeleme_ZAYIFLADIYSA_uyarir(tmp_path, monkeypatch):
    """Asıl koruma, cihazın GERÇEK hasta adlarını maskelemektir; o liste DB'den gelir. Şifreli
    DB açılamazsa (araç servis dışında çalıştırıldı) koruma sessizce zayıflar — ve paketi
    gönderen kişi bunu bilmez. Sessizce zayıflamış maskeleme, hiç maskelememekten kötüdür."""
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "a.log").write_text("hasta=Pamuk\n", encoding="utf-8")
    from database import treatment_history_db as thm

    monkeypatch.setattr(thm, "get_treatment_db", lambda _d: (_ for _ in ()).throw(RuntimeError("sifreli DB acilamadi")))
    from utils.support_bundle import olustur

    _veri, ozet = olustur(tmp_path)
    assert "UYARI" in ozet, "maskeleme zayifladi ama paket bunu SOYLEMIYOR"
    assert "HASTA ADI" in ozet["UYARI"]


def test_maskeleme_TAM_calisirken_uyarmaz(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    _veri, ozet = olustur(kok)
    assert "UYARI" not in ozet, "gereksiz uyari — operator gercek uyariyi ciddiye almaz"


# ── neyin girmediği ─────────────────────────────────────────────────────────


def test_KRITIK_sir_dosyasi_ve_DB_pakete_GIRMEZ(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    veri, ozet = olustur(kok)
    z, icerik = _ac(veri)
    adlar = " ".join(z.namelist())
    for yasak in ("pemf_secrets.json", "hasta.db", "kurtarma-zarfi.enc"):
        assert yasak not in adlar, f"YASAK dosya pakete girdi: {yasak}"
    assert "CANLI-SIR" not in "\n".join(icerik.values())
    assert set(ozet["atlanan_dosyalar"]) >= {"pemf_secrets.json", "hasta.db", "kurtarma-zarfi.enc"}


def test_paket_NE_yaptigini_soyler(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    _z, icerik = _ac(olustur(kok)[0])
    o = json.loads(icerik["OZET.json"])
    assert o["alinan_dosyalar"] and o["maskelenen_eslesme"] > 0
    assert o["atlanan_dosyalar"], "atlanan dosyalar bildirilmiyor"
    assert "maskeleme" in o["not"].lower()


def test_saglik_ozeti_SURUM_tasir(kurulum):
    from utils.support_bundle import olustur

    kok, _ = kurulum
    _z, icerik = _ac(olustur(kok)[0])
    s = json.loads(icerik["saglik.json"])
    assert s.get("app_version"), "destek paketi surumu hic tasimiyorsa teshis yine yok"
    assert "at_rest_encrypted" in s


def test_denetim_OZETI_var_ama_ICERIK_yok(kurulum):
    """Destek "3 kez toplu silme olmuş" bilgisini görmeli; kimin sildiğini görmek zorunda değil."""
    from utils.support_bundle import olustur

    kok, db = kurulum
    db.denetim_yaz("ai_log.delete_all", operator_email="gizli@klinik.com", scope="TUM_KLINIK")
    _z, icerik = _ac(olustur(kok)[0])
    d = json.loads(icerik["denetim_ozeti.json"])
    assert d.get("ai_log.delete_all") == 1
    assert "gizli@klinik.com" not in "\n".join(icerik.values()), "denetim izi kimligi pakete sizdi"


def test_log_kuyrugu_TAVANLI(kurulum):
    """60 MB'lık dosyanın tamamı gönderilmemeli."""
    from utils.support_bundle import olustur

    kok, _ = kurulum
    (kok / "logs" / "buyuk.log").write_text("X" * 200_000, encoding="utf-8")
    _z, icerik = _ac(olustur(kok, log_tavani=10_000)[0])
    assert len(icerik["logs/buyuk.log"]) <= 10_100


# ── HTTP ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(kurulum, monkeypatch):
    kok, db = kurulum
    from servers import api_server

    monkeypatch.setattr(api_server, "_app_data_dir", lambda: kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: db)
    return TestClient(api_server.app, client=("127.0.0.1", 51234))


def test_uc_paket_uretir(client):
    r = client.post("/api/support/bundle")
    assert r.status_code == 200, r.text[:300]
    g = r.json()
    assert g["filename"].endswith(".zip") and g["data_b64"]
    import base64

    z, icerik = _ac(base64.b64decode(g["data_b64"]))
    assert "OZET.json" in z.namelist()
    assert "Pamuk Yildiz" not in "\n".join(icerik.values())


def test_KRITIK_uc_LANdan_kimliksiz_REDDEDILIR():
    """Paket log ve sürüm bilgisi taşır; klinik ağındaki rastgele bir cihaz üretememeli."""
    from servers import api_server

    lan = TestClient(api_server.app, client=("192.168.1.77", 51234))
    assert lan.post("/api/support/bundle").status_code == 403


def test_paket_uretimi_DENETIM_izine_yazilir(client, kurulum):
    _kok, db = kurulum
    client.post("/api/support/bundle")
    assert "support.bundle" in [k["event_type"] for k in db.denetim_oku(20)]
