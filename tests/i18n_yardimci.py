# -*- coding: utf-8 -*-
"""I18N KAPI YARDIMCISI — kaynak METNİNİ tarayan pytest kapılarını göçe dayanıklı yapar (T13). ZAYIFLATMAZ.

Göç bir metni kaynaktan kataloğa taşır: `<Text>Tüm bobinler durduruldu</Text>` → `<Text>{t("guvenlik.acilDurdur.durduruldu")}</Text>`.
Kaynakta `"Tüm bobinler durduruldu" in src` arayan eski kapı yanlış kırmızı verir. Ölçüt GEVŞETİLMEZ, YER DEĞİŞTİRİR:

    gorunen_metin_var(dosya, "Tüm bobinler durduruldu")
        = kaynakta düz metin VAR (henüz taşınmamış)
          YA DA kaynak bir anahtarı KULLANIYOR ve o anahtarın TR değeri metni İÇERİYOR ve EN değeri BOŞ DEĞİL.

    metin_kapisi(dosya, anahtar, beklenen_tr)
        = kaynak anahtarı kullanıyor VE tr değeri beklenen metinle AYNI VE en değeri boş değil (taşınmış kapının kesin biçimi).

Her çevrilen kapıya iki mutant (KURALLAR.md §Metin tarayan kapı): (1) TR değeri değişti → kırmızı; (2) `t()` çağrısı kaynaktan kalktı →
kırmızı. Bu yardımcının kendisi `tests/test_i18n_yardimci.py` ile sınanır.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import ortak  # noqa: E402

#: Kaynakta anahtar kullanımı — TEK KAYNAK `scripts/i18n/ortak.py` (aynı düzenli ifadeyi `katalog.py taban` da kullanır).
ANAHTAR_KULLANIMI = ortak.ANAHTAR_KULLANIMI


def kaynak(dosya: str) -> str:
    return (KOK / dosya).read_text(encoding="utf-8")


def kullanilan_anahtarlar(metin: str) -> set[str]:
    return ortak.kullanilan_anahtarlar(metin)


@lru_cache(maxsize=None)
def _duz(yuzey: str, dil: str) -> dict:
    return ortak.duzlestir(ortak.katalog_yukle(yuzey, dil))


def katalog_yenile() -> None:
    _duz.cache_clear()


def katalog(yuzey: str, dil: str = "tr") -> dict:
    return _duz(yuzey, dil)


def _yuzey(dosya: str, yuzey: str | None) -> str:
    y = yuzey or ortak.dosyanin_yuzeyi(dosya)
    if not y:
        raise AssertionError(f"{dosya}: yüzeyi bilinmiyor — yuzey= verin")
    return y


def _kullanilan_degerler(dosya: str, yuzey: str | None, dil: str) -> dict[str, str]:
    y = _yuzey(dosya, yuzey)
    duz = katalog(y, dil)
    sonuc = {}
    for k in kullanilan_anahtarlar(kaynak(dosya)):
        for aday in (k, *(k + s for s in ortak.COGUL_SONEKLERI)):
            if aday in duz:
                sonuc[aday] = duz[aday]
    return sonuc


def gorunen_metin_var(dosya: str, metin: str, yuzey: str | None = None) -> bool:
    """Metin kullanıcıya bu dosyadan ulaşıyor mu: kaynakta düz metin YA DA kullanılan bir anahtarın TR değerinde (+ EN dolu)."""
    if metin in kaynak(dosya):
        return True
    y = _yuzey(dosya, yuzey)
    en = katalog(y, "en")
    return any(metin in v and str(en.get(k, "")).strip() for k, v in _kullanilan_degerler(dosya, yuzey, "tr").items())


def gorunen_metinler(dosya: str, yuzey: str | None = None) -> str:
    """Kaynak + kullandığı anahtarların TR değerleri (düzenli ifade kapıları için birleşik metin)."""
    return kaynak(dosya) + "\n" + "\n".join(_kullanilan_degerler(dosya, yuzey, "tr").values())


def metin_kapisi(dosya: str, anahtar: str, beklenen_tr: str, yuzey: str | None = None) -> None:
    """Taşınmış kapının KESİN biçimi: kaynak anahtarı kullanıyor + TR değeri birebir + EN dolu."""
    y = _yuzey(dosya, yuzey)
    kullanilan = kullanilan_anahtarlar(kaynak(dosya))
    assert anahtar in kullanilan, (
        f"{dosya} '{anahtar}' anahtarını KULLANMIYOR (t() çağrısı kalkmış ya da anahtar değişmiş)"
    )
    tr = katalog(y, "tr")
    en = katalog(y, "en")
    deger = tr.get(anahtar, tr.get(anahtar + "_other"))
    assert deger == beklenen_tr, f"{anahtar} TR değeri değişmiş: {deger!r} ≠ {beklenen_tr!r}"
    assert str(en.get(anahtar, en.get(anahtar + "_other", ""))).strip(), f"{anahtar} EN değeri BOŞ / yok"


def gorunur_satir(satir: str, yuzey: str) -> str:
    """SATIR bazlı kapılar için: satırdaki anahtar kullanımlarını (`t("…")`, `ceviri.t("…")`, NSIS `$(PEMF_…)` …) o anahtarın TR
    değeriyle değiştirir — EN değeri boş olan anahtar DEĞİŞTİRİLMEZ (yarım çeviri ölçütü geçemez). Örn. hooks.nsi
    `MessageBox … "$(PEMF_estopDogrulanamadiKutu)"` → `MessageBox … "PEMF: bobin acil-durdurma DOĞRULANAMADI … ELLE kontrol edin …"`."""
    tr, en = katalog(yuzey, "tr"), katalog(yuzey, "en")

    def degistir(m: re.Match) -> str:
        anahtar = m.group(1) or m.group(2) or ("nsis." + m.group(3).replace("_", ".") if m.group(3) else "")
        if anahtar in tr and str(en.get(anahtar, "")).strip():
            return f"{m.group(0)} «{tr[anahtar]}»"
        return m.group(0)

    return ANAHTAR_KULLANIMI.sub(degistir, satir)
