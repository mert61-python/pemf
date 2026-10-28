# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D7.02 · DENETIM-12 §3.2 P2 — kedi AI Pro ek EM girdileri TEK KAYNAK: `ai_router._AI_ACHIEVED_B` / `_AI_DUTY_SUM` =
`ai_pro_hedef.KEDI_ACHIEVED_B` / `KEDI_DUTY_SUM` (adlar korunur).

ÖLÇÜLEN (HEAD ebf1c3fe): iki modülde AYRI literal (`ai_router.py:704-705` 0.001 / 1.5 ↔ `ai_pro_hedef.py:37-38` 0.001 / 1.5).
Sürüş (`_predict_and_drive_cpu/_gpu`) ai_router kopyasını, XAI açıklaması (`KediSaglayici.xai_sensitivity`) ve onay metası
ai_pro_hedef kopyasını okuyor. Sahip kararı #9 ("açıklama dozun FİİLEN hesaplandığı girdilerle") yalnız TESADÜFİ eşitlikle
tutuyordu: sürüş tarafı değişince açıklama başka bir çalışma noktasını anlatır ve hiçbir test kırmızı olmaz.

A (davranış): gerçek `_predict_and_drive_cpu` ile gerçek `KediSaglayici().xai_sensitivity`'nin sahte modele verdiği ek girdiler EŞİT
ve tarihsel değerde (0.001 / 1.5 — testte pinli). B (yapı): ai_router'da modül düzeyinde TAM 1 atama, değeri
`ai_pro_hedef.KEDI_*` niteliği (literal değil). Y142: kedi AI Pro SÜRÜŞÜ KAPALI kalır — bu kapı sürüşü açmaz, yalnız işlevleri
doğrudan çağırır.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"
_TARIHSEL = {"achieved_B": 0.001, "duty_sum": 1.5}  # eski camera_ai_thread ile birebir (pinli)


class _SahteKedi:
    def __init__(self):
        self.cagri: list = []

    def predict(self, **k):
        self.cagri.append(k)
        return {f"D{i}": 0.1 for i in range(1, 8)} | {f"P{i}": 0.0 for i in range(1, 8)} | {"result_E": 1.0}


def test_A_kedi_surus_ve_XAI_AYNI_ek_girdilerle(monkeypatch):
    import servers.ai_router as air
    from servers import ai_pro_hedef

    sahte = _SahteKedi()
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: sahte)
    D, P, E = air._predict_and_drive_cpu(10.0, -5.0, 3.0, 2)
    assert len(D) == 7 and len(P) == 7 and E == 1.0
    assert len(sahte.cagri) == 1
    surus = {k: sahte.cagri[0].get(k) for k in ("achieved_B", "duty_sum")}

    xai_gelen: list = []
    sahte_iek = types.ModuleType("ai_hub.em_kedi.inference_em_kedi")

    def _xai(model, x, y, z, hedef, achieved_B=None, duty_sum=None):
        xai_gelen.append({"achieved_B": achieved_B, "duty_sum": duty_sum})
        return {"ok": True}

    sahte_iek.xai_hizli_sensitivity = _xai
    import ai_hub.em_kedi as _paket

    monkeypatch.setitem(sys.modules, "ai_hub.em_kedi.inference_em_kedi", sahte_iek)
    monkeypatch.setattr(_paket, "inference_em_kedi", sahte_iek, raising=False)
    ai_pro_hedef.KediSaglayici().xai_sensitivity(10.0, -5.0, 3.0, 2)
    assert len(xai_gelen) == 1
    assert surus == xai_gelen[0], (
        f"sürüş {surus} ↔ XAI açıklaması {xai_gelen[0]} — açıklama BAŞKA çalışma noktasını anlatıyor"
    )
    assert surus == _TARIHSEL, f"kedi ek girdileri tarihsel değerden kaydı: {surus} ≠ {_TARIHSEL}"


def test_A2_GPU_yolu_da_ayni_ek_girdileri_gonderir(monkeypatch):
    """İkiz çağrı yeri: `_predict_and_drive_gpu` (GPU servisine devir) aynı ek girdileri taşır."""
    import servers.ai_router as air

    giden: list = []

    def _devret(ad, govde, *a, **k):
        giden.append((ad, dict(govde)))
        return {f"D{i}": 0.1 for i in range(1, 8)} | {f"P{i}": 0.0 for i in range(1, 8)} | {"result_E": 1.0}

    monkeypatch.setattr(air, "delegate_json_sync", _devret)
    air._predict_and_drive_gpu(10.0, -5.0, 3.0, 2)
    assert giden and giden[0][0] == "em_kedi"
    assert {k: giden[0][1].get(k) for k in ("achieved_B", "duty_sum")} == _TARIHSEL


def _modul_atamalari(ad: str) -> list:
    agac = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    return [
        d
        for d in agac.body
        if (isinstance(d, ast.Assign) and any(isinstance(h, ast.Name) and h.id == ad for h in d.targets))
        or (isinstance(d, ast.AnnAssign) and isinstance(d.target, ast.Name) and d.target.id == ad)
    ]


def test_B_ai_router_ek_girdileri_TEK_KAYNAKTAN_baglar():
    import servers.ai_router as air
    from servers import ai_pro_hedef

    for yerel, kaynak in (("_AI_ACHIEVED_B", "KEDI_ACHIEVED_B"), ("_AI_DUTY_SUM", "KEDI_DUTY_SUM")):
        atamalar = _modul_atamalari(yerel)
        assert len(atamalar) == 1, f"{yerel}: modül düzeyinde {len(atamalar)} atama (tam 1 olmalı)"
        deger = atamalar[0].value
        assert (
            isinstance(deger, ast.Attribute)
            and deger.attr == kaynak
            and isinstance(deger.value, ast.Name)
            and deger.value.id == "ai_pro_hedef"
        ), (
            f"{yerel} = {ast.unparse(deger)} — `ai_pro_hedef.{kaynak}` niteliğine bağlanmalı (ikinci literal kopya YASAK)"
        )
        assert getattr(air, yerel) is getattr(ai_pro_hedef, kaynak) or getattr(air, yerel) == getattr(
            ai_pro_hedef, kaynak
        )
