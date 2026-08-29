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

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
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


def test_yasak_gercekten_ultralytics_davranisini_degistirir():
    """SÖZDE değil GERÇEK etki: ultralytics kendi AUTOINSTALL sabitini False okumalı.

    Env'i okuyan bizim kodumuz değil, ultralytics'in `utils/__init__.py`'si — bayrak IMPORT
    ANINDA okunduğu için yasak, ultralytics'ten önce kurulmuş olmalı. Bu testin değeri:
    'env yazdım' demek yetmez, tüketen kütüphanenin davranışını ölçer.
    """
    ultra = pytest.importorskip("ultralytics.utils", reason="ultralytics kurulu değil")
    assert getattr(ultra, "AUTOINSTALL", True) is False, (
        "ultralytics.utils.AUTOINSTALL hâlâ True — yasak ultralytics IMPORTUNDAN SONRA kurulmuş "
        "olabilir (bayrak import anında okunur, sonradan set etmek ETKİSİZDİR)"
    )


def test_ai_hub_import_edilince_yasak_kendiliginden_kurulur():
    """ai_hub'ı doğrudan import eden yollar (test/CLI/scratch) da korunmalı."""
    os.environ.pop("YOLO_AUTOINSTALL", None)
    modul = importlib.import_module("ai_hub")
    importlib.reload(modul)
    assert os.environ.get("YOLO_AUTOINSTALL", "").lower() == "false", "ai_hub import edildiğinde pip yasağı kurulmadı"


def test_giris_noktalari_yasagi_ULTRALYTICSTEN_ONCE_cagiriyor():
    """Sıra kilidi: `pip_kurulumunu_yasakla` çağrısı, ultralytics'i çeken importlardan önce olmalı.

    Kaynak sırası kontrol edilir çünkü yanlış sıra SESSİZDİR — kapı 'kurulu' görünür, bayrak
    zaten okunmuş olduğu için hiçbir işe yaramaz.
    """
    # ⚠️ Çıpa GERÇEK import satırına pinlenir, düz kelimeye DEĞİL: 'onnxruntime' aynı dosyanın
    # docstring'inde de geçiyor ve düz `find()` orayı bulup yanlış alarm veriyordu (ölçüldü).
    for dosya, ultra_deseni in (
        (_KOK / "backend_service.py", r"^from headless_core import"),
        (_KOK / "ai_service" / "app.py", r"^import onnxruntime\b"),
    ):
        metin = dosya.read_text(encoding="utf-8")
        y = metin.find("pip_kurulumunu_yasakla")
        assert y != -1, f"{dosya.name}: pip yasağı çağrısı YOK"
        m = re.search(ultra_deseni, metin, re.MULTILINE)
        assert m, f"{dosya.name}: çıpa import satırı bulunamadı ({ultra_deseni}) — çıpa kaymış olabilir"
        assert y < m.start(), (
            f"{dosya.name}: pip yasağı, AI zincirini çeken '{m.group(0)}' importundan SONRA "
            f"({y} > {m.start()}) — ultralytics bayrağı import anında okur, bu sıra etkisizdir"
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


@pytest.mark.parametrize("paket", _METADATA_SART)
def test_paketler_bu_ortamda_gercekten_KURULU(paket):
    """Liste hayali olmasın: spec'in toplayacağı paketler build makinesinde kurulu olmalı."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        assert version(paket)
    except PackageNotFoundError:
        pytest.fail(
            f"'{paket}' bu ortamda kurulu değil — spec onu toplayamaz ve frozen EXE'de "
            f"ilgili yol sessizce bozulur (build makinesinde `pip install {paket}`)"
        )


def test_urun_kaynaginda_calisma_ani_pip_cagrisi_YOK():
    """Sınıfsal kapı: ürün kodu hiçbir yerde çalışma anında pip çağırmamalı."""
    # Yalnız ÜRÜN kaynağı taranır. Kök `rglob` node_modules'taki aşırı uzun iOS yollarında
    # FileNotFoundError ile düşüyordu (ölçüldü) — kapı, kendi tarama hatasıyla kırmızı olmamalı.
    suphe = []
    taranan = 0
    for dizin in ("servers", "ai_hub", "ai_service", "utils", "database", "controllers", "services", "ai"):
        kok = _KOK / dizin
        if not kok.is_dir():
            continue
        for yol in kok.rglob("*.py"):
            p = str(yol)
            if any(x in p for x in ("PEMF_BUILD", "node_modules", "site-packages", "__pycache__")):
                continue
            taranan += 1
            try:
                metin = yol.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # ⚠️ Aranan şey pip'i ÇALIŞTIRMAK; "pip install X" yazan bir ImportError mesajı
            # meşrudur (geliştiriciyi yönlendirir, hiçbir şey kurmaz). İlk sürüm bu ayrımı
            # yapmıyor ve 10 masum hata mesajını bulguymuş gibi gösteriyordu — kapı, doğru
            # kodu suçlarsa kapatılır ve asıl işini de yapamaz.
            satirlar = metin.splitlines()
            for i, satir_metni in enumerate(satirlar):
                s = satir_metni.strip()
                if s.startswith("#") or "pip" not in s:
                    continue
                # Çalıştırma bağlamı: aynı satırda ya da bir önceki satırda süreç başlatma.
                pencere = " ".join(satirlar[max(0, i - 1) : i + 2])
                if re.search(r"\b(subprocess|Popen|check_call|check_output|os\.system|sys\.executable)\b", pencere):
                    suphe.append(f"{yol.relative_to(_KOK)}:{i + 1}")
            # ultralytics'in kendi bağımlılık kurucusunu ürün kodundan çağırmak da yasak.
            for m in re.finditer(r"^\s*[^#\n]*\bcheck_requirements\s*\(", metin, re.MULTILINE):
                suphe.append(f"{yol.relative_to(_KOK)}:{metin[: m.start()].count(chr(10)) + 1}")
    assert taranan > 50, f"tarama boş kaldı ({taranan} dosya) — kapı hiçbir şey ölçmüyor"
    assert not suphe, (
        "Ürün kaynağında çalışma-anı pip izi bulundu (paketlenmiş cihaz kendi bağımlılıklarını "
        f"değiştirmemeli): {suphe[:10]}"
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
