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

import capraz
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
    """Git INDEX'inde mi? (`ls-files --error-unmatch` çıkış 0 = izleniyor).

    ⚠️ D4.06 (B-10.52, 2026-10-10): eski sürüm burada `check-ignore -q` soruyordu. `check-ignore` İZLENEN bir dosya için
    kuralları HİÇ değerlendirmez (`--no-index` olmadan) → `.gitignore` sonuna `*.onnx` eklemek ya da istisna satırını
    silmek bu kapıyı YEŞİL bırakıyordu; `git rm --cached` sonrası dosya diskte durduğu için yine yeşildi (ölçüldü)."""
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", f"release_assets/ai_models/{rel}"],
        cwd=_KOK,
        capture_output=True,
    )
    return r.returncode == 0


def _kural_disliyor_mu(rel: str) -> bool:
    """`.gitignore` kuralları bu yolu dışlıyor mu — index'e BAKMADAN (`--no-index`): bir sonraki `git add` onu alır mı.

    ⚠️ 4-A inc. 4A-2.10: yalnız DEPONUN `.gitignore`'u sayılır — `.git/info/exclude` / `core.excludesFile` makineye özgüdür
    (kural yalnız oradaysa kapı yerelde yeşil, CI'da/başka makinede kırmızı ya da 857 MB'lık ağırlık `git add -A` ile girer)."""
    return _gitignore_disliyor_mu(f"release_assets/ai_models/{rel}")


def _gitignore_disliyor_mu(yol: str) -> bool:
    import re

    r = subprocess.run(
        ["git", "check-ignore", "--no-index", "-v", yol],
        cwd=_KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    m = re.match(r"^(.*):(\d+):(.*)\t", r.stdout)
    if r.returncode != 0 or not m:
        return False
    kaynak, desen = m.group(1).strip('"').replace("\\", "/"), m.group(3)
    # `-v` NEGASYON (`!`) eşleşmesinde de çıkış 0 verir (ölçüldü) — o yol dışlanmıyor demektir.
    return (
        (kaynak == ".gitignore" or kaynak.endswith("/.gitignore"))
        and not kaynak.startswith((".git/", "/"))
        and (":" not in kaynak)
        and not desen.startswith("!")
    )


@pytest.mark.parametrize("rel", _DEPODA_DURMALI)
def test_KRITIK_yedegi_olmayan_model_DEPODA(rel):
    """Yayında kopyası olmayan model dosyası git'te DURMALI — yoksa makineyle birlikte kaybolur.

    D4.06 (B-10.52 · B-10.53): dosya yoksa SKIP DEĞİL FAIL (izlenen dosya her checkout'ta vardır; yokluğu silinmesidir);
    üç ayrı iddia: index'te · kural dışlamıyor · diskte ve 100 MiB altında."""
    assert _izleniyor_mu(rel), (
        f"{rel} git index'inde YOK (git rm --cached?). Bu dosyanin yayinlanmis hicbir pakette kopyasi YOK -> makine "
        f"kaybinda geri getirilemez."
    )
    assert not _kural_disliyor_mu(rel), (
        f"{rel} .gitignore tarafindan DISLANIYOR (--no-index). Muhtemel sebep: istisnalar dosyanin SONUNDAN yukari "
        f"tasindi ya da yeni bir genel kural (*.onnx/*.pkl) eklendi — sonraki `git add` onu almaz."
    )
    p = _MODELLER / rel
    assert p.is_file(), f"{rel} izleniyor ama diskte YOK — calisma agacindan silinmis"
    assert p.stat().st_size < _SERT_SINIR, (
        f"{rel} 100 MiB'i asmis ({p.stat().st_size / 2**20:.0f} MB) — git'e giremez, "
        f"Releases'e tasinmali ve bu listeden cikarilmali"
    )


@pytest.mark.parametrize("rel", _DEPODA_DURMAMALI)
def test_KARSIT_KANIT_buyuk_agirliklar_depoya_ALINMAZ(rel):
    """Karşıt-kanıt: "hepsini ekleyelim" biçimindeki bir yama depoyu kırar (100 MiB sert sınır).

    D4.06: index/kural iddiaları dosya diskte OLMASA da ölçülür (temiz klonda büyük ağırlık yoktur)."""
    assert not _izleniyor_mu(rel), f"{rel} git'e alinmis — GitHub 100 MiB ustunu SERT olarak reddeder, push kirilir"
    assert _kural_disliyor_mu(rel), f"{rel} .gitignore'da DISLANMIYOR — bir sonraki `git add -A` onu depoya alir"
    p = _MODELLER / rel
    # D5-F: eski düz pytest.skip — büyük ağırlık İZLENMEZ (Releases'te durur); ZORUNLU kipte DÜŞER
    capraz.atla_yoksa(f"release_assets/ai_models/{rel}")
    assert p.stat().st_size > _SERT_SINIR, f"{rel} artik kucuk — bu karsit-kanit guncellenmeli"


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


# ⚠️ 4-A inc. 4A-2.11: bu üç kapı `skipif(not _ARSIV.is_dir())` taşıyordu — arşiv `git rm -r` ile SİLİNİNCE üçü de ATLANIYOR,
# ZORUNLU=1'de bile rc 0 (ölçüldü). Arşiv İZLENEN ağaçtır: index'e bakan iki kapı koşulsuz koşar (silinmişse DÜŞER); diske bakan
# boyut kapısı `capraz.atla_yoksa(izlenen=True)` (varsayılanda nedenle atlar, ZORUNLU=1'de düşer — D4.04 deseni).
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
        assert (_KOK / kritik).is_file(), f"{kritik} izleniyor ama diskte YOK — calisma agacindan silinmis"


def test_KRITIK_arsivdeki_hicbir_dosya_gitignore_ile_GIZLENMIYOR():
    """`git checkout <dal> -- <yol>` gitignore'u ATLAR — dosyalar index'e girer ama gizli kalir.

    Olculdu (2026-08-18): `*.pkl` (satir 186) ve `*.pdf` kurallari 434 dosyanin 65'ini
    gizliyordu. Index dolu oldugu icin `git check-ignore` de sessizdi (`--no-index` sart).
    Sonuc: sonraki bir `git add` o dosyalari ATLARDI ve arsiv sessizce eksilirdi.
    """
    gizli = [
        a
        for a in _izlenen_dosyalar("training_archive")
        if _gitignore_disliyor_mu(a)  # 4A-2.10: yalnız deponun .gitignore'u (makineye özgü exclude sayılmaz)
    ]
    assert not gizli, (
        f"{len(gizli)} arsiv dosyasi gitignore ile gizleniyor (ornek: {gizli[:3]}). "
        "`!training_archive/**` negasyonu .gitignore'un EN SONUNDA durmali — git son eslesen "
        "kurali uygular."
    )


def test_KARSIT_KANIT_arsivde_100MiB_ustu_dosya_YOK():
    """Muafiyet sinirsiz degil: 100 MiB ustu bir dosya push'u tamamen kirar."""
    capraz.atla_yoksa("training_archive", izlenen=True)
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
