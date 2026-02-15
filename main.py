#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEMF Medical System - Ana Başlatıcı
Bu dosya reorganize edilmiş proje yapısı için ana başlatıcıdır.
"""

import sys
import os
import multiprocessing
from pathlib import Path


class NullWriter:
    def write(self, data):
        pass
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = NullWriter()

if sys.stderr is None:
    sys.stderr = NullWriter()
# Windows'ta yönetici hakları kontrolü (opsiyonel - bilgilendirme amaçlı)
if sys.platform == 'win32':
    import ctypes
    
    def is_admin():
        """Yönetici haklarına sahip olup olmadığını kontrol et"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

# Proje kök dizinini Python path'ine ekle
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Ana GUI uygulamasını başlat
if __name__ == "__main__":
    # Windows'ta sonsuz döngü (spawn bomb) sorununu engeller
    multiprocessing.freeze_support()
    
    from windows.gui_pyqt_v11 import main
    main()