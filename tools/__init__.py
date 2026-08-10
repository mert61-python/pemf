# Author: mertaygn, cglrgrkn
"""Yardımcı araçlar paketi.

⚠️ 2026-08-09'da EKLENDİ (denetim, ENGEL): `tools/` bir namespace-dizindi ve frozen EXE'ye
girmiyordu. `tools/kurtarma.py` (felaket kurtarma) sahada ÇALIŞTIRILAMIYORDU — makinesi ölen
veterinerde Python yok. Artık `backend_service.py --kurtarma` ile çağrılıyor ve PyInstaller'ın
modülü paketleyebilmesi için bu dosya gerekli (bkz. build_tools/PEMF_Backend_onedir.spec).

Buradaki diğer araçlar (simülatör, e2e, sniffer) geliştirme içindir ve pakete GİRMEZ:
spec yalnız `tools.kurtarma`yı açıkça bundle eder.
"""
