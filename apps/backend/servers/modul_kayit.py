# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) B1 — GELİŞTİRİCİ MODÜLÜ KAYIT DEFTERİ: `moduller/<kimlik>/modul.json` okuma / doğrulama + sınırların SUNUCUDA zorlanması
+ görünürlük ayarı (Y299: varsayılan GİZLİ, Ayarlar → "Geliştirici modülleri").

`modul.json` (şema 1) — geliştirici doldurur (kart bilgisi ayrıca `KART.md` formunda):
  kimlik (klasör adıyla AYNI, [a-z0-9-], 2–32) · ad {tr, en} (kişinin adı) · gelistirici · surum · baglanti (seri | wifi | ble | usb | sahte)
  · baglanti_ayrinti {…} (ör. seri: vid / pid / seri_no — ana STM kartının portu ASLA) · sinirlar {ad: [en az, en çok]} (frekans_hz,
  duty_yuzde, siddet_yuzde, sure_dk) · bekci_ms (kartın kalp atışı bekçisi, 1500–5000: kalp 500 ms'de bir → bekçi ≥ 3 × aralık; ana STM
  kartındaki keep-alive 0,5 s / deadman 1,5 s ile AYNI ilke — ölçüldü 19-11: bekçi = aralık iken gecikmede yanlış kesme) · kart {mikroislemci, surme_karti, bobin, …}.
Bozuk modül listede `hata` koduyla görünür (geliştirici ne düzelteceğini görsün) ama SEÇİLEMEZ.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

SEMA = 1
KIMLIK_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
BAGLANTILAR = ("seri", "wifi", "ble", "usb", "sahte")
#: kart bekçisi alt / üst sınırı (ms) — sunucu kalp atışı 500 ms; bekçi ≥ 3 aralık
BEKCI_MS_EN_AZ, BEKCI_MS_EN_COK = 1500, 5000
SINIR_ADLARI = ("frekans_hz", "duty_yuzde", "siddet_yuzde", "sure_dk")
AYAR_DOSYASI = "gelistirici_modulleri.json"
_ayar_kilidi = threading.Lock()


class ModulHatasi(Exception):
    """`kod` → arayüzde eylem söyleyen metin (`kontrol.modul.hata.<kod>`); `alan` hangi ayar / alan."""

    def __init__(self, kod: str, alan: str = ""):
        super().__init__(f"{kod}:{alan}" if alan else kod)
        self.kod = kod
        self.alan = alan


def kok() -> Path:
    """Modüller kökü: `PEMF_MODULLER_KOKU` (test / geliştirme) → donmuş pakette `_MEIPASS/moduller` → kaynakta depo kökü `moduller/`."""
    acik = os.environ.get("PEMF_MODULLER_KOKU", "").strip()
    if acik:
        return Path(acik)
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))) / "moduller"
    return Path(__file__).resolve().parents[3] / "moduller"


def _sayi(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def oku(klasor) -> dict:
    """Klasördeki `modul.json` → doğrulanmış sözlük; değilse `ModulHatasi(kod, alan)`."""
    klasor = Path(klasor)
    try:
        m = json.loads((klasor / "modul.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ModulHatasi("modulJsonYok") from None
    except (OSError, ValueError):
        raise ModulHatasi("modulJsonBozuk") from None
    if not isinstance(m, dict) or m.get("sema") != SEMA:
        raise ModulHatasi("semaUyumsuz", "sema")
    kimlik = m.get("kimlik")
    if not isinstance(kimlik, str) or not KIMLIK_DESENI.match(kimlik) or kimlik != klasor.name:
        raise ModulHatasi("kimlikGecersiz", "kimlik")
    ad = m.get("ad")
    if not isinstance(ad, dict) or not all(isinstance(ad.get(d), str) and ad.get(d).strip() for d in ("tr", "en")):
        raise ModulHatasi("adGecersiz", "ad")
    if not isinstance(m.get("surum"), str) or not m["surum"].strip():
        raise ModulHatasi("surumGecersiz", "surum")
    if m.get("baglanti") not in BAGLANTILAR:
        raise ModulHatasi("baglantiGecersiz", "baglanti")
    sinirlar = m.get("sinirlar")
    if not isinstance(sinirlar, dict) or not sinirlar:
        raise ModulHatasi("sinirlarGecersiz", "sinirlar")
    for k, v in sinirlar.items():
        if k not in SINIR_ADLARI or not (
            isinstance(v, list) and len(v) == 2 and all(_sayi(x) for x in v) and v[0] <= v[1]
        ):
            raise ModulHatasi("sinirlarGecersiz", str(k))
    bekci = m.get("bekci_ms")
    if not (isinstance(bekci, int) and not isinstance(bekci, bool) and BEKCI_MS_EN_AZ <= bekci <= BEKCI_MS_EN_COK):
        raise ModulHatasi("bekciGecersiz", "bekci_ms")
    if not (klasor / "surucu.py").is_file():
        raise ModulHatasi("surucuYok", "surucu.py")
    return m


def liste() -> list[dict]:
    """Kökteki bütün modüller (ada göre sıralı): geçerliler `{kimlik, ad, surum, baglanti, sinirlar, bekci_ms}`, bozuklar `{kimlik, hata}`."""
    k = kok()
    if not k.is_dir():
        return []
    out = []
    for d in sorted(p for p in k.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        try:
            m = oku(d)
        except ModulHatasi as e:
            out.append({"kimlik": d.name, "hata": e.kod, "alan": e.alan})
            continue
        out.append({a: m[a] for a in ("kimlik", "ad", "surum", "baglanti", "sinirlar", "bekci_ms")})
    return out


def bul(kimlik: str) -> tuple[Path, dict]:
    if not isinstance(kimlik, str) or not KIMLIK_DESENI.match(kimlik):
        raise ModulHatasi("modulYok")
    d = kok() / kimlik
    if not d.is_dir():
        raise ModulHatasi("modulYok")
    return d, oku(d)


def ayar_dogrula(modul: dict, ayar) -> dict:
    """Panelden gelen ayar → `modul.json` sınırları içinde mi (SUNUCUDA zorlanır; kart da kendi sınırını uygular). Bilinmeyen alan,
    sayı olmayan ya da sınır dışı değer → `ModulHatasi` (karta HİÇ gitmez)."""
    if not isinstance(ayar, dict) or not ayar:
        raise ModulHatasi("ayarGecersiz")
    sinirlar = modul["sinirlar"]
    temiz = {}
    for k, v in ayar.items():
        if k not in sinirlar:
            raise ModulHatasi("ayarBilinmeyen", str(k))
        if not _sayi(v):
            raise ModulHatasi("ayarSayiDegil", str(k))
        alt, ust = sinirlar[k]
        if not alt <= v <= ust:
            raise ModulHatasi("ayarSinirDisi", str(k))
        temiz[k] = v
    return temiz


def _ayar_yolu() -> Path:
    from utils.path_utils import get_app_data_directory

    return Path(get_app_data_directory()) / AYAR_DOSYASI


def gorunur_mu() -> bool:
    """Y299: modüller satılan üründe varsayılan GİZLİ — Ayarlar → "Geliştirici modülleri" açıkça açılmadıkça False."""
    try:
        return json.loads(_ayar_yolu().read_text(encoding="utf-8")).get("gorunur") is True
    except (OSError, ValueError, AttributeError):
        return False


def gorunur_yaz(gorunur: bool) -> bool:
    yol = _ayar_yolu()
    with _ayar_kilidi:
        fd, gecici = tempfile.mkstemp(dir=str(yol.parent), prefix=".gm-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"gorunur": bool(gorunur)}, fh)
            os.replace(gecici, yol)
        except OSError:
            try:
                os.unlink(gecici)
            except OSError:
                pass
            raise
    return bool(gorunur)
