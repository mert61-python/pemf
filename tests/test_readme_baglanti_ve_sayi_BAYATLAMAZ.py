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

🔴 D4.01 / D4.03 (B-11.1 = B-10.1, 2026-10-10): hedefler DİSKTE değil TEMİZ AĞAÇTA (`git ls-files -z`) çözülür.
Eski çözücü `Path.exists()` idi: geliştirme makinesinin çalışma ağacında izlenmeyen (gitignore'lu) yerel dizinler
(`release_assets/README.md`, `offline dağıtım/`, `lattekurulum/`, `apple-mac-cert/`, `keys/`, `bin/README.md`) DURDUĞU
için kapı yerelde YEŞİL, temiz klonda (CI'ın gördüğü ağaç) 10 kırık bağlantı + 3 harita girdisiyle KIRMIZIYDI — ilk push
critical-path-tests'i kırardı. Aynı nedenle büyük/küçük harfi yanlış bağlantı (Windows'ta açılır, GitHub/Linux'ta açılmaz)
ve ters bölülü yol da artık KIRIK sayılır. Dizin haritasında bilerek izlenmeyen yerel dizin `**YEREL**` diye işaretlenir;
kapı o dizinin GERÇEKTEN izlenmediğini ve `.gitignore`'da olduğunu ölçer (sır dizini — `apple-mac-cert/`, `keys/` —
yanlışlıkla izlenmeye başlarsa da kırmızı).
"""

from __future__ import annotations

import functools
import posixpath
import re
import subprocess
import urllib.parse
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)

#: Kullanıcının OLUŞTURACAĞI dosyalar — yokluğu arıza değildir.
MUAF_ADLAR = (".env",)

#: Dizin haritasında bilerek izlenmeyen (yalnız geliştirme makinesinde duran) dizinin işareti.
YEREL_ISARETI = "**YEREL**"


@functools.lru_cache(maxsize=8)
def _izlenen(kok: str) -> tuple[frozenset[str], frozenset[str]]:
    """(izlenen dosyalar, izlenen dosyaların bütün üst dizinleri) — TEMİZ AĞAÇ, `git ls-files -z`.

    ⚠️ Kök çözülemezse (git yok / depo değil) SESSİZCE boş küme DÖNMEZ: boş küme her bağlantıyı
    kırık sayardı ama `_md_dosyalari` de boşalıp vakum kapısına düşerdi — hata burada verilir.
    """
    sonuc = subprocess.run(["git", "ls-files", "-z"], cwd=kok, capture_output=True, timeout=180)
    if sonuc.returncode != 0:
        raise AssertionError(f"git ls-files {kok} içinde çalışmadı (rc={sonuc.returncode}): {sonuc.stderr[:300]!r}")
    dosyalar = frozenset(x.decode("utf-8") for x in sonuc.stdout.split(b"\x00") if x)
    dizinler = {""}
    for yol in dosyalar:
        parca = yol.split("/")[:-1]
        for i in range(1, len(parca) + 1):
            dizinler.add("/".join(parca[:i]))
    return dosyalar, frozenset(dizinler)


def _md_dosyalari(kok: Path = KOK) -> list[str]:
    return sorted(y for y in _izlenen(str(kok))[0] if y.endswith(".md"))


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


def _cozulur_mu(kaynak_rel: str, hedef: str, kok: Path = KOK) -> bool:
    """`kaynak_rel` (depo-göreli, `/` ayraçlı) içindeki `hedef` bağlantısı TEMİZ AĞAÇTA var mı.

    Yalnız `/` ayraçtır (GitHub'ın çözdüğü biçim) — ters bölü dosya adının parçası sayılır, büyük/küçük harf
    birebir eşleşmelidir; depo dışına çıkan (`../..`) hedef çözülmez.
    """
    dosyalar, dizinler = _izlenen(str(kok))
    for aday in dict.fromkeys((hedef, urllib.parse.unquote(hedef))):
        yol = posixpath.normpath(posixpath.join(posixpath.dirname(kaynak_rel), aday))
        yol = "" if yol == "." else yol
        if yol == ".." or yol.startswith("../"):
            continue
        if yol in dosyalar or yol in dizinler:
            return True
    return False


def kirik_baglantilar(kok: Path = KOK) -> list[tuple[str, str]]:
    """[(dosya, hedef)] — çözülemeyen yerel bağlantılar. Kapının tek karar noktası."""
    bulgular = []
    for rel in _md_dosyalari(kok):
        metin = _cit_disi((kok / rel).read_bytes().decode("utf-8", errors="replace"))
        for m in re.finditer(r"\]\(([^)#?]+?)(?:#[^)]*)?\)", metin):
            hedef = m.group(1).strip()
            if hedef.startswith(("http://", "https://", "mailto:", "<")) or not hedef:
                continue
            if Path(hedef).name.startswith(MUAF_ADLAR):
                continue
            if not _cozulur_mu(rel, hedef, kok):
                bulgular.append((rel, hedef))
    return bulgular


def harita_girdileri(metin: str) -> list[tuple[str, bool]]:
    """Kök README dizin haritasının girdileri: [(dizin/, YEREL mi)] — "ÜRETİLEN" satırlar hariç."""
    girdiler = []
    for satir in metin.splitlines():
        if not satir.lstrip().startswith("|"):
            continue
        # ⚠️ "ÜRETİLEN" işaretli satırlar MUAF: `build/` · `dist/` gibi PyInstaller çıktıları
        #    derleme yapılmadan önce DİSKTE OLMAYABİLİR ve bu arıza değildir. Ölçülen vaka
        #    `icon_master/` ÜRETİLEN değildi — silinmiş KAYNAK dizindi; ayrım tam burada.
        if "ÜRETİLEN" in satir:
            continue
        # ⚠️ İLK HÜCREYE ÇIPALI: satırın herhangi bir yerini taramak README'deki ÖTEKİ
        #    tabloları da içeri aldı (`credentials/`, `PEMF_AI_Test_Girdileri/` — dizin
        #    haritasında değiller). Harita satırı `| `dizin/` |` biçiminde BAŞLAR.
        m = re.match(r"^\|\s*(?:\[)?`([^`]+/)`", satir.lstrip())
        if m:
            girdiler.append((m.group(1), YEREL_ISARETI in satir))
    return girdiler


def harita_sorunlari(kok: Path = KOK) -> tuple[int, list[str]]:
    """(girdi sayısı, sorunlar) — izlenen girdi TEMİZ AĞAÇTA olmalı; YEREL girdi izlenMEMELİ ve gitignore'lu olmalı."""
    _, dizinler = _izlenen(str(kok))
    girdiler = harita_girdileri((kok / "README.md").read_bytes().decode("utf-8", errors="replace"))
    sorunlar = []
    for girdi, yerel in girdiler:
        ad = girdi.rstrip("/")
        if not yerel:
            if ad not in dizinler:
                sorunlar.append(f"{girdi} temiz ağaçta YOK (git ls-files)")
            continue
        # ⚠️ ARAÇ TUZAĞI (ölçüldü 2026-10-10): sonu `/` olan yol (`apple-mac-cert/`) CRLF'li çalışma ağacı
        #    .gitignore'unda yalnız `\r` taşıyan BOŞ satırla da "eşleşir" — kural silinse bile rc 0. Dizinin İÇİNDEKİ
        #    bir yol sorulur: `dizin/` kuralı o yolu dizin bileşeninden yakalar, boş satır yakalamaz.
        sonda = posixpath.join(ad, "_yerel_kapi_sondasi")
        if ad in dizinler:
            sorunlar.append(f"{girdi} {YEREL_ISARETI} işaretli ama git'te İZLENİYOR")
        elif subprocess.run(["git", "check-ignore", "--no-index", "-q", sonda], cwd=kok, timeout=60).returncode != 0:
            sorunlar.append(f"{girdi} {YEREL_ISARETI} işaretli ama .gitignore'da DEĞİL (yanlışlıkla izlenebilir)")
    return len(girdiler), sorunlar


def _sahte_depo(kok: Path, izlenen: dict[str, str], izlenmeyen: dict[str, str], gitignore: bytes = b"") -> Path:
    """tmp_path'te gerçek bir git deposu: `izlenen` index'e eklenir, `izlenmeyen` yalnız diskte durur.

    `.gitignore` BAYT olarak yazılır (Windows checkout'u gibi CRLF + boş satır her işletim sisteminde aynı kalsın).
    """
    subprocess.run(["git", "init", "-q", str(kok)], check=True, timeout=60)
    for ad, icerik in {**izlenen, **izlenmeyen}.items():
        (kok / ad).parent.mkdir(parents=True, exist_ok=True)
        (kok / ad).write_text(icerik, encoding="utf-8")
    if gitignore:
        (kok / ".gitignore").write_bytes(gitignore)
        izlenen = {**izlenen, ".gitignore": ""}
    subprocess.run(["git", "-C", str(kok), "add", "--", *izlenen], check=True, timeout=60)
    _izlenen.cache_clear()
    return kok


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
    """`offline%20dağıtım/...` görüntüleyicide çalışır → KIRIK SAYILMAZ (Türkçe adlı izlenen yol dahil)."""
    kok = _sahte_depo(tmp_path, {"README.md": "y", "a b/OKU.md": "x", "dağıtım klasörü/OKU.md": "z"}, {})
    assert _cozulur_mu("README.md", "a%20b/OKU.md", kok) is True
    assert _cozulur_mu("README.md", "da%C4%9F%C4%B1t%C4%B1m%20klas%C3%B6r%C3%BC/OKU.md", kok) is True
    assert _cozulur_mu("README.md", "dağıtım klasörü/OKU.md", kok) is True
    assert _cozulur_mu("README.md", "a%20b/YOK.md", kok) is False


def test_KARSIT_KANIT_TEMIZ_AGAC_izlenmeyen_hedef_KIRIK(tmp_path):
    """D4.01: hedef DİSKTE durması yetmez — TEMİZ AĞAÇTA (git ls-files) yoksa KIRIK.

    Eski çözücü (`Path.exists`) bu dosyalarda yalnız `kirik` listesinin ilk ögesini görürdü: izlenmeyen /
    gitignore'lu / yanlış harfli / ters bölülü hedefler geliştirme makinesinde açılıyor, CI'ın temiz klonunda yok.
    """
    readme = "\n".join(
        [
            "[izli](docs/A.md) [dizin](docs/) [ust](alt/../docs/A.md)",
            "[izlenmeyen](yerel/B.md) [gitignore](sir/README.md) [hic](yok/C.md)",
            "[harf](docs/a.md) [ters](docs\\A.md) [depo-disi](../disari.md)",
        ]
    )
    kok = _sahte_depo(
        tmp_path / "depo",
        {"README.md": readme, "docs/A.md": "a"},
        {"yerel/B.md": "b", "sir/README.md": "s"},
        gitignore=b"sir/\n",
    )
    (tmp_path / "disari.md").write_text("d", encoding="utf-8")
    assert sorted(h for _, h in kirik_baglantilar(kok)) == sorted(
        ["yerel/B.md", "sir/README.md", "yok/C.md", "docs/a.md", "docs\\A.md", "../disari.md"]
    )


def test_KARSIT_KANIT_harita_YEREL_isareti_DOGRULANIR(tmp_path):
    """D4.01: dizin haritası temiz ağaca göre; YEREL girdi izlenmemeli VE gitignore'da olmalı.

    `.gitignore` Windows checkout'u gibi CRLF ve BOŞ satırlı: `git check-ignore acik/` (sonu `/`) bu dosyada
    boş satırla sahte eşleşme verir (ölçüldü) — `acik/` kuralsız olduğu hâlde "gitignore'lu" görünürdü.
    """
    harita = "\n".join(
        [
            "| Klasör | Ne |",
            "|---|---|",
            "| [`docs/`](docs/A.md) | izlenen |",
            "| `yerel/` | izlenmeyen ama YEREL işareti yok |",
            f"| `sir/` | {YEREL_ISARETI} sır dizini, gitignore'lu |",
            f"| `acik/` | {YEREL_ISARETI} ama gitignore'da değil |",
            f"| `docs/` | {YEREL_ISARETI} ama izleniyor |",
            "| `build/` | **ÜRETİLEN** — yokluğu arıza değil |",
        ]
    )
    kok = _sahte_depo(
        tmp_path,
        {"README.md": harita, "docs/A.md": "a"},
        {"yerel/x.txt": "y", "sir/x.txt": "s", "acik/x.txt": "a"},
        gitignore=b"# sirlar\r\nsir/\r\n\r\n# son\r\n",
    )
    sayi, sorunlar = harita_sorunlari(kok)
    assert sayi == 5
    assert sorunlar == [
        "yerel/ temiz ağaçta YOK (git ls-files)",
        f"acik/ {YEREL_ISARETI} işaretli ama .gitignore'da DEĞİL (yanlışlıkla izlenebilir)",
        f"docs/ {YEREL_ISARETI} işaretli ama git'te İZLENİYOR",
    ]


# ──────────────────────────────────────────────────────────────────────────
# 1) ASIL İDDİALAR
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_README_baglantilari_COZULUYOR():
    """Klasör taşımaları belgeleri sessizce çürütmesin — temiz klonda (CI) da."""
    dosyalar = _md_dosyalari()
    assert len(dosyalar) > 50, f"VAKUM: yalnız {len(dosyalar)} markdown tarandı — tarama bozuk"
    kirik = kirik_baglantilar()
    assert not kirik, (
        "KIRIK BAĞLANTI (%d) — hedef TEMİZ AĞAÇTA (git ls-files) yok:\n  " % len(kirik)
        + "\n  ".join(f"{d} -> {h}" for d, h in kirik[:40])
        + "\n\nBunların çoğu klasör taşıması artığıdır: hedefi depoda arayıp göreli yolu "
        "yeniden hesaplayın. Hedef yalnız bu makinede duruyorsa (gitignore'lu yerel dizin) ya da "
        "GERÇEKTEN yoksa bağlantıyı kaldırın (etiket kalsın)."
    )


def test_KRITIK_kok_README_dizin_haritasi_GERCEK():
    """Dizin haritasında TEMİZ AĞAÇTA OLMAYAN girdi kalmasın (silinen dizinin satırı gibi).

    Ölçülen vaka: `icon_master/` `862219f` kök temizliğinde silinmişti ama harita satırı
    kalmıştı — okuyucu var olmayan bir dizin arıyordu. D4.01: izlenmeyen yerel dizin
    (`lattekurulum/`, `apple-mac-cert/`…) yalnız YEREL işaretiyle ve gitignore'luysa kalabilir.
    """
    sayi, sorunlar = harita_sorunlari()
    assert sayi > 20, f"VAKUM: haritada yalnız {sayi} girdi bulundu"
    assert not sorunlar, (
        f"kök README dizin haritası temiz ağaçla UYUŞMUYOR: {sorunlar}. Silinen dizinin satırı da silinmeli."
    )


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
