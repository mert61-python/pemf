# -*- coding: utf-8 -*-
"""2-F incelemesi §10 #7 (D5 · yardımcı E) — sensör telemetri kaydının yazım hatası GÖRÜNÜR (WARNING + operatöre tek bildirim + sağlık
ucu) ve çöken sürecin YARIM satırı yeni satırla BİRLEŞMEZ.

ÖLÇÜLEN KUSURLAR (HEAD 9c6d4505, sonda `_inceleme/E-7/kayit/sonda_HEAD.txt`):
  (1) yazılamaz kayıt klasöründe (GERÇEK işletim sistemi hatası: klasör yolunda bir DOSYA var) her satır `kaydet` → False, `atilan`
      artıyor ama günlükte YALNIZ DEBUG (üretim düzeyi INFO → hiçbir iz yok); operatöre bildirim yok; `durum()` hiçbir uçta yok
      (hiçbir uçta sensör kaydı yok — alan artık `/api/system/info`ta; sağlık ucu gzip eşiği altında kalsın diye orada değil) — araştırma telemetrisi kimseye söylenmeden duruyordu;
  (2) süreç satırın ortasında öldüyse (güç kesintisi / disk dolu) dosya satır sonu olmadan biter; sonraki açılışın ilk satırı yarım
      satırın SONUNA eklenip iki kaydı tek bozuk satırda birleştiriyordu (32 yerine 38 sütun).
Düzeltme: hata SERİSİNİN ilk satırında WARNING (istisna zinciriyle) + TEK iki dilli bildirim (`bildirim.sensorKaydiYazilamiyor`),
seri sürerken DEBUG, ilk başarılı yazım seriyi kapatır; `/api/system/info` `sensorKaydi` {acik, hata, sonHata, yazilan, atilan} (yol YOK;
yalnız yerel/LAN; kaydedici sağlık ucunda YARATILMAZ — kurucu veri kökünü mkdir eder); dosya satır sonu olmadan bitiyorsa ekleme
öncesi satır sonu (yarım satır olduğu gibi kalır).
Kurulum EN ALT katta: yazılamazlık GERÇEK dosya sistemi hatası; yarım satır dosyanın GERÇEK içeriği; uç süreç içi `TestClient`.
"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

YUK = {"object_temp": 23.4, "magnetic_field": 0.03, "mag_x": -0.1}
ENGEL = "engel_E7"


@pytest.fixture()
def sk(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_SENSOR_LOG_DIR", str(tmp_path / "sensor_log"))
    monkeypatch.setenv("PEMF_SENSOR_LOG", "1")
    monkeypatch.delenv("PEMF_SENSOR_LOG_DAYS", raising=False)
    monkeypatch.delenv("PEMF_SENSOR_LOG_MB", raising=False)
    import servers.sensor_kaydedici as m

    importlib.reload(m)
    yield m
    try:
        if m._kaydedici is not None:
            m._kaydedici.kapat()
    except Exception:
        pass


@pytest.fixture()
def bildirimler(monkeypatch):
    from servers import live_state

    alinan = []

    def _yakala(message, level="info", mesajlar=None):
        alinan.append(
            {"message": message, "level": level, "mesajlar": dict(live_state._BILDIRIM_MESAJLARI.get() or {})}
        )

    monkeypatch.setattr(live_state, "_push_notification", _yakala)
    return alinan


def _yazilamaz(tmp_path, k):
    """GERÇEK işletim sistemi hatası: kayıt klasörünün yolunda bir DOSYA var (mkdir / open düşer)."""
    engel = tmp_path / ENGEL
    engel.write_text("dosya, klasor degil", encoding="utf-8")
    k.kapat()
    k.dizin = engel / "sensor_log"


def _uyarilar(caplog):
    return [r for r in caplog.records if r.name == "servers.sensor_kaydedici" and r.levelno >= logging.WARNING]


def test_KRITIK_yazim_hatasi_SERI_basinda_WARNING_zincirli_ve_TEK_iki_dilli_bildirim(sk, tmp_path, caplog, bildirimler):
    """MUTASYON: hata yalnız DEBUG (HEAD) → KIRMIZI; bildirim yok → KIRMIZI; her satırda WARNING → KIRMIZI; seri kapanmaz → KIRMIZI."""
    from utils import ceviri

    k = sk.kaydedici()
    _yazilamaz(tmp_path, k)
    caplog.set_level(logging.DEBUG, logger="servers.sensor_kaydedici")
    assert [sk.kaydet(1, "sensors", YUK) for _ in range(3)] == [False] * 3, "aparat: yazılamaz klasörde satır yazıldı"
    uyarilar = _uyarilar(caplog)
    assert len(uyarilar) == 1, (
        f"yazım hatası serisi için TEK WARNING beklenir (0 = sessiz, >1 = her satırda): {[r.getMessage() for r in uyarilar]}"
    )
    assert uyarilar[0].exc_info and isinstance(uyarilar[0].exc_info[1], OSError), (
        "WARNING kök nedeni (istisna zinciri) taşımıyor"
    )
    assert len(bildirimler) == 1, f"operatöre TEK bildirim beklenir (0 = söylenmiyor, >1 = her satırda): {bildirimler}"
    b = bildirimler[0]
    assert b["level"] == "warning", b
    assert b["mesajlar"].get("tr") == ceviri.t("bildirim.sensorKaydiYazilamiyor", dil="tr"), b
    assert b["mesajlar"].get("en") == ceviri.t("bildirim.sensorKaydiYazilamiyor", dil="en"), b
    assert b["mesajlar"]["tr"] != b["mesajlar"]["en"] and "sensorKaydiYazilamiyor" not in b["mesajlar"]["en"], b
    assert ENGEL not in b["message"], "bildirim kayıt klasörünün yolunu taşıyor"
    d = k.durum()
    assert d["hata"] is True and d["son_hata"] and d["atilan"] == 3, f"durum hatayı göstermiyor: {d}"
    # İyileşme: ilk başarılı yazım seriyi kapatır.
    k.dizin = tmp_path / "sensor_log_ok"
    assert sk.kaydet(1, "sensors", YUK) is True
    assert k.durum()["hata"] is False, "başarılı yazımdan sonra hata serisi kapanmadı"
    # İkinci seri: yeniden TEK WARNING + TEK bildirim.
    _yazilamaz(tmp_path, k)
    assert sk.kaydet(1, "sensors", YUK) is False and sk.kaydet(1, "sensors", YUK) is False
    assert len(_uyarilar(caplog)) == 2 and len(bildirimler) == 2, (
        f"ikinci hata serisi bildirilmedi / fazla bildirildi: uyarı {len(_uyarilar(caplog))}, bildirim {len(bildirimler)}"
    )


@pytest.fixture()
def istemci():
    from servers import api_server

    def _yap(basliklar=None):
        return TestClient(api_server.app, client=("127.0.0.1", 51307)).get("/api/system/info", headers=basliklar or {})

    return _yap


def test_KRITIK_saglik_ucu_sensorKaydi_HATAYI_tasir_YOL_tasimaz_uzaga_vermez(sk, tmp_path, istemci, bildirimler):
    k = sk.kaydedici()
    _yazilamaz(tmp_path, k)
    assert sk.kaydet(2, "sensors", YUK) is False
    r = istemci()
    assert r.status_code == 200, r.text[:300]
    alan = r.json().get("sensorKaydi")
    assert isinstance(alan, dict), f"/api/system/info sensör kaydı durumunu taşımıyor: {sorted(r.json())}"
    assert alan["hata"] is True and alan["atilan"] == 1 and alan["yazilan"] == 0 and alan["acik"] is True, alan
    assert alan["sonHata"] == k.son_hata and alan["sonHata"], alan
    assert ENGEL not in r.text, "sağlık yanıtı kayıt klasörünün yolunu taşıyor"
    uzak = istemci({"cf-connecting-ip": "203.0.113.9"})
    assert uzak.status_code == 200 and uzak.json().get("sensorKaydi") is None, (
        "sensör kaydı durumu tünel (uzak) istemcisine verildi"
    )


def test_KARSIT_saglik_ucu_KAYDEDICIYI_yaratmaz(sk, istemci):
    """Kaydedici henüz kurulmadıysa sağlık ucu onu KURMAZ (kurucu veri kökünü mkdir eder — olay döngüsünde disk G/Ç'si, A-8/A-9)."""
    assert sk._kaydedici is None, "aparat: kaydedici önceden kurulmuş"
    r = istemci()
    assert r.status_code == 200
    assert sk._kaydedici is None, (
        "sağlık ucu sensör kaydedicisini KURDU (veri kökünde mkdir — olay döngüsünde disk G/Ç'si)"
    )
    assert r.json().get("sensorKaydi") == {"acik": True, "hata": False, "sonHata": None, "yazilan": 0, "atilan": 0}


def _bugun_dosyasi(sk, tmp_path):
    d = tmp_path / "sensor_log"
    d.mkdir(exist_ok=True)
    return d / f"sensor_{datetime.now():%Y-%m-%d}.csv"


def test_KRITIK_coken_surecin_YARIM_satiri_yeni_satirla_BIRLESMEZ(sk, tmp_path):
    yol = _bugun_dosyasi(sk, tmp_path)
    yarim = "2026-10-27T10:00:00.000,1761555600000,,1,sensors,,23.1"
    yol.write_bytes((",".join(sk.SUTUNLAR) + "\n" + yarim).encode("utf-8"))  # süreç satırın ortasında öldü
    assert sk.kaydet(3, "sensors", YUK) is True
    sk.kaydedici().flush()
    satirlar = yol.read_text(encoding="utf-8").splitlines()
    assert yarim in satirlar, f"yarım satır silindi ya da yeni satırla birleşti: {[s[:60] for s in satirlar]}"
    yeni = dict(zip(sk.SUTUNLAR, satirlar[-1].split(",")))
    assert len(satirlar[-1].split(",")) == len(sk.SUTUNLAR), (
        f"yeni satır yarım satırla BİRLEŞTİ ({len(satirlar[-1].split(','))} sütun): {satirlar[-1][:120]!r}"
    )
    assert yeni["bobin"] == "3" and yeni["temp_object"] == "23.4", yeni


def test_KARSIT_saglam_dosyaya_ekleme_BOS_satir_uretmez(sk, tmp_path):
    yol = _bugun_dosyasi(sk, tmp_path)
    tam = "2026-10-27T10:00:00.000,1761555600000,,1,sensors,,23.1" + "," * (len(sk.SUTUNLAR) - 7)
    yol.write_bytes((",".join(sk.SUTUNLAR) + "\n" + tam + "\n").encode("utf-8"))
    assert sk.kaydet(4, "sensors", YUK) is True
    sk.kaydedici().flush()
    satirlar = yol.read_text(encoding="utf-8").split("\n")
    assert satirlar[-1] == "" and "" not in satirlar[:-1], (
        f"sağlam dosyaya eklemede BOŞ satır oluştu: {[s[:40] for s in satirlar]}"
    )
    assert len(satirlar) == 4, satirlar
