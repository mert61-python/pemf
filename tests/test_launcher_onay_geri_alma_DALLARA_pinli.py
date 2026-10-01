# Author: mertaygn, cglrgrkn
"""D1.35 · B-10.46 · B-10.47 — launcher'ın güncelleme ONAY / GERİ-ALMA kararı doğru DALA pinli.

Denetleyiciler `tests/launcher_onay_karari.py`'de; gerçek `main.rs`'e uygulanan kapılar
`test_runtime_geri_alma_dongusu_bagli.py` ve `test_saglik_db_kapisi_bagli.py`'dedir (adları
korundu). Bu dosya denetleyicilerin ve Rust yorum soyucusunun KENDİSİNİ kanıtlar (Ö.6): gerçek
`main.rs` metnine bellek içinde uygulanan her mutantta ilgili denetleyici KIRMIZI olmalı,
mutantsız metinde YEŞİL. Kör bir denetleyici burada düşer.

Neden önemli (plan C1b-60 / D1.37 orkestratör notu): D1.37 backend'i DB'siz AÇIK tutacak; o andan
sonra DB'yi bozan bir yayını yakalayan TEK ağ launcher'ın `dbReady == false → geri al` dalıdır.
Bu dal kör kapıyla korunuyordu.
"""

from __future__ import annotations

import pytest
from launcher_onay_karari import (
    MAIN_RS,
    db_kapisi_denetle,
    err_kolu_denetle,
    onay_sirasi_denetle,
)
from rs_soyucu import ifade_deseni, rs_soy, ust_duzey_eslesmeler

# ── Rust yorum soyucusu öz-denetimi ─────────────────────────────────────────


def test_soyucu_omur_belirtecinden_SONRAKI_yorumu_da_soyar():
    """`c_soy` burada 'static'i karakter sabiti sanıp dosyanın kalanını yorumsuz bırakırdı."""
    src = "fn f(x: &'static str) -> u8 { 1 } // KAPI_IFADESI\nfn g<'a>(y: &'a u8) {} /* KAPI_IFADESI */\n"
    assert "KAPI_IFADESI" not in rs_soy(src)


def test_soyucu_ham_dize_ve_normal_dizeyi_KORUR_yorumu_soyar():
    src = 'let a = r#"x "//" {y}"#; let b = "http://z {e}"; let c = \'"\'; // YORUM\n'
    soy = rs_soy(src)
    assert 'r#"x "//" {y}"#' in soy and '"http://z {e}"' in soy and "'\"'" in soy
    assert "YORUM" not in soy


def test_soyucu_IC_ICE_blok_yorumu_soyar():
    soy = rs_soy("a /* dis /* ic */ hala_yorum */ b")
    assert "hala_yorum" not in soy and soy.split() == ["a", "b"]


def test_soyucu_UZUNLUGU_korur_ve_dizeleri_bosaltinca_suslu_parantez_kalmaz():
    src = 'let s = format!("{e} {{x}}"); // {\nlet t = r"{";\n'
    assert len(rs_soy(src)) == len(src) == len(rs_soy(src, dizeleri_bosalt=True))
    assert rs_soy(src, dizeleri_bosalt=True).count("{") == 0


def test_ust_duzey_eslesme_ALT_BLOK_icindekini_SAYMAZ():
    src = "{ if false { X(); } Y(); }"
    soy, maske = rs_soy(src), rs_soy(src, dizeleri_bosalt=True)
    assert ust_duzey_eslesmeler(soy, maske, 1, len(src) - 1, "X();") == []
    assert len(ust_duzey_eslesmeler(soy, maske, 1, len(src) - 1, "Y();")) == 1
    assert ifade_deseni("a(&b) == Some(false) {").fullmatch("a( & b )==Some( false ){")


# ── denetleyicilerin öz-denetimi: gerçek main.rs + bellek içi mutant ─────────


@pytest.fixture(scope="module")
def main_rs() -> str:
    return MAIN_RS.read_text(encoding="utf-8").replace("\r\n", "\n")


_ERR_KAYDET = (
    "                flow::geri_almayi_kaydet(&root2, &manifest_raw);\n"
    "                let geri_hata = flow::guncellemeyi_geri_al(&root2, &geri)"
)
_ERR_GERI_AL_SATIRI = (
    "                let geri_hata = flow::guncellemeyi_geri_al(&root2, &geri).err().map(|x| x.to_string());\n"
)
_DB_IF = "                if backend::db_hazir_mi(port) == Some(false) {\n"
_TEARDOWN = "                    stop_backend_for_teardown(Some((child, port)), &root2, bellek2.clone());\n"
_ONAYLA = "                flow::guncellemeyi_onayla(&root2, &geri);\n"

# (ad, denetleyici, [(eski, yeni), ...]) — eski metin main.rs'te TAM 1 kez geçmeli.
_MUTANTLAR = [
    # B-10.46 — sağlık kapısı düştüğünde deneme sayacı
    ("err_kaydet_SILINDI", err_kolu_denetle, [(_ERR_KAYDET, _ERR_KAYDET.split("\n", 1)[1])]),
    ("err_kaydet_YORUMDA_kopya", err_kolu_denetle, [(_ERR_KAYDET, "                // " + _ERR_KAYDET.lstrip())]),
    (
        "err_kaydet_IF_FALSE_icinde",
        err_kolu_denetle,
        [
            (
                _ERR_KAYDET,
                "                if false { flow::geri_almayi_kaydet(&root2, &manifest_raw); }\n"
                + _ERR_KAYDET.split("\n", 1)[1],
            )
        ],
    ),
    (
        "err_kaydet_geri_almadan_SONRA",
        err_kolu_denetle,
        # "\n" öneki: 16 boşluklu satır, 20 boşluklu kardeşlerinin ALT DİZESİ olarak da geçer
        [
            ("\n" + _ERR_KAYDET.split("\n", 1)[0] + "\n", "\n"),
            (_ERR_GERI_AL_SATIRI, _ERR_GERI_AL_SATIRI + _ERR_KAYDET.split("\n", 1)[0] + "\n"),
        ],
    ),
    # B-10.47 — dbReady=false geri alma dalı
    (
        "db_AND_FALSE",
        db_kapisi_denetle,
        [(_DB_IF, "                if backend::db_hazir_mi(port) == Some(false) && false {\n")],
    ),
    ("db_SOME_TRUE", db_kapisi_denetle, [(_DB_IF, "                if backend::db_hazir_mi(port) == Some(true) {\n")]),
    (
        "db_BILINMEYEN_de_geri_alir",
        db_kapisi_denetle,
        [(_DB_IF, "                if backend::db_hazir_mi(port) != Some(true) {\n")],
    ),
    (
        "db_kosulu_YORUMDA_kopya",
        db_kapisi_denetle,
        [(_DB_IF, "                // if backend::db_hazir_mi(port) == Some(false) {\n                if false {\n")],
    ),
    ("db_dali_E_STOPSUZ_kill", db_kapisi_denetle, [(_TEARDOWN, "                    let _ = child.kill();\n")]),
    # onay sırası
    ("onay_db_denetiminden_ONCE", onay_sirasi_denetle, [(_ONAYLA, ""), (_DB_IF, _ONAYLA + _DB_IF)]),
    ("onay_ERR_kolunda_da", onay_sirasi_denetle, [(_ERR_GERI_AL_SATIRI, _ERR_GERI_AL_SATIRI + _ONAYLA)]),
]


def _uygula(src: str, degisiklikler) -> str:
    for eski, yeni in degisiklikler:
        assert src.count(eski) == 1, f"mutant çapası main.rs'te {src.count(eski)} kez: {eski[:70]!r}"
        src = src.replace(eski, yeni)
    return src


def test_ON_KOSUL_mutantsiz_main_rs_TUM_denetleyicilerden_gecer(main_rs):
    err_kolu_denetle(main_rs)
    db_kapisi_denetle(main_rs)
    onay_sirasi_denetle(main_rs)


@pytest.mark.parametrize(("ad", "denetleyici", "degisiklikler"), _MUTANTLAR, ids=[m[0] for m in _MUTANTLAR])
def test_KRITIK_denetleyici_mutantta_KIRMIZI(main_rs, ad, denetleyici, degisiklikler):
    mutant = _uygula(main_rs, degisiklikler)
    assert mutant != main_rs
    with pytest.raises(AssertionError):
        denetleyici(mutant)
