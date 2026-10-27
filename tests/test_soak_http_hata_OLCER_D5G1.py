# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 G-1 (D0Ö §6.4 · DALGA-1-KAPANIS) — `soak_http_ws` soak ORTASINDA başarısız HTTP isteğini karara katıyor.

ARIZA (kör kapı): sahte backend (`sahte_soak_backend`) okuma uçlarına HEP 200 döndüğü için `main()`deki HTTP-hata
kolu (`if kod not in KABUL: hata += 1` → `if hata:` → "HTTP kararliligi supheli") hiçbir kapıda yürütülmüyordu.
ÖLÇÜLDÜ (HEAD 8d9169cf): karar dalını silmek, sayacı artırmamak ya da `_istek`in HTTPError'unu 200 saymak →
soak kapıları (ws/rss/f4/betikler) 50/50 YEŞİL; HTTP'si kararsız koşu "SONUC: TEMIZ" / 0 derdi. Yalnız koşulu
ters çevirmek (`if not hata`) karşıt kolda (hep-200 → SORUNLU) yakalanıyordu.

KAPI: betiğin GERÇEK `main()`i 127.0.0.1 rastgele porttaki sahte backend'e karşı kısa koşar (psutil sahte, RSS
kararlı, WS açık kalır — tek neden HTTP olsun). Ön-uçuş bittikten sonra backend
  · her 3. isteğe 503 döner                → SORUNLU (1 neden), özetteki `hata` = backend'in döndürdüğü 5xx sayısı;
  · her 3. isteği YANITSIZ keser           → aynı (bağlantı koptu / ret sınıfı: betik kod 0 sayar);
  · yalnız İLK isteğe 500 döner            → TEK başarısız istek de SORUNLU (eşik `> 1` değil);
  · ön-uçuşta bir uç 422 döner             → soak HİÇ başlamaz, çıkış 2 (2026-09-13 yazım hatası sınıfı).
KARŞIT: hep 200 → TEMIZ / 0, özette `hata: 0`, HTTP kararlılık uyarısı YOK.
MUTASYON: karar dalını sil · sayacı artırma · HTTPError'u 200 say · bağlantı hatasını 200 say · eşik `> 1` ·
KABUL'e 5xx/0 ekle → KIRMIZI.
"""

from __future__ import annotations

import re
import sys

from sahte_soak_backend import SahteBackend, kos, sahte_psutil, soak_modulu


def _kos(monkeypatch, capsys, http_davranis: str) -> tuple[int, str, SahteBackend]:
    m = soak_modulu(monkeypatch)
    sunucu = SahteBackend("tut", http_davranis=http_davranis)
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0, port=sunucu.port))
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    return rc, cikti, sunucu


def _ozet(cikti: str) -> str:
    """Kararın basıldığı bölüm — koşu sırasındaki periyodik satırlar sayılmaz (sabit anahtar alt-dize tuzağı)."""
    return cikti.split("=== OZET ===", 1)[1] if "=== OZET ===" in cikti else ""


def _sayac(ozet: str, ad: str) -> int:
    m = re.search(rf"\b{ad}: (\d+)", ozet)
    assert m, f"özette '{ad}: <n>' yok:\n{ozet[-800:]}"
    return int(m.group(1))


def _http_hatasi_karara_girer(rc: int, cikti: str, sunucu: SahteBackend) -> None:
    ozet = _ozet(cikti)
    assert "soak basladi" in cikti and ozet, f"soak başlamadı / özet yok (rc={rc}) — kol yürütülmedi:\n{cikti[-800:]}"
    assert sunucu.http_hata >= 1, f"aparat: backend soak sırasında hiç hata döndürmedi ({sunucu.http_sirasi} istek)"
    assert _sayac(ozet, "istek") == sunucu.http_sirasi, f"aparat: soak istek sayısı backend'inkiyle eşleşmiyor:\n{ozet}"
    assert _sayac(ozet, "hata") == sunucu.http_hata, (
        f"backend {sunucu.http_hata} isteğe hata döndürdü ama özet başka sayı basıyor:\n{ozet}"
    )
    beklenen = f"UYARI: {sunucu.http_hata} istek basarisiz -> HTTP kararliligi supheli."
    assert beklenen in ozet, f"başarısız HTTP istekleri karara girmedi (beklenen: {beklenen!r}):\n{ozet}"
    assert rc == 1 and "TEMIZ" not in cikti, f"HTTP'si kararsız soak TEMIZ / {rc} döndü:\n{ozet}"
    # Tek neden HTTP: RSS kararlı, WS açık — kırmızı başka bir kola kaymasın.
    assert "SONUC: SORUNLU (1 neden)" in ozet, f"neden sayısı 1 değil (HTTP dışı bir kol mu tetiklendi?):\n{ozet}"


def test_KRITIK_soak_ortasinda_5xx_donerse_TEMIZ_DEMEZ(monkeypatch, capsys):
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "5xx")
    _http_hatasi_karara_girer(rc, cikti, sunucu)


def test_KRITIK_soak_ortasinda_BAGLANTI_yanitsiz_kesilirse_TEMIZ_DEMEZ(monkeypatch, capsys):
    """Yanıtsız kapanış (bağlantı koptu / ret sınıfı): `_istek` kod 0 döndürür — 0 da başarısız sayılmalı."""
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "kes")
    _http_hatasi_karara_girer(rc, cikti, sunucu)


def test_KRITIK_TEK_basarisiz_istek_de_SORUNLU(monkeypatch, capsys):
    """Eşik yok: koşu boyunca TEK bir 500 de HTTP kararlılığını şüpheli yapar."""
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "tek_500")
    assert sunucu.http_hata == 1, f"aparat: tek_500 kipi {sunucu.http_hata} hata döndürdü"
    _http_hatasi_karara_girer(rc, cikti, sunucu)


def test_KRITIK_on_ucusta_BEKLENMEDIK_kod_soak_BASLAMAZ(monkeypatch, capsys):
    """2026-09-13 sınıfı: yanlış uç her turda 422 döndürüp "ürün kararsız" diye raporlanmıştı — ön-uçuş reddeder."""
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "on_ucus_422")
    assert rc == 2, f"ön-uçuşta 422 dönen uç varken çıkış {rc} (2 beklenir):\n{cikti[-800:]}"
    assert "on-ucus dogrulamasi BASARISIZ" in cikti and "/api/history/ -> HTTP 422" in cikti, (
        f"ön-uçuş reddi / nedeni (uç + kod) basılmadı:\n{cikti[-800:]}"
    )
    assert "soak basladi" not in cikti and "TEMIZ" not in cikti, f"ön-uçuş reddine rağmen soak başladı:\n{cikti}"
    assert sunucu.ws_yukseltme_sayisi() == 0, "HTTP ön-uçuşu reddettiği hâlde betik /ws'ye geçti"


def test_KARSIT_KANIT_hep_200_hata_0_TEMIZ(monkeypatch, capsys):
    rc, cikti, sunucu = _kos(monkeypatch, capsys, "200")
    ozet = _ozet(cikti)
    assert sunucu.http_hata == 0 and sunucu.http_sirasi >= 1, "aparat: karşıt kol soak isteği görmedi / hata döndü"
    assert _sayac(ozet, "istek") == sunucu.http_sirasi, f"aparat: soak istek sayısı backend'inkiyle eşleşmiyor:\n{ozet}"
    assert _sayac(ozet, "hata") == 0, f"backend hep 200 döndürdü ama özet başarısız istek sayıyor:\n{ozet}"
    assert "HTTP kararliligi" not in cikti, f"hiç başarısız istek yokken HTTP uyarısı basıldı:\n{ozet}"
    assert rc == 0 and "SONUC: TEMIZ" in ozet, f"sağlıklı koşu TEMIZ değil (rc={rc}):\n{ozet}"
