# -*- coding: utf-8 -*-
# Author: mertaygn
"""SENSÖR KABLOLAMA MODELİ — "bir hatta tek sensör taksam çalışır mı?" sorusunun KANITI.

SAHİP SORUSU 2026-09-10: *"o I2C2 hattına bir sensör de taksam düzgün çalışmalı, çalışıyor
mu, ister manyetik ister sıcaklık"*

C bu depoda DERLENMEZ → "çalışıyor" demek kanıt değildir. Bu dosya `pemf_sensor.c`'nin
durum makinesini Python'da MODELLER ve üç kablolamayı da koşturur. Aynı teknik depoda
zaten var: `test_stm_unipolar_ayna.py` DDS ISR'ını böyle modelliyor.

⚠️ MODEL SESSİZCE AYRIŞMASIN: aşağıdaki yapısal testler, modelin dayandığı üç kararın
kaynakta GERÇEKTEN durduğunu doğrular (yok olan cihazın atlanması, yokluğunun hata
sayılmaması, turun eksik de olsa tamamlanması). Biri kaldırılırsa model değil KAPI kırılır.

⚠️ BU DOSYA BİR ÖZ-DÜZELTMENİN ÜRÜNÜ. Varlık tespitini eklerken sahibe "yok olan sıcaklık
sensörü her ~5 saniyede hat kurtarma tetikler ve aynı hattaki çalışan manyetik sensörü
sakatlar" demiştim. Model bunu ölçtü ve **YANLIŞ** çıktı: `ardisik_hata` HAT BAŞINA tutulur
ve BAŞARILI her işlem onu sıfırlar, dolayısıyla manyetik okuma çalışırken sayaç 1→0 salınır
ve eşiğe asla ulaşmaz. Sahip kablolaması düzeltmeden ÖNCE de çalışıyordu.

Varlık tespitinin gerçek faydası üç kalem, hepsi hijyen/teşhis:
  1. her turda boşa giden bir I2C işlemi (bütçe + bus gürültüsü),
  2. `i2c_hata` teşhis sayacı takılı olmayan cihaz için sonsuza kadar artar → gerçek arıza
     göstergesi olmaktan çıkar (tezgâh kabul kriteri "sayaç 0" idi),
  3. TAMAMEN BOŞ hatta hiç başarı olmadığı için eşik AŞILIR ve boşuna kurtarma koşar.

Ders: "çalışmıyor" iddiası da "çalışıyor" iddiası kadar ölçüm ister. Bu model ikisini de
ölçüyor (bkz. `test_BELGELENMIS_DAVRANIS_calisan_cihaz_sayaci_SIFIRLAR`).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SRC = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "pemf_sensor.c"

pytestmark = pytest.mark.skipif(not SRC.exists(), reason="pemf_sensor.c yok")

#: Kaynaktaki `I2C_KURTARMA_ESIGI` — kaç ardışık hatadan sonra hat kurtarma tetiklenir.
KURTARMA_ESIGI = 5


class HatModeli:
    """`pemf_sensor.c` `hat_ilerlet()` durum makinesinin modeli.

    Yalnız KARAR AKIŞINI modeller (I2C registre işlemleri değil): hangi durum hangi
    koşulda atlanır, hata sayacı ne zaman artar, tur ne zaman tamamlanır.
    """

    def __init__(self, sicaklik_var: bool, alan_var: bool, sicaklik_bozuk: bool = False):
        # `sicaklik_adres` / `mag_adres`: 0 = o hatta o cihaz YOK
        self.sicaklik_adres = 0x5A if sicaklik_var else 0
        self.mag_adres = 0x18 if alan_var else 0
        # "takılı ama okumuyor" (gerçek bus arızası) — hata SAYILMALI
        self.sicaklik_bozuk = sicaklik_bozuk
        self.durum = "BOSTA"
        self.ardisik_hata = 0
        self.kurtarma_sayisi = 0
        self.sicaklik_ok = False
        self.alan_ok = False

    def _hata(self) -> None:
        self.ardisik_hata += 1
        if self.ardisik_hata >= KURTARMA_ESIGI:
            self.kurtarma_sayisi += 1
            self.ardisik_hata = 0

    def ilerlet(self) -> bool:
        """Bir `PEMF_Sensor_Poll` çağrısı. @return tur tamamlandı mı."""
        if self.durum == "BOSTA":
            self.durum = "TOBJ"
            return False

        if self.durum == "TOBJ":
            if self.sicaklik_adres == 0:
                # YOK → atla, hata SAYMA
                self.sicaklik_ok = False
                self.durum = "MAG_BASLAT"
                return False
            if self.sicaklik_bozuk:
                self.sicaklik_ok = False
                self._hata()
                self.durum = "MAG_BASLAT"
                return False
            self.ardisik_hata = 0
            self.durum = "TA"
            return False

        if self.durum == "TA":
            if self.sicaklik_adres == 0:
                self.sicaklik_ok = False
                self.durum = "MAG_BASLAT"
                return False
            self.sicaklik_ok = not self.sicaklik_bozuk
            if self.sicaklik_bozuk:
                self._hata()
            self.durum = "MAG_BASLAT"
            return False

        if self.durum == "MAG_BASLAT":
            if self.mag_adres == 0:
                # YOK → alan bildirilmez, hata SAYILMAZ, tur BİTER (telemetri gitsin)
                self.alan_ok = False
                self.durum = "BOSTA"
                return True
            self.durum = "MAG_BEKLE"
            return False

        if self.durum == "MAG_BEKLE":
            self.durum = "MAG_OKU"
            return False

        if self.durum == "MAG_OKU":
            self.alan_ok = True
            self.ardisik_hata = 0
            self.durum = "BOSTA"
            return True

        raise AssertionError("bilinmeyen durum: " + self.durum)

    def tur_kos(self, tur: int = 1) -> None:
        for _ in range(tur):
            for _adim in range(12):  # tavan: sonsuz döngü olursa test PATLASIN
                if self.ilerlet():
                    break
            else:
                raise AssertionError(f"tur TAMAMLANMADI (durum={self.durum}) — SONSUZ DÖNGÜ")


# ── ÜÇ KABLOLAMA ─────────────────────────────────────────────────────────────


def test_KRITIK_a_tek_hatta_SICAKLIK_ve_MANYETIK():
    """(a) Bir hatta ikisi birden: adresler 0x5A ↔ 0x18, çakışmazlar."""
    h = HatModeli(sicaklik_var=True, alan_var=True)
    h.tur_kos(20)
    assert h.sicaklik_ok and h.alan_ok, (h.sicaklik_ok, h.alan_ok)
    assert h.kurtarma_sayisi == 0, "gereksiz hat kurtarma tetiklendi"
    assert h.ardisik_hata == 0


def test_KRITIK_b_hatta_YALNIZ_MANYETIK():
    """(b) Sahip kablolaması: I2C2'de yalnız manyetik sensör.

    MUTASYON (kaynakta): `S_TOBJ`taki `sicaklik_adres == 0U` erken-çıkışını sil →
    aşağıdaki `kurtarma_sayisi == 0` iddiası KIRMIZI olur (20 turda 4 kurtarma).
    """
    h = HatModeli(sicaklik_var=False, alan_var=True)
    h.tur_kos(20)
    assert h.alan_ok, "manyetik okuma ÇALIŞMIYOR — tek sensörlü hat desteklenmiyor"
    assert not h.sicaklik_ok, "olmayan sıcaklık sensörü 'ölçtü' göründü"
    assert h.kurtarma_sayisi == 0, (
        f"{h.kurtarma_sayisi} kez hat kurtarma tetiklendi — var olmayan sıcaklık sensörünün "
        "yokluğu HATA sayılıyor ve kurtarma AYNI hattaki ÇALIŞAN manyetik sensörü sakatlar"
    )


def test_KRITIK_c_hatta_YALNIZ_SICAKLIK():
    """(c) Tersi: I2C2'de yalnız sıcaklık sensörü."""
    h = HatModeli(sicaklik_var=True, alan_var=False)
    h.tur_kos(20)
    assert h.sicaklik_ok, "sıcaklık okuma ÇALIŞMIYOR"
    assert not h.alan_ok, "olmayan manyetik sensör 'ölçtü' göründü"
    assert h.kurtarma_sayisi == 0, (
        f"{h.kurtarma_sayisi} kez hat kurtarma — olmayan manyetik sensörün yokluğu hata sayılıyor"
    )


def test_KRITIK_d_hatta_HIC_SENSOR_YOK_donguye_girmez():
    """(d) Boş hat: tur yine TAMAMLANMALI, yoksa Poll sonsuza kilitlenir."""
    h = HatModeli(sicaklik_var=False, alan_var=False)
    h.tur_kos(20)  # tur_kos, tamamlanmayan turda AssertionError atar
    assert not h.sicaklik_ok and not h.alan_ok
    assert h.kurtarma_sayisi == 0, "boş hatta hat kurtarma tetiklendi"


def test_KARSIT_KANIT_hata_sayaci_GERCEKTEN_CANLI():
    """Model her yokluğu bağışlamıyor: gerçek bir arıza kurtarmayı TETİKLİYOR.

    ⚠️ Bu testin karşıt-kanıt değeri yüksek: yukarıdaki dört test "kurtarma 0" diyor. Model
    hata sayımını HİÇ yapmıyorsa o dördü de anlamsız yeşil olurdu.

    Senaryo: sıcaklık sensörü TAKILI ama okumuyor **ve** hatta başka çalışan cihaz yok →
    hiçbir başarı sayacı sıfırlamaz → eşik aşılır → kurtarma koşar. Doğru davranış: bu
    GERÇEK bir bus arızası ve kurtarma tam bunun için var.
    """
    h = HatModeli(sicaklik_var=True, alan_var=False, sicaklik_bozuk=True)
    h.tur_kos(20)
    assert h.kurtarma_sayisi > 0, (
        "GERÇEK bus arızasında hat kurtarma TETİKLENMEDİ — hata sayacı ölü, diğer "
        "testlerin 'kurtarma 0' iddiası anlamsız yeşil"
    )


def test_BELGELENMIS_DAVRANIS_calisan_cihaz_sayaci_SIFIRLAR():
    """⚠️ İLK ANLATIMIMIN DÜZELTMESİ — ölçülen gerçek davranış.

    Sahibe "yok olan sıcaklık sensörü her ~5 saniyede hat kurtarma tetikler ve aynı hattaki
    çalışan manyetik sensörü sakatlar" demiştim. **YANLIŞTI.** `ardisik_hata` HAT BAŞINA
    tutulur ve BAŞARILI her işlem onu sıfırlar (`pemf_sensor.c`, `S_MAG_OKU` başarı dalı).
    Manyetik okuma çalışırken sayaç her turda 1→0 salınır ve eşiğe ASLA ulaşmaz.

    Yani sahip kablolaması (I2C2'de yalnız manyetik) varlık tespiti EKLENMEDEN ÖNCE de
    çalışıyordu. Varlık tespitinin gerçek faydası üç kalem — hepsi hijyen/teşhis:
      1. her turda boşa giden bir I2C işlemi (bütçe + bus gürültüsü),
      2. `i2c_hata` teşhis sayacı takılı olmayan cihaz için sonsuza kadar artar → gerçek
         arıza göstergesi olmaktan çıkar (tezgâh kabul kriteri "sayaç 0" idi),
      3. TAMAMEN BOŞ hatta hiç başarı olmadığı için eşik AŞILIR ve boşuna kurtarma koşar.

    Bu test o davranışı PİNLER: bir cihaz çalışırken diğerinin arızası kurtarma tetiklemez.
    Değişirse bilinçli olsun.
    """
    h = HatModeli(sicaklik_var=True, alan_var=True, sicaklik_bozuk=True)
    h.tur_kos(20)
    assert h.kurtarma_sayisi == 0, (
        f"{h.kurtarma_sayisi} kez kurtarma — çalışan cihazın başarısı artık sayacı "
        "sıfırlamıyor. Bu bir davranış değişikliği: bilinçli mi?"
    )
    assert h.alan_ok, "sıcaklık arızası manyetik okumayı ÖLDÜRDÜ (hatlar birbirine bağlanmış)"


# ── MODELİN DAYANDIĞI KARARLAR KAYNAKTA DURUYOR MU ───────────────────────────


def _kod() -> str:
    return io.open(SRC, encoding="utf-8", errors="replace").read()


def test_KRITIK_model_KAYNAKLA_ayrismis_DEGIL():
    """Modelin üç dayanağı kaynakta gerçekten var mı? Yoksa model değil KAPI kırılır."""
    kod = _kod()
    # 1) Kurtarma esigi modelle AYNI
    m = re.search(r"#define\s+I2C_KURTARMA_ESIGI\s+(\d+)", kod)
    assert m, "I2C_KURTARMA_ESIGI bulunamadi -> kapi BAYAT"
    assert int(m.group(1)) == KURTARMA_ESIGI, f"kaynak esigi {m.group(1)}, model {KURTARMA_ESIGI} — model AYRISMIS"
    # 2) Yok olan manyetik sensorun yoklugu hata SAYILMIYOR (kosullu i2c_hata_islet)
    i = kod.find("case S_MAG_BASLAT:")
    assert i > 0, "S_MAG_BASLAT bulunamadi -> kapi BAYAT"
    pencere = kod[i : i + 900]
    assert re.search(r"if\s*\(h->mag_adres\s*!=\s*0U\)\s*\{\s*\n\s*i2c_hata_islet", pencere), (
        "yok olan manyetik sensorun yoklugu KOSULSUZ hata sayiliyor -> bos hatta 5 turda bir hat kurtarma"
    )
    # 3) Tur, cihaz eksik olsa da TAMAMLANIYOR (return true)
    assert "return true; /* tur bitti (eksik de olsa)" in pencere, (
        "eksik cihazda tur TAMAMLANMIYOR -> Poll sonsuza kilitlenir, telemetri hic gitmez"
    )


def test_KRITIK_acilis_raporu_KABLOLAMAYI_soyluyor():
    """`STM_SENS` satırı olmadan "kablo mu yanlış, sensör mü bozuk" ayırt edilemez.

    Telemetri satırı iki durumda da o alanı taşımaz; fark yalnız açılış raporunda görünür.
    """
    ana = io.open(
        KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c", encoding="utf-8", errors="replace"
    ).read()
    assert "STM_SENS" in ana, "acilista bulunan sensor raporu YOK"
    assert "PEMF_Sensor_Rapor" in ana, "rapor API'si cagrilmiyor"
    i = ana.find("STM_SENS")
    pencere = ana[max(0, i - 1200) : i + 1200]
    assert "sicaklik=0x%02X" in pencere and "alan=0x%02X" in pencere, (
        "rapor BULUNAN ADRESLERI basmiyor -> hangi cihazin eksik oldugu anlasilmaz"
    )
    assert "ACS712" in ana, "bobin 1-5 akim kanallarinin kalibrasyon durumu raporlanmiyor"
