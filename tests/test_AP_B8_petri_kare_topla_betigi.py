# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP · B8 (istem 48 · S-AP.8 "ayrı betik"): petri YOLO yeniden eğitimi / eşik ölçümü için kabin kamerası KARE TOPLAMA betiği.
Sözleşme: renkli kayıpsız PNG + kare başına ızgara tanısı (`tani.csv`); okunamayan kare atlanır; veri köküne YAZMAZ; ağa ÇIKMAZ (YOLO yerelden,
indirme yolu çağrılmaz); kamera seçilmemişse / açılamazsa eylem söyleyip çıkar. Kamera ve hat SAHTE (gerçek kamera / model açılmaz)."""

import csv
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture()
def betik():
    spec = importlib.util.spec_from_file_location("petri_kare_topla", KOK / "scripts" / "petri_kare_topla.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Kamera:
    def __init__(self, kareler):
        self._k = list(kareler)
        self.birakildi = False

    def isOpened(self):
        return True

    def read(self):
        if not self._k:
            return False, None
        k = self._k.pop(0)
        return (k is not None), k

    def release(self):
        self.birakildi = True


def _kare(r):
    k = np.zeros((48, 64, 3), np.uint8)
    k[:, :, 0] = (np.arange(64)[None, :] * 7 + np.arange(48)[:, None] * 13) % 256  # doku: kayıplı kodlama bunu bozar
    k[:, :, 2] = r
    return k


def test_KRITIK_kareler_RENKLI_kayipsiz_ve_tani_csv(betik, tmp_path):
    import cv2

    uykular = []
    cap = _Kamera([_kare(10), None, _kare(20), _kare(30)])
    satirlar = betik.topla(
        cap, 3, 1.5, tmp_path / "c", tani=lambda k: {"yolo_aday": 7, "ecc": True}, uyu=uykular.append
    )
    assert [s["kare"] for s in satirlar] == ["kare_0001.png", "kare_0002.png", "kare_0003.png"]
    oku = cv2.imdecode(np.frombuffer((tmp_path / "c" / "kare_0002.png").read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    assert oku.shape == (48, 64, 3) and np.array_equal(oku, _kare(20))  # renkli, KAYIPSIZ, okunamayan kare ATLANDI
    satir = list(csv.DictReader(open(tmp_path / "c" / "tani.csv", encoding="utf-8")))
    assert len(satir) == 3 and satir[0]["yolo_aday"] == "7" and satir[0]["ecc"] == "True"
    assert uykular.count(1.5) == 2  # son kareden sonra beklenmez


def test_tani_hatasi_kareyi_DUSURMEZ(betik, tmp_path):
    def _bozuk(_k):
        raise ValueError("x")

    s = betik.topla(_Kamera([_kare(1)]), 1, 0, tmp_path / "c", tani=_bozuk, uyu=lambda _s: None)
    assert s[0]["uyarilar"] == "tani_hatasi: ValueError"


def test_KRITIK_veri_kokune_YAZMAZ(betik, tmp_path, monkeypatch):
    betik._yollari_kur()
    import utils.path_utils as pu

    kok = tmp_path / "ProgramData" / "PEMF_System" / "PEMF_GUI"
    kok.mkdir(parents=True)
    monkeypatch.setattr(pu, "get_app_data_directory", lambda *a, **k: str(kok))
    from utils import kabin_kamerasi

    monkeypatch.setattr(
        kabin_kamerasi, "kamera_ac", lambda *a, **k: pytest.fail("veri kökü reddinden ÖNCE kamera açıldı")
    )
    assert betik.main(["--cikti", str(kok / "kareler"), "--tanisiz"]) == 2
    assert not (kok / "kareler").exists()


def test_KRITIK_model_yerelde_YOKSA_petri_paketi_YUKLENMEDEN_YOLOsuz_taniya_duser(betik, monkeypatch):
    # Model çözücü ağa ÇIKMAZ ("Hugging Face indirme KALDIRILDI"); yerelde yoksa YOLO'suz tanı. Dosya yokken petri paketi İÇE AKTARILMAZ:
    # aktarım ürünün öteki petri modellerini de çözer — C08 kapısında sahte yol süreçteki sonraki 9 petri testine sızdı (kirlilik).
    betik._yollari_kur()
    import utils.model_downloader as md

    monkeypatch.setattr(md, "yan_dosya_coz", lambda yerel, goreli: str(Path(yerel).with_name("yok.onnx")))

    class _Yasak(types.ModuleType):
        def __getattr__(self, ad):
            if ad.startswith("__"):
                raise AttributeError(ad)
            pytest.fail(f"model dosyası yokken petri dedektörü içe aktarıldı ({ad})")

    monkeypatch.setitem(sys.modules, "ai_hub.inference_petri_dish.petri_cv_v2.petri_detector", _Yasak("petri_detector"))
    assert betik.yolo_kur() is None


def test_kamera_secilmemisse_EYLEM_soyleyip_cikar(betik, tmp_path, monkeypatch, capsys):
    betik._yollari_kur()
    from utils import kabin_kamerasi

    def _secilmedi(*a, **k):
        raise kabin_kamerasi.KameraSecilmedi()

    monkeypatch.setattr(kabin_kamerasi, "kamera_ac", _secilmedi)
    assert betik.main(["--cikti", str(tmp_path / "c"), "--tanisiz"]) == 3
    assert "!!!" in capsys.readouterr().out


def test_ucdan_uca_sahte_kamera_ile_main(betik, tmp_path, monkeypatch):
    betik._yollari_kur()
    from utils import kabin_kamerasi

    cap = _Kamera([_kare(5)] * (betik.ISINMA + 2))
    monkeypatch.setattr(kabin_kamerasi, "kamera_ac", lambda *a, **k: (cap, 0))
    monkeypatch.setattr(betik.time, "sleep", lambda _s: None)
    assert betik.main(["--cikti", str(tmp_path / "c"), "--adet", "2", "--aralik", "0", "--tanisiz"]) == 0
    assert sorted(p.name for p in (tmp_path / "c").iterdir()) == ["kare_0001.png", "kare_0002.png", "tani.csv"]
    assert cap.birakildi
