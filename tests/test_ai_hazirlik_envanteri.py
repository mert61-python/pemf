# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI HAZIRLIK KAPISI KÖR OLMAMALI — denetim 2026-08-28 #03.

Sessiz ölümleri yakalamak için eklenen `/api/ai/hazirlik` ucunun KENDİSİ aynı sınıftandı:

  (a) MODEL SÜTUNU SAHTEYDİ. 13 modülün 12'sinde model yolu `None`; `_model_hazir_mi(None)`
      tek satırda `return "gomulu",""` diyordu — hiçbir dosyaya bakmadan PASS. Ölçülen kesin
      kanıt: model dizini eksik kurulumda `/api/ai/sound/cat` + `/vision/thermal` HTTP 500
      verirken kapı 12/13 "gomulu" diyordu; eksik dizin koşan sürece kopyalanıp uçlar 200'e
      dönünce kapının çıktısı BİT DÜZEYİNDE AYNI kaldı. Sütunun bilgi içeriği sıfırdı.
  (b) XAI ZİNCİRİ GÖRÜNMÜYORDU. `pytorch_grad_cam`/`captum`/`shap`/`ttach` fonksiyon içinde
      lazy import edilir; kapı yalnız üst-seviye import deniyordu. Tüm XAI yığını bloklandığında
      kapı 13/13 `kod=ok` demeye devam etti, gerçek termal XAI aynı anda ImportError'la patladı.
      Bu boşluk BİR KEZ ISIRDI: `.npz` spec'te yoktu → EM XAI 1.9.25'ten beri üretimde sessiz
      ölüydü, kapı görmedi.
  (c) İKİ UÇ ENVANTERDE YOKTU: `/api/ai/disease` ve `/api/ai/disease/kidney`.

Destek mühendisi tam bu sınıf için eklenen uca bakıp "13/13 hazır, model=gömülü" okuyor ve
teşhisi model paketinden UZAKLAŞTIRIYORDU.

⚠️ Bu testler kapıyı GEVŞETMEK için değil SERTLEŞTİRMEK için var. Bir modül gerçekten eksikse
kırmızı olması DOĞRU davranıştır — envantere yanlış yol yazıp yeşile boyamayın.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from servers.ai_router import _AI_MODUL_ENVANTERI, _model_hazir_mi, _xai_zinciri_durumu

_KOK = Path(__file__).resolve().parents[1]

# Envanterde MUTLAKA bulunması gereken uçlar (denetim #03(c) — eklenmeden önce yoktular).
_ZORUNLU_MODULLER = {"cat_disease", "kidney_disease"}


# ── (a) Model sütunu gerçek dosyaya bakmalı ──────────────────────────────────


def test_KRITIK_envanterde_None_model_yolu_YOK():
    """`None` model yolu = kapının o modül için hiçbir şey ölçmemesi demekti."""
    bos = [ad for ad, _imp, model in _AI_MODUL_ENVANTERI if not model]
    assert not bos, (
        f"Bu modüllerin model yolu tanımsız → kapı onlar için KÖR: {bos}. "
        f"Gerçek ağırlık yolunu yazın (make_model_zip.py::PROFILLER / make_base_zip.py::CORE_MODELS)."
    )


def test_KRITIK_None_yolu_artik_PASS_saymiyor():
    """Eski davranışın tam tersi kilitlenir: None → 'gomulu' (PASS) DEĞİL, hata."""
    durum, sebep = _model_hazir_mi(None)
    assert durum != "gomulu", "None model yolu hâlâ 'gomulu' (PASS) sayılıyor — bulgunun kendisi"
    assert durum == "envanter_eksik", f"beklenen 'envanter_eksik', gelen: {durum}"
    assert sebep, "sebep boş — destek mühendisi ne yapacağını anlayamaz"


def test_KRITIK_olmayan_model_dosyasi_YAKALANIR():
    """Kapı gerçekten dosyaya bakıyor mu: var olmayan ağırlık kırmızı olmalı."""
    durum, sebep = _model_hazir_mi("ai_hub/kesinlikle_olmayan_modul/olmayan_model.onnx")
    assert durum == "model_yok", (
        f"var olmayan ağırlık için '{durum}' döndü — kapı dosyaya BAKMIYOR (bulgunun ta kendisi)"
    )
    assert "bulunamadı" in sebep or "kök" in sebep, f"sebep açıklayıcı değil: {sebep}"


def test_KRITIK_gomulu_durumu_HAZIR_saymaz(monkeypatch):
    """Savunma derinliği: ileride bir dal yine "gomulu" döndürürse PASS OLMAMALI.

    "gomulu" dosyaya bakmadan verilen bir geçiş notuydu; bugün hiçbir kod yolu onu üretmiyor
    ama kriter onu kabul etmeye devam ederse bulgu tek satırla geri gelebilir. Burada durum
    ZORLA "gomulu" yapılır ve ucun onu HAZIR saymadığı ölçülür.
    """
    from fastapi.testclient import TestClient

    from servers import ai_router, api_server

    monkeypatch.setattr(ai_router, "_model_hazir_mi", lambda _yol: ("gomulu", ""))
    c = TestClient(api_server.app, client=("127.0.0.1", 51241))
    d = c.get("/api/ai/hazirlik").json()

    assert d["hazir"] == 0, (
        f"model durumu 'gomulu' iken {d['hazir']}/{d['toplam']} modül HAZIR sayıldı — "
        f"dosyaya bakmadan verilen geçiş notu yeniden PASS oluyor (denetim #03(a))"
    )


@pytest.mark.parametrize("ad,_imp,model", _AI_MODUL_ENVANTERI, ids=lambda x: x if isinstance(x, str) else "")
def test_envanterdeki_her_model_yolu_bu_ortamda_COZULEBILIYOR(ad, _imp, model):
    """Yollar hayali olmasın: yanlış yazılmış bir yol SAHTE kırmızı üretir ve kapı güvenilmez olur.

    (Bu test geliştirme/build makinesinde model kökleri kuruluyken anlamlıdır; ağırlıkların hiç
    kurulmadığı bir ortamda tümü atlanır.)
    """
    from utils.model_downloader import find_installed_model

    if not any(find_installed_model(m) for _a, _i, m in _AI_MODUL_ENVANTERI):
        pytest.skip("bu ortamda hiçbir model ağırlığı kurulu değil")
    assert find_installed_model(model), (
        f"'{ad}' için yazılan yol çözülemiyor: {model} — envanterdeki yol YANLIŞ olabilir "
        f"(sahte kırmızı, kapıyı güvenilmez yapar). Gerçek dosya konumunu doğrulayın."
    )


# ── (c) Kapsam: canlı uçlar envanterde ───────────────────────────────────────


@pytest.mark.parametrize("modul", sorted(_ZORUNLU_MODULLER))
def test_KRITIK_eksik_uclar_envantere_eklendi(modul):
    adlar = {ad for ad, _i, _m in _AI_MODUL_ENVANTERI}
    assert modul in adlar, f"'{modul}' envanterde yok → o uç için kapı hiçbir şey söylemiyor"


def test_envanter_kapsami_daralmadi():
    """Regresyon: envanterden modül SİLİNMESİ sessizce kapsamı düşürür."""
    assert len(_AI_MODUL_ENVANTERI) >= 15, (
        f"envanter {len(_AI_MODUL_ENVANTERI)} modüle düştü — kapsam daralması sessiz bir gerilemedir"
    )


# ── (b) XAI zinciri ──────────────────────────────────────────────────────────


def test_xai_probu_gercek_kutuphaneleri_olcuyor():
    durum = _xai_zinciri_durumu()
    for anahtar in ("grad_cam", "pytorch_grad_cam", "captum", "shap", "ttach"):
        assert anahtar in durum, f"XAI probu '{anahtar}' bileşenini hiç ölçmüyor"
    assert "em_ref_stats_eksik" in durum, "EM referans istatistikleri (.npz) ölçülmüyor"


def test_KRITIK_xai_probu_TORCH_XAI_AVAILABLE_kullanmiyor():
    """Yanlış sinyal yasağı — bu bayrak grad-cam YOKKEN de True döner (ölçüldü).

    `xai_utils/__init__` yalnız `grad_cam` MODÜLÜNÜN import edilebildiğine bakar; modül
    `pytorch_grad_cam` yokken kendi içinde `_AVAILABLE=False`'a düşüp sessizce açıklamasız
    çalışır. Kapı bu bayrağa güvenirse (b) bulgusu geri gelir.
    """
    import inspect

    from servers import ai_router

    kaynak = inspect.getsource(ai_router._xai_zinciri_durumu)
    assert "TORCH_XAI_AVAILABLE" not in kaynak.replace("`TORCH_XAI_AVAILABLE`", ""), (
        "XAI probu TORCH_XAI_AVAILABLE'a bakıyor — grad-cam yokken de True döner, yanlış sinyal"
    )
    assert "_AVAILABLE" in kaynak, "doğru sinyal (grad_cam._AVAILABLE) kullanılmıyor"


def test_KRITIK_xai_kutuphanesi_bloklanirsa_kapi_KIRMIZI_olur():
    """Kapının kırmızı OLABİLDİĞİNİN kanıtı: `shap` import'u bloklanır, prob görmeli.

    Denetimde ölçülen eski davranış: tüm XAI yığını bloklandığında kapı 13/13 `kod=ok`
    demeye devam ediyordu. Aynı senaryo artık yakalanmalı.
    """

    class _Engel:
        def find_module(self, ad, yol=None):
            return self if ad == "shap" or ad.startswith("shap.") else None

        def load_module(self, ad):
            raise ImportError("test: shap bilerek bloklandı")

        def find_spec(self, ad, yol=None, hedef=None):
            if ad == "shap" or ad.startswith("shap."):
                raise ImportError("test: shap bilerek bloklandı")
            return None

    engel = _Engel()
    yedek_shap = {k: v for k, v in sys.modules.items() if k == "shap" or k.startswith("shap.")}
    for k in yedek_shap:
        del sys.modules[k]
    sys.meta_path.insert(0, engel)
    try:
        durum = _xai_zinciri_durumu()
    finally:
        sys.meta_path.remove(engel)
        sys.modules.update(yedek_shap)

    assert durum.get("shap") == "yok", (
        f"shap bloklandığı hâlde prob '{durum.get('shap')}' dedi — XAI zinciri hâlâ görünmüyor"
    )
    # Karşı-kanıt: blokaj kalkınca yeşile dönmeli (test kalıcı hasar bırakmadı).
    assert _xai_zinciri_durumu().get("shap") == "ok", "blokaj kaldırıldıktan sonra shap hâlâ 'yok'"


# ── Tek-kaynak sapması ───────────────────────────────────────────────────────


def _sabit_oku(dosya: Path, ad: str) -> tuple[str, ...]:
    """Bir Python dosyasındaki string-tuple sabitini ÇALIŞTIRMADAN oku."""
    import ast

    agac = ast.parse(dosya.read_text(encoding="utf-8"))
    for dugum in agac.body:
        hedefler = (
            dugum.targets
            if isinstance(dugum, ast.Assign)
            else ([dugum.target] if isinstance(dugum, ast.AnnAssign) else [])
        )
        if any(isinstance(t, ast.Name) and t.id == ad for t in hedefler):
            deger = dugum.value
            if isinstance(deger, (ast.Tuple, ast.List)):
                return tuple(e.value for e in deger.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    pytest.fail(f"{dosya.name} içinde '{ad}' sabiti bulunamadı (çıpa kaymış olabilir)")


def test_envanter_yollari_model_paketi_listeleriyle_TUTARLI():
    """Envanterdeki her ağırlık, sevk edilen paketlerden birinde GERÇEKTEN olmalı.

    Envanter (frozen'da build_tools yok diye) açık yazılır; bu test tek-kaynak sapmasını
    yakalar — paket listesinden çıkarılmış bir ağırlığa kapı hâlâ bakıyorsa ya da tersi.
    """
    sys.path.insert(0, str(_KOK / "build_tools"))
    try:
        mmz = importlib.import_module("make_model_zip")
    except Exception as e:
        pytest.skip(f"make_model_zip içe aktarılamadı ({e}) — frozen/CI ortamı")

    paketli = set()
    for grup in getattr(mmz, "PROFILLER", {}).values():
        paketli.update(grup)
    for grup in getattr(mmz, "PARCALAR", {}).values():
        paketli.update(grup)

    # ⚠️ `make_base_zip` IMPORT EDİLMEZ: modül seviyesinde frozen build arayıp `sys.exit` ediyor
    # (ölçüldü — testi kendi ortam kontrolüyle düşürüyordu). Sabit AST ile okunur.
    cekirdek_onekler = _sabit_oku(_KOK / "build_tools" / "make_base_zip.py", "CORE_MODELS")
    cekirdek_onekler = tuple(p.replace("pemf_backend/_internal/ai_models/", "") for p in cekirdek_onekler)

    # ÜÇÜNCÜ kategori: EXE'ye GÖMÜLÜ küçük modeller (profil paketinde değil, çekirdekte de değil;
    # spec `datas` ile bundle'a girer — ör. kidney_rna 1,2 MB ve kidney_disease 774 KB, ikisi de
    # `PEMF_BUILD/dist/.../_internal/ai_models/` altında ölçüldü). Bunları paket listesinde
    # aramak yanlış alarmdı; tek-kaynağı `release_assets/ai_models` ağacıdır.
    gomulu_kok = _KOK / "release_assets" / "ai_models"

    disarda = [
        (ad, model)
        for ad, _i, model in _AI_MODUL_ENVANTERI
        if model not in paketli and not model.startswith(cekirdek_onekler) and not (gomulu_kok / model).exists()
    ]
    assert not disarda, (
        "Envanterdeki bu ağırlıklar ne profil paketlerinde, ne çekirdekte, ne de gömülü model "
        f"ağacında — kapı sevk EDİLMEYEN bir dosyayı arıyor olabilir (kalıcı sahte kırmızı): {disarda}"
    )
