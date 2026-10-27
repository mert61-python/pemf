# Author: mertaygn, cglrgrkn
"""TAŞINMIŞ DİZİN ADI ÇALIŞAN KODDA KALMAZ.

NE OLDU (2026-09-18): `pf/` → `apps/ui/` taşınırken dört ayrı yol biçimi düzeltildi ve
tüm süit (3112 test) YEŞİL döndü. Buna rağmen `build_mac.sh` içinde **çalışan kod**
kalmıştı:

    [[ -d pf ]] || die "pf/ (Expo frontend) yok."
    ( cd pf && npm ci --legacy-peer-deps && npm run export:web )
    cp -R pf/dist frontend/dist

Hiçbir kapı `.sh` dosyasındaki YALIN `pf`yi taramıyordu; bunu ancak izlenen tüm
dosyaları elle gezen bir karşıt-kanıt turu ortaya çıkardı. Etkisi: Mac paketi
4/7. adımda ölürdü — Windows'ta hiçbir zaman koşmadığı için de fark edilmezdi.

BU KAPININ KAPSAMI BİLEREK DAR: yalnız **çalıştırılan** dosyalar (.sh/.ps1/.py/.yml/.spec).
Belgelerdeki bayat yol kozmetiktir; betikteki bayat yol build'i kırar. Tarihli denetim
kayıtları (CHANGELOG, DEPO-DENETIMI-*) o günün durumunu anlatır — onlar dokunulmaz.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

# Taşınmış dizinler: eski ad -> yeni ad. Yeni bir taşıma yapıldığında buraya eklenir.
TASINMIS = {
    "pf": "apps/ui",
    "pemf-vet-web": "apps/web",
}

# ⚠️ SABİT SAYAÇ (depo deseni): listeden bir giriş SİLMEK kapıyı sessizce boşaltırdı.
TASINMIS_SAYISI = 2

# D5.30 (B-10.260): F4 taşıması (2026-09-18) — `servers/ services/ database/ utils/ controllers/` → `apps/backend/`. Bu adlar
# Python'da İMPORT adı olarak yaşar (`from utils.x import`) ve başka ağaçlarda meşru yol parçasıdır (`apps/ui/src/services`),
# bu yüzden YALNIZ Python OLMAYAN çalışan dosyalarda (kabuk / PowerShell / CI yml / bat) ve yol biçiminde aranır:
# önünde `[\w.$/\\-]` olmayan `<ad>/` (ör. `cp -R servers/x`; `apps/backend/servers/` YAKALANMAZ) ve `cd <ad>` / `-d <ad>`.
TASINMIS_KABUK = {
    "servers": "apps/backend/servers",
    "services": "apps/backend/services",
    "database": "apps/backend/database",
    "utils": "apps/backend/utils",
    "controllers": "apps/backend/controllers",
}
TASINMIS_KABUK_SAYISI = 5
KABUK_UZANTILAR = {".sh", ".bash", ".ps1", ".psm1", ".yml", ".yaml", ".bat", ".cmd"}

CALISAN_UZANTILAR = {".sh", ".ps1", ".psm1", ".py", ".yml", ".yaml", ".spec", ".bat", ".cmd"}

# `pf` üç meşru anlamda geçer ve hiçbiri DİZİN değildir:
#   • CLI kimliği   — `--hedef pf`, `HEDEFLER["pf"]`, `a.hedef == "pf"`, `--pf-dist`
#   • bu kapının kendi tablosu
#   • `pemf`, `.pfx`, `pf_` gibi daha uzun kelimelerin parçası (desen zaten sınır arıyor)
MUAF_DOSYALAR = {
    "tests/test_tasinmis_dizin_calisan_kodda_YOK.py",
    "scripts/responsive_kapisi.py",  # `--hedef pf` = KİMLİK (baseline anahtarı), dizin değil
}


def _izlenen_dosyalar() -> list[str]:
    """İzlenen TÜM dosyalar. D5.30 (B-10.262): `git ls-files` (`-z`siz) aksanlı yolu TIRNAKLI + sekizli kaçışlı verir
    (`"dema-terapi-sim\\303\\274lat…/x.sh"`) → uzantısı `.sh"` olur ve dosya SESSİZCE elenirdi. `-z` + UTF-8 çözümü."""
    ch = subprocess.run(["git", "ls-files", "-z"], cwd=KOK, capture_output=True, timeout=120)
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    return [x.decode("utf-8") for x in ch.stdout.split(b"\x00") if x]


def _izlenen_calisan_dosyalar() -> list[str]:
    yollar = []
    for ad in _izlenen_dosyalar():
        if not ad or ad in MUAF_DOSYALAR:
            continue
        # Taşınan ağacın KENDİ içindeki dosyalar konu dışı (kendi göreli yollarını kullanırlar).
        if any(ad.startswith(f"{yeni}/") for yeni in TASINMIS.values()):
            continue
        if Path(ad).suffix.lower() in CALISAN_UZANTILAR:
            yollar.append(ad)
    return yollar


def _desen(eski: str) -> re.Pattern[str]:
    """Eski dizin adını YOL olarak arar.

    Yakalar:  `cd pf`, `pf/dist`, `pf\\app.json`, `-d pf`, `"pf"`, `'pf'`, `../pf`
    Yakalamaz: `pemf`, `pf_kalan`, `mypf`, `.pfx`  (kelime sınırı + ayraç şartı)
    """
    a = re.escape(eski)
    return re.compile(
        rf"(?<![\w.-]){a}(?=[/\\])"  # ayraçla biten yol parçası:  pf/dist  pf\app.json
        rf"|(?<![\w.-]){a}(?![\w./\\-])",  # yalın/tırnaklı tam kelime:  cd pf   "pf"
    )


def yorumsuz(satir: str, kabuk: bool = False) -> str:
    """Satırın KOD kısmını döndürür — `#`ten sonrası atılır.

    ⚠️ 7. KEZ AYNI TUZAK (2026-09-18): kapının ilk hâli .py/.ps1/.spec içindeki
    YORUMLARI ihlal sayıyordu ve 10'dan fazla yanlış-kırmızı verdi — üstelik bir kısmı
    tam da taşımayı ANLATAN açıklamalardı ("`pf/`den taşındı"). Bu kapının konusu
    çalıştırılan satırdır; yorum bayatlarsa kimse yanlış yola gitmez.

    Tırnak-farkındadır: `"#kanal"` gibi dize içi `#` yorum sayılmaz — yoksa kapı
    kendi kapsamını sessizce daraltırdı.

    D5.30 (B-10.261) `kabuk=True` (bash / PowerShell / YAML / bat): `#` YALNIZ sözcük başında (satır başı ya da boşluktan sonra)
    yorumdur — `${#PWD}`, `$#`, `a#b` yorum DEĞİLDİR. Eski kural `[ ${#PWD} -gt 0 ] && cd pf` satırını `[ $` noktasında kesip
    ARKASINDAKİ `cd pf`yi görünmez yapıyordu.
    """
    tirnak = None
    for i, ch in enumerate(satir):
        if tirnak:
            if ch == tirnak:
                tirnak = None
        elif ch in ("'", '"'):
            tirnak = ch
        elif ch == "#" and (not kabuk or i == 0 or satir[i - 1].isspace()):
            return satir[:i]
    return satir


def _kabuk_desenleri(eski: str) -> list[re.Pattern[str]]:
    """F4 adları için kabuk / CI dosyalarındaki YOL kullanımı (bkz. `TASINMIS_KABUK`)."""
    a = re.escape(eski)
    return [
        re.compile(r"(?<![\w.$/\\-])" + a + r"(?=[/\\])"),
        re.compile(r"(?:\bcd|-[dfe])\s+[\"']?(?:\./)?" + a + r"[\"']?(?![\w./\\-])"),
        # CI / compose: `working-directory: services`, `context: ./utils` (yalın değer)
        re.compile(r"\b(?:working-directory|context|cwd|path|dir)\s*:\s*[\"']?(?:\.{1,2}/)*" + a + r"[\"']?\s*$"),
    ]


def docstring_satirlari(metin: str) -> set[int]:
    """Python docstring'lerinin kapladığı satır numaraları.

    ⚠️ Yorum ayıklama YETMEDİ: bu deponun test dosyaları uzun Türkçe ANLATI docstring'leri
    taşıyor ve 4'ü eski dizin adını geçmişi anlatmak için anıyor. `#` ayıklayıcı onları
    görmez. Docstring tanım gereği çalıştırılmaz — kapsam dışıdır. Ayıklama `ast` ile
    yapılır; kaba üç-tırnak taraması GERÇEK yol dizelerini de yerdi.
    """
    import ast
    import warnings

    try:
        with warnings.catch_warnings():  # depoda birkaç dosyada ham `\s` var; konumuz değil
            warnings.simplefilter("ignore", DeprecationWarning)
            agac = ast.parse(metin)
    except SyntaxError:
        return set()
    satirlar: set[int] = set()
    for dugum in ast.walk(agac):
        if not isinstance(dugum, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        govde = getattr(dugum, "body", None)
        if not govde:
            continue
        ilk = govde[0]
        if isinstance(ilk, ast.Expr) and isinstance(ilk.value, ast.Constant) and isinstance(ilk.value.value, str):
            satirlar.update(range(ilk.lineno, (ilk.end_lineno or ilk.lineno) + 1))
    return satirlar


def _ihlaller() -> dict[str, list[str]]:
    bulgu: dict[str, list[str]] = {}
    for rel in _izlenen_calisan_dosyalar():
        try:
            metin = (KOK / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:  # D5.30: okunamayan çalışan dosya ATLANMAZ — ölçülmedi demektir
            bulgu.setdefault(rel, []).append(f"OKUNAMADI ({type(e).__name__}) — kapı bu dosyayı ölçemedi")
            continue
        atlanan = docstring_satirlari(metin) if rel.endswith((".py", ".spec")) else set()
        kabuk = Path(rel).suffix.lower() in KABUK_UZANTILAR
        desenler = [_desen(eski) for eski in TASINMIS]
        if kabuk:
            desenler += [d for eski in TASINMIS_KABUK for d in _kabuk_desenleri(eski)]
        for no, satir in enumerate(metin.splitlines(), 1):
            if no in atlanan:
                continue
            kod = yorumsuz(satir, kabuk=kabuk)
            if any(d.search(kod) for d in desenler):
                bulgu.setdefault(rel, []).append(f"{no}: {satir.strip()[:100]}")
    return bulgu


def test_KRITIK_tasinmis_dizin_adi_calisan_kodda_YOK():
    """🔴 ASIL REGRESYON: taşıma sonrası betikte kalan eski yol → o platformda build ÖLÜR."""
    dosyalar = _izlenen_calisan_dosyalar()
    assert len(dosyalar) > 100, f"tarama çok dar ({len(dosyalar)}) — kapı boş dönüyor olabilir"

    bulgu = _ihlaller()
    assert not bulgu, (
        "Taşınmış dizin adı ÇALIŞAN kodda duruyor:\n"
        + "\n".join(f"  {k}\n    " + "\n    ".join(v) for k, v in sorted(bulgu.items()))
        + f"\nEşleme: {TASINMIS}. Bu satırlar çalıştıklarında var olmayan yola giderler."
    )


def test_KARSIT_KANIT_kapi_gercekten_yakaliyor():
    """Kapı boş geçmiyor: `build_mac.sh`in 2026-09-18'deki bozuk hâli YAKALANMALI."""
    d = _desen("pf")
    for bozuk in (
        '[[ -d pf ]] || die "pf/ (Expo frontend) yok."',
        "( cd pf && npm ci --legacy-peer-deps )",
        "cp -R pf/dist frontend/dist",
        "  working-directory: pf",
        r'$FrontendDir = Join-Path $ProjectRoot "pf"',
        "context: ../pf",
        'Info "pf web export -> frontend\\dist kopyalandi."',
    ):
        # ⚠️ `yorumsuz`tan GEÇİRİLEREK ölçülür: yorum ayıklama kapıyı KÖRLEŞTİRMEMELİ.
        assert d.search(yorumsuz(bozuk)), f"kapı KAÇIRIYOR: {bozuk}"

    dw = _desen("pemf-vet-web")
    assert dw.search(yorumsuz("cd pemf-vet-web && npm run build")), "web taşıması KAÇIRILIYOR"


def test_KARSIT_KANIT_yorum_ayiklama_KODU_kesmiyor():
    """Yorum ayıklayıcı fazla yemiyor: dize içi `#` kodu kesmemeli."""
    assert yorumsuz('curl "https://x/y#frag" && cd pf') == 'curl "https://x/y#frag" && cd pf'
    assert yorumsuz("cd pf  # apps/ui'ye taşındı") == "cd pf  "
    assert yorumsuz("# cd pf") == ""
    # Kapının asıl kanıtı: YORUM kırmızı vermez ama AYNI metin KOD olarak verir.
    d = _desen("pf")
    assert not d.search(yorumsuz("# eskiden pf/dist okunuyordu")), "yorum ihlal sayılıyor"
    assert d.search(yorumsuz("cp -R pf/dist frontend/dist")), "kod kaçırılıyor"


def test_KARSIT_KANIT_docstring_ayiklama_KOD_DIZESINI_kesmiyor():
    """Docstring ayıklayıcı yalnız docstring'i yer; aynı dosyadaki KOD dizesi korunur.

    Bu, kapının en kolay körelme yoludur: üç-tırnak gören her şeyi atlamak, gerçek
    `Path("pf") / "dist"` satırını da kapsam dışına çıkarırdı.
    """
    ornek = '"""Bu docstring pf/dist anlatır."""\nyol = "pf/dist"\nbaska = """pf/x"""\n'
    atlanan = docstring_satirlari(ornek)
    assert 1 in atlanan, "modül docstring'i ayıklanmıyor — kapı yanlış kırmızı verir"
    assert 2 not in atlanan, "KOD satırı docstring sanıldı — kapı körelir"
    # 3. satır bir atama değeri; docstring DEĞİL → taranmaya devam etmeli.
    assert 3 not in atlanan, "üç-tırnaklı DEĞER docstring sanıldı — kapı körelir"


def test_KARSIT_KANIT_mesru_kullanim_YANLIS_KIRMIZI_vermez():
    """`pf` daha uzun adların parçası olarak her yerde geçer; kapı onlara dokunmamalı."""
    d = _desen("pf")
    for temiz in (
        "PEMF_ESP_ENABLED=1",
        "from scripts import pf_kalan",
        "sertifika.pfx dosyasi",
        "apps/ui/dist",
        "pemf-vet-web.vercel.app",  # ⚠️ CANLI alan adı — asla yeniden adlandırılmaz
        "$LASTEXITCODE -ne 0",
    ):
        assert not d.search(temiz), f"YANLIŞ KIRMIZI: {temiz}"

    dw = _desen("pemf-vet-web")
    assert not dw.search("https://pemf-vet-web.vercel.app/api/health"), (
        "CANLI alan adı yol sanıldı — bu kapı deploy URL'sini bozmamalı"
    )


def test_KARSIT_KANIT_D5_30_F4_adlari_kabukta_YAKALANIR_importta_YAKALANMAZ():
    desenler = [d for eski in TASINMIS_KABUK for d in _kabuk_desenleri(eski)]
    for bozuk in (
        "( cd servers && npm ci )",
        "cp -R utils/x dist",
        '[[ -d controllers ]] || exit 1',
        "  working-directory: ./services",
    ):
        assert any(d.search(yorumsuz(bozuk, kabuk=True)) for d in desenler), f"F4 kabuk yolu KAÇIRILIYOR: {bozuk}"
    for temiz in (
        "from utils.x import y",
        "python apps/backend/utils/x.py",
        "cd apps/backend/servers",
        "$env:PEMF_DB = $database_url",
        "my_services/x",
    ):
        assert not any(d.search(yorumsuz(temiz, kabuk=True)) for d in desenler), f"YANLIŞ KIRMIZI: {temiz}"


def test_KARSIT_KANIT_D5_30_bash_dolar_diyez_YORUM_SAYILMAZ():
    d = _desen("pf")
    assert d.search(yorumsuz("[ ${#PWD} -gt 0 ] && cd pf", kabuk=True)), (
        "${#…} yorum sanıldı — arkasındaki kod görünmez"
    )
    assert d.search(yorumsuz('[ $# -eq 0 ] && cd pf', kabuk=True)), "$# yorum sanıldı"
    assert not d.search(yorumsuz("echo x # cd pf", kabuk=True)), "gerçek kabuk yorumu ihlal sayıldı"


def test_KARSIT_KANIT_D5_30_aksanli_yollar_COZULUR():
    """`-z` + UTF-8: aksanlı izlenen yol tırnaksız ve gerçek adıyla listelenir (DEMA simülatörü ağacı)."""
    izlenen = _izlenen_dosyalar()
    assert "dema-terapi-simülatörü/README.md" in izlenen, (
        "aksanlı yol çözülmüyor (tırnaklı / kaçışlı) — o ağaç kapı dışı kalır"
    )
    assert not [y for y in izlenen if y.startswith('"')], "tırnaklı (kaçışlı) yol kaldı"


def test_KARSIT_KANIT_esleme_tablosu_BOSALTILMAMIS():
    """ "Kırmızıyı sustur" diye tabloyu ya da muafiyeti şişiren yamayı yakalar."""
    assert len(TASINMIS_KABUK) == TASINMIS_KABUK_SAYISI, f"F4 kabuk tablosu değişmiş: {TASINMIS_KABUK}"
    assert KABUK_UZANTILAR >= {".sh", ".ps1", ".yml"}, "kabuk uzantı kapsamı daraltılmış"
    assert len(TASINMIS) == TASINMIS_SAYISI, (
        f"eşleme tablosu değişmiş ({len(TASINMIS)} ≠ {TASINMIS_SAYISI}) — bilinçli "
        "eklemede bu sayı da güncellenir, SİLMEDE kapı sessizce boşalır"
    )
    assert len(MUAF_DOSYALAR) <= 3, f"muafiyet listesi şişmiş: {MUAF_DOSYALAR}"
    assert CALISAN_UZANTILAR >= {".sh", ".ps1", ".py", ".yml"}, "uzantı kapsamı daraltılmış"
