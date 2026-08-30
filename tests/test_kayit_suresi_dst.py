# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SEANS KAYIT SÜRESİ — DST/saat-değişimi güvenli (zaman denetimi 2026-08-30).

⚠️ Kayıt süresi (`duration_minutes`) `time.time()` FARKINDAN hesaplanıyordu. Duvar saati ileri/geri
giderse (NTP düzeltmesi, DST, elle) RAPORLANAN süre gerçekten sapıyordu — `max(0,…)` negatifi
engelliyordu ama değeri yanlış. Gerçek tedavi zaten monotonic watchdog'la güvencede (hasta güvenli);
bu yalnız KAYDI etkiliyordu.

DÜZELTME: `_kayit_suresi_dk(start_mono, started_epoch)` — MONOTONIC öncelikli (saat-değişiminden
bağımsız), `start_mono` yoksa wall-clock geri-çekilme (recovery gibi yollar için geriye uyumlu).
Seans başlarken zaten `start_mono = time.monotonic()` snapshot'ı vardı (watchdog için); artık kayıt
da onu kullanıyor.
"""

from __future__ import annotations

import time

from servers.api_server import _kayit_suresi_dk


def test_KRITIK_monotonic_saat_degisiminden_ETKILENMEZ():
    """⚠️ Bug'ın kalbi: duvar-saati started_epoch YANLIŞ (90 dk) görünse bile, monotonic 30 dk
    ise kayıt 30 dk olmalı (DST +1 saat senaryosu)."""
    now_mono = time.monotonic()
    start_mono = now_mono - 30 * 60  # gerçek: 30 dk
    yanlis_wall = time.time() - 90 * 60  # DST: duvar saati 90 dk önce görünüyor
    assert _kayit_suresi_dk(start_mono, yanlis_wall) == 30, (
        "kayıt süresi duvar-saatine kapıldı → DST/saat-değişiminde yanlış süre"
    )


def test_start_mono_YOKSA_wall_clock_fallback():
    """Geriye uyumluluk: monotonic snapshot'ı olmayan yol (recovery) wall-clock kullanır."""
    start_epoch = time.time() - 20 * 60
    assert _kayit_suresi_dk(None, start_epoch) == 20


def test_KARSIT_negatif_clamp():
    """Saat büyük geri sıçrarsa (monotonic yok, wall-clock geri) negatif → 0, çökme yok."""
    gelecek_epoch = time.time() + 3600  # başlangıç 'gelecekte' (saat geri gitti)
    assert _kayit_suresi_dk(None, gelecek_epoch) == 0


def test_gecersiz_girdi_None():
    assert _kayit_suresi_dk(None, None) is None
    assert _kayit_suresi_dk(None, "abc") is None


def test_monotonic_gecersizse_wall_clock_a_duser():
    """start_mono bozuksa (tip) sessizce wall-clock'a düşer, çökmez."""
    start_epoch = time.time() - 10 * 60
    assert _kayit_suresi_dk("bozuk", start_epoch) == 10


def test_KRITIK_finalize_ve_stop_MONOTONIC_kullaniyor():
    """⚠️ ZAYIF-ÇIPA: helper doğru olsa da çağıranlar start_mono GEÇMİYORSA kayıt yine wall-clock.

    Kaynakta ham `int((_now - float(started_epoch))...)` doz-süresi hesabı KALMAMALI; hepsi
    `_kayit_suresi_dk` üzerinden gitmeli."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "int((_now - float(started_epoch))" not in src, "ham wall-clock süre hesabı hâlâ var → DST bug'ı geri gelir"
    # Her iki bitiş yolu da start_mono geçirmeli (finalize parametresi + stop yerel değişkeni)
    assert src.count("_kayit_suresi_dk(") >= 2, "iki bitiş yolu da helper'ı kullanmıyor"
    assert "start_mono=prev.get(\"start_mono\")" in src or "start_mono=sess.get(\"start_mono\")" in src, (
        "finalize çağrıları start_mono geçirmiyor → helper wall-clock'a düşer"
    )
