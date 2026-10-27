# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ÜRÜN ÇALIŞIRKEN KENDİNE PAKET KURMAZ — denetim 2026-08-28 #10.

Sevk edilen backend, her AI modeli yüklendiğinde ultralytics'in bağımlılık denetimine giriyor,
`onnxruntime`'ı EKSİK sanıyor ve şunu deniyordu:

    "…\\PEMF_Backend.exe" -m pip install --no-cache-dir onnxruntime      → exit 2

Ürün kendi EXE'sini alt-süreç olarak başlatıp kendine paket kuruyordu. Ölçülen zarar: destek
mühendisini var olmayan bir eksik bağımlılığa yönlendiren kırmızı log + model başına ~2,9 sn
(soğuk 3,975 s → yasakla 1,069 s).

İKİ BAĞIMSIZ SAVUNMA var, bu dosya ikisini de kilitler:
  1) BUILD zamanı — `onnxruntime`/`pi-heif` metadata'sı pakete girer (spec kapısı; ayrıca
     spec artık kurulu bir paketin metadata'sı toplanamazsa build'i DÜŞÜRÜR),
  2) ÇALIŞMA anı — pip yasağı. Bu madde metadata düzelse bile KALIR: paketlenmiş bir tıbbi
     cihaz yazılımı çalışırken kendi bağımlılıklarını değiştirmemelidir.

⚠️ Yalnız (1)'i yapmak yetmez: yeni bir bağımlılık eklendiğinde aynı sınıf geri gelir.
⚠️ Yalnız (2)'yi yapmak da yetmez: paket "yalan söylemeye" devam eder (metadata eksik kalır).
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
# Üç giriş noktası: her biri yasağı ultralytics'i çeken ilk importtan ÖNCE kendisi kurar (ai_hub'ı doğrudan import eden yollar için üçüncü kilit).
# Çıpa: AI zincirini çeken GERÇEK import düğümü (modül adı) — ai_hub'ın kendisi çıpa taşımaz (dosyanın geri kalanı alt modül importu değil).
_GIRISLER = {
    "backend": (_KOK / "apps" / "backend" / "backend_service.py", "headless_core"),
    "ai_service": (_KOK / "ai_service" / "app.py", "onnxruntime"),
    "ai_hub": (_KOK / "ai_hub" / "__init__.py", None),
}
_SPEC = _KOK / "build_tools" / "PEMF_Backend_onedir.spec"

# Frozen'da metadata'sı ŞART olan paketler: kodu bundle'a giriyor ama çalışma anında
# `importlib.metadata.version()` ile sorgulanıyor (ya da bir bağımlısı sorguluyor).
_METADATA_SART = ("onnxruntime", "celldetection", "albumentations", "grad-cam", "pi-heif")


# ── 1) Çalışma-anı yasağı ────────────────────────────────────────────────────


def test_KRITIK_yasak_ultralytics_AUTOINSTALLi_kapatir():
    """ultralytics'in pip alt-süreci açan bayrağı kapalı olmalı."""
    from utils.runtime_guards import pip_kurulumunu_yasakla

    pip_kurulumunu_yasakla()
    assert os.environ.get("YOLO_AUTOINSTALL", "").lower() == "false", (
        "YOLO_AUTOINSTALL kapatılmadı → ürün çalışırken 'pip install' alt-süreci açabilir"
    )


# D5.23 (18K devri): eski hâli ultralytics'i EBEVEYNDE import edip AUTOINSTALL'ı okuyordu — sonuç dosyadaki ÖNCEKİ testin env'i kurmasına
# bağlıydı (ölçüldü: tek başına koşunca HEAD'de KIRMIZI, dosyayla YEŞİL; başka bir dosya ultralytics'i önce çekerse ters yönde de kör).
# Bayrak import ANINDA okunduğu için ölçüm ancak TAZE süreçte anlamlıdır: çocuk GERÇEK giriş noktasını içe aktarır, sonra ultralytics'in
# kendi sabitini okur. Karşıt kanıt (giriş noktasısız çocuk) aynı ölçümün True görebildiğini kanıtlar (ölçüm aracı kör değil).
_COCUK_AUTOINSTALL = r'''
import json, os, sys
KOK, GIRIS, CIKTI = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [os.path.join(KOK, "apps", "backend"), KOK, os.path.join(KOK, "ai_service")]
if GIRIS == "backend":
    import backend_service  # noqa: F401  GERÇEK giriş noktası (modül düzeyindeki kilit burada koşar)
elif GIRIS == "ai_service":
    import app  # noqa: F401
elif GIRIS == "ai_hub":
    import ai_hub  # noqa: F401
import ultralytics.utils as U
json.dump({"autoinstall": U.AUTOINSTALL, "env": os.environ.get("YOLO_AUTOINSTALL")}, open(CIKTI, "w"))
'''


def _autoinstall_olc(giris: str, tmp_path: Path) -> dict:
    # Varlık İÇE AKTARMADAN sorulur: ebeveynde `import ultralytics` AUTOINSTALL'ı erken dondurur (sıraya bağlı kapı = bu bulgu).
    if importlib.util.find_spec("ultralytics") is None:
        from capraz import ZORUNLU

        if ZORUNLU:
            pytest.fail(
                "PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama ultralytics kurulu değil — pip yasağının GERÇEK etkisi ölçülemedi"
            )
        pytest.skip("ultralytics kurulu değil")
    betik, cikti = tmp_path / f"autoinstall_{giris}.py", tmp_path / f"autoinstall_{giris}.json"
    betik.write_text(_COCUK_AUTOINSTALL, encoding="utf-8")
    ortam = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTEST_CURRENT_TEST", "YOLO_AUTOINSTALL", "ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS")
    }
    ortam["YOLO_OFFLINE"] = "true"  # karşıt kanıt çocuğunda da ultralytics içe aktarılırken DNS denemesin (18K K3)
    ortam["YOLO_CONFIG_DIR"] = str(tmp_path / "ultralytics_ayar")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(betik), str(_KOK), giris, str(cikti)],
        env=ortam,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        cwd=str(tmp_path),
    )
    assert r.returncode == 0 and cikti.exists(), (
        f"çocuk süreç düştü (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-3000:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8"))


@pytest.mark.parametrize("giris", sorted(_GIRISLER))
def test_yasak_gercekten_ultralytics_davranisini_degistirir(giris, tmp_path):
    """SÖZDE değil GERÇEK etki: GERÇEK giriş noktası içe aktarıldıktan sonra ultralytics kendi AUTOINSTALL sabitini False okumalı.

    Env'i okuyan bizim kodumuz değil, ultralytics'in kendi `utils/__init__.py`'si — bayrak IMPORT ANINDA okunduğu için yasak,
    ultralytics'ten önce kurulmuş olmalı. 'env yazdım' demek yetmez, tüketen kütüphanenin davranışı TAZE süreçte ölçülür.
    """
    s = _autoinstall_olc(giris, tmp_path)
    assert s["autoinstall"] is False, (
        f"{giris}: giriş noktası içe aktarıldıktan sonra ultralytics.utils.AUTOINSTALL hâlâ True ({s}) — yasak kurulmamış ya da "
        "ultralytics IMPORTUNDAN SONRA kurulmuş (bayrak import anında okunur, sonradan set etmek ETKİSİZDİR)"
    )


def test_yasak_olcumu_karsit_kanit_giris_noktasiz_AUTOINSTALL_ACIK(tmp_path):
    """Ölçüm aracının kendisi kör değil: giriş noktası içe aktarılmayan taze süreçte ultralytics varsayılanı (True) görülür."""
    s = _autoinstall_olc("yok", tmp_path)
    assert s["autoinstall"] is True, (
        f"karşıt kanıt: yasaksız taze süreçte AUTOINSTALL True olmalıydı ({s}) — ölçüm aracı KÖR"
    )


def test_ai_hub_import_edilince_yasak_kendiliginden_kurulur():
    """ai_hub'ı doğrudan import eden yollar (test/CLI/scratch) da korunmalı."""
    os.environ.pop("YOLO_AUTOINSTALL", None)
    modul = importlib.import_module("ai_hub")
    importlib.reload(modul)
    assert os.environ.get("YOLO_AUTOINSTALL", "").lower() == "false", "ai_hub import edildiğinde pip yasağı kurulmadı"


def _ust_duzey_deyimler(govde):
    """Modül açılışında koşan deyimler: modül gövdesi + üst düzey `try` gövdesi (def / class İÇİ sayılmaz — çağrı açılışta koşmalı)."""
    for d in govde:
        yield d
        if isinstance(d, ast.Try):
            yield from _ust_duzey_deyimler(d.body)


def _yasak_cagrisi_ve_cipa(dosya: Path, cipa_modul):
    """(takma adlar, yasak ÇAĞRISININ satırı, çıpa import düğümünün satırı) — AST'den, metin araması DEĞİL."""
    deyimler = list(_ust_duzey_deyimler(ast.parse(dosya.read_text(encoding="utf-8")).body))
    takma = {
        a.asname or a.name
        for d in deyimler
        if isinstance(d, ast.ImportFrom) and d.module == "utils.runtime_guards"
        for a in d.names
        if a.name == "pip_kurulumunu_yasakla"
    }
    cagri = next(
        (
            d.lineno
            for d in deyimler
            if isinstance(d, ast.Expr)
            and isinstance(d.value, ast.Call)
            and isinstance(d.value.func, ast.Name)
            and d.value.func.id in takma
        ),
        None,
    )
    cipa = None
    if cipa_modul:
        cipa = next(
            (
                d.lineno
                for d in deyimler
                if (isinstance(d, ast.ImportFrom) and d.module == cipa_modul)
                or (isinstance(d, ast.Import) and any(a.name == cipa_modul for a in d.names))
            ),
            None,
        )
    return takma, cagri, cipa


@pytest.mark.parametrize("giris", sorted(_GIRISLER))
def test_giris_noktalari_yasagi_ULTRALYTICSTEN_ONCE_cagiriyor(giris):
    """Sıra kilidi: `pip_kurulumunu_yasakla` ÇAĞRISI, ultralytics'i çeken importlardan önce olmalı.

    Kaynak sırası kontrol edilir çünkü yanlış sıra SESSİZDİR — kapı 'kurulu' görünür, bayrak
    zaten okunmuş olduğu için hiçbir işe yaramaz.
    """
    # ⚠️ D5.23 (B-10.114): eski hâl `metin.find("pip_kurulumunu_yasakla")` ile IMPORT satırını buluyordu — `_pip_yasakla()` çağrısı
    # `pass` yapılınca ya da yorum içine alınınca kapı YEŞİL kalıyordu (ölçüldü). Artık AST: modül açılışında koşan bir Call düğümü,
    # adı `utils.runtime_guards.pip_kurulumunu_yasakla`'nın takma adı olmalı (başka bir işlevi aynı adla içe aktarmak da yakalanır).
    dosya, cipa_modul = _GIRISLER[giris]
    takma, cagri, cipa = _yasak_cagrisi_ve_cipa(dosya, cipa_modul)
    assert takma, f"{dosya.name}: `from utils.runtime_guards import pip_kurulumunu_yasakla` (modül açılışında) YOK"
    assert cagri is not None, (
        f"{dosya.name}: pip yasağı içe aktarılıyor ama modül açılışında ÇAĞRILMIYOR (takma adlar {sorted(takma)}) — "
        "import tek başına hiçbir şey kurmaz"
    )
    if cipa_modul:
        assert cipa is not None, f"{dosya.name}: çıpa import düğümü bulunamadı ({cipa_modul}) — çıpa kaymış olabilir"
        assert cagri < cipa, (
            f"{dosya.name}: pip yasağı çağrısı (satır {cagri}) AI zincirini çeken '{cipa_modul}' importundan (satır {cipa}) "
            "SONRA — ultralytics bayrağı import anında okur, bu sıra etkisizdir"
        )


def test_frozen_DISINDA_bagimlilik_kontrolu_ACIK_kalir_karsit_kanit():
    """Karşı-kanıt: geliştirme ortamında kontrolleri tümden kapatmıyoruz.

    Frozen'da kontrol boşuna (pip zaten çalışamaz, eksik build zamanında yakalanmalı); ama
    geliştirme makinesinde kapatmak GERÇEK bir eksik bağımlılığı gizler."""
    from utils import runtime_guards

    if getattr(sys, "frozen", False):
        pytest.skip("bu koşu frozen — karşı-kanıt geliştirme ortamı içindir")
    os.environ.pop("ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS", None)
    runtime_guards.pip_kurulumunu_yasakla()
    assert "ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS" not in os.environ, (
        "geliştirme ortamında bağımlılık kontrolü kapatılmamalı (gerçek eksikler gizlenir)"
    )


# ── 2) Build zamanı: metadata sözleşmesi ─────────────────────────────────────


# ⚠️ Çıpalar spec METNİNDE aranmaz, AST'de İLGİLİ DÜĞÜME pinlenir. İlk sürüm düz metin
# aramasıydı ve iki mutasyonu birden kaçırdı (ölçüldü): `'onnxruntime'` spec'in BAŞKA bir
# listesinde (satır 57) de geçtiği için metadata listesinden silinince test yeşil kaldı;
# `SystemExit` spec'in AI kapısında da geçtiği için sessiz-yutmaya dönüş de yakalanmadı.
def _spec_agaci():
    import ast

    return ast.parse(_SPEC.read_text(encoding="utf-8"))


def _metadata_listesi() -> list[str]:
    """`_metadata_topla((...))` çağrısına GERÇEKTEN verilen paket adları."""
    import ast

    for dugum in ast.walk(_spec_agaci()):
        if (
            isinstance(dugum, ast.Call)
            and isinstance(dugum.func, ast.Name)
            and dugum.func.id == "_metadata_topla"
            and dugum.args
        ):
            arg = dugum.args[0]
            if isinstance(arg, (ast.Tuple, ast.List)):
                return [e.value for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    pytest.fail("spec'te `_metadata_topla((...))` çağrısı bulunamadı — metadata toplama kaldırılmış olabilir")


def _metadata_fonksiyon_govdesi():
    import ast

    for dugum in ast.walk(_spec_agaci()):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == "_metadata_topla":
            return dugum
    pytest.fail("spec'te `_metadata_topla` fonksiyonu yok")


def test_metadata_listesi_okunabiliyor():
    """Kapının kendisi çalışıyor mu."""
    assert len(_metadata_listesi()) >= 10, "metadata listesi beklenmedik şekilde kısa"


@pytest.mark.parametrize("paket", _METADATA_SART)
def test_KRITIK_spec_metadata_listesi_paketi_iceriyor(paket):
    """Bundle'a metadata'sı girmesi gereken paket, TOPLAMA ÇAĞRISINDA olmalı."""
    liste = _metadata_listesi()
    assert paket in liste, (
        f"'{paket}' spec metadata TOPLAMA listesinde yok → frozen'da "
        f"importlib.metadata.version('{paket}') PackageNotFoundError verir (ilgili modül sessizce "
        f"ölür ya da pip denemesi tetiklenir). Mevcut liste: {liste}"
    )


def test_KRITIK_spec_kurulu_paketin_metadata_hatasini_YUTMAZ():
    """En önemli madde: eski blok `except: print(...)` ile sessizce atlıyordu.

    Ölçülen sonuç — `recursive=True`, ağaçtaki tek bir eksik dağıtımda (`opencv-python-headless`)
    TÜM çağrıyı düşürüyor; celldetection + albumentations + grad-cam metadata'sı HİÇ toplanmıyordu.
    Yani 27 Ağustos arızası için yazılan önlem, arızanın kendi paketini kapsamıyordu ve build
    yine de YEŞİL kalıyordu. Artık kurulu bir paketin metadata'sı alınamazsa build DÜŞER.
    """
    import ast

    govde = _metadata_fonksiyon_govdesi()
    dusuruyor = any(
        isinstance(d, ast.Raise)
        and isinstance(d.exc, ast.Call)
        and isinstance(d.exc.func, ast.Name)
        and d.exc.func.id in {"SystemExit", "RuntimeError"}
        for d in ast.walk(govde)
    )
    assert dusuruyor, (
        "`_metadata_topla`, kurulu bir paketin metadata'sı toplanamadığında build'i DÜŞÜRMÜYOR — "
        "sessiz atlama bu bulgunun ta kendisiydi"
    )
    # Düz (non-recursive) düşüş yolu olmalı: recursive tek eksik bağımlılıkta patlıyor.
    duz_dusus = any(
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "copy_metadata"
        and len(d.args) == 1
        and not d.keywords
        for d in ast.walk(govde)
    )
    assert duz_dusus, "recursive başarısızlığında düz (non-recursive) metadata düşüşü yok"


def test_KRITIK_spec_konsol_mesajlari_ASCII_disi_karakter_TASIMIYOR():
    """PyInstaller konsolu cp1254: ASCII dışı bir karakter build'i UnicodeEncodeError ile DÜŞÜRÜR.

    ÖLÇÜLDÜ (2026-08-28): metadata düzeltmesinin ilk halindeki `→` (U+2192) tam olarak bunu
    yaptı — build, düzeltmenin kendisi yüzünden kırıldı. Bu sınıf daha önce de ısırdı
    (make_manifest cp1252 tuzağı). Yorumlar ve docstring'ler serbesttir (yazdırılmaz);
    kısıt yalnız KONSOLA GİDEN metinler için geçerli: `print(...)` ve `raise SystemExit(...)`.
    """
    import ast

    agac = _spec_agaci()
    sorunlu = []
    for dugum in ast.walk(agac):
        yazdirilan = None
        if isinstance(dugum, ast.Call) and isinstance(dugum.func, ast.Name) and dugum.func.id == "print":
            yazdirilan = dugum
        elif (
            isinstance(dugum, ast.Raise)
            and isinstance(dugum.exc, ast.Call)
            and isinstance(dugum.exc.func, ast.Name)
            and dugum.exc.func.id == "SystemExit"
        ):
            yazdirilan = dugum.exc
        if yazdirilan is None:
            continue
        for alt in ast.walk(yazdirilan):
            if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                try:
                    alt.value.encode("cp1254")
                except UnicodeEncodeError:
                    kotu = [c for c in alt.value if not _cp1254_uyumlu(c)]
                    sorunlu.append(f"satır {alt.lineno}: {kotu} → {alt.value[:60]!r}")

    assert not sorunlu, (
        "Spec'in konsola yazdırdığı metinlerde cp1254'e çevrilemeyen karakter var — build "
        f"UnicodeEncodeError ile DÜŞER (ölçülmüş arıza): {sorunlu}"
    )


def _cp1254_uyumlu(karakter: str) -> bool:
    try:
        karakter.encode("cp1254")
        return True
    except UnicodeEncodeError:
        return False


def _paket_kurulu(ad: str) -> bool:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return bool(version(ad))
    except PackageNotFoundError:
        return False


def _build_makinesi_mi() -> bool:
    """Spec'i GERÇEKTEN çalıştırabilecek ortam mı?

    Kapının sorusu "spec bu paketi toplayabilecek mi" — bu sorunun anlamı yalnız paketi
    toplayacak makinede vardır. PyInstaller'ın varlığı bunun dar ve doğrulanmış işaretidir:
    `requirements-test.txt` onu KURMAZ (ölçüldü), dolayısıyla CI bu daldan geçmez; build
    makinesinde ise zorunlu olarak kuruludur.

    ⚠️ Ortamı "CI mi" diye sormaktan KASITLI olarak kaçınılıyor: `CI` bayrağı, kapıyı kapatmanın
    kolay yolu olur ve zamanla gerçek eksikleri de gizler. Burada ölçülen şey ortamın adı değil,
    YETENEĞİ.
    """
    return _paket_kurulu("pyinstaller")


@pytest.mark.parametrize("paket", _METADATA_SART)
def test_paketler_bu_ortamda_gercekten_KURULU(paket):
    """Liste hayali olmasın: spec'in toplayacağı paketler build makinesinde kurulu olmalı."""
    if _paket_kurulu(paket):
        return
    if not _build_makinesi_mi():
        pytest.skip(f"'{paket}' yok ve bu ortam paketleme yapmıyor (PyInstaller kurulu değil)")
    pytest.fail(
        f"'{paket}' bu ortamda kurulu değil — spec onu toplayamaz ve frozen EXE'de "
        f"ilgili yol sessizce bozulur (build makinesinde `pip install {paket}`)"
    )


# İG-5.51 / D5.23 (B-10.113): F4 taşımasından (283c419, 09-18) beri backend ağacı `apps/backend/` altında; eski kök listesi
# ("servers", "utils", "database", "controllers", "services") depo kökünde YOKTU ve tarama sessizce `continue` ediyordu → apps/backend
# HİÇ taranmıyordu (ölçüldü: sync_worker.py'ye `subprocess.check_call([sys.executable, "-m", "pip", ...])` eklenince kapı YEŞİL).
# Artık kök YOKSA kapı DÜŞER ve her kökte en az bir dosya taranmış olmalı.
_PIP_TARAMA_KOKLERI = (
    "apps/backend/servers",
    "apps/backend/utils",
    "apps/backend/database",
    "apps/backend/controllers",
    "apps/backend/services",
    "ai_hub",
    "ai_service",
    "ai",
)
_PIP_TARAMA_UST_DUZEY = "apps/backend"  # backend_service.py, headless_core.py, event_bus.py (özyinelemesiz)
# Asgari taranan dosya: HEAD 5bc99be1'de apps/backend 102 (.py), toplam 197 — sabit kendi kopyası (ürün listesinden okunmaz).
_PIP_TARAMA_ASGARI_BACKEND = 90
_PIP_TARAMA_ASGARI_TOPLAM = 170

_SUREC_ISLEVLERI = {
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "os.system",
    "os.popen",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execl",
    "os.execlp",
    "os.spawnv",
    "os.spawnl",
    "os.spawnlp",
    "os.spawnvp",
    "os.startfile",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "runpy.run_module",
}
# "pip install X" / "-m pip" biçimli KOMUT dizgesi (f-string parçası dahil). İnsan iletisi ("Kur: pip install grad-cam") da buna uyar —
# o yüzden tek başına şüphe DEĞİL; yalnız süreç çağrısının içinde ya da `sys.executable` ile aynı deyimde şüphedir.
_PIP_KOMUTU = re.compile(r"(?:^|[\s\"'/\\])pip3?(?:\.exe)?\s+(?:install|uninstall|download)\b|-m\s+pip\b")
_PIP_ARGV = {"pip", "pip3", "pip.exe"}


def _nokta_adi(dugum, takma: dict) -> str:
    if isinstance(dugum, ast.Name):
        return takma.get(dugum.id, dugum.id)
    if isinstance(dugum, ast.Attribute):
        sol = _nokta_adi(dugum.value, takma)
        return f"{sol}.{dugum.attr}" if sol else ""
    return ""


def _dizgeler(dugum):
    for alt in ast.walk(dugum):
        if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
            yield alt.value


def _pip_izleri(kaynak: str) -> list:
    """AST ile çalışma-anı pip izleri (satır, tür). Yorum ve docstring AST'de çağrı DEĞİLDİR → masum iletiler sahte kırmızı vermez;
    çok satırlı (black biçimli) çağrı ve değişkene atanmış komut da görülür (eski satır sezgisi ±1 satır penceresine bakıyordu)."""
    agac = ast.parse(kaynak)
    takma: dict = {}
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            for a in d.names:
                takma[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(d, ast.ImportFrom) and d.module:
            for a in d.names:
                takma[a.asname or a.name] = f"{d.module}.{a.name}"
    izler = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Call):
            ad = _nokta_adi(d.func, takma)
            if ad in _SUREC_ISLEVLERI:
                argv = {s for s in _dizgeler(d) if s in _PIP_ARGV}
                if argv or any(_PIP_KOMUTU.search(s) for s in _dizgeler(d)):
                    izler.append((d.lineno, f"süreç çağrısında pip ({ad})"))
            if ad.rsplit(".", 1)[-1] == "check_requirements":
                izler.append((d.lineno, "ultralytics check_requirements (bağımlılık KURUCUSU)"))
        elif isinstance(d, (ast.List, ast.Tuple)):
            if any(isinstance(e, ast.Constant) and e.value in _PIP_ARGV for e in d.elts):
                izler.append((d.lineno, "argv listesinde 'pip'"))
        elif isinstance(d, (ast.Import, ast.ImportFrom)):
            mod = d.module if isinstance(d, ast.ImportFrom) else None
            adlar = [mod] if mod else [a.name for a in d.names]
            if any(a and (a == "pip" or a.startswith("pip.")) for a in adlar):
                izler.append((d.lineno, "pip modülü içe aktarılıyor"))
        if isinstance(d, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Return)):
            # Değişkene atanmış komut: `komut = f'"{sys.executable}" -m pip install …'` → başka satırda `check_output(komut)`.
            # Yalnız BASİT deyim: bileşik deyimde (try / if gövdesi) iki ayrı satırdaki masum parçalar birleşip sahte kırmızı vermesin.
            if any(
                _nokta_adi(a, takma) == "sys.executable" for a in ast.walk(d) if isinstance(a, ast.Attribute)
            ) and any(_PIP_KOMUTU.search(s) or s in _PIP_ARGV for s in _dizgeler(d)):
                izler.append((d.lineno, "sys.executable ile pip komutu"))
    return sorted(set(izler))


def _pip_tarama_dosyalari():
    eksik, dosyalar, kok_sayisi = [], [], {}
    for dizin in _PIP_TARAMA_KOKLERI:
        kok = _KOK / dizin
        if not kok.is_dir():
            eksik.append(dizin)
            continue
        bulunan = [
            y
            for y in kok.rglob("*.py")
            if not any(x in str(y) for x in ("PEMF_BUILD", "node_modules", "site-packages", "__pycache__"))
        ]
        kok_sayisi[dizin] = len(bulunan)
        dosyalar += bulunan
    ust = sorted((_KOK / _PIP_TARAMA_UST_DUZEY).glob("*.py"))
    kok_sayisi[_PIP_TARAMA_UST_DUZEY + "/*.py"] = len(ust)
    return eksik, dosyalar + ust, kok_sayisi


def test_urun_kaynaginda_calisma_ani_pip_cagrisi_YOK():
    """Sınıfsal kapı: ürün kodu hiçbir yerde çalışma anında pip çağırmamalı."""
    # Yalnız ÜRÜN kaynağı taranır. Kök `rglob` node_modules'taki aşırı uzun iOS yollarında
    # FileNotFoundError ile düşüyordu (ölçüldü) — kapı, kendi tarama hatasıyla kırmızı olmamalı.
    # ⚠️ Aranan şey pip'i ÇALIŞTIRMAK; "pip install X" yazan bir ImportError mesajı meşrudur (geliştiriciyi yönlendirir, hiçbir şey
    # kurmaz). İlk sürüm bu ayrımı yapmıyor ve 10 masum hata mesajını bulguymuş gibi gösteriyordu — kapı, doğru kodu suçlarsa kapatılır.
    eksik, dosyalar, kok_sayisi = _pip_tarama_dosyalari()
    assert not eksik, (
        f"pip taraması kökü YOK: {eksik} — kök taşındıysa listeyi güncelle (sessiz atlama kör kapıydı: İG-5.51)"
    )
    bos = [k for k, n in kok_sayisi.items() if n == 0]
    assert not bos, f"pip taraması kökü BOŞ: {bos} ({kok_sayisi})"
    backend = sum(1 for y in dosyalar if (_KOK / "apps" / "backend") in y.parents)
    assert backend >= _PIP_TARAMA_ASGARI_BACKEND, (
        f"apps/backend'den yalnız {backend} dosya tarandı ({kok_sayisi}) — kapı backend'i ölçmüyor"
    )
    assert len(dosyalar) >= _PIP_TARAMA_ASGARI_TOPLAM, f"tarama beklenenden dar ({len(dosyalar)} dosya: {kok_sayisi})"
    suphe, cozulemeyen = [], []
    for yol in dosyalar:
        try:
            izler = _pip_izleri(yol.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as e:  # okunamayan dosya ATLANMAZ — kapı onu ölçemediğini söyler
            cozulemeyen.append(f"{yol.relative_to(_KOK)}: {type(e).__name__}")
            continue
        suphe += [f"{yol.relative_to(_KOK)}:{satir} ({tur})" for satir, tur in izler]
    assert not cozulemeyen, f"pip taraması bu dosyaları AYRIŞTIRAMADI (ölçülmedi): {cozulemeyen}"
    assert not suphe, (
        "Ürün kaynağında çalışma-anı pip izi bulundu (paketlenmiş cihaz kendi bağımlılıklarını "
        f"değiştirmemeli): {suphe[:10]}"
    )


@pytest.mark.parametrize(
    ("kaynak", "beklenen"),
    [
        ('import subprocess, sys\nsubprocess.check_call([sys.executable, "-m", "pip", "install", "x"])\n', True),
        (
            'import subprocess\nimport sys\n\nsubprocess.run(\n    [\n        sys.executable,\n        "-m",\n        "pip",\n        "install",\n        "x",\n    ]\n)\n',
            True,
        ),
        (
            'import subprocess, sys\nkomut = f\'"{sys.executable}" -m pip install x\'\n\n\n\nsubprocess.check_output(komut, shell=True)\n',
            True,
        ),
        ("from subprocess import check_output as co\nco('pip install x', shell=True)\n", True),
        ("import os\nos.system('pip3 install x')\n", True),
        ("from ultralytics.utils.checks import check_requirements\ncheck_requirements(['onnxruntime'])\n", True),
        ('raise ImportError("ReportLab gerekli. \'pip install reportlab\' komutunu çalıştırın.")\n', False),
        (
            '"""Kurulum:\n    pip install zeroconf\n"""\nimport logging\nlogging.getLogger().error("Kurulum: pip install zeroconf")\n',
            False,
        ),
        (
            '# subprocess.run([sys.executable, "-m", "pip", "install", "x"])\nX = {"pip": "pip install neurokit2"}\n',
            False,
        ),
    ],
    ids=[
        "argv",
        "cok_satirli_black",
        "degiskene_atanmis",
        "takma_ad",
        "os_system",
        "check_requirements",
        "importerror_iletisi",
        "docstring_ve_log",
        "yorum_ve_sozluk",
    ],
)
def test_pip_izi_tarayicisi_KARSIT_KANIT(kaynak, beklenen):
    """Tarayıcının kendisi: gerçek pip çağrısı biçimlerini görür, masum iletileri suçlamaz (iki yönlü)."""
    assert bool(_pip_izleri(kaynak)) is beklenen, (
        f"tarayıcı {'görmedi' if beklenen else 'sahte kırmızı verdi'}: {_pip_izleri(kaynak)}"
    )


def test_pip_alt_sureci_gercekten_dogmuyor():
    """Uçtan uca: yasak kurulu bir süreçte ultralytics checks pip alt-süreci AÇMAMALI.

    `subprocess.check_output`'u araya girip yakalarız; gerçek bir pip komutu denenirse test düşer.
    """
    ultra_checks = pytest.importorskip("ultralytics.utils.checks", reason="ultralytics kurulu değil")
    from utils.runtime_guards import pip_kurulumunu_yasakla

    pip_kurulumunu_yasakla()

    yakalanan = []
    gercek = subprocess.check_output

    def _casus(cmd, *a, **k):
        yakalanan.append(cmd)
        return b""

    subprocess.check_output = _casus
    try:
        # onnxruntime KURULU; yasak açıkken bu çağrı hiçbir kurulum denemesi yapmamalı.
        ultra_checks.check_requirements(["onnxruntime"])
    except Exception:
        pass  # sürüm/parse farkları bu testin konusu değil — ölçtüğümüz şey alt-süreç
    finally:
        subprocess.check_output = gercek

    pip_izi = [c for c in yakalanan if "pip" in str(c)]
    assert not pip_izi, f"yasağa rağmen pip alt-süreci denendi: {pip_izi}"
