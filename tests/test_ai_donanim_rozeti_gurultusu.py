# -*- coding: utf-8 -*-
# Author: mertaygn
""" "⚠️ Cihaz SÜRÜLMEDİ" ROZETİ — gürültü ile GERÇEK uyarı ayrımı (sahip bildirimi 2026-09-13).

Sahip: *"cihaz sürülemedi kısmını kaldır burası ai modu."*

===============================================================================
ÖLÇÜLEN DURUM
===============================================================================
`apps/backend/servers/ai_router.py:500` → `hw_status = "idle"` **varsayılandır**. Otonom mod KAPALIYKEN
(düz analiz) hiçbir dal onu değiştirmez, yani her sıradan analizin altında

    ⚠️ Cihaz SÜRÜLMEDİ
    Otonom sürüş atlandı (idle).

yazıyordu. Hiç istenmemiş bir şeyin olmadığını duyurmak, gerçek uyarıların yanında gürültüdür
ve uyarı körlüğü üretir (bu depoda tekrar eden sınıf: "kalıcı kırmızıya alışan operatör gerçek
arızayı da görmez").

===============================================================================
⚠️ BLOK NEDEN TÜMDEN KALDIRILMADI
===============================================================================
`skipped_session_active` / `skipped_unauthenticated` / `skipped_no_detection` durumlarında
kullanıcı otonom sürüşü **İSTEMİŞTİR** ve olmadığını GÖRMEK ZORUNDADIR — aksi halde seansın
başladığını sanar. Blok tam olarak o boşluk için eklenmişti (AiHubScreen'deki kendi notu:
"backend'in skipped_* yanıtları sessizce yutuluyordu → kullanıcı seansın başladığını
sanabiliyordu"). Bu yüzden yalnız `idle` elendi.

⚠️ ÇIPA (TSX) `c_soy` İLE SOYULUR — Python kaynağı (`ai_router.py`) AST ile okunur (O-B.1): düzeltmenin kendi YORUMU
"idle" kelimesini içeriyor; ham metinde
arama yapan bir kapı, kod geri alınsa bile yorum yüzünden YEŞİL kalırdı ("yorum kapıyı
kandırdı" — bu depoda ALTI kez yaşandı).
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
for _p in (str(KOK), str(KOK / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_EKRAN = KOK / "apps" / "ui" / "src" / "screens" / "AiHubScreen.tsx"
_ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"


def _kaynak() -> str:
    from c_soyucu import c_soy

    return c_soy(_EKRAN.read_text(encoding="utf-8"))


def test_KRITIK_idle_durumunda_rozet_CIZILMEZ():
    """⚠️ ASIL KAPI — sahibin gördüğü gürültü.

    MUTASYON: `result.hw_status !== "idle"` koşulunu sil → KIRMIZI (her düz analizde
    "Cihaz SÜRÜLMEDİ" geri gelir).
    """
    src = _kaynak()
    assert '!== "idle"' in src, (
        "AiHubScreen 'idle' durumunu ELEMIYOR -> otonom mod KAPALIYKEN bile her analizin "
        "altinda 'Cihaz SURULMEDI' yazar (gurultu -> uyari korlugu)"
    )


def test_KRITIK_GERCEK_atlama_uyarilari_HALA_GORUNUR():
    """⚠️ KARŞIT KANIT — blok tümden silinmemeli.

    Kullanıcı otonom sürüşü İSTEDİĞİNDE ve backend atladığında bunu görmek ZORUNDA;
    aksi halde seansın başladığını sanar.

    MUTASYON: `hw_status` bloğunu tamamen sil → KIRMIZI.
    """
    # I18N-P1: görünen metin kataloğa taşındı — ölçüt GEVŞEMEDİ, yer değiştirdi (`gorunen_metin_var`: kaynakta düz metin YA DA kullanılan anahtarın TR
    # değeri metni içeriyor + EN dolu; blok silinirse anahtar kullanımı da kalkar → kırmızı). Durum kodları kod olarak kaynakta kalır.
    import i18n_yardimci as iy

    src = _kaynak()
    for zorunlu in ("skipped_session_active", "skipped_unauthenticated"):
        assert zorunlu in src, (
            f"'{zorunlu}' AiHubScreen'den KALKMIS -> otonom surus atlandiginda kullanici "
            "sessizce seansin basladigini sanar"
        )
    # `metin_kapisi`: kaynak anahtarı GERÇEKTEN kullanıyor + TR değeri birebir + EN dolu (kaynakta düz metin aramak YORUMA da takılırdı — AiHubScreen'in
    # yorumları "Cihaz SÜRÜLMEDİ" der)
    dosya = "apps/ui/src/screens/AiHubScreen.tsx"
    iy.metin_kapisi(dosya, "ai.otonom.surulmedi", "⚠️ Cihaz SÜRÜLMEDİ")
    # Sürüş GERÇEKTEN olduğunda da görünür kalmalı (üçüncü durum).
    iy.metin_kapisi(dosya, "ai.otonom.suruluyor", "⚡ Cihaz otonom olarak sürülüyor")


def test_KRITIK_idle_backend_VARSAYILANI_OLMAYA_DEVAM_EDIYOR():
    """Bu kapı "idle = sürüş istenmedi" varsayımına dayanıyor. Backend o anlamı değiştirirse
    (ör. idle'ı gerçek bir atlama sebebi yaparsa) eleme YANLIŞ olur ve sessizce bilgi gizler.

    MUTASYON: `ai_router.py`de `hw_status = "idle"` satırını başka bir değere çevir → KIRMIZI.

    ⚠️ O-B.1 (2-C): Python kaynağı AST ile okunur. Eskiden `c_soy` (C yorum sökücüsü) uygulanıyordu; docstring'deki
    `/api/ai/pro/*` blok yorum başlattığı için dosyanın 2254. satırından sonu BOŞALIYORDU → ikinci bir atama orada
    GÖRÜNMÜYORDU (ölçüldü: o mutant eski kapıda yeşil). AST yorumu ve dizeyi görmez; yalnız gerçek atamaları sayar.
    """
    import ast

    idle_atamalari = []
    for d in ast.walk(ast.parse(_ROUTER.read_text(encoding="utf-8"))):
        if isinstance(d, (ast.Assign, ast.AnnAssign)) and d.value is not None:
            hedefler = d.targets if isinstance(d, ast.Assign) else [d.target]
            if any(isinstance(h, ast.Name) and h.id == "hw_status" for h in hedefler) and any(
                isinstance(x, ast.Constant) and x.value == "idle" for x in ast.walk(d.value)
            ):
                idle_atamalari.append(d.lineno)
    assert idle_atamalari, (
        "ai_router artik 'idle' varsayilanini kullanmiyor -> arayuzdeki eleme varsayimi "
        "GECERSIZ; ya varsayilani geri getirin ya elemeyi gozden gecirin"
    )
    # Ve `idle` GERÇEK bir atlama sebebi olarak atanmamalı (yalnız varsayılan kalmalı).
    assert len(idle_atamalari) == 1, (
        f"'idle' birden cok yerde ATANIYOR (satir {idle_atamalari}) -> artik 'surus istenmedi' anlamina gelmiyor olabilir"
    )
