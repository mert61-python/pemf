# -*- coding: utf-8 -*-
"""A9 KAPISI — eşzamanlı ağır import yarışı geri gelemesin.

ÖLÇÜLEN ARIZA: aynı kod/girdi, iki E2E koşumu → birinde 8 AI ucu 200, diğerinde HEPSİ 500.
`torch/__init__.py:465  for name in dir(_C)` → `NameError: name '_C' is not defined`,
tek koşumda 38 kez. Kök: `lifespan` `scratch-warmup` thread'ini başlatıp HEMEN `yield`
ediyordu; sunucu, ısıtma sürerken istek kabul ediyordu.

⚠️ BU KAPININ ASIL İDDİASI SIRALAMADIR, VARLIK DEĞİL. `_torch_isit()` çağrısının var
olması hiçbir şey kanıtlamaz — `_scratch_isit_baslat()`ın ALTINA ya da `yield`in SONRASINA
alınırsa arıza aynen geri gelir ve "çağrı var" diyen bir test bunu GÖREMEZ. Bu yüzden sıra
AST'den okunuyor.

⚠️ Davranış testi (test_eszamanli_import_SERILESIR) çıpayı gerçek kilide pinler: yapısal
iddialar doğruyken bile kilit fiilen serileştirmiyorsa kırmızı olur.
"""

from __future__ import annotations

import ast
import importlib
import sys
import threading
import time
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul  # kök çıpası: SABİT DERİNLİK YOK

KOK = kaynak_kokunu_bul(__file__)
API_SERVER = KOK / "apps" / "backend" / "servers" / "api_server.py"
AI_ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"
AGIR = KOK / "apps" / "backend" / "utils" / "agir_import.py"
SCRATCH = KOK / "ai_hub" / "inference_paper_dilek_hoca" / "inference_paper_dilek_hoca.py"
SERVIS = KOK / "apps" / "backend" / "backend_service.py"


def _agac(p: Path) -> ast.AST:
    assert p.is_file(), f"kaynak yok: {p}"
    return ast.parse(p.read_text(encoding="utf-8"))


def _fonksiyon(agac: ast.AST, ad: str):
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad:
            return d
    raise AssertionError(f"fonksiyon bulunamadı: {ad}")


def _cagri_satirlari(dugum, ad: str) -> list[int]:
    """`ad(...)` çağrılarının satır numaraları (nitelikli çağrılar dahil)."""
    out = []
    for d in ast.walk(dugum):
        if not isinstance(d, ast.Call):
            continue
        f = d.func
        adi = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        if adi == ad:
            out.append(d.lineno)
    return out


# ──────────────────────────────────────────────────────────────────────────
# 1) SIRA — kapının asıl iddiası
# ──────────────────────────────────────────────────────────────────────────


def test_torch_isitmasi_SCRATCH_ISITMASINDAN_ONCE():
    """`_torch_isit()` `_scratch_isit_baslat()`tan ÖNCE çağrılmalı.

    Sonra çağrılırsa ısıtma thread'i torch'u yarı-kurulu bırakırken kurulum yarışır.
    """
    lifespan = _fonksiyon(_agac(API_SERVER), "lifespan")
    isit = _cagri_satirlari(lifespan, "_torch_isit")
    scratch = _cagri_satirlari(lifespan, "_scratch_isit_baslat")
    assert isit, "lifespan içinde _torch_isit() çağrısı YOK — A9 geri geldi"
    assert scratch, "lifespan içinde _scratch_isit_baslat() çağrısı YOK (saha düzeltmesi silinmiş)"
    assert min(isit) < min(scratch), (
        f"SIRA BOZULDU: _torch_isit() satır {min(isit)}, _scratch_isit_baslat() satır "
        f"{min(scratch)}. torch ısıtma thread'inden ÖNCE tamamlanmalı (A9)."
    )


def test_torch_isitmasi_YIELD_ONCESINDE():
    """`_torch_isit()` `yield`DEN önce olmalı — `yield` istek kabulünü açar."""
    lifespan = _fonksiyon(_agac(API_SERVER), "lifespan")
    isit = min(_cagri_satirlari(lifespan, "_torch_isit"))
    yieldler = [d.lineno for d in ast.walk(lifespan) if isinstance(d, ast.Yield)]
    assert yieldler, "lifespan'de yield yok — dosya beklenenden farklı"
    assert isit < min(yieldler), (
        f"_torch_isit() satır {isit}, yield satır {min(yieldler)}. yield'den SONRA ısıtmak "
        "sunucu istek alırken ısıtmak demektir — ölçülen arızanın ta kendisi."
    )


def test_scratch_isitmasi_HALA_VAR():
    """2026-08-27 saha düzeltmesi silinmemeli — A9 'ısıtmayı kaldır' ile çözülmedi."""
    kaynak = API_SERVER.read_text(encoding="utf-8")
    assert "scratch-warmup" in kaynak, (
        "scratch ısıtma thread'i kaldırılmış. A9 düzeltmesi ısıtmayı KALDIRMAK değil, "
        "SERİLEŞTİRMEKTİ (ilk analiz 32,8 sn → saha bildirimi 2026-08-27)."
    )


# ──────────────────────────────────────────────────────────────────────────
# 1b) ASIL KÖK NEDEN — `ai-warmup` uvicorn'dan ÖNCE başlar (izciyle ölçüldü)
# ──────────────────────────────────────────────────────────────────────────


def test_torch_isitmasi_AI_WARMUP_THREADINDEN_ONCE():
    """🔴 A9'un GERÇEK kökü: `_start_ai_warmup_safe()` `ai-warmup` daemon'ını başlatır ve
    o thread `ai_hub.inference_cat_sound` → `import torch` yapar. İzci ölçümü:
        1.500 sn  ai-warmup   ai_hub.inference_cat_sound
        1.547 sn  MainThread  torch
    Isıtma bu çağrının ALTINA düşerse arıza aynen geri gelir.

    ⚠️ İlk düzeltme YALNIZ `lifespan`e konmuştu ve YETMEDİ — `ai-warmup` uvicorn'dan
    önce başlıyor. Bu test o hatayı tekrar edilemez kılar.
    """
    fn = _fonksiyon(_agac(SERVIS), "main")
    isit = _cagri_satirlari(fn, "_torch_isit") + _cagri_satirlari(fn, "torch_isit")
    warm = _cagri_satirlari(fn, "_start_ai_warmup_safe")
    assert isit, "backend_service.main() içinde torch ısıtma çağrısı YOK — A9 geri geldi"
    assert warm, "_start_ai_warmup_safe() çağrısı YOK (ısıtma silinmiş)"
    assert min(isit) < min(warm), (
        f"SIRA BOZULDU: ısıtma satır {min(isit)}, _start_ai_warmup_safe satır {min(warm)}. "
        "torch, ai-warmup thread'i başlamadan ÖNCE kurulmalı (A9 gerçek kök nedeni)."
    )


def test_ai_warmup_threadi_KILITTEN_GECIYOR():
    """`ai-warmup` kendi ağır import'unu süreç-geneli kilitten geçirmeli."""
    kaynak = SERVIS.read_text(encoding="utf-8")
    assert "name=\"ai-warmup\"" in kaynak, "ai-warmup thread'i kaldırılmış (ısıtma saha kararı)"
    assert "agir_import(\"ai_hub.inference_cat_sound.inference_cat_sound\")" in kaynak, (
        "ai-warmup ağır import'u _KILIT'ten GEÇMİYOR — A9 yarışının bir tarafı açık."
    )


# ──────────────────────────────────────────────────────────────────────────
# 2) TEK BOĞUM — kilit paylaşılıyor mu
# ──────────────────────────────────────────────────────────────────────────


def test_model_kilidi_AYRI_DEGIL_PAYLASILAN():
    """`_model_lock` kendi `threading.Lock()`u OLMAMALI; paylaşılan _KILIT olmalı.

    Ayrı kilit, `hazirlik?derin=1` ile model yükleyicinin paralel import etmesine izin
    veriyordu — yarışın ikinci tarafı buydu.
    """
    kaynak = AI_ROUTER.read_text(encoding="utf-8")
    assert "_model_lock = threading.Lock()" not in kaynak, (
        "ai_router kendi ayrı _model_lock'unu geri koymuş — tek boğum bozuldu (A9)."
    )
    assert "from utils.agir_import import _KILIT as _model_lock" in kaynak, (
        "_model_lock paylaşılan utils.agir_import._KILIT'ten gelmiyor (A9)."
    )


def test_derin_hazirlik_probu_KILIT_ALTINDA():
    """`_modul_hazir_mi` derin dalı çıplak `importlib.import_module` KULLANMAMALI."""
    fn = _fonksiyon(_agac(AI_ROUTER), "_modul_hazir_mi")
    ciplak = []
    for d in ast.walk(fn):
        if (
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "import_module"
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id == "importlib"
        ):
            ciplak.append(d.lineno)
    assert not ciplak, (
        f"_modul_hazir_mi satır {ciplak}: çıplak importlib.import_module. Derin prob HER "
        "ai_hub modülünü import eder ve istek yoluyla yarışır — _agir_import() kullanılmalı."
    )
    assert _cagri_satirlari(fn, "_agir_import"), "_modul_hazir_mi _agir_import() çağırmıyor (A9)."


def test_scratch_cell_importu_KILIT_ALTINDA():
    """Ölçülen yığın izinin tepesi: `_cell_import` kilitsizdi."""
    fn = _fonksiyon(_agac(SCRATCH), "_cell_import")
    with_altinda = set()
    for d in ast.walk(fn):
        if isinstance(d, ast.With):
            for alt in ast.walk(d):
                if isinstance(alt, (ast.Import, ast.ImportFrom)):
                    with_altinda.add(alt.lineno)
    tum = {d.lineno for d in ast.walk(fn) if isinstance(d, (ast.Import, ast.ImportFrom))}
    assert tum, "_cell_import içinde import yok — dosya beklenenden farklı"
    assert tum <= with_altinda, (
        f"_cell_import: kilit dışında import satırları {sorted(tum - with_altinda)}. "
        "Hepsi _agir_kilit() bloğu içinde olmalı (A9)."
    )


def test_ai_hub_BACKENDE_ZORUNLU_BAGIMLI_DEGIL():
    """`ai_hub` backend olmadan da import edilebilmeli (GPU mikroservisi).

    Kilit ZORUNLU değil, VARSA kullanılır — bu yüzden import try/except içinde olmalı.
    """
    fn = _fonksiyon(_agac(SCRATCH), "_agir_kilit")
    denemeler = [d for d in ast.walk(fn) if isinstance(d, ast.Try)]
    assert denemeler, "_agir_kilit try/except kullanmıyor — backend'siz kurulumda ai_hub import'u ÇÖKER."


# ──────────────────────────────────────────────────────────────────────────
# 3) DAVRANIŞ — kilit fiilen serileştiriyor mu
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def agir():
    yol = str(KOK / "apps" / "backend")
    eklendi = yol not in sys.path
    if eklendi:
        sys.path.insert(0, yol)
    try:
        modul = importlib.import_module("utils.agir_import")
        yield importlib.reload(modul)
    finally:
        if eklendi:
            sys.path.remove(yol)


def test_eszamanli_import_SERILESIR(agir, monkeypatch):
    """İki thread aynı anda agir_import çağırırsa GÖVDELER ÖRTÜŞMEMELİ.

    ⚠️ VAKUM KARŞITI: kilit kaldırılırsa bu test kırmızı olmalı. Çıpa, gerçek
    `_KILIT`e pinli — sahte bir kilit nesnesi testi yeşile çeviremez.
    """
    ici = []
    engel = threading.Barrier(2, timeout=10)

    def sahte_import(yol):
        ici.append(("gir", yol, time.monotonic()))
        time.sleep(0.15)
        ici.append(("cik", yol, time.monotonic()))
        return object()

    # ⚠️ monkeypatch ŞART: agir.importlib GLOBAL importlib'dir; düz atama sonraki
    # testlere sızar (bu kapıyı yazarken ölçüldü: fixture'ın kendi import'u bozuldu).
    monkeypatch.setattr(agir.importlib, "import_module", sahte_import)

    def kos(ad):
        engel.wait()
        agir.agir_import(ad)

    t = [threading.Thread(target=kos, args=(f"sahte_{i}",)) for i in range(2)]
    for x in t:
        x.start()
    for x in t:
        x.join(timeout=15)
        assert not x.is_alive(), "thread bitmedi — kilit KİLİTLENMEYE dönüşmüş olabilir"

    # Serileşmişse olay dizisi gir,cik,gir,cik olur; örtüşmüşse gir,gir,...
    sira = [e[0] for e in ici]
    assert sira == ["gir", "cik", "gir", "cik"], (
        f"import gövdeleri ÖRTÜŞTÜ: {sira}. Kilit serileştirmiyor — A9 yarışı açık."
    )


def test_kilit_REENTRANT(agir):
    """Ağır modüller birbirini import eder; düz Lock aynı thread'de KİLİTLENİRDİ."""
    with agir._KILIT:
        alindi = agir._KILIT.acquire(timeout=2)
        assert alindi, "kilit reentrant DEĞİL (RLock olmalı) — iç içe import kilitlenir."
        agir._KILIT.release()


def test_kilit_alinamazsa_DONMAZ(agir, monkeypatch):
    """Kilit zaman aşımına uğrarsa import KİLİTSİZ yapılır — klinik cihaz DONMAZ."""
    monkeypatch.setattr(agir, "_KILIT_BEKLEME_SN", 0.2)
    cagrildi = []
    monkeypatch.setattr(agir.importlib, "import_module", lambda y: cagrildi.append(y) or object())

    tutuldu = threading.Event()
    birak = threading.Event()

    def tutucu():
        with agir._KILIT:
            tutuldu.set()
            birak.wait(timeout=10)

    th = threading.Thread(target=tutucu, daemon=True)
    th.start()
    assert tutuldu.wait(timeout=5)
    try:
        t0 = time.monotonic()
        agir.agir_import("sahte_zaman_asimi")
        gecen = time.monotonic() - t0
    finally:
        birak.set()
        th.join(timeout=5)

    assert cagrildi == ["sahte_zaman_asimi"], "zaman aşımında import HİÇ yapılmadı — uç ÖLÜR"
    assert gecen < 5, f"{gecen:.1f} sn bekledi — zaman aşımı uygulanmıyor"


def test_torch_isit_IDEMPOTENT(agir, monkeypatch):
    """Isıtma iki kez çağrılırsa torch İKİ KEZ import edilmez."""
    sayac = []
    monkeypatch.setattr(agir.importlib, "import_module", lambda y: sayac.append(y) or object())
    assert agir.torch_isit() is True
    assert agir.torch_isit() is True
    assert sayac == ["torch"], f"ısıtma idempotent değil: {sayac}"
