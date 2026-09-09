# -*- coding: utf-8 -*-
# Author: mertaygn
"""[BKAYIT] SERİ-PORT TOPLAYICI — S3'ün B kaydını masaüstünde CSV'ye yazar.

SAHİP İSTEĞİ (2026-09-09): "manyetik alan değerleriyle zamanı, sadece — 2 kolon. PWM başlayınca
kayıt başlasın, bitince dursun. Masaüstüne kaydetsin."

⚠️ NEDEN İKİ PARÇA: S3 bir mikrodenetleyicidir, PC'nin dosya sistemine erişemez. Kart veriyi
ayrıştırılabilir biçimde seri porta basar (`esps3_pemf_coil.ino::bKaydiRaporla`), bu betik de
her PWM oturumunu masaüstünde AYRI bir CSV'ye yazar. Broker/backend YOK — yalnız COM portu.

KULLANIM:
    python scripts/b_kaydi_topla.py              # portu kendisi bulur
    python scripts/b_kaydi_topla.py COM3         # portu sen ver
    python scripts/b_kaydi_topla.py COM3 D:\\olcum   # cikti klasorunu sen ver

Açık bırak; her PWM başlatmanda yeni dosya açılır, durdurmanda kapanır. Ctrl+C ile çık.

⚠️ DTR/RTS'E DOKUNULMAZ (2026-09-09'da ölçüldü): ESP32-S3'ün native USB CDC'sinde bu hatları
darbelemek kartı İNDİRME (bootloader) kipine sokar — darbe atan bir deneme 40 saniye boyunca
SIFIR satır getirdi, darbe kaldırılınca veri aktı. `pyserial` Windows'ta portu açarken DTR'yi
kendiliğinden etkinleştirir; bu normal çalışma durumudur, ek bir darbe GEREKMEZ.

⚠️ ARDUINO SERİ MONİTÖRÜ AÇIKKEN ÇALIŞMAZ: Windows'ta COM portu tek süreç tutar
("Erişim engellendi"). Monitörü kapat, sonra bu betiği çalıştır (ya da tersi).
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

BAUD = 115200
ONEK = "[BKAYIT]"

#: `[BKAYIT] BASLA coil=8 freq=100 duty=25 saat=epoch ts=1788965123456`
_BASLA = re.compile(r"\[BKAYIT\]\s+BASLA\s+coil=(\d+)\s+freq=(-?\d+)\s+duty=(-?\d+)\s+saat=(\w+)\s+ts=(\d+)")
#: `[BKAYIT] 1788965123656,0.0198`  → TAM İKİ KOLON (sahip şartı)
_VERI = re.compile(r"\[BKAYIT\]\s+(\d+),(-?\d+(?:\.\d+)?)\s*$")
#: `[BKAYIT] BITTI ornek=1024 atlanan=3 sure_ms=205000`
_BITTI = re.compile(r"\[BKAYIT\]\s+BITTI\s+ornek=(\d+)\s+atlanan=(\d+)\s+sure_ms=(\d+)")


def satiri_coz(satir: str) -> tuple[str, dict] | None:
    """Bir seri satırını olaya çevirir: `("basla"|"veri"|"bitti", alanlar)` ya da `None`.

    SAF FONKSİYON — kapı bunu doğrudan ölçer (seri port ya da kart gerekmez).
    ⚠️ `[BKAYIT]` öneki taşımayan satır YOK SAYILIR: aynı porta `[MAG]`, `[MQTT]`, `[Sensör]`
    ve açılış günlüğü de akıyor. Önek filtresi olmadan CSV o gürültüyle dolardı.
    """
    if ONEK not in satir:
        return None
    m = _BASLA.search(satir)
    if m:
        return "basla", {
            "bobin": int(m.group(1)),
            "freq": int(m.group(2)),
            "duty": int(m.group(3)),
            "saat": m.group(4),
            "ts": int(m.group(5)),
        }
    m = _BITTI.search(satir)
    if m:
        return "bitti", {
            "ornek": int(m.group(1)),
            "atlanan": int(m.group(2)),
            "sure_ms": int(m.group(3)),
        }
    m = _VERI.search(satir)
    if m:
        return "veri", {"zaman_ms": m.group(1), "b_mT": m.group(2)}
    return None


def saat_metni(zaman_ms: str, saat_turu: str | None) -> str:
    """Kart damgasını saat metnine çevirir: `18.02.56.123` (sahip 2026-09-09).

    KAYNAK SEÇİMİ:
      · `saat=epoch` (NTP oturmuş) → KARTIN KENDİ damgası çevrilir. Ölçülen şey kartın
        zamanlamasıdır; PC'nin varış anını kullanmak seri port/işletim sistemi gecikmesini
        veriye karıştırırdı.
      · `saat=uptime` (NTP yok) → damga açılıştan sayar, saate çevrilemez; o durumda PC'nin
        o anki saati yazılır (elde tek gerçek saat odur) ve dosya adında `_uptime` uyarısı kalır.

    ⚠️ MİLİSANİYE KORUNUR: örnekleme 5 Hz, yani saniyede 5 satır. Saniye çözünürlüğünde beş
    satır AYNI görünür ve zamanlama analizi (aralık, kayma) imkânsızlaşır. Sahibin verdiği
    biçim korunup sonuna aynı ayırıcıyla ms eklendi.

    ⚠️ TARİH YOK: sütun yalnız saat taşır (sahip "sadece zaman ve mT" dedi). Gün bilgisi dosya
    ADINDA duruyor; gece yarısını geçen bir oturumda saatin 00'a dönmesi oradan çözülür.
    """
    try:
        if saat_turu == "epoch":
            ms = int(zaman_ms)
            an = datetime.fromtimestamp(ms / 1000.0)
            return an.strftime("%H.%M.%S.") + f"{ms % 1000:03d}"
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    an = datetime.now()
    return an.strftime("%H.%M.%S.") + f"{an.microsecond // 1000:03d}"


def dosya_adi(bilgi: dict | None) -> str:
    """Oturum dosyasının adı — SADE (sahip 2026-09-09: "bobin 8'i de kaldır, duty frekans
    kaldır, sadece zaman ve mT istiyorum").

    Bobin/frekans/duty ADA DA YAZILMAZ. Kimlik gerekiyorsa dosyanın zaman damgası ve içindeki
    epoch damgaları yeterlidir.

    ⚠️ TEK İSTİSNA `_uptime` eki: NTP oturmamışsa kartın damgası epoch DEĞİL, açılıştan geçen
    ms'dir. O ek olmadan dosya 1970 tarihleriyle dolu görünür ve sebebi hiçbir yerde yazmaz —
    ölçümü sessizce çöpe çeviren tek bilgi bu, o yüzden ADDA KALIYOR. Normal (NTP'li) koşuda
    hiçbir ek yok.
    """
    damga = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not bilgi:
        return f"pemf_b_{damga}_oturum-ortasi.csv"
    if bilgi.get("saat") != "epoch":
        return f"pemf_b_{damga}_uptime.csv"
    return f"pemf_b_{damga}.csv"


class Toplayici:
    """Oturum durumunu tutar; her `BASLA`da yeni dosya, her `BITTI`de kapatır."""

    def __init__(self, cikti_dizini: Path):
        self.dizin = Path(cikti_dizini)
        self.dosya = None
        self.yol = None
        self.satir = 0
        self.oturum = 0
        # Oturumun saat türü (epoch / uptime): damga çevriminde kaynağı belirler.
        self.saat_turu = None

    def _bos_yol(self, ad: str) -> Path:
        """Var olan dosyayı EZMEZ; `_2`, `_3`… ekler.

        ⚠️ ZORUNLU (kapı yakaladı): ad artık yalnız saniye çözünürlüklü damga taşıyor (bobin/
        frekans/duty adan kaldırıldı). Operatör durdurup 1 saniye içinde yeniden başlatırsa iki
        oturum AYNI adı üretir ve `open(..., "w")` ilkini SESSİZCE siler — ölçüm kaybı, hiçbir
        uyarı yok.
        """
        yol = self.dizin / ad
        if not yol.exists():
            return yol
        kok, uzanti = ad.rsplit(".", 1)
        for i in range(2, 1000):
            aday = self.dizin / f"{kok}_{i}.{uzanti}"
            if not aday.exists():
                return aday
        return self.dizin / f"{kok}_{int(time.time())}.{uzanti}"

    def _ac(self, bilgi: dict | None) -> None:
        self._kapat()
        self.dizin.mkdir(parents=True, exist_ok=True)
        self.yol = self._bos_yol(dosya_adi(bilgi))
        self.dosya = open(self.yol, "w", encoding="utf-8", newline="")
        self.saat_turu = (bilgi or {}).get("saat")
        # Sahip isteği (2026-09-09): saat + mT — iki kolon, başka yok.
        self.dosya.write("saat,b_mT\n")
        self.satir = 0
        self.oturum += 1
        if bilgi:
            print(
                f"\n[oturum {self.oturum}] BASLADI — bobin {bilgi['bobin']}, "
                f"{bilgi['freq']} Hz, duty %{bilgi['duty']}, saat={bilgi['saat']}",
                flush=True,
            )
        else:
            print(f"\n[oturum {self.oturum}] oturum ORTASINDA yakalandi (BASLA gorulmedi)", flush=True)
        print(f"           -> {self.yol}", flush=True)

    def _kapat(self) -> None:
        if self.dosya is not None:
            try:
                self.dosya.flush()
                self.dosya.close()
            except OSError:
                pass
            self.dosya = None

    def isle(self, satir: str) -> None:
        olay = satiri_coz(satir)
        if olay is None:
            return
        tur, alan = olay
        if tur == "basla":
            self._ac(alan)
        elif tur == "veri":
            if self.dosya is None:
                self._ac(None)  # betik oturum ortasinda baslatilmis — veriyi KAYBETME
            # Satır başına flush: 5 Hz'de maliyeti yok, Ctrl+C'de veri kaybı OLMAZ.
            self.dosya.write(f"{saat_metni(alan['zaman_ms'], self.saat_turu)},{alan['b_mT']}\n")
            self.dosya.flush()
            self.satir += 1
            if self.satir % 25 == 0:
                print(f"           {self.satir} satir...", end="\r", flush=True)
        elif tur == "bitti":
            print(
                f"\n[oturum {self.oturum}] BITTI — {self.satir} satir yazildi "
                f"(kart: ornek={alan['ornek']} atlanan={alan['atlanan']} "
                f"sure={alan['sure_ms'] / 1000:.1f} sn)",
                flush=True,
            )
            if alan["atlanan"]:
                print(
                    f"           uyari: {alan['atlanan']} ornek ATLANDI (sensor o anda okunamadi) "
                    "-> CSV'de o zamanlar YOK, 0 yazilmadi",
                    flush=True,
                )
            print(f"           dosya: {self.yol}", flush=True)
            self._kapat()

    def kapat(self) -> None:
        if self.dosya is not None:
            print(f"\n[oturum {self.oturum}] yarida kesildi — {self.satir} satir kaydedildi: {self.yol}")
        self._kapat()


def port_bul() -> str | None:
    """S3'ün portunu bulmaya çalış (native USB CDC). Bulamazsa None."""
    try:
        from serial.tools import list_ports
    except Exception:
        return None
    adaylar = list(list_ports.comports())
    for p in adaylar:
        ad = f"{p.description} {p.manufacturer or ''}".lower()
        if "usb seri" in ad or "usb serial device" in ad or "cdc" in ad:
            return p.device
    return adaylar[0].device if adaylar else None


def main() -> int:
    import serial  # gec import: --help/testler pyserial istemesin

    port = sys.argv[1] if len(sys.argv) > 1 else port_bul()
    if not port:
        print("Seri port bulunamadi. Kullanim: python scripts/b_kaydi_topla.py COM3")
        return 2
    dizin = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(os.path.expanduser("~")) / "Desktop"

    print(f"[toplayici] port={port} baud={BAUD}")
    print(f"[toplayici] cikti={dizin}")
    print("[toplayici] PWM baslatinca kayit basliyor; durdurunca dosya kapaniyor. Cikis: Ctrl+C\n")

    t = Toplayici(dizin)
    try:
        while True:
            try:
                # ⚠️ DTR/RTS'e DOKUNMA (dosya basindaki nota bak) — kart indirme kipine girer.
                s = serial.Serial(port, BAUD, timeout=1)
            except Exception as e:
                print(f"[toplayici] port acilamadi ({e}) — 3 sn sonra yeniden denenecek", flush=True)
                time.sleep(3)
                continue
            print(f"[toplayici] {port} baglandi, dinleniyor...", flush=True)
            try:
                while True:
                    ham = s.readline()
                    if not ham:
                        continue
                    t.isle(ham.decode("utf-8", "replace").rstrip())
            except Exception as e:
                # Kart reset/çıkarma → porta yeniden bağlan (oturum dosyası korunur).
                print(f"\n[toplayici] baglanti koptu ({e}) — yeniden baglanilacak", flush=True)
            finally:
                try:
                    s.close()
                except Exception:
                    pass
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[toplayici] durduruldu.")
    finally:
        t.kapat()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
