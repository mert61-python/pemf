# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) — canlı alan testleri için SENTETİK küçük alan tablosu + örnek kalibrasyon.

İzlenmeyen model dosyasına (`alan_tablosu.npz`, Y282 — AI model katmanında) BAĞLI DEĞİL: CI'da da koşar (K6C10 / KP-8 dersi — modelli test
CI'da atlanınca kapsam < 100). Tablo gerçek tablonun YAPISINDA (B (nx, ny, nz, 3, 7) float32, CST kökü / adımı / boyutu, kimlik) ama kaba
(40 mm) ve +Y (CST genişlik) kenarı cam içini TAM örtmez → "tablo dışı" noktalar da sınanır. Alan: bobin başına sabit merkezli dipol (mT)."""

from __future__ import annotations

import copy
import json
import os

import numpy as np

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")

#: CST çerçevesinde bobin merkezleri (X yükseklik, Y genişlik, Z derinlik; mm) ve dipol yönleri — gerçek kabine benzer dağılım.
_MERKEZ = np.array(
    [
        [-60, -150, -120],
        [-60, 0, -120],
        [-60, 150, -120],
        [-60, -150, 150],
        [-60, 150, 150],
        [200, -100, 0],
        [200, 100, 0],
    ],
    float,
)
_YON = np.array([[1, 0, 0], [1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, 1, 1]], float)


def kalibrasyon() -> dict:
    """12 Kasım tezgâh kalibrasyonunun özü (izlenen `tests/veri/odak_kalibrasyon_ornek.json`) — her çağrıda bağımsız kopya."""
    with open(ORNEK, encoding="utf-8") as fh:
        return copy.deepcopy(json.load(fh))


def tablo(adim: float = 40.0, kimlik: str = "sentetik-ga-1") -> dict:
    """`ai_hub.odak.alan.alan_tablosu()` biçiminde sentetik birim alan tablosu."""
    kok = np.array([-170.0, -290.0, -230.0])
    boyut = np.array([12, 15, 13]) if adim == 40.0 else np.ceil(np.array([440.0, 560.0, 480.0]) / adim).astype(int) + 1
    eks = [kok[i] + np.arange(boyut[i]) * adim for i in range(3)]
    P = np.stack(np.meshgrid(*eks, indexing="ij"), axis=-1)  # (nx, ny, nz, 3)
    B = np.zeros(tuple(boyut) + (3, 7), np.float32)
    for c in range(7):
        r = P - _MERKEZ[c]
        d = np.linalg.norm(r, axis=-1, keepdims=True) + 80.0
        rh = r / d
        m = _YON[c] / np.linalg.norm(_YON[c])
        mr = np.sum(rh * m, axis=-1, keepdims=True)
        B[..., :, c] = (3.0 * mr * rh - m) * (8.0e6 / d**3)
    return {"B": B, "kok": kok, "adim": float(adim), "boyut": boyut, "kimlik": kimlik}


def model(f_hz: float | None = None, K: dict | None = None, T: dict | None = None):
    from ai_hub.odak.alan import AlanModeli

    return AlanModeli(K if K is not None else kalibrasyon(), tablo=T if T is not None else tablo(), f_hz=f_hz)
