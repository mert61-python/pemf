# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.35 (B-10.59) — `PEMF_Backend.exe --kurtarma` donmuş EXE'de, depo DIŞINDA içe aktarmada ÖLMEZ.

Kusur: `tools/kurtarma.py` modül düzeyinde depo kökünü İŞARET dosyasıyla (`pyproject.toml` + `apps/backend`) arıyor, bulamazsa
`RuntimeError` atıyordu. Donmuş EXE'de işaret dosyası pakete girmez → yeni makinede (depo yok — tam da kurtarma anı) `--kurtarma`
içe aktarma anında ölüyordu: anakartı ölen klinik zarfı AÇAMAZDI. (1.9.50'de bu kök araması yoktu — 218f48f ile geldi; sahada YOK,
ilk yeni derlemeyle sevk edilirdi.)

Kapı: `tests/donmus_kurtarma_aparati.py` (depo dışı paket dizini + `sys.frozen` / `_MEIPASS` benzetimi, alt süreç, derleme YOK).
"""

from __future__ import annotations

from betik_alt_sureci import kostur, yalitik_ortam
from donmus_kurtarma_aparati import DEPO, donmus_kurtarma_kos


def test_KRITIK_donmus_EXEde_depo_DISINDA_kurtarma_ICE_AKTARILIR_ve_CALISIR_D235(tmp_path):
    sonuc, cikti = donmus_kurtarma_kos(
        tmp_path, ["--zarf", str(tmp_path / "yok" / "kurtarma-zarfi.enc"), "--kod", "AAAAA"]
    )
    assert "kacan" not in sonuc, f"`PEMF_Backend.exe --kurtarma` İÇE AKTARMADA öldü: {sonuc.get('kacan')}"
    assert sonuc.get("open_envelope") is True, f"utils.backup_recovery çözülmedi: {sonuc}"
    assert sonuc.get("depo_koku_yolda") is False, "donmuş EXE depo kökünü sys.path'e ekledi (paket gölgelenebilir)"
    assert sonuc.get("rc") == 2 and "zarf bulunamadi" in cikti, (
        f"araç tanımlı davranışa ulaşmadı: {sonuc}\n{cikti[-600:]}"
    )


def test_KARSIT_kaynak_agacinda_python_ile_CALISIR_D235(tmp_path):
    """Karşıt: geliştirme yolu (kaynak ağacı, donmuş DEĞİL) bozulmadı — kök bulunur, araç çalışır."""
    p = kostur(
        [str(DEPO / "tools" / "kurtarma.py"), "--zarf", str(tmp_path / "yok.enc"), "--kod", "AAAAA"],
        cwd=DEPO,
        env=yalitik_ortam(tmp_path / "ev"),
        sure=120,
    )
    assert "Traceback" not in p.stdout + p.stderr, (p.stdout + p.stderr)[-1200:]
    assert p.returncode == 2 and "zarf bulunamadi" in p.stdout, (p.returncode, p.stdout[-600:])
