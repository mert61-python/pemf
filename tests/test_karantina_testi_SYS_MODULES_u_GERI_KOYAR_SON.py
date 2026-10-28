# -*- coding: utf-8 -*-
"""SON-A1.4 (22-SON A1a §6a · D5 §5 AÇIK aparat sızıntısı) — `test_anahtar_uyusmazligi_karantina.py` sys.modules'u GERİ KOYAR.

ÖLÇÜLEN SIZINTI (uç 8b002fc0): karantina testi `:96 / :134 / :161`'de `database.patient_database` ve `database.treatment_history_db`
modüllerini `del sys.modules[...]` ile silip yeniden içe aktarıyor, GERİ KOYMUYOR. İçe aktarma anında işlev bağlayan ürün modülleri
(`servers.patient_router.get_patient_database`, `servers.history_router.get_treatment_db`, `servers.sync_worker`, `servers.api_server`)
ESKİ modülü görmeye devam eder; sonraki dosyaların `database.*` üzerindeki yamaları (monkeypatch / tekil örnek) uca ULAŞMAZ. D5
kapanış süitinde bu yüzden 503 kapısı 200 verdi (C136 yalnız o kapının fikstürünü bağımsız kıldı).

Kapı ALT SÜREÇTE (sıra bağımsız): GERÇEK karantina dosyası + ondan SONRA koşan sentetik dosya (ürün modüllerini toplama anında —
karantinadan ÖNCE — içe aktarır, gerçek süitteki gibi) aynı pytest sürecinde koşar; sentetik dosya ürün bağlamalarının hâlâ
`sys.modules`taki modülün işlevi olduğunu ölçer. Köprü conftest `test_PEMF_ortami_dosyadan_SIZMAZ_gozcusu_D5._KOPRU` (gerçek conftest).
"""

from __future__ import annotations

from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam
from test_PEMF_ortami_dosyadan_SIZMAZ_gozcusu_D5 import _KOPRU

_TESTLER = Path(__file__).resolve().parent

_SONRAKI = '''
import sys

import servers.history_router as _hr  # toplama anında (karantinadan ÖNCE) bağlanır — gerçek süitteki gibi
import servers.patient_router as _pr


def test_z_sonraki_dosyanin_urun_baglamalari_SYS_MODULES_ile_AYNI():
    sapma = [
        f"{urun.__name__}.{ad} ESKİ {db} modülüne bağlı (sys.modules'taki yeni modülün işlevi değil)"
        for urun, ad, db in (
            (_pr, "get_patient_database", "database.patient_database"),
            (_hr, "get_treatment_db", "database.treatment_history_db"),
        )
        if getattr(urun, ad) is not getattr(sys.modules[db], ad)
    ]
    assert not sapma, sapma


def test_z_paket_ozniteligi_SYS_MODULES_ile_AYNI_nesne():
    # 22-SON kapanış: girdi geri konup paket özniteliği YENİ modülde kalırsa `from database import patient_database` ile
    # `from database.patient_database import …` FARKLI modülleri görür — sonraki dosyaların yamaları ürüne ulaşmaz.
    import database

    sapma = [
        f"database.{ad} paket özniteliği sys.modules['database.{ad}'] ile AYNI nesne değil"
        for ad in ("patient_database", "treatment_history_db")
        if getattr(database, ad, None) is not sys.modules.get(f"database.{ad}")
    ]
    assert not sapma, sapma
'''


def test_KRITIK_karantina_testi_SONRAKI_dosyaya_ESKI_modul_birakmaz(tmp_path):
    d = tmp_path / "sentetik"
    d.mkdir()
    (d / "test_a_karantina.py").write_text(
        (_TESTLER / "test_anahtar_uyusmazligi_karantina.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (d / "test_z_sonraki.py").write_text(_SONRAKI, encoding="utf-8")
    (d / "conftest.py").write_text(
        _KOPRU.format(dizin=str(_TESTLER), yol=str(_TESTLER / "conftest.py")), encoding="utf-8"
    )
    p = kostur(
        ["-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", "-p", "no:randomly", "--rootdir", str(d), str(d)],
        cwd=d,
        env=yalitik_ortam(tmp_path / "ev"),
    )
    cikti = p.stdout + p.stderr
    assert "test_z_sonraki_dosyanin_urun_baglamalari_SYS_MODULES_ile_AYNI" in cikti or "passed" in cikti, (
        f"aparat: alt süreç pytest koşmadı:\n{cikti[-2000:]}"
    )
    assert "FAILED test_a_karantina" not in cikti and "ERROR test_a_karantina" not in cikti, (
        f"aparat: karantina testleri alt süreçte kırmızı (sonda ölçemez):\n{cikti[-2000:]}"
    )
    assert "FAILED test_z_sonraki" not in cikti, (
        "karantina testi database.* modülünü sys.modules'tan silip GERİ KOYMADI — sonraki dosyaların ürün bağlamaları ESKİ "
        f"modülde ya da paket özniteliği YENİ modülde kaldı (girdiyi VE üst paketin özniteliğini geri koyun):\n{cikti[-2000:]}"
    )
    assert p.returncode == 0, cikti[-2000:]
