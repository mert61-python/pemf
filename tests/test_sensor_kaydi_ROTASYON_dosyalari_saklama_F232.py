# -*- coding: utf-8 -*-
"""F2-3.2 (2-F incelemesi A3, K1 · D2.39) — başlık rotasyonunun `sensor_<gün>_<n>.csv` dosyaları gün sınırında SİLİNİR, etkin dosya
boyut tavanında korunur.

D2.39 (`d8a1828`) o gün eski başlıkla açılmış dosya varsa satırları `sensor_<gün>_<n>.csv`ye yazar ve iki iddia taşır: "retention gün
etiketini ilk 10 karakterden okur" (`_temizle` `[:10]`) ve "etkin dosya (`_aktif_ad`) silinmez". D2.39 kapısı ve `test_sensor_kaydedici`
bu iki iddiayı ÖLÇMÜYOR: `[:10]` kaldırılınca (`_n` dosyaları gün sınırında hiç silinmez — strptime ValueError → continue) 18/18 YEŞİL.
GERÇEK `SensorKaydedici`, dizin testin tmp'si.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def sk(tmp_path, monkeypatch):
    from servers import sensor_kaydedici as mod

    monkeypatch.delenv("PEMF_SENSOR_LOG", raising=False)
    return mod


def _g(gun_once: int) -> str:
    return f"{datetime.now() - timedelta(days=gun_once):%Y-%m-%d}"


def test_KRITIK_rotasyon_dosyalari_GUN_SINIRINDA_silinir(sk, tmp_path):
    d = tmp_path / "sensor_log"
    d.mkdir()
    eski = [f"sensor_{_g(20)}.csv", f"sensor_{_g(20)}_2.csv", f"sensor_{_g(20)}_3.csv"]
    taze = [f"sensor_{_g(1)}_2.csv"]
    for ad in eski + taze:
        (d / ad).write_text("x\n", encoding="utf-8")
    k = sk.SensorKaydedici(dizin=d, gun=14, mb=500)
    try:
        assert k.kaydet(6, "sensors", {"object_temp": 30.0}) is True
    finally:
        k.kapat()
    kalan = {p.name for p in d.glob("sensor_*.csv")}
    assert not (set(eski) & kalan), f"gün sınırını aşan rotasyon dosyaları SİLİNMEDİ: {sorted(set(eski) & kalan)}"
    assert set(taze) <= kalan, "gün sınırı içindeki rotasyon dosyası silindi"


def test_KRITIK_etkin_rotasyon_dosyasi_BOYUT_TAVANINDA_korunur(sk, tmp_path):
    """Aynı gün yeniden açılış: taban dosya eski başlıklı, etkin dosya `_2` ve tavanı tek başına aşıyor → `_2` silinmez, yazım sürer.
    ⚠️ Windows'ta açık dosyanın silinmesi WinError 32 verir (`_temizle` yutar): tavanı `_aktif_ad` yerine taban adla karşılaştıran ya da
    `_aktif_ad`ı yazmayan mutant bu platformda EŞDEĞER (orkestratör ölçtü: yeşil); kol Linux CI'da ayırt eder."""
    d = tmp_path / "sensor_log"
    d.mkdir()
    bugun = _g(0)
    (d / f"sensor_{bugun}.csv").write_text(",".join(sk.SUTUNLAR[:24]) + "\n1\n", encoding="utf-8")
    etkin = d / f"sensor_{bugun}_2.csv"
    with open(etkin, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(sk.SUTUNLAR) + "\n")
        f.write(("y" * 1023 + "\n") * 1600)  # ~1,6 MB > 1 MB tavan
    k = sk.SensorKaydedici(dizin=d, gun=14, mb=1)
    try:
        assert k.kaydet(6, "sensors", {"object_temp": 31.0}) is True
        k.flush()
    finally:
        k.kapat()
    assert etkin.exists(), "boyut tavanı ETKİN rotasyon dosyasını sildi (yazılan satırlar kayıp)"
    assert etkin.read_text(encoding="utf-8").rstrip("\n").splitlines()[-1].split(",")[6] == "31.0", (
        "etkin dosyaya yazılmadı"
    )
