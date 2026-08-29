# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""mDNS ADI ÇAKIŞMAZ VE HATA GÖRÜNÜR — denetim 2026-08-28 #08.

ÖLÇÜLEN ARIZA (gerçek LAN'da, bu makinede):
  * `start_mdns` servisi SABİT `PEMF-Vet` adıyla kaydediyordu; aynı ağdaki ikinci cihazda
    `register_service` → `NonUniqueNameException`.
  * Kritik olan ad değil SIRAYDI: `_mdns_started = True` ve `add_reregister_callback(...)`
    kayıt denemesinden SONRA yazılmıştı. İstisna ikisini de atlıyor → `_reregister` süreç
    ömrü boyunca guard'a takılıp no-op oluyor VE callback zaten hiç kaydedilmemiş oluyordu.
    Yani arayüz/IP değişiminde de toparlanma YOKTU: cihaz o oturumda mDNS'te hiç görünmüyordu.
  * Teşhis körlüğü: zeroconf 0.148'de `NonUniqueNameException` dâhil tüm `Error` alt
    sınıflarının `str(e)` değeri BOŞ. Canlı logda `mDNS başlatılamadı:` 12 kez geçiyordu ve
    12'sinin de mesajı boştu — destek hangi hatayı aldığını ayırt edemiyordu.

⚠️ `allow_name_change=True` YETERSİZ (ölçüldü): zeroconf yalnız `info.name`i değiştirir,
`server=` hostname'i (A kaydı) hâlâ çakışır. Bu yüzden ad, kaynağında benzersizleştirilir.

⚠️ KORUNAN DAVRANIŞLAR: loopback (127.*) YAYINLANMAZ; `stop_mdns` sonrası callback kasıtlı
kaldırılan servisi DİRİLTMEZ.
"""

from __future__ import annotations

import logging

import pytest

from servers import auto_discovery as ad

# ── 1) Ad benzersiz ve kararlı ───────────────────────────────────────────────


def test_KRITIK_mdns_adi_SABIT_DEGIL():
    """Ad, taban addan farklı olmalı — aksi hâlde iki cihaz aynı adı iddia eder."""
    assert ad._mdns_ad("PEMF-Vet") != "PEMF-Vet", (
        "mDNS adı hâlâ sabit — aynı ağdaki ikinci cihazda NonUniqueNameException"
    )
    assert ad._mdns_ad("PEMF-Vet").startswith("PEMF-Vet-"), "taban ad korunmalı (keşif filtreleri buna bakar)"


def test_KRITIK_ad_KARARLI():
    """Her açılışta değişen ad ağda çöp kayıt biriktirir ve hostname'i oynatır."""
    assert ad._mdns_ad("PEMF-Vet") == ad._mdns_ad("PEMF-Vet")


def test_KRITIK_ham_cihaz_kimligi_YAYINLANMAZ():
    """device_id tenant anahtarıdır; mDNS LAN'a multicast eder → yalnız geri-döndürülemez özet."""
    from utils.path_utils import get_unique_device_id

    kimlik = str(get_unique_device_id() or "")
    adi = ad._mdns_ad("PEMF-Vet")
    if kimlik:
        assert kimlik not in adi, f"ham device_id mDNS adında yayınlanıyor: {adi}"


def test_env_ile_taban_ad_degistirilebilir(monkeypatch):
    monkeypatch.setenv("PEMF_DEVICE_NAME", "Klinik-A")
    assert ad._mdns_ad("PEMF-Vet").startswith("Klinik-A-")


def test_ad_uretimi_HICBIR_KOSULDA_patlamaz(monkeypatch):
    """Kimlik okunamazsa bugünkü davranışa düşer, istisna fırlatmaz."""
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "get_unique_device_id", lambda *a, **k: (_ for _ in ()).throw(OSError("yok")))
    assert ad._mdns_ad("PEMF-Vet")  # boş olmayan bir ad dönmeli


# ── 2) Hata metni körlüğü ────────────────────────────────────────────────────


def test_KRITIK_bos_istisna_TIP_ADIYLA_loglanir():
    """zeroconf istisnalarının str()'i boş — tip adı olmadan log işe yaramaz."""

    class _BosHata(Exception):
        def __str__(self):
            return ""

    assert ad._hata_metni(_BosHata()) == "_BosHata"
    assert ad._hata_metni(ValueError("gercek mesaj")) == "ValueError: gercek mesaj"


# ── 3) Kayıt çakışmasında toparlanma ─────────────────────────────────────────


class _CakisanZeroconf:
    """`register_service` daima çakışma atan sahte Zeroconf."""

    def __init__(self):
        self.denemeler = 0

    def register_service(self, info, *a, **k):
        self.denemeler += 1
        raise RuntimeError()  # str() boş: gerçek NonUniqueNameException gibi

    def unregister_service(self, *a, **k):
        pass


def test_KRITIK_ad_cakismasi_TOPARLANMAYI_OLDURMEZ(monkeypatch, caplog):
    """Bulgunun özü: kayıt patlasa bile bayrak + callback kurulmalı.

    Eskiden istisna tek dıştaki except'e düşüyor, `_mdns_started` False kalıyor ve callback
    hiç kaydedilmiyordu → cihaz o oturum boyunca mDNS'te GÖRÜNMÜYORDU."""
    import utils.zeroconf_singleton as zs

    sahte = _CakisanZeroconf()
    kayitlar = []
    monkeypatch.setattr(zs, "get_shared_zeroconf", lambda *a, **k: sahte)
    monkeypatch.setattr(zs, "add_reregister_callback", lambda cb: kayitlar.append(cb))
    monkeypatch.setattr(ad, "_get_local_ip", lambda *a, **k: "192.168.1.37")
    monkeypatch.setattr(ad, "_mdns_started", False, raising=False)

    with caplog.at_level(logging.WARNING, logger="servers.auto_discovery"):
        sonuc = ad.start_mdns(port=8000, device_name="PEMF-Vet")

    assert sahte.denemeler == 1, "kayıt hiç denenmedi"
    assert sonuc is True, "kayıt çakışması tüm mDNS başlatmayı düşürdü (eski davranış)"
    assert ad._mdns_started is True, (
        "_mdns_started False kaldı → _reregister süreç ömrü boyunca no-op olur (bulgunun ta kendisi)"
    )
    assert kayitlar, "re-register callback'i kaydedilmedi → arayüz değişiminde toparlanma YOK"
    # Hata görünür olmalı ve tip adını taşımalı.
    mesajlar = " ".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in mesajlar, f"çakışma hatası tip adıyla loglanmadı: {mesajlar!r}"

    ad._mdns_started = False  # test sonrası global durumu bırakma


class _KaydedenZeroconf:
    """Kaydı BAŞARIYLA alan ve ServiceInfo'yu saklayan sahte Zeroconf."""

    def __init__(self):
        self.kayitlar = []

    def register_service(self, info, *a, **k):
        self.kayitlar.append(info)

    def unregister_service(self, *a, **k):
        pass


def test_KRITIK_start_mdns_BENZERSIZ_adi_GERCEKTEN_kullaniyor(monkeypatch):
    """⚠️ ZAYIF-ÇIPA KORUMASI: `_mdns_ad()` doğru olabilir ama `start_mdns` onu ÇAĞIRMIYORSA
    hiçbir şey değişmez. Ölçüldü: `device_name = _mdns_ad(device_name)` satırı silindiğinde
    saf-fonksiyon testleri YEŞİL kalıyordu. Bu test kablolamayı kilitler: gerçekten kaydedilen
    ServiceInfo'nun adına bakar."""
    import utils.zeroconf_singleton as zs

    sahte = _KaydedenZeroconf()
    monkeypatch.setattr(zs, "get_shared_zeroconf", lambda *a, **k: sahte)
    monkeypatch.setattr(zs, "add_reregister_callback", lambda cb: None)
    monkeypatch.setattr(ad, "_get_local_ip", lambda *a, **k: "192.168.1.37")
    monkeypatch.setattr(ad, "_mdns_started", False, raising=False)

    ad.start_mdns(port=8000, device_name="PEMF-Vet")
    ad._mdns_started = False

    assert sahte.kayitlar, "hiç kayıt yapılmadı"
    info = sahte.kayitlar[0]
    assert not info.name.startswith("PEMF-Vet._"), (
        f"SABİT ad kaydedildi ({info.name}) — iki cihaz aynı adı iddia eder, benzersizleştirme start_mdns'e BAĞLANMAMIŞ"
    )
    assert info.name.startswith("PEMF-Vet-"), f"taban ad korunmamış: {info.name}"
    assert str(info.server).startswith("PEMF-Vet-"), (
        f"server (A kaydı) benzersizleştirilmemiş: {info.server} — allow_name_change'in yetmediği nokta"
    )


def test_KARSIT_KANIT_loopback_YAYINLANMAZ(monkeypatch):
    """Korunan değişmez: 127.* asla ServiceInfo'ya girmez (telefon kendi loopback'ine gider)."""
    import utils.zeroconf_singleton as zs

    sahte = _CakisanZeroconf()
    monkeypatch.setattr(zs, "get_shared_zeroconf", lambda *a, **k: sahte)
    monkeypatch.setattr(zs, "add_reregister_callback", lambda cb: None)
    monkeypatch.setattr(ad, "_get_local_ip", lambda *a, **k: "127.0.0.1")
    monkeypatch.setattr(ad, "_mdns_started", False, raising=False)

    assert ad.start_mdns(port=8000) is True
    assert sahte.denemeler == 0, "loopback IP ile kayıt DENENDİ — korunan değişmez ihlali"
    ad._mdns_started = False


def test_build_info_adi_HEM_name_HEM_server_icin_kullanir():
    """`allow_name_change` yetersizliğinin sebebi: hostname de çakışıyor."""
    pytest.importorskip("zeroconf")
    info = ad._build_info("192.168.1.37", 8000, "PEMF-Vet-abc123")
    assert info.name.startswith("PEMF-Vet-abc123.")
    assert str(info.server).startswith("PEMF-Vet-abc123."), "server (A kaydı) benzersizleştirilmemiş"
