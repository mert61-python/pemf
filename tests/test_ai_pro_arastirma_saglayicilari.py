# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FANTOM / PETRİ HEDEF SAĞLAYICILARI — Faz 2 kapıları (2026-09-09).

Bu dosya AĞIRLIK GEREKTİRMEZ: `ai_router._get_or_load_model` önbelleği sahte bir pipeline/predictor
ile doldurulur, böylece sağlayıcı MANTIĞI (hedef seçimi, güven vekili, kalibrasyon zorunluluğu,
kalıcı kimlik + takip, E anahtarı eşlemesi, eğitim-aralığı uyarısı, ipucu metinleri) CI'da da
ölçülür. Gerçek pipeline ile uçtan uca ölçüm ayrı dosyada (entegrasyon işaretli).

Kapatılan sessiz hata sınıfları:
  · **E anahtarı:** kedi modeli tek `result_E` döndürür; fantom/petri `result_E_cancer` /
    `result_E_healthy`. Kedi anahtarını okumak e_field'ı SESSİZCE 0 yapardı.
  · **Kalibrasyonsuz sürüş:** piksel/ölçek modunda koordinat kabin çerçevesinde DEĞİLDİR
    (nesne-merkezli, z=0) → yöntem tavanı eşiğin altında kalır, hedef yapısal olarak "bulunamadı".
  · **Hedef kayması:** petri kuyuları her karede yeniden sıralanır; mühürlenen "Kuyu 3" etiketi
    başka bir kuyuya kayabilirdi. Kalıcı kimlik + yarıçap sınırlı eşleme bunu engeller.
  · **Makullik reddi:** "petri değil" durumu canlı döngüde İSTİSNA değil "özne yok" olmalı.
  · **Model yeniden yükleme:** pipeline her karede kurulur; ağır modeller ENJEKTE edilmezse her
    karede 60-90 MB yeniden açılır.
"""

import pytest


# ── Sahte boru hattı iskeleti ──────────────────────────────────────────────────────────────
class _SahteBolge:
    def __init__(self, px, mm, organ_id=1, area=100, bbox=(0, 0, 20, 20), e_c=0.9, e_h=0.1):
        self.centroid_px = px
        self.centroid_cabin_mm = mm
        self.centroid_cabin_cm = tuple(v / 10.0 for v in mm)
        self.organ_id = organ_id
        self.area_px = area
        self.bbox_px = bbox
        self.E_cancer = e_c
        self.E_healthy = e_h
        # petri alanları
        self.well_id = f"W{px[0]:.0f}"
        self.reliability = 0.8
        self.conf = 0.9


class _SahteSonuc:
    def __init__(self, *, success=True, method="aruco_pnp", error="", tumor=None, wells=None, phantom=None):
        self.success = success
        self.method = method
        self.mm_per_px = 0.5
        self.error = error
        self.tumor_regions = list(tumor or [])
        self.healthy_regions = []
        self.wells = list(wells or [])
        self.phantom_detection = phantom if phantom is not None else {"primary": {"solidity": 0.9, "n_blue_inside": 12}}


class _SahtePipeline:
    """`process_image` çağrıldığında sıradaki sonucu döndürür; enjeksiyonu kaydeder."""

    izler: dict = {}

    def __init__(self, cfg, **kw):
        self.cfg = cfg
        self.kw = kw
        self._predictor = None
        self.yolo = None
        _SahtePipeline.izler.setdefault("kurulum", []).append(kw)

    def process_image(self, frame, achieved_B=None, duty_sum=None):
        _SahtePipeline.izler.setdefault("process", []).append(
            {"achieved_B": achieved_B, "duty_sum": duty_sum, "predictor": self._predictor, "yolo": self.yolo}
        )
        sonuclar = _SahtePipeline.izler.get("sonuclar") or []
        sonuc = sonuclar.pop(0) if sonuclar else _SahteSonuc()
        return sonuc, {"img_und": frame}

    def render_panels(self, ctx, result, lang="tr"):
        return {"07_combined": "overlay"}


class _SahtePredictor:
    def __init__(self):
        self.cagrilar = []

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        self.cagrilar.append({"organ_id": organ_id, "achieved_B": achieved_B, "duty_sum": duty_sum})
        out = {f"D{i}": 0.3 for i in range(1, 8)}
        out.update({f"P{i}": 12.0 for i in range(1, 8)})
        # ⚠️ `result_E` KASITEN YOK: kedi anahtarını okuyan bir sağlayıcı 0 döndürür (kapı bunu ölçer).
        out["result_E_cancer"] = 0.77
        out["result_E_healthy"] = 0.11
        out["result_E_avg"] = 0.44
        return out


class _SahteCfg:
    class phantom:  # noqa: N801  (cfg.phantom.achieved_B erişimi taklit edilir)
        achieved_B = 0.001
        duty_sum = 2.4


@pytest.fixture()
def sag(monkeypatch):
    """Fantom/petri sağlayıcılarını sahte önbellekle çalıştırır."""
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    _SahtePipeline.izler = {}
    pred = _SahtePredictor()
    cache = {
        "cls": _SahtePipeline,
        "cfg": _SahteCfg(),
        "predictor": pred,
        "yolo": "SAHTE_YOLO",
        "yolo_path": "yolo.onnx",
    }
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: cache)

    fantom = hedef.FantomSaglayici()
    petri = hedef.PetriSaglayici()
    return hedef, fantom, petri, pred, _SahtePipeline.izler


def _sonuc_kuyruguna(izler, *sonuclar):
    izler["sonuclar"] = list(sonuclar)


def test_KRITIK_E_anahtari_SINIFA_gore_eslenir(sag):
    """MUTASYON: `predict`te `result_E` (kedi anahtarı) okuyun → e_field 0 → KIRMIZI."""
    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(izler, _SahteSonuc(tumor=[_SahteBolge((10, 10), (-40.0, 0.0, 0.0), organ_id=1)]))

    fantom.localize("kare", 0)
    D, P, e = fantom.predict(-40.0, 0.0, 0.0, 0)

    assert len(D) == 7 and len(P) == 7
    assert e == pytest.approx(0.77), f"kanserli hedefte e_field {e} — sınıfa göre E eşlenmiyor"
    assert pred.cagrilar[-1]["organ_id"] == 1, "EM doku sınıfı seçili hedeften gelmiyor"
    assert pred.cagrilar[-1]["duty_sum"] == pytest.approx(2.4), "ekstra girdi kabin cfg'sinden değil"


def test_KRITIK_saglikli_hedefte_E_HEALTHY_okunur(sag):
    """Kontrol dozu (sahip kararı #2): sağlıklı kuyuda E, sağlıklı sınıfın değeri olmalı."""
    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(izler, _SahteSonuc(wells=[_SahteBolge((5, 5), (0.0, 0.0, 0.0), organ_id=0)]))

    petri.localize("kare", 0)
    _D, _P, e = petri.predict(0.0, 0.0, 0.0, 0)

    assert pred.cagrilar[-1]["organ_id"] == 0
    assert e == pytest.approx(0.11), f"sağlıklı hedefte kanser E'si kullanıldı: {e}"


def test_KRITIK_ARUCO_zorunlu_piksel_modunda_hedef_BULUNAMADI(sag):
    """Karar #4 + #7: piksel/ölçek modunda yöntem tavanı (0.25) eşiğin (0.3) ALTINDA → yapısal red.
    MUTASYON: `YONTEM_TAVANI_VARSAYILAN`ı 1.0 yapın → KIRMIZI."""
    hedef, fantom, petri, pred, izler = sag
    bolge = _SahteBolge((10, 10), (-40.0, 0.0, 0.0), organ_id=1)
    _sonuc_kuyruguna(izler, _SahteSonuc(method="pixel", tumor=[bolge]), _SahteSonuc(method="aruco_pnp", tumor=[bolge]))

    piksel = fantom.localize("kare", 0)
    aruco = fantom.localize("kare", 0)

    assert piksel[0] is False, "piksel modunda hedef 'bulundu' sayıldı — kabin çerçevesi yok, doz yanlış noktaya"
    assert aruco[0] is True, "ArUco modunda hedef bulunamadı (kapı fazla kısıtlayıcı)"
    assert hedef.YONTEM_TAVANI_VARSAYILAN < hedef.MIN_GUVEN, (
        "yöntem tavanı eşiğin ÜSTÜNDE — kalibrasyonsuz sürüş yapısal olarak engellenmiyor"
    )


def test_KRITIK_fantom_guven_vekili_MAVI_NOKTA_ister(sag):
    """Karar #7: fantom bölgesinde güven alanı yok → vekil `solidity` × mavi-nokta.
    Mavi odak yoksa güven 0 olur ve hedef sürülmez."""
    hedef, fantom, petri, pred, izler = sag
    bolge = _SahteBolge((10, 10), (-40.0, 0.0, 0.0), organ_id=1)
    _sonuc_kuyruguna(
        izler,
        _SahteSonuc(tumor=[bolge], phantom={"primary": {"solidity": 0.95, "n_blue_inside": 0}}),
        _SahteSonuc(tumor=[bolge], phantom={"primary": {"solidity": 0.95, "n_blue_inside": 7}}),
    )

    mavisiz = fantom.localize("kare", 0)
    mavili = fantom.localize("kare", 0)

    assert mavisiz[0] is False and mavisiz[4] == 0.0, "mavi tümör odağı yokken hedef sürülebilir sayıldı"
    assert mavili[0] is True and mavili[4] > hedef.MIN_GUVEN


def test_KRITIK_petri_otomatik_secim_KANSERLI_kuyu(sag):
    """Sağlıklı kuyu daha yüksek güvende olsa bile otomatik seçim KANSERLİ kuyudur (sağlıklı
    yalnız elle seçilir — kontrol dozu anahtarı)."""
    hedef, fantom, petri, pred, izler = sag
    saglikli = _SahteBolge((5, 5), (0.0, 0.0, 0.0), organ_id=0)
    saglikli.reliability = 0.99
    kanserli = _SahteBolge((80, 80), (10.0, 10.0, 0.0), organ_id=1)
    kanserli.reliability = 0.55
    _sonuc_kuyruguna(izler, _SahteSonuc(wells=[saglikli, kanserli]))

    petri.localize("kare", 0)
    meta = petri.son_lokalizasyon_meta()

    assert meta["secili_organ_id"] == 1, f"otomatik seçim sağlıklı kuyuya gitti: {meta}"


def test_KRITIK_kalici_kimlik_SIRA_degisince_korunur(sag):
    """Petri kuyuları her karede yeniden sıralanır; mühürlenen etiket kaymamalı.
    MUTASYON: `_kimlik_ata`yı sıralı numaralamaya indirin → KIRMIZI."""
    hedef, fantom, petri, pred, izler = sag
    a = _SahteBolge((100, 100), (10.0, 0.0, 0.0), organ_id=1, bbox=(90, 90, 20, 20))
    b = _SahteBolge((300, 100), (30.0, 0.0, 0.0), organ_id=1, bbox=(290, 90, 20, 20))
    # İkinci karede LİSTE SIRASI ters (pipeline sıralaması kararsız), konumlar aynı.
    _sonuc_kuyruguna(izler, _SahteSonuc(wells=[a, b]), _SahteSonuc(wells=[b, a]))

    petri.localize("kare", 0)
    ilk = {t["label"]: (t["px"][0], t["id"]) for t in petri.son_lokalizasyon_meta()["targets"]}
    petri.localize("kare", 0)
    ikinci = {t["label"]: (t["px"][0], t["id"]) for t in petri.son_lokalizasyon_meta()["targets"]}

    assert ilk == ikinci, f"sıra değişince kimlik/etiket kaydı: {ilk} → {ikinci}"


def test_KRITIK_uzak_komsuya_KILITLENMEZ(sag):
    """Seçili hedef kaybolursa yarıçap dışındaki komşu AYNI hedef sayılmamalı; hedef "bulunamadı"
    olur ve mevcut 3-ardışık STOP mekanizması devreye girer.
    MUTASYON: `TAKIP_YARICAP_KATI`nı 100 yapın → KIRMIZI (komşuya kilitlenir)."""
    hedef, fantom, petri, pred, izler = sag
    a = _SahteBolge((100, 100), (10.0, 0.0, 0.0), organ_id=1, bbox=(90, 90, 20, 20))
    uzak = _SahteBolge((400, 400), (40.0, 40.0, 0.0), organ_id=1, bbox=(390, 390, 20, 20))
    _sonuc_kuyruguna(izler, _SahteSonuc(wells=[a]), _SahteSonuc(wells=[uzak]))

    petri.localize("kare", 0)
    secili_id = petri.son_lokalizasyon_meta()["secili_id"]
    ikinci = petri.localize("kare", secili_id)  # aynı kimliği ELLE hedefle

    assert ikinci[0] is False, "seçili hedef kaybolduğu hâlde uzak komşu AYNI hedef sayıldı"


def test_KRITIK_petri_makullik_reddi_ISTISNA_degil_ozne_yok(sag):
    """ "Petri değil" durumu canlı döngüde hazırlığı bitirmez; hedef yok sayılır ve ipucu verilir."""
    hedef, fantom, petri, pred, izler = sag
    from ai_hub.inference_petri_dish import plausibility as pl

    _sonuc_kuyruguna(izler, _SahteSonuc(success=False, error=pl.PETRI_REJECT))

    sonuc = petri.localize("kare", 0)

    assert sonuc[0] is False, "reddedilen karede hedef bulundu sayıldı"
    assert sonuc[6] is False, "makullik reddinde 'özne kadrajda' True kaldı — operatöre yanlış eylem"
    ipucu = petri.ipucu(False, "Kuyu 1")
    for yasak in ("yükle", "modül", "PEMF_AI_", "Traceback"):
        assert yasak.lower() not in ipucu.lower(), f"canlı ipucu yükleme bağlamı/teknik ayrıntı taşıyor: {ipucu!r}"
    assert "plaka" in ipucu.lower(), f"ipucu ne yapılacağını söylemiyor: {ipucu!r}"


def test_KRITIK_fantom_ozne_yok_ile_hedef_yok_AYRILIR(sag):
    """Kedi hattındaki `kedi_var` mandalının karşılığı: fantom görünmüyor mu, görünüyor ama odak mı
    yok? İki durum FARKLI eylem gerektirir."""
    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(
        izler,
        _SahteSonuc(success=False, error="phantom_not_detected"),
        _SahteSonuc(success=True, tumor=[], phantom={"primary": {"solidity": 0.9, "n_blue_inside": 3}}),
    )

    yok = fantom.localize("kare", 0)
    var_ama_odak_yok = fantom.localize("kare", 0)

    assert yok[6] is False, "fantom yok ama 'özne kadrajda' True"
    assert var_ama_odak_yok[6] is True, "fantom görülüyor ama 'özne kadrajda' False"
    assert yok[0] is False and var_ama_odak_yok[0] is False
    assert "fantom" in fantom.ipucu(False, "Tümör 1").lower()


def test_KRITIK_egitim_araligi_DISINDA_ood_isaretlenir(sag):
    """Onay ekranındaki "araştırma amaçlı" uyarısını besler; sürüşü ENGELLEMEZ. Aralık sabit
    yazılmaz, modülün referans örnekleminden okunur."""
    hedef, fantom, petri, pred, izler = sag
    ic = _SahteBolge((10, 10), (-40.0, 0.0, 0.0), organ_id=1)  # fantom aralığı x∈[-56,6; -30,6]
    dis = _SahteBolge((10, 10), (250.0, 0.0, 0.0), organ_id=1)
    _sonuc_kuyruguna(izler, _SahteSonuc(tumor=[ic]), _SahteSonuc(tumor=[dis]))

    fantom.localize("kare", 0)
    assert fantom.son_lokalizasyon_meta()["ood"] is False, "aralık içindeki konum OOD işaretlendi"
    fantom.localize("kare", 0)
    assert fantom.son_lokalizasyon_meta()["ood"] is True, "aralık dışındaki konum OOD işaretlenmedi"


def test_KRITIK_agir_modeller_ENJEKTE_edilir(sag):
    """Pipeline her karede kurulur; ağır modeller enjekte edilmezse her karede 60-90 MB yeniden
    açılır (pipeline lazy property'leri). MUTASYON: `pl._predictor = ...` satırını silin → KIRMIZI."""
    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(izler, _SahteSonuc(tumor=[_SahteBolge((10, 10), (-40.0, 0.0, 0.0))]), _SahteSonuc(wells=[]))

    fantom.localize("kare", 0)
    petri.localize("kare", 0)

    f_kayit, p_kayit = izler["process"][0], izler["process"][1]
    assert f_kayit["predictor"] is pred, "fantom pipeline'a önbellekli predictor enjekte edilmedi"
    assert p_kayit["predictor"] is pred, "petri pipeline'a önbellekli predictor enjekte edilmedi"
    assert p_kayit["yolo"] == "SAHTE_YOLO", "petri pipeline'a önbellekli YOLO enjekte edilmedi"
    assert izler["kurulum"][0].get("manual_fallback") is False, (
        "fantom pipeline manual_fallback=True kuruldu — headless serviste cv2 penceresi açıp döngüyü dondurur"
    )
    assert izler["kurulum"][1].get("yolo_device") == "cpu", "petri pipeline CPU'ya sabitlenmedi (CUDA yok)"


def test_KRITIK_pipeline_patlarsa_SIFIR_doner_ve_ozne_yok(sag):
    """Beklenmeyen istisna döngüyü öldürmemeli; hedef yok sayılır (bobin sürülmez)."""
    hedef, fantom, petri, pred, izler = sag

    def _patla(*a, **k):
        raise RuntimeError("beklenmeyen")

    izler["sonuclar"] = []
    _SahtePipeline.process_image = _patla
    try:
        sonuc = fantom.localize("kare", 0)
    finally:
        del _SahtePipeline.process_image

    assert sonuc[0] is False and sonuc[6] is False
    assert fantom.son_lokalizasyon_meta().get("hata") == "pipeline"
