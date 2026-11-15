# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KURULUM AGACINI DEGISTIREN HER AKIS KURULUM KILIDINI ALIR (denetim 2026-08-23, bulgu C6).

⚠️ BU HATA IKI KEZ OLDU — kapi bu yuzden var.
2026-08-16 denetimi (Bulgu 3) `apply_runtime_update`in kilidi ALMADIGINI bulmustu ve duzeltmisti.
Ama ayni sinifin bir uyesi daha vardi: `apply_self_update`. O da en sonunda NSIS'i `/S` ile
calistiriyor ve kurulum kancasi `taskkill /F /IM PEMF_Backend.exe /T` yapiyor — yani ikinci bir
pencere o sirada kurulum/onarim/guncelleme yapiyorsa ONUN backend'ini olduruyor: saglik kapisi
duser ve SAGLAM bir guncelleme bosuna geri alinir, ya da agac yarim kalir.

Duzeltmeyi tek akista yapmak bu deponun 1 numarali hata desenidir ("ayni kural iki yerde, biri
guncellenmis oteki unutulmus"). Bu dosya kurali AKISLARIN TAMAMI icin kilitler: yeni bir yikici
akis eklendiginde de kirmizi verir.

⚠️ `prefetch_runtime_update` KASTEN LISTEDE DEGIL: o yalnizca ON-INDIRME yapar, agaca dokunmaz;
kilidi YOKLAYIP birakir (main.rs yorumu bunu acikca gerekcelendiriyor). Kilit almasi gerekseydi
arka plan indirmesi kurulumu bloklardi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from kaynak_soyucu import rust_soy

_KOK = Path(__file__).resolve().parents[1]
_MAIN = _KOK / "launcher" / "app" / "src" / "main.rs"

# Kurulum agacini DEGISTIREN (ya da onu degistiren bir sureci baslatan) komutlar.
_YIKICI_AKISLAR = [
    "install_and_launch_ile",  # KP-6 D4: komut kabuk.rs'te ince S kabuğu, gövde `_ile`
    "repair_ile",  # KP-6 D4
    "uninstall_ile",  # KP-6 D5
    "apply_runtime_update_ile",  # KP-6 D6
    "apply_self_update_ile",  # KP-6 D7
]


@pytest.fixture(scope="module")
def kaynak() -> str:
    # D5.52 (B-10.127): YORUM-SOYULMUŞ kaynak (dizge-farkında) — yorumdaki `let _kilit = …` kilit SAYILMAZ.
    return rust_soy(_MAIN.read_text(encoding="utf-8", errors="replace"))


def _govde(kaynak: str, ad: str) -> str:
    """Fonksiyon govdesi — bir sonraki ust-seviye `async fn`/`fn` tanimina kadar."""
    # KP-6 D4: gövdeler genel tür parametreli olabilir (`fn x_ile<O: KomutOrtami>(`)
    m = re.search(rf"(?:async\s+)?fn\s+{re.escape(ad)}\s*(?:<[^>(]*>)?\s*\(", kaynak)
    assert m, f"`{ad}` main.rs'te bulunamadi — ad degismis olabilir, kapi guncellensin"
    sonraki = re.search(r"\n(?:#\[[^\n]*\]\n)*(?:pub\s+)?(?:async\s+)?fn\s+\w+\s*(?:<[^>(]*>)?\s*\(", kaynak[m.end() :])
    return kaynak[m.end() : m.end() + (sonraki.start() if sonraki else len(kaynak))]


@pytest.mark.parametrize("akis", _YIKICI_AKISLAR)
def test_KRITIK_yikici_akis_kurulum_kilidini_ALIR(kaynak, akis):
    g = _govde(kaynak, akis)
    # D5.52: ADLI bağ şart — adsız deyim `install::kurulum_kilidi_al(&root)?;` değeri ANINDA düşürür (kilit fiilen YOK).
    assert re.search(r"let\s+(?:mut\s+)?(?!_\s*[=:])[A-Za-z_]\w*\s*=\s*install::kurulum_kilidi_al\(", g), (
        f"`{akis}` kurulum agacini degistiriyor ama `install::kurulum_kilidi_al` CAGIRMIYOR — "
        "iki pencere ayni anda kurulum yapabilir; biri otekinin backend'ini oldurur "
        "(2026-08-16 Bulgu 3'un ayni sinifi, bkz. dosya basligi)"
    )


@pytest.mark.parametrize("akis", _YIKICI_AKISLAR)
def test_KRITIK_kilit_ANINDA_dusurulmez(kaynak, akis):
    """⚠️ `let _ = kurulum_kilidi_al(...)` koruma DEGILDIR.

    Rust'ta `let _ = deger` bagi kurmaz: deger ifadenin sonunda ANINDA `Drop` olur, yani kilit
    dosyasi hemen birakilir ve akis kilitsiz surer. Koruma ancak `let _kilit = ...` gibi ADI OLAN
    bir bagla (ya da baska bir bagla) yasar. Bu ayrim goz kararı fark edilmez; testle kilitlenir.
    """
    g = _govde(kaynak, akis)
    assert not re.search(r"let\s+_\s*=\s*install::kurulum_kilidi_al", g), (
        f"`{akis}` kilidi `let _ =` ile aliyor → deger ANINDA dusuyor, kilit fiilen YOK. `let _kilit = ...` kullanin."
    )


def test_KARSIT_KANIT_prefetch_kilidi_TUTMAZ(kaynak):
    """On-indirme kilidi TUTMAMALI — tutsaydi arka plan indirmesi kurulumu bloklardi.

    Kapinin asiri genislemedigini olcer: `prefetch_runtime_update` kilidi yalnizca YOKLAR
    (mesgulse vazgecer) ve tutmaz. Bu KASITLI bir istisnadir.
    """
    g = _govde(kaynak, "prefetch_runtime_update_ile")  # KP-6 D3: komut kabuk.rs'te ince S kabuğu, gövde `_ile`
    assert "kurulum_kilidi_al" in g, "prefetch kilidi hic yoklamiyor — mesgulken indirmeye girer"
    assert not re.search(r"let\s+_kilit\s*=\s*install::kurulum_kilidi_al", g), (
        "prefetch kilidi TUTUYOR — arka plan indirmesi kurulumu bloklar (kasitli istisna bozuldu)"
    )
