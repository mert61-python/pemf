# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Gelistirici ve CI betikleri (paket).

⚠️ BU DOSYA BILEREK VAR (denetim 2026-09-17). Bu dizin hem dogrudan calistirilarak hem de paket gibi import
ediliyordu ama `__init__.py`'si YOKTU — yani PEP 420 "ortam paketi" (namespace package)
olarak cozuluyordu. Ortam paketlerinde bir ad cakismasi ya da `sys.path` sirasi
degisikligi SESSIZCE baska bir dizini ayni ada baglayabilir; hata vermez, yanlis modulu
yukler. Acik `__init__.py` paketi TEK bir dizine sabitler.

⚠️ SILMEYIN. Kapi: tests/test_paket_sinirlari.py

Not: Buradaki dosyalar hem `python scripts/x.py` seklinde DOGRUDAN calistirilir hem de
`from scripts.x import y` ile import edilir (or. `tests/test_notice_envanteri.py` ->
`scripts.lisans_envanteri_uret`). `__init__.py` ikinci kullanimi saglamlastirir, birincisini
DEGISTIRMEZ.
"""
