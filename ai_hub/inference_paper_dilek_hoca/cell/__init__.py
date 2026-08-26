# -*- coding: utf-8 -*-
"""cell — CPN sarmalayıcı paketi (İSKELET; dosyalar Çağlar Hoca'dan bekleniyor).

Sahip talimatı (2026-08-26 22:58): "cell diye bir klasör oluştursan yeter —
içine cpn, prep, util .py alacak". Üç dosya geldiğinde AYNEN bu klasöre konur:

    cell/cpn.py    → CpnInterface (model yükleme + tile'lı inference)
    cell/prep.py   → multi_norm(img, "cstm-mix") (eğitimdeki normalizasyon)
    cell/util.py   → yardımcılar (cpn/prep'in iç bağımlılığı)

Bu __init__ BİLEREK hiçbir şeyi import ETMEZ: dosyalar gelmeden import hatası
üretmemeli. Hazır-olma denetimi her yerde ALT-MODÜLE bakar
(`find_spec("...cell.cpn")` / `from ...cell.cpn import CpnInterface`) — iskelet
klasörün varlığı 'model hazır' sanılmaz. celldetection sürümü sahip onayıyla
0.4.9 pinli (dört yüzeyde).
"""
