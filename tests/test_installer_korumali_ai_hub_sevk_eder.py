# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""INNO INSTALLER KORUMASIZ `ai_hub` SEVK EDİYORDU (bulgu 30, cid. 5).

`build_tools/build_installer.ps1` `guii\\dist`i temizleyip KENDİ PyInstaller'ını koşuyor ve
`scripts/build_backend_exe.ps1:193-216`'daki KOD KORUMA adımını (compile_pyd.py / encrypt_sources.py)
HİÇ çalıştırmıyordu. ISCC'yi de `/DBuildOutput` vermeden çağırdığı için `.iss` varsayılanı
(`..\\dist\\PEMF_Backend`) düz kaynağı installer'a koyuyordu. Diskte ölçüldü — ikisi de VERSION=1.9.15:

    dist/PEMF_Backend/_internal/ai_hub        -> 62 .py / 0 .pyd    <- Inno bunu paketliyordu
    PEMF_BUILD/dist/PEMF_Backend/.../ai_hub   -> 49 .pyd / 13 .py   <- base.zip kaynağı

Yani aynı sürüm numarası altında **iki farklı yazılım** dağıtılıyordu ve installer kanalı korumasız
kaynak sevk ediyordu. Deponun kendi ilkesi bunu yasaklıyor: *"onefile da olsa onedir de olsa client
de olsa pyd olmalı; koruma prosedürel değil YAPISAL olur"*.

DÜZELTME: (1) installer kendi PyInstaller'ını koşmayı bırakır, `build_backend_exe.ps1`e delege eder
(`-SkipWeb`, ASLA `-SkipProtect`); (2) ISCC'ye `/DBuildOutput=<korumalı ağaç>` geçilir; (3) ISCC'den
ÖNCE yapısal bir koruma kapısı koşar; (4) `.iss` varsayılanı da korumalı ağaca çevrilir.

⚠️ KAPI ZORUNLU: `build_backend_exe.ps1:198-200` MSVC yoksa yalnızca UYARIR ve korumasız ağaç
bırakır; Inno yolunda `make_base_zip` gibi bir downstream kapı YOKTUR.
⚠️ ONEFILE'A GEÇİLMEDİ (ölçülüp reddedilmiş sahip kararı); üç mevcut koruma kapısı da AYNEN kaldı —
bu dördüncü bir kapıdır.

⚠️ BU TESTLER GERÇEK BUILD KOŞMAZ: ne PyInstaller ne ISCC. Betikten `=== ... ===` çıpaları arasındaki
GERÇEK PowerShell blokları çıkarılıp stub'larla koşturulur (teknik:
`tests/test_installer_frontend_aynalama.py`). Ölçüm metin araması DEĞİL — stub'ların yazdığı argv
DOSYALARI ve proses ÇIKIŞ KODU üzerinden yapılır, dolayısıyla yorum/docstring içine doğru deseni
yazmakla geçilemez (bu depoda o hata dört kez oldu).
"""

import os
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
BETIK = KOK / "build_tools" / "build_installer.ps1"

_PWSH = None
for _ad in ("pwsh", "powershell"):
    import shutil as _sh

    if _sh.which(_ad):
        _PWSH = _sh.which(_ad)
        break


def _blok(bas: str, son: str) -> str:
    """Betikten iki çıpa arasındaki GERÇEK PowerShell bloğunu çıkar.

    ⚠️ Çıpa yoksa test ATLAMAZ, açık `AssertionError` verir: sessiz atlama, kapının kaybolmasını
    "yeşil" gösterirdi."""
    ham = BETIK.read_text(encoding="utf-8")
    i = ham.find(bas)
    j = ham.find(son)
    assert i != -1, f"cipa BULUNAMADI: {bas} — kapi tasinmis/silinmis olabilir"
    assert j > i, f"kapanis cipasi BULUNAMADI: {son}"
    return ham[i + len(bas) : j]


def _kos(govde: str, tmp: Path, hazirlik: str = "") -> subprocess.CompletedProcess:
    betik = tmp / "surucu.ps1"
    betik.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "function Write-Step($m) { Write-Host \"STEP: $m\" }\n"
        "function Write-OK($m)   { Write-Host \"OK: $m\" }\n"
        "function Write-Warn($m) { Write-Host \"WARN: $m\" }\n"
        "function Write-Fail($m) { Write-Host \"FAIL: $m\"; exit 9 }\n"
        f"{hazirlik}\n{govde}\n"
        'Write-Host "OUTPUTDIR=$OutputDir"\n',
        encoding="utf-8",
    )
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(betik)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp),
    )


def _iscc_stub(tmp: Path) -> Path:
    p = tmp / "iscc_stub.ps1"
    p.write_text(
        "$args -join [Environment]::NewLine | Set-Content -Path "
        f"'{(tmp / 'iscc_argv.txt').as_posix()}' -Encoding UTF8\nexit 0\n",
        encoding="utf-8",
    )
    return p


def _ai_hub_kur(kok: Path, dosyalar: dict) -> Path:
    d = kok / "dist" / "PEMF_Backend" / "_internal" / "ai_hub"
    d.mkdir(parents=True, exist_ok=True)
    for rel, icerik in dosyalar.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(icerik, encoding="utf-8")
    return kok / "dist" / "PEMF_Backend"


def _ps_kodu(ham: str) -> str:
    """PowerShell kaynağından SATIR yorumu (`#`), BLOK yorumu (`<# .. #>`) ve HERE-STRING
    (`@" .. "@` / `@' .. '@`) içeriklerini SOY.

    ⚠️ NEDEN (denetim 2026-08-17): eski soyucu yalnız `#` ile BAŞLAYAN satırı atıyordu. `<#` ile
    başlayan bir satır `#` ile başlamadığı için GEÇİYOR ve blok içindeki GERÇEK kod satırları
    `kod`da kalıyordu → bir kod bloğunu yorum içine almak onu YÜRÜTÜLMEZ yapar ama POZİTİF metin
    iddialarını GEÇİRİRDİ. Aynısı here-string içine yazılan kod için de geçerli.
    ⚠️ KÖR NOKTA (dürüstlük): bir STRING içinde geçen `<#` de blok başlatır. Bugün dosyada yok.
    """
    cikti, blok, here = [], False, None
    for s in ham.splitlines():
        d = s.strip()
        if here is not None:
            if d == here:
                here = None
            continue
        if blok:
            if "#>" in s:
                blok = False
            continue
        # ⚠️ KÖR NOKTA KAPATILDI (denetim 2026-08-17): eskiden satırın HERHANGİ bir yerindeki
        # `<#` blok başlatıyordu, dolayısıyla bir STRING içinde geçen `<#`
        # (ör. `Write-Host "ornek <# metin"`) soyucuyu yanıltıp ondan sonraki GERÇEK kodu
        # yutuyordu. Fazla yutma bir NEGATİF iddiayı (ör. `"--distpath" not in kod`) SAHTE olarak
        # geçirebilirdi — yani kapı yanlış-YEŞİL olurdu.
        # BASİTLEŞTİRME (dürüstçe): blok başlangıcı yalnız satır BAŞINDA kabul edilir. Tam bir
        # PowerShell tırnak/kaçış ayrıştırıcısı YAZILMIYOR. Kaçırdığı şey: gerçek kodun ardından
        # AYNI satırda başlayan bir blok yorumu (`$x = 1 <#` ...). O durumda soyucu bloğu hiç
        # görmez ve blok içindeki satırlar `kod`da kalır — yani hata YÖNÜ güvenli tarafa döner
        # (fazla yutmak yerine az yutmak: negatif iddia sahte geçmez, pozitif iddia zaten kod
        # satırına bakar).
        if d.startswith("<#"):
            blok = "#>" not in d[2:]
            s = ""
            d = ""
        if d.endswith('@"') or d.endswith("@'"):
            here = '"@' if d.endswith('@"') else "'@"
            cikti.append(s.split("#")[0])
            continue
        if d.startswith("#"):
            continue
        cikti.append(s.split("#")[0])
    return chr(10).join(cikti)


# ── T4: çıpa/metin emniyet ağı — PowerShell'siz ortamda da koşar ──────────────


def test_cipalar_ve_kapi_metni_yerinde():
    """PowerShell'siz (Linux CI) ortamda ince emniyet ağı. ASIL iddialar T1-T3'te DAVRANIŞSALDIR.

    ⚠️ Yorum satırları ATILIR: kusuru açıklayan ya da doğru deseni anlatan bir yorum kapıyı
    geçemesin."""
    ham = BETIK.read_text(encoding="utf-8")
    for cipa in (
        "=== PEMF-BACKEND-BUILD-BASI ===",
        "=== PEMF-BACKEND-BUILD-SONU ===",
        "=== PEMF-KORUMA-KAPISI-BASI ===",
        "=== PEMF-KORUMA-KAPISI-SONU ===",
    ):
        assert cipa in ham, f"cipa YOK: {cipa}"

    kod = _ps_kodu(ham)
    assert "/DBuildOutput=$OutputDir" in kod, "ISCC'ye /DBuildOutput GECILMIYOR"
    assert "-SkipProtect" not in kod, "delegeye -SkipProtect gecilmis (koruma atlanir)"
    assert "build_backend_exe.ps1" in kod, "korumali build'e delege EDILMIYOR"
    # ⚠️ Ölçüt "PyInstaller adı geçmesin" DEĞİL: `-m PyInstaller --version` (kurulu mu kontrolü)
    # MEŞRUDUR ve korunur. Yasak olan bir PyInstaller **BUILD**'i koşmak — onun imzası spec/distpath.
    assert "--distpath" not in kod, "installer HALA kendi PyInstaller BUILD'ini kosuyor (--distpath)"
    assert "PEMF_Backend_onedir.spec" not in kod, (
        "installer spec'i DOGRUDAN kosuyor → koruma adimi atlanir (build_backend_exe.ps1'e delege edilmeli)"
    )


def test_iss_varsayilani_KORUMALI_agaci_gosterir():
    """`.iss` varsayılanı da korumalı ağaç olmalı: çıplak `iscc` / Inno IDE Build yolları için.

    ⚠️ SERTLEŞTİRİLDİ (denetim 2026-08-17): eski hâli `"#define BuildOutput" in s` ile PREFIX
    eşleşmesi yapıyordu (`#define BuildOutputEski` de eşleşirdi) ve YALNIZ İLK eşleşmeye bakıyordu.
    Inno preprocessor `#define`ı YENİDEN TANIMLAYABİLİR; ikinci tanım ilkini EZER ve yalnız ilkine
    bakan bir kapı YANLIŞ-YEŞİL olur."""
    import re

    iss = (KOK / "build_tools" / "PEMF_Backend_Setup.iss").read_text(encoding="utf-8")
    kod = [s for s in iss.splitlines() if not s.strip().startswith(";")]

    tanimlar = [s for s in kod if re.match(r"\s*#\s*define\s+BuildOutput\b", s)]
    assert tanimlar, "`.iss`de #define BuildOutput YOK -> ciplak iscc yolunda varsayilan belirsiz"
    assert len(tanimlar) == 1, f"BuildOutput birden fazla tanimlanmis, ETKIN olan belirsiz: {tanimlar}"
    assert "PEMF_BUILD" in tanimlar[0], f".iss varsayilani hala korumasiz agaci gosteriyor: {tanimlar[0].strip()}"
    # `/DBuildOutput` override'i bozulmasın.
    assert any(re.match(r"\s*#\s*ifndef\s+BuildOutput\b", s) for s in kod), (
        "#ifndef BuildOutput kalkmis -> /DBuildOutput override'i ETKISIZ kalabilir"
    )


# ── T1-T3: gerçek PowerShell blokları, stub'larla ────────────────────────────

pwsh_gerekli = pytest.mark.skipif(_PWSH is None or os.name != "nt", reason="Windows PowerShell yok")


@pwsh_gerekli
@pytest.mark.parametrize(
    "dosyalar, beklenen_fail",
    [
        ({"__init__.py": "", "inference_em_fantom.py": "x=1"}, True),  # duz .py -> DUR
        ({"__init__.py": "", "inference_x/lib/helper.py": "x=1"}, True),  # ic ice -> DUR (ozyineleme)
        ({"__init__.py": "", "inference_x/__init__.py": "", "m.pyenc": "sifreli"}, False),  # mesru
        ({"__init__.py": "", "m.cp310-win_amd64.pyd": "PYD"}, False),  # normal korumali
    ],
    ids=["duz_py", "ic_ice_duz_py", "pyenc_yedek", "korumali_pyd"],
)
def test_KRITIK_koruma_kapisi_duz_py_gorurse_ISCC_HIC_CAGRILMAZ(tmp_path, dosyalar, beklenen_fail):
    """Kapı düz `.py` görürse installer ÜRETİLMEMELİ — ISCC'ye hiç varılmamalı.

    ⚠️ Negatif iddia tek başına yanlış-yeşil olabilirdi (stub'a hiç ulaşılmaması de argv dosyası
    üretmez). Bu yüzden AYNI kabloyla pozitif vakalar da (pyenc/pyd) koşuluyor: onlarda argv dosyası
    OLUŞMAK ZORUNDA."""
    cikti = _ai_hub_kur(tmp_path, dosyalar)
    iscc = _iscc_stub(tmp_path)
    (tmp_path / "PEMF_Backend_Setup.iss").write_text("; kukla", encoding="utf-8")

    hazirlik = (
        f"$OutputDir = '{cikti.as_posix()}'\n"
        f"$IsccExe   = '{iscc.as_posix()}'\n"
        f"$IssFile   = '{(tmp_path / 'PEMF_Backend_Setup.iss').as_posix()}'\n"
        "$Mode = 'device'\n$startTime2 = Get-Date\n"
    )
    govde = _blok("=== PEMF-KORUMA-KAPISI-BASI ===", "=== PEMF-KORUMA-KAPISI-SONU ===")
    r = _kos(govde, tmp_path, hazirlik)
    argv = tmp_path / "iscc_argv.txt"

    if beklenen_fail:
        assert r.returncode != 0, f"korumasiz agac ile installer URETILDI: {r.stdout[-500:]}"
        assert not argv.exists(), "kapi reddetmesine ragmen ISCC CAGRILDI"
        assert "KORUMASIZ" in r.stdout, f"hangi dosyanin korumasiz oldugu SOYLENMEDI: {r.stdout[-400:]}"
    else:
        assert r.returncode == 0, f"mesru korumali agac REDDEDILDI: {r.stdout[-600:]}"
        assert argv.exists(), "mesru agacta ISCC CAGRILMADI"


@pwsh_gerekli
def test_KRITIK_ai_hub_HIC_YOKSA_da_DURUR(tmp_path):
    """ "Düz .py yok, çünkü ai_hub hiç yok" yanlış-yeşilini kapatır."""
    cikti = tmp_path / "dist" / "PEMF_Backend"
    (cikti / "_internal").mkdir(parents=True)
    iscc = _iscc_stub(tmp_path)
    (tmp_path / "k.iss").write_text("; kukla", encoding="utf-8")
    hazirlik = (
        f"$OutputDir = '{cikti.as_posix()}'\n$IsccExe = '{iscc.as_posix()}'\n"
        f"$IssFile = '{(tmp_path / 'k.iss').as_posix()}'\n$Mode = 'device'\n$startTime2 = Get-Date\n"
    )
    r = _kos(_blok("=== PEMF-KORUMA-KAPISI-BASI ===", "=== PEMF-KORUMA-KAPISI-SONU ==="), tmp_path, hazirlik)

    assert r.returncode != 0, f"ai_hub'i HIC OLMAYAN agac sessizce paketlendi: {r.stdout[-400:]}"
    assert not (tmp_path / "iscc_argv.txt").exists()


@pwsh_gerekli
def test_KRITIK_ISCC_ye_DBuildOutput_GECILIR(tmp_path):
    """ISCC korumalı ağacı `/DBuildOutput` ile ALMALI — yoksa `.iss` varsayılanına düşer."""
    cikti = _ai_hub_kur(tmp_path, {"__init__.py": "", "m.cp310-win_amd64.pyd": "PYD"})
    iscc = _iscc_stub(tmp_path)
    (tmp_path / "k.iss").write_text("; kukla", encoding="utf-8")
    hazirlik = (
        f"$OutputDir = '{cikti.as_posix()}'\n$IsccExe = '{iscc.as_posix()}'\n"
        f"$IssFile = '{(tmp_path / 'k.iss').as_posix()}'\n$Mode = 'device'\n$startTime2 = Get-Date\n"
    )
    r = _kos(_blok("=== PEMF-KORUMA-KAPISI-BASI ===", "=== PEMF-KORUMA-KAPISI-SONU ==="), tmp_path, hazirlik)
    assert r.returncode == 0, r.stdout[-600:]

    satirlar = (tmp_path / "iscc_argv.txt").read_text(encoding="utf-8").splitlines()
    assert "/DModeName=device" in satirlar, f"ModeName akisi bozuldu: {satirlar}"
    define = next((s for s in satirlar if s.startswith("/DBuildOutput=")), None)
    assert define, f"/DBuildOutput GECILMEDI → .iss varsayilanina duser: {satirlar}"

    # ⚠️ Sabit-kodlanmış bir yol da bu karşılaştırmada düşer.
    verilen = os.path.normcase(os.path.realpath(define.split("=", 1)[1]))
    assert verilen == os.path.normcase(os.path.realpath(str(cikti))), (
        f"/DBuildOutput sevk agacini GOSTERMIYOR: {define}"
    )


@pwsh_gerekli
def test_KRITIK_installer_kendi_PyInstallerini_KOSMAZ(tmp_path):
    """Backend build KORUMALI betiğe delege edilmeli; installer kendi PyInstaller'ını koşmamalı."""
    (tmp_path / "scripts").mkdir()
    delege = tmp_path / "scripts" / "build_backend_exe.ps1"
    delege.write_text(
        "$args -join [Environment]::NewLine | Set-Content -Path "
        f"'{(tmp_path / 'delege_argv.txt').as_posix()}' -Encoding UTF8\n"
        "$i = [array]::IndexOf($args, '-BuildRoot')\n"
        "$kok = if ($i -ge 0) { $args[$i+1] } else { Join-Path $PWD 'PEMF_BUILD' }\n"
        "$d = Join-Path $kok 'dist\\PEMF_Backend\\_internal\\ai_hub'\n"
        "New-Item -ItemType Directory -Path $d -Force | Out-Null\n"
        "Set-Content -Path (Join-Path $d 'x.pyd') -Value 'PYD'\n"
        "Set-Content -Path (Join-Path (Split-Path (Split-Path $d)) 'PEMF_Backend.exe') -Value 'EXE'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    py_stub = tmp_path / "py_stub.ps1"
    py_stub.write_text(
        f"$args -join ' ' | Set-Content -Path '{(tmp_path / 'python_argv.txt').as_posix()}' -Encoding UTF8\nexit 0\n",
        encoding="utf-8",
    )

    hazirlik = f"$ProjectRoot = '{tmp_path.as_posix()}'\n$PythonExe = '{py_stub.as_posix()}'\n"
    r = _kos(_blok("=== PEMF-BACKEND-BUILD-BASI ===", "=== PEMF-BACKEND-BUILD-SONU ==="), tmp_path, hazirlik)
    assert r.returncode == 0, f"delege bloku patladi: {r.stdout[-700:]}"

    assert (tmp_path / "delege_argv.txt").exists(), "korumali build'e DELEGE EDILMEDI"
    argv = (tmp_path / "delege_argv.txt").read_text(encoding="utf-8")
    assert "-BuildRoot" in argv, f"-BuildRoot gecilmedi: {argv!r}"
    assert "-SkipWeb" in argv, f"-SkipWeb gecilmedi (web export iki kez kosar): {argv!r}"
    assert "-SkipProtect" not in argv, f"YASAKLI -SkipProtect gecildi → koruma atlanir: {argv!r}"

    assert not (tmp_path / "python_argv.txt").exists(), (
        "installer HALA kendi PyInstaller'ini kosuyor (korumasiz agac uretir)"
    )

    cikti = next(s for s in r.stdout.splitlines() if s.startswith("OUTPUTDIR="))
    yol = cikti.split("=", 1)[1].strip()
    assert yol, "OutputDir bos"
    assert os.path.normcase(os.path.realpath(yol)) == os.path.normcase(
        os.path.realpath(str(tmp_path / "PEMF_BUILD" / "dist" / "PEMF_Backend"))
    ), f"sevk agaci DELEGE EDILEN agac degil: {yol}"


# ── Soyucunun KENDİ birim testleri (denetim 2026-08-17) ──────────────────────


@pytest.mark.parametrize(
    "kaynak, olmali, olmamali",
    [
        # (1) Satır yorumu
        ("# gizli\nWrite-Host 'kod'", "kod", "gizli"),
        # (2) Satır SONU yorumu
        ("Write-Host 'kod'  # aciklama", "kod", "aciklama"),
        # (3) Blok yorumu — içindeki kod YUTULMALI
        ("<#\n& $Iscc /DBuildOutput=X\n#>\nWrite-Host 'kod'", "kod", "DBuildOutput"),
        # (4) Here-string — içeriği YUTULMALI
        ("$m = @'\n--distpath yasak\n'@\nWrite-Host 'kod'", "kod", "--distpath"),
    ],
    ids=["satir_yorumu", "satir_sonu", "blok_yorumu", "here_string"],
)
def test_ps_soyucu_dogru_yutar(kaynak, olmali, olmamali):
    """⚠️ (5) ASIL DÜZELTME: eskiden string içindeki `<#` bloğu başlatıyor ve ondan SONRAKİ gerçek
    kod yutuluyordu. Fazla yutma, `"--distpath" not in kod` gibi NEGATİF iddiaları SAHTE olarak
    geçirir — kapı yanlış-YEŞİL olur."""
    kod = _ps_kodu(kaynak)
    assert olmali in kod, f"gercek kod YUTULDU: {kod!r}"
    assert olmamali not in kod, f"yorum/here-string icerigi SIZDI: {kod!r}"


def test_KRITIK_STRING_icindeki_blok_isareti_SONRAKI_kodu_YUTMAZ():
    """⚠️ ASIL DÜZELTME (denetim 2026-08-17): bir STRING içinde geçen `<#` blok BAŞLATMAMALI.

    Eskiden satırın herhangi bir yerindeki `<#` bloğu açıyordu, dolayısıyla
    `Write-Host "ornek <# metin"` gibi masum bir satır soyucuyu yanıltıp ondan SONRAKİ gerçek kodu
    yutuyordu. Fazla yutma, `"--distpath" not in kod` gibi NEGATİF iddiaları SAHTE olarak geçirir —
    yani kapı yanlış-YEŞİL olur.
    ⚠️ Yalnız VARLIK iddia edilir: `ornek` gerçek kod içeriğidir (yorum değil), silinmesi
    beklenmez."""
    kod = _ps_kodu('Write-Host "ornek <# metin"\n& $Iscc /DBuildOutput=$OutputDir')
    assert "/DBuildOutput" in kod, f"STRING icindeki `<#` blok sandi ve SONRAKI GERCEK KODU yuttu: {kod!r}"


def test_ps_soyucu_KOR_NOKTASI_kayda_gecti():
    """⚠️ Bilinen sınır: gerçek kodun ARDINDAN aynı satırda başlayan blok yorumu görülmez.

    Hata yönü GÜVENLİ tarafta (az yutmak): blok içindeki satırlar `kod`da kalır, yani negatif
    iddia sahte geçmez. Bu test o sınırı DAVRANIŞ olarak kayda geçiriyor ki ileride biri onu
    "düzeltilmiş" sanmasın."""
    kod = _ps_kodu("$x = 1 <#\n--distpath burada\n#>")
    assert "--distpath" in kod, "sinir DEGISTI: artik satir-ici blok da yutuluyor (kayit guncellenmeli)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
