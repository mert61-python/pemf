# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.04 (B-3.63) KAPISI — yedek rotasyonu SİLİNEMEYEN eski yedeği günlükte DOSYA ADIYLA ve TAM ZİNCİRLE söyler.

ARIZA (DENETİM-03 B-3.63): `_cleanup_backups`taki iç `except: pass` eski yedeğin `unlink` hatasını (kilitli dosya / AV / izin)
YUTUYORDU; yedekler sessizce birikiyor, disk doluyordu. D2.63 (B-3.20) gövdeyi `logger.warning(..., exc_info=True)` yaptı ve
sessiz-yutma muafiyetini kaldırdı — ama davranışı ölçen bir kapı YOKTU: uyarı satırı silinip `pass`/`debug` yazılsa da
rotasyon kapıları yeşil kalırdı (yalnız AST tabanlı sessiz-yutma kapısı `pass`ı görür; `logger.debug(...)` onu da geçer).

KAPI (davranış): 16 günlük GERÇEK yedek (aile başına 14 tutulur → aile başına 2 silinmeli); `Path.unlink` EN ESKİ yedekte
`PermissionError` fırlatır → (1) rotasyon ÇÖKMEZ, öteki aileler ve öteki eski yedek yine silinir, (2) silinemeyen dosya
DİSKTE kalır, (3) WARNING kaydı dosya adını taşır ve `exc_info` doludur (kök neden: PermissionError).
MUTASYON: iç `except OSError` gövdesini `pass` ya da `logger.debug(...)` yapmak / `exc_info=True`yu silmek → KIRMIZI.
"""

from __future__ import annotations

import logging
from pathlib import Path

from test_yerel_yedek_penceresi_KORUNUR_D263 import _dbler, _gecerli_yedekler, _servis


def test_KRITIK_D504_SILINEMEYEN_eski_yedek_dosya_adiyla_ve_TAM_ZINCIRLE_uyarilir(temp_app_data, monkeypatch, caplog):
    tdb, hdb = _dbler(monkeypatch, temp_app_data, sifreli=False)
    bdir = temp_app_data / "backups"
    try:
        gecerli = _gecerli_yedekler(temp_app_data, tdb, hdb, list(range(17, 1, -1)))  # aile başına 16 → 2 fazla
        tedavi = sorted(p for p in gecerli if p.name.startswith("pemf_treatment_history_"))
        hasta = sorted(p for p in gecerli if p.name.startswith("pemf_patients_"))
        kilitli = tedavi[0]  # en eski tedavi yedeği: silinemez (AV / açık tanıtıcı benzetimi)
        orijinal_unlink = Path.unlink

        def _unlink(self, *a, **k):
            if self.name == kilitli.name:
                raise PermissionError(13, "D504 SIMULE KILIT (dosya baska surecte acik)", str(self))
            return orijinal_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", _unlink)
        w = _servis(temp_app_data, tdb, hdb)
        with caplog.at_level(logging.DEBUG):
            w._cleanup_backups(bdir)  # ÇÖKMEMELİ
        kalan = {p.name for p in bdir.iterdir()}
        assert kilitli.name in kalan, "aparat: kilitli yedek silinmiş görünüyor (unlink yaması tutmadı)"
        assert tedavi[1].name not in kalan, (
            "bir yedeğin silinememesi aynı ailedeki öteki eski yedeğin silinmesini DURDURDU"
        )
        assert hasta[0].name not in kalan and hasta[1].name not in kalan, (
            "silinemeyen yedek ÖTEKİ ailenin rotasyonunu durdurdu"
        )
        ilgili = [r for r in caplog.records if kilitli.name in r.getMessage()]
        assert ilgili, (
            "silinemeyen yedek günlükte DOSYA ADIYLA söylenmiyor → yedekler sessizce birikir (B-3.63). Görülen: "
            f"{[r.getMessage()[:80] for r in caplog.records]}"
        )
        kayit = ilgili[-1]
        assert kayit.levelno >= logging.WARNING, f"seviye {kayit.levelname}: normal günlükte görünmez (sessiz birikme)"
        assert kayit.exc_info and kayit.exc_info[0] is PermissionError, (
            "kayıtta kök neden (PermissionError zinciri) YOK"
        )
        assert "D504 SIMULE KILIT" in logging.Formatter().format(kayit), "biçimlenmiş kayıtta kök hata metni yok"
    finally:
        tdb.close()
        hdb._reset_thread_conn()
