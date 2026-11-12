# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODAK — AI Pro petri / fantom / kedi sürüşünün faz + duty'si (istem 45 · Y268–Y274 · Y280).

Amaç (sahip, Y273 / Y274): DOZ = hedefte toplam TEPE |B| (mT; MLX ve telemetriyle aynı). Kullanıcı dozu SEÇER (üst sınır o konumda duty ≤ %50 ile
verilebilen en büyük doz); "DOZ GARANTİ, KALAN GÜÇ ODAĞA". Faz = işaret + tepe hizalama gecikmesi (Y280). Bobin alanı CST birim alanı × 0. adımın
(12 Kasım 2026 tezgâh, MLX) kalibrasyonu. Model KNN k = 1 + yerel alan (A3 karşılaştırması, `DENETIM\\ODAK.md`); her tahmin FİZİKLE DENETLENİR
(karar vermez): |doz hatası| > %10, hedef cam içi kutunun dışında, kalibrasyon yok / eski / eşleme doğrulanmamış → SÜRME (fail-closed).

Modüller: `alan` (tek dönüşüm yeri + alan + duty + zaman domeni) · `model` (ONNX KNN) · `oneri` (plan + fizik denetimi + kuyu haritası).
"""
