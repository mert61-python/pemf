# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-G inceleme G-14.2 — bobin koşu kaydı haritası testler arası SIZMAZ (conftest `_kosu_kaydi_sizmaz`).

ÖLÇÜLEN KUSUR (inceleme, `a5801c0`; 1G-YB3'ün sınıfı): `coil_run_tracker._active_coil_runs` / `_coil_run_stats`
modül-geneldir ve Y63'ten beri "Seansı Durdur" açık koşu kaydı olan bobini de durdurur. Salt-okur gözcü (159 dosya) 15
testin / 9 dosyanın kayıt bıraktığını, 4 dosyanın (A47, D168, Y5_D170, treatment_persistence) DOSYA SONUNDA bile
bıraktığını ölçtü; tam süitte araya giren bir seans başlatması maskeliyor, alt küme koşuları kırmızı: A47'den sonra koşan
`test_p2p3_regression_gaps.py::test_devralma_YOKSA_bobinler_normal_durdurulur` → [1, 2, 6, 7] != [1, 2].

SÖZLEŞME: bir test kayıt açıp KAPATMADAN bitse de sonraki test haritaları kendinden önceki hâliyle görür. İki kol SIRALI
(pytest dosya içi tanım sırası; süitte rastgele sıra eklentisi YOK): 1. kol kaydı açık bırakır, 2. kol temiz görmeli.
Gerçek ürün yolu: 1. kol kaydı `coil_run_tracker._begin_coil_run` ile açar (DB yazımı bu dosyanın sahte DB'sine).
"""

from __future__ import annotations

_BOBIN = 8


def _crt(monkeypatch):
    from servers import coil_run_tracker as crt

    class _SahteDB:
        def start_coil_run(self, *a, **k):
            return 987654

        def __getattr__(self, ad):
            return lambda *a, **k: None

    monkeypatch.setattr(crt, "_treatment_db_getter", lambda: _SahteDB())
    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: 4242)  # `_begin_coil_run` yalnız etkin seansta açar
    return crt


def test_G142_1_kol_kosu_kaydini_ACIK_birakir(monkeypatch):
    crt = _crt(monkeypatch)
    crt._begin_coil_run(_BOBIN, 100.0, 40.0, 0.0, None, "esp")
    with crt._active_coil_runs_lock:
        assert crt._active_coil_runs.get(_BOBIN) == 987654, f"aparat: kayıt açılmadı: {crt._active_coil_runs}"
    # sızıntı deseni (1G-YB3 / A47): kayıt KAPATILMADAN test biter


def test_KRITIK_G142_2_kol_sonraki_test_TEMIZ_baslar(monkeypatch):
    crt = _crt(monkeypatch)
    with crt._active_coil_runs_lock:
        sizan = crt._active_coil_runs.get(_BOBIN)
    with crt._coil_run_stats_lock:
        istatistik = 987654 in crt._coil_run_stats
    assert sizan != 987654 and not istatistik, (
        f"önceki testin AÇIK bıraktığı koşu kaydı sonraki teste SIZDI (bobin {_BOBIN} → {sizan}, istatistik {istatistik}) — "
        "'Seansı Durdur' bu bobini de durdurur, ilgisiz testler sıraya bağlı kırmızı/maskeli olur"
    )
