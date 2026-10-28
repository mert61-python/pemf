# Author: mertaygn, cglrgrkn
"""Yardımcı araçlar paketi.

⚠️ 2026-08-09'da EKLENDİ (denetim, ENGEL): `tools/` bir namespace-dizindi ve frozen EXE'ye
girmiyordu. `tools/kurtarma.py` (felaket kurtarma) sahada ÇALIŞTIRILAMIYORDU — makinesi ölen
veterinerde Python yok. Artık `apps/backend/backend_service.py --kurtarma` ile çağrılıyor ve PyInstaller'ın
modülü paketleyebilmesi için bu dosya gerekli (bkz. build_tools/PEMF_Backend_onedir.spec).

D6.47 (Y32): `tools/destek_paketi.py` da aynı yolla sahaya gider (`backend_service.py --destek-paketi`).

Buradaki diğer araçlar (simülatör, e2e, sniffer) geliştirme içindir ve pakete GİRMEZ:
spec yalnız `tools.kurtarma` ve `tools.destek_paketi`yi açıkça bundle eder.
"""
