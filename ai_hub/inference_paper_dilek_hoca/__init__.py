# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""paper_dilek_hoca — CPN hücre segmentasyonu + scratch/wound-healing analizi.

⚠️ `cell/` alt paketi (CpnInterface + multi_norm) teslim paketinde KIRIK POSIX
symlink'ti; gerçek paket sahibin eğitim deposundan gelene kadar model yolu açık
RuntimeError verir. Post-processing (closure/analysis) fonksiyonları cell'siz
çalışır ve CI'da test edilir. Plan: guii/scratch-entegrasyon-plani.md
"""
