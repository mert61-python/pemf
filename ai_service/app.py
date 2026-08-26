"""
PEMF AI Servisi (GPU) — mikroservis.
  • /health          → CUDA/onnxruntime sağlayıcıları + GPU
  • /models          → /models altındaki .onnx dosyaları  |  /infer/models → bağlı uçlar
  • /benchmark       → seçilen modeli CUDA ile yükle, sentetik girdiyle süre ölç
  • /infer/histopath → (görüntü)  Böbrek histopatoloji grade — GPU
  • /infer/sound      → (ses)      Kedi sesi sınıflandırma — GPU (mel-spektrogram CPU)
ai_hub predictor'ları GERÇEK inference; ağırlıklar /models mount.
NOT (2026-08-26): başlıktaki "torch YOK" tarihiydi — XAI dalgası (grad-cam) ve
/infer/scratch (CPN, celldetection) torch KULLANIR; requirements-ai torch cu128 pinli.
"""

import asyncio
import base64
import glob
import math
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

import numpy as np
import onnxruntime as ort
from fastapi import Body, FastAPI, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from ai_service import predictors
from ai_service.gpu import gpu_ok as _gpu_ok
from ai_service.gpu import onnx_providers as _providers
from ai_service.gpu import yolo_device as _yolo_device

# ⚠️ MODALİTE + SESSİZLİK KAPILARI — TEK KAYNAK `utils/`, KOPYA DEĞİL.
# Deponun kendi kuralı (`ai_hub/inference_petri_dish/plausibility.py`): "denetim ROUTER'da DEĞİL
# burada durmalı, çünkü PEMF_AI_SERVICE_URL tanımlıyken servers/ai_router.py HİÇ çalışmaz."
# Bu uçlar auth-muaftır ve backend'i atlayan bir istemci doğrudan çağırabilir; kapı yalnız
# router'da kalırsa o yolda hiç çalışmaz — ölçüldü: CT kesiti → /infer/histopath → 200
# {"top_1_class":"Grade 4","top_1_prob":1.0} (kapının var olma sebebi olan 2026-08-06 saha vakası).
# ⚠️ IMPORT ÜST DÜZEY ve try/except İÇİNDE DEĞİL: fail-open bir kapı kapı değildir. Modüller
# imajda yoksa (docker/Dockerfile.ai'deki COPY satırı silinirse) uvicorn açılışta ImportError ile
# GÜRÜLTÜLÜ düşer — kapının sessizce kaybolması imkânsız.
from utils.image_domain import DomainMismatch as _DomainMismatch
from utils.image_domain import check as _domain_check

# ⚠️ ASGARİ GİRDİ KAPILARI (denetim 2026-08-17) — router ile AYNI nesne, KOPYA DEĞİL.
# Ölçüldü: bu iki uç boş gövdeyle 200 dönüyordu — `/infer/disease` → "Conjunctivitis %53" ve
# `low_confidence: false`; `/infer/kidney_disease` → `prob_pct 78.0, label "ckd"`. O %78 hastanın
# verisinden değil eğitim setinin ön-olasılığından gelir (sahip bildirimi 2026-08-07).
from utils.klinik_asgari import AsgariGirdiYok as _AsgariGirdiYok
from utils.klinik_asgari import ckd_kapisi as _ckd_kapisi
from utils.klinik_asgari import vital_kapisi as _vital_kapisi
from utils.ses_kalitesi import guvenilir_mi as _ses_guvenilir_mi
from utils.ses_kalitesi import normalize_entropi as _ses_entropi
from utils.ses_kalitesi import sessiz_mi as _ses_sessiz_mi
from utils.ses_kalitesi import wav_rms_dbfs as _ses_wav_rms

MODELS_DIR = os.environ.get("PEMF_AI_MODELS_DIR", "/models")
app = FastAPI(title="PEMF AI Service (GPU)", version="0.3.0")


@app.on_event("startup")
def _scratch_warmup():
    """CPN (872 MB) warmup — plan v2 bulgu 12: yükleme istek anına kalırsa
    scratch'in İLK isteği 15-30 sn boyunca predictor kilidini tutar. Açılışta
    arka-plan thread'inde ısıtılır; cell/PT yoksa zarifçe atlanır (isit loglar).
    Kapatma: PEMF_SCRATCH_WARMUP=0."""
    if os.environ.get("PEMF_SCRATCH_WARMUP", "1") != "1":
        return
    # CI OLCUMU (2026-08-26, exit 134): cell/ yokken daemon thread isit() icinde
    # loglayip HEMEN bitiyor ve kisa omurlu TestClient/interpreter kapanisiyla
    # yarisinca 'Fatal Python error: _enter_buffered_busy ... daemon threads'
    # SIGABRT'i uretebiliyordu (1724 test GECTIKTEN sonra surec dustu). cell teslim
    # edilmemisse thread HIC baslatilmaz — senkron ve ucuz on-kontrol:
    import importlib.util

    # ⚠️ ALT-MODULE bakilir: cell/ artik ISKELET olarak repoda (sahip talimati) —
    # paket-varligi yanlis-pozitif olur; gercek teslim gostergesi cell/cpn.py'dir.
    if importlib.util.find_spec("ai_hub.inference_paper_dilek_hoca.cell.cpn") is None:
        return
    import threading

    from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as _ipd

    threading.Thread(target=_ipd.isit, daemon=True, name="scratch-warmup").start()


# GPU tespiti (_gpu_ok / _yolo_device / _providers) → ai_service.gpu (tek nokta; üstte import edildi).

# ── Auth-muaf /infer uçları için DoS sertleştirme (upload boyut + eşzamanlılık) ──────────────
# Bu servisin /infer uçları kimlik-muaf (core→GPU dahili çağrı). Sınır yoksa: (1) dev yükler
# belleği/diski doldurur (_save_temp), (2) sınırsız paralel ağır GPU inference GPU/bellek/loop'u
# tüketip AI Pro kapalı-döngü sürüşünü geciktirir. Aşağıdaki middleware her ikisini de kapatır.
MAX_UPLOAD_BYTES = int(os.environ.get("PEMF_AI_MAX_UPLOAD_MB", "100")) * 1024 * 1024
_MAX_CONCURRENT_INFER = max(1, int(os.environ.get("PEMF_AI_MAX_CONCURRENT", "4")))
_infer_sem = asyncio.Semaphore(_MAX_CONCURRENT_INFER)


@app.middleware("http")
async def _guard_infer(request, call_next):
    """Yalnız ağır /infer + /benchmark uçlarını sınırla; /health, /models vb. serbest."""
    path = request.url.path
    if not (path.startswith("/infer/") or path == "/benchmark"):
        return await call_next(request)
    # (1) Boyut kapağı: Content-Length aşarsa gövdeyi OKUMADAN 413 döndür (bellek/disk DoS).
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > MAX_UPLOAD_BYTES:
                return JSONResponse(
                    {"error": f"Yük çok büyük (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"},
                    status_code=413,
                )
        except ValueError:
            pass
    # (2) Eşzamanlılık sınırı: asyncio.Semaphore event-loop'u BLOKLAMAZ (await ile bekler),
    # aynı anda en çok _MAX_CONCURRENT_INFER ağır inference koşar → GPU/bellek/loop korunur.
    async with _infer_sem:
        return await call_next(request)


def _read_bgr(data: bytes):
    import cv2

    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("görüntü çözülemedi")
    return img


def _kapi(data: bytes, label: str):
    """Modalite kapısı: uyuşmazlıkta 422 `JSONResponse`, aksi hâlde `None`.

    `utils.image_domain.check` ile AYNI nesneyi çağırır — kapının ikinci bir kopyası YOK
    (bu bulgunun kök nedeni tam olarak iki transportun ayrışmasıydı).
    ⚠️ Decode edilemeyen girdide kapı ZORLANMAZ: o yolun mevcut hata davranışı (uç kendi
    `except`iyle 500 döner) korunur; kapı yeni bir başarısızlık modu getirmez.
    ⚠️ Ret 422 ile AYRI yoldan döner, `_err500`in jenerik mesajına karışmaz — istemci reddin
    SEBEBİNİ görür (router tarafındaki kalıbın aynısı)."""
    try:
        _domain_check(_read_bgr(data), label)
    except _DomainMismatch as dm:
        return JSONResponse({"error": dm.user_message(), "domain_mismatch": True}, status_code=422)
    except Exception:
        return None
    return None


def _jpg_b64(bgr) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode("utf-8")


def _err500(exc, code: int = 500):
    """Audit P3: ham istisna metni (sunucu dosya yolları/iç detay) istemciye SIZMASIN — jenerik mesaj
    + correlation-id döndür, tam istisnayı yalnız sunucu log'una yaz (keşif/bilgi-ifşası engellenir)."""
    import logging as _lg
    import uuid as _uuid

    eid = _uuid.uuid4().hex[:12]
    _lg.getLogger("ai_service").error("infer hata [%s]: %s: %s", eid, type(exc).__name__, exc)
    return JSONResponse({"error": "Sunucu hatasi (loglandi)", "error_id": eid}, status_code=code)


# ── yardımcılar ──────────────────────────────────────────────────────────────
def _list_onnx():
    out = []
    for p in glob.glob(os.path.join(MODELS_DIR, "**", "*.onnx"), recursive=True):
        try:
            out.append({"path": os.path.relpath(p, MODELS_DIR), "mb": round(os.path.getsize(p) / 1048576, 1)})
        except OSError:
            pass
    return sorted(out, key=lambda x: x["mb"])


def _synthetic_input(sess):
    inp = sess.get_inputs()[0]
    shape = [d if isinstance(d, int) and d > 0 else (1 if i == 0 else 224) for i, d in enumerate(inp.shape)]
    tmap = {
        "tensor(float)": np.float32,
        "tensor(float16)": np.float16,
        "tensor(int64)": np.int64,
        "tensor(int32)": np.int32,
        "tensor(uint8)": np.uint8,
        "tensor(double)": np.float64,
    }
    dt = tmap.get(inp.type, np.float32)
    arr = np.random.rand(*shape).astype(dt) if np.issubdtype(dt, np.floating) else np.zeros(shape, dtype=dt)
    return inp.name, arr


def _save_temp(data: bytes, suffix: str) -> str:
    # İkincil boyut-kapağı: Content-Length'siz (chunked) istekte middleware'in header-kontrolü
    # devreye girmez → burada da diske yazmadan reddet (disk-dolumu DoS savunma-derinliği).
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"yük çok büyük (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    tf = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tf.write(data)
    tf.close()
    return tf.name


# ── sağlık / keşif ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    avail = ort.get_available_providers()
    gpu = _gpu_ok()
    info = {
        "status": "online",
        "service": "pemf-ai",
        "onnxruntime": ort.__version__,
        "onnx_providers": avail,
        "cuda": "CUDAExecutionProvider" in avail,
        "gpu_usable": gpu,
        "device": "gpu" if gpu else "cpu",
        "models_dir": MODELS_DIR,
        "onnx_count": len(_list_onnx()),
        "infer_endpoints": sorted(predictors.REGISTRY.keys()),
        "loaded": predictors.loaded(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["torch_cuda"] = torch.cuda.is_available()
    except Exception as e:
        info["torch"] = f"yok ({type(e).__name__})"
    return info


@app.get("/models")
def models():
    return {"models_dir": MODELS_DIR, "onnx": _list_onnx()}


@app.get("/infer/models")
def infer_models():
    return {k: {"kind": v["kind"], "title": v["title"], "onnx": v["onnx"]} for k, v in predictors.REGISTRY.items()}


@app.get("/benchmark")
def benchmark(model: Optional[str] = Query(None), runs: int = Query(20, ge=1, le=200)):
    lst = _list_onnx()
    if not lst:
        return JSONResponse({"error": f"{MODELS_DIR} altında .onnx yok"}, status_code=404)
    rel = model or lst[0]["path"]
    # Audit P3: path-traversal engelle — rel MODELS_DIR ALTINDA olmalı ('../..' / mutlak yol reddet).
    full = os.path.realpath(os.path.join(MODELS_DIR, rel))
    _root = os.path.realpath(MODELS_DIR)
    if not (full == _root or full.startswith(_root + os.sep)) or not os.path.exists(full):
        return JSONResponse({"error": "model yok"}, status_code=404)
    provs = _providers(True)
    try:
        t0 = time.time()
        sess = ort.InferenceSession(full, providers=provs)
        load_ms = (time.time() - t0) * 1000
    except Exception:
        return JSONResponse({"error": "model yuklenemedi"}, status_code=400)
    used = sess.get_providers()
    name, arr = _synthetic_input(sess)
    sess.run(None, {name: arr})
    t1 = time.time()
    for _ in range(runs):
        sess.run(None, {name: arr})
    return {
        "model": rel,
        "active_providers": used,
        "ran_on_gpu": bool(used) and used[0] == "CUDAExecutionProvider",
        "load_ms": round(load_ms, 1),
        "inference_ms_avg": round((time.time() - t1) / runs * 1000, 2),
        "runs": runs,
    }


# ── GERÇEK inference uçları ──────────────────────────────────────────────────
@app.post("/infer/histopath")
def infer_histopath(file: UploadFile = File(...), explain: str = Form(None)):
    """Böbrek histopatoloji doku görüntüsü → grade0-4 + olasılıklar (GPU).

    explain=true → ensemble HiRes-CAM + DISAGREEMENT (Faz 4 paritesi — TEK-KAYNAK
    xai_histopat_isi_haritasi; GPU'da ~sn, CPU'da dakikaya uzayabilir).
    """
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "histopath")
        if _red:
            return _red
        clf = predictors.get("histopath")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        result = clf.predict(tmp, top_k=5)
        yanit = {
            "status": "success",
            "device": getattr(clf, "device", "?"),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result.get("probabilities"),
        }
        if str(explain).lower() == "true":
            try:
                from ai_hub.inference_renal_histopath_kmc import inference_renal_histopath_kmc as _irh

                _x = _irh.xai_histopat_isi_haritasi(tmp)
                yanit["xai_image_base64"] = _x["xai_image_base64"]
                yanit["xai_disagreement_base64"] = _x["xai_disagreement_base64"]
                yanit["xai_method"] = _x.get("method")
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("Histopat XAI üretilemedi: %s", xe)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/scratch")
def infer_scratch(
    file: UploadFile = File(...),
    scratch_yonu: str = Form(None),
    pixel_mm: float = Form(None),
    explain: str = Form(None),
    xai_method: str = Form(None),
):
    """Yara Kapanma (Scratch) — CPN + wound-closure (TEK-KAYNAK scratch_analiz;
    router paritesi). Delegate alanları STRING gelir, None'lar ATLANIR →
    her alan Form(None) + burada default'lanır (plan v2 bulgu 3)."""
    tmp = None
    try:
        from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as _ipd

        yon = scratch_yonu or "dikey"
        if yon not in _ipd.GECERLI_SCRATCH_YONLERI:
            return JSONResponse({"error": "scratch_yonu 'dikey' ya da 'yatay' olmalı"}, status_code=422)
        met = xai_method or "eigencam"
        if met not in _ipd.GECERLI_XAI_YONTEMLERI:
            return JSONResponse({"error": f"xai_method geçersiz: {met}"}, status_code=422)
        pmm = float(pixel_mm) if pixel_mm else _ipd.PIXEL_TO_MM_DEFAULT

        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        # Modalite kapısı YOK (karar 0.3) — boş görüntüyü scratch_analiz'in
        # n_cells==0 yapılandırılmış uyarısı yakalar. KAYIPSIZ .png tmp (ölçüm!).
        tmp = _save_temp(data, ".png")
        t0 = time.time()
        try:
            sonuc = _ipd.scratch_analiz(
                tmp, scratch_yonu=yon, pixel_mm=pmm, explain=str(explain).lower() == "true", xai_method=met
            )
        except _ipd.ScratchMesgul:
            # Kilit kısa timeout'la denendi — semafor slotu dakikalarca işgal edilmez
            return JSONResponse(
                {"error": "Başka bir yara-kapanma analizi sürüyor — birazdan yeniden deneyin."}, status_code=429
            )
        except _ipd.ModelKurulumEksik:
            # SABİT mesaj — ham istisna metni sunucu yollarını sızdırıyordu (auth-muaf uç)
            return JSONResponse(
                {"error": "Yara kapanma modeli bu kurulumda hazır değil — model paketi /models mount'una eklenmeli."},
                status_code=503,
            )
        except ValueError as ve:
            return JSONResponse({"error": str(ve)}, status_code=422)
        return {"status": "success", "inference_ms": round((time.time() - t0) * 1000, 1), **sonuc}
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/sound")
def infer_sound(file: UploadFile = File(...), explain: str = Form(None), xai_method: str = Form(None)):
    """Kedi sesi (mp3/wav/m4a) → ffmpeg 22050 mono WAV → 10 sınıf + top-3 (ONNX GPU).

    explain=true → mel üzerinde Grad-CAM (Faz 2 paritesi — TEK-KAYNAK
    ai_hub.inference_cat_sound.xai_ses_isi_haritasi; sessizlik kapısının ARKASINDA).
    """
    # A6 allowlist paritesi (dusman-dogrulama 2026-08-27): router 422 veriyordu, burasi
    # yazim-hatasini zarif-dususe yutuyordu -> cagiran yontem adinin hatali oldugunu ogrenemiyordu.
    if xai_method is not None and xai_method not in _GECERLI_CAM:
        return JSONResponse({"error": f"xai_method geçersiz: {xai_method}"}, status_code=422)
    tmp_in = tmp_wav = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "ses boş/çok küçük"}, status_code=400)
        # ⚠️ `predictors.get("sound")` BURADAN sessizlik kapısının ARDINA taşındı (aşağıya bkz.).
        tmp_in = _save_temp(data, ".bin")
        tmp_wav = tmp_in + ".wav"
        ff = shutil.which("ffmpeg") or "ffmpeg"
        # Audit P2: ffmpeg sertleştir (SSRF/disk-dolumu) — -protocol_whitelist file, -nostdin, -t 30, -fs cap.
        proc = subprocess.run(
            [
                ff,
                "-nostdin",
                "-protocol_whitelist",
                "file",
                "-t",
                "30",
                "-y",
                "-i",
                tmp_in,
                "-ar",
                "22050",
                "-ac",
                "1",
                "-fs",
                "30000000",
                tmp_wav,
            ],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0 or not os.path.exists(tmp_wav):
            return JSONResponse({"error": "ses çözümlenemedi (ffmpeg)"}, status_code=400)

        # ⚠️ SESSİZLİK KAPISI (saha bildirimi 2026-08-15) — router'daki kapının AYNI modülü.
        # Modelin 10 sınıfının HEPSİ kedi duygusu; "kedi değil" sınıfı YOK → softmax sessizliğe
        # bile mutlaka bir duygu atar. Bu uç kapısız olduğu için boş kayıt :8100'e doğrudan
        # gittiğinde yine "duygu" dönüyordu.
        # ⚠️ RMS ölçülemezse kapı ZORLANMAZ (router'daki fail-open ile birebir aynı davranış).
        try:
            _rms = _ses_wav_rms(tmp_wav)
        except Exception:
            _rms = None
        # ⚠️ `-inf`/`nan` JSON'a YAZILAMAZ. Tam sessiz bir kayıtta RMS `-inf` olur ve ham
        # `round(_rms, 1)` `ValueError: Out of range float values are not JSON compliant` atar →
        # istek 422 yerine jenerik 500'e düşer ve kullanıcı reddin SEBEBİNİ göremez (ölçüldü:
        # bu yamanın ilk hâlinde tam olarak böyle oldu, test yakaladı).
        _rms_json = None if _rms is None or not math.isfinite(_rms) else round(_rms, 1)
        if _rms is not None and _ses_sessiz_mi(_rms):
            return JSONResponse(
                {
                    "error": "Kayıt sessiz ya da çok zayıf — ses alınamamış olabilir.",
                    "rms_dbfs": _rms_json,
                },
                status_code=422,
            )

        # ⚠️ MODEL YÜKLEMESİ KAPIDAN SONRA (2026-08-16 dersi, router'da da böyle): sessiz bir
        # kaydı REDDETMEK için 15 MB'lik ONNX boşuna yüklenmesin ve modelin bulunmadığı ortamda
        # istek kapıya HİÇ varamadan 500 ile düşmesin.
        clf = predictors.get("sound")
        t0 = time.time()
        result = clf.predict(tmp_wav, top_k=3)
        # BELİRSİZLİK sonuçla BİRLİKTE taşınır (router yanıtıyla alan-uyumu): devredilen yanıt bu
        # alanları TAŞIDIĞI için backend tarafında ayrıca üretilmesi gerekmez — tek kaynak.
        # ⚠️ `len(_p) >= 2` ZORUNLU: `normalize_entropi` len<2'de 0.0 döner → `guvenilir_mi` True
        # olur ve olasılık DÖNMEYEN bir yanıt SAHTE "güvenilir" işaretlenirdi.
        _p = list((result.get("probabilities") or {}).values())
        _ek = {}
        if len(_p) >= 2:
            _ek = {"guvenilir": _ses_guvenilir_mi(_p), "belirsizlik": round(_ses_entropi(_p), 3)}
        # Faz 2 XAI paritesi: sessizlik kapısı YUKARIDA kesti — buraya gelen kayıt analiz
        # edilebilir. Açıklama İKİNCİL: hatası analizi düşürmez.
        if str(explain).lower() == "true":
            try:
                from ai_hub.inference_cat_sound import inference_cat_sound as _ics

                _x = _ics.xai_ses_isi_haritasi(tmp_wav, None, xai_method or "gradcam++")
                _ek["xai_image_base64"] = _x["xai_image_base64"]
                _ek["xai_method"] = _x.get("method")
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("Ses XAI üretilemedi (analiz etkilenmedi): %s", xe)
                _ek["xai_error"] = "Açıklama üretilemedi"
        return {
            "status": "success",
            "device": getattr(clf, "device", "?"),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result.get("probabilities"),
            "rms_dbfs": _rms_json,
            **_ek,
        }
    except Exception as e:
        return _err500(e)
    finally:
        for p in (tmp_in, tmp_wav):
            if p and os.path.exists(p):
                os.unlink(p)


# ── YOLO/görüntü uçları (Faz 2b — GPU via ultralytics device=0 → onnxruntime CUDA) ──
@app.post("/infer/kidney_ct")
def infer_kidney_ct(file: UploadFile = File(...), explain: str = Form(None)):
    """Böbrek CT → YOLOv8s tespit (taş/kist/normal) + annotated görsel (GPU).

    explain=true → EigenCAM (Faz 2 paritesi — TEK-KAYNAK xai_ct_isi_haritasi).
    """
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "kidney_ct")
        if _red:
            return _red
        det = predictors.get("kidney_ct")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        result = det.predict(tmp)
        overlay = det.draw_overlay(tmp, result)
        yanit = {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "n_detections": result.get("n_detections"),
            "class_counts": result.get("class_counts"),
            "detections": result.get("detections"),
            "image_base64": _jpg_b64(overlay),
        }
        if str(explain).lower() == "true":
            try:
                from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as _ikt

                _x = _ikt.xai_ct_isi_haritasi(tmp)
                yanit["xai_image_base64"] = _x["xai_image_base64"]
                yanit["xai_method"] = _x.get("method")
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("CT XAI üretilemedi: %s", xe)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/segmentation")
def infer_segmentation(file: UploadFile = File(...)):
    """Kedi segmentasyon → YOLOv8m-seg maske overlay + kedi sayısı (GPU)."""
    import cv2

    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "segmentation")
        if _red:
            return _red
        img = _read_bgr(data)
        model = predictors.get("segmentation")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        results = model.predict(source=tmp, conf=0.25, iou=0.7, imgsz=640, device=_yolo_device(), verbose=False)
        r = results[0]
        cat_count = len(r.boxes) if r.boxes is not None else 0
        if r.masks is not None and len(r.masks) > 0:
            for mask_data in r.masks.data:
                mask_np = mask_data.cpu().numpy()
                mask_rs = cv2.resize(mask_np, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                colored = np.zeros_like(img)
                colored[:, :, 1] = 160
                blend = cv2.addWeighted(img, 0.55, colored, 0.45, 0)
                img = np.where(mask_rs[:, :, None] > 0.5, blend, img).astype(np.uint8)
        return {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "cat_count": int(cat_count),
            "image_base64": _jpg_b64(img),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/landmark")
def infer_landmark(file: UploadFile = File(...)):
    """Kedi yüzü → YOLO-pose keypoint → FGS ağrı skoru + keypoint overlay (GPU).

    Tespit yoksa yanlış-güvence verme: fgs_total=null, detected=false.
    """
    import cv2

    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "landmark")
        if _red:
            return _red
        img = _read_bgr(data)
        model = predictors.get("landmark")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        results = model.predict(tmp, conf=0.25, device=_yolo_device(), verbose=False)
        infer_ms = round((time.time() - t0) * 1000, 1)

        fgs, detected = {}, False
        if results and len(results) > 0:
            r = results[0]
            if r.keypoints is not None and len(r.keypoints.xy) > 0 and r.boxes is not None and len(r.boxes) > 0:
                kp_xy = r.keypoints.xy[0].cpu().numpy()
                kp_conf = None
                try:
                    if r.keypoints.conf is not None:
                        kp_conf = r.keypoints.conf[0].cpu().numpy()
                except Exception:
                    kp_conf = None
                x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                bw, bh = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
                kp_norm = kp_xy.copy()
                kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh
                from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs

                fgs = compute_fgs(kp_norm)
                _ft = fgs.get("fgs_total", -1)
                _valid = int(np.count_nonzero((kp_xy[:, 0] > 0) | (kp_xy[:, 1] > 0)))
                _conf_ok = True if kp_conf is None else (float(np.mean(kp_conf)) >= 0.20)
                if _ft is not None and _ft >= 0 and _valid >= 20 and _conf_ok:
                    detected = True
                    for pt in kp_xy:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 or py > 0:
                            cv2.circle(img, (px, py), 4, (0, 255, 80), -1)

        # Kapi-paritesi (dusman-dogrulama 2026-08-27): raw_fgs/action_units/fgs_bantlari
        # router yanitinda vardi ama burada YOKTU -> GPU profilinde AU dokumu + A4
        # olcum-band paneli sessizce hic cikmiyordu. Bantlar TEK-KAYNAK modul fonksiyonundan.
        from ai_hub.cat_landmark.inference_cat_landmark import fgs_bantlari as _fgs_bantlari_tek

        return {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": infer_ms,
            "detected": detected,
            "fgs_total": (fgs.get("fgs_total") if detected else None),
            "fgs_bantlari": _fgs_bantlari_tek(),
            "raw_fgs": (fgs if detected else None),
            "action_units": (fgs.get("action_units") if detected else None),
            "pain_level": (fgs.get("pain_level", "Unknown") if detected else "Kedi yüzü tespit edilemedi"),
            "image_base64": _jpg_b64(img),
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ── Faz 2c: termal (görüntü, GPU), cat_organ (görüntü 3B, GPU) ──
_GECERLI_CAM = ("gradcam++", "gradcam", "eigencam", "hirescam")


@app.post("/infer/thermal")
def infer_thermal(file: UploadFile = File(...), explain: str = Form(None), xai_method: str = Form(None)):
    """Termal görüntü → sağlık sınıflandırma (GhostNetV2 ONNX, GPU).

    explain=true → Grad-CAM ısı haritası (Faz 2 paritesi — router ile TEK-KAYNAK
    ai_hub.cat_thermal.xai_termal_isi_haritasi; GPU'da PT Grad-CAM 200-500 ms).
    ⚠️ Açıklama İKİNCİL: hatası analizi düşürmez (xai_error).
    """
    # A6 allowlist paritesi (dusman-dogrulama 2026-08-27): router 422 veriyordu, burasi
    # yazim-hatasini zarif-dususe yutuyordu -> cagiran yontem adinin hatali oldugunu ogrenemiyordu.
    if xai_method is not None and xai_method not in _GECERLI_CAM:
        return JSONResponse({"error": f"xai_method geçersiz: {xai_method}"}, status_code=422)
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "thermal")
        if _red:
            return _red
        clf = predictors.get("thermal")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        result = clf.predict(tmp, threshold=0.5)
        dev = clf.session.get_providers()[0].replace("ExecutionProvider", "").lower()
        yanit = {"status": "success", "device": dev, "inference_ms": round((time.time() - t0) * 1000, 1), **result}
        if str(explain).lower() == "true":
            try:
                from ai_hub.cat_thermal import inference_cat_thermal as _ict

                _x = _ict.xai_termal_isi_haritasi(tmp, None, xai_method or "gradcam++")
                yanit["xai_image_base64"] = _x["xai_image_base64"]
                yanit["xai_method"] = _x.get("method")
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("Termal XAI üretilemedi (analiz etkilenmedi): %s", xe)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


@app.post("/infer/cat_organ")
def infer_cat_organ(file: UploadFile = File(...), target_oid: int = Form(None)):
    """Kedi görüntüsü → 10 organ 3B lokalizasyon (3 ONNX) + overlay (GPU).
    target_oid (ops): AI Pro seçili organı → overlay o organa odaklanır (CPU-parite; 0/None=Tüm Vücut)."""
    import cv2

    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "cat_organ")
        if _red:
            return _red
        clf = predictors.get("cat_organ")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        _toid = (int(target_oid) or None) if target_oid is not None else None
        result = clf.predict(tmp, render=True, target_oid=_toid)
        infer_ms = round((time.time() - t0) * 1000, 1)
        overlay = result.get("_overlay_bgr")
        image_b64 = None
        if overlay is not None:
            oh, ow = overlay.shape[:2]
            scale = min(1.0, 1280.0 / max(oh, ow))
            if scale < 1.0:
                overlay = cv2.resize(overlay, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
            image_b64 = _jpg_b64(overlay)
        organs = result.get("organs") or {}
        organs_list = [
            {
                "id": int(oid),
                "name": o.get("name"),
                "coord_3d_cm": o.get("coord_3d_cm"),
                "coord_cabin_cm": o.get("coord_cabin_cm"),
                "reliability": o.get("reliability"),
                # Sunum-katmanı XAI paritesi (2026-08-26): router GPU yolunda da güven dökümü
                # taşınsın (_extract_organ_target 8. eleman) — kapı-paritesi dersi.
                "reliability_components": o.get("reliability_components"),
                "calibrated": o.get("calibrated"),
            }
            for oid, o in sorted(organs.items(), key=lambda kv: int(kv[0]))
        ]
        return {
            "status": "success",
            "device": getattr(clf, "device", "?"),
            "inference_ms": infer_ms,
            "n_organs": len(organs_list),
            "organs": organs_list,
            "pose_type": (result.get("pose_classifier") or {}).get("type"),
            # Kapi-paritesi (dusman-dogrulama 2026-08-27): A2 rozetleri router'da vardi,
            # burada YOKTU -> GPU dagitiminda ayna/anatomik uyarilar hic gorunmuyordu.
            "mirror_warning": bool((result.get("pnp_fit") or {}).get("mirror_warning")),
            "anatomic_consistency": result.get("anatomic_consistency"),
            "image_base64": image_b64,
        }
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ── Faz 2c: JSON girdili uçlar (küçük/CPU modeller) ──
@app.post("/infer/disease")
def infer_disease(payload: dict = Body(...)):
    """Kedi hastalık (XGBoost) — JSON: age,weight,hr,temp,duration,symptom_indices."""
    try:
        # ⚠️ ASGARİ GİRDİ KAPISI — MODEL YÜKLEMESİNDEN ÖNCE (2026-08-16 dersinin aynısı:
        # reddedilecek istek için ağırlık yüklenmesin) ve router ile AYNI nesneden.
        _vital_kapisi(payload)
        clf = predictors.get("disease")
        t0 = time.time()
        results = clf.predict(
            payload.get("age", 0.0),
            payload.get("weight", 0.0),
            payload.get("hr", 0.0),
            payload.get("temp", 0.0),
            payload.get("duration", 0.0),
            payload.get("symptom_indices", []),
        )
        formatted = [{"disease": d, "probability": p} for d, p in results]
        top_p = max((float(p) for _, p in results), default=0.0)
        yanit = {
            "status": "success",
            "device": "cpu",
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "results": formatted,
            "top_probability": round(top_p, 3),
            "low_confidence": top_p < 0.40,
        }
        # Sunum-katmanı XAI paritesi (2026-08-26): router'daki explain=true buraya da düşer
        # (delegate_json payload'ı aynen taşır) — TEK-KAYNAK ai_hub.xai_top_features.
        # ⚠️ Açıklama İKİNCİL: hatası analizi düşürmez (router ile aynı zarif düşüş).
        if payload.get("explain"):
            try:
                from ai_hub.cat_disease import inference_cat_disease as _icd

                yanit["xai"] = _icd.xai_top_features(
                    clf,
                    payload.get("age", 0.0),
                    payload.get("weight", 0.0),
                    payload.get("hr", 0.0),
                    payload.get("temp", 0.0),
                    payload.get("duration", 0.0),
                    payload.get("symptom_indices", []),
                )
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("cat_disease XAI üretilemedi (analiz etkilenmedi): %s", xe)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    # ⚠️ SIRA KRİTİK: bu kol `except Exception`dan ÖNCE gelmeli, yoksa `_err500` onu yutup 500
    # döner ve kullanıcı reddin SEBEBİNİ göremez (aynı sınıf hata bu turda bir kez yaşandı).
    except _AsgariGirdiYok as ag:
        return JSONResponse({"error": ag.user_message(), "insufficient_input": True}, status_code=422)
    except Exception as e:
        return _err500(e)


@app.post("/infer/kidney_disease")
def infer_kidney_disease(payload: dict = Body(...)):
    """İnsan KBH (ExtraTrees ONNX) — JSON: 24 klinik özellik."""
    try:
        # ⚠️ ASGARİ GİRDİ KAPISI — MODEL YÜKLEMESİNDEN ÖNCE (2026-08-16 dersinin aynısı:
        # reddedilecek istek için ağırlık yüklenmesin) ve router ile AYNI nesneden.
        # XAI bayrağını klinik alanlardan AYIR (router ile aynı sözleşme).
        explain = bool(payload.pop("explain", False)) if isinstance(payload, dict) else False
        _ckd_kapisi(payload)
        from ai_hub.inference_human_kidney_disease import predict_one

        t0 = time.time()
        r = predict_one(payload)
        yanit = {
            "status": "success",
            "device": "cpu",
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "prob_ckd": r["prob_ckd"],
            "prob_pct": round(r["prob_ckd"] * 100, 1),
            "label": r["label"],
            "model": r.get("model"),
        }
        # Sunum-katmanı XAI paritesi (2026-08-26): TEK-KAYNAK xai_top_features; hatası
        # analizi düşürmez (router ile aynı zarif düşüş).
        if explain:
            try:
                from ai_hub import inference_human_kidney_disease as _ihd

                yanit["xai"] = _ihd.xai_top_features(payload)
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("CKD XAI üretilemedi (analiz etkilenmedi): %s", xe)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    except _AsgariGirdiYok as ag:  # ⚠️ `except Exception`dan ÖNCE (yukarıdaki gerekçe)
        return JSONResponse({"error": ag.user_message(), "insufficient_input": True}, status_code=422)
    except Exception as e:
        return _err500(e)


@app.post("/infer/rna")
def infer_rna(file: UploadFile = File(...), explain: str = Form(None)):
    """Böbrek RNA-seq CSV (satır=hasta, sütun=gen) → KIRC sınıflandırma (MLP ONNX).

    explain=true → hasta başına IG top-gen katkıları (Faz 2 paritesi — TEK-KAYNAK
    xai_top_genler; router ile aynı N<=25 sınırı).
    """
    try:
        import io as _io

        import pandas as pd

        data = file.file.read()
        if len(data) < 50:
            return JSONResponse({"error": "CSV boş/çok küçük"}, status_code=400)
        df = pd.read_csv(_io.BytesIO(data), index_col=0)
        if df.shape[0] == 0:
            return JSONResponse({"error": "CSV boş — hasta satırı yok"}, status_code=400)
        pred = predictors.get("kidney_rna")
        if getattr(pred, "expected_cols", None) and df.shape[1] != pred.expected_cols:
            return JSONResponse(
                {"error": f"gen sütun sayısı uyuşmuyor: beklenen {pred.expected_cols}, gelen {df.shape[1]}"},
                status_code=400,
            )
        t0 = time.time()
        predictions = pred.predict(df)
        yanit = {
            "status": "success",
            "device": "cpu",
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "n_patients": len(predictions),
            "classes": pred.classes,
            "predictions": predictions,
        }
        if str(explain).lower() == "true":
            if len(df) > 25:
                yanit["xai_error"] = "Açıklama en fazla 25 hastalık CSV için üretilir (IG maliyeti)."
            else:
                try:
                    from ai_hub.inference_human_kidney_rna import inference_human_kidney_rna as _ihr

                    yanit["xai"] = _ihr.xai_top_genler(df)
                except Exception as xe:
                    import logging as _lg

                    _lg.getLogger("ai_service").warning("RNA XAI üretilemedi: %s", xe)
                    yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    except Exception as e:
        return _err500(e)


# ── Faz kalan: reticulocytes (YOLO detect) + em_fantom/em_petri (kabin-CV pipeline) ──
@app.post("/infer/reticulocytes")
def infer_reticulocytes(file: UploadFile = File(...), explain: str = Form(None)):
    """Kan mikroskop görüntüsü → YOLOv8s retikülosit tespiti + sayım + overlay (GPU).

    explain=true → EigenCAM ısı haritası (Faz 2 paritesi — TEK-KAYNAK
    ai_hub.feline_reticulocytes.xai_retikulosit_isi_haritasi).
    """
    tmp = None
    try:
        data = file.file.read()
        if len(data) < 200:
            return JSONResponse({"error": "görüntü boş/çok küçük"}, status_code=400)
        _red = _kapi(data, "reticulocytes")
        if _red:
            return _red
        model = predictors.get("reticulocytes")
        tmp = _save_temp(data, ".jpg")
        t0 = time.time()
        results = model.predict(source=tmp, conf=0.25, iou=0.7, imgsz=640, device=_yolo_device(), verbose=False)
        r = results[0]
        n = len(r.boxes) if r.boxes is not None else 0
        yanit = {
            "status": "success",
            "device": _yolo_device(),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            "n_detections": int(n),
            "image_base64": _jpg_b64(r.plot()),
        }
        if str(explain).lower() == "true":
            try:
                from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as _ifr

                _x = _ifr.xai_retikulosit_isi_haritasi(tmp)
                yanit["xai_image_base64"] = _x["xai_image_base64"]
                yanit["xai_method"] = _x.get("method")
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("Retikülosit XAI üretilemedi: %s", xe)
                yanit["xai_error"] = "Açıklama üretilemedi"
        return yanit
    except Exception as e:
        return _err500(e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def _prov_dev(session):
    try:
        return session.get_providers()[0].replace("ExecutionProvider", "").lower()
    except Exception:
        return "?"


@app.post("/infer/em_fantom")
def infer_em_fantom(
    file: UploadFile = File(...),
    phantom_length_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
):
    """Fantom tümör: klasik CV + BiLSTM (D/P/E). phantom_length_cm ile gerçek-mm ölçek."""
    try:
        data = file.file.read()
        _red = _kapi(data, "em_fantom")
        if _red:
            return _red
        img = _read_bgr(data)
        c = predictors.get("em_fantom")
        pl = c["cls"](c["cfg"], phantom_length_cm=phantom_length_cm, manual_fallback=False)
        pl._predictor = c["predictor"]  # önbellekli predictor enjekte (router deseni)
        t0 = time.time()
        result, ctx = pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum)
        infer_ms = round((time.time() - t0) * 1000, 1)
        overlay = pl.render_panels(ctx, result, lang="tr")["07_combined"] if result.success else img
        payload = result.to_dict()
        # §KALAN A5 (router paritesi): ilk tumor bolgesi icin hafif duyarlilik meta'si.
        # Aciklama IKINCIL — hatasi analizi ASLA dusurmez (zarif). Sync uc (threadpool)
        # oldugundan dogrudan cagri yeterli; 7+1 ONNX forward ~ms mertebesi.
        _xai_meta = {}
        if result.success and payload.get("tumor_regions"):
            try:
                from ai_hub.inference_em_fantom import inference_em_fantom as _ief

                _r0 = payload["tumor_regions"][0]
                _c = list(_r0.get("centroid_cabin_mm") or (0.0, 0.0, 0.0))
                # Baz-nokta = tahminin FIILEN kullandigi nokta (dusman-dogrulama 2026-08-27:
                # 'or 0.0' cfg-default'la [B=0.001, duty=2.4] celisiyordu — pipeline ikamesiyle birebir).
                _B = achieved_B if achieved_B is not None else float(c["cfg"].phantom.achieved_B)
                _D = duty_sum if duty_sum is not None else float(c["cfg"].phantom.duty_sum)
                _xai_meta["xaiSensitivity"] = _ief.xai_hizli_sensitivity(
                    c["predictor"], _c[0], _c[1], _c[2], _r0.get("organ_id", 1), _B, _D
                )
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("em_fantom XAI meta uretilemedi (analiz etkilenmedi): %s", xe)
        return {
            "status": "success" if result.success else "no_detection",
            "device": _prov_dev(c["predictor"].session),
            "inference_ms": infer_ms,
            "success": result.success,
            "error": result.error,
            "n_tumor": result.n_tumor,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "tumor_regions": payload["tumor_regions"],
            "healthy_regions": payload["healthy_regions"],
            "timing_ms": result.timing_ms,
            "image_base64": _jpg_b64(overlay),
            **_xai_meta,
        }
    except Exception as e:
        return _err500(e)


@app.post("/infer/em_petri")
def infer_em_petri(
    file: UploadFile = File(...),
    petri_diameter_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
):
    """Petri kuyu: YOLO-seg + klasik CV + BaggingRegressor. petri_diameter_cm ile gerçek-mm."""
    from dataclasses import asdict

    try:
        data = file.file.read()
        _red = _kapi(data, "em_petri")
        if _red:
            return _red
        img = _read_bgr(data)
        c = predictors.get("em_petri")
        pl = c["cls"](
            c["cfg"], petri_diameter_cm=petri_diameter_cm, yolo_model_path=c["yolo_path"], yolo_device=_yolo_device()
        )
        pl.yolo = c["yolo"]
        pl._predictor = c["predictor"]
        t0 = time.time()
        result, ctx = pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum)
        infer_ms = round((time.time() - t0) * 1000, 1)
        overlay = pl.render_panels(ctx, result, lang="tr")["07_combined"] if result.success else img
        wells = [asdict(w) for w in result.wells]
        # §KALAN A5 (router paritesi): ilk kuyu icin hafif duyarlilik meta'si (zarif).
        _xai_meta = {}
        if result.success and wells:
            try:
                from ai_hub.inference_em_petri import inference_em_petri as _iep

                _w0 = wells[0]
                _c = list(_w0.get("centroid_cabin_mm") or (0.0, 0.0, 0.0))
                _B = achieved_B if achieved_B is not None else float(c["cfg"].phantom.achieved_B)
                _D = duty_sum if duty_sum is not None else float(c["cfg"].phantom.duty_sum)
                _xai_meta["xaiSensitivity"] = _iep.xai_hizli_sensitivity(
                    c["predictor"], _c[0], _c[1], _c[2], _w0.get("organ_id", 1), _B, _D
                )
            except Exception as xe:
                import logging as _lg

                _lg.getLogger("ai_service").warning("em_petri XAI meta uretilemedi (analiz etkilenmedi): %s", xe)
        return {
            "status": "success" if result.success else "no_detection",
            "device": _prov_dev(c["predictor"].session),
            "inference_ms": infer_ms,
            "success": result.success,
            "error": result.error,
            "n_wells": result.n_wells,
            "n_cancer": result.n_cancer,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "wells": wells,
            "timing_ms": result.timing_ms,
            "image_base64": _jpg_b64(overlay),
            **_xai_meta,
        }
    except Exception as e:
        return _err500(e)


@app.post("/infer/em_kedi")
def infer_em_kedi(payload: dict = Body(...)):
    """AI Pro bobin-sürüş: em_kedi (BiLSTM_XXL_Raw ONNX, GPU) → D1-7/P1-7/result_E.
    JSON: x,y,z (mm) + organ_id + achieved_B(ops) + duty_sum(ops). AI Pro loop/frame'in AĞIR
    sürüş-inference'ını GPU'ya devreder (çekirdek _predict_and_drive ai_service_enabled'da çağırır)."""
    try:
        pred = predictors.get("em_kedi")
        t0 = time.time()
        result = pred.predict(
            x=float(payload.get("x", 0.0)),
            y=float(payload.get("y", 0.0)),
            z=float(payload.get("z", 0.0)),
            organ_id=int(payload.get("organ_id", 0)),
            achieved_B=float(payload.get("achieved_B", 0.001)),
            duty_sum=float(payload.get("duty_sum", 2.0)),
        )
        # numpy skalerlerini JSON-serileştirilebilir float'a çevir (aksi halde json.dumps patlar).
        out = {}
        for k, v in result.items():
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
        return {
            "status": "success",
            "device": _prov_dev(pred.session),
            "inference_ms": round((time.time() - t0) * 1000, 1),
            **out,
        }
    except Exception as e:
        return _err500(e)
