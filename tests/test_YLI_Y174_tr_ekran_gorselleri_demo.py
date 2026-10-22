# -*- coding: utf-8 -*-
"""Y174 (S-YH.4) — sitenin 8 Türkçe telefon ekran görüntüsü kum havuzunda DEMO veriyle yeniden çekildi (YLI, 2026-10-22).

ÖLÇÜLEN DURUM (YH): `apps/web/public/screenshots/*.jpg` sahibin GERÇEK e-postasını ve 08-08 öncesi "Tedavi Kontrol" terimini gösteriyordu.
YLI: aynı 8 çerçeve (YH B7 İngilizce setiyle aynı akış) yalıtılmış kum havuzunda (SIM, kafes, rastgele 127.0.0.1, başsız Edge geçici profil)
Türkçe DEMO veriyle (dr.demo@klinik-demo.com · Pamuk / Karabaş / Minnoş / Tarçın) çekildi; 560 × 1116 JPEG, aynı sıkıştırma (q 82, 4:2:0).

KAPI: eski 8 görselin SHA-256'sı bir daha GELMEZ (gerçek e-posta / eski terim taşıyan dosyalar geri yüklenmesin — ör. eski bir daldan
birleştirme ya da toplu geri alma). Biçim denetimi `test_YH_B7_site_ekran_gorselleri.py`'de.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
TR = KOK / "apps" / "web" / "public" / "screenshots"

#: Y174 öncesi (YH B7'den önceki) Türkçe set — gerçek e-posta + "Tedavi Kontrol". Değerler `957ba225` git nesnelerinden ölçüldü.
YASAK = {
    "ffdbce1de85fdc03e45412b0ad4fb3517554efb1776a1864e5ad0594e6365942": "01-profil.jpg",
    "6f34241955c22e04857907cdaa02537be67ef76614079e00589940f85a6bd1e7": "02-teshis.jpg",
    "e4af2b65cd31e2442daf0834b3ed3c133f74e4f3e883243158de9bed5f1fa863": "03-modeller.jpg",
    "6ce349d184b1fcc0b71f0761f5a643bc849f0fb0592a178d5c086a979a30a1e3": "04-aipro.jpg",
    "64dfa9af525d87f36328be288bc3411d134b8a113530f6b966776f4fbce38a20": "05-kontrol.jpg",
    "a47a1c3151598a33e577523668f4a4f1a90578d84a7276935561fad19991cc1a": "06-dashboard.jpg",
    "25eddb79f1c797982ff9491a1c103be1d73b3bd5d2585d3e7a45da70cc486cce": "07-hastalar.jpg",
    "9b205a48b395c89da426798ee172b6d113808307512f8bd32d49c5b528dd6165": "08-gecmis.jpg",
}


def test_KRITIK_Y174_eski_gercek_veri_gorselleri_GERI_GELMEZ():
    dosyalar = sorted(TR.rglob("*.jpg"))
    assert len(dosyalar) >= 16, f"ekran görseli sayısı beklenmedik: {len(dosyalar)}"  # 8 TR + 8 EN
    geri = [
        f"{p.relative_to(KOK).as_posix()} (= eski {YASAK[h]})"
        for p in dosyalar
        if (h := hashlib.sha256(p.read_bytes()).hexdigest()) in YASAK
    ]
    assert not geri, "Y174 öncesi gerçek e-posta / 'Tedavi' terimli ekran görüntüsü geri geldi:\n" + "\n".join(geri)


def test_KARSIT_Y174_yasak_liste_8_ayri_dosya():
    assert len(YASAK) == 8 and len(set(YASAK.values())) == 8
