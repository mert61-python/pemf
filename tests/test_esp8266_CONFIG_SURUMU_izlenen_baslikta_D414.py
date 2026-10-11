# -*- coding: utf-8 -*-
"""D4.14 (B-8.1 · A-41) — 8266 firmware'inin EEPROM yapılandırma SÜRÜMÜ izlenen (sır olmayan) başlıkta ve README'nin ilanıyla aynı.

ARIZA: `.ino` açılıştaki sürüm denetiminde `CONFIG_VERSION`'ı kullanıyordu; makro YALNIZ skip-worktree'li `Secrets.h`'de tanımlıydı.
[D4] artışı (1→2, README) yalnız sahibin yerel `Secrets.h`'sinde yapıldı, hiç commit'lenmedi → HEAD'den derlenen firmware 1 taşıyor;
v2 kartla dönüşümlü yakmada her seferinde WiFi bölgesi siliniyor (denetim EEPROM taklidiyle ölçtü). A-41 (önerilen, uygulandı): sır
OLMAYAN değerler git'te izlenir.

Ölçüm: `.ino`'nun yorum-soyulmuş metninden sürüm denetiminin kullandığı makro adı alınır (karşılaştırma + `EEPROM.write` AYNI ad);
`#include "…"` kapanışı izlenerek makronun TÜM tanımları toplanır. ⚠️ Skip-worktree / sır dosyaları (`secrets_backup._SW_DOSYALAR` +
`git ls-files -v` 'S') ÇALIŞMA KOPYASINDAN OKUNMAZ — yalnız `git show HEAD:` (sahibin yerel sırları görülmez, test HEAD'i ölçer).
C derleyicisi bu makinede yok → önişlemci yaklaşığı (yalnız nesne-benzeri `#define`, yorumlar `c_soy` ile soyulur).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from c_soyucu import c_soy

from build_tools.secrets_backup import _SW_DOSYALAR

KOK = Path(__file__).resolve().parents[1]
ESP_REL = "firmware/esp8266_pemf_coil"
INO_REL = f"{ESP_REL}/esp8266_pemf_coil.ino"
README = KOK / ESP_REL / "README.md"


def _git(*a: str) -> str:
    return subprocess.run(
        ["git", *a], cwd=KOK, capture_output=True, text=True, encoding="utf-8", timeout=60, check=True
    ).stdout


def _sir_dosyalari() -> set[str]:
    sw = {s[2:].strip() for s in _git("ls-files", "-v", ESP_REL).splitlines() if s[:1] == "S"}
    return sw | set(_SW_DOSYALAR)


def _oku(rel: str, sirlar: set[str]) -> str:
    if rel in sirlar:
        return _git("show", f"HEAD:{rel}")  # çalışma kopyası (yerel sırlar) OKUNMAZ
    return (KOK / rel).read_text(encoding="utf-8", errors="replace")


def _tanimlar(rel: str, sirlar: set[str], gorulen: set[str]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for satir in c_soy(_oku(rel, sirlar)).splitlines():
        m = re.match(r'\s*#\s*include\s+"([^"]+)"', satir)
        if m:
            alt = (Path(rel).parent / m.group(1)).as_posix()
            if alt not in gorulen and (alt in sirlar or (KOK / alt).is_file()):
                gorulen.add(alt)
                out += _tanimlar(alt, sirlar, gorulen)
            continue
        m = re.match(r"\s*#\s*define\s+([A-Za-z_]\w*)\s+(\S.*?)\s*$", satir)
        if m:
            out.append((m.group(1), m.group(2), rel))
    return out


def _surum_makrosu() -> str:
    ino = c_soy((KOK / INO_REL).read_text(encoding="utf-8", errors="replace"))
    karsi = re.findall(r"storedVersion\s*!=\s*([A-Za-z_]\w*)", ino)
    yaz = re.findall(r"EEPROM\.write\(\s*EEPROM_CONFIG_VER_ADDR\s*,\s*([A-Za-z_]\w*)\s*\)", ino)
    assert len(karsi) == 1 and len(yaz) == 1, f"çıpa: sürüm denetimi bulunamadı (karşılaştırma {karsi}, yazım {yaz})"
    assert karsi == yaz, (
        f"sürüm denetimi ile EEPROM'a yazılan sürüm FARKLI makro: {karsi[0]} ≠ {yaz[0]} (her açılışta wipe)"
    )
    return karsi[0]


def test_KRITIK_sayilan_surum_makrosu_IZLENEN_baslikta_ve_README_ile_AYNI_B8_1():
    sirlar = _sir_dosyalari()
    assert any(s.endswith("Secrets.h") for s in sirlar), "VAKUM: sır dosyası listesi boş"
    ad = _surum_makrosu()
    tanimlar = [(d, r) for (n, d, r) in _tanimlar(INO_REL, sirlar, {INO_REL}) if n == ad]
    assert len(tanimlar) == 1, f"{ad} include kapanışında {len(tanimlar)} kez tanımlı (belirsiz/yok): {tanimlar}"
    deger, dosya = tanimlar[0]
    assert dosya not in sirlar, (
        f"{ad} yalnız skip-worktree/sır dosyasında ({dosya}) — HEAD'den derlenen firmware sahibin yerel değerini TAŞIMAZ"
    )
    ilan = re.findall(r"CONFIG_VERSION`?\s*1→(\d+)", README.read_text(encoding="utf-8"))
    assert len(ilan) == 1, f"çıpa: README sürüm ilanı (1→N) bulunamadı: {ilan}"
    assert int(deger.strip("()")) == int(ilan[0]), (
        f"HEAD'deki {ad}={deger} ({dosya}) README'nin ilan ettiği {ilan[0]} DEĞİL — v{ilan[0]} kartla dönüşümlü yakmada WiFi silinir"
    )


def test_KARSIT_KANIT_sir_dosyasi_HEAD_blobundan_okunur():
    """Ölçüm aracı skip-worktree çalışma kopyasına bakmıyor: sır dosyası içeriği HEAD blobuyla AYNI (içerik basılmaz)."""
    sirlar = _sir_dosyalari()
    rel = f"{ESP_REL}/Secrets.h"
    assert rel in sirlar
    ayni = _oku(rel, sirlar) == _git("show", f"HEAD:{rel}")
    assert ayni, "sır dosyası HEAD blobundan okunmadı"
