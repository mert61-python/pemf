# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM32 BOBİN SAYISI TEK KAYNAK — elle yazılmış initializer listesi SESSİZCE sıfırlar.

⚠️ NEDEN BU KAPI VAR (2026-09-10, bobin 6-7 ESP'den STM'e taşınırken ölçüldü):

`NUM_COILS` 5'ten 7'ye çıkarıldığında firmware'de bobin başına BİR eleman taşıyan **dokuz**
adet elle yazılmış initializer listesi vardı:

    static volatile uint32_t g_tpp[NUM_COILS] = {500, 500, 500, 500, 500};
    static uint8_t g_prev_state[NUM_COILS] = {255, 255, 255, 255, 255};
    static volatile CoilParamSet_t g_shadow = { .coil = { {...}, {...}, {...}, {...}, {...} } };

C standardı, eksik elemanları **sessizce sıfırlar** ve **derleyici UYARMAZ** (`-Wall` dahil;
`-Wmissing-field-initializers` yalnız struct ALANLARI için, dizi elemanları için değil).
Somut zarar, bobin 6-7 için:

* `g_tpp[5..6] = 0`      → ISR `50000/0`; tpp=0 ile `tick >= tpp` her tick'te doğru
* `g_slew_ticks[5..6]=0` → duty ASLA yükselmez; bobin sessizce hiç sürülmez
* `g_prev_state[5..6]=0` → 0 = "B darbesi sürüyor" demek; ilk tick'te geçiş kodu atlanır
* `g_shadow.coil[5..6].freq = 0` → aynı bölme

Hiçbiri hata vermez, hiçbiri log basmaz: bobin **sessizce ölür** ya da tanımsız davranır.
Bu, deponun tekrar eden en pahalı sınıfı (aynı gün maskede de yaşandı: darbe bağlı olmayan
pine gitti, ACK "çalışıyor" dedi, alan sıfırdı).

ÇÖZÜM (bu kapının pinlediği): sıfır olan diziler `{0}` ile (C tümünü sıfırlar), SIFIR-OLMAYAN
varsayılanlar `Coil_StateInit()` içinde **döngüyle** atanır → sayı `NUM_COILS`'ten TÜREUR.
Kablolamaya özgü kalması gereken tek liste (`g_ntc_kanal`) firmware'de bir `_Static_assert`
ile bağlanmıştır; bu depoda C derlenmediği için o iddia burada da AYRICA ölçülür.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
FW = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
# ⚠️ AYNA KAPISI KALDIRILDI (2026-09-11): `stm32_pemf_unipolar` projesi silindi.
# Sebep: surus kipi artik `PEMF_BOBIN_UNIPOLAR_MASKESI` ile BOBIN BASINA seciliyor,
# ikinci bir derleme gerekmiyor. TEK kaynak = firmware/stm32_pemf.

pytestmark = pytest.mark.skipif(not FW.exists(), reason="firmware/ kaynak agaci yok")


def _oku(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def yorumsuz(kod: str) -> str:
    """C yorumlarını ve string/char literallerini BOŞLUKLA değiştirir (satır sayısı korunur).

    Neden gerekli: yorum içindeki `{500, 500, 500, 500, 500}` örneği kapıyı yanlış yere
    kilitler; string içindeki süslü parantez de eleman saymayı bozar.
    """
    out = []
    i, n, durum = 0, len(kod), "kod"
    while i < n:
        ch = kod[i]
        if durum == "kod":
            if kod[i : i + 2] == "//":
                durum = "satir"
                out.append("  ")
                i += 2
                continue
            if kod[i : i + 2] == "/*":
                durum = "blok"
                out.append("  ")
                i += 2
                continue
            if ch in '"' + chr(39):
                durum = "str" if ch == '"' else "chr"
                out.append(" ")
                i += 1
                continue
            out.append(ch)
        elif durum == "satir":
            out.append("\n" if ch == "\n" else " ")
            if ch == "\n":
                durum = "kod"
        elif durum == "blok":
            out.append("\n" if ch == "\n" else " ")
            if kod[i : i + 2] == "*/":
                out.append(" ")
                durum = "kod"
                i += 2
                continue
        else:  # str / chr
            if ch == chr(92):
                out.append("  ")
                i += 2
                continue
            kapanis = '"' if durum == "str" else chr(39)
            out.append("\n" if ch == "\n" else " ")
            if ch == kapanis:
                durum = "kod"
        i += 1
    return "".join(out)


def _kapanisi_bul(kod: str, acilis: int) -> int:
    """`kod[acilis] == '{'` varsayar; eşleşen '}' indeksini döndürür (-1 = eşleşme yok)."""
    derinlik = 0
    for j in range(acilis, len(kod)):
        if kod[j] == "{":
            derinlik += 1
        elif kod[j] == "}":
            derinlik -= 1
            if derinlik == 0:
                return j
    return -1


def ust_seviye_elemanlar(govde: str) -> list[str]:
    """`{a, b, {c, d}, e}` gövdesini ÜST SEVİYE virgüllerden ayırır (iç içe süslüyü sayar)."""
    parcalar, derinlik, son = [], 0, 0
    for i, ch in enumerate(govde):
        if ch in "{[(":
            derinlik += 1
        elif ch in "}])":
            derinlik -= 1
        elif ch == "," and derinlik == 0:
            parcalar.append(govde[son:i])
            son = i + 1
    parcalar.append(govde[son:])
    return [p.strip() for p in parcalar if p.strip() != ""]


#: `<tip> <ad>[NUM_COILS] = {` biçimindeki dosya-kapsamlı dizi tanımları.
DIZI_TANIMI = re.compile(
    r"\b(?:static\s+)?(?:volatile\s+)?(?:const\s+)?(?:static\s+)?(?:volatile\s+)?"
    r"(u?int(?:8|16|32)_t|float|char)\s+(\w+)\s*\[\s*NUM_COILS\s*\]\s*=\s*\{"
)


def num_coils(kod: str) -> int:
    m = re.search(r"#define\s+NUM_COILS\s+(\d+)", kod)
    assert m, "NUM_COILS #define bulunamadi -> kapi BAYAT"
    return int(m.group(1))


def ihlaller(kaynak: str) -> list[tuple[str, int, str]]:
    """NUM_COILS uzunluklu ama eleman sayısı NUM_COILS'e EŞİT OLMAYAN initializer'lar.

    `{0}` MEŞRUDUR: C kalan elemanları sıfırlar ve sayı bilgisi taşımaz → sürüklenemez.
    """
    kod = yorumsuz(kaynak)
    n = num_coils(kod)
    bulunan: list[tuple[str, int, str]] = []
    for m in DIZI_TANIMI.finditer(kod):
        acilis = kod.index("{", m.end() - 1)
        kapanis = _kapanisi_bul(kod, acilis)
        assert kapanis > acilis, f"{m.group(2)} initializer'i ayristirilamadi"
        elemanlar = ust_seviye_elemanlar(kod[acilis + 1 : kapanis])
        if len(elemanlar) == 1 and elemanlar[0] == "0":
            continue  # {0} → tam sıfırlama, sayıdan bağımsız
        if len(elemanlar) != n:
            satir = kod[:acilis].count("\n") + 1
            bulunan.append((m.group(2), satir, f"{len(elemanlar)} eleman / NUM_COILS={n}"))
    return bulunan


def test_KRITIK_elle_yazilmis_bobin_listeleri_NUM_COILS_ile_ayrisMAMIS():
    """Her `[NUM_COILS]` dizisi ya `{0}` ya da TAM NUM_COILS eleman taşımalı.

    MUTASYON: `g_tpp[NUM_COILS] = {0}` yerine `{500, 500, 500, 500, 500}` yaz → KIRMIZI.
    Sahadaki etki: bobin 6-7 tpp=0 ile açılır (50000/0) ve/veya duty asla yükselmez —
    derleyici UYARMAZ, log basılmaz, bobin sessizce sürülmez.
    """
    for p in (FW,):
        if not p.exists():
            continue
        kotu = ihlaller(_oku(p))
        assert not kotu, (
            f"{p.name}: NUM_COILS ile AYRISMIS initializer(lar) — eksik elemanlar SESSIZCE "
            "sifirlanir (derleyici uyarmaz). Sifir diziler `{0}`, sifir-olmayan varsayilanlar "
            "`Coil_StateInit()` dongusunde olmali. Bulunanlar: "
            + "; ".join(f"{ad}@{satir} ({bilgi})" for ad, satir, bilgi in kotu)
        )


def test_KRITIK_g_shadow_da_elle_bobin_listesi_TASIMAZ():
    """`g_shadow` initializer'ı bobin başına bir satır TAŞIMAMALI (aynı sürüklenme sınıfı)."""
    kod = yorumsuz(_oku(FW))
    i = kod.find("CoilParamSet_t g_shadow")
    assert i > 0, "g_shadow tanimi bulunamadi -> kapi BAYAT"
    acilis = kod.index("{", i)
    govde = kod[acilis + 1 : _kapanisi_bul(kod, acilis)]
    assert ".coil" not in govde, (
        "g_shadow hala `.coil = {...}` elle listesi tasiyor -> NUM_COILS artarsa yeni "
        "bobinler freq=0 ile acilir (50000/0). Varsayilanlar Coil_StateInit()'te olmali."
    )


def test_KRITIK_Coil_StateInit_ISR_BASLAMADAN_ONCE_cagriliyor():
    """`Coil_StateInit()` hem VAR olmalı hem de `Coil_TimInit()`ten (ISR) ÖNCE çağrılmalı.

    ⚠️ Sıra kritik: TIM1 ISR'ı başladıktan sonra varsayılan atamak, ISR'ın bir süre
    tpp=0/prev_state=0 ile koşması demektir.
    MUTASYON: `Coil_StateInit();` satırını `Coil_TimInit();`ten SONRAYA taşı → KIRMIZI.
    """
    kod = yorumsuz(_oku(FW))
    assert re.search(r"static void Coil_StateInit\(void\)\s*\{", kod), (
        "Coil_StateInit tanimi YOK -> sifir-olmayan varsayilanlar nereden geliyor?"
    )
    s_cagri = kod.find("Coil_StateInit();")
    t_cagri = kod.find("Coil_TimInit();")
    assert s_cagri > 0, "Coil_StateInit() HIC CAGRILMIYOR -> tpp/slew/prev_state sifir kalir"
    assert t_cagri > 0, "Coil_TimInit() cagrisi bulunamadi -> kapi BAYAT"
    assert s_cagri < t_cagri, (
        "Coil_StateInit(), Coil_TimInit()'ten SONRA cagriliyor -> ISR bir sure tpp=0 ve "
        "prev_state=0 ile kosar (tanimsiz cikis)"
    )
    # Dongu GERCEKTEN NUM_COILS'e bagli mi (sabit 5 yazilmis olmasin)
    govde_bas = kod.index("static void Coil_StateInit(void)")
    acilis = kod.index("{", govde_bas)
    govde = kod[acilis : _kapanisi_bul(kod, acilis) + 1]
    assert "NUM_COILS" in govde, "Coil_StateInit dongusu NUM_COILS'e bagli DEGIL (sabit sayi?)"


def test_KRITIK_ntc_kanal_tablosu_derleme_zamani_IDDIASI_TASIR():
    """Kablolamaya özgü tek elle liste (`g_ntc_kanal`) uzunluğu NUM_COILS'e bağlanmalı.

    Bu liste döngüyle üretilemez (ADC kanal numaraları donanıma özgü) → hem firmware'de
    `_Static_assert` hem burada eleman sayımı. ⚠️ C bu depoda DERLENMEDİĞİ için firmware'deki
    iddia tek başına yeterli değildir.
    """
    kod = yorumsuz(_oku(FW))
    assert "_Static_assert" in kod and "g_ntc_kanal" in kod, "g_ntc_kanal uzunlugu icin derleme-zamani iddiasi YOK"
    i = kod.find("g_ntc_kanal[NUM_COILS]")
    assert i > 0, "g_ntc_kanal tanimi bulunamadi -> kapi BAYAT"
    acilis = kod.index("{", i)
    elemanlar = ust_seviye_elemanlar(kod[acilis + 1 : _kapanisi_bul(kod, acilis)])
    assert len(elemanlar) == num_coils(kod), (
        f"g_ntc_kanal {len(elemanlar)} eleman, NUM_COILS={num_coils(kod)} -> eksik eleman "
        "0 olur ve YANLIS ADC kanali (kanal 0 = PA0) okunur"
    )


def test_KARSIT_KANIT_kapi_gercekten_sayiyor():
    """Öz-test: ayrıştırıcı gerçekten eleman sayıyor mu, yoksa her şeyi mi geçiriyor?

    Kapının kendisi bozuksa (regex hiç eşleşmiyorsa) yukarıdaki testler SESSİZCE yeşil
    kalırdı. Burada bilinen-kötü ve bilinen-iyi girdiler enjekte edilir.
    """
    iyi = "#define NUM_COILS 7U\nstatic volatile uint32_t g_x[NUM_COILS] = {0};\n"
    assert ihlaller(iyi) == [], "kapi MESRU {0} idiyomunu ihlal sandi"

    kotu = "#define NUM_COILS 7U\nstatic volatile uint32_t g_x[NUM_COILS] = {500, 500, 500, 500, 500};\n"
    bulunan = ihlaller(kotu)
    assert bulunan and bulunan[0][0] == "g_x", f"kapi 5-elemanli listeyi YAKALAMADI: {bulunan}"

    tam = "#define NUM_COILS 7U\nstatic uint8_t g_y[NUM_COILS] = {1, 2, 3, 4, 5, 6, 7};\n"
    assert ihlaller(tam) == [], "kapi TAM uzunluktaki listeyi ihlal sandi"

    # YORUM icindeki ornek kapiyi ALDATMAMALI
    yorum = "#define NUM_COILS 7U\n/* ornek: g_z[NUM_COILS] = {1, 2, 3} */\nstatic uint8_t g_z[NUM_COILS] = {0};\n"
    assert ihlaller(yorum) == [], "YORUM icindeki ornek ihlal sayildi -> yorum ayiklama bozuk"

    # IC ICE susluler ust-seviye eleman sayimini bozmamali
    ic = "#define NUM_COILS 2U\nstatic uint8_t g_w[NUM_COILS] = {{1, 9}, {2, 8}};\n"
    assert ihlaller(ic) == [], f"ic-ice suslu eleman sayimi bozuk: {ihlaller(ic)}"
