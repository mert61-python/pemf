# -*- coding: utf-8 -*-
# Author: mertaygn
"""SANİYELİK **TEPE** MANYETİK ÖLÇÜM — STM32 + ESP-S3 yapısal kapıları.

SAHİP KARARI 2026-09-11:
  "bu bobinler aynı anda açılıp kapanıyor ya bana max değer lazım. yani hepsi aynı anda
   açıkken kaç mT geliyor onu yazdırmalı toplam olarak. bir de okuma hızını maxlayabilirsin
   sensörün kapasitesine göre. sonra saniyede 1 sonuç verir en yükseğini mesela. hem stm hem
   esps3 için bu düzeltmeleri yap."
  "1-10 MT ARASI GENELDE ÖLÇÜMLER OLCAK ONA GÖRE AYARLA 0-5 ARASI AŞIRI FAZLA OLCAK HATTA"

===============================================================================
KORUNAN ÜÇ ARIZA SINIFI
===============================================================================
1. **ANLIK ÖRNEK TESADÜFTÜR.** Bobinler ~1-100 Hz'de birlikte anahtarlanıyor. Saniyede bir
   alınan anlık örnek darbenin neresine denk geldiğine göre 0 ile tam alan arasında herhangi
   bir sayı verir; operatör bunu "yoğunluk düştü" diye okur. Örnekleme darbeden çok daha
   hızlı olmalı ve raporlanan sayı pencerenin **TEPESİ** olmalı.

2. **BAYAT ZİRVE.** Pencerede hiç geçerli örnek yoksa bir önceki pencerenin tepesi
   raporlanamaz. Bayat bir sayıyı "bu saniyenin ölçümü" diye göndermek, ölçülmeyeni 0.0
   göndermekle aynı sınıf yalandır (bu deponun tekrarlayan arızası).

3. **SESSİZ TAŞMA.** RES_16'da MLX90393 19-bit sonucun ALT 16 BİTİNİ verir; aşan değer
   KIRPILMAZ, **SARAR** — büyük alan küçük/negatif okunur ve zirve mantığı o yanlış sayıyı
   "maksimum" diye kilitler. Sarma yazılımdan TESPİT EDİLEMEZ; tek savunma yeterli aralıktır.
   Bu yüzden aralık kapısı (test_stm_sensor_firmware.py) bir bayrağın değil FİZİĞİN kapısıdır.

⚠️ Bu dosya YAPISAL kapıdır — C/C++ bu depoda çalıştırılmaz. Davranışsal karşılığı
`test_seans_alan_kaydi.py` (gerçek Python) ve tezgâh doğrulamasıdır.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
STM = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c"
STM_H = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_sensor.h"
STM_MAIN = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
S3 = KOK / "firmware" / "esps3_pemf_coil" / "SensorManager.cpp"
S3_H = KOK / "firmware" / "esps3_pemf_coil" / "SensorManager.h"
S3_SHARED = KOK / "firmware" / "esps3_pemf_coil" / "SharedDefs.h"
S3_INO = KOK / "firmware" / "esps3_pemf_coil" / "esps3_pemf_coil.ino"

pytestmark = pytest.mark.skipif(not STM.exists() or not S3.exists(), reason="firmware kaynagi yok")


def _oku(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


# ============================================================================
# STM32
# ============================================================================


def test_KRITIK_STM_pencere_TEPEYI_raporlar_ANLIGI_degil():
    """`alan_mt` pencerenin EN BÜYÜĞÜ olmalı; her örnekte üzerine yazılmamalı.

    MUTASYON: `if (mt > h->zirve_mt) { h->zirve_mt = mt; }` → `h->zirve_mt = mt;` → KIRMIZI.
    Sahadaki etki: raporlanan sayı pencerenin SON örneği olur; darbe kapalıyken biten bir
    pencere 0'a yakın bir "yoğunluk" gösterir ve operatör cihazı çalışmıyor sanır.
    """
    kod = _oku(STM)
    m = re.search(r"case S_MAG_OKU:(.*?)\n    h->durum = S_BOSTA;", kod, re.S)
    assert m, "S_MAG_OKU govdesi ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    assert re.search(r"if\s*\(\s*mt\s*>\s*h->zirve_mt\s*\)", govde), (
        "olcum ZIRVE ile KARSILASTIRILMIYOR -> 'max' aslinda 'son ornek' oluyor"
    )
    assert "h->zirve_ornek++" in govde, "ornek sayaci artmiyor -> zirvenin kac ornekten geldigi bilinemez"


def test_KRITIK_STM_ornek_yoksa_BAYAT_ZIRVE_raporlanmaz():
    """Pencerede geçerli örnek yoksa `alan_ok` FALSE olmalı — eski tepe KORUNMAZ.

    MUTASYON: `pencere_kapat`taki `else` dalını sil (zirve_ornek==0 iken alan_ok'a
    dokunulmasın) → KIRMIZI. Sahadaki etki: sensör kablosu çıkınca arayüz son ölçülen
    değeri SONSUZA KADAR "canlı" gösterir; CSV'ye de o sayı yazılır.
    """
    kod = _oku(STM)
    m = re.search(r"static void pencere_kapat\(SensorHat_t \*h, uint32_t simdi_ms\) \{(.*?)\n\}", kod, re.S)
    assert m, "pencere_kapat ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    assert re.search(r"if\s*\(h->zirve_ornek\s*>\s*0U\)", govde), "ornek sayisi KONTROL EDILMIYOR"
    # else dalinda alan_ok KESINLIKLE false olmali
    else_i = govde.find("} else {")
    assert else_i > 0, "ornek YOKKEN dal YOK -> bayat zirve raporlanir"
    else_govde = govde[else_i:]
    assert re.search(r"h->veri\.alan_ok\s*=\s*false", else_govde), (
        "ornek YOKKEN `alan_ok` false yapilmiyor -> bayat zirve 'bu saniyenin olcumu' diye gider"
    )
    # ⚠️ KARSIT-KANIT: bayat zirveyi 0.0 ile DE degistirmemeli (0.0 'olculdu' sayilir).
    assert not re.search(r"h->veri\.alan_mt\s*=\s*0\.0f", else_govde), (
        "olcum yokken alan_mt 0.0 yaziliyor -> asagi akis bunu '0.0 mT olculdu' diye KAYDEDER"
    )


def test_KRITIK_STM_biriktirici_pencere_kapaninca_SIFIRLANIR():
    """Zirve biriktirici sıfırlanmazsa "saniyelik tepe" seans-boyu tepeye dönüşür.

    MUTASYON: `h->zirve_mt = 0.0f;` satırını `pencere_kapat`tan sil → KIRMIZI.
    Sahadaki etki: değer bir kez yükselince bir daha ASLA düşmez; bobin kapatılsa bile
    arayüz eski tepeyi göstermeye devam eder (operatör enerjinin kesildiğini göremez).
    """
    kod = _oku(STM)
    m = re.search(r"static void pencere_kapat\(SensorHat_t \*h, uint32_t simdi_ms\) \{(.*?)\n\}", kod, re.S)
    assert m, "pencere_kapat ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    for alan in ("h->zirve_mt = 0.0f;", "h->zirve_ornek = 0U;", "h->zirve_doygun = false;"):
        assert alan in govde, f"pencere kapanisinda `{alan}` YOK -> saniyelik tepe seans tepesine doner"


def test_KRITIK_STM_manyetik_SUREKLI_ornekleniyor():
    """Manyetik döngü bir saniyelik zamanlayıcıya BAĞLANMAMALI (aksi hâlde 1 Hz'e döner).

    MUTASYON: `S_MAG_OKU` sonunda `h->durum = S_BOSTA;` yerine
    `h->pencere_bitis_ms`i bekleyen bir dal koy → KIRMIZI.
    """
    kod = _oku(STM)
    m = re.search(r"case S_BOSTA:(.*?)case S_TOBJ:", kod, re.S)
    assert m, "S_BOSTA ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    # S_BOSTA, manyetigi ZAMANA degil yalnizca CIHAZ VARLIGINA kapilamali.
    assert re.search(r"if\s*\(h->mag_adres\s*!=\s*0U\)\s*\{\s*\n\s*h->durum\s*=\s*S_MAG_BASLAT;", govde), (
        "S_BOSTA manyetik olcumu dogrudan baslatmiyor -> ornekleme hizi 1 Hz'e duser"
    )
    assert "pencere_bitis_ms" not in govde, (
        "manyetik baslatma ZAMANLAYICIYA kapilanmis -> saniyede tek ornek, zirve TESADUF olur"
    )


def test_KRITIK_STM_bobin_kimligi_TABLODAN_gelir():
    """Tek manyetik sensör (I2C2) arayüzde **bobin 6**'da görünmeli — sahip kararı.

    ⚠️ Aritmetik eşleme (`ILK_BOBIN_ID + sira`) onu bobin 7 diye raporluyordu.
    MUTASYON: main.c'de `PEMF_Sensor_BobinId(si)` → `PEMF_SENSOR_ILK_BOBIN_ID + si` → KIRMIZI.
    """
    hdr = _oku(STM_H)
    m = re.search(r"#define\s+PEMF_SENSOR_BOBIN_IDLERI\s*\{([^}]*)\}", hdr)
    assert m, "PEMF_SENSOR_BOBIN_IDLERI tablosu YOK"
    idler = [int(x.strip().rstrip("Uu")) for x in m.group(1).split(",") if x.strip()]
    assert idler == [6, 6], (
        f"bobin kimlik tablosu {idler} — sahip karari: TEK manyetik sensor (I2C2) arayuzde "
        "BOBIN 6'da gorunmeli, ikisi de 6'ya raporlar"
    )
    ana = _oku(STM_MAIN)
    assert "PEMF_Sensor_BobinId(si)" in ana, "telemetri satiri bobin kimligini TABLODAN almiyor"
    assert "PEMF_Sensor_BobinId(sr)" in ana, "acilis STM_SENS satiri bobin kimligini TABLODAN almiyor"
    # ⚠️ KARSIT-KANIT: eski aritmetik esleme telemetri/rapor yolunda KALMAMALI.
    assert not re.search(r"PEMF_SENSOR_ILK_BOBIN_ID\s*\+\s*s[ir]", ana), (
        "aritmetik esleme HALA kullaniliyor -> manyetik alan yanlis bobinde gorunur"
    )


def test_KRITIK_STM_telemetri_ORNEK_SAYISINI_ve_DOYGUNLUGU_tasir():
    """`N=` ve `S=1` olmadan "zirve tek örnekten mi geldi" ve "değer güvenilir mi" görünmez."""
    ana = _oku(STM_MAIN)
    assert ',B=%.3f,N=%u"' in ana, "telemetri satiri ornek sayisini (N=) TASIMIYOR"
    assert '",S=1"' in ana, "manyetik doygunluk bayragi (S=1) telemetriye YAZILMIYOR"
    # ⚠️ Doygunluk yalniz alan VARKEN basilmali (alan yokken S=1 anlamsizdir).
    i = ana.find(',B=%.3f,N=%u"')
    pencere = ana[i : i + 400]
    assert "sv.alan_doygun" in pencere, "S=1 dali alan blogunun ICINDE degil"


# ============================================================================
# ESP-S3
# ============================================================================


def test_KRITIK_S3_olcek_STM_ile_AYNI():
    """İki kart aynı GAIN'i kullanmalı; yoksa mT sayıları doğrudan kıyaslanamaz.

    ⚠️ ESP-S3 `GAIN_2_5X` kullanıyordu (0.376/0.605 µT/LSB → XY tam ölçek 12,3 mT), STM ise
    `GAIN_SEL=7` (4,92 mT). İkisi de sahibin 1-10 mT bandını PAYLA karşılamıyordu ve
    birbirinin sayısıyla kıyaslanamıyordu. İkisi de `GAIN_5X`/`GAIN_SEL=0`a (±24,6 mT) çekildi.

    MUTASYON: `MLX90393_GAIN_5X` → `MLX90393_GAIN_2_5X` → KIRMIZI.
    """
    kod = _oku(S3)
    assert "MLX90393_GAIN_5X" in kod, (
        "S3 GAIN_5X kullanmiyor -> XY tam olcegi 12,3 mT'de kalir, sahibin bandinin ustu SARAR "
        "ve STM'in sayisiyla KIYASLANAMAZ"
    )
    assert "MLX90393_GAIN_2_5X" not in kod, "eski GAIN_2_5X ayari HALA kaynakta"
    # Hiz: OSR_0 + FILTER_0 (tconv 1,27 ms). Eskisi OSR_1/FILTER_3 = 3,76 ms idi.
    assert "MLX90393_OSR_0" in kod and "MLX90393_FILTER_0" in kod, (
        "S3 en hizli donusum ayarinda DEGIL -> 100 Hz'lik darbede yeterli ornek dusmez"
    )
    # STM'in LSB sabitleriyle AYNI satirdan turedigini belgele (tablo: GAIN_SEL=0 -> 0.751/1.210)
    stm = _oku(STM)
    assert "#define MLX90393_GAIN_SEL 0U" in stm, "STM GAIN_SEL 0 degil -> iki kart AYRI olcekte"


def test_KRITIK_S3_pencere_TEPEYI_mandallar():
    """`pollMagnetic` biriktirir, pencere kapanınca mandallar, biriktiriciyi SIFIRLAR."""
    kod = _oku(S3)
    m = re.search(r"void SensorManager::pollMagnetic\(\) \{(.*?)\n\}", kod, re.S)
    assert m, "pollMagnetic ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    assert re.search(r"if\s*\(buyukluk\s*>\s*_magBirikenZirve\)", govde), (
        "olcum ZIRVE ile KARSILASTIRILMIYOR -> 'max' aslinda 'son ornek'"
    )
    for sifir in ("_magBirikenZirve  = 0.0f;", "_magBirikenOrnek  = 0;"):
        assert sifir in govde, f"pencere kapanisinda `{sifir}` YOK -> saniyelik tepe seans tepesine doner"
    assert "_magZirveMt     = _magBirikenZirve;" in govde, "mandallama YOK"


def test_KRITIK_S3_readAll_I2Cye_DOKUNMAZ():
    """Manyetik I2C sahipliği TEK yerde (`pollMagnetic`) olmalı — iki görev aynı bus'a girmez.

    MUTASYON: `readAll()`in manyetik blokuna `_mlxMag.readMeasurement(...)` geri koy → KIRMIZI.
    Sahadaki etki: ControlTask (Core 1) ve MagneticTask aynı Wire1'e aynı anda girer;
    okuma bozulur, hata sayacı dolar ve sensör "ÇEVRİMDIŞI" ilan edilir.
    """
    kod = _oku(S3)
    m = re.search(r"SensorReadings SensorManager::readAll\(\) \{(.*?)\n    // 3\. Akım", kod, re.S)
    assert m, "readAll manyetik bolumu ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    assert "_mlxMag." not in govde, "readAll HALA MLX90393'e dokunuyor -> ayni Wire1'e iki gorev girer, okuma bozulur"
    assert "_magZirveMt" in govde, "readAll mandallanmis zirveyi OKUMUYOR"
    # Mandal ATOMIK okunmali: bes deger bir kumedir, karisirsa "1 ornekli 8 mT" gibi imkansiz satir cikar.
    assert "portENTER_CRITICAL(&_magMux)" in govde, "mandal korumasiz okunuyor -> degerler AYRI pencerelerden gelebilir"


def test_KRITIK_S3_hizli_gorev_VAR_ve_watchdoga_KAYITLI_DEGIL():
    """Örnekleme ayrı görevde olmalı (ControlTask 5 Hz) ama cihazı YENİDEN BAŞLATMAMALI.

    ⚠️ Kayıtlı sahip kararı: **sensör kopunca restart YOK**. Görev `esp_task_wdt_add` ile
    kaydedilirse, takılan bir I2C sensörü tedavi ortasında cihazı yeniden başlatır.
    """
    ino = _oku(S3_INO)
    assert "void TaskMagnetic(" in ino, "hizli manyetik ornekleme gorevi YOK -> ornekleme 5 Hz'de kalir"
    m = re.search(r"void TaskMagnetic\(void \*pvParameters\) \{(.*?)\n\}", ino, re.S)
    assert m, "TaskMagnetic govdesi ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    assert "esp_task_wdt_add" not in govde, (
        "olcum gorevi watchdog'a KAYITLI -> kopan sensor tedavi ortasinda cihazi YENIDEN BASLATIR "
        "(kayitli sahip karari: sensor kopunca restart YOK)"
    )
    assert "vTaskDelay" in govde, "gorev HER TURDA teslim etmiyor -> ayni cekirdekteki ControlTask ac kalir"
    assert "sysSensors.pollMagnetic()" in govde, "gorev ornekleme cagirmiyor"
    # Oncelik: guvenlik dongusunun ALTINDA olmali.
    shared = _oku(S3_SHARED)
    onc = {ad: int(d) for ad, d in re.findall(r"#define\s+(PRIORITY_\w+)\s+(\d+)", shared)}
    assert onc.get("PRIORITY_MAGNETIC") is not None, "PRIORITY_MAGNETIC tanimli degil"
    assert onc["PRIORITY_MAGNETIC"] < onc["PRIORITY_CONTROL"], (
        f"olcum gorevi onceligi {onc['PRIORITY_MAGNETIC']} >= kontrol {onc['PRIORITY_CONTROL']} — "
        "sensor okumasi ugruna bobin surusu/termal kesme dongusu geciktirilemez"
    )


def test_KRITIK_S3_ilk_tur_SAHTE_HATA_saymaz():
    """Boru hattının ilk turunda bekleyen ölçüm YOKTUR — bu hata DEĞİLDİR.

    ⚠️ 5 Hz'de zararsızdı; ~400 Hz'de sahte hata sayacı her saniye eşiği (5) aşar ve
    ÇALIŞAN sensörü "ÇEVRİMDIŞI" ilan eder.

    MUTASYON: `if ((bekleyenVardi && !readOk) || !baslatildi)` → `if (!readOk)` → KIRMIZI.
    """
    kod = _oku(S3)
    m = re.search(r"void SensorManager::pollMagnetic\(\) \{(.*?)\n\}", kod, re.S)
    assert m, "pollMagnetic ayristirilamadi -> kapi BAYAT"
    govde = m.group(1)
    assert "bekleyenVardi" in govde, (
        "ilk tur ile GERCEK hata ayirt EDILMIYOR -> calisan sensor 'CEVRIMDISI' ilan edilir"
    )
    assert re.search(r"if\s*\(\(bekleyenVardi\s*&&\s*!readOk\)\s*\|\|\s*!baslatildi\)", govde), (
        "hata dali ilk turu HARIC TUTMUYOR"
    )


def test_KRITIK_S3_kurulum_bitmeden_BUSA_DOKUNMAZ():
    """Hızlı görev, `_initI2C()` bitmeden Wire1'e girmemeli (açılış yarışı).

    MUTASYON: `pollMagnetic` başındaki `if (!_i2cHazir) return;` kapısını sil → KIRMIZI.
    Sahadaki etki: görev, kurulumun `delay()`leri sırasında çalışır, `_magOk` false olduğu
    için doğrudan `recoverI2CBus(1)`e girer ve KURULUMLA ÇAKIŞIR — sensör açılışta sessizce ölür.
    """
    kod = _oku(S3)
    m = re.search(r"void SensorManager::pollMagnetic\(\) \{(.*?)const unsigned long simdi", kod, re.S)
    assert m, "pollMagnetic girisi ayristirilamadi -> kapi BAYAT"
    assert "_i2cHazir" in m.group(1), "kurulum-hazir kapisi YOK -> acilis yarisi (bus'a erken dokunma)"
    # Bayrak `_initI2C()` SONUNDA set edilmeli, basinda degil.
    m2 = re.search(r"void SensorManager::_initI2C\(\) \{(.*?)\n\}", kod, re.S)
    assert m2, "_initI2C ayristirilamadi"
    ini = m2.group(1)
    assert "_i2cHazir = true;" in ini, "_i2cHazir `_initI2C` icinde set EDILMIYOR"
    assert ini.index("_i2cHazir = true;") > ini.index("_magNextRetryMs"), (
        "hazir bayragi geri-cekilme damgalari kurulmadan set ediliyor -> ilk turda recoverI2CBus "
        "kosar ve az once basarili olan kurulumu bozar"
    )
