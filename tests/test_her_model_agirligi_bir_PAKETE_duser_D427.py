# -*- coding: utf-8 -*-
"""D4.27 (B-9.9) — `release_assets/ai_models`'taki HER dosya launcher'ın kurduğu bir pakete düşer; böbrek-RNA açıklaması launcher
düzeninde ÇALIŞIR.

Launcher kurulumu = katmanlı paket (base-app + base-deps) + profil paketleri (home / vet / research [+ research-2 parçası]).
`_internal/ai_models` katmanlı pakette çekirdek (`inference_cat_organ`) DIŞINDA HARİÇTİR (make_base_zip EXCLUDE). Bir ağırlığın
sahaya varabileceği yollar yalnız şunlar:
  · profil / parça zip'i (`make_model_zip.PROFILLER` / `PARCALAR`),
  · çekirdek (`make_base_zip.CORE_MODELS` → deps katmanı, spec `_internal/ai_models` gömmesinden),
  · app katmanı (spec'in `ai_hub/<modül>` datas'ı) — ve bu yol DEPODA İZLENEN bir kaynaktan beslenmeli (yoksa yalnız bu
    derleme makinesinde çalışır; temiz makinede pakete girmez).

ARIZA (ölçüldü): `mlp_medium_kirc.pt` (RNA gen-katkısı açıklamasının PT ikizi) hiçbirinde değildi → sahadaki launcher kurulumunda
RNA `explain=1` "Açıklama üretilemedi" (1.9.50'de canlı). Ayrıca app katmanının 10 küçük modeli (böbrek-hastalık, böbrek-RNA ONNX +
scaler, em_petri scaler'ları) yalnız modül dizinindeki İZLENMEYEN yerel kopyalardan geliyordu. Var olan envanter kapısı
(`test_ai_hazirlik_envanteri`) `release_assets`'te bulunmayı "gömülü" sayıyordu — katmanlı pakette o kopya HARİÇ (kör).

Ölçüm: spec PyInstaller OLMADAN GERÇEK metniyle alt süreçte (D2.36 sürücüsü); davranış kolu GERÇEK `ai_router.analyze_kidney_rna`
ucunu launcher düzeni benzetiminde (`sys.frozen`, `_MEIPASS` = yalnız app katmanı içeriği, `PEMF_AI_MODELS_DIR` = yalnız araştırma
profilinin içeriği) çağırır. Gerçek ağırlıklar yalnız OKUNUR (tmp'ye kopya).
"""

from __future__ import annotations

import ast
import asyncio
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"
RA = KOK / "release_assets" / "ai_models"
RNA_PT = "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar (DLL/yol mantığı)"
)

_SURUCU = r'''
import json, os, sys, types
spec, cikti = sys.argv[1], sys.argv[2]
def _bos(*a, **k):
    return []
def _hepsi(*a, **k):
    return ([], [], [])
hooks = types.ModuleType("PyInstaller.utils.hooks")
hooks.collect_data_files = hooks.collect_dynamic_libs = hooks.copy_metadata = _bos
# D4.17: spec birinci-taraf paket toplaması BOŞ dönerse derlemeyi durdurur → sahte toplayıcı boş olmayan liste döner
# (bu sürücü datas'ı ölçer; gizli içe aktarmayı test_spec_BIRINCI_TARAF_paketleri_TOPLANIR_D417_D418 ölçer).
hooks.collect_submodules = lambda pkg, *a, **k: [pkg + '._sahte']
hooks.collect_all = _hepsi
pi, ut = types.ModuleType("PyInstaller"), types.ModuleType("PyInstaller.utils")
pi.utils, ut.hooks = ut, hooks
sys.modules.update({"PyInstaller": pi, "PyInstaller.utils": ut, "PyInstaller.utils.hooks": hooks})
yakalanan = {}
class Analysis:
    def __init__(self, scripts, **kw):
        yakalanan["datas"] = [[os.fspath(s), d] for s, d in kw.get("datas", [])]
        self.datas = [(os.path.join(d, os.path.basename(s)), s, "DATA") for s, d in kw.get("datas", [])]
        self.pure, self.scripts, self.binaries, self.zipfiles = [], [], [], []
class _Bos:
    def __init__(self, *a, **k):
        pass
g = {"__name__": "__main__", "__file__": spec, "Analysis": Analysis, "PYZ": _Bos, "EXE": _Bos, "COLLECT": _Bos}
exec(compile(open(spec, encoding="utf-8").read(), spec, "exec"), g)
json.dump(yakalanan, open(cikti, "w", encoding="utf-8"), ensure_ascii=False)
'''


def _mmz():
    """make_model_zip içe aktarımı yan etkisiz (modül docstring'i); tablo TEK KAYNAK olarak okunur."""
    s = importlib.util.spec_from_file_location("_mmz_d427", KOK / "build_tools" / "make_model_zip.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _cekirdek_onekleri() -> tuple[str, ...]:
    """make_base_zip içe aktarılamaz (üst düzeyde paketler) → CORE_MODELS AST'den."""
    for d in ast.parse((KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8")).body:
        if isinstance(d, ast.Assign) and any(getattr(h, "id", "") == "CORE_MODELS" for h in d.targets):
            return tuple(v.replace("pemf_backend/_internal/ai_models/", "") for v in ast.literal_eval(d.value))
    raise AssertionError("make_base_zip.py'de CORE_MODELS bulunamadi")


def _izlenenler() -> set[str]:
    ham = subprocess.run(["git", "ls-files", "-z"], cwd=KOK, capture_output=True, timeout=180).stdout
    return {x.decode("utf-8") for x in ham.split(b"\x00") if x}


@pytest.fixture(scope="module")
def spec_datas(tmp_path_factory) -> list[tuple[str, str]]:
    d = tmp_path_factory.mktemp("spec_d427")
    surucu, cikti = d / "surucu.py", d / "cikti.json"
    surucu.write_text(_SURUCU, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(surucu), str(SPEC), str(cikti)],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert p.returncode == 0 and cikti.exists(), (
        f"spec koşmadı (rc={p.returncode}):\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}"
    )
    return [(s, d.replace("\\", "/")) for s, d in json.loads(cikti.read_text(encoding="utf-8"))["datas"]]


def _depo_goreli(yol: str) -> str | None:
    """Depo köküne göre yol — büyük/küçük harf KORUNUR (git ls-files ile karşılaştırılır; yalnız önek karşılaştırması harfe duyarsız)."""
    tam, kok = os.path.normpath(yol), os.path.normpath(str(KOK))
    if not os.path.normcase(tam).startswith(os.path.normcase(kok) + os.sep):
        return None
    return tam[len(kok) + 1 :].replace("\\", "/")


def _app_katmani(spec_datas) -> dict[str, str]:
    """App katmanı (`_internal/ai_hub/...`) ağırlıkları: 'ai_hub/<modül>/<dosya>' -> spec kaynağı (depo-göreli)."""
    sonuc = {}
    for s, d in spec_datas:
        if d == "ai_hub" or d.startswith("ai_hub/"):
            g = _depo_goreli(s)
            if g is not None and os.path.isfile(s):
                sonuc[f"{d}/{os.path.basename(s)}"] = g
    return sonuc


def test_KRITIK_release_assets_teki_HER_dosya_bir_PAKETE_duser(spec_datas):
    mmz = _mmz()
    paketli = {r for t in (mmz.PROFILLER, mmz.PARCALAR) for liste in t.values() for r in liste}
    cekirdek = _cekirdek_onekleri()
    app = _app_katmani(spec_datas)
    izlenen = _izlenenler()
    dosyalar = sorted(p.relative_to(RA).as_posix() for p in RA.rglob("*") if p.is_file())
    assert len(dosyalar) >= 11, f"vakum: release_assets/ai_models'ta {len(dosyalar)} dosya (izlenen 11 bile yok)"
    hedefsiz, izlenmeyen_kaynak = [], []
    for rel in dosyalar:
        if rel in paketli or rel.lower().startswith(cekirdek):
            continue
        kaynak = app.get(rel)
        if kaynak is None:
            hedefsiz.append(rel)
        elif kaynak not in izlenen:
            izlenmeyen_kaynak.append(f"{rel} <- {kaynak}")
    assert not hedefsiz, (
        "release_assets/ai_models'taki bu dosyalar HICBIR launcher paketine (profil / parca / cekirdek / app katmani) girmiyor "
        f"→ sahada sessizce yok: {hedefsiz}"
    )
    assert not izlenmeyen_kaynak, (
        "app katmanina giden bu modeller depoda IZLENMEYEN yerel kopyadan geliyor → temiz makinede (clone + restore_assets + build) "
        f"pakete GIRMEZ: {izlenmeyen_kaynak}"
    )


def test_KRITIK_spec_ayni_hedefe_IKI_kaynak_GOMMEZ(spec_datas):
    hedefler: dict[str, list[str]] = {}
    for s, d in spec_datas:
        if d == "ai_hub" or d.startswith("ai_hub/"):
            hedefler.setdefault(f"{d}/{os.path.basename(s)}", []).append(s)
    cift = {h: k for h, k in hedefler.items() if len(k) > 1}
    assert not cift, f"ayni paket yoluna iki kaynak (hangisinin kazanacagi PyInstaller'a kalir): {cift}"


def test_KRITIK_RNA_aciklamasi_LAUNCHER_duzeninde_URETILIR(spec_datas, tmp_path, monkeypatch):
    """Gerçek uç: app katmanı (spec'in gömdüğü RNA modül dosyaları) + araştırma profili (make_model_zip'in paketlediği RNA dosyaları);
    başka model kökü YOK. `explain=1` analiz `xai` döndürmeli, `xai_error` değil.

    `.pt` depoda İZLENMEZ (yalnız derleme makinesinde ve — yayınlanınca — research.zip'te): klonda / CI'da yoksa profile, ürünün
    TEK mimari kaynağıyla (`_load_mlp_medium_pt`'nin katmanları) sabit tohumlu SENTETİK bir state_dict konur. Ölçülen şey ağırlığın
    değeri değil, paket düzeninde BULUNUP yüklenmesidir (gerçek ağırlık hiçbir yere kopyalanmaz/yazılmaz)."""
    torch = capraz.paket_yoksa_atla("torch")
    app_dir = tmp_path / "runtime" / "PEMF_Backend" / "_internal" / "ai_hub" / "inference_human_kidney_rna"
    app_dir.mkdir(parents=True)
    for hedef, kaynak in _app_katmani(spec_datas).items():
        if hedef.startswith("ai_hub/inference_human_kidney_rna/"):
            shutil.copy2(KOK / kaynak, app_dir / Path(hedef).name)
    profil = tmp_path / "ai_models"
    profil.mkdir()
    mmz = _mmz()
    meta = json.loads(
        (KOK / "ai_hub" / "inference_human_kidney_rna" / "best_model_meta.json").read_text(encoding="utf-8")
    )
    for rel in [*mmz.PROFILLER["research"], *(r for t in mmz.PARCALAR.values() for r in t)]:
        if not rel.startswith("ai_hub/inference_human_kidney_rna/"):
            continue
        (profil / rel).parent.mkdir(parents=True, exist_ok=True)
        if (RA / rel).is_file():
            shutil.copy2(RA / rel, profil / rel)
        elif rel == RNA_PT:
            # D3.48: SENTETİK ağırlık takipli özeti taşımaz → yalnız bu anahtar manifest dışı (yoksa bütünlük reddi — doğru davranış).
            from utils import model_downloader as _md

            _gercek = dict(_md._manifest_ozetleri())
            monkeypatch.setattr(_md, "_manifest_ozetleri", lambda: {k: v for k, v in _gercek.items() if k != RNA_PT})
            nn = torch.nn
            torch.manual_seed(0)
            sentetik = nn.Sequential(
                nn.Linear(int(meta["in_dim"]), 256),
                nn.BatchNorm1d(256),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(256, 128),
                nn.BatchNorm1d(128),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(128, 64),
                nn.BatchNorm1d(64),
                nn.ReLU(),
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, len(meta["class_labels"])),
            )
            torch.save(sentetik.state_dict(), profil / rel)
    (tmp_path / "ProgramData").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(app_dir.parents[1]), raising=False)
    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(profil))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    monkeypatch.delenv("PEMF_AI_SERVICE_URL", raising=False)

    from servers import ai_router

    from ai_hub.inference_human_kidney_rna import inference_human_kidney_rna as ihr

    # donmuş EXE'de modül _internal/ai_hub/<modül> altından yüklenir → HERE ve ondan içe aktarmada türetilen yollar oraya
    for ad, dosya in (
        ("META_PATH", "best_model_meta.json"),
        ("SCALER_PATH", "scaler.pkl"),
        ("FEATURE_IDX_PATH", "feature_indices.npy"),
        ("CLASSES_PATH", "classes.json"),
    ):
        assert getattr(ihr, ad) == ihr.HERE / dosya, f"{ad} artik HERE'den turemiyor — benzetim guncellensin"
        monkeypatch.setattr(ihr, ad, app_dir / dosya)
    monkeypatch.setattr(ihr, "HERE", app_dir)
    monkeypatch.setattr(ihr, "_XAI_PT_CACHE", {})
    monkeypatch.setattr(ai_router, "_models", {})
    n = int(meta["n_input_genes_total"])
    csv = "id," + ",".join(f"g{i}" for i in range(n)) + "\nH1," + ",".join("1" for _ in range(n)) + "\n"
    yanit = asyncio.run(
        ai_router.analyze_kidney_rna(
            file=None, csv_base64=base64.b64encode(csv.encode()).decode(), explain=True, _res=None
        )
    )
    assert yanit.get("status") == "success", yanit
    assert "xai_error" not in yanit, f"launcher duzeninde RNA aciklamasi DUSTU: {yanit.get('xai_error')}"
    assert yanit.get("xai") and yanit["xai"][0]["top_genes"], f"aciklama bos: {yanit.get('xai')}"
