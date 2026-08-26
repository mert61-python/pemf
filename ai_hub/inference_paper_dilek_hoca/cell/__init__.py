# -*- coding: utf-8 -*-
"""cell — CPN sarmalayıcı paketi (✅ TESLİM ALINDI, 2026-08-26 23:12).

Sahibin eğitim deposundan gelen üç dosya (cell.zip): `cpn.py` (CpnInterface —
model yükleme + tile'lı inference, init'te requires_grad_(False), çağrıda
torch.no_grad), `prep.py` (multi_norm "cstm-mix" — eğitimdeki normalizasyon),
`util.py` (tif/imageio yardımcıları; inference yolu import etmez).

Bu __init__ BİLEREK hiçbir şeyi import ETMEZ (sahibin orijinali de boştu):
ağır importlar (celldetection/torch) çağrı anına kalır; hazır-olma denetimleri
alt-modüle bakar (`find_spec(".cell.cpn")`). celldetection==0.4.9 pinli
(sahip onayı). Vendor incelemesi: doğrudan torch.load YOK, sys.path/ağ/subprocess
YOK; ckpt çözümü cd.resolve_model üzerinden — üst modüldeki
`_cpn_yukleme_kapsami()` kapsamlı weights_only yönetimini üstlenir.
"""
