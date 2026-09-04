# Author: mertaygn, cglrgrkn
"""DOKUNMA HEDEFİ KAPISI (sabit sayaçlı cırcır)  [S3 adım 9, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM: uygulamadaki dokunulabilir öğelerin çoğu `paddingVertical: spacing.xs` ya da
`rs(40)` gibi ÖLÇEKLE KÜÇÜLEN değerlerle kuruluydu. 320 px'lik telefonda ölçek 0,85 olduğu için
44 px'lik erişilebilirlik tabanı 34-37 px'e düşüyor, ikon-only düğmeler ise yalnız ikon boyutu
kadar (24-32 px) dokunulabilir kalıyordu.

BU KAPI NE YAPAR: `Pressable` / `TouchableOpacity` JSX açılışlarını bulur, `style` içindeki
`styles.X` referanslarını aynı dosyanın `StyleSheet.create` bloğuna çözer ve hedefin YETERLİ olup
olmadığına bakar. Yeterlilik ölçütleri (herhangi biri):
  · stil gövdesinde `touch.min` / `touch.sm` (ölçekle küçülmeyen taban),
  · `minHeight`/`height`/`width` >= 44 sabiti,
  · `minHeight: rs(N)` ile N >= 52 (0,85 × 52 = 44),
  · ortak ilkel kullanımı (`IconButton`, `Chip`, `Button`) — onların tabanı jest ile kilitli,
  · satırın hemen üstünde `// dokunma-hedefi: muaf (gerekçe)` yorumu.

⚠️ SABİT SAYAÇ: bu bir CIRCIR'dır, tam temizlik değil. Kalan ihlaller sayılır ve sayı SABİTE
eşit olmalıdır. Sayı ARTARSA kapı kırmızı olur (yeni ihlal girdi); AZALIRSA da kırmızı olur
(sabiti düşürmeyi unuttunuz — memory: "Route Contract Sayaç Kapısı"). Faz D'de hedef 0.

⚠️ `hitSlop` (touch.slopFor dahil) BOYUT ölçütünü KARŞILAMAZ ve muafiyet saymaz: tampon yalnız
komşu hedeflerle binişmeyi düzenler, kutunun kendisini büyütmez. (Ölçüldü: slopFor'u muafiyet
sayan ilk sürümde bobin seçicinin `rs(40)`'a geri dönmesi kapıyı KIRMIZI YAPMIYORDU.)

⚠️ Kapının KIRMIZI olabildiği `test_kapi_gercekten_olcuyor` ile kanıtlanır (sentetik mutasyon).
"""

import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "pf" / "src"

# 2026-09-05 ölçümü (S3: 139 → 119; S7 adım 10 flipBtn ile 118).
# Faz D hedefi: 0. Düşürdükçe bu sayıyı da düşürün.
KALAN_IHLAL = 118
# Gerekçeli muafiyetler (perde/kart gibi dokunuş yutucular).
MUAF_SAYISI = 2

pytestmark = pytest.mark.skipif(
    not (_PF / "components" / "ui" / "IconButton.tsx").exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)

_DOKUNULABILIR = re.compile(r"<(Pressable|TouchableOpacity)\b(.*?)(?<!=)>", re.DOTALL)
_STIL_REF = re.compile(r"styles\.(\w+)")
_SAYI = re.compile(r"(minHeight|height|minWidth|width)\s*:\s*(\d+)")
_RS = re.compile(r"(minHeight|height|minWidth|width)\s*:\s*rs\(\s*(\d+)\s*\)")


def _stil_sozlugu(src: str) -> dict:
    """`StyleSheet.create({...})` bloğunu parantez eşleyerek `ad -> gövde` sözlüğüne çevir."""
    i = src.find("StyleSheet.create(")
    if i < 0:
        return {}
    j = src.index("{", i)
    derinlik, k = 0, j
    while k < len(src):
        if src[k] == "{":
            derinlik += 1
        elif src[k] == "}":
            derinlik -= 1
            if derinlik == 0:
                break
        k += 1
    govde = src[j : k + 1]
    sozluk, pos = {}, 0
    for m in re.finditer(r"^\s{2}(\w+)\s*:\s*\{", govde, re.MULTILINE):
        if m.start() < pos:
            continue
        ic, n = 0, m.end() - 1
        while n < len(govde):
            if govde[n] == "{":
                ic += 1
            elif govde[n] == "}":
                ic -= 1
                if ic == 0:
                    break
            n += 1
        sozluk[m.group(1)] = govde[m.end() - 1 : n + 1]
        pos = n
    # Tek satırlık stiller (`ad: { ... },` aynı satırda)
    for m in re.finditer(r"^\s{2}(\w+)\s*:\s*(\{[^\n]*\}),?\s*$", govde, re.MULTILINE):
        sozluk.setdefault(m.group(1), m.group(2))
    return sozluk


def _yeterli_stil(govde: str) -> bool:
    if "touch.min" in govde or "touch.sm" in govde:
        return True
    for m in _SAYI.finditer(govde):
        if int(m.group(2)) >= 44:
            return True
    for m in _RS.finditer(govde):
        if int(m.group(2)) >= 52:
            return True
    return False


def _tara():
    """(ihlal listesi, muaf sayısı) döndürür."""
    ihlal, muaf = [], 0
    for p in sorted(_PF.rglob("*.tsx")):
        if "__tests__" in p.parts:
            continue
        src = p.read_text(encoding="utf-8")
        stiller = _stil_sozlugu(src)
        for m in _DOKUNULABILIR.finditer(src):
            props = m.group(2)
            onceki = src[: m.start()].rsplit("\n", 3)[0]
            if "dokunma-hedefi: muaf" in src[max(0, m.start() - 220) : m.start()]:
                muaf += 1
                continue
            if any(_yeterli_stil(stiller.get(ad, "")) for ad in _STIL_REF.findall(props)):
                continue
            if re.search(r"(minHeight|height)\s*:\s*touch\.", props):
                continue
            satir = src[: m.start()].count("\n") + 1
            etiket = re.search(r'accessibilityLabel=\{?["`]([^"`}]{0,40})', props)
            ihlal.append(f"{p.relative_to(_PF).as_posix()}:{satir} {etiket.group(1) if etiket else ''}".strip())
            del onceki
    return ihlal, muaf


def test_KRITIK_dokunma_hedefi_cırcırı_geri_gitmedi():
    """Sayı ARTTIYSA yeni ihlal girdi; AZALDIYSA sabiti düşürmeyi unuttunuz."""
    ihlal, _ = _tara()
    assert len(ihlal) == KALAN_IHLAL, (
        f"Dokunma hedefi ihlali sayısı {len(ihlal)}, sabit {KALAN_IHLAL}.\n"
        "ARTTIYSA: yeni eklenen dokunulabilir öğeye touch.min/touch.sm tabanı verin ya da\n"
        "ortak ilkeli (IconButton/Chip/Button) kullanın.\n"
        "AZALDIYSA: bu dosyadaki KALAN_IHLAL sabitini yeni sayıya düşürün.\n"
        "İlk 25 ihlal:\n" + "\n".join(ihlal[:25])
    )


def test_muafiyetler_gerekceli_ve_sayili():
    """Muafiyet ancak `// dokunma-hedefi: muaf (gerekçe)` yorumuyla verilir."""
    _, muaf = _tara()
    assert muaf == MUAF_SAYISI, f"Gerekçeli muafiyet sayısı {muaf}, sabit {MUAF_SAYISI}"


def test_ortak_ilkeller_tabani_kaynakta_tasiyor():
    """Cırcırın dayanağı: ilkellerin tabanı ölçekle AŞAĞI inmez."""
    for ad, beklenen in (("IconButton.tsx", "touch.min"), ("Chip.tsx", "touch.sm")):
        src = (_PF / "components" / "ui" / ad).read_text(encoding="utf-8")
        assert beklenen in src, f"{ad} dokunma tabanını bırakmış"
    tokens = (_PF / "theme" / "tokens.ts").read_text(encoding="utf-8")
    assert "Math.max(44, rs(44))" in tokens and "Math.max(40, rs(40))" in tokens, (
        "touch tabanı `rs()`e bırakılmış: 320 px'te 37/34 px'e düşer."
    )


def test_kapi_gercekten_olcuyor():
    """MUTASYON ÖZ-TESTİ: yeterli bir stil bozulunca tarayıcı onu ihlal sayıyor mu?"""
    assert _yeterli_stil("{ minHeight: touch.min }")
    assert _yeterli_stil("{ height: 44, width: 44 }")
    assert _yeterli_stil("{ minHeight: rs(52) }")
    assert not _yeterli_stil("{ minHeight: rs(40) }")  # 320 px'te 34 px
    assert not _yeterli_stil("{ paddingVertical: spacing.xs }")
    assert not _yeterli_stil("{ height: 32 }")
