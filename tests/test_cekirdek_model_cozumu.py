# Author: mertaygn, cglrgrkn
"""ÇEKİRDEK MODEL ÇÖZÜMÜ — vet-only kurulumda AI Pro organ lokalizasyonu çalışır mı?

BAĞLAM (2026-08-10). `inference_cat_organ` (3 ONNX, ~200 MB) AI Pro'nun organ
lokalizasyonunu çalıştırır ve eskiden YALNIZ `home.zip` içindeydi. Bu yüzden
"Veteriner" profili "Ev Sahibi"ne bağımlıydı: yalnız veteriner kuran kullanıcıda
özellik SESSİZCE bozuluyordu. Model ÇEKİRDEĞE alındı
(`build_tools/make_base_zip.py::CORE_MODELS` → deps katmanı → frozen bundle).

Bu dosya, taşımanın SAHADA gerçekten işe yaradığını kanıtlar. Kritik nokta:
launcher kuruluma `PEMF_AI_MODELS_DIR=<install>/ai_models` ortam değişkenini verir
(bkz. launcher/core/src/install.rs::models_dir). O dizin vet-only kurulumda VARDIR
ama içinde cat_organ YOKTUR. Çözücü "ilk VAR OLAN kökü seç" mantığıyla çalışsaydı
bundle'a hiç düşmez, model bulunamazdı. `find_installed_model` DOSYA-başına düşer;
aşağıdaki testler bu davranışı kilitler — regresyonu sessiz olmaz.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import model_downloader  # noqa: E402

# catorgan_predictor._resolve_models'in download_model_sync'e verdiği repo_path'ler.
CEKIRDEK_REPO_PATHS = [
    "ai_hub/inference_cat_organ/models/yolov8m-seg.onnx",
    "ai_hub/inference_cat_organ/models/superanimal_quadruped_fasterrcnn_mobilenet_v3_large_fpn.onnx",
    "ai_hub/inference_cat_organ/models/superanimal_quadruped_rtmpose_s.onnx",
]

# _model_integrity_ok asgari boyut eşiği .onnx için 100_000 bayt — sahte model bunu geçmeli,
# yoksa test "model yok" ile "model bozuk"u ayırt edemez.
SAHTE_ONNX = b"\x00" * 200_000


def _kokleri_izole_et(monkeypatch, tmp_path: Path) -> None:
    """PEMF_AI_MODELS_DIR ve bundle DIŞINDAKİ tüm model köklerini boş dizine yönlendir.

    ⚠️ `release_assets/ai_models` (proje-yanı kök) bu makinede GERÇEKTEN dolu. İzole
    edilmezse testler modeli oradan bulur ve "çekirdek paketten çözülüyor" sanılır —
    testin kanıtlamak istediği şeyin tam tersi. Kök #4 `model_downloader.__file__`
    üzerinden hesaplandığı için modül niteliği yamanır (çağrı anında okunur)."""
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "yok_programdata"))
    monkeypatch.setattr(model_downloader, "get_persistent_model_dir", lambda: tmp_path / "yok_appdata")
    monkeypatch.setattr(model_downloader, "__file__", str(tmp_path / "yok_proje" / "utils" / "md.py"))


def _sahte_model_yaz(kok: Path, repo_path: str) -> Path:
    p = kok / repo_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(SAHTE_ONNX)
    return p


@pytest.fixture
def vet_only_kurulum(tmp_path, monkeypatch):
    """Vet-only kurulumun sahadaki hâli: PEMF_AI_MODELS_DIR VAR ama cat_organ YOK;
    bundle (frozen _internal/ai_models) çekirdek modeli TAŞIR."""
    install_models = tmp_path / "install" / "ai_models"
    (install_models / "ai_hub" / "em_kedi").mkdir(parents=True)
    (install_models / "ai_hub" / "em_kedi" / "BiLSTM_XXL_Raw.onnx").write_bytes(SAHTE_ONNX)

    bundle = tmp_path / "bundle" / "ai_models"
    for rp in CEKIRDEK_REPO_PATHS:
        _sahte_model_yaz(bundle, rp)

    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(install_models))
    _kokleri_izole_et(monkeypatch, tmp_path)
    monkeypatch.setattr(model_downloader, "resource_path", lambda rel: str(tmp_path / "bundle" / rel))
    return {"install": install_models, "bundle": bundle}


@pytest.mark.parametrize("repo_path", CEKIRDEK_REPO_PATHS)
def test_KRITIK_vet_only_kurulumda_cekirdek_model_BULUNUR(vet_only_kurulum, repo_path):
    """Ev Sahibi paketi kurulu DEĞİLKEN cat_organ modelleri bundle'dan çözülmeli.

    Bu testin kırmızıya dönmesi = profil bağımsızlığı yalanı: kullanıcı yalnız veteriner
    kurar, AI Pro organ lokalizasyonu sessizce çalışmaz."""
    bulunan = model_downloader.find_installed_model(repo_path)
    assert bulunan is not None, (
        f"{repo_path} vet-only kurulumda ÇÖZÜLEMEDİ → AI Pro organ lokalizasyonu SESSİZCE bozuk. "
        "Model çekirdekten düşmüş ya da çözücü kök-başına seçime dönmüş olabilir."
    )
    assert "bundle" in str(bulunan).replace("\\", "/"), f"beklenmedik kaynaktan çözüldü: {bulunan}"


def test_KRITIK_cozucu_ILK_VAR_OLAN_KOKTE_DURMAZ(vet_only_kurulum):
    """Çözücü DOSYA-başına düşmeli. Kök-başına seçime dönerse (ilk var olan kök kazanır),
    PEMF_AI_MODELS_DIR hep var olduğu için bundle'a HİÇ bakılmaz ve çekirdeğe taşıma
    hiçbir şey çözmemiş olur."""
    # Aynı çağrıda: install kökünde OLAN bir model install'dan, OLMAYAN bundle'dan gelmeli.
    vet_modeli = model_downloader.find_installed_model("ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx")
    cekirdek = model_downloader.find_installed_model(CEKIRDEK_REPO_PATHS[0])

    assert vet_modeli is not None and "install" in str(vet_modeli).replace("\\", "/")
    assert cekirdek is not None and "bundle" in str(cekirdek).replace("\\", "/"), (
        "çözücü ilk var olan kökte durdu → çekirdeğe taşıma İŞE YARAMAZ"
    )


def test_KRITIK_home_paketi_KURULUYSA_yine_calisir(vet_only_kurulum):
    """Ev Sahibi de kuruluysa (model install kökünde de var) çözüm bozulmamalı —
    taşıma, mevcut kurulumlar için regresyon olmamalı."""
    yerel = _sahte_model_yaz(vet_only_kurulum["install"], CEKIRDEK_REPO_PATHS[0])
    bulunan = model_downloader.find_installed_model(CEKIRDEK_REPO_PATHS[0])
    assert bulunan is not None
    assert Path(bulunan) == yerel, "kurulu profil modeli çekirdek kopyayı ezmeli (yerel öncelikli)"


def test_cekirdek_model_YOKSA_None_doner(tmp_path, monkeypatch):
    """Karşı-kanıt: modeller hiçbir kökte yoksa None dönmeli. Bu olmadan yukarıdaki
    testler her koşulda yeşil yanabilir (yanlış güvence)."""
    monkeypatch.setenv("PEMF_AI_MODELS_DIR", str(tmp_path / "bos"))
    _kokleri_izole_et(monkeypatch, tmp_path)
    monkeypatch.setattr(model_downloader, "resource_path", lambda rel: str(tmp_path / "yok3"))
    assert model_downloader.find_installed_model(CEKIRDEK_REPO_PATHS[0]) is None


def test_predictor_download_model_sync_YOLUNU_kullanir():
    """catorgan_predictor gerçekten `download_model_sync` üzerinden çözmeli.
    Doğrudan `models_dir` sabitine dönerse bundle'a düşüş devre dışı kalır ve
    yukarıdaki testler gerçeği ölçmez hâle gelir."""
    src = (
        Path(__file__).resolve().parent.parent / "ai_hub" / "inference_cat_organ" / "catorgan_predictor.py"
    ).read_text(encoding="utf-8")
    assert "download_model_sync(f\"ai_hub/inference_cat_organ/models/{fname}\")" in src, (
        "cat_organ model çözümü download_model_sync yolundan çıkmış → çekirdek bundle'a düşmez"
    )


def test_paket_betigi_cekirdek_modeli_KORUR():
    """`make_base_zip.py` çekirdek istisnası silinirse model pakete girmez ve saha
    kurulumları sessizce bozulur. Tek-kaynak burada kilitlenir."""
    src = (Path(__file__).resolve().parent.parent / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8")
    assert "CORE_MODELS" in src, "CORE_MODELS istisnası kaldırılmış"
    assert "inference_cat_organ" in src, "çekirdek model yolu kaldırılmış"


def test_KRITIK_profil_paketi_cekirdek_modeli_KABUL_ETMEZ(monkeypatch):
    """Çekirdek model bir profil paketine geri konursa kullanıcı ~209 MB'ı İKİ KEZ indirir
    ve iki kopya sürüm-atlayabilir. `make_model_zip.py` bunu üretim anında reddetmeli —
    yorum satırıyla değil, KODLA."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build_tools"))
    import make_model_zip

    monkeypatch.setitem(
        make_model_zip.PROFILLER,
        "home",
        ("ai_hub/inference_cat_organ/models/yolov8m-seg.onnx",),
    )
    with pytest.raises(SystemExit) as ex:
        make_model_zip.dosyalari_topla("home")
    assert "CEKIRDEK" in str(ex.value), f"reddedildi ama sebebi belirsiz: {ex.value}"


def test_profil_paketi_icerigi_KODDA_tek_kaynak():
    """Paketler eskiden ELLE üretiliyordu; ne içerdikleri hiçbir yerde yazılı değildi —
    profil bağımlılığı hatası tam olarak buradan doğdu ve ancak yayındaki zip'in merkezî
    dizini uzaktan okunarak bulunabildi. İçerik KODDA kalmalı."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build_tools"))
    import make_model_zip

    assert make_model_zip.PROFILLER.get("home"), "home paketi içeriği tanımsız"
    assert not any("inference_cat_organ" in yol for yol in make_model_zip.PROFILLER["home"]), (
        "çekirdek model home paketine geri konmuş → çift indirme"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
