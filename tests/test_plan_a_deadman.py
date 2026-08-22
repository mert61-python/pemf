# Author: mertaygn, cglrgrkn
"""PLAN A (HG-5/HG-6) — sahip kararı 2026-08-19: deadman YERİNE üç katman.

Sahibin "PWM ağ koparsa DURMAZ" değişmezini KORUYARAK:
  A-1  SÜRESİZ-MOD MUTLAK TAVANI (firmware, S3+8266): duration=0 modda cihaz-yerel 7200 sn
       son-tarih. Zamana bağlı, ağa DEĞİL → değişmez ihlal edilmez; süreli seans etkilenmez.
  A-2  E-STOP BULUT AYNASI (backend): acil durdurma yerel broker'a EK olarak HiveMQ cloud'a da
       yayınlanır → buluta failover etmiş ESP'ye de ulaşır. Sırlar yoksa sessiz devre dışı.
  A-3  HEDEFLİ RECONCILE (backend): ESP "çalışıyor" raporlar ama backend niyeti/aktif seans
       kapsamıyorsa hedefli STOP. Niyet, tek boğaz noktası _mqtt_publish'te kaydedilir.
       Retained-STOP bilinçli REDDEDİLDİ (meşru seansı da öldürürdü).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import servers.api_server as api

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _temiz_intent():
    def _sifirla():
        with api._esp_intent_lock:
            api._esp_commanded_running.clear()
            api._reconcile_last_stop.clear()
            api._esp_stop_zamani.clear()
        with api._session_lock:
            api._active_session["is_active"] = False
            api._active_session["coil_ids"] = []

    _sifirla()
    yield
    _sifirla()


# ── A-1: firmware süresiz-mod tavanı (yapısal) ─────────────────────────────────


def test_KRITIK_A1_iki_firmware_de_suresiz_tavani_ICERIR():
    for klasor in ("esps3_pemf_coil", "esp8266_pemf_coil"):
        sd = (KOK / "firmware" / klasor / "SharedDefs.h").read_text(encoding="utf-8", errors="replace")
        assert "#define SURESIZ_TAVAN_SEC 7200UL" in sd, f"{klasor}: SURESIZ_TAVAN_SEC yok/değişmiş"
    s3 = (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    e8 = (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    # S3: süresiz dal — !_hasDuration + tavan karşılaştırması + durdurma
    assert "!_hasDuration" in s3 and "SURESIZ_TAVAN_SEC" in s3, "S3 süresiz-tavan dalı yok"
    i = s3.index("SURESIZ_TAVAN_SEC * 1000UL")
    assert "_stopPWM" in s3[i : i + 300], "S3 tavanda durdurmuyor"
    # 8266: _pwmDuration == 0 dalı
    assert "_pwmDuration == 0" in e8 and "SURESIZ_TAVAN_SEC * 1000UL" in e8, "8266 süresiz-tavan dalı yok"
    j = e8.index("SURESIZ_TAVAN_SEC * 1000UL")
    assert "stop()" in e8[j : j + 300], "8266 tavanda durdurmuyor"


def test_A1_tavan_backend_STM_deadline_ile_AYNI():
    """7200 sn = 120 dk — hardware_controller.GOZETIMSIZ_VARSAYILAN_DAKIKA ile parite."""
    import controllers.hardware_controller as hc

    assert hc.GOZETIMSIZ_VARSAYILAN_DAKIKA * 60 == 7200, (
        "STM gözetimsiz varsayılanı değişmiş — firmware SURESIZ_TAVAN_SEC ile hizalayın"
    )


def test_A1_sureli_seans_yolu_wrap_GUVENLI():
    """Süreli dal (duration>0) duruyor VE wrap-güvenli (review: millis ~49,7 günde sarar;
    eski `millis() >= _endTime` hep-açık klinik makinede seansı anında kesebilirdi)."""
    s3 = (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    e8 = (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    # S3: fark tabanlı karşılaştırma; eski mutlak-zaman formu GERİ GELMEMELİ
    assert "_active && _hasDuration && (millis() - _startTime) >= _duration" in s3
    assert "millis() >= _endTime" not in s3.replace("`millis() >= _endTime`", ""), (
        "S3 süreli dal mutlak-zaman karşılaştırmasına dönmüş (wrap'ta seans kesilir)"
    )
    # getState kalan-süre de fark tabanlı
    assert "(_duration > gecen) ? (_duration - gecen)" in s3, "S3 kalan-süre hesabı wrap-güvenli değil"
    assert "_pwmActive && _pwmDuration > 0" in e8
    # 8266'nın değişmez yorumu yerinde (ağ PWM'i etkilemez)
    assert "PWM'i ASLA ETK" in e8, "8266 ağ-bağımsızlık değişmez yorumu kaybolmuş"


def test_KRITIK_A1_tavan_KUMULATIF_crash_loop_delemez():
    """Review: <2 saatte bir çöküp dirilen cihaz (crash-loop) + otomatik resume, tavanı
    fiilen sınırsız yapıyordu. Artık geçen süre NVS/EEPROM'a kümülatif yazılır ve resume
    devralır; yalnız YENİ START komutu (operatör eylemi) pencereyi sıfırlar."""
    s3 = (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    e8 = (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    for ad, src in (("S3", s3), ("8266", e8)):
        assert "_suresizGecenMs" in src, f"{ad}: kümülatif sayaç yok"
    # tavan kontrolü kümülatif toplamla
    assert "(_suresizGecenMs + (millis() - _startTime))" in s3, "S3 tavanı kümülatif değil"
    assert "(_suresizGecenMs + safeMillisDiff(millis(), _pwmStartTime))" in e8, "8266 tavanı kümülatif değil"
    # persist: süresiz modda elapsed kümülatif yazılır
    assert "_suresizGecenMs + (millis() - _startTime))" in s3
    assert "_suresizGecenMs + safeMillisDiff(millis(), _pwmStartTime);" in e8, "8266 savePWMState kümülatif yazmıyor"
    # resume devralır (S3 loadState / 8266 restorePWMState) — 2. tur [1.3]: devralma artık
    # KAYIT ARALIĞI tabanıyla ve S3'te _beginOutput PARAMETRESİYLE (kayıttan ÖNCE) yapılır;
    # ayrıntılı sıra/taban kapıları aşağıdaki A-1 TAMAMLAMASI bölümünde.
    assert "s.elapsedMs + NVS_KAYIT_ARALIGI_MS" in s3, "S3 resume kümülatifi (taban dahil) devralmıyor"
    assert "_suresizGecenMs = (state.duration == 0) ? (state.elapsed + NVS_KAYIT_ARALIGI_MS) : 0" in e8, (
        "8266 resume devralmıyor (taban dahil)"
    )
    # taze START pencereyi sıfırlar (operatör eylemi): ctor sıfırlar; _beginOutput'un devralma
    # parametresi taze çağrılarda VERİLMEZ → varsayılan 0 (başlıktaki default'u ve loadState
    # dışındaki çağrıların argümansızlığını A-1 TAMAMLAMASI kapıları kilitler).
    assert "_suresizGecenMs = 0" in s3, "S3 ctor sıfırlaması yok"
    assert "_suresizGecenMs = devralinanSuresizMs" in s3, "S3 _beginOutput sayaç ataması yok"
    assert e8.count("_suresizGecenMs = 0") >= 2, "8266 taze-start sıfırlaması yok (ctor+start)"


def test_A1_kumulatif_tavan_MODEL():
    """Python modeli: crash-loop'ta (90dk çalış → çök → resume) tavan 2. boot'ta dolar;
    taze START ise pencereyi meşru sıfırlar."""
    TAVAN = 7200_000

    class _Cihaz:
        def __init__(self):
            self.gecen_devir = 0  # _suresizGecenMs
            self.boot_ms = 0

        def calis(self, ms):
            self.boot_ms += ms
            return (self.gecen_devir + self.boot_ms) >= TAVAN  # tavan doldu mu

        def kaydet(self):
            return self.gecen_devir + self.boot_ms  # NVS elapsedMs

        def resume(self, nvs_elapsed):
            self.gecen_devir = nvs_elapsed
            self.boot_ms = 0

        def taze_start(self):
            self.gecen_devir = 0
            self.boot_ms = 0

    c = _Cihaz()
    assert not c.calis(90 * 60_000)  # 90 dk — tavan dolmadı
    nvs = c.kaydet()
    c.resume(nvs)  # çöktü, dirildi
    assert c.calis(31 * 60_000), "crash-loop: 90+31=121 dk kümülatifte tavan DOLMALIYDI"
    c.taze_start()  # operatör yeni start verdi
    assert not c.calis(119 * 60_000), "taze start sonrası pencere sıfırlanmadı"


# ── A-1 TAMAMLAMASI: resume kaydı birikimi SİLMEZ + kayıt-aralığı tabanı ────────
# DENETIM 2. TUR [1.3] (2026-08-20). İki kusur:
#   (a) S3 loadState → _beginOutput içindeki forceSaveState, kümülatif sayaç RAM'e geri
#       yüklenmeden ÖNCE koşuyor ve NVS'e elapsedMs≈0 yazıyordu → resume'dan sonraki 30 sn
#       içinde ikinci bir çökme BİRİKİMİ SİLİYORDU (8266 kardeşi etkilenmiyordu — restore
#       EEPROM'a yazmaz). b7b842c'nin kapattığını iddia ettiği crash-loop deliğinin kendisi.
#   (b) Periyodik kayıt 30 sn'de bir: <30 sn periyotlu çök-diril döngüsünde HİÇBİR boot
#       birikim kaydedemez → tavan sıfırdan başlayan hızlı döngüde HİÇ dolmaz (iki cihazda da).
#       Çözüm: her resume, bir kayıt-aralığı (NVS_KAYIT_ARALIGI_MS) TABAN sayılır ve HEMEN
#       kalıcılaştırılır → kümülatif her çevrimde en az bir aralık büyür; yön FAIL-SAFE
#       (tavan asla geç dolmaz, en fazla resume başına ≤30 sn erken dolar).
#
# ⚠️ Kapılar YORUM-SOYULMUŞ C kaynağında çalışır (bu deponun bilinen dersi: kusuru anlatan
# yorum düzeltme sanılmasın / doğru deseni anlatan yorumla kapı geçilmesin).

import re as _re


def _c_soy(src: str) -> str:
    """C yorumlarını söker (/* */ + //). String içi '//' bu dosyalarda yok — LOG metinleri Türkçe."""
    src = _re.sub(r"/\*.*?\*/", " ", src, flags=_re.S)
    src = _re.sub(r"//[^\n]*", " ", src)
    return src


def _c_govde(soyulmus: str, imza: str) -> str:
    """`imza` ile başlayan fonksiyon gövdesi — bir SONRAKİ üst-düzey tanıma (veya dosya sonuna) kadar."""
    i = soyulmus.index(imza)
    adaylar = [soyulmus.find(p, i + len(imza)) for p in ("\nvoid ", "\nbool ", "\nuint32_t ", "\nstruct ", "\nstatic ")]
    adaylar = [a for a in adaylar if a > 0]
    return soyulmus[i : min(adaylar)] if adaylar else soyulmus[i:]


def test_KRITIK_A1_S3_resume_kaydi_birikimi_SILMEZ():
    """(a) kusurunun kapısı: devralınan birikim _beginOutput'a PARAMETRE olarak girer ki içindeki
    forceSaveState NVS'e 0 değil DOĞRU değeri yazsın; eski 'çağrıdan SONRA RAM'e geri yükle'
    deseni kaynaktan tamamen çıkmış olmalı."""
    s3 = _c_soy(
        (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    )
    h = _c_soy(
        (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.h").read_text(encoding="utf-8", errors="replace")
    )

    # imza: varsayılanı 0 olan devralma parametresi (taze START'lar pencereyi sıfırlamaya devam eder)
    assert _re.search(r"_beginOutput\s*\(\s*unsigned long long \w+\s*,\s*unsigned long \w+\s*=\s*0\s*\)", h), (
        "S3 başlığında _beginOutput devralma parametresi (varsayılan 0) yok — resume birikimi "
        "kayıttan önce devralamaz / taze START sıfırlaması garantisiz"
    )

    bo = _c_govde(s3, "void CoilController::_beginOutput")
    i_atama = bo.find("_suresizGecenMs = devralinanSuresizMs")
    i_kayit = bo.find("forceSaveState()")
    assert i_atama >= 0, "_beginOutput devralınan birikimi sayaca yazmıyor"
    assert 0 <= i_atama < i_kayit, (
        "_beginOutput birikimi kayıttan SONRA yazıyor — forceSaveState NVS'e yine ≈0 yazar, "
        "resume+30sn içindeki ikinci çökme birikimi siler (bulgunun kendisi)"
    )

    ls = _c_govde(s3, "void CoilController::loadState")
    assert _re.search(r"_beginOutput\s*\([^;]*elapsedMs", ls), (
        "loadState devralınan birikimi _beginOutput çağrısına GEÇİRMİYOR"
    )
    assert "_suresizGecenMs = s.elapsedMs" not in ls, (
        "eski desen geri gelmiş: birikim çağrıdan SONRA RAM'e yükleniyor — içerideki kayıt onu NVS'te siler"
    )


def test_KRITIK_A1_resume_TABANI_iki_cihazda_da_kalicilastirilir():
    """(b) kusurunun kapısı: <30 sn periyotlu döngüde hiçbir periyodik kayıt koşamaz → her resume
    bir kayıt-aralığı TABAN sayılıp HEMEN kalıcılaştırılmalı (S3: _beginOutput içindeki
    forceSaveState; 8266: restore sonrası açık savePWMState). Taban sabiti kayıt aralığıyla
    TEK KAYNAK (aralık değişirse taban da değişsin)."""
    for klasor in ("esps3_pemf_coil", "esp8266_pemf_coil"):
        sd = (KOK / "firmware" / klasor / "SharedDefs.h").read_text(encoding="utf-8", errors="replace")
        assert "#define NVS_KAYIT_ARALIGI_MS 30000UL" in sd, f"{klasor}: NVS_KAYIT_ARALIGI_MS sabiti yok"

    s3 = _c_soy(
        (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    )
    e8 = _c_soy(
        (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    )

    # S3: periyodik kayıt + resume tabanı aynı sabitten
    assert _re.search(r"_lastSaveTimeMs\)\s*>=\s*NVS_KAYIT_ARALIGI_MS", s3), (
        "S3 periyodik kayıt sabiti tek-kaynak değil"
    )
    s3_ls = _c_govde(s3, "void CoilController::loadState")
    assert _re.search(r"elapsedMs\s*\+\s*NVS_KAYIT_ARALIGI_MS", s3_ls), (
        "S3 resume tabanı yok — <30 sn periyotlu crash-loop'ta birikim hiç büyümez, tavan dolmaz"
    )

    # 8266: periyodik kayıt + resume tabanı + restore'da KALICILAŞTIRMA (sırası: önce sayaç, sonra kayıt)
    assert _re.search(r"lastEEPROMSave\)\s*>=\s*NVS_KAYIT_ARALIGI_MS", e8), (
        "8266 periyodik kayıt sabiti tek-kaynak değil"
    )
    e8_rs = _c_govde(e8, "bool CoilController::restorePWMState")
    assert _re.search(r"state\.elapsed\s*\+\s*NVS_KAYIT_ARALIGI_MS", e8_rs), "8266 resume tabanı yok"
    i_sayac = e8_rs.find("_suresizGecenMs = ")
    i_kayit = e8_rs.find("savePWMState()")
    assert i_kayit > 0, (
        "8266 restore tabanı KALICILAŞTIRMIYOR (savePWMState yok) — taban yalnız RAM'de kalır, "
        "EEPROM'daki değer büyümez, <30 sn döngüde tavan yine delinir"
    )
    assert 0 <= i_sayac < i_kayit, "8266 restore kaydı sayaç atamasından ÖNCE — 0/bayat değer kalıcılaşır"


def test_KRITIK_A1_resume_kaydi_ve_taban_MODEL_30sn_alti_crash_loop():
    """Ayrıştırıcı model: 20 sn periyotlu çök-diril (periyodik kayıt HİÇ koşamaz).
    ESKİ S3 semantiği (resume kaydı 0 yazar, RAM'e geri yükleme sonra) → birikim her çevrimde
    SİLİNİR, tavan asla dolmaz. YENİ semantik (devralınan + taban, kayıttan önce) → kümülatif
    her çevrimde bir kayıt-aralığı büyür, tavan sınırlı sayıda çevrimde dolar."""
    TAVAN = 7200_000
    ARALIK = 30_000
    CALISMA = 20_000  # < ARALIK → periyodik kayıt hiç koşamaz

    def dongu(resume_semantigi):
        nvs = 0
        for cevrim in range(1, 400):
            # resume: (yeni) devralınan+taban kayıttan önce → NVS büyür; (eski) kayıt 0 yazar
            if resume_semantigi == "yeni":
                devir = nvs + ARALIK
                nvs = devir  # _beginOutput/savePWMState kalıcılaştırdı
            else:  # eski S3
                devir = nvs  # RAM'e sonradan yüklenen değer
                nvs = 0  # _beginOutput içindeki forceSaveState ≈0 yazdı
            if devir + CALISMA >= TAVAN:
                return cevrim  # tavan bu boot'ta doldu → bobin durdu
            # CALISMA ms sonra çökme: bu boot'un süresi hiçbir kayda girmedi
        return None

    yeni = dongu("yeni")
    assert yeni is not None and yeni <= (TAVAN // ARALIK) + 1, (
        f"YENİ semantikte tavan sınırlı çevrimde dolmalıydı (sonuç: {yeni!r})"
    )
    assert dongu("eski") is None, (
        "model ayrıştırmıyor: ESKİ semantik de tavana ulaştı — kapı yanlış şeyi ölçüyor olabilir"
    )


def test_KARSIT_KANIT_A1_taze_start_ve_sureli_resume_DEGISMEDI():
    """Taban yalnız SÜRESİZ resume'a uygulanır; taze START pencereyi sıfırlamaya devam eder
    (operatör eylemi = gözetimli) ve süreli resume'un kalan-süre hesabı büyümez."""
    s3 = _c_soy(
        (KOK / "firmware" / "esps3_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    )
    e8 = _c_soy(
        (KOK / "firmware" / "esp8266_pemf_coil" / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    )

    # S3 ctor sıfırlar; loadState DIŞINDA hiçbir _beginOutput çağrısı devralma argümanı geçirmez
    assert "_suresizGecenMs = 0" in s3, "S3 ctor sıfırlaması kaybolmuş"
    for govde_imza in ("bool CoilController::handleCommand", "void CoilController::process"):
        govde = _c_govde(s3, govde_imza)
        for cagri in _re.findall(r"_beginOutput\s*\(([^;]*)\)\s*;", govde):
            assert "elapsedMs" not in cagri and "NVS_KAYIT_ARALIGI" not in cagri, (
                f"{govde_imza}: taze/zamanlanmış START devralma argümanı geçiriyor — operatör start'ı pencereyi sıfırlamalı"
            )
    # 8266: süresiz-dışı resume'da sayaç 0 kalır (taban yalnız duration==0 dalında)
    e8_rs = _c_govde(e8, "bool CoilController::restorePWMState")
    assert _re.search(
        r"state\.duration\s*==\s*0\s*\)\s*\?\s*\(?state\.elapsed\s*\+\s*NVS_KAYIT_ARALIGI_MS\)?\s*:\s*0", e8_rs
    ), "8266 tabanı süresiz-dışı resume'a da sızmış ya da hiç yok"


# ── A-3: niyet kaydı (tek boğaz noktası) ───────────────────────────────────────


def test_KRITIK_A3_niyet_ASIMETRIK_start_dogrulamali_stop_hemen():
    """F4 (review): START yalnız DOĞRULANMIŞ publish'te True; STOP hemen False + an damgası."""
    # başarısız/doğrulanmamış start niyeti True YAPMAZ (NVS-hayaleti süresiz muaf kalırdı)
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "start", "freq": 10}, basarili=False)
    assert api._esp_commanded_running.get(6) is not True
    # doğrulanmış start → True
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "start", "freq": 10}, basarili=True)
    assert api._esp_commanded_running.get(6) is True
    # stop HEMEN (basarili=False çağrısında) False + F5 an damgası
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "stop"}, basarili=False)
    assert api._esp_commanded_running.get(6) is False
    assert api._esp_stop_zamani.get(6, 0) > 0, "stop anı damgalanmadı (F5 grace penceresi çalışmaz)"
    # kontrol-dışı topic ve start/stop-dışı komutlar niyeti DEĞİŞTİRMEZ; bozuk topic çökertmez
    api._kaydet_esp_komut_niyeti("pemf/coil/6/status", {"command": "start"}, basarili=True)
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "SELFTEST"}, basarili=True)
    assert api._esp_commanded_running.get(6) is False
    api._kaydet_esp_komut_niyeti("pemf/coil/abc/control", {"command": "start"}, basarili=True)


def test_KRITIK_A3_niyet_kayit_sirasi_ve_asimetri_KODDA():
    """Yapısal: STOP kaydı probe'dan ÖNCE (broker kapalıyken bile), START kaydı yalnız
    yayinlandi=True dalında (F4)."""
    import inspect

    src = inspect.getsource(api._mqtt_publish)
    assert "_kaydet_esp_komut_niyeti(topic, payload, basarili=False)" in src
    assert src.index("basarili=False") < src.index("create_connection"), (
        "STOP niyet kaydı broker probe'undan SONRA — broker kapalıyken niyet kaybolur"
    )
    i = src.index("basarili=True")
    assert "yayinlandi" in src[i - 400 : i], "START kaydı doğrulanmış-publish dalında değil"


# ── A-3: hedefli reconcile ─────────────────────────────────────────────────────


def _reconcile_kos(coil_id, snapshot, bekle=1.5):
    """Reconcile'ı koş; arka-plan STOP thread'inin yayınını yakala."""
    yayinlar = []
    bitti = threading.Event()

    def _fake_pub(topic, payload):
        yayinlar.append((topic, payload))
        bitti.set()
        return True

    orijinal = api._mqtt_publish
    api._mqtt_publish = _fake_pub
    api_push = api._push_notification
    api._push_notification = lambda *a, **k: None
    try:
        api._reconcile_esp_calisiyor(coil_id, snapshot)
        bitti.wait(bekle)
    finally:
        api._mqtt_publish = orijinal
        api._push_notification = api_push
    return yayinlar


def test_KRITIK_A3_beklenmedik_calisan_bobine_STOP():
    yayinlar = _reconcile_kos(6, {"running": True})
    assert yayinlar, "reconcile STOP yayınlamadı — hayalet bobin enerjili kalır"
    topic, payload = yayinlar[0]
    assert topic == "pemf/coil/6/control" and payload["command"] == "stop"
    assert payload["command_id"].startswith("reconcile_")


def test_KRITIK_A3_mesru_calisma_DURDURULMAZ():
    # (a) backend start komutladıysa
    with api._esp_intent_lock:
        api._esp_commanded_running[7] = True
    assert not _reconcile_kos(7, {"running": True}, bekle=0.4), "komutlanmış bobini durdurdu (meşru seans katli)"
    # (b) aktif seans kapsıyorsa
    with api._session_lock:
        api._active_session["is_active"] = True
        api._active_session["coil_ids"] = [8]
    assert not _reconcile_kos(8, {"running": True}, bekle=0.4), "seanslı bobini durdurdu"


def test_A3_STM_ve_durmus_bobin_TETIKLEMEZ():
    assert not _reconcile_kos(1, {"running": True}, bekle=0.3), "STM bobinine MQTT reconcile gitti"
    assert not _reconcile_kos(6, {"running": False}, bekle=0.3), "durmuş bobine STOP gitti"


def test_A3_hiz_siniri_30sn():
    assert _reconcile_kos(6, {"running": True})
    assert not _reconcile_kos(6, {"running": True}, bekle=0.4), "30 sn içinde ikinci reconcile-STOP gitti (fırtına)"


def test_KRITIK_A3_F5_stop_sonrasi_grace_penceresi():
    """Normal STOP'tan hemen sonra uçuştaki 'running' status sahte reconcile TETİKLEMEMELİ
    (her normal stop'ta sahte 'güvenlik durdurması' bildirimi = alarm yorgunluğu)."""
    api._kaydet_esp_komut_niyeti("pemf/coil/6/control", {"command": "stop"}, basarili=False)
    assert not _reconcile_kos(6, {"running": True}, bekle=0.4), (
        "stop'tan hemen sonraki bayat 'running' status reconcile tetikledi (grace penceresi yok)"
    )
    # grace penceresi GEÇMİŞSE hayalet yakalanmalı (karşıt-kanıt)
    with api._esp_intent_lock:
        api._esp_stop_zamani[6] = time.monotonic() - 60.0
    assert _reconcile_kos(6, {"running": True}), "grace geçtikten sonra gerçek hayalet yakalanmadı"


def test_KRITIK_A3_F3_publish_oncesi_son_kontrol():
    """Karar ile publish arası pencerede meşru start gelirse reconcile-STOP VAZGEÇMELİ
    (yoksa yeni başlamış tedaviyi sessizce durdurur + stop niyeti start'ı ezer)."""
    yayinlar = []
    bitti = threading.Event()

    def _fake_pub(topic, payload):
        yayinlar.append((topic, payload))
        bitti.set()
        return True

    orijinal_pub = api._mqtt_publish
    orijinal_push = api._push_notification
    # thread spawn'ını yakala: karar verildi ama thread'i BİZ koşturacağız (araya start sokup)
    yakalanan = {}
    orijinal_thread = threading.Thread

    class _GecikmisThread(orijinal_thread):
        def start(self):
            yakalanan["hedef"] = self._target  # koşturma — pencereyi biz kontrol ediyoruz

    api._mqtt_publish = _fake_pub
    api._push_notification = lambda *a, **k: None
    try:
        import unittest.mock as mock

        with mock.patch.object(threading, "Thread", _GecikmisThread):
            api._reconcile_esp_calisiyor(6, {"running": True})
        assert "hedef" in yakalanan, "reconcile karar vermedi (test kurgusu bozuk)"
        # PENCERE: publish'ten önce meşru start geliyor
        with api._esp_intent_lock:
            api._esp_commanded_running[6] = True
        yakalanan["hedef"]()  # _stop_gonder şimdi koşuyor → son-kontrol vazgeçmeli
        assert not yayinlar, "F3 son-kontrol yok: reconcile-STOP meşru yeni tedaviyi durdurdu"
    finally:
        api._mqtt_publish = orijinal_pub
        api._push_notification = orijinal_push


def test_KRITIK_A3_handler_yalniz_CANLI_status_ile_tetikler():
    """Retained status (8266 retain=true yayınlar) reconcile TETİKLEMEMELİ."""
    import inspect

    src = inspect.getsource(api._on_mqtt_message_api)
    i = src.index("_reconcile_esp_calisiyor")
    onceki = src[:i].rsplit("if not is_retained", 1)
    assert len(onceki) == 2 and len(src[:i]) - len(onceki[0]) < 400, (
        "reconcile çağrısı is_retained korumasız — bayat retained 'running' sahte STOP üretir"
    )


# ── A-2: E-stop bulut aynası ───────────────────────────────────────────────────


def test_KRITIK_A2_sirlar_yoksa_ayna_SESSIZ_devre_disi(monkeypatch):
    monkeypatch.setattr("utils.secrets_manager.get_secret", lambda *a, **k: "")
    api._estop_cloud_mirror([6, 7, 8], "test")  # çökmemeli, paho'ya hiç dokunmamalı


def test_KRITIK_A2_F6_GERCEK_get_secret_ATLANDI_yolunu_izler(monkeypatch, caplog):
    """F6 (review): monkeypatch'SİZ gerçek get_secret ile — mqtt_cloud_* _REGISTRY'de TANIMLI
    olmalı ki tanımsız-değer durumunda KeyError değil 'ATLANDI' info yolu izlensin. İlk sürümde
    anahtarlar registry'de yoktu → ilk get_secret KeyError atıyor, dış except yutuyordu → ayna
    ÖLÜ DOĞMUŞTU ve testler monkeypatch yüzünden görmüyordu."""
    import logging as _logging

    from utils import secrets_manager as sm

    # kayıt kapısı: 4 anahtar registry'de
    for k in ("mqtt_cloud_host", "mqtt_cloud_port", "mqtt_cloud_user", "mqtt_cloud_pass"):
        assert k in sm._REGISTRY, f"{k} _REGISTRY'de yok → get_secret KeyError atar, ayna ölü doğar"
    # env fallback'leri temizle (makinede tanımlıysa testi kirletmesin)
    for ev in ("PEMF_MQTT_CLOUD_HOST", "PEMF_MQTT_CLOUD_PORT", "PEMF_MQTT_CLOUD_USER", "PEMF_MQTT_CLOUD_PASS"):
        monkeypatch.delenv(ev, raising=False)
    # 2026-08-19 gece: sahip kararıyla PAKETE GÖMÜLÜ provizyon dosyası eklendi (bkz.
    # test_cloud_provision.py) — build makinesinde GERÇEK değerler yerelde durur. Bu test
    # "sır TANIMSIZ" yolunu sınar → gömülü dosyayı da izole et (yoksa gerçek get_secret
    # gerçek kimliği bulur ve ayna testte GERÇEK buluta bağlanmaya kalkar!).
    monkeypatch.setenv("PEMF_CLOUD_PROVISION_PATH", r"C:\yok\boyle\bir\dosya.json")
    with caplog.at_level(_logging.INFO, logger="servers.api_server"):
        api._estop_cloud_mirror([6], "f6-test")  # GERÇEK get_secret — KeyError atmamalı
    assert any("ATLANDI" in r.message for r in caplog.records), (
        "ayna 'sırlar tanımsız → ATLANDI' info yolunu izlemedi (KeyError'a mı düştü?)"
    )
    assert not any("basarisiz" in r.message.lower() for r in caplog.records), (
        "ayna exception yoluna düştü — sırlar tanımsızken bu sessiz-atlama olmalıydı"
    )


def test_KRITIK_A2_sirlar_varsa_buluta_stop_yayinlar(monkeypatch):
    def fake_secret(key, default="", generate=True):
        assert generate is False, "generate=True → sır dosyasına rastgele değer YAZILIR (yasak)"
        return {
            "mqtt_cloud_host": "ornek.hivemq.cloud",
            "mqtt_cloud_user": "u",
            "mqtt_cloud_pass": "p",
            "mqtt_cloud_port": "8883",
        }.get(key, default)

    monkeypatch.setattr("utils.secrets_manager.get_secret", fake_secret)

    yayinlar = []

    class _Info:
        def wait_for_publish(self, timeout=None):
            pass

        def is_published(self):
            return True

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def username_pw_set(self, u, p):
            pass

        def tls_set(self, *a, **k):
            self.tls = True

        def connect(self, host, port, keepalive=10):
            assert port == 8883 and "hivemq" in host

        def loop_start(self):
            pass

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

        def publish(self, topic, payload, qos=0):
            yayinlar.append((topic, qos))
            return _Info()

    import sys
    import types

    fake_paho = types.ModuleType("paho.mqtt.client")
    fake_paho.Client = _FakeClient
    fake_paho.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
    # `import paho.mqtt.client as _pm` üç seviyeyi de çözümler — hepsini sahtele
    fake_mqtt = types.ModuleType("paho.mqtt")
    fake_mqtt.client = fake_paho
    fake_root = types.ModuleType("paho")
    fake_root.mqtt = fake_mqtt
    monkeypatch.setitem(sys.modules, "paho", fake_root)
    monkeypatch.setitem(sys.modules, "paho.mqtt", fake_mqtt)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", fake_paho)

    api._estop_cloud_mirror([6, 7, 8], "test")
    topikler = [t for t, _ in yayinlar]
    for cid in (6, 7, 8):
        assert f"pemf/coil/{cid}/control" in topikler, f"bobin {cid} bulut STOP'u eksik"
    assert all(q == 1 for _, q in yayinlar), "bulut STOP qos=1 değil"


def test_KARSIT_KANIT_A2_estop_ayna_threadi_KODDA():
    import inspect

    src = inspect.getsource(api)
    assert 'name="estop-cloud-mirror"' in src, "E-stop bulut ayna thread'i düşmüş (HG-5 geri açıldı)"
    i = src.index('name="estop-cloud-mirror"')
    # yerel yoldan ÖNCE başlatılıyor (paralel; yerel yolu bloklamaz)
    assert "_cf.ThreadPoolExecutor" in src[i : i + 800], "ayna, yerel E-stop havuzunun yanında değil"
