# -*- coding: utf-8 -*-
# Author: mertaygn
"""Petri Kuyu Analizi — ARAYÜZDEN ayarlanabilir 6 parametre + küçültme + denetim anahtarı.

SAHİP TALEBİ (2026-09-09): "3 parametre arayüzden ayarlanabilir olsun. Görüntünün çözünürlüğü
fazla, yoloya göre resize ekle." → netleştirme: "Altısı da ayarlanabilir olsun."

NE ÖLÇÜLÜYOR (varlık değil UYGULAMA): bu dosya "alan tanımlı mı" diye bakmaz — parametrenin
zincirin HER halkasında TAŞINDIĞINI ölçer. Bugün aynı sınıf hatayı iki kez gördük:
  · `scratch_yonu` arayüzde seçiliyor, `predict()`e geçiyor ama `compute_closure_metrics`e
    GEÇMİYORDU → kullanıcı dikey seçiyor, çizgiler yatay çiziliyordu (sessiz).
  · Modalite kapısı gömülü yolda vardı, mikroservis yolunda YOKTU → aynı fotoğraf iki
    profilde farklı davranıyordu (tests/test_ai_mikroservis_modalite_kapisi.py).
Bu yüzden kapılar: (a) uç → boru hattı kwargs'ı, (b) uç → mikroservis form alanları,
(c) iki ucun AST paritesi, (d) sınırların gerçekten zorlandığı 422, (e) eşik varsayılanlarının
tek kaynağı. Hepsi ters-mutasyonla KIRMIZI olduğu görülerek yazıldı.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

from ai_hub.inference_petri_dish import petri_ayar as pa
from ai_hub.inference_petri_dish import plausibility as plaus

KOK = Path(__file__).resolve().parents[1]
PETRI = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri" / "06_PetriKuyu.jpg"

pytestmark = pytest.mark.skipif(not PETRI.exists(), reason="petri test girdisi yok")


# == 1) SAF ÇÖZÜM KATMANI ===================================================================
def test_KRITIK_bos_istek_HICBIR_kwarg_uretmez():
    """Hiçbir parametre gönderilmezse boru hattı kwargs'ı BOŞ olmalı.

    ⚠️ Bu, "arayüz ayarı ekledik, sessizce hepsini kendi varsayılanımıza çektik" regresyonunu
    yapısal olarak imkânsız kılar: boş sözlük = `PetriCvPipeline` kendi imzasındaki
    varsayılanlarda kalır = bugünkü davranış BİT-BİT aynı. `coz()` None'ları kwarg olarak
    koyarsa (ör. `resize_max=None` yerine `resize_max=0`) bu test KIRMIZI olur.
    """
    assert pa.coz() == {}, "bos istek varsayilanlari EZIYOR"


@pytest.mark.parametrize(
    "ad,kotu",
    [
        ("yolo_conf", 0.0),
        ("yolo_conf", 1.0),
        ("yolo_iou", 0.05),
        ("yolo_iou", 1.5),
        ("resize_max", 1),
        ("resize_max", 99999),
        ("plaus_circularity", 1.4),
        ("plaus_circularity", -0.1),
        ("plaus_conf", 2.0),
        ("plaus_area_frac", 0.0),
        ("plaus_area_frac", 1.7),
    ],
)
def test_KRITIK_aralik_disi_deger_REDDEDILIR(ad, kotu):
    """Sınırlar süsleme değil: uç auth-muaf, curl ile doğrudan çağrılabilir.

    `resize_max=1` bütün plakayı tek piksele indirir; `yolo_conf=0` on binlerce sahte tespit
    üretip belleği doldurur. Arayüz doğrulaması atlanabildiği için sınır UÇTA zorlanmalı.
    """
    with pytest.raises(pa.AyarHatasi):
        pa.coz(**{ad: kotu})


def test_resize_max_SIFIR_kucultme_KAPALI_demek():
    """Arayüzdeki "kapalı" seçeneği 0 gönderir; bu bir sınır ihlali DEĞİL, kapatmadır."""
    assert pa.coz(resize_max=0) == {}
    assert pa.coz(resize_max="") == {}


def test_KRITIK_esik_varsayilanlari_TEK_KAYNAK_plausibility(monkeypatch):
    """Makullik varsayılanları `petri_ayar`da TEKRAR YAZILMAMALI.

    ⚠️ `plausibility.py` eşiği değiştirirse (sahip bir kez 0.55'i ölçerek seçti) arayüzün
    "varsayılana dön" değeri birlikte değişmeli; kopyalanırsa arayüz eski sayıyı gösterir ve
    kullanıcı yanlış referansa göre ayar yapar.

    ⚠️ Eşitlik karşılaştırması TEK BAŞINA YETMEZ: `petri_ayar`a aynı sayıları elle yazan bir
    kopya da geçerdi. Bu yüzden kaynak sözlük DEĞİŞTİRİLİR ve `varsayilanlar()`ın TAKİP
    ETTİĞİ ölçülür — kopya bu mutasyonda kırmızı olur.
    """
    v = pa.varsayilanlar()
    assert v["plaus_circularity"] == plaus.ESIK_VARSAYILAN["circularity_med"]
    assert v["plaus_conf"] == plaus.ESIK_VARSAYILAN["conf_med"]
    assert v["plaus_area_frac"] == plaus.ESIK_VARSAYILAN["max_area_frac"]

    monkeypatch.setitem(plaus.ESIK_VARSAYILAN, "conf_med", 0.61)
    assert pa.varsayilanlar()["plaus_conf"] == 0.61, "varsayilan KOPYALANMIS (plausibility'yi izlemiyor)"


def test_esikler_plausibility_ANAHTARLARINA_cevrilir():
    """Telde `plaus_conf`, ölçüm modülünde `conf_med` — çevrim yapılmazsa eşik SESSİZCE düşer
    (`esikleri_coz` bilinmeyen anahtarı yok sayar → override hiç uygulanmaz)."""
    kw = pa.coz(plaus_conf=0.4, plaus_circularity=0.3, plaus_area_frac=0.9)
    assert kw["plaus_esikler"] == {"conf_med": 0.4, "circularity_med": 0.3, "max_area_frac": 0.9}
    assert set(kw["plaus_esikler"]) <= set(plaus.ESIK_VARSAYILAN), "anahtar plausibility'de YOK -> override OLU"


def test_KRITIK_RET_MESAJI_ETKIN_esikleri_soyler():
    """Ret mesajındaki "beklenen ≥" sayıları ETKİN eşikten gelmeli, modül sabitinden DEĞİL.

    ⚠️ Sabitten okunursa: kullanıcı güveni 0,85 → 0,40'a düşürür, görüntü yine reddedilir ve
    mesaj "beklenen ≥0.85" der. Kullanıcı ayarının hiç uygulanmadığını sanar — ikna edici ama
    yanlış bir yönlendirme (`hata-mesaji-eylem-soylesin` dersi).
    """
    m = plaus.analyze([], [], 1000.0, {"conf_med": 0.40})
    mesaj = plaus.user_message(m)
    assert "≥0.40" in mesaj, mesaj
    assert "≥0.85" not in mesaj, "ret mesaji SABIT esigi soyluyor (etkin esik degil)"


# == 2) UÇ -> BORU HATTI (asıl kapı) ========================================================
@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51239))


class _SahteSonuc:
    """`PipelineResult` yerine geçen asgari nesne (gerçek ONNX yüklenmez)."""

    def __init__(self):
        self.success = False
        self.error = None
        self.n_wells = 0
        self.n_cancer = 0
        self.n_healthy = 0
        self.method = ""
        self.mm_per_px = 0.0
        self.wells = []
        self.timing_ms = {}
        self.plausibility = {"thresholds": {"conf_med": 0.42}, "votes": 2}
        self.yolo_ayar = {"conf": 0.33, "iou": 0.44, "imgsz": 640}
        self.resize = {"from": [1200, 1600], "to": [720, 960], "max": 960}


@pytest.fixture()
def yakala(monkeypatch):
    """Boru hattı sınıfını casusla: uç HANGİ kwargs'la kurdu?"""
    from servers import ai_router

    kayit: dict = {}

    class _SahtePipeline:
        def __init__(self, cfg, **kw):
            kayit.update(kw)

        def process_image(self, img, **kw):
            return _SahteSonuc(), {}

    monkeypatch.setattr(
        ai_router,
        "_get_or_load_model",
        lambda key, loader: {
            "cls": _SahtePipeline,
            "cfg": object(),
            "yolo_path": "x.onnx",
            "yolo": object(),
            "predictor": object(),
        },
    )
    return kayit


def _gonder(client, **form):
    with open(PETRI, "rb") as f:
        return client.post(
            "/api/ai/vision/em_petri",
            files={"file": ("06_PetriKuyu.jpg", f.read(), "image/jpeg")},
            data={k: str(v) for k, v in form.items()},
        )


def test_KRITIK_UC_alti_parametreyi_BORU_HATTINA_gecirir(client, yakala):
    """Uç formdan okuduğu ayarları `PetriCvPipeline(...)`a GEÇİRMELİ.

    ⚠️ Bu testin var olma sebebi: `**_ayar` satırı silinse ya da `coz()` sonucu kullanılmasa
    uç 200 dönmeye DEVAM eder — kullanıcı eşiği değiştirir, sonuç değişmez, hata görünmez.
    """
    r = _gonder(
        client,
        yolo_conf=0.05,
        yolo_iou=0.5,
        resize_max=960,
        plaus_circularity=0.30,
        plaus_conf=0.40,
        plaus_area_frac=0.90,
        plaus_guard="false",
    )
    assert r.status_code == 200, r.text
    assert yakala.get("yolo_conf") == pytest.approx(0.05)
    assert yakala.get("yolo_iou") == pytest.approx(0.5)
    assert yakala.get("resize_max") == 960
    assert yakala.get("plaus_esikler") == {
        "circularity_med": pytest.approx(0.30),
        "conf_med": pytest.approx(0.40),
        "max_area_frac": pytest.approx(0.90),
    }
    assert yakala.get("plaus_guard") is False


def test_KRITIK_parametresiz_istek_BORU_HATTI_VARSAYILANINDA_birakir(client, yakala):
    """KARŞIT KANIT: parametre yoksa hiçbir ayar kwarg'ı geçmemeli (eski davranış korunur)."""
    r = _gonder(client)
    assert r.status_code == 200, r.text
    for ad in ("yolo_conf", "yolo_iou", "resize_max", "plaus_esikler", "plaus_guard"):
        assert ad not in yakala, f"{ad} istenmeden geciriliyor -> varsayilan EZILIYOR"


def test_KRITIK_UC_aralik_disini_422_ile_REDDEDER(client, yakala):
    """Sınır ihlali 500 değil 422 + NE yapılacağını söyleyen Türkçe metin olmalı."""
    r = _gonder(client, resize_max=1)
    assert r.status_code == 422, r.text
    detay = r.json().get("detail", "")
    assert "resize_max" in detay and "320" in detay, detay
    assert not yakala, "aralik disi istek boru hattini KURDU (dogrulama tespitten SONRA)"


def test_YANIT_ETKIN_ayarlari_tasir(client, yakala):
    """Sonuç hangi eşiklerle üretildi? Gevşetilmiş bir koşu arayüzde "normal" görünmemeli."""
    r = _gonder(client, plaus_conf=0.42)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["yolo_ayar"]["conf"] == pytest.approx(0.33)
    assert g["resize"]["max"] == 960
    assert g["plausibility"]["thresholds"]["conf_med"] == pytest.approx(0.42)


# == 3) MİKROSERVİS DALI (GPU dağıtımında ölü kalmasın) =====================================
def test_KRITIK_MIKROSERVIS_dali_TUM_ayarlari_TASIR(client, monkeypatch):
    """`PEMF_AI_SERVICE_URL` tanımlıyken gömülü yol HİÇ çalışmaz.

    Ayarlar `data={...}` içinde taşınmazsa GPU profilinde arayüzdeki her ayar SESSİZCE ölür
    (FastAPI tanımadığı form alanını atar, istemci hata görmez).
    """
    from servers import ai_router

    kayit: dict = {}

    async def _sahte_devret(name, **kw):
        kayit["name"] = name
        kayit["data"] = dict(kw.get("data") or {})
        return {"status": "success", "success": True, "n_wells": 3, "error": None}

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "_kapili_devret", _sahte_devret)

    r = _gonder(client, yolo_conf=0.05, resize_max=960, plaus_conf=0.4, plaus_guard="false")
    assert r.status_code == 200, r.text
    assert kayit["name"] == "em_petri"
    for ad in pa.SINIRLAR:
        assert ad in kayit["data"], f"{ad} mikroservise TASINMIYOR -> GPU profilinde OLU ayar"
    assert "plaus_guard" in kayit["data"], "denetim anahtari mikroservise TASINMIYOR"
    assert kayit["data"]["yolo_conf"] == pytest.approx(0.05)
    assert kayit["data"]["plaus_guard"] is False


def test_KRITIK_MIKROSERVIS_dali_ARALIK_DISINI_devretmeden_REDDEDER(client, monkeypatch):
    """Doğrulama devretmeden ÖNCE olmalı; yoksa absürt değer GPU servisine gider."""
    from servers import ai_router

    cagrildi = []

    async def _sahte_devret(name, **kw):
        cagrildi.append(name)
        return {"status": "success"}

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(ai_router, "_kapili_devret", _sahte_devret)

    r = _gonder(client, yolo_conf=0.0)
    assert r.status_code == 422, r.text
    assert not cagrildi, "aralik disi deger mikroservise DEVREDILDI"


# == 4) İKİ UCUN AST PARİTESİ (kopyalanma/sürüklenme yasağı) ================================
def _fonksiyon(yol: Path, ad: str):
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad:
            return d
    raise AssertionError(f"{ad} bulunamadi: {yol}")


UCLAR = [
    (KOK / "servers" / "ai_router.py", "analyze_em_petri"),
    (KOK / "ai_service" / "app.py", "infer_em_petri"),
]


@pytest.mark.parametrize("yol,ad", UCLAR, ids=["gomulu", "mikroservis"])
def test_KRITIK_HER_IKI_UC_ayni_form_alanlarini_TANIR(yol, ad):
    """Alan adı üç katmanda TEK: `petri_ayar.SINIRLAR` anahtarları = iki ucun Form alanları
    = arayüzün gönderdiği isimler. Bir uçta eksikse o profilde ayar ölür."""
    fn = _fonksiyon(yol, ad)
    argumanlar = {a.arg for a in list(fn.args.args) + list(fn.args.kwonlyargs)}
    eksik = [k for k in pa.SINIRLAR if k not in argumanlar]
    assert not eksik, f"{yol.name}::{ad} bu Form alanlarini TANIMIYOR: {eksik}"
    assert "plaus_guard" in argumanlar, f"{yol.name}::{ad} denetim anahtarini TANIMIYOR"


@pytest.mark.parametrize("yol,ad", UCLAR, ids=["gomulu", "mikroservis"])
def test_KRITIK_HER_IKI_UC_petri_ayar_COZ_CAGIRIR(yol, ad):
    """⚠️ AST TABANLI: ham metin araması docstring'e petri_ayar.coz(...) yazan bir
    değişiklikte YEŞİL kalırdı (`ast` docstring'i çağrı düğümü olarak görmez)."""
    fn = _fonksiyon(yol, ad)
    coz_cagrisi = [
        d
        for d in ast.walk(fn)
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "coz"
    ]
    assert coz_cagrisi, f"{yol.name}::{ad} petri_ayar.coz() CAGIRMIYOR -> sinir/cevrim TEK KAYNAK degil"
    gecirilen = {k.arg for c in coz_cagrisi for k in c.keywords}
    eksik = [k for k in pa.SINIRLAR if k not in gecirilen]
    assert not eksik, f"{yol.name}::{ad} bu alanlari coz()a GECIRMIYOR: {eksik}"


@pytest.mark.parametrize("yol,ad", UCLAR, ids=["gomulu", "mikroservis"])
def test_KRITIK_HER_IKI_UC_SINIRLARI_KOPYALAMAMIS(yol, ad):
    """Sınır sayıları uç dosyalarında TEKRAR YAZILMAMALI (sürüklenirse iki profil ayrışır).

    Sayıları aramak kırılgan olurdu (0.25 başka anlamda da geçer); yerine ölçüt şu: uç,
    sınır sözlüğünün KENDİSİNİ tanımlamamalı.
    """
    kaynak = yol.read_text(encoding="utf-8")
    for yasak in ("SINIRLAR =", "SINIRLAR:", "_PETRI_PARAM_SINIR"):
        assert yasak not in kaynak, f"{yol.name} sinir sozlugunu KOPYALAMIS ({yasak})"


# == 5) ARAYÜZ TEL SÖZLEŞMESİ (TS Python'u import edemez → kopya KİLİTLENİR) ================
_TSX = KOK / "pf" / "src" / "screens" / "AiHubScreen.tsx"
_TSX_ALAN = re.compile(
    r"ad:\s*\"(?P<ad>\w+)\"[^}]*?vars:\s*\"(?P<vars>[^\"]+)\"[^}]*?"
    r"alt:\s*(?P<alt>-?[\d.]+),\s*ust:\s*(?P<ust>-?[\d.]+)",
    re.DOTALL,
)

tsx_yok = pytest.mark.skipif(not _TSX.exists(), reason="pf/ kaynak agaci yok (yalniz backend paketi)")


def _tsx_tablosu() -> dict:
    kaynak = _TSX.read_text(encoding="utf-8")
    i = kaynak.find("const PETRI_AYAR_ALANLARI")
    assert i >= 0, "PETRI_AYAR_ALANLARI tablosu AiHubScreen.tsx'te YOK"
    j = kaynak.index("];", i)
    return {
        m.group("ad"): (m.group("vars"), float(m.group("alt")), float(m.group("ust")))
        for m in _TSX_ALAN.finditer(kaynak[i:j])
    }


@tsx_yok
def test_KRITIK_ARAYUZ_sinir_tablosu_BACKEND_ILE_AYNI():
    """Arayüzdeki (alt, üst) kopyası `petri_ayar.SINIRLAR` ile BİREBİR eşleşmeli.

    ⚠️ Kopya bilinçli: TypeScript Python sözlüğünü import edemez (`_PETRI_NOT_PLATE` ile aynı
    desen). Kopyanın bedeli sürüklenme riskidir; bu test o riski kapatır. Ayrışırsa kullanıcı
    arayüzde kabul edilen bir sayı girer, sunucu 422 ile reddeder — sebebi görünmez bir hata.
    """
    tsx = _tsx_tablosu()
    assert set(tsx) == set(pa.SINIRLAR), f"alan kumesi AYRISMIS: arayuz={sorted(tsx)} backend={sorted(pa.SINIRLAR)}"
    for ad, (_v, alt, ust) in tsx.items():
        assert (alt, ust) == pytest.approx(pa.SINIRLAR[ad]), f"{ad}: arayuz ({alt},{ust}) != backend {pa.SINIRLAR[ad]}"


@tsx_yok
def test_KRITIK_ARAYUZ_gosterilen_VARSAYILANLAR_dogru():
    """Alanın "varsayılan X" ipucu gerçek varsayılanı göstermeli.

    ⚠️ Kullanıcı ayarı bu sayıya GÖRE değiştiriyor: 0,85 yerine 0,25 yazan bir ipucu, eşiği
    gevşettiğini sanan bir araştırmacıyı sıkılaştırmaya götürür (sessiz yanlış yön).
    `resize_max` istisnadır: varsayılanı "kapalı"dır (0 = küçültme yok).
    """
    tsx = _tsx_tablosu()
    beklenen = pa.varsayilanlar()
    for ad, (gosterilen, _alt, _ust) in tsx.items():
        if ad == "resize_max":
            assert gosterilen == "kapalı", f"resize_max varsayilani 'kapali' olmali: {gosterilen}"
            continue
        assert float(gosterilen.replace(",", ".")) == pytest.approx(beklenen[ad]), (
            f"{ad}: arayuz '{gosterilen}' gosteriyor, gercek varsayilan {beklenen[ad]}"
        )


@tsx_yok
def test_KRITIK_ARAYUZ_alanlari_ISTEGE_EKLIYOR():
    """Tablo dolu olup `formData`ya eklenmezse ayarlar hiç gönderilmez (sessiz ölü arayüz)."""
    kaynak = _TSX.read_text(encoding="utf-8")
    assert 'formData.append(a.ad, String(d))' in kaynak, "gelismis ayarlar formData'ya EKLENMIYOR"
    assert 'formData.append("plaus_guard", "false")' in kaynak, "denetim anahtari GONDERILMIYOR"
    # Denetim AÇIKken gönderilmemeli: yoksa sunucudaki PEMF_AI_PLAUSIBILITY_GUARD kaçış
    # kapağı arayüz tarafından sessizce EZİLİR.
    assert 'formData.append("plaus_guard", "true")' not in kaynak, (
        "denetim ACIKken de gonderiliyor -> PEMF_AI_PLAUSIBILITY_GUARD kacis kapagi EZILIR"
    )
