# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.56 · B-4.25 · Y17 — `exe/latest.json`: "kural yok" ile "okunamadı" AYRI raporlanır (kilit) ve `update_manager`
yorumu ölçülen gerçeği söyler.

ÖLÇÜLEN (DENETIM-04 B-4.25, 2026-09-24): `exe/latest.json` 200 döner (yorum "404 döner" diyordu) — içerik 2026-07-01'den
beri değişmemiş 1.4.0 taslağı: anahtarlar `installerUrl/mandatory/notes/sha256/version`, `installerUrl=''`,
`firmware`/`uyumluluk` YOK. Oto-firmware zinciri (`firmware_manager.manifest_oku`) AYNI dosyayı okur. Kanalı "ölü" sanan
biri zincirin neye bağlı olduğunu yanlış değerlendirir (kat. 6). Sahip Y17: uyum kuralları AYRI bir yayın varlığında
yayınlanacak (D1.120).

KÖR KAPI (ölçüldü, bu commit'te): iki dalı "okunamadı" sınıfına çökerten mutant (kuralsız manifest → BEKLE "manifest
okunamadı") mevcut `test_firmware_manager.py`de YEŞİL kalıyordu — gerçek içerikle davranış hiç kilitli değildi.
"""

from __future__ import annotations

import importlib
import io
import re
import tokenize
from pathlib import Path

import pytest
from utils import surum_uyumu as su

KOK = Path(__file__).resolve().parents[1]
UPDATE_MANAGER = KOK / "apps" / "backend" / "servers" / "update_manager.py"

#: Ölçülen `exe/latest.json` (B-4.25) — aynı anahtarlar, aynı boşluklar; `firmware`/`uyumluluk` YOK.
GERCEK_LATEST = {"version": "1.4.0", "installerUrl": "", "sha256": "", "mandatory": False, "notes": "taslak"}


@pytest.fixture()
def fm(monkeypatch):
    m = importlib.import_module("servers.firmware_manager")
    importlib.reload(m)  # modül-global durum testler arasında sızmasın
    monkeypatch.setattr(m.um, "get_current_version", lambda: "1.9.51")
    monkeypatch.setattr(m.um, "get_status", lambda: {"previousStable": {"version": "1.9.20"}})
    return m


def test_KRITIK_gercek_latest_json_KURAL_YOK_der_eylem_yok_okunamadi_DEGIL(fm, monkeypatch):
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: dict(GERCEK_LATEST))
    indir: list = []
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: indir.append(a) or (None, "x"))
    d = fm.acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=True)
    assert d["eylem"] == su.EYLEM_YOK, f"kuralsız gerçek manifestte eylem {d['eylem']!r}: {d['gerekce']}"
    assert "uyumluluk kuralı YOK" in d["gerekce"], d["gerekce"]
    assert "okunamad" not in d["gerekce"], f"'kural yok' 'okunamadı' sınıfında raporlandı: {d['gerekce']}"
    assert not indir and d["uygulandi"] is False, "kuralsız manifestte indirme/yakma denendi"


def test_KRITIK_okunamayan_manifest_BEKLE_ve_kural_yok_ile_AYNI_SINIF_DEGIL(fm, monkeypatch):
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: None)
    d = fm.acilis_denetimi(firmware_surum="2.3", stm_bagli=True)
    assert d["eylem"] == su.BEKLE, d
    assert "okunamad" in d["gerekce"] and "kural" not in d["gerekce"].lower(), d["gerekce"]


def _yorumlar(yol: Path) -> str:
    kaynak = yol.read_text(encoding="utf-8")
    return "\n".join(
        t.string for t in tokenize.generate_tokens(io.StringIO(kaynak).readline) if t.type == tokenize.COMMENT
    )


def test_KRITIK_update_manager_yorumu_OLCULEN_gercegi_ve_OKUYANI_soyler():
    """Yorum (yalnız `#` satırları) bayat "404 döner" iddiasını taşımaz; 200/1.4.0 taslağını, dosyayı okuyan
    firmware zincirini, iki raporlama dalını ve Y17 kararını söyler."""
    y = _yorumlar(UPDATE_MANAGER)
    assert not re.search(r"404\s+d[öo]ner", y), (
        "update_manager yorumu hâlâ 'exe/latest.json 404 döner' diyor (ölçülen: 200)"
    )
    eksik = [p for p in ("200", "1.4.0", "firmware_manager", "kuralı YOK", "bekle", "Y17") if p not in y]
    assert not eksik, f"yorum ölçülen gerçeği/okuyanı/ayrımı söylemiyor — eksik: {eksik}"
