# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.91 · B-7.29 · B-7.30 · A-37 (sahip) — DEMA simülatörü TANITIM/EĞİTİM aracıdır ve öyle etiketlenir.

Sahip kararı A-37 (b): açık etiket "tanıtım/eğitim amaçlıdır, cihaz davranışını temsil etmez"; dayanaksız "ISO 13485"
iddiası ve fiziksel modeli olmayan "E-Alan" göstergesi (V/m + "Canlı" rozeti; değer = frekans × yoğunluk / 100) kalkar.
Simülatör dizini CANLI — SİLİNMEZ.

ÖLÇÜLEN KUSUR (07 §B-7.29/B-7.30; 1.9.50'de VAR): başlık "EU ISO 13485 Tıbbi Cihazlar yönetmeliğine uyumlu tek DEMA terapi
cihazıdır", "Canlı" rozetli V/m ölçer; ürün menüsünden erişilen ekran "canlı olarak izleyebilirsiniz" diyordu. Sevk edilen
`dist` depoda TAKİPSİZ: kaynak düzelse de bayat dist iddiaları pakete taşır (ölçüldü: guii'deki dist 4 iddia + etiket yok).

Kapı: (1) kaynak ortak ölçütle (`build_tools.dema_iddia_denetimi`) temiz; (2) spec'in GERÇEK `sim_dir` bloğu AST'den çıkarılıp
bayat ve temiz bir dist'le KOŞTURULUR — bayatta derleme DURUR, temizde gömülür (yorum/metin pini değil, davranış);
(3) `PEMF_DEMA_DIST_ZORUNLU=1` ise gerçek dist de denetlenir (yoksa KIRMIZI; temiz klonda/CI'da dist yok → atlanır).
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_DEMA = _KOK / "dema-terapi-simülatörü"
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

from build_tools.dema_iddia_denetimi import ZORUNLU_ETIKET, denetle  # noqa: E402

_BAYAT_JS = (
    'h1("EU ISO 13485 Tıbbi Cihazlar yönetmeliğine uyumlu tek DEMA terapi cihazıdır.");span("V/m");span("Canlı");'
)


def _kaynak_kopyasi(tmp_path: Path) -> Path:
    hedef = tmp_path / "kaynak"
    (hedef / "src").mkdir(parents=True)
    for rel in ("src/App.tsx", "index.html", "metadata.json"):
        (hedef / rel).write_bytes((_DEMA / rel).read_bytes())
    return hedef


def test_KRITIK_simulator_kaynagi_A37_ile_UYUMLU(tmp_path):
    assert _DEMA.is_dir(), "simulator dizini SILINMEMELI (A-37)"
    sorunlar = denetle(_kaynak_kopyasi(tmp_path))
    assert sorunlar == [], f"simulator kaynagi A-37 ile celisiyor: {sorunlar}"
    assert ZORUNLU_ETIKET in (_DEMA / "src" / "App.tsx").read_text(encoding="utf-8")


def test_KARSIT_olcut_bayat_iddialari_YAKALAR(tmp_path):
    (tmp_path / "index.js").write_text(_BAYAT_JS, encoding="utf-8")
    sorunlar = denetle(tmp_path)
    assert len(sorunlar) == 5, sorunlar  # 4 iddia + etiket yok


def _spec_sim_blogu() -> ast.Module:
    agac = ast.parse((_KOK / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8"))
    bloklar = [
        d
        for d in agac.body
        if isinstance(d, ast.If) and "sim_dir" in ast.unparse(d.test) and "exists" in ast.unparse(d.test)
    ]
    assert len(bloklar) == 1, "spec'te `if os.path.exists(sim_dir):` blogu bulunamadi"
    return ast.Module(body=bloklar, type_ignores=[])


def _spec_kos(sim_dir: Path) -> list:
    ns = {"os": os, "sim_dir": str(sim_dir), "datas": []}
    exec(compile(_spec_sim_blogu(), "PEMF_Backend_onedir.spec", "exec"), ns)  # noqa: S102 — spec'in GERÇEK blogu
    return ns["datas"]


def test_KRITIK_derleme_BAYAT_disti_GOMMEZ_ve_DURUR(tmp_path):
    bayat = tmp_path / "dist"
    (bayat / "assets").mkdir(parents=True)
    (bayat / "assets" / "index-eski.js").write_text(_BAYAT_JS, encoding="utf-8")
    (bayat / "index.html").write_text("<title>My Google AI Studio App</title>", encoding="utf-8")
    with pytest.raises(SystemExit) as hata:
        _spec_kos(bayat)
    assert "ISO 13485" in str(hata.value)


def test_KARSIT_derleme_TEMIZ_disti_gomer(tmp_path):
    temiz = tmp_path / "dist"
    temiz.mkdir()
    (temiz / "index.html").write_text(
        f"<title>DEMA Simülatörü — tanıtım/eğitim amaçlıdır, {ZORUNLU_ETIKET}</title>", encoding="utf-8"
    )
    datas = _spec_kos(temiz)
    assert datas and datas[0][0] == str(temiz), datas


@pytest.mark.skipif(
    os.environ.get("PEMF_DEMA_DIST_ZORUNLU") != "1", reason="dist depoda takipsiz; derleme makinesinde zorunlu"
)
def test_ZORUNLU_gercek_dist_A37_ile_UYUMLU():
    dist = _DEMA / "dist"
    assert dist.is_dir(), "PEMF_DEMA_DIST_ZORUNLU=1 ama dist yok"
    assert denetle(dist) == [], denetle(dist)
