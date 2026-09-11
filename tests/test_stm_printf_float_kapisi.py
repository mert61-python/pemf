# -*- coding: utf-8 -*-
# Author: mertaygn
"""printf FLOAT DESTEĞİ — STM'in TÜM sensör telemetrisinin bağlı olduğu kapı.

===============================================================================
SAHA ARIZASI 2026-09-11 — kök neden ve neden bu kadar geç bulundu
===============================================================================
BELİRTİ: seans CSV'si bomboş (`# olcum_satiri,0`), seans ne kadar sürerse sürsün.
Arayüzde bobin 6-7 sıcaklığı, manyetik alan ve bobin 1-5 akımı hep "—". Seans
kartındaki yoğunluk reçete değerinde (0 mT) takılı. **Ama bobinler sorunsuz
sürülüyor** ve kart "bağlı" görünüyor.

KÖK NEDEN: firmware `-specs=nano.specs` (newlib-nano) ile bağlanıyor ve newlib-nano'da
`printf` ailesinin **float dönüşümü varsayılan olarak bağlanmaz**. `-u _printf_float`
bayrağı ne `.cproject`te ne derleme betiğinde vardı. `snprintf(..., "%.3f", x)` o
dönüşüm için **hiçbir şey basmaz ve hata da vermez**.

Hatta giden satır:

    -> STM_TELE: C=6,T=,A=,B=,N=412,XN=,XP=,YN=,YP=,ZN=,ZP=

`headless_core._parse_stm_tele` hiçbir sayısal alan eşleştiremeyip `None` döndürdü →
`hardware.stm.telemetry` olayı **hiç yayınlanmadı** → CSV satırı yok, sıcaklık yok,
alan yok, akım yok.

NEDEN GEÇ BULUNDU: ACK (`STM_OK`) **tamsayı** biçimleyicilerle (`Coil_AckSayi`)
kurulduğu için etkilenmedi. Arıza bu yüzden "cihaz çalışıyor ama sensörler bozuk"
gibi göründü ve sensör/kablo/I2C tarafında arandı. Tek bir eksik bağlayıcı ayarı,
ölçüm zincirinin TAMAMINI sessizce kesiyordu.

⚠️ İKİNCİ ZARAR: bobin 6-7'deki tek otomatik termal koruma arayüzdeki 48 °C istemci
interlock'udur (cihaz-taraflı kesme sahip kararıyla YOK) ve o da `T=` alanının
ulaşmasına bağlıdır. Yani bu arıza sürerken o iki bobinde **hiçbir** termal koruma
katmanı çalışmıyordu.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
1. Kaynakta zorlama başvurusu duruyor mu (hızlı, derleyici GEREKTİRMEZ).
2. Derleme betiği bayrağı KENDİ SAĞLAMIYOR mu (sağlarsa kendi bayrağını doğrular,
   sahibin CubeIDE ikilisini ölçmez) ve bağlanan ELF'te sembolü ARIYOR mu.
3. ⚠️ ASIL KAPI: float'sız satırın backend tarafından GERÇEKTEN reddedildiği —
   yani belirtinin kendisi. Bu, düzeltme geri alınırsa hangi davranışın geri
   geleceğini kilitler.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
DERLE = KOK / "scripts" / "firmware_derle.py"


def _oku(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def _c_yorumsuz(kod: str) -> str:
    """C kaynağından `/* … */` ve `//` yorumlarını ÇIKARIR.

    ⚠️ NEDEN GEREKLİ: bu düzeltmenin main.c'deki açıklaması `_printf_float` adını
    defalarca geçiriyor. Düz metin araması yapan bir kapı, KOD silinse bile YEŞİL
    kalır — 2026-09-11 mutasyon turunda bu tam olarak ölçüldü (kapı sahte-yeşildi).
    Satır-başı süzgeci de yetmez: çok satırlı yorumun gövde satırları `*` ile
    başlamak ZORUNDA değildir.
    """
    cikti = []
    i, n = 0, len(kod)
    while i < n:
        if kod.startswith("/*", i):
            son = kod.find("*/", i + 2)
            i = n if son < 0 else son + 2
            cikti.append(" ")
        elif kod.startswith("//", i):
            son = kod.find("\n", i)
            i = n if son < 0 else son
            cikti.append(" ")
        else:
            cikti.append(kod[i])
            i += 1
    return "".join(cikti)


# ============================================================================
# 1. KAYNAK — zorlama başvurusu duruyor mu
# ============================================================================


@pytest.mark.skipif(not MAIN.exists(), reason="firmware kaynagi yok")
def test_KRITIK_main_c_printf_float_SEMBOLUNU_zorluyor():
    """MUTASYON: `g_printf_float_zorla` satırını sil → KIRMIZI.

    Sahadaki etki: sıcaklık + manyetik alan + akım telemetrisi TAMAMEN durur,
    hiçbir hata mesajı çıkmadan.
    """
    kod = _c_yorumsuz(_oku(MAIN))
    # ⚠️ BILDIRIM YETMEZ, BASVURU GEREKIR. `extern int _printf_float(void);` tek basina
    # bagalayiciya HICBIR sey yaptirmaz: sembol yalniz ADI GECMIS olur, tanimi
    # kutuphaneden CEKILMEZ. Bagalayiciyi zorlayan sey ya adresin alinmasi
    # (`&_printf_float`) ya da asm `.global` yonergesidir.
    #
    # ⚠️ Bu ayrimi ilk yazdigim kapi GOREMIYORDU: `extern` satiri yerinde kalinca
    # basvuruyu silen mutasyon YESIL kaldi (2026-09-11 mutasyon turunda olculdu).
    adres_alindi = "&_printf_float" in kod
    asm_global = (".global _printf_float" in kod) or (".globl _printf_float" in kod)
    assert adres_alindi or asm_global, (
        "main.c `_printf_float` sembolune GERCEK BASVURU yapmiyor "
        f"(adres alindi={adres_alindi}, asm .global={asm_global}). "
        "Yalniz `extern` bildirimi ya da yorum YETMEZ -> newlib-nano float printf'i "
        "baglanmaz ve TUM STM_TELE satirlari sayisiz gider (2026-09-11 saha arizasi): "
        "sicaklik, manyetik alan ve akim arayuze BIR DAHA ULASMAZ."
    )


# ============================================================================
# 2. DERLEME KAPISI — bayrağı sağlamaz, ÜRÜNÜ ölçer
# ============================================================================


@pytest.mark.skipif(not DERLE.exists(), reason="derleme betigi yok")
def test_KRITIK_derleme_betigi_bayragi_SAGLAMAZ_urunu_OLCER():
    """⚠️ Betik `-u _printf_float` eklerse KENDİ bayrağını doğrular.

    Sahip CubeIDE'de derliyor; betiğin ölçmesi gereken şey CubeIDE'nin üreteceği
    ikilidir. Bayrağı betiğin kendisi verirse kapı sahte-yeşil olur: betik geçer,
    sahanın flaşladığı ikili yine sensörsüz kalır.

    MUTASYON: betiğe `-u _printf_float` ekle → KIRMIZI.
    """
    betik = _oku(DERLE)
    # ⚠️ YORUM SATIRLARI DUSULUR: bu betigin kendi aciklamasi bayragin adini ANLATIYOR
    # ("... `-u _printf_float` EKLENMEZ ..."). Duz metin aramasi o aciklamayi ihlal sanar
    # ve kapi KENDI BELGESINE takilir — bu depoda daha once yasanmis bir sinif.
    kodsuz = "\n".join(ln for ln in betik.splitlines() if not ln.lstrip().startswith("#"))
    assert '"-u"' not in kodsuz and "-u _printf_float" not in kodsuz, (
        "derleme betigi `-u _printf_float` bayragini KENDI veriyor -> kapi kendi bayragini "
        "dogrular, CubeIDE ikilisini OLCMEZ (sahte yesil)"
    )
    # ⚠️ ÇIPA AST'YE PINLENIR, duz metne DEGIL. Onceki hali `"_printf_float" in betik`
    # diyordu ve kontrolu `if False:` yapan mutasyon YESIL kaliyordu — cunku ad hem
    # yorumlarda hem de hata MESAJINDA geciyor. Simdi gercekten bir `in`/`not in`
    # KARSILASTIRMASI araniyor ve ardindan `return 1` (yani derlemenin DUSMESI).
    import ast

    agac = ast.parse(betik)
    kontrol_var = False
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.If):
            continue
        kaynak_test = ast.dump(dugum.test)
        if "_printf_float" not in kaynak_test:
            continue
        if "NotIn" not in kaynak_test and "In(" not in kaynak_test:
            continue
        # Gövde derlemeyi DÜŞÜRMELİ: yalnız uyarı basmak kapı değildir.
        dusuruyor = any(
            isinstance(g, ast.Return) and isinstance(g.value, ast.Constant) and g.value.value == 1
            for g in ast.walk(dugum)
        )
        if dusuruyor:
            kontrol_var = True
            break
    assert kontrol_var, (
        "derleme betiginde `_printf_float`i ELF'te ARAYAN ve bulamazsa `return 1` ile "
        "derlemeyi DUSUREN bir kontrol YOK -> kapi kosmuyor (yalniz uyari basmak yetmez: "
        "uyari gormeden flaslanan kart sensorsuz kalir)"
    )
    assert "arm-none-eabi-nm" in betik, "sembol kontrolu icin nm cagrilmiyor -> kapi yok"


# ============================================================================
# 3. ⚠️ ASIL KAPI — belirtinin kendisi
# ============================================================================


def _cozumle(satir: str):
    """`_parse_stm_tele`yi GERÇEK desenle çağırır (tam HeadlessCore kurmadan).

    ⚠️ Desen sınıf özniteliğidir; sahte nesneye ELLE bir kopya koymak kapıyı üretimden
    KOPARIRDI (desen değişir, test eski kopyayla yeşil kalır). Üretimdeki nesnenin
    kendisi bağlanır.
    """
    import headless_core

    class _Sahte:
        STM_COIL_COUNT = 7
        _TELE_DESENI = headless_core.HeadlessCore._TELE_DESENI

    return headless_core.HeadlessCore._parse_stm_tele(_Sahte(), satir)


def test_KRITIK_floatSIZ_telemetri_satiri_REDDEDILIR_sessizce_0_URETMEZ():
    """Bozuk firmware'in ürettiği GERÇEK satır — ayrıştırıcı ne yapmalı?

    Doğru davranış REDDETMEKTİR (`None`): alanlar boş geldiğinde 0.0 üretmek,
    CSV'ye ve doz kaydına "0.000 mT ölçüldü" yazardı — bu deponun tekrarlayan
    sahte-ölçüm sınıfı ve bomboş CSV'den çok daha kötüsü.

    MUTASYON: `_parse_stm_tele` sonundaki "hic olcum yok -> None" dalını kaldır →
    KIRMIZI.
    """
    bozuk = "-> STM_TELE: C=6,T=,A=,B=,N=412,XN=,XP=,YN=,YP=,ZN=,ZP="
    assert _cozumle(bozuk) is None, (
        "float'siz satirdan olay URETILDI -> asagi akis bunu 'olculdu' sayar ve 0.0 mT / 0.0 C doz kaydina girer"
    )


def test_KRITIK_saglam_telemetri_satiri_TAM_cozulur():
    """Karşıt kanıt: kapı "her satırı reddet" diyerek geçilemesin.

    Bu satır, düzeltilmiş firmware'in bastığı biçimin birebir aynısıdır.
    """
    saglam = "-> STM_TELE: C=6,T=34.20,A=27.10,B=1.842,N=412,XN=-1.203,XP=1.198,YN=-0.412,YP=0.407,ZN=-1.011,ZP=1.004"
    g = _cozumle(saglam)
    assert g is not None, "saglam satir REDDEDILDI -> ayristirici bicimle uyusmuyor"
    assert g["coil_id"] == 6
    assert g["magnetic_field"] == pytest.approx(1.842)
    assert g["object_temp"] == pytest.approx(34.20)
    assert g["ambient_temp"] == pytest.approx(27.10)
    assert g["magnetic_samples"] == 412
    assert g["mag_x_min"] == pytest.approx(-1.203)
    assert g["mag_z_max"] == pytest.approx(1.004)


def test_KRITIK_akim_satiri_da_floatSIZ_iken_REDDEDILIR():
    """Bobin 1-5 akımı aynı arızadan etkileniyordu (`,I=%.3f`)."""
    assert _cozumle("-> STM_TELE: C=3,I=") is None, "floatsiz akim satiri kabul edildi"
    g = _cozumle("-> STM_TELE: C=3,I=2.417")
    assert g is not None and g["current"] == pytest.approx(2.417)
