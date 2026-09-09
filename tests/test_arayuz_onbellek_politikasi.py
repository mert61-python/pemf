# -*- coding: utf-8 -*-
# Author: mertaygn
"""ARAYÜZ ÖNBELLEK POLİTİKASI — sessiz güncelleme sonrası "karışık yapı" açılışını engeller.

ÖLÇÜLEN SAHA ARIZASI (2026-09-09, sahibin masaüstü istemcisi): Kontrol ekranı açılırken
tam-ekran "Beklenmeyen bir hata oluştu — Loading module .../ControlScreen-<hash>.js failed"
çıkıyordu. `client_errors.jsonl` gerçek hatayı kaydetmiş:

    15:21:55  [FATAL] Requiring unknown module "2642".
    15:36:37  [FATAL] Requiring unknown module "2636".

TEŞHİS (ölçüldü, tahmin değil):
  · İstenen chunk diskte İSTENEN HASH'LE vardı ve HTTP 200 dönüyordu → dosya kaybı DEĞİL.
  · `base-app.zip` 15:21'de kuruldu; sunulan 13 chunk'ın hepsi 15:21 damgalı, aynı ekranın
    ikinci bir hash'i yok → diskte karışık yapı YOK.
  · İlk FATAL kurulumdan 34 saniye sonra.
  · "Requiring unknown module" YALNIZCA paketin iki yarısı farklı yapılardan geldiğinde olur:
    Metro modül numaralarını (2636 gibi) her yapıda yeniden atar.
  · `curl -I /` ölçümü: `last-modified` + `etag` VAR, **`Cache-Control` YOK**.

KÖK NEDEN: `Cache-Control` göndermeyen yanıta tarayıcı SEZGİSEL tazelik uygular
(RFC 9111 §4.2.2) → WebView2 `index.html`i doğrulamadan yeniden kullanabiliyor. Güncelleme
`entry-*`/`__common-*` hash'lerini değiştirdiği için önbellekten gelen ESKİ sayfa YENİ
chunk'larla karışıyor. Sessiz oto-güncelleme + sezgisel önbellek = her açılışta FATAL.

NE KİLİTLENİYOR: giriş belgesi (`*.html`) ASLA önbellekten gelmez → sayfa ve chunk'lar her
zaman AYNI yapıdan. Hash'li varlıklar 1 yıl `immutable` KALIR; ⚠️ onları da `no-store` yapmak
arızayı "çözer" ama her açılışta tüm paketi yeniden indirtir (klinik hotspot'ta ölçülür bir
bedel) — bu yüzden testler İKİ YÖNÜ de kilitler.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
DIST = KOK / "frontend" / "dist"

pytestmark = pytest.mark.skipif(not (DIST / "index.html").exists(), reason="frontend/dist yok (yalniz backend agaci)")


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app, client=("127.0.0.1", 51247))


def _hashli_varlik() -> str:
    """Sunulan dizinden GERÇEK bir içerik-hash'li dosya yolu seç (çıpa sabit yazılmaz)."""
    kok = DIST / "_expo" / "static" / "js" / "web"
    adaylar = sorted(kok.glob("*-*.js")) if kok.is_dir() else []
    assert adaylar, "hash'li chunk bulunamadi -> kapi BAYAT (dist duzeni degismis olabilir)"
    return "/" + str(adaylar[0].relative_to(DIST)).replace("\\", "/")


# ══ 1) SAF POLİTİKA ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "yol,beklenen",
    [
        ("index.html", "no-store"),
        ("alt/dizin/index.html", "no-store"),
        ("_expo/static/js/web/ControlScreen-bc3e94fba28746f941f61e99bfb58484.js", "immutable"),
        ("_expo/static/js/web/entry-b1a7252d99a5a371ac5ff51ed2f72f75.js", "immutable"),
        # Expo yazı tipleri hash'i NOKTAYLA ayırır; ikon dosyaları hash'ten sonra @2x taşır.
        ("assets/fonts/Inter_400Regular.51b6ad87261f18b6433ec52871ddfabc.ttf", "immutable"),
        ("assets/icons/clear-icon.c94f6478e7ae0cdd9f15de1fcb9e5e55@2x.png", "immutable"),
        ("metadata.json", "no-cache"),
        ("favicon.ico", "no-cache"),
        # ⚠️ YANLIŞ-POZİTİF KORUMASI: tarih benzeri sayı dizisi hash SAYILMAZ (16 haneli eşik).
        ("report-20260909.js", "no-cache"),
    ],
)
def test_politika_dogru_siniflandiriyor(api, yol, beklenen):
    assert beklenen in api._onbellek_politikasi(yol), api._onbellek_politikasi(yol)


def test_KRITIK_dizin_yolu_da_giris_belgesi_sayilir(api):
    """`/` isteğinde Starlette yol olarak "." verir; sınıflandırma İÇERİK TİPİNDEN yapılmalı.

    ⚠️ Bu vakayı kapı ilk koşuda yakaladı: yalnız dosya adına bakan sürüm giriş belgesine
    `no-cache` yazıyordu. Revalidasyon zorladığı için tehlikesizdi ama hedef `no-store`du;
    içerik tipi olmadan bu ayrım sessizce kaybolur.
    """
    assert "no-store" in api._onbellek_politikasi(".", "text/html; charset=utf-8")
    assert "no-store" in api._onbellek_politikasi("", "text/html")
    # Karşıt kanıt: içerik tipi html DEĞİLSE hash kuralı çalışmaya devam eder.
    assert "immutable" in api._onbellek_politikasi(
        "_expo/static/js/web/entry-b1a7252d99a5a371ac5ff51ed2f72f75.js", "text/javascript"
    )


def test_index_html_dogrudan_istenirse_de_no_store(client):
    """Hem `/` hem `/index.html` aynı politikayı almalı (iki giriş, tek davranış)."""
    r = client.get("/index.html")
    assert r.status_code == 200, r.status_code
    assert "no-store" in r.headers.get("cache-control", ""), r.headers.get("cache-control")


# ══ 2) GERÇEK HTTP BAŞLIKLARI (asıl kapı) ══════════════════════════════════════════════════
def test_KRITIK_index_html_ONBELLEKLENMEZ(client):
    """Giriş belgesi `no-store` olmalı — arızanın doğrudan pini.

    ⚠️ `Cache-Control` başlığı HİÇ yoksa da bu test kırmızı olur: ölçülen arıza tam olarak
    "başlık yok → tarayıcı sezgisel önbelleğe aldı" durumuydu.
    """
    r = client.get("/")
    assert r.status_code == 200, r.status_code
    cc = r.headers.get("cache-control", "")
    assert "no-store" in cc, f"index.html Cache-Control: {cc!r} (no-store bekleniyor)"


def test_KRITIK_hashli_chunk_UZUN_SURE_onbelleklenir(client):
    """KARŞIT KANIT: hash'li varlık `immutable` KALMALI.

    Bu test olmadan "her şeye no-store" mutasyonu birinci kapıyı YEŞİL yapardı ve her açılışta
    tüm paket yeniden inerdi (klinik hotspot'unda ölçülür yavaşlama).
    """
    yol = _hashli_varlik()
    r = client.get(yol)
    assert r.status_code == 200, (yol, r.status_code)
    cc = r.headers.get("cache-control", "")
    assert "immutable" in cc and "max-age=31536000" in cc, f"{yol} Cache-Control: {cc!r}"
    assert "no-store" not in cc, f"hash'li varlik no-store ile sunuluyor: {cc!r}"


def test_hashsiz_dosya_DOGRULAMAYA_zorlanir(client):
    """Hash'siz dosya (`metadata.json`) `no-cache` ile gelir → ETag'le 304, ama bayat kalmaz."""
    r = client.get("/metadata.json")
    if r.status_code == 404:
        pytest.skip("metadata.json bu dist'te yok")
    assert "no-cache" in r.headers.get("cache-control", ""), r.headers.get("cache-control")


def test_KRITIK_304_yanitinda_da_politika_VAR(client):
    """Koşullu istekte (ETag) dönen 304'te de başlık bulunmalı.

    ⚠️ `file_response`u sarmak yerine `get_response`u sarmanın sebebi bu: 304 ve 404 yolları
    `file_response`tan GEÇMEZ, dolayısıyla o kancaya konan politika koşullu isteklerde
    SESSİZCE düşerdi ve tarayıcı yine sezgisel davranırdı.
    """
    yol = _hashli_varlik()
    ilk = client.get(yol)
    etag = ilk.headers.get("etag")
    assert etag, "ETag yok -> kosullu istek olculemez"
    r = client.get(yol, headers={"if-none-match": etag})
    assert r.status_code == 304, r.status_code
    assert "immutable" in r.headers.get("cache-control", ""), r.headers.get("cache-control")


# ══ 3) MOUNT GERÇEKTEN POLİTİKALI SINIFI KULLANIYOR MU ═════════════════════════════════════
def test_KRITIK_MOUNTLAR_politikali_sinifi_kullanir(api):
    """Politika sınıfı tanımlı olup mount'ta KULLANILMAZSA hiçbir başlık değişmez (sessiz ölüm).

    Bu yüzden kapı sınıfın VARLIĞINA değil, mount edilmiş uygulama NESNESİNİN tipine bakar.
    """
    statik_mountlar = [(r.name, r.app) for r in api.app.routes if isinstance(getattr(r, "app", None), StaticFiles)]
    assert statik_mountlar, "hic StaticFiles mount'u bulunamadi -> kapi BAYAT"
    ciplak = [ad for ad, uygulama in statik_mountlar if not isinstance(uygulama, api.OnbellekPolitikaliStatik)]
    assert not ciplak, (
        f"bu mount'lar duz StaticFiles kullaniyor (Cache-Control YOK): {ciplak} — "
        "OnbellekPolitikaliStatik ile degistirin"
    )
