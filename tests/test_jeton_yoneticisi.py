# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""JETON YÖNETİCİSİ — cihaz tarafı (7. parti, sahip talimatı 2026-08-20).

Ücretlendirme jeton tüketimine bağlandı (bkz. database/supabase_jetonlar.sql,
pemf-vet-web/src/config.ts::JETON). Bu modül KLİNİK CİHAZINDA koşar ve üç zor koşulu birden
karşılamak zorundadır:

  1. ⚠️ TIBBİ GÜVENLİK (pazarlık edilemez): jeton TİCARİ bir kapıdır. Süren seansı, seans
     durdurmayı, ACİL DURDURMAYI, sensör okumayı ve cihaz kontrolünü ASLA engellemez.
     Yalnız YENİ yapay zekâ ANALİZİ isteğini kapılar. (Depo emsali: entitlement.py aynı ilkeyi
     "compute-önceliği kapısı, güvenlik kontrolü DEĞİL" diye yazıyor ve fail-open davranıyor.)
  2. ÇEVRİMDIŞI KLİNİK: internet yokken analiz durmaz — tüketim yerel deftere yazılır, bağlantı
     gelince uzlaşır. Sınırsız değil: `OFFLINE_TAVAN` kadar (aksi hâlde ücretlendirme anlamsızlaşır).
  3. ÇİFT DÜŞME YOK: her tüketimin `istek_id`si vardır; yeniden deneme/uzlaştırma aynı jetonu
     iki kez harcayamaz (sunucu tarafında da UNIQUE ile kilitli).

⚠️ BAYRAKLI + FAIL-OPEN: `PEMF_JETON_ENFORCED` kapalıyken her şey serbest (mevcut davranış
korunur; satış açılana kadar canlı bozulmaz) — entitlement.py ile birebir aynı desen.
"""

from __future__ import annotations

import importlib
import os

import pytest


def _yeni(tmp_path, **env):
    """Modülü TEMİZ ortamla yeniden yükle (bayraklar import zamanında okunuyor)."""
    ortam = {"PEMF_JETON_ENFORCED": "0", "PEMF_DATA_DIR": str(tmp_path)}
    ortam.update(env)
    for k, v in ortam.items():
        os.environ[k] = v
    import servers.jeton as j

    importlib.reload(j)
    return j


# ─────────────────────── 1) TIBBİ GÜVENLİK DEĞİŞMEZİ ───────────────────────


def test_KRITIK_GUVENLIK_seans_ve_acil_durdurma_ASLA_kapilanmaz(tmp_path):
    """Jeton bitse bile tedavi tarafı çalışır. Bu, ürünün pazarlık edilemez değişmezi."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 0, tuketim_gonderici=lambda **k: False)

    for guvenli in ("seans_baslat", "seans_durdur", "acil_durdur", "sensor_oku", "cihaz_kontrol"):
        karar = y.izin(guvenli)
        assert karar.izinli, f"jeton kapısı GÜVENLİK yolunu engelledi: {guvenli}"
        assert karar.jeton_harcandi == 0, f"{guvenli} jeton harcamamalı"


def test_KRITIK_yalniz_YAPAY_ZEKA_analizi_kapilanir(tmp_path):
    """Bakiye sıfırken analiz reddedilir — ama mesaj tedavinin etkilenmediğini söyler."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 0, tuketim_gonderici=lambda **k: False)

    karar = y.izin("goruntu")
    assert not karar.izinli, "bakiye 0 iken analiz izni verildi"
    assert "seans" in karar.mesaj.lower() or "acil durdurma" in karar.mesaj.lower(), (
        f"red mesajı tedavinin etkilenmediğini SÖYLEMİYOR: {karar.mesaj!r}"
    )


# ─────────────────────── 2) BAYRAK / FAIL-OPEN ───────────────────────


def test_KRITIK_bayrak_KAPALIYKEN_hicbir_sey_kapilanmaz(tmp_path):
    """Satış açılana kadar canlı davranış DEĞİŞMEZ (entitlement.py deseni)."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="0")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 0, tuketim_gonderici=lambda **k: False)
    karar = y.izin("agir_arastirma")
    assert karar.izinli, "bayrak kapalıyken analiz engellendi (canlı davranış bozuldu)"


def test_KRITIK_sunucuya_ULASILAMAZSA_analiz_durmaz(tmp_path):
    """Çevrimdışı klinik: bakiye okunamıyor → yerel tavana kadar İZİN + borç kaydı."""

    def patlayan():
        raise ConnectionError("ağ yok")

    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=patlayan, tuketim_gonderici=lambda **k: False)

    karar = y.izin("goruntu")
    assert karar.izinli, "internet yokken analiz engellendi — klinik çalışamaz hâle gelir"
    assert y.bekleyen_tuketim_sayisi() == 1, "çevrimdışı tüketim yerel deftere yazılmadı"


def test_KRITIK_cevrimdisi_TAVAN_asilinca_reddedilir(tmp_path):
    """Sınırsız çevrimdışı kullanım ücretlendirmeyi anlamsız yapardı."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1", PEMF_JETON_OFFLINE_TAVAN="3")

    def patlayan():
        raise ConnectionError("ağ yok")

    y = j.JetonYoneticisi(bakiye_okuyucu=patlayan, tuketim_gonderici=lambda **k: False)
    for _ in range(3):
        assert y.izin("goruntu").izinli
    son = y.izin("goruntu")
    assert not son.izinli, "çevrimdışı tavan aşıldığı hâlde analiz sürdü"
    # ⚠️ Tavan aşılsa BİLE tedavi yolu serbest kalmalı.
    assert y.izin("acil_durdur").izinli


# ─────────────────────── 3) TÜKETİM / İDEMPOTANS ───────────────────────


def test_KRITIK_bakiye_yeterliyken_TUKETIM_gonderilir(tmp_path):
    gonderilen = []
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 100,
        tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1],
    )
    karar = y.izin("agir_arastirma")
    assert karar.izinli
    assert karar.jeton_harcandi == j.MALIYET["agir_arastirma"], "ağır model maliyeti yanlış"
    assert len(gonderilen) == 1 and gonderilen[0]["miktar"] == karar.jeton_harcandi
    assert len(gonderilen[0]["istek_id"]) >= 8, "idempotans anahtarı üretilmedi"


def test_KRITIK_AYNI_istek_iki_kez_dusmez(tmp_path):
    """Yeniden deneme aynı `istek_id` ile gider — sunucu ikinciyi yok sayar, yerel defter şişmez."""
    gonderilen = []
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 100,
        tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1],
    )
    k1 = y.izin("goruntu", istek_id="ayni-istek-0001")
    k2 = y.izin("goruntu", istek_id="ayni-istek-0001")
    assert k1.izinli and k2.izinli
    assert len({g["istek_id"] for g in gonderilen}) == 1, "aynı istek iki farklı kimlikle gönderildi"


def test_KRITIK_bekleyen_tuketim_UZLASTIRILIR_ve_defterden_dusulur(tmp_path):
    """Bağlantı gelince biriken çevrimdışı tüketim gönderilir; başarılı olanlar defterden silinir."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")

    def patlayan():
        raise ConnectionError("ağ yok")

    y = j.JetonYoneticisi(bakiye_okuyucu=patlayan, tuketim_gonderici=lambda **k: False)
    y.izin("goruntu")
    y.izin("ses")
    assert y.bekleyen_tuketim_sayisi() == 2

    gonderilen = []
    y2 = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 100,
        tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1],
    )
    gonderilen_sayisi = y2.bekleyenleri_uzlastir()
    assert gonderilen_sayisi == 2, "bekleyen tüketim uzlaştırılmadı"
    assert y2.bekleyen_tuketim_sayisi() == 0, "uzlaşan kayıtlar defterden düşmedi"


def test_KARSIT_KANIT_uzlastirma_BASARISIZSA_kayit_KORUNUR(tmp_path):
    """Aşırı-düzeltme koruması: gönderim düşerse kayıt silinirse tüketim SESSİZCE kaybolurdu."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")

    def patlayan():
        raise ConnectionError("ağ yok")

    y = j.JetonYoneticisi(bakiye_okuyucu=patlayan, tuketim_gonderici=lambda **k: False)
    y.izin("goruntu")
    assert y.bekleyen_tuketim_sayisi() == 1

    y2 = j.JetonYoneticisi(bakiye_okuyucu=lambda: 100, tuketim_gonderici=lambda **k: False)
    y2.bekleyenleri_uzlastir()
    assert y2.bekleyen_tuketim_sayisi() == 1, "gönderim başarısızken kayıt silindi — tüketim kayboldu"


def test_KARSIT_KANIT_maliyet_tablosu_WEB_ile_AYNI(tmp_path):
    """İki taraf ayrışırsa kullanıcı sitede '1 jeton' okuyup cihazda 3 harcar."""
    import json
    import re
    from pathlib import Path

    j = _yeni(tmp_path)
    web = (Path(__file__).resolve().parent.parent / "pemf-vet-web" / "src" / "config.ts").read_text(
        encoding="utf-8", errors="replace"
    )
    m = re.search(r"maliyet:\s*\{([^}]*)\}", web)
    assert m, "web tarafında JETON.maliyet bulunamadı"
    web_maliyet = dict(re.findall(r"(\w+):\s*(\d+)", m.group(1)))
    for ad, deger in web_maliyet.items():
        assert ad in j.MALIYET, f"cihaz tarafında '{ad}' maliyeti tanımsız"
        assert j.MALIYET[ad] == int(deger), f"'{ad}' maliyeti ayrıştı: web={deger} cihaz={j.MALIYET[ad]}"
    assert json.dumps(sorted(web_maliyet)) == json.dumps(sorted(j.MALIYET)), "maliyet anahtarları ayrıştı"
