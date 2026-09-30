# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.22 (B-9.26) — `soak_http_ws` GERÇEKTEN WebSocket açıyor ve kopmayı karara katıyor.

ARIZA: betik adı, özeti ve belgeler "HTTP + WebSocket soak" diyordu ama hiç `/ws` açmıyordu — canlı
telemetri/kontrol kanalının kopma sınıfı soak'ta GÖRÜNMÜYORDU, yine de "TEMIZ" kaydı düşüldü
(VERIFICATION §7).

KAPI: betiğin GERÇEK `main()`i 127.0.0.1 rastgele porttaki SAHTE backend'e karşı kısa koşar
(`sahte_soak_backend`); psutil sahtedir, RSS kararlı. WS ortada kesilir → kopma SAYISI ≥1 raporlanır
ve ≠0; sunucu kaydında `/ws` yükseltmesi ≥1. Karşıt: WS açık kalır → TEMIZ / 0. `/ws` artık açıldığı
için varsayılan port 8000 (sahibin backend'i) SESSİZCE hedeflenmez: `--port` zorunlu.
MUTASYON: WS istemci bloğunu silmek → KIRMIZI.

⚠️ D0Ö.22 ek (bağımsız inceleme tur 4):
  · "KOP" alt-dizesi özet satırındaki SABİT `KOPMA {n}` etiketine çarpıyordu (kopma=0 iken de geçerdi) —
    artık SAYI ve sınıf (SUPHELI / OLCULMEDI) pinlenir ("SABİT anahtar alt-dize" tuzağı).
  · WS'ye bağlanılamayan / auth isteyen / ilk mesajı yollamayan backend soak BAŞLAMADAN reddedilir
    (ön-uçuş, çıkış 2) — 72 saatlik koşu sonunda "ölçülmedi" demek yerine.
  · websockets CI test bağımlılıklarında YOKTU: kes/tut kolları CI'da koddan bağımsız KIRMIZI, reddet
    kolu "yüklenemedi" yüzünden YANLIŞ sebeple yeşildi → requirements-test.txt'e sabitlendi (kapı).
"""

from __future__ import annotations

import re
import sys

import pytest
from betik_alt_sureci import KOK, betik_modulu
from sahte_soak_backend import SahteBackend, kos, sahte_psutil, soak_modulu


def _kos(monkeypatch, capsys, ws_davranis: str, rss_olculur: bool = True) -> tuple[int, str, SahteBackend]:
    """`rss_olculur=False`: sahte psutil'de hedef portu dinleyen süreç YOK → RSS ÖLÇÜLEMEZ."""
    m = soak_modulu(monkeypatch)
    sunucu = SahteBackend(ws_davranis)
    port = sunucu.port if rss_olculur else None
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0, port=port))
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    return rc, cikti, sunucu


def _sayac(cikti: str, ad: str) -> int:
    m = re.search(rf"\b{ad} (\d+)", cikti)
    assert m, f"özet satırında '{ad} <n>' yok:\n{cikti[-800:]}"
    return int(m.group(1))


def test_KRITIK_soak_GERCEK_WS_acar_ve_KOPMAYI_karara_katar(monkeypatch, capsys):
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "kes")
    assert sunucu.ws_yukseltme_sayisi() >= 1, "soak /ws'ye HİÇ yükseltme isteği atmadı — WS ölçülmüyor (B-9.26)"
    assert rc == 1, f"WS koptuğu hâlde çıkış {rc} (B-9.26):\n{cikti[-800:]}"
    assert "TEMIZ" not in cikti, f"WS kopması TEMIZ sayıldı:\n{cikti[-800:]}"
    assert _sayac(cikti, "KOPMA") >= 1, f"kopma SAYILMADI (etiket sabit, sayı 0):\n{cikti[-800:]}"
    assert "SUPHELI" in cikti, f"kopma 'WS kararlılığı ŞÜPHELİ' diye sınıflanmadı:\n{cikti[-800:]}"


def test_KRITIK_WS_on_ucusu_BAGLANAMAZSA_soak_BASLAMAZ(monkeypatch, capsys):
    """Bağlanılamayan kanal "kararlı" sayılamaz — soak BAŞLAMADAN reddedilir (ölçülmezdi)."""
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "reddet")
    assert rc == 2 and "TEMIZ" not in cikti, f"WS'ye bağlanılamadığı hâlde soak başladı/TEMIZ (rc={rc}):\n{cikti}"
    # D0Ö.22+15 ek-3 (tur 6): tam ifade — çıplak "OLCULMEDI" başka satırlardan (DB/RSS) da gelebilir.
    assert "WS kararliligi OLCULMEDI olurdu" in cikti and "soak basladi" not in cikti, f"ön-uçuş reddi yok:\n{cikti}"
    # D0Ö.15 ek-2: çıplak "403" rastgele port numarasına (ör. 54030) da çarpabilirdi.
    assert "HTTP 403" in cikti and "yuklenemedi" not in cikti, f"ret nedeni 403 değil (paket eksik?):\n{cikti}"
    assert sunucu.ws_yukseltme_sayisi() >= 1, "ön-uçuş /ws'yi hiç denemedi"


def test_KRITIK_WS_on_ucusu_AUTH_1008_i_adiyla_soyler(monkeypatch, capsys):
    """Auth açık profilde `/ws` token ister: accept() sonra 1008 — "koptu" değil, auth diye raporlanır."""
    rc, cikti, _ = _kos(monkeypatch, capsys, "auth1008")
    assert rc == 2 and "soak basladi" not in cikti, f"auth reddinde soak başladı (rc={rc}):\n{cikti[-800:]}"
    # D0Ö.22+15 ek-3 (tur 6): çıplak "1008" HATA satırındaki rastgele porta (ör. 51008) da çarpabilirdi.
    assert "sunucu 1008 (politika)" in cikti and "auth" in cikti.lower(), f"1008 auth diye adlandırılmadı:\n{cikti}"


def test_KRITIK_on_ucus_gecti_ama_WS_ye_HIC_baglanilamadi_OLCULMEDI(monkeypatch, capsys):
    rc, cikti, _ = _kos(monkeypatch, capsys, "ilk_sonra_reddet")
    assert rc == 1 and "TEMIZ" not in cikti, f"WS'ye hiç bağlanılamadığı hâlde TEMIZ/0 (rc={rc}):\n{cikti[-800:]}"
    assert _sayac(cikti, "baglanti") == 0 and _sayac(cikti, "baglanamama") >= 1, cikti[-800:]
    # D0Ö.22+15 ek-3 (tur 6 — f00d9c3 regresyonu): ek-2'nin yeni "DB : OLCULMEDI" özet satırı çıplak
    # "OLCULMEDI" iddiasını HER koşuda karşılıyordu (süreç içi kapılarda veri kökü yok) → sınıf etiketi korumasızdı.
    ozet = cikti.split("=== OZET ===", 1)[1] if "=== OZET ===" in cikti else ""
    assert "WS kararliligi OLCULMEDI" in ozet, f"bağlanılamayan WS 'ölçülmedi' diye sınıflanmadı:\n{ozet}"


def test_KRITIK_WS_bagli_ama_HIC_mesaj_yok_SUPHELI(monkeypatch, capsys):
    """Açık kalan ama snapshot bile almayan bağlantı "kararlı" değildir (eskiden TEMIZ çıkardı)."""
    rc, cikti, _ = _kos(monkeypatch, capsys, "ilk_sonra_sessiz")
    assert _sayac(cikti, "baglanti") >= 1 and _sayac(cikti, "mesaj") == 0, cikti[-800:]
    assert rc == 1 and "TEMIZ" not in cikti and "SUPHELI" in cikti, f"mesajsız WS TEMIZ (rc={rc}):\n{cikti}"


def test_KRITIK_TUM_nedenler_basilir(monkeypatch, capsys):
    """RSS ölçülemedi VE WS koptu: ikisi de söylenir (eskiden yalnız ilki basılıp dönülüyordu)."""
    rc, cikti, _ = _kos(monkeypatch, capsys, "kes", rss_olculur=False)
    assert rc == 1, cikti[-800:]
    # D0Ö.15 ek-2: yalnız KARAR bölümünde — baştaki 'RSS OLCULEMIYOR … RSS OLCULMEDI olur' uyarısı sayılmaz.
    ozet = cikti.split("=== OZET ===", 1)[1] if "=== OZET ===" in cikti else ""
    assert "RSS OLCULMEDI" in ozet and "KOPTU" in ozet, f"nedenlerden biri karar bölümünde basılmadı:\n{ozet}"


def test_KARSIT_KANIT_WS_acik_ve_RSS_kararli_TEMIZ(monkeypatch, capsys):
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "tut")
    assert sunucu.ws_yukseltme_sayisi() >= 1, "karşıt senaryo WS açmadı"
    assert rc == 0 and "TEMIZ" in cikti, f"sağlıklı koşu TEMIZ değil (rc={rc}):\n{cikti[-800:]}"
    # D0Ö.22+15 ek-3 (tur 6): ek-2'nin görünürlük satırları pinli — veri kökünde .db yok (yalıtım) → "DB : OLCULMEDI"
    # (ölçülmüş "0 -> 0 KB" değil); ölçülen koşuda RSS kaynağı PID + ad ile özette.
    ozet = cikti.split("=== OZET ===", 1)[1] if "=== OZET ===" in cikti else ""
    assert "DB : OLCULMEDI" in ozet and "KB  (fark" not in ozet, f"ölçülmeyen DB ölçülmüş gibi basıldı:\n{ozet}"
    assert "RSS kaynagi: PID 4242 (PEMF_Backend.exe)" in ozet, f"özette RSS kaynağı yok:\n{ozet}"
    assert _sayac(cikti, "KOPMA") == 0 and _sayac(cikti, "mesaj") >= 1, cikti[-800:]


def test_KRITIK_port_ZORUNLU_istek_ATILMAZ(monkeypatch):
    m = betik_modulu("soak_http_ws")
    istekler: list[str] = []
    monkeypatch.setattr(m, "_istek", lambda taban, yol, *a, **k: istekler.append(taban + yol) or (0, 0))
    monkeypatch.setattr(sys, "argv", ["soak_http_ws.py", "--dakika", "0.01"])
    with pytest.raises(SystemExit) as e:
        m.main()
    assert e.value.code == 2, f"--port verilmeden çalıştı (çıkış {e.value.code!r})"
    assert not istekler, f"--port verilmeden istek atıldı: {istekler}"


def _sabit_surum(dosya: str, paket: str) -> str | None:
    for satir in (KOK / dosya).read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^\s*{paket}\s*==\s*([^\s#]+)", satir, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def test_KRITIK_websockets_CI_test_bagimliliklarinda_URETIMLE_ESIT():
    """Bu kapılar GERÇEK websockets istemcisiyle koşar; CI yalnız requirements-test.txt kurar."""
    uretim = _sabit_surum("requirements.txt", "websockets")
    assert uretim, "requirements.txt'te websockets sabiti yok — kapı bayat"
    test = _sabit_surum("requirements-test.txt", "websockets")
    assert test == uretim, (
        f"requirements-test.txt websockets={test!r} (üretim {uretim}): CI'da kes/tut kolları koddan "
        "bağımsız KIRMIZI, reddet kolu 'yüklenemedi' yüzünden YANLIŞ sebeple yeşil olur."
    )
