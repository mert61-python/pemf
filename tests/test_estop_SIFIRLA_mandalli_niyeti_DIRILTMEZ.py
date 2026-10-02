# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · Y4 (1-C bağımsız inceleme i1-F1) — "Sıfırla", mandal KURULUYKEN alınmış bir START niyetini DİRİLTEMEZ.

ÖLÇÜLEN KUSUR (c5b3c04, i1 3 koşu × 30/30): `analyze_landmark` (AI (Auto)) sürüş niyetinin neslini istek girişinde
alır; mandal yalnız sürüş anında denetlenir. `estop_mandali.sifirla()` nesli DEĞİŞTİRMİYORDU ("uçuştaki eski niyetler
acil durdurmanın artırdığı nesille zaten bayattır" — bu yalnız E-stop'tan ÖNCE alınmış niyetler için doğru). Mandal
kuruluyken alınan niyetin nesli zaten E-stop SONRASI nesildir → çıkarım sürerken basılan "Sıfırla"dan sonra niyet
"taze" görünür ve YENİ bir START olmadan 7 bobini %31 duty ile 30 dk sürer. Y4 iki yerden çiğnenir: "mandal kuruluyken
hiçbir START kabul edilmez" ve "sıfırlama kendi başına yeniden başlatmaz".

KAPI: GERÇEK `analyze_landmark` → `_drive_landmark_auto` → `start_ai_session` → `start_all_coils` → paket kurucu;
sahte olan yalnız model (çıkarım bir Event'te BLOKLANIR = çıkarım penceresi), FGS (sabit 2) ve istek kaynağının
"yerel" sayılması (TestClient'ın "testclient"ı yerel değil). Sıra: E-stop → landmark `auto_adjust` (mandallı) → çıkarım
sürerken Sıfırla → çıkarım biter. ≥30 deneme; ölçüt donanıma GİDEN duty>0 paket + çalışan bobin + ESP START yayını.
KARŞIT kollar: Sıfırla YOKKEN aynı istek reddedilir; Sıfırla'dan SONRA verilen YENİ istek sürer (aparat sürebiliyor).
"""

from __future__ import annotations

import base64
import threading
import types

import ai_pro_aparati as ap
import numpy as np
import pytest

DENEME = 30
_SIFIRLA = "/api/hardware/estop_mandali/sifirla"


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


class _T:
    """Ultralytics tensörünün yeterli taklidi (`.cpu().numpy()`, indeks, uzunluk)."""

    def __init__(self, a):
        self.a = np.asarray(a, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self.a

    def __getitem__(self, i):
        return _T(self.a[i])

    def __len__(self):
        return len(self.a)


class _Kutular:
    def __init__(self):
        self._k = [types.SimpleNamespace(xyxy=_T([[0.0, 0.0, 60.0, 60.0]]))]

    def __len__(self):
        return 1

    def __getitem__(self, i):
        return self._k[i]


def _sahte_sonuc():
    kp = np.array([[10.0 + (i % 8) * 5.0, 10.0 + (i // 8) * 5.0] for i in range(48)])  # 48 görünür nokta
    return types.SimpleNamespace(keypoints=types.SimpleNamespace(xy=_T([kp]), conf=None), boxes=_Kutular())


class _SahteModel:
    def __init__(self, durum):
        self.durum = durum

    def predict(self, *a, **k):
        self.durum.girdi.set()
        if self.durum.engel is not None:
            assert self.durum.engel.wait(10), "aparat: çıkarım engeli 10 sn'de kalkmadı"
        return [_sahte_sonuc()]


@pytest.fixture
def lm(o, monkeypatch):
    from servers import auth

    import ai_hub.cat_landmark.inference_cat_landmark as inf

    durum = types.SimpleNamespace(engel=None, girdi=threading.Event())
    monkeypatch.setattr(o.air, "_get_or_load_model", lambda ad, yukleyici: _SahteModel(durum))
    monkeypatch.setattr(inf, "compute_fgs", lambda kp: {"fgs_total": 2, "pain_level": "Mild", "action_units": {}})
    monkeypatch.setattr(auth, "is_local_request", lambda *a, **k: True)
    o.lm = durum
    return o


def _landmark(o):
    img = base64.b64encode(b"\xff\xd8\xff\xd9").decode()
    return o.c.post("/api/ai/vision/landmark", data={"image_base64": img, "auto_adjust": "true"})


def _landmark_arka_planda(o):
    kutu: dict = {}

    def _calis():
        try:
            kutu["yanit"] = _landmark(o)
        except Exception as e:  # pragma: no cover - aparat tanısı
            kutu["hata"] = e

    t = threading.Thread(target=_calis, daemon=True, name="test-landmark")
    t.start()
    return t, kutu


def _temizle(o):
    o.c.post("/api/session/stop")
    ap.mandali_sifirla(o.c)
    o.hc.stop_all_coils()


def _ihlal(o, sonra: int) -> bool:
    return bool(ap.surus_paketleri(o, sonra)) or bool(ap.calisan(o))


def test_KRITIK_mandalliyken_istenen_AI_Auto_START_SIFIRLA_sonrasi_SURULMEZ_N30(lm):
    o = lm
    ihlal = esp_start = 0
    durumlar: list = []
    ornek = None
    for _ in range(DENEME):
        _temizle(o)
        o.lm.engel = threading.Event()
        o.lm.girdi.clear()
        o.api._emergency_stop_all("manual")  # mandal KURULU
        sonra = ap.paket_sayisi(o)
        y0 = len(o.yayin)
        t, kutu = _landmark_arka_planda(o)  # MANDALLIYKEN istenen otonom START; çıkarım sürüyor
        assert o.lm.girdi.wait(10), "aparat: istek çıkarıma ulaşmadı"
        r = o.c.post(_SIFIRLA, json={"onay": True})  # operatörün Sıfırla'sı (bu istekten SONRA)
        assert r.status_code == 200, r.text[:200]
        o.lm.engel.set()
        t.join(15)
        assert not t.is_alive(), "aparat: landmark isteği bitmedi"
        assert "yanit" in kutu, f"aparat: yanıt yok {kutu.get('hata')!r}"
        durumlar.append(kutu["yanit"].json().get("hw_status"))
        bu = _ihlal(o, sonra)
        ihlal += bu
        if bu and ornek is None:
            ornek = (ap.surus_paketleri(o, sonra)[:1], ap.calisan(o))
        esp_start += any(str(p.get("command")) == "start" for _t, p in o.yayin[y0:])
    _temizle(o)
    assert ihlal == 0 and esp_start == 0, (
        f"{DENEME} denemenin {ihlal}'inde MANDALLIYKEN istenen AI (Auto) START, Sıfırla'dan SONRA yeni START olmadan "
        f"donanımı sürdü (ilk örnek duty/çalışan: {ornek}); hw_status dağılımı "
        f"{ {d: durumlar.count(d) for d in set(durumlar)} }; ESP START yayını {esp_start}/{DENEME}"
    )


def test_KARSIT_sifirla_YOKKEN_mandalli_istek_REDDEDILIR(lm):
    o = lm
    _temizle(o)
    o.lm.engel = threading.Event()
    o.lm.girdi.clear()
    o.api._emergency_stop_all("manual")
    sonra = ap.paket_sayisi(o)
    t, kutu = _landmark_arka_planda(o)
    assert o.lm.girdi.wait(10)
    o.lm.engel.set()
    t.join(15)
    assert kutu["yanit"].json().get("hw_status") == "skipped_estop_latched", kutu["yanit"].text[:300]
    assert not _ihlal(o, sonra)


def test_KARSIT_sifirla_SONRASI_YENI_istek_SURER_aparat_surebiliyor(lm):
    o = lm
    _temizle(o)
    o.api._emergency_stop_all("manual")
    ap.mandali_sifirla(o.c)
    sonra = ap.paket_sayisi(o)
    o.lm.engel = None
    r = _landmark(o)
    assert r.json().get("hw_status") == "updated", r.text[:300]
    assert ap.surus_paketleri(o, sonra), "aparat: Sıfırla sonrası yeni istek donanımı sürmedi"
    _temizle(o)


def test_KRITIK_sifirla_nesli_ARTIRIR_mandal_yokken_ARTIRMAZ():
    """Birim: mandal kuruluyken Sıfırla nesli artırır (mandallıyken alınmış her niyet bayatlar); mandal yokken
    Sıfırla hiçbir şeyi değiştirmez (boş Sıfırla uçuştaki geçerli niyetleri öldürmesin)."""
    from utils import estop_mandali as em

    em.sifirla("test-onkosul")
    n0 = em.nesil()
    assert em.sifirla("test") is False and em.nesil() == n0, "mandal yokken Sıfırla nesli değiştirdi"
    em.mandalla("test")
    n1 = em.nesil()
    assert n1 == n0 + 1
    assert em.sifirla("test") is True
    assert em.nesil() == n1 + 1, "mandal kuruluyken Sıfırla nesli ARTIRMADI (mandallıyken alınmış niyet diriliyor)"
    assert em.baslatma_engeli(n1) == em.NESIL_MESAJI
    assert em.baslatma_engeli(em.nesil()) == ""
