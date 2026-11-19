# -*- coding: utf-8 -*-
"""D4.23 (B-2.15 · B-2.16 · Y24) — çevrimdışı jeton defteri: bekleyen sayısı GERÇEK, bağlantı dönünce uzlaşır.

ARIZA 1 (B-2.15): `bakiye_ozeti`nin çevrimdışı dalı `JetonYoneticisi()` ARGÜMANSIZ kuruyordu; kurucu iki zorunlu argüman ister →
`TypeError` yutuluyor, uç defterde kayıt varken HER ZAMAN `bekleyen: 0` diyordu (4-A incelemesi 4A-1.3 ölçtü).
ARIZA 2 (B-2.16): `bekleyenleri_uzlastir` tanımlıydı ama HİÇBİR üretim yolu çağırmıyordu → zorlama açılınca defter hiç uzlaşmaz, 50
çevrimdışı analizden sonra analizler kalıcı tavana takılır, tüketim faturalanmaz.
Y24 (önerilen, uygulandı): çevrimdışı tüketim bağlantı dönünce GERİYE DÖNÜK düşülür ve ekranda gösterilir (rozet sunucu bakiyesini
gösterir; `bekleyen` alanı uzlaşmamış sayıyı söyler).

Ölçüm: GERÇEK `bakiye_ozeti` / `_jeton_kapisi_karari` üretim yolları; Supabase taşıma katmanı (`_bakiye_satiri_oku`,
`_tuketim_gonder_canli`) sahte — canlı Supabase YOK. Defter gerçek dosya (`PEMF_DATA_DIR` = tmp_path).
2026-10-19 (S-4B.5 + S-4BI.8): çevrimdışı analiz kaldırıldı — defterde yalnız YOLDA KALAN ÖDEME olur (çevrimiçi karar, düşüm o an
gönderilemedi); uzlaştırma sözleşmesi aynen, yalnız sunucunun KESİN reddi (`yetersiz`) kaydı artık DÜŞÜRÜR (eksi bakiye yok).
"""

from __future__ import annotations

import base64
import importlib
import json
import threading

import pytest


def _jwt(sub: str) -> str:
    """D4.23 eki: uzlaştırma kaydı TÜKETENE bağlı → test jetonları `sub` taşıyan JWT biçiminde (imza önemsiz)."""
    from jwt_test_anahtari import imzali_jwt  # TA T4: GERÇEK ES256 imza (JWKS doğrulaması)

    return imzali_jwt({"sub": sub})


def _sub(token: str) -> str:
    govde = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(govde + "=" * (-len(govde) % 4)))["sub"]


class _SahteIstek:
    def __init__(self, token: str, yol: str = "/api/jeton/bakiye"):
        self.headers = {"authorization": f"Bearer {_jwt(token)}"} if token else {}
        self.url = type("U", (), {"path": yol})()


@pytest.fixture
def j(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    mod = importlib.import_module("servers.jeton")
    monkeypatch.setattr(mod, "JETON_ENFORCED", True)
    # Önceki testin ipliği bu testin "uzlaştırma başladı" iddiasını SAHTE-YEŞİL yapmasın.
    monkeypatch.setattr(mod, "_son_uzlastirma", None, raising=False)
    yield mod
    t = getattr(mod, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _defter_yaz(j, kayitlar, sub):
    """Kayıtlar `sub` kullanıcısının çevrimdışı tüketimi (sahip özeti ürünün türetmesiyle — kimlik bağlama ayrıca D4.23b'de ölçülür)."""
    sahip = j._jwt_sahip(_jwt(sub))
    j._defter_yolu().write_text(json.dumps([{**k, "sahip": sahip} for k in kayitlar]), encoding="utf-8")


def _defter(j):
    return json.loads(j._defter_yolu().read_text(encoding="utf-8") or "[]")


def _cevrimici(j, monkeypatch, gonderilen, cevap=lambda k: True, bekle=None):
    monkeypatch.setattr(
        j, "_bakiye_satiri_oku", lambda _t: {"aylik_hak": 10, "satin_alinan": 0, "odeme_modeli": "on_odemeli"}
    )

    def _gonder(token, **k):
        if bekle is not None:
            assert bekle.wait(10), "test: uzlaştırma kapısı açılmadı"
        gonderilen.append((_sub(token), k.get("istek_id")))
        return cevap(k)

    monkeypatch.setattr(j, "_tuketim_gonder_canli", _gonder)


def _bitir(j):
    t = getattr(j, "_son_uzlastirma", None)
    assert t is not None, "bağlantı döndüğü hâlde uzlaştırma BAŞLATILMADI (hiçbir üretim yolu çağırmıyor)"
    t.join(timeout=10)
    assert not t.is_alive(), "uzlaştırma 10 sn'de bitmedi"


def test_KRITIK_cevrimdisi_bakiye_ozeti_defterdeki_BEKLEYEN_sayisini_soyler_B2_15(j, monkeypatch):
    monkeypatch.setattr(j, "_bakiye_satiri_oku", lambda _t: (_ for _ in ()).throw(ConnectionError("ag yok")))
    _defter_yaz(
        j, [{"istek_id": "a-1", "miktar": 1}, {"istek_id": "a-2", "miktar": 3}, {"istek_id": "a-3", "miktar": 1}], "tok"
    )
    ozet = j.bakiye_ozeti(_SahteIstek("tok"))
    assert ozet.get("bilinmiyor") is True and ozet.get("sebep") == "cevrimdisi", ozet
    assert ozet.get("bekleyen") == 3, f"defterde 3 bekleyen tüketim var ama uç {ozet.get('bekleyen')!r} diyor"


def test_KRITIK_baglanti_DONUNCE_bakiye_ozeti_defteri_UZLASTIRIR_B2_16(j, monkeypatch):
    gonderilen = []
    _cevrimici(j, monkeypatch, gonderilen)
    _defter_yaz(
        j,
        [{"istek_id": "b-1", "miktar": 1, "tur": "analiz"}, {"istek_id": "b-2", "miktar": 3, "tur": "analiz"}],
        "tok-1",
    )
    ozet = j.bakiye_ozeti(_SahteIstek("tok-1"))
    assert ozet.get("bilinmiyor") is False and ozet.get("bekleyen") == 2, ozet
    _bitir(j)
    assert sorted(gonderilen) == [("tok-1", "b-1"), ("tok-1", "b-2")], gonderilen
    assert _defter(j) == [], "uzlaşan kayıtlar defterden düşmedi"


def test_KRITIK_baglanti_DONUNCE_analiz_kapisi_da_UZLASTIRIR_B2_16(j, monkeypatch):
    gonderilen = []
    _cevrimici(j, monkeypatch, gonderilen)
    _defter_yaz(j, [{"istek_id": "c-1", "miktar": 1, "tur": "analiz"}], "tok-2")
    j._jeton_kapisi_karari(_SahteIstek("tok-2", "/api/ai/vision/wound"))
    _bitir(j)
    assert ("tok-2", "c-1") in gonderilen and all(i != "c-1" for i in (k.get("istek_id") for k in _defter(j))), (
        gonderilen,
        _defter(j),
    )


def test_KRITIK_uzlastirma_SIRASINDA_eklenen_tuketim_KAYBOLMAZ(j, monkeypatch):
    """Uzlaştırma arka planda; o arada bir analizin tüketimi deftere düşerse yeniden yazımda SİLİNMEMELİ (bedava analiz olurdu)."""
    gonderilen = []
    kapi = threading.Event()
    _cevrimici(j, monkeypatch, gonderilen, bekle=kapi)
    _defter_yaz(j, [{"istek_id": "d-1", "miktar": 1, "tur": "analiz"}], "tok-3")
    j.bakiye_ozeti(_SahteIstek("tok-3"))
    y = j._defter_yoneticisi()
    y._bekleyene_ekle({"istek_id": "d-YENI", "miktar": 1, "tur": "analiz", "detay": "goruntu", "cihaz_id": None})
    kapi.set()
    _bitir(j)
    kalan = [k.get("istek_id") for k in _defter(j)]
    assert kalan == ["d-YENI"], (
        f"uzlaştırma sırasında eklenen tüketim defterden SİLİNDİ ya da gönderilen kaldı: {kalan}"
    )


def test_KRITIK_uzlastirma_TEK_UCUS(j, monkeypatch):
    gonderilen = []
    kapi = threading.Event()
    _cevrimici(j, monkeypatch, gonderilen, bekle=kapi)
    _defter_yaz(j, [{"istek_id": "e-1", "miktar": 1, "tur": "analiz"}], "tok-4")
    j.bakiye_ozeti(_SahteIstek("tok-4"))
    ilk = j._son_uzlastirma
    j.bakiye_ozeti(_SahteIstek("tok-4"))
    assert j._son_uzlastirma is ilk, "süren uzlaştırma varken İKİNCİSİ başlatıldı"
    kapi.set()
    _bitir(j)
    assert [i for _, i in gonderilen] == ["e-1"], f"aynı kayıt birden çok gönderildi: {gonderilen}"


def test_KARSIT_hala_CEVRIMDISI_iken_uzlastirma_DENENMEZ(j, monkeypatch):
    gonderilen = []
    monkeypatch.setattr(j, "_bakiye_satiri_oku", lambda _t: (_ for _ in ()).throw(ConnectionError("ag yok")))
    monkeypatch.setattr(j, "_tuketim_gonder_canli", lambda t, **k: gonderilen.append(k) or True)
    _defter_yaz(j, [{"istek_id": "f-1", "miktar": 1}], "tok-5")
    j.bakiye_ozeti(_SahteIstek("tok-5"))
    assert j._son_uzlastirma is None and not gonderilen and len(_defter(j)) == 1


def test_KARSIT_gonderilemeyen_kayit_KORUNUR(j, monkeypatch):
    gonderilen = []
    _cevrimici(j, monkeypatch, gonderilen, cevap=lambda k: k.get("istek_id") != "g-2")
    _defter_yaz(j, [{"istek_id": "g-1", "miktar": 1}, {"istek_id": "g-2", "miktar": 1}], "tok-6")
    j.bakiye_ozeti(_SahteIstek("tok-6"))
    _bitir(j)
    assert [k.get("istek_id") for k in _defter(j)] == ["g-2"], "başarısız gönderim defterden silindi (tüketim kaybolur)"


def test_KRITIK_uzlastirmada_KESIN_red_kaydi_DUSURUR_gecici_hata_KORUR_S4BI8(j, monkeypatch):
    """Arka plan uzlaştırması (gerçek tetik): `yetersiz` alan kayıt düşer (eksi bakiye tutulmaz), geçici hata alan kalır."""
    gonderilen = []
    _cevrimici(
        j, monkeypatch, gonderilen, cevap=lambda k: j.TUKETIM_REDDEDILDI if k.get("istek_id") == "h-1" else False
    )
    _defter_yaz(j, [{"istek_id": "h-1", "miktar": 1}, {"istek_id": "h-2", "miktar": 1}], "tok-8")
    j.bakiye_ozeti(_SahteIstek("tok-8"))
    _bitir(j)
    assert sorted(i for _, i in gonderilen) == ["h-1", "h-2"], gonderilen
    assert [k.get("istek_id") for k in _defter(j)] == ["h-2"], (
        "kesin red defterde kaldı ya da geçici hata alan kayıt silindi"
    )


def test_KARSIT_bayrak_KAPALIYKEN_hicbir_sey_yapilmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    mod = importlib.import_module("servers.jeton")
    monkeypatch.setattr(mod, "JETON_ENFORCED", False)
    monkeypatch.setattr(mod, "_son_uzlastirma", None, raising=False)
    monkeypatch.setattr(mod, "_bakiye_satiri_oku", lambda _t: pytest.fail("bayrak kapalıyken ağ çağrısı"))
    assert mod.bakiye_ozeti(_SahteIstek("tok-7")) == {"etkin": False}
    assert mod._son_uzlastirma is None
