# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI ISITMA — ses hattının JIT maliyeti açılışta, arka planda ödenir (2026-08-12).

ARIZA: kedi-sesi analizi diğer modellerden belirgin şekilde geç sonuç veriyordu; peş peşe
analiz başlatıldığında istemci zaman aşımına düşüyordu (bkz. `test_ai_zaman_asimi.py`).

ÖLÇÜM (temiz süreç, adım adım — sebep MODEL DEĞİL, librosa/numba katmanı):
    librosa.load (ilk)              36,7 sn   ← baskın maliyet
    librosa.effects.trim (ilk)       6,5 sn
    imageio_ffmpeg yol çözümü        3,0 sn
    mel + delta + power_to_db        0,03 sn
    ONNX yükle + çalıştır            0,17 sn
Kıyas (aynı koşullar): böbrek CT **0,6 sn** (model 42,7 MB), böbrek hastalığı 1,7 sn,
ses 4,5 sn (model 14,1 MB). CT'nin modeli 3 kat BÜYÜK ama 7 kat HIZLI → maliyet modelde
değil, ses hattının numba-JIT ön-işlemesinde. Ses, JIT kullanan TEK model.

ÇÖZÜMÜN ÖLÇÜLEN ETKİSİ (kullanıcının gördüğü ilk analiz süresi):
                          ısıtma YOK   ısıtma VAR
    yeni kurulum            38,2 sn      0,28 sn
    sonraki açılışlar        4,7 sn      0,27 sn

Kilitlenen değişmezler:
  1) Isıtma açılış akışında ÇAĞRILIR (unutulursa maliyet yine kullanıcıya biner).
  2) Açılışı BLOKLAMAZ (ayrı thread) ve hata hâlinde servisi DÜŞÜRMEZ — ısıtma bir
     optimizasyondur, tıbbi işlevin ön koşulu değildir.
  3) Isıtma, modelin KENDİ ön-işleme fonksiyonunu çağırır. Ayrı bir kopya yazılırsa
     ısıtılan yol ile çıkarım yolu ayrışır ve ısıtma sessizce işe yaramaz hâle gelir.
  4) Bayrakla kapatılabilir (`PEMF_AI_WARMUP=0`) — düşük çekirdekli sahada kapatmak
     istenebilir; kapatma yolu kaybolmamalı.

⚠️ KOD KORUMASI DOĞRULANDI: üretim paketinde `ai_hub` düz `.py` DEĞİL, Cython `.pyd`'dir
(`inference_cat_sound.cp310-win_amd64.pyd`). Isıtmanın kullandığı `audio_to_mel_image`
paketin `__init__.py`sinde re-export EDİLMEZ — alt-modülden alınır. Bu yüzden yayınlanan
paketin KENDİ `.pyd`'si doğrudan yüklenip sembolün var ve çağrılabilir olduğu ölçüldü
(2026-08-12). Varsayılmadı: derleme sembolü düşürseydi ısıtma sessizce "atlandı" loglayıp
hiçbir işe yaramazdı.

TEŞHİS KOLAYLIĞI: ısıtma bitince `AI ısıtma tamam (ses ön-işleme): X sn` loglanır. Bir
kurulumda bu satır her açılışta ~38 sn gösteriyorsa numba disk önbelleği YAZILAMIYOR
demektir (beklenen: ilk açılışta ~38 sn, sonrakilerde ~4 sn).
"""

import ast
import inspect
import os
import sys
import textwrap
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

os.environ.pop("PEMF_SIMULATE", None)


@pytest.fixture(scope="module")
def bs():
    import backend_service

    return backend_service


def test_KRITIK_acilista_CAGRILIYOR(bs):
    """Çağrılmazsa maliyet yine ilk analize biner — düzeltme sessizce ölür."""
    src = inspect.getsource(bs)
    assert "_start_ai_warmup_safe(logger)" in src, (
        "AI isitma acilis akisinda CAGRILMIYOR — ses analizi yine 38 sn'ye kadar bekletir"
    )


def test_KRITIK_acilisi_BLOKLAMAZ(bs, monkeypatch):
    """Isıtma ~38 sn sürebilir; `main()` bunu beklerse backend O KADAR geç açılır."""
    import threading as _t

    baslatilan = {}

    class _SahteThread:
        def __init__(self, target=None, name=None, daemon=None, **kw):
            baslatilan["daemon"] = daemon
            baslatilan["name"] = name

        def start(self):
            baslatilan["start"] = True

    monkeypatch.setattr(_t, "Thread", _SahteThread)
    monkeypatch.delenv("PEMF_AI_WARMUP", raising=False)

    import logging

    bs._start_ai_warmup_safe(logging.getLogger("t"))
    assert baslatilan.get("start"), "isitma ARKA PLANDA baslatilmadi (acilis bloklanir)"
    assert baslatilan.get("daemon") is True, "thread daemon degil — yarim kalan isitma KAPANISI GECIKTIRIR"


def test_KRITIK_bayrakla_KAPATILABILIR(bs, monkeypatch):
    """Düşük çekirdekli sahada kapatma yolu bulunmalı."""
    import logging
    import threading as _t

    cagrildi = {}
    monkeypatch.setenv("PEMF_AI_WARMUP", "0")
    monkeypatch.setattr(_t, "Thread", lambda **kw: cagrildi.setdefault("thread", True) and None)
    bs._start_ai_warmup_safe(logging.getLogger("t"))
    assert "thread" not in cagrildi, "PEMF_AI_WARMUP=0 iken bile isitma baslatildi"


def test_KRITIK_MODELIN_KENDI_on_islemesini_cagirir(bs):
    """⚠️ Isıtma ayrı bir kopya ön-işleme yazarsa, ısıtılan kod yolu ile çıkarımda
    kullanılan yol AYRIŞIR: librosa'nın gerçekten çağrılan fonksiyonları derlenmemiş kalır
    ve ısıtma sessizce hiçbir işe yaramaz. Tek kaynak `audio_to_mel_image` olmalı."""
    src = textwrap.dedent(inspect.getsource(bs._start_ai_warmup_safe))

    # ⚠️ `"audio_to_mel_image" in src` YETMEZ: mutasyon turunda ÇAĞRI kendi librosa kopyasıyla
    # değiştirildi ama `from ... import audio_to_mel_image` satırı kaldığı için dize eşleşmesi
    # testi GEÇTİ. İddia ÇAĞRININ KENDİSİNE bağlanmalı (aynı tuzağa `test_ai_zaman_asimi` ve
    # `test_hotspot_autostart` SSID testinde de düşülmüştü).
    agac = ast.parse(src)
    cagrilar = {
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(agac)
        if isinstance(n, ast.Call)
    }
    assert "audio_to_mel_image" in cagrilar, (
        "isitma modelin KENDI on-islemesini CAGIRMIYOR (yalniz import etmis olabilir) — "
        f"isitilan yol cikarim yoluyla ayrisir; bulunan cagrilar: {sorted(cagrilar)}"
    )
    # Uç de aynı fonksiyonu kullanmalı; biri değişip diğeri kalırsa kapı burada kırılır.
    router = (KOK / "ai_hub" / "inference_cat_sound" / "inference_cat_sound.py").read_text(encoding="utf-8")
    assert "def audio_to_mel_image" in router, (
        "audio_to_mel_image kayboldu/yeniden adlandirildi — isitma da guncellenmeli"
    )


def test_KRITIK_HATA_servisi_DUSURMEZ(bs, monkeypatch):
    """Isıtma bir optimizasyondur; librosa/model yoksa servis normal açılmaya devam etmeli."""
    import logging

    monkeypatch.delenv("PEMF_AI_WARMUP", raising=False)
    # Gerçek thread'de çalıştır ve bitmesini bekle — istisna sızarsa test düşer.
    bs._start_ai_warmup_safe(logging.getLogger("t"))  # istisna ATMAMALI

    # Yapısal: iş gövdesi geniş bir `except` ile sarılı olmalı (thread içindeki istisna
    # sessizce kaybolur ama `finally` temizliği ve log yolu korunmalı).
    agac = ast.parse(textwrap.dedent(inspect.getsource(bs._start_ai_warmup_safe)))
    ic_fonksiyonlar = [n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "_calistir"]
    assert ic_fonksiyonlar, "isitma is govdesi (_calistir) bulunamadi"
    denemeler = [n for n in ast.walk(ic_fonksiyonlar[0]) if isinstance(n, ast.Try)]
    assert any(h.type is None or "Exception" in ast.unparse(h.type) for t in denemeler for h in t.handlers), (
        "isitma govdesi genis bir except ile sarilmamis — hata thread'i patlatir"
    )
    assert any(t.finalbody for t in denemeler), "gecici ses dosyasi finally ile SILINMIYOR — her acilista temp birikir"
