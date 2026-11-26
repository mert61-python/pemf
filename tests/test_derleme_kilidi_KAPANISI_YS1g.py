# -*- coding: utf-8 -*-
"""YS1g (26-11): DERLEME KİLİDİ (`build_tools/myenv-requirements.txt`) KAPALI olmalı — kilitteki her paketin koşulsuz (extra'sız, bu
platformda geçerli) bağımlılığı ya kilitte ya da gerekçeli BİLİNÇLİ_DIŞARIDA listesinde.

NEDEN: CI ürün ortamını `scripts/bootstrap.ps1` ile AYNI komutla kurunca (`pip install --no-deps -r build_tools/myenv-requirements.txt`)
`import albumentations` (simsimd / stringzilla) ve `import celldetection` (pynvml → nvidia-ml-py, segmentation-models-pytorch) DÜŞTÜ: derleme
makinesinde elle kuruluydular, kilitte YOKTULAR → donmuş EXE çalışıyordu ama kilitten yeni makinede kurulan ortam BOZUKTU.
Ortam: çalışan yorumlayıcının kurulu dağıtımları (CI = taze kilit ortamı; yerel = gömülü derleme Python'u) — kilidin TAMAMI kurulu olmalı
(yoksa ölçüm kör).
"""

from __future__ import annotations

import importlib.metadata as md
import re
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

KOK = Path(__file__).resolve().parents[1]
KILIT = KOK / "build_tools" / "myenv-requirements.txt"

#: Kilitteki bir paketin istediği ama kilide BİLEREK girmeyen dağıtımlar (her biri gerekçeli; kullanılmayan satır KIRMIZI).
BILINCLI_DISARIDA = {
    "opencv-python-headless": "ürün opencv-python kullanır; headless kurulum sonrası KALDIRILIR (kilit notu: albumentations / grad-cam)",
    "opencv-contrib-python": "D3.41: kurulu görünen 4.9.0.80 BAYAT İKİZ meta veri — cv2 dosyaları opencv-python'dan (kilit notu)",
    "tensorboard": "celldetection yalnız eğitim günlüğünde kullanır; içe aktarmada GEREKMEZ (YS1g: taze kilit ortamında ölçüldü)",
    "pip": "kurulum aracı (pip-api) — her Python ortamında zaten var",
    "setuptools": "kurulum aracı (pyinstaller) — sanal ortam / gömülü Python ile gelir",
}


def _ad(s: str) -> str:
    return re.sub(r"[-_.]+", "-", s).lower()


def _kilit(metin: str | None = None) -> dict[str, str]:
    sabit = {}
    for satir in (metin if metin is not None else KILIT.read_text(encoding="utf-8")).splitlines():
        m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#;]+)", satir)
        if m:
            sabit[_ad(m.group(1))] = m.group(2)
    return sabit


def _eksikler(kilit_metni: str | None = None) -> tuple[dict[str, set[str]], list[str]]:
    kilit = _kilit(kilit_metni)
    kurulu = {_ad(d.metadata["Name"]): d for d in md.distributions()}
    kurulmamis = sorted(p for p in kilit if p not in kurulu)
    ortam = {**default_environment(), "extra": ""}
    eksik: dict[str, set[str]] = {}
    for p in kilit:
        if p not in kurulu:
            continue
        for r in kurulu[p].requires or []:
            req = Requirement(r)
            if req.marker is not None and not req.marker.evaluate(ortam):
                continue
            if _ad(req.name) not in kilit:
                eksik.setdefault(_ad(req.name), set()).add(p)
    return eksik, kurulmamis


def test_KRITIK_derleme_kilidi_KAPALI_kilitteki_paketlerin_bagimliligi_kilitte():
    eksik, kurulmamis = _eksikler()
    assert len(_kilit()) >= 200, "kilit okunamıyor / küçülmüş — kapı kör"
    assert not kurulmamis, (
        f"kilitteki paketler bu ortamda KURULU DEĞİL (ölçüm kör / ortam kilitten sapmış): {kurulmamis[:20]}"
    )
    acik = {k: sorted(v) for k, v in eksik.items() if k not in BILINCLI_DISARIDA}
    assert not acik, (
        f"derleme kilidinde OLMAYAN koşulsuz bağımlılık(lar): {acik} — kilitten (--no-deps) kurulan ortamda bu paketler EKSİK kalır "
        "(albumentations / celldetection vakası). Kilide derleme ortamındaki sürümle ekleyin ya da gerekçesiyle BİLİNÇLİ_DIŞARIDA'ya yazın."
    )


def test_KRITIK_BILINCLI_DISARIDA_listesi_BAYATLAMAZ():
    eksik, _ = _eksikler()
    bayat = sorted(k for k in BILINCLI_DISARIDA if k not in eksik)
    assert not bayat, f"BİLİNÇLİ_DIŞARIDA'da artık hiçbir kilit paketinin istemediği satır(lar): {bayat} — kaldırın"


def test_KARSIT_kapi_YENI_kilitteki_YS1g_ekleri_olmadan_YAKALAR():
    """Mutasyon benzetimi: YS1g'de eklenen 4 satır kilitten düşünce kapı onları ADIYLA söyler."""
    gercek = KILIT.read_text(encoding="utf-8")
    dusuk = "\n".join(
        s
        for s in gercek.splitlines()
        if not re.match(r"^(simsimd|stringzilla|nvidia-ml-py|segmentation-models-pytorch)==", s)
    )
    eksik, _ = _eksikler(dusuk)
    assert {"simsimd", "stringzilla", "nvidia-ml-py", "segmentation-models-pytorch"} <= set(eksik), sorted(eksik)
