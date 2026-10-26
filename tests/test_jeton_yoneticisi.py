# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""JETON YÖNETİCİSİ — cihaz tarafı (7. parti, sahip talimatı 2026-08-20).

Ücretlendirme jeton tüketimine bağlandı (bkz. apps/backend/database/supabase_jetonlar.sql,
apps/web/src/config.ts::JETON). Bu modül KLİNİK CİHAZINDA koşar ve üç zor koşulu birden
karşılamak zorundadır:

  1. ⚠️ TIBBİ GÜVENLİK (pazarlık edilemez): jeton TİCARİ bir kapıdır. Süren seansı, seans
     durdurmayı, ACİL DURDURMAYI, sensör okumayı ve cihaz kontrolünü ASLA engellemez.
     Yalnız YENİ yapay zekâ ANALİZİ isteğini kapılar. (Depo emsali: entitlement.py aynı ilkeyi
     "compute-önceliği kapısı, güvenlik kontrolü DEĞİL" diye yazıyor ve fail-open davranıyor.)
  2. İNTERNET ŞARTI (S-4B.5 + S-4BI.8, sahip kararı 2026-10-19; yalnız ücretlendirme AÇIKKEN): bakiye okunamıyorsa yeni
     analiz BAŞLATILMAZ (eskiden çevrimdışı tavana kadar izin + defter + "eksi bakiye"). Defterde yalnız YOLDA KALAN ÖDEME
     olur (karar çevrimiçi alındı, düşüm tam o an gönderilemedi) — sonra yeniden denenir ve o zamana dek bakiyeden düşülür.
  3. ÇİFT DÜŞME YOK: her tüketimin `istek_id`si vardır; yeniden deneme/uzlaştırma aynı jetonu
     iki kez harcayamaz (sunucu tarafında da UNIQUE ile kilitli).

⚠️ BAYRAKLI + FAIL-OPEN: `PEMF_JETON_ENFORCED` kapalıyken her şey serbest (mevcut davranış
korunur; satış açılana kadar canlı bozulmaz) — entitlement.py ile birebir aynı desen.
"""

from __future__ import annotations

import importlib
import os

import pytest

_ORTAM_ANAHTARLARI = ("PEMF_JETON_ENFORCED", "PEMF_DATA_DIR")


@pytest.fixture(autouse=True)
def _ortam_ve_modul_geri_yukle():
    """D5 (ortam sızıntısı envanteri): `_yeni` `os.environ`a DOĞRUDAN yazar ve `servers.jeton`u yeniden yükleyip `JETON_ENFORCED`i elle
    kurar — test bitince bunlar KALIYORDU (`PEMF_JETON_ENFORCED` sonraki dosyalara sızıyordu [ÖLÇTÜM]). Ortam eski hâline döner,
    modül o ortamla yeniden yüklenir. Gözcü: tests/ortam_sizinti_gozcusu.py"""
    once = {k: os.environ.get(k) for k in _ORTAM_ANAHTARLARI}
    yield
    for k, v in once.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import servers.jeton as j

    importlib.reload(j)


def _yeni(tmp_path, **env):
    """Modülü TEMİZ ortamla yeniden yükle (bayraklar import zamanında okunuyor)."""
    ortam = {"PEMF_JETON_ENFORCED": "0", "PEMF_DATA_DIR": str(tmp_path)}
    ortam.update(env)
    for k, v in ortam.items():
        os.environ[k] = v
    import servers.jeton as j

    importlib.reload(j)
    # T3 · Y194: jeton KOD düzeyinde kapalı (`JETON_SAHIP_ACIK = False`, ortam yok sayılır) → ücretlendirme mantığı burada sahip
    # anahtarı açılmış gibi sınanır (satış açılınca geçerli olacak davranış).
    j.JETON_ENFORCED = os.environ.get("PEMF_JETON_ENFORCED") == "1"
    return j


# ─────────────────────── 1) TIBBİ GÜVENLİK DEĞİŞMEZİ ───────────────────────


class _Istek:
    """`_jeton_kapisi_karari`nın kullandığı en küçük Request yüzeyi. ⚠️ "test-jwt" `sub` TAŞIMAZ → zorlama açıkken analiz yolu
    kimlik reddi (402 `kimlik_yok`) alır; kimlikli analiz için `_IstekKimlikli`."""

    def __init__(self, path: str):
        self.url = type("U", (), {"path": path})()
        self.headers = {"authorization": "Bearer test-jwt"}


class _IstekKimlikli(_Istek):
    """`sub` taşıyan JWT ({"sub": "test-kullanici"}) — kapı kimliği çözer, karar bakiye/internet üzerinden verilir."""

    def __init__(self, path: str):
        super().__init__(path)
        self.headers = {"authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LWt1bGxhbmljaSJ9.imza"}


_GUVENLIK_YOLLARI_ORNEK = (
    "/api/session/start",
    "/api/session/stop",
    "/api/hardware/emergency_stop",
    "/api/coil/6/control",
    "/api/ai/pro/stop",
)


def test_KRITIK_GUVENLIK_seans_ve_acil_durdurma_ASLA_kapilanmaz(tmp_path, monkeypatch):
    """Jeton bitse bile tedavi tarafı çalışır. Bu, ürünün pazarlık edilemez değişmezi.

    ⚠️ D4.11 (B-2.14): bu test eskiden `izin("acil_durdur")` gibi ADLARI soruyordu (`GUVENLIK_YOLLARI`); üretimde `izin()`e
    yalnız `_islem_turu`nun MALIYET anahtarları gelir → ÖLÜ değeri koruyordu. Artık GERÇEK kapı gövdesi gerçek YOLLARLA
    (bayrak açık, bakiye 0, bakiye okuması sayılır). Uygulamanın tüm rotaları: test_jeton_kapisi_TUM_ROTALARDA_…_D411.py."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    okumalar: list = []
    monkeypatch.setattr(j, "_bakiye_satiri_oku", lambda token: (okumalar.append(token), {"aylik_hak": 0})[1])

    for yol in _GUVENLIK_YOLLARI_ORNEK:
        assert j._islem_turu(yol) is None, f"jeton kapısı GÜVENLİK yolunu ücretli sınıfa eşledi: {yol}"
        j._jeton_kapisi_karari(_Istek(yol))  # 402 fırlatmamalı
    assert not okumalar, f"güvenlik yolu için bakiye okundu (ağ çağrısı) — {okumalar}"


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


def test_KRITIK_sunucuya_ULASILAMAZSA_analiz_BASLATILMAZ_S4B5(tmp_path):
    """S-4B.5 + S-4BI.8 (sahip kararı 2026-10-19 "internetsizken analiz yapılmasın"): bakiye okunamıyor (internet yok) → yeni analiz
    BAŞLATILMAZ, deftere / sunucuya tüketim YAZILMAZ (eskiden: çevrimdışı tavana kadar izin + borç kaydı). Mesaj nedenini ve tedavinin
    etkilenmediğini söyler."""

    def patlayan():
        raise ConnectionError("ağ yok")

    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    gonderilen: list = []
    y = j.JetonYoneticisi(bakiye_okuyucu=patlayan, tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1])

    karar = y.izin("goruntu")
    assert not karar.izinli and karar.sebep == "cevrimdisi", f"internetsiz analiz izin aldı: {karar}"
    assert "internet gerekir" in karar.mesaj and "ETKİLENMEZ" in karar.mesaj, karar.mesaj
    assert y.bekleyen_tuketim_sayisi() == 0 and not gonderilen, "internetsiz analiz deftere / sunucuya tüketim yazdı"


def test_KARSIT_bayrak_KAPALIYKEN_internetsiz_analiz_SERBEST(tmp_path):
    """İnternet şartı YALNIZ ücretlendirme açıkken (sahip seçimi): bugünkü ücretsiz kipte internetsiz klinik analiz yapar."""

    def patlayan():
        raise ConnectionError("ağ yok")

    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="0")
    y = j.JetonYoneticisi(bakiye_okuyucu=patlayan, tuketim_gonderici=lambda **k: False)
    assert y.izin("goruntu").izinli, "ücretlendirme KAPALIYKEN internetsiz analiz engellendi (bugünkü davranış bozuldu)"


def test_KRITIK_kapida_internetsiz_analiz_402_SEBEP_basligi_ve_tedavi_SERBEST(tmp_path, monkeypatch):
    """GERÇEK kapı gövdesi: internet yok → 402 + `X-PEMF-Jeton-Sebep: cevrimdisi` (arayüz "İnternet bağlantısı gerekli" başlığını
    seçer); ACİL DURDUR yolu kapıya hiç girmez. (Eski sürüm `sub`'sız jetonla ölçüyordu — 402'yi kimlik reddi veriyordu, kördü.)"""
    from fastapi import HTTPException

    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")

    def patlayan(token):
        raise ConnectionError("ağ yok")

    monkeypatch.setattr(j, "_bakiye_satiri_oku", patlayan)
    with pytest.raises(HTTPException) as ex:
        j._jeton_kapisi_karari(_IstekKimlikli("/api/ai/vision/landmark"))
    assert ex.value.status_code == 402
    assert (ex.value.headers or {}).get(j.JETON_SEBEP_BASLIGI) == "cevrimdisi", ex.value.headers
    assert "internet gerekir" in str(ex.value.detail), ex.value.detail
    assert j._jeton_kapisi_karari(_IstekKimlikli("/api/hardware/emergency_stop")) is None  # 402 fırlatmamalı


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


def test_KRITIK_yolda_kalan_odeme_UZLASTIRILIR_ve_defterden_dusulur(tmp_path):
    """ "Bir süre yeniden dene" (sahip, 2026-10-19): analiz çevrimiçi karar aldı ve teslim edildi ama düşüm tam o an gönderilemedi →
    kayıt defterde bekler; bağlantı gelince gönderilir, başarılı olanlar defterden silinir."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 100, tuketim_gonderici=lambda **k: False)
    assert y.izin("goruntu").izinli and y.izin("ses").izinli, "düşüm gönderilemedi diye teslim edilen analiz reddedildi"
    assert y.bekleyen_tuketim_sayisi() == 2, "gönderilemeyen düşüm deftere yazılmadı (yolda kalan ödeme kayboldu)"

    gonderilen = []
    y2 = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 100,
        tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1],
    )
    gonderilen_sayisi = y2.bekleyenleri_uzlastir()
    assert gonderilen_sayisi == 2, "yolda kalan ödeme uzlaştırılmadı"
    assert y2.bekleyen_tuketim_sayisi() == 0, "uzlaşan kayıtlar defterden düşmedi"


def test_KARSIT_KANIT_uzlastirma_GECICI_hatada_kayit_KORUNUR(tmp_path):
    """Aşırı-düzeltme koruması: gönderim (ağ / 5xx) düşerse kayıt silinseydi tüketim SESSİZCE kaybolurdu."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 100, tuketim_gonderici=lambda **k: False)
    y.izin("goruntu")
    assert y.bekleyen_tuketim_sayisi() == 1

    y2 = j.JetonYoneticisi(bakiye_okuyucu=lambda: 100, tuketim_gonderici=lambda **k: False)
    y2.bekleyenleri_uzlastir()
    assert y2.bekleyen_tuketim_sayisi() == 1, "gönderim başarısızken kayıt silindi — tüketim kayboldu"


def test_KRITIK_uzlastirmada_KESIN_red_kaydi_DUSURUR_eksi_bakiye_YOK_S4BI8(tmp_path, monkeypatch):
    """S-4BI.8 (sahip "eksi bakiyeyi temizleyelim"): sunucu kaydı KESİN reddederse (`yetersiz`) kayıt defterden düşer ve günlüğe
    yazılır (eskiden Y24: bakiye yüklenene dek "eksi bakiye" olarak bekliyor, her uzlaştırmada yeniden reddediliyordu). Aynı turda
    GEÇİCİ hata alan kayıt KALIR."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 100, tuketim_gonderici=lambda **k: False)
    y.izin("goruntu")
    y.izin("ses")
    uyarilar: list = []
    monkeypatch.setattr(j.logger, "warning", lambda m, *a, **k: uyarilar.append(m % a if a else m))
    y2 = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: j.TUKETIM_REDDEDILDI if k.get("detay") == "goruntu" else False,
    )
    assert y2.bekleyenleri_uzlastir() == 0, "kesin red 'gönderildi' sayıldı"
    assert [k.get("detay") for k in y2._defteri_oku()] == ["ses"], (
        "kesin reddedilen kayıt defterde kaldı (eksi bakiye) ya da geçici hata alan kayıt silindi"
    )
    assert any("KESİN reddedildi" in u for u in uyarilar), f"kesin red günlüğe yazılmadı: {uyarilar}"


def test_KRITIK_yolda_kalan_odeme_SONRAKI_kararda_BAKIYEDEN_dusulur(tmp_path):
    """Bakiye 1: analiz teslim edildi, düşüm gönderilemedi (sunucu hâlâ 1 der). Sonraki analiz o jetonu ALAMAZ — alsaydı yolda kalan
    ödeme uzlaştırmada `yetersiz` alıp düşer, bir analiz BEDAVA olurdu. Defter sahibe bağlı: başka hesabın bakiyesi etkilenmez."""
    j = _yeni(tmp_path, PEMF_JETON_ENFORCED="1")
    y = j.JetonYoneticisi(bakiye_okuyucu=lambda: 1, tuketim_gonderici=lambda **k: False, sahip="sahip-1")
    assert y.izin("goruntu").izinli and y.bekleyen_tuketim_sayisi() == 1
    ikinci = j.JetonYoneticisi(bakiye_okuyucu=lambda: 1, tuketim_gonderici=lambda **k: True, sahip="sahip-1").izin(
        "goruntu"
    )
    assert not ikinci.izinli and ikinci.sebep == "yetersiz", (
        f"yolda kalan ödeme sayılmadı — aynı jeton iki analize: {ikinci}"
    )
    baska = j.JetonYoneticisi(bakiye_okuyucu=lambda: 1, tuketim_gonderici=lambda **k: True, sahip="sahip-2").izin(
        "goruntu"
    )
    assert baska.izinli, "bir hesabın yolda kalan ödemesi başka hesabın bakiyesinden düşüldü"


def test_KARSIT_KANIT_maliyet_tablosu_WEB_ile_AYNI(tmp_path):
    """İki taraf ayrışırsa kullanıcı sitede '1 jeton' okuyup cihazda 3 harcar."""
    import json
    import re
    from pathlib import Path

    j = _yeni(tmp_path)
    web = (Path(__file__).resolve().parent.parent / "apps/web" / "src" / "config.ts").read_text(
        encoding="utf-8", errors="replace"
    )
    m = re.search(r"maliyet:\s*\{([^}]*)\}", web)
    assert m, "web tarafında JETON.maliyet bulunamadı"
    web_maliyet = dict(re.findall(r"(\w+):\s*(\d+)", m.group(1)))
    for ad, deger in web_maliyet.items():
        assert ad in j.MALIYET, f"cihaz tarafında '{ad}' maliyeti tanımsız"
        assert j.MALIYET[ad] == int(deger), f"'{ad}' maliyeti ayrıştı: web={deger} cihaz={j.MALIYET[ad]}"
    assert json.dumps(sorted(web_maliyet)) == json.dumps(sorted(j.MALIYET)), "maliyet anahtarları ayrıştı"
