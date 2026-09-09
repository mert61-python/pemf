# -*- coding: utf-8 -*-
# Author: mertaygn
"""[BKAYIT] PWM-KAPILI B KAYDI — firmware + seri toplayıcı kapısı (sahip 2026-09-09).

SAHİP İSTEĞİ: "manyetik alan değerleriyle zamanı, sadece, başka yok — 2 tane toplam: B değeri
ve zaman. PWM üretmeye başlayınca kayıt başlasın, bitince dursun. Masaüstüne kaydetsin."

İKİ PARÇA: kart (`esps3_pemf_coil.ino::bKaydiRaporla`) seri porta ayrıştırılabilir satır basar;
`scripts/b_kaydi_topla.py` her oturumu masaüstünde ayrı CSV'ye yazar. S3 bir mikrodenetleyici —
PC dosya sistemine erişemez, o yüzden iş bölünmek ZORUNDA.

⚠️ TEST GİRDİLERİ GERÇEK: aşağıdaki gürültü satırları (`[MAG]`, `[MQTT]`, `[Sensör]`, açılış
günlüğü) 2026-09-09'da S3'ün COM3 portundan YAKALANDI. Uydurma girdi, önek filtresinin gerçek
gürültüyü ayıklayıp ayıklamadığını gizlerdi — CSV o satırlarla dolar ve kimse fark etmez.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
INO = KOK / "firmware" / "esps3_pemf_coil" / "esps3_pemf_coil.ino"
sys.path.insert(0, str(KOK / "scripts"))

from b_kaydi_topla import Toplayici, dosya_adi, saat_metni, satiri_coz  # noqa: E402

#: 2026-09-09, COM3'ten yakalanan GERÇEK gürültü — CSV'ye ASLA girmemeli.
GERCEK_GURULTU = [
    "[MAG] x=+0.004 y=+0.009 z=-0.009 B=0.013 mT",
    "[MQTT] Status -> Bobin: 0.0°C, Ortam: 0.0°C",
    "[Sensör] Bobin: 0.0°C, Ortam: 0.0°C, Mag: 0.01 mT, Akım: -37.49A",
    "[DDS] 100Hz duty%25 faz0 -> tpp=500 duty_t=125 faz_t=0 (efektif %25)",
    "[PWM] BASLADI: 100Hz duty%25 faz0 sure=1200sn (efektif duty%25)",
    "[Stack] ControlTask min free stack: 13568 bytes",
    "ESP-ROM:esp32s3-20210327",
    "",
]


# ══ 1) AYRIŞTIRICI (saf) ═══════════════════════════════════════════════════════════════════
def test_KRITIK_gercek_GURULTU_yok_sayiliyor():
    """`[BKAYIT]` öneki olmayan hiçbir satır olaya çevrilmemeli.

    ⚠️ Aynı porta açılış günlüğü + [MAG] + [MQTT] + [Sensör] akıyor. Önek filtresi olmadan
    CSV bu satırlarla dolar; dosya "çalışıyor" görünür ama içi çöp olur.
    """
    for s in GERCEK_GURULTU:
        assert satiri_coz(s) is None, f"gurultu olaya cevrildi: {s!r}"


def test_BASLA_satiri_cozuluyor():
    olay = satiri_coz("[BKAYIT] BASLA coil=8 freq=100 duty=25 saat=epoch ts=1788965123456")
    assert olay is not None
    tur, a = olay
    assert tur == "basla"
    assert (a["bobin"], a["freq"], a["duty"], a["saat"], a["ts"]) == (8, 100, 25, "epoch", 1788965123456)


def test_KRITIK_VERI_satiri_TAM_IKI_KOLON():
    """Veri satırı yalnız zaman + B taşımalı — sahip şartı "başka yok"."""
    olay = satiri_coz("[BKAYIT] 1788965123656,0.0198")
    assert olay is not None
    tur, a = olay
    assert tur == "veri"
    assert set(a) == {"zaman_ms", "b_mT"}, f"fazla/eksik alan: {sorted(a)}"
    assert a["zaman_ms"] == "1788965123656" and a["b_mT"] == "0.0198"


def test_negatif_ve_uptime_damgasi_da_cozuluyor():
    """NTP yoksa damga uptime'dır; B teorik olarak negatif gelmez ama ayrıştırıcı kırılmamalı."""
    assert satiri_coz("[BKAYIT] 29278,0.0000")[1]["b_mT"] == "0.0000"
    assert satiri_coz("[BKAYIT] 5,-0.5")[1]["b_mT"] == "-0.5"


def test_BITTI_satiri_ve_ATLANAN_sayisi():
    tur, a = satiri_coz("[BKAYIT] BITTI ornek=1024 atlanan=3 sure_ms=205000")
    assert tur == "bitti"
    assert (a["ornek"], a["atlanan"], a["sure_ms"]) == (1024, 3, 205000)


def test_bozuk_BKAYIT_satiri_YOK_SAYILIR():
    """Yarım/bozuk satır (seri gürültüsü, kesik yazım) CSV'ye girmemeli."""
    for s in ("[BKAYIT] BASLA coil=8", "[BKAYIT] abc,def", "[BKAYIT] 123", "[BKAYIT]"):
        assert satiri_coz(s) is None, f"bozuk satir kabul edildi: {s!r}"


# ══ 2) TOPLAYICI — oturum yönetimi ve DOSYA ════════════════════════════════════════════════
def test_KRITIK_PWM_OTURUMU_dosyaya_yaziliyor(tmp_path):
    """BASLA → dosya aç + başlık; veri → satır; BITTI → kapat. Gürültü hiç girmemeli."""
    t = Toplayici(tmp_path)
    akis = [
        "ESP-ROM:esp32s3-20210327",
        "[BKAYIT] BASLA coil=8 freq=100 duty=25 saat=epoch ts=1000",
        "[MAG] x=+0.004 y=+0.009 z=-0.009 B=0.013 mT",
        "[BKAYIT] 1200,0.0198",
        "[MQTT] Status -> Bobin: 0.0°C, Ortam: 0.0°C",
        "[BKAYIT] 1400,0.0203",
        "[BKAYIT] BITTI ornek=2 atlanan=0 sure_ms=400",
    ]
    for s in akis:
        t.isle(s)
    t.kapat()

    dosyalar = list(tmp_path.glob("*.csv"))
    assert len(dosyalar) == 1, dosyalar
    satirlar = dosyalar[0].read_text(encoding="utf-8").strip().splitlines()
    assert satirlar[0] == "saat,b_mT", satirlar[0]
    assert len(satirlar) == 3, satirlar
    for s in satirlar[1:]:
        p = s.split(",")
        assert len(p) == 2, f"satir 2 kolon degil: {s!r}"
        # Saat kolonu HH.MM.SS.mmm biçiminde (sahip örneği: 18.02.56)
        assert re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{3}", p[0]), f"saat bicimi bozuk: {p[0]!r}"
    assert [s.split(",")[1] for s in satirlar[1:]] == ["0.0198", "0.0203"]


def test_KRITIK_HER_PWM_OTURUMU_AYRI_dosya(tmp_path):
    """İki start/stop → iki dosya. Aynı dosyaya eklemek oturumları birbirine karıştırırdı.

    ⚠️ BU TEST GERÇEK BİR HATA YAKALADI (2026-09-09): bobin/frekans/duty adan kaldırılınca ad
    yalnız saniye çözünürlüklü damga taşıdı; aynı saniyedeki iki oturum AYNI adı üretiyor ve
    `open(..., "w")` ilkini SESSİZCE siliyordu. Toplayıcı artık `_2`, `_3`… ekliyor. Bu test
    iki oturumu aynı saniyede açtığı için o korumayı da ölçer.
    """
    t = Toplayici(tmp_path)
    for i in (1, 2):
        t.isle(f"[BKAYIT] BASLA coil=8 freq={100 * i} duty=25 saat=epoch ts={i}")
        t.isle(f"[BKAYIT] {i}00,0.01{i}")
        t.isle("[BKAYIT] BITTI ornek=1 atlanan=0 sure_ms=200")
    t.kapat()
    dosyalar = sorted(tmp_path.glob("*.csv"))
    assert len(dosyalar) == 2, dosyalar
    for d in dosyalar:
        assert len(d.read_text(encoding="utf-8").strip().splitlines()) == 2  # baslik + 1 satir


def test_oturum_ORTASINDA_baslatilinca_veri_KAYBOLMAZ(tmp_path):
    """Betik PWM sürerken açılırsa BASLA görülmez — veri yine kaydedilmeli."""
    t = Toplayici(tmp_path)
    t.isle("[BKAYIT] 500,0.0150")
    t.isle("[BKAYIT] 700,0.0160")
    t.kapat()
    dosyalar = list(tmp_path.glob("*.csv"))
    assert len(dosyalar) == 1
    assert "oturum-ortasi" in dosyalar[0].name, dosyalar[0].name
    assert len(dosyalar[0].read_text(encoding="utf-8").strip().splitlines()) == 3


def test_KRITIK_dosya_adi_SADE_bobin_freq_duty_YOK():
    """Sahip kararı (2026-09-09): "bobin 8'i de kaldır, duty frekans kaldır, sadece zaman ve mT".

    Ne kolonda ne ADDA bobin/frekans/duty bulunmalı.
    """
    ad = dosya_adi({"bobin": 8, "freq": 100, "duty": 25, "saat": "epoch", "ts": 1})
    for yasak in ("bobin", "Hz", "duty", "epoch"):
        assert yasak not in ad, f"'{yasak}' dosya adinda KALMIS: {ad}"
    assert ad.startswith("pemf_b_") and ad.endswith(".csv"), ad


def test_KRITIK_SAAT_bicimi_ve_MILISANIYE():
    """Saat kolonu `18.02.56.123` biçiminde olmalı (sahip örneği + ms).

    ⚠️ MİLİSANİYE ZORUNLU: örnekleme 5 Hz — saniye çözünürlüğünde beş satır AYNI görünür ve
    zamanlama analizi (aralık, kayma, atlanan örnek) imkânsızlaşır.
    """
    m = saat_metni("1788965924103", "epoch")
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{3}", m), m
    assert m.endswith(".103"), f"kartin ms'i korunmuyor: {m}"


def test_KRITIK_epoch_KARTIN_damgasini_kullanir():
    """NTP varken kartın kendi damgası çevrilmeli, PC'nin varış anı DEĞİL.

    ⚠️ Ölçülen şey kartın zamanlamasıdır; PC varış anını kullanmak seri port ve işletim
    sistemi gecikmesini veriye karıştırır (5 Hz'de bu gecikme örnek aralığıyla aynı mertebede).
    """
    a = saat_metni("1788965924103", "epoch")
    b = saat_metni("1788965924303", "epoch")
    assert a != b, "iki farkli kart damgasi ayni saate cevrildi -> PC saati kullaniliyor"
    assert a.endswith(".103") and b.endswith(".303")


def test_uptime_PC_saatine_duser_ve_COKMEZ():
    """NTP yoksa damga saate çevrilemez → PC saati kullanılır; bozuk girdi de çökertmez."""
    for ham, tur in (("65285", "uptime"), ("abc", "epoch"), ("", None), ("99999999999999999999", "epoch")):
        m = saat_metni(ham, tur)
        assert re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{3}", m), (ham, tur, m)


def test_KRITIK_NTP_YOKSA_uptime_eki_KALIYOR():
    """Tek istisna: NTP oturmamışsa `_uptime` eki adda kalmalı.

    ⚠️ O ek olmadan damgalar epoch sanılır ve dosya 1970 tarihleriyle dolu görünür; sebebi
    hiçbir yerde yazmaz. Ölçümü sessizce çöpe çeviren tek bilgi budur — sadelik uğruna
    atılamaz. Normal (NTP'li) koşuda hiçbir ek YOK (üstteki test).
    """
    ad = dosya_adi({"bobin": 8, "freq": 100, "duty": 25, "saat": "uptime", "ts": 1})
    assert "_uptime" in ad, f"NTP yokken uyari eki DUSMUS: {ad}"


# ══ 3) FIRMWARE TARAFI (yapısal — C burada derlenemez) ═════════════════════════════════════
firmware_yok = pytest.mark.skipif(not INO.exists(), reason="firmware/ agaci yok")


@firmware_yok
def test_KRITIK_firmware_PWM_KENARLARINA_bagli():
    """Kayıt PWM yükselen kenarda başlamalı, düşen kenarda bitmeli (sahip şartı).

    Sürekli yazan bir sürüm testte "çalışıyor" görünür ama PWM kapalıyken de dosya doldurur.
    """
    k = INO.read_text(encoding="utf-8", errors="replace")
    i = k.index("static void bKaydiRaporla")
    govde = k[i : i + 2200]
    assert "pwm.active && !oncekiAktif" in govde, "BASLA yukselen kenara bagli DEGIL"
    assert "!pwm.active && oncekiAktif" in govde, "BITTI dusen kenara bagli DEGIL"
    assert "oncekiAktif = pwm.active" in govde, "kenar durumu guncellenmiyor"


@firmware_yok
def test_KRITIK_firmware_VERI_satiri_IKI_ALAN():
    """Kartın bastığı veri satırı tam iki alan olmalı — biçim sözleşmesi."""
    k = INO.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'LOG_PRINTF\("\[BKAYIT\] (%llu,%\.\d+f)\\n"', k)
    assert m, "veri satiri bicimi bulunamadi/degismis"
    assert m.group(1).count(",") == 1, f"iki alandan fazla: {m.group(1)}"


@firmware_yok
def test_KRITIK_firmware_sensor_YOKKEN_SIFIR_YAZMIYOR():
    """Sensör okunamayan örnek ATLANMALI, `0` yazılmamalı.

    ⚠️ `0,0000 mT` ölçülmüş bir değer gibi görünür ve alan analizinde GERÇEK bir sonuçtur.
    Atlananlar sayılıp BITTI satırında raporlanır → kayıp görünür kalır.
    """
    k = INO.read_text(encoding="utf-8", errors="replace")
    i = k.index("static void bKaydiRaporla")
    govde = k[i : i + 2200]
    assert "r.magSensorOk" in govde, "sensor durumu KONTROL EDILMIYOR"
    assert "atlanan++" in govde, "atlanan ornek SAYILMIYOR"
    assert "atlanan=%u" in govde, "atlanan sayisi BITTI satirinda raporlanmiyor"


@firmware_yok
def test_KRITIK_firmware_CAGRILIYOR_ve_saat_turu_bildiriliyor():
    """Fonksiyon kontrol döngüsünden çağrılmalı; saat türü BASLA'da bildirilmeli.

    ⚠️ `saat=` olmadan NTP oturmamış bir koşunun damgaları uptime'dır ve masaüstündeki CSV
    1970 tarihleriyle dolar — sebebi hiçbir yerde yazmaz.
    """
    k = INO.read_text(encoding="utf-8", errors="replace")
    assert k.count("bKaydiRaporla") >= 2, "tanimli ama CAGRILMIYOR -> seri porta hicbir sey dusmez"
    assert k.index("static void bKaydiRaporla") < k.index("bKaydiRaporla(readings"), (
        "tanim cagridan SONRA -> otomatik prototipe bagli kirilgan derleme"
    )
    assert "saat=%s" in k, "saat turu (epoch/uptime) BASLA satirinda bildirilmiyor"
    assert "#include <sys/time.h>" in k, "gettimeofday icin sys/time.h include EDILMEMIS"
