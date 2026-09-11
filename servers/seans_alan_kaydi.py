# Author: mertaygn, cglrgrkn
"""Seans boyunca ÖLÇÜLEN manyetik alanı biriktirir ve masaüstüne CSV yazar.

SAHİP KARARI 2026-09-11:
  "aktif seans kısmı var en üstte manuel modu başlatınca frekans var süre var yoğunluk var
   ordaki yoğunluk değeri stm e bağlı olan SENSÖRDEN GELSİN VE AYNI ZAMANDA CSV YE KAYDEDİP
   MASAÜSTÜNE KOYSUN. SEANS ÖZELİNDE OLCAK BU."

===============================================================================
İKİ FARKLI "YOĞUNLUK" VARDIR — KARIŞTIRILMAMALI
===============================================================================
1. **Reçete** (`intensity_mt`): operatörün yazdığı sayı. Cihaza GÖNDERİLMEZ (STM/ESP
   paketi mT taşımaz), yalnız DB'ye kaydedilir. Arayüzde "(kayıt)" etiketiyle duruyordu
   çünkü denetim 2026-09-03'te operatörlerin bunu UYGULANAN doz sandığı görüldü.
2. **Ölçülen** (bu dosya): MLX90393'ün gerçekten okuduğu tepe alan.

Bu dosya (1)'i DEĞİŞTİRMEZ. DB'deki reçete alanı olduğu gibi kalır; ölçülen değer ayrı
taşınır ve arayüzde etiketi de değişir. Ölçümü reçetenin üzerine yazmak, geçmişteki
"yazılan sayı ölçülmüş gibi kaydedildi" sınıfının aynısı olurdu.

===============================================================================
⚠️ ÖLÇÜM YOKKEN 0.0 ÜRETİLMEZ
===============================================================================
Sensör bağlı değilse `zirve()` **None** döner ve arayüz reçete değerine düşer (etiketiyle
birlikte). 0.0 döndürmek, aşağı akışta "0.0 mT ölçüldü" olarak kaydedilir — bu deponun
tekrarlayan arızası (PDF'e "0.0 °C ölçüldü" yazdıran desen).

===============================================================================
⚠️ MASAÜSTÜ HER ZAMAN VAR DEĞİLDİR
===============================================================================
Backend Windows servisi olarak da koşabilir (LocalSystem). O hesapta `~` =
`C:\\Windows\\System32\\config\\systemprofile` olur ve orada "Desktop" ya yoktur ya da
kimsenin görmediği bir dizindir. CSV sessizce oraya yazılırsa sahip dosyayı ASLA bulamaz.
Bu yüzden hedef dizin ADAYLAR arasından seçilir, `systemprofile` REDDEDİLİR ve seçilen yol
çağırana DÖNDÜRÜLÜR ki bildirimde gösterilebilsin.
"""

from __future__ import annotations

import csv
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: CSV başlığı — sütun eklenirse SONA eklenir (eski dosyalarla açılabilirlik).
CSV_BASLIKLARI = [
    "zaman",  # ISO-8601 yerel
    "gecen_sn",  # seans başından beri geçen saniye
    "bobin",  # telemetriyi gönderen bobin kimliği
    "alan_mt",  # o saniyenin TEPE |B| değeri (anlık DEĞİL)
    "ornek",  # tepenin türediği örnek sayısı ("" = firmware bildirmedi)
    "doygun",  # 1 = ham eksen tam ölçeğe dayandı → değer GÜVENİLMEZ
    # ⚠️ İŞARETLİ EKSEN UÇLARI (mT) — sahip isteği 2026-09-11: "- +b diye kaydetsin".
    # `alan_mt` BÜYÜKLÜKTÜR (işaretsiz) ve unipolar (0→+B) ile bipolari (−B→+B) AYNI
    # gösterir. Sürüş kipinin ve fazın gerçek etkisi ancak burada görünür:
    #   tepeden-tepeye = x_max − x_min  (eksen başına)
    #   DC ofset       = (x_max + x_min) / 2   → unipolarda ≠0, bipolarda ≈0
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    # Türetilmiş kolaylık sütunları (aşağı akış hesaplamasın diye):
    "pp_x",
    "pp_y",
    "pp_z",  # tepeden-tepeye, eksen başına
]


def masaustu_dizini() -> tuple[Path, str]:
    """(dizin, gerekçe) — CSV'nin yazılacağı yer.

    Sıra: ``~/Desktop`` → ``~/OneDrive/Desktop`` → ``~/Masaüstü`` → geçerli çalışma dizini.
    ⚠️ LocalSystem profili (``systemprofile``) REDDEDİLİR: oraya yazılan dosyayı sahip
    göremez ve "kaydetmedi" sanır.
    """
    ev = Path(os.path.expanduser("~"))
    if "systemprofile" in str(ev).lower():
        yedek = Path.cwd()
        return yedek, "servis hesabı (masaüstü yok)"
    for aday in (ev / "Desktop", ev / "OneDrive" / "Desktop", ev / "Masaüstü"):
        if aday.is_dir():
            return aday, "masaüstü"
    return Path.cwd(), "masaüstü bulunamadı"


def _guvenli_parca(metin: str, azami: int = 40) -> str:
    """Dosya adına konabilecek hâle getirir (yol ayıracı/kontrol karakteri bırakmaz)."""
    temiz = "".join(c for c in (metin or "") if c.isalnum() or c in (" ", "-", "_")).strip()
    temiz = temiz.replace(" ", "_")
    return temiz[:azami]


class SeansAlanKaydi:
    """Tek aktif seansın ölçülen alanını biriktirir ve CSV'ye yazar.

    ⚠️ SATIR SATIR YAZILIR, SONDA TOPLU DEĞİL: backend seans ortasında çökerse (ya da
    operatör fişi çekerse) o ana kadarki ölçüm KALIR. Bu deponun kayıtlı arızalarından
    biri tam olarak "yalnız sonda yazılıyordu, çökünce hiçbir şey kalmıyordu" idi.
    """

    def __init__(self) -> None:
        self._kilit = threading.Lock()
        self._aktif = False
        self._seans_id: str | None = None
        self._baslangic_mono: float = 0.0
        self._yol: Path | None = None
        self._dosya = None
        self._yazici = None
        self._zirve: float | None = None
        self._zirve_bobin: int | None = None
        self._son: float | None = None
        self._satir = 0
        self._doygun_goruldu = False

    # ── yaşam döngüsü ────────────────────────────────────────────────────────
    def seans_basladi(self, seans_id: str, meta: dict | None = None) -> Path | None:
        """Yeni seans için CSV açar. Dosya açılamazsa None döner — SEANS ENGELLENMEZ."""
        self.seans_bitti("yeni seans başladı")  # savunma: yarım kalan kaydı kapat
        meta = meta or {}
        try:
            dizin, _gerekce = masaustu_dizini()
            damga = datetime.now().strftime("%Y%m%d_%H%M%S")
            hasta = _guvenli_parca(str(meta.get("patient_name") or ""))
            ad = f"PEMF_alan_{damga}" + (f"_{hasta}" if hasta else "") + ".csv"
            yol = dizin / ad
            # utf-8-sig: Excel'in Türkçe karakterleri doğru açması için BOM ŞART.
            dosya = open(yol, "w", encoding="utf-8-sig", newline="")
            yazici = csv.writer(dosya)
            # Üst bilgi: seansın kim/ne olduğunu dosyanın KENDİSİ taşısın (dosya adı yeter
            # sanılıp taşındığında/yeniden adlandırıldığında bağlam kaybolur).
            yazici.writerow(["# PEMF seans alan kaydı"])
            yazici.writerow(["# seans", seans_id])
            for anahtar in ("patient_name", "operator_name", "mode", "frequency", "duty", "duration_minutes"):
                if meta.get(anahtar) is not None:
                    yazici.writerow([f"# {anahtar}", meta.get(anahtar)])
            yazici.writerow(["# recete_yogunluk_mt", meta.get("intensity")])
            yazici.writerow(["# NOT", "alan_mt = O SANIYENIN TEPE degeri (anlik degil)"])
            yazici.writerow(CSV_BASLIKLARI)
            dosya.flush()
        except Exception:
            logger.exception("seans alan kaydı açılamadı — seans etkilenmez")
            return None

        with self._kilit:
            self._aktif = True
            self._seans_id = seans_id
            self._baslangic_mono = time.monotonic()
            self._yol = yol
            self._dosya = dosya
            self._yazici = yazici
            self._zirve = None
            self._zirve_bobin = None
            self._son = None
            self._satir = 0
            self._doygun_goruldu = False
        logger.info("seans alan kaydı açıldı: %s", yol)
        return yol

    def seans_bitti(self, sebep: str = "") -> Path | None:
        """CSV'yi özetle kapatır ve yolunu döndürür (kayıt yoksa None)."""
        with self._kilit:
            if not self._aktif:
                return None
            self._aktif = False
            dosya, yazici, yol = self._dosya, self._yazici, self._yol
            zirve, bobin, satir, doygun = self._zirve, self._zirve_bobin, self._satir, self._doygun_goruldu
            self._dosya = self._yazici = None
        try:
            if yazici is not None:
                yazici.writerow([])
                yazici.writerow(["# bitis", datetime.now().isoformat(timespec="seconds"), sebep])
                yazici.writerow(["# olcum_satiri", satir])
                yazici.writerow(["# seans_tepe_mt", "" if zirve is None else round(zirve, 3)])
                yazici.writerow(["# seans_tepe_bobin", "" if bobin is None else bobin])
                if doygun:
                    yazici.writerow(["# UYARI", "en az bir olcum tam olcege dayandi — degerler GUVENILMEZ"])
            if dosya is not None:
                dosya.close()
        except Exception:
            logger.exception("seans alan kaydı kapatılamadı")
        return yol

    # ── ölçüm girişi ─────────────────────────────────────────────────────────
    def olcum(
        self,
        bobin: int,
        mt: float,
        ornek: int | None = None,
        doygun: bool = False,
        uclar: dict | None = None,
    ) -> None:
        """Bir saniyelik TEPE ölçümünü kaydeder. Seans yoksa sessizce yok sayılır.

        `uclar`: {"mag_x_min":…, "mag_x_max":…, …} — işaretli eksen uçları (mT).
        ⚠️ Yoksa o sütunlar BOŞ bırakılır; 0.0 yazmak "ölçüldü, sıfır çıktı" diye
        okunur (bu deponun tekrarlayan sahte-ölçüm sınıfı).
        """
        try:
            deger = float(mt)
        except (TypeError, ValueError):
            return
        # ⚠️ NaN/inf SÜZÜLÜR: sqrt/ölçek yolundan gelen bozuk bir sayı `max()` ile seans
        # tepesine yerleşirse bir daha ASLA düşmez ve tüm seansın kaydını zehirler.
        if deger != deger or deger in (float("inf"), float("-inf")):
            return
        satir = None
        with self._kilit:
            if not self._aktif:
                return
            self._son = deger
            if (self._zirve is None) or (deger > self._zirve):
                self._zirve = deger
                self._zirve_bobin = int(bobin)
            if doygun:
                self._doygun_goruldu = True
            self._satir += 1
            gecen = time.monotonic() - self._baslangic_mono
            satir = [
                datetime.now().isoformat(timespec="seconds"),
                round(gecen, 1),
                int(bobin),
                round(deger, 3),
                "" if ornek is None else int(ornek),
                1 if doygun else 0,
            ]
            # İşaretli uçlar + türetilmiş tepeden-tepeye. Alan YOKSA boş bırakılır.
            u = uclar or {}
            for eksen in ("x", "y", "z"):
                for uc in ("min", "max"):
                    v = u.get(f"mag_{eksen}_{uc}")
                    satir.append("" if v is None else round(float(v), 3))
            for eksen in ("x", "y", "z"):
                lo, hi = u.get(f"mag_{eksen}_min"), u.get(f"mag_{eksen}_max")
                satir.append("" if (lo is None or hi is None) else round(float(hi) - float(lo), 3))
            yazici, dosya = self._yazici, self._dosya
        if yazici is None or satir is None:
            return
        try:
            yazici.writerow(satir)
            if dosya is not None:
                dosya.flush()  # çökme anında son satır da diskte olsun
        except Exception:
            logger.exception("seans alan kaydı satırı yazılamadı")

    # ── okuma ────────────────────────────────────────────────────────────────
    def zirve(self) -> float | None:
        """Seans boyunca ölçülen EN BÜYÜK |B| (mT). None = hiç ölçüm gelmedi."""
        with self._kilit:
            return self._zirve

    def son_deger(self) -> float | None:
        """En son gelen saniyelik tepe (mT). None = hiç ölçüm gelmedi."""
        with self._kilit:
            return self._son

    def durum(self) -> dict:
        """Teşhis özeti (API/log için)."""
        with self._kilit:
            return {
                "aktif": self._aktif,
                "seans_id": self._seans_id,
                "yol": str(self._yol) if self._yol else None,
                "satir": self._satir,
                "zirve_mt": self._zirve,
                "son_mt": self._son,
                "doygun": self._doygun_goruldu,
            }


#: Süreç genelinde tek örnek — aynı anda yalnız bir seans olabilir (`/session/start` 409 döner).
seans_alan_kaydi = SeansAlanKaydi()
