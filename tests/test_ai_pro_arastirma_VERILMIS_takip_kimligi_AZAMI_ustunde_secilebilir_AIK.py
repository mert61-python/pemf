# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AIK (Y143 eki, S-AIK) — araştırma AI Pro'da VERİLMİŞ takip kimliği `azami_hedef`i aşsa da GEÇERLİ hedeftir.

ÖLÇÜLEN KUSUR (AIK, taban `ac1c3405`; `kayit/K2_kimlik_tasma.txt`): AII-2.1'den beri takip kimliği BAŞKA hedefe yeniden verilmez
(doğru) ama sayaç da geri dönmez. Fantom ~35 px kaydırılınca (hedef yarıçapı 10 px) 5 tümör YENİ kimlik alır: 1–5 → 6–10. Fantom
`hedef_idleri` 0–8 (`azami_hedef` 8) olduğundan kimliği 9 / 10 olan tümör SEÇİLEMİYORDU: `/propose` ve `/organ` 422 "Hedef 10 …
desteklenmiyor". Y143 otomatik öneriyi seçili KİMLİKLE mühürlediği için aynı duvar otomatik akışı da `/start`ta 422'ye düşürürdü.

SÖZLEŞME: sağlayıcının o ana dek VERDİĞİ her kimlik geçerli hedeftir (dört doğrulama noktası — öneri, başlatma, hedef değişimi,
hazırlık — `hedef_idleri` tek kaynağını kullanır); VERİLMEMİŞ kimlik (ör. 999) yine 422. `azami_hedef` (ilk tavan) değişmez.
"""

from __future__ import annotations

from test_ai_pro_arastirma_OTOMATIK_hedef_SECILI_KIMLIGI_muhurler_Y143 import (  # noqa: F401 — aparat
    _hazirlik_karesi,
    _onayla_baslat,
    _oner,
    _urun_sakla,
    o,
)

T5 = [((100.0 + 40 * i, 100.0), (-40.0, -80.0 + 40 * i, 0.0), 100 + 10 * i) for i in range(5)]
KAYIK = [((px[0] + 25.0, px[1] + 25.0), mm, a) for px, mm, a in T5]  # fantom ~35 px kaydırıldı (yarıçap 10 px)


def _kaydir(o):
    _hazirlik_karesi(o, T5)
    _hazirlik_karesi(o, KAYIK)
    kimlikler = sorted(t["id"] for t in o.air._ai_organ_cache.get("targets") or [])
    assert kimlikler == [6, 7, 8, 9, 10], f"aparat: kaydırma sonrası kimlikler {kimlikler}"
    return kimlikler


def test_KRITIK_AIK_azami_ustu_VERILMIS_kimlik_ELLE_secilir_onerilir_ve_baslatilir(o):
    _kaydir(o)
    r_org = o.c.post("/api/ai/pro/organ", json={"organ_id": 10, "model": "fantom"})
    assert r_org.status_code == 200, f"verilmiş kimlik 10 seçilemedi: {r_org.status_code} {r_org.text[:160]}"
    _hazirlik_karesi(o, KAYIK)
    r = _oner(o, 10)
    assert r.status_code == 200 and r.json()["specs"]["organ_id"] == 10, (
        f"verilmiş kimlik 10 önerilemedi: {r.text[:200]}"
    )
    assert _onayla_baslat(o, r.json()["proposalId"]).status_code == 200


def test_KRITIK_AIK_otomatik_secim_azami_ustu_kimligi_MUHURLER_ve_BASLATIR(o):
    _kaydir(o)  # otomatik seçim: EN BÜYÜK odak = son T5 (alan 140) → kimlik 10
    r = _oner(o, 0)
    assert r.status_code == 200 and r.json()["specs"]["organ_id"] == 10, r.text[:200]
    s = _onayla_baslat(o, r.json()["proposalId"])
    assert s.status_code == 200, f"otomatik mühürlü kimlik 10 başlatılamadı: {s.status_code} {s.text[:200]}"


def test_KARSIT_AIK_VERILMEMIS_kimlik_YINE_reddedilir_tavan_DEGISMEZ(o):
    _kaydir(o)
    assert o.c.post("/api/ai/pro/organ", json={"organ_id": 999, "model": "fantom"}).status_code == 422
    assert _oner(o, 11).status_code == 422, "henüz VERİLMEMİŞ kimlik 11 kabul edildi"
    from servers import ai_pro_hedef

    assert ai_pro_hedef.FantomSaglayici.azami_hedef == 8 and ai_pro_hedef.PetriSaglayici.azami_hedef == 96
