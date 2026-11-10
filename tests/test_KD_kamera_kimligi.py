# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD-2 (sahip kararı 2026-11-10) — kabin kamerası KİMLİĞİ: ad + VID/PID + aygıt yolu.

ÖLÇÜLEN KUSUR (KD-1, tezgâh): OpenCV MSMF indeks sırası DEĞİŞTİ (Pusat 1 → 0; dahili HP kamera yer değiştirdi) — yalnız indeksle
saklanan seçim YANLIŞ kamerayı açardı. SÖZLEŞME: seçim kimlikle saklanır; açılışta aygıt listesi yeniden okunur → önce aygıt yolu,
yol değişmişse (başka USB girişi) ad + VID/PID'i TEK olan aygıt; bulunamazsa kamera AÇILMAZ (`KameraBulunamadi`, eylem metni kimliği
söyler); liste okunamıyorsa saklı indeks (günlük). Kalibrasyon kimliği karşılaştırır, indeksi değil (test_KD_sabit_duzlem / uçlar).
Sahte EN ALT katta: aygıt listesi (`kamera_kimligi.msmf_kameralar` — gerçek Media Foundation çağrısı Windows'ta tezgâhta doğrulandı),
`cv2` (VideoCapture / read / imencode). Gerçek kamera AÇILMAZ.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

PUSAT = {
    "ad": "FHD Camera",
    "vidpid": "VID_1BCF&PID_28C4",
    "aygit_yolu": r"\\?\usb#vid_1bcf&pid_28c4&mi_00#7&1da11eb4&1&0000#{x}",
}
HP = {
    "ad": "HP True Vision FHD Camera",
    "vidpid": "VID_30C9&PID_0069",
    "aygit_yolu": r"\\?\usb#vid_30c9&pid_0069&mi_00#6&2&0&0000#{x}",
}


class _Cv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self):
        self.acilan: list = []
        self.okunan = 0

    def VideoCapture(self, i):  # noqa: N802 — cv2 API adı
        cv = self
        cv.acilan.append(i)

        class _Cap:
            def isOpened(self):  # noqa: N802
                return True

            def set(self, *_a):
                return True

            def get(self, _p):
                return 0.0

            def read(self):
                cv.okunan += 1
                return True, np.full((4, 6, 3), cv.okunan, dtype=np.uint8)

            def release(self):
                return None

        return _Cap()

    @staticmethod
    def resize(kare, boyut):
        return np.zeros((boyut[1], boyut[0], 3), dtype=np.uint8) + kare[0, 0, 0]

    @staticmethod
    def imencode(_uz, kare, _p=None):
        return True, np.frombuffer(bytes([int(kare[0, 0, 0])]) * 3, dtype=np.uint8)


@pytest.fixture()
def kk(tmp_path, monkeypatch):
    from utils import kabin_kamerasi as kk
    from utils import kamera_kimligi

    monkeypatch.delenv("PEMF_KABIN_KAMERASI", raising=False)
    kok = tmp_path / "veri"
    kok.mkdir()
    monkeypatch.setattr(kk, "_veri_koku", lambda: kok)
    aygitlar: list = []
    monkeypatch.setattr(kamera_kimligi, "msmf_kameralar", lambda: [dict(a) for a in aygitlar])
    kk.canli_durdur()
    yield kk, aygitlar, kok
    kk.canli_durdur()


def _liste(*aygitlar):
    return [dict(a, indeks=i) for i, a in enumerate(aygitlar)]


def test_vidpid_aygit_yolundan_ve_esleme_KURALLARI():
    from utils import kamera_kimligi as kmk

    assert kmk.vidpid(PUSAT["aygit_yolu"]) == "VID_1BCF&PID_28C4" and kmk.vidpid("yok") is None
    assert kmk.esle(PUSAT, _liste(HP, PUSAT)) == (1, "yol")
    baska_giris = dict(PUSAT, aygit_yolu="baska-usb-girisi")
    assert kmk.esle(PUSAT, _liste(baska_giris, HP)) == (0, "ad_vidpid")
    assert kmk.esle(PUSAT, _liste(baska_giris, dict(PUSAT, aygit_yolu="ucuncu"))) == (None, "yok"), (
        "iki eş kamera — tahmin YOK"
    )
    assert kmk.esle(PUSAT, _liste(HP)) == (None, "yok")


def test_KRITIK_secim_KIMLIKLE_saklanir_MSMF_sirasi_degisince_DOGRU_kamera_acilir(kk):
    kk, aygitlar, kok = kk
    aygitlar[:] = _liste(HP, PUSAT)
    kk.kamera_sec(1)
    assert json.loads((kok / kk.KAMERA_DOSYASI).read_text(encoding="utf-8"))["kimlik"] == PUSAT
    aygitlar[:] = _liste(PUSAT, HP)  # KD-1'deki gibi sıra değişti
    cv = _Cv2()
    cap, indeks = kk.kamera_ac(cv)
    assert indeks == 0 and cv.acilan == [0], "MSMF sırası değişince ESKİ indeks (artık dahili kamera) açıldı"


def test_KRITIK_kimlik_BULUNAMAZSA_kamera_ACILMAZ_ve_EYLEM_metni_kimligi_soyler(kk):
    from utils import ceviri

    kk, aygitlar, _kok = kk
    aygitlar[:] = _liste(HP, PUSAT)
    kk.kamera_sec(1)
    aygitlar[:] = _liste(HP)  # Pusat çıkarıldı — dahili kamera indeks 0'da
    cv = _Cv2()
    with pytest.raises(kk.KameraBulunamadi) as e:
        kk.kamera_ac(cv)
    assert cv.acilan == [], "kimlik yokken başka kamera açıldı"
    assert isinstance(e.value, kk.KameraSecilmedi)  # her yakalayıcı kamerayı açmadan durur
    m = kk.secim_hatasi_metni(e.value)
    assert "FHD Camera" in m and "VID_1BCF&PID_28C4" in m and m != ceviri.t("ai.pro.hazirlik.kameraSecilmedi"), m
    assert kk.secim_hatasi_metni(kk.KameraSecilmedi()) == ceviri.t("ai.pro.hazirlik.kameraSecilmedi")


def test_KARSIT_aygit_listesi_OKUNAMAZSA_sakli_indeks_ve_kimliksiz_eski_secim(kk):
    kk, aygitlar, kok = kk
    aygitlar[:] = _liste(HP, PUSAT)
    kk.kamera_sec(1)
    aygitlar[:] = []  # MF okunamadı / Windows dışı
    cv = _Cv2()
    assert kk.kamera_ac(cv)[1] == 1 and cv.acilan == [1]
    (kok / kk.KAMERA_DOSYASI).write_text(json.dumps({"indeks": 2}), encoding="utf-8")  # KD-2 öncesi seçim dosyası
    assert kk.secili_kamera() == {"indeks": 2, "kaynak": "ayar"}  # eski biçim AYNEN (kimlik alanı yok)
    cv2 = _Cv2()
    assert kk.kamera_ac(cv2)[1] == 2


def test_kare_al_ADET_ayni_acilista_son_N_kare_ve_KIMLIK(kk):
    kk, aygitlar, _kok = kk
    aygitlar[:] = _liste(PUSAT)
    kk.kamera_sec(0)
    cv = _Cv2()
    k = kk.kare_al(cv, adet=3)
    assert cv.acilan == [0] and len(k["ek_kareler"]) == 2 and k["kimlik"] == PUSAT, k
    tek = kk.kare_al(_Cv2())
    assert "ek_kareler" not in tek and tek["kimlik"] == PUSAT


def test_KRITIK_kare_ucu_KIMLIK_bulunamazsa_409_EYLEM_metni(kk):
    import servers.api_server as apis
    from fastapi.testclient import TestClient

    kk, aygitlar, _kok = kk
    aygitlar[:] = _liste(PUSAT)
    kk.kamera_sec(0)
    aygitlar[:] = _liste(HP)
    r = TestClient(apis.app).post("/api/settings/kabin-kamerasi/kare")
    assert r.status_code == 409 and "VID_1BCF&PID_28C4" in r.json()["detail"], r.text


def test_tarama_KAMERA_ADINI_da_dondurur(kk):
    kk, aygitlar, _kok = kk
    aygitlar[:] = _liste(HP, PUSAT)
    out = kk.kameralari_tara(_Cv2(), sayi=2)
    assert [(o["indeks"], o["ad"], o["vidpid"]) for o in out] == [
        (0, HP["ad"], HP["vidpid"]),
        (1, PUSAT["ad"], PUSAT["vidpid"]),
    ]
