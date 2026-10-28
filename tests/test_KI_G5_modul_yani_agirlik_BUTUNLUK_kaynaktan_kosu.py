# Author: mertaygn, cglrgrkn
"""KI G5 (22 A3a G5 · D3.48 / Y18 ikizi) — modülün YANINDAKİ ana ağırlık KAYNAKTAN koşuda da bütünlük denetiminden geçer; donmuş paket DEĞİŞMEZ.

ÖLÇÜLEN (HEAD `fc7bcd6d` + KI): altı yükleme yeri ağırlığı `os.path.exists(<modül>/<ağırlık>)` ise DOĞRUDAN yüklüyor, bütünlük denetimli
`download_model_sync` yalnız modül yanında dosya YOKSA çağrılıyordu: `cat_disease` (XGBoost.pkl — git'te İZLENEN 53 MB, her kaynak koşusunda
modül yanında), `cat_thermal` (GhostNetV2.onnx), `em_kedi` / `inference_em_fantom` (BiLSTM_XXL_Raw.onnx), `inference_em_petri`
(BaggingRegressor.onnx), `inference_human_kidney_rna` XAI (mlp_medium_kirc.pt). Yönlendirici yalnız `release_assets` kopyasını denetliyordu →
modül yanındaki kurcalanmış / başka sürüm ağırlık uyarısız yükleniyordu. Donmuş pakette ≥ 5 MB ağırlık modül yanına gömülmez (spec) — yol hep
çözücüden geçer (kurulu 1.9.51 `_internal/ai_hub`: modül yanında yalnız ölçekleyiciler / küçük ONNX, hepsi `yan_dosya_coz` ile denetimli).

Kural (`utils.model_downloader.modul_yani_agirlik`): kaynaktan koşuda beklenen özet (`<dosya>.sha256` / takipli manifest) tutmazsa, dosya
kesikse ya da okunamazsa `ModelButunlukHatasi` (YÜKLENMEZ → AI ucu 503 + açık uyarı); beklenen özet YOKSA açık UYARI (günlük). Donmuşta yol
AYNEN döner (özet bile hesaplanmaz).

Sahte EN ALT katta: modül kaynağının geçici kopyası + yanında kurcalanmış ağırlık dosyası; manifest GERÇEK takipli dosya
(`release_assets/ai_models_sha256.json`); donmuş benzetimi `sys.frozen` + `sys._MEIPASS` (içinde manifestin paketteki konumu).
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import shutil
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
AI = KOK / "ai_hub"
MANIFEST = KOK / "release_assets" / "ai_models_sha256.json"

# Modül yanı ana ağırlık yükleme yerleri (dosya → manifest anahtarı).
YERLER = {
    "ai_hub/cat_disease/inference_cat_disease.py": "ai_hub/cat_disease/XGBoost.pkl",
    "ai_hub/cat_thermal/inference_cat_thermal.py": "ai_hub/cat_thermal/GhostNetV2.onnx",
    "ai_hub/em_kedi/inference_em_kedi.py": "ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx",
    "ai_hub/inference_em_fantom/inference_em_fantom.py": "ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx",
    "ai_hub/inference_em_petri/inference_em_petri.py": "ai_hub/inference_em_petri/BaggingRegressor.onnx",
    "ai_hub/inference_human_kidney_rna/inference_human_kidney_rna.py": "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt",
}
_KURCALANMIS = (
    b"\x00KI-G5-kurcalanmis" * 12_000
)  # ≥ asgari boyut (.onnx / .pt 100 kB, .pkl 200 B) → sebep "ozet", "kucuk" değil


@pytest.fixture
def md(monkeypatch):
    from utils import model_downloader as md

    monkeypatch.setattr(md, "_manifest_onbellegi", {})
    monkeypatch.setattr(md, "_ozet_onbellegi", {})
    return md


def _kopya(tmp_path: Path, modul_rel: str, agirlik: bytes | None) -> Path:
    """Modül kaynağı + (varsa) TRACKED yan dosyaları geçici `<modül>/` dizinine; ana ağırlık `agirlik` içeriğiyle (None → yok)."""
    kaynak = KOK / modul_rel
    d = tmp_path / kaynak.parent.name
    d.mkdir()
    shutil.copy2(kaynak, d / kaynak.name)
    for yan in kaynak.parent.glob("*.pkl"):
        if yan.name != Path(YERLER[modul_rel]).name:
            shutil.copy2(yan, d / yan.name)
    if agirlik is not None:
        (d / Path(YERLER[modul_rel]).name).write_bytes(agirlik)
    return d / kaynak.name


def _yukle(yol: Path):
    spec = importlib.util.spec_from_file_location(f"ki_g5_{yol.parent.parent.name}_{yol.stem}", yol)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _YukleyiciyeUlasti(AssertionError):
    """Kurcalanmış ağırlık bütünlük denetimine takılmadan GERÇEK yükleyiciye (onnxruntime / torch) ulaştı."""


def _yukleyici_yasak(*_a, **_k):
    raise _YukleyiciyeUlasti("kurcalanmış modül-yanı ağırlık denetimsiz YÜKLEYİCİYE ulaştı")


def _calistir(modul_rel: str, yol: Path, monkeypatch):
    """Ağırlığı modül YÜKLENİRKEN değil İŞLEVDE çözen iki yer: o işlev çağrılır; gerçek yükleyici (onnxruntime / torch) yerine nöbetçi
    (ağırlık yolu çözüldükten SONRASI — denetimin geçip geçmediği yükleyiciye ulaşılıp ulaşılmadığından ölçülür)."""
    if modul_rel.endswith("inference_cat_thermal.py"):
        import onnxruntime

        monkeypatch.setattr(onnxruntime, "InferenceSession", _yukleyici_yasak)
        return _yukle(yol).CatThermalPredictor()
    if modul_rel.endswith("inference_human_kidney_rna.py"):
        import pandas as pd

        mod = _yukle(yol)

        class _Olcekleyici:
            def transform(self, x):
                return x

        # Yardımcı veri (meta / ölçekleyici / seçim) bu sorunun dışı; ağırlık yolu GERÇEK `HERE`den çözülür.
        monkeypatch.setattr(
            mod,
            "_load_meta_and_aux",
            lambda: ({"torch_state_dict": "mlp_medium_kirc.pt"}, _Olcekleyici(), [0], ["KIRC", "other"]),
        )
        monkeypatch.setattr(mod, "_load_mlp_medium_pt", _yukleyici_yasak)
        return mod.xai_top_genler(pd.DataFrame({"g": [1.0]}, index=["h1"]))
    return _yukle(yol)


# ── 1) Altı yükleme yeri: kurcalanmış modül-yanı ağırlık YÜKLENMEZ (kaynaktan koşu) ─────────────────────────────────────────────────
@pytest.mark.parametrize("modul_rel", sorted(YERLER))
def test_KRITIK_KI_G5_kurcalanmis_MODUL_YANI_agirlik_REDDEDILIR(md, tmp_path, caplog, monkeypatch, modul_rel):
    assert MANIFEST.is_file(), "takipli manifest yok"
    yol = _kopya(tmp_path, modul_rel, _KURCALANMIS)
    with caplog.at_level(logging.ERROR, logger="utils.model_downloader"):
        with pytest.raises(md.ModelButunlukHatasi) as e:
            _calistir(modul_rel, yol, monkeypatch)
    assert e.value.sebep == "ozet" and e.value.dosya.endswith(Path(YERLER[modul_rel]).name), (
        e.value.dosya,
        e.value.sebep,
    )
    assert any("REDDİ" in r.getMessage() for r in caplog.records), "ret günlüğe yazılmadı"


def test_KARSIT_KI_G5_dogru_ozetli_MODUL_YANI_agirlik_KABUL_edilir(md, tmp_path, caplog):
    """İzlenen gerçek XGBoost.pkl (manifestle AYNI) modül yanında → yüklenir, uyarı / ret YOK."""
    modul_rel = "ai_hub/cat_disease/inference_cat_disease.py"
    yol = _kopya(tmp_path, modul_rel, (AI / "cat_disease" / "XGBoost.pkl").read_bytes())
    with caplog.at_level(logging.WARNING, logger="utils.model_downloader"):
        mod = _yukle(yol)
    assert Path(mod.MODEL_PATH) == yol.parent / "XGBoost.pkl"
    assert not [r for r in caplog.records if "XGBoost" in r.getMessage()], [r.getMessage() for r in caplog.records]


# ── 2) Yardımcının kendisi (sahte EN ALT katta: dosya + yan özet / manifest) ────────────────────────────────────────────────────────
def test_KI_G5_yardimci_yan_ozet_tutmazsa_RET_kesikse_RET_ozet_yoksa_ACIK_UYARI(md, tmp_path, monkeypatch, caplog):
    import hashlib

    d = tmp_path / "ai_hub" / "yeni_modul"
    d.mkdir(parents=True)
    agirlik = d / "model.onnx"
    agirlik.write_bytes(b"a" * 200_000)
    (d / "model.onnx.sha256").write_text(
        hashlib.sha256(b"a" * 200_000).hexdigest() + "  model.onnx\n", encoding="utf-8"
    )
    assert md.modul_yani_agirlik(agirlik, "ai_hub/yeni_modul/model.onnx") == str(agirlik)
    agirlik.write_bytes(b"b" * 200_000)
    with pytest.raises(md.ModelButunlukHatasi) as e:
        md.modul_yani_agirlik(agirlik, "ai_hub/yeni_modul/model.onnx")
    assert e.value.sebep == "ozet"
    agirlik.write_bytes(b"b" * 10)
    with pytest.raises(md.ModelButunlukHatasi) as e:
        md.modul_yani_agirlik(agirlik, "ai_hub/yeni_modul/model.onnx")
    assert e.value.sebep == "kucuk"
    (d / "model.onnx.sha256").unlink()
    agirlik.write_bytes(b"c" * 200_000)
    with caplog.at_level(logging.WARNING, logger="utils.model_downloader"):
        assert md.modul_yani_agirlik(agirlik, "ai_hub/yeni_modul/model.onnx") == str(agirlik)
    assert any("DENETİMSİZ" in r.getMessage() and "model.onnx" in r.getMessage() for r in caplog.records), (
        "beklenen özeti olmayan modül-yanı ağırlık AÇIK uyarısız yüklendi"
    )


# ── 3) Donmuş paket DEĞİŞMEZ ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def donmus(md, tmp_path, monkeypatch):
    """Donmuş benzetimi: `sys.frozen` + `_MEIPASS` (manifest paketteki yerinde: `_internal/ai_hub/ai_models_sha256.json`)."""
    mei = tmp_path / "_internal"
    (mei / "ai_hub").mkdir(parents=True)
    shutil.copy2(MANIFEST, mei / "ai_hub" / MANIFEST.name)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    return md


def test_KRITIK_KI_G5_DONMUS_modul_yani_agirlik_AYNEN_doner_ozet_HESAPLANMAZ(donmus, tmp_path, monkeypatch):
    md = donmus
    agirlik = tmp_path / "ai_hub" / "em_kedi" / "BiLSTM_XXL_Raw.onnx"
    agirlik.parent.mkdir(parents=True)
    agirlik.write_bytes(_KURCALANMIS)

    def _ozet_yasak(*_a, **_k):
        raise AssertionError("donmuş pakette modül-yanı ağırlığın özeti hesaplandı (davranış değişti)")

    monkeypatch.setattr(md, "_dosya_ozeti", _ozet_yasak)
    assert md.modul_yani_agirlik(agirlik, "ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx") == str(agirlik)


def test_KRITIK_KI_G5_DONMUS_modul_yaninda_agirlik_YOKSA_cozucu_AYNEN_cagrilir(donmus, tmp_path, monkeypatch):
    """Donmuş paketin gerçek düzeni (büyük ağırlık modül yanında YOK): modül `download_model_sync`'i aynı göreli yolla çağırır."""
    md = donmus
    cagri = []
    monkeypatch.setattr(md, "download_model_sync", lambda rel: cagri.append(rel) or f"COZULDU:{rel}")
    mod = _yukle(_kopya(tmp_path, "ai_hub/em_kedi/inference_em_kedi.py", None))
    assert (
        cagri == ["ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx"]
        and mod.ONNX_PATH == "COZULDU:ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx"
    )
    assert mod.MODEL_DOWNLOAD_ERROR is None


def test_KRITIK_KI_G5_DONMUS_modul_yaninda_kurcalanmis_agirlik_eski_davranis_YUKLENIR(donmus, tmp_path):
    """Donmuşta modül yanında ağırlık olsa bile (spec gömmez; elle bırakılmış) davranış HEAD'dekiyle AYNI: yol aynen kullanılır."""
    yol = _kopya(tmp_path, "ai_hub/em_kedi/inference_em_kedi.py", _KURCALANMIS)
    mod = _yukle(yol)
    assert Path(mod.ONNX_PATH) == yol.parent / "BiLSTM_XXL_Raw.onnx"


# ── 4) Yokluk kapısı: "modül yanında varsa DENETİMSİZ yükle" kalıbı ai_hub'da kalmadı (yeni modül de yakalanır) ──────────────────────
def _cagri_adlari(dugumler) -> set[str]:
    adlar = set()
    for kok in dugumler:
        for n in ast.walk(kok):
            if isinstance(n, ast.Call):
                f = n.func
                adlar.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return adlar


def _olumsuz_varlik(test) -> bool:
    for n in ast.walk(test):
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not) and isinstance(n.operand, ast.Call):
            f = n.operand.func
            if (isinstance(f, ast.Attribute) and f.attr == "exists") or (isinstance(f, ast.Name) and f.id == "exists"):
                return True
    return False


def test_KRITIK_KI_G5_modul_yani_varsa_denetimsiz_yukleme_KALIBI_YOK():
    yerler, eksik = {}, []
    for py in sorted(AI.rglob("*.py")):
        rel = py.relative_to(KOK).as_posix()
        agac = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(agac):
            if isinstance(n, ast.If) and _olumsuz_varlik(n.test) and "download_model_sync" in _cagri_adlari(n.body):
                yerler.setdefault(rel, []).append(n.lineno)
                if not ({"_modul_yani", "modul_yani_agirlik"} & _cagri_adlari(n.orelse)):
                    eksik.append(f"{rel}:{n.lineno}")
    assert set(YERLER) <= set(yerler), (
        f"kapı KÖR: bilinen yerler bulunamadı (kalıp değişti?): {sorted(set(YERLER) - set(yerler))}"
    )
    assert not eksik, (
        f"modül yanında ağırlık VARSA bütünlük denetimsiz yükleniyor (else dalında `_modul_yani` yok): {eksik}"
    )
