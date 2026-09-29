# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.15 (B-10.97) — `soak_http_ws` bellek sızıntısını ÖLÇEMEDİĞİNDE "TEMIZ" demiyor.

ARIZA: psutil yoksa ya da `PEMF_Backend` süreci bulunamazsa RSS 0 okunuyordu; oran 0 → sonuç
"TEMIZ" / 0 (bellek sızıntısı hiç ölçülmeden). Tek örnekte de 0 dönüyordu. RSS ölçülemezken ısınma
beklemesi 180 sn boşuna dönüyordu (ölçülemeyen şey oturmaz). Veri kökünü çözen ölü import D0Ö.19
(`a7a2b48`) ile düzeldi (kapı: `test_f4_rapor_soak_betikleri_CALISIYOR`).

KAPI: GERÇEK `main()`, sahte backend (`sahte_soak_backend`) + sahte psutil (hedef portu dinleyen süreç
YOK): "RSS OLCULMEDI" ve ≠0, TEMIZ DEĞİL; tek örnek → 1 ve "karar VERILEMEDI"; RSS ölçülemezken ısınma
beklenmez.
MUTASYON: RSS=0'da denetimi atlayıp TEMIZ dönmek → KIRMIZI.

⚠️ D0Ö.15 ek (bağımsız inceleme tur 4):
  · RSS süreci ADA göre seçiliyordu (`pemf_backend*`) — `--port` ile bağı yoktu. Hedef `python.exe`
    (kaynaktan dev backend) iken makinede başka bir PEMF_Backend koşuyorsa RSS O süreçten okunur, hedef
    ölçülmeden TEMIZ/0 çıkardı. Artık `--port`u LISTEN eden PID okunur; bulunamazsa ÖLÇÜLMEDİ.
  · Neden + eylem söylenir (psutil yok → `pip install psutil`; portu dinleyen süreç görülemedi);
    jeton ASCII `RSS OLCULMEDI` (günlükte tek jetonla aranabilir).
  · Ölçülmeyen RSS özet satırında "0.0 -> 0.0 MB (%+0.0)" diye ÖLÇÜLMÜŞ gibi basılmaz.
  · Isınma beklemesinin kendisi (254 → 2310 MB oturması) karşıt kanıtla pinlenir.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from betik_alt_sureci import betik_modulu
from sahte_soak_backend import SahteBackend, kos, sahte_psutil, soak_modulu


def _kos(monkeypatch, capsys, psutil_fn, **kw) -> tuple[int, str, SahteBackend]:
    """`psutil_fn(hedef_port)` → sahte psutil (ya da None: psutil YOK)."""
    m = soak_modulu(monkeypatch)
    sunucu = SahteBackend("tut")
    monkeypatch.setitem(sys.modules, "psutil", psutil_fn(sunucu.port))
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port, **kw)
    finally:
        sunucu.kapat()
    return rc, cikti, sunucu


def test_KRITIK_RSS_OLCULEMEZSE_TEMIZ_DEMEZ(monkeypatch, capsys):
    rc, cikti, sunucu = _kos(monkeypatch, capsys, lambda port: sahte_psutil("python.exe", 80.0))  # port dinlenmez
    assert rc != 0 and "TEMIZ" not in cikti, f"RSS hiç ölçülmeden TEMIZ/0 (B-10.97, rc={rc}):\n{cikti[-800:]}"
    assert "RSS OLCULMEDI" in cikti, f"'RSS OLCULMEDI' denmedi:\n{cikti[-800:]}"
    assert "0.0 -> 0.0" not in cikti, f"ölçülmeyen RSS ölçülmüş %0 gibi basıldı:\n{cikti[-800:]}"
    assert "KARAR VEREMEZ" in cikti, f"koşunun RSS için karar veremeyeceği BAŞTA söylenmedi:\n{cikti[-800:]}"
    assert sunucu.ws_yukseltme_sayisi() >= 1, "soak /ws açmadı — 'HTTP + WebSocket soak' iddiası boş (B-10.97)"


def test_KRITIK_RSS_HEDEF_PORTU_dinleyen_surecten_okunur(monkeypatch, capsys):
    """Hedef (python.exe, dev backend) sızdırıyor; makinede BAŞKA portta kararlı bir PEMF_Backend var.

    Ada göre seçen eski betik kararlı olanı okuyup TEMIZ/0 derdi — hedef hiç ölçülmeden."""

    def _psutil(port):
        return sahte_psutil(
            "python.exe", lambda n: 100.0 * 2**n, port=port, digerleri=(("PEMF_Backend.exe", 500.0, port + 1),)
        )

    rc, cikti, _ = _kos(monkeypatch, capsys, _psutil)
    assert rc == 1 and "TEMIZ" not in cikti, f"hedefin sızıntısı görülmedi (rc={rc}):\n{cikti[-800:]}"
    assert "SIZINTI" in cikti, f"RSS hedef portu dinleyen süreçten okunmadı:\n{cikti[-800:]}"


def test_KRITIK_hedef_portu_dinleyen_surec_YOKSA_RSS_OLCULMEDI(monkeypatch, capsys):
    """Yalnız BAŞKA portta bir PEMF_Backend var: hedefin RSS'i ÖLÇÜLMEDİ (onunki değil)."""
    rc, cikti, _ = _kos(monkeypatch, capsys, lambda port: sahte_psutil("PEMF_Backend.exe", 500.0, port=port + 1))
    assert rc == 1 and "TEMIZ" not in cikti, f"başka sürecin RSS'i hedefinki sayıldı (rc={rc}):\n{cikti[-800:]}"
    assert "RSS OLCULMEDI" in cikti and "dinleyen" in cikti, f"neden söylenmedi:\n{cikti[-800:]}"


def test_KRITIK_psutil_YOKSA_eylemi_SOYLER(monkeypatch, capsys):
    rc, cikti, _ = _kos(monkeypatch, capsys, lambda port: None)  # import psutil → ImportError
    assert rc == 1 and "RSS OLCULMEDI" in cikti, f"(rc={rc}):\n{cikti[-800:]}"
    assert "pip install psutil" in cikti, f"psutil eksikliğinin eylemi söylenmedi:\n{cikti[-800:]}"


def test_KRITIK_tek_ornekte_cikis_SIFIR_DEGIL(monkeypatch, capsys):
    rc, cikti, _ = _kos(
        monkeypatch, capsys, lambda port: sahte_psutil("PEMF_Backend.exe", 500.0, port=port), dakika=0.03, aralik=30.0
    )
    # D0Ö.15 ek: yalnız "≠0" değil — ön-uçuş (rc=2) gibi başka bir erken çıkış bu kapıyı yeşil tutmasın.
    assert rc == 1, f"tek örnekle karar verilemez ama çıkış {rc} (B-10.97):\n{cikti[-600:]}"
    assert "soak basladi" in cikti and "karar VERILEMEDI" in cikti, f"tek-örnek dalı değil:\n{cikti[-600:]}"
    # D0Ö.22 ek: erken dönüş yolunda da WS sayaçları basılır (eskiden bu yolda WS özeti hiç yoktu).
    assert "baglanti" in cikti and "KOPMA" in cikti, f"tek örnek yolunda WS özeti yok:\n{cikti[-600:]}"


def _sahte_saat(m, monkeypatch) -> list[float]:
    saat = {"t": 0.0}
    uykular: list[float] = []

    def _uyu(sn):
        uykular.append(sn)
        saat["t"] += sn

    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=lambda: saat["t"], sleep=_uyu))
    return uykular


def test_KRITIK_RSS_OLCULEMEZKEN_isinma_BEKLENMEZ(monkeypatch):
    m = betik_modulu("soak_http_ws")
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("python.exe", 80.0))
    uykular = _sahte_saat(m, monkeypatch)
    m._rss_oturmasini_bekle(8082, azami_sn=30.0)
    assert not uykular, f"RSS ölçülemezken {sum(uykular):.0f} sn ısınma beklendi (ölçülemeyen şey oturmaz)"


def test_KARSIT_KANIT_olculebilir_RSS_te_isinma_BEKLENIR_ve_OTURMUS_deger_doner(monkeypatch):
    """D0Ö.15 ek: ısınmayı atlayan mutant (koşulsuz erken dönüş) tüm kapılarda yeşil kalıyordu — oysa
    254 MB'lık health-anı değeri taban alınırsa AI ısınması (→ 2310 MB, +%809) SIZINTI sanılır."""
    m = betik_modulu("soak_http_ws")
    seri = [254.0, 2310.0, 2310.0, 2310.0, 2310.0, 2310.0]
    monkeypatch.setitem(
        sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", lambda n: seri[min(n, len(seri) - 1)], port=8082)
    )
    uykular = _sahte_saat(m, monkeypatch)
    oturmus = m._rss_oturmasini_bekle(8082, azami_sn=180.0, kararli_tur=3)
    assert oturmus == 2310.0, f"oturmuş RSS değil ısınma-öncesi değer döndü: {oturmus}"
    assert sum(uykular) >= 15.0, f"ısınma beklenmedi ({sum(uykular):.0f} sn)"
