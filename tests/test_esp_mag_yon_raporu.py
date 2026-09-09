# -*- coding: utf-8 -*-
# Author: mertaygn
"""[MAG] BOBİN YÖNÜ RAPORU — 8266 ↔ S3 paritesi (sahip talebi 2026-09-09).

SAHİP TALEBİ: "bu yanlardaki coillerin de yönlerini belirleyelim … esp8266 da seri porta
yazdır s3deki gibi, yönüne bakalım karar verelim."

NEDEN KAPI GEREKİYOR: ölçümün TEK amacı iki kartın sayılarını YAN YANA karşılaştırmak. Biçim
ya da BİRİM ayrışırsa karşılaştırma sessizce anlamsızlaşır — kimse fark etmez, çünkü her iki
kart da "çalışıyor" görünür. Bu, bu depoda ölçülmüş bir hata sınıfı (S3'e eklenen
`_effectiveDutyPct` 8266'ya eklenmemişti → backend gerçek çıkışı sıfır sanıyordu).

⚠️ ASIL BULGU (2026-09-09, bu iş sırasında ölçüldü): `SensorData.magX/magY/magZ` 8266'da
YALNIZCA yapıcıda sıfırlanıyordu — MLX90393 okuması eksenleri `_lastGoodValues` dizisine
yazıp SensorData'ya HİÇ geçirmiyordu. Tüketici olmadığı için (yayınlanan JSON yalnız
`magnetic_field` taşır) kimse görmemişti; yön ölçümü eksen İŞARETİNE dayandığı için bu
alanlar doldurulmadan rapor kalıcı olarak 0 gösterirdi.

C bu makinede DERLENEMEZ → doğrulanabilir = YAPISAL. Yapısal kapı + mutasyon burada tam koşar;
gerçek ölçüm (bobin açık/kapalı, işaretin polariteyi vermesi) tezgâh-ONLY.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
ESP8266 = KOK / "firmware" / "esp8266_pemf_coil"
ESPS3 = KOK / "firmware" / "esps3_pemf_coil"

INO8266 = ESP8266 / "esp8266_pemf_coil.ino"
INOS3 = ESPS3 / "esps3_pemf_coil.ino"
SENSOR8266 = ESP8266 / "SensorManager.cpp"

pytestmark = pytest.mark.skipif(not INO8266.exists(), reason="firmware/ kaynak agaci yok")

#: `LOG_PRINTF("[MAG] …")` biçim dizesini yakalar (iki kartta da aynı olmalı).
_BICIM = re.compile(r'LOG_PRINTF\(\s*"(\[MAG\][^"]*)"')


def _mag_bicimi(yol: Path) -> str:
    soy = c_soy(yol.read_text(encoding="utf-8", errors="replace"))
    m = _BICIM.search(soy)
    assert m, f"{yol.name}: [MAG] LOG_PRINTF bicim dizesi bulunamadi"
    return m.group(1)


def test_KRITIK_8266_MAG_raporu_VAR():
    """8266'da rapor fonksiyonu tanımlı VE loop'tan çağrılıyor olmalı.

    ⚠️ Yalnız tanımın varlığını ölçmek yetmez: çağrılmayan bir fonksiyon derlenir, uyarı bile
    vermez ve seri porta hiçbir şey düşmez (sessiz ölüm).
    """
    soy = c_soy(INO8266.read_text(encoding="utf-8", errors="replace"))
    assert "static void magRaporla(" in soy, "magRaporla tanimi YOK"
    cagrilar = [m.start() for m in re.finditer(r"\bmagRaporla\s*\(", soy)]
    assert len(cagrilar) >= 2, "magRaporla tanimli ama CAGRILMIYOR -> seri porta hicbir sey dusmez"


def test_KRITIK_tanim_CAGRIDAN_ONCE():
    """Tanım çağrıdan önce gelmeli — Arduino'nun otomatik prototip üretimine güvenilmez.

    ⚠️ İlk yazımda blok `loop()`tan SONRAYA konmuştu; `static` fonksiyon + otomatik prototip
    birleşimi kırılgandır, üstelik derleyici hatası ancak sahibin makinesinde görülürdü.
    """
    soy = c_soy(INO8266.read_text(encoding="utf-8", errors="replace"))
    tanim = soy.index("static void magRaporla(")
    cagri = min(m.start() for m in re.finditer(r"\bmagRaporla\s*\(", soy) if m.start() != tanim + len("static void "))
    # Tanımın kendisi de eşleşir; gerçek çağrı `magRaporla(td)` biçimindedir.
    gercek_cagri = soy.index("magRaporla(td)")
    assert tanim < gercek_cagri, (
        f"magRaporla tanimi (offset {tanim}) cagridan (offset {gercek_cagri}) SONRA -> "
        "otomatik prototipe bagli kirilgan derleme"
    )
    assert cagri >= 0


def test_KRITIK_BICIM_S3_ILE_BIREBIR_AYNI():
    """İki kartın `[MAG]` satırı BİREBİR aynı olmalı (alan sırası, hane sayısı, birim).

    Bu testin var olma sebebi: ölçümün amacı karşılaştırma. Birim `mT` yerine `uT` yazılırsa
    ya da alan sırası değişirse sayılar sessizce kıyaslanamaz hale gelir.
    """
    a = _mag_bicimi(INO8266)
    b = _mag_bicimi(INOS3)
    assert a == b, f"[MAG] bicimi AYRISMIS:\n  8266: {a!r}\n  S3  : {b!r}"
    assert "mT" in a, f"birim mT degil: {a!r}"
    for eksen in ("x=%+.3f", "y=%+.3f", "z=%+.3f", "B=%.3f"):
        assert eksen in a, f"{eksen} bicimde YOK: {a!r}"


def test_KRITIK_EKSENLER_SensorData_ya_DOLDURULUYOR():
    """MLX90393 okuması `_data.magX/magY/magZ`'yi YAZMALI (asıl bulgu).

    Doldurulmazsa rapor kalıcı olarak 0,000 gösterir ve yön ASLA okunamaz — üstelik hiçbir
    hata belirtisi olmaz.
    """
    soy = c_soy(SENSOR8266.read_text(encoding="utf-8", errors="replace"))
    okuma = soy.index("_mlxMag.readData(&x, &y, &z)")
    pencere = soy[okuma : okuma + 1200]
    for alan in ("_data.magX", "_data.magY", "_data.magZ"):
        assert alan in pencere, f"{alan} MLX90393 okumasinda YAZILMIYOR -> yon okunamaz"


def test_KRITIK_eksen_BIRIMI_mT():
    """Eksenler mT'ye çevrilmeli: `magneticField` mT, S3'ün `magX`i mT.

    ⚠️ Ham okuma µT'dir. Çevrilmezse `[MAG]` satırı 1000× büyük çıkar ve S3'ün sayılarıyla
    kıyaslanamaz — üstelik "sensör bozuk" gibi görünür.
    """
    soy = c_soy(SENSOR8266.read_text(encoding="utf-8", errors="replace"))
    okuma = soy.index("_mlxMag.readData(&x, &y, &z)")
    pencere = soy[okuma : okuma + 1200]
    for alan, ham in (("_data.magX", "x"), ("_data.magY", "y"), ("_data.magZ", "z")):
        m = re.search(rf"{re.escape(alan)}\s*=\s*([^;]+);", pencere)
        assert m, f"{alan} atamasi bulunamadi"
        ifade = m.group(1)
        assert "1000" in ifade and "/" in ifade, f"{alan} mT'ye cevrilmiyor: {ifade!r}"
        assert ham in ifade, f"{alan} ham {ham} degerinden turemiyor: {ifade!r}"


def test_KRITIK_sensor_YOKKEN_sifir_YAZILMAZ():
    """Sensör kritik durumdayken eksenler NaN olmalı.

    ⚠️ Bayat/0 eksen değeri `[MAG]` satırında GERÇEK ölçüm gibi görünür ve yanlış polarite
    kararına götürür — bu ölçümün tek çıktısı bir işaret olduğu için sessiz ve ikna edici
    bir hata olurdu. Rapor ayrıca `magnetic_sensor_ok` + `isnan` ile kapılanır.
    """
    soy_sensor = c_soy(SENSOR8266.read_text(encoding="utf-8", errors="replace"))
    # ⚠️ ÇIPA `getData()` İÇİNDEKİ DALA PİNLENİR. İlk yazımda `index("_magneticSensorCritical")`
    # kullanılmıştı ve YAPICIDAKİ sıfırlamayı buluyordu → kapı yanlış yere bakıp kırmızı kaldı.
    # Doğru çıpa, `magneticField = NAN` yazan gerçek dal.
    kritik = soy_sensor.index("_data.magneticField = NAN")
    pencere = soy_sensor[kritik : kritik + 400]
    for alan in ("_data.magX = NAN", "_data.magY = NAN", "_data.magZ = NAN"):
        assert alan in pencere, f"kritik durumda {alan} yapilmiyor -> bayat eksen GERCEK gibi gorunur"

    soy_ino = c_soy(INO8266.read_text(encoding="utf-8", errors="replace"))
    fn = soy_ino[soy_ino.index("static void magRaporla(") :]
    fn = fn[: fn.index("\nvoid setup()") if "\nvoid setup()" in fn else 2000]
    assert "magnetic_sensor_ok" in fn, "rapor sensor durumunu KONTROL ETMIYOR"
    assert "isnan(" in fn, "rapor NaN'i AYIKLAMIYOR -> NaN ortalamasi basilir"


def test_README_yon_bolumu_ve_UNIPOLAR_uyarisi():
    """Ölçüm yöntemi belgelenmeli: bipolar sürüşte ortalama ≈ 0 → yön okunamaz.

    Bu uyarı olmadan sahip bipolar sürüşte ölçüm yapıp "yön yok" sonucuna varır (ölçülen
    değer doğrudur, YORUM yanlış olur).
    """
    r = (ESP8266 / "README.md").read_text(encoding="utf-8", errors="replace")
    assert "[MAG]" in r, "README'de [MAG] bolumu YOK"
    assert "unipolar" in r.lower(), "README unipolar sartini soylemiyor"
    assert "1 Hz" in r, "README 8266'nin 1 Hz ornekleme sinirini soylemiyor"
