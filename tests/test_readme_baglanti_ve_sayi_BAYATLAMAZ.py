# -*- coding: utf-8 -*-
"""README bağlantıları ÇÖZÜLSÜN, sayısal iddialar KAYNAKLA UYUŞSUN.

🔴 ÖLÇÜLEN DURUM (2026-09-21, F5 turu): depodaki **244 yerel bağlantının 54'ü KIRIKTI**
(%22). Örüntü tekti: `../utils/README.md`, `../servers/README.md`, `../docs/ARCHITECTURE.md`
— hepsi **F1–F4 klasör taşımalarının artığı**. Kod tarafında aynı sınıf bu depoda üç kez
ısırdı (beş-biçimli dizin adı · betiğin kendi konumunu kırması · F4'ün `tools/e2e_*.py`yi
iki gün ölü bırakması); belge tarafında ise **hiç ölçülmemişti**.

Ayrıca `tools/README.md` STM paketini "88 bayt" diyordu; kaynak `assert PKT_SIZE == 121`
(2026-09-10'da 5→7 bobin). Belge, protokolü hata ayıklayan kişiyi yanlış sayıyla karşılıyordu.

BU KAPI ÜÇ ŞEY İDDİA EDER:
  1. Takipli her `.md` içindeki yerel bağlantı ÇÖZÜLMELİ
  2. Kök README'nin dizin haritasındaki her girdi DİSKTE olmalı (silinmiş dizin satırı kalmasın)
  3. `tools/README.md`'deki paket boyutu kaynaktaki `PKT_SIZE` ile AYNI olmalı

⚠️ ARAÇ TUZAKLARI — üçü de bu turda ölçülerek bulundu, kapı bunlara karşı bağışık:
  · Kod çitleri (```) ATLANIR: `docs/VERIFICATION.md` içindeki PowerShell satırları
    (`$p.WorkingSet64/1MB`) markdown bağlantısı sanılıyordu.
  · `%20` gibi kaçışlar ÇÖZÜLÜR: `offline%20dağıtım/...` görüntüleyicide çalışır.
  · `git ls-files -z` ŞART: Türkçe adlı dizin (`dema-terapi-simülatörü/`) düz `ls-files`
    ile sekizlik kaçışla gelir ve okunamaz; ilk aracım onu SESSİZCE atlıyordu.
"""

from __future__ import annotations

import re
import subprocess
import urllib.parse
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)

#: Kullanıcının OLUŞTURACAĞI dosyalar — yokluğu arıza değildir.
MUAF_ADLAR = (".env",)


def _md_dosyalari() -> list[str]:
    ham = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=KOK, capture_output=True, timeout=180).stdout
    return [x.decode("utf-8") for x in ham.split(b"\x00") if x]


def _cit_disi(metin: str) -> str:
    """Kod çiti (```) içindeki satırları BOŞLUĞA çevir — kod, belge bağlantısı değildir.

    ⚠️ Satır-içi kod (`...`) SİLİNMEZ: bağlantı etiketleri kod içerir
    (`[`icon_master/`](...)`) ve silinince etiket kaybolur.
    """
    out, cit, nl = [], False, chr(10)
    for satir in metin.splitlines(keepends=True):
        if satir.lstrip().startswith("```"):
            cit = not cit
            out.append(" " * (len(satir) - 1) + nl)
            continue
        out.append((" " * (len(satir) - 1) + nl) if cit else satir)
    return "".join(out)


def _cozulur_mu(kaynak: Path, hedef: str) -> bool:
    if (kaynak.parent / hedef).exists():
        return True
    coz = urllib.parse.unquote(hedef)
    return coz != hedef and (kaynak.parent / coz).exists()


def kirik_baglantilar() -> list[tuple[str, str]]:
    """[(dosya, hedef)] — çözülemeyen yerel bağlantılar. Kapının tek karar noktası."""
    bulgular = []
    for rel in _md_dosyalari():
        p = KOK / rel
        metin = _cit_disi(p.read_bytes().decode("utf-8", errors="replace"))
        for m in re.finditer(r"\]\(([^)#?]+?)(?:#[^)]*)?\)", metin):
            hedef = m.group(1).strip()
            if hedef.startswith(("http://", "https://", "mailto:", "<")) or not hedef:
                continue
            if Path(hedef).name.startswith(MUAF_ADLAR):
                continue
            if not _cozulur_mu(p, hedef):
                bulgular.append((rel, hedef))
    return bulgular


# ──────────────────────────────────────────────────────────────────────────
# 0) KARŞIT-KANIT — ayrıştırıcı GERÇEKTEN ayırıyor mu
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "metin,beklenen_baglanti,aciklama",
    [
        ("bak [x](README.md)", ["README.md"], "duz baglanti"),
        ("```\n[x](YOK.md)\n```", [], "KOD CITI icindeki baglanti SAYILMAZ"),
        ("[`a/`](a/README.md)", ["a/README.md"], "etiket satir-ici kod — SILINMEMELI"),
        ("[x](https://a.b/c)", [], "harici baglanti sayilmaz"),
        ("[x](a.md#bolum)", ["a.md"], "capa (#) atilir"),
    ],
)
def test_KARSIT_KANIT_ayristirici_AYIRIYOR(metin, beklenen_baglanti, aciklama):
    """⚠️ Kapı kendi ayrıştırıcısına dayanıyor; önce ONU kanıtla."""
    bulunan = [
        m.group(1).strip()
        for m in re.finditer(r"\]\(([^)#?]+?)(?:#[^)]*)?\)", _cit_disi(metin))
        if not m.group(1).strip().startswith(("http://", "https://", "mailto:"))
    ]
    assert bulunan == beklenen_baglanti, aciklama


def test_KARSIT_KANIT_yuzde20_kacisi_COZULUR(tmp_path):
    """`offline%20dağıtım/...` görüntüleyicide çalışır → KIRIK SAYILMAZ."""
    (tmp_path / "a b").mkdir()
    (tmp_path / "a b" / "OKU.md").write_text("x", encoding="utf-8")
    sahte = tmp_path / "README.md"
    sahte.write_text("y", encoding="utf-8")
    assert _cozulur_mu(sahte, "a%20b/OKU.md") is True
    assert _cozulur_mu(sahte, "a%20b/YOK.md") is False


# ──────────────────────────────────────────────────────────────────────────
# 1) ASIL İDDİALAR
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_README_baglantilari_COZULUYOR():
    """Klasör taşımaları belgeleri sessizce çürütmesin."""
    dosyalar = _md_dosyalari()
    assert len(dosyalar) > 50, f"VAKUM: yalnız {len(dosyalar)} markdown tarandı — tarama bozuk"
    kirik = kirik_baglantilar()
    assert not kirik, (
        "KIRIK BAĞLANTI (%d):\n  " % len(kirik)
        + "\n  ".join(f"{d} -> {h}" for d, h in kirik[:40])
        + "\n\nBunların çoğu klasör taşıması artığıdır: hedefi depoda arayıp göreli yolu "
        "yeniden hesaplayın. Hedef GERÇEKTEN yoksa bağlantıyı kaldırın (etiket kalsın)."
    )


def test_KRITIK_kok_README_dizin_haritasi_GERCEK():
    """Dizin haritasında DİSKTE OLMAYAN girdi kalmasın (silinen dizinin satırı gibi).

    Ölçülen vaka: `icon_master/` `862219f` kök temizliğinde silinmişti ama harita satırı
    kalmıştı — okuyucu var olmayan bir dizin arıyordu.
    """
    metin = (KOK / "README.md").read_bytes().decode("utf-8", errors="replace")
    # ⚠️ "ÜRETİLEN" işaretli satırlar MUAF: `build/` · `dist/` gibi PyInstaller çıktıları
    #    derleme yapılmadan önce DİSKTE OLMAYABİLİR ve bu arıza değildir. Ölçülen vaka
    #    `icon_master/` ÜRETİLEN değildi — silinmiş KAYNAK dizindi; ayrım tam burada.
    girdiler = []
    for satir in metin.splitlines():
        if not satir.lstrip().startswith("|"):
            continue
        if "ÜRETİLEN" in satir:
            continue
        # ⚠️ İLK HÜCREYE ÇIPALI: satırın herhangi bir yerini taramak README'deki ÖTEKİ
        #    tabloları da içeri aldı (`credentials/`, `PEMF_AI_Test_Girdileri/` — dizin
        #    haritasında değiller). Harita satırı `| `dizin/` |` biçiminde BAŞLAR.
        m = re.match(r"^\|\s*(?:\[)?`([^`]+/)`", satir.lstrip())
        if m:
            girdiler.append(m.group(1))
    assert len(girdiler) > 20, f"VAKUM: haritada yalnız {len(girdiler)} girdi bulundu"
    yok = [g for g in girdiler if not (KOK / g.rstrip("/")).exists()]
    assert not yok, f"kök README dizin haritasında DİSKTE OLMAYAN girdi: {yok}. Silinen dizinin satırı da silinmeli."


def test_KRITIK_tools_README_paket_boyutu_KAYNAKLA_UYUSUR():
    """`tools/README.md`'deki bayt sayısı kaynaktaki `PKT_SIZE` ile aynı olmalı.

    Ölçülen bayatlık: README "88 bayt" diyordu, kaynak `assert PKT_SIZE == 121`
    (2026-09-10'da bobin 5→7). Protokolü hata ayıklayan kişi yanlış sayıyla karşılanıyordu.
    """
    kaynak = (KOK / "tools" / "stm32_simulator.py").read_text(encoding="utf-8")
    m = re.search(r"assert\s+PKT_SIZE\s*==\s*(\d+)", kaynak)
    assert m, "stm32_simulator.py içinde `assert PKT_SIZE == N` yok — çıpa bayat"
    gercek = m.group(1)

    belge = (KOK / "tools" / "README.md").read_bytes().decode("utf-8")
    sayilar = re.findall(r"(\d+)[- ]?(?:byte|bayt)", belge, re.I)
    assert sayilar, "tools/README.md paket boyutundan hiç söz etmiyor — çıpa bayat"
    yanlis = [s for s in sayilar if s != gercek]
    assert not yanlis, (
        f"tools/README.md {yanlis} bayt diyor, kaynak {gercek}. STM paket biçimi değişince "
        "belge de değişmeli (2026-09-10'da 5→7 bobin taşımasında bu kaçtı)."
    )
