# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-5.30 · CKD SHAP açıklaması EŞZAMANLI istekte de deterministik — küresel RNG kritik bölgesi kilitli (D67, 2026-10-28).

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe): `xai_top_features` determinizmi küresel `np.random` üzerine kurulu (get_state → seed(0) →
KernelExplainer → set_state). shap 0.49.1 KernelExplainer'ın seed parametresi YOK; koalisyon örneklemesi küresel
`np.random.choice` / `np.random.permutation` kullanır. Router (`asyncio.to_thread`) ve ai_service istekleri iş parçacıklarında
koşar → bir isteğin seed(0)'ı ötekinin örneklemesini ortadan keser, get_state/set_state sırası karışır.
Ölçüm (sonda, 50 iş parçacığı Barrier ile aynı anda): 50 FARKLI sonuç, 0'ı tek iş parçacığı sonucuna eşit (ilk-7 kümesi bile
değişti: `pe` düştü, `pcv` girdi; 1. sıra sg↔htn yer değiştirdi); küresel RNG durumu çağrı öncesine DÖNMEDİ.
KÖR KAPI: `test_ckd_xai.py::test_KRITIK_ckd_xai_DETERMINISTIK` seed(0) SİLİNİNCE de yeşil (12/12) — get_state/set_state ardışık iki
çağrıyı AYNI ön-duruma döndürdüğü için seed'siz de eşit çıkıyor (ölçüldü: seed'siz, 10 farklı ön-durum → 10 farklı sonuç).

KAPI:
  (1) farklı küresel ön-durumlarda (seed 1 / 2 / 3) sonuç BİREBİR aynı (seed(0) silinirse KIRMIZI);
  (2) ardışık çağrı küresel RNG durumunu çağrı öncesine döndürür (set_state silinirse KIRMIZI);
  (3) N iş parçacığı Barrier ile AYNI ANDA → hepsi tek iş parçacığı sonucuna eşit + küresel durum geri döner (kilitsiz KIRMIZI).
Düzeltme tek çağrının DEĞERİNİ değiştirmez (kritik bölge yalnız sıralanır).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from golden.eser import ckd_eserleri as _ckd_eserleri
from golden.eser import eser_var_mi as _eser_var_mi
from golden.eser import zorunlu_mu as _zorunlu_mu

_MODEL_VAR = _eser_var_mi(*_ckd_eserleri())
gercek_model_gerekir = pytest.mark.skipif(
    not _MODEL_VAR and not _zorunlu_mu(),
    reason="CKD ONNX/preprocessor yerel degil (gitignore'lu model agirligi) — gercek-model testi yalniz modelli ortamda",
)

#: Eşzamanlı iş parçacığı sayısı (sonda 50 ile ölçtü; kapı süresi için 16 — HEAD'de 16'da da hepsi ayrışıyor).
N_ES = 16

_HASTA = {
    "age": 62,
    "bp": 90,
    "sg": 1.01,
    "al": 3,
    "su": 0,
    "bgr": 140,
    "bu": 55,
    "sc": 2.8,
    "sod": 132,
    "pot": 4.9,
    "hemo": 9.1,
    "pcv": 29,
    "wc": 9800,
    "rc": 3.9,
    "rbc": "abnormal",
    "pc": "abnormal",
    "pcc": "present",
    "ba": "notpresent",
    "htn": "yes",
    "dm": "yes",
    "cad": "no",
    "appet": "poor",
    "pe": "yes",
    "ane": "yes",
}


def _durum_esit(a, b) -> bool:
    return len(a) == len(b) and all(np.array_equal(x, y) if isinstance(x, np.ndarray) else x == y for x, y in zip(a, b))


@gercek_model_gerekir
def test_KRITIK_ckd_xai_KURESEL_on_durumdan_BAGIMSIZ():
    """Seed(0) kritik bölgede kurulmalı: farklı küresel ön-durumlarda sonuç BİREBİR aynı (4 ondalık, sıra dahil)."""
    from ai_hub.inference_human_kidney_disease import xai_top_features

    sonuclar = []
    for tohum in (1, 2, 3):
        np.random.seed(tohum)
        sonuclar.append(xai_top_features(_HASTA, top_n=7))
    assert sonuclar[0] == sonuclar[1] == sonuclar[2], (
        "CKD açıklaması çağrı öncesi küresel RNG durumuna göre değişiyor (seed(0) kritik bölgede kurulmuyor): "
        f"{[r['top_features'][:3] for r in sonuclar]}"
    )


@gercek_model_gerekir
def test_KRITIK_ckd_xai_KURESEL_RNG_durumunu_GERI_YUKLER():
    from ai_hub.inference_human_kidney_disease import xai_top_features

    np.random.seed(4242)
    once = np.random.get_state()
    xai_top_features(_HASTA, top_n=7)
    assert _durum_esit(once, np.random.get_state()), (
        "xai_top_features küresel np.random durumunu çağrı öncesine döndürmüyor (set_state yok) — başka kodun RNG akışı bozulur"
    )


@gercek_model_gerekir
def test_KRITIK_ckd_xai_ESZAMANLI_isteklerde_DETERMINISTIK():
    """N iş parçacığı Barrier ile AYNI ANDA aynı hastayı açıklar → hepsi tek iş parçacığı sonucuna eşit."""
    from ai_hub.inference_human_kidney_disease import xai_top_features

    ref = xai_top_features(_HASTA, top_n=7)
    np.random.seed(777)
    once = np.random.get_state()
    engel = threading.Barrier(N_ES, timeout=120)

    def _is(_i):
        engel.wait()
        return xai_top_features(_HASTA, top_n=7)

    with ThreadPoolExecutor(max_workers=N_ES) as ex:
        sonuclar = list(ex.map(_is, range(N_ES)))
    sonra = np.random.get_state()

    farkli = [r for r in sonuclar if r != ref]
    assert not farkli, (
        f"eşzamanlı {N_ES} istekte {len(farkli)} açıklama tek iş parçacığı sonucundan FARKLI (küresel np.random yarışı): "
        f"ref={ref['top_features'][:3]} örnek={farkli[0]['top_features'][:3]}"
    )
    assert _durum_esit(once, sonra), (
        "eşzamanlı isteklerden sonra küresel np.random durumu çağrı öncesine dönmedi (geri yükleme yarışı)"
    )


@gercek_model_gerekir
def test_HATA_yolunda_da_KURESEL_durum_geri_yuklenir_ve_kilit_BIRAKILIR(monkeypatch):
    """Tur 2 kolu (çürütücü — koruyucu hata yolu): açıklayıcı kritik bölgede İSTİSNA fırlatırsa (bozuk arka plan, shap
    yükseltmesi, bellek) küresel np.random durumu YİNE çağrı öncesine döner (`finally`) ve kilit bırakılır — aksi hâlde tek
    bir hatalı istek sürecin geri kalanındaki RNG akışını seed(0)'da bırakır ya da sonraki tüm CKD açıklamalarını kilitler."""
    import shap

    from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as ihd
    from ai_hub.inference_human_kidney_disease import xai_top_features

    class _SahteHata(RuntimeError):
        pass

    def _patlayan(*_a, **_k):
        np.random.random(5)  # seed(0) sonrası akışı ilerlet — geri yüklenmezse durum kirli kalır
        raise _SahteHata("sahte KernelExplainer hatası (İG-5.30 tur 2 kolu)")

    monkeypatch.setattr(shap, "KernelExplainer", _patlayan)
    np.random.seed(777)
    once = np.random.get_state()
    with pytest.raises(_SahteHata):
        xai_top_features(_HASTA, top_n=7)
    assert _durum_esit(once, np.random.get_state()), (
        "açıklayıcı hata verdiğinde küresel np.random durumu çağrı öncesine DÖNMEDİ (hata yolunda set_state yok)"
    )
    assert ihd._SHAP_RNG_KILIDI.acquire(timeout=2), "açıklayıcı hata verdiğinde kilit BIRAKILMADI"
    ihd._SHAP_RNG_KILIDI.release()
