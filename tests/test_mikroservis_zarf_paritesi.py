# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MİKROSERVİS ↔ GÖMÜLÜ YOL ZARF PARİTESİ — denetim 2026-08-28 #09.

Aynı arayüz iki taşımayı da tüketiyor: gömülü yol (`servers/ai_router.py`, klinik EXE) ve GPU
mikroservisi (`ai_service/app.py`, Docker). Yanıt zarfları AYRIŞINCA arayüz veriyi göremiyor ve
panel SESSİZCE boş kalıyor — hata yok, uyarı yok, 200 OK.

ÖLÇÜLEN AYRIŞMALAR (gerçek fixture + FastAPI TestClient ile):
  * `/infer/thermal` → mikroservis `{status, device, inference_ms, label, probability_sick,
    confidence}`; gömülü yol `{status, prediction, image_base64}`. Arayüzün TÜM termal paneli
    (`AiHubScreen.tsx:1517` geçmiş kaydı + `:1603` sonuç satırı) `result.prediction` kapısının
    ardında → GPU profilinde panel boş.
  * `/infer/reticulocytes` → mikroservis yalnız `n_detections`; gömülü yol sınıf bazlı `counts`.
    Retikülosit ORANI (`:1535`) ve üç sayım satırı (`:1608-1612`) `counts`a bağlı. Veri kayıp
    DEĞİLDİ: aynı `r.boxes.cls`ten türetilebiliyordu, atılıyordu.

⚠️ GERİYE UYUM: düz anahtarlar (label/probability_sick/n_detections) KALDI — :8100'e doğrudan
bağlanan duman betikleri kırılmasın. Yalnız alan EKLENDİ, hiçbir alan çıkarılmadı.

⚠️ Bu profil şu an SEVK EDİLMİYOR (CI/yayın betiklerinde Docker imajı yok); bulgu gelecekteki
mikroservis geçişi için kapatıldı.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_SERVIS = _KOK / "ai_service" / "app.py"
_ROUTER = _KOK / "servers" / "ai_router.py"


def _yanit_anahtarlari(predictor_adi: str) -> set[str]:
    """`predictors.get("<ad>")` çağıran fonksiyondaki `yanit = {...}` sözlüğünün anahtarları.

    ⚠️ ÇIPA AST'DE, METİNDE DEĞİL. İlk sürüm düz metin araması yapıyordu ve `"prediction"`
    kelimesini KENDİ AÇIKLAMA YORUMUMDA buluyordu → sarmalayıcıyı silen mutasyon kapıyı YEŞİL
    bırakıyordu (ölçüldü). Bu projede aynı zayıf-çıpa hatası bu turda üç kez tekrarlandı.
    """
    agac = ast.parse(_SERVIS.read_text(encoding="utf-8"))
    for fn in ast.walk(agac):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        govde_metni = ast.unparse(fn)
        if f"predictors.get('{predictor_adi}')" not in govde_metni:
            continue
        for d in ast.walk(fn):
            if (
                isinstance(d, ast.Assign)
                and len(d.targets) == 1
                and isinstance(d.targets[0], ast.Name)
                and d.targets[0].id == "yanit"
                and isinstance(d.value, ast.Dict)
            ):
                return {k.value for k in d.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    pytest.fail(f"'{predictor_adi}' ucundaki `yanit = {{...}}` sözlüğü bulunamadı (çıpa kaymış olabilir)")


def test_cipa_calisiyor():
    """Kapının kendisi: iki uç da bulunabiliyor mu."""
    assert "status" in _yanit_anahtarlari("thermal")
    assert "status" in _yanit_anahtarlari("reticulocytes")


def test_KRITIK_termal_zarfi_prediction_TASIYOR():
    """Arayüzün termal paneli `prediction` kapısının ardında."""
    assert "prediction" in _yanit_anahtarlari("thermal"), (
        "mikroservis termal yanıtı `prediction` sarmalayıcısını taşımıyor → GPU profilinde "
        "arayüzün termal paneli SESSİZCE boş kalır (veri gelir, arayüz göremez)"
    )


@pytest.mark.parametrize("alan", ["label", "probability_sick"])
def test_termal_duz_anahtarlar_KORUNDU(alan):
    """Geriye uyum: :8100'e doğrudan bağlanan istemciler kırılmamalı."""
    metin = _SERVIS.read_text(encoding="utf-8")
    i = metin.find('clf = predictors.get("thermal")')
    # Düz anahtarlar `**result` ile geliyor; sözleşmeyi kaynak üzerinden doğrula.
    assert "**result" in metin[i : i + 1800], f"`**result` düz açılımı kaldırılmış — '{alan}' kaybolur"


def test_KRITIK_retikulosit_zarfi_counts_TASIYOR():
    """Retikülosit oranı ve üç sayım satırı `counts` alanına bağlı."""
    anahtarlar = _yanit_anahtarlari("reticulocytes")
    assert "counts" in anahtarlar, (
        "mikroservis retikülosit yanıtı `counts` taşımıyor → oran ve sınıf sayımları görünmez"
    )
    assert "n_detections" in anahtarlar, "geriye uyum alanı `n_detections` kaldırılmış"


def test_KRITIK_counts_sinif_adlari_gomulu_yolla_AYNI():
    """Sınıf adları ayrışırsa arayüz yine boş satır gösterir (sessiz ayrışmanın ikinci hâli)."""
    servis = _SERVIS.read_text(encoding="utf-8")
    router = _ROUTER.read_text(encoding="utf-8")

    def _adlar(metin: str, degisken: str) -> list[str]:
        m = re.search(rf"{degisken}\s*=\s*\[(.*?)\]", metin, re.DOTALL)
        assert m, f"{degisken} bulunamadı"
        return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))

    assert _adlar(servis, "SINIF_ADLARI") == _adlar(router, "CLASS_NAMES"), (
        "mikroservis ve gömülü yol farklı sınıf adları kullanıyor → sayımlar arayüzde eşleşmez"
    )


# ── Docker imajında yan model dosyaları ──────────────────────────────────────


def test_KRITIK_yan_dosya_cozucusu_VAR():
    """Ana model `/models`'e düşüyordu ama scaler/encoder modül dizinine sabitti."""
    from utils.model_downloader import yan_dosya_coz

    assert callable(yan_dosya_coz)


def test_KRITIK_yan_dosya_cozucusu_OLMAYAN_dosyayi_models_agacinda_arar(tmp_path):
    """Docker imajı senaryosu: dosya modül dizininde YOK, `/models` ağacında VAR.

    ⚠️ Senaryonun ön koşulu, o yan dosyanın ağaçta GERÇEKTEN bulunmasıdır. CI'da ölçüldü:
    ağırlık ağacı klonlanmadığı için çözücü hiçbir şey bulamıyor ve kapı, çözücünün kusuru
    yokken kırmızı yanıyordu. Ön koşul yoksa ölçülecek davranış da yoktur.
    """
    from utils.model_downloader import find_installed_model, yan_dosya_coz

    hedef = "ai_hub/cat_disease/scaler_X.pkl"
    if not find_installed_model(hedef):
        pytest.skip(f"'{hedef}' bu ortamın model ağacında yok — /models senaryosu kurulamaz")

    yok = tmp_path / "scaler_X.pkl"
    cozulen = yan_dosya_coz(yok, hedef)
    assert cozulen != str(yok), "çözücü /models ağacına hiç bakmadı"
    assert Path(cozulen).exists(), f"çözülen yol yok: {cozulen}"


def test_yan_dosya_cozucusu_VAR_OLANI_oldugu_gibi_dondurur(tmp_path):
    """Klinik (frozen EXE) yolu ETKİLENMEMELİ: dosya yanındaysa kısa devre."""
    from utils.model_downloader import yan_dosya_coz

    var = tmp_path / "scaler_X.pkl"
    var.write_bytes(b"x" * 500)
    assert yan_dosya_coz(var, "ai_hub/cat_disease/scaler_X.pkl") == str(var)


def test_yan_dosya_cozucusu_HICBIR_KOSULDA_patlamaz():
    """Bulunamazsa yerel yolu döndürür; çağıran kendi hatasını üretir."""
    from utils.model_downloader import yan_dosya_coz

    assert yan_dosya_coz("/olmayan/x.pkl", "ai_hub/olmayan_modul/olmayan.pkl") == "/olmayan/x.pkl"
    assert yan_dosya_coz(None, "ai_hub/x/y.pkl") is not None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "modul,degiskenler",
    [
        ("ai_hub/cat_disease/inference_cat_disease.py", ["SCALER_PATH", "ENCODER_PATH"]),
        ("ai_hub/em_kedi/inference_em_kedi.py", ["SCALER_X_PATH", "SCALER_EXTRA_PATH", "SCALER_Y_PATH"]),
    ],
)
def test_KRITIK_yan_dosyalar_cozucuye_BAGLI(modul, degiskenler):
    """⚠️ ZAYIF-ÇIPA KORUMASI: çözücü var olabilir ama modül onu ÇAĞIRMIYORSA hiçbir şey
    değişmez. AST ile atamanın gövdesinde çağrı olduğunu doğrula."""
    agac = ast.parse((_KOK / modul).read_text(encoding="utf-8"))
    bulunan = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Assign) and len(d.targets) == 1 and isinstance(d.targets[0], ast.Name):
            if d.targets[0].id in degiskenler and "_yan(" in ast.unparse(d.value):
                bulunan.add(d.targets[0].id)
    eksik = set(degiskenler) - bulunan
    assert not eksik, f"{modul}: bu yan dosyalar çözücüye bağlanmamış → Docker imajında bulunamaz: {eksik}"


def test_KRITIK_kidney_disease_MODELS_agacina_bakiyor():
    """Bu modülde ONNX dahil HİÇBİR dosya için fallback yoktu (kardeşlerinden de kötü)."""
    kaynak = (_KOK / "ai_hub" / "inference_human_kidney_disease" / "inference_human_kidney_disease.py").read_text(
        encoding="utf-8"
    )
    i = kaynak.find("def load_model")
    assert i != -1
    govde = kaynak[i : i + 2500]
    assert "yan_dosya_coz" in govde, "load_model /models ağacına bakmıyor → Docker profilinde uç ölü"
