# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODAK modeli (istem 45 A3): KNN k = 1 + yerel alan, çıktı = doz başına genlik (a / D). ONNX (ölçekleme + uzaklık + ArgMin + Gather tek grafikte).

Öznitelikler EĞİTİMLE BİREBİR (`DENETIM\\odak\\model\\ortak.Numune.ornekle` + `a3_model.FizikOzellik`): kip temel öznitelikleri (ölçüm çerçevesi,
mm) + yerel alan M (3 × 7, CST eksenleri, kalibrasyonlu) + M / doz. Model dosyası eğitildiği kalibrasyonun kimliğini taşır; sürüşteki kalibrasyon
farklıysa `oneri` SÜRMEZ ("model eski").
"""
from __future__ import annotations

import functools
import json
import os

import numpy as np

from ai_hub.odak.alan import VERI_DIZINI, model_katmani_yolu

KIPLER = ("TUM_PETRI", "KUYUCUK", "FANTOM", "KEDI_TV", "KEDI_ORGAN")
#: Yerel alanın alındığı nokta (eğitimdeki `FizikOzellik._X` ile AYNI): kip → (temel öznitelik adlarından konum kuralı)
YEREL_Y_SABIT = {"FANTOM": 20.0, "KEDI_TV": 73.7}  # taban camından mm (eğitim varsayımı; fantom KD-3b ölçüsüyle güncellenir)
SIVI_ORTA_PAYI = 5.0  # petri: taban + altlık + 5 mm (eğitimle aynı)


def yerel_nokta(kip: str, oz: dict, taban_y: float) -> np.ndarray:
    """Temel öznitelikler (ölçüm çerçevesi) → yerel alan noktası (ölçüm çerçevesi, mm)."""
    if kip == "TUM_PETRI":
        return np.array([oz["plaka_x"], taban_y + oz["altlik"] + SIVI_ORTA_PAYI, oz["plaka_z"]])
    if kip == "KUYUCUK":
        return np.array([oz["hedef_x"], taban_y + oz["altlik"] + SIVI_ORTA_PAYI, oz["hedef_z"]])
    if kip == "FANTOM":
        return np.array([oz["tumor_x"], taban_y + YEREL_Y_SABIT["FANTOM"], oz["tumor_z"]])
    if kip == "KEDI_TV":
        return np.array([oz["kedi_x"], taban_y + YEREL_Y_SABIT["KEDI_TV"], oz["kedi_z"]])
    return np.array([oz["organ_x"], oz["organ_y"], oz["organ_z"]])


class OdakModeli:
    """Bir kipin ONNX KNN'i + üst verisi (`model_<KIP>.onnx` + `model_<KIP>.json`). Y282: `dizin` verilmezse üst veri depodaki
    `VERI_DIZINI`den, ONNX AI MODEL KATMANINDAN (`alan.model_katmani_yolu`; yoksa FileNotFoundError → ODAK engeli `modelYok`)."""

    def __init__(self, kip: str, dizin: str | None = None):
        if kip not in KIPLER:
            raise ValueError(kip)
        self.kip = kip
        with open(os.path.join(dizin or VERI_DIZINI, f"model_{kip}.json"), encoding="utf-8") as fh:
            self.meta = json.load(fh)
        self.ozellik_ad = list(self.meta["ozellik_ad"])
        self.kalibrasyon_kimligi = str(self.meta["kalibrasyon_kimligi"])
        self.sinir = float(self.meta["sinir"])
        self._yol = os.path.join(dizin, f"model_{kip}.onnx") if dizin else model_katmani_yolu(f"model_{kip}.onnx")
        self._oturum = None

    def _sess(self):
        if self._oturum is None:
            import onnxruntime as ort

            so = ort.SessionOptions()
            so.intra_op_num_threads = 1
            self._oturum = ort.InferenceSession(self._yol, sess_options=so, providers=["CPUExecutionProvider"])
        return self._oturum

    def ozellik(self, oz: dict, M: np.ndarray, doz_mT: float) -> np.ndarray:
        """Temel öznitelikler + yerel alan (3, 7) → tam öznitelik satırı (1, F) — eğitimdeki sıra."""
        temel = np.array([float(doz_mT) if a == "doz_mT" else float(oz[a]) for a in self.ozellik_ad], dtype=np.float64)
        m = np.asarray(M, dtype=np.float64).reshape(-1)
        return np.concatenate([temel, m, m / float(doz_mT)])[None, :].astype(np.float32)

    def tahmin(self, X: np.ndarray) -> np.ndarray:
        """(n, F) → doz başına genlik (n, 7), eğitim sınırına kırpılmış."""
        s = self._sess()
        y = s.run(None, {s.get_inputs()[0].name: np.asarray(X, dtype=np.float32)})[0]
        return np.clip(np.asarray(y, dtype=np.float64), -self.sinir, self.sinir)


@functools.lru_cache(maxsize=8)
def model_al(kip: str, dizin: str | None = None) -> OdakModeli:
    return OdakModeli(kip, dizin)
