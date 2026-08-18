# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
""":8100'e DOĞRUDAN yapılan çağrılar MODALİTE/SESSİZLİK KAPISIZDI.

DENETİM BULGUSU (2026-08-17, fix-12'den sarkan kalem). Görüntü uçlarındaki kapı `servers/ai_router.py`
içinde `_kapili_devret` ile devretmenin önüne alındı — ama bu yalnız **backend üzerinden** geçen
istekleri korur. `ai_service/app.py` (`:8100`) kendi başına kapısızdı ve uçları **auth-muaf**:

    POST :8100/infer/histopath  +  07a_BobrekCT_tas.jpg (CT kesiti)
      → HTTP 200 {"top_1_class": "Grade 4", "top_1_prob": 1.0}      ← ÖLÇÜLDÜ

Yani kapının var olma sebebi olan 2026-08-06 saha vakası (CT kesitine "Grade 4 · %100") bu
transportta birebir duruyordu. Aynısı ses ucunda: sessiz kayıt için model yine "duygu" döndürüyordu.

⚠️ Deponun KENDİ kuralı bunu yazıyor (`ai_hub/inference_petri_dish/plausibility.py`):
*"denetim ROUTER'da DEĞİL burada durmalı, çünkü `PEMF_AI_SERVICE_URL` tanımlıyken
`servers/ai_router.py` HİÇ çalışmaz."* Petri kapısı boru hattının İÇİNDE olduğu için iki yolda da
çalışıyordu; kurala uyan tek kapı oydu.

DÜZELTME = kapıyı KOPYALAMAK DEĞİL, aynı modülü iki transporttan çağırmak. `utils/image_domain` ve
`utils/ses_kalitesi` yaprak modüller (depo-içi bağımlılığı SIFIR, yalnız cv2/numpy/stdlib) ve
`docker/Dockerfile.ai` imaja bir `COPY` satırıyla alınıyor. Kapıları `ai_hub/`e TAŞIMAK bilerek
REDDEDİLDİ: `pyproject.toml` coverage `omit */ai_hub/*` + mypy `exclude (ai_hub|...)` yüzünden iki
güvenlik kapısı kalıcı kör noktaya girerdi (2026-08-09 ratchet kararının tersi).
"""

import ast
import base64
import io
import os
import wave
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest

KOK = Path(__file__).resolve().parent.parent
FIXTURE = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri"
CT = FIXTURE / "07a_BobrekCT_tas.jpg"
PATOLOJI = FIXTURE / "08c_BobrekPatoloji_grade4.jpg"
SES = FIXTURE / "10a_KediSesi_mutlu.mp3"


@pytest.fixture(scope="module")
def app_modulu():
    # ⚠️ CI'DA HATA VERDİ (2026-08-18): `ai_service/app.py` modül düzeyinde `onnxruntime` import
    # ediyor; GitHub runner'ında o paket YOK → fixture `ModuleNotFoundError` ile ERROR veriyordu.
    # Bu dosyadaki eski testler yalnız fixture dosyaları yoksa atladıkları için hatayı görmüyordu.
    # `importorskip` DAR tutulur: yalnız eksik ÇALIŞMA ZAMANI paketinde atlanır; `ai_service`in
    # kendi kodundaki bir bozulma yine HATA verir (aksi halde kapı sessizce atlanırdı).
    pytest.importorskip("onnxruntime", reason="ai_service :8100 calisma zamani paketi yok (CI)")
    from ai_service import app as _app

    return _app


@pytest.fixture()
def client(app_modulu, monkeypatch):
    """`:8100` uygulamasının gerçek TestClient'ı; predictor'lar SAHTE (GPU/model gerekmez).

    ⚠️ `PEMF_AI_DOMAIN_GUARD` ortamdan SİLİNİR: sızmış bir `0` değeri kapıyı kapatır ve test
    sessizce yanlış-yeşile döner (`utils/image_domain.py` bu env'i ÇAĞRI ANINDA okuyor)."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)

    class _SahteModel:
        device = "sahte"

        def predict(self, *a, **k):
            return {
                "top_1_class": "Grade 4",
                "top_1_prob": 1.0,
                "top_k": [("Grade 4", 1.0)],
                "probabilities": {"Grade 4": 1.0, "Grade 1": 0.0},
            }

        def draw_overlay(self, *a, **k):
            # ⚠️ `None` DÖNDÜRME: uç bunu `_jpg_b64`e veriyor ve cv2.imencode boş görüntüde
            # assertion ile patlıyor → uç 500 döner ve test kapıyı ölçmek yerine kurguya takılır.
            import numpy as _np

            return _np.zeros((8, 8, 3), dtype=_np.uint8)

    monkeypatch.setattr(app_modulu.predictors, "get", lambda ad: _SahteModel())
    return TestClient(app_modulu.app)


def _gonder(client, uc: str, p: Path, mime: str = "image/jpeg"):
    with p.open("rb") as f:
        return client.post(uc, files={"file": (p.name, f, mime)})


# ── 1) Modalite kapısı :8100'de de çalışmalı ──────────────────────────────────


@pytest.mark.skipif(not CT.exists(), reason="CT fixture yok")
def test_KRITIK_8100_histopath_CT_REDDEDILIR(client):
    """CT kesiti → /infer/histopath: 422 ile reddedilmeli (bugün 200 "Grade 4 %100" dönüyordu).

    ⚠️ `!= 200` DEĞİL, TAM 422: `_err500`in 500'ü de `!= 200`'dür ve kapıyı hiç çalıştırmadan
    testi yanlış-yeşile çevirirdi."""
    r = _gonder(client, "/infer/histopath", CT)

    assert r.status_code == 422, (
        f":8100 modalite kapisi ATLANIYOR (HTTP {r.status_code}). Backend'i atlayan bir istemci "
        f"CT kesiti icin 'Grade 4 %100' aliyor. Yanit: {r.text[:200]}"
    )
    assert r.json().get("domain_mismatch") is True, f"ret sebebi isaretlenmedi: {r.text[:200]}"


@pytest.mark.skipif(not PATOLOJI.exists(), reason="patoloji fixture yok")
def test_KRITIK_8100_DOGRU_modalite_GECER_karsit_kanit(client):
    """Karşıt-kanıt: kapı "her şeyi reddet"e dönüşmemeli — doğru modalite geçmeli.

    Aynı zamanda sahte predictor'ın patlamasından kaynaklanacak sahte-yeşili imkânsız kılar:
    yanıtta gerçek sonuç alanları bulunmak zorunda."""
    r = _gonder(client, "/infer/histopath", PATOLOJI)

    assert r.status_code == 200, f"dogru modalite reddedildi: {r.text[:200]}"
    assert r.json().get("top_1_class") == "Grade 4", f"boru hatti bozuldu: {r.text[:200]}"


@pytest.mark.skipif(not CT.exists(), reason="CT fixture yok")
def test_KRITIK_8100_ayni_CT_kidney_ct_ucunda_GECER(client):
    """Karşıt-kanıt: AYNI CT dosyası DOĞRU ucunda geçmeli.

    Bir fixture'ın bir uçta reddedilip diğerinde geçmesi, kapının modaliteyi GERÇEKTEN ölçtüğünün
    (ve girdinin decode edilebildiğinin) bağımsız kanıtıdır."""
    r = _gonder(client, "/infer/kidney_ct", CT)
    assert r.status_code == 200, f"CT, kidney_ct ucunda reddedildi: {r.text[:200]}"


# ── 2) Sessizlik kapısı :8100'de de çalışmalı ─────────────────────────────────


def _ffmpeg_yolu() -> str:
    """ffmpeg ikilisinin yolu: önce PATH, sonra `imageio_ffmpeg`in gömülü ikilisi.

    ⚠️ `ai_service/app.py` `shutil.which("ffmpeg")` kullanıyor (konteynerde apt ile kurulu) ama bu
    geliştirme makinesinde PATH'te ffmpeg YOK. Testleri atlamak, sessizlik kapısının HİÇ
    ölçülmemesi demekti — kapı için kabul edilemez. Bunun yerine `app.shutil.which` yamalanır ve
    deponun `servers/ai_router.py`de zaten kullandığı `imageio_ffmpeg` ikilisine yönlendirilir;
    böylece kapı GERÇEK bir transcode üzerinden ölçülür."""
    import shutil

    yol = shutil.which("ffmpeg")
    if yol:
        return yol
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if os.path.exists(exe) else ""
    except Exception:
        return ""


FFMPEG = _ffmpeg_yolu()


@pytest.fixture()
def ffmpeg(app_modulu, monkeypatch):
    """`ai_service.app`in `shutil.which("ffmpeg")` çağrısını gerçek bir ikiliye bağla."""
    if not FFMPEG:
        pytest.skip("hicbir ffmpeg ikilisi bulunamadi (PATH + imageio_ffmpeg)")
    monkeypatch.setattr(app_modulu.shutil, "which", lambda ad: FFMPEG if ad == "ffmpeg" else None)
    return FFMPEG


def _sessiz_wav(tmp_path: Path) -> Path:
    p = tmp_path / "sessiz.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 22050)
    return p


def test_KRITIK_8100_SESSIZ_ses_REDDEDILIR(client, ffmpeg, tmp_path):
    """Sessiz kayıt → /infer/sound: 422. Bugün 200 + uydurma bir "duygu" dönüyor."""
    r = _gonder(client, "/infer/sound", _sessiz_wav(tmp_path), "audio/wav")

    assert r.status_code == 422, f":8100 sessizlik kapisi ATLANIYOR (HTTP {r.status_code}): {r.text[:200]}"
    assert "sessiz" in r.text.lower()


@pytest.mark.skipif(not SES.exists(), reason="ses fixture'i yok")
def test_KRITIK_8100_GERCEK_ses_GECER_ve_belirsizlik_TASINIR(client, ffmpeg):
    """Karşıt-kanıt: gerçek kayıt geçmeli VE belirsizlik alanları yanıtta taşınmalı.

    Alanlar burada üretilirse backend'in devrettiği yanıt da onları taşır — aynı bilgi iki yerde
    hesaplanmaz (tek kaynak)."""
    r = _gonder(client, "/infer/sound", SES, "audio/mpeg")

    assert r.status_code == 200, f"gercek kayit reddedildi: {r.text[:200]}"
    j = r.json()
    assert "rms_dbfs" in j, f"rms_dbfs tasinmiyor: {j}"
    assert "guvenilir" in j and "belirsizlik" in j, f"belirsizlik alanlari tasinmiyor: {j}"


def test_bos_olasilik_sahte_GUVENILIR_isaretlenmez(client, ffmpeg, monkeypatch, app_modulu):
    """⚠️ İnce tuzak: `normalize_entropi` len<2'de 0.0 döner → `guvenilir_mi` True olur.

    Yani olasılık DÖNMEYEN bir model yanıtı SAHTE "güvenilir" işaretlenirdi. `len(_p) >= 2`
    koruması bunu engelliyor; bu test o korumayı kilitler."""
    if not SES.exists():
        pytest.skip("ses fixture'i yok")

    class _OlasiliksizModel:
        device = "sahte"

        def predict(self, *a, **k):
            return {"top_1_class": "Resting", "top_1_prob": 0.17, "top_k": [], "probabilities": {}}

    monkeypatch.setattr(app_modulu.predictors, "get", lambda ad: _OlasiliksizModel())
    r = _gonder(client, "/infer/sound", SES, "audio/mpeg")

    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert "guvenilir" not in j, f"olasilik yokken SAHTE 'guvenilir' isaretlendi: {j}"


# ── 3) Kapı TEK KAYNAK olmalı (kopya YASAK) ───────────────────────────────────


def test_KAPI_TEK_KAYNAK_nesne_kimligi():
    """İki transport AYNI sınıf/fonksiyon NESNESİNİ kullanmalı — kapının kopyası YASAK.

    ⚠️ Bu test METİN değil NESNE KİMLİĞİ karşılaştırıyor: yorumla/docstring'le kandırılamaz.
    Biri kapıyı `ai_service/app.py`ye ikinci bir kopya olarak gömerek "düzeltirse" ya da import'u
    try/except'e alıp except'te no-op bir kapı tanımlarsa bu test KIRILIR. Bu bulgunun kök nedeni
    tam olarak iki transportun ayrışmasıydı; ikinci bir kopya aynı hatayı yeniden üretir."""
    import ai_service.app as A
    import servers.ai_router as R

    assert A._DomainMismatch is R._ImgDomainMismatch, (
        "iki transport AYNI DomainMismatch sinifini kullanmiyor → kapi KOPYALANMIS"
    )
    assert A._domain_check.__module__ == "utils.image_domain", (
        f"kapi utils/image_domain'den GELMIYOR (modul: {A._domain_check.__module__})"
    )
    assert A._ses_sessiz_mi.__module__ == "utils.ses_kalitesi"


def test_DOCKERFILE_kapi_modullerini_KOPYALIYOR():
    """Yapısal kapı: `app.py`nin üst-düzey `utils.*` import'larının HEPSİ imaja kopyalanmalı.

    ⚠️ AST TABANLI — yorum/docstring içindeki örnek bir `from utils...` satırı GÖRÜLMEZ ve
    `utils/`ü yalnız YORUMDA anan bir Dockerfile bu kapıdan GEÇEMEZ. (Bu depoda "yorum kapıyı
    kandırdı" hatası dört kez oldu; bu yüzden metin araması değil AST + yorum-soyma kullanılıyor.)
    Gerçek arıza sınıfı: `.dockerignore`/COPY kaynaklı sessiz dosya kaybı — bu depo onunla iki kez
    yandı."""
    kaynak = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    gerekli = set()
    for d in agac.body:  # YALNIZ üst düzey: fonksiyon içi import fail-open olurdu
        if isinstance(d, ast.ImportFrom) and (d.module or "").startswith("utils."):
            gerekli.add((d.module or "").split(".")[1] + ".py")

    assert gerekli, "app.py artik utils/ kapilarini import ETMIYOR → kapi kaldirilmis olabilir"

    dockerfile = (KOK / "docker" / "Dockerfile.ai").read_text(encoding="utf-8")
    etkin = "\n".join(s for s in dockerfile.splitlines() if not s.strip().startswith("#"))
    eksik = [m for m in sorted(gerekli) if f"utils/{m}" not in etkin]

    assert not eksik, (
        f"docker/Dockerfile.ai bu kapi modullerini imaja KOPYALAMIYOR: {eksik}. "
        "Konteynerde uvicorn ImportError ile acilmaz (ya da kapi sessizce kaybolur)."
    )


def test_HICBIR_gorsel_uc_kapisiz_KALMAMALI():
    """Yapısal kapı: her görüntü ucunda `_kapi(data, "<uç adı>")` çağrısı bulunmalı.

    ⚠️ AST TABANLI (denetim 2026-08-17). İlk yazımda ham metin araması yapıyordu; bir uç
    docstring'ine `_kapi(data, "histopath")` yazan biri kapıyı GEÇEBİLİYORDU — `ast` yorumları ve
    docstring'i düğüm olarak GÖRMEZ. Ayrıca metin araması biçimlendirmeye bağlıydı: `_kapi(\n
    data, "x")` ya da `_kapi(data=data, label="x")` yazımı YANLIŞ-KIRMIZI verirdi.
    ⚠️ `thermal` BİLEREK listede: etiketi `EXPECTED`de olmadığı için çağrı fiilen no-op'tur, ama
    simetri korunur ki ileride bir termal beklentisi eklendiğinde uç kendiliğinden kapsansın.
    `rna` (CSV) ve JSON uçları kapsam dışı: modalite kavramı yok (onların kapısı ASGARİ GİRDİ).
    """
    agac = ast.parse((KOK / "ai_service" / "app.py").read_text(encoding="utf-8"))

    kapili = set()
    for d in ast.walk(agac):
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "_kapi"):
            continue
        if len(d.args) == 2 and isinstance(d.args[1], ast.Constant) and isinstance(d.args[1].value, str):
            kapili.add(d.args[1].value)

    beklenen = [
        "histopath",
        "kidney_ct",
        "segmentation",
        "landmark",
        "thermal",
        "cat_organ",
        "reticulocytes",
        "em_fantom",
        "em_petri",
    ]
    eksik = [u for u in beklenen if u not in kapili]
    assert not eksik, f"bu :8100 uclari modalite kapisi CAGIRMIYOR: {eksik}"

    # Ses ucunun kapısı ayrı (RMS) ve MODEL YÜKLEMESİNDEN ÖNCE gelmeli (2026-08-16 dersi).
    # ⚠️ Sıra da AST'den ölçülür: satır numaraları DÜĞÜMLERDEN gelir, yorumdan DEĞİL.
    ses = [
        d.lineno
        for d in ast.walk(agac)
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "_ses_sessiz_mi"
    ]
    model = [
        d.lineno
        for d in ast.walk(agac)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr == "get"
        and isinstance(d.func.value, ast.Name)
        and d.func.value.id == "predictors"
        and d.args
        and isinstance(d.args[0], ast.Constant)
        and d.args[0].value == "sound"
    ]
    assert ses, "sessizlik kapisi :8100'de YOK"
    assert model, "predictors.get('sound') bulunamadi -> kapi BAYAT"
    assert min(ses) < min(model), "sessizlik kapisi model yuklemesinden SONRA geliyor (2026-08-16 dersi)"


# ── 4) ASGARİ GİRDİ kapısı :8100'de de çalışmalı (denetim 2026-08-17) ────────
#
# Ölçüldü — AYNI boş gövde iki transportta farklı davranıyordu:
#     backend /api/ai/disease        {}  ->  422 "geçerli vital veriler gerekli"
#     :8100   /infer/disease         {}  ->  200 "Conjunctivitis %53", low_confidence: FALSE
#     backend /api/ai/disease/kidney {}  ->  422 "yeterli klinik veri yok"
#     :8100   /infer/kidney_disease  {}  ->  200 prob_pct 78.0, label "ckd"
# %78 hastanın verisinden DEĞİL eğitim setinin ön-olasılığından geliyor (sahip bildirimi
# 2026-08-07); `predict_one({"sc": 1.2})` de aynı 0.78 dönüyor.


@pytest.fixture()
def hastalik_client(app_modulu, monkeypatch):
    """`/infer/disease` için LİSTE-OF-TUPLE döndüren sahte predictor.

    ⚠️ Yukarıdaki `client` fixture'ı BU UÇTA KULLANILAMAZ: `_SahteModel.predict` dict döndürüyor,
    uç ise `for d, p in results` yapıyor → `ValueError` → `_err500` → 500. O hâlde `!= 200` yazan
    bir test bugün de yeşil olurdu, yani bulguyu HİÇ ölçmezdi."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)

    class _Sahte:
        cagrildi = False

        def predict(self, age, weight, hr, temp, duration, symptoms):
            _Sahte.cagrildi = True
            return [("Conjunctivitis", 0.53), ("Gastroenteritis", 0.41)]

    _Sahte.cagrildi = False
    _Sahte.yuklendi = False

    def _get(ad):
        # ⚠️ MODEL YÜKLEME de işaretlenir: kapı YALNIZ `predict`ten önce olsaydı, reddedilecek
        # istek için 15 MB ONNX yine boşuna yüklenirdi (2026-08-16 dersi). İlk yazımda bayrak
        # yalnız `predict` içindeydi ve kapıyı `predictors.get`ten SONRAYA taşıyan mutasyon
        # SESSİZCE geçti (ölçüldü).
        _Sahte.yuklendi = True
        return _Sahte()

    monkeypatch.setattr(app_modulu.predictors, "get", _get)
    return TestClient(app_modulu.app), _Sahte


@pytest.fixture()
def ckd_client(app_modulu, monkeypatch):
    """`/infer/kidney_disease` için sahte `predict_one`.

    ⚠️ PAKET yamalanır, ALT-MODÜL değil: uç `from ai_hub.inference_human_kidney_disease import
    predict_one` yapıyor, yani PAKET attribute'unu okuyor. Alt-modülü yamalamak İŞE YARAMIYOR
    (ölçüldü: gerçek ONNX modeli koştu, 737 ms). Yanlış hedefte test sessizce gerçek modeli
    çalıştırır ve ağırlık bulunmayan bir ortamda YANLIŞ-KIRMIZI olur."""
    from fastapi.testclient import TestClient

    import ai_hub.inference_human_kidney_disease as KD

    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    durum = {"cagrildi": False}

    def _sahte_predict_one(features):
        durum["cagrildi"] = True
        return {"prob_ckd": 0.99, "label": "ckd", "model": "SAHTE"}

    monkeypatch.setattr(KD, "predict_one", _sahte_predict_one)
    return TestClient(app_modulu.app), durum


def test_KRITIK_8100_disease_BOS_GOVDE_REDDEDILIR(hastalik_client):
    """Boş gövde → 422. Bugün 200 + "Conjunctivitis %53" + `low_confidence: false` dönüyordu."""
    c, sahte = hastalik_client
    r = c.post("/infer/disease", json={})

    # ⚠️ TAM 422 (`!= 200` YASAK): `_err500`in 500'ü de `!= 200`'dür ve kapıyı hiç çalıştırmadan
    # testi yanlış-yeşile çevirirdi.
    assert r.status_code == 422, f":8100 asgari-girdi kapisi ATLANIYOR (HTTP {r.status_code}): {r.text[:200]}"
    assert r.json().get("insufficient_input") is True, f"ret sebebi isaretlenmedi: {r.text[:200]}"
    assert "vital" in r.text.lower(), f"mesaj router'inkiyle ayni kaynaktan gelmiyor: {r.text[:200]}"
    assert sahte.yuklendi is False, "kapi MODEL YUKLEMESINDEN SONRA calisiyor (15 MB ONNX bosuna yuklendi)"
    assert sahte.cagrildi is False, "kapi tahminden SONRA calisiyor"


def test_KRITIK_8100_kidney_disease_BOS_GOVDE_REDDEDILIR(ckd_client):
    """Boş gövde → 422. Bugün 200 + `prob_pct 78.0` + `label "ckd"` dönüyordu."""
    c, durum = ckd_client
    r = c.post("/infer/kidney_disease", json={})

    assert r.status_code == 422, f":8100 CKD kapisi ATLANIYOR (HTTP {r.status_code}): {r.text[:200]}"
    assert "prob_ckd" not in r.text and "prob_pct" not in r.text, (
        f"kullaniciya olasilik SIZDI - bos formda '%78 ckd' gosterilemez: {r.text[:200]}"
    )
    assert "yeterli klinik veri yok" in r.text and "yanıltıcı" in r.text
    assert durum["cagrildi"] is False, "kapi MODELDEN SONRA calisiyor"


def test_KRITIK_8100_ckd_CEKIRDEK_belirtec_YOKSA_reddedilir(ckd_client):
    """6 alan DOLU ama renal belirteç YOK → yine 422.

    Yalnızca alan SAYAN eksik bir yamayı yakalar: renal sinyal yoksa sayı demografiden türer."""
    c, durum = ckd_client
    r = c.post(
        "/infer/kidney_disease",
        json={"age": 48, "bp": 80, "su": 0, "sod": 137, "pot": 4.4, "wc": 7800},
    )

    assert r.status_code == 422, f"cekirdek belirtec olmadan tahmin URETILDI: {r.text[:200]}"
    assert "böbrek işlevine dair" in r.text
    assert durum["cagrildi"] is False


def test_KARSIT_KANIT_8100_GECERLI_vital_GECER(hastalik_client):
    """Karşıt-kanıt: kapı "her şeyi reddet"e dönüşmemeli."""
    c, sahte = hastalik_client
    r = c.post(
        "/infer/disease",
        json={"age": 3, "weight": 4.2, "hr": 180, "temp": 38.5, "duration": 10, "symptom_indices": [1]},
    )

    assert r.status_code == 200, f"gecerli vital REDDEDILDI: {r.text[:200]}"
    assert r.json()["results"][0]["disease"] == "Conjunctivitis"
    assert sahte.cagrildi is True, "boru hatti kosmadi"


def test_KARSIT_KANIT_8100_METIN_vital_500_URETMEZ(hastalik_client):
    """⚠️ `:8100` gövdesi Pydantic'ten GEÇMİYOR: `"4.2"` gibi metin gelebilir.

    Kapıda sayıya çevirme olmasaydı `0 < "4.2"` TypeError verir ve kapı YENİ bir 500 arıza modu
    getirirdi. Metin vital geçerli aralıktaysa istek GEÇMELİ."""
    c, sahte = hastalik_client
    r = c.post(
        "/infer/disease",
        json={"age": "3", "weight": "4.2", "hr": "180", "temp": "38.5", "duration": 10, "symptom_indices": []},
    )

    assert r.status_code == 200, f"metin vital YENI bir ariza modu dogurdu: {r.text[:200]}"
    assert sahte.cagrildi is True


def test_KARSIT_KANIT_8100_GECERLI_ckd_formu_GECER(ckd_client):
    """Karşıt-kanıt: 6 alan + çekirdek belirteç → geçmeli."""
    c, durum = ckd_client
    r = c.post("/infer/kidney_disease", json={"sc": 1.2, "bu": 40, "sg": 1.02, "al": 1, "hemo": 12, "age": 55})

    assert r.status_code == 200, f"gecerli CKD formu REDDEDILDI: {r.text[:200]}"
    # "SAHTE" → yamanın GERÇEKTEN bağlandığının kanıtı (gerçek model "ExtraTrees" derdi).
    assert r.json()["model"] == "SAHTE", f"sahte predict_one baglanmadi, GERCEK model kostu: {r.text[:200]}"
    assert durum["cagrildi"] is True


def test_8100_bos_metin_DOLU_SAYILMAZ(ckd_client):
    """Boşluklu metinler alan SAYILMAMALI (router kuralının birebir taşındığının kanıtı)."""
    c, _ = ckd_client
    r = c.post(
        "/infer/kidney_disease",
        json={"rbc": "  ", "pc": "  ", "pcc": " ", "ba": " ", "htn": " ", "dm": " "},
    )
    assert r.status_code == 422, f"bos metinler DOLU sayildi: {r.text[:200]}"


def test_ASGARI_GIRDI_TEK_KAYNAK_nesne_kimligi():
    """İki transport AYNI fonksiyon/sınıf NESNESİNİ kullanmalı — kapının kopyası YASAK.

    ⚠️ METİN değil NESNE KİMLİĞİ: yorumla kandırılamaz. Biri kapıyı `ai_service/app.py`ye ikinci
    kopya olarak gömerse ya da import'u try/except'e alıp fail-open bir taklit tanımlarsa KIRILIR.
    Bu bulgunun kök nedeni tam olarak iki transportun ayrışmasıydı."""
    import ai_service.app as A
    import servers.ai_router as R

    assert A._AsgariGirdiYok is R._AsgariGirdiYok, "iki transport AYRI istisna sinifi kullaniyor"
    assert A._ckd_kapisi is R._ckd_kapisi, "CKD kapisi KOPYALANMIS"
    assert A._vital_kapisi is R._vital_kapisi, "vital kapisi KOPYALANMIS"
    assert A._ckd_kapisi.__module__ == "utils.klinik_asgari", (
        f"kapi utils/klinik_asgari'den GELMIYOR (modul: {A._ckd_kapisi.__module__})"
    )


def test_ASGARI_esikler_TASINDI_ve_ARDA_KOPYA_KALMADI():
    """Eşikler taşınırken gevşetilmemiş/sertleştirilmemiş olmalı VE router'da kopya kalmamalı.

    İki kaynak kalırsa biri sessizce kayar — bu bulgunun kök neden sınıfı."""
    import servers.ai_router as R
    from utils.klinik_asgari import CKD_CEKIRDEK, CKD_MIN_ALAN

    assert CKD_MIN_ALAN == 6, "asgari alan esigi DEGISTIRILMIS (tasima, sertlestirme degil)"
    assert CKD_CEKIRDEK == ("sc", "bu", "sg", "al", "hemo")
    for ad in ("_CKD_MIN_ALAN", "_CKD_CEKIRDEK", "_CKD_ETIKET"):
        assert not hasattr(R, ad), f"router'da ARDA KALAN kopya sabit: {ad}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
