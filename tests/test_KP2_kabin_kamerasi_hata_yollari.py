# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-2 · apps/backend/utils/kabin_kamerasi.py · sözleşmeler: seçim diske yazılamazsa ASIL hata yükselir, geçici dosya kalmaz,
seçim yok kalır · tek karede hiç kare okunamazsa / JPEG kodlanamazsa None ve kamera HER durumda bırakılır · canlı okuyucu
okuma hatasında durur (oturum kapalı görünür, günlüğe uyarı) ve kamera bırakma hatası iş parçacığını düşürmez · canlı oturum
kaydında kodlayıcı yoksa modül düzeyi `cv2` ile gerçek JPEG üretilir · canlı karede JPEG kodlanamazsa `hazir: False`.

Sahte yalnız EN ALT katta: `cv2` (VideoCapture / read / release / imencode), dosya sistemi (tmp; hedef yolda DİZİN → gerçek
`os.replace` hatası), `os.unlink`, `threading.excepthook` (yalnız kayıt). Gerçek kamera AÇILMAZ.
"""

from __future__ import annotations

import base64
import json
import logging
import threading

import numpy as np
import pytest


class _SahteCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self, *, kare_ver=True, kodla=True, okuma_hatasi=None, birakma_hatasi=None):
        self.kare_ver, self.kodla = kare_ver, kodla
        self.okuma_hatasi, self.birakma_hatasi = okuma_hatasi, birakma_hatasi
        self.capler: list = []

    def VideoCapture(self, i):  # noqa: N802 — cv2 API adı
        cv = self

        class _Cap:
            def __init__(self):
                self.indeks, self.sira, self.boyut = i, [], [640, 480]
                self.istek = [10**6, 10**6]

            def isOpened(self):  # noqa: N802
                return True

            def set(self, prop, deger):
                # KD madde 0: ölçülen sürücü davranışı — istek, desteklenen modlardan isteği AŞMAYAN en büyüğüne iner (9999 → 1920×1080).
                self.sira.append(("set", prop, deger))
                self.istek[0 if prop == 3 else 1] = int(deger)
                uygun = [
                    m
                    for m in ((640, 480), (1280, 720), (1920, 1080))
                    if m[0] <= self.istek[0] and m[1] <= self.istek[1]
                ]
                self.boyut = list(max(uygun) if uygun else (640, 480))
                return True

            def get(self, prop):
                return float(self.boyut[0 if prop == 3 else 1])

            def read(self):
                self.sira.append(("read",))
                if cv.okuma_hatasi is not None:
                    raise cv.okuma_hatasi
                if not cv.kare_ver:
                    return False, None
                return True, np.zeros((self.boyut[1], self.boyut[0], 3), dtype=np.uint8)

            def release(self):
                self.sira.append(("release",))
                if cv.birakma_hatasi is not None:
                    raise cv.birakma_hatasi

        c = _Cap()
        self.capler.append(c)
        return c

    @staticmethod
    def resize(kare, boyut):
        return np.zeros((boyut[1], boyut[0], 3), dtype=np.uint8)

    def imencode(self, _uz, _kare, _p=None):
        if not self.kodla:
            return False, None
        return True, np.frombuffer(b"\xff\xd8kp2", dtype=np.uint8)


@pytest.fixture()
def kk(tmp_path, monkeypatch):
    from utils import kabin_kamerasi as kk

    monkeypatch.delenv("PEMF_KABIN_KAMERASI", raising=False)
    kok = tmp_path / "veri"
    kok.mkdir()
    monkeypatch.setattr(kk, "_veri_koku", lambda: kok)
    kk.canli_durdur()
    yield kk
    kk.canli_durdur()
    assert not kk.canli_acik()


# ── seçim yazılamazsa ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_secim_YAZILAMAZSA_hata_yukselir_gecici_dosya_kalmaz_secim_yok(kk):
    kok = kk._veri_koku()
    (kok / kk.KAMERA_DOSYASI).mkdir()
    with pytest.raises(OSError):
        kk.kamera_sec(1)
    assert sorted(p.name for p in kok.iterdir()) == [kk.KAMERA_DOSYASI], "geçici seçim dosyası artığı kaldı"
    assert kk.secili_kamera() is None


def test_secim_gecici_dosya_SILINEMESE_de_ASIL_hata_yukselir(kk, monkeypatch):
    kok = kk._veri_koku()
    (kok / kk.KAMERA_DOSYASI).mkdir()
    istenen = []

    def _kilitli(yol, *a, **k):
        istenen.append(str(yol))
        raise PermissionError(13, "kp2-sahte-unlink-kilitli", str(yol))

    monkeypatch.setattr(kk.os, "unlink", _kilitli)
    with pytest.raises(OSError) as hata:
        kk.kamera_sec(2)
    assert "kp2-sahte-unlink-kilitli" not in str(hata.value)
    assert len(istenen) == 1 and istenen[0].endswith(".tmp")


# ── tek kare ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_tek_kare_HIC_okunamazsa_None_ve_kamera_birakilir(kk):
    kk.kamera_sec(1)
    cv = _SahteCv2(kare_ver=False)
    assert kk.kare_al(cv) is None
    cap = cv.capler[0]
    assert cap.sira.count(("read",)) == kk.KARE_ISINMA + 1, "ısınma kareleri denenmedi"
    assert cap.sira[-1] == ("release",), "kare alınamayınca kamera bırakılmadı"


def test_tek_kare_JPEG_kodlanamazsa_None_ve_kamera_birakilir(kk):
    kk.kamera_sec(1)
    cv = _SahteCv2(kodla=False)
    assert kk.kare_al(cv) is None
    assert cv.capler[0].sira[-1] == ("release",)
    # KARŞIT: kodlanabilen kare sonuç verir
    iyi = _SahteCv2()
    k = kk.kare_al(iyi)
    assert (k["indeks"], k["genislik"], k["yukseklik"]) == (1, 1920, 1080)
    assert base64.b64decode(k["image_base64"]) == b"\xff\xd8kp2"


# ── canlı oturum ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_canli_okuyucu_OKUMA_hatasinda_durur_BIRAKMA_hatasi_is_parcacigini_dusurmez(kk, monkeypatch, caplog):
    yakalanmamis = []
    monkeypatch.setattr(threading, "excepthook", lambda a: yakalanmamis.append(a))
    kk.kamera_sec(1)
    cv = _SahteCv2(okuma_hatasi=RuntimeError("kp2 akış koptu"), birakma_hatasi=OSError("kp2 bırakılamadı"))
    with caplog.at_level(logging.WARNING, logger=kk.__name__):
        assert kk.canli_baslat(cv) == {"indeks": 1, "acik": True}
        d = kk._canli
        d["is"].join(timeout=5.0)
    assert not d["is"].is_alive(), "okuyucu iş parçacığı okuma hatasında durmadı"
    assert yakalanmamis == [], f"okuyucu yakalanmamış istisnayla düştü: {yakalanmamis}"
    assert d["dur"].is_set() and not kk.canli_acik()
    assert cv.capler[0].sira[-1] == ("release",), "okuyucu kamerayı bırakmayı denemedi"
    assert any("canli okuyucu durdu" in r.getMessage() for r in caplog.records)
    assert kk.canli_kare(cv2=cv) is None, "durmuş oturum kare verdi"


def _canli_kare_hazir(kk, cv):
    kk.kamera_sec(1)
    assert kk.canli_baslat(cv) == {"indeks": 1, "acik": True}
    k = kk.canli_kare(tam=True, cv2=cv, bekle_sn=2.0)
    assert k is not None and k["hazir"] is True, k


def test_canli_kare_JPEG_kodlanamazsa_HAZIR_DEGIL_doner(kk):
    cv = _SahteCv2()
    _canli_kare_hazir(kk, cv)
    kotu = _SahteCv2(kodla=False)
    assert kk.canli_kare(cv2=kotu) == {"indeks": 1, "hazir": False}
    assert kk.canli_acik(), "kodlama hatası canlı oturumu kapattı"


def test_canli_oturum_kaydinda_kodlayici_YOKSA_modul_cv2_ile_GERCEK_JPEG(kk):
    cv = _SahteCv2()
    _canli_kare_hazir(kk, cv)
    kk._canli["cv2"] = None
    k = kk.canli_kare()
    assert k["hazir"] is True and (k["genislik"], k["yukseklik"]) == (kk.CANLI_ONIZLEME_GENISLIK, 540)
    assert base64.b64decode(k["image_base64"])[:2] == b"\xff\xd8", "gerçek JPEG değil"


def test_kare_al_CANLI_aciksa_ve_kodlanamazsa_None(kk):
    """Canlı oturum açık ama kare kodlanamıyor (`hazir: False`) → tek kare None, canlı KAPANMAZ, ikinci kamera AÇILMAZ."""
    cv = _SahteCv2()
    _canli_kare_hazir(kk, cv)
    kotu = _SahteCv2(kodla=False)
    assert kk.kare_al(kotu) is None
    assert kotu.capler == [] and kk.canli_acik()
    assert json.loads((kk._veri_koku() / kk.KAMERA_DOSYASI).read_text(encoding="utf-8")) == {"indeks": 1}
