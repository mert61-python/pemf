# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Sessiz kayıt reddi UÇTAN UCA: kullanıcı SEBEBİNİ görebilmeli.

`tests/test_ses_kalite_kapisi.py` kapının eşiklerini kilitler; bu dosya kapının HTTP
katmanında doğru davrandığını doğrular — asıl tuzak burada:

⚠️ `_ai_fail` ham hata mesajlarını BİLEREK yutar ve istemciye yalnız kısa bir etiket döner
("Ses analiz hatası", 500) — auth-muaf uçlarda bilgi ifşasını önlemek için. Yani kapıyı düz
bir `ValueError` ile kurarsanız kullanıcı "Kayıt sessiz" mesajını ASLA GÖRMEZ; ekranda genel
bir hata belirir ve ne yapması gerektiğini bilemez. (Aynı tuzak görüntü uçlarında yaşanmış ve
`_ai_fail`'in HTTPException'ı aynen geçirmesiyle çözülmüştü — dosyanın kendi yorumu bunu
anlatıyor.) Bu yüzden kapı `HTTPException(422)` fırlatır ve BU TEST onu kilitler.
"""

import base64
import importlib.util
import io
import math
import os
import struct
import wave

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

SR = 22050

# ⚠️ Sessizlik kapısı ses ÇÖZMEYİ gerektirir (ffmpeg → 22050 Hz mono WAV → RMS). CI hafif
# bağımlılık setiyle koşuyor (`requirements-test.txt`); `imageio-ffmpeg` yalnız
# `requirements.txt`te. O modül yokken uç HİÇ çalışamaz (her ses isteği 500) — bu bir kapı
# arızası değil, ortam eksikliğidir. Eşik/karar mantığı zaten `test_ses_kalite_kapisi.py`
# (18 test) ile ffmpeg'siz doğrulanıyor; burada kilitlenen şey HTTP davranışıdır.
_FFMPEG_VAR = importlib.util.find_spec("imageio_ffmpeg") is not None
_ffmpeg_gerekir = pytest.mark.skipif(
    not _FFMPEG_VAR,
    reason="imageio_ffmpeg yok (CI hafif bağımlılık seti) — ses çözülemez, uç çalışamaz",
)


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


def _wav_b64(ornekler, sr=SR) -> str:
    """Örnekleri 16-bit PCM WAV'a yazıp base64 döndür (uç `audio_base64` kabul ediyor)."""
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, int(x * 32767)))) for x in ornekler))
    return base64.b64encode(tampon.getvalue()).decode("ascii")


@_ffmpeg_gerekir
def test_KRITIK_sessiz_kayit_422_ve_SEBEP_donuyor(client):
    """🔴 Sahibin bildirdiği durum: boş kayıt analiz edilip sonuç veriyordu.

    Artık analiz EDİLMİYOR — ve kullanıcı ne yapacağını okuyabiliyor.
    """
    sessiz = _wav_b64([0.0] * (SR * 3))
    r = client.post("/api/ai/sound/cat", data={"audio_base64": sessiz})

    assert r.status_code == 422, f"sessiz kayıt reddedilmedi (HTTP {r.status_code}) — gövde: {r.text[:300]}"
    detay = (r.json() or {}).get("detail", "")
    assert "sessiz" in detay.lower(), f"kullanıcıya sebep ulaşmıyor: {detay!r}"
    # Genel etikete düşmüş olmamalı — düşerse `_ai_fail` mesajı yutmuş demektir.
    assert "Ses analiz hatası" not in detay, (
        "mesaj `_ai_fail` tarafından yutulmuş: kapı HTTPException DEĞİL ham hata fırlatıyor "
        "olabilir → kullanıcı sebebi göremez."
    )
    # Reddedilen kayıt için sınıf/olasılık SIZDIRILMAMALI (yoksa arayüz yine sonuç gösterir).
    assert "top_1_class" not in r.text


@_ffmpeg_gerekir
def test_sessiz_kayitta_sinif_sonucu_URETILMEZ(client):
    """Kapı 'analiz et ama işaretle' değil, 'analiz ETME' olmalı."""
    r = client.post("/api/ai/sound/cat", data={"audio_base64": _wav_b64([0.0] * SR)})
    govde = r.json()
    assert govde.get("status") != "success"
    for alan in ("top_1_class", "top_1_prob", "probabilities"):
        assert alan not in govde, f"reddedilen kayıtta {alan} dönüyor"


def test_cok_kisa_veri_de_anlasilir_sekilde_reddedilir(client):
    """Kayıt hiç başlamamışsa içerik birkaç bayt olur — bu da anlaşılır bir hata vermeli."""
    r = client.post("/api/ai/sound/cat", data={"audio_base64": base64.b64encode(b"ab").decode()})
    assert r.status_code >= 400
    assert r.json().get("status") != "success"


@_ffmpeg_gerekir
def test_KRITIK_yeterli_seviyedeki_kayit_kapiya_TAKILMAZ(client):
    """🔴 Kapı gerçek kayıtları elerse ev sahibi AĞRIYI KAÇIRIR.

    Burada sınıflandırma sonucunu DEĞİL, yalnız "sessizlik kapısına takılmadığını" doğruluyoruz:
    ölçülen gerçek kayıtlar -12..-26 dBFS; bu sinüs ~-13 dBFS, yani kapının belirgin üstünde.
    (Model yoksa/indirilemiyorsa uç başka bir hata döndürür — o durumda test atlanır; burada
    kilitlenen şey SESSİZLİK kapısıdır.)
    """
    n = SR * 2
    sinus = [0.3 * math.sin(2 * math.pi * 700 * i / SR) for i in range(n)]
    r = client.post("/api/ai/sound/cat", data={"audio_base64": _wav_b64(sinus)})

    detay = str((r.json() or {}).get("detail", ""))
    if r.status_code == 422 and "sessiz" in detay.lower():
        pytest.fail(
            f"yeterli seviyedeki kayıt SESSİZ sanıldı (eşik çok yüksek): {detay!r} — "
            "gerçek kedi kayıtları da reddedilir."
        )
    # Model yüklenemiyorsa (ONNX yok) 500 gelebilir; bu testin konusu o değil.
    if r.status_code == 200:
        govde = r.json()
        assert govde.get("status") == "success"
        # Belirsizlik alanları sözleşmenin parçası — istemci uyarıyı buna göre gösteriyor.
        assert "guvenilir" in govde, "istemci uyarıyı `guvenilir` alanından okuyor"
        assert isinstance(govde["guvenilir"], bool)
        assert 0.0 <= govde.get("belirsizlik", 0.0) <= 1.0
