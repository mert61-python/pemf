# -*- coding: utf-8 -*-
"""CT3 (istem 66 · Y326 katman 7) — başlatıcı + istemci KAPSAM RAPORU kırmızıda da GÖRÜNÜR.

Ölçüldü (28-11, ilk GitHub koşusu @ 6d1ebb75): `launcher (cargo)` `--fail-under-lines` eşiğinde düştü ama `--lcov` kipinde ölçülen değer
HİÇ basılmıyordu ve `lcov.info` eser olarak yüklenmiyordu → eşik altı kalan dosya / satır GitHub'dan görülemiyordu. `frontend` işi
de global dal eşiğinde düştü (%94,39 < taban %94,4); dosya bazında rapor eser değildi → yerel ölçümle karşılaştırılamadı. CT2 d
yalnız backend `coverage.json`'unu eser yapmıştı. Bu kapı: başlatıcı işi kırmızıda da `cargo llvm-cov report --summary-only`
(eşik adımıyla AYNI dışlama deseni) iş sayfasına basar + `lcov.info`'yu eser yükler; istemci işi `coverage/` raporunu (lcov +
coverage-final.json) eser yükler.
"""

from __future__ import annotations

from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
AKIS = KOK / ".github" / "workflows"


def _adimlar(dosya: str, is_: str) -> list[dict]:
    return yaml.safe_load((AKIS / dosya).read_text(encoding="utf-8"))["jobs"][is_]["steps"]


def _kirmizida_da(adim: dict) -> bool:
    kosul = str(adim.get("if", ""))
    return "always()" in kosul or "failure()" in kosul


def test_KRITIK_baslatici_lcov_ESER_olarak_kirmizida_da_yuklenir_ESIK_adiminin_kendi_ciktisi():
    adimlar = _adimlar("tests.yml", "launcher")
    esik = [a for a in adimlar if "--fail-under-lines" in str(a.get("run", ""))]
    assert (
        len(esik) == 1
        and "--lcov --output-path lcov.info" in esik[0]["run"]
        and esik[0]["working-directory"] == "launcher"
    )
    eser = [
        a
        for a in adimlar
        if "upload-artifact" in str(a.get("uses", ""))
        and "launcher/lcov.info" in str((a.get("with") or {}).get("path", ""))
    ]
    assert eser, "başlatıcı lcov.info eser olarak yüklenmiyor"
    assert _kirmizida_da(eser[0]) and "CI_ALAN" in str(eser[0]["if"]), (
        "eser yalnız yeşilde yükleniyor (eşik kırmızısında görünmez)"
    )
    assert adimlar.index(eser[0]) > adimlar.index(esik[0]), "eser adımı eşik adımından ÖNCE (lcov henüz yok)"
    # Dışlama deseni TEK yerde (ikinci bir `cargo llvm-cov … --ignore-filename-regex` adımı deseni çatallardı — KP3 kapısı).
    assert sum("--ignore-filename-regex" in str(a.get("run", "")) for a in adimlar) == 1


def test_KRITIK_istemci_kapsam_raporu_ESER_olarak_kirmizida_da_yuklenir():
    adimlar = _adimlar("frontend.yml", "test")
    eser = [a for a in adimlar if "upload-artifact" in str(a.get("uses", ""))]
    assert eser, "istemci (jest) kapsam raporu eser olarak yüklenmiyor"
    yol = str((eser[0].get("with") or {}).get("path", ""))
    assert "apps/ui/coverage/lcov.info" in yol and "apps/ui/coverage/coverage-final.json" in yol
    assert _kirmizida_da(eser[0]), "eser yalnız yeşilde yükleniyor (eşik kırmızısında görünmez)"
