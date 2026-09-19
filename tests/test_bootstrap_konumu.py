# Author: mertaygn, cglrgrkn
r"""BOOTSTRAP'IN KENDİ KONUM MANTIĞI DOSYANIN GERÇEK DERİNLİĞİYLE UYUŞUR.

NE OLDU (2026-09-19): kök dizin temizliğinde `guii/bootstrap.ps1` → `guii/scripts/bootstrap.ps1`
taşındı. Betik konumunu şöyle çözüyordu:

    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $GuiRoot   = $ScriptDir                       # <-- taşımadan SONRA YANLIŞ
    $EmbRoot   = Split-Path -Parent $GuiRoot

Taşımadan sonra `$GuiRoot` = `guii/scripts`, `$EmbRoot` = `guii` olurdu. Sonuç:

  • `$embPy = $EmbRoot\python.exe` → BULUNAMAZ
  • Adım 5 (Python doğrulaması), 5b (pre-commit hook), 5c (skip-worktree sır koruması)
    `if (Test-Path $embPy)` koşuluyla korunuyor → hepsi SESSİZCE atlanır, `Warn` basar
  • Betik **exit 0** döner ve "TÜM ARAÇ ZİNCİRİ HAZIR" tablosunda yalnız bir satır kırmızı olur

Yani yeni bir makinede sır koruması KURULMAMIŞ olurdu ve kimse fark etmezdi — bu deponun
"yarım kapsamla yeşil" sınıfının bir örneği daha ([[kapi-cozulemeyen-koku-sessizce-dusuruyordu]]).

KAPININ BİÇİMİ — SABİT SAYI YOK. Beklenen `Split-Path -Parent` adımı, dosyanın depodaki
GERÇEK derinliğinden TÜRETİLİR. Betik yarın `build_tools/` altına taşınırsa kapı kendini
ayarlar; taşınıp da hop sayısı düzeltilmezse KIRMIZI olur. Sabit `== 2` yazmak, aynı hatayı
bir sonraki taşımada tekrar ettirirdi ([[pemf-tek-kaynaga-toplama-test-dikisini-koparir]]).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

BETIK_ADI = "bootstrap.ps1"

#: Betiğin ÇALIŞTIRILMA yolunu veren kullanım kılavuzları. Bayat yol = insan yanlış komut yazar.
KOSUM_BELGELERI = ("BUILD.md", "docs/TEMIZ-MAKINE.md")

CALISAN_UZANTILAR = {".sh", ".ps1", ".psm1", ".py", ".yml", ".yaml", ".spec", ".bat", ".cmd"}

# Tarihçe: o günün durumunu anlatır, bayatlaması DOĞRUDUR.
#   test_kontrol_bayti_kapisi — 2026-08-18'de ölçülen `.\bootstrap.ps1` → `.ootstrap.ps1`
#   hatasının KAYDI. O gün yol gerçekten kökteydi.
MUAF_DOSYALAR = {
    "tests/test_bootstrap_konumu.py",
    "tests/test_kontrol_bayti_kapisi.py",
}


# ═════════════════════════════════════════════════════════════════════════════════════════
# YARDIMCILAR
# ═════════════════════════════════════════════════════════════════════════════════════════


def yorumsuz(satir: str) -> str:
    """Satırın KOD kısmı — tırnak-farkındalı `#` ayıklaması.

    ⚠️ ŞART: bu kapının konusu olan `bootstrap.ps1`, taşımayı ANLATAN bir uyarı yorumu
    taşıyor ve o yorumun içinde tam olarak `$GuiRoot = $ScriptDir` (yani bozuk hâli)
    yazıyor. Ham metinde arayan bir kapı, kod DOĞRUYKEN kırmızı verirdi. Bu deponun
    tekrar eden sınıfı: "yorum kapıyı kandırdı" (7 vaka).

    Tırnak farkındalığı da şart: `Write-Host "gh auth login  # GitHub icin"` satırında
    `#` bir YORUM değildir.
    """
    tirnak = None
    for i, ch in enumerate(satir):
        if tirnak:
            if ch == tirnak:
                tirnak = None
        elif ch in ("'", '"'):
            tirnak = ch
        elif ch == "#":
            return satir[:i]
    return satir


def ps_kodu(kaynak: str) -> str:
    """PowerShell kaynağı, yorumlar ayıklanmış (dizeler DURUR)."""
    return "\n".join(yorumsuz(s) for s in kaynak.splitlines())


_ATAMA = re.compile(r"^\s*\$(\w+)\s*=\s*(.+?)\s*$", re.M)
_USTE_CIK = re.compile(r"^Split-Path\s+-Parent\s+\$(\w+)$", re.I)
_AYNI = re.compile(r"^\$(\w+)$")


def hop_haritasi(kaynak: str) -> dict[str, int]:
    """`$ScriptDir`den kaç `Split-Path -Parent` adımı uzakta olduğunu değişken başına verir.

    `$ScriptDir` = 0. `$X = Split-Path -Parent $Y` → hop(X) = hop(Y) + 1.
    `$X = $Y` (takma ad) → hop(X) = hop(Y). Çözülemeyen değişken haritaya GİRMEZ.

    ⚠️ Çözülemeyeni SESSİZCE atlamak bu depoda kapsam kaybının imzasıdır; burada zararsız
    çünkü kapı aradığı adı BULAMAZSA ayrıca kırmızı verir (aşağıdaki assert'ler).
    """
    hop: dict[str, int] = {"ScriptDir": 0}
    # Birkaç tur: atamalar kaynakta sırayla yazılmış olsa da bağımsız olalım.
    for _ in range(6):
        for ad, deger in _ATAMA.findall(ps_kodu(kaynak)):
            if ad in hop:
                continue
            u = _USTE_CIK.match(deger)
            if u and u.group(1) in hop:
                hop[ad] = hop[u.group(1)] + 1
                continue
            a = _AYNI.match(deger)
            if a and a.group(1) in hop:
                hop[ad] = hop[a.group(1)]
    return hop


def _betik_yolu() -> str:
    """Betiğin depodaki GERÇEK yolu (git'e sorar — sabit yazmak taşımayı gizlerdi)."""
    ch = subprocess.run(["git", "ls-files"], cwd=KOK, capture_output=True, text=True, timeout=120)
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    adaylar = [a for a in ch.stdout.splitlines() if Path(a).name == BETIK_ADI]
    assert len(adaylar) == 1, f"{BETIK_ADI} depoda {len(adaylar)} kez var: {adaylar} — tek olmalı"
    return adaylar[0]


def _izlenen_calisan_dosyalar() -> list[str]:
    ch = subprocess.run(["git", "ls-files"], cwd=KOK, capture_output=True, text=True, timeout=120)
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    return [
        a
        for a in ch.stdout.splitlines()
        if a and a not in MUAF_DOSYALAR and Path(a).suffix.lower() in CALISAN_UZANTILAR
    ]


#: `.\scripts\bootstrap.ps1` · `./scripts/bootstrap.ps1` · `scripts/bootstrap.ps1` · `bootstrap.ps1`
_ANMA = re.compile(r"(?<![\w.-])((?:\.[/\\])?(?:[\w.-]+[/\\])*)" + re.escape(BETIK_ADI))


def _dizin_kismi(on_ek: str) -> str | None:
    """Yakalanan ön ekten dizin iddiasını çıkarır.

        ``                 → None        çıplak anma (`bootstrap.ps1 toolchain'i kurar`) — YOL DEĞİL
        `.\\` · `./`        → ``          "bulunduğun dizinde" = DEPO KÖKÜ iddiası
        `.\\scripts\\`       → `scripts`
        `build_tools/alt/` → `build_tools/alt`

    ⚠️ BU AYRIM BİR MUTASYONLA ORTAYA ÇIKTI (2026-09-19, M5). İlk hâl `lstrip("./")`
    kullanıyordu; `.\\bootstrap.ps1` ile çıplak `bootstrap.ps1` AYNI sonuca (``) düşüyordu
    ve ikisi de "iddia yok" sayılıyordu. Sonuç: kılavuzdaki `.\\scripts\\` → `.\\` mutasyonu
    kapıyı YEŞİL geçti — yani kapı tam da yazılma sebebini kaçırıyordu.
    """
    if not on_ek:
        return None
    s = on_ek.replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    return s.rstrip("/")


# ═════════════════════════════════════════════════════════════════════════════════════════
# ASIL SÖZLEŞME
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_konum_zinciri_GERCEK_derinlikle_uyusuyor():
    """🔴 ASIL REGRESYON: hop sayısı dosyanın derinliğinden bir eksikse `python.exe` bulunmaz.

    Beklenen TÜRETİLİR:
        hop($GuiRoot) = betiğin depo kökünden derinliği   (scripts/ → 1)
        hop($EmbRoot) = o + 1                              (embeddable kök = depo kökünün üstü)
    """
    rel = _betik_yolu()
    derinlik = len(Path(rel).parts) - 1  # 'scripts/bootstrap.ps1' → 1
    kaynak = (KOK / rel).read_text(encoding="utf-8")
    hop = hop_haritasi(kaynak)

    assert "GuiRoot" in hop, (
        f"{rel}: $GuiRoot, $ScriptDir'den TÜRETİLMİYOR (Split-Path zinciri koptu) — konum mantığı artık ölçülemez"
    )
    assert "EmbRoot" in hop, f"{rel}: $EmbRoot, $ScriptDir'den türetilmiyor"

    assert hop["GuiRoot"] == derinlik, (
        f"{rel} depo kökünün {derinlik} kademe altında ama $GuiRoot {hop['GuiRoot']} kademe "
        f"yukarı çıkıyor → $GuiRoot depo kökü DEĞİL. `.git` kontrolleri ve "
        "`Push-Location` yanlış dizinde çalışır; pre-commit hook'u kurulmaz."
    )
    assert hop["EmbRoot"] == derinlik + 1, (
        f"{rel}: $EmbRoot {hop['EmbRoot']} kademe yukarıda, olması gereken {derinlik + 1}. "
        "Yanlışsa `$EmbRoot\\python.exe` bulunmaz → adım 5/5b/5c SESSİZCE atlanır "
        "(Warn basar, exit 0 döner): yeni makinede sır koruması KURULMAMIŞ olur."
    )


def test_KRITIK_depo_koku_isteyen_yerler_PSScriptRoot_KULLANMAZ():
    """`$PSScriptRoot` = betiğin dizini. Betik kökte DEĞİLSE depo kökü anlamına gelmez.

    Taşımadan önce beşi de doğruydu (betik kökteydi); taşımadan sonra hepsi `scripts/`i
    gösterirdi: `.git` bulunamaz → "Bu klasor bir git deposu degil" → koruma kurulmaz.
    """
    rel = _betik_yolu()
    derinlik = len(Path(rel).parts) - 1
    if derinlik == 0:
        pytest.skip("betik kökte — $PSScriptRoot zaten depo köküdür")
    kod = ps_kodu((KOK / rel).read_text(encoding="utf-8"))
    kacaklar = [s.strip() for s in kod.splitlines() if "$PSScriptRoot" in s]
    assert not kacaklar, (
        f"{rel} depo kökü yerine $PSScriptRoot kullanıyor ({len(kacaklar)} satır):\n  "
        + "\n  ".join(k[:100] for k in kacaklar)
        + f"\n$PSScriptRoot = {Path(rel).parent.as_posix()} — depo kökü DEĞİL. $GuiRoot kullan."
    )


def test_KRITIK_calisan_kodda_BAYAT_yol_YOK():
    """Betiği ÇAĞIRAN satırlardaki yol, betiğin gerçek yeriyle aynı olmalı.

    ⚠️ KAPSAM: yalnız KOD (yorumlar ayıklanır) — ve bu kez gerekçesi CANLI ÖLÇÜLDÜ.
    `bootstrap.ps1` kendi içinde taşımayı anlatan bir not taşıyor:

        # ⚠️ 2026-09-19'da `guii\\bootstrap.ps1` -> `guii\\scripts\\bootstrap.ps1` TASINDI.

    Yorumları da tarayan bir kapı BU SATIR yüzünden şu an yanlış-kırmızı verirdi — aynı
    sınıfın 8. vakası. Bayat yorum kimseyi yanlış yola götürmez; bayat DİZE (`Warn "...
    .\\scripts\\bootstrap.ps1 ile kurun"`) götürür, ve dizeler ayıklanmaz.
    """
    rel = _betik_yolu()
    dogru = Path(rel).parent.as_posix().strip(".")
    dosyalar = _izlenen_calisan_dosyalar()
    assert len(dosyalar) > 100, f"tarama çok dar ({len(dosyalar)}) — kapı boş dönüyor olabilir"

    bulgu: dict[str, list[str]] = {}
    konu_sayisi = 0
    for ad in dosyalar:
        try:
            metin = (KOK / ad).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for no, satir in enumerate(metin.splitlines(), 1):
            for on_ek in _ANMA.findall(yorumsuz(satir)):
                d = _dizin_kismi(on_ek)
                if d is None:
                    continue  # çıplak anma — yol iddiası yok
                konu_sayisi += 1
                if d != dogru:
                    bulgu.setdefault(ad, []).append(f"{no}: {satir.strip()[:100]}")
    assert not bulgu, f"{BETIK_ADI} `{dogru or '<kök>'}/` altında ama bu satırlar başka yeri gösteriyor:\n" + "\n".join(
        f"  {k}\n    " + "\n    ".join(v) for k, v in sorted(bulgu.items())
    )
    # ⚠️ BOŞ KAPI KAPISI: yorum ayıklama kapsamı daralttığı için bu tarama KOLAYCA
    # sıfır özneye düşer ve sonsuza kadar yeşil kalır ("yarım kapsamla yeşil" sınıfı).
    assert konu_sayisi >= 1, (
        "taramada TEK BİR yol iddiası bile kalmadı — kapı vakum. Beklenen özne: "
        "scripts/build_backend_exe.ps1 içindeki `Cozum: ...` uyarı dizesi."
    )


@pytest.mark.parametrize("belge", KOSUM_BELGELERI)
def test_kosum_belgesi_GUNCEL_yolu_verir(belge):
    """Kullanım kılavuzundaki komut, kopyalanıp yapıştırıldığında ÇALIŞMALI."""
    rel = _betik_yolu()
    p = KOK / belge
    if not p.exists():
        pytest.skip(f"{belge} yok")
    metin = p.read_text(encoding="utf-8")
    assert BETIK_ADI in metin, f"{belge} {BETIK_ADI}'den hiç söz etmiyor — kılavuz eksik"

    dogru = Path(rel).parent.as_posix().strip(".")
    iddialar = [
        (no, s, _dizin_kismi(on_ek))
        for no, s in enumerate(metin.splitlines(), 1)
        for on_ek in _ANMA.findall(s)
        if _dizin_kismi(on_ek) is not None
    ]
    assert iddialar, (
        f"{belge} {BETIK_ADI} adını anıyor ama ÇALIŞTIRILABİLİR bir yol vermiyor — "
        "kılavuzun işi tam olarak o komutu vermek"
    )
    yanlis = [f"{no}: {s.strip()[:100]}" for no, s, d in iddialar if d != dogru]
    assert not yanlis, f"{belge} bayat çalıştırma yolu veriyor:\n  " + "\n  ".join(yanlis)


# ═════════════════════════════════════════════════════════════════════════════════════════
# KARŞIT-KANITLAR — kapı boş geçmiyor
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_yorum_kapiyi_KANDIRMIYOR():
    """CANLI kanıt: bugünkü `bootstrap.ps1` bozuk hâli bir YORUMDA anlatıyor.

    Ham metinde arayan bir kapı ŞU AN yanlış-kırmızı verirdi. Bu test onu ölçer —
    sentetik değil, dosyanın gerçek içeriğiyle.
    """
    kaynak = (KOK / _betik_yolu()).read_text(encoding="utf-8")
    assert "$GuiRoot = $ScriptDir" in kaynak, (
        "uyarı yorumu kaldırılmış — bu karşıt-kanıtın dayanağı gitti; testi güncelle"
    )
    assert "$GuiRoot = $ScriptDir" not in ps_kodu(kaynak), (
        "yorum ayıklayıcı çalışmıyor: bozuk atama YORUMDA duruyor ama KOD sayılıyor"
    )
    # Aynı şekilde eski yol da yalnız yorumda anılıyor.
    assert "guii\\bootstrap.ps1" in kaynak and "guii\\bootstrap.ps1" not in ps_kodu(kaynak)


def test_KARSIT_KANIT_bozuk_zincir_KIRMIZI_veriyor():
    """Taşıma sonrası düzeltilmemiş hâl gerçekten yakalanmalı."""
    bozuk = (
        "$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path\n"
        "$GuiRoot   = $ScriptDir\n"
        "$EmbRoot   = Split-Path -Parent $GuiRoot\n"
    )
    hop = hop_haritasi(bozuk)
    assert hop["GuiRoot"] == 0 and hop["EmbRoot"] == 1, hop
    # scripts/ altındaki bir dosya için beklenen 1 ve 2 idi → kapı KIRMIZI olurdu.

    dogru = (
        "$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path\n"
        "$GuiRoot   = Split-Path -Parent $ScriptDir\n"
        "$EmbRoot   = Split-Path -Parent $GuiRoot\n"
    )
    h2 = hop_haritasi(dogru)
    assert h2["GuiRoot"] == 1 and h2["EmbRoot"] == 2, h2

    # Zincir KOPARSA (sabit yol yazılırsa) haritaya hiç girmemeli — sessiz yeşil olmasın.
    kopuk = "$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path\n$GuiRoot = 'C:\\guii'\n"
    assert "GuiRoot" not in hop_haritasi(kopuk), "sabit yol çözülmüş sayıldı — kapı körelir"


def test_KARSIT_KANIT_yol_deseni_dogru_ayiriyor():
    """Ön ek ayıklayıcısı hem yakalamalı hem yanlış-kırmızı vermemeli."""
    yakala = {
        r".\scripts\bootstrap.ps1": "scripts",
        "./scripts/bootstrap.ps1": "scripts",
        "scripts/bootstrap.ps1": "scripts",
        r"build_tools\alt\bootstrap.ps1": "build_tools/alt",
        # ⚠️ M5'in yakaladığı ayrım: `.\` DEPO KÖKÜ iddiasıdır, "iddia yok" değil.
        r".\bootstrap.ps1": "",
        "./bootstrap.ps1": "",
        # Çıplak ad = yol iddiası YOK → None (belgelerde meşru anma).
        "`bootstrap.ps1` toolchain'i kurar": None,
    }
    for metin, beklenen in yakala.items():
        bulunan = _ANMA.findall(metin)
        assert bulunan, f"desen KAÇIRIYOR: {metin}"
        assert _dizin_kismi(bulunan[0]) == beklenen, f"{metin} → {_dizin_kismi(bulunan[0])!r}, beklenen {beklenen!r}"

    # ⚠️ ASIL KANIT: kök iddiası ile çıplak anma AYRI sonuç vermeli. Eşitlerse M5 geri gelir.
    assert _dizin_kismi(_ANMA.findall(r".\bootstrap.ps1")[0]) != _dizin_kismi(
        _ANMA.findall("bootstrap.ps1 kurar")[0]
    ), "`.\\bootstrap.ps1` ile çıplak ad aynı sayılıyor — kapı kök iddiasını göremez"

    # Yorum ayıklamadan GEÇİRİLİNCE: yorumdaki bayat yol ihlal sayılmaz, koddaki sayılır.
    assert not _ANMA.findall(yorumsuz(r"# eskiden .\bootstrap.ps1 idi"))
    assert _ANMA.findall(yorumsuz(r"& .\scripts\bootstrap.ps1 -VerifyOnly"))


def test_KARSIT_KANIT_muafiyet_listesi_SISMEMIS():
    """Kırmızıyı susturmanın en kolay yolu muafiyet eklemektir."""
    assert len(MUAF_DOSYALAR) <= 2, f"muafiyet listesi şişmiş: {MUAF_DOSYALAR}"
    assert CALISAN_UZANTILAR >= {".sh", ".ps1", ".py", ".yml"}, "uzantı kapsamı daraltılmış"
    assert len(KOSUM_BELGELERI) >= 2, "kılavuz kapsamı daraltılmış"
