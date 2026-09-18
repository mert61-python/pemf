# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Paketleme ve derleme araclari (paket).

⚠️ BU DOSYA BILEREK VAR (denetim 2026-09-17). Bu dizin derleme betiklerinden paket gibi import
ediliyordu ama `__init__.py`'si YOKTU — yani PEP 420 "ortam paketi" (namespace package)
olarak cozuluyordu. Ortam paketlerinde bir ad cakismasi ya da `sys.path` sirasi
degisikligi SESSIZCE baska bir dizini ayni ada baglayabilir; hata vermez, yanlis modulu
yukler. Acik `__init__.py` paketi TEK bir dizine sabitler.

⚠️ SILMEYIN. Kapi: tests/test_paket_sinirlari.py

Not: Bu paket FROZEN EXE'ye BUNDLE EDILMEZ (bu yuzden `apps/backend/utils/source_crypto` yeniden
disa aktarimi vardir). `__init__.py` yalnizca kaynak agacindaki import cozumunu
kesinlestirir; sevk edilen ikiliyi ETKILEMEZ.
"""
