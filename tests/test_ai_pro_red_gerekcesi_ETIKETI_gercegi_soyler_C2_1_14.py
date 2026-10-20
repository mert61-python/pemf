# -*- coding: utf-8 -*-
"""C2-1.14 (2-C inceleme, A1) — AI Pro onay penceresinin red alanı "Red gerekçesi (kayda geçer)" diyor; O-A2.2'den (`3fbdd6e`) beri
gerekçe METNİ hiçbir kalıcı yere yazılmıyor (yalnız süreç belleğindeki öneri kaydında; yeniden başlatmada kaybolur — S-C.1).

Kapı, ekranın verdiği sözü ürünün gerçeğiyle karşılaştırır: pencere kaynağındaki etiket "kayda geçer" diyorsa GERÇEK `/propose` →
`/reject` sonrası gerekçe metni tedavi DB'sinin HERHANGİ bir tablosunda (ham + `\\u` kaçışlı) bulunmalı; bulunmuyorsa etiket bunu
söylememeli. S-C.1'in iki seçeneği de kapıyı yeşile çevirir: (a) metin şifreli tabloda saklanır, (b) etiket "kayda geçmez / yalnız
gerekçe girildiği kaydedilir" der. HEAD'de KIRMIZI (etiket söz veriyor, metin hiçbir tabloda yok). KARAR: S-C.1 — yamalanmadı.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
PENCERE = KOK / "apps" / "ui" / "src" / "components" / "domain" / "AiSpecApprovalModal.tsx"
GEREKCE = "BENZERSIZ-GEREKCE-9431 kilo yüksek"


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc

    o = ap.kur(monkeypatch, tmp_path)
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            yield o
    finally:
        o.geri()


def _tum_tablolarda(db, metin: str) -> list:
    bulunan = []
    kac = json.dumps(metin)[1:-1]
    with db._get_connection() as c:
        tablolar = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tablolar:
            for satir in c.execute(f'SELECT * FROM "{t}"').fetchall():
                for v in tuple(satir):
                    if isinstance(v, str) and (metin in v or kac in v):
                        bulunan.append(t)
    return sorted(set(bulunan))


def test_KRITIK_C2_1_14_red_gerekcesi_etiketi_KAYDA_GECER_diyorsa_metin_kayitta(o):
    kaynak = PENCERE.read_text(encoding="utf-8")
    # I18N: etiket katalogda — kaynak anahtari KULLANIYOR, TR degeri birebir ve EN dolu (metin_kapisi); kapi metni bu degerden okur.
    import i18n_yardimci as iy

    anahtar = re.search(r'<Text style=\{s\.rejectLabel\}>\{t\("([^"]+)"\)\}</Text>', kaynak).group(1)
    iy.metin_kapisi("apps/ui/src/components/domain/AiSpecApprovalModal.tsx", anahtar, "Red gerekçesi (kayda geçer)")
    etiket = iy.katalog("arayuz", "tr")[anahtar]
    o.air._ai_organ_id = 2
    with o.air._ai_cache_lock:
        o.air._ai_organ_cache.update(
            {
                "x_mm": 1.0,
                "y_mm": 2.0,
                "z_mm": 3.0,
                "reliability": 0.9,
                "localized": True,
                "overlay_bgr": None,
                "at": time.time(),
                "organ_id": 2,
                "kedi_var": True,
                "guven_dokumu": None,
                "model": "kedi",
            }
        )
    r = o.c.post("/api/ai/pro/propose", json={"organ_id": 2, "duration_minutes": 5})
    pid = r.json()["proposalId"]
    assert (
        o.c.post(
            "/api/ai/pro/reject", json={"proposal_id": pid, "operator_email": "h@k.com", "reason": GEREKCE}
        ).status_code
        == 200
    )
    o.db.add_ai_analysis(module_id="m", patient_name="P", result_summary="POZITIF-KONTROL-77 ş")
    assert _tum_tablolarda(o.db, "POZITIF-KONTROL-77 ş") == ["ai_analyses"], "araç: tarayıcı bilinen metni bulmalı"
    yerler = _tum_tablolarda(o.db, GEREKCE)
    print(f"\nC2-1.14: etiket={etiket!r} · gerekçenin bulunduğu tablolar={yerler}")
    assert not ("kayda geçer" in etiket and not yerler), (
        f"pencere '{etiket}' diyor ama gerekçe metni hiçbir kalıcı tabloda yok (O-A2.2 sonrası; S-C.1 bekliyor)"
    )
