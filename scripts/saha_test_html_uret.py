# -*- coding: utf-8 -*-
# Author: mertaygn
"""`docs/SAHA-TEST-LISTESI.md` → `docs/saha-test-listesi.html` içindeki `const VERI` bloğu.

⚠️ NEDEN BU BETİK VAR
=====================
Saha listesi İKİ dosyada duruyordu: okunan Markdown ve sahada işaretlenen HTML. İkisi elle
güncelleniyordu → HTML 5 kademede kalmıştı, Markdown'a eklenen senaryolar telefonda HİÇ
görünmüyordu. Bu, depoda tekrar eden "aynı kural N yerde" arızasının aynısı.

Artık **tek kaynak Markdown'dur**. HTML'in yalnız `const VERI = [ ... ];` bloğu üretilir;
tasarımına, betiğine, başlığına DOKUNULMAZ.

Kullanım:
    python scripts/saha_test_html_uret.py            # üret ve yaz
    python scripts/saha_test_html_uret.py --kontrol  # yalnız kıyasla (CI/test kapısı)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
MD = KOK / "docs" / "SAHA-TEST-LISTESI.md"
HTML = KOK / "docs" / "saha-test-listesi.html"

#: Üretilen bloğun sınırları — HTML'de BİREBİR bu iki dizge aranır.
BAS = "  const VERI = [\n"
SON = "  ];\n"

#: Kademe başlığı: "## Kademe 3 — AĞ VE BAĞLANTI (klinik gerçeği)"
_KADEME = re.compile(r"^##\s+Kademe\s+(\d+)\s+[—-]\s+(.+?)\s*$")
#: Alt başlık: "### 6A. Kurulum, açılış, sürüm"
_ALT = re.compile(r"^###\s+(?:\d+[A-ZÇĞİÖŞÜ]\.\s*)?(.+?)\s*$")
#: Tablo satırı: "| 1.1 | senaryo | beklenen |"
_SATIR = re.compile(r"^\|\s*([0-9]+\.[0-9]+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")

#: Kademe başlığının EKRANDA görünen adı.
#: ⚠️ `str.capitalize()` KULLANILMAZ: Türkçe'de "MOBİL".capitalize() → "Mobi̇l" (i + U+0307).
#: Ölçüldü (2026-09-12) — kapı bu yüzden kırmızı döndü. Ad tek tek yazılır, türetilmez.
ADLAR = {
    "1": "Hasta güvenliği",
    "2": "Güncelleme ve kurulum",
    "3": "Ağ ve bağlantı",
    "4": "Veri, AI, yetki",
    "5": "Dayanıklılık",
    "6": "Mobil",
    "7": "Bu turun değişiklikleri",
    "8": "Bilinen açıklar",
}

#: Kademe notu — Markdown'da serbest metin; HTML kartının alt başlığı.
NOTLAR = {
    "1": "Her yayında, istisnasız. Bu bölümdeki her başarısızlık yayını durdurur.",
    "2": "En taze kod, en yüksek risk. Güncelleme/kurulum kodu her değiştiğinde koşulur.",
    "3": "Klinik gerçeği: ağ kopar, IP değişir, internet gider. Yanlış renk = uyarı körlüğü.",
    "4": "Veri, dışa aktarma, AI ve kim-neyi-görür. Sessiz veri kaybı bu bölümde yakalanır.",
    "5": "Sürüm turlarında. Uzun süre açık kalan klinik makinesinde ortaya çıkan sınıf.",
    "6": "En az bakılan katman. Masaüstünde geçen senaryo burada geçmeyebilir: kabuk, izin, "
    "klavye, dosya yolu ve ağ farklı.",
    "7": "Bu turun regresyonu. Soru 'bozuldu mu' değil — 'istenen gerçekten oldu mu'.",
    "8": "Bunlar bulgu DEĞİL: bilinçli kararlar ve kapanmamış işler. Beklenen sonuç "
    "'belgelenen davranışın aynısı'. Farklıysa BELGE yanlıştır.",
}
#: Yayını durduran kademeler.
BLOK = {"1"}


def _kacir(metin: str) -> str:
    """JS tek-tırnaklı değil çift-tırnaklı dizge üretiyoruz → yalnız `"` ve `\\` kaçar."""
    return metin.replace("\\", "\\\\").replace('"', '\\"')


def _md_to_html(metin: str) -> str:
    """Markdown vurgularını HTML'e çevir. Tablo hücresi olduğu için kapsam dar."""
    metin = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", metin)
    metin = re.sub(r"`(.+?)`", r"<code>\1</code>", metin)
    return metin


def kademeleri_oku(md_metni: str) -> list[dict]:
    kademeler: list[dict] = []
    aktif: dict | None = None
    grup: dict | None = None

    for ham in md_metni.splitlines():
        k = _KADEME.match(ham)
        if k:
            no, ad = k.group(1), k.group(2)
            # Parantezli açıklamayı başlıktan at ("AĞ VE BAĞLANTI (klinik gerçeği)").
            ad = re.sub(r"\s*\(.*\)\s*$", "", ad).strip()
            aktif = {
                "no": no,
                "ad": ADLAR.get(no, ad),
                "blok": no in BLOK,
                "not": NOTLAR.get(no, ""),
                "gruplar": [],
            }
            kademeler.append(aktif)
            grup = None
            continue

        if aktif is None:
            continue

        a = _ALT.match(ham)
        if a:
            grup = {"alt": a.group(1), "items": []}
            aktif["gruplar"].append(grup)
            continue

        s = _SATIR.match(ham)
        if s:
            no, senaryo, beklenen = s.group(1), s.group(2), s.group(3)
            if senaryo.strip("-| ") == "" or senaryo.startswith("---"):
                continue
            if grup is None:
                grup = {"alt": None, "items": []}
                aktif["gruplar"].append(grup)
            grup["items"].append((no, _md_to_html(senaryo), _md_to_html(beklenen)))

    # Senaryosuz grupları at (ör. yalnız başlık olan bölümler).
    for kd in kademeler:
        kd["gruplar"] = [g for g in kd["gruplar"] if g["items"]]
    return [kd for kd in kademeler if kd["gruplar"]]


def veri_blogu(kademeler: list[dict]) -> str:
    satirlar = [BAS.rstrip("\n")]
    for kd in kademeler:
        satirlar.append("    {")
        satirlar.append(f'      no: "{kd["no"]}", ad: "{_kacir(kd["ad"])}", blok: {"true" if kd["blok"] else "false"},')
        satirlar.append(f'      not: "{_kacir(kd["not"])}",')
        satirlar.append("      gruplar: [")
        for g in kd["gruplar"]:
            bas = "        { " + (f'alt: "{_kacir(g["alt"])}", ' if g["alt"] else "") + "items: ["
            satirlar.append(bas)
            for no, senaryo, beklenen in g["items"]:
                satirlar.append(f'          ["{no}", "{_kacir(senaryo)}", "{_kacir(beklenen)}"],')
            satirlar.append("        ]},")
        satirlar.append("      ]")
        satirlar.append("    },")
    satirlar.append(SON.rstrip("\n"))
    return "\n".join(satirlar) + "\n"


def html_uret(mevcut_html: str, blok: str) -> str:
    bas = mevcut_html.index(BAS)
    son = mevcut_html.index(SON, bas) + len(SON)
    return mevcut_html[:bas] + blok + mevcut_html[son:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kontrol", action="store_true", help="yazma, yalnız kıyasla (kapı)")
    args = ap.parse_args()

    kademeler = kademeleri_oku(MD.read_text(encoding="utf-8"))
    toplam = sum(len(g["items"]) for kd in kademeler for g in kd["gruplar"])
    if toplam < 50:
        print(f"HATA: yalnizca {toplam} senaryo ayristirildi — Markdown bicimi degismis olabilir")
        return 2

    mevcut = HTML.read_text(encoding="utf-8")
    yeni = html_uret(mevcut, veri_blogu(kademeler))

    if args.kontrol:
        if yeni != mevcut:
            print("HTML, Markdown ile AYRISMIS -> python scripts/saha_test_html_uret.py")
            return 1
        print(f"HTML guncel ({len(kademeler)} kademe, {toplam} senaryo)")
        return 0

    HTML.write_text(yeni, encoding="utf-8")
    print(f"saha-test-listesi.html uretildi: {len(kademeler)} kademe, {toplam} senaryo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
