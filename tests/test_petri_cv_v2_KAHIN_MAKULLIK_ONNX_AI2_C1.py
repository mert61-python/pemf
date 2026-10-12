# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI-2 C1/C2 — hocanın petri v2'si guii'de: KÂHİN + plaka MAKULLİK kapısı + ONNX aday uyarlaması + guii sertleştirmesi.

KÂHİN (plan §3.12): hocanın `beklenen_sonuclar/` + 6 plaka fotoğrafı `tests/kahin/hoca_cv_2026_10/` (kaynak ve SHA-256:
KAYNAK.md). Hocanın ölçütü 6/6'da 24 kuyucuk; burada ek olarak kimlik sırası (A1…D6), etiket (kanser/sağlıklı) birebir ve
kuyucuk merkezi hatası < 0,25 × aralık (hocanın `eval_plate` "doğru kuyucuk" tanımı). Ölçüldü (C0, kâhin ağacı): guii
ONNX'iyle hocanın kodu OLDUĞU GİBİ 6/6'da ÇÖKÜYORDU (`INVALID_ARGUMENT … Got: 1280 Expected: 640`); 640 uyarlamasıyla
144/144 kuyucuk doğru, maks sapma 1,62 px.

MAKULLİK: hocanın v2'si plaka kipinde HER pembe/mor bölgeye 24 kuyucuk dayatıp `success=True` dönüyordu (9/9 fantom
fotoğrafı 3–18 "kanser", tekil kap fotoğrafı 24/24 "kanser") — 2026-08-06 sahip bildiriminin sınıfı. Kural ve ölçüm:
`ai_hub/inference_petri_dish/plausibility.py` PLAKA KİPİ bloğu.

⚠️ Gerçek ağırlıklı testler `golden.eser` düzenini izler: ağırlık yoksa ATLANIR, `PEMF_GOLDEN_REQUIRED=1`'de DÜŞER (4-A).
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import numpy as np
import pytest

KAHIN = Path(__file__).resolve().parent / "kahin" / "hoca_cv_2026_10"
_YOLO = "ai_hub/inference_petri_dish/yolo11m-seg.onnx"
_EM = "ai_hub/inference_em_petri/BaggingRegressor.onnx"
#: 24'lük plaka kuyucuk aralığı (SBS/ANSI; hocanın PLATE_SPECS) — test kendi sabitini taşır, mutasyon hedefinden OKUMAZ.
_ARALIK_MM = 19.3
_KIMLIK = [f"{r}{c}" for r in "ABCD" for c in range(1, 7)]


def _beklenen():
    kuyu: dict[str, list[dict]] = {}
    for s in csv.DictReader(open(KAHIN / "beklenen_petri" / "wells.csv", encoding="utf-8")):
        kuyu.setdefault(s["image"], []).append(s)
    ozet = {s["image"]: s for s in csv.DictReader(open(KAHIN / "beklenen_petri" / "summary.csv", encoding="utf-8"))}
    return kuyu, ozet


def _oku(yol: Path):
    import cv2

    img = cv2.imdecode(np.fromfile(str(yol), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, f"kâhin görüntüsü okunamadı: {yol}"
    return img


def _kod(uyari: str) -> str:
    return str(uyari).split(":", 1)[0].strip()


@pytest.fixture(scope="module")
def petri_v2():
    """GERÇEK v2 boru hattı: ürün yapılandırması (`load_cabin_config(None)` = cabin_config_v2.yaml) + ürünün ONNX'i."""
    pytest.importorskip("ultralytics")
    from golden.eser import atla, eser_var_mi

    if not eser_var_mi(_YOLO, _EM):
        atla(f"petri ağırlıkları ürün çözücüsünde yok ({_YOLO}, {_EM})")
    from utils.model_downloader import download_model_sync

    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    pl = PetriCvPipeline(load_cabin_config(None), yolo_model_path=download_model_sync(_YOLO), yolo_device="cpu")
    return pl


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 1. KÂHİN — hocanın 6 plaka fotoğrafı, guii ONNX'i
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════

_RESIMLER = sorted(p.name for p in (KAHIN / "petri").glob("WhatsApp Image *.jpeg"))


def test_kahin_verisi_TAM():
    """Vakum kapısı: 6 görüntü + beklenen satırlar (yoksa parametreli test hiç koşmaz)."""
    kuyu, ozet = _beklenen()
    assert len(_RESIMLER) == 6 and set(_RESIMLER) == set(ozet) == set(kuyu)
    assert all(len(v) == 24 for v in kuyu.values())


@pytest.mark.parametrize("ad", _RESIMLER)
def test_KRITIK_KAHIN_24_kuyucuk_kimlik_etiket_konum(petri_v2, ad):
    kuyu, ozet = _beklenen()
    r, _ = petri_v2.process_image(_oku(KAHIN / "petri" / ad), image_name=ad)
    assert r.success, f"{ad}: başarısız ({r.error}) — plausibility={r.plausibility}"
    assert r.n_wells == 24, f"{ad}: {r.n_wells} kuyucuk (hoca: 24)"
    assert [w.well_id for w in r.wells] == [s["well_id"] for s in kuyu[ad]] == _KIMLIK
    fark = [w.well_id for w, s in zip(r.wells, kuyu[ad]) if w.label != s["label"]]
    assert not fark, f"{ad}: etiket farkı {fark}"
    aralik_px = _ARALIK_MM / float(ozet[ad]["mm_per_px"])
    sapma = [
        math.hypot(w.centroid_px[0] - float(s["cx_px"]), w.centroid_px[1] - float(s["cy_px"]))
        for w, s in zip(r.wells, kuyu[ad])
    ]
    assert max(sapma) < 0.25 * aralik_px, (
        f"{ad}: kuyucuk merkezi hatası {max(sapma):.2f} px ≥ 0,25 aralık ({aralik_px:.1f} px)"
    )
    # Uyarı kodları hocanınkiyle aynı (çekim kalitesi + PEMF çerçevesi); plaka kipi + kabin konumu yok.
    assert sorted(_kod(u) for u in r.warnings) == sorted(_kod(u) for u in ozet[ad]["warnings"].split(" | ") if u)
    assert (r.method, r.coord_frame, r.pemf_valid) == ("plate_grid", "plate", False)
    # ONNX ↔ PT farkı GİZLENMEZ: aday kırpıntısı ONNX'in sabit girişine çekildi, aday sayısı ve kuyucuk kaynağı yanıtta.
    assert r.yolo_ayar.get("aday_imgsz") == 640 and r.yolo_ayar.get("plate_type") == 24
    assert isinstance(r.plate.get("n_yolo_candidates"), int)
    assert {w.source for w in r.wells} <= {"yolo", "hough", "grid"}
    assert r.plausibility.get("kip") == "plaka" and r.plausibility.get("ecc_ok") is True


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2. MAKULLİK — plaka kipi yanlış girdiye 24 kuyucuk DAYATMAZ
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════

_FANTOMLAR = sorted(p.name for p in (KAHIN / "fantom").glob("*.jpeg"))


@pytest.mark.parametrize("ad", _FANTOMLAR)
def test_KRITIK_fantom_fotografi_PLAKA_kipinde_REDDEDILIR(petri_v2, ad):
    """Ölçüldü: hocanın v2'si bu 9 fotoğrafın 9'una 24 kuyucuk + 3–18 "kanser" üretiyordu."""
    from ai_hub.inference_petri_dish import plausibility as pl

    r, _ = petri_v2.process_image(_oku(KAHIN / "fantom" / ad), image_name=ad)
    assert not r.success and r.n_wells == 0, f"{ad}: fantom fotoğrafına {r.n_wells} kuyucuk üretildi"
    if r.error != "plate_not_found":  # pembe bölge hiç bulunmadıysa ızgara da yok (sessiz sonuç değil)
        assert r.error == pl.PETRI_REJECT, r.error
        assert "24 kuyucuklu" in r.plausibility.get("message", ""), r.plausibility


def test_KRITIK_tekil_kap_fotografi_PLAKA_kipinde_REDDEDILIR_TEKIL_kipte_KABUL(petri_v2):
    """`real_petri.jpg` (= 06_PetriKuyu): plaka kipinde 24/24 "kanser" dayatılıyordu; tekil kipte v1 davranışı (8 kap)."""
    from ai_hub.inference_petri_dish import plausibility as pl
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline

    img = _oku(KAHIN / "petri" / "real_petri.jpg")
    r, _ = petri_v2.process_image(img)
    assert r.error == pl.PETRI_REJECT and not r.success and r.wells == []
    tekil = PetriCvPipeline(petri_v2.cfg, plate_type=0, yolo_model_path=petri_v2.yolo.model_path, yolo_device="cpu")
    tekil.yolo, tekil._predictor = petri_v2.yolo, petri_v2._predictor
    r0, _ = tekil.process_image(img)
    assert r0.success and r0.n_wells == 8 and r0.plausibility.get("kip") != "plaka", (r0.error, r0.n_wells)
    assert [w.well_id for w in r0.wells] == [f"W{i}" for i in range(1, 9)]


def test_plaka_makullik_kurali_SAF():
    """Ölçülen sınırlar: gerçek plaka en kötü (ECC ✔, aday 4) GEÇER; plaka dışı (ECC ✔ aday 0 · ECC ✘ aday 4) REDDEDİLİR;
    ölçüm alanı yoksa REDDEDİLİR (fail-closed); denetim kapalıysa geçer ve `guard: off` kayda geçer."""
    from ai_hub.inference_petri_dish import plausibility as pl

    assert pl.evaluate_plate({"n_inliers": 4, "ecc_ok": True}, guard=True)[0] is True
    assert pl.evaluate_plate({"n_inliers": 2, "ecc_ok": True}, guard=True)[0] is True
    for kotu in (
        {"n_inliers": 0, "ecc_ok": True},
        {"n_inliers": 1, "ecc_ok": True},
        {"n_inliers": 4, "ecc_ok": False},
        {"n_inliers": 24},
        {"ecc_ok": True},
        {},
        None,
    ):
        ok, m = pl.evaluate_plate(kotu, guard=True)
        assert ok is False, kotu
        assert "ızgarası doğrulanamadı" in m["message"] and "Tekil petri kapları" in m["message"]
    ok, m = pl.evaluate_plate({"n_inliers": 0, "ecc_ok": False}, guard=False)
    assert ok is True and m["guard"] == "off"


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 3. ONNX UYARLAMASI — model gerekmez
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


class _SahteYolo:
    def __init__(self, yol: str, imgsz: int = 640, patla: bool = False):
        self.model_path, self.imgsz, self.iou, self.device, self._patla = Path(yol), imgsz, 0.7, "cpu", patla
        self.cagri = []

    def _ensure_model(self):
        if self._patla:
            raise RuntimeError("INVALID_ARGUMENT : Got invalid dimensions for input")
        yolo = self

        class _M:
            def predict(self, source, conf, iou, imgsz, device, verbose):
                yolo.cagri.append((source.shape[:2], imgsz))
                return []

        return _M()


def test_KRITIK_ONNX_aday_imgsz_SABIT_girise_cekilir():
    from ai_hub.inference_petri_dish.petri_cv_v2.plate_grid import _yolo_candidates, aday_imgsz

    assert aday_imgsz(_SahteYolo("m/yolo11m-seg.onnx")) == 640
    assert aday_imgsz(_SahteYolo("m/YOLO11M-SEG.ONNX", imgsz=640)) == 640
    assert aday_imgsz(_SahteYolo("m/yolo11m-seg.pt")) == 1280, "PT (hocanın) kipi 1280 kalır"
    y = _SahteYolo("m/yolo11m-seg.onnx")
    _yolo_candidates(np.zeros((400, 900, 3), np.uint8), (0, 0, 900, 400), y, 20.0)
    ((sekil, imgsz),) = y.cagri
    assert imgsz == 640 and max(sekil) == 640, f"ONNX'e {sekil} / imgsz {imgsz} verildi (640 sabit)"


def test_KRITIK_YOLO_aday_hatasi_izgarayi_OLDURMEZ_ama_GORUNUR():
    """YOLO yalnız ipucu (hoca): aday çağrısı düşerse ızgara Hough + ECC ile kurulur, uyarı + aday 0 yanıtta."""
    from ai_hub.inference_petri_dish.petri_cv_v2.plate_grid import detect_plate_wells

    img = _oku(KAHIN / "petri" / "WhatsApp Image 2026-10-02 at 19.40.15(2).jpeg")
    g = detect_plate_wells(img, 24, yolo=_SahteYolo("m/yolo11m-seg.onnx", patla=True))
    assert g.success and len(g.detections) == 24
    assert g.n_yolo_candidates == 0
    assert any(_kod(u) == "yolo_candidates_failed" for u in g.warnings), g.warnings


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 4. guii SERTLEŞTİRMESİ v2 yolunda (3 yollu birleştirme kaybetmedi)
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_v2_EM_ongorucu_PAKET_yolundan_sys_path_hilesi_YOK():
    """Hocanın `../../inference_em_petri` sys.path hilesi alınmadı: modül adı TEK (paket), sys.path'e ai_hub alt dizini girmez."""
    from ai_hub.inference_em_petri import inference_em_petri as paket
    from ai_hub.inference_petri_dish.petri_cv_v2 import pipeline as pp

    assert pp.PetriPredictor is paket.PetriPredictor
    # YAPISAL: paketin HİÇBİR modülü sys.path'e dokunmaz. (Süreç geneli sys.path bakılmaz — aynı koşumda v1 boru hatları
    # hâlâ yüklenebilir ve kendi eklemelerini yapar; ölçülen şey BU paketin davranışı.)
    paket_dizini = Path(pp.__file__).parent
    dokunanlar = [
        y.name
        for y in sorted(paket_dizini.glob("*.py"))
        if re.search(r"sys\.path\.(insert|append)\b", y.read_text(encoding="utf-8"))
    ]
    assert not dokunanlar, f"petri_cv_v2 sys.path hilesi taşıyor: {dokunanlar}"


def test_v2_dedektor_RuntimeError_ve_CAGRI_BASINA_esik_korunur():
    """guii v1 sertleştirmesi: SystemExit DEĞİL RuntimeError (AI Pro iş parçacığından kaçmaz) + paylaşılan dedektörün
    eşiği yazılmaz (cağrı başına conf/iou)."""
    import inspect

    from ai_hub.inference_petri_dish.petri_cv_v2 import petri_detector as pd

    kaynak = inspect.getsource(pd.PetriYoloDetector._ensure_model)
    assert "raise RuntimeError(" in kaynak and "raise SystemExit" not in kaynak
    imza = inspect.signature(pd.PetriYoloDetector.detect)
    assert "conf" in imza.parameters and "iou" in imza.parameters
