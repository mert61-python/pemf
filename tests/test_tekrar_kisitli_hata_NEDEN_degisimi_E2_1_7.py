# -*- coding: utf-8 -*-
"""E2-1.7 (2-E incelemesi, A1) — `secrets_manager.tekrar_kisitli_hata` (O-A2-1.b): NEDEN değişince (1) yeni neden HEMEN basılmalı —
D2.80 kapısı bunu ölçmüyor (A1 mutantı "neden karşılaştırması yok" YEŞİL kaldı: farklı arıza 60 sn gizlenir); (2) bastırılan sayı
ESKİ nedene aittir — HEAD onu YENİ nedenin satırına "[… ayni nedenle N kez daha]" diye ekliyor (ölçüldü: 'satir B [onceki 60 sn icinde
ayni nedenle 4 kez daha]' — 4'ün hepsi A idi). Günlük, bir arızanın kaç kez tekrarladığını YANLIŞ nedene yazar.
"""

from __future__ import annotations

import logging


def _topla():
    kayit = []

    class _H(logging.Handler):
        def emit(self, r):
            kayit.append(r.getMessage())

    lg = logging.getLogger("e2_1_7")
    lg.handlers[:] = [_H()]
    lg.propagate = False
    return lg, kayit


def test_KRITIK_neden_degisince_yeni_neden_HEMEN_basilir_E2_1_7(monkeypatch):
    from utils import secrets_manager as sm

    monkeypatch.setattr(sm, "_tekrar_gunluk", {})
    lg, kayit = _topla()
    assert sm.tekrar_kisitli_hata(lg, "k", "NEDEN-A", "ileti %s", "A") is True
    assert sm.tekrar_kisitli_hata(lg, "k", "NEDEN-A", "ileti %s", "A") is False  # aynı neden → bastırılır
    assert sm.tekrar_kisitli_hata(lg, "k", "NEDEN-B", "ileti %s", "B") is True, "FARKLI neden 60 sn içinde BASTIRILDI"
    assert any(m.startswith("ileti B") for m in kayit), kayit


def test_KRITIK_bastirilan_sayi_ESKI_nedene_yazilir_yeni_nedene_ayni_nedenle_DENMEZ_E2_1_7(monkeypatch):
    from utils import secrets_manager as sm

    monkeypatch.setattr(sm, "_tekrar_gunluk", {})
    lg, kayit = _topla()
    for _ in range(5):
        sm.tekrar_kisitli_hata(lg, "k", "NEDEN-A", "ileti %s", "A")
    sm.tekrar_kisitli_hata(lg, "k", "NEDEN-B", "ileti %s", "B")
    b = [m for m in kayit if m.startswith("ileti B")]
    assert b, kayit
    assert "ayni nedenle" not in b[0], (
        f"ESKİ nedenin (A) bastırılan 4 satırı YENİ nedene (B) 'aynı nedenle' diye yazıldı: {b[0]!r}"
    )
    assert any("4" in m and "NEDEN-A" in m for m in kayit), (
        f"A'nın bastırılan 4 tekrarı hiçbir satırda A'ya atfedilmedi: {kayit}"
    )


def test_KARSIT_ayni_neden_sure_dolunca_sayiyla_basilir_E2_1_7(monkeypatch):
    from utils import secrets_manager as sm

    monkeypatch.setattr(sm, "_tekrar_gunluk", {})
    lg, kayit = _topla()
    for _ in range(3):
        sm.tekrar_kisitli_hata(lg, "k", "NEDEN-A", "ileti %s", "A")
    sm._tekrar_gunluk["k"]["zaman"] -= sm._ERISIM_GUNLUK_ARALIK_SN + 1  # süre doldu
    sm.tekrar_kisitli_hata(lg, "k", "NEDEN-A", "ileti %s", "A")
    assert kayit[-1].endswith("2 kez daha]"), kayit
