# Author: mertaygn, cglrgrkn
"""GRAFİK/KAMERA KATMANI KAPISI  [S7 adım 7, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM:
  · `RealtimeChart` eksen boşlukları SABİTTİ (left 60, right 60): 320 px'lik telefonda çizim alanı
    200 px'e düşüyordu ve sıcaklık ekseni kapalıyken sağda 60 px boş duruyordu.
  · Seans detayı sıcaklık grafiği `viewBox="0 0 720 260"` + `width="100%"` ile çiziliyordu; 360 px'lik
    telefonda her şey 0,5 ölçekle küçülüp 11 px'lik eksen yazıları 5-6 px'e iniyordu (okunmuyordu).
  · Sensör ekranı grafiği 1200 px ile kapaklanıyordu.

BU KAPI kaynak-düzeyi ÇIPALARI kilitler; DAVRANIŞ jest ile ölçülür:
  · pf/src/components/visual/__tests__/chartLayout.test.ts (saf hesaplar)
  · pf/src/components/domain/__tests__/SessionDetailModal.tempChart.test.tsx (ölçülen genişlik)
  · pf/src/utils/__tests__/kameraKutusu.test.ts (oran kilidi)

⚠️ NEDEN KAYNAK ÇIPASI DA GEREKLİ (ölçüldü): saf hesap testleri, bileşenin o hesabı KULLANMAYI
bırakmasını yakalayamıyor. `RealtimeChart`teki `hesaplaPad(...)` çağrısı elle sabit PAD'e geri
çevrildiğinde jest süiti YEŞİL kalıyordu; bağlantıyı bu dosya kilitler.
"""

import pathlib

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "pf" / "src"

pytestmark = pytest.mark.skipif(
    not (_PF / "components" / "visual" / "chartLayout.ts").exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)


def _oku(bagil: str) -> str:
    return (_PF / bagil).read_text(encoding="utf-8")


def test_KRITIK_realtime_grafik_bosluklari_genislikten_turer():
    src = _oku("components/visual/RealtimeChart.tsx")
    assert src.count("hesaplaPad(width, showTemp)") == 2, (
        "RealtimeChart'ın web ve native dallarının İKİSİ de hesaplaPad kullanmalı "
        "(sabit PAD 320 px'te çizim alanını 200 px'e düşürüyordu)."
    )
    assert "top: 20, right: 60, bottom: 40, left: 60" not in src, "sabit PAD geri gelmiş"


def test_KRITIK_web_tuvali_DPR_ile_kurulur():
    src = _oku("components/visual/RealtimeChart.tsx")
    assert "canvasBoyutla(" in src, "web tuvali DPR ölçeklemesi olmadan bulanık çizer"
    assert "devicePixelRatio" in src


def test_KRITIK_seans_sicaklik_grafigi_olculen_genislikte():
    src = _oku("components/domain/SessionDetailModal.tsx")
    assert "const width = 720" not in src, (
        "TempChart sabit 720 px viewBox'a dönmüş: 360 px telefonda eksen yazıları 5-6 px'e düşer."
    )
    assert 'testID="seans-sicaklik-grafigi"' in src and "onLayout" in src


def test_sensor_grafigi_sabit_kapakla_sinirlanmiyor():
    src = _oku("screens/SensorMonitorScreen.tsx")
    assert "Math.min(chartW, 1200)" not in src, "1200 px kapağı geri gelmiş"


def _kodu(src: str) -> str:
    """Yorum satırlarını eler. (Sözleşmenin KENDİSİ yorumlarda geçiyor; ilk sürüm onları ihlal saydı.)"""
    ayik = []
    for satir in src.splitlines():
        kirp = satir.strip()
        if kirp.startswith("//") or kirp.startswith("*") or kirp.startswith("/*"):
            continue
        ayik.append(satir.split("//")[0])
    return "\n".join(ayik)


def test_kamera_kutusu_oran_kilidi_tek_kaynakta():
    src = _oku("utils/kameraKutusu.ts")
    assert "kameraKutusu" in src and "kareOrani" in src
    # aspectRatio + maxHeight birleşimi oranı bozar; kutu AÇIK px hesaplanmalı.
    assert "aspectRatio" not in _kodu(src), (
        "Oran kilidi aspectRatio'ya dönmüş: maxHeight ile birlikte genişlik %100 kalır ve "
        "oran yine bozulur (organ işaretleri canlı görüntüyle kayar)."
    )
