# -*- coding: utf-8 -*-
# Author: mertaygn
"""STM32 WORKSPACE'İNİ FLASH İÇİN KOPYALA — derleme artıkları HARİÇ.

===============================================================================
⚠️ NEDEN VAR — SAHADA BİR GÜN KAYBETTİREN TUZAK (2026-09-11)
===============================================================================
Workspace masaüstüne `Debug/` klasörüyle birlikte kopyalandı. O klasörde **8 Eylül
tarihli, 5 BOBİNLİK** bir `PEMF_UNIPOLAR.elf` duruyordu (7 bobin geçişi 10 Eylül'de
oldu). CubeIDE kaynağı yeniden derlemek yerine **o bayat ikiliyi flashladı**.

Sonuç sinsi: kart bağlı, uygulama STM'i görüyor, ama backend'in 120 baytlık paketini
88 bayt bekleyen firmware çerçeveliyor → CRC tutmuyor → **her pakete `STM_NACK: CRC`**
→ hiçbir bobin çalışmıyor (1-5 dahil). Ekranda "başarılı" görünür; arıza yalnız
bildirim selinden ve UART banner'ından anlaşılır.

Kaynağın doğru olması, KARTA YÜKLENDİĞİNİ kanıtlamaz. Bu betik artıkları taşımayarak
CubeIDE'yi yeniden derlemeye ZORLAR ve kopyanın gerçekten 7 bobinlik olduğunu DOĞRULAR.

KULLANIM:
    python scripts/stm_workspace_kopyala.py                    # masaüstüne, tarihli klasör
    python scripts/stm_workspace_kopyala.py --hedef D:/yedek   # başka yere

AYNI GÜN YENİDEN KOŞUM: var olan tarihli klasör SİLİNMEZ, yanına `<ad>_yedek_<HHMMSS>` adıyla
TAŞINIR (sahibin o günkü düzenlemeleri ve `.metadata` korunur). ⚠️ Yedek, bayat `Debug/*.elf`
taşıyabilir: onu CubeIDE'de AÇMAYIN / FLASHLAMAYIN — yalnız farkınızı alın. Yedekler kendiliğinden
temizlenmez.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
#: ⚠️ TEK PROJE (2026-09-11): `stm32_pemf_unipolar` aynasi KALDIRILDI. Surus kipi artik
#: `PEMF_BOBIN_UNIPOLAR_MASKESI` ile bobin basina seciliyor; ikinci bir derleme gerekmiyor.
PROJELER = ["stm32_pemf"]

#: Kopyaya ASLA girmeyecek dizinler — DERLEME ÇIKTISI.
#: ⚠️ `Debug`/`Release` burada OLMAK ZORUNDA: içlerindeki `.elf` doğrudan flashlanabilir
#: ve CubeIDE yeniden derlemeden onu yükleyebilir (bu betiğin var oluş sebebi).
#: ⚠️ `.settings` BİLEREK HARİÇ DEĞİL: CubeIDE proje tercihleri (indeksleyici/biçimlendirici)
#: oradadır, derlemeyi `.cproject` belirler. Dışlamak kopyayı sahibin çalışan kurulumundan
#: gereksizce ayrıştırırdı; kopya, derleme artıkları DIŞINDA depo kaynağıyla BİREBİR kalmalı.
HARIC_DIZIN = {"Debug", "Release", ".metadata", "__pycache__"}
#: Kopyaya ASLA girmeyecek dosya uzantıları — flashlanabilir ikililer.
HARIC_UZANTI = {".elf", ".bin", ".hex", ".map", ".o", ".d", ".su", ".lst"}


def _atla(dizin: str, adlar: list[str]) -> set[str]:
    atlanan = {a for a in adlar if a in HARIC_DIZIN}
    for a in adlar:
        if Path(a).suffix.lower() in HARIC_UZANTI and not (Path(dizin) / a).is_dir():
            atlanan.add(a)
    return atlanan


def _bobin_sayisi(main_c: Path) -> int | None:
    try:
        m = re.search(r"#define\s+NUM_COILS\s+(\d+)", main_c.read_text(encoding="utf-8", errors="replace"))
        return int(m.group(1)) if m else None
    except OSError:
        return None


# ⚠️ PROTOKOL ÖZELLİKLERİ — her biri paketin GENİŞLİĞİNİ değiştirmiş bir aşamadır.
# Kaynak eski bir aşamada kalmışsa flaşlanan kart backend'in paketini CRC'den düşürür ve
# HİÇBİR bobin çalışmaz (2026-09-11 sahasında bayat ELF ile tam olarak bu yaşandı).
# NUM_COILS tek başına YETMEZ: 7 bobinli ama kip alanı olmayan bir kaynak da 120 baytlıktır.
PROTOKOL_ISARETLERI = (
    ("unipolar_maskesi", "paket kip alani YOK -> 120 baytlik ESKI protokol"),
    ("Coil_KipUygula", "kip uygulama fonksiyonu YOK -> istek pakete girse de kullanilmaz"),
    ("g_yalniz_unipolar", "donanim yetenek tabani YOK -> bobin 6-7 bipolar surulmeye calisilir"),
    # ⚠️ 2026-09-11 saha arizasi: newlib-nano float printf'i baglanmazsa TUM STM_TELE
    # satirlari sayisiz gider (`B=`, `T=`, `A=`, `I=`), backend onlari reddeder ve
    # sicaklik/manyetik alan/akim arayuze BIR DAHA HIC ULASMAZ. Bobinler calismaya
    # devam ettigi icin ariza "sensor bozuk" gibi gorunur. Bayat bir kaynagin
    # masaustune cikip flaslanmasini ENGELLE.
    ("&_printf_float", "printf float zorlamasi YOK -> TUM sensor telemetrisi SESSIZCE olur"),
)


def _protokol_eksikleri(main_c: Path) -> list[str]:
    try:
        kaynak = main_c.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["main.c okunamadi"]
    return [aciklama for isaret, aciklama in PROTOKOL_ISARETLERI if isaret not in kaynak]


def _yedek_yolu(hedef: Path) -> Path:
    """Var olan hedefin TAŞINACAĞI, henüz VAR OLMAYAN yol (aynı kök, saat damgalı)."""
    damga = _dt.datetime.now().strftime("%H%M%S")
    aday = hedef.with_name(f"{hedef.name}_yedek_{damga}")
    n = 1
    while aday.exists():
        n += 1
        aday = hedef.with_name(f"{hedef.name}_yedek_{damga}_{n}")
    return aday


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedef", default=None, help="hedef kök (varsayılan: Masaüstü)")
    a = ap.parse_args()

    kok = Path(a.hedef) if a.hedef else Path(os.path.expanduser("~/Desktop"))
    if not kok.is_dir():
        print(f"[HATA] hedef kok yok: {kok}", file=sys.stderr)
        return 2

    # D0Ö.16 ek: kaynaklar hedefe DOKUNMADAN ÖNCE denetlenir — eskiden denetim taşımadan SONRAYDI:
    # betik depo dışına kopyalanıp koşulursa sahibin workspace'i yedeğe taşınır, CubeIDE'nin açtığı
    # yolda boş bir hedef kalırdı.
    eksik_proje = [str(KOK / "firmware" / p) for p in PROJELER if not (KOK / "firmware" / p).is_dir()]
    if eksik_proje:
        print(f"[HATA] proje yok: {eksik_proje} — hedefe DOKUNULMADI", file=sys.stderr)
        return 2
    # D0Ö.16 ek-2 (tur 5): kaynağın İÇERİĞİ de hedefe dokunmadan denetlenir — varlık yetmiyordu: bayat
    # (ör. eski dal, NUM_COILS 5) ya da kısmi kaynakta sahibin workspace'i yedeğe taşınıyor, CubeIDE'nin
    # açtığı yolda bayat kopya kalıyordu. Kopyanın kendisi aşağıda YİNE doğrulanır.
    kaynak_sorun: list[str] = []
    for p in PROJELER:
        ana = KOK / "firmware" / p / "Core" / "Src" / "main.c"
        n = _bobin_sayisi(ana)
        if n != 7:
            kaynak_sorun.append(f"{p}: NUM_COILS={n} (7 bekleniyordu)")
        else:
            kaynak_sorun += [f"{p}: {e}" for e in _protokol_eksikleri(ana)]
    if kaynak_sorun:
        for s in kaynak_sorun:
            print(f"[HATA] KAYNAK BAYAT/KISMI: {s} — hedefe DOKUNULMADI", file=sys.stderr)
        return 1

    hedef = kok / f"PEMF_STM32_workspace_{_dt.date.today().isoformat()}"
    yedek = None
    if hedef.exists():
        # ⚠️ D0Ö.16 (B-10.211): ASLA SİLİNMEZ, YEDEĞE TAŞINIR. Eskiden `shutil.rmtree(hedef)` idi:
        # aynı gün ikinci koşum, sahibin o gün CubeIDE'de yaptığı `main.c` düzenlemesini ve
        # `.metadata`yı onaysız ve GERİ DÖNÜŞSÜZ siliyordu. Taşınamazsa (ör. CubeIDE klasörü
        # açık tutuyor) silmeye DÜŞÜLMEZ — durulur. Kapı: tests/test_stm_workspace_kopyala_korur.py
        yedek = _yedek_yolu(hedef)
        try:
            hedef.rename(yedek)
        except OSError as e:
            print(
                f"[HATA] {hedef} zaten var ve yedege tasinamadi ({e}). HICBIR SEY SILINMEDI. "
                "CubeIDE bu klasoru aciksa kapatip yeniden deneyin ya da --hedef ile baska bir kok verin.",
                file=sys.stderr,
            )
            return 2
        print(f"  onceki kopya YEDEGE tasindi (silinmedi): {yedek}")
        # D0Ö.16 ek-2: uyarı TAŞIMA ANINDA da basılır — sonraki bir adım düşse bile görünsün.
        print("   Bu yedegi CubeIDE'de ACMAYIN / FLASHLAMAYIN (bayat Debug/*.elf tasiyabilir); yalniz farkinizi alin.")
    hedef.mkdir(parents=True)

    for p in PROJELER:
        shutil.copytree(KOK / "firmware" / p, hedef / p, ignore=_atla)
        print(f"  kopyalandi: {p}")

    # ── DOĞRULAMA — kopyanın kendisi ölçülür, kopyalandığı varsayılmaz ──────────
    sorun: list[str] = []

    artiklar = [q for q in hedef.rglob("*") if q.suffix.lower() in HARIC_UZANTI and q.is_file()]
    if artiklar:
        sorun.append(f"derleme artigi TASINDI ({len(artiklar)}): {[str(x.name) for x in artiklar[:5]]}")

    for p in PROJELER:
        n = _bobin_sayisi(hedef / p / "Core" / "Src" / "main.c")
        if n is None:
            sorun.append(f"{p}: NUM_COILS okunamadi")
        elif n != 7:
            sorun.append(f"{p}: NUM_COILS={n} (7 bekleniyordu) — BAYAT KAYNAK")
        else:
            eksik = _protokol_eksikleri(hedef / p / "Core" / "Src" / "main.c")
            if eksik:
                for e in eksik:
                    sorun.append(f"{p}: {e} — BAYAT KAYNAK")
            else:
                print(f"  dogrulandi : {p}  NUM_COILS=7, paket 121 bayt (kip alani VAR)")

    print()
    if sorun:
        for s in sorun:
            print(f"[HATA] {s}", file=sys.stderr)
        return 1

    print(f"HAZIR: {hedef}")
    print()
    # D0Ö.16 ek-2: ASCII — çıktı cp1254'e yönlendirilince emoji UnicodeEncodeError atıp sonraki satırları kesiyordu.
    print("UYARI: CubeIDE'de FLASH ETMEDEN ONCE:")
    print("   1) Project -> Clean...   (bayat nesne dosyasi kalmasin)")
    print("   2) Project -> Build      (yeni .elf URETILSIN)")
    print("   3) Run/Debug ile yukle")
    print("   4) DOGRULA: UART banner 'STM_READY: ... (7-ch ...' demeli.")
    print("      '5-ch' goruyorsan ESKI ikili yuklenmis demektir.")
    print("      Hizli kontrol:  python scripts/stm_firmware_kimligi.py")
    if yedek is not None:
        print()
        print(f"ONCEKI KOPYA (silinmedi): {yedek}")
        print("   Bu yedegi CubeIDE'de ACMAYIN / FLASHLAMAYIN (bayat Debug/*.elf tasiyabilir); yalniz farkinizi alin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
