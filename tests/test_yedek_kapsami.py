# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI MODEL AĞIRLIKLARININ HEPSİ GERİ GETİRİLEBİLİR OLMALI (denetim 2026-08-18).

Sahip şunu istedi: *"guii klasörü taşınabilir bir PEMF projesi olsun; makineye bir şey olursa
git yedek olsun — build çıktıları lazım değil, kaynaklar lazım."*

Ölçüldü: `release_assets/ai_models` altındaki 51 model dosyasından **40'ı** yayınlanmış
paketlerde yedekli (`home.zip` 8 + `vet.zip` 9 + `research.zip` 20 + çekirdek `base-deps` 3),
ama **11'i hiçbir yerde yoktu** — bu makine ölse geri getirilemezlerdi. On biri de küçük
(toplam 6 MB), yani git'in 100 MiB sert sınırının çok altında → depoya alındılar.

⚠️ BÜYÜK AĞIRLIKLAR GİT'E ALINMAZ. `v22_kmc_classictrio_kmc.onnx` tek başına 857 MB; git'te
yeri yok (100 MiB sert sınır) ve LFS ücretli (public muafiyeti yok). Onlar Releases'te durur.

⚠️ BU KAPININ ASIL İŞİ: `.gitignore`da `*.onnx`/`*.pkl` gibi GENEL kurallar var ve git SON eşleşen
kuralı uygular. Bu yüzden istisnalar dosyanın SONUNDA olmak zorunda — ölçüldü: yukarı konulduğunda
11 dosyadan yalnız 1'i görünüyordu. Biri istisnaları yukarı taşırsa ya da yeni bir genel kural
eklerse yedek SESSİZCE kaybolur; bu test onu yakalar.
"""

import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_MODELLER = _KOK / "release_assets" / "ai_models"

#: Yayınlanmış paketlerde YEDEĞİ OLMAYAN, bu yüzden depoda DURMASI ŞART olan dosyalar.
_DEPODA_DURMALI = (
    "ai_hub/inference_human_kidney_disease/CatBoost.onnx",
    "ai_hub/inference_human_kidney_disease/ExtraTrees.onnx",
    "ai_hub/inference_human_kidney_disease/LogisticRegression.onnx",
    "ai_hub/inference_human_kidney_disease/RandomForest.onnx",
    "ai_hub/inference_human_kidney_disease/best_model.txt",
    "ai_hub/inference_human_kidney_disease/preprocessor.pkl",
    "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.onnx",
    "ai_hub/inference_human_kidney_rna/scaler.pkl",
    "ai_hub/inference_em_petri/scaler_X.pkl",
    "ai_hub/inference_em_petri/scaler_extra.pkl",
    "ai_hub/inference_em_petri/scaler_y.pkl",
)

#: Git'e ASLA girmemesi gereken (100 MiB üstü) örnekler — karşıt-kanıt.
_DEPODA_DURMAMALI = (
    "ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx",
    "ai_hub/inference_em_petri/BaggingRegressor.onnx",
)

_SERT_SINIR = 100 * 1024 * 1024


def _izleniyor_mu(rel: str) -> bool:
    """Git bu yolu YOK SAYIYOR mu? (`check-ignore` çıkış kodu 0 = yok sayılıyor)"""
    r = subprocess.run(
        ["git", "check-ignore", "-q", f"release_assets/ai_models/{rel}"],
        cwd=_KOK,
        capture_output=True,
    )
    return r.returncode != 0


@pytest.mark.skipif(not _MODELLER.is_dir(), reason="model dizini bu çalışma kopyasında yok")
@pytest.mark.parametrize("rel", _DEPODA_DURMALI)
def test_KRITIK_yedegi_olmayan_model_DEPODA(rel):
    """Yayında kopyası olmayan model dosyası git'te DURMALI — yoksa makineyle birlikte kaybolur."""
    p = _MODELLER / rel
    if not p.is_file():
        pytest.skip(f"dosya bu kopyada yok: {rel}")
    assert p.stat().st_size < _SERT_SINIR, (
        f"{rel} 100 MiB'i asmis ({p.stat().st_size / 2**20:.0f} MB) — git'e giremez, "
        f"Releases'e tasinmali ve bu listeden cikarilmali"
    )
    assert _izleniyor_mu(rel), (
        f"{rel} .gitignore tarafindan DISLANIYOR. Bu dosyanin yayinlanmis hicbir pakette kopyasi "
        f"YOK -> makine kaybinda geri getirilemez. Muhtemel sebep: istisnalar dosyanin SONUNDAN "
        f"yukari tasindi ya da yeni bir genel kural (*.onnx/*.pkl) eklendi."
    )


@pytest.mark.skipif(not _MODELLER.is_dir(), reason="model dizini bu çalışma kopyasında yok")
@pytest.mark.parametrize("rel", _DEPODA_DURMAMALI)
def test_KARSIT_KANIT_buyuk_agirliklar_depoya_ALINMAZ(rel):
    """Karşıt-kanıt: "hepsini ekleyelim" biçimindeki bir yama depoyu kırar (100 MiB sert sınır)."""
    p = _MODELLER / rel
    if not p.is_file():
        pytest.skip(f"dosya bu kopyada yok: {rel}")
    assert p.stat().st_size > _SERT_SINIR, f"{rel} artik kucuk — bu karsit-kanit guncellenmeli"
    assert not _izleniyor_mu(rel), (
        f"{rel} ({p.stat().st_size / 2**20:.0f} MB) git'e alinmis — GitHub 100 MiB ustunu SERT "
        f"olarak reddeder, push tamamen kirilir. Buyuk agirliklar Releases'te durmali."
    )


# ── training_archive/ — silinen `esp` dalindan kurtarilan egitim arsivi (2026-08-18) ──────────
# `esp` dali silinmeden once bu 434 dosya (296 MB) production-hardening'e alindi: tek kopyasi
# versiyonlanmayan yerel bir klasordeydi ve iki dalin ORTAK ATASI YOKTU, yani dal silinince
# git tarafinda geri getirilemezlerdi. `models_em_kedi/scaler_{X,y}.pkl` uretimdekinden FARKLI
# ozellik uzayina (10 vs 5) ait ve kaynak veri seti depoda olmadigi icin yeniden fit EDILEMEZ.
#
# pre-commit'in 2 MB `check-added-large-files` esigi bu yol icin muaf tutuldu; asagidaki test
# GERCEK tavani (GitHub'in 100 MiB sert siniri) kilitler ki muafiyet sinirsiz sanilmasin.

_ARSIV = _KOK / "training_archive"


def _izlenen_dosyalar(dizin: str) -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z", "--", dizin], cwd=_KOK, capture_output=True, text=True)
    return [a for a in r.stdout.split(chr(0)) if a]


@pytest.mark.skipif(not _ARSIV.is_dir(), reason="training_archive bu çalışma kopyasında yok")
def test_KRITIK_egitim_arsivi_DEPODA():
    """`esp` silindikten sonra tek kaynak burasi — arsiv sessizce dusmemeli."""
    izlenen = _izlenen_dosyalar("training_archive")
    assert len(izlenen) > 400, (
        f"training_archive'da yalnizca {len(izlenen)} izlenen dosya var (>400 bekleniyor). "
        "esp dali SILINDI; bu agac dusrse doktora/TUBITAK egitim artefaktlari geri getirilemez."
    )
    for kritik in (
        "training_archive/dr_calisma/models/models_em_kedi/scaler_X.pkl",
        "training_archive/dr_calisma/models/models_em_kedi/scaler_y.pkl",
    ):
        assert kritik in izlenen, f"{kritik} izlenmiyor — yeniden fit EDILEMEZ, kaybi kalicidir"


@pytest.mark.skipif(not _ARSIV.is_dir(), reason="training_archive bu çalışma kopyasında yok")
def test_KRITIK_arsivdeki_hicbir_dosya_gitignore_ile_GIZLENMIYOR():
    """`git checkout <dal> -- <yol>` gitignore'u ATLAR — dosyalar index'e girer ama gizli kalir.

    Olculdu (2026-08-18): `*.pkl` (satir 186) ve `*.pdf` kurallari 434 dosyanin 65'ini
    gizliyordu. Index dolu oldugu icin `git check-ignore` de sessizdi (`--no-index` sart).
    Sonuc: sonraki bir `git add` o dosyalari ATLARDI ve arsiv sessizce eksilirdi.
    """
    gizli = [
        a
        for a in _izlenen_dosyalar("training_archive")
        if subprocess.run(["git", "check-ignore", "--no-index", "-q", a], cwd=_KOK, capture_output=True).returncode == 0
    ]
    assert not gizli, (
        f"{len(gizli)} arsiv dosyasi gitignore ile gizleniyor (ornek: {gizli[:3]}). "
        "`!training_archive/**` negasyonu .gitignore'un EN SONUNDA durmali — git son eslesen "
        "kurali uygular."
    )


@pytest.mark.skipif(not _ARSIV.is_dir(), reason="training_archive bu çalışma kopyasında yok")
def test_KARSIT_KANIT_arsivde_100MiB_ustu_dosya_YOK():
    """Muafiyet sinirsiz degil: 100 MiB ustu bir dosya push'u tamamen kirar."""
    asan = [
        (a, (_KOK / a).stat().st_size)
        for a in _izlenen_dosyalar("training_archive")
        if (_KOK / a).is_file() and (_KOK / a).stat().st_size > _SERT_SINIR
    ]
    assert not asan, (
        "training_archive'da GitHub'in 100 MiB sert sinirini asan dosya var: "
        + ", ".join(f"{a} ({b / 2**20:.0f} MB)" for a, b in asan)
        + ". pre-commit muafiyeti 2 MB esigini kaldirdi ama GERCEK tavan bu — Releases'e tasiyin."
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
