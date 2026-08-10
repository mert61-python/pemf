# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KAYNAK ŞİFRELEME PAROLASI — ŞABLON.

KULLANIM: bu dosyayı `_static_password.py` olarak kopyalayın ve parolayı yazın.
    copy build_tools\_static_password.example.py build_tools\_static_password.py

⚠️ `_static_password.py` .gitignore'ludur — ASLA depoya girmemeli.
⚠️ Bu parola frozen EXE'ye GÖMÜLÜR. Yani üründe gider: kopyalamayı zorlaştırır,
   tersine mühendisliği ENGELLEMEZ. Asıl koruma `.py → .pyd` derlemedir.
⚠️ PAROLAYI KAYBEDERSENİZ şifrelenmiş build'ler açılamaz. Yedekleyin (keys/ ile aynı yere).
"""

SOURCE_PASSWORD = "BURAYA-GUCLU-BIR-PAROLA-YAZIN"
