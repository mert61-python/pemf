# -*- coding: utf-8 -*-
# Author: mertaygn
"""SENSÖR TELEMETRİSİ YEREL KAYIT — sürekli çalışan CSV kaydedici (sahip kararı 2026-09-09).

SAHİP KARARI: veri **bilgisayar tarafında** dursun ve kayıt **her zaman açık** olsun.

NEREYE BAĞLANIYOR: backend zaten `pemf/coil/+/sensors` ve `pemf/coil/+/status` konularına
ABONE (`api_server.py:605-606`) ve her mesajı `_live_state`e işliyor. Kaydedici tam o noktaya
takılır — YENİ ABONELİK YOK, ekstra ağ yükü YOK, cihaz tarafında değişiklik gerekmez.

⚠️ NEDEN HASTA VERİTABANINA YAZMIYOR: `services/headless_db_maintenance` hasta/seans DB'sine
retention + PII-maskeleme + **yedekleme** uyguluyor. Ölçülen telemetri hacmi 3 bobin × 1 Hz
≈ 3 satır/sn ≈ **16 MB/gün**; bunu o DB'ye dökmek her açılış yedeğini şişirir ve tıbbi kaydın
yedekleme/geri-yükleme süresini bozar. Araştırma telemetrisi AYRI bir klasörde, düz CSV olarak
durur — Excel/Python ile doğrudan açılır, yedek zincirine hiç girmez.

⚠️ NEDEN DÜZ CSV: veri araştırma amaçlı (bobin yönü/polarite ölçümü, alan büyüklüğü). Düz metin
grep'lenir, Excel'e sürüklenir, `pandas.read_csv` ile okunur; ayrı bir SQLite dosyası sorgu
kolaylığı katardı ama analiz zincirine engel bir katman eklerdi.

⚠️ DİSK DOLMASI YAPISAL OLARAK ENGELLİ: günlük döndürme + gün sayısı sınırı + TOPLAM BOYUT
tavanı. "Her zaman açık" kaydın en gerçek riski budur; tavan olmadan klinik makinesinin diski
sessizce dolar (ve `headless_db_maintenance`in disk kontrolü tıbbi kaydı korumaya çalışırken
telemetri yüzünden alarm verirdi).

⚠️ MQTT YOLUNA ASLA HATA SIZDIRMAZ: bu modüldeki her giriş noktası geniş `except` ile sarılı.
Telemetri kaydı bir KOLAYLIKTIR; bir dosya kilidi ya da dolu disk yüzünden canlı durum
güncellemesinin, panelin ya da E-stop görünürlüğünün bozulması kabul edilemez.

KAPATMA: `PEMF_SENSOR_LOG=0`. Ayarlar: `PEMF_SENSOR_LOG_DAYS` (varsayılan 14),
`PEMF_SENSOR_LOG_MB` (varsayılan 500), `PEMF_SENSOR_LOG_DIR` (varsayılan veri kökü/sensor_log).
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from utils.akim_olcumu import akimsiz
from utils.dongu_guvenligi import dongu_hatasini_bildir

logger = logging.getLogger(__name__)

#: CSV sütunları — SIRA SÖZLEŞMEDİR (mevcut dosyalara yeni sütun eklenirse başlık değişir ve
#: eski dosyalar ayrı kalır; bu yüzden başlık her dosyanın İLK satırına yazılır).
#: `mag_x/mag_y/mag_z`: bobin YÖNÜ (polarite) ölçümünün taşıyıcısı — skaler `magnetic_field`
#: yön taşımaz. ⚠️ Firmware bunları yayınlamıyorsa sütunlar BOŞ kalır (sessizce sıfır DEĞİL,
#: boş — "ölçülmedi" ile "sıfır ölçüldü" karıştırılmasın).
SUTUNLAR: tuple[str, ...] = (
    "ts_yerel",  # ISO 8601, yerel saat (analiz kolaylığı)
    "ts_epoch_ms",  # kaydedicinin damgası (tek saat referansı)
    "cihaz_ts_ms",  # cihazın kendi damgası (NTP'liyse epoch, değilse uptime)
    "bobin",
    "msg_type",
    "fw",
    "temp_object",
    "temp_ambient",
    "magnetic_field",
    "mag_x",
    "mag_y",
    "mag_z",
    "current",
    "max_magnetic_field",
    "max_current",
    "pwm_active",
    "pwm_frequency",
    "pwm_duty",
    "sensors_ok",
    "temp_sensor_ok",
    "magnetic_sensor_ok",
    "current_sensor_ok",
    "uptime_ms",
    "wifi_rssi",
    # ⚠️ D2.39 (B-1.12): STM telemetrisinin (`STM_TELE` → `hardware.stm.telemetry`) İŞARETLİ eksen uçları — saniyelik pencerenin
    # min/max'ı (mT). `magnetic_field` büyüklüktür, unipolar ile bipolari AYNI gösterir; bipolar / faz kazancını YALNIZ bunlar taşır.
    # SONA eklendi (sıra sözleşmesi): o gün eski başlıkla açılmış dosyaya yazılmaz, yeni dosya açılır (`_dosyayi_hazirla`).
    "mag_x_min",
    "mag_x_max",
    "mag_y_min",
    "mag_y_max",
    "mag_z_min",
    "mag_z_max",
    "current_saturated",
    "magnetic_saturated",
)

#: Yük anahtarı → CSV sütunu. İki firmware ailesi farklı adlar kullanıyor (8266
#: `pwm_duty_cycle`, S3 `pwm_duty`); ikisi de aynı sütuna düşer.
_ESLEME: dict[str, str] = {
    "timestamp": "cihaz_ts_ms",
    "fw_version": "fw",
    "object_temp": "temp_object",
    "ambient_temp": "temp_ambient",
    "magnetic_field": "magnetic_field",
    "mag_x": "mag_x",
    "mag_y": "mag_y",
    "mag_z": "mag_z",
    "current": "current",
    "max_magnetic_field": "max_magnetic_field",
    "max_current": "max_current",
    "pwm_active": "pwm_active",
    "pwm_frequency": "pwm_frequency",
    "pwm_duty": "pwm_duty",
    "pwm_duty_cycle": "pwm_duty",
    "sensors_ok": "sensors_ok",
    "temp_sensor_ok": "temp_sensor_ok",
    "magnetic_sensor_ok": "magnetic_sensor_ok",
    "current_sensor_ok": "current_sensor_ok",
    "uptime": "uptime_ms",
    "wifi_rssi": "wifi_rssi",
    # D2.39: STM telemetri alanları (adlar `headless_core._parse_stm_tele` ile birebir; skalerler yukarıdaki eşlemeyle ortak).
    "mag_x_min": "mag_x_min",
    "mag_x_max": "mag_x_max",
    "mag_y_min": "mag_y_min",
    "mag_y_max": "mag_y_max",
    "mag_z_min": "mag_z_min",
    "mag_z_max": "mag_z_max",
    "current_saturated": "current_saturated",
    "magnetic_saturated": "magnetic_saturated",
}

#: Sensör alanı taşıyan mesaj tipleri. ⚠️ `status` DA LİSTEDE: S3 hiç `sensors` yayınlamaz
#: (UYUMSUZ-6) ve sensör değerlerini `status` içine koyar — telde ölçüldü. Yalnız `sensors`
#: dinleyen bir kaydedici, S3 bobinleri için BOŞ dosya üretirdi.
KAYDEDILEN_TIPLER = ("sensors", "status")

_FLUSH_ARALIGI_SN = 2.0
_VARSAYILAN_GUN = 14
_VARSAYILAN_MB = 500


def _acik_mi() -> bool:
    return os.environ.get("PEMF_SENSOR_LOG", "1").strip().lower() not in ("0", "false", "no", "off")


def _sayi(deger: str, varsayilan: int) -> int:
    try:
        d = int(float(str(deger).strip()))
        return d if d > 0 else varsayilan
    except (TypeError, ValueError):
        return varsayilan


def _kayit_dizini() -> Path:
    ozel = os.environ.get("PEMF_SENSOR_LOG_DIR")
    if ozel:
        return Path(ozel)
    try:
        from utils.path_utils import get_app_data_directory

        return Path(get_app_data_directory()) / "sensor_log"
    except Exception:
        return Path.home() / "pemf_sensor_log"


class SensorKaydedici:
    """Günlük döndürmeli, boyut-tavanlı CSV kaydedici. Tüm giriş noktaları hata yutar."""

    def __init__(self, dizin: Path | None = None, gun: int | None = None, mb: int | None = None):
        self.dizin = Path(dizin) if dizin else _kayit_dizini()
        self.gun = gun if gun is not None else _sayi(os.environ.get("PEMF_SENSOR_LOG_DAYS", ""), _VARSAYILAN_GUN)
        self.mb = mb if mb is not None else _sayi(os.environ.get("PEMF_SENSOR_LOG_MB", ""), _VARSAYILAN_MB)
        self._kilit = threading.Lock()
        self._dosya = None
        self._gun_etiketi = ""
        self._aktif_ad = ""
        self._son_flush = 0.0
        self.yazilan = 0
        self.atilan = 0

    # ── iç yardımcılar ────────────────────────────────────────────────────────────────────
    def _dosya_yolu(self, etiket: str) -> Path:
        return self.dizin / f"sensor_{etiket}.csv"

    def _dosyayi_hazirla(self, simdi: datetime) -> None:
        """Gün değiştiyse yeni dosya aç; yeni dosyaya başlık yaz; retention uygula."""
        etiket = simdi.strftime("%Y-%m-%d")
        if self._dosya is not None and etiket == self._gun_etiketi:
            return
        if self._dosya is not None:
            try:
                self._dosya.close()
            except Exception:
                pass
            self._dosya = None
        self.dizin.mkdir(parents=True, exist_ok=True)
        # ⚠️ D2.39: o gün ESKİ başlıkla (ör. güncellemeden önce) açılmış dosyaya yeni sütunlu satır eklenmez — sütunlar kayardı.
        # Başlığı uyuşmayan dosya olduğu gibi kalır, satırlar `sensor_<gün>_<n>.csv`ye gider (retention gün etiketini ilk 10
        # karakterden okur). Kapı: tests/test_stm_telemetrisi_SENSOR_KAYDINA_yazilir_D239.py
        baslik = ",".join(SUTUNLAR)
        yol, n = self._dosya_yolu(etiket), 1
        while yol.exists() and yol.stat().st_size > 0 and self._ilk_satir(yol) != baslik:
            n += 1
            yol = self.dizin / f"sensor_{etiket}_{n}.csv"
        yeni = not yol.exists() or yol.stat().st_size == 0
        self._dosya = open(yol, "a", encoding="utf-8", newline="")
        if yeni:
            self._dosya.write(baslik + "\n")
        self._gun_etiketi = etiket
        self._aktif_ad = yol.name
        self._temizle(simdi)

    @staticmethod
    def _ilk_satir(yol: Path) -> str:
        try:
            with open(yol, encoding="utf-8", newline="") as f:
                return f.readline().rstrip("\r\n")
        except OSError:
            return ""

    def _temizle(self, simdi: datetime) -> None:
        """Gün sınırı + TOPLAM BOYUT tavanı. ⚠️ Tavan olmadan disk sessizce dolar."""
        try:
            dosyalar = sorted(self.dizin.glob("sensor_*.csv"))
        except Exception:
            return
        sinir = simdi - timedelta(days=self.gun)
        for y in list(dosyalar):
            etiket = y.stem.replace("sensor_", "")[:10]  # D2.39: `sensor_<gün>_<n>.csv` da aynı gün
            try:
                if datetime.strptime(etiket, "%Y-%m-%d") < sinir and y.name != self._aktif_ad:
                    y.unlink()
                    dosyalar.remove(y)
            except (ValueError, OSError):
                continue
        # Boyut tavanı: en ESKİden başlayarak sil (bugünün dosyasına dokunma).
        tavan = self.mb * 1024 * 1024
        try:
            toplam = sum(y.stat().st_size for y in dosyalar)
        except OSError:
            return
        for y in dosyalar:
            if toplam <= tavan:
                break
            if y.name == self._aktif_ad:
                continue
            try:
                boyut = y.stat().st_size
                y.unlink()
                toplam -= boyut
            except OSError:
                continue

    # ── genel API ─────────────────────────────────────────────────────────────────────────
    def kaydet(self, bobin, msg_type: str, yuk: dict, zaman: float | None = None) -> bool:
        """Bir telemetri mesajını CSV'ye ekler. `True` = satır yazıldı.

        ⚠️ ASLA FIRLATMAZ: MQTT işleyicisinden çağrılır; bir dosya hatası canlı durum
        güncellemesini, paneli ya da E-stop görünürlüğünü bozamaz.
        `zaman` (epoch sn): satırın damgası — arka plan kaydı mesajın GELDİĞİ anı verir (yoksa şimdi).
        """
        if not _acik_mi():
            return False
        if msg_type not in KAYDEDILEN_TIPLER or not isinstance(yuk, dict):
            return False
        try:
            satir = {s: "" for s in SUTUNLAR}
            _t = time.time() if zaman is None else float(zaman)
            simdi = datetime.fromtimestamp(_t)
            satir["ts_yerel"] = simdi.isoformat(timespec="milliseconds")
            satir["ts_epoch_ms"] = str(int(_t * 1000))
            satir["bobin"] = str(bobin)
            satir["msg_type"] = str(msg_type)
            # CH4 · Y154: akım sensörü KAPALIYKEN akım sütunları (current / current_saturated / max_current / current_sensor_ok)
            # BOŞ kalır — STM ve ESP kaydının ortak tek girişi; sütun sırası (sözleşme) DEĞİŞMEZ.
            for anahtar, deger in akimsiz(yuk).items():
                sutun = _ESLEME.get(anahtar)
                if not sutun:
                    continue
                if isinstance(deger, bool):
                    satir[sutun] = "1" if deger else "0"
                elif deger is None:
                    satir[sutun] = ""
                else:
                    metin = str(deger)
                    # CSV bütünlüğü: virgül/tırnak/satır sonu taşıyan alanı (ör. wifi_ssid
                    # benzeri metinler ileride eklenirse) alıntıla.
                    if any(c in metin for c in (",", '"', "\n", "\r")):
                        metin = '"' + metin.replace('"', '""') + '"'
                    satir[sutun] = metin

            with self._kilit:
                self._dosyayi_hazirla(simdi)
                self._dosya.write(",".join(satir[s] for s in SUTUNLAR) + "\n")
                self.yazilan += 1
                if time.monotonic() - self._son_flush >= _FLUSH_ARALIGI_SN:
                    self._dosya.flush()
                    self._son_flush = time.monotonic()
            return True
        except Exception:
            self.atilan += 1
            logger.debug("sensor telemetri kaydi basarisiz (canli akis etkilenmedi)", exc_info=True)
            return False

    def flush(self) -> None:
        """Tampondaki satırları diske indir.

        ⚠️ TAMPONLAMA BİLİNÇLİ: her satırda `flush` yapmak 3 bobin × 1 Hz'de saniyede üç disk
        senkronu demektir (SSD ömrü + gereksiz I/O). Bedeli: süreç aniden ölürse en fazla
        `_FLUSH_ARALIGI_SN` kadar telemetri kaybolur — telemetri için kabul edilebilir, tıbbi
        kayıt için OLMAZDI (o yüzden hasta verisi bu yoldan GEÇMİYOR).
        Kapanışta ve dışarıdan okuma öncesinde çağrılır.
        """
        _arka_kuyruk_bosalsin(
            2.0
        )  # F2-3.1: arka plan kuyruğundaki satırlar önce dosyaya (kilit DIŞINDA — işçi kilidi alır)
        with self._kilit:
            if self._dosya is not None:
                try:
                    self._dosya.flush()
                    self._son_flush = time.monotonic()
                except Exception:
                    logger.debug("sensor kaydi flush edilemedi", exc_info=True)

    def kapat(self) -> None:
        with self._kilit:
            if self._dosya is not None:
                try:
                    self._dosya.flush()
                    self._dosya.close()
                except Exception:
                    pass
                self._dosya = None

    def durum(self) -> dict:
        return {
            "acik": _acik_mi(),
            "dizin": str(self.dizin),
            "gun": self.gun,
            "mb": self.mb,
            "yazilan": self.yazilan,
            "atilan": self.atilan,
            "sutunlar": len(SUTUNLAR),
        }


_kaydedici: SensorKaydedici | None = None
_olustur_kilit = threading.Lock()


def kaydedici() -> SensorKaydedici:
    """Süreç ömrü boyunca tek kaydedici (dosya tanıtıcısı paylaşılır)."""
    global _kaydedici
    if _kaydedici is None:
        with _olustur_kilit:
            if _kaydedici is None:
                _kaydedici = SensorKaydedici()
    return _kaydedici


def kaydet(bobin, msg_type: str, yuk: dict) -> bool:
    """MQTT işleyicisinin çağırdığı tek satırlık giriş. Hata yutar."""
    try:
        return kaydedici().kaydet(bobin, msg_type, yuk)
    except Exception:
        logger.debug("sensor kaydedici olusturulamadi", exc_info=True)
        return False


# ⚠️ F2-3.1 (2-F incelemesi, D2.39): STM telemetrisi STM OKUYUCU iş parçacığında yayımlanır (`_handle_stm_line` → olay veriyolu →
# api işleyicisi EŞZAMANLI abone) — kaydın dosya G/Ç'si (gün değişiminde mkdir + glob + unlink dahil) okuyucuda koşuyordu. Dizin
# asılınca (USB/ağ yolu, sürücü takılması) okuyucu sonraki satırları (kartın tüm-sıfır ACK'i = ACİL DURDUR teyidi, NACK, STM_EVT)
# işleyemiyor, kaydedicinin kilidini tutan asılı okuyucu yeniden bağlanmanın el sıkışmasını da kilitliyordu (ölçüldü). Çağıran
# artık yalnız SINIRLI kuyruğa koyar (ASLA bloklamaz; dolu kuyrukta satır atılır ve `atilan` sayılır); G/Ç tek arka plan işçisinde.
_ARKA_KUYRUK_BOYU = 2048  # ~5 dk (7 bobin × 1 satır/sn); taşarsa telemetri atılır — canlı akış beklemez
_arka_kuyruk: queue.Queue = queue.Queue(maxsize=_ARKA_KUYRUK_BOYU)
_arka_is: threading.Thread | None = None
_arka_kilit = threading.Lock()


def _arka_isci() -> None:
    while True:
        bobin, msg_type, yuk, zaman = _arka_kuyruk.get()
        try:
            kaydedici().kaydet(bobin, msg_type, yuk, zaman=zaman)
        except Exception:
            # D1.17: daemon döngüsünün bildirimi de fırlatmamalı (yoksa işçi sessizce ölür, kuyruk dolar, telemetri hep atılır).
            # Kapı: tests/test_dongu_hata_bildirimi_OLDURMEZ.py
            dongu_hatasini_bildir("sensor kaydi (arka plan) basarisiz", logger=logger, seviye=logging.DEBUG)
        finally:
            _arka_kuyruk.task_done()


def kaydet_arka_planda(bobin, msg_type: str, yuk: dict) -> bool:
    """Satırı arka plan kaydına KUYRUKLAR. ⚠️ ASLA BLOKLAMAZ, ASLA FIRLATMAZ (STM okuyucu / el sıkışma iş parçacığından çağrılır).
    `True` = kuyruğa alındı; `False` = kayıt kapalı / ilgisiz tip / kuyruk dolu (satır atıldı)."""
    global _arka_is
    try:
        if not _acik_mi() or msg_type not in KAYDEDILEN_TIPLER or not isinstance(yuk, dict):
            return False
        if _arka_is is None or not _arka_is.is_alive():
            with _arka_kilit:
                if _arka_is is None or not _arka_is.is_alive():
                    _arka_is = threading.Thread(target=_arka_isci, name="sensor-kaydi", daemon=True)
                    _arka_is.start()
        _arka_kuyruk.put_nowait((bobin, msg_type, dict(yuk), time.time()))
        return True
    except queue.Full:
        try:
            kaydedici().atilan += 1
        except Exception:
            pass
        return False
    except Exception:
        logger.debug("sensor kaydi kuyruga alinamadi", exc_info=True)
        return False


def _arka_kuyruk_bosalsin(sure: float) -> bool:
    """Arka plan kuyruğu en çok `sure` sn boşalsın diye bekler (okuma / kapanış öncesi). Asılı diskte süre dolar — bloklamaz."""
    son = time.monotonic() + sure
    with _arka_kuyruk.all_tasks_done:
        while _arka_kuyruk.unfinished_tasks:
            kalan = son - time.monotonic()
            if kalan <= 0:
                return False
            _arka_kuyruk.all_tasks_done.wait(kalan)
    return True
