# -*- coding: utf-8 -*-
# Author: mertaygn
""" "⚡ Cihaz otonom olarak sürülüyor" / "⚠️ Cihaz SÜRÜLMEDİ" — AI Hub DONANIM SONUCU bloğu ÖLÜYDÜ ve KALDIRILDI.

===============================================================================
TARİHÇE
===============================================================================
2026-09-13 (sahip: *"cihaz sürülemedi kısmını kaldır burası ai modu."*): blok `hw_status === "idle"`da gizlendi; `skipped_*`
durumları "kullanıcı otonom sürüşü İSTEDİ" gerekçesiyle görünür tutuldu (bu dosyanın eski karşıt kapısı "blok tümden silinmemeli").

2026-10-02 D1.88 (B-6.30 · A-19, `81312475`): FGS "Otonom Biofeedback" AI Pro MÜHRÜNE bağlandı — `analyze_landmark` sürüş yolu
kaldırıldı (`auto_adjust=true` → 428), ekranın İKİ analiz yolu `auto_adjust`ı SABİT "false" gönderir. O andan beri hiçbir backend
sürümü bu ekrana `idle` dışı `hw_status` döndüremez (eski backend de `updated` / `skipped_*`ı YALNIZ `auto_adjust=true`da üretirdi)
→ blok ÖLÜ: "kullanıcı sürüş istedi" öncülü artık hiç doğru olamaz. L1-7.3 · L1-7.16 · i3-F-9 (D67): blok + 7 katalog anahtarı kaldırıldı.

===============================================================================
BU KAPI NEYİ TUTAR (eski iki arayüz kapısının yerine — daha güçlü: ölülüğün ÖNCÜLÜNÜ pinler)
===============================================================================
1. Ekran sürüş İSTEMEZ: her `append("auto_adjust", …)` değeri SABİT "false" (≥ 2 çağrı yeri: canlı + elle analiz). Biri `true`ya
   dönerse sürüş yolu geri gelmiş olur ve sürüş geri bildirimi (eski blok) de birlikte geri gelmek ZORUNDADIR — bu kapı KIRMIZI olur.
2. Yasak iddia YOK: ekran kaynağında `hw_status` okunmaz; "sürülüyor / SÜRÜLMEDİ" anahtarları ne kaynakta ne katalogda (TR + EN).
   Doğru iddia VAR: anahtarın ipucu "bu ekran cihazı sürmez" der (TR birebir + EN dolu).
3. Backend öncülü: `ai_router` `hw_status`u tek yerde ve yalnız "idle" olarak atar (AST).

⚠️ ÇIPA (TSX) `c_soy` İLE SOYULUR — kaldırma notu yorumda "sürülüyor" / `hw_status` kelimelerini içerir; ham metinde arayan kapı yorum
yüzünden kırmızı / yeşil yanılırdı ("yorum kapıyı kandırdı"). Python kaynağı (`ai_router.py`) AST ile okunur (O-B.1).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
for _p in (str(KOK), str(KOK / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_EKRAN = KOK / "apps" / "ui" / "src" / "screens" / "AiHubScreen.tsx"
_ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"
_DOSYA = "apps/ui/src/screens/AiHubScreen.tsx"

#: Kaldırılan ölü bloğun anahtarları — geri gelirse "cihaz sürülüyor" iddiası da geri gelir.
_OLU_ANAHTARLAR = (
    "ai.otonom.suruluyor",
    "ai.otonom.frekansSiddet",
    "ai.otonom.durdurmakIcin",
    "ai.otonom.surulmedi",
    "ai.otonom.baskaSeans",
    "ai.otonom.kimliksiz",
    "ai.otonom.atlandi",
)


def _kaynak() -> str:
    from c_soyucu import c_soy

    return c_soy(_EKRAN.read_text(encoding="utf-8"))


def test_KRITIK_ekran_SURUS_ISTEMEZ_auto_adjust_HEP_false():
    """ÖLÜLÜĞÜN ÖNCÜLÜ: ekran hiçbir yolda `auto_adjust` için "false" dışında değer göndermez.

    MUTASYON: herhangi bir `append("auto_adjust", "false")` → `"true"` / değişken → KIRMIZI.
    """
    src = _kaynak()
    cagrilar = re.findall(r"""\.append\(\s*["']auto_adjust["']\s*,\s*([^)]*?)\s*\)""", src)
    assert len(cagrilar) >= 2, (
        f"AiHubScreen'de `auto_adjust` gönderen çağrı sayısı {len(cagrilar)} (< 2: canlı + elle analiz) — kapı ölçtüğünü bulamıyor"
    )
    yabanci = [c for c in cagrilar if c not in ('"false"', "'false'")]
    assert not yabanci, (
        f"AiHubScreen `auto_adjust`a SABİT \"false\" dışında değer gönderiyor: {yabanci} — sürüş yolu geri gelmiş olur; "
        "sürüş GERİ BİLDİRİMİ (eski DONANIM SONUCU bloğu) de birlikte geri gelmeli (D1.88 / A-19)"
    )


def test_KRITIK_olu_DONANIM_SONUCU_blogu_ve_iddiasi_GERI_GELMEZ():
    """Yasak iddia YOK: ekran `hw_status` okumaz, ölü anahtarlar kaynakta ve katalogda (TR + EN) yok.

    MUTASYON: bloğu geri ekle (ya da yalnız `t("ai.otonom.suruluyor")`) ya da kataloğa anahtarı geri koy → KIRMIZI.
    """
    import i18n_yardimci as iy

    src = _kaynak()
    assert "hw_status" not in src, (
        "AiHubScreen yine `hw_status` okuyor — bu ekran sürüş istemez (auto_adjust hep false), backend hep 'idle' yazar: "
        "'cihaz sürülüyor / SÜRÜLMEDİ' bloğu ÖLÜ ve yanıltıcı"
    )
    kullanilan = iy.kullanilan_anahtarlar(_EKRAN.read_text(encoding="utf-8"))
    geri = sorted(set(_OLU_ANAHTARLAR) & kullanilan)
    assert not geri, f"AiHubScreen ölü sürüş anahtarlarını yine kullanıyor: {geri}"
    for dil in ("tr", "en"):
        katalog = iy.katalog("arayuz", dil)
        kalan = [a for a in _OLU_ANAHTARLAR if a in katalog]
        assert not kalan, f"{dil} kataloğunda ölü sürüş anahtarları duruyor: {kalan}"
    tr_degerleri = "\n".join(str(v) for v in iy.katalog("arayuz", "tr").values())
    assert "Cihaz otonom olarak sürülüyor" not in tr_degerleri, (
        "TR katalogda 'Cihaz otonom olarak sürülüyor' iddiası duruyor"
    )


def test_dogru_iddia_VAR_ekran_cihazi_SURMEZ_der():
    """Doğru iddia VAR: otonom anahtarının ipucu sürüşün YALNIZ AI Pro onay akışıyla başladığını söyler (TR birebir + EN dolu)."""
    import i18n_yardimci as iy

    iy.metin_kapisi(
        _DOSYA,
        "ai.otonom.ipucu",
        "Otonom sürüş yalnız Kontrol → AI Pro onay akışıyla başlar; bu ekran cihazı sürmez",
    )


def test_KRITIK_idle_backend_VARSAYILANI_OLMAYA_DEVAM_EDIYOR():
    """Ölülüğün backend öncülü: landmark yanıtında `hw_status` yalnız "idle" olarak ve TEK yerde atanır.

    MUTASYON: `ai_router.py`de `hw_status = "idle"` satırını başka bir değere çevir ya da ikinci bir atama ekle → KIRMIZI.

    ⚠️ O-B.1 (2-C): Python kaynağı AST ile okunur. Eskiden `c_soy` (C yorum sökücüsü) uygulanıyordu; docstring'deki
    `/api/ai/pro/*` blok yorum başlattığı için dosyanın 2254. satırından sonu BOŞALIYORDU → ikinci bir atama orada
    GÖRÜNMÜYORDU (ölçüldü: o mutant eski kapıda yeşil). AST yorumu ve dizeyi görmez; yalnız gerçek atamaları sayar.
    """
    import ast

    idle_atamalari = []
    diger_atamalar = []
    for d in ast.walk(ast.parse(_ROUTER.read_text(encoding="utf-8"))):
        if isinstance(d, (ast.Assign, ast.AnnAssign)) and d.value is not None:
            hedefler = d.targets if isinstance(d, ast.Assign) else [d.target]
            if any(isinstance(h, ast.Name) and h.id == "hw_status" for h in hedefler):
                if isinstance(d.value, ast.Constant) and d.value.value == "idle":
                    idle_atamalari.append(d.lineno)
                else:
                    diger_atamalar.append(d.lineno)
    assert idle_atamalari, (
        "ai_router artik 'idle' varsayilanini kullanmiyor -> AI Hub'in surus blogunu kaldirma onculu GECERSIZ; "
        "ya varsayilani geri getirin ya surus geri bildirimini ekrana geri koyun"
    )
    assert len(idle_atamalari) == 1, f"'idle' birden cok yerde ATANIYOR (satir {idle_atamalari})"
    assert not diger_atamalar, (
        f"ai_router `hw_status`a 'idle' DISINDA deger atiyor (satir {diger_atamalar}) -> landmark yine surus durumu bildiriyor; "
        "AI Hub'da bunu gosterecek blok YOK (kaldirildi) — geri getirin"
    )
