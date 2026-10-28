# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.19 · B-5.20 · Y19 — Scratch "Analiz" paneli ile closure metrikleri AYNI bandı KULLANMIYOR; yorum bunu söyler.

ÖLÇÜLEN (HEAD ebf1c3fe): `draw_analysis` docstring'i "closure metrikleri de ayni bandi kullanir" diyordu. Gerçek: Analiz paneli
`HALF_BAND_RATIO` (yarı-bant max(50 px, %10) → ~%20) ile, closure metrikleri ve Kapanma paneli `SCRATCH_ROI_RATIO` (%30) ile
çalışır — 1600 px'te [640, 960) ↔ [560, 1040). Sahip kararı Y19: bant EŞİTLENMEZ (metrikler değişmez, geçmiş analizlerle
kıyaslanabilirlik); YALNIZ etiket / yorum düzelir.

Kapı: (1) davranış PİNİ — iki bant bugünkü değerlerinde (panel çizgileri renk maskesiyle ölçülür; closure `roi_bas/roi_son`),
eşitlenirse (Y19 ihlali) KIRMIZI; (2) yorum gerçeği söyler — yanlış "aynı bant" cümlesi YOK, iki oran ve Y19 VAR.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import capraz
import numpy as np

cv2 = capraz.paket_yoksa_atla("cv2")

KOK = Path(__file__).resolve().parents[1]
MODUL_YOLU = KOK / "ai_hub" / "inference_paper_dilek_hoca" / "inference_paper_dilek_hoca.py"


def _modul():
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as m

    return m


def _kirmizi_kolonlar(rgb: np.ndarray) -> list[int]:
    """Analiz panelindeki DİKEY kırmızı bant çizgilerinin kolonları (metin glifleri üst 80 satırda — dışarıda)."""
    govde = rgb[100:, :, :]
    k = (govde[..., 0] > 200) & (govde[..., 1] < 80) & (govde[..., 2] < 80)
    dolu = k.sum(axis=0)
    return [int(x) for x in np.where(dolu > 0.9 * govde.shape[0])[0]]


def test_KRITIK_analiz_paneli_bandi_yuzde20_closure_bandi_yuzde30_AYRI_Y19():
    m = _modul()
    w, h = 1600, 400
    maske = np.full((h, w), 255, dtype=np.uint8)
    maske[:, 780:820] = 0  # ortada dikey yara
    panel = m.draw_analysis(maske, dikey_kusak=True)
    kolon = _kirmizi_kolonlar(panel)
    assert kolon, "panelde dikey bant çizgisi bulunamadı (ölçüm aparatı)"
    # cv2.line kalınlık 3 → her çizgi birkaç kolon; çizgi MERKEZİ = kümenin ortası (sol çizgi `left`, sağ çizgi `right - 1`)
    orta = w // 2
    sol_k = [c for c in kolon if c < orta]
    sag_k = [c for c in kolon if c > orta]
    assert sol_k and sag_k, f"iki bant çizgisi bekleniyordu: {kolon}"
    sol = round((min(sol_k) + max(sol_k)) / 2)
    sag = round((min(sag_k) + max(sag_k)) / 2)
    assert (sol, sag) == (640, 959), (
        f"Analiz paneli bandı çizgileri {sol} / {sag} — beklenen 640 / 959, yani [640, 960) (~%20)"
    )
    r = m.compute_closure_metrics(maske, scratch_yonu="dikey")
    assert (r["roi_bas"], r["roi_son"]) == (560, 1040), (
        f"closure bandı {r['roi_bas']}-{r['roi_son']} — beklenen [560, 1040) (%30)"
    )
    # Y19: bant EŞİTLENMEDİ — eşitleme ya panel sayılarını ya closure metriklerini değiştirir.
    assert (sol, sag + 1) != (r["roi_bas"], r["roi_son"])


def _docstring(ad: str) -> str:
    agac = ast.parse(MODUL_YOLU.read_text(encoding="utf-8"))
    for dugum in agac.body:
        if isinstance(dugum, ast.FunctionDef) and dugum.name == ad:
            return ast.get_docstring(dugum) or ""
    raise AssertionError(f"{ad} bulunamadı")


def test_yorum_GERCEGI_soyler_ayni_bant_iddiasi_YOK():
    doc = _docstring("draw_analysis")
    duz = " ".join(doc.split())
    assert "closure metrikleri de ayni bandi kullanir." not in duz, f"yanlış 'aynı bant' iddiası duruyor: {doc!r}"
    assert "HALF_BAND_RATIO" in duz and "SCRATCH_ROI_RATIO" in duz and "%20" in duz and "%30" in duz, (
        f"docstring iki bandı (Analiz ~%20 / closure %30) söylemiyor: {doc!r}"
    )
    assert "Y19" in duz, "bandın bilerek ayrı kaldığı (Y19) yazmıyor"
    # D67 orkestratör mutantları YAŞADI (yalnız eski cümlenin birebir hâli aranıyordu): "aynı bant" iddiası başka sözcüklerle de YOK;
    # oranlar doğru sabite bağlı (%20 ↔ %30 ters yazılamaz). "Eski ... cumlesi YANLISTI" tarihçe cümlesi iddia sayılmaz.
    iddia = re.sub(r"Eski \"[^\"]*\"\s*cumlesi YANLISTI\.?", "", duz)
    assert not re.search(r"ayn[iı]\s+(\w+\s+)?band", iddia, flags=re.IGNORECASE), (
        f"'aynı bant' iddiası (başka sözcüklerle) duruyor: {doc!r}"
    )
    assert re.search(r"HALF_BAND_RATIO\s+ile\s+~?%20", duz) and re.search(r"SCRATCH_ROI_RATIO\s+ile\s+%30", duz), (
        f"oranlar sabitlerine ters / bağsız yazılmış (Analiz HALF_BAND_RATIO ~%20, closure SCRATCH_ROI_RATIO %30): {doc!r}"
    )
    kaynak = MODUL_YOLU.read_text(encoding="utf-8")
    sabit = [ln for ln in kaynak.splitlines() if ln.startswith("HALF_BAND_RATIO =")]
    assert len(sabit) == 1 and "Analiz paneli" in sabit[0], f"HALF_BAND_RATIO satır yorumu kapsamı söylemiyor: {sabit}"


def test_yanlis_ayni_bant_iddiasi_MODULUN_HICBIR_yerinde_canli_degil():
    """Tur 2 kolu (çürütücü — yorum içine taşıma / ikiz satır): yanlış "closure metrikleri de aynı bandı kullanır" iddiası
    yalnız `draw_analysis` docstring'inde değil, modülün HİÇBİR yorumunda / dizesinde canlı durmaz (tek izinli geçiş: tırnak
    içinde "… cumlesi YANLISTI" tarihçesi). `SCRATCH_ROI_RATIO` satır yorumu da kapsamını söyler (closure; Analiz paneli DEĞİL)."""
    import re

    kaynak = MODUL_YOLU.read_text(encoding="utf-8")
    duz = " ".join(kaynak.replace("#", " ").split())
    iddia = "closure metrikleri de ayni bandi kullanir"
    canli = [
        duz[max(0, m.start() - 60) : m.end() + 30]
        for m in re.finditer(re.escape(iddia), duz)
        if not duz[m.end() :].startswith('" cumlesi YANLISTI')
    ]
    assert not canli, f"yanlış 'aynı bant' iddiası modülde canlı: {canli}"
    roi = [ln for ln in kaynak.splitlines() if ln.startswith("SCRATCH_ROI_RATIO =")]
    assert len(roi) == 1 and "closure" in roi[0] and "Analiz paneli DEGIL" in roi[0], (
        f"SCRATCH_ROI_RATIO satır yorumu kapsamını (closure; Analiz paneli DEĞİL) söylemiyor: {roi}"
    )
