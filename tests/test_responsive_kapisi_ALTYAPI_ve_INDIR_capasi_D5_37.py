# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.37 (B-10.216 · B-10.217) — responsive kapısı: bozuk tarayıcı ALTYAPI hatası (çıkış 2); /download kritiği `data-kapi="indir"` çıpasına PİNLİ.

(216) ARIZA (ölçüldü): tarayıcı VAR ama CDP portunu açmıyorsa `tarayici_baslat` RuntimeError atıyor, `main` onu yakalamıyordu → Python iz
      dökümü + çıkış 1 ("YENİ bulgu" — sözleşme dışı); `--zorunlu` altında da "çıkış 3 ile atlanmalı" diyordu (orada 3 hiç dönmez).
      ÖLÇÜM (tarayıcısız kol): "tarayıcı" olarak bu Python yorumlayıcısı verilir — Chromium bayraklarını tanımaz, hemen ölür → CDP açılmaz.
      Gerçek Edge / Chrome BAŞLATILMAZ. `--hedef launcher` (HTTP sunucusu açılmaz); çıktı geçici dizinde.
(217) ARIZA: /download kritiği `main button[data-kapi='indir'], main button` — `main button` geri düşüşü yüzünden Windows indirme düğmesi
      gizlense de sayfadaki başka bir düğme kritiği karşılıyordu. Seçici artık YALNIZ çıpa; çıpa `Download.tsx`'te (vitest:
      `apps/web/src/__tests__/indir-capasi.D5_37.test.ts`). Gerçek tarayıcıda gizleme mutantı → 1: ORKESTRATÖR (gerçek tarayıcı).
MUTASYON: `tarayici_baslat`'ı try dışına geri almak ya da seçiciye `main button` geri düşüşünü eklemek → KIRMIZI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "responsive_kapisi.py"


def _modul():
    spec = importlib.util.spec_from_file_location("responsive_kapisi_d537", BETIK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("zorunlu", [True, False])
def test_KRITIK_CDP_acilmayan_tarayici_ALTYAPI_hatasi_cikis_2(tmp_path, capsys, zorunlu):
    m = _modul()
    arg = ["--hedef", "launcher", "--tarayici", sys.executable, "--cikti", str(tmp_path / "cikti"), "--png-yok"]
    try:
        kod = m.main(arg + (["--zorunlu"] if zorunlu else []))
    except RuntimeError as e:  # HEAD davranışı: istisna main'den sızar (iz dökümü + çıkış 1)
        pytest.fail(
            f"CDP açılmayan tarayıcıda istisna main'den SIZDI (çıkış 1 = 'YENİ bulgu' sayılır, D5.37): {str(e)[:200]}"
        )
    cikti = capsys.readouterr().out
    assert kod == 2, f"bozuk tarayıcı (CDP açılmadı) çıkış {kod} — sözleşme: altyapı hatası 2 (D5.37)"
    assert "ALTYAPI" in cikti and "CDP" in cikti, f"altyapı hatasının nedeni yazılmadı:\n{cikti[-600:]}"
    if zorunlu:
        assert "çıkış 3" not in cikti and "(3)" not in cikti, (
            f"--zorunlu altında GEÇERSİZ 'çıkış 3 ile atla' önerisi basıldı (orada 3 hiç dönmez):\n{cikti[-600:]}"
        )


def test_KRITIK_download_kritigi_YALNIZ_indir_capasina_pinli():
    m = _modul()
    kritik = m.HEDEFLER["site"]["download"]["kritik"]
    assert kritik, "/download kritiği tanımsız"
    for k in kritik:
        parcalar = [p.strip() for p in k["css"].split(",") if p.strip()]
        assert parcalar and all("[data-kapi='indir']" in p for p in parcalar), (
            f"/download kritiği {k['css']!r} — çıpasız geri düşüş (ör. `main button`) Windows indirme düğmesi gizlense de "
            "başka bir düğmeyle karşılanır (D5.37 / B-10.217)"
        )
