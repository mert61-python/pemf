# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""THIRD_PARTY_LICENSES.md URETECI — atif (NOTICE) envanterini yeniden uretir.

KULLANIM:
    python scripts/lisans_envanteri_uret.py            # dosyayi yeniden yaz
    python scripts/lisans_envanteri_uret.py --kontrol  # yalnizca FARKI bildir (cikis 1)

⚠️ NEDEN VAR (denetim 2026-09-16). Envanter 2026-08-10'da donmustu ve `shap`, `grad-cam`,
`timm`, `captum`, `celldetection` gibi sonradan eklenen bagimliliklari icermiyordu. Elle
yazilan her envanter bayatlar; `README` surum tablosu ayni tuzaga UC kez dustu. Uretec
olmadan dorduncusu kacinilmazdi.

⚠️ IKI KAYNAK BIRLESTIRILIR — ve bu BILINCLI:

  1. `requirements.txt` — SEVK EDILEN calisma-zamani bagimliliklari. Bu liste HER ZAMAN
     okunabilir (temiz checkout, CI dahil) ve dagitilan seyin BEYANIDIR.
  2. `pemf-app-packages/base-deps.zip` icindeki `dist-info/METADATA` — gercek lisans
     METINLERI. Yalniz paket varsa okunur.

⚠️ NEDEN TEK BASINA (2) YETMEZ: PyInstaller cogu paketin metadata'sini AYIKLAR. Olculdu
(2026-09-16): pakette yalniz 26 paketin METADATA'si kaldi ve cogunun lisans alani BOS
("belirtilmemis"). Oysa `numpy`, `pillow`, `opencv-python`, `fastapi` gibi paketler
GERCEKTEN sevk ediliyor. Yalniz pakete bakan bir envanter, atif yuzeyini OLDUGUNDAN
KUCUK gosterir — ticari bir urunde bu, eksik atif demektir.

⚠️ `requirements-dev.txt` DISARIDA: ruff/pytest/pre-commit sevk EDILMEZ, atif gerektirmez.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_REQ = KOK / "requirements.txt"
_PAKET = KOK / "pemf-app-packages" / "base-deps.zip"
_HEDEF = KOK / "THIRD_PARTY_LICENSES.md"

_BASLIK_SONU = "## Dağıtılan pakette tespit edilen bileşenler"
_NPM_BASLIGI = "### Arayüz, site, DEMA ve launcher (npm)"

#: YH D3 (2026-10-22): npm envanteri TAMAM — her kilit dosyasındaki BÜTÜN çalışma-zamanı (geliştirme bağımlılığı OLMAYAN) girdiler.
#: Eskiden (I18N-0, Y157) yalnız çok dillilik kütüphaneleri listeleniyordu; react, expo … HİÇ yoktu (S-I18N kaydı) → atıf eksikti.
#: Sürüm ve lisans KİLİT DOSYASINDAN okunur (`package-lock.json` → `packages["node_modules/<ad>"]`); tahmin YAZILMAZ.
#: ⚠️ Kilitteki "çalışma-zamanı" kümesi derleme araçlarının bir kısmını da (metro, babel …) kapsar — fazla atıf güvenli taraftır.
#: Anahtar = tabloda "Kullanan" sütununa yazılan yüzey adı.
_NPM_KILITLERI = {
    "arayüz": KOK / "apps" / "ui" / "package-lock.json",
    "site": KOK / "apps" / "web" / "package-lock.json",
    "DEMA": KOK / "dema-terapi-simülatörü" / "package-lock.json",
    "launcher": KOK / "launcher" / "app" / "package-lock.json",
}

#: Paket adi -> lisans. `dist-info/METADATA` okunamayan paketler icin elle dogrulanmis
#: degerler. ⚠️ Her satir PyPI sayfasindan dogrulanmistir; tahmin YAZILMAZ.
_BILINEN_LISANSLAR = {
    "fastapi": "MIT",
    "uvicorn": "BSD-3-Clause",
    "starlette": "BSD-3-Clause",
    "pydantic": "MIT",
    "numpy": "BSD-3-Clause",
    "scipy": "BSD-3-Clause",
    "pandas": "BSD-3-Clause",
    "matplotlib": "PSF-based (matplotlib licence)",
    "pillow": "MIT-CMU",
    "opencv-python": "Apache-2.0",
    "opencv-python-headless": "Apache-2.0",
    "onnxruntime": "MIT",
    "scikit-learn": "BSD-3-Clause",
    "xgboost": "Apache-2.0",
    "joblib": "BSD-3-Clause",
    "shap": "MIT",
    "captum": "BSD-3-Clause",
    "timm": "Apache-2.0",
    "grad-cam": "MIT",
    "ttach": "MIT",
    "celldetection": "Apache-2.0",
    "safetensors": "Apache-2.0",
    "slicer": "MIT",
    "paho-mqtt": "EPL-2.0 / EDL-1.0",
    "pyserial": "BSD-3-Clause",
    "zeroconf": "LGPL-2.1",
    "reportlab": "BSD-3-Clause",
    "python-multipart": "Apache-2.0",
    "httpx": "BSD-3-Clause",
    "supabase": "MIT",
    "sentry-sdk": "MIT",
    "pyyaml": "MIT",
    "imageio-ffmpeg": "BSD-2-Clause",
    "ultralytics": "AGPL-3.0",
}


#: `requirements.txt`te listeli ama URUNLE SEVK EDILMEYEN araclar. Atif gerektirmezler:
#: kullanicinin eline gecen pakette bulunmazlar (olculdu — base-deps.zip'te METADATA'lari yok).
#: ⚠️ Buraya bir sey eklemek "bu paket dagitilmiyor" beyanidir; olcmeden eklemeyin.
_SEVK_EDILMEYEN = {"pyinstaller", "pytest"}


def _req_paketleri() -> list[str]:
    """`requirements.txt`teki SEVK EDILEN paket adlari (yorum/secenek satirlari haric)."""
    adlar = []
    for satir in _REQ.read_text(encoding="utf-8").splitlines():
        s = satir.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        ad = re.split(r"[=<>!~\[; ]", s)[0].strip()
        if ad:
            adlar.append(ad.lower())
    return sorted(set(adlar))


def metadata_lisansi(meta: str) -> str:
    """Bir `dist-info/METADATA` metninden lisans alanini cikar.

    ⚠️ `License-Expression` ONCELIKLI (PEP 639). Bu alani okumayan bir ayristirici, modern
    paketlerin lisansini BOS gorur. Olculdu (2026-09-16, sevk edilen base-deps.zip):
    100 paketin **30'unun** lisansi eski okuyucuyla BOS cikiyordu, yeni okuyucuyla 0.

    ⚠️ BUGUN GIZLI BIR UYUMSUZLUK YOK: iki okuyucu da kopyleft kumesini AYNI buluyor
    (`{ultralytics}`). Yani bu, yasanmis bir ihlal degil, GELECEK icin acik bir delikti —
    `License-Expression: AGPL-3.0` diyen yeni bir paket kopyleft kapisina GORUNMEZ olurdu.

    ⚠️ TEK KAYNAK: `tests/test_license_surface.py` bu fonksiyonu IMPORT eder, kendi
    kopyasini yazmaz. (Bu depo 2026-09-15'te "ayni kural iki yerde -> sessizce ayristi"
    arizasini UC ayri noktada yasadi.)

    ⚠️ D6.43 (B-11.15, 2026-10-28): oncelik `License-Expression` > LISANS ADI olan `License:` > TUM `Classifier: License ::`
    > ham `License:`. Eskiden `License:` alaninin ILK SATIRI siniflandiricidan once geliyordu ve baslik yalniz ilk 80
    satirda taraniyordu → lisans METNINI `License:` alanina koyan paketlerde (numpy, scipy, matplotlib, kiwisolver,
    scikit-image: siniflandirici 82.–981. satirda) NOTICE hucresi "Copyright (c) …" / "=====" / "Files: *" /
    "Dual License" oluyordu (7 satir, olculdu). `License:` bir lisans adiysa ve siniflandirici FARKLI bir aile
    soyluyorsa ikisi de yazilir (pi-heif: `BSD-3-Clause` + LGPLv3 siniflandiricisi — paket kendi icinde celisir; hangisinin
    baglayici oldugu hukuki sorudur, belge ikisini de gosterir). Kapi: tests/test_notice_lisans_hucresi_LISANS_ADI_D6_43.py
    """
    ifade = klasik = ""
    siniflar: list[str] = []
    for satir in _metadata_basligi(meta):
        if satir.startswith("License-Expression:"):
            ifade = satir.split(":", 1)[1].strip()
        elif satir.startswith("License:"):
            klasik = klasik or satir.split(":", 1)[1].strip()
        elif satir.startswith("Classifier: License ::"):
            s = satir.split("::")[-1].strip()
            if s and s not in siniflar:
                siniflar.append(s)
    if ifade:
        return ifade
    if lisans_adi_mi(klasik):
        farkli = [s for s in siniflar if not (_aileler(s) & _aileler(klasik))]
        return f"{klasik} (sınıflandırıcı: {' / '.join(farkli)})" if farkli else klasik
    return " / ".join(siniflar) or klasik


def _metadata_basligi(meta: str) -> list[str]:
    """METADATA BASLIK satirlari: ilk BOS satira kadar (sonrasi README govdesi). ⚠️ D6.43: eski `[:80]` siniri, `License:`
    alanina cok satirli lisans metni koyan paketlerin siniflandiricisini kesiyordu (numpy: 981. satir)."""
    out = []
    for satir in meta.splitlines():
        if (
            satir == ""
        ):  # ⚠️ YALNIZ tam boş satır: çok satırlı `License:` metnindeki boşluklu satırlar ("        ") başlıktır
            break
        out.append(satir)
    return out


#: Lisans AILESI imzalari (`lisans_adi_mi` ve aile karsilastirmasi). Sira onemli: LGPL / AGPL, GPL'den ONCE.
_AILELER = (
    ("LGPL", re.compile(r"LGPL|LESSER\s+GENERAL\s+PUBLIC")),
    ("AGPL", re.compile(r"AGPL|AFFERO")),
    ("GPL", re.compile(r"(?<![LA])GPL|(?<!LESSER )GENERAL\s+PUBLIC\s+LICEN[CS]E")),
    ("BSD", re.compile(r"BSD")),
    ("MIT", re.compile(r"\bMIT\b")),
    ("APACHE", re.compile(r"APACHE")),
    ("MPL", re.compile(r"\bMPL\b|MOZILLA")),
    ("ISC", re.compile(r"\bISC\b")),
    ("PSF", re.compile(r"\bPSF\b|PYTHON\s+SOFTWARE\s+FOUNDATION")),
    ("EPL", re.compile(r"\bEPL\b|\bEDL\b|ECLIPSE")),
    ("HPND", re.compile(r"\bHPND\b|HISTORICAL\s+PERMISSION")),
    ("UNLICENSE", re.compile(r"UNLICENSE|PUBLIC\s+DOMAIN|\bCC0\b")),
    ("ZLIB", re.compile(r"\bZLIB\b")),
)


def _aileler(lisans: str) -> set[str]:
    u = (lisans or "").upper()
    return {ad for ad, desen in _AILELER if desen.search(u)}


def lisans_adi_mi(lisans: str) -> bool:
    """Hucre bir LISANS ADI / SPDX kimligi mi (bilinen bir aile imzasi tasiyan kisa metin) — yoksa lisans metninin ilk
    satiri mi ("Copyright (c) …", "=====", "Files: *", "Dual License", "License agreement for …")?"""
    s = (lisans or "").strip()
    return bool(s) and len(s) <= 120 and not s.lower().startswith("copyright") and bool(_aileler(s))


#: LGPL biçimleri — KASITLI muaf (dinamik bağlamada kapalı kaynak ürünle dağıtılabilir; bu projede öyle kullanılır).
#: ⚠️ 4A-3.6 (A3 incelemesi): uzun adın ardındaki `[^,;()]*` KALDIRILDI — virgül/parantez görene dek açgözlü siliyor, aynı
#: cümledeki "… and GNU General Public License v3" / "and GPL-2.0" / "and GNU Affero …"yu da siliyordu (kopyleft GÖRÜNMEZDİ).
#: Sürüm/"or later" kuyruğu silinmese de GPL imzası taşımaz.
_LGPL = re.compile(
    r"\bLGPL[\w.+-]*|GNU\s+(?:LIBRARY\s+OR\s+)?LESSER\s+GENERAL\s+PUBLIC\s+LICENSE|\bLESSER\s+GENERAL\s+PUBLIC"
)
#: "GPL-compatible" (PSF / BSD türevlerinin ibaresi) kopyleft DEĞİL — LGPL gibi aramadan önce silinir (4A-3.6 yanlış pozitifi).
_GPL_UYUMLU = re.compile(r"\bGPL[-\s]+COMPATIBLE\b")
#: Kopyleft imzaları (LGPL bölümleri SİLİNDİKTEN sonra aranır): yalın `GPL`, `GPL-3.0`, `GPLv2+`, `AGPL…`, uzun adlar.
#: ⚠️ 4-A inc. S-A3.2 (Y123 önerilen, 2026-10-11): GPL ailesi DIŞINDAKİ güçlü kopyleftler de — EUPL (European Union Public
#: Licence), SSPL (Server Side Public License), OSL (Open Software License). Bugün pakette yoklar (yanlış alarm üretmez).
_KOPYLEFT = re.compile(
    r"\bA?GPL(?:\b|[-V]?\d)|\bGNU\s+(?:AFFERO\s+)?GENERAL\s+PUBLIC\b|\bAFFERO\b"
    r"|\bEUPL\b|\bEUROPEAN\s+UNION\s+PUBLIC\s+LICEN[CS]E\b|\bSSPL\b|\bSERVER\s+SIDE\s+PUBLIC\s+LICENSE\b"
    r"|\bOSL-\d|\bOPEN\s+SOFTWARE\s+LICEN[CS]E\b"
)


def kopyleft_mu(lisans: str) -> bool:
    """Lisans metni kaynak açma yükümlülüğü doğuran (AGPL/GPL) bir bileşen mi — TEK KAYNAK (`tests/test_license_surface`).

    ⚠️ D4.08 (B-10.94, 2026-10-10): eski sınıflandırıcı alt-dize listesine bakıyordu ve metinde "LGPL" geçerse TAMAMINI
    muaf sayıyordu → yalın `License: GPL`, bileşik `LGPL-2.1 AND GPL-3.0` ve `GNU Affero General Public License v3`
    kopyleft kapısına GÖRÜNMEZDİ (ölçüldü). Artık önce yalnız LGPL BÖLÜMLERİ çıkarılır, kalan metinde GPL aranır."""
    u = _GPL_UYUMLU.sub(" ", _LGPL.sub(" ", (lisans or "").upper()))
    return bool(_KOPYLEFT.search(u))


def paket_lisanslari(paket: Path | None = None) -> dict[str, tuple[str, str]]:
    """Sevk edilen pakette (paket adi -> (surum, lisans)). Paket yoksa bos sozluk."""
    yol = paket or _PAKET
    out: dict[str, tuple[str, str]] = {}
    if not yol.exists():
        return out
    with zipfile.ZipFile(yol) as z:
        for n in z.namelist():
            m = re.match(r"PEMF_Backend/_internal/([^/]+)-([^/]+)\.dist-info/METADATA$", n)
            if not m:
                continue
            lic = metadata_lisansi(z.read(n).decode("utf-8", "replace"))
            out[m.group(1).lower().replace("_", "-")] = (m.group(2), lic)
    return out


def kopyleft_metadata_mu(meta: str) -> bool:
    """Bir `dist-info/METADATA` kopyleft mi — TÜM lisans alanlarına bakar (License-Expression, License, HER
    `Classifier: License ::`).

    ⚠️ 4A-3.7 (A3 incelemesi): kopyleft kapısı lisansı `metadata_lisansi`nin TEK alanından (NOTICE tablosunun gösterdiği
    değer: License-Expression > License > İLK sınıflandırıcı) okuyordu → `License: UNKNOWN`, serbest metin (`Dual License`,
    `Copyright (c) …`) ya da ilk sınıflandırıcısı MIT olan bir paketin GPL sınıflandırıcısı kapıya GÖRÜNMEZDİ. NOTICE metni
    değişmez (o hâlâ `metadata_lisansi`); yalnız kopyleft KARARI tüm alanlardan verilir.
    ⚠️ D6.43: başlık TAMAMI taranır (eski `[:80]` sınırı uzun `License:` metninin ardındaki sınıflandırıcıyı — numpy'de
    981. satır — kopyleft kapısına da GÖRÜNMEZ yapıyordu)."""
    for satir in _metadata_basligi(meta):
        if satir.startswith(("License-Expression:", "License:")) and kopyleft_mu(satir.split(":", 1)[1]):
            return True
        if satir.startswith("Classifier: License ::") and kopyleft_mu(satir.split("::", 1)[1]):
            return True
    return False


def paket_kopyleft(paket: Path | None = None) -> set[str]:
    """Sevk edilen pakette kopyleft olan paket adları (`kopyleft_metadata_mu`). Paket yoksa boş küme."""
    yol = paket or _PAKET
    out: set[str] = set()
    if not yol.exists():
        return out
    with zipfile.ZipFile(yol) as z:
        for n in z.namelist():
            m = re.match(r"PEMF_Backend/_internal/([^/]+)-([^/]+)\.dist-info/METADATA$", n)
            if m and kopyleft_metadata_mu(z.read(n).decode("utf-8", "replace")):
                out.add(m.group(1).lower().replace("_", "-"))
    return out


def _paket_metadata_lisanslari() -> dict[str, tuple[str, str]]:
    return paket_lisanslari()


def envanter() -> list[tuple[str, str, str]]:
    """(paket, surum, lisans) — ad sirali. Surum/lisans bilinmiyorsa '—'."""
    meta = _paket_metadata_lisanslari()
    satirlar = []
    for ad in _req_paketleri():
        if ad in _SEVK_EDILMEYEN:
            continue
        surum, lisans = meta.get(ad, ("", ""))
        if not lisans:
            lisans = _BILINEN_LISANSLAR.get(ad, "")
        satirlar.append((ad, surum or "—", lisans or "⚠️ doğrulanmadı"))
    # Pakette olup requirements'ta olmayanlar (dolayli bagimliliklar) da atif gerektirir.
    reqler = set(_req_paketleri())
    for ad, (surum, lisans) in sorted(meta.items()):
        if ad not in reqler:
            satirlar.append((ad, surum or "—", lisans or _BILINEN_LISANSLAR.get(ad, "belirtilmemiş")))
    return sorted(satirlar, key=lambda t: t[0])


def _npm_lisansi(p: dict) -> str:
    """Kilit girdisinin lisansı: SPDX dizesi; eski biçimler (`{"type": …}` / liste) dizeye indirgenir."""
    li = p.get("license")
    if isinstance(li, dict):
        li = li.get("type")
    elif isinstance(li, list):
        li = " OR ".join(str(x.get("type") if isinstance(x, dict) else x) for x in li)
    return str(li or "").strip()


def _npm_girdileri() -> dict[tuple[str, str], tuple[str, set[str]]]:
    """(ad, sürüm) → (lisans, {kullanan yüzeyler}) — geliştirme bağımlılıkları (`dev` / `devOptional`) ve çalışma alanı bağları HARİÇ."""
    gorulen: dict[tuple[str, str], tuple[str, set[str]]] = {}
    for yuzey, kilit in _NPM_KILITLERI.items():
        if not kilit.exists():
            continue
        paketler = json.loads(kilit.read_text(encoding="utf-8")).get("packages") or {}
        for yol, p in paketler.items():
            if not yol or p.get("dev") or p.get("devOptional") or p.get("link"):
                continue
            anahtar = (yol.rsplit("node_modules/", 1)[-1], str(p.get("version") or "—"))
            _lisans, yuzeyler = gorulen.setdefault(anahtar, (_npm_lisansi(p) or "⚠️ doğrulanmadı", set()))
            yuzeyler.add(yuzey)
    return gorulen


def npm_envanteri() -> list[tuple[str, str, str]]:
    """(paket, sürüm, lisans) — bütün kilit dosyalarının çalışma-zamanı girdileri. Ad + sürüm tekil, ad sıralı."""
    return sorted((a, s, li) for (a, s), (li, _) in _npm_girdileri().items())


#: SPDX ifadesi belirteçleri: parantez ya da boşluksuz kelime (`AND` / `OR` / `WITH` / lisans kimliği).
_SPDX_BELIRTEC = re.compile(r"\(|\)|[^\s()]+")
#: YLI-A2.1: bağlaçlar SPDX'teki gibi BÜYÜK harfle eşlenir — küçük `or` / `and` serbest metindir (`GPL-3.0 or later` bir seçim DEĞİL,
#: "ya da sonraki sürüm"dür) → ifade ayrıştırılamaz → metnin tamamı (güvenli taraf).
_SPDX_BAGLACLARI = ("AND", "OR", "WITH")
#: YLI-A2.1: lisans KİMLİĞİ olmayan sözcükler — `OR` seçeneği olarak "izin veren seçenek" SAYILMAZ (`GPL-3.0 OR later`;
#: `AGPL-3.0 OR Commercial`: ticari lisans satın alınmadıkça seçilebilen tek lisans AGPL'dir) → ifade ayrıştırılamaz → güvenli taraf.
_KIMLIK_DISI = re.compile(
    r"LATER|ONLY|COMMERCIAL|PROPRIETARY|UNLICENSED|SEE|CUSTOM|OTHER|NONE|(?:LICENSE|DOCUMENT)REF-\S*", re.I
)


def lisans_belirsiz_mu(lisans: str) -> bool:
    """YLI-A2.1: kilitteki lisans dizesinden kopyleft kararı VERİLEMEZ mi — boş / "doğrulanmadı" / `UNLICENSED` (npm: kullanım izni
    verilmemiş) / `SEE LICENSE IN <dosya>` (lisans ifadede değil dosyada). Kapı bunları [SAHİBE] el ile bakılacak liste olarak ister."""
    u = (lisans or "").strip()
    return not u or "doğrulanmadı" in u or u.upper() == "UNLICENSED" or u.upper().startswith("SEE LICENSE IN")


def spdx_kopyleft_mu(ifade: str) -> bool:
    """SPDX lisans İFADESİ kaynak açma yükümlülüğü doğuruyor mu (YH D3). Yaprak kararı `kopyleft_mu` (TEK KAYNAK); bağlaçlar SPDX
    önceliğiyle: `WITH` > `AND` > `OR`. `A OR B` → seçim hakkı: YALNIZ hepsi kopyleftse kopyleft (`BSD-3-Clause OR GPL-2.0` DEĞİL);
    `A AND B` → biri kopyleftse kopyleft; `X WITH istisna` → X. Ayrıştırılamayan ifade → metnin tamamına `kopyleft_mu` (güvenli taraf)."""
    belirtecler = _SPDX_BELIRTEC.findall(ifade or "")
    konum = 0

    def bak() -> str | None:
        return belirtecler[konum] if konum < len(belirtecler) else None

    def al() -> str:
        nonlocal konum
        konum += 1
        return belirtecler[konum - 1]

    def birim() -> bool:
        if bak() == "(":
            al()
            sonuc = veya()
            if bak() != ")":
                raise ValueError("kapanmayan parantez")
            al()
            return sonuc
        if bak() in (None, ")", *_SPDX_BAGLACLARI):
            raise ValueError("lisans kimliği bekleniyordu")
        kimlik = al()
        if _KIMLIK_DISI.fullmatch(kimlik) or kimlik.upper() in _SPDX_BAGLACLARI:
            raise ValueError("lisans kimliği değil")
        sonuc = kopyleft_mu(kimlik)
        if bak() == "WITH":
            al()
            al()
        return sonuc

    def ve() -> bool:
        sonuc = birim()
        while bak() == "AND":
            al()
            sonuc = birim() or sonuc
        return sonuc

    def veya() -> bool:
        sonuc = ve()
        while bak() == "OR":
            al()
            sonuc = ve() and sonuc
        return sonuc

    try:
        sonuc = veya()
        if konum != len(belirtecler):
            raise ValueError("artık belirteç")
        return sonuc
    except (ValueError, IndexError):
        return kopyleft_mu(ifade)


def npm_kopyleft() -> list[tuple[str, str, str]]:
    """npm envanterinde kopyleft (SPDX ifadesiyle karar verilmiş) girdiler — kapı: `tests/test_YH_D3_npm_lisans_envanteri.py`."""
    return [(a, s, li) for a, s, li in npm_envanteri() if spdx_kopyleft_mu(li)]


def _tablo(satirlar) -> str:
    bas = "| Paket | Sürüm | Lisans |\n|---|---|---|\n"
    return bas + "\n".join(f"| `{a}` | {s} | {li} |" for a, s, li in satirlar) + "\n"


def _npm_bolumu() -> str:
    girdiler = _npm_girdileri()
    if not girdiler:
        return ""
    sira = list(_NPM_KILITLERI)
    satirlar = "\n".join(
        f"| `{a}` | {s} | {li} | {', '.join(sorted(yz, key=sira.index))} |"
        for (a, s), (li, yz) in sorted(girdiler.items())
    )
    kaynaklar = " + ".join(f"`{k.relative_to(KOK).as_posix()}`" for k in _NPM_KILITLERI.values() if k.exists())
    return (
        f"\n{_NPM_BASLIGI}\n\n"
        f"Kaynak: {kaynaklar} — her kilit dosyasındaki BÜTÜN çalışma-zamanı girdileri\n"
        "(geliştirme bağımlılıkları hariç; sürüm ve lisans kilit dosyasından). Küme derleme araçlarının bir kısmını da kapsar\n"
        "(fazla atıf güvenli taraftır). Çift lisanslı girdilerde (`A OR B`) izin veren seçenek kullanılır.\n\n"
        "| Paket | Sürüm | Lisans | Kullanan |\n|---|---|---|---|\n" + satirlar + "\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kontrol", action="store_true", help="yazma; yalniz fark varsa 1 don")
    a = ap.parse_args()

    # ⚠️ D4.08 (B-10.94, 2026-10-10): paket YOKKEN `paket_lisanslari` boş sözlük döner ve tablo yalnız requirements'tan
    # kurulur — dolaylı bağımlılıkların atfı sessizce SİLİNİRDİ (ölçüldü: 113 → ~44 satır, "[OK]", çıkış 0). Paketsiz
    # ortamda ne yazma ne "güncel" hükmü: ikisi de yarım kaynakla verilir → çıkış 2, dosya DEĞİŞMEZ.
    if not _PAKET.exists():
        print(
            f"[HATA] {_PAKET.name} yok ({_PAKET}) — lisans METINLERI okunamaz; envanter yarim kalir. "
            f"{'Kontrol' if a.kontrol else 'Yazma'} REDDEDILDI; paketi uretip/indirip yeniden kosun."
        )
        return 2

    satirlar = envanter()
    mevcut = _HEDEF.read_text(encoding="utf-8")
    bas = mevcut.index(_BASLIK_SONU)
    ust = mevcut[:bas]
    yeni_govde = (
        f"{_BASLIK_SONU}\n\n"
        "Aşağıdaki liste **üretilmiştir** (`scripts/lisans_envanteri_uret.py`); elle\n"
        "düzenlemeyin. Kaynaklar: `requirements.txt` (sevk edilen çalışma-zamanı\n"
        "bağımlılıkları) + `pemf-app-packages/base-deps.zip` içindeki `dist-info/METADATA`.\n\n"
        "⚠️ PyInstaller çoğu paketin metadata'sını ayıkladığı için sürüm/lisans alanları\n"
        "pakette bulunamayan satırlarda doğrulanmış sabit tablodan gelir.\n\n" + _tablo(satirlar) + _npm_bolumu()
    )
    yeni = ust + yeni_govde

    if a.kontrol:
        if yeni.strip() != mevcut.strip():
            print("[FARK] THIRD_PARTY_LICENSES.md guncel DEGIL -> `python scripts/lisans_envanteri_uret.py`")
            return 1
        print("[OK] envanter guncel")
        return 0

    _HEDEF.write_text(yeni, encoding="utf-8")
    print(f"[OK] {_HEDEF.name} yeniden uretildi: {len(satirlar)} bilesen")
    dogrulanmamis = [a_ for a_, _, li in satirlar if "doğrulanmadı" in li]
    if dogrulanmamis:
        print(f"[!!] lisansi DOGRULANMAMIS {len(dogrulanmamis)} paket: {dogrulanmamis}")
        print("     `_BILINEN_LISANSLAR`a PyPI'dan dogrulayarak ekleyin (tahmin YAZMAYIN).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
