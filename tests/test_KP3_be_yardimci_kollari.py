# -*- coding: utf-8 -*-
"""KP-3 C · backend yardımcı modüllerinin kapsanmayan kolları — her test bir DAVRANIŞ iddiası:

- `simple_signal`: çağrılamaz geri çağırım reddedilir; `disconnect()` (argümansız) hepsini, `disconnect(cb)` yalnız onu söker, bilinmeyeni
  sessizce yok sayar; bir dinleyicinin istisnası DİĞERLERİNİ durdurmaz (günlüğe yazılır).
- `session_state`: `snapshot()` KOPYA döner (okuyucu küresel seansı bozamaz); `is_active()` bayrağı okur.
- `operator_tokens`: boş e-postaya jeton YOK; süresi dolan jeton yeni üretimde bellekten ATILIR (sınır `son + TTL <= şimdi`).
- `ai_approval`: 3×TTL'den eski öneriler yeni öneri açılınca budanır; tüketilMEMİŞ onay "geri verilemez".
- `ai_kapi_metni`: bilinmeyen modalite AYNEN adlandırılır; sözlük olmayan termal doğrulama girdisi AYNEN döner.
- `dongu_guvenligi`: logging da çökerse son çare stderr'e yazılır; `%` biçimi bozuksa mesaj + argümanlar ham basılır (fırlatmaz).
- `profil`: başlıkları okunamayan istek → profil YOK (süzgeç uygulanmaz, istisna sızmaz).
- `seans_durum`: tanınmayan "Ad N" AI Pro hedefi AYNEN gösterilir.
- `db_hatalari`: sqlcipher bağlayıcısı YOKKEN (düz-metin kurulum) hata sınıfları yalnız sqlite3'tür.
- `gizli_surec`: Windows dışı → bayrak 0; `baslat(ayrik=True)` konsolsuz + AYRIK bayraklarla Popen'a gider, çağıranın bayrağı ezilmez.
- `panel_yayin`: `utils.ceviri` olmayan GPU imajında panel adı ham anahtardır; `None` panel kodlayıcıya HİÇ verilmez.
- `runtime_guards`: dondurulmuş derlemede ultralytics gereksinim denetimi KAPATILIR; kapı yarım kapalıysa "etkin değil" der.
- `path_utils.resource_path`: kaynak kökte yoksa `pemf_gui/` altındaki yedeğe düşer.

Sahte EN ALT katta: saat (`time` modül özniteliği), `subprocess` (modül özniteliği), istek başlıkları, logger, `utils.ceviri` içe aktarımı.
"""

from __future__ import annotations

import importlib.util
import logging
import sqlite3
import sys
import types
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


# ── simple_signal ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sinyal_cagrilamaz_reddedilir_ve_disconnect_kollari(caplog):
    from utils.simple_signal import SimpleSignal

    s = SimpleSignal()
    with pytest.raises(TypeError):
        s.connect("geri-cagirim-degil")
    gelen: list = []

    def a(x):
        gelen.append(("a", x))

    def b(x):
        gelen.append(("b", x))

    def bozuk(x):
        raise RuntimeError("dinleyici patladı")

    s.connect(bozuk)
    s.connect(a)
    s.connect(b)
    with caplog.at_level(logging.ERROR, logger="utils.simple_signal"):
        s.emit(1)
    assert gelen == [("a", 1), ("b", 1)], "bozuk dinleyici sonrakileri durdurdu"
    assert any("Signal callback failed" in r.getMessage() for r in caplog.records)
    s.disconnect(a)
    s.disconnect(lambda x: None)  # hiç bağlanmamış → sessiz
    s.emit(2)
    assert gelen[-1] == ("b", 2) and ("a", 2) not in gelen
    s.disconnect()
    s.emit(3)
    assert ("b", 3) not in gelen, "argümansız disconnect dinleyicileri sökmedi"


# ── session_state ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_seans_durumu_kopya_doner_ve_aktiflik_okunur(monkeypatch):
    from servers import session_state as ss

    monkeypatch.setitem(ss._active_session, "is_active", True)
    monkeypatch.setitem(ss._active_session, "patient", "Pamuk")
    kopya = ss.snapshot()
    assert kopya["patient"] == "Pamuk" and ss.is_active() is True
    kopya["patient"] = "BOZULDU"
    kopya["is_active"] = False
    assert ss._active_session["patient"] == "Pamuk", "snapshot küresel seansı paylaştı"
    assert ss.is_active() is True
    monkeypatch.setitem(ss._active_session, "is_active", False)
    assert ss.is_active() is False


# ── operator_tokens ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_operator_jetonu_bos_eposta_ve_suresi_dolan_budanir(monkeypatch):
    from servers import operator_tokens as ot

    saat = [1_000_000.0]
    monkeypatch.setattr(ot, "time", types.SimpleNamespace(time=lambda: saat[0]))
    ot.temizle_hepsi()
    try:
        with pytest.raises(ValueError):
            ot.uret("   ")
        eski = ot.uret("vet@ornek.test")
        saat[0] += ot.TTL_SANIYE  # tam sınır: son + TTL <= şimdi → süresi doldu
        yeni = ot.uret("diger@ornek.test")
        assert eski not in ot._jetonlar, "süresi dolan jeton yeni üretimde bellekten atılmadı"
        assert ot.cozumle(yeni) == "diger@ornek.test"
    finally:
        ot.temizle_hepsi()


# ── ai_approval ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ai_onayi_eski_oneriler_budanir_tuketilmemis_geri_verilmez(monkeypatch):
    from servers import ai_approval as aa

    saat = [5_000_000.0]
    monkeypatch.setattr(aa, "time", types.SimpleNamespace(time=lambda: saat[0]))
    aa.clear()
    try:
        eski = aa.create("cat_organ", {"frekans": 10})["id"]
        assert aa.geri_ver(eski) is False, "tüketilmemiş (bekleyen) öneri 'geri verildi'"
        assert aa.get(eski)["status"] == aa.PENDING
        saat[0] += aa.TTL_S * 3 + 1
        yeni = aa.create("cat_organ", {"frekans": 12})["id"]
        assert aa.get(eski) is None, "3×TTL'den eski öneri budanmadı"
        assert aa.get(yeni) is not None
    finally:
        aa.clear()


# ── ai_kapi_metni ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_kapi_metni_bilinmeyen_modalite_ve_sozluk_olmayan_girdi_aynen():
    from servers import ai_kapi_metni as km

    assert km.modalite_adi("hiperspektral") == "hiperspektral"
    assert km.termal_dogrulama_cevir(None) is None
    assert km.termal_dogrulama_cevir("ham") == "ham"


# ── dongu_guvenligi ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_dongu_hatasi_logging_coktugunde_bozuk_bicim_ham_basilir(capfd):
    from utils.dongu_guvenligi import dongu_hatasini_bildir

    class _CokenLogger:
        def log(self, *a, **k):
            raise OSError("günlük diski dolu")

    try:
        1 / 0
    except ZeroDivisionError:
        kanal = dongu_hatasini_bildir("oran %d", "yuzde-degil", logger=_CokenLogger())
    assert kanal == "stderr"
    err = capfd.readouterr().err
    assert "[DONGU HATASI] oran %d ('yuzde-degil',)  (logging BASARISIZ)" in err
    assert "ZeroDivisionError" in err, "son çare kanalı yığın izini basmadı"


# ── profil ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_basliklari_okunamayan_istek_profilsiz_sayilir():
    from utils.profil import istek_profili

    class _BozukIstek:
        @property
        def headers(self):
            raise RuntimeError("başlıklar ayrıştırılamadı")

    assert istek_profili(_BozukIstek()) is None


# ── seans_durum ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_taninmayan_numarali_ai_pro_hedefi_aynen_gosterilir():
    from utils.seans_durum import AI_PRO_ONEK, mod_etiketi

    assert mod_etiketi(f"{AI_PRO_ONEK}YeniModel · Bilinmeyen 3") == f"{AI_PRO_ONEK}YeniModel · Bilinmeyen 3"


# ── db_hatalari ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sqlcipher_yokken_db_hata_siniflari_yalniz_sqlite3(monkeypatch):
    from database import sqlcipher_util

    monkeypatch.setattr(sqlcipher_util, "import_sqlcipher", lambda: None)
    spec = importlib.util.spec_from_file_location("kp3_db_hatalari_kopya", KOK / "apps/backend/database/db_hatalari.py")
    kopya = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kopya)  # sys.modules'a KAYDEDİLMEZ — ürünün modülü etkilenmez
    assert kopya._DB_OPERATIONAL is sqlite3.OperationalError
    assert kopya._DB_ERROR is sqlite3.Error
    assert kopya._DB_INTEGRITY is sqlite3.IntegrityError
    with pytest.raises(kopya._DB_OPERATIONAL):
        sqlite3.connect(":memory:").execute("SELECT * FROM olmayan_tablo")


# ── gizli_surec ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_gizli_surec_windows_disi_bayraksiz_ve_ayrik_baslatma(monkeypatch):
    from utils import gizli_surec as gs

    cagri: list = []
    monkeypatch.setattr(
        gs, "subprocess", types.SimpleNamespace(Popen=lambda args, **k: cagri.append((args, k)) or "surec")
    )
    monkeypatch.setattr(gs, "os", types.SimpleNamespace(name="nt"))
    assert gs.baslat(["arac.exe"], ayrik=True) == "surec"
    assert cagri[-1] == (
        ["arac.exe"],
        {"creationflags": gs.CREATE_NO_WINDOW | gs.DETACHED_PROCESS | gs.CREATE_NEW_PROCESS_GROUP},
    )
    gs.baslat(["arac.exe"], creationflags=0x10)
    assert cagri[-1][1] == {"creationflags": 0x10}, "çağıranın bayrağı ezildi"
    monkeypatch.setattr(gs, "os", types.SimpleNamespace(name="posix"))
    assert gs.bayraklar(ayrik=True) == 0
    gs.baslat(["arac"])
    assert cagri[-1][1] == {"creationflags": 0}


# ── panel_yayin ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ceviri_olmayan_gpu_imajinda_panel_adi_ham_anahtar_ve_bos_panel_kodlanmaz(monkeypatch):
    import utils as utils_paketi
    from utils import panel_yayin as py_

    monkeypatch.delattr(utils_paketi, "ceviri", raising=False)
    monkeypatch.setitem(sys.modules, "utils.ceviri", None)
    kodlanan: list = []

    def kodlayici(img):
        kodlanan.append(img)
        return b"jpeg", {"image_w": 2, "image_h": 1}

    anahtar = next(iter(py_.PANEL_ADLARI))
    cikti = py_.panelleri_yayina_hazirla({anahtar: "goruntu", "bos_panel": None}, kodlayici)
    assert [c["k"] for c in cikti] == [anahtar]
    assert cikti[0]["ad"] == anahtar, "çevirisiz imajda panel adı ham anahtar değil"
    assert kodlanan == ["goruntu"], "None panel kodlayıcıya verildi"


# ── runtime_guards ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_dondurulmus_derlemede_gereksinim_denetimi_kapanir_yarim_kapi_etkin_degil(monkeypatch):
    from utils import runtime_guards as rg

    monkeypatch.setenv("YOLO_AUTOINSTALL", "true")
    monkeypatch.setenv("ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS", "0")
    monkeypatch.setattr(rg, "_frozen_mu", lambda: True)
    assert rg.kurulum_yasagi_etkin_mi() is False, "YOLO_AUTOINSTALL açıkken kapı etkin sayıldı"
    rg.pip_kurulumunu_yasakla()
    import os

    assert os.environ["ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS"] == "1"
    assert rg.kurulum_yasagi_etkin_mi() is True
    monkeypatch.setenv("ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS", "0")
    assert rg.kurulum_yasagi_etkin_mi() is False, "dondurulmuş derlemede yarım kapalı kapı etkin sayıldı"


# ── path_utils.resource_path ──────────────────────────────────────────────────────────────────────────────────────────
def test_kaynak_kokte_yoksa_pemf_gui_yedegine_duser(monkeypatch, tmp_path):
    from utils.path_utils import resource_path

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    yedek = tmp_path / "pemf_gui" / "resources" / "icons" / "kalp.ico"
    yedek.parent.mkdir(parents=True)
    yedek.write_bytes(b"ico")
    assert Path(resource_path("resources/icons/kalp.ico")) == yedek
    assert Path(resource_path("resources/icons/yok.ico")) == tmp_path / "resources" / "icons" / "yok.ico"
    (tmp_path / "resources" / "icons").mkdir(parents=True)
    (tmp_path / "resources" / "icons" / "kalp.ico").write_bytes(b"asil")
    assert Path(resource_path("resources/icons/kalp.ico")) == tmp_path / "resources" / "icons" / "kalp.ico"
