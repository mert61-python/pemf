# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DEV-C2 — i18n çıkarıcısı (`scripts/i18n/cikar.py::rust_adaylari`) Rust DİZGE / KARAKTER SABİTİ sınırlarını doğru bulur.

ARIZA (LN L8c, 2026-10-22; hafıza "K-2 Rust dizgesi `}`"): çıkarıcı yorumları soyuyor ama dizge İÇERİĞİNİ bırakıyordu; `#[cfg(test)]` /
`#[test]` bölgelerini süslü parantez sayarak bulurken dizgedeki (`"\\n}\\n"`) ve karakter sabitindeki (`'}'`) parantezi de saydı → test bölgesi
ERKEN kapandı, test modülündeki metin "kapsam dışı sabit metin" (K-2 kırmızısı) sayıldı. Ayrıca bayt-ham dizge `br"…\\"` ham dizge olarak
TANINMIYORDU (önündeki `b` tanımlayıcı karakteri sayılıyordu) → normal dizge gibi `\\"` kaçış sanılıp dizge bir SONRAKİ tırnağa kadar uzuyor,
ardından gelen ürün metninin sınırı kayıyordu. Geçici çözüm kaynakta `"\\u{7d}"` idi; kalıcı çözüm çıkarıcıda.

ÖLÇÜM: sentetik Rust kaynağı GERÇEK `rust_adaylari`'na verilir. Ürün metni DEĞİŞMEZ (K-1…K-7 ve TR taban yeşil kalmalı — küme kaydında).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import cikar  # noqa: E402

_TEST_MODULU = r'''pub fn uretim() -> String { t("rust.ornek.anahtar") }

#[cfg(test)]
mod tests {
    #[test]
    fn kapanis_dizgesi() {
        let kapanis = "\n}\n";
        let c = '}';
        let mesaj = "Kurulum tamamlandı, lütfen bekleyin";
        assert!(!mesaj.is_empty() && kapanis.len() == 3 && c == '}');
    }
}
'''

_BAYT_HAM = r'''pub fn yol() -> &'static [u8] { br"C:\yol\" }
pub fn mesaj() -> String { String::from("Güncelleme başarısız oldu, tekrar deneyin") }
'''

_HAM_VE_OMUR = r'''pub fn h<'a>(x: &'a str) -> &'a str { let _ = r#"a "}" b"#; x }
pub fn m() -> String { String::from("Profil kaldırılamadı, bağlantıyı kontrol edin") }
'''


def _metinler(kaynak: str) -> list[str]:
    return [a["metin"] for a in cikar.rust_adaylari("launcher/core/src/sentetik.rs", kaynak)]


def test_KRITIK_dizgedeki_ve_karakter_sabitindeki_parantez_TEST_bolgesini_KAPATMAZ():
    assert _metinler(_TEST_MODULU) == [], (
        "test modülündeki metin ürün metni sayıldı — dizgedeki / karakter sabitindeki `}` test bölgesini ERKEN kapattı (DEV-C2)"
    )


#: Her parantez kaynağı AYRI ölçülür (iki kaynak birlikteyken biri ötekini dengeliyordu — mutant sağ kaldı, ölçüldü). Metin test
#: modülünde ama #[test] işlevinin DIŞINDA (sabit) → yalnız `mod tests` bölgesi doğru kapanırsa kapsam dışı kalır.
_TEK_KAYNAK = {
    "dizge": 'let k = "\\n}\\n";',
    "karakter_sabiti": "let c = '}';",
    "bayt_ham": 'let b = br"}";',
}


@pytest.mark.parametrize("kaynak", sorted(_TEK_KAYNAK))
def test_KRITIK_TEK_parantez_kaynagi_test_modulunu_ERKEN_kapatmaz(kaynak):
    src = (
        "pub fn u() -> String { t(\"x.y\") }\n\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn a() {\n        "
        + _TEK_KAYNAK[kaynak]
        + '\n    }\n    const MESAJ: &str = "Kurulum tamamlandı, lütfen bekleyin";\n}\n'
    )
    assert _metinler(src) == [], (
        f"{kaynak} içindeki `}}` test modülünü ERKEN kapattı — test metni ürün metni sayıldı (DEV-C2)"
    )


def test_KRITIK_ters_boluyle_biten_BAYT_HAM_dizge_sonraki_metnin_sinirini_KAYDIRMAZ():
    assert _metinler(_BAYT_HAM) == ["Güncelleme başarısız oldu, tekrar deneyin"], (
        "`br\"…\\\"` bayt-ham dizgesi normal dizge sanıldı — sonraki ürün metninin sınırı kaydı (DEV-C2)"
    )


def test_KARSIT_ham_dizge_ve_omur_adi_ETKILEMEZ():
    assert _metinler(_HAM_VE_OMUR) == ["Profil kaldırılamadı, bağlantıyı kontrol edin"]
