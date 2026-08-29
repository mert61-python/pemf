# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KOD KORUMASI GERÇEKTEN ETKİN Mİ — denetim 2026-08-28 #07.

ÖLÇÜLEN ARIZA. `collect_submodules('ai_hub')` ai_hub'ın tüm modüllerini `a.pure`'a, oradan da
PYZ arşivine BYTECODE olarak gömüyordu. `compile_pyd.py` ise yalnız DİSKTEKİ `.py`'leri `.pyd`'ye
çevirip siliyordu. PyInstaller 6'da `PyiFrozenFinder` aynı dizin için ÖNCE PYZ'ye bakar → PYZ
diski her zaman yener. Sevk edilen 1.9.31 EXE'sinde ölçülen:

    * PYZ arşivinde 87 ai_hub girişi (65 modül + 18 paket + 4 namespace paketi),
    * `ai_hub.cat_disease.inference_cat_disease` PYZ'den çözülüp docstring'i ve fonksiyon
      adları (`CatDiseasePredictor`, `xai_top_features`, ...) okundu,
    * çalışan süreçte yüklü ai_hub `.pyd` sayısı **1/65** — ve o tek modül tam olarak
      `cat_segmentation`, yani PYZ'de ikizi OLMAYAN tek modül (doğal deney).

Dört koruma kapısı da YEŞİL yanıyordu, çünkü dördü de yalnız "DİSKTE düz .py kaldı mı" diye
soruyordu — PYZ'ye bakan yoktu.

İKİNCİ, DAHA SİNSİ KUSUR (aynı turda bulundu): spec'teki torch kaynak-eleme filtresi yol-çıpasız
olduğu için `ai_hub/xai_tabular/ig_torch.py`yi de yiyordu (adında "torch" geçiyor). O modül sevk
ağacına HİÇ girmiyor, yalnız PYZ'de yaşıyordu ve `inference_human_kidney_rna.py:219` onu canlı
XAI yolunda lazy import ediyor. Yani PYZ temizliği tek başına yapılsaydı, RNA gen-katkısı
açıklaması SAHADA SESSİZCE ÖLECEKTİ — düzeltmenin kendisi yeni bir sessiz ölüm üretecekti.

⚠️ ÇIPA NOTU: bu dosya AST kullanır ve fonksiyonun VAR OLMASINI değil ÇAĞRILMASINI kilitler.
Bu projede zayıf çıpa iki kez ısırdı (düz metin araması spec'in başka bölümünü buluyordu).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_SPECLER = {
    "onedir": _KOK / "build_tools" / "PEMF_Backend_onedir.spec",
    "onefile": _KOK / "build_tools" / "PEMF_Backend_onefile.spec",
}


def _agac(spec: Path) -> ast.Module:
    return ast.parse(spec.read_text(encoding="utf-8"))


# ── 1) ai_hub PYZ'den ÇIKARILIYOR ────────────────────────────────────────────


def _pure_temizligi(agac: ast.Module) -> ast.Assign | None:
    """`a.pure[:] = [...]` biçimindeki dilim atamasını bul."""
    for d in ast.walk(agac):
        if not isinstance(d, ast.Assign) or len(d.targets) != 1:
            continue
        h = d.targets[0]
        if (
            isinstance(h, ast.Subscript)
            and isinstance(h.value, ast.Attribute)
            and h.value.attr == "pure"
            and isinstance(h.slice, ast.Slice)
        ):
            return d
    return None


@pytest.mark.parametrize("ad", sorted(_SPECLER))
def test_KRITIK_ai_hub_PYZden_cikariliyor(ad):
    """Korumanın çekirdeği: ai_hub `a.pure`'dan çıkarılmalı, yoksa .pyd'ler hiç yüklenmez."""
    spec = _SPECLER[ad]
    d = _pure_temizligi(_agac(spec))
    assert d is not None, (
        f"{spec.name}: `a.pure[:] = [...]` temizliği YOK → ai_hub PYZ'ye gömülür ve import "
        f"diskteki .pyd'yi ATLAR (ölçüldü: 64/65 .pyd hiç yüklenmiyordu)"
    )
    assert "ai_hub" in ast.unparse(d.value), f"{spec.name}: temizlik ai_hub'ı hedeflemiyor"


@pytest.mark.parametrize("ad", sorted(_SPECLER))
def test_KRITIK_pure_temizligi_PYZden_ONCE(ad):
    """Sıra kilidi: temizlik `PYZ(a.pure)` çağrısından SONRA olursa hiçbir işe yaramaz —
    ve bu sessizdir, build yine yeşil kalır."""
    spec = _SPECLER[ad]
    agac = _agac(spec)
    temizlik = _pure_temizligi(agac)
    assert temizlik is not None, f"{spec.name}: temizlik yok"
    pyz = next(
        (d for d in ast.walk(agac) if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "PYZ"),
        None,
    )
    assert pyz is not None, f"{spec.name}: PYZ(...) çağrısı bulunamadı"
    assert temizlik.lineno < pyz.lineno, (
        f"{spec.name}: a.pure temizliği ({temizlik.lineno}) PYZ çağrısından ({pyz.lineno}) SONRA — "
        f"etkisiz, ai_hub yine arşive girer"
    )


@pytest.mark.parametrize("ad", sorted(_SPECLER))
def test_pure_temizligi_YERINDE_atama_kullaniyor(ad):
    """`a.pure = [...]` (yeniden bağlama) PYZ kod önbelleğini düşürür: önbellek `id(a.pure)`
    ile aranır (build_main.py:953 → api.py:109), liste kimliği değişince tüm PYZ kaynaktan
    yeniden derlenir ve build belirgin şekilde yavaşlar. Dilim ataması kimliği korur."""
    spec = _SPECLER[ad]
    metin = spec.read_text(encoding="utf-8")
    for satir in metin.splitlines():
        s = satir.strip()
        if s.startswith("a.pure") and "=" in s and not s.startswith("a.pure["):
            pytest.fail(f"{spec.name}: `a.pure` yeniden bağlanıyor ({s[:60]}) — dilim ataması kullanın")


# ── 2) torch filtresi yol-çıpalı VE gerçekten kullanılıyor ───────────────────


@pytest.mark.parametrize("ad", sorted(_SPECLER))
def test_KRITIK_torch_filtresi_YOL_CIPALI(ad):
    """`'torch' in yol` deseni `ai_hub/xai_tabular/ig_torch.py`yi de yiyordu."""
    spec = _SPECLER[ad]
    agac = _agac(spec)
    fn = next(
        (d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef) and d.name == "_torch_kaynagi_mi"),
        None,
    )
    assert fn is not None, f"{spec.name}: `_torch_kaynagi_mi` yok — yol-çıpasız filtreye dönülmüş olabilir"

    # Fonksiyonu izole çalıştır: davranışı KİLİTLE (metin araması değil).
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<spec>", "exec"), ns)
    f = ns["_torch_kaynagi_mi"]
    assert f("torch/nn/modules/linear.py") is True, "torch paket kökü elenmiyor"
    assert f("torchvision/models/resnet.py") is True, "torchvision paket kökü elenmiyor"
    assert f("ai_hub/xai_tabular/ig_torch.py") is False, (
        "ig_torch.py HÂLÂ eleniyor → modül sevk ağacına girmez, RNA XAI'si sessizce ölür"
    )
    assert f("ai_hub\\xai_tabular\\ig_torch.py") is False, "ters-bölülü yol için de geçerli olmalı"
    assert f("torch/version.txt") is False, ".py olmayan dosya elenmemeli"


@pytest.mark.parametrize("ad", sorted(_SPECLER))
def test_KRITIK_torch_filtresi_GERCEKTEN_CAGRILIYOR(ad):
    """ZAYIF ÇIPA KORUMASI: fonksiyon doğru olabilir ama ÇAĞRILMIYORSA hiçbir şey değişmez.

    Kapıyı yeşil bırakan mutasyon şuydu: `_torch_kaynagi_mi`'yi olduğu gibi bırak, ama
    `a.datas` atamasını eski yol-çıpasız haline döndür. Bu test ikisini birden kilitler.
    """
    spec = _SPECLER[ad]
    agac = _agac(spec)
    kullaniliyor = False
    for d in ast.walk(agac):
        if not isinstance(d, ast.Assign) or len(d.targets) != 1:
            continue
        h = d.targets[0]
        if isinstance(h, ast.Attribute) and h.attr == "datas":
            if "_torch_kaynagi_mi" in ast.unparse(d.value):
                kullaniliyor = True
            else:
                # a.datas'a başka bir filtre atanıyorsa ve içinde ham 'torch' deseni varsa,
                # eski kırık filtre geri gelmiş demektir.
                govde = ast.unparse(d.value)
                assert "'torch' in" not in govde and '"torch" in' not in govde, (
                    f"{spec.name}: yol-çıpasız torch filtresi geri gelmiş → ig_torch.py yine yenir"
                )
    assert kullaniliyor, f"{spec.name}: `_torch_kaynagi_mi` tanımlı ama `a.datas` filtresinde KULLANILMIYOR"


def test_iki_spec_ayni_torch_filtresini_KULLANIYOR():
    """İki spec kopyası birbirinden sapmamalı (çürütme notu: kopya varsa sapma kaçınılmazdır)."""
    govdeler = {}
    for ad, spec in _SPECLER.items():
        fn = next(
            (d for d in ast.walk(_agac(spec)) if isinstance(d, ast.FunctionDef) and d.name == "_torch_kaynagi_mi"),
            None,
        )
        assert fn is not None, f"{spec.name}: `_torch_kaynagi_mi` yok"
        # Docstring hariç gövde karşılaştırılır (yorum/açıklama farkı serbest).
        govde = [g for g in fn.body if not (isinstance(g, ast.Expr) and isinstance(g.value, ast.Constant))]
        govdeler[ad] = ast.unparse(ast.Module(body=govde, type_ignores=[]))
    assert govdeler["onedir"] == govdeler["onefile"], (
        f"iki spec'teki torch filtresi SAPMIŞ:\n--- onedir ---\n{govdeler['onedir']}\n"
        f"--- onefile ---\n{govdeler['onefile']}"
    )


# ── 3) Kapı betikleri var ve build'e BAĞLI ───────────────────────────────────


@pytest.mark.parametrize("betik", ["scripts/pyz_koruma_kapisi.py", "scripts/sevk_agaci_ai_hub_kapisi.py"])
def test_kapi_betikleri_var(betik):
    assert (_KOK / betik).is_file(), f"{betik} yok"


@pytest.mark.parametrize("betik", ["pyz_koruma_kapisi.py", "sevk_agaci_ai_hub_kapisi.py"])
def test_KRITIK_kapilar_build_betiginden_CAGRILIYOR_ve_DIE_ediyor(betik):
    """Kapı var olmak yetmez; build onu çağırmalı VE kırmızıda durmalı.

    Yalnız çağırıp `$LASTEXITCODE`'a bakmamak, kapıyı süs hâline getirir."""
    ps = (_KOK / "scripts" / "build_backend_exe.ps1").read_text(encoding="utf-8")
    assert betik in ps, f"{betik} build betiğinden çağrılmıyor"
    i = ps.find(betik)
    pencere = ps[i : i + 700]
    assert "LASTEXITCODE" in pencere, f"{betik} çağrılıyor ama çıkış kodu kontrol edilmiyor"
    assert "Die" in pencere, f"{betik} kırmızıyken build DURMUYOR (yalnız uyarı) — kapı süs olur"


def test_calisma_ani_kontrolu_SkipProtect_ile_muaf():
    """`-SkipProtect` ve MSVC-yok build'leri sert hataya çevrilmemeli (çürütme itirazı).

    `.pyenc` de meşru sayılmalı: build_installer.ps1:574 ve make_base_zip.py sahip ölçütü
    'düz .py YOK mu' — .pyd zorunluluğu ayrı bir sahip kararıdır."""
    ps = (_KOK / "scripts" / "build_backend_exe.ps1").read_text(encoding="utf-8")
    i = ps.find("yukleme -notin")
    assert i != -1, "çalışma-anı koruma kontrolü yok"
    pencere = ps[max(0, i - 900) : i + 200]
    assert "SkipProtect" in pencere, "çalışma-anı kontrolü -SkipProtect ile muaf tutulmuyor"
    assert "'pyenc'" in ps[i : i + 200] or '"pyenc"' in ps[i : i + 200], (
        "`.pyenc` korumasız sayılıyor — sahip ölçütünü sessizce tersine çevirir"
    )


# ── 4) Teşhis ucu: yükleme biçimi UZANTIYA değil YÜKLEYİCİYE bakar ──────────


def test_KRITIK_yukleme_bicimi_YUKLEYICI_SINIFINA_bakar():
    """Ölçüldü: PyInstaller 6.20 PYZ modülüne de `.py` uzantılı `__file__` verir
    (pyimod02_importers.py:405-418) ve `EncryptedLoader` `__file__` hiç atamaz. Uzantıya
    bakan bir sınıflandırma 'PYZ bytecode' ile 'diskte düz kaynak'ı KARIŞTIRIR — oysa alanın
    var oluş sebebi tam olarak bu ayrımdır."""
    import inspect

    from servers import ai_router

    kaynak = inspect.getsource(ai_router._modul_yukleme_bicimi)
    assert "__loader__" in kaynak, "yükleme biçimi yükleyici sınıfına bakmıyor"
    for sinif in ("ExtensionFileLoader", "PyiFrozenLoader", "EncryptedLoader", "SourceFileLoader"):
        assert sinif in kaynak, f"{sinif} sınıflandırması eksik"
    assert "endswith" not in kaynak, "uzantı tabanlı sınıflandırma kalmış (ölçümle yanlışlandı)"


def test_yukleme_bicimi_gercek_modulleri_siniflandiriyor():
    """Davranışsal: bilinen modüller doğru sınıflanmalı, bilinmeyen 'yok' dönmeli."""
    from servers.ai_router import _modul_yukleme_bicimi

    assert _modul_yukleme_bicimi("hicboyle_bir_modul_yok_12345") == "yok"
    # Bu testin kendisi düz kaynaktan yüklenir (frozen olmayan ortam).
    assert _modul_yukleme_bicimi("servers.ai_router") in ("py", "pyc", "pyd", "pyenc", "pyz")
