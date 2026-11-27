# -*- coding: utf-8 -*-
"""CT2 g (istem 66 · Y320 / Y326 katman 11) — `launcher.yml` yalnız Windows paketler (macOS + Linux matrisi ve onlara özgü adımlar
— Apple imza / notarization / DMG, WebKitGTK — kaldırıldı; git geçmişinde). cargo audit Windows'ta koşar. Y327: yayın eserleri yine
yayın makinesinde (kod imzalama sertifikası alınmayacak)."""

from __future__ import annotations

from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
YOL = KOK / ".github" / "workflows" / "launcher.yml"


def test_KRITIK_launcher_matrisi_YALNIZ_windows():
    d = yaml.safe_load(YOL.read_text(encoding="utf-8"))
    dahil = d["jobs"]["build"]["strategy"]["matrix"]["include"]
    assert [m["os"] for m in dahil] == ["windows-latest"], dahil
    metin = YOL.read_text(encoding="utf-8")
    for yasak in ("macos-", "ubuntu-", "APPLE_", "notarytool", "build_dmg.sh", "webkit2gtk"):
        assert yasak not in metin, f"launcher.yml'de Windows dışı kalıntı: {yasak}"


def test_cargo_audit_KOSULSUZ_ve_tetik_ayni():
    d = yaml.safe_load(YOL.read_text(encoding="utf-8"))
    adim = [a for a in d["jobs"]["build"]["steps"] if "cargo audit --deny warnings" in str(a.get("run", ""))]
    assert len(adim) == 1 and "if" not in adim[0]
    tetik = d.get("on", d.get(True))
    assert tetik["push"]["tags"] == ["launcher-v*"] and d["permissions"] == {"contents": "read"}
