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


def test_KRITIK_pipeline_patlarsa_SIFIR_doner_ve_ozne_yok(sag, monkeypatch):
    """Beklenmeyen istisna döngüyü öldürmemeli; hedef yok sayılır (bobin sürülmez).

    ⚠️ `monkeypatch` ŞART: doğrudan `_SahtePipeline.process_image = ...` + `del` yapmak sınıfın
    GERÇEK metodunu kalıcı silip SONRAKİ testleri bozuyordu (ölçüldü)."""
    hedef, fantom, petri, pred, izler = sag

    def _patla(*a, **k):
        raise RuntimeError("beklenmeyen")

    izler["sonuclar"] = []
    monkeypatch.setattr(_SahtePipeline, "process_image", _patla)
    sonuc = fantom.localize("kare", 0)

    assert sonuc[0] is False and sonuc[6] is False
    assert fantom.son_lokalizasyon_meta().get("hata") == "pipeline"


# ── Faz 2b: sağlayıcı meta'sının TEL SÖZLEŞMESİNE akması ──────────────────────────────────


def test_KRITIK_saglayici_metasi_STATUS_ucuna_akar(monkeypatch):
    """Kare üstünde hedef seçimi, kalibrasyon rozeti ve onay uyarıları BU alanlardan beslenir.
    MUTASYON: cache.update'ten `**_saglayici_cache_alanlari()` satırını silin → KIRMIZI."""
    from fastapi.testclient import TestClient

    import servers.ai_router as air
    import servers.api_server as apis

    snap = dict(air._ai_organ_cache)
    try:
        with air._ai_cache_lock:
            air._ai_organ_cache.update(
                {
                    "targets": [{"id": 3, "label": "Kuyu 3", "px": [10, 20], "secili": True}],
                    "method": "aruco_pnp",
                    "mm_per_px": 0.42,
                    "target_label": "Kuyu 3",
                    "ood": True,
                }
            )
        st = TestClient(apis.app).get("/api/ai/pro/status").json()
    finally:
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(snap)

    assert st.get("targets") and st["targets"][0]["label"] == "Kuyu 3", f"hedef adayları status'a akmıyor: {st}"
    assert st.get("method") == "aruco_pnp", "kalibrasyon yöntemi status'a akmıyor (rozet çizilemez)"
    assert st.get("mmPerPx") == 0.42 and st.get("targetLabel") == "Kuyu 3"
    assert st.get("ood") is True, "eğitim-aralığı işareti status'a akmıyor (onay uyarısı çizilemez)"


def test_KRITIK_kedi_hattinda_meta_alanlari_BOS_kalir():
    """Veteriner tel sözleşmesi değişmez: kedi sağlayıcısı kare üstü aday üretmez."""
    import servers.ai_pro_hedef as hedef

    assert hedef.saglayici_al("kedi").son_lokalizasyon_meta() == {}, (
        "kedi sağlayıcısı meta üretiyor — veteriner panelinde beklenmeyen hedef adayları görünür"
    )


def test_YAPISAL_petri_dedektoru_SystemExit_FIRLATMAZ():
    """SystemExit BaseException'dır ve `except Exception`dan KAÇAR: AI Pro thread'inde kamerayı
    bırakan try/finally atlanır, `_ai_hazirlik_active` True kalır ve sonraki seans kamerayı
    açamaz. MUTASYON: RuntimeError'ı SystemExit'e döndürün → KIRMIZI."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    src = (kok / "ai_hub" / "inference_petri_dish" / "petri_cv" / "petri_detector.py").read_text(encoding="utf-8")
    assert "raise SystemExit(" not in src, (
        "petri dedektörü SystemExit fırlatıyor — hazırlık/seans thread'inde kamera sızdırır"
    )
    assert "raise RuntimeError(" in src, "ultralytics eksikliği artık hiç bildirilmiyor?"


def test_YAPISAL_EM_scaler_yollari_MODEL_DIZINININ_disinda_da_aranir():
    """Docker imajında ai_hub'ın küçük .pkl dosyaları elenir; ONNX ProgramData'dan çözülürken
    scaler'lar modül dizininde aranıp predictor SESSİZCE ölüyordu (em_kedi'de çözülmüş desen).
    MUTASYON: `_yan(...)` çağrılarını `os.path.join(_DIR, ...)`a döndürün → KIRMIZI."""
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    for modul in ("inference_em_fantom", "inference_em_petri"):
        src = (kok / "ai_hub" / modul / f"{modul}.py").read_text(encoding="utf-8")
        assert "yan_dosya_coz" in src, f"{modul}: scaler yolu çözücüsü yok (Docker'da sessiz ölüm)"
        for sabit in ("SCALER_X_PATH", "SCALER_EXTRA_PATH", "SCALER_Y_PATH"):
            satir = [s for s in src.splitlines() if s.startswith(f"{sabit} = ")]
            assert satir and "_yan(" in satir[0], f"{modul}: {sabit} çözücüsüz ({satir})"


def test_KRITIK_meta_UC_lokalizasyon_yolunda_da_cache_e_YAZILIR(sag, monkeypatch):
    """Önceki test status→cache OKUMASINI ölçüyor; bu test cache'e YAZIMI ölçer.

    ⚠️ Neden ayrı: mutasyon (cache.update'ten `**_saglayici_cache_alanlari()` silinmesi) yalnız
    okuma testinde YEŞİL kalıyordu — "varlık değil uygulama ölç" dersi. Burada (a) yardımcının
    aktif sağlayıcının meta'sını gerçekten eşlediği, (b) ÜÇ lokalizasyon yolunun (hazırlık, seans,
    mobil kare) da bu alanları yazdığı ölçülür.
    MUTASYON: üç bloktan birindeki `**_saglayici_cache_alanlari()` satırını silin → KIRMIZI."""
    from pathlib import Path

    import servers.ai_router as air

    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(izler, _SahteSonuc(wells=[_SahteBolge((7, 7), (1.0, 2.0, 3.0), organ_id=1)]))
    monkeypatch.setitem(hedef.SAGLAYICILAR, "petri_test", petri)
    monkeypatch.setattr(air, "_ai_hedef_modeli", "petri_test")

    petri.localize("kare", 0)
    alanlar = air._saglayici_cache_alanlari()

    assert alanlar.get("targets"), f"yardımcı aktif sağlayıcının hedeflerini eşlemiyor: {alanlar}"
    assert alanlar.get("method") == "aruco_pnp", "kalibrasyon yöntemi eşlenmiyor"
    assert alanlar.get("target_label"), "seçili hedef etiketi eşlenmiyor"
    assert "ood" in alanlar and "e_cancer" in alanlar, f"onay ekranı alanları eksik: {sorted(alanlar)}"

    src = (Path(air.__file__)).read_text(encoding="utf-8")
    say = src.count("**_saglayici_cache_alanlari(),")
    assert say == 3, (
        f"lokalizasyon yollarından {say}/3'ü sağlayıcı meta'sını cache'e yazıyor — yazmayan yolda "
        "(hazırlık / seans / mobil kare) kare üstü hedef seçimi ve kalibrasyon rozeti çalışmaz"
    )


class _SahteKare:
    """`.shape` taşıyan asgari kare (gerçek karenin yerine); numpy gerektirmez."""

    def __init__(self, h: int, w: int):
        self.shape = (h, w, 3)


def test_KRITIK_hedefler_KARE_ORANLI_pxn_tasir(sag):
    """Panel halkaları hedefi kare üstünde `pxn` ile yerleştirir (0..1 oranı).

    ⚠️ NEDEN ORAN: WS önizlemesi kareyi 960 px'e KÜÇÜLTÜP yayınlar ve `imageW` küçültülmüş boyutu
    taşır; ham `px` / küçültülmüş genişlik oranı işaretleri gerçek hedeften kaydırırdı ([S7 adım 6]
    overlay ölçek kaymasının aynı sınıfı).
    MUTASYON: `_hedef_tel`de `pxn`i kare boyutuna bölmeyin (ham px yazın) → KIRMIZI."""
    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(izler, _SahteSonuc(tumor=[_SahteBolge((160, 60), (-40.0, 0.0, 0.0), organ_id=1)]))

    fantom.localize(_SahteKare(240, 320), 0)
    meta = fantom.son_lokalizasyon_meta()

    assert meta.get("frame_w") == 320 and meta.get("frame_h") == 240, f"kare boyutu meta'da yok: {meta}"
    t = meta["targets"][0]
    assert t["pxn"] == pytest.approx([0.5, 0.25], abs=1e-4), f"pxn kare oranı değil: {t.get('pxn')} (px={t.get('px')})"
    assert 0.0 <= t["pxn"][0] <= 1.0 and 0.0 <= t["pxn"][1] <= 1.0, "pxn 0..1 dışına çıkmış"


def test_KARSIT_KANIT_boyutsuz_kare_lokalizasyonu_COKERTMEZ(sag):
    """`pxn` yalnız SUNUM alanıdır: boyutu okunamayan girdide hedef bulma çalışmaya devam eder
    (panel halkaları çizilmez, erişilebilir liste yedeği yine hedefleri gösterir)."""
    hedef, fantom, petri, pred, izler = sag
    _sonuc_kuyruguna(izler, _SahteSonuc(tumor=[_SahteBolge((10, 10), (-40.0, 0.0, 0.0), organ_id=1)]))

    lokalize = fantom.localize("boyutsuz-kare", 0)

    assert lokalize[0] is True, "boyutsuz kare lokalizasyonu düşürdü"
    t = fantom.son_lokalizasyon_meta()["targets"][0]
    assert "pxn" not in t, f"boyut bilinmezken uydurma pxn yazılmış: {t.get('pxn')}"
