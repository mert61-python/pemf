# -*- coding: utf-8 -*-
"""KP-3 C · backend yardımcı modülleri (2. grup) kapsanmayan kolları — her test bir DAVRANIŞ iddiası:

- `surum_uyumu`: kuraldaki sınır ayrıştırılamıyorsa karar VERİLMEZ (None) — eşleşen başka kural yoksa; ayrıştırılamayan sürüm → None.
- `source_crypto.read_password`: ortam değişkeni önce; yoksa gömülü parola modülü (boşluk kırpılır, boş parola modülü atlanır).
- `data_export.decrypt_bundle`: kısa başlık / gzip-JSON olmayan içerik / sözlük olmayan yük → ayrı, okunur `ExportError`.
- `platform_support`: adayın varlık denetimi patlarsa (geçersiz yol) o aday ATLANIR, sonraki bulunur.
- `agir_import.torch_isit`: torch içe aktarılamazsa False + yığın izli uyarı; tanılama ısıtılmadı der.
- `ses_kalitesi`: boş örnek → -inf; RMS dBFS doğru; numpy YOKKEN saf-Python yolu aynı sonucu verir.
- `ai_rapor_ogeleri`: NaN/inf sayı "—"; yüzde olmayan / aralık dışı olasılık yok sayılır; boş liste "—"; yalnız iç içe öğeli liste
  kayıt sayısıyla özetlenir; gizli / iç içe sözlük alanı rapora girmez; çözülemeyen tarih aynen; adsız / sözlük olmayan olasılık atlanır;
  atfı olmayan XAI özelliği listelenmez.
- `dongu_disi_yazim`: işçinin İÇİNDEN gelen kayıt kendini beklemeden koşar; yürütücü kapalıysa eşzamanlı yola düşer (bekleyen sayacı
  geri alınır); geç biten kaydın hatası günlüğe yazılır (iptal sessiz); boşaltma: işçi yoksa True, süre dolarsa False.
- `encrypted_import`: geçersiz arama kökü atlanır, `.pyenc` yoksa spec yok; kurulum bir kez — parola varsa bulucu eklenir.
- `estop_mandali`: önceki oturumun iç nedeni çift önek almaz; denetlenemeyen dosya söylenir; Sıfırla eşzamanlı yazar; bildirim kancası
  patlasa da yazım bildirimi fırlatmaz; iş parçacığı açılamazsa mandal satır içi yine diske yazılır.
- `ai_client`: bozuk zaman aşımı değeri içe aktarımı düşürmez (180 sn); yüklenen dosya adı + içeriği servise gider; girdi yoksa hata.
- `image_domain`: gri (2B) görüntü GRAYSCALE / termalde AKROMATİK; boya maskesi boşsa H&E ölçütleri 0; boş girdi UNKNOWN; termal hesap
  patlarsa doğrulama "unknown" + uyarı (fırlatmaz); termal tablo yarışında kilidi alan, kazananın tablosunu kullanır.

Sahte EN ALT katta: modül öznitelikleri (`time`/`threading`/`_post_async`/`_isci`), `sys.modules` (numpy / parola modülü), dosya sistemi tmp.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import gzip
import importlib.util
import json
import logging
import math
import sys
import threading
import types
import wave
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]


# ── surum_uyumu ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ayristirilamayan_kural_siniri_karar_vermez_eslesen_kural_kazanir():
    from utils import surum_uyumu as su

    bozuk = {"clientMin": "bir.iki", "firmwareMin": "1.0.0"}
    karar, neden = su.uyumlu_mu("1.9.54", "2.3.0", [bozuk])
    assert karar is None and "ayrıştırılamayan" in neden
    iyi = {"clientMin": "1.9.0", "firmwareMin": "2.0.0"}
    assert su.uyumlu_mu("1.9.54", "2.3.0", [bozuk, iyi])[0] is True
    assert su._aralikta("surum-degil", "", "") is None


# ── source_crypto ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_kaynak_parolasi_ortam_once_sonra_gomulu_modul(monkeypatch):
    from utils.source_crypto import read_password

    bos = types.ModuleType("_static_password")
    bos.SOURCE_PASSWORD = "   "
    gomulu = types.ModuleType("build_tools._static_password")
    gomulu.SOURCE_PASSWORD = "  gomulu-parola  "
    monkeypatch.setitem(sys.modules, "_static_password", bos)
    monkeypatch.setitem(sys.modules, "build_tools._static_password", gomulu)
    monkeypatch.setenv("PEMF_SOURCE_KEY", "x")
    monkeypatch.delenv("PEMF_SOURCE_KEY")
    assert read_password() == "gomulu-parola", "boş parola modülü atlanmadı / boşluk kırpılmadı"
    monkeypatch.setenv("PEMF_SOURCE_KEY", "  ortam-parolasi ")
    assert read_password() == "ortam-parolasi"


# ── data_export ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_yedek_paketi_bozuk_baslik_icerik_ve_bicim_ayri_hatalar():
    from cryptography.fernet import Fernet
    from utils import ceviri
    from utils import data_export as de

    with pytest.raises(de.ExportError) as e:
        de.decrypt_bundle(de.MAGIC + b"kisa", "parola")
    assert str(e.value) == ceviri.t("yedek.dosya.bozukBaslik")
    tuz = b"\x01" * de.SALT_LEN
    anahtar = Fernet(de._derive_key("parola", tuz))
    with pytest.raises(de.ExportError) as e:
        de.decrypt_bundle(de.MAGIC + tuz + anahtar.encrypt(b"gzip-degil"), "parola")
    assert str(e.value) == ceviri.t("yedek.dosya.icerikOkunamadi")
    with pytest.raises(de.ExportError) as e:
        de.decrypt_bundle(de.MAGIC + tuz + anahtar.encrypt(gzip.compress(json.dumps([1, 2]).encode())), "parola")
    assert str(e.value) == ceviri.t("yedek.dosya.icerikBicim")


# ── platform_support ──────────────────────────────────────────────────────────────────────────────────────────────────
class _ErisilemeyenAday:
    """Varlık denetimi erişim reddiyle patlayan aday (ör. ACL'si kilitli paket dizini) — `Path.exists` bunu YUTMAZ."""

    def __init__(self, *a):
        pass

    def __truediv__(self, ad):
        return self

    def exists(self):
        raise PermissionError(13, "Erişim engellendi")


def test_varlik_denetimi_patlayan_aday_atlanir(monkeypatch, tmp_path):
    from utils import platform_support as ps

    (tmp_path / "mosquitto.conf").write_text("x")
    gercek_path = ps.Path
    monkeypatch.setattr(ps, "Path", lambda d: _ErisilemeyenAday() if str(d) == "kilitli" else gercek_path(d))
    assert ps.find_bundled_file("mosquitto.conf", ["kilitli", tmp_path]) == tmp_path / "mosquitto.conf"
    monkeypatch.setattr(ps, "Path", gercek_path)
    ikili = tmp_path / ps.binary_name("kp3-arac-olmayan")
    ikili.write_text("x")
    bulunan = ps.find_executable(
        "kp3-arac-olmayan", bundle_dirs=[], extra=[_ErisilemeyenAday(), ikili], prefer_system=False
    )
    assert bulunan == ikili


# ── agir_import ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_torch_isitilamazsa_false_ve_yigin_izli_uyari(monkeypatch, caplog):
    from utils import agir_import as ai_mod

    monkeypatch.setattr(ai_mod, "_isitildi", False)

    def _yok(yol):
        raise ImportError(f"{yol} kurulu değil")

    monkeypatch.setattr(ai_mod, "agir_import", _yok)
    with caplog.at_level(logging.WARNING, logger=ai_mod.logger.name):
        assert ai_mod.torch_isit() is False
    kayit = [r for r in caplog.records if "torch ısıtılamadı" in r.getMessage()]
    assert kayit and kayit[0].exc_info is not None, "uyarı yığın izi taşımıyor (teşhis körlüğü)"
    assert ai_mod.kilit_durumu() == {"isitildi": False, "bekleme_sn": ai_mod._KILIT_BEKLEME_SN}


# ── ses_kalitesi ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _wav(yol: Path, ornekler: list[int]) -> str:
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(np.asarray(ornekler, dtype="<i2").tobytes())
    return str(yol)


def test_rms_dbfs_bos_ve_deger_numpysiz_yol_ayni(monkeypatch, tmp_path):
    from utils import ses_kalitesi as sk

    assert sk.rms_dbfs([]) == float("-inf")
    assert sk.rms_dbfs([0.5, -0.5]) == pytest.approx(20 * math.log10(0.5))
    yol = _wav(tmp_path / "s.wav", [16384, -16384] * 50)
    numpyli = sk.wav_rms_dbfs(yol)
    monkeypatch.setitem(sys.modules, "numpy", None)
    assert sk.wav_rms_dbfs(yol) == pytest.approx(numpyli)
    assert numpyli == pytest.approx(20 * math.log10(0.5))


# ── ai_rapor_ogeleri ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_rapor_ogeleri_sinir_degerleri():
    from utils import ai_rapor_ogeleri as ro
    from utils import ceviri

    assert ro._sayi(float("nan")) == "—" and ro._sayi(float("inf")) == "—"
    assert ro._yuzde("yuzde") is None and ro._yuzde(float("nan")) is None
    assert ro._yuzde(250) is None, "aralık dışı olasılık yüzde sayıldı"
    assert ro._metne_cevir([]) == "—"
    assert ro._metne_cevir([{"a": 1}, [2]]) == ceviri.t("ai.rapor.kayit", count=2)
    gizli = next(iter(ro.IC_ALANLAR))
    assert ro._metne_cevir({gizli: "sır", "ic": {"x": 1}}) == "—", "gizli / iç içe alan rapora girdi"
    assert ro._tarih("dün akşam") == "dün akşam"
    sonuc = ro._olasi_sonuclar(["metin", {"probability": 0.9}, {"disease": "Konjonktivit", "probability": 0.7}])
    assert len(sonuc) == 1 and "Konjonktivit" in sonuc[0]
    assert ro._etkileyen_belirtiler({"top_features": [{"feature": "ates"}]}) == []


# ── dongu_disi_yazim ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_iscinin_icinden_gelen_kayit_kendini_beklemez():
    from utils import dongu_disi_yazim as ddy

    def ic():
        return threading.current_thread().name

    def dis():
        return ddy.sirada_calistir(ic, bekleme_sn=5.0)

    assert ddy.bosalt(10.0) is True  # önceki testlerin kuyruğu boşalsın (birikim varsa dış çağrı hiç beklemez)
    ad = ddy.sirada_calistir(dis, bekleme_sn=5.0)
    assert ad is not None and ad.startswith("pemf-kayit-yazim"), "işçi kendi kuyruğunu bekledi (kilitlenme / None)"


def test_yurutucu_kapaliysa_eszamanli_yola_duser_sayac_geri_alinir(monkeypatch):
    from utils import dongu_disi_yazim as ddy

    kapali = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    kapali.shutdown()
    monkeypatch.setattr(ddy, "_isci", lambda: kapali)
    once = ddy._bekleyen
    assert ddy.sirada_calistir(lambda a, b=0: a + b, 2, b=3) == 5
    assert ddy._bekleyen == once, "başarısız gönderimde bekleyen sayacı geri alınmadı"


def test_gec_biten_kayit_hatasi_gunluge_iptal_sessiz(caplog):
    from utils import dongu_disi_yazim as ddy

    bitti = ddy._gec_hata_gunlugu("seans-kapanisi")
    iptal = concurrent.futures.Future()
    iptal.cancel()
    hatali = concurrent.futures.Future()
    hatali.set_exception(OSError("disk dolu"))
    with caplog.at_level(logging.ERROR, logger=ddy._logger.name):
        bitti(iptal)
        assert not caplog.records, "iptal edilen kayıt hata gibi günlüğe yazıldı"
        bitti(hatali)
    assert any("seans-kapanisi" in r.getMessage() and "disk dolu" in r.getMessage() for r in caplog.records)


def test_bosalt_isci_yoksa_true_sure_dolarsa_false(monkeypatch):
    from utils import dongu_disi_yazim as ddy

    monkeypatch.setattr(ddy, "_yurutucu", None)
    assert ddy.bosalt(0.01) is True
    mesgul = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    birak = threading.Event()
    mesgul.submit(birak.wait, 5)
    monkeypatch.setattr(ddy, "_yurutucu", mesgul)
    try:
        assert ddy.bosalt(0.05) is False
    finally:
        birak.set()
        mesgul.shutdown(wait=True)


# ── encrypted_import ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_sifreli_bulucu_gecersiz_koku_atlar_kurulum_bir_kez(monkeypatch, tmp_path):
    from utils import encrypted_import as ei

    bulucu = ei.EncryptedFinder("parola")
    assert bulucu.find_spec("pkg.kp3_yok", path=[None, str(tmp_path)]) is None
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(ei, "_installed", False)
    monkeypatch.setattr(ei, "_password", lambda: "parola")
    assert ei.install() is True
    assert isinstance(sys.meta_path[-1], ei.EncryptedFinder) and sys.meta_path[-1].password == "parola"
    uzunluk = len(sys.meta_path)
    assert ei.install() is True and len(sys.meta_path) == uzunluk, "ikinci kurulum bulucuyu yeniden ekledi"


# ── estop_mandali ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_onceki_oturum_ic_nedeni_cift_onek_almaz(tmp_path):
    from utils import estop_mandali as em

    yol = tmp_path / "estop_mandal.json"
    yol.write_text(json.dumps({"aktif": True, "neden": f"{em.ONCEKI_OTURUM_NEDENI}:asiri_akim"}), encoding="utf-8")
    d = em.kalicilik_kur(yol)
    assert d["aktif"] is True
    assert em._durum["neden"] == f"{em.ONCEKI_OTURUM_NEDENI}:asiri_akim", "önek her yeniden başlatmada çoğaldı"


def test_denetlenemeyen_mandal_dosyasi_soylenir():
    from utils import estop_mandali as em

    class _Patlayan:
        def is_dir(self):
            raise OSError("ağ sürücüsü yanıt vermiyor")

    assert em._yazim_yoklamasi(_Patlayan()) == "dosya denetlenemedi"


def test_sifirla_yazimi_eszamanli_kanca_patlasa_da_bildirim_firlatmaz(monkeypatch, tmp_path, caplog):
    from utils import estop_mandali as em

    yol = tmp_path / "m" / "estop_mandal.json"
    em.kalicilik_kur(yol)
    em.mandalla("kp3-test")
    assert em.diske_yaz() is True
    assert json.loads(yol.read_text(encoding="utf-8"))["aktif"] is True

    def _kanca(d):
        raise RuntimeError("ekran bildirimi düştü")

    monkeypatch.setattr(em, "_yazim_hatasi_kancasi", _kanca)
    with caplog.at_level(logging.WARNING, logger=em._log.name):
        em._yazim_hatasini_bildir({"yazilamadi": True})
    assert any("bildirimi yapilamadi" in r.getMessage() for r in caplog.records)


def test_is_parcacigi_acilamazsa_mandal_satir_ici_diske_yazilir(monkeypatch, tmp_path):
    from utils import estop_mandali as em

    yol = tmp_path / "estop_mandal.json"
    em.kalicilik_kur(yol)
    em.mandalla("kp3-test")

    class _AcilmayanIs:
        def __init__(self, *a, **k):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(em, "threading", types.SimpleNamespace(Thread=_AcilmayanIs))
    em.diske_yaz_arka_planda()
    assert json.loads(yol.read_text(encoding="utf-8"))["aktif"] is True, (
        "iş parçacığı açılamayınca mandal diske yazılmadı"
    )


# ── ai_client ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_bozuk_ai_zaman_asimi_iceri_aktarimi_dusurmez(monkeypatch, caplog):
    monkeypatch.setenv("PEMF_AI_SERVICE_TIMEOUT", "yuzseksen")
    spec = importlib.util.spec_from_file_location("kp3_ai_client_kopya", KOK / "apps/backend/servers/ai_client.py")
    kopya = importlib.util.module_from_spec(spec)
    with caplog.at_level(logging.WARNING):
        spec.loader.exec_module(kopya)
    assert kopya._TIMEOUT == 180.0
    assert any("PEMF_AI_SERVICE_TIMEOUT" in r.getMessage() for r in caplog.records)


def test_yuklenen_dosya_servise_gider_girdi_yoksa_hata(monkeypatch):
    from servers import ai_client as ac

    giden: list = []

    async def _post(url, **kw):
        giden.append((url, kw))
        return {"ok": True}

    monkeypatch.setattr(ac, "_post_async", _post)

    class _Yukleme:
        filename = "kedi.jpg"

        async def read(self):
            return b"jpeg-bayt"

    class _Adsiz:
        filename = None

        async def read(self):
            return b"ham"

    assert asyncio.run(ac.delegate_infer("cat_organ", file=_Yukleme(), data={"a": 1, "b": None})) == {"ok": True}
    assert giden[-1][1] == {"files": {"file": ("kedi.jpg", b"jpeg-bayt")}, "data": {"a": "1"}}
    asyncio.run(ac.delegate_infer("cat_organ", file=_Adsiz()))
    assert giden[-1][1]["files"]["file"] == ("input.bin", b"ham")
    with pytest.raises(ValueError):
        asyncio.run(ac.delegate_infer("cat_organ"))


# ── image_domain ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_gri_bos_ve_boyasiz_goruntu_kollari():
    from utils import image_domain as idm

    gri = np.full((40, 40), 128, dtype=np.uint8)
    assert idm.analyze(gri) == (idm.GRAYSCALE, {"achromatic_ratio": 1.0, "stain_ratio": 0.0})
    assert idm.termal_analiz(None) == (idm.UNKNOWN, {})
    assert idm.termal_analiz(gri)[0] == idm.TERMAL_AKROMATIK
    assert idm.scratch_analizi(np.zeros((0, 0), dtype=np.uint8)) == (idm.UNKNOWN, {})
    bos_maske = np.zeros((4, 4), dtype=bool)
    assert idm._he_yapisi(np.zeros((4, 4, 3), np.uint8), np.zeros((4, 4)), bos_maske) == {
        "iki_boya": 0.0,
        "doku": 0.0,
        "bulanik_oran": 0.0,
    }


def test_termal_hesap_patlarsa_dogrulama_firlatmaz(monkeypatch, caplog):
    from utils import image_domain as idm

    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "1")

    def _patla(img):
        raise MemoryError("ölçek tablosu ayrılamadı")

    monkeypatch.setattr(idm, "termal_analiz", _patla)
    with caplog.at_level(logging.WARNING, logger=idm.logger.name):
        d = idm.termal_girdi_dogrulamasi(np.zeros((8, 8, 3), np.uint8))
    assert d["durum"] == idm.UNKNOWN and d["dogrulandi"] is False and d["uyari"]
    assert any("hesaplanamadı" in r.getMessage() for r in caplog.records)


def test_termal_tablo_yarisinda_kazananin_tablosu_kullanilir(monkeypatch):
    from utils import image_domain as idm

    kazanan = {"jet": "baska-is-parcaciginin-tablosu"}

    class _YarisanKilit:
        def __enter__(self):
            idm._TERMAL_TABLO = kazanan  # kilidi beklerken diğer iş parçacığı tabloyu kurdu
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(idm, "_TERMAL_TABLO", None)
    monkeypatch.setattr(idm, "_TERMAL_KILIT", _YarisanKilit())
    assert idm._termal_tablosu() is kazanan
