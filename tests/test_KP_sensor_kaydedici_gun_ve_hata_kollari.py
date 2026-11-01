# -*- coding: utf-8 -*-
"""KP-1 · `servers/sensor_kaydedici.py` · sözleşmeler: gece yarısı geçişinde satır YENİ günün dosyasına gider ve önceki dosya kapanır (taban
süiti yalnız gece yarısını geçen koşuda bu satırları koşuyordu → sahte saatle kalıcı) · dosya sistemi hataları (listeleme, stat, silme, kapatma,
flush, okunamayan dosya) kaydı ve canlı akışı DURDURMAZ · CSV bütünlüğü (virgül / tırnak taşıyan alan alıntılanır) · arka plan kuyruğu
ASLA bloklamaz ve ASLA fırlatmaz (kuyruk dolu / kaydedici kurulamaz / beklenmeyen hata) · boşaltma beklemesi süre dolunca döner.

Gerçek veri kökü YOK: kayıt dizini `tmp_path`; dosya sistemi hataları `Path` / dosya tanıtıcısı düzeyinde (EN ALT kat) sahte; modülün
süreç geneli durumu (tekil kaydedici, arka plan kuyruğu / işçisi) her testte geri konur.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from servers import sensor_kaydedici as sk


@pytest.fixture
def k(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_SENSOR_LOG", "1")
    kd = sk.SensorKaydedici(dizin=tmp_path / "log", gun=14, mb=500)
    try:
        yield kd
    finally:
        kd.kapat()


def _epoch(y, a, g, s, d, sn):
    return datetime(y, a, g, s, d, sn).timestamp()


def test_KRITIK_gece_yarisi_gecisinde_satir_YENI_gunun_dosyasina_gider_eski_kapanir(k):
    assert k.kaydet(6, "sensors", {"object_temp": 36.5}, zaman=_epoch(2026, 11, 1, 23, 59, 59))
    eski_tanitici = k._dosya
    assert k.kaydet(6, "sensors", {"object_temp": 36.7}, zaman=_epoch(2026, 11, 2, 0, 0, 1))
    assert eski_tanitici.closed, "gün değişti ama önceki günün dosyası açık kaldı (tanıtıcı sızıntısı)"
    k.flush()
    d1 = (k.dizin / "sensor_2026-11-01.csv").read_text(encoding="utf-8").splitlines()
    d2 = (k.dizin / "sensor_2026-11-02.csv").read_text(encoding="utf-8").splitlines()
    assert d1[0] == d2[0] == ",".join(sk.SUTUNLAR), "yeni günün dosyası başlıksız"
    assert len(d1) == 2 and "36.5" in d1[1] and "2026-11-01T23:59:59" in d1[1]
    assert len(d2) == 2 and "36.7" in d2[1] and "2026-11-02T00:00:01" in d2[1], (
        "gece yarısından sonraki satır eski güne yazıldı"
    )


def test_gun_gecisinde_eski_dosya_KAPATILAMAZSA_yine_yeni_dosya_acilir(k):
    k.kaydet(1, "sensors", {"temperature": 1.0}, zaman=_epoch(2026, 11, 1, 23, 0, 0))
    gercek = k._dosya

    class _Patlayan:
        def close(self):
            gercek.close()
            raise OSError("ağ sürücüsü koptu")

    k._dosya = _Patlayan()
    assert k.kaydet(1, "sensors", {"temperature": 2.0}, zaman=_epoch(2026, 11, 2, 1, 0, 0)) is True
    k.flush()
    assert (k.dizin / "sensor_2026-11-02.csv").read_text(encoding="utf-8").count("\n") == 2


def test_kayit_dizini_cozucu_DUSERSE_ev_dizinine_duser(monkeypatch, tmp_path):
    import utils.path_utils as pu

    monkeypatch.delenv("PEMF_SENSOR_LOG_DIR", raising=False)
    monkeypatch.setattr(pu, "get_app_data_directory", lambda: (_ for _ in ()).throw(RuntimeError("kök yok")))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "ev"))
    assert sk._kayit_dizini() == tmp_path / "ev" / "pemf_sensor_log"


def test_okunamayan_dosya_basligi_BOS_satir_sonu_YOK_sayilir(tmp_path):
    (tmp_path / "dizin.csv").mkdir()  # dosya yerine DİZİN → open OSError
    assert sk.SensorKaydedici._ilk_satir(tmp_path / "dizin.csv") == ""
    assert sk.SensorKaydedici._satir_sonuyla_bitiyor(tmp_path / "yok.csv") is False


def test_CSV_butunlugu_virgul_ve_tirnak_tasiyan_alan_ALINTILANIR(k):
    k.kaydet(2, "status", {"sensors_ok": 'a,"b"', "temperature": 3.0}, zaman=_epoch(2026, 11, 1, 10, 0, 0))
    k.flush()
    import csv

    with open(k.dizin / "sensor_2026-11-01.csv", encoding="utf-8", newline="") as f:
        satirlar = list(csv.reader(f))
    assert len(satirlar[1]) == len(sk.SUTUNLAR), "alıntılanmayan virgül sütunları kaydırdı"
    assert satirlar[1][sk.SUTUNLAR.index("sensors_ok")] == 'a,"b"'


def test_temizlik_listeleme_ve_boyut_olcumu_DUSERSE_kayit_SURER(k, monkeypatch):
    k.kaydet(1, "sensors", {"temperature": 1.0}, zaman=_epoch(2026, 11, 1, 10, 0, 0))
    k.dizin = SimpleNamespace(glob=lambda d: (_ for _ in ()).throw(OSError("listelenemiyor")))
    k._temizle(datetime(2026, 11, 1))  # sessizce atlanır
    k.dizin = Path(k._dosya.name).parent
    eski = k.dizin / "sensor_2026-01-01.csv"  # gün sınırı dışı ama boyut ölçülemezse tavan adımı atlanır
    eski.write_text("z", encoding="utf-8")
    k.gun, k.mb = 3650, 0
    gercek_stat = Path.stat
    with monkeypatch.context() as m:
        m.setattr(
            Path,
            "stat",
            lambda self, *a, **kw: (
                (_ for _ in ()).throw(OSError("stat yok"))
                if self.name.startswith("sensor_")
                else gercek_stat(self, *a, **kw)
            ),
        )
        k._temizle(datetime(2026, 11, 1))  # boyut ölçülemedi → silme YOK, istisna YOK
    assert eski.exists() and (k.dizin / "sensor_2026-11-01.csv").exists(), "boyut ölçülemeden dosya silindi"


def test_gun_etiketi_COZULEMEYEN_dosya_saklamada_SILINMEZ_tavanda_silinemeyen_ATLANIR(k, monkeypatch):
    k.dizin.mkdir(parents=True)
    (k.dizin / "sensor_kopya.csv").write_text("x" * 10, encoding="utf-8")
    (k.dizin / "sensor_2026-09-01.csv").write_text("eski", encoding="utf-8")
    k.kaydet(1, "sensors", {"temperature": 1.0}, zaman=_epoch(2026, 11, 1, 10, 0, 0))  # gun=14 saklama
    kalan = {p.name for p in k.dizin.glob("sensor_*.csv")}
    assert "sensor_kopya.csv" in kalan, "gün etiketi çözülemeyen dosya saklama adımında silindi"
    assert "sensor_2026-09-01.csv" not in kalan, "14 günden eski dosya silinmedi"
    for g in ("2026-10-30", "2026-10-31"):
        (k.dizin / f"sensor_{g}.csv").write_text("y" * 2048, encoding="utf-8")
    k.mb = 0  # tavan 0 → en eskiden başlayarak siler
    gercek_unlink = Path.unlink
    denenen: list = []

    def _unlink(self, *a, **kw):
        denenen.append(self.name)
        if self.name == "sensor_2026-10-30.csv":
            raise PermissionError("kilitli")
        return gercek_unlink(self, *a, **kw)

    with monkeypatch.context() as m:
        m.setattr(Path, "unlink", _unlink)
        k._temizle(datetime(2026, 11, 1))
    kalan = {p.name for p in k.dizin.glob("sensor_*.csv")}
    assert "sensor_2026-10-30.csv" in kalan and "sensor_2026-10-31.csv" not in kalan, (
        "silinemeyen dosya tavan döngüsünü durdurdu"
    )
    # Windows açık dosyanın silinmesini zaten reddeder → sonuç değil DENEME ölçülür (Linux'ta aktif dosya gerçekten silinirdi)
    assert "sensor_2026-11-01.csv" not in denenen and "sensor_2026-11-01.csv" in kalan, (
        "tavan bugünün (aktif) dosyasını silmeyi denedi"
    )


def test_flush_ve_kapat_HATASI_yutulur(k, caplog):
    k.kaydet(1, "sensors", {"temperature": 1.0})
    gercek = k._dosya
    k._dosya = SimpleNamespace(
        flush=lambda: (_ for _ in ()).throw(OSError("disk dolu")),
        close=lambda: (_ for _ in ()).throw(OSError("disk dolu")),
    )
    with caplog.at_level(logging.DEBUG, logger=sk.logger.name):
        k.flush()
        k.kapat()
    assert k._dosya is None
    assert any("flush edilemedi" in r.getMessage() for r in caplog.records)
    gercek.close()


def test_hata_bildirimi_GONDERILEMEZSE_kayit_yolu_firlatmaz(k, monkeypatch, caplog):
    from servers import live_state

    monkeypatch.setattr(
        live_state, "_bildir", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("bildirim kuyruğu yok"))
    )
    k.dizin = Path(k.dizin) / "yok" / "\0gecersiz"  # mkdir düşer → kayıt hatası → bildirim denemesi
    with caplog.at_level(logging.DEBUG, logger=sk.logger.name):
        assert k.kaydet(1, "sensors", {"temperature": 1.0}) is False
    assert k.atilan == 1 and k.durum()["hata"] is True
    assert any("bildirimi gonderilemedi" in r.getMessage() for r in caplog.records)


@pytest.fixture
def arka(monkeypatch):
    """Arka plan kuyruğu / işçi / tekil kaydedici bu test için taze; testten sonra eskileri geri konur."""
    monkeypatch.setenv("PEMF_SENSOR_LOG", "1")
    monkeypatch.setattr(sk, "_arka_kuyruk", queue.Queue(maxsize=4))
    monkeypatch.setattr(sk, "_arka_is", None)
    monkeypatch.setattr(sk, "_kaydedici", None)
    return sk


def test_tekil_kaydedici_KURULAMAZSA_giris_noktasi_False_doner(arka, monkeypatch):
    monkeypatch.setattr(sk, "SensorKaydedici", lambda: (_ for _ in ()).throw(OSError("dizin yok")))
    assert sk.kaydet(1, "sensors", {"temperature": 1.0}) is False


def test_KRITIK_arka_isci_kayit_PATLASA_da_YASAR_hata_bildirilir(arka, monkeypatch):
    bildirilen: list = []
    monkeypatch.setattr(sk, "dongu_hatasini_bildir", lambda ileti, **kw: bildirilen.append(ileti))
    yazilan: list = []

    class _Kaydedici:
        def kaydet(self, bobin, msg_type, yuk, zaman=None):
            if yuk.get("patla"):
                raise OSError("disk asılı")
            yazilan.append(yuk["temperature"])
            return True

    monkeypatch.setattr(sk, "_kaydedici", _Kaydedici())
    assert sk.kaydet_arka_planda(1, "sensors", {"patla": True}) is True
    assert sk.kaydet_arka_planda(1, "sensors", {"temperature": 2.0}) is True
    assert sk._arka_kuyruk_bosalsin(5) is True
    assert bildirilen == ["sensor kaydi (arka plan) basarisiz"] and yazilan == [2.0], "patlayan satır işçiyi öldürdü"
    assert sk._arka_is.is_alive()


def test_KRITIK_kuyruk_DOLUYKEN_bloklamaz_atilan_sayilir_kaydedici_yoksa_da_firlatmaz(arka, monkeypatch):
    monkeypatch.setattr(sk, "_arka_kuyruk", queue.Queue(maxsize=1))
    monkeypatch.setattr(sk, "_arka_is", SimpleNamespace(is_alive=lambda: True))  # işçi "canlı" ama tüketmiyor
    sayac = SimpleNamespace(atilan=0)
    monkeypatch.setattr(sk, "_kaydedici", sayac)
    assert sk.kaydet_arka_planda(1, "sensors", {"temperature": 1.0}) is True
    t0 = time.monotonic()
    assert sk.kaydet_arka_planda(1, "sensors", {"temperature": 2.0}) is False
    assert time.monotonic() - t0 < 0.5 and sayac.atilan == 1, "dolu kuyrukta bloklandı ya da atılan sayılmadı"
    monkeypatch.setattr(sk, "kaydedici", lambda: (_ for _ in ()).throw(RuntimeError("kurulamadı")))
    assert sk.kaydet_arka_planda(1, "sensors", {"temperature": 3.0}) is False
    monkeypatch.setattr(
        sk, "_arka_kuyruk", SimpleNamespace(put_nowait=lambda *_: (_ for _ in ()).throw(RuntimeError("beklenmeyen")))
    )
    assert sk.kaydet_arka_planda(1, "sensors", {"temperature": 4.0}) is False


def test_bosaltma_beklemesi_SURE_dolunca_False_doner(arka, monkeypatch):
    q = queue.Queue()
    q.put(("tüketilmeyen",))
    monkeypatch.setattr(sk, "_arka_kuyruk", q)
    t0 = time.monotonic()
    assert sk._arka_kuyruk_bosalsin(0.05) is False
    assert time.monotonic() - t0 < 2.0
    assert threading.active_count() >= 1
