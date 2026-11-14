# Author: mertaygn, cglrgrkn
import asyncio
import base64
import logging
import math as _math
import os
import sys

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from servers import ai_pro_hedef  # AI Pro hedef saglayicilari (kedi | fantom | petri)
from servers.ai_client import (
    ai_service_enabled,
    delegate_infer,
    delegate_infer_sync,  # mikroservis: AI'yı GPU servisine devret (bayraklı; sync=AI Pro loop)
    delegate_json,
    delegate_json_sync,
)
from servers.entitlement import ai_queue_gate, require_research  # tier-enforcement (flag-gated, fail-open)

logger = logging.getLogger("ai_router")

# (A9) modul-duzeyi `import threading` KALDIRILDI: _model_lock artik utils.agir_import._KILIT.
import time

from utils import estop_mandali  # D1.81 · Y4: acil durdurma mandalı + sürüş nesli
from utils.dongu_guvenligi import dongu_hatasini_bildir
from utils.model_downloader import ModelButunlukHatasi, download_model_sync
from utils.ses_kalitesi import guvenilir_mi as ses_guvenilir_mi
from utils.ses_kalitesi import normalize_entropi as ses_normalize_entropi
from utils.ses_kalitesi import sessiz_mi as ses_sessiz_mi
from utils.ses_kalitesi import wav_rms_dbfs as ses_wav_rms_dbfs
from utils.stm32_protocol_limits import (
    AI_PRO_DUTY_MAX_RATIO,
    normalize_ai_pro_duty_ratio,
    normalize_phase_deg,
)

# RNA CSV (20531 gen × N hasta) ve ses base64 yüklemeleri, Starlette multipart part-limitini
# (varsayılan 1MB — YALNIZ non-file form alanlarına uygulanır; dosya part'ları diske spool → limitsiz)
# aşabilir. audit B-2.3: eski çözüm Starlette İÇ sınıfı MultiPartParser.__init__'i GLOBAL monkeypatch
# ediyordu → sürüm yükseltmesinde SESSİZCE kırılabilirdi. Artık DESTEKLENEN request.form(max_part_size=)
# API'si + router-düzeyi dependency: yalnız multipart isteklerde limiti yükseltir, JSON gövdeye
# DOKUNMAZ; form'u request._form'a cache'ler → FastAPI'nin File/Form çözümü aynı cache'i kullanır.
_RNA_MAX_PART = 50 * 1024 * 1024  # 50 MB (~350 hasta RNA CSV'si)


async def _allow_large_upload(request: Request) -> None:
    """Büyük multipart yüklemeler için part-limitini yükselt (yalnız multipart; JSON gövdeye dokunmaz)."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        await request.form(max_part_size=_RNA_MAX_PART)


# JETON-SISTEMI Adım 4 (2026-08-22): jeton kapısı router-seviyesinde — entitlement/ai_queue_gate
# ile aynı desen. `PEMF_JETON_ENFORCED` KAPALIYKEN tam no-op (bugünkü canlı; satış açılmadı).
# ⚠️ Tedavi/kontrol uçları bu router'da DEĞİL ve jeton onları ASLA kapılamaz — yapısal kilit:
# tests/test_jeton_gate.py::test_KRITIK_GUVENLIK_tedavi_uclari_jeton_kapisinin_ARKASINDA_DEGIL
# SG.G4-5 / G5-4 (2026-10-14): `jeton_gate` yalnız KARAR verir (402 aynen); jeton `jeton_tuketimi` ile uç İSTİSNASIZ dönünce düşer
# (`scope="function"`: yanıt gönderilmeden önce) — reddedilen (422), düşen (500) ya da istemcisi kopan analiz ücretlenmez.
from servers.jeton import jeton_gate, jeton_tuketimi, sonuc_izle  # noqa: E402

ai_router = APIRouter(
    dependencies=[
        Depends(_allow_large_upload),
        Depends(ai_queue_gate),
        Depends(jeton_gate),
        Depends(jeton_tuketimi, scope="function"),
    ]
)


from utils import ceviri, kabin_kamerasi
from utils.image_domain import DomainMismatch as _ImgDomainMismatch

# ⚠️ ASGARİ GİRDİ KAPILARI — TEK KAYNAK `utils/klinik_asgari.py` (denetim 2026-08-17).
# Bu kapılar eskiden BURADA GÖMÜLÜ koddu, dolayısıyla `:8100` (auth-muaf, backend'i atlayan
# istemci) tarafında HİÇ çalışmıyordu: boş gövdeyle "Conjunctivitis %53" ve "ckd %78" dönüyordu.
from utils.klinik_asgari import AsgariGirdiYok as _AsgariGirdiYok
from utils.klinik_asgari import ckd_kapisi as _ckd_kapisi
from utils.klinik_asgari import vital_kapisi as _vital_kapisi
from utils.panel_yayin import PANEL_ADLARI as _PANEL_ADLARI
from utils.panel_yayin import PETRI_PANEL_ADLARI as _PETRI_PANEL_ADLARI
from utils.panel_yayin import kok_gorseli_sec as _kok_gorseli_sec
from utils.panel_yayin import panelleri_yayina_hazirla as _panelleri_hazirla

from servers import ai_kapi_metni


def _panel_adlarini_cevir(yanit, adlar: dict):
    """I18NI-A3.2: GPU mikroservisinden gelen `paneller[].ad`ı İSTEK dilinde yeniden kur (servis katalog taşımaz — `k` döner).
    Bilinmeyen anahtar / panelsiz yanıt aynen geçer (eski servis Türkçe `ad` gönderse de tablo anahtarı varsa çevrilir)."""
    if isinstance(yanit, dict):
        for p in yanit.get("paneller") or ():
            if isinstance(p, dict) and (panel_anahtari := adlar.get(p.get("k"))):
                p["ad"] = ceviri.t(panel_anahtari)
    return yanit


def _ai_fail(label, e: Exception) -> HTTPException:
    """AI uç hatası (audit B-4.1): gerçek nedeni SUNUCU-TARAFI logla; istemciye ham str(e)/traceback
    SIZDIRMA (bilgi ifşası — bu uçlar auth-muaf/publik). İstemciye yalnız kısa etiket döner.

    2026-08-06: HTTPException AYNEN geçirilir. Tüm görüntü uçları `except Exception → _ai_fail`
    deseni kullanıyor; bu, `_decode_image`'in ürettiği ANLAMLI istemci hatalarını (alan uyuşmazlığı
    422, boyut/çözünürlük sınırı) yutup hepsini "500 <etiket>"e çeviriyordu → kullanıcı "Analiz
    hatası" görüp NEDENİNİ öğrenemiyordu. Tek noktada düzeltildi (10 uçta tekrar gerekmez)."""
    # I18N-P1: `label` metin YA DA `dil → metin` (`lambda d: ceviri.t("…", dil=d)`): günlük HER ZAMAN Türkçe, yanıt istek dilinde.
    if isinstance(e, HTTPException):
        return e
    # D3.48 · Y18 (sahip): model bütünlük reddi → 503 + AÇIK uyarı (hangi dosya); manuel seans ve ACİL DURDUR etkilenmez. Modüller
    # indirme / yükleme hatasını sarabildiği için zincire ve iletiye bakılır (ör. em_kedi `MODEL_DOWNLOAD_ERROR` metni).
    _b = _butunluk_hatasi(e)
    if _b is not None or _BUTUNLUK_ILETISI in str(e):
        logger.error("%s — MODEL BÜTÜNLÜK REDDİ (analiz kapatıldı): %s", label("tr") if callable(label) else label, e)
        _dosya = os.path.basename(_b.dosya) if _b is not None else "?"
        return HTTPException(status_code=503, detail=ceviri.t("ai.hata.modelButunluk", dosya=_dosya))
    logger.exception("%s", label("tr") if callable(label) else label)
    return HTTPException(status_code=500, detail=label(None) if callable(label) else label)


#: `utils.model_downloader.ModelButunlukHatasi` iletisinin değişmez başı (sarılmış hata metinlerinde aranır).
_BUTUNLUK_ILETISI = "model butunluk denetimi gecmedi"


def _butunluk_hatasi(e: BaseException):
    """D3.48: istisna zincirindeki model bütünlük reddi (yoksa None)."""
    from utils.model_downloader import ModelButunlukHatasi

    gorulen: set = set()
    x = e
    for _ in range(8):
        if x is None or id(x) in gorulen:
            break
        gorulen.add(id(x))
        if isinstance(x, ModelButunlukHatasi):
            return x
        x = x.__cause__ or x.__context__
    return None


def _kok_neden_zinciri(e: BaseException, sinir: int = 5) -> str:
    """İstisna zincirini ('__cause__') tek satırlık okunur köke indirger.

    ⚠️ SAHA DERSİ (2026-08-27): scratch modülü `ImportError`ı sabit bir "model paketi
    gerekli" metnine sarıyor, router da onu loglamadan 503'e çeviriyordu. Sahadaki
    kullanıcı KURULU bir model için "model yok" görüyor, destek ise hiçbir kayıt
    bulamıyordu. Zincir artık ilk halkadan köke kadar tek satırda yazılır —
    "yeni model eklendi, sessizce çalışmıyor" sınıfının teşhis anahtarı budur.
    """
    parcalar = []
    gecerli: BaseException | None = e
    for _ in range(sinir):
        if gecerli is None:
            break
        parcalar.append(f"{type(gecerli).__name__}: {gecerli}")
        gecerli = gecerli.__cause__ or gecerli.__context__
    return " ⇐ ".join(parcalar) or "?"


# ── PETRİ MAKULLİK REDDİ (2026-08-06, sahip bildirimi) ────────────────────────────────────
# Denetimin KENDİSİ ai_hub boru hattındadır (mikroservis yolunda da çalışsın diye — bkz.
# ai_hub/inference_petri_dish/plausibility.py). Burada YALNIZ HTTP çevrimi yapılır.
# Sabit dize bilerek KOPYALANDI: `ai_hub...petri_cv_v2` paketini modül seviyesinde import etmek
# onnxruntime/ultralytics zincirini her açılışta yükletirdi ve mikroservis modunda ai_hub hiç
# gerekmez. Değer bir TEL SÖZLEŞMESİDİR (JSON `error` alanı); tests/test_petri_plausibility.py
# iki tarafın eşitliğini kilitler → sessizce ayrışamaz.
_PETRI_NOT_PLATE = "not_a_petri_plate"


def _petri_reject_message(plausibility) -> str:
    """Boru hattının ürettiği ölçümlü mesajı kullan; yoksa (mikroservis yanıtı `plausibility`
    alanını taşımıyor) ölçümsüz ama aynı yönlendirmeyi veren metne düş.
    I18NI-O.2: ileti istek dilinde katalogdan kurulur (boru hattının metni Türkçedir); Türkçe görünüm aynı."""
    return ai_kapi_metni.petri_ret_metni(plausibility)


from utils.path_utils import kaynak_kokunu_bul

# Proje ana dizinini bul
# ⚠️ SABIT DERINLIK KULLANMA (2026-09-18, klasor duzeni F4): burada eskiden
# `os.path.dirname(current_dir)` vardi ve depo kokunu "bir ust dizin" sayiyordu.
# `servers/` -> `apps/backend/servers/` tasinmasinda bu SESSIZCE `apps/backend`i
# gosterdi; `ai_hub/` depo KOKUNDE oldugu icin FGS bantlari (ve diger model yollari)
# bulunamaz oldu. Fonksiyon hata ATMIYOR, bos dict donuyordu -> panel sessizce
# kayboluyordu. Kapi: tests/test_xai_kalan_a_grubu.py yakaladi.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = str(kaynak_kokunu_bul(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Thread-safe lazy loading için model önbelleği
_models: dict = {}
# ⚠️ A9: model yükleyici ile derin-hazırlık probu AYNI süreç-geneli kilidi paylaşır.
# Ayrı `threading.Lock()` tutmak, `hazirlik?derin=1`in modelleri yüklerken aynı ağır
# modülleri paralel import etmesine izin veriyordu (yarı-kurulu torch → NameError: _C).
# Ayrıca RLock: ağır modüller birbirini import eder, düz Lock kendini kilitlerdi.
from utils.agir_import import _KILIT as _model_lock  # noqa: E402  (A9 — tek boğum)
from utils.agir_import import agir_import as _agir_import  # noqa: E402


def _get_or_load_model(key: str, loader_fn):
    """
    Thread-safe model yükleme yardımcısı.
    Model daha önce yüklendiyse direk döner.
    Yükleme sırasında kilidi tutar, hata olursa cache'i temizler.
    """
    if key in _models:
        return _models[key]
    with _model_lock:
        # Double-check after acquiring lock
        if key in _models:
            return _models[key]
        logger.info(f"Model yükleniyor: {key}")
        try:
            model = loader_fn()
            _models[key] = model
            logger.info(f"Model yüklendi ve önbelleğe alındı: {key}")
            return model
        except Exception as e:
            logger.error(f"Model yüklenemedi ({key}): {e}", exc_info=True)
            _models.pop(key, None)  # kırık model kalmasın
            raise


_MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB — tek görüntü üst sınırı (sınırsız upload = RAM DoS koruması)
_MAX_IMAGE_PIXELS = 50_000_000  # 50 MP — dekompresyon-bombası koruması (küçük dosya → dev BGR ayırma → OOM)


async def _decode_image(file, image_base64, *, label: str) -> np.ndarray:
    """UploadFile veya base64'ten BGR görüntü çöz. İki yaygın hatayı TEK yerde, tutarlı ele alır:
      (1) girdi yok, (2) 'görüntü yerine HTML geldi' (React fallback index.html gönderdi).
    Böylece görüntü-decode sorunu çıkınca bakılacak tek fonksiyon burasıdır (tekrar kaldırıldı).
    GÜVENLİK: girdi _MAX_IMAGE_BYTES ile sınırlanır → devasa upload ile RAM tüketimi (DoS) engellenir."""
    if image_base64:
        # base64 çözülünce ~%75'ine iner; çözmeden ÖNCE kaba string sınırı (dev RAM allocation'ı önle).
        if len(image_base64) > (_MAX_IMAGE_BYTES * 4) // 3 + 1024:
            raise ValueError(f"Görüntü çok büyük (base64 girdi > {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
        content = base64.b64decode(image_base64)
    elif file:
        # UploadFile.read(N): en fazla N bayt oku → tüm dosyayı RAM'e almadan sınırı aşanı reddet.
        content = await file.read(_MAX_IMAGE_BYTES + 1)
        if len(content) > _MAX_IMAGE_BYTES:
            raise ValueError(f"Görüntü çok büyük (> {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
    else:
        raise ValueError("Görüntü verisi bulunamadı.")
    if len(content) > _MAX_IMAGE_BYTES:
        raise ValueError(f"Görüntü çok büyük (> {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
    # Audit P2: dekompresyon-bombası guard — byte-limit yetmez (küçük PNG → dev BGR ayırma → OOM).
    # Decode ÖNCESİ header'dan boyutu oku (PIL lazy; piksel decode etmez); megapiksel eşiğini aşan reddet.
    try:
        import io as _io

        from PIL import Image as _PILImage

        with _PILImage.open(_io.BytesIO(content)) as _im:
            _w, _h = _im.size
            if _w * _h > _MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Görüntü çözünürlüğü çok yüksek ({_w}x{_h}px > {_MAX_IMAGE_PIXELS // 1_000_000}MP sınırı)."
                )
    except ValueError:
        raise
    except Exception:
        pass  # PIL header okuyamazsa cv2'ye bırak (bozuk/desteklenmeyen format zaten reddedilir)
    img = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        stripped = content.strip()
        logger.error("%s: görüntü decode edilemedi (boyut=%d, baş=%r)", label, len(content), content[:40])
        if stripped.startswith(b"<!DOCTYPE html>") or stripped.startswith(b"<html"):
            raise ValueError("Görüntü yerine HTML (index.html) alındı. React paketini kontrol edin.")
        raise ValueError(f"Geçersiz görüntü verisi. Alınan boyut: {len(content)} bytes.")
    # ALAN (modalite) DENETİMİ — 2026-08-06: sınıflandırıcılar eğitim dağılımının DIŞINDAKİ bir
    # girdiye de softmax ile %100 "güvenir" (Böbrek Patoloji'ye CT kesiti → "Grade 4 · %100").
    # Modelin güvenine güvenmek yerine girdinin modalitesini bağımsız ölç; kesin uyuşmazlıkta
    # 422 ile ANLAŞILIR bir mesaj dön (bkz. utils/image_domain.py). Kapatma: PEMF_AI_DOMAIN_GUARD=0
    try:
        from utils import image_domain as _imgdom

        _imgdom.check(img, label)
    except _ImgDomainMismatch as _dm:
        raise HTTPException(status_code=422, detail=ai_kapi_metni.alan_ret_metni(_dm)) from None
    except HTTPException:
        raise
    except Exception:
        # A-24 (sahip kararı) · D4.09: kapı İÇ HATADA REDDEDER — analiz yapılmaz, neden söylenir. Eskiden DEBUG + atla
        # (fail-open): kapı bozulunca yanlış modalite sessizce analize gidiyordu. Modalitesi BELİRLENEMEYEN girdi ve kuralı
        # olmayan etiket `check` içinde bilinçli olarak geçer (hata değil) → buraya düşmez.
        logger.warning("AI modalite kapısı çalıştırılamadı [%s] — analiz REDDEDİLDİ (A-24)", label, exc_info=True)
        try:
            _mesaj = ai_kapi_metni.denetim_calismadi()
        except Exception:
            _mesaj = ceviri.t("ai.alan.denetimKisa")
        raise HTTPException(status_code=422, detail=_mesaj) from None
    return img


async def _kapili_devret(name: str, label: str = None, *, file=None, image_base64: str = None, data: dict = None):
    """MODALİTE KAPISINI UYGULA, sonra GPU mikroservisine devret.

    ⚠️ DENETİM 2026-08-17 — KAPI, DEVRETMENİN ARKASINDA KALIYORDU. Her görüntü ucunda
    `if ai_service_enabled(): return await delegate_infer(...)` satırı, kapıyı çalıştıran
    `_decode_image(...)` satırından ÖNCE dönüyordu. `ai_service/app.py` ne modalite denetimi ne
    sessizlik kapısı içeriyor ve `docker/Dockerfile.ai` imaja `utils/`i HİÇ kopyalamıyor →
    mikroservis profilinde kapı TAMAMEN yoktu. Deneysel olarak ölçüldü (gerçek CT fixture'ı →
    Böbrek Patoloji ucu):
        GÖMÜLÜ mod      -> HTTP 422 "boyalı patoloji preparatı (H&E) bekliyor"
        MİKROSERVİS mod -> HTTP 200 {"top_1_class": "Grade 4", "top_1_prob": 1.0}
    Yani kapının var olma sebebi olan 2026-08-06 saha vakası ("CT → Grade 4 · %100") birebir
    geri gelmişti. Kapsam 8 uç: landmark, segmentation, thermal, reticulocytes, em_fantom,
    kidney_ct, histopath, cat_organ.

    ⚠️ GİRDİ TEK KEZ OKUNUR: `UploadFile.read()` ikinci çağrıda BOŞ döner, dolayısıyla "önce kapı,
    sonra devret" için baytları elde tutup mikroservise `image_base64` olarak vermek ZORUNLU.
    Böylece GPU servisi kapıdan geçen AYNI baytları alır (yeniden kodlama/kayıp yok).

    ⚠️ KAPSAM DIŞI (bilerek): (a) ses ucundaki sessizlik kapısı — ffmpeg transcode + RMS ölçümüne
    bağlı, devretmenin önüne almak ses hattını yeniden kurgulamak demek; (b) `:8100`e DOĞRUDAN
    yapılan çağrılar — deponun kendi kuralına göre (bkz. `ai_hub/inference_petri_dish/
    plausibility.py`) kalıcı çözüm kapıları `ai_hub/`e taşımaktır.

    Kilit: `tests/test_ai_mikroservis_modalite_kapisi.py` (karşıt-kanıt testleri dahil).
    """
    # ⚠️ `label` VARSAYILAN OLARAK `name`: sekiz çağrı yerinin hepsi aynı dizeyi İKİ KEZ
    # veriyordu ve bu, ileride `("histopath", "kidney_ct")` gibi bir yazım hatasının bobini değil
    # ama TEŞHİSİ yanlış modalite kapısından geçirmesine davetiyeydi (sessiz klinik hata).
    # Artık tek dize yeterli; farklı bir etiket ancak AÇIKÇA istenirse verilir.
    label = label or name
    if image_base64:
        b64 = image_base64
    else:
        if file is None:
            raise ValueError("Görüntü verisi bulunamadı.")
        content = await file.read(_MAX_IMAGE_BYTES + 1)
        if len(content) > _MAX_IMAGE_BYTES:
            raise ValueError(f"Görüntü çok büyük (> {_MAX_IMAGE_BYTES // (1024 * 1024)} MB sınırı).")
        b64 = base64.b64encode(content).decode("ascii")
    # Boyut/piksel sınırları + modalite denetimi KAPISI (uyuşmazlıkta HTTPException(422)).
    await _decode_image(None, b64, label=label)
    return await delegate_infer(name, image_base64=b64, data=data)


def _encode_jpg_b64(img: np.ndarray, quality: int | None = None) -> str:
    """BGR görüntüyü JPEG'e kodla → base64 string (opsiyonel kalite 0-100)."""
    params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)] if quality is not None else []
    _, buffer = cv2.imencode(".jpg", img, params)
    return base64.b64encode(buffer).decode("utf-8")


#: GÖSTERİM JPEG kalitesi. ⚠️ YALNIZ operatöre GÖSTERİLEN kareler için — model GİRDİSİ
#: olan kodlamalara UYGULANMAZ (bkz. `_localize_organ_gpu` notu).
#:
#: OpenCV varsayılanı q95'tir ve argüman verilmeyen her çağrı sessizce onu kullanır.
#: q85 görsel olarak ayırt edilemez ama dosyayı yarıya indirir (plan ölçümü: segmentasyon
#: 797→358 KB, termal 286→141 KB, fantom mozaik 1.646→364 KB).
#:
#: ⚠️ AYRICA PARİTE: gömülü backend q95, GPU mikroservisi q85 üretiyordu → AYNI analiz
#: dağıtıma göre 1,9× farklı boyutta dönüyordu. Tek sabit bunu da kapatır.
GOSTERIM_JPEG_KALITESI = 85

#: Çok panelli mozaiklerin (fantom/petri) en uzun kenar kapağı (px).
#: ⚠️ NEDEN GEREKLİ: `07_combined` 2×3 mozaiktir; dikey telefon fotoğrafında 6048×12256'ya
#: kadar çıkıyor ve q95 ile megabaytlarca JPEG üretiyordu. Kapak olmadan yalnız kalite
#: düşürmek YETMEZ — bağlayıcı kısıt ÇÖZÜNÜRLÜK.
MOZAIK_AZAMI_KENAR = 1600


def _kapakli_kodla(img: np.ndarray, azami: int = MOZAIK_AZAMI_KENAR) -> tuple[bytes, dict]:
    """Uzun kenarı `azami`ye indir (gerekirse), GÖSTERİM kalitesinde JPEG'e kodla.

    @return (jpeg_baytlari, {"image_w", "image_h"}) — boyut KODLANAN kareye aittir.

    ⚠️ BOYUT DA DÖNER, ÇÜNKÜ KAPAK KAREYİ KÜÇÜLTÜR. İstemcinin oran kilidi
    (`_kare_boyutu` sözleşmesi) ORİJİNAL boyutu alırsa kutu oranı yanlış hesaplanır ve
    üzerine çizilen işaretler canlı görüntüyle KAYAR — bu bir tıbbi karar ekranıdır.
    (ADIM 1 kapağı eklenince doğan tuzak; ADIM 2'de kapatıldı.)

    ⚠️ BÜYÜTME YAPMAZ (`min(1.0, ...)`): küçük bir görüntüyü şişirmek dosyayı büyütür,
    bilgi eklemez. `INTER_AREA` küçültmede doğru olan (moiré üretmez).
    """
    oh, ow = img.shape[:2]
    sc = min(1.0, float(azami) / max(oh, ow))
    if sc < 1.0:
        img = cv2.resize(img, (int(ow * sc), int(oh * sc)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), GOSTERIM_JPEG_KALITESI])
    if not ok:
        raise RuntimeError("JPEG kodlama basarisiz")
    return buf.tobytes(), _kare_boyutu(img)


def _kare_boyutu(img: np.ndarray) -> dict:
    """Kodlanan karenin GERÇEK boyutu — istemci oran kilidi için.  [S7 adım 4, 2026-09-04]

    ÖLÇÜLEN DURUM: yanıtlar yalnız `image_base64` taşıyordu; boyut burada zaten hesaplanıyor
    (küçültme için) ama ATILIYORDU. İstemci kutunun oranını bilemediği için kareyi kırpıyor,
    üzerine çizilen ORGAN İŞARETLERİ canlı görüntüyle kayıyordu (tıbbi karar ekranı).
    Alan YALNIZ-EK: eski istemciler yok sayar, yeni istemci yoksa varsayılana düşer.
    """
    h, w = img.shape[:2]
    return {"image_w": int(w), "image_h": int(h)}


class DiseaseInput(BaseModel):
    age: float = 0.0
    weight: float = 0.0
    hr: float = 0.0
    temp: float = 0.0
    duration: float = 0.0
    symptom_indices: list[int] = []
    # Sunum-katmanı XAI (2026-08-26): true → yanıta SHAP top-özellik katkıları eklenir
    # ("xai" alanı). Aynı uç/aynı jeton (Faz 0 karar #6: açıklama analizin parçası).
    explain: bool = False


@ai_router.post("/api/ai/disease")
async def analyze_disease(data: DiseaseInput):
    """XGBoost Kedi Hastalık Analizi"""
    # ── Girdi validasyonu — sıfır/boş vital ile anlamsız tahmin üretilmesin (audit P1).
    # Canlı bir kedide kilo/nabız/sıcaklık 0 olamaz; eksikse SESSİZ yanlış tahmin yerine
    # 422 dönüp kullanıcıdan geçerli vital iste.
    # ⚠️ Kapı `ai_service_enabled()` kontrolünden ÖNCE kalmalı: aksi hâlde mikroservis profilinde
    # router'daki koruma yine kaybolur. Gövde `utils/klinik_asgari`ye TAŞINDI (tek kaynak).
    try:
        _vital_kapisi(data.model_dump())
    except _AsgariGirdiYok as ag:
        raise HTTPException(status_code=422, detail=ai_kapi_metni.asgari_metni(ag)) from None

    try:
        if ai_service_enabled():
            return await delegate_json("disease", data.model_dump())

        def _load():
            from utils.model_downloader import download_model_sync

            download_model_sync("ai_hub/cat_disease/XGBoost.pkl")
            from ai_hub.cat_disease.inference_cat_disease import CatDiseasePredictor

            return CatDiseasePredictor()

        predictor = await asyncio.to_thread(_get_or_load_model, "disease", _load)
        results = predictor.predict(data.age, data.weight, data.hr, data.temp, data.duration, data.symptom_indices)

        # Sonuçlar list of tuples [('Hastalık A', 0.85), ...] formatında geliyor.
        formatted = [{"disease": d, "probability": p} for d, p in results]
        # Güven-eşiği: en yüksek olasılık düşükse FE "düşük güven — veteriner doğrulaması
        # gerekir" uyarısı göstersin (audit: güven-eşiği yoktu).
        top_p = max((float(p) for _, p in results), default=0.0)
        yanit = {
            "status": "success",
            "results": formatted,
            "top_probability": round(top_p, 3),
            "low_confidence": top_p < 0.40,
        }
        # Sunum-katmanı XAI (2026-08-26): SHAP TreeExplainer top-özellik katkıları.
        # ⚠️ Açıklama İKİNCİLDİR — hatası ana analizi ASLA düşürmez (zarif düşüş; plan §8).
        if data.explain:
            try:
                from ai_hub.cat_disease import inference_cat_disease as _icd

                yanit["xai"] = await asyncio.to_thread(
                    _icd.xai_top_features,
                    predictor,
                    data.age,
                    data.weight,
                    data.hr,
                    data.temp,
                    data.duration,
                    data.symptom_indices,
                )
            except Exception as xe:
                logger.warning("cat_disease XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                yanit["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        return yanit
    except Exception as e:
        logger.error(f"Disease inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.hastalikAnalizi", dil=d), e)


#: D1.88 (B-6.30 · A-19): Otonom Biofeedback'in ONAY yolu — eylem söyleyen TEK metin (uç 428 detayı).
def otonom_fgs_onay_mesaji() -> str:
    return ceviri.t("ai.pro.hata.otonomFgsOnay")


@ai_router.post("/api/ai/vision/landmark")
@sonuc_izle  # TD9: canlı kipte "yüz bulunamadı" karesi dakikayı ücretlendirmez
async def analyze_landmark(
    request: Request, file: UploadFile = File(None), image_base64: str = Form(None), auto_adjust: bool = Form(False)
):
    """YOLO Pose + FGS Ağrı Skoru — SALT ANALİZ (D1.88: bu uç cihazı SÜRMEZ)."""
    # ⚠️ D1.88 (B-6.30 · A-19, sahip kararı): FGS "Otonom Biofeedback" AI Pro MÜHRÜNE bağlıdır — öneri → hekim onayı →
    # mühür akışından geçmeden sürüş YOK. Eskiden `auto_adjust=true` (galeri fotoğrafı + istemcideki onay penceresi
    # yeterdi) 30 dk 8 bobinli "AI (Auto)" seansı açıyordu: `start_ai_session(…, range(1,9))` + ESP START yayını —
    # aynı durumda AI Pro 428 veriyor (onay asimetrisi ölçüldü, D0). Mühürlü seans varken de bu yol zaten sürmüyordu
    # (`_ai_loop_active` / aktif seans türü denetimi) → sürüş yolu KALDIRILDI. Sürüm kayması: eski istemci bayrağı
    # göndermeye devam edebilir → analiz yapılmadan 428 + eylem metni (çıkarım saniyelerini boşa harcamaz).
    # Mikroservis profilinde de AYNI (kapı devretmeden önce).
    if auto_adjust:
        raise HTTPException(status_code=428, detail=otonom_fgs_onay_mesaji())
    try:
        if ai_service_enabled():
            # NOT (D1.88): `auto_adjust` yukarıda 428 ile reddedildi — buraya yalnız SALT ANALİZ gelir; AI servisi de
            # yalnız analiz döner. Donanım biofeedback'i (eski "AI (Auto)" sürüşü) hiçbir profilde YOK.
            return await _kapili_devret("landmark", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="landmark")

        def _load_landmark():
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync

            path = download_model_sync("ai_hub/cat_landmark/yolo26m-pose.onnx")
            return YOLO(path, task="pose")

        model = await asyncio.to_thread(_get_or_load_model, "landmark", _load_landmark)

        # Görüntüyü gecici dosyaya kaydet çünkü predict file path istiyor.
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        try:
            _gecici_gorsel_yaz(tmp.name, img)
            results = await asyncio.to_thread(lambda: model.predict(tmp.name, conf=0.25, device="cpu", verbose=False))
        finally:
            # Hata olsa da geçici dosyayı temizle (disk şişmesini önle).
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        fgs_result = {}
        detected = False
        # D1.E09 (İG-5.31): sevk edilen model (`kpt_shape [48,2]`) nokta başına GÜVEN/GÖRÜNÜRLÜK kanalı vermez → örtülü
        # nokta (ör. kulak) da tahmin edilir ve FGS'yi değiştirebilir (ölçüldü: üst %30 örtülü → FGS 1→2, kabul). Görüntü
        # temelli görünürlük ölçütleri gerçek fotoğrafta yanlış ret / kaçırma verdi (D1D raporu §4 D1.E09) → skor
        # REDDEDİLMEZ, yanıt bunu AÇIKÇA söyler; arayüz uyarı satırı gösterir.
        _nokta_guveni_yok = False
        if results and len(results) > 0:
            r = results[0]
            if r.keypoints is not None and len(r.keypoints.xy) > 0 and r.boxes is not None and len(r.boxes) > 0:
                kp_xy = r.keypoints.xy[0].cpu().numpy()
                # Keypoint güven skoru (varsa): (0,0)/düşük-güvenli noktalar bozuk geometri -> sahte skor üretir.
                kp_conf = None
                try:
                    if r.keypoints.conf is not None:
                        kp_conf = r.keypoints.conf[0].cpu().numpy()
                except Exception:
                    kp_conf = None
                _nokta_guveni_yok = kp_conf is None
                x1, y1, x2, y2 = r.boxes[0].xyxy[0].cpu().numpy()
                bw = max(x2 - x1, 1.0)
                bh = max(y2 - y1, 1.0)
                kp_norm = kp_xy.copy()
                kp_norm[:, 0] = (kp_norm[:, 0] - x1) / bw
                kp_norm[:, 1] = (kp_norm[:, 1] - y1) / bh

                from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs

                fgs_result = compute_fgs(kp_norm)

                # GEÇERLİ TESPİT: skor >=0 + yeterli görünür keypoint + (varsa) makul güven.
                _ft = fgs_result.get("fgs_total", -1)
                _valid_kp = int(np.count_nonzero((kp_xy[:, 0] > 0) | (kp_xy[:, 1] > 0)))
                _conf_ok = True if kp_conf is None else (float(np.mean(kp_conf)) >= 0.20)
                if _ft is not None and _ft >= 0 and _valid_kp >= 20 and _conf_ok:
                    detected = True
                    for pt in kp_xy:
                        px, py = int(pt[0]), int(pt[1])
                        if px > 0 or py > 0:
                            cv2.circle(img, (px, py), 4, (0, 255, 80), -1)

        b64_image = _encode_jpg_b64(img, quality=GOSTERIM_JPEG_KALITESI)

        # KRİTİK: tespit yoksa FGS=0 "Ağrı Yok" YANLIŞ-GÜVENCESİ verme -> null + detected:false.
        if detected:
            total = fgs_result.get("fgs_total")
            pain_level = fgs_result.get("pain_level", "Unknown")
        else:
            total = None
            pain_level = "Kedi yüzü tespit edilemedi"

        # ⚠️ D1.88 (A-19): bu uç cihazı SÜRMEZ (sürüş isteği yukarıda 428). Alanlar eski istemciler için sabit kalır.
        hw_status = "idle"
        hw_params = {}

        return JSONResponse(
            content={
                "status": "success",
                "image_base64": b64_image,
                **_kare_boyutu(img),
                "detected": detected,
                "fgs_total": total,
                # §KALAN A4: olculen-deger-vs-populasyon-bandi paneli icin p5/p95
                # bantlari (thresholds_calibrated.json — kalibrasyon tek-kaynagi).
                "fgs_bantlari": _fgs_bantlari(),
                "pain_level": pain_level,
                "raw_fgs": fgs_result if detected else None,
                "action_units": fgs_result.get("action_units") if detected else None,
                # D1.E09: model nokta görünürlüğünü bildirmiyor → örtülü yüzde skor yanıltıcı olabilir (arayüz söyler).
                "nokta_gorunurlugu_dogrulanmadi": bool(detected and _nokta_guveni_yok),
                "hw_status": hw_status,
                "hw_params": hw_params,
            }
        )
    except Exception as e:
        logger.error(f"Landmark inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.landmark", dil=d), e)


# ── AI Pro durumu (modül seviyesi) ──
_ai_loop_active = False
#: D1.81 (İG-5.11): her `/ai/pro/start` döngüye YENİ bir numara verir (yalnız `_ai_loop_lock` altında yazılır).
#: Eski döngü bayrak `/stop`→`/start` ile ms içinde yeniden True olsa da numarası eskidiği için ÇIKAR; ölçüldü:
#: 15 hızlı stop/start'ta 14 döngü aynı anda canlıydı (tel sürüş hızı 2,5×).
_ai_dongu_no = 0
#: Otonom seansı BAŞLATAN istemcinin kimliği.
#
# ⚠️ DENETİM 2026-08-17: yalnız "durdurma yetkisini BASTIRMAK" için var, ASLA yetkilendirmek için
# DEĞİL. `/ai/pro/stop` gövdesiz ve herkese açık kalmaya devam ediyor (her istemcinin operatörü
# tedaviyi durdurabilmeli); uydurma bir `client_id` kimseye YENİ yetki vermez. Sorun tersiydi:
# AI Pro panelini yalnızca GÖRÜNTÜLEYEN ikinci istemci, sekmeden çıkınca unmount cleanup'ında
# `/ai/pro/stop` gönderip BAŞKASININ süren otonom seansını (7 bobin) sebep söylemeden kesiyordu.
# ⚠️ MÜHÜR İHLALİ DEĞİL: `client_id` bir TEDAVİ PARAMETRESİ değil; onaylanan D/P/organ/süre yine
# mühürlü kopyadan okunuyor.
_ai_owner_client = ""


def _ai_kare_yabanci(client_id) -> bool:
    """3. tur denetimi [B1] (2026-08-24): bu kare/istek AKTİF seansın SAHİBİ DIŞINDAN mı geliyor?

    YABANCI = sahip BİLİNİYOR (modern istemci start'ta client_id yolladı → `_ai_owner_client` dolu)
    AND gelen kimlik ONDAN FARKLI. Sahip boşsa (eski/anonim başlatım) → False (hiç bastırma yok;
    tek-eski-istemci sürüşü + geriye-uyum korunur).

    ⚠️ `bool(frame_client)` şartı KASITEN YOK (adversaryal tasarım-vetting Hole 1): kimliksiz kare
    de yabancı sayılmalı — yoksa alanı atlayan bir izleyici/saldırgan bastırmayı baypaslardı. Modern
    sahip kendi karesinde HER ZAMAN id taşıdığından (start'taki kimlikle aynı) yanlış-bastırma olmaz.

    ⚠️ KAYITLI SAHİP-KARARI KORUNUR: bu YENİ YETKİ VERMEZ (deny-only) — yabancı yalnız SÜRÜŞTEN /
    organ-değişiminden / relocalize'den men edilir; `/ai/pro/stop` GÖVDESİZ ve HERKESE AÇIK kalır,
    onaylanan D/P/organ/süre mührü değişmez. En fazla best-effort: aynı-klinik istemcisi sahibin
    id'sini /status'tan okuyup taklit ederse bastırma aşılır (client_id yetki belirteci değil) —
    ama B1'in KAZA senaryosu (iki hekim, ayrı telefon, rastgele id) kapanır.

    ⚠️ AKTİF-SEANS KAPISI (adversaryal kod-inceleme MAJOR bulgusu, 2026-08-25): _ai_owner_client YALNIZ
    /ai/pro/stop tarafından sıfırlanır; süre-dolumu / acil-durdur / dış /session/stop ile biten seansta
    STALE kalır. Aktif-seans kontrolü olmadan bu, BAŞKA bir modern istemciyi AI Pro'dan KALICI kilitlerdi
    (yabancı sayılır → kare localize etmez → propose 409 → owner'ı ezecek tek yol olan /start'a asla
    ulaşamaz). Bastırma bu yüzden YALNIZ gerçekten AKTİF sahipli seansta uygulanır; seans bitince
    (is_active=False) owner stale kalsa da bastırma YOK."""
    if not _ai_owner_client:
        return False
    try:
        import servers.api_server as _api

        with _api._session_lock:
            _s = _api._active_session
            _aktif = bool(_s.get("is_active")) and str(_s.get("mode", "")).startswith("AI")
    except Exception:
        _aktif = False
    if not _aktif:
        return False
    frame_client = str(client_id or "")[:64]
    return frame_client != _ai_owner_client


import threading as _ai_threading

# TOCTOU koruma: start/stop check-and-set atomik olsun → iki es-zamanli /ai/pro/start ikinci bir
# kamera loop'u acip VideoCapture(0)'i cakistiramasin / bobinleri cift suremesin.
_ai_loop_lock = _ai_threading.Lock()
_ai_thread = None
#: İG-5.1: `/frame`'de ARDIŞIK hedef kaybı sayacı — mühürdeki onaya bağlı (yeni seans sıfırlar). Döngünün
#: `_lost_streak` kuralının mobil kare karşılığı; eskiden `/frame`'de hiç yoktu (bkz. `_frame_hedef_durumu`).
_frame_kayip = {"onay": None, "seri": 0}
_frame_kayip_kilit = _ai_threading.Lock()
# 3. tur denetimi — WEB KAPALI-DÖNGÜ (2026-08-25): web/sunucu-kameralı yolda öneri ÖNCESİ
# lokalizasyon için HAZIRLIK önizleme loop'u. Kamerayı açar + seçili organı periyodik lokalize
# eder (cache'i günceller) ama BOBİN SÜRMEZ ve SEANS BAŞLATMAZ. Gerçek seans (/ai/pro/start)
# başlarken durur ve kamerayı bırakır → tek fiziksel kamera, çakışma yok. Telefondaki "hazırlık"ın
# sunucu-kamera karşılığı (1.9.22 mobil kapalı-döngü düzeltmesi web'e uygulanmamıştı).
_ai_hazirlik_active = False
_ai_hazirlik_thread = None
_ai_hazirlik_started_at = 0.0
_AI_HAZIRLIK_TAVAN_S = 120  # önizleme üst sınırı — kamera sonsuza dek tutulmasın (mobil HAZIRLIK_TAVAN paritesi)
# B3 (siyah ekran, 2026-09-03): önizleme thread'i kamera/model hatasıyla SESSİZCE ölüyordu; /baslat
# "success" demişti ve /status bunu hiç söylemiyordu → panel 120 sn "Hazırlanıyor…"da takılıyordu.
# Hata metni burada tutulur, /status `hazirlikHata` olarak verir, /baslat sıfırlar.
_ai_hazirlik_hata = ""
# Önizleme kare yayını aralığı (sn). Seans loop'u 1 Hz yayınlar; önizlemede operatör kadrajı ayarlar,
# biraz daha akıcı olsun ama WS kuyruğunu (64) boğmasın.
_AI_HAZIRLIK_YAYIN_ARALIK_S = 0.33
_ai_organ_id = 0
_ai_duration_min = 20
_ai_started_at = 0.0
# Klinik güvenlik: AI Pro seans süresi üst sınırı (Audit P1). Uzaktan {duration_minutes: 999999}
# ile günlerce/gözetimsiz PEMF sürüşünü engeller. (freq/duty güvenlik sınırı EKLEMEZ — sahip kararıyla kaldırıldılar;
# 48 °C termal kesme / interlock hiçbir katmanda YOK, A-47.)
_AI_PRO_MAX_DURATION_MIN = 120
# AI Pro freq SABİT 100 Hz — SAHİP KARARI (KD-3a, 11 Kasım tezgâh: kart her AI Pro sürüşünde F=1 alıyordu; "100hz olcak ai pro freq").
# Eskiden 1 Hz'di (yalnız "eski PyQt DDS varsayılanı"). Vekil doz modellerinin girdisinde frekans YOK → öneri (duty / faz) değişmez,
# yalnız karta giden F. Sabit; backend'de limit/clamp EKLEME. Kapı: tests/test_KD3a_dogrulama_2cm_AIPro_100Hz_kapi_eylemi.py
_AI_PRO_FREQ_HZ = 100.0
# ODK8 (sahip 13 Kasım 2026: "ai pro kısmına frekans seçme de koy 76 100 107 147"): seçilebilir AI Pro frekansları; seçim ÖNERİ MÜHRÜNE
# yazılır, `/start` seansın sürüş frekansını mühürden kurar (`_ai_pro_frek_hz`), durdurma 100'e döndürür. Varsayılan 100 (KD-3a kararı).
AI_PRO_FREKANSLARI = (76.0, 100.0, 107.0, 147.0)
_ai_pro_frek_hz = _AI_PRO_FREQ_HZ
# em_kedi modelinin sabit ekstra girdileri (eski camera_ai_thread ile birebir: 0.001 T = 1 mT · 1.5).
# ⚠️ D7.02 (DENETIM-12 P2): TEK KAYNAK `ai_pro_hedef.KEDI_*` — sürüş (`_predict_and_drive_cpu/_gpu`) bu adları, XAI açıklaması
# ve onay metası `KediSaglayici.achieved_B/duty_sum`'ı okur; iki ayrı literal sahip kararı #9'u ("açıklama dozun FİİLEN
# hesaplandığı girdilerle") yalnız TESADÜFEN tutuyordu. Adlar korunur (monkeypatch çıpaları). Kapı:
# tests/test_kedi_ai_pro_ek_girdileri_TEK_KAYNAK_D7_02.py
_AI_ACHIEVED_B = ai_pro_hedef.KEDI_ACHIEVED_B
_AI_DUTY_SUM = ai_pro_hedef.KEDI_DUTY_SUM
#: Organ kimliği → ad işlevi (`ai.organ.*`; anahtarlar AÇIK yazılır — dinamik anahtar yok). Ad `mode` VERİSİNE de girer (`AI Pro · model · organ`) → veri için `dil="tr"`.
_ORGAN_ADLARI = {
    0: lambda dil: ceviri.t("ai.organ.tumVucut", dil=dil),
    1: lambda dil: ceviri.t("ai.organ.mide", dil=dil),
    2: lambda dil: ceviri.t("ai.organ.bobrek", dil=dil),
    3: lambda dil: ceviri.t("ai.organ.karaciger", dil=dil),
    4: lambda dil: ceviri.t("ai.organ.mesane", dil=dil),
    5: lambda dil: ceviri.t("ai.organ.pankreas", dil=dil),
    6: lambda dil: ceviri.t("ai.organ.bagirsak", dil=dil),
    7: lambda dil: ceviri.t("ai.organ.kalp", dil=dil),
    8: lambda dil: ceviri.t("ai.organ.dalak", dil=dil),
    9: lambda dil: ceviri.t("ai.organ.akcigerSag", dil=dil),
    10: lambda dil: ceviri.t("ai.organ.akcigerSol", dil=dil),
}


def _organ_adi(hedef_id, dil: str | None = "tr") -> str:
    """Organ adı. Varsayılan Türkçe (VERİ: `mode` / kayıt); gösterim için `dil=None` (istek dili)."""
    yap = _ORGAN_ADLARI.get(int(hedef_id))
    return yap(dil) if yap else ""


# ── cat_organ organ-lokalizasyon (el takibi YERİNE; kullanıcı kararı: MediaPipe Hands SÖKÜLDÜ) ──
# cat_organ ~1-4sn/kare (ağır) → loop HER KAREDE çalıştırmaz; periyodik lokalize + cache.
# AKTIF HEDEF MODELI (Faz 1, 2026-09-08): istemci `model` alaniyla secer, onay muhrune yazilir,
# /ai/pro/start MUHURDEN okur. Yalniz `_ai_loop_lock` altinda yazilir. Varsayilan "kedi" ->
# `model` gondermeyen ESKI istemciler (ve mobil kare yolu) bugunku davranisi surdurur.
_ai_hedef_modeli = ai_pro_hedef.VARSAYILAN_MODEL
#: Hazırlık hatasının SINIFI (kamera | model_paketi | model_yukleme). Kullanıcı metni
#: `_ai_hazirlik_hata`da kalır (panel string bekliyor); bu alan YALNIZ-EK → panel uyarı
#: başlığını koda göre seçebilir.
_ai_hazirlik_hata_kodu = ""
_ai_hazirlik_hata_saglayici = None  # hata anındaki sağlayıcı (model adı istek dilinde gösterilsin)

_ORGAN_LOCALIZE_INTERVAL_S = 10.0
_AI_LOST_STOP_STREAK = 3  # DENETIM P2: bu kadar ARDISIK hedef-kaybindan sonra bobinleri durdur
_MIN_RELIABILITY = 0.3  # organ güveni bu eşiğin altında → "bulunamadı" → coil SÜRÜLMEZ
_ai_relocalize = True  # bir sonraki karede zorla yeniden-lokalize (start/organ-değişim/yeniden-konumla)
_ai_organ_cache = {
    "x_mm": 0.0,
    "y_mm": 0.0,
    "z_mm": 0.0,
    "reliability": 0.0,
    "localized": False,
    "overlay_bgr": None,
    "at": 0.0,
    "organ_id": -1,
    # Karede kedi var mı (organ lokalizasyonundan AYRI) — hazırlık ekranı operatöre doğru
    # yönlendirmeyi verebilsin: "kediyi kadraja alın" mı, "açıyı değiştirin" mi?
    "kedi_var": False,
    # Sunum-katmanı XAI (2026-08-26): seçili organın reliability bileşen dökümü
    # (pipeline guven_dokumu_hesapla) — panel "Güven %X"in NEDENİNİ gösterebilsin.
    "guven_dokumu": None,
}
# Audit P2: _ai_organ_cache arkaplan loop (_ai_pro_loop) VE mobil frame ucu (ai_pro_frame) arasinda
# paylasilir. Cok-alanli okuma/.update() kilitsiz interleave olursa yirtik-okuma (bir organin
# reliability'si baska koordinatla) + celiskili bobin komutu. Kisa kritik-bolumler icin tek kilit
# (I/O kilit DISINDA → deadlock yok).
_ai_cache_lock = _ai_threading.Lock()


def _get_or_load_kedi():
    """KediPredictor'ı (em_kedi BiLSTM_XXL_Raw) thread-safe önbellekle."""

    def _load():
        # ONNX dosyasını standart kurulum/release_assets yolundan hazırla (find_installed_model).
        try:
            download_model_sync("ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx")
        except Exception as _de:
            logger.warning("em_kedi ONNX indirme/çözümleme uyarısı: %s", _de)
        from ai_hub.em_kedi.inference_em_kedi import KediPredictor

        return KediPredictor(providers=["CPUExecutionProvider"])

    return _get_or_load_model("em_kedi", _load)


def _get_or_load_catorgan():
    """CatOrganPredictor'ı (kedi organ 3B lokalizasyon, 3 ONNX CPU) thread-safe önbellekle."""

    def _load():
        from ai_hub.inference_cat_organ.catorgan_predictor import CatOrganPredictor

        return CatOrganPredictor(device="cpu")

    return _get_or_load_model("cat_organ", _load)


def _hat_dokumu(poz_turu, pnp_hata_px, ayna_uyarisi, anatomik, pnp_olcek_px_cm=None) -> dict:
    """AI1.K3 (hoca kedi organ v2 `ara_ciktilar`): güven dökümüne hattın KALİTE ara çıktıları — poz türü, PnP (keypoint) uyum
    hatası, ayna uyarısı, anatomik kontrol. CPU (predictor sonucu) ve GPU (servis yanıtı) yolları AYNI alanları üretir (parite).
    YALNIZ-EK ve yalnız GÖSTERİM: güven, konum ve sürüş DEĞİŞMEZ; eski servis yanıtında alan yoksa boş kalır.
    AII-2.7 (AI inceleme): px çözünürlükle doğrusal (aynı kedi 4032 / 1008 px'te 231 / 49 px) → gösterim `pnp_hata_cm` =
    residual_px / scale_px_per_cm (hattın kendi ölçeği; kedi gövdesi biriminde, çözünürlükten bağımsız). Ölçek yoksa None."""
    an = anatomik if isinstance(anatomik, dict) else {}
    try:
        ham = float(pnp_hata_px)
        hata = round(ham, 1) if _math.isfinite(ham) else None
    except (TypeError, ValueError):
        hata = None
    try:
        olcek = float(pnp_olcek_px_cm)
    except (TypeError, ValueError):
        olcek = None
    hata_cm = (
        round(ham / olcek, 1)
        if hata is not None and olcek is not None and _math.isfinite(olcek) and olcek > 0
        else None
    )
    return {
        "poz_turu": str(poz_turu) if poz_turu else None,
        "pnp_hata_px": hata,
        "pnp_hata_cm": hata_cm,
        "ayna_uyarisi": bool(ayna_uyarisi),
        "anatomik_gecti": None if an.get("passed") is None else bool(an.get("passed")),
        "anatomik_skor": an.get("score"),
    }


#: ODK (istem 45) · kedi ODAK: son `_extract_organ_target` çağrısının organ sözlüğü — AYNI iş parçacığında `KediSaglayici.localize`
#: okur (gövde merkezi + yönü organlardan, `ai_pro_hedef.kedi_govde_geometrisi`). İş parçacığı yerel: eşzamanlı lokalizasyonlar karışmaz.
_kedi_organ_izi = _ai_threading.local()


def _extract_organ_target(organs_by_id, organ_id, overlay, hat=None):
    """cat_organ sonucundan (CPU dict VEYA GPU-JSON'dan kurulmuş dict) seçili organ hedefini çıkar.
    organs_by_id: {id: {coord_cabin_cm|coord_3d_cm, reliability}}. organ_id 0 (Tüm Vücut) → max-reliability
    güven-geçidi + koordinat (0,0,0). NOT: estimate_organs_pnp INT-anahtarlı ama JSON'da str → ikisi denenir.
    Döner: (localized, x_mm, y_mm, z_mm, reliability, overlay_bgr, kedi_var, guven_dokumu).
    guven_dokumu (2026-08-26, sunum-katmanı XAI): seçili organın reliability_components'ı
    (yoksa/Tüm Vücut'ta None). Tüketiciler `*ekstra` ile açar → eski 7'li tuple'lar KIRILMAZ.
    hat (AI1.K3): `_hat_dokumu` alanları dökümün KOPYASINA eklenir (organ sözlüğü değişmez; döküm yoksa eklenmez).

    ⚠️ `kedi_var` NEDEN AYRI (sahip isteği 2026-08-24): "kedi yok" ile "kedi var ama hedef organ
    bulunamadı" tek bir `detected: false` altında birleşiyordu ve operatöre NE YAPACAĞI
    söylenemiyordu — kamerayı hayvana mı doğrultsun, açıyı mı değiştirsin? cat_organ hiçbir organ
    döndürmediyse karede kedi yoktur; organ döndürüp hedef seçilemiyorsa kedi vardır ama o organ
    (okluzyon/açı) görünmüyordur. İki durum farklı eylem gerektirir."""
    kedi_var = bool(organs_by_id)
    _kedi_organ_izi.organlar = organs_by_id if isinstance(organs_by_id, dict) else {}
    if int(organ_id) == 0:
        # Tüm Vücut: EN AZ BİR organ güvenle lokalize değilse "bulunamadı" → coil SÜRÜLMEZ (max güven-geçidi;
        # eski zorla-1.0 baypası KALDIRILDI — okluzyonlu organlara rağmen gerçek kediyi reddetmez, çöpte sürmez).
        # Döküm None: agregat max-güvenin tek-organ bileşen dökümü anlamlı değil.
        rels = [float(v.get("reliability") or 0.0) for v in organs_by_id.values() if isinstance(v, dict)]
        conf = max(rels) if rels else 0.0
        return (conf >= _MIN_RELIABILITY), 0.0, 0.0, 0.0, conf, overlay, kedi_var, None
    o = organs_by_id.get(int(organ_id)) or organs_by_id.get(str(int(organ_id)))
    if not o:
        return False, 0.0, 0.0, 0.0, 0.0, overlay, kedi_var, None
    coord = o.get("coord_cabin_cm") or o.get("coord_3d_cm") or [0.0, 0.0, 0.0]
    rel = float(o.get("reliability") or 0.0)
    dokum = o.get("reliability_components") if isinstance(o.get("reliability_components"), dict) else None
    if dokum is not None and hat:
        dokum = {**dokum, **hat}
    # ⚠️ D1.85 (B-5.11): kabin DIŞI ya da sonlu olmayan hedef REDDEDİLİR (WARNING) — kıskaçtan ÖNCE. Eskiden aşağıdaki
    # ±300 mm kıskacı onu kabin kenarına çekip SÜRÜYORDU (Y/Z kabin sınırı 250 mm; NaN → 300 mm). Kabin sınırı kabin
    # yapılandırmasından (`ai_pro_hedef.kabin_yari_boyut_mm`). Reddedilen hedef "bulunamadı"dır → döngü/`/frame` hedef
    # kaybı kuralıyla bobinleri durdurur (İG-5.1).
    try:
        ham_mm = tuple(float(v) * 10.0 for v in coord[:3])
    except (TypeError, ValueError):
        ham_mm = (float("nan"),) * 3
    _neden = ai_pro_hedef.hedef_kabin_disi_nedeni(*ham_mm) if len(ham_mm) == 3 else "kabin denetimi: eksik koordinat"
    if _neden:
        logger.warning("AI Pro hedefi kabin/geçerlilik denetiminde REDDEDİLDİ (organ %s): %s", organ_id, _neden)
        if _neden.startswith("kabin boyutu okunamadı"):
            _kabin_okunamaz_bildir()
        return False, 0.0, 0.0, 0.0, rel, overlay, kedi_var, dokum

    def _mm(v):
        # em_kedi eğitim aralığı ±300 mm. Kabin İÇİNDE kalan tek kısılan bant x ∈ (300, 325] mm (bkz. rapor, Açık).
        return max(-300.0, min(300.0, v))

    _kisik = (_mm(ham_mm[0]), _mm(ham_mm[1]), _mm(ham_mm[2]))
    if _kisik != ham_mm:
        _kiskac_izi(organ_id, ham_mm, _kisik)
    return (rel >= _MIN_RELIABILITY), _kisik[0], _kisik[1], _kisik[2], rel, overlay, kedi_var, dokum


#: 1-C inceleme i7-F-9: (300, 325] mm bandı kısma izi — organ + cm değeri başına bu aralıkta en çok BİR WARNING.
_KISKAC_IZ_ARALIK_S = 60.0
_kiskac_iz_son: dict = {}
#: 1-C inceleme i7-F-8: kabin yapılandırması okunamazken eylem bildirimi — seans (onay) başına BİR KEZ.
_kabin_okunamaz_bildirilen: dict = {"anahtar": None}


def _kiskac_izi(organ_id, ham_mm, kisik_mm) -> None:
    """i7-F-9: kabin İÇİ ama em_kedi eğitim aralığı (±300 mm) DIŞI hedef kısılınca İZ bırak. Ölçüldü: x ∈ (300, 325] mm
    iz bırakmadan (WARNING yok, yanıtta kısılmış değer) ±300'e kısılıp sürülüyordu. Ö.4-Y9: YENİ kıskaç DEĞİL —
    mevcut ±300 kıskacının görünürlüğü (kısma kararı sahip/model işi, rapor "Açık")."""
    try:
        anahtar = (int(organ_id), tuple(round(a / 10.0) for a in ham_mm))
        simdi = time.monotonic()
        if simdi - _kiskac_iz_son.get(anahtar, -1e9) < _KISKAC_IZ_ARALIK_S:
            return
        if len(_kiskac_iz_son) > 256:
            _kiskac_iz_son.clear()
        _kiskac_iz_son[anahtar] = simdi
        logger.warning(
            "AI Pro hedefi (organ %s) kabin İÇİNDE ama em_kedi eğitim aralığı (±300 mm) DIŞINDA: %s mm → %s mm'ye "
            "kısıldı (doz tahmini kısılmış konumla yapılır).",
            organ_id,
            tuple(round(a, 1) for a in ham_mm),
            tuple(round(a, 1) for a in kisik_mm),
        )
    except Exception:
        logger.debug("kıskaç izi yazılamadı", exc_info=True)


def _kabin_okunamaz_bildir() -> None:
    """i7-F-8: kabin yapılandırması okunamıyorsa HER hedef reddedilir; yanıt "hedef bulunamadı" olur ve panel "açıyı
    değiştirin" der — operatör hayvanı boşuna yeniden konumlar ("hata mesajı EYLEM söylesin"). Seans başına BİR KEZ
    eylem söyleyen bildirim (her karede değil — alarm yorgunluğu yok). Güvenli yön korunur: hedef yine REDDEDİLİR."""
    try:
        import servers.api_server as _apx

        with _apx._session_lock:
            _anahtar = _apx._active_session.get("onay_kimligi") or _apx._active_session.get("session_id") or ""
        if _kabin_okunamaz_bildirilen.get("anahtar") == _anahtar:
            return
        _kabin_okunamaz_bildirilen["anahtar"] = _anahtar
        _apx._bildir(lambda d: ceviri.t("bildirim.aiProKabinYapilandirma", dil=d), "error")
    except Exception:
        logger.debug("kabin okunamaz bildirimi gönderilemedi", exc_info=True)


#: D1.E07 (İG-5.15): doz modeli hata verdiğinde eylem bildirimi — seans (onay) başına BİR KEZ.
_doz_hatasi_bildirilen: dict = {"anahtar": None}


def _doz_hatasi_bildir() -> None:
    """D1.E07 (İG-5.15, seans ortası): doz modeli geçerli doz üretmedi (zarf `[0]*7`) → bobinler SÜRÜLMEZ ve hedef-kaybı
    gibi sayılır (N turda STOP). Eskiden sıfır doz "sürüş" olarak gönderiliyordu — bildirimsiz, panel "sürüldü". Seans
    başına BİR KEZ eylem söyleyen bildirim (alarm yorgunluğu yok)."""
    try:
        import servers.api_server as _apx

        with _apx._session_lock:
            _anahtar = _apx._active_session.get("onay_kimligi") or _apx._active_session.get("session_id") or ""
        if _doz_hatasi_bildirilen.get("anahtar") == _anahtar:
            return
        _doz_hatasi_bildirilen["anahtar"] = _anahtar
        _apx._bildir(lambda d: ceviri.t("bildirim.aiProDozUretmedi", dil=d), "error")
    except Exception:
        logger.debug("doz hatası bildirimi gönderilemedi", exc_info=True)


# E3-b (denetim 2026-08-24): cat_organ SEGMENTASYON aşaması başarısız olursa (kedi kadrajda YOK)
# catorgan_predictor RuntimeError("segmentasyon: ...") atar. Bu, "kedi yok" durumudur; pose/PnP
# hatası (kedi VAR ama organ okluzyon/açı) FARKLI bir şeydir. ⚠️ Mesaj-prefix'e bağlı — kaynak
# tek yer (catorgan_predictor.py:80 sabit "segmentasyon:"); firmware kadar kırılgan değil ama
# değişirse test_ai_pro_kedi_yok_mandal kırmızı verir.
_CAT_ABSENT_ERR_PREFIX = "segmentasyon:"


def _gecici_gorsel_yaz(yol: str, img) -> None:
    """Geçici analiz görselini Unicode-güvenli yaz (AII-3.11). ⚠️ OpenCV `imwrite` Windows'ta ASCII DIŞI yola (C:\\Users\\Müjde\\…\\Temp)
    YAZAMAZ ve yalnız False döner — dönüş denetlenmiyordu: dosya 0 bayt kalıyor, termal ucu her çağrıda, kedi organ / AI Pro ilk karede 500
    veriyordu (ultralytics içe aktarılınca cv2'yi yamaladığı için sonuç içe aktarma SIRASINA bağlıydı). Kodla + Python dosyasıyla yaz."""
    ok, buf = cv2.imencode(os.path.splitext(str(yol))[1] or ".jpg", img)
    if not ok:
        raise RuntimeError(f"geçici görsel kodlanamadı ({os.path.basename(str(yol))})")
    with open(yol, "wb") as f:
        f.write(buf.tobytes())


def _is_cat_absent_error(exc) -> bool:
    return isinstance(exc, RuntimeError) and str(exc).startswith(_CAT_ABSENT_ERR_PREFIX)


def _cat_kabin_uyarisi(result) -> str | None:
    """D1.E08: kabin yapılandırması yüklenemediyse operatör metni (tek kaynak `catorgan_predictor.kabin_uyarisi`)."""
    from ai_hub.inference_cat_organ.catorgan_predictor import kabin_uyarisi

    return kabin_uyarisi(result)


def _localize_organ_cpu(frame, organ_id):
    """cat_organ'ı YEREL (in-process, CPU) çalıştır → hedef organ. (tek-EXE klinik + GPU-fallback yolu)."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    _gecici_gorsel_yaz(tmp.name, frame)
    try:
        clf = _get_or_load_catorgan()
        result = clf.predict(tmp.name, render=True, target_oid=(int(organ_id) or None))
    except Exception as e:
        # E3-b: kedi-yok (segmentasyon hatası) İSTİSNA yerine temiz "kedi yok" tuple'ı dön
        # (localized=False, kedi_var=False) → loop/frame'in MEVCUT başarılı cache.update'i kedi_var=False
        # yazar → tek-yönlü mandal hata dallarına DOKUNMADAN kırılır. pose/PnP/model-yükleme hatası
        # YUKARI fırlar (kedi_var son değerde KORUNUR; frame yolu 500 döner — mevcut davranış).
        if _is_cat_absent_error(e):
            return _extract_organ_target({}, organ_id, None)
        raise
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
    # ⚠️ D1.E08 (İG-5.27): kabin yapılandırması yüklenemediyse sonuç kalibrasyonsuzdur (kabin koordinatı yok, güven
    # tavanlı) → hedef DOĞRULANAMAZ ve sürülmez; operatöre 1-C'nin EYLEM söyleyen kabin bildirimi (seans başına bir kez).
    if (result.get("kabin_yapilandirmasi") or {}).get("yuklendi") is False:
        logger.warning(
            "AI Pro: kabin yapılandırması yüklenemedi (%s) — hedef doğrulanamaz, SÜRÜLMEZ",
            (result.get("kabin_yapilandirmasi") or {}).get("hata"),
        )
        _kabin_okunamaz_bildir()
        return False, 0.0, 0.0, 0.0, 0.0, result.get("_overlay_bgr"), bool(result.get("organs")), None
    _pnp = result.get("pnp_fit") or {}
    return _extract_organ_target(
        result.get("organs") or {},
        organ_id,
        result.get("_overlay_bgr"),
        hat=_hat_dokumu(
            (result.get("pose_classifier") or {}).get("type"),
            _pnp.get("residual_px"),
            _pnp.get("mirror_warning"),
            result.get("anatomic_consistency"),
            _pnp.get("scale_px_per_cm"),
        ),
    )


def _localize_organ_gpu(frame, organ_id):
    """cat_organ inference'ını GPU servisine DEVRET (delegate_infer_sync; kare zaten to_thread'de).
    GPU-JSON organs list → {id:organ} dict + overlay base64→BGR → paylaşılan _extract_organ_target.
    (Hoca yönü: AI Pro'nun AĞIR 3B-lokalizasyonu Docker/GPU servisinde koşar.)"""
    # ⚠️ BURAYA KALİTE ARGÜMANI EKLENMEDİ — BİLEREK (ADIM 1 denetimi, 2026-09-11).
    # Bu kare operatöre GÖSTERİLMİYOR; GPU mikroservisine ÇIKARIM GİRDİSİ olarak yükleniyor.
    # Gösterim kodlamalarında q85 güvenlidir (göz ayırt etmez), ama model girdisinde
    # sıkıştırma artefaktı tespit/segmentasyon sonucunu DEĞİŞTİREBİLİR ve bu bir tıbbi
    # karar ekranını besler. Düşürülecekse önce doğruluk ÖLÇÜLMELİ (aynı görüntü kümesinde
    # q95 vs q85 çıktı karşılaştırması), tahminle değil.
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("frame JPG encode başarısız")
    resp = delegate_infer_sync(
        "cat_organ", buf.tobytes(), filename="frame.jpg", data={"target_oid": (int(organ_id) or None)}
    )
    organs_by_id = {}
    for o in resp.get("organs") or []:
        if isinstance(o, dict) and "id" in o:
            try:
                organs_by_id[int(o["id"])] = o
            except (TypeError, ValueError):
                pass
    overlay = None
    img_b64 = resp.get("image_base64")
    if img_b64:
        try:
            arr = np.frombuffer(base64.b64decode(img_b64), np.uint8)
            overlay = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            overlay = None
    # D1.E08: GPU servisi aynı öngörücüyü koşar ve aynı `kabin_uyarisi`nı döner (parite) → CPU yoluyla AYNI davranış.
    if resp.get("kabin_uyarisi"):
        logger.warning("AI Pro (GPU): kabin yapılandırması yüklenemedi — hedef doğrulanamaz, SÜRÜLMEZ")
        _kabin_okunamaz_bildir()
        return False, 0.0, 0.0, 0.0, 0.0, overlay, bool(organs_by_id), None
    # AI1.K3 parite: servis yanıtı aynı ara çıktıları üst düzeyde taşır (ai_service `infer_cat_organ`).
    return _extract_organ_target(
        organs_by_id,
        organ_id,
        overlay,
        hat=_hat_dokumu(
            resp.get("pose_type"),
            resp.get("pnp_residual_px"),
            resp.get("mirror_warning"),
            resp.get("anatomic_consistency"),
            resp.get("pnp_scale_px_per_cm"),
        ),
    )


# İSTEK-YEREL hedef bağlamı (2026-09-08): `/propose` HENÜZ AKTİF OLMAYAN bir modelin dozunu
# hesaplar (model seansla birlikte aktifleşir). Aktif sağlayıcı okunursa öneri, mühre yazılan
# modelden BAŞKASININ (varsayılan kedinin) duty/faz desenini taşır — mührün amacını boşa çıkaran
# sessiz bir uyumsuzluk (kapı: tests/test_ai_pro_model_muhru.py). Global yerine THREAD-LOCAL:
# eş zamanlı koşan hazırlık/seans thread'leri kendi modelini okumaya devam eder.
_ai_hedef_yerel = _ai_threading.local()


#: Araştırma modellerinin (kedi DIŞI) kapalı-döngü sürüşünü açan bayrak. VARSAYILAN KAPALI.
#: Neden: fantom/petri koordinat dönüşümü ArUco modunda marker→kabin ROTASYONUNU uygulamıyor ve
#: kesişimi kabin Z=plate_z düzleminde alıyor; kedi hattı ise kabin-merkezli PnP kullanıyor. İki
#: hattın AYNI 3B çerçeveyi ürettiği KANITLANMADI (fantom eğitim aralığı da çok dar) → tezgâh
#: doğrulaması ve hoca kararı (#6) gelmeden bobinler bu modellerin koordinatıyla SÜRÜLMEZ.
#: ⚠️ Kapı UI'da değil BACKEND'de: AI Pro uçları sahip kararıyla auth-muaf ve backend istemci
#: profilini bilmez → yalnız düğmeyi gizlemek yeterli değildi (eski/yanlış istemci ya da curl
#: doğrudan propose+approve+start yapabilirdi).
#: Taşıyıcı: deploy/device.env satırı (kurulum NSSM ortamına yazar; backend .env'i KENDİ okumaz).
#: ⚠️ T-f (Y195, GÜVENLİK): bu bayrak artık YALNIZ PETRİ'yi (ve fantom DIŞI araştırma modellerini) açar — FANTOM kendi bayrağına
#: bağlı (`ARASTIRMA_AIPRO_FANTOM_BAYRAGI`). Bu makinede ve LattePanda'da bayrak petri için AÇIK (Y145 / T3).
ARASTIRMA_AIPRO_BAYRAGI = "PEMF_ARASTIRMA_AIPRO"
#: T-f (Y195, GÜVENLİK — T2B B1, T3 açık #4): FANTOM AI Pro kapalı döngü SÜRÜŞÜ AYRI bayrak, VARSAYILAN KAPALI. Neden: fantom hattı
#: boş kabinde de "tümör" bulup sonucu "sürülebilir" diyor (tezgâhta petri karelerinde 1–61 sahte tümör); eskiden petri için açılan
#: `PEMF_ARASTIRMA_AIPRO` fantomu da AÇIYORDU. Analiz / önizleme bayraktan BAĞIMSIZ. Anlam aynı: yok / boş / bozuk = KAPALI; yalnız
#: `1|true|yes|on` açar. Taşıyıcı: `deploy/device.env` `=0` + launcher geçişi (`install.rs::ENV_ARASTIRMA_AIPRO_FANTOM`, varsayılan
#: "0", ortam korunur — LN L8 / Y142 deseni). Kapı: tests/test_Tf_FANTOM_aipro_AYRI_bayrak_varsayilan_KAPALI.py
ARASTIRMA_AIPRO_FANTOM_BAYRAGI = "PEMF_ARASTIRMA_AIPRO_FANTOM"


def _arastirma_aipro_acik() -> bool:
    """Araştırma modelleriyle (fantom HARİÇ — T-f) kapalı-döngü sürüşe izin var mı (env bayrağı; varsayılan HAYIR)."""
    return str(os.environ.get(ARASTIRMA_AIPRO_BAYRAGI, "")).strip().lower() in ("1", "true", "yes", "on")


def _arastirma_aipro_fantom_acik() -> bool:
    """T-f: FANTOM AI Pro kapalı-döngü sürüşüne izin var mı (kendi env bayrağı; varsayılan HAYIR)."""
    return str(os.environ.get(ARASTIRMA_AIPRO_FANTOM_BAYRAGI, "")).strip().lower() in ("1", "true", "yes", "on")


def _fantom_modeli_mi(saglayici) -> bool:
    return str(getattr(saglayici, "ad", "") or "").strip().lower() == ai_pro_hedef.FantomSaglayici.ad


def _arastirma_aipro_kapisi(saglayici) -> None:
    """Kedi DIŞI bir model için sürüş/öneri isteniyorsa bayrağı denetle → 409.

    Metin operatöre durumu ve nedenini söyler; "hata" değil "henüz doğrulanmadı" durumudur.
    T-f: FANTOM yalnız kendi bayrağıyla (`PEMF_ARASTIRMA_AIPRO_FANTOM`) geçer — genel araştırma bayrağı fantomu AÇMAZ."""
    if getattr(saglayici, "ad", "kedi") == ai_pro_hedef.VARSAYILAN_MODEL:
        return
    if _fantom_modeli_mi(saglayici):
        if _arastirma_aipro_fantom_acik():
            return
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hata.fantomSurusKapali"))
    if _arastirma_aipro_acik():
        return
    raise HTTPException(
        status_code=409,
        detail=(ceviri.t("ai.pro.hata.arastirmaDogrulama", model=ai_pro_hedef.model_adi(saglayici))),
    )


def _duzlem_kalibrasyonu_kapisi(saglayici) -> None:
    """KD · Y259 (sahip 2026-11-10): araştırma modelleri (petri / fantom) YALNIZ geçerli SABİT DÜZLEM kalibrasyonuyla önerilir,
    başlatılır ve SÜRÜLÜR → değilse 409 (nedeni + eylemi istek dilinde). Kedi bu kapıya TABİ DEĞİL (kendi Y142 kapısı).
    Kare başına denetimler (sahne kayması, kuyu aralığı, fantom boyu / boş kabin) hatta — geçmeyen kare lokalize sayılmaz.
    ⚠️ ACİL DURDUR / STOP bu kapıya BAĞLI DEĞİL (Ö.4-Y8): yalnız başlatma / öneri / sürüş yolu."""
    if _kedi_modeli_mi(saglayici):
        return
    kod = ai_pro_hedef.duzlem_surus_engeli(saglayici)
    if kod:
        raise HTTPException(status_code=409, detail=ai_pro_hedef.kapi_metni(kod) or kod)


#: Y142 (S-AI1.5, sahip 2026-10-13): KEDİ AI Pro kapalı döngü SÜRÜŞÜ — VARSAYILAN KAPALI.
#: Neden: hocanın uyarısı "EM'e henüz güvenme, bobine gönderme" — kedi kabin çerçevesi ↔ em_kedi EĞİTİM çerçevesinin aynı
#: olduğu hiçbir ölçümle kanıtlanmadı (AI-1 K2: kabin içi eğitim DIŞI hedef yalnız `ood` ile işaretlenip SÜRÜLÜYORDU).
#: Kapalıyken analiz, hazırlık, öneri ve onay ekranı GÖRÜNÜR kalır; AI Pro'dan BAŞLATMA, onay mührü ve BOBİN SÜRÜŞÜ eylem
#: söyleyen iletiyle reddedilir. Elle seans (Kontrol), araştırma sağlayıcıları (kendi bayrakları) ve ACİL DURDUR ETKİLENMEZ
#: (Ö.4-Y8). Anlam araştırma bayrağıyla AYNI: yok / boş / bozuk = KAPALI; yalnız `1|true|yes|on` açar. Tezgâhta kabin → EM
#: çerçevesi doğrulanınca SAHİP onayıyla açılır (TEZGAH-LISTESI §F6). Taşıyıcı (S-AIK.6 açık #1, LN L8): `deploy/device.env`
#: satırı `=0` (servis kurulumu) + launcher geçişi (`install.rs::ENV_KEDI_AIPRO_SURUS`, varsayılan "0", ortam korunur) — bayrak
#: yine KAPALI; yokluğu da KAPALI (fail-closed yön). Kapı: tests/test_ai_pro_KEDI_surus_KAPALI_varsayilan_Y142.py
KEDI_AIPRO_SURUS_BAYRAGI = "PEMF_KEDI_AIPRO_SURUS"


def kedi_aipro_surus_kapali_mesaji() -> str:
    return ceviri.t("ai.pro.hata.kediSurusKapali")


def _kedi_aipro_surus_acik() -> bool:
    """Kedi AI Pro kapalı döngü sürüşüne izin var mı (Y142; env bayrağı, varsayılan HAYIR)."""
    return str(os.environ.get(KEDI_AIPRO_SURUS_BAYRAGI, "")).strip().lower() in ("1", "true", "yes", "on")


def _kedi_modeli_mi(saglayici_ya_da_ad) -> bool:
    """Sağlayıcı ya da mühürdeki model adı KEDİ mi? Adı OLMAYAN / boş model kedi sayılır (`saglayici_al(None)` → kedi;
    model alanı taşımayan eski öneri / seans mührü) — Y142 kapısı fail-closed."""
    if isinstance(saglayici_ya_da_ad, str):
        ad = saglayici_ya_da_ad
    else:
        ad = getattr(saglayici_ya_da_ad, "ad", "")
    return (str(ad or "").strip().lower() or ai_pro_hedef.VARSAYILAN_MODEL) == ai_pro_hedef.KediSaglayici.ad


def _kedi_aipro_surus_kapisi(saglayici_ya_da_ad) -> None:
    """Y142: kedi modeliyle AI Pro BAŞLATMA / ONAY isteniyor ve bayrak kapalı → 409 (eylem söyleyen metin)."""
    if _kedi_modeli_mi(saglayici_ya_da_ad) and not _kedi_aipro_surus_acik():
        raise HTTPException(status_code=409, detail=kedi_aipro_surus_kapali_mesaji())


#: Y143: otomatik (0) araştırma önerisinde mühürlenecek SEÇİLİ hedef yok / kimliği okunamadı — eylem söyleyen metin.
def otomatik_hedef_secilemedi_mesaji() -> str:
    return ceviri.t("ai.pro.hata.otomatikHedef")


def _yukle_em_fantom_cv() -> dict:
    """phantom_cv_v3 boru hattı + PhantomPredictor'ı BİR KEZ ısıt → `_get_or_load_model` önbelleğine.

    ⚠️ MODÜL SEVİYESİNE TAŞINDI (2026-09-09): eskiden `analyze_em_fantom` içinde bir kapanıştı.
    Araştırma AI Pro fantom sağlayıcısı AYNI önbelleği kullanacağı için (anahtar "em_fantom_cv")
    yükleyici de tek olmalı — aksi halde 60 MB ONNX + scaler'lar analiz ve seans yolları için İKİ
    KEZ yüklenirdi. Dönen sözlük sözleşmesi DEĞİŞMEDİ: {cfg, predictor, cls}.
    """
    # Büyük ONNX runtime'da indirilir (ProgramData/HF); yerel dev'de mevcut.
    try:
        download_model_sync("ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx")
    except Exception as _de:
        logger.warning("em_fantom ONNX indirme/çözümleme uyarısı: %s", _de)
    # AI-2 (2026-10-12): hocanın fantom v3'ü (T1–T5 sabit kimlik, halka ölçeği, `reliable`, `pemf_valid`) — v1 emekli.
    from ai_hub.inference_em_fantom.phantom_cv_v3 import (
        PhantomCvPipeline,
        load_cabin_config,
    )

    cfg = load_cabin_config(None)  # gömülü cabin_config_v3.yaml (saha kabin ölçüsü + hocanın phantom_v2 bölümü)
    warm = PhantomCvPipeline(cfg, manual_fallback=False)
    _ = warm.predictor  # ONNX + scaler'ları bir kez yükle
    return {"cfg": cfg, "predictor": warm._predictor, "cls": PhantomCvPipeline}


def _yukle_em_petri_cv() -> dict:
    """petri_cv_v2 boru hattı + YOLO11m-seg + PetriPredictor'ı BİR KEZ ısıt → önbelleğe.

    ⚠️ MODÜL SEVİYESİNE TAŞINDI (2026-09-09; fantomla aynı gerekçe): 239 MB BaggingRegressor +
    90 MB YOLO analiz ve seans yolları için iki kez yüklenmesin. Sözleşme DEĞİŞMEDİ:
    {cfg, cls, yolo, predictor, yolo_path}.
    """
    # AI-2 (2026-10-12): hocanın petri v2'si (24'lük plaka ızgarası A1–D6, `pemf_valid`, kontrol kuyucuklu sınıflama) — v1 emekli.
    from ai_hub.inference_petri_dish.petri_cv_v2 import (
        PetriCvPipeline,
        load_cabin_config,
    )

    # YOLO ONNX yolu (ProgramData/HF'den indir; yoksa yerel dev).
    try:
        yolo_path = download_model_sync("ai_hub/inference_petri_dish/yolo11m-seg.onnx")
    except ModelButunlukHatasi:  # D3I-A2.4 · Y18: bütünlük reddi YUTULMAZ → 503 + açık uyarı
        raise
    except Exception as _de:
        logger.warning("em_petri YOLO ONNX indirme/çözümleme uyarısı: %s", _de)
        yolo_path = os.path.join(project_root, "ai_hub", "inference_petri_dish", "yolo11m-seg.onnx")
    cfg = load_cabin_config(None)  # gömülü cabin_config_v2.yaml (saha kabin ölçüsü + hocanın multiwell bölümü)
    # yolo_device="cpu" ŞART (headless — CUDA yok).
    warm = PetriCvPipeline(cfg, yolo_model_path=yolo_path, yolo_device="cpu")
    _ = warm.predictor  # BaggingRegressor ONNX (kendi fallback'i)
    try:
        warm.process_image(np.zeros((640, 640, 3), dtype=np.uint8))  # YOLO modelini ısıt
    except Exception:
        pass
    return {
        "cfg": cfg,
        "cls": PetriCvPipeline,
        "yolo": warm.yolo,
        "predictor": warm._predictor,
        "yolo_path": yolo_path,
    }


def _pemf_alanlari(payload: dict, model: str, kosulsuz: bool = False) -> dict:
    """AI-2: hocanın v2/v3 yanıt alanları + tüketim kapısı (TEK KAYNAK `ai_hub.cv_ortak.pemf_kapisi`; ai_service aynısını
    kullanır). `payload` = `result.to_dict()` (NaN-güvenli). Kapı hesaplanamazsa alanlar BOŞ dönmez, FAIL-CLOSED işaret
    döner: `pemf_valid` False ve `pemf_kapisi.surulebilir` False — arayüz D/P/E'yi "geçersiz" etiketiyle gösterir."""
    try:
        from ai_hub.cv_ortak import pemf_kapisi as _pk

        _d = _pk.yanit_alanlari(payload, model=model, kosulsuz=kosulsuz)  # T3 · Y189: koşulsuz kip (tek kaynak)
        _d["pemf_kapisi"] = ai_pro_hedef.kapi_cevir(
            _d["pemf_kapisi"]
        )  # KD: fiziksel (kalibrasyon) nedenleri istek dilinde
        _eski = ai_pro_hedef.kalibrasyon_eski_metni(payload)  # KD-1 sahip: "kalibre etmeden devam" → kalıcı uyarı
        if _eski:
            _d["kalibrasyon_uyarisi"] = _eski
        return _d
    except Exception:
        logger.warning("%s PEMF kapısı alanları üretilemedi → geçersiz işaretlendi", model, exc_info=True)
        _m = ceviri.t("ai.pemf.gecerlilikHesaplanamadi")
        return {
            "pemf_valid": False,
            "pemf_kapisi": {
                "surulebilir": False,
                "pemf_gecerli": False,
                "nedenler": ["kapi_hesaplanamadi"],
                "eylem": _m,
                "mesajlar": [{"kod": "kapi_hesaplanamadi", "metin": _m}],
                "varsayimlar": [],
            },
        }


def _saglayici_meta() -> dict:
    """Aktif sağlayıcının SON lokalizasyon meta'sı (hedef adayları, kalibrasyon yöntemi, E, ood).

    Kedi hattı BOŞ döndürür (kare üstü aday üretmez; organ çiplerden seçilir) → yalnız-ek alanlar
    boş kalır ve veteriner tel sözleşmesi DEĞİŞMEZ."""
    try:
        return _aktif_saglayici().son_lokalizasyon_meta() or {}
    except Exception:
        logger.debug("AI Pro: sağlayıcı meta okunamadı", exc_info=True)
        return {}


def _saglayici_cache_alanlari() -> dict:
    """`_ai_organ_cache.update(...)` için YALNIZ-EK meta alanları (Faz 2).

    Üç lokalizasyon yolu (hazırlık / seans / mobil kare) aynı alanları yazar → /status, WS
    `ai_vision` ve /frame yanıtları tek kaynaktan beslenir (kare üstü hedef seçimi + kalibrasyon
    rozeti + onay ekranı E/ood satırları)."""
    m = _saglayici_meta()
    return {
        "targets": m.get("targets") or [],
        "method": m.get("method") or "",
        "mm_per_px": m.get("mm_per_px"),
        "target_label": m.get("target_label") or "",
        "e_cancer": m.get("e_cancer"),
        "e_healthy": m.get("e_healthy"),
        "ood": bool(m.get("ood")),
        # Y143: lokalizasyonun SEÇTİĞİ hedefin kalıcı kimliği (araştırma; kedide yok → None). Otomatik (0) öneri bunu mühürler.
        "secili_id": m.get("secili_id"),
        # T3 · Y189: bu konum KOŞULSUZ kipte mi bulundu (öneri tazelik denetimi ve mühür buna bakar; kedide hep False).
        "kosulsuz": bool(getattr(_aktif_saglayici(), "kosulsuz", False)),
        # KD-3a (B-KD3a.1): kapı FİZİKSEL nedenle (kalibrasyon / kamera oynamış / kör bölge …) kestiyse ilk eylem metni (dile çevrilmiş).
        "kapi_eylem": _kapi_fiziksel_eylemi(m.get("pemf_kapisi")),
    }


def _kapi_fiziksel_eylemi(kapi) -> str:
    """KD-3a (B-KD3a.1, tezgâh 11 Kasım): sabit düzlem kipinde kapı FİZİKSEL nedenle kestiğinde panel nedeni göremiyor, rozet ArUco
    metnine ("kabin işareti … kare kod … görünmüyor") düşüyordu. Kapı kestiyse İLK fiziksel mesajın (sağlayıcıda `kapi_cevir` ile
    dile çevrilmiş) metni; kapı geçtiyse / hesaplanmadıysa / neden fiziksel değilse "" (hocanın kalite nedenleri kendi şeridinde)."""
    if not isinstance(kapi, dict) or kapi.get("surulebilir") is not False:
        return ""
    from ai_hub.cv_ortak import pemf_kapisi as _pk

    for m in kapi.get("mesajlar") or []:
        if isinstance(m, dict) and str(m.get("kod") or "") in _pk.FIZIKSEL:
            metin = ai_pro_hedef.kapi_metni(str(m.get("kod")))
            return str(metin or m.get("metin") or "")
    return ""


def _hazirlik_hata_metni(kod: str, ad: str, dil: str | None = "tr") -> str:
    """Hazırlık hata kodunun metni (`dil="tr"` = depolanan Türkçe; durum yanıtı istek dilinde yeniden üretir)."""
    if kod == "model_paketi":
        return ceviri.t("ai.pro.hazirlik.modelPaketi", dil=dil, ad=ad)
    if kod == "model_yukleme":
        return ceviri.t("ai.pro.hazirlik.modelYukleme", dil=dil, ad=ad)
    if kod == "kamera":
        return ceviri.t("ai.pro.hazirlik.kamera", dil=dil)
    if kod == "kamera_secilmedi":
        return ceviri.t("ai.pro.hazirlik.kameraSecilmedi", dil=dil)
    return ""


def _hazirlik_hata_goster() -> str:
    """Durum yanıtındaki hazırlık hatası: depolanan metin Türkçe (hazırlık iş parçacığı istek bağlamında değil); yanıt İSTEK dilinde."""
    if _ai_hazirlik_hata and _ai_hazirlik_hata_kodu in ("model_paketi", "model_yukleme", "kamera", "kamera_secilmedi"):
        sag = _ai_hazirlik_hata_saglayici
        ad = ai_pro_hedef.model_adi(sag) if sag is not None else ""
        return _hazirlik_hata_metni(_ai_hazirlik_hata_kodu, ad, None)
    return _ai_hazirlik_hata


def _hazirlik_hata_sinifi(exc: Exception, saglayici) -> "tuple[str, str]":
    """Model yükleme istisnasını (kod, KULLANICI METNİ) çiftine çevir — eylem söyleyen hata kuralı.

    Ham istisna metni / iç sınıf adı KULLANICIYA GİTMEZ (yalnız log'a): "AI modeli yüklenemedi:
    FileNotFoundError(...onnx bulunamadi...)" gibi bir metin operatöre "yazılımda bug var"
    izlenimi verir, oysa yapılacak iş bellidir (paketi kur / uygulamayı yeniden başlat).
    Model paketi metnindeki YÖNLENDİRME sahip kararı #18'e baglidir (kurulum programının
    kullanıcıya görünen adı); karar gelince yalnız bu metin güncellenecek."""
    _ad = getattr(saglayici, "title", "AI modeli")
    if isinstance(exc, FileNotFoundError) or "bulunamad" in str(exc).lower():
        return ("model_paketi", _hazirlik_hata_metni("model_paketi", _ad))
    return ("model_yukleme", _hazirlik_hata_metni("model_yukleme", _ad))


def _ai_seansi_mi(seans: dict) -> bool:
    """DURDURMA yönü (pasife alma) için: oturum bir AI seansı mı? Türe bakılır; türü olmayan eski kayıtta `mode`
    öneki. ⚠️ Bu YETKİ VERMEZ — sürüş yetkisi YALNIZ `_ai_pro_surus_muhru` (D1.80). Durdurma yönünde geniş olmak
    güvenlidir (pasif seans hiçbir şeyi enerjilemez)."""
    tur = seans.get("tur")
    if tur is not None:
        return tur in ("ai_pro", "ai_auto")
    return str(seans.get("mode", "")).startswith("AI")


def _ai_pro_surus_muhru():
    """D1.80 · D1.81 · İG-5.9 — sürülebilir AI Pro seansının MÜHRÜ (anlık görüntü) ya da None.

    Sürüş YALNIZ `/api/ai/pro/start`ın açtığı, hekim onayı TÜKETİLMİŞ seansta: `tur == "ai_pro"`, onay kimliği ve
    sürüş nesli dolu. `mode` (serbest metin; `/api/session/start` "AI…" önekini de kabul eder) ARTIK YETKİ VERMEZ —
    ölçüldü: önekli elle seans 17/17 onaysız AI dozu açıyordu, önek daraltılınca bile 1/17 (İG-5.2).
    SÜRE MÜHÜRDEN: seans başlangıcı (`start_mono`) + onaylanan süre. AI Pro globalleri (`_ai_duration_min`,
    `_ai_started_at`) bayat kalabilir — ölçüldü: önceki 1 dk'lık seansın globali 3 dk'lık seansı 58. sn'de kesiyor,
    telde süre 1 dk gidiyordu (İG-5.9)."""
    try:
        import servers.api_server as _api

        with _api._session_lock:
            s = dict(_api._active_session)
    except Exception:
        logger.exception("AI Pro: seans mührü okunamadı → SÜRÜLMEZ")
        return None
    if not (
        s.get("is_active") and s.get("tur") == "ai_pro" and s.get("onay_kimligi") and s.get("surus_nesli") is not None
    ):
        return None
    try:
        kalan_s = float(s.get("duration_minutes") or 0) * 60.0 - (time.monotonic() - float(s["start_mono"]))
    except (KeyError, TypeError, ValueError):
        return None
    if kalan_s <= 0:
        return None
    return {
        "nesil": s["surus_nesli"],
        "onay": s["onay_kimligi"],
        "model": str(s.get("model") or ""),
        # D1.60 (A-16): hekimin ONAYLADIĞI hedef — sürüş yalnız bunu sürer, başka hedefe geçiş yeni onay ister.
        # Mühürde yoksa (None) hiçbir hedef "onaylı" sayılmaz (fail-closed).
        "hedef": s.get("onay_hedefi"),
        "kalan_s": kalan_s,
        "bitis_mono": time.monotonic() + kalan_s,
    }


def _muhur_surulebilir_mi(muhur) -> bool:
    """Mühür VAR + etkin sağlayıcı MÜHÜRDEKİ model + (araştırma modeliyse) bayrak AÇIK (D1.80 · B-5.10).

    Bayrak SÜRÜŞ ANINDA denetlenir: bayrak açıkken alınmış onay, bayrak kapatıldıktan sonra sürülmez (`/start` yalnız
    başlangıçta bakıyordu). Model mühürden ayrıştıysa (hazırlık ya da başka bir yol değiştirdi) sürülmez."""
    if not muhur:
        return False
    sag = _aktif_saglayici()
    if muhur.get("model") and getattr(sag, "ad", "") != muhur["model"]:
        logger.warning("AI Pro: etkin model %r mühürdeki %r değil → SÜRÜLMEZ", getattr(sag, "ad", ""), muhur["model"])
        return False
    try:
        _arastirma_aipro_kapisi(sag)
    except HTTPException:
        logger.warning("AI Pro: araştırma bayrağı kapalı → '%s' ile SÜRÜLMEZ", getattr(sag, "ad", ""))
        return False
    # KD · Y259: kalibrasyon SÜRÜŞ ANINDA da denetlenir (seans sürerken silinen / bozulan / kamerası değişen kalibrasyonla sürülmez).
    try:
        _duzlem_kalibrasyonu_kapisi(sag)
    except HTTPException as e:
        logger.warning(
            "AI Pro: sabit düzlem kalibrasyonu geçersiz → '%s' ile SÜRÜLMEZ (%s)", getattr(sag, "ad", ""), e.detail
        )
        return False
    # Y142: kedi sürüşü de SÜRÜŞ ANINDA denetlenir (bayrak açıkken alınmış onay / başka yoldan yazılmış mühür sürülmez).
    if _kedi_modeli_mi(sag) and not _kedi_aipro_surus_acik():
        logger.warning("AI Pro: kedi sürüşü kapalı (Y142, %s) → SÜRÜLMEZ", KEDI_AIPRO_SURUS_BAYRAGI)
        return False
    return True


def _dongu_bayragini_indir(dongu_muhru) -> None:
    """`_ai_loop_active`i YALNIZ bu döngü hâlâ GÜNCEL döngüyse indir (D1.81 · İG-5.11).

    Eski döngü bayrağı koşulsuz False yazsaydı, `/stop`→`/start` ile başlamış YENİ döngüyü öldürürdü."""
    global _ai_loop_active
    with _ai_loop_lock:
        if dongu_muhru is None or dongu_muhru.get("dongu") == _ai_dongu_no:
            _ai_loop_active = False


def _ai_seansi_pasife_al(neden: str, dongu_muhru=None) -> None:
    """Seans loop'u BAŞLAMADAN öldüyse `_active_session`i pasife çek (teardown paritesi).

    2026-09-09 düzeltmesi: /ai/pro/start `start_ai_session(...)`i thread spawn'indan ÖNCE
    çağırıyor. Loop kamerayı açamaz ya da modeli yükleyemezse `_ai_loop_active=False` yapıp
    dönüyordu ama oturum AI modunda AKTİF kalıyordu → panel/geçmiş seansı "sürüyor" gösteriyor,
    süre-watchdog dolana kadar kapanmıyordu. Bobin sürülmediği için tedavi yok; görünen durum
    ile gerçek durum AYRIŞIYORDU.

    ⚠️ YALNIZ KENDİ SEANSI (1-C inceleme i2-F6, teardown'daki `_kendi` kuralının aynısı): mühür verilirse yalnız onay
    kimliği eşleşen seans pasife alınır ve canlı durum yalnız o zaman yazılır. Ölçüldü: eski döngü modeli yüklerken
    operatör onu durdurup YENİ onaylı seans açınca, eski döngünün başlangıç hatası O AN AKTİF olan yeni seansı pasife
    çekiyordu (30/30) — yeni döngü bir sonraki turda çıkıyor, onayı tüketilmiş tedavi operatör bir şey yapmadan bitiyordu."""
    try:
        import servers.api_server as _api3

        with _api3._session_lock:
            _s = _api3._active_session
            if dongu_muhru is not None:
                _kendi = _s.get("onay_kimligi") == dongu_muhru.get("onay")
            else:
                _kendi = _ai_seansi_mi(_s)
            _iptal = dict(_s) if (_kendi and _s.get("is_active")) else None
            if _kendi:
                _s["is_active"] = False
            _baskasi_aktif = bool(_s.get("is_active")) and not _kendi
        # D2.E07: döngü bobin SÜRMEDEN öldü (model / kamera) → satır "İptal Edildi" kapanır (açık kalıp yeniden açılışta
        # "Elektrik Kesintisi" olmaz).
        # C2-1.4: bu pencerede kare yolu (`/frame`, mühürlü seans) bobin SÜRMÜŞ olabilir — KENDİ seansının bobinlerine STOP
        # (idempotent; satır kapanışından ÖNCE); sürüldüyse kayıt "Kesintiye Uğradı" (İptal Edildi = bobin sürülmedi).
        _sebep = "iptal-ai-pro"
        if _iptal is not None:
            try:
                _cs = getattr(getattr(_api3.state, "hardware", None), "coils_state", None) or {}
                if any((_cs.get(int(c)) or {}).get("is_running") for c in (_iptal.get("coil_ids") or [])):
                    _sebep = "ai-pro-kesinti"
            except Exception:
                logger.debug("AI Pro: bobin durumu okunamadı", exc_info=True)
            try:
                _api3._bildir_teyitsiz_stop(
                    _api3._stop_session_coils(_iptal.get("coil_ids") or list(range(1, 8)), yetkiyi_kes=True),
                    lambda d: ceviri.t("bildirim.kaynak.aiProBaslatilamadi", dil=d),
                )
            except Exception:
                logger.exception("AI Pro: başlatılamayan seansın bobinleri durdurulamadı")
        _ai_pro_satirini_kapat(_iptal, _sebep)
        if _baskasi_aktif:
            logger.error("AI Pro döngüsü başlatılamadı (%s) — aktif seans bu döngünün değil, ona DOKUNULMADI.", neden)
            return
        _api3.update_live_session_state(is_active=False, mode="Sistem Hazır")
        logger.error("AI Pro seansı başlatılamadı (%s) — oturum pasife alındı.", neden)
    except Exception:
        logger.exception("AI Pro: oturum pasife alınamadı (%s)", neden)


def _aktif_saglayici():
    """Bu iş parçacığı için geçerli hedef sağlayıcısı (kedi | fantom | petri).

    Öncelik: istek-yerel bağlam (propose) → `_ai_hedef_modeli` (seans/hazırlık; yalnız
    `_ai_loop_lock` altında yazılır, start onu MÜHÜRDEN okur). Bilinmeyen bir ad kalırsa döngü
    ölmesin diye varsayılana (kedi) düşülür — istemci doğrulaması uçlarda 422 ile zaten yapılır."""
    _yerel = getattr(_ai_hedef_yerel, "saglayici", None)
    if _yerel is not None:
        return _yerel
    try:
        return ai_pro_hedef.saglayici_al(_ai_hedef_modeli)
    except ValueError:
        logger.error("AI Pro: bilinmeyen hedef modeli %r → varsayılana düşüldü", _ai_hedef_modeli)
        return ai_pro_hedef.saglayici_al(None)


def _localize_organ(frame, organ_id):
    """Kareden seçili HEDEFİ lokalize et — AKTİF SAĞLAYICIYA delege eder (Faz 1, 2026-09-08).

    Kedi sağlayıcısında davranış DEĞİŞMEDİ: cat_organ pipeline (YOLOseg + DLC + RTMPose + PnP,
    ~1-4sn) → 10 organ 3B; hedefin coord_cabin_cm(ArUco)/coord_3d_cm → cm→mm [-300,300] clamp;
    organ_id 0 (Tüm Vücut) → (0,0,0); ai_service_enabled() ise GPU'ya devredilir (hata → CPU).

    ⚠️ Bu ADIN ve 8'li tuple sözleşmesinin korunması bilinçlidir: hazırlık/seans/mobil üç yolu da
    buradan geçer ve 9+ test bu adı monkeypatch'ler. Çağıranlar sonucu YILDIZLI açar (bkz.
    tests/test_ai_pro_seans_dongusu_lokalizasyon.py).
    Döner: (localized, x_mm, y_mm, z_mm, reliability, overlay_bgr, ozne_var, guven_dokumu)."""
    return _aktif_saglayici().localize(frame, organ_id)


def _predict_and_drive_cpu(x_mm, y_mm, z_mm, organ_id):
    """em_kedi'yi YEREL (in-process CPU) çalıştır → D[7]/P[7]/e_field. (tek-EXE + GPU-fallback yolu).
    Eski PyQt davranışı: duty 0..0.50 clip (modelin kendi politikası); EK clamp yok."""
    predictor = _get_or_load_kedi()
    result = predictor.predict(
        x=x_mm,
        y=y_mm,
        z=z_mm,
        organ_id=organ_id,
        achieved_B=_AI_ACHIEVED_B,
        duty_sum=_AI_DUTY_SUM,
    )
    # ⚠️ HAM: duty kirpmasi `_predict_and_drive` ZARFINDA (2026-09-08, tek kaynak).
    D = [float(result.get(f"D{i}", 0.0)) for i in range(1, 8)]
    P = [float(result.get(f"P{i}", 0.0)) for i in range(1, 8)]  # zaten bobin-1 referanslı
    e_field = float(max(0.0, result.get("result_E", 0.0)))
    return D, P, e_field


def _predict_and_drive_gpu(x_mm, y_mm, z_mm, organ_id):
    """em_kedi sürüş inference'ını GPU servisine DEVRET (delegate_json_sync; zaten to_thread'de) → D/P/E.
    (Hoca yönü: AI Pro'nun bobin-sürüş modeli de Docker/GPU'da.) Aynı duty-clip(0..0.50) + faz-referansı."""
    resp = delegate_json_sync(
        "em_kedi",
        {
            "x": x_mm,
            "y": y_mm,
            "z": z_mm,
            "organ_id": int(organ_id),
            "achieved_B": _AI_ACHIEVED_B,
            "duty_sum": _AI_DUTY_SUM,
        },
    )
    # ⚠️ HAM: duty kirpmasi `_predict_and_drive` ZARFINDA (2026-09-08, tek kaynak).
    D = [float(resp.get(f"D{i}", 0.0)) for i in range(1, 8)]
    P = [float(resp.get(f"P{i}", 0.0)) for i in range(1, 8)]
    e_field = float(max(0.0, resp.get("result_E", 0.0)))
    return D, P, e_field


def _predict_and_drive(x_mm, y_mm, z_mm, organ_id):
    """EM doz modeli → D[7]/P[7]/e_field — AKTİF SAĞLAYICIYA delege eder (Faz 1, 2026-09-08).

    ⚠️ DUTY KIRPMASI ARTIK TEK YERDE: burada. Eskiden `_predict_and_drive_cpu`/`_gpu` içinde iki
    kez yazılıydı (0..0.50 literali) ve YALNIZ kedi yolunu kapsıyordu; sağlayıcı arayüzü gelince
    yeni bir model kırpmasız kalabilirdi. Kırpma zarfa alınınca HER sağlayıcı aynı politikadan
    geçer ve onay ekranında gösterilen D ile donanıma giden D aynı olur (`_drive_coils_ai_pro` ve
    `_build_ai_pro_percoil` zaten `normalize_ai_pro_duty_ratio` kullanıyor). Sınır DEĞİŞMEDİ:
    `AI_PRO_DUTY_MAX_RATIO` (0.50) — bu YENİ bir backend güvenlik sınırı DEĞİL, mevcut model
    politikasının tek kaynağa alınmasıdır.

    TAM başarısızlıkta (0,0,0) döner = bobin SÜRÜLMEZ (güvenli varsayılan, değişmedi).
    Döner: (D_list[7], P_list[7], e_field)."""
    sag = _aktif_saglayici()
    try:
        D, P, e_field = sag.predict(x_mm, y_mm, z_mm, organ_id)
    except Exception as pred_err:
        logger.error("AI Pro doz tahmini hatası (model=%s): %s", getattr(sag, "ad", "?"), pred_err)
        return [0.0] * 7, [0.0] * 7, 0.0
    return (
        [float(d) for d in np.clip(D, 0.0, AI_PRO_DUTY_MAX_RATIO)],
        [float(p) for p in P],
        float(max(0.0, e_field)),
    )


def _ai_pro_bobinleri() -> list:
    """D1.83 (S-1.1 · Y25): AI Pro planının (em_kedi D[7]) SÜRÜLEBİLİR bobinleri — TEK KAYNAK `live_state.STM_COIL_IDS`
    (faz 4'ten beri 1-7 STM'de, 8 ESP'de). Topoloji değişirse plan bobini burada görünmez → "sürülmedi" (ölü yayın YOK)."""
    from servers.live_state import STM_COIL_IDS

    return [c for c in range(1, 8) if c in STM_COIL_IDS]


# ── Y54 (sahip, İNCELEME-2 i1-F-2): operatörün tekil STOP'u o bobini AI Pro PLANINDAN çıkarır ─────────────────────────
# Ölçüldü: AI Pro sürerken `/api/coil/{id}/control start:false` bir sonraki karede (≤ 1 sn) geri alınıyordu — bobin yeniden
# enerjileniyordu. Operatörün durdurma isteği otomasyona YENİLMEZ: bobin o AI Pro seansının (hekim onay kimliği) SONUNA KADAR
# sürülmez; diğer bobinler sürer. STOP'un kendisi kapılanmaz (Ö.4-Y8) — bu küme yalnız otomasyonun yeniden START'ını keser.
# Yeni AI Pro seansı (yeni onay) temiz başlar.
_ai_pro_plan_disi: dict = {"onay": None, "bobinler": set()}
_ai_pro_plan_disi_kilit = _ai_threading.Lock()


def _ai_pro_seans_onayi():
    """Etkin AI Pro seansının onay kimliği (yoksa None) — plan-dışı kümesinin anahtarı."""
    try:
        import servers.api_server as _api

        with _api._session_lock:
            s = dict(_api._active_session)
    except Exception:
        return None
    if s.get("is_active") and s.get("tur") == "ai_pro" and s.get("onay_kimligi"):
        return s["onay_kimligi"]
    return None


def ai_pro_bobinlerini_plandan_cikar(bobinler) -> list:
    """Y54: operatör bu bobinleri durdurdu — etkin AI Pro seansı varsa planından ÇIKAR. @return yeni çıkarılanlar.
    STOP gönderiminden ÖNCE çağrılır (sonraki kare çıkarılmış bobini görür); istisna atmaz."""
    onay = _ai_pro_seans_onayi()
    if onay is None:
        return []
    plan = set(_ai_pro_bobinleri())
    yeni = []
    with _ai_pro_plan_disi_kilit:
        if _ai_pro_plan_disi["onay"] != onay:
            _ai_pro_plan_disi["onay"] = onay
            _ai_pro_plan_disi["bobinler"] = set()
        for b in bobinler:
            try:
                b = int(b)
            except (TypeError, ValueError):
                continue
            if b in plan and b not in _ai_pro_plan_disi["bobinler"]:
                _ai_pro_plan_disi["bobinler"].add(b)
                yeni.append(b)
    return yeni


def _ai_pro_plan_disi_bobinler(onay=None) -> set:
    """Y54: ETKİN AI Pro seansının plan dışı bobinleri (başka / bitmiş seansınki sayılmaz)."""
    onay = _ai_pro_seans_onayi() if onay is None else onay
    with _ai_pro_plan_disi_kilit:
        if onay is None or _ai_pro_plan_disi["onay"] != onay:
            return set()
        return set(_ai_pro_plan_disi["bobinler"])


def _canli_e_odak() -> None:
    """ODK6 (istem 45): bu turda SÜRÜLEN ODAK planının CST E'si (hedef / çevre, tepe V/m) → canlı E çubuğu. Sağlayıcı ODAK değilse
    (`son_odak_e` yok) dokunmaz → analiz bağlamının vekil yolu aynen. Hata sürüşü ETKİLEMEZ (yalnız gösterim)."""
    try:
        _odak_e = getattr(_aktif_saglayici(), "son_odak_e", None)
        if _odak_e is not None:
            from servers import efield_live as _ef_odak

            _ef_odak.odak_guncelle(_odak_e)
    except Exception:
        logger.debug("ODAK canlı E yazılamadı (yalnız gösterim)", exc_info=True)


def _drive_coils_ai_pro(D, P) -> list:
    """
    em_kedi çıktısı D[7]/P[7] ile bobin 1-7'yi PER-COIL sürer (paylaşımlı tek faz YOK) → GERÇEKTEN sürülen bobinler.
      - Bobin 1-7: `STM_COIL_IDS` tek kaynağından `hardware_controller.update_coil` (duty yüzde, freq=`_AI_PRO_FREQ_HZ` 100 Hz, per-coil faz).
        ⚠️ D1.83/D1.84 (S-1.1 · B-5.2 · Y25): 6-7 eskiden `for idx in (5, 6)` → MQTT `pemf/coil/{6,7}/control`
        yayınıyla "sürülüyordu"; faz 4'ten beri 6-7 STM'de → telde duty 0, konular ÖLÜ (1-C §9 #3), panel/kayıt ise 7
        bobini uygulanmış gösteriyordu. `update_coil`'in dönüşü artık OKUNUR (İG-5.32): reddedilen bobin "sürülmedi".
      - Bobin 8: SÜRÜLMEZ (kapalı).
    Döner: kabul edilen bobin kimlikleri (mühür yoksa / donanım yoksa boş liste).
    Limit/clamp EKLENMEZ — yalnız mevcut normalize_* yardımcıları (yüzde dönüşümü/0..360 faz).

    D1.81 / İG-5.9: SÜRE seans MÜHRÜNDEN (kalan süre) — bayat `_ai_duration_min` globali telde yanlış süre ve erken /
    geç kesilme demekti. Sürülebilir mühür yoksa HİÇ sürülmez. Niyet nesli çağıranın `estop_mandali.surus_baglami`
    bağlamından gelir ve `update_coil` onu DURUM KİLİDİ ALTINDA denetler (acil durdurma/durdurma sonrası uçuştaki tur
    reddedilir).
    """
    from servers.api_server import state

    _muhur = _ai_pro_surus_muhru()
    if _muhur is None:
        logger.warning("AI Pro sürüşü ATLANDI: sürülebilir (onaylı, süresi dolmamış) AI Pro seansı yok.")
        return []
    _kalan_s = _muhur["kalan_s"]
    _kalan_dk = max(1, _math.ceil(_kalan_s / 60.0))  # firmware dakika granülerliği (yukarı); yazılım deadline'ı saniye

    surulen: list = []
    if not (state and state.hardware):
        return surulen
    _plan_disi = _ai_pro_plan_disi_bobinler(_muhur["onay"])  # Y54: operatörün durdurduğu bobin SÜRÜLMEZ
    _surulecek = _ai_pro_bobinleri()
    # ⚠️ Y142: EN ALT sürüş katı (döngü ve `/frame` ORTAK) — mühür kedi modelindeyken (model alanı yoksa da) bayrak kapalıysa
    # hiçbir bobine START gitmez; `/start` ve kare yolunun kapıları bu katmana güvenmez, bu katman da onlara. Aşağıdaki plan-dışı
    # STOP bloğu (yalnız ARTAN STOP — Ö.4-Y8) AYNEN koşar.
    if _kedi_modeli_mi(_muhur.get("model") or "") and not _kedi_aipro_surus_acik():
        logger.warning("AI Pro sürüşü ATLANDI: kedi AI Pro sürüşü kapalı (Y142 — %s).", KEDI_AIPRO_SURUS_BAYRAGI)
        _surulecek = []
    for cid in _surulecek:
        if cid in _plan_disi:
            continue
        idx = cid - 1
        duty_pct = normalize_ai_pro_duty_ratio(D[idx]) * 100.0  # ratio→% (eski 0.50 cap)
        phase_i = normalize_phase_deg(P[idx])
        try:
            kabul = state.hardware.update_coil(
                cid,
                freq=_ai_pro_frek_hz,
                duty=duty_pct,
                phase=phase_i,
                duration=_kalan_dk,
                start=True,
                duration_seconds=_kalan_s,
            )
        except Exception as _he:
            logger.warning("AI Pro bobin %d sürüş hatası (sürülmedi): %s", cid, _he)
            continue
        if kabul:
            surulen.append(cid)
        else:
            logger.warning("AI Pro bobin %d SÜRÜLMEDİ: donanım komutu reddetti (ya da sürüş yetkisi geçersiz).", cid)
    # ⚠️ 1-E incelemesi (i-6.1, Y54): plan-dışı kümesi döngüden ÖNCE okunur. Operatörün tekil STOP'u döngü ORTASINA düşerse
    # (küme okunduktan sonra, o bobinin START'ından önce) bu karenin START'ı bobini yeniden enerjiliyordu ve sonraki kareler
    # onu yalnız ATLADIĞI için bobin seans boyunca telde kalıyordu — ekran "plandan çıkarıldı, sürülmedi" derken (ölçüldü).
    # Döngüden SONRA küme yeniden okunur: plan dışı olup telde ÇALIŞAN bobine STOP gider (yalnız ARTAR, Ö.4-Y8).
    _plan_disi_son = _ai_pro_plan_disi_bobinler(_muhur["onay"])
    if _plan_disi_son:
        try:
            _teldeki = state.hardware.calisan_bobin_durumu()
        except Exception:
            _teldeki = dict.fromkeys(_plan_disi_son)  # okunamazsa STOP gönderilir (güvenli taraf)
        for cid in sorted(_plan_disi_son):
            if cid not in _teldeki:
                continue
            try:
                state.hardware.update_coil(cid, 0.0, 0.0, 0.0, 0, start=False)
            except Exception:
                logger.exception("AI Pro: plan dışı bobin %d STOP'u gönderilemedi", cid)
        surulen = [c for c in surulen if c not in _plan_disi_son]
    return surulen


def _teldeki_ai_pro_bobinleri() -> dict:
    """İNCELEME-2 i1-F-1 (Y25 · B-5.2): AI Pro bobinlerinden şu an TELDE çalışanlar → {bobin: (freq Hz, duty %, faz °)}.

    ⚠️ NEDEN: sürüş komutu verilmeyen karede/turda — hedef-kaybı serisi N'den küçükken (kayıp STOP'u henüz yok) ya da
    yabancı izleyicinin karesinde — bobinler önceki komutla keep-alive'da ÇALIŞIR; ölçüldü: telde 7 bobin çalışırken yanıt/WS
    7 bobini "sürülmedi" (duty 0) diyordu. Okunamazsa boş (eski gösterim). Yalnız okuma: hiçbir şeyi durdurmaz/engellemez."""
    try:
        import servers.api_server as _api

        _hw = _api.state.hardware
        _durum = _hw.calisan_bobin_durumu() if _hw is not None and hasattr(_hw, "calisan_bobin_durumu") else {}
    except Exception:
        logger.debug("AI Pro: teldeki bobin durumu okunamadı (eski gösterim)", exc_info=True)
        return {}
    _ai = set(_ai_pro_bobinleri())
    return {
        int(c): (float(s["freq"]), float(s["duty"]) * 100.0, float(s["phase"]))
        for c, s in _durum.items()
        if int(c) in _ai
    }


def _build_ai_pro_percoil(D, P, surulen=(), teldeki=None):
    """7-bobinlik perCoil yükü (PLANLANAN per-coil AI duty/phase, yüzde) + `suruldu` (telde GERÇEKTEN sürüldü mü).
    Bobin 8 yok (kapalı). D1.84 (B-5.2): eskiden plan değeri "uygulandı" diye okunuyordu (6-7 telde 0'ken); `suruldu`
    yalnız `_drive_coils_ai_pro`'nun kabul ettiği bobinlerde True — ekran 6-7 (ve herhangi bir bobin) için gerçeği gösterir.
    `teldeki` (İNCELEME-2 i1-F-1): bu karede sürülmeyen ama telde ÇALIŞAN bobin TELDEKİ değerle `suruldu: True` döner —
    enerjili bobin "sürülmedi" gösterilmez (`_teldeki_ai_pro_bobinleri`; yalnız AI Pro seansı varken verilir)."""
    _s = set(surulen or ())
    _t = teldeki or {}
    _disi = _ai_pro_plan_disi_bobinler()  # Y54: panel "Bobin X AI Pro planından çıkarıldı" der
    out = []
    for idx in range(7):
        if (idx + 1) in _disi:
            out.append(
                {
                    "id": idx + 1,
                    "freq": 0.0,
                    "duty": 0.0,
                    "phase": 0.0,
                    "suruldu": False,
                    "planDisi": True,
                }
            )
            continue
        if (idx + 1) not in _s and (idx + 1) in _t:
            _f, _d, _ph = _t[idx + 1]
            out.append(
                {"id": idx + 1, "freq": round(_f, 1), "duty": round(_d, 1), "phase": round(_ph, 1), "suruldu": True}
            )
            continue
        out.append(
            {
                "id": idx + 1,
                "freq": round(_ai_pro_frek_hz, 1),
                "duty": round(normalize_ai_pro_duty_ratio(D[idx]) * 100.0, 1),
                "phase": round(normalize_phase_deg(P[idx]), 1),
                "suruldu": (idx + 1) in _s,
            }
        )
    return out


def _ai_hazirlik_loop():
    """WEB/sunucu-kameralı HAZIRLIK önizlemesi: kamerayı açar, seçili organı periyodik LOKALİZE eder
    (cache'i günceller) ama BOBİN SÜRMEZ ve SEANS BAŞLATMAZ (`_active_session`e / `_ai_loop_active`e
    dokunmaz). Panel /ai/pro/status'tan `localized` görünce öneriyi (propose) OTOMATİK ister.

    ⚠️ TEK KAMERA: gerçek seans loop'u (`_ai_pro_loop`) da AYNI kabin kamerasını açar (T2D-2); ikisi AYNI ANDA
    açamaz. `/ai/pro/start` bu önizlemeyi ÖNCE durdurup kamerayı bıraktırır (join), sonra seans
    loop'unu başlatır. `/ai/pro/hazirlik/baslat` da seans aktifken (`_ai_loop_active`) başlamaz.
    ⚠️ Lokalizasyon yolu `_ai_pro_loop` ile BİREBİR (relocalize-tüket + organ-snapshot, denetim P2);
    değişirse İKİSİ birlikte güncellenmeli."""
    global _ai_hazirlik_active, _ai_relocalize, _ai_hazirlik_hata, _ai_hazirlik_hata_kodu, _ai_hazirlik_hata_saglayici
    _sag = _aktif_saglayici()
    logger.info("AI Pro HAZIRLIK önizlemesi BAŞLADI (model=%s, sunucu kamerası, sürüş YOK).", _sag.ad)
    # MODEL KAMERADAN ÖNCE (2026-09-09): eskiden kamera açılıp SONRA model yükleniyordu. Ağır
    # sağlayıcılarda (petri: 239 MB ONNX + 90 MB YOLO + ısıtma) bu, kameranın yükleme boyunca
    # TUTULMASI demekti; araya /ai/pro/start girerse `_ai_hazirlik_durdur_ic` join'i dolar ve seans
    # loop'u kamerayı alamazdı. Yükleme önce yapılınca kamera tutma süresi yükten bağımsız olur.
    try:
        _sag.yukle()
    except Exception as e:
        logger.error("Hazırlık: %s yüklenemedi (kamera hiç açılmadı): %s", _sag.ad, e)
        _ai_hazirlik_hata_kodu, _ai_hazirlik_hata = _hazirlik_hata_sinifi(e, _sag)
        _ai_hazirlik_hata_saglayici = _sag
        _ai_hazirlik_active = False
        return
    # T2D-2 (Tezgâh-2 #3): sabit `VideoCapture(0)` dahili kamerayı açıyordu → seçili KABİN kamerası, ilk okumadan önce 1920×1080.
    try:
        cap, _kamera_no = kabin_kamerasi.kamera_ac(cv2)
    except kabin_kamerasi.KameraSecilmedi as e:
        logger.error(
            "Hazırlık: kabin kamerası SEÇİLMEDİ / kimliği bulunamadı — kamera açılmadı (başka kameraya düşülmez)."
        )
        _ai_hazirlik_hata_kodu = "kamera_secilmedi"
        _ai_hazirlik_hata = (
            kabin_kamerasi.secim_hatasi_metni(e)
            if isinstance(e, kabin_kamerasi.KameraBulunamadi)
            else _hazirlik_hata_metni("kamera_secilmedi", "")
        )
        _ai_hazirlik_hata_saglayici = _sag
        _ai_hazirlik_active = False
        return
    if not cap.isOpened():
        logger.error("Hazırlık: kabin kamerası açılamadı (indeks %s).", _kamera_no)  # ham ayrıntı YALNIZ log'a
        cap.release()
        _ai_hazirlik_hata_kodu = "kamera"
        _ai_hazirlik_hata = _hazirlik_hata_metni("kamera", "")
        _ai_hazirlik_hata_saglayici = _sag
        _ai_hazirlik_active = False
        return
    # B3 (siyah ekran): önizleme kareleri istemciye HİÇ gitmiyordu (yalnız _ai_pro_loop `ai_vision`
    # yayınlıyordu) → web paneli hazırlıkta kapkara kalıyor, "kedi var/yok"u da öğrenemiyordu.
    # Seans loop'uyla AYNI `ai_vision` şeması (perCoil boş, remainingSec 0) + `preview: True`.
    _son_yayin = 0.0
    try:
        from servers.api_server import _ws_broadcast_sync as _yayinla
    except Exception:  # api_server yoksa (izole test) yayın atlanır
        _yayinla = None
    try:
        while _ai_hazirlik_active:
            if _ai_hazirlik_started_at and (time.monotonic() - _ai_hazirlik_started_at) >= _AI_HAZIRLIK_TAVAN_S:
                logger.info("Hazırlık tavanı (%s sn) doldu — önizleme kendiliğinden duruyor.", _AI_HAZIRLIK_TAVAN_S)
                break
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.3)
                continue
            now = time.time()
            need_localize = (
                _ai_relocalize
                or _ai_organ_cache["organ_id"] != _ai_organ_id
                or (now - _ai_organ_cache["at"]) >= _ORGAN_LOCALIZE_INTERVAL_S
            )
            if need_localize:
                # ⚠️ _ai_pro_loop'un lokalizasyon bloğuyla BİREBİR (organ-snapshot + relocalize-ÖNCE-tüket,
                # denetim P2): işlem sırasında gelen organ/relocalize isteği YUTULMAZ.
                _oid = _ai_organ_id
                _ai_relocalize = False
                _kayip_damgasi = estop_mandali.kayip_nesli()  # i7-F-1: gözlem LOKALİZASYON BAŞINDA damgalanır
                try:
                    # *l_ek: 8. eleman guven_dokumu (2026-08-26) — eski 7'li tuple'lar (test
                    # mock'lari dahil) KIRILMADAN acilir (l_ek bos kalir, dokum None yazilir).
                    lz, lx, ly, lzz, lrel, lov, lkedi, *l_ek = _localize_organ(frame, _oid)
                    with _ai_cache_lock:
                        _ai_organ_cache.update(
                            {
                                "x_mm": lx,
                                "y_mm": ly,
                                "z_mm": lzz,
                                "reliability": lrel,
                                "localized": lz,
                                "kayip_damgasi": _kayip_damgasi,
                                "overlay_bgr": lov,
                                "at": now,
                                "organ_id": _oid,
                                "kedi_var": lkedi,  # anahtar adı korunur (anlam: "özne kadrajda")
                                # MODEL DAMGASI (Faz 1): propose tazelik kontrolü buna bakar —
                                # kedi hazırlığından kalan cache fantom önerisine "taze" görünmesin.
                                "model": _ai_hedef_modeli,
                                # Sağlayıcı meta'sı (Faz 2): kare üstü hedef adayları, kalibrasyon
                                # yöntemi, seçili hedefin E'leri, eğitim-aralığı işareti. Kedi'de BOŞ.
                                **_saglayici_cache_alanlari(),
                                "guven_dokumu": (l_ek[0] if l_ek else None),
                            }
                        )
                except Exception as le:
                    dongu_hatasini_bildir(  # D1.19 (B-10.121)
                        "Hazırlık cat_organ lokalizasyon hatası: %s", le, logger=logger, exc_info=False
                    )
                    with _ai_cache_lock:
                        _ai_organ_cache["localized"] = False
            # ── Önizleme yayını (B3): cache'li overlay (varsa) yoksa ham kare → web paneli ──
            if _yayinla is not None and (now - _son_yayin) >= _AI_HAZIRLIK_YAYIN_ARALIK_S:
                _son_yayin = now
                try:
                    with _ai_cache_lock:
                        _c = dict(_ai_organ_cache)
                    overlay = _c.get("overlay_bgr")
                    src = overlay if overlay is not None else frame
                    oh, ow = src.shape[:2]
                    sc = min(1.0, 960.0 / max(oh, ow))
                    ov = (
                        cv2.resize(src, (int(ow * sc), int(oh * sc)), interpolation=cv2.INTER_AREA) if sc < 1.0 else src
                    )
                    _, buffer = cv2.imencode(".jpg", ov, [cv2.IMWRITE_JPEG_QUALITY, 55 if overlay is not None else 50])
                    _yayinla(
                        {
                            "type": "ai_vision",
                            "data": {
                                "imageBase64": base64.b64encode(buffer).decode("utf-8"),
                                # [S7 adım 4] Kare boyutu istemcinin oran kilidi için (yalnız-ek).
                                "imageW": int(ov.shape[1]),
                                "imageH": int(ov.shape[0]),
                                "preview": True,
                                "detected": bool(_c.get("localized")),
                                "catDetected": bool(_c.get("kedi_var")),
                                "reliability": round(float(_c.get("reliability", 0.0)), 3),
                                "target": {
                                    "x": round(float(_c.get("x_mm", 0.0)), 1),
                                    "y": round(float(_c.get("y_mm", 0.0)), 1),
                                    "z": round(float(_c.get("z_mm", 0.0)), 1),
                                },
                                "eField": 0.0,
                                "organId": _ai_organ_id,
                                "organName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _ai_organ_id),
                                # YALNIZ-EK (Faz 1): mevcut anahtarlar aynen kalır (sürüm kayması deseni).
                                "model": _aktif_saglayici().ad,
                                "modelName": _aktif_saglayici().title,
                                "subjectLabel": _aktif_saglayici().subject_label,
                                "targetName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _ai_organ_id),
                                "targets": _ai_organ_cache.get("targets") or [],
                                "method": _ai_organ_cache.get("method") or "",
                                "kapiEylem": _ai_organ_cache.get("kapi_eylem") or "",  # YALNIZ-EK (KD-3a · B-KD3a.1)
                                "targetLabel": _ai_organ_cache.get("target_label") or "",
                                "perCoil": [],
                                "remainingSec": 0,
                                "durationMin": _ai_duration_min,
                            },
                        }
                    )
                except Exception as wse:
                    dongu_hatasini_bildir("Hazırlık önizleme WS yayın hatası: %s", wse, logger=logger, exc_info=False)
            time.sleep(0.05)  # CPU nefes payı (lokalizasyon zaten ~1-4 sn'de bir)
    finally:
        cap.release()
        _ai_hazirlik_active = False
        logger.info("AI Pro HAZIRLIK önizlemesi DURDU (kamera bırakıldı).")


def _ai_hazirlik_durdur_ic():
    """Önizleme loop'unu durdur ve KAMERANIN bırakılmasını BEKLE (join). `/ai/pro/start` seans
    kamerasını açmadan ÖNCE bunu çağırır → iki VideoCapture çakışmaz."""
    global _ai_hazirlik_active, _ai_hazirlik_thread
    _ai_hazirlik_active = False
    t = _ai_hazirlik_thread
    if t is not None and t.is_alive():
        # ⚠️ join, önizleme loop'unun O AN _localize_organ içinde (kesintisiz, ~1-4 sn) olabileceğini
        # KAPSAMALI: bayrak set edilse de o kare bitene kadar loop çıkamaz → kamerayı bırakamaz.
        # Kısa timeout (3 sn) 4 sn'lik lokalizasyonu kaçırıp handoff'ta çift VideoCapture'a yol
        # açıyordu (adversaryal inceleme MAJOR). _ai_pro_loop açılışta ayrıca retry yapar (savunma).
        # Sağlayıcı bazlı süre (2026-09-09): ağır modellerde bir lokalizasyon turu daha uzun
        # sürebilir; kısa timeout kamera devrinde çift VideoCapture'a yol açar.
        t.join(timeout=float(getattr(_aktif_saglayici(), "join_timeout_s", 6.0)))
    _ai_hazirlik_thread = None


def _ai_pro_loop(dongu_muhru=None):
    """Sunucu kameralı AI Pro kapalı döngüsü.

    `dongu_muhru` (D1.81 · İG-5.11/5.29/5.3): `{"nesil", "onay", "dongu"}` — `/ai/pro/start` verir. Döngü YALNIZ
    nesli geçerli (durdurma/acil durdurma yok, mandal yok) VE kendi numarası güncel iken sürer; her sürüşü bu nesille
    yapar (`update_coil` kilit altında denetler). Böylece (a) tahmin/lokalizasyon sırasında (damla serviste dakikalar)
    gelen acil durdurmadan sonra tur bobini yeniden enerjileyemez, (b) `/stop`→`/start` ms içinde gelse de eski döngü
    çıkar (birikmez). `None` = eski çağıranlar (yalnız mandal denetlenir)."""
    global _ai_loop_active, _ai_relocalize
    logger.info("AI Pro Closed-Loop (cat_organ organ-lokalizasyon + em_kedi) arkaplan görevi BAŞLADI.")
    _nesil = dongu_muhru.get("nesil") if dongu_muhru else None

    def _dongu_gecerli() -> bool:
        if dongu_muhru is None:
            return True
        return dongu_muhru.get("dongu") == _ai_dongu_no and not estop_mandali.baslatma_engeli(_nesil)

    # WEB handoff (2026-08-25): hazırlık önizlemesi kamerayı henüz bırakıyor olabilir (join,
    # kesintisiz ~4 sn'lik bir lokalizasyonu aşabilir) → açılışı birkaç kez DENE (0,5 sn arayla) ki
    # çift-open yüzünden doktor-ONAYLI seans sessizce ölmesin (adversaryal inceleme MAJOR savunması).
    # MODEL KAMERADAN ÖNCE (2026-09-09; hazırlık döngüsüyle aynı gerekçe): ağır sağlayıcının
    # yüklemesi kamerayı tutmasın. Hata hâlinde kamera HİÇ açılmadığı için sızıntı da yok.
    try:
        _aktif_saglayici().yukle()
    except Exception as e:
        logger.error("AI Pro modeli yüklenemedi (kamera hiç açılmadı): %s", e)
        _dongu_bayragini_indir(dongu_muhru)
        _ai_seansi_pasife_al("model yüklenemedi", dongu_muhru)
        return

    # T2D-2 (Tezgâh-2 #3): seçili KABİN kamerası (sabit 0 değil), ilk okumadan önce 1920×1080; seçim yoksa açılmaz.
    try:
        cap, _kamera_no = kabin_kamerasi.kamera_ac(cv2)
        for _ in range(5):
            if cap.isOpened():
                break
            cap.release()
            time.sleep(0.5)
            cap, _kamera_no = kabin_kamerasi.kamera_ac(cv2)
    except kabin_kamerasi.KameraSecilmedi:
        logger.error(
            "Kabin kamerası SEÇİLMEDİ / kimliği bulunamadı — AI Pro kamerası açılmadı (başka kameraya düşülmez). AI Pro durduruluyor."
        )
        _dongu_bayragini_indir(dongu_muhru)
        _ai_seansi_pasife_al("kabin kamerası seçilmedi", dongu_muhru)
        return
    if not cap.isOpened():
        logger.error("Kabin kamerası açılamadı (indeks %s, tekrarlı denemeye rağmen). AI Pro durduruluyor.", _kamera_no)
        cap.release()
        _dongu_bayragini_indir(dongu_muhru)
        # `start_ai_session` bu thread spawn edilmeden ÖNCE çağrıldı → oturum AI modunda AKTİF.
        # Pasife almazsak panel/geçmiş seansı "sürüyor" gösterir (bobin sürülmediği hâlde).
        _ai_seansi_pasife_al("kamera açılamadı", dongu_muhru)
        return

    _lost_streak = 0  # ardisik hedef-kaybi sayaci (bkz. _AI_LOST_STOP_STREAK)
    # C2-1.1: döngü KENDİ süre sayacıyla bittiyse kapanış "Tamamlandı" yazar (kesinti DEĞİL; süre bekçisiyle aynı sebep).
    _sure_doldu = False
    while _ai_loop_active and _dongu_gecerli():
        start_time = time.time()
        # Dış STOP (acil-durdur / süre-watchdog / STM-disconnect / /session/stop) AI loop'u da durdursun.
        try:
            import servers.api_server as _api

            with _api._session_lock:
                _ext_active = bool(_api._active_session.get("is_active"))
            if not _ext_active:
                logger.info("AI Pro: seans dışarıdan durduruldu → loop sonlandırılıyor.")
                # DENETIM P0: bayrak TEMIZLENMEDEN break edilirse asagidaki teardown guard'i
                # (:730 `if _ai_loop_active: return`) bunu "yeni loop basladi" sanip bobin
                # STOP'unu ATLIYORDU. Dis durdurma (E-stop / sure-watchdog / /session/stop)
                # surus penceresine denk geldiginde bobinler keep-alive ile ENERJILI kaliyordu.
                # Sure-bitisi (:679) ve /ai/pro/stop (:813) yollari zaten temizliyor; yalniz bu
                # yol asimetrikti. start_ai_pro atomik check-and-set yaptigindan (:775-778)
                # bayrak True iken ikinci loop zaten baslayamaz → burada temizlemek guvenli;
                # bundan SONRA yeni loop baslarsa teardown guard'i onu dogru korur.
                # D1.81: yalnız bu döngü hâlâ güncelse (yeni döngünün bayrağı ezilmesin).
                _dongu_bayragini_indir(dongu_muhru)
                break
        except Exception:
            dongu_hatasini_bildir(  # B-4.2 · D1.19 (B-10.121)
                "AI Pro loop: seans durum kontrolü hatası (yok sayıldı)", logger=logger, seviye=logging.DEBUG
            )
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.5)
            continue

        try:
            from servers.api_server import _ws_broadcast_sync, update_live_session_state

            now = time.time()

            # ── cat_organ periyodik organ-lokalizasyon (HER KARE DEĞİL: ~1-4sn → cache) ──
            need_localize = (
                _ai_relocalize
                or _ai_organ_cache["organ_id"] != _ai_organ_id
                or (now - _ai_organ_cache["at"]) >= _ORGAN_LOCALIZE_INTERVAL_S
            )
            if need_localize:
                try:
                    # DENETIM P2 (organ-degisim yarisi): lokalizasyon 1-4 sn surer. Eskiden
                    # cache guncellenirken `_ai_organ_id` GLOBALI YENIDEN okunuyordu → bu sure
                    # icinde klinisyen /api/ai/pro/organ ile organi degistirdiyse ESKI organin
                    # koordinatlari YENI organin etiketiyle damgalaniyordu. Sonraki 10 sn boyunca
                    # need_localize'in uc kosulu da False kaldigindan em_kedi, yeni organ icin
                    # uretilmis duty/faz desenini ESKI organin konumuna odakliyordu; UI ise dogru
                    # organ adini gosteriyordu (enerji yanlis organa). Ayrica `_ai_relocalize`
                    # KOSULSUZ temizlendigi icin, lokalizasyon ucarken basilan "yeniden konumla"
                    # istegi de sessizce yutuluyordu.
                    # Cozum: iterasyon basinda organ kimligini SNAPSHOT al, cache'i onunla damgala;
                    # relocalize bayragini yalnizca ARADA yeni istek GELMEDIYSE temizle.
                    _oid = _ai_organ_id
                    # Bayragi ONCE tuket: bu lokalizasyon zaten mevcut istegi karsiliyor. Boylece
                    # islem SIRASINDA gelen yeni bir istek bayragi tekrar True yapar ve SONRAKI
                    # iterasyonda yeniden lokalize edilir — istek YUTULMAZ. (Sonradan kosulsuz
                    # temizlemek, ayirt edilemedigi icin taze istegi siliyordu.)
                    _ai_relocalize = False
                    # ⚠️ *l_ek ZORUNLU (2026-09-08 düzeltmesi): `_extract_organ_target` 2026-08-26'dan
                    # beri 8 eleman döndürüyor (8. = guven_dokumu). Hazırlık (:1016) ve mobil kare
                    # (:1796) yolları yıldızlı açılıma geçirilmiş, SEANS döngüsü unutulmuştu → her
                    # lokalizasyon "too many values to unpack" ile aşağıdaki except'e düşüyor,
                    # localized=False kalıyor ve bobin HİÇ sürülmüyordu (onaylı seans "aktif"
                    # görünürken tedavi uygulanmıyor; 3. turda yanıltıcı "hedef kaybı" STOP'u).
                    # Kapı: tests/test_ai_pro_seans_dongusu_lokalizasyon.py (yıldızsız açılım → KIRMIZI).
                    # 1-C inceleme i7-F-1: gözlem LOKALİZASYON BAŞINDAKİ kayıp nesliyle damgalanır (kare bu andan).
                    _kayip_damgasi = estop_mandali.kayip_nesli()
                    lz, lx, ly, lzz, lrel, lov, lkedi, *l_ek = _localize_organ(frame, _oid)
                    with _ai_cache_lock:
                        _ai_organ_cache.update(
                            {
                                "x_mm": lx,
                                "y_mm": ly,
                                "z_mm": lzz,
                                "reliability": lrel,
                                "localized": lz,
                                "kayip_damgasi": _kayip_damgasi,
                                "overlay_bgr": lov,
                                "at": now,
                                "organ_id": _oid,  # SNAPSHOT: global yeniden okunmaz
                                # E3 (denetim 2026-08-24): loop `lkedi`yi çözüp ATIYORDU — cache'i
                                # yalnız mobil /frame yolu (:1411) güncelliyordu. Web/sunucu-kameralı
                                # seansta ws `catDetected` bu yüzden bayat kalıyordu (aşama şeridi +
                                # 409 ipucu yanlış yönlendirme). Frame yolu paritesi.
                                "kedi_var": lkedi,  # anahtar adı korunur (anlam: "özne kadrajda")
                                # MODEL DAMGASI (Faz 1): propose tazelik kontrolü buna bakar —
                                # kedi hazırlığından kalan cache fantom önerisine "taze" görünmesin.
                                "model": _ai_hedef_modeli,
                                # Sağlayıcı meta'sı (Faz 2): kare üstü hedef adayları, kalibrasyon
                                # yöntemi, seçili hedefin E'leri, eğitim-aralığı işareti. Kedi'de BOŞ.
                                **_saglayici_cache_alanlari(),
                                # Sunum-katmanı XAI paritesi (2026-09-08): hazırlık ve mobil kare
                                # yolları güven dökümünü yazıyordu, seans yolu yazmıyordu → seans
                                # boyunca /status ve WS `guvenDokumu` hazırlıktan kalan BAYAT değeri
                                # (ya da None) taşıyordu. Panel "Güven %X"in nedenini yanlış gösterir.
                                "guven_dokumu": (l_ek[0] if l_ek else None),
                            }
                        )
                except Exception as le:
                    logger.error("cat_organ lokalizasyon hatası: %s", le)
                    # Audit P2: lokalizasyon HATASINDA cache'i geçersiz kıl — aksi halde ESKİ localized=True
                    # + bayat x/y/z ile bobinler eski (yanlış) hedefe sürülüyordu (kedi kabinden çıkınca /
                    # hareket edince). mobil ai_pro_frame zaten 500 dönüp sürmüyordu → asimetriyi kapatır.
                    with _ai_cache_lock:
                        _ai_organ_cache["localized"] = False

            with _ai_cache_lock:
                localized = _ai_organ_cache["localized"]
                x_mm = _ai_organ_cache["x_mm"]
                y_mm = _ai_organ_cache["y_mm"]
                z_mm = _ai_organ_cache["z_mm"]
                rel = _ai_organ_cache["reliability"]
                kayip_damgasi = _ai_organ_cache.get("kayip_damgasi")
                # ⚠️ D1.59 (B-5.4): koordinatın ORGANI — aynı anlık görüntüden. Global `_ai_organ_id` lokalizasyon
                # sırasında değişmiş olabilir; tahmine o verilirse yeni organın deseni eski organın konumuna gider.
                _c_oid = _ai_organ_cache.get("organ_id")
            kedi_var = bool(_ai_organ_cache.get("kedi_var"))
            # Gösterilen organ = sürülen organ (koordinat bulunduysa); yoksa seçili hedef.
            _gosterim_oid = _c_oid if (localized and isinstance(_c_oid, int) and _c_oid >= 0) else _ai_organ_id
            # ⚠️ 1-C inceleme i7-F-1: bir hedef-kaybı STOP'undan ESKİ "bulundu" gözlemi (ör. STOP'tan sonra biten uçuştaki
            # lokalizasyon) BULUNDU SAYILMAZ: sürülmez, kayıp sayılır. Asıl kapı sürüşte (HC, durum kilidi altında).
            _bulundu = bool(localized) and not estop_mandali.gozlem_engeli(kayip_damgasi)
            # ⚠️ D1.60 (A-16, 2. katman): yalnız ONAYLANAN hedef sürülür (`/start`ın döngü mührü). Mühür dışı hedefin
            # koordinatı "hedef yok" sayılır → sürülmez, N turda STOP. Mühürsüz eski çağıranlar (`dongu_muhru` None) aynen.
            _surulebilir_hedef = _bulundu and (dongu_muhru is None or _c_oid == dongu_muhru.get("hedef"))
            _surulen: list = []  # D1.84: bu turda telde GERÇEKTEN sürülen bobinler (perCoil `suruldu`)

            # ── em_kedi → per-coil → sür (YALNIZCA organ bulunduysa; el yerine organ-tespiti koşulu) ──
            if _surulebilir_hedef:
                # Audit P1: E-stop/stop lokalizasyon (~1-4s) sırasında gelmiş olabilir → SÜRMEDEN ÖNCE
                # is_active'i yeniden doğrula (E-stop'un ~1 iterasyon geçersiz kılınmasını engelle).
                import servers.api_server as _apx

                with _apx._session_lock:
                    _still = bool(_apx._active_session.get("is_active"))
                if not _still:
                    _dongu_bayragini_indir(dongu_muhru)
                    break
                D, P, e_field = _predict_and_drive(x_mm, y_mm, z_mm, _c_oid)
                if not any(D):
                    # ⚠️ D1.E07 (İG-5.15, seans ortası): doz modeli hata verdi (zarf `[0]*7` döndürür) — eskiden bu "sürüş"
                    # olarak gönderiliyordu (bildirimsiz; panel "sürüldü"). SÜRÜLMEZ, operatöre söylenir ve hedef-kaybı
                    # gibi sayılır (N turda STOP — mevcut kural; yeni durdurma türü değil).
                    _doz_hatasi_bildir()
                    _surulebilir_hedef = False
                else:
                    # ⚠️ D1.81 (İG-5.3/5.29): yukarıdaki "seans hâlâ aktif mi" bakışı TAHMİNDEN ÖNCEDİR; tahmin (CPU 0,3–2,2
                    # sn, yanıtsız AI servisinde dakikalar) sırasında gelen acil durdurmayı göremez — ölçüldü: döngü 40'ta
                    # 11, damla serviste 36,5 sn sonra yeniden enerjiledi. Sürüş bu döngünün NESLİYLE yapılır; `update_coil`
                    # onu DURUM KİLİDİ ALTINDA denetler → bayatsa reddedilir. Sonra döngü de çıkar.
                    # i7-F-1: gözlem damgası da taşınır — tahmin sırasında kayıp STOP'u geldiyse `update_coil` kilit altında
                    # reddeder.
                    with estop_mandali.surus_baglami(_nesil), estop_mandali.gozlem_baglami(kayip_damgasi):
                        _surulen = _drive_coils_ai_pro(D, P) or []
                    if _surulen:
                        _canli_e_odak()  # ODK6: canlı E = bu turda sürülen ODAK planının CST E'si
                    if not _dongu_gecerli():
                        logger.warning("AI Pro: sürüş sırasında durdurma/acil durdurma geldi → döngü sonlandırılıyor.")
                        break
                    _lost_streak = 0  # hedef yeniden bulundu
            if not _surulebilir_hedef:
                D, P, e_field = [0.0] * 7, [0.0] * 7, 0.0
                # DENETIM P2: bu dalda YALNIZCA yeni komut gonderilmiyordu; halihazirda enerjili
                # bobinlere STOP GITMIYORDU. STM keep-alive son duty paketini saniyede bir
                # tazeledigi ve ESP kendi `duration`i boyunca surdugu icin, hayvan kabinden
                # cikinca/kimildayinca (guven < _MIN_RELIABILITY) HEDEFSIZ tedavi seans sonuna
                # kadar devam ediyordu. Ustelik WS `perCoil` %0 yayinladigi icin operator
                # bobinleri kapali saniyordu. _MIN_RELIABILITY yorumunun NIYETI zaten
                # "coil SURULMEZ"di; artik aktif olarak durduruluyor.
                # Tek kare kaybinda durdurmak tedaviyi kirilgan yapar (tespit anlik sekebilir) →
                # ARDISIK _AI_LOST_STOP_STREAK kayiptan sonra durdur, tekrar bulununca surmeye
                # devam eder (seansi bitirmez; sure-watchdog + teardown kendi isini gorur).
                _lost_streak += 1
                # ⚠️ 1-C inceleme i7-F-1 (arka kalkan): STOP eskiden yalnız `== N` turunda gidiyordu — kayıp STOP'unu atlatan
                # bir sürüşten sonra hedef kayıp kaldıkça bir daha STOP gelmiyordu. N ve sonrasındaki HER kayıp turunda STOP
                # yinelenir (idempotent; Ö.4-Y8: STOP yalnız artar); bildirim/günlük N turda bir (alarm yorgunluğu yok).
                if _lost_streak >= _AI_LOST_STOP_STREAK:
                    _bildir = _lost_streak % _AI_LOST_STOP_STREAK == 0
                    try:
                        estop_mandali.kayip_nesli_artir()  # uçuştaki "bulundu" gözlemleri bu STOP'tan SONRA süremez
                    except Exception:
                        logger.exception("AI Pro: kayıp nesli artırılamadı (STOP yine gönderilir)")
                    try:
                        import servers.api_server as _apx2

                        # Denetim 2. tur [1.1]: teyitsiz STOP'lar operatore bildirilir
                        # (broker oluyken hedef-kaybi durdurmasi sessizce dusuyordu).
                        _teyitsiz2 = _apx2._stop_session_coils(range(1, 8))
                        if _bildir:
                            _apx2._bildir_teyitsiz_stop(
                                _teyitsiz2, lambda d: ceviri.t("bildirim.kaynak.aiProHedefKaybi", dil=d)
                            )
                            logger.warning(
                                "AI Pro: hedef %d ardisik iterasyondur bulunamadi → bobinler DURDURULDU "
                                "(hedef yeniden bulunursa surus devam eder).",
                                _lost_streak,
                            )
                    except Exception:
                        logger.exception("AI Pro: hedef-kayip STOP hatasi")

            remaining = (
                max(0, int(_ai_duration_min * 60 - (time.monotonic() - _ai_started_at))) if _ai_started_at else 0
            )
            if _ai_started_at and remaining <= 0:
                _sure_doldu = True
                _dongu_bayragini_indir(dongu_muhru)  # süre doldu → otomatik durdur

            # Canlı seans göstergesi: bobin-1 AI duty'sini temsil değer olarak ver.
            # ⚠️ D1.89 (İNCELEME-2 §10 #5): duty AYRI alanda (`duty_temsil`, %) — mT reçete alanına (`intensity`) YAZILMAZ;
            # AI Pro'nun mT reçetesi yok (0 = reçete yok). Eskiden kart "%37 duty"yi "YOĞUNLUK (kayıt) 37 mT" gösteriyordu.
            rep_duty = round(normalize_ai_pro_duty_ratio(D[0]) * 100.0, 1) if localized else 0.0
            update_live_session_state(
                is_active=True,
                mode=f"AI Pro · {_aktif_saglayici().title} · {_aktif_saglayici().hedef_adi(_gosterim_oid)}",
                freq=_ai_pro_frek_hz,
                intensity=0.0,
                duty_temsil=rep_duty,
                remaining_min=remaining // 60,
                duration_sec=_ai_duration_min * 60,
                surus_nesli=_nesil,  # D1.81 (İG-5.36): bayat tur acil durdurmadan sonra "aktif" yazamaz
            )

            # ── Telemetri yayını: cache'li organ overlay + per-coil (React buradan dinler) ──
            overlay = _ai_organ_cache.get("overlay_bgr")
            if overlay is not None:
                oh, ow = overlay.shape[:2]
                sc = min(1.0, 960.0 / max(oh, ow))
                ov = (
                    cv2.resize(overlay, (int(ow * sc), int(oh * sc)), interpolation=cv2.INTER_AREA)
                    if sc < 1.0
                    else overlay
                )
                _kodlanan_kare = ov
                _, buffer = cv2.imencode('.jpg', ov, [cv2.IMWRITE_JPEG_QUALITY, 55])
            else:
                _kodlanan_kare = frame
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            b64_image = base64.b64encode(buffer).decode('utf-8')
            per_coil = _build_ai_pro_percoil(D, P, _surulen, _teldeki_ai_pro_bobinleri())
            ws_data = {
                "imageBase64": b64_image,
                # [S7 adım 4] Kare boyutu istemcinin oran kilidi için (yalnız-ek).
                "imageW": int(_kodlanan_kare.shape[1]),
                "imageH": int(_kodlanan_kare.shape[0]),
                "detected": localized,
                # AŞAMA (sahip isteği 2026-08-24): "kedi yok" ile "kedi var, organ bulunamadı"
                # ayrı bilgiler — hazırlık ekranı operatöre doğru yönlendirmeyi verir.
                "catDetected": kedi_var,
                "reliability": round(rel, 3),
                "target": {"x": round(x_mm, 1), "y": round(y_mm, 1), "z": round(z_mm, 1)},
                "eField": round(e_field, 4),
                "organId": _gosterim_oid,
                "organName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _gosterim_oid),
                # YALNIZ-EK (Faz 1): mevcut anahtarlar aynen kalır (sürüm kayması deseni).
                "model": _aktif_saglayici().ad,
                "modelName": _aktif_saglayici().title,
                "subjectLabel": _aktif_saglayici().subject_label,
                "targetName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _gosterim_oid),
                "targets": _ai_organ_cache.get("targets") or [],
                "method": _ai_organ_cache.get("method") or "",
                "kapiEylem": _ai_organ_cache.get("kapi_eylem") or "",  # YALNIZ-EK (KD-3a · B-KD3a.1)
                "targetLabel": _ai_organ_cache.get("target_label") or "",
                "perCoil": per_coil,
                "remainingSec": remaining,
                "durationMin": _ai_duration_min,
            }
            try:
                _ws_broadcast_sync({"type": "ai_vision", "data": ws_data})
            except Exception as wse:
                logger.error(f"WS broadcast error in AI loop: {wse}")

        except Exception as e:
            # D1.19 (B-10.121): bildirim fırlatırsa AI Pro sürüş döngüsü ölür (bobinler seans süresince
            # son ayarda kalır, süre bekçisi keser).
            dongu_hatasini_bildir("AI Loop iteration error: %s", e, logger=logger, exc_info=False)

        elapsed = time.time() - start_time
        sleep_time = max(0.1, 1.0 - elapsed)
        time.sleep(sleep_time)

    # O-A2-K.1: döngünün BİTTİĞİ andaki canlı E bağlamı nesli — kapanış (aşağıda) yalnız BU dönemin bağlamını temizler;
    # çıkıştan sonra (kamera bırakılırken, STOP yayınlanırken) yeni bir analizin kurduğu bağlam silinmez.
    try:
        from servers import efield_live as _ef_cikis

        _baglam_nesli = _ef_cikis.baglam_nesli()
    except Exception:
        _baglam_nesli = None
    cap.release()
    # Audit P2 (teardown-race seal): süre-doldu ile bu teardown arasındaki ~1sn'de yeni bir
    # start_ai_pro başlamış olabilir (_ai_loop_active tekrar True + yeni seans). O durumda YENİ seans
    # bobinlere sahiptir → bu ESKİ thread'in teardown'ı onları DURDURMASIN + is_active'ini EZMESİN.
    # D1.81 (İG-5.11): "yeni döngü" DÖNGÜ NUMARASIYLA bilinir — bayrak, eski döngünün bayat tur denetimi ile yeni
    # döngünün `/start`'ı arasında ms içinde değişebildiği için tek başına güvenilmez.
    # Loop bittiğinde (süre doldu / durduruldu / hata) bobinleri DONANIM düzeyinde durdur —
    # keep-alive ile sonsuza sürmesin (AI artık sürmüyor).
    # ⚠️ D1.81: döngünün sürüş yetkisi bir durdurma ile ZATEN kesildiyse (nesil bayat) o durdurma STOP'unu GÖNDERDİ ve
    # döngü sonrasında hiçbir şey süremedi → burada tekrar STOP gönderilmez: aradaki "yeni elle seans/tekil sürüş"ün
    # bobinlerini bu ESKİ döngü durduramaz. Yetki hâlâ geçerliyse (süre doldu, hata) bobinler bu döngünündür → durdurulur.
    # ⚠️ 1-C inceleme i3-F-1 (A-63 · Ö.4-Y8): mandal KURULUYKEN hiçbir START geçemez → "yeni seans" yoktur; STOP her
    # zaman gider (eskiden mandal da `baslatma_engeli`ni doldurduğu için E-stop sonrası teardown STOP'u atlanıyordu:
    # STM stop_all 2→1, ESP STOP 3→2 — yedek gönderim azaltılamaz).
    # ⚠️ 1-C inceleme i2-F5: "yeni döngü yok" kararı ile STM STOP'u AYNI kritik bölgede (`_ai_loop_lock`). Eskiden kilit
    # bırakıldıktan SONRA gönderiliyordu → arada başlayan YENİ onaylı seansın bobinleri durup nesli artıyor, yeni döngü
    # "bayat" sayılıp sessizce çıkıyordu (onayı yanmış, 30/30). STM STOP yalnız kuyruğa konur — beklemez (Ö.4-Y8);
    # ESP yayınları (saniyeler) kilidin DIŞINDA kalır. Kilit sırası `_ai_loop_lock` → HC `_state_lock` (ters yön yok).
    with _ai_loop_lock:
        _yeni_dongu = dongu_muhru is not None and dongu_muhru.get("dongu") != _ai_dongu_no
        if dongu_muhru is not None and not _yeni_dongu:
            _ai_loop_active = False  # bu (güncel) döngü bitiyor
        _atla = _yeni_dongu or (dongu_muhru is None and _ai_loop_active)
        _yetki_gecerli = dongu_muhru is None or estop_mandali.mandalli_mi() or not estop_mandali.baslatma_engeli(_nesil)
        if not _atla and _yetki_gecerli:
            try:
                import servers.api_server as _api_k

                if _api_k.state and _api_k.state.hardware:
                    _api_k.state.hardware.stop_all_coils()
            except Exception:
                logger.exception("AI Pro loop sonu STM STOP hatasi")
    if _atla:
        logger.info("AI Pro teardown atlandı: yeni loop başlamış (bobinler yeni seansa ait).")
        return
    try:
        import servers.api_server as _api2

        if _yetki_gecerli:
            # ESP 6-8'i de durdur (AI bunları da sürüyordu — audit #13).
            # ⚠️ FAZ 4: kapsam elle yaziliydi (yukaridaki ile ayni sinif). Tek kaynak.
            for _cid in sorted(_api2.ESP_COIL_IDS):
                try:
                    _api2._mqtt_publish(
                        f"pemf/coil/{_cid}/control",
                        {
                            "command": "stop",
                            # 1-C §9 #4 (D1.E10 deseni): süreç-içi sıra eki — yalnız ms'de aynı ms'deki iki STOP'tan
                            # ikincisi 8266 tekrar önbelleğinde yutulabiliyordu.
                            "command_id": _api2._komut_kimligi("ai_stop", _cid),
                        },
                    )
                except Exception:
                    logger.warning("AI Pro stop: bobin %s STOP publish hatası", _cid, exc_info=True)  # B-4.2
        _kesilen = None
        with _api2._session_lock:
            _s = _api2._active_session
            # Yalnız KENDİ seansını kapatır (mühürdeki onay kimliği); eski çağıranda önceki kural.
            _kendi = _s.get("onay_kimligi") == dongu_muhru.get("onay") if dongu_muhru is not None else _ai_seansi_mi(_s)
            if _kendi:
                if _s.get("is_active") and not _s.get("ai_pro_durduruluyor"):
                    # Seans hâlâ AKTİFSE (ve operatör durdurmuyorsa) döngü KENDİ kesildi (hedef kaybı / doz modeli hatası /
                    # kamera): durdurma, acil durdurma ve süre-watchdog oturumu önce pasife alıp satırı kendileri kapatır.
                    _kesilen = dict(_s)
                _s["is_active"] = False
            _baskasi_aktif = bool(_s.get("is_active")) and not _kendi
        # ⚠️ D2.E07 (YA-1): döngünün kendi kesintisi satırı "Kesintiye Uğradı" diye GERÇEK süreyle kapatır (STOP yukarıda gitti).
        _ai_pro_satirini_kapat(_kesilen, "sure-doldu" if _sure_doldu else "ai-pro-kesinti")
        if not _baskasi_aktif:
            # Mandal kuruluyken "Sistem Hazır" yazılmaz, "Acil Durdurma" kalır (live_state kuralı, İG-5.36).
            _api2.update_live_session_state(is_active=False, mode="Sistem Hazır", e_baglam_nesli=_baglam_nesli)
        # Canlı E bağlamını TEMİZLE (2026-09-09): fantom/petri seansı bağlamı kuruyor; seans
        # bitince temizlenmezse bir sonraki (kedi) seansta E barı ESKİ hedefin değerini "canlı"
        # göstermeye devam ederdi.
        try:
            from servers import efield_live as _ef2

            if _baglam_nesli is None:
                _ef2.set_context([])
            elif not _ef2.temizle_degismediyse(_baglam_nesli):
                # O-A2-K.1: döngü çıktıktan SONRA yeni bir analiz bağlam kurdu → onun; dokunulmaz.
                logger.info("AI Pro teardown: canlı E bağlamı döngü bittikten sonra yeniden kurulmuş — dokunulmadı.")
        except Exception:
            logger.debug("AI Pro teardown: canlı E bağlamı temizlenemedi", exc_info=True)
    except Exception:
        logger.exception("AI Pro loop sonu STOP hatasi")
    logger.info("AI Pro Closed-Loop arkaplan görevi DURDU.")


class AiProStartPayload(BaseModel):
    organ_id: int = 0
    duration_minutes: int = 20
    #: Hedef modeli: "kedi" | "fantom" | "petri" (Faz 1, 2026-09-08). YENİ ROTA AÇILMADI — model
    #: seçimi mevcut uçların gövdesinden gelir (route-contract sabit sayacı ve auth-muafiyet
    #: önekleri değişmez). Boş = "kedi" → `model` göndermeyen ESKİ istemcilerde davranış AYNI.
    #: ⚠️ `/ai/pro/start` bu alanı YOK SAYAR: model ONAY MÜHRÜNDEN okunur (organ/süre ile aynı
    #: ilke) — "fantom önerisini onaylat, kediyi başlat" yapısal olarak imkânsızdır.
    model: str = ""
    # SERT KAPI (2026-08-06 sahip kararı): onaylanmış öneri kimliği ZORUNLU.
    # Boş bırakılırsa istek 428 ile reddedilir — otonom tedavi hekim onayı olmadan başlamaz.
    proposal_id: str = ""
    #: Bu isteği yapan istemcinin kalıcı kimliği (bkz. `_ai_owner_client`). Boş bırakılabilir:
    #: eski istemcilerde davranış DEĞİŞMEZ (sahiplik bilinmez → panel eski kuralı uygular).
    client_id: str = ""
    #: T3 · Y189: KOŞULSUZ kip (yalnız araştırma modelleri — fantom / petri). HAZIRLIK bunu sağlayıcıya verir; `/start` YOK
    #: SAYAR ve mühürden okur (organ / model ile aynı ilke). Varsayılan False = davranış AYNI.
    kosulsuz: bool = False


class AiProProposePayload(BaseModel):
    organ_id: int = 0
    duration_minutes: int = 20
    #: Hedef modeli (bkz. `AiProStartPayload.model`). Öneri MÜHRÜNE (`specs.model`) yazılır ve
    #: seans başlangıcı onu mühürden okur.
    model: str = ""
    #: İstemcinin BİLDİRDİĞİ kullanıcı profili ("veterinarian" | "researcher" | ...). Yalnız
    #: DENETİM İZİ: backend profil bilmez ve buna göre yetki VERMEZ (AI uçları auth-muaf — sahip
    #: kararı); onay izinde "hangi profil bu dozu onaylattı" sorusu yanıtlanabilsin diye mühür
    #: meta'sına yazılır (api_server AI-log'undaki `mode` alanı emsali). Boş bırakılabilir.
    client_mode: str = ""
    #: ⚠️ D2.E15 (İG-5.14): seansın HASTASI (opak kimlik + ad) öneri MÜHRÜNE yazılır — organ/süre/model ile aynı ilke:
    #: "A için onaylat, B'ye başlat" yapısal olarak imkânsız; `/start` hastayı mühürden okur. Boş = hasta seçilmedi
    #: (seans bugünkü gibi sahipsiz kaydedilir; arayüz bunu ayrıca onaylatır).
    patient_id: str = ""
    patient_name: str = ""
    #: T3 · Y189: panelin seçili kipi. Önizleme konumu FARKLI kipte bulunduysa öneri 409 (kip değişti → önizleme yeniden);
    #: eşleşirse MÜHÜRE yazılır (`specs.kosulsuz`), `/start` seansı o kipte açar.
    kosulsuz: bool = False
    #: ODAK (istem 45 · Y273): kullanıcının SEÇTİĞİ doz (hedefte tepe |B|, mT). None → tavanın %80'i (onay penceresinde değiştirilir).
    doz_mT: float | None = None
    #: ODAK petri kipi: "TUM_PETRI" (24 kuyunun en zayıfı = doz) | "KUYUCUK" (seçili kuyu = doz; varsayılan). Diğer modellerde yok sayılır.
    odak_kip: str = ""
    #: ODK8: AI Pro frekansı (Hz) — `AI_PRO_FREKANSLARI`; None → 100. Mühüre yazılır, `/start` sürüşü bu frekansla yapar.
    frek_hz: float | None = None
    #: AP-B3 (istem 48, tezgâh 13-11): onay penceresinin kuyu HARİTASINDAN seçilen kuyu ("C6"). AYNI lokalizasyonun adaylarından plan;
    #: mühür o kuyunun KALICI kimliğiyle (görülen = sürülen). Kamerada sıvı görülmeyen (boş) kuyu aday değildir → `kuyuYok` (ODK11).
    #: Yalnız petri; diğer modellerde yok sayılır (`odak_kip` gibi). Boş = istenen hedef (`organ_id`).
    kuyu: str = ""


def _uzaktan_kimliksiz_mi(request) -> bool:
    """S-A1.1 (a) · Y123 (2-C incelemesi): istek tünelden / ters-proxy'den (cf-* ya da X-Forwarded-For) geliyor ve NE geçerli
    operatör jetonu NE geçerli cihaz token'ı taşıyor mu? AI Pro uçları auth-muaf (sahip kararı) — tünel ERİŞİMİ değişmez; yalnız
    böyle bir öneri hastaya BAĞLANMAZ. Ölçüldü (A1): saha kimlik kipinde anonim tünel `/propose` → `/approve` → `/start` 200 ile
    kimliği bilinen herhangi bir hastanın Seans Geçmişi'ne AI Pro satırı ve sahibinin e-postasını yazabiliyordu (aynı tünelden
    elle seans 401). Karar verilemezse BAĞLANMAZ (seans E15 öncesi gibi sahipsiz kaydedilir — tedavi engellenmez)."""
    try:
        h = request.headers
        if not (h.get("cf-connecting-ip") or h.get("cf-ray") or h.get("x-forwarded-for")):
            return False
        from servers import auth as _auth
        from servers import operator_tokens as _jetonlar

        if _jetonlar.cozumle(_auth._operator_jetonu(request)):
            return False
        _t = _auth._istek_tokeni(request)
        return not (_t and _auth.check_token(_t))
    except Exception:
        logger.exception("AI Pro önerisi: uzak istek kimlik denetimi yapılamadı → hasta BAĞLANMAZ (fail-closed)")
        return True


_ODAK_OZET_ALANLARI = (
    "kip",
    "doz_mT",
    "beklenen_mT",
    "tavan_mT",
    "cevre_mT",
    "oran",
    "frek_hz",
    "e_hedef_Vm",
    "e_cevre_Vm",
    "pay_yuzde",
    "sapma_yuzde",
    "kuyular",
    "kalibrasyon",
    "model",
)


def _odak_ozet(plan: dict) -> dict:
    """ODAK planının MÜHÜRE yazılan kısmı (onay penceresi + `/start`)."""
    return {k: plan.get(k) for k in _ODAK_OZET_ALANLARI if plan.get(k) is not None}


@ai_router.post("/api/ai/pro/propose")
def propose_ai_pro(request: Request, payload: AiProProposePayload = AiProProposePayload()):
    """AI'ın önerdiği tedavi parametrelerini ÜRET — DONANIMA DOKUNMADAN.

    SAHİP KARARI (2026-08-06, sert kapı): hekim önce ne uygulanacağını görür, sonra onaylar.
    Bu uç yalnız HESAPLAR: organ konumu (taze lokalizasyon önbelleğinden) → em_kedi → D[7]/P[7].
    Dönen `proposalId` onaylanmadan `/api/ai/pro/start` çalışmaz.

    ⚠️ DÜRÜSTLÜK: AI Pro KAPALI DÖNGÜdür — onay TEDAVİNİN BAŞLAMASINI kapıya bağlar, sonraki
    her döngü adımını DEĞİL. Hayvan hareket ettikçe `_ai_pro_loop` yeniden lokalize edip
    duty/faz'ı günceller; bunları dondurmak kapalı-döngü tasarımını bozardı. Onay = "bu hasta
    için bu organda otonom tedaviyi başlatıyorum" beyanıdır.
    """
    oid = int(payload.organ_id)
    # Hedef modeli: istemciden gelir, MÜHÜRE yazılır, /start onu mühürden okur (Faz 1).
    try:
        _saglayici = ai_pro_hedef.saglayici_al(payload.model)
    except ValueError as _me:
        raise HTTPException(status_code=422, detail=str(_me)) from None
    _arastirma_aipro_kapisi(_saglayici)  # kedi DIŞI model + bayrak kapalı → 409
    _duzlem_kalibrasyonu_kapisi(_saglayici)  # KD · Y259: araştırma modeli + geçerli kalibrasyon yok → 409
    if oid not in _saglayici.hedef_idleri():
        _gecerli = ", ".join(str(i) for i in sorted(_saglayici.hedef_idleri()))
        _ek = {"oid": oid, "model": ai_pro_hedef.model_adi(_saglayici), "gecerli": _gecerli}
        raise HTTPException(status_code=422, detail=ceviri.t("ai.pro.hata.hedefDesteklenmiyor", **_ek))
    with _ai_cache_lock:
        c = dict(_ai_organ_cache)
    # ⚠️ TAZELİK MODELE DE BAKAR (Faz 1): kedi hazırlığından kalan taze cache, fantom önerisine
    # "taze" görünüp YANLIŞ modelin koordinatıyla doz ürettirebilirdi.
    taze = (
        bool(c.get("localized"))
        and int(c.get("organ_id", -1)) == oid
        and str(c.get("model") or ai_pro_hedef.VARSAYILAN_MODEL) == _saglayici.ad
        and (time.time() - float(c.get("at") or 0)) < 120.0
    )
    if not taze:
        # ⚠️ MESAJ GERÇEĞE ÇEKİLDİ (saha bildirimi 2026-08-24): eski metin kullanıcıya
        # "'Yeniden konumla' ile lokalizasyonu tamamlayın" diyordu. Mobilde o düğme yalnız
        # sunucuda bir bayrak set ediyor ve kare akmadığı için HİÇBİR ŞEY olmuyordu — kullanıcı
        # aynı hataya kilitleniyordu. Akış düzeltildi (panel artık hazırlık aşamasında kare
        # akıtıyor); mesaj da ne olduğunu ve kimin ne yapacağını dürüstçe söylüyor.
        with _ai_cache_lock:
            _kedi = bool(_ai_organ_cache.get("kedi_var"))  # anahtar adı korunur: "özne kadrajda"
        _ad = ai_pro_hedef.hedef_gosterim_adi(_saglayici, oid) or ceviri.t("ai.pro.hedefOrgan")
        _ipucu = _saglayici.ipucu(_kedi, _ad)
        raise HTTPException(
            status_code=409,
            detail=ceviri.t("ai.pro.hata.konumlandirilmadi", ad=_ad, ipucu=_ipucu),
        )
    # ⚠️ Y143 (S-AII.4, sahip 2026-10-13): araştırma modelinde "otomatik" (0) hedef MÜHÜRE YAZILMAZ — o anki lokalizasyonun
    # SEÇTİĞİ hedefin kalıcı KİMLİĞİ yazılır (onay ekranında görülen = sürülen). Eskiden 0 mühürleniyordu: döngü / kare yolu
    # her karede yeniden "en yüksek öncelikli" hedefi seçiyor, öncelik değişince ya da onaylanan hedef kaybolunca ONAYLANMAYAN
    # komşu sürülüyordu (ölçüldü). Kimlik bu lokalizasyonla AYNI önbellek anlık görüntüsünden (x/y/z, etiket); mühür onaydan
    # SONRA güncellenmez (`/start` mühürden okur). Seçili kimlik okunamazsa öneri REDDEDİLİR. Kedi (0 = Tüm Vücut) DEĞİŞMEZ.
    # T3 · Y189: konum hangi kipte bulunduysa öneri o kipte olur — panelin kipi farklıysa (kip değiştirildi) 409, mühür karışmaz.
    _kosulsuz = bool(c.get("kosulsuz")) and not _kedi_modeli_mi(_saglayici)
    if _kosulsuz != (bool(payload.kosulsuz) and not _kedi_modeli_mi(_saglayici)):
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hata.kosulsuzUyusmuyor"))
    _muhur_hedefi = oid
    _otomatik_secim = False
    _kuyu = str(payload.kuyu or "").strip().upper()
    if _kuyu and _saglayici.ad == ai_pro_hedef.PetriSaglayici.ad:
        # AP-B3: tazelik yukarıda İSTEĞİN hedefiyle (önizlemenin lokalize ettiği) denetlendi; seçilen kuyu AYNI lokalizasyonun adayıdır.
        _aday = next(
            (
                t
                for t in (c.get("targets") or [])
                if isinstance(t, dict) and ai_pro_hedef._etiket_eki(_saglayici, t.get("label")).strip().upper() == _kuyu
            ),
            None,
        )
        if _aday is None or isinstance(_aday.get("id"), bool) or not isinstance(_aday.get("id"), int):
            raise HTTPException(
                status_code=409,
                detail=ai_pro_hedef.odak_engel_metni({"engel": "kuyuYok", "engel_ek": {"hedef": _kuyu}}),
            )
        c = {
            **c,
            "target_label": _aday.get("label") or "",
            "x_mm": float(_aday.get("x", c["x_mm"])),
            "y_mm": float(_aday.get("y", c["y_mm"])),
            "z_mm": float(_aday.get("z", c["z_mm"])),
            "e_cancer": None,
            "e_healthy": None,
        }
        _muhur_hedefi = int(_aday["id"])
    elif oid == 0 and not _kedi_modeli_mi(_saglayici):
        _secili = c.get("secili_id")
        if isinstance(_secili, bool) or not isinstance(_secili, int) or _secili <= 0:
            raise HTTPException(status_code=409, detail=otomatik_hedef_secilemedi_mesaji())
        if _secili not in _saglayici.hedef_idleri():
            _ek = {"mesaj": otomatik_hedef_secilemedi_mesaji(), "secili": _secili}
            raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hata.otomatikHedefGecersiz", **_ek))
        _muhur_hedefi, _otomatik_secim = _secili, True
    # Sağlayıcıyı bu isteğin thread'ine bağla → `_predict_and_drive` MÜHÜRLENEN modelin dozunu
    # üretir (imza değişmez: mevcut testlerin 4 argümanlı mock'ları çalışmaya devam eder).
    _ai_hedef_yerel.saglayici = _saglayici
    _odak = None
    try:
        if ai_pro_hedef.odak_destekli(_saglayici):
            # ODAK (istem 45): faz / duty istenen DOZLA ODAK modelinden; fizik denetimi engellerse SÜRME (eylem söyleyen 409).
            _frek = float(payload.frek_hz) if payload.frek_hz is not None else _AI_PRO_FREQ_HZ
            if not any(abs(_frek - f) < 1e-6 for f in AI_PRO_FREKANSLARI):
                _izinli = ", ".join(f"{f:g}" for f in AI_PRO_FREKANSLARI)
                _metin = ceviri.t("ai.pro.hata.frekansGecersiz", frek=f"{_frek:g}", izinli=_izinli)
                raise HTTPException(status_code=422, detail=_metin)
            _odak = ai_pro_hedef.odak_plani(_saglayici, c, _muhur_hedefi, payload.doz_mT, payload.odak_kip, _frek)
            if _odak.get("engel"):
                raise HTTPException(status_code=409, detail=ai_pro_hedef.odak_engel_metni(_odak))
            D, P, e_field = [float(d) for d in _odak["duty"]], [float(p) for p in _odak["faz"]], 0.0
        else:
            D, P, e_field = _predict_and_drive(c["x_mm"], c["y_mm"], c["z_mm"], oid)
    finally:
        _ai_hedef_yerel.saglayici = None
    if not any(float(d) > 0 for d in D):
        raise HTTPException(
            status_code=422,
            detail=ceviri.t("ai.pro.hata.dozUretmedi"),
        )
    from servers import ai_approval

    # Sunum-katmanı XAI (Faz 1.2, 2026-08-26): hekim onay ekranına "önerilen dozu en çok
    # ne belirledi" satırı — 7+1 ONNX forward'lık HAFİF duyarlılık (D-kanalları; eğitim-
    # dağılımı ref_std ile tek-örnek dejenerasyonu yok; SHAP/PNG YOK — kapalı-döngü kuralı).
    # ⚠️ Açıklama İKİNCİL: hatası ÖNERİYİ asla düşürmez (zarif düşüş).
    xai_meta = {}
    try:
        # ODAK önerisinde hoca modelinin duyarlılığı dozu AÇIKLAMAZ (sürüş kaynağı değil) → gösterilmez.
        _duyarlilik = None if _odak is not None else _saglayici.xai_sensitivity(c["x_mm"], c["y_mm"], c["z_mm"], oid)
        if _duyarlilik:
            xai_meta["xaiSensitivity"] = _duyarlilik
    except Exception as xe:
        # D5.05 (B-5.15): kök neden tam zincirle loglanır VE yanıtta söylenir — eskiden exc_info'suz uyarı + alan yok: hekim onay
        # ekranında "dozu ne belirledi" satırının NEDEN olmadığı bilinmiyordu (XAI sessizce kayıp).
        logger.warning("AI Pro öneri XAI üretilemedi (öneri etkilenmedi): %s", xe, exc_info=True)
        xai_meta["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")

    sure = max(1, min(_AI_PRO_MAX_DURATION_MIN, int(payload.duration_minutes)))
    _hasta_id = str(payload.patient_id or "").strip()[:64]
    _hasta_adi = str(payload.patient_name or "").strip()[:120]
    if (_hasta_id or _hasta_adi) and _uzaktan_kimliksiz_mi(request):
        # S-A1.1 (a): kimliksiz uzak öneri hastaya bağlanmaz (mühürde hasta YOK → `/start` seansı sahipsiz açar).
        logger.warning("AI Pro önerisi uzaktan KİMLİKSİZ geldi — hasta bağı kurulmadı (S-A1.1)")
        _hasta_id, _hasta_adi = "", ""
    rec = ai_approval.create(
        "ai_pro",
        {
            # Y143: otomatik (0) araştırma önerisinde SEÇİLİ hedefin kimliği (yukarıda); aksi hâlde istenen hedef.
            "organ_id": _muhur_hedefi,
            "duration_minutes": sure,
            # MÜHÜRLÜ MODEL (Faz 1): /start bunu okur, gövdedeki `model` yok sayılır.
            "model": _saglayici.ad,
            "target_label": (c.get("target_label") or _saglayici.hedef_adi(_muhur_hedefi)),
            # Onay ekranı (Faz 2): hedef sınıfının ve çevresinin E'si — onaylayan kişi seçiciliği görsün.
            "e_cancer": c.get("e_cancer"),
            "e_healthy": c.get("e_healthy"),
            "coil_ids": list(range(1, 8)),
            "D": [round(float(d), 4) for d in D],
            "P": [round(float(p), 2) for p in P],
            "e_field": round(float(e_field), 6),
            # D2.E15: hasta MÜHÜRDE (onay penceresi gösterir; `/start` buradan okur, gövdedeki hasta YOK SAYILIR).
            "patient_id": _hasta_id,
            "patient_name": _hasta_adi,
            # T3 · Y189: KOŞULSUZ öneri mühürde (onay penceresi söyler; `/start` seansı bu kipte açar). Koşulluda alan YOK (eski mühür).
            **({"kosulsuz": True} if _kosulsuz else {}),
            # ODAK (istem 45): seçilen doz + kip + fizik denetimi (onay penceresi: doz ± konum payı, tavan, çevre, oran, 24 kuyu haritası);
            # `/start` doz / kipi BURADAN okur (döngü aynı dozla yeniden hesaplar).
            **({"odak": _odak_ozet(_odak)} if _odak is not None else {}),
        },
        meta={
            "x_mm": c["x_mm"],
            "y_mm": c["y_mm"],
            "z_mm": c["z_mm"],
            "reliability": round(float(c.get("reliability") or 0.0), 3),
            "localized_at": c.get("at"),
            "subject_label": _saglayici.subject_label,
            "method": c.get("method") or "",
            "mm_per_px": c.get("mm_per_px"),
            # Konum modelin eğitim örnekleminin DIŞINDA mı? "Araştırma amaçlı model tahmini"
            # uyarısını besler; sürüşü ENGELLEMEZ.
            "ood": bool(c.get("ood")),
            "client_mode": str(payload.client_mode or "")[:32],
            # Y143: hedef otomatik seçimden mühürlendi (onay ekranı "seans boyunca yalnız bu hedef sürülür" der).
            **({"otomatik_secim": True} if _otomatik_secim else {}),
            "achieved_B": _saglayici.achieved_B,
            "duty_sum": _saglayici.duty_sum,
            **xai_meta,
        },
    )
    # Y142: öneri GÖRÜNÜR kalır ama onay ekranı sürüşün kapalı olduğunu SÖYLER (mühüre/denetim izine girmez — yanıt alanı).
    # Araştırma modeli buraya ancak kendi bayrağı açıkken gelir (`_arastirma_aipro_kapisi`).
    _surus_acik = not (_kedi_modeli_mi(_saglayici) and not _kedi_aipro_surus_acik())
    return {
        "status": "success",
        "proposalId": rec["id"],
        "specs": rec["specs"],
        "meta": rec["meta"],
        "expiresAt": rec["expires_at"],
        "surusAcik": _surus_acik,
        "surusKapaliNedeni": "" if _surus_acik else kedi_aipro_surus_kapali_mesaji(),
    }


class AiApprovalPayload(BaseModel):
    proposal_id: str = ""
    operator_email: str = ""
    reason: str = ""


@ai_router.post("/api/ai/pro/approve")
def approve_ai_pro(payload: AiApprovalPayload, request: Request):
    """Hekim önerilen parametreleri ONAYLAR. Denetim izi session_events'e yazılır.

    ⚠️ D2.41 (D-2.2 · İG-6.25): mühürdeki hekim İSTEMCİ BEYANINDAN değil sunucu kuralından (`cozumlenmis_operator`: jeton;
    kanıtsız kayıtlı-hekim beyanı → sahipsiz; operatörsüz klinikte beyan — Kural 2). Seansın sahibi `/start`ta bu
    mühürden okunur. Eskiden tünelden ANONİM bir istek kayıtlı bir hekimin adıyla mühür basıp tedaviyi başlatıyordu
    (ölçüldü). SAHİP KARARI D-2.2: `/api/ai/pro/*` tünelden kimliksiz erişilebilir — ERİŞİM SINIFI DEĞİŞMEZ (onay 200
    kalır, mühür '' olur, başlatma sürer). Kapı: tests/test_kayit_atfi_COZUMLENMIS_operator_D241.py."""
    from servers import ai_approval
    from servers.auth import cozumlenmis_operator

    # Y142: onay = "bu hasta için otonom tedaviyi başlatıyorum" beyanı (bkz. `propose_ai_pro`). Kedi sürüşü kapalıyken
    # başlatılamayacak tedavi için MÜHÜR basılmaz ve karar kaydına "onaylandı" yazılmaz; red ucu etkilenmez.
    _kayit = ai_approval.get(payload.proposal_id)
    if _kayit is not None:
        _kedi_aipro_surus_kapisi(str((_kayit.get("specs") or {}).get("model") or ""))
    try:
        rec = ai_approval.approve(payload.proposal_id, cozumlenmis_operator(request, payload.operator_email))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    _kaydet_onay_izi("ai_proposal_approved", rec)
    return {"status": "success", "proposalId": rec["id"]}


@ai_router.post("/api/ai/pro/reject")
def reject_ai_pro(payload: AiApprovalPayload, request: Request):
    """Hekim önerilen parametreleri REDDEDER (gerekçesiyle). Tedavi BAŞLAMAZ.
    ⚠️ D2.41 (İG-6.25): red mührü de onay gibi sunucu kuralından (bkz. `approve_ai_pro`)."""
    from servers import ai_approval
    from servers.auth import cozumlenmis_operator

    try:
        rec = ai_approval.reject(
            payload.proposal_id, cozumlenmis_operator(request, payload.operator_email), payload.reason
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    # S-F2-1.2 (2-F incelemesi · Y123 · C2-1.14): onay penceresi "Red gerekçesi (kayda geçer)" diyor — karar kaydı yazılamazsa ret yine
    # 200 (tedavi BAŞLAMAZ, akış durmaz) ama yanıt bunu SÖYLER; arayüz hekimi uyarır.
    # Kapı: tests/test_ai_pro_red_GEREKCE_KAYDEDILDI_mi_soyler_SF212.py
    kaydedildi = _kaydet_onay_izi("ai_proposal_rejected", rec)
    return {"status": "success", "proposalId": rec["id"], "gerekceKaydedildi": kaydedildi}


def _kaydet_onay_izi(olay: str, rec: dict) -> bool:
    """Onay/red kararını KALICI denetim izine yaz (append-only session_events).
    Best-effort: DB hatası klinik akışı DURDURMAZ, ama sessizce de yutulmaz (log'a düşer). Dönen: AI Pro karar kaydı (ret gerekçesi
    metni dahil) yazıldı mı — S-F2-1.2."""
    try:
        from servers.api_server import _get_treatment_db

        # D2.E15: hasta ADI öneri mühründe (onay penceresi gösterir) ama süresiz denetim izine GİRMEZ — iz yalnız opak
        # kimliği taşır (hangi hastaya onaylatıldığı yine izlenebilir).
        _specs = dict(rec.get("specs") or {})
        _specs.pop("patient_name", None)
        _yuk = {
            "proposal_id": rec.get("id"),
            "operator": rec.get("operator"),
            "specs": _specs,
            "meta": rec.get("meta"),
        }
        if olay == "ai_proposal_rejected":
            # O-A2.2 (2-B incelemesi): hekimin serbest red gerekçesi hasta/sahip adı, klinik bulgu taşıyabilir → iz METİNSİZ,
            # yalnız varlığı (D2.19'un AI değerlendirmesi kuralıyla aynı ilke).
            _yuk["gerekce_var"] = bool(str(rec.get("reason") or "").strip())
        _get_treatment_db().record_session_event(
            None,
            olay,
            payload=_yuk,
            severity="info",
        )
    except Exception:
        logger.warning("AI onay denetim izi yazılamadı (%s)", olay, exc_info=True)
    # ⚠️ Y119 (S-C.1): kararın kendisi ve ret gerekçesi METNİ şifreli DB'nin AI Pro karar tablosuna — iz metinsiz kalır (yukarıda).
    # Ayrı try: biri düşerse öteki yine yazılır; ikisi de kararı (ve tedaviyi) DURDURMAZ. Onay penceresi "Red gerekçesi (kayda
    # geçer)" diyor — C2-1.14. Kapı: tests/test_ai_pro_red_gerekcesi_KARAR_TABLOSUNDA_Y119.py
    try:
        from servers.api_server import _get_treatment_db

        _get_treatment_db().ai_pro_karari_yaz(
            rec.get("id"),
            "reddedildi" if olay == "ai_proposal_rejected" else "onaylandi",
            gerekce=str(rec.get("reason") or "") if olay == "ai_proposal_rejected" else "",
            operator_email=rec.get("operator") or "",
            patient_uuid=str((rec.get("specs") or {}).get("patient_id") or ""),
        )
    except Exception:
        logger.warning("AI Pro karar kaydı (gerekçe metni) yazılamadı (%s)", olay, exc_info=True)
        return False
    return True


@ai_router.post("/api/ai/pro/start")
def start_ai_pro(payload: AiProStartPayload = AiProStartPayload()):
    global _ai_loop_active, _ai_thread, _ai_organ_id, _ai_duration_min, _ai_started_at, _ai_relocalize, _ai_hedef_modeli
    global _ai_owner_client, _ai_dongu_no
    # ⚠️ D1.81 (B-5.3 · Y4): START NİYETİ isteğin VARIŞ anındaki nesli taşır (`api_server._SurusNiyetiVarisDamgasi`,
    # i1-F2); seans mührüne yazılır ve döngü / `/frame` bütün sürüşlerini bu nesille yapar. Başlatma sürerken gelen
    # durdurma/acil durdurma bu seansı doğmadan bayatlatır.
    _niyet_nesli = estop_mandali.niyet_nesli()
    _giris_engeli = estop_mandali.baslatma_engeli(_niyet_nesli)
    if _giris_engeli:
        raise HTTPException(status_code=409, detail=_giris_engeli)
    # Güncelleme uygulanıyorken otonom AI Pro tedavisi BAŞLATMA: installer servisi durdurup
    # EXE'yi değiştirebilir → bobinler kontrolcüsüz kalır (update TOCTOU guard'ının ters yönü).
    try:
        from servers import update_manager as _um

        if _um.is_update_in_progress():
            raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hata.guncellemeSuruyor"))
    except HTTPException:
        raise
    except Exception:
        pass
    # T2D-2: sunucu kamerası döngüsü kabin kamerası seçilmeden başlamaz — onay TÜKETİLMEDEN, eylem söyleyen 409.
    if kabin_kamerasi.secili_kamera() is None:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hazirlik.kameraSecilmedi"))
    # ── SERT KAPI (2026-08-06 sahip kararı): ONAYSIZ OTONOM TEDAVİ BAŞLAMAZ ────────────
    # Uygulanacak parametreler onaylananın MÜHÜRLÜ kopyasından okunur → "onayı al, başka parametreyle sür"
    # yapısal olarak imkânsız.
    # ⚠️ D1.E06 (İG-5.16): onay önce YALNIZ DOĞRULANIR, EN SON (bütün denetimlerden sonra) ve `_ai_loop_lock`
    # ALTINDA tüketilir. Eskiden ilk satırda tüketiliyordu → döngü sürerken gelen ikinci `/start` ("Already
    # running"), eşzamanlı ikinci istek, STM reddi (409), desteklenmeyen hedef (422) ve araştırma bayrağı (409)
    # BAŞLAMAYAN tedavi için hekimin tek kullanımlık onayını yakıyordu; STM reddinde globaller de (süre 2 → 7 dk)
    # başlamayan seansın değerinde kalıyordu (İG-5.9'un bayat globali).
    from servers import ai_approval

    try:
        _onay = ai_approval.dogrula(payload.proposal_id)
    except ValueError as e:
        raise HTTPException(status_code=428, detail=str(e)) from None
    _spec = _onay.get("specs") or {}

    # Audit P2: em_kedi yalnız organ 0-6'yı TEDAVİ eder; 7-10 (Kalp/Dalak/Akciğer) cat_organ ile
    # lokalize olur ama _build_input ValueError→D=P=0 (sessiz sıfır-tedavi) YİNE 'aktif+lokalize·Kalp'
    # gösterir → klinisyeni 'kalp tedavi ediliyor' diye yanıltır. Desteklenmeyeni reddet.
    # Organ ve süre ONAYLANAN mühürden okunur; istemcinin gövdede gönderdiği değer YOK SAYILIR
    # (aksi halde "organ 2'yi onaylat, organ 5'i başlat" mümkün olurdu — enerji YANLIŞ ORGANA).
    # MODEL de MÜHÜRDEN okunur (Faz 1, 2026-09-08): gövdedeki `model` YOK SAYILIR — "fantom
    # önerisini onaylat, kediyi başlat" (ya da tersi) yapısal olarak imkânsız. Mühürsüz eski
    # kayıtlar (Faz 1 öncesi onaylar) varsayılan "kedi" ile açılır → geriye-uyum korunur.
    # D1.E06: bu denetimlerin HİÇBİRİ global yazmaz; globaller yalnız onay tüketildikten sonra (kilit altında).
    try:
        _saglayici = ai_pro_hedef.saglayici_al(_spec.get("model"))
    except ValueError as _me:
        raise HTTPException(status_code=422, detail=str(_me)) from None
    # Bayrak MÜHÜRLÜ model için de denetlenir: bayrak açıkken alınmış bir onay, bayrak
    # kapatıldıktan sonra (ör. tezgâh sonucu olumsuz çıktı) SÜRÜLMEMELİ.
    _arastirma_aipro_kapisi(_saglayici)
    # KD · Y259: araştırma modeli geçerli sabit düzlem kalibrasyonu olmadan BAŞLAMAZ — onay TÜKETİLMEDEN (D1.E06).
    _duzlem_kalibrasyonu_kapisi(_saglayici)
    # Y142: kedi AI Pro sürüşü kapalıyken başlatma 409 — onay TÜKETİLMEDEN (D1.E06: başlamayan tedavi onayı yakmaz).
    _kedi_aipro_surus_kapisi(_saglayici)
    _organ_req = int(_spec.get("organ_id", payload.organ_id))
    if _organ_req not in _saglayici.hedef_idleri():
        _gecerli = ", ".join(str(i) for i in sorted(_saglayici.hedef_idleri()))
        _ek = {"oid": _organ_req, "model": ai_pro_hedef.model_adi(_saglayici), "gecerli": _gecerli}
        raise HTTPException(status_code=422, detail=ceviri.t("ai.pro.hata.hedefDesteklenmiyor", **_ek))
    # Süreyi klinik üst sınıra kapla (Audit P1) — aksi halde {duration_minutes: 999999} uzaktan
    # kabul ediliyordu. Bu değer hem STM/watchdog'a hem ESP MQTT yüküne gider.
    # Süre de MÜHÜRDEN okunur (organ ile aynı gerekçe: "20 dk onayla, 180 dk başlat" olmasın).
    _sure_dk = max(1, min(_AI_PRO_MAX_DURATION_MIN, int(_spec.get("duration_minutes", payload.duration_minutes))))
    # ⚠️ FIRMWARE UYUŞMAZLIĞI KAPISI (denetim 2026-09-12): kart komutları sistematik
    # reddediyorken otonom seans başlatmak, manuel yolda düzeltilen sahte-başarının aynısını
    # AI Pro'da yaşatırdı — üstelik burada operatör ekranın başında bile durmuyor olabilir.
    try:
        import servers.api_server as _api_red
        from servers import live_state as _ls_red

        if _ls_red.stm_komutlari_reddediyor():
            # Y74 / 1-G §8 #2: son red DUTY reddiyse eylem duty'dir (firmware uyuşmazlığı DEĞİL).
            raise HTTPException(
                status_code=409,
                detail=_ls_red.stm_red_duty_metni(ceviri.t("ai.pro.sonuc.baslatilmadi")) or _api_red.stm_red_mesaji(),
            )
    except HTTPException:
        raise
    except Exception:
        logger.debug("AI Pro STM red kontrolu yapilamadi (engellenmedi).", exc_info=True)
    # ⚠️ D1.77 (B-3.9 · İG-5.12, orkestratör notu): "kayıtsız tedavi başlamaz" — elle seansla AYNI kapı
    # (`_kayit_db_hazir`: DB açılamadı / disk kritik). Eskiden AI Pro "DB satırı açılamadı (tedavi sürer)" deyip
    # otonom sürüşe başlıyordu. Onay TÜKETİLMEDEN (aşağıdaki kilitli bölgeden önce) → düzelince aynı onayla başlar.
    import servers.api_server as _api_kayit

    _kayit_ok, _kayit_sebep = _api_kayit._kayit_db_hazir()
    if not _kayit_ok:
        raise HTTPException(status_code=503, detail=ceviri.t("ai.pro.hata.baslatilmadiNeden", sebep=_kayit_sebep))

    # ── ATOMİK: döngü denetimi + mandal/nesil + onay TÜKETİMİ + globaller, AYNI kilit altında ──
    # İki eşzamanlı start ikinci loop'u AÇMAZ ve kaybedenin onayı tüketilmez (D1.E06 (c)).
    with _ai_loop_lock:
        if _ai_loop_active:
            # [B1]: MEVCUT sahibi döndür (çağıranı DEĞİL) → çağıran ownedRef'i yanlışça true yapıp
            # panelini kapatınca başkasının seansına /stop göndermesin (ownedRef <3sn drift kapanır).
            # D1.E06 (b): onay TÜKETİLMEZ (başlamayan tedavi).
            return {"status": "success", "message": "Already running", "ownerClientId": _ai_owner_client}
        _engel = estop_mandali.baslatma_engeli(_niyet_nesli)
        if _engel:
            raise HTTPException(status_code=409, detail=_engel)
        try:
            _onay = ai_approval.consume(payload.proposal_id)
        except ValueError as e:
            raise HTTPException(status_code=428, detail=str(e)) from None
        _ai_loop_active = True
        _ai_dongu_no += 1
        _dongu_muhru = {
            "nesil": _niyet_nesli,
            "onay": str(payload.proposal_id),
            "dongu": _ai_dongu_no,
            "hedef": _organ_req,  # D1.60 (A-16): döngü yalnız ONAYLANAN hedefi sürer
        }
        # Sahiplik kilidin İÇİNDE yazılır: iki eş-zamanlı start'ta kazanan ile sahip AYNI olur.
        _ai_owner_client = str(payload.client_id or "")[:64]
        _ai_organ_id = _organ_req
        _ai_hedef_modeli = _saglayici.ad  # döngü ve /frame bu modeli kullanır (mühürle aynı)
        # T3 · Y189: kip MÜHÜRDEN (gövde yok sayılır)
        ai_pro_hedef.kosulsuz_ayarla(_saglayici, _spec.get("kosulsuz") is True)
        # ODAK (istem 45): doz / kip / hedef MÜHÜRDEN — döngünün `predict`i bunlarla yeniden hesaplar (mühürsüz → sürülmez).
        ai_pro_hedef.odak_ayarla(_saglayici, _spec.get("odak"), _spec.get("target_label") or "")
        global _ai_pro_frek_hz
        # ODK8: seansın sürüş frekansı MÜHÜRDEN (eski / ODAK'sız mühür → 100 Hz)
        _ai_pro_frek_hz = float(((_spec.get("odak") or {}).get("frek_hz")) or _AI_PRO_FREQ_HZ)
        _ai_duration_min = _sure_dk
        # DENETIM P2: DUVAR SAATI idi. AI Pro sure siniri gecen-sure farkiyla hesaplandigindan
        # NTP duzeltmesi/DST/elle saat degisimi GERI giderse maruziyet UZAR (donanim deadline'i
        # keep-alive ile her saniye tazelendigi icin onu da kesmez). Dort kullanimin hepsi delta
        # oldugundan monotonic'e gecildi (epoch olarak hicbir yerde gosterilmiyor).
        _ai_started_at = time.monotonic()
        _ai_relocalize = True  # başlangıçta hemen cat_organ lokalizasyonu yap
        # Kilit sırası _ai_loop_lock → _ai_cache_lock (hazırlık ucuyla aynı; ters sıra depoda YOK).
        with _ai_cache_lock:
            _ai_organ_cache["localized"] = False

    # Seansı baştan _active_session'a yaz → süre-watchdog + emergency-stop AI Pro'yu da kapsar.
    # 1-7: STM (D1.83: `STM_COIL_IDS` tek kaynak; bobin 8 KAPALI; em_kedi 7 bobinlik per-coil duty/phase üretir).
    from servers.api_server import KayitAcilamadi

    try:
        from servers.api_server import start_ai_session

        # ⚠️ SAHİP ONAY MÜHRÜNDEN OKUNUR, İSTEMCİ GÖVDESİNDEN DEĞİL: organ/süre/model ile
        # AYNI ilke. Seansın sahibi, otonom sürüşü ONAYLAYAN hekimdir — sorumluluğu üstlenen
        # kişi odur. İstemciden ayrı bir alan istemek, "başkasının adına seans açma"yı mümkün
        # kılardı. (Mühür `ai_approval.approve(pid, operator)` ile damgalanır.)
        # D1.80: seans TÜRÜ + tüketilen ONAY + niyet NESLİ + MODEL mühre yazılır — `/frame` yalnız bunlarla sürer
        # (`mode` metni artık yetki vermez).
        start_ai_session(
            0.0,
            0.0,
            _sure_dk,
            range(1, 8),
            f"AI Pro · {_saglayici.title}",
            operator_email=str(_onay.get("operator") or ""),
            tur="ai_pro",
            onay_kimligi=str(payload.proposal_id),
            surus_nesli=_niyet_nesli,
            model=_saglayici.ad,
            onay_hedefi=_organ_req,
            # ⚠️ D2.E15 (İG-5.14): hasta ONAY MÜHRÜNDEN — eskiden `/start` gövdesinin `patient_name`i pydantic tarafından
            # atılıyordu (alan yok) → AI Pro satırı ad/kimlik NULL, hastanın geçmişinde tedavi YOKTU (ölçüldü).
            hasta={
                "id": str((_onay.get("specs") or {}).get("patient_id") or ""),
                "name": str((_onay.get("specs") or {}).get("patient_name") or ""),
            },
        )
    except KayitAcilamadi as _kayitsiz:
        # ⚠️ Y65 (sahip, 1-F inceleme S-İF1): tedavi kaydının DB satırı açılamadı → otonom sürüş BAŞLAMAZ (döngü açılmaz,
        # bobin sürülmedi). Başlamayan tedavi hekimin onayını YAKMAZ (D1.E06): DB düzelince aynı onayla başlanır.
        _dongu_bayragini_indir(_dongu_muhru)
        ai_approval.geri_ver(payload.proposal_id)
        raise HTTPException(status_code=503, detail=str(_kayitsiz)) from None
    except Exception:
        logger.exception("start_ai_session failed")
    # D1.81: başlatma sürerken durdurma / acil durdurma geldiyse döngü BAŞLATILMAZ (seans doğmadan bayat). Onay
    # tüketildi: durdurmadan sonra eski onayla yeniden başlatılamaması güvenli yöndür (yeni öneri gerekir).
    _engel = estop_mandali.baslatma_engeli(_niyet_nesli)
    if _engel:
        _dongu_bayragini_indir(_dongu_muhru)
        try:
            import servers.api_server as _api_geri

            with _api_geri._session_lock:
                if _api_geri._active_session.get("onay_kimligi") == _dongu_muhru["onay"]:
                    _api_geri._active_session["is_active"] = False
        except Exception:
            logger.exception("AI Pro: başlatma iptalinde seans pasife alınamadı")
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hata.baslatmaSirasindaDurduruldu"))
    import threading

    # WEB kapalı-döngü (2026-08-25): hazırlık önizlemesi kamerayı tutuyor olabilir → seans loop'u
    # VideoCapture(0)'ı açmadan ÖNCE önizlemeyi durdur ve kameranın bırakılmasını BEKLE (join).
    _ai_hazirlik_durdur_ic()
    _ai_thread = threading.Thread(target=_ai_pro_loop, args=(_dongu_muhru,), daemon=True, name="ai-pro-dongu")
    _ai_thread.start()
    return {
        "status": "success",
        "message": "AI Pro Closed-Loop Started",
        "organId": _ai_organ_id,
        "durationMin": _ai_duration_min,
        # [B1]: sahiplik kimliği → panel ownedRef'i YALNIZ ownerClientId===benimId ise true yapar.
        "ownerClientId": _ai_owner_client,
    }


@ai_router.post("/api/ai/pro/stop")
async def stop_ai_pro_ucu():
    """AI Pro durdurma UCU. ⚠️ O-1.1 (Ö.4-Y8): gövde (`stop_ai_pro`) KENDİ iş parçacığında — eşzamanlı (`def`) uç olarak
    anyio'nun ORTAK iş parçacığı sınırlayıcısında (40) sıra beklemez (bağımlılığı `jeton_gate` de havuza girmeden karar
    verir). Ölçüldü (1-G önce-kırmızı): iki ortak havuz asılı işlerle doluyken STOP 30/30 porta GİTMİYORDU."""
    import servers.api_server as _api

    return await _api._durdurma_is_parcaciginda(stop_ai_pro, ad="ai-pro-stop")


def stop_ai_pro():
    global _ai_loop_active, _ai_owner_client, _ai_hedef_modeli
    import servers.api_server as _api

    # ⚠️ D2.E07: durdurma NİYETİ döngü bayrağından ÖNCE oturuma işlenir ve kapatılacak seansın anlık görüntüsü alınır —
    # döngünün teardown'ı bayrak iner inmez koşabilir; işaret olmasa operatör durdurmasını kendi kesintisi ("Kesintiye
    # Uğradı") sayardı. Bobin STOP'u bundan ETKİLENMEZ (aşağıda, sırası değişmeden).
    _kapanacak = None
    try:
        with _api._session_lock:
            if _ai_seansi_mi(_api._active_session) and _api._active_session.get("is_active"):
                _api._active_session["ai_pro_durduruluyor"] = True
                _kapanacak = dict(_api._active_session)
    except Exception:
        logger.exception("stop_ai_pro: durdurma niyeti işlenemedi (STOP etkilenmez)")
    with _ai_loop_lock:
        _ai_loop_active = False
        # Aktif modeli VARSAYILANA döndür (Faz 1): aksi halde fantom seansından sonra `model`
        # göndermeyen bir istemcinin (eski APK, mobil kare yolu) kareleri hâlâ fantom
        # sağlayıcısına gider ve "hedef yok" döngüsüne girerdi.
        _ai_hedef_modeli = ai_pro_hedef.VARSAYILAN_MODEL
        for _s in ai_pro_hedef.SAGLAYICILAR.values():  # T3 · Y189: koşulsuz kip seansla biter
            ai_pro_hedef.kosulsuz_ayarla(_s, False)
            ai_pro_hedef.odak_ayarla(_s, None)  # ODAK (istem 45): mühürlü doz / kip seansla biter
            globals()["_ai_pro_frek_hz"] = _AI_PRO_FREQ_HZ  # ODK8: sürüş frekansı varsayılana
        # [B1] Sahiplik kilidin İÇİNDE temizlenir: stop'tan sonra başka bir modern istemci AI
        # Pro'yu devralabilsin (stale owner kimseyi kilitlemesin).
        _ai_owner_client = ""

    # Bobinleri TÜM transport'larda durdur: STM 1-5 + ESP 6-8 (Audit P1 #3). Eskiden yalnız
    # stop_all_coils (STM) çağrılıyordu; kamerasız/mobil yolda loop-cleanup çalışmadığı için
    # ESP 6-7 STOP almadan enerjili kalıyordu. _stop_session_coils ikisini de durdurur + coil-run kapatır.
    # DENETIM P1: kapsam range(1,8) idi = bobin 8 ATLANIYORDU. "AI (Auto)" landmark yolu
    # (_drive_landmark_auto) 8 BOBINLI seans acar (start_ai_session(..., range(1,9)) + ESP 6,7,8'e
    # duration=1800 publish) ve /ai/pro/start'i HIC cagirmaz → _ai_pro_loop teardown'u da yok.
    # Boylece acik STOP komutundan sonra bobin 8, ESP'de 30 dk enerjili kaliyordu; onu durduracak
    # baska yazilim katmani da yok (sure-watchdog ve /session/stop 'aktif seans yok' diye erken doner).
    # Calismayan bobine STOP gondermek zararsiz/idempotenttir → kapsami TUM 8 bobine cikar.
    # (D1.88: AI (Auto) landmark surus yolu KALDIRILDI; tum bobinlere STOP yine dogru — idempotent.)
    try:
        # Denetim 2. tur [1.1]: teyitsiz STOP'lar operatore bildirilir — broker oluyken
        # bu uc "success" donerken bobinlerin durmadigi sessiz kaliyordu.
        # D1.81 (İG-5.3 "/ai/pro/stop kolu"): yetki KESİLİR (nesil++) → tahmindeki uçuştaki `/frame`/döngü turu bu
        # STOP'tan sonra bobini yeniden enerjileyemez (ölçüldü: 20'de 2, zorlanmış zamanlamada 30'da 30).
        _api._bildir_teyitsiz_stop(
            _api._stop_session_coils(range(1, 9), yetkiyi_kes=True),
            lambda d: ceviri.t("bildirim.kaynak.aiProDurdurma", dil=d),
        )
    except Exception:
        logger.exception("stop_ai_pro: _stop_session_coils hatası")
    # ⚠️ O-1.1 kapsamı (1-G): önizleme durdurma ve canlı E bağlamı STOP'tan SONRA. Eskiden STOP'tan ÖNCEydi: önizleme o an
    # lokalizasyondaysa `_ai_hazirlik_durdur_ic` kamerayı bırakmasını `join(timeout=6)` ile BEKLİYOR, STOP 6 sn'ye dek
    # gecikiyordu (ölçüldü 30/30; mobil `/frame` seansı `_ai_loop_active` kurmaz → önizleme açık kalabilir). İkisi de bobin
    # sürmez; sıra yalnız STOP'u öne alır.
    # Mobil (/frame) seansında loop teardown'ı YOKTUR → canlı E bağlamını burada da temizle.
    try:
        from servers import efield_live as _ef3

        _ef3.set_context([])
    except Exception:
        logger.debug("AI Pro stop: canlı E bağlamı temizlenemedi", exc_info=True)
    # WEB kapalı-döngü: hazırlık önizlemesi çalışıyorsa onu da durdur (kamera bırakılsın).
    _ai_hazirlik_durdur_ic()
    # AI seansını da kapat → süre-watchdog ve frame-geçidi 'seans aktif değil' görsün.
    try:
        with _api._session_lock:
            if _ai_seansi_mi(_api._active_session):
                _api._active_session["is_active"] = False
    except Exception:
        logger.exception("stop_ai_pro: _active_session reset hatası")
    _api.update_live_session_state(is_active=False, mode="Sistem Hazır")
    # ⚠️ D2.E07 (YA-1): AI Pro satırı GERÇEK süreyle KAPATILIR — STOP'TAN SONRA (Ö.4-Y8: bobin STOP'u yukarıda gitti; kayıt
    # yazımı onu geciktiremez). Eskiden kapatılmıyordu: satır `active` kalıyor, yeniden açılışta kurtarma onu "Elektrik
    # Kesintisi, 0 dk" mühürlüyordu (ölçüldü). Operatör durdurması = "completed" (elle seansın durdurulmasıyla aynı).
    # Yalnız durdurma anında AKTİF olan KENDİ seansı ve yalnız satırı hâlâ AÇIKSA (acil durdurmanın "EMERGENCY_STOPPED"
    # mührü ezilmez).
    # ⚠️ C2-1.3 (2-C inceleme · Ö.4-Y8): kapanış KAYIT kuyruğunda (sıra korunur — ACİL DURDUR kapanışıyla aynı işçi: "durum
    # hâlâ active mi?" denetimi ile finalize arasına öteki kapanış giremez); yanıt en çok `DURDURMA_KAYIT_BEKLEME_SN` bekler.
    # Tedavi DB'si kilitliyken yanıt 21 sn bekliyordu (arayüz zaman aşımı 8 sn → bobinler durmuşken "Durdurulamadı").
    from utils import dongu_disi_yazim as _kayit_kuyrugu

    _kayit_kuyrugu.sirada_calistir(
        _ai_pro_satirini_kapat, _kapanacak, "ai-pro-durdurma", ad="AI Pro durdurma seans kaydi kapanisi"
    )
    return {"status": "success", "message": "AI Pro Closed-Loop Stopped"}


def _ai_pro_satirini_kapat(seans: dict | None, sebep: str) -> None:
    """D2.E07 (YA-1): AI Pro seansının DB satırını `_finalize_session_db` ile kapat (kısmi dakika + sensör + bitiş damgası).
    `seans` = kapatılmadan HEMEN önce alınmış oturum anlık görüntüsü (yalnız o an aktif olan KENDİ seansı); yoksa ya da
    satır zaten kapatıldıysa (`db_finalized`) hiçbir şey yapılmaz. STOP'u asla beklemez: yalnız STOP gönderildikten sonra
    çağrılır. `sebep` durumu belirler (`api_server._finalize_session_db`)."""
    if not seans or not seans.get("db_session_id") or seans.get("db_finalized"):
        return
    try:
        import servers.api_server as _api_k

        _db = _api_k._get_treatment_db()
        _durum = (_db.get_session_details(int(seans["db_session_id"])) or {}).get("session_status") if _db else None
        if _durum != "active":
            # Başka bir yol (acil durdurma, süre-watchdog, devralma, durdurma) satırı zaten kapattı — mührü EZİLMEZ.
            return
        _api_k._finalize_session_db(
            seans.get("db_session_id"),
            seans.get("started_epoch") or seans.get("start_time"),
            reason=sebep,
            start_mono=seans.get("start_mono"),
        )
    except Exception:
        logger.exception("AI Pro seans satırı kapatılamadı (%s)", sebep)


@ai_router.post("/api/ai/pro/organ")
def set_ai_pro_organ(payload: AiProStartPayload = AiProStartPayload()):
    """Hedef organı değiştir (loop çalışırken de geçerli) + hemen yeniden-lokalize et."""
    global _ai_organ_id, _ai_relocalize
    # 3. tur denetimi [B1]: mid-seans organ değişimi ONAYLANMAMIŞ organa enerji verebilir; YABANCI
    # (sahip dışı) istemci onaylı seansın organını değiştiremez (deny-only, yeni yetki vermez).
    if _ai_kare_yabanci(payload.client_id):
        raise HTTPException(status_code=403, detail=ceviri.t("ai.pro.hata.sahipDegilOrgan"))
    _organ_req = int(payload.organ_id)
    # Hedef kümesi AKTİF sağlayıcıdan (Faz 1) — kedi için 0-6 (Audit P2: em_kedi yalnız 0-6
    # TEDAVİ eder; 7-10 lokalize olur ama _build_input ValueError → sessiz sıfır-tedavi).
    _saglayici = _aktif_saglayici()
    _bekleyen = False  # AP-B5: boşta İSTENEN modelin seçimi — etkin model ve küresel hedef DEĞİŞMEZ
    if payload.model and payload.model.strip().lower() != _saglayici.ad:
        # AP-B5 · B2 (istem 48, tezgâh 13-11): `/ai/pro/stop` etkin modeli KEDİ'ye döndürür; seans bitince panel petride kalır ve kuyu
        # seçimi kedi kümesiyle 422 alıyordu ("Hedef 11 'Kedi Organ' için desteklenmiyor") — panel seçimi geri alıp hazırlığı OTOMATİK
        # hedefle başlatıyordu (C6 → C2). BOŞTA (döngü / hazırlık / mühürlü seans yok) seçim İSTENEN modelin kümesiyle doğrulanır; etkin
        # model ve `_ai_organ_id` DEĞİŞMEZ (başka istemcinin kareleri etkilenmez) — hazırlık seçimi kendi gövdesindeki model + hedefle kurar.
        if _ai_loop_active or _ai_hazirlik_active or _ai_pro_surus_muhru() is not None:
            raise HTTPException(
                status_code=422,
                detail=ceviri.t("ai.pro.hata.aktifModel", ad=_saglayici.ad, model=payload.model),
            )
        try:
            _saglayici = ai_pro_hedef.saglayici_al(payload.model)
        except ValueError as _me:
            raise HTTPException(status_code=422, detail=str(_me)) from None
        _bekleyen = True
    if _organ_req not in _saglayici.hedef_idleri():
        _gecerli = ", ".join(str(i) for i in sorted(_saglayici.hedef_idleri()))
        _ek = {"oid": _organ_req, "model": ai_pro_hedef.model_adi(_saglayici), "gecerli": _gecerli}
        raise HTTPException(status_code=422, detail=ceviri.t("ai.pro.hata.hedefDesteklenmiyor", **_ek))
    # ⚠️ D1.60 (B-5.5 · İG-6.10) — SAHİP KARARI A-16: seans sürerken MÜHÜRDE OLMAYAN hedefe geçiş YENİ ONAY ister.
    # Onay mührü bir hedefe verilir; mühür dışı hedefe sürüş onaysız tedavidir. Ölçüldü (İG-6.10): sahip istemcinin
    # `/organ {2}`'si onaylı organ-0 seansında 200 dönüyor, teldeki duty/faz yeni organın desenine geçiyordu.
    # Küresel hedef DEĞİŞMEZ; sürüş de ayrıca yalnız mühürdeki hedefi sürer (2. katman: `/frame`, döngü).
    _muhur = _ai_pro_surus_muhru()
    if _muhur is not None and _organ_req != _muhur.get("hedef"):
        _onayli = _muhur.get("hedef")
        _onayli_ad = _saglayici.hedef_adi(_onayli) if isinstance(_onayli, int) else "bilinmiyor"
        logger.warning(
            "AI Pro: seans sürerken mühür dışı hedefe geçiş REDDEDİLDİ (onaylı %s, istenen %s) — A-16",
            _onayli,
            _organ_req,
        )
        raise HTTPException(
            status_code=409,
            detail=(ceviri.t("ai.pro.hata.onaysizHedef", ad=_onayli_ad)),
        )
    if not _bekleyen:
        _ai_organ_id = _organ_req
        _ai_relocalize = True  # yeni hedef için lokalizasyonu hemen yeniden çalıştır
    return {
        "status": "success",
        "organId": _organ_req,
        "organName": ai_pro_hedef.hedef_gosterim_adi(_saglayici, _organ_req),
        "model": _saglayici.ad,
    }


@ai_router.post("/api/ai/pro/calibrate")
def calibrate_ai_pro(payload: AiProStartPayload = AiProStartPayload()):
    """Yeniden konumla: bir sonraki karede cat_organ organ-lokalizasyonunu zorla tazele.
    (Eski avuç-tabanlı Z kalibrasyonu KALDIRILDI — el takibi söküldü.)"""
    global _ai_relocalize
    # [B1]: YABANCI istemci sahibin lokalizasyonunu zorla tazeleyemez (deny-only).
    if _ai_kare_yabanci(payload.client_id):
        raise HTTPException(status_code=403, detail=ceviri.t("ai.pro.hata.sahipDegil"))
    _ai_relocalize = True
    return {"status": "success", "relocalize": True}


# ══ KD · KABİN KALİBRASYONU UÇLARI (Y260: araştırma profili, masaüstü + telefon + web) ══════════════════════════════════════════
# Yetki /api/ai/pro/* ile AYNI (sahibin AI Pro muafiyeti, `auth._EXEMPT_PREFIXES`) + araştırma eklentisi (`require_research`).
# Akış: kare al (kabin kamerası, sunucuda saklanır) → 4 köşeye dokun + sol / ön cm + lens → hesapla → kaydet (lens > 2 cm farkta AÇIK onay)
# → doğrula (plaka başka yerde, 2 köşe) → fantom ayarı. Kayıt / doğrulama / fantom ayarı DENETİM İZİNE (append-only session_events).
# ⚠️ Seans sürerken kalibrasyon DEĞİŞTİRİLMEZ (hedefler kayar) → 409. ACİL DURDUR bu uçlara bağlı DEĞİL (Ö.4-Y8).
from servers import kabin_kalibrasyonu as _kk_uclari  # noqa: E402

ai_router.include_router(_kk_uclari.router)


@ai_router.post("/api/ai/pro/hazirlik/baslat")
def ai_pro_hazirlik_baslat(payload: AiProStartPayload = AiProStartPayload()):
    """WEB/sunucu-kameralı HAZIRLIK önizlemesini başlat: kamera açılır + seçili organ lokalize edilir
    (BOBİN SÜRÜLMEZ, SEANS BAŞLAMAZ). Panel /status'tan `localized` görünce öneriyi otomatik ister.
    Telefonun hazırlık akışının sunucu-kamera karşılığı — web'in propose-önce-lokalizasyon kapalı
    döngüsünü kırar (2026-08-25). Aktif seans varsa gereksiz (kamera zaten seansta) → sessiz başarı."""
    global \
        _ai_hazirlik_active, \
        _ai_hazirlik_thread, \
        _ai_hazirlik_started_at, \
        _ai_organ_id, \
        _ai_relocalize, \
        _ai_hedef_modeli, \
        _ai_hazirlik_hata_kodu
    global _ai_hazirlik_hata, _ai_hazirlik_hata_saglayici
    import threading

    _organ_req = int(payload.organ_id)
    try:
        _saglayici = ai_pro_hedef.saglayici_al(payload.model)
    except ValueError as _me:
        raise HTTPException(status_code=422, detail=str(_me)) from None

    # ⚠️ SAHİPLİK KAPISI (2026-09-08) — `/api/ai/pro/organ`daki B1 kapısının paritesi. Bu uç sahip
    # kararıyla auth-muaf olduğundan, aktif seansın sahibi OLMAYAN bir istemci buradan hedefe
    # dokunabiliyordu (organ ucunda 403 vardı, burada yoktu). Deny-only: sahip bilinmiyorsa ya da
    # seans aktif değilse bastırma YOK (geriye-uyum korunur).
    if _ai_kare_yabanci(payload.client_id):
        raise HTTPException(
            status_code=403,
            detail=ceviri.t("ai.pro.hata.sahipDegilHedef"),
        )
    # T2D-2: kabin kamerası seçilmediyse önizleme hiç başlamaz — eylem söyleyen 409 (panel 120 sn boş önizleme beklemesin).
    if kabin_kamerasi.secili_kamera() is None:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hazirlik.kameraSecilmedi"))

    # ⚠️ MUTASYON KİLİT İÇİNDE + AKTİFLİK KONTROLÜNDEN SONRA (2026-09-08 düzeltmesi):
    # organ/relocalize/cache yazımları eskiden BU BLOKTAN ÖNCE, kilit dışında yapılıyor; sonra
    # kilide girilip "Seans zaten aktif" ile SESSİZ BAŞARI dönülüyordu — yani mutasyon KALICI
    # oluyordu. Onaylı bir seans sürerken herhangi bir istemci {"organ_id": 5} gönderip
    # `need_localize` koşulunu tetikleyebiliyor, bobinler MÜHÜRDE ONAYLANMAYAN organa sürülüyordu
    # (2026-08-06 "organ/süre gövdeden değil mühürden okunur" kararının yan kapısı).
    # ⚠️ 200 yerine 409: sessiz başarı panelde de zararlıydı — `AiProPanel` yanıtı truthy görüp
    # `setHazirlik(true)` yapıyor ve hiç gelmeyecek önizlemeyi 120 sn bekliyordu (B3 dersi).
    # Kapı: tests/test_ai_pro_hazirlik_mutasyon_kilidi.py (mutasyonu kilit öncesine taşı → KIRMIZI).
    # ⚠️ ATOMİK (adversaryal inceleme MAJOR-2 TOCTOU): _ai_loop_active + _ai_hazirlik_active kontrolü
    # VE thread spawn'ı AYNI _ai_loop_lock içinde. Eskiden _ai_loop_active kilit DIŞINDA okunuyordu →
    # eş-zamanlı /ai/pro/start ile çift VideoCapture(0) açılabiliyordu (kilit tam bunu önlemek içindi).
    # ⚠️ D1.80 (B-5.10): sunucu kamerası döngüsü çalışmasa da (mobil `/frame` seansı) MÜHÜRLÜ bir AI Pro seansı
    # sürerken model/hedef DEĞİŞTİRİLEMEZ — bayrak yalnız döngüye bakıyordu. (Mühür, kilit sırası tersine dönmesin
    # diye kilitten ÖNCE okunur; hazırlık bobin sürmez, aradaki pencere zararsız.)
    _muhurlu_seans = _ai_pro_surus_muhru() is not None
    with _ai_loop_lock:
        if _ai_loop_active or _muhurlu_seans:
            raise HTTPException(
                status_code=409,
                detail=ceviri.t("ai.pro.hata.seansSurerkenHedef"),
            )
        # Buradan sonrası: SEANS YOK → bobin sürülmüyor, hedef mutasyonu güvenli. Hazırlık zaten
        # çalışıyorsa da organ güncellenir: panelin "Yeniden Konumla" akışı (AiProPanel.tsx:575)
        # önizleme sürerken bu ucu yeni organla çağırır.
        _ai_hazirlik_hata = ""  # B3: her yeni hazırlık taze; eski hata metni bayat kalmasın
        _ai_hazirlik_hata_kodu = ""
        _ai_hazirlik_hata_saglayici = None
        # Model seçimi (Faz 1): seans YOK → güvenli. Hazırlık sürerken model değişirse önizleme
        # yeni sağlayıcıyla devam eder (thread her turda `_aktif_saglayici()` okur).
        _ai_hedef_modeli = _saglayici.ad
        ai_pro_hedef.kosulsuz_ayarla(_saglayici, payload.kosulsuz is True)  # T3 · Y189 (kedide yok sayılır)
        if _organ_req in _saglayici.hedef_idleri():
            _ai_organ_id = _organ_req  # panelde seçili hedef için lokalize et
        elif _organ_req != _saglayici.varsayilan_hedef:
            # Hedef bu modele ait değil (ör. kedi organ 5 → fantom): varsayılana çek, 422 döngüsü
            # yaratma (panel modeli yeni seçmiş olabilir).
            _ai_organ_id = _saglayici.varsayilan_hedef
        _ai_relocalize = True  # yeni hazırlıkta taze lokalizasyon zorla
        # MINOR (adversaryal inceleme): bayat `localized`=True bir önceki önizlemeden kalmış olabilir →
        # önizleme TAZE lokalize etmeden panel bayat ölçümden öneri istemesin. Cache'i geçersiz kıl;
        # /status 'localized' önizleme yeni kare üretene kadar False döner (start_ai_pro:1434 paritesi).
        # Kilit sırası _ai_loop_lock → _ai_cache_lock (ters sıra depoda YOK → deadlock riski yok).
        with _ai_cache_lock:
            _ai_organ_cache["localized"] = False
        if _ai_hazirlik_active:
            return {"status": "success", "message": ceviri.t("ai.pro.mesaj.hazirlikCalisiyor")}
        _ai_hazirlik_active = True
        _ai_hazirlik_started_at = time.monotonic()
        _ai_hazirlik_thread = threading.Thread(target=_ai_hazirlik_loop, daemon=True)
        _ai_hazirlik_thread.start()
    return {"status": "success", "message": ceviri.t("ai.pro.mesaj.hazirlikBasladi")}


@ai_router.post("/api/ai/pro/hazirlik/durdur")
def ai_pro_hazirlik_durdur():
    """Önizlemeyi durdur (kamera bırakılır). Panel Vazgeç / süre-tavanı / seans başlangıcında çağırır.
    Gövdesiz + açık: önizleme bir tedavi DEĞİL (bobin sürmez), durdurmak herkese açık kalabilir."""
    _ai_hazirlik_durdur_ic()
    # T3 · Y189: seans yokken koşulsuz kip önizlemeyle biter (seans sürüyorsa kip MÜHÜRDENDİR — dokunulmaz).
    if not _ai_loop_active and _ai_pro_surus_muhru() is None:
        for _s in ai_pro_hedef.SAGLAYICILAR.values():
            ai_pro_hedef.kosulsuz_ayarla(_s, False)
            ai_pro_hedef.odak_ayarla(_s, None)  # ODAK (istem 45): mühürlü doz / kip seansla biter
            globals()["_ai_pro_frek_hz"] = _AI_PRO_FREQ_HZ  # ODK8: sürüş frekansı varsayılana
    return {"status": "success"}


@ai_router.get("/api/ai/pro/status")
def ai_pro_status():
    remaining = 0
    if _ai_loop_active and _ai_started_at:
        remaining = max(0, int(_ai_duration_min * 60 - (time.monotonic() - _ai_started_at)))
    return {
        "active": _ai_loop_active,
        "organId": _ai_organ_id,
        "organName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _ai_organ_id),
        "durationMin": _ai_duration_min,
        "remainingSec": remaining,
        "localized": bool(_ai_organ_cache.get("localized")),
        "catDetected": bool(_ai_organ_cache.get("kedi_var")),
        # YALNIZ-EK alanlar (Faz 1, 2026-09-08): mevcut anahtarlar (organId/organName/
        # catDetected/guvenDokumu/ownerClientId/hazirlik*) AYNEN kalır → eski istemciler kırılmaz.
        "model": _aktif_saglayici().ad,
        "modelName": _aktif_saglayici().title,
        # T3 · Y189 yalnız-ek: etkin sağlayıcı KOŞULSUZ kipte mi (panel rozeti).
        "kosulsuz": bool(getattr(_aktif_saglayici(), "kosulsuz", False)),
        # Faz 2 yalnız-ek: kare üstünde hedef seçimi (targets), kalibrasyon rozeti (method/mmPerPx)
        # ve onay ekranı uyarıları (ood) BU alanlardan beslenir. Kedi hattında boş/varsayılan.
        "targets": _ai_organ_cache.get("targets") or [],
        # YALNIZ-EK (AP-B5): hedef adaylarının ait olduğu model = SON LOKALİZASYONUN modeli. `model` ETKİN sağlayıcıdır (durdurma kediye
        # döndürür) — panel başka modelin bayat adaylarını göstermesin, kendi modelininkini (seans bitse de) seçtirebilsin.
        "targetsModel": str(_ai_organ_cache.get("model") or ""),
        "method": _ai_organ_cache.get("method") or "",
        # YALNIZ-EK (KD-3a · B-KD3a.1): kapının FİZİKSEL eylem metni (kesmediyse ""). Panel rozeti / şeridi ArUco metni yerine bunu yazar.
        "kapiEylem": _ai_organ_cache.get("kapi_eylem") or "",
        "mmPerPx": _ai_organ_cache.get("mm_per_px"),
        "targetLabel": _ai_organ_cache.get("target_label") or "",
        "ood": bool(_ai_organ_cache.get("ood")),
        "subjectLabel": _aktif_saglayici().subject_label,
        "subjectDetected": bool(_ai_organ_cache.get("kedi_var")),
        "targetName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _ai_organ_id),
        "reliability": round(float(_ai_organ_cache.get("reliability", 0.0)), 3),
        # Sunum-katmanı XAI (2026-08-26): güvenin bileşen dökümü (poz × derinlik × maske ×
        # belirsizlik + kalibrasyon tavanı) — panel "Güven %X"in NEDENİNİ gösterebilsin.
        "guvenDokumu": _ai_organ_cache.get("guven_dokumu"),
        # ⚠️ Alanın VARLIĞI istemci için anlamlı: yoksa (eski backend) panel ESKİ davranışı sürdürür.
        "ownerClientId": _ai_owner_client,
        # B3 (siyah ekran): web önizlemesi canlı mı + neden öldü (kamera/model). Panel `hazirlikHata`
        # doluysa hazırlığı sonlandırıp NEDENİ gösterir (120 sn kör bekleyiş yerine).
        "hazirlikActive": bool(_ai_hazirlik_active),
        # YALNIZ-EK (AP-B1): sürmekte olan önizlemenin geçen süresi (sn) — yeniden açılan panel hazırlık saatini oradan sürdürür.
        "hazirlikGecenSn": (
            int(max(0.0, time.monotonic() - _ai_hazirlik_started_at))
            if _ai_hazirlik_active and _ai_hazirlik_started_at
            else 0
        ),
        "hazirlikHata": _hazirlik_hata_goster(),
        "hazirlikHataKodu": _ai_hazirlik_hata_kodu,  # YALNIZ-EK (2026-09-09)
        # YALNIZ-EK (2026-09-09): araştırma modelleriyle sürüş açık mı? Panel model kartlarını
        # buna göre "Deneysel — tezgâh doğrulaması bekleniyor" diye pasifleştirir.
        "arastirmaAiProAcik": _arastirma_aipro_acik(),
        # YALNIZ-EK (T-f, Y195): FANTOM AI Pro sürüşü açık mı (ayrı bayrak). Panel fantom kartını "AI Pro sürüşü KAPALI" diye işaretler
        # (alan yoksa — eski backend — `arastirmaAiProAcik`e düşer).
        "arastirmaAiProFantomAcik": _arastirma_aipro_fantom_acik(),
        # YALNIZ-EK (Y142): kedi AI Pro kapalı döngü sürüşü açık mı. Panel kapalıyken başlatma düğmesini ve onay ekranını
        # gerçeğe göre etiketler (alan yoksa — eski backend — eski davranış).
        "kediAiProSurusAcik": _kedi_aipro_surus_acik(),
    }


def _frame_hedef_durumu(muhur, bulundu: bool) -> int:
    """İG-5.1: `/frame` hedef durumunu kare kare sayar; ARDIŞIK kayıp sayısını döndürür (bulunduysa 0). Çağıran
    `>= _AI_LOST_STOP_STREAK` iken STOP gönderir.

    ⚠️ ÖLÇÜLDÜ: `/frame`'de hedef kaybının (`localized:false`) else dalı yoktu — 70 sn kedisiz karede telde 159 duty>0
    paket, STOP 0; son sürüşten 65,8 sn sonra hâlâ enerjili (sürüş deadline'a dek keep-alive ile sürüyordu).
    Döngünün kuralıyla AYNI: tek kare kaybında durdurmaz (tespit anlık sekebilir); hedef yeniden bulununca sayaç
    sıfırlanır ve sürüş sürer — seans BİTMEZ, sürüş yetkisi (nesil) kesilmez.
    ⚠️ 1-C inceleme i7-F-1 (arka kalkan): STOP eskiden yalnız `seri == N` anında gidiyordu — kayıp STOP'unu atlatan bir
    sürüşten sonra hedef kayıp kaldıkça bir daha STOP gelmiyordu. Artık N ve sonrasındaki HER kayıp karede yinelenir.
    ⚠️ 1-C inceleme i7-F-2: sayaç GÜNCEL seansın onayına aittir. Eski seansın mührüyle girmiş, hâlâ işlenen (ör.
    lokalizasyonda bekleyen) kare — `/ai/pro/stop` → yeni `/start` arasında — sayacı ESKİ onaya çevirip sıfırlıyordu;
    yeni seansın sonraki karesi onu yeniden sıfırlıyor, kayıp STOP'u gecikiyordu (ölçüldü 30/30: 3. yerine 5. karede).
    Mührü güncel aktif seansın onayı OLMAYAN kare sayaca DOKUNMAZ (0 döner; sürüşü zaten mühür/nesil kapısıyla reddedilir)."""
    import servers.api_server as _apx

    with _apx._session_lock:
        _guncel = _apx._active_session.get("onay_kimligi") if _apx._active_session.get("is_active") else None
    if muhur.get("onay") != _guncel:
        return 0
    with _frame_kayip_kilit:
        if _frame_kayip["onay"] != muhur["onay"]:
            _frame_kayip.update(onay=muhur["onay"], seri=0)
        if bulundu:
            _frame_kayip["seri"] = 0
            return 0
        _frame_kayip["seri"] += 1
        return _frame_kayip["seri"]


async def _frame_kayip_stopu(neden: str, seri: int = _AI_LOST_STOP_STREAK) -> None:
    """İG-5.1: AI'nın sürdüğü bobinlere STOP (döngünün hedef-kaybı durdurmasıyla aynı kapsam). STOP yalnız artar (Ö.4-Y8).

    ⚠️ 1-C inceleme i7-F-1: STOP'tan ÖNCE hedef-kaybı nesli artar → bu STOP'tan önce başlamış bir "bulundu" gözlemi
    (tahminde bekleyen uçuştaki kare) artık SÜREMEZ (`update_coil` kilit altında reddeder). Sürüş yetkisi KESİLMEZ:
    hedef yeniden bulununca (yeni gözlem) sürüş sürer. Yinelenen STOP'ta bildirim/günlük N karede bir."""
    _bildir = seri % _AI_LOST_STOP_STREAK == 0
    try:
        estop_mandali.kayip_nesli_artir()
    except Exception:
        logger.exception("AI Pro /frame: kayıp nesli artırılamadı (STOP yine gönderilir)")
    try:
        import servers.api_server as _apx

        # O-1.1 (Ö.4-Y8): KENDİ iş parçacığı — ortak havuz (`to_thread`) asılı G/Ç ile doluyken STOP sıra beklemez.
        _teyitsiz = await _apx._durdurma_is_parcaciginda(_apx._stop_session_coils, range(1, 8), ad="frame-kayip-stop")
        if _bildir:
            _apx._bildir_teyitsiz_stop(_teyitsiz, lambda d: ceviri.t("bildirim.kaynak.aiProHedefKaybiMobil", dil=d))
    except Exception:
        logger.exception("AI Pro /frame: hedef-kayıp STOP hatası")
    if _bildir:
        logger.warning(
            "AI Pro /frame: hedef %d ardışık karedir bulunamadı (%s) → bobinler DURDURULDU (hedef yeniden bulunursa "
            "sürüş sürer).",
            seri,
            neden,
        )


@ai_router.post("/api/ai/ai_pro/frame")
async def ai_pro_frame(
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    client_id: str = Form(""),
):
    """
    MOBİL AI Pro karesi: telefon kamerasından gelen TEK kareyi işler.
    cat_organ organ-lokalizasyon + em_kedi KediPredictor → bobin 1-7 PER-COIL sürüş
    (loop ile AYNI donanım yolu; el takibi SÖKÜLDÜ) → organ overlay + per-coil/metrik döner.
    cat_organ ağır (~1-4sn) → periyodik lokalize + cache (mobil akıcı kalsın).

    Organ/süre AKTİF AI Pro seansından okunur (web ile aynı state). FE bu çağrıdan
    ÖNCE /api/ai/pro/start çağırır; mobilde kareler bu endpoint'ten, web'de sunucu kamerasından.
    """
    # ⚠️ D1.80 · D1.81: sürüş NİYETİ İSTEK GİRİŞİNDE seans MÜHRÜNDEN alınır (tür = ai_pro + tüketilmiş onay + nesil +
    # model + kalan süre). Lokalizasyon/tahmin 0,3–2,2 sn sürer; arada gelen acil durdurma / durdurma (ve ardından
    # "Sıfırla + yeni seans") nesli bayatlatır → sürüş `update_coil`da DURUM KİLİDİ ALTINDA reddedilir. Eskiden seans
    # tahminden ÖNCE bir kez ve `mode.startswith("AI")` ile denetleniyordu (İG-5.2/5.3: onaysız seans + yeniden enerji).
    _muhur = _ai_pro_surus_muhru()
    try:
        img = await _decode_image(file, image_base64, label="ai_pro_frame")

        # 3. tur denetimi [B1]: YABANCI (sahip dışı) istemcinin karesi paylaşılan cache'i localize
        # edip KİRLETMEZ ve bobin SÜRMEZ (aşağıda). Yabancıysa lokalizasyon HİÇ koşmaz → sahibin
        # cat_organ koordinatları izleyicinin kamerasıyla ezilmez.
        is_foreign = _ai_kare_yabanci(client_id)

        # cat_organ organ-lokalizasyon (el takibi söküldü). Ağır (~1-4sn) → periyodik + cache;
        # inference'i thread'e AL → event-loop'u (WS telemetri + diğer istekler) bloklamasın.
        global _ai_relocalize
        now = time.time()
        need_localize = (not is_foreign) and (
            _ai_relocalize
            or _ai_organ_cache["organ_id"] != _ai_organ_id
            or (now - _ai_organ_cache["at"]) >= _ORGAN_LOCALIZE_INTERVAL_S
        )
        if need_localize:
            # DENETIM P2 (mobil yolda AYNI organ-degisim yarisi — loop tarafiyla simetrik):
            # organ kimligini SNAPSHOT al (await sonrasi global yeniden okunmasin, yoksa ESKI
            # organin koordinatlari YENI organin etiketiyle 10 sn cache'lenir) ve relocalize
            # bayragini ONCE tuket (islem sirasinda gelen yeni istek yutulmasin).
            _oid = _ai_organ_id
            _ai_relocalize = False
            _kayip_damgasi = estop_mandali.kayip_nesli()  # i7-F-1: gözlem LOKALİZASYON BAŞINDA damgalanır
            # *l_ek: 8. eleman guven_dokumu (2026-08-26) — geriye-uyumlu acilim (7'li tuple'da None).
            try:
                lz, lx, ly, lzz, lrel, lov, lkedi, *l_ek = await asyncio.to_thread(_localize_organ, img, _oid)
            except Exception:
                # ⚠️ İG-5.1 (istisna kolu): lokalizasyon hatası (ör. fantom karesi → pose/PnP) = hedef KAYBI. Ölçüldü:
                # yanıt 500 dönüyor (12/12), cache ESKİ "bulundu" kalıyor ve STOP yok — enerji sürüyordu. Döngüyle aynı:
                # cache geçersiz kılınır ve kayıp sayılır (N'de ve sonrasında STOP); yanıt eskisi gibi hata döner.
                with _ai_cache_lock:
                    _ai_organ_cache["localized"] = False
                if _muhur is not None and not is_foreign:
                    _seri = _frame_hedef_durumu(_muhur, False)
                    if _seri >= _AI_LOST_STOP_STREAK:
                        await _frame_kayip_stopu("lokalizasyon hatası", _seri)
                raise
            with _ai_cache_lock:
                _ai_organ_cache.update(
                    {
                        "x_mm": lx,
                        "y_mm": ly,
                        "z_mm": lzz,
                        "reliability": lrel,
                        "localized": lz,
                        "kayip_damgasi": _kayip_damgasi,
                        "overlay_bgr": lov,
                        "at": now,
                        "organ_id": _oid,
                        "kedi_var": lkedi,  # anahtar adı korunur (anlam: "özne kadrajda")
                        # MODEL DAMGASI (Faz 1): propose tazelik kontrolü buna bakar —
                        # kedi hazırlığından kalan cache fantom önerisine "taze" görünmesin.
                        "model": _ai_hedef_modeli,
                        # Sağlayıcı meta'sı (Faz 2): kare üstü hedef adayları, kalibrasyon
                        # yöntemi, seçili hedefin E'leri, eğitim-aralığı işareti. Kedi'de BOŞ.
                        **_saglayici_cache_alanlari(),
                        "guven_dokumu": (l_ek[0] if l_ek else None),
                    }
                )

        with _ai_cache_lock:
            localized = _ai_organ_cache["localized"]
            x_mm = _ai_organ_cache["x_mm"]
            y_mm = _ai_organ_cache["y_mm"]
            z_mm = _ai_organ_cache["z_mm"]
            rel = _ai_organ_cache["reliability"]
            kedi_var = bool(_ai_organ_cache.get("kedi_var"))
            guven_dokumu = _ai_organ_cache.get("guven_dokumu")  # snapshot (yirtik-okuma politikasi)
            kayip_damgasi = _ai_organ_cache.get("kayip_damgasi")  # i7-F-1: gözlemin damgası (lokalizasyon başı)
            # ⚠️ D1.59 (B-5.4): koordinatın ORGANI aynı anlık görüntüden (await sırasında global değişmiş olabilir).
            _c_oid = _ai_organ_cache.get("organ_id")
            # F2 (denetim 2026-08-24): bir LOKALİZASYONUN kimliği (cache 'at'; istek-başı `now` DEĞİL).
            # Kareler 1,5 sn'de, lokalizasyon en fazla 10 sn'de bir → eko karelerde update bloğuna
            # girilmez, `at` önceki ölçümün damgasını korur. Panel ARDISIK_ONAY sayacını yalnız YENİ
            # damgada artırır (eko-kare değil) → "iki tutarlı ölçüm" gerçekten iki AYRI lokalizasyon.
            localized_at = _ai_organ_cache.get("at") or 0.0

        # GÜVENLİK (Audit P0): bobin YALNIZCA süre-watchdog kapsamındaki AKTİF AI Pro seansı
        # varken sürülür. /start çağrılmadan (veya süre dolduktan / durdurulduktan sonra) gelen
        # kare bobin SÜRMEZ → watchdog'un izlemediği gözetimsiz/uzayan PEMF maruziyetini engeller.
        # D1.80: "aktif AI Pro seansı" = istek girişindeki MÜHÜR (tür + onay + nesil), süresi MÜHÜRDEN (İG-5.9),
        # model mühürdeki ve (araştırma modeliyse) bayrak SÜRÜŞ ANINDA açık.
        session_active = False
        try:
            session_active = (
                _muhur is not None and _muhur["bitis_mono"] > time.monotonic() and _muhur_surulebilir_mi(_muhur)
            )
        except Exception:
            logger.exception("ai_pro_frame: aktif-seans kontrolü hatası")
            session_active = False

        # ⚠️ 1-C inceleme i7-F-1: bir hedef-kaybı STOP'undan ESKİ "bulundu" gözlemi (STOP'tan sonra biten uçuştaki
        # lokalizasyonun önbelleğe yazdığı) BULUNDU SAYILMAZ — sürülmez ve kayıp sayılır.
        _bulundu = bool(localized) and not estop_mandali.gozlem_engeli(kayip_damgasi)
        # Gösterilen organ = sürülen organ (koordinat bulunduysa); yoksa seçili hedef.
        _gosterim_oid = _c_oid if (localized and isinstance(_c_oid, int) and _c_oid >= 0) else _ai_organ_id
        # ⚠️ D1.60 (A-16, 2. katman): yalnız MÜHÜRDEKİ hedef sürülür. Küresel hedef `/organ` dışında bir yolla değişse
        # de (409 1. katmandır) mühür dışı hedefin koordinatı sürülmez; o kare "hedef yok" sayılır (N'de STOP).
        _surulebilir_hedef = _bulundu and _muhur is not None and _c_oid == _muhur.get("hedef")
        # İG-5.1: sürülebilir seansta SAHİBİN karesi hedefi kaybettiyse kayıp sayılır; ARDIŞIK N kayıpta (ve sonrasında her
        # kayıp karede — i7-F-1 arka kalkanı) AI'nın sürdüğü bobinlere STOP. Yabancı kare sayılmaz.
        # D1.E07: "bulundu" sayacı sıfırlaması tahminden SONRA (aşağıda) — doz modeli her karede hata verirse sayaç
        # sıfırlanıp STOP hiç gelmezdi (önceki doz keep-alive ile sürerdi).
        if session_active and not is_foreign and not _surulebilir_hedef:
            _seri = _frame_hedef_durumu(_muhur, False)
            if _seri >= _AI_LOST_STOP_STREAK:
                await _frame_kayip_stopu("hedef bulunamadı", _seri)

        D, P, e_field = [0.0] * 7, [0.0] * 7, 0.0
        _surdu = False
        _surulen: list = []  # D1.84: telde GERÇEKTEN sürülen bobinler
        # GERÇEK donanımı sür (loop ile aynı yol) — organ bulundu VE aktif AI Pro seansı varsa VE
        # kare seansın SAHİBİNDEN geliyorsa. Bobin 1-7. [B1]: yabancı kare ASLA sürmez (yanlış
        # kameradan hesaplanan hedefe onaylı seansta enerji verilmesini önler).
        if _surulebilir_hedef and session_active and not is_foreign:
            D, P, e_field = await asyncio.to_thread(_predict_and_drive, x_mm, y_mm, z_mm, _c_oid)
        if _surulebilir_hedef and session_active and not is_foreign and not any(D):
            # ⚠️ D1.E07 (İG-5.15, seans ortası): doz modeli hata verdi (zarf `[0]*7`) → SÜRÜLMEZ, operatöre söylenir ve
            # bu kare hedef-kaybı sayılır (N karede STOP — mevcut kural). Eskiden sıfır doz "sürüldü" diye gönderiliyordu.
            _doz_hatasi_bildir()
            _seri = _frame_hedef_durumu(_muhur, False)
            if _seri >= _AI_LOST_STOP_STREAK:
                await _frame_kayip_stopu("doz modeli hatası", _seri)
        elif _surulebilir_hedef and session_active and not is_foreign:
            _frame_hedef_durumu(_muhur, True)  # hedef bulundu VE geçerli doz → kayıp sayacı sıfırlanır
            # Audit P2: _drive_coils_ai_pro senkron seri port yazımı yapar (bobin başına ~onlarca ms; D1.83'e kadar 6-7
            # için MQTT de) → event-loop'u bloklardi (es-zamanli /emergency_stop yaniti gecikir). to_thread'e al.
            # D1.81: niyet nesli bağlamı `to_thread` iş parçacığına kopyalanır; `update_coil` onu kilit altında denetler.
            # i7-F-1: gözlem damgası da taşınır — tahmin sırasında kayıp STOP'u geldiyse sürüş kilit altında reddedilir.
            with estop_mandali.surus_baglami(_muhur["nesil"]), estop_mandali.gozlem_baglami(kayip_damgasi):
                _surulen = await asyncio.to_thread(_drive_coils_ai_pro, D, P) or []
            # Sürüş GEÇERLİ kaldı mı (tahmin/sürüş sırasında durdurma ya da kayıp STOP'u geldiyse donanım reddetti).
            # D1.84: en az bir bobin telde KABUL edilmediyse "sürüldü" denmez.
            _surdu = bool(_surulen) and not (
                estop_mandali.baslatma_engeli(_muhur["nesil"]) or estop_mandali.gozlem_engeli(kayip_damgasi)
            )
            if _surdu:
                _canli_e_odak()  # ODK6: canlı E = bu karede sürülen ODAK planının CST E'si
            if _surdu:
                remaining = max(0, int(_muhur["bitis_mono"] - time.monotonic()))
                try:
                    from servers.api_server import update_live_session_state

                    rep_duty = round(normalize_ai_pro_duty_ratio(D[0]) * 100.0, 1)
                    update_live_session_state(
                        is_active=True,
                        mode=f"AI Pro · {_aktif_saglayici().title} · {_aktif_saglayici().hedef_adi(_gosterim_oid)}",
                        freq=_ai_pro_frek_hz,
                        intensity=0.0,  # D1.89: duty mT alanına yazılmaz
                        duty_temsil=rep_duty,
                        remaining_min=remaining // 60,
                        duration_sec=_ai_duration_min * 60,
                        surus_nesli=_muhur["nesil"],  # İG-5.36: kilit altında yeniden denetlenir
                    )
                except Exception:
                    logger.exception("AI Pro frame: live state update hatası")
            else:
                session_active = False

        # Organ overlay (yoksa ham kare) — mobil için küçült. [B1]: yabancı izleyiciye SAHİBİN
        # overlay'ini gösterme (kendi ham karesini görür, "yalnız görüntüleme" bandı paneldedir).
        overlay = None if is_foreign else _ai_organ_cache.get("overlay_bgr")
        img_out = overlay if overlay is not None else img
        oh, ow = img_out.shape[:2]
        sc = min(1.0, 960.0 / max(oh, ow))
        if sc < 1.0:
            img_out = cv2.resize(img_out, (int(ow * sc), int(oh * sc)), interpolation=cv2.INTER_AREA)
        b64_image = _encode_jpg_b64(img_out, quality=70)

        return JSONResponse(
            content={
                "status": "success",
                "image_base64": b64_image,
                **_kare_boyutu(img_out),
                # [B1]: yabancı izleyici için detected/catDetected bastırılır (kendi kamerasını
                # localize etmedik → dürüst değer False) + foreignViewer bayrağı + sahip kimliği.
                "detected": bool(localized) and not is_foreign,
                "foreignViewer": is_foreign,
                "ownerClientId": _ai_owner_client,
                # AŞAMA (E2, denetim 2026-08-24): "kedi yok" ile "kedi var, organ bulunamadı" AYRI
                # bilgiler — mobil hazırlık ekranı doğru yönlendirmeyi bundan seçer. Mobil panel
                # catDetected'i YALNIZ bu /frame yanıtından okur (AiProStatus tipi taşımaz); alan
                # olmadan hazırlık şeridi "hayvan görünüyor, organ aranıyor" aşamasını hiç gösteremezdi.
                "catDetected": kedi_var and not is_foreign,
                # F2: lokalizasyon damgası — panel ardisik sayacını eko-karelerden AYIRIR.
                "localizedAt": localized_at,
                "driven": bool(localized and session_active and not is_foreign and _surdu),
                "sessionActive": session_active,
                "reliability": round(rel, 3),
                # Sunum-katmanı XAI (2026-08-26): web/mobil paritesi — güven dökümü.
                "guvenDokumu": guven_dokumu,
                # İNCELEME-2 i1-F-1: AI Pro seansı (mühür) varken sürülmeyen ama telde çalışan bobin "sürülmedi" denmez.
                "perCoil": _build_ai_pro_percoil(
                    D, P, _surulen if _surdu else (), _teldeki_ai_pro_bobinleri() if _muhur is not None else None
                ),
                "target": {"x": round(x_mm, 1), "y": round(y_mm, 1), "z": round(z_mm, 1)},
                "eField": round(e_field, 4),
                "organId": _gosterim_oid,
                "organName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _gosterim_oid),
                # YALNIZ-EK (Faz 1): mevcut anahtarlar aynen kalır (sürüm kayması deseni).
                "model": _aktif_saglayici().ad,
                "modelName": _aktif_saglayici().title,
                "subjectLabel": _aktif_saglayici().subject_label,
                "targetName": ai_pro_hedef.hedef_gosterim_adi(_aktif_saglayici(), _gosterim_oid),
                "targets": _ai_organ_cache.get("targets") or [],
                "method": _ai_organ_cache.get("method") or "",
                "kapiEylem": _ai_organ_cache.get("kapi_eylem") or "",  # YALNIZ-EK (KD-3a · B-KD3a.1)
                "targetLabel": _ai_organ_cache.get("target_label") or "",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI Pro frame error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.aiProKare", dil=d), e)


@ai_router.post("/api/ai/vision/segmentation")
@sonuc_izle  # TD9: "kedi bulunamadı" (cat_count 0) ücretsiz
async def analyze_segmentation(file: UploadFile = File(None), image_base64: str = Form(None)):
    """YOLO Seg Kedi Segmentasyonu"""
    try:
        if ai_service_enabled():
            return await _kapili_devret("segmentation", file=file, image_base64=image_base64)
        img = await _decode_image(file, image_base64, label="segmentation")

        def _load_seg():
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync

            path = download_model_sync("ai_hub/cat_segmentation/yolov8m-seg.onnx")
            return YOLO(path, task="segment")

        model = await asyncio.to_thread(_get_or_load_model, "seg", _load_seg)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)
        # P2 audit 2026-06-28: tmp .jpg'yi HER durumda sil (predict/mask hata yolunda sizmasin → disk
        # dolar → _ensure_write_guardrail sensor/seans yazimini engelleyebilir). landmark deseni.
        try:
            results = await asyncio.to_thread(
                lambda: model.predict(source=tmp.name, conf=0.25, iou=0.7, imgsz=640, device="cpu", verbose=False)
            )
            r = results[0]
            cat_count = len(r.boxes) if r.boxes else 0
            if r.masks is not None and len(r.masks) > 0:
                for mask_data in r.masks.data:
                    mask_np = mask_data.cpu().numpy()
                    mask_resized = cv2.resize(mask_np, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                    colored = np.zeros_like(img)
                    colored[:, :, 1] = 160
                    blend = cv2.addWeighted(img, 0.55, colored, 0.45, 0)
                    img = np.where(mask_resized[:, :, None] > 0.5, blend, img).astype(np.uint8)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        b64_image = _encode_jpg_b64(img, quality=GOSTERIM_JPEG_KALITESI)

        return {"status": "success", "cat_count": cat_count, "image_base64": b64_image, **_kare_boyutu(img)}
    except Exception as e:
        logger.error(f"Segmentation inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.segmentasyon", dil=d), e)


_FGS_BANTLARI_CACHE: dict | None = None


def _fgs_bantlari() -> dict:
    """thresholds_calibrated.json'dan {olcum: {p5, p95}} — bir kez yüklenir.

    §KALAN A4: UI 'ölçülen değer vs popülasyon bandı' panelini bu bantlarla çizer;
    dosya okunamazsa boş dict (panel gizlenir — zarif)."""
    global _FGS_BANTLARI_CACHE
    if _FGS_BANTLARI_CACHE is None:
        try:
            import json as _json

            _yol = os.path.join(project_root, "ai_hub", "cat_landmark", "thresholds_calibrated.json")
            with open(_yol, encoding="utf-8") as _f:
                _ham = _json.load(_f)
            _FGS_BANTLARI_CACHE = {
                k: {"p5": round(float(v["p5"]), 4), "p95": round(float(v["p95"]), 4)}
                for k, v in _ham.items()
                if isinstance(v, dict) and "p5" in v and "p95" in v
            }
        except Exception:
            logger.warning("fgs bantlari yuklenemedi (panel gizlenecek)", exc_info=True)
            _FGS_BANTLARI_CACHE = {}
    return _FGS_BANTLARI_CACHE


@ai_router.post("/api/ai/vision/thermal")
async def analyze_thermal(
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    explain: bool = Form(False),
    xai_method: str = Form("hirescam"),
):
    """GhostNetV2 Termal Analiz (+opsiyonel CAM ısı haritası — Faz 2 + §KALAN A6:
    CAM yöntemi dışa açıldı, allowlist'li). AI1.X1: harita TAHMİN EDİLEN sınıfı açıklar (varsayılan HiRes-CAM;
    Grad-CAM++ tek lojitte sınıf-duyarsız) ve açıklanan sınıf `xai_hedef` olarak döner."""
    if xai_method not in ("gradcam++", "gradcam", "eigencam", "hirescam"):
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.xaiYontemi", xai_method=xai_method))
    try:
        if ai_service_enabled():
            return await _kapili_devret(
                "thermal",
                file=file,
                image_base64=image_base64,
                data=({"explain": "true", "xai_method": xai_method} if explain else None),
            )
        img = await _decode_image(file, image_base64, label="thermal")
        # SG.G4: termal makullik kapısı `_decode_image` içinde koştu (KESİN uyumsuz → 422, analiz yok). Geçen girdi doğrulanamadıysa
        # (akromatik / kararsız) sonuç bunu SÖYLER — arayüz yalnız gösterir (`utils/image_domain.termal_girdi_dogrulamasi`).
        from utils import image_domain as _imgdom

        girdi_dogrulama = ai_kapi_metni.termal_dogrulama_cevir(_imgdom.termal_girdi_dogrulamasi(img))

        def _load_thermal():
            from ai_hub.cat_thermal.inference_cat_thermal import CatThermalPredictor

            return CatThermalPredictor(model_name="GhostNetV2")

        predictor = await asyncio.to_thread(_get_or_load_model, "thermal", _load_thermal)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)

        # P2 audit 2026-06-28: tmp .jpg'yi HER durumda sil (predict hata yolunda sizmasin → disk dolar).
        # Faz 2: XAI da AYNI tmp'yi kullanir → silme XAI'den SONRA (finally kapsami genisletildi).
        yanit = {}
        try:
            result = await asyncio.to_thread(lambda: predictor.predict(tmp.name, threshold=0.5))
            # Sunum-katmanı XAI: CAM ısı haritası — EKRANDA GÖSTERİLEN tahminin (Sağlıklı / Hasta) kanıtı (AI1.X1:
            # eskiden hep 'Hasta' lojiti açıklanıyordu). ⚠️ Açıklama İKİNCİL — hatası analizi ASLA düşürmez (zarif
            # düşüş). CPU'da PT CAM sn'ler sürebilir (karar #2 notu) → to_thread; tek-iş kilidi modülde.
            if explain:
                try:
                    from ai_hub.cat_thermal import inference_cat_thermal as _ict

                    _etiket = result.get("label")
                    _x = await asyncio.to_thread(
                        lambda: _ict.xai_termal_isi_haritasi(tmp.name, None, xai_method, hedef_sinif=_etiket)
                    )
                    yanit["xai_image_base64"] = _x["xai_image_base64"]
                    yanit["xai_method"] = _x.get("method")
                    yanit["xai_hedef"] = _x.get("hedef")
                except Exception as xe:
                    logger.warning("Termal XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                    yanit["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        b64_image = _encode_jpg_b64(img, quality=GOSTERIM_JPEG_KALITESI)

        return {
            "status": "success",
            "prediction": result,
            "image_base64": b64_image,
            **_kare_boyutu(img),
            **yanit,
            "girdi_dogrulama": girdi_dogrulama,
        }
    except Exception as e:
        logger.error(f"Thermal inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.termal", dil=d), e)


@ai_router.post("/api/ai/vision/reticulocytes")
async def analyze_reticulocytes(
    file: UploadFile = File(None), image_base64: str = Form(None), explain: bool = Form(False)
):
    """YOLO Detect Retikülosit Sayımı (+opsiyonel tespit hedefli HiRes-CAM — Faz 2 kuyruğu; AI1.X2)"""
    tmp = None  # finally'de temizlenecek temp görüntü (hata olsa da sızmasın)
    try:
        if ai_service_enabled():
            return await _kapili_devret(
                "reticulocytes",
                file=file,
                image_base64=image_base64,
                data=({"explain": "true"} if explain else None),
            )
        img = await _decode_image(file, image_base64, label="reticulocytes")

        def _load_retic():
            from ultralytics import YOLO
            from utils.model_downloader import download_model_sync

            path = download_model_sync("ai_hub/feline_reticulocytes/yolov8s.onnx")
            return YOLO(path, task="detect")

        # model-load-thread: ilk-yükleme (indir+ONNX) event-loop'u bloklamasın → thread-safe cache'i offload et.
        model = await asyncio.to_thread(_get_or_load_model, "retic", _load_retic)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)

        temp_project = os.path.join(tempfile.gettempdir(), "PEMF_API_AI")
        output_dir = os.path.join(temp_project, 'feline_reticulocytes', 'results')
        os.makedirs(output_dir, exist_ok=True)

        results = await asyncio.to_thread(
            lambda: model.predict(
                source=tmp.name,
                conf=0.25,
                iou=0.7,
                imgsz=640,
                device='cpu',
                save=True,
                project=os.path.join(temp_project, 'feline_reticulocytes'),
                name='results',
                exist_ok=True,
            )
        )

        CLASS_NAMES = ['erythrocyte', 'punctate reticulocyte', 'aggregate reticulocyte']
        counts = {c: 0 for c in CLASS_NAMES}

        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    counts[CLASS_NAMES[cls_id]] += 1

        saved_image_path = os.path.join(output_dir, os.path.basename(tmp.name))

        if os.path.exists(saved_image_path):
            img_res = cv2.imread(saved_image_path)
            _kodlanan = img_res
        else:
            _kodlanan = img
        b64_image = _encode_jpg_b64(_kodlanan, quality=GOSTERIM_JPEG_KALITESI)

        # Sunum-katmanı XAI (Faz 2 kuyruğu; AI1.X2): tespit hedefli HiRes-CAM — tespitlere dayanılan hücre bölgeleri.
        # ⚠️ tmp finally'de siliniyor → XAI burada. Açıklama İKİNCİL (zarif düşüş).
        _xai_alanlari = {}
        if explain:
            try:
                from ai_hub.feline_reticulocytes import inference_feline_reticulocytes as _ifr

                _x = await asyncio.to_thread(_ifr.xai_retikulosit_isi_haritasi, tmp.name)
                _xai_alanlari["xai_image_base64"] = _x["xai_image_base64"]
                _xai_alanlari["xai_method"] = _x.get("method")
            except Exception as xe:
                logger.warning("Retikülosit XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                _xai_alanlari["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")

        return {
            "status": "success",
            "counts": counts,
            "image_base64": b64_image,
            **_kare_boyutu(_kodlanan),
            **_xai_alanlari,
        }
    except Exception as e:
        logger.error(f"Reticulocytes inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.retikulosit", dil=d), e)
    finally:
        # reticulocytes-finally fix: temp dosyayı hata olsa da MUTLAKA sil (diğer uçlarla tutarlı).
        # Eski kod os.unlink'i finally DIŞINDA çağırıyordu → predict/imwrite hata verirse temp sızardı.
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


def _y51_duty_etiketi(model: str, duty_sum, cfg) -> dict:
    """1-E inceleme i-15.1 · Y51 (sahip): araştırma ucuna verilen (ya da kabin YAML'ından gelen) `duty_sum` vekil modelin
    EĞİTİM aralığı DIŞINDAYSA sonuç "eğitim aralığı dışı — güvenilmez" etiketi taşır (canlı E barıyla AYNI yardımcı ve
    alanlar: `efield_live.egitim_duty_araligi`). Değer gizlenmez/kırpılmaz (Ö.4-Y9: kıskaç değil, gösterim). Aralık
    okunamazsa etiket konmaz (bilinmiyor ≠ dışarıda)."""
    try:
        from servers.efield_live import egitim_duty_araligi

        etkin = float(duty_sum) if duty_sum is not None else float(cfg.phantom.duty_sum)
        aralik = egitim_duty_araligi(model)
    except Exception:
        logger.debug("Y51 duty etiketi hesaplanamadi (%s)", model, exc_info=True)
        return {}
    if aralik is None or aralik[0] <= etkin <= aralik[1]:
        return {}
    return {"dutyEgitimAraligiDisi": True, "dutyEgitimAraligi": [round(aralik[0], 2), round(aralik[1], 2)]}


def _kabin_cfg_hafif(model: str):
    """L1-7.18: mikroservis devrinde etkin varsayılan `duty_sum` için kabin YAML'ı — MODEL YÜKLENMEDEN (yalnız yapılandırma; servis
    istek değeri yoksa aynı gömülü YAML'ı kullanır)."""
    if model == "fantom":
        from ai_hub.inference_em_fantom.phantom_cv_v3 import load_cabin_config
    else:
        from ai_hub.inference_petri_dish.petri_cv_v2 import load_cabin_config
    return load_cabin_config(None)


def _y51_devir_etiketi(model: str, yanit, duty_sum):
    """L1-7.18 · i-15.1 açığı: GPU mikroservisine DEVREDİLEN yanıt da Y51 etiketini taşır (gömülü yolla AYNI yardımcı). Eskiden servis
    yanıtı geldiği gibi dönüyordu — aynı istek GPU profilinde etiketsizdi. Kabin YAML'ı okunamazsa etiket konmaz (bilinmiyor ≠ dışarıda)."""
    if not isinstance(yanit, dict):
        return yanit
    try:
        cfg = _kabin_cfg_hafif(model) if duty_sum is None else None
    except Exception:
        logger.debug("Y51 devir etiketi: kabin YAML okunamadi (%s)", model, exc_info=True)
        return yanit
    return {**yanit, **_y51_duty_etiketi(model, duty_sum, cfg)}


@ai_router.post("/api/ai/vision/em_fantom")
@sonuc_izle  # T3 · Y190e: canlı kipte "tümör / fantom bulunamadı" (no_detection) karesi dakikayı ücretlendirmez
async def analyze_em_fantom(
    _res=Depends(require_research),
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    phantom_length_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
    # T3 · Y189 (sahip + Çağlar Hoca): KOŞULSUZ kip — PEMF kapısının engelleyici / yeniden-çekim / güvenilmez nedenleri
    # sonucu "kullanılamaz" yapmaz, uyarı olarak gösterilir (`pemf_kapisi.atlanan`). Varsayılan KOŞULLU.
    kosulsuz: bool = Form(False),
):
    """Fantom Tümör Analizi (phantom_cv_v3 — hocanın v3'ü, AI-2 — + BiLSTM_XXL_Raw ONNX).

    Sentetik böbrek fantomu fotoğrafından: fantomu tespit et → mavi tümör
    odaklarını bul → 3B mm koordinatı (phantom_length_cm verilirse gerçek mm,
    yoksa piksel) → PhantomPredictor ile her tümör için D1-7/P1-7 + E_cancer.
    Klasik CV (headless-güvenli), 6-panel annotated görsel döner.
    """
    # T3 · Y189: YALNIZ gerçek True açar — doğrudan çağrıda (test / iç çağıran) Form varsayılanı FieldInfo'dur (truthy).
    kosulsuz = kosulsuz is True
    try:
        if ai_service_enabled():
            # I18NI-A3.2: GPU servisi katalog taşımaz (yaprak modül) → panel adları burada İSTEK dilinde kurulur.
            # L1-7.18: devir yanıtı da Y51 etiketini taşır (gömülü yolla aynı).
            _devir = _panel_adlarini_cevir(
                await _kapili_devret(
                    "em_fantom",
                    file=file,
                    image_base64=image_base64,
                    # I18NI-A3.3: panel GÖRSELİNE yazılan metnin dili (servis katalog taşımaz; alanı bilmeyen eski servis yok sayar → tr)
                    data={
                        "phantom_length_cm": phantom_length_cm,
                        "achieved_B": achieved_B,
                        "duty_sum": duty_sum,
                        "dil": ceviri.etkin_dil(),
                        # T3 · Y189 (None = gönderilmez; eski servis etkilenmez)
                        "kosulsuz": True if kosulsuz else None,
                    },
                ),
                _PANEL_ADLARI,
            )
            return _y51_devir_etiketi("fantom", _devir, duty_sum)
        img = await _decode_image(file, image_base64, label="em_fantom")

        # Yükleyici MODÜL SEVİYESİNDE (`_yukle_em_fantom_cv`): araştırma AI Pro fantom sağlayıcısı
        # aynı önbelleği paylaşır → ağır ONNX iki kez yüklenmez.
        cache = await asyncio.to_thread(_get_or_load_model, "em_fantom_cv", _yukle_em_fantom_cv)
        # Her istekte hafif pipeline (taze intrinsics), önbellekli predictor enjekte.
        # manual_fallback=False ŞART — headless serviste GUI açmamalı.
        pl = cache["cls"](cache["cfg"], phantom_length_cm=phantom_length_cm, manual_fallback=False)
        pl._predictor = cache["predictor"]
        # KD · Y258: veri kökünde sabit düzlem kalibrasyonu VARSA ArUco aranmaz (kare kalibrasyon kamerası / çözünürlüğünde değilse konum yok).
        pl.duzlem, pl.kamera_indeksi, pl.kamera_kimligi = (
            ai_pro_hedef.duzlem_durumu(),
            ai_pro_hedef.secili_kamera_indeksi(),
            ai_pro_hedef.secili_kamera_kimligi(),
        )

        result, ctx = await asyncio.to_thread(lambda: pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum))

        if result.success:
            # I18NI-A3.3: görsele yazılan başlık / not İSTEK dilinde (çizici iki dili taşır; `lang="tr"` sabiti EN arayüzde Türkçe çiziyordu).
            _dil = ceviri.etkin_dil()
            panels = await asyncio.to_thread(lambda: pl.render_panels(ctx, result, lang=_dil))
            # ⚠️ KAPAK + KALİTE (ADIM 1): mozaik 2×3'tür ve dikey telefon fotoğrafında
            # 6048×12256'ya çıkıyordu; q95 ile megabayt üretiyordu. Kapak olmadan yalnız
            # kaliteyi düşürmek YETMEZ (bağlayıcı kısıt çözünürlük).
            # ⚠️ ÇOKLU PANEL (ADIM 3): boru hattı 7 panel üretiyordu ve 6'sı AYNI SATIRDA
            # çöpe atılıyordu. Artık hepsi yayına çıkıyor; kök `image_base64` (07_combined)
            # KALIYOR → eski istemci etkilenmez (`paneller` yalnızca EK alan).
            _paneller = _panelleri_hazirla(panels, _kapakli_kodla, _PANEL_ADLARI)
            # ⚠️ KÖK GÖRSEL PANELDEN: `07_combined` zaten kodlandı. İkinci kez kodlamak
            # ÖLÇÜLEN 38 ms'i (6048×12256 dikey mozaik) boşuna yakar VE iki kodlamanın ileride
            # sessizce ayrışmasına kapı açardı — kök görsel ile panel AYNI kare olmalı.
            b64_image, _boyut = _kok_gorseli_sec(_paneller, _kapakli_kodla, img)
            status = "success"
        else:
            _bayt, _boyut = _kapakli_kodla(img)  # tespit yok → orijinali dön
            b64_image = base64.b64encode(_bayt).decode('utf-8')
            _paneller = []
            status = "no_detection"

        payload = result.to_dict()
        # Y144: tüketim kapısı BİR KEZ hesaplanır — hem yanıta eklenir hem bağlam / açıklama kararını verir (tek kaynak).
        _pemf = _pemf_alanlari(payload, "fantom", kosulsuz)
        # CANLI E-ALANI bağlamı (2026-08-06): tümör konumu + organ seans boyunca DEĞİŞMEZ.
        # Bunu saklarsak tedavi sürerken E'yi AYNI vekil modelle canlı B/duty'den türetebiliriz
        # → bar'daki değer bu paneldeki E ile aynı kaynaktan gelir (bkz. servers/efield_live.py).
        # ⚠️ D1.E07 (İG-5.76): PİKSEL kipinde koordinat piksel farkıdır (mm DEĞİL) ve doz hesaplanmaz → canlı E bağlamı
        # ve XAI duyarlılığı KURULMAZ (bağlam piksel konumuyla kurulsaydı E barı anlamsız konumdan E üretirdi).
        # ⚠️ AI-2 C7 (S-AI2.5): hocanın v2 / v3 kuralı — kabin konumu bilinmeyen çerçevede (`pemf_valid` false: fantom boyu /
        # halka / yerleşim ya da petri çapı / plaka çerçevesi — mm ama KABİN DEĞİL) D / P / E fiziksel olarak geçersiz. Etiketsiz
        # canlı E barı ve "dozu belirleyen" açıklaması bu konumdan KURULMAZ (D1.E07 piksel kuralıyla aynı sınıf); D / P / E yine
        # gösterilir, `pemf_kapisi` eylemiyle (C4).
        # ⚠️ Y144 (S-AII.7, sahip 2026-10-13): `pemf_valid` YETMEZ — kabin konumu geçerli ama fantom tespiti güvenilmez
        # (`reliable=false`), yerleşim referansla uyuşmuyor (`layout_mismatch`) ya da sonucu kullanılamaz / yeniden çekim isteyen
        # uyarı varken (`control_*`, `oblique_view`, `ring_partial` …) bağlam ve açıklama bu konumdan KURULMAZ: bobin sürüşüne esas
        # alınamayan sonuç seans boyunca "canlı" görünmesin. Ölçüt TEK KAYNAK `pemf_kapisi.surulebilir` (AI Pro sürüş kapısıyla aynı).
        _fiziksel = result.method != "pixel" and _pemf["pemf_kapisi"].get("surulebilir") is True
        try:
            from servers import efield_live as _ef

            # D1.100: konumu çözülemeyen bölge bağlam kuramaz; ilk bölge çözülemediyse eski bağlam KALMAZ (boş → temizler).
            _konumlu = [r for r in (payload.get("tumor_regions") or []) if r.get("centroid_cabin_mm")]
            _ef.set_context(_konumlu if _fiziksel else [])
        except Exception:
            logger.debug("canlı E-alanı bağlamı kurulamadı", exc_info=True)
        # §KALAN A5 (em_kedi paritesi): "tahmini en cok ne surukledi" meta'si — ILK
        # tumor bolgesi icin hafif duyarlilik. Aciklama IKINCIL: hatasi analizi dusurmez.
        _xai_meta = {}
        # D1.100: XAI yalnız konumu ÇÖZÜLMÜŞ ilk bölgede (eskiden konum yoksa (0, 0, 0)'da üretilirdi).
        _xai_r0 = next((r for r in (payload.get("tumor_regions") or []) if r.get("centroid_cabin_mm")), None)
        if result.success and _fiziksel and _xai_r0 is not None:
            try:
                from ai_hub.inference_em_fantom import inference_em_fantom as _ief

                _r0 = _xai_r0
                _c = list(_r0["centroid_cabin_mm"])
                _xai_meta["xaiSensitivity"] = await asyncio.to_thread(
                    _ief.xai_hizli_sensitivity,
                    cache["predictor"],
                    _c[0],
                    _c[1],
                    _c[2],
                    _r0.get("organ_id", 1),
                    # Baz-nokta = pipeline'in FIILEN kullandigi (None -> cfg.phantom
                    # default'lari; dusman-dogrulama 2026-08-27 — 'or 0.0' yanlis noktada
                    # aciklama uretiyordu, 8/8 test noktasinda top-3 farkliydi).
                    achieved_B if achieved_B is not None else float(cache["cfg"].phantom.achieved_B),
                    duty_sum if duty_sum is not None else float(cache["cfg"].phantom.duty_sum),
                )
            except Exception as xe:
                logger.warning("em_fantom XAI meta üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                _xai_meta["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")  # D5.05 (B-5.15)
        return {
            "status": status,
            "image_base64": b64_image,
            # ⚠️ KODLANAN karenin boyutu (ADIM 2): istemcinin oran kilidi bunu okur.
            # `_kapakli_kodla` kareyi KÜÇÜLTEBİLDİĞİ için orijinal boyut YANLIŞ olurdu →
            # kutu oranı kayar, üzerine çizilen işaretler canlı görüntüyle uyuşmaz.
            **_boyut,
            "paneller": _paneller,
            "success": result.success,
            "error": result.error,
            "n_tumor": result.n_tumor,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "tumor_regions": payload["tumor_regions"],
            "healthy_regions": payload["healthy_regions"],
            "timing_ms": result.timing_ms,
            **_xai_meta,
            **_y51_duty_etiketi("fantom", duty_sum, cache["cfg"]),  # i-15.1 · Y51
            # AI-2 (hoca fantom v3): `reliable`, `pemf_valid`, `pemf_source`, `coord_frame`, `warnings`, kayıt / halka özeti
            # + tüketim kapısının eylem metinleri (`pemf_kapisi`). YALNIZ EK — eski istemci etkilenmez. Tek kaynak: ai_hub.
            **_pemf,
        }
    except Exception as e:
        # D1.E07 (İG-5.80): sonlu olmayan girdi (ör. achieved_B=nan) ya da bozuk ölçekleyici → 422 (istemci girdisi;
        # eskiden "makul" bir doz dönüyordu). Metin yalnız hangi alanın geçersiz olduğunu söyler (iç ayrıntı yok).
        from ai_hub.em_girdi import SonluOlmayanGirdi as _SonluDegil

        if isinstance(e, _SonluDegil):
            logger.warning("em_fantom: geçersiz girdi reddedildi: %s", e)
            raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.fantomAnalizi", e=e)) from None
        logger.error(f"em_fantom inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.fantomAnaliz", dil=d), e)


@ai_router.post("/api/ai/vision/em_petri")
@sonuc_izle  # T3 · Y190e: canlı kipte "plaka / kuyucuk bulunamadı" (no_detection) karesi dakikayı ücretlendirmez
async def analyze_em_petri(
    _res=Depends(require_research),
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    petri_diameter_cm: float = Form(None),
    achieved_B: float = Form(None),
    duty_sum: float = Form(None),
    # ── ARAYÜZDEN AYARLANABİLİR (sahip talebi 2026-09-09) ───────────────────────────────
    # Hepsi opsiyonel; verilmeyen alan boru hattı varsayılanında kalır. Sınırlar ve çözüm
    # TEK KAYNAK: ai_hub/inference_petri_dish/petri_ayar.py (mikroservis ucu da onu kullanır).
    yolo_conf: float = Form(None),
    yolo_iou: float = Form(None),
    resize_max: float = Form(None),
    plaus_circularity: float = Form(None),
    plaus_conf: float = Form(None),
    plaus_area_frac: float = Form(None),
    plaus_guard: bool = Form(None),
    # AI-2 (hocanın petri v2'si): kip + laboratuvar protokolü. Verilmezse YAML `multiwell:` (24'lük plaka, A1 auto,
    # kontrol yok). plate_type 0 = tekil petri kapları (eski YOLO kipi). Doğrulama TEK KAYNAK: petri_ayar.
    plate_type: int = Form(None),
    control_healthy: str = Form(None),
    control_cancer: str = Form(None),
    a1_corner: str = Form(None),
    # T3 · Y191b (sahip + Çağlar Hoca): plaka kipinde ızgara hücresi skoru eşiği (verilmezse boru hattı varsayılanı 0,6; 0 = kapalı).
    kuyu_skor_esigi: float = Form(None),
    # T3 · Y189 (sahip + Çağlar Hoca): KOŞULSUZ kip — hattı kesen engeller (plaka bulunamadı → ham YOLO, makullik reddi) ve
    # PEMF kapısının nedenleri uyarıya döner. Varsayılan KOŞULLU = davranış AYNI.
    kosulsuz: bool = Form(False),
):
    """Petri Kuyu Analizi (petri_cv_v2 — hocanın v2'si: 24'lük plaka ızgarası / tekil kap YOLO11m-seg + BaggingRegressor ONNX).

    Petri fotoğrafından: YOLO ile N kuyucuk tespit → her kuyuda HSV kanser
    sınıflandırma → 3B mm koordinat (petri_diameter_cm verilirse gerçek mm) →
    PetriPredictor ile D1-7/P1-7 + E_cancer. Klasik CV + YOLO (headless-güvenli),
    7-panel annotated görsel döner.

    AYARLANABİLİR PARAMETRELER (hepsi opsiyonel; hiçbiri verilmezse davranış BİT-BİT eskisi):
      · yolo_conf (0.6 — T3 · Y191 sahip 2026-10-24; önce 0.25) / yolo_iou (0.7) — tespit eşikleri. ÖLÇÜLDÜ (2026-09-09):
        aynı fotoğrafta conf 0.25 → 0.05 bir kuyucuktan üç kuyucuğa çıkardı.
      · resize_max — uzun kenar bunu aşarsa görüntü küçültülür (0/boş = kapalı). YOLO ONNX'i
        640x640'a SABİT export edilmiştir; imgsz bu yüzden YÜKSELTİLEMEZ (960/1280 denemesi
        "INVALID_ARGUMENT ... Expected: 640" verir) — küçültme o sabitin altında kalan tek
        kontroldür. Ölçek-güvenlidir: petri ölçeği görüntünün İÇİNDEN gelir (kuyu çapı ya da
        kabin işareti) ve kalibrasyon K'si _olcekli_intrinsics ile birlikte ölçeklenir.
      · plaus_circularity (0.55) / plaus_conf (0.85) / plaus_area_frac (0.25) — "petri değil"
        denetiminin eşikleri; plaus_guard=false denetimi tamamen kapatır.
        ⚠️ Denetim YANLIŞ MODÜLE yüklenen fotoğrafa sessizce sonuç üretmeyi engeller; gevşetilmiş
        eşikle çıkan sonuç yanıltıcı olabilir. Bu yüzden yanıt ETKİN ayarları taşır
        (plausibility.thresholds + yolo_ayar + resize) — denetim izi.
    """
    # T3 · Y189: YALNIZ gerçek True açar — doğrudan çağrıda (test / iç çağıran) Form varsayılanı FieldInfo'dur (truthy).
    kosulsuz = kosulsuz is True
    # T3 · Y191b: doğrudan çağrıda (test / iç çağıran) Form varsayılanı FieldInfo'dur → yalnız gerçek sayı / dize "verildi" sayılır
    # (ölçüldü: GPU servisi doğrudan çağrıda 422 "kuyu_skor_esigi bir sayı olmalı (gelen: Form(None))" dönüyordu).
    kuyu_skor_esigi = kuyu_skor_esigi if isinstance(kuyu_skor_esigi, (int, float, str)) else None
    try:
        # Sınır doğrulaması İKİ DALIN DA ÖNÜNDE: uç auth-muaf ve curl ile doğrudan çağrılabilir,
        # yani arayüz doğrulaması atlanabilir (resize_max=1 görüntüyü tek piksele indirir,
        # yolo_conf=0 on binlerce sahte tespit üretir). petri_ayar ai_hub'da çünkü aynı kuralı
        # ai_service/app.py::infer_em_petri de uygular — kopyalanırsa sürüklenir.
        # ⚠️ Fonksiyon içi import: petri_cv_v2 paketini modül seviyesinde çekmek her açılışta
        # onnxruntime/ultralytics zincirini yükletirdi (bkz. _PETRI_NOT_PLATE notu).
        from ai_hub.inference_petri_dish import petri_ayar as _pa

        try:
            _ayar = _pa.coz(
                yolo_conf=yolo_conf,
                yolo_iou=yolo_iou,
                resize_max=resize_max,
                plaus_circularity=plaus_circularity,
                plaus_conf=plaus_conf,
                plaus_area_frac=plaus_area_frac,
                plaus_guard=plaus_guard,
                plate_type=plate_type,
                control_healthy=control_healthy,
                control_cancer=control_cancer,
                a1_corner=a1_corner,
                kuyu_skor_esigi=kuyu_skor_esigi,
            )
        except _pa.AyarHatasi as _ae:
            raise HTTPException(status_code=422, detail=str(_ae)) from None

        if ai_service_enabled():
            _remote = await _kapili_devret(
                "em_petri",
                file=file,
                image_base64=image_base64,
                # ⚠️ Ayarlar mikroservis dalına da GEÇER: taşınmazsa GPU dağıtımında arayüzdeki
                # ayarlar sessizce ÖLÜ kalırdı (bugün scratch scratch_yonu'nda ölçülen sınıf).
                # delegate_infer None alanları atar → gönderilmeyen alan varsayılanda kalır.
                data={
                    "petri_diameter_cm": petri_diameter_cm,
                    "achieved_B": achieved_B,
                    "duty_sum": duty_sum,
                    "yolo_conf": yolo_conf,
                    "yolo_iou": yolo_iou,
                    "resize_max": resize_max,
                    "plaus_circularity": plaus_circularity,
                    "plaus_conf": plaus_conf,
                    "plaus_area_frac": plaus_area_frac,
                    "plaus_guard": plaus_guard,
                    "plate_type": plate_type,
                    "control_healthy": control_healthy,
                    "control_cancer": control_cancer,
                    "a1_corner": a1_corner,
                    "kuyu_skor_esigi": kuyu_skor_esigi,  # T3 · Y191b (None = gönderilmez)
                    "dil": ceviri.etkin_dil(),  # I18NI-A3.3: panel görselinin dili (fantom ucuyla aynı)
                    # T3 · Y189 (None = gönderilmez; eski servis etkilenmez)
                    "kosulsuz": True if kosulsuz else None,
                },
            )
            # MİKROSERVİS YOLU: makullik reddi ai_hub boru hattında verilir (ai_service o kodu
            # aynen çalıştırır) ve JSON `error` alanıyla telden geçer. Burada da 422'ye çevrilmeli;
            # aksi halde GPU dağıtımında kullanıcı yine sessiz bir "no_detection" görürdü.
            if isinstance(_remote, dict) and _remote.get("error") == _PETRI_NOT_PLATE:
                raise HTTPException(status_code=422, detail=_petri_reject_message(_remote.get("plausibility")))
            # I18NI-A3.2 · L1-7.18 (devir yanıtı da Y51 etiketini taşır)
            return _y51_devir_etiketi("petri", _panel_adlarini_cevir(_remote, _PETRI_PANEL_ADLARI), duty_sum)
        img = await _decode_image(file, image_base64, label="em_petri")

        # Yükleyici MODÜL SEVİYESİNDE (`_yukle_em_petri_cv`): araştırma AI Pro petri sağlayıcısı
        # aynı önbelleği paylaşır → 239 MB ONNX + 90 MB YOLO iki kez yüklenmez.
        cache = await asyncio.to_thread(_get_or_load_model, "em_petri_cv", _yukle_em_petri_cv)
        # Her istekte hafif pipeline (taze intrinsics); önbellekli YOLO + predictor enjekte
        # (ağır modeller yeniden yüklenmez, yarış yok). yolo_device="cpu" ŞART.
        pl = cache["cls"](
            cache["cfg"],
            petri_diameter_cm=petri_diameter_cm,
            yolo_model_path=cache["yolo_path"],
            yolo_device="cpu",
            kosulsuz=kosulsuz,
            **_ayar,
        )
        pl.yolo = cache["yolo"]
        pl._predictor = cache["predictor"]
        # KD · Y258: veri kökünde sabit düzlem kalibrasyonu VARSA ArUco aranmaz (kare kalibrasyon kamerası / çözünürlüğünde değilse konum yok).
        pl.duzlem, pl.kamera_indeksi, pl.kamera_kimligi = (
            ai_pro_hedef.duzlem_durumu(),
            ai_pro_hedef.secili_kamera_indeksi(),
            ai_pro_hedef.secili_kamera_kimligi(),
        )

        result, ctx = await asyncio.to_thread(lambda: pl.process_image(img, achieved_B=achieved_B, duty_sum=duty_sum))

        # MAKULLİK REDDİ ≠ "tespit yok". `success=False` dalı 200 + status="no_detection" döner;
        # yanlış modülün fotoğrafı için bu SESSİZ bir başarısızlıktır (kullanıcı neden sonuç
        # alamadığını anlamaz, tekrar dener). 422 + NE yapması gerektiğini söyleyen Türkçe mesaj.
        # `_ai_fail` HTTPException'ı aynen geçirir → aşağıdaki except bunu 500'e çevirmez.
        if result.error == _PETRI_NOT_PLATE:
            raise HTTPException(status_code=422, detail=_petri_reject_message(result.plausibility))

        if result.success:
            # I18NI-A3.3: görsel metni istek dilinde (fantom ucuyla aynı).
            _dil = ceviri.etkin_dil()
            panels = await asyncio.to_thread(lambda: pl.render_panels(ctx, result, lang=_dil))
            # ⚠️ KAPAK + KALİTE (ADIM 1): mozaik 2×3'tür ve dikey telefon fotoğrafında
            # 6048×12256'ya çıkıyordu; q95 ile megabayt üretiyordu. Kapak olmadan yalnız
            # kaliteyi düşürmek YETMEZ (bağlayıcı kısıt çözünürlük).
            # ⚠️ ÇOKLU PANEL (ADIM 3): boru hattı 7 panel üretiyordu ve 6'sı AYNI SATIRDA
            # çöpe atılıyordu. Artık hepsi yayına çıkıyor; kök `image_base64` (07_combined)
            # KALIYOR → eski istemci etkilenmez (`paneller` yalnızca EK alan).
            # ⚠️ PETRİ AYRI TABLO: boru hattı aynı 7 yuvayı FARKLI anahtarlarla dolduruyor
            # (`02_yolo_dets`/`03_yolo_masks`) — fantom tablosu kullanılsaydı o paneller
            # "bilinmeyen" dalına düşer, ham anahtarla adlandırılır ve SIRALARI bozulurdu.
            _paneller = _panelleri_hazirla(panels, _kapakli_kodla, _PETRI_PANEL_ADLARI)
            # ⚠️ KÖK GÖRSEL PANELDEN: `07_combined` zaten kodlandı. İkinci kez kodlamak
            # ÖLÇÜLEN 38 ms'i (6048×12256 dikey mozaik) boşuna yakar VE iki kodlamanın ileride
            # sessizce ayrışmasına kapı açardı — kök görsel ile panel AYNI kare olmalı.
            b64_image, _boyut = _kok_gorseli_sec(_paneller, _kapakli_kodla, img)
            status = "success"
        else:
            _bayt, _boyut = _kapakli_kodla(img)  # tespit yok → orijinali dön
            b64_image = base64.b64encode(_bayt).decode('utf-8')
            _paneller = []
            status = "no_detection"

        # AI-2: kuyucuklar `to_dict()`ten (hocanın `_json_safe`'i: NaN/inf → None, numpy → Python) — v2 alanları (plaka
        # mm, Lab b*, kanser nedenleri) NaN taşıyabilir; çıplak `asdict` katı JSON'u bozardı.
        _payload = result.to_dict()
        wells = _payload["wells"]
        # Y144: tüketim kapısı BİR KEZ hesaplanır (yanıt + açıklama kararı — tek kaynak).
        _pemf = _pemf_alanlari(_payload, "petri", kosulsuz)
        # §KALAN A5: em_kedi paritesi — ilk kuyu icin hafif duyarlilik meta'si (zarif).
        _xai_meta = {}
        # ⚠️ D1.E07 (İG-5.76): PİKSEL kipinde koordinat piksel farkıdır → XAI duyarlılığı üretilmez (fantomla aynı).
        _xai_w0 = next((w for w in wells if w.get("centroid_cabin_mm")), None)  # D1.100: konumu çözülmüş ilk kuyu
        # ⚠️ AI-2 C7 (S-AI2.5): hocanın v2 / v3 kuralı — kabin konumu bilinmeyen çerçevede (`pemf_valid` false: fantom boyu /
        # halka / yerleşim ya da petri çapı / plaka çerçevesi — mm ama KABİN DEĞİL) D / P / E fiziksel olarak geçersiz. Etiketsiz
        # canlı E barı ve "dozu belirleyen" açıklaması bu konumdan KURULMAZ (D1.E07 piksel kuralıyla aynı sınıf); D / P / E yine
        # gösterilir, `pemf_kapisi` eylemiyle (C4).
        # ⚠️ Y144 (S-AII.7): `pemf_valid` YETMEZ — açıklama yalnız SÜRÜLEBİLİR sonuçta (kontrol kuyucuğu / kırpık plaka / az aday …
        # varken "dozu belirleyen" satırı üretilmez). Ölçüt TEK KAYNAK `pemf_kapisi.surulebilir`.
        if (
            result.success
            and _xai_w0 is not None
            and result.method != "pixel"
            and _pemf["pemf_kapisi"].get("surulebilir") is True
        ):
            try:
                from ai_hub.inference_em_petri import inference_em_petri as _iep

                _w0 = _xai_w0
                _c = list(_w0["centroid_cabin_mm"])
                _xai_meta["xaiSensitivity"] = await asyncio.to_thread(
                    _iep.xai_hizli_sensitivity,
                    cache["predictor"],
                    _c[0],
                    _c[1],
                    _c[2],
                    _w0.get("organ_id", 1),
                    achieved_B if achieved_B is not None else float(cache["cfg"].phantom.achieved_B),
                    duty_sum if duty_sum is not None else float(cache["cfg"].phantom.duty_sum),
                )
            except Exception as xe:
                logger.warning("em_petri XAI meta üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                _xai_meta["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")  # D5.05 (B-5.15)
        return {
            "status": status,
            "image_base64": b64_image,
            # ⚠️ KODLANAN karenin boyutu (ADIM 2): istemcinin oran kilidi bunu okur.
            # `_kapakli_kodla` kareyi KÜÇÜLTEBİLDİĞİ için orijinal boyut YANLIŞ olurdu →
            # kutu oranı kayar, üzerine çizilen işaretler canlı görüntüyle uyuşmaz.
            **_boyut,
            "paneller": _paneller,
            "success": result.success,
            "error": result.error,
            "n_wells": result.n_wells,
            "n_cancer": result.n_cancer,
            "n_healthy": result.n_healthy,
            "method": result.method,
            "mm_per_px": round(result.mm_per_px, 4),
            "wells": wells,
            "timing_ms": result.timing_ms,
            # ETKİN ayarlar (istek DEĞİL, boru hattının gerçekten kullandığı): arayüz sonucun
            # hangi eşiklerle üretildiğini gösterir, gevşetilmiş bir koşu "normal" görünmesin.
            "yolo_ayar": result.yolo_ayar,
            "resize": result.resize,
            "plausibility": _payload.get("plausibility") or {},
            **_xai_meta,
            **_y51_duty_etiketi("petri", duty_sum, cache["cfg"]),  # i-15.1 · Y51
            # AI-2 (hoca petri v2): `pemf_valid`, `coord_frame`, `warnings`, plaka ızgarası özeti (ONNX aday sayısı dahil),
            # sınıflama / kontrol QC + tüketim kapısının eylem metinleri (`pemf_kapisi`). YALNIZ EK. Tek kaynak: ai_hub.
            **_pemf,
        }
    except Exception as e:
        # D1.E07 (İG-5.80): sonlu olmayan girdi / bozuk ölçekleyici → 422 (fantomla aynı sözleşme).
        from ai_hub.em_girdi import SonluOlmayanGirdi as _SonluDegil

        if isinstance(e, _SonluDegil):
            logger.warning("em_petri: geçersiz girdi reddedildi: %s", e)
            raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.petriAnalizi", e=e)) from None
        logger.error(f"em_petri inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.petriAnaliz", dil=d), e)


@ai_router.post("/api/ai/rna/kidney")
async def analyze_kidney_rna(
    file: UploadFile = File(None),
    csv_base64: str = Form(None),
    explain: bool = Form(False),
    _res=Depends(require_research),
):
    """Böbrek RNA-seq → KIRC sınıflandırma (MLP-medium ONNX).

    Girdi: CSV — satır=hasta, sütun=20531 gen (eğitim/TCGA sırasında), 1. sütun hasta ID.
    log2(x+1) → StandardScaler → SelectKBest top-1000 → MLP → KIRC/other + güven.
    Foto DEĞİL — bir sekans laboratuvarı çıktısı. Tümü <5MB → model EXE'ye gömülü.
    """
    try:
        if ai_service_enabled():
            return await delegate_infer(
                "rna",
                file=file,
                csv_base64=csv_base64,
                data=({"explain": "true"} if explain else None),
            )
        if csv_base64:
            content = base64.b64decode(csv_base64)
        elif file:
            # Audit P2: sınırsız file.read() → GB dosya OOM/temp-disk dolumu (Starlette max_part_size
            # yalnız non-file form alanlarını sınırlar; file part sınır-kontrolsüz spool edilir). RNA CSV ~60MB.
            content = await file.read(60 * 1024 * 1024 + 1)
            if len(content) > 60 * 1024 * 1024:
                raise ValueError("CSV çok büyük (> 60 MB sınırı).")
        else:
            raise ValueError("CSV verisi bulunamadı.")

        import io as _io

        import pandas as _pd

        # event-loop-blok fix: 50MB'a kadar CSV × 20531 sütun pandas parse'ı CPU-yoğun → thread'e offload.
        def _parse_csv():
            return _pd.read_csv(_io.BytesIO(content), index_col=0)

        try:
            df = await asyncio.to_thread(_parse_csv)
        except Exception as pe:
            raise ValueError(f"CSV okunamadı ({pe}). Beklenen: satır=hasta, sütun=gen, 1. sütun hasta ID.")
        if df.shape[0] == 0:
            raise ValueError("CSV boş — hasta satırı yok.")

        def _load_kidney_rna():
            from ai_hub.inference_human_kidney_rna import KidneyRnaPredictor

            return KidneyRnaPredictor()

        predictor = await asyncio.to_thread(_get_or_load_model, "kidney_rna", _load_kidney_rna)

        if predictor.expected_cols and df.shape[1] != predictor.expected_cols:
            raise HTTPException(
                status_code=400,
                detail=(ceviri.t("ai.hata.genSutunSayisi", beklenen=predictor.expected_cols, gelen=df.shape[1])),
            )

        predictions = await asyncio.to_thread(lambda: predictor.predict(df))
        yanit = {
            "status": "success",
            "n_patients": len(predictions),
            "classes": predictor.classes,
            "predictions": predictions,
        }
        # Sunum-katmanı XAI (Faz 2 kuyruğu): hasta başına IG top-gen katkıları.
        # ⚠️ IG maliyeti N ile lineer → N>25'te ÜRETİLMEZ (60MB CSV'de patlama); analiz
        # yine döner. Açıklama İKİNCİL: hatası analizi düşürmez.
        if explain:
            if len(df) > 25:
                yanit["xai_error"] = ceviri.t("ai.hata.xaiEnFazla25")
            else:
                try:
                    from ai_hub.inference_human_kidney_rna import inference_human_kidney_rna as _ihr

                    yanit["xai"] = await asyncio.to_thread(_ihr.xai_top_genler, df)
                except Exception as xe:
                    logger.warning("RNA XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                    yanit["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        return yanit
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"kidney_rna inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.rnaAnaliz", dil=d), e)


class KidneyDiseaseInput(BaseModel):
    # 14 sayısal klinik değer (eksik → None → preprocessor impute eder)
    age: float | None = None
    bp: float | None = None
    sg: float | None = None
    al: float | None = None
    su: float | None = None
    bgr: float | None = None
    bu: float | None = None
    sc: float | None = None
    sod: float | None = None
    pot: float | None = None
    hemo: float | None = None
    pcv: float | None = None
    wc: float | None = None
    rc: float | None = None
    # 10 kategorik (rbc/pc: normal/abnormal · pcc/ba: present/notpresent ·
    # htn/dm/cad/pe/ane: yes/no · appet: good/poor)
    rbc: str | None = None
    pc: str | None = None
    pcc: str | None = None
    ba: str | None = None
    htn: str | None = None
    dm: str | None = None
    cad: str | None = None
    appet: str | None = None
    pe: str | None = None
    ane: str | None = None
    # Sunum-katmanı XAI (2026-08-26): true → yanıta SHAP top-özellik katkıları ("xai").
    # ⚠️ Uçta features'tan POP edilir — alan sayımına (total_fields=24) SIZMAMALI.
    explain: bool = False


# ⚠️ CKD ASGARİ GİRDİ KURALI `utils/klinik_asgari.py`ye TAŞINDI (denetim 2026-08-17): sabitler
# (`CKD_MIN_ALAN`, `CKD_CEKIRDEK`, `CKD_ETIKET`) ve kapı gövdesi artık orada, çünkü `:8100`
# transportu da AYNI nesneyi çağırmak zorunda. Burada İKİNCİ bir kopya BIRAKILMADI — iki kaynak
# kalırsa biri sessizce kayar (bu bulgunun kök nedeni tam olarak iki transportun ayrışmasıydı).


@ai_router.post("/api/ai/disease/kidney")
async def analyze_kidney_disease(data: KidneyDiseaseInput, _res=Depends(require_research)):
    """İnsan Kronik Böbrek Hastalığı (UCI-CKD) sınıflandırma (ExtraTrees ONNX).

    24 klinik özellik (14 sayısal + 10 kategorik; eksikler impute) → preprocessor →
    ONNX → {prob_ckd, label(ckd/notckd)}. `/api/ai/disease` prefix'iyle auth-muaf.
    Model EXE'ye gömülü (<5MB); CPU. Foto/CSV DEĞİL — form girişi.

    ⚠️ ASGARİ GİRDİ ZORUNLU (2026-08-07): boş/yetersiz istek 422 ile reddedilir;
    bkz. `utils.klinik_asgari.CKD_MIN_ALAN`.
    """
    features = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    # XAI bayrağını klinik alanlardan AYIR (total_fields=24 şeffaflık sözleşmesi bozulmasın).
    explain = bool(features.pop("explain", False))
    try:
        dolu = _ckd_kapisi(features)
    except _AsgariGirdiYok as ag:
        raise HTTPException(status_code=422, detail=ai_kapi_metni.asgari_metni(ag)) from None
    try:
        if ai_service_enabled():
            return await delegate_json("kidney_disease", {**features, "explain": explain})
        from ai_hub.inference_human_kidney_disease import predict_one

        result = await asyncio.to_thread(lambda: predict_one(features))
        yanit = {
            "status": "success",
            "prob_ckd": result["prob_ckd"],
            "prob_pct": round(result["prob_ckd"] * 100, 1),
            "label": result["label"],
            "model": result.get("model"),
            # ŞEFFAFLIK: kaç alanın impute edildiğini klinisyen GÖRMELİ — 6/24 alanla üretilen
            # tahminle 22/24 alanla üretilen aynı güvenle sunulmamalı.
            "filled_fields": len(dolu),
            "total_fields": len(features),
            "imputed_fields": len(features) - len(dolu),
            "low_evidence": len(dolu) < 12,
        }
        # Sunum-katmanı XAI (2026-08-26): SHAP KernelExplainer over ONNX ('ortalama-hasta'
        # referansıyla — tek-hasta dejenerasyonu yok). ⚠️ Açıklama İKİNCİL: hatası ana
        # analizi ASLA düşürmez (zarif düşüş).
        if explain:
            try:
                from ai_hub import inference_human_kidney_disease as _ihd

                yanit["xai"] = await asyncio.to_thread(_ihd.xai_top_features, features)
            except Exception as xe:
                logger.warning("CKD XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                yanit["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        return yanit
    except Exception as e:
        logger.error(f"kidney_disease inference error: {e}", exc_info=True)
        # B5 (2026-09-03): 500 yolu — mesaj EYLEME dönük olsun (ham "analiz hatası" operatörü
        # kör bırakıyordu). `_ai_fail` exc_info'yu zaten loglar; Türkçe olduğu için aiDetayCumlesi aynen gösterir.
        raise _ai_fail(lambda d: ceviri.t("ai.hata.bobrekHastalik", dil=d), e)


@ai_router.post("/api/ai/sound/cat")
async def analyze_cat_sound(
    file: UploadFile = File(None),
    audio_base64: str = Form(None),
    explain: bool = Form(False),
    xai_method: str = Form("gradcam"),  # AI1.X7: Grad-CAM++ bazı örneklerde BOŞ harita (ölçüldü 2/23)
):
    """Kedi Sesi Sınıflandırma (EfficientNet_Lite0 mel-spektrogram ONNX).

    Ses (mp3/wav/m4a/…) → ffmpeg 22050Hz mono WAV → librosa mel-spektrogram (mel+delta+
    delta²) → EfficientNet_Lite0 ONNX → 10 sınıf (Angry..Warning) + top-3. Foto/CSV/form
    DEĞİL — SES. `/api/ai/sound` prefix'iyle auth-muaf.
    """
    if xai_method not in ("gradcam++", "gradcam", "eigencam", "hirescam"):
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.xaiYontemi", xai_method=xai_method))
    import tempfile

    tmp_in = None
    tmp_wav = None
    try:
        if audio_base64:
            content = base64.b64decode(audio_base64)
        elif file:
            # Audit P2: sınırsız file.read() → GB ses OOM/temp-disk dolumu; ffmpeg tüm girdiyi transcode
            # eder. Ses üst-sınırı ~25MB.
            content = await file.read(25 * 1024 * 1024 + 1)
            if len(content) > 25 * 1024 * 1024:
                raise ValueError("Ses dosyası çok büyük (> 25 MB sınırı).")
        else:
            raise ValueError("Ses verisi bulunamadı.")
        if len(content) < 200:
            raise ValueError(f"Ses verisi boş/çok küçük ({len(content)} bytes).")

        def _load_cat_sound():
            try:
                onnx = download_model_sync("ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx")
            except ModelButunlukHatasi:  # D3I-A2.4 · Y18: bütünlük reddi YUTULMAZ → 503 + açık uyarı
                raise
            except Exception as _de:
                logger.warning("cat_sound ONNX indirme/çözümleme uyarısı: %s", _de)
                onnx = os.path.join(project_root, "ai_hub", "inference_cat_sound", "EfficientNet_Lite0.onnx")
            from ai_hub.inference_cat_sound import CatSoundClassifier

            # device="cpu" ŞART (headless); runtime onnx (torch YOK).
            return CatSoundClassifier(model_path=onnx, runtime="onnx", device="cpu")

        # ⚠️ MODEL YUKLEMESI KAPIDAN SONRAYA ALINDI (2026-08-16, CI kirmizisi).
        # Eskiden model burada yukleniyordu; sessizlik kapisi ise ffmpeg'den SONRA calisiyordu.
        # Iki sorunu vardi: (a) sessiz bir kaydi REDDETMEK icin 15 MB'lik ONNX bosuna yukleniyordu,
        # (b) modelin bulunmadigi ortamda (CI, model indirilmemis kurulum) istek kapiya HIC
        # varamadan 500 "Ses analiz hatasi" ile dusuyordu -> kullanici sessiz kayit yaptiginda
        # sebebini ogrenemiyordu. Sinyal seviyesi modelden BAGIMSIZ olcculur; once o.
        # Ham sesi temp'e yaz → ffmpeg ile 22050Hz mono WAV'a çevir (herhangi format:
        # mp3/wav/m4a/aac/ogg... — kayıt Android m4a olabilir; librosa/soundfile m4a decode
        # etmez, ffmpeg üniversal). Sonra classifier librosa ile WAV'ı işler.
        tf = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
        tf.write(content)
        tf.close()
        tmp_in = tf.name
        tmp_wav = tmp_in + ".wav"
        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        # Audit P2: ffmpeg sertleştir — -protocol_whitelist file (HLS/concat SSRF engelle), -nostdin,
        # -t 30 (girdi okuma süresi cap), -fs (çıktı WAV boyut cap) → uzun/kötücül medya disk-dolumu+SSRF keser.
        proc = await asyncio.to_thread(
            lambda: __import__('utils.gizli_surec', fromlist=['calistir']).calistir(
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
        )
        if proc.returncode != 0 or not os.path.exists(tmp_wav):
            raise ValueError("Ses çözümlenemedi (desteklenmeyen format?).")

        # ⚠️ SESSİZLİK KAPISI (saha bildirimi 2026-08-15): modelin 10 sınıfının HEPSİ kedi
        # duygusu; "kedi değil" sınıfı YOK → softmax sessizliğe bile mutlaka bir duygu atar.
        # Sahip boş bir kayıt analiz edince "Resting" sonucu alıyordu (ölçüldü: %16,7 — şans
        # %10, yani model aslında hiçbir şey söylemiyor). Sessiz kaydı ANALİZ ETME.
        # Eşik gerçek kayıtlarla kalibre edildi (utils/ses_kalitesi başlığındaki tablo).
        try:
            _rms = await asyncio.to_thread(ses_wav_rms_dbfs, tmp_wav)
        except Exception as _se:  # ölçüm başarısızsa kapıyı ZORLAMA (analiz engellenmesin)
            logger.warning("cat_sound RMS ölçülemedi, sessizlik kapısı atlandı: %s", _se)
            _rms = None
        if _rms is not None and ses_sessiz_mi(_rms):
            # ⚠️ `ValueError` DEĞİL, `HTTPException(422)`: `_ai_fail` ham hataları bilerek
            # yutup istemciye yalnız "Ses analiz hatası" döndürür (bilgi ifşası koruması) —
            # kullanıcı NEDENİNİ öğrenemezdi. `_ai_fail` HTTPException'ı AYNEN geçirir; bu,
            # görüntü uçlarında zaten kurulmuş kalıp (bkz. `_decode_image` / petri reddi).
            raise HTTPException(
                status_code=422,
                detail=(ceviri.t("ai.hata.sesSessiz")),
            )

        # ⚠️ KAPI-SONRA-DEVRET — görüntü uçlarındaki `_kapili_devret` ile AYNI düzen.
        # Bu satırlar ESKİDEN fonksiyonun İLK satırıydı; `PEMF_AI_SERVICE_URL` tanımlıyken sessizlik
        # kapısına HİÇ varılmıyordu → sessiz/boş bir kayıt için :8100'den gelen "duygu" sonucu aynen
        # istemciye dönüyordu (kapının var olma sebebi olan 2026-08-15 saha vakası).
        # Kapı ZORUNLU olarak transcode'dan sonra: `utils/ses_kalitesi.wav_rms_dbfs` WAV'ı `wave`
        # ile okur, mp3/m4a'da RIFF hatası verir. Bu yüzden devretme de kapıdan SONRA olmak zorunda.
        # ⚠️ `file` tükendi (yukarıda okundu) → baytlar ELDE, base64 ile geçilir; `file=file`
        # bırakmak BOŞ gövde gönderirdi (bu yamanın en olası hatası, testle kilitli).
        # ÖLÇÜLDÜ: ffmpeg 27-31 ms + RMS 2-9 ms. WAV göndermek 2. transcode'dan ~0-3 ms kazandırır
        # ama yükü ~3,5× şişirir → HAM bayt gönderilir, tel formatı DEĞİŞMEZ.
        if ai_service_enabled():
            return await delegate_infer(
                "sound",
                audio_base64=base64.b64encode(content).decode("ascii"),
                data=({"explain": "true", "xai_method": xai_method} if explain else None),
            )

        # Kayit analiz edilebilir -> ANCAK SIMDI modeli yukle.
        clf = await asyncio.to_thread(_get_or_load_model, "cat_sound", _load_cat_sound)
        result = await asyncio.to_thread(lambda: clf.predict(tmp_wav, top_k=3))
        # Sunum-katmanı XAI (Faz 2, 2026-08-26): mel üzerinde Grad-CAM — SESSİZLİK KAPISININ
        # ARKASINDA (yukarıda 422 kesti; sessiz kayda duygu ısı-haritası ÜRETİLMEZ, saha
        # 2026-08-15). ⚠️ tmp_wav finally'de siliniyor → XAI burada, silinmeden. Açıklama
        # İKİNCİL: hatası analizi düşürmez.
        _xai_alanlari = {}
        if explain:
            try:
                from ai_hub.inference_cat_sound import inference_cat_sound as _ics

                _x = await asyncio.to_thread(_ics.xai_ses_isi_haritasi, tmp_wav, None, xai_method)
                _xai_alanlari["xai_image_base64"] = _x["xai_image_base64"]
                _xai_alanlari["xai_method"] = _x.get("method")
            except Exception as xe:
                logger.warning("Ses XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                _xai_alanlari["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        # BELİRSİZLİK sonuçla BİRLİKTE taşınır: istemci düşük güvende sonucu kesin bir bulgu
        # gibi sunmaz. ⚠️ `guvenilir=False` "kedi sesi yok" DEMEK DEĞİLDİR — bu model bunu
        # söyleyemez; aralıklar örtüşüyor (gerçek ağrı kaydı 0,563 · oda gürültüsü 0,595).
        # Bu yüzden düşük güven REDDEDİLMEZ, yalnız işaretlenir (sahip kararı 2026-08-15).
        _probs = list((result.get("probabilities") or {}).values())
        _entropi = ses_normalize_entropi(_probs)
        return {
            "status": "success",
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result["probabilities"],
            "guvenilir": ses_guvenilir_mi(_probs),
            "belirsizlik": round(_entropi, 3),
            # ⚠️ `-inf`/`nan` JSON'a yazılamaz (`round` onları AYNEN geçirir) → yanıt 500'e
            # düşerdi. `-inf` sessizlik kapısında zaten elenir ama `nan` eşik karşılaştırmasını
            # False geçer; burada sonluluk kontrolü son savunmadır.
            "rms_dbfs": None if _rms is None or not _math.isfinite(_rms) else round(_rms, 1),
            **_xai_alanlari,
        }
    except Exception as e:
        logger.error(f"cat_sound inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.sesAnaliz", dil=d), e)
    finally:
        for _p in (tmp_in, tmp_wav):
            if _p and os.path.exists(_p):
                try:
                    os.unlink(_p)
                except Exception:
                    pass


@ai_router.post("/api/ai/vision/kidney_ct")
async def analyze_kidney_ct(
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    explain: bool = Form(False),
    _res=Depends(require_research),
):
    """Böbrek CT Tespit (YOLOv8s ONNX, 3 sınıf: Kidney Stone / Kidney / Kidney Cyst).

    CT görüntüsü → YOLO detect → annotated görsel + tespit sayıları. `/vision/` auth-muaf.
    """
    try:
        if ai_service_enabled():
            return await _kapili_devret(
                "kidney_ct",
                file=file,
                image_base64=image_base64,
                data=({"explain": "true"} if explain else None),
            )
        img = await _decode_image(file, image_base64, label="kidney_ct")

        def _load_kidney_ct():
            try:
                onnx = download_model_sync("ai_hub/inference_human_kidney_ct/yolov8s.onnx")
            except ModelButunlukHatasi:  # D3I-A2.4 · Y18: bütünlük reddi YUTULMAZ → 503 + açık uyarı
                raise
            except Exception as _de:
                logger.warning("kidney_ct ONNX indirme/çözümleme uyarısı: %s", _de)
                onnx = os.path.join(project_root, "ai_hub", "inference_human_kidney_ct", "yolov8s.onnx")
            from ai_hub.inference_human_kidney_ct import KidneyCTDetector

            return KidneyCTDetector(model_path=onnx, backend="onnx", device="cpu")

        det = await asyncio.to_thread(_get_or_load_model, "kidney_ct", _load_kidney_ct)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)
        _xai_alanlari = {}
        try:
            result = await asyncio.to_thread(lambda: det.predict(tmp.name))
            overlay = await asyncio.to_thread(lambda: det.draw_overlay(tmp.name, result))
            # Sunum-katmanı XAI (Faz 2 kuyruğu; Faz-0 karar #4 AGPL onaylı; AI1.X3): tespit hedefli HiRes-CAM.
            # tmp bu blokta silinir → XAI silinmeden. Açıklama İKİNCİL (zarif düşüş).
            if explain:
                try:
                    from ai_hub.inference_human_kidney_ct import inference_human_kidney_ct as _ikt

                    _x = await asyncio.to_thread(_ikt.xai_ct_isi_haritasi, tmp.name)
                    _xai_alanlari["xai_image_base64"] = _x["xai_image_base64"]
                    _xai_alanlari["xai_method"] = _x.get("method")
                except Exception as xe:
                    logger.warning("CT XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                    _xai_alanlari["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        b64_image = _encode_jpg_b64(overlay, quality=GOSTERIM_JPEG_KALITESI)
        return {
            "status": "success",
            "image_base64": b64_image,
            **_kare_boyutu(overlay),
            "n_detections": result["n_detections"],
            "class_counts": result["class_counts"],
            "detections": result["detections"],
            **_xai_alanlari,
        }
    except Exception as e:
        logger.error(f"kidney_ct inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.bobrekCt", dil=d), e)


@ai_router.post("/api/ai/vision/histopath")
async def analyze_histopath(
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    explain: bool = Form(False),
    _res=Depends(require_research),
):
    """Böbrek Histopatoloji Grade (V22-KMC-ClassicTrio ONNX, 5 sınıf grade0-4).

    Histoloji doku görüntüsü → 3-backbone ensemble → grade + olasılıklar (sınıflandırıcı,
    detektör değil → overlay yok). `/vision/` auth-muaf.
    """
    try:
        if ai_service_enabled():
            return await _kapili_devret(
                "histopath",
                file=file,
                image_base64=image_base64,
                data=({"explain": "true"} if explain else None),
            )
        img = await _decode_image(file, image_base64, label="histopath")

        def _load_histopath():
            try:
                onnx = download_model_sync("ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx")
            except ModelButunlukHatasi:  # D3I-A2.4 · Y18: bütünlük reddi YUTULMAZ → 503 + açık uyarı
                raise
            except Exception as _de:
                logger.warning("histopath ONNX indirme/çözümleme uyarısı: %s", _de)
                onnx = os.path.join(
                    project_root, "ai_hub", "inference_renal_histopath_kmc", "v22_kmc_classictrio_kmc.onnx"
                )
            from ai_hub.inference_renal_histopath_kmc import RenalHistopathClassifier

            return RenalHistopathClassifier(model_path=onnx, backend="onnx", device="cpu")

        clf = await asyncio.to_thread(_get_or_load_model, "histopath", _load_histopath)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)
        _xai_alanlari = {}
        try:
            result = await asyncio.to_thread(lambda: clf.predict(tmp.name, top_k=5))
            # Sunum-katmanı XAI (Faz 4): ensemble HiRes-CAM + DISAGREEMENT haritası.
            # tmp bu blokta silinir → XAI silinmeden. Açıklama İKİNCİL (zarif düşüş).
            # ⚠️ CPU'da 3-backbone backward dakikaya uzayabilir → to_thread + modül kilidi.
            if explain:
                try:
                    from ai_hub.inference_renal_histopath_kmc import inference_renal_histopath_kmc as _irh

                    _x = await asyncio.to_thread(_irh.xai_histopat_isi_haritasi, tmp.name)
                    _xai_alanlari["xai_image_base64"] = _x["xai_image_base64"]
                    _xai_alanlari["xai_disagreement_base64"] = _x["xai_disagreement_base64"]
                    # D6.64: kararsızlığın MUTLAK ölçüsü (0 = üç model aynı, 1 = kuramsal en büyük ayrışma)
                    _xai_alanlari["xai_disagreement_max"] = _x.get("xai_disagreement_max")
                    _xai_alanlari["xai_method"] = _x.get("method")
                except Exception as xe:
                    logger.warning("Histopat XAI üretilemedi (analiz etkilenmedi): %s", xe, exc_info=True)
                    _xai_alanlari["xai_error"] = ceviri.t("ai.sonuc.aciklamaUretilemedi")
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        return {
            "status": "success",
            "top_1_class": result["top_1_class"],
            "top_1_prob": result["top_1_prob"],
            "top_k": result["top_k"],
            "probabilities": result["probabilities"],
            **_xai_alanlari,
        }
    except Exception as e:
        logger.error(f"histopath inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.histopatoloji", dil=d), e)


@ai_router.post("/api/ai/vision/scratch")
async def analyze_scratch(
    file: UploadFile = File(None),
    image_base64: str = Form(None),
    scratch_yonu: str = Form("dikey"),
    pixel_mm: float = Form(0.0016),
    explain: bool = Form(False),
    xai_method: str = Form("hirescam"),  # AI1.X5: tespit hedefli (eski hedefte gradcam/gradcam++ BOŞ harita)
    _res=Depends(require_research),
):
    """Yara Kapanma (Scratch) — CPN hücre segmentasyonu + wound-closure metrikleri.

    TEK girdi → ÇOKLU görsel çıktı (seg/overlay/analysis/closure + opsiyonel XAI),
    bellek-içi base64 (plan: docs/scratch-entegrasyon-plani.md v3). Karar 0.6: ağır
    araştırma = 3 jeton (jeton.py::_AGIR_UCLAR). TD11 (Y150): mikroskopi makullik kapısı
    (`image_domain.scratch_analizi`; eski karar 0.3 "kapı YOK" kalktı) — mikroskopi olmayan görüntü
    422 + eylem metni, jeton düşmez; hücre bulunamayan görüntü `uyari` ile döner. Karar 0.5: explain
    EK jeton değil.
    `/vision/` auth-muaf.
    """
    from ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca import (
        GECERLI_SCRATCH_YONLERI,
        GECERLI_XAI_YONTEMLERI,
    )

    if scratch_yonu not in GECERLI_SCRATCH_YONLERI:
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.scratchYonu"))
    if xai_method not in GECERLI_XAI_YONTEMLERI:
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.xaiYontemi", xai_method=xai_method))
    if not (0.00001 <= pixel_mm <= 0.01):
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.pixelMm"))
    try:
        if ai_service_enabled():
            # Delegate STRING'lerle gider (ai_client str() yapar; ai_service Form parse eder)
            data = {"scratch_yonu": scratch_yonu, "pixel_mm": str(pixel_mm), "xai_method": xai_method}
            if explain:
                data["explain"] = "true"
            try:
                return await _kapili_devret("scratch", file=file, image_base64=image_base64, data=data)
            except Exception as devir_hatasi:
                # DÜŞMAN-DOĞRULAMA (deneysel kanıtlı): :8100'ün 503/429/422'si
                # raise_for_status ile HTTPStatusError'a dönüyor ve _ai_fail bunu
                # jenerik 500 yapıyordu — zarif sözleşme birincil (mikroservis)
                # modda kayboluyordu. Alt-servis durum kodları AYNEN geçirilir.
                import httpx

                if isinstance(devir_hatasi, httpx.HTTPStatusError):
                    kod = devir_hatasi.response.status_code
                    if kod == 503:
                        raise HTTPException(
                            status_code=503, detail=ceviri.t("ai.hata.scratchKurulum")
                        ) from devir_hatasi
                    if kod == 429:
                        raise HTTPException(status_code=429, detail=ceviri.t("ai.hata.scratchMesgul")) from devir_hatasi
                    if kod == 422:
                        try:
                            detay = devir_hatasi.response.json().get("error") or ceviri.t("ai.hata.gecersizParametre")
                        except Exception:
                            detay = ceviri.t("ai.hata.gecersizParametre")
                        raise HTTPException(status_code=422, detail=detay) from devir_hatasi
                raise

        # Gömülü yol (karar 0.1: celldetection frozen'da). Girdi 25MB/50MP kapısından
        # geçer; analize KAYIPSIZ PNG tmp ile gider — ölçüm görüntüsü (µm/mm²)
        # JPEG'e SIKIŞTIRILMAZ. TD11: scratch mikroskopi kapısı `_decode_image` → `image_domain.check` içinde (422, jeton düşmez).
        img = await _decode_image(file, image_base64, label="scratch")

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)
        try:
            from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as _ipd

            try:
                sonuc = await asyncio.to_thread(
                    _ipd.scratch_analiz,
                    tmp.name,
                    scratch_yonu=scratch_yonu,
                    pixel_mm=pixel_mm,
                    explain=explain,
                    xai_method=xai_method,
                )
            except _ipd.ScratchMesgul as mesgul:
                # Kilit KISA timeout'la denenir (modül) — thread'ler dakikalarca
                # executor işgal etmez; istemciye dürüst 429.
                raise HTTPException(status_code=429, detail=ceviri.t("ai.hata.scratchMesgul")) from mesgul
            except _ipd.ModelKurulumEksik as kurulum_hatasi:
                # DAR eşleme (düşman-doğrulama: genel RuntimeError CUDA-OOM'u da
                # 'model paketi gerekli' sanıyordu) — yalnız gerçek kurulum eksiği 503.
                # ⚠️ SAHA DERSİ (2026-08-27): bu blok hatayı SESSİZCE yutuyordu. Kullanıcı
                # "model paketi gerekli" görüyordu ama model paketi KURULUYDU; gerçek sebep
                # (bağımlılık import'u) hiçbir yere yazılmadığı için sahada teşhis İMKANSIZDI.
                # Artık kök neden zinciriyle loglanır (kullanıcı mesajı sade kalır).
                logger.error(
                    "SCRATCH KURULUM EKSİĞİ → 503. Kök neden: %s",
                    _kok_neden_zinciri(kurulum_hatasi),
                    exc_info=True,
                )
                raise HTTPException(status_code=503, detail=ceviri.t("ai.hata.scratchKurulum")) from kurulum_hatasi
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        return {"status": "success", **sonuc}
    except Exception as e:
        raise _ai_fail(lambda d: ceviri.t("ai.hata.yaraKapanma", dil=d), e)


#: SG.G5: GPU servisinin `/infer/cat_organ`ına AI Hub'ın gönderdiği İSTEK form alanı (yanıt alanı değil) — "bulunamadı"yı bilgi
#: olarak ister; AI Pro GPU kolu göndermez (onun "kedi yok" anlamı değişmez).
_KEDI_ORGAN_AI_HUB_FORMU = {"bulunamadi_bilgi": "1"}


def _kedi_organ_bulunamadi_yaniti(img, neden: str) -> dict:
    """SG.G5: kedi organ "bulunamadı" BİLGİ yanıtı — başarılı, boş organ listesi, nedeni ve eylemi söyleyen metin (tek kaynak
    `catorgan_predictor.BULUNAMADI_METNI`); gösterim karesi girdinin kendisi (organ işareti YOK). GPU servisi aynı alanları döner."""
    from ai_hub.inference_cat_organ.catorgan_predictor import BULUNAMADI_METNI

    oh, ow = img.shape[:2]
    scale = min(1.0, 1280.0 / max(oh, ow))
    gosterim = cv2.resize(img, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA) if scale < 1.0 else img
    return {
        "status": "success",
        "image_base64": _encode_jpg_b64(gosterim, quality=GOSTERIM_JPEG_KALITESI),
        **_kare_boyutu(gosterim),
        "n_organs": 0,
        "organs": [],
        "detected": False,
        "bulunamadi": neden,
        "bulunamadi_mesaji": BULUNAMADI_METNI[neden],
        "pose_type": None,
        "pnp_residual_px": None,
        "pnp_scale_px_per_cm": None,
        "mirror_warning": False,
        "anatomic_consistency": None,
        "kabin_uyarisi": None,
    }


@ai_router.post("/api/ai/vision/cat_organ")
@sonuc_izle  # TD9: "kedi / organ bulunamadı" ücretsiz
async def analyze_cat_organ(file: UploadFile = File(None), image_base64: str = Form(None)):
    """Kedi Organ 3B Lokalizasyon (YOLOv8m-seg + SuperAnimal FasterRCNN + RTMPose ONNX).

    Kedi görüntüsü → 10 organ 3B konumu (cm) + organ overlay. Sınıflandırıcı/detektör
    değil, lokalizasyon pipeline'ı. `/vision/` auth-muaf.
    """
    try:
        if ai_service_enabled():
            # SG.G5: AI Hub "bulunamadı"yı bilgi olarak ister (servis bu alan olmadan AI Pro'nun eski davranışını korur).
            return await _kapili_devret(
                "cat_organ", file=file, image_base64=image_base64, data=_KEDI_ORGAN_AI_HUB_FORMU
            )
        img = await _decode_image(file, image_base64, label="cat_organ")

        def _load_cat_organ():
            from ai_hub.inference_cat_organ.catorgan_predictor import CatOrganPredictor

            return CatOrganPredictor(device="cpu")

        clf = await asyncio.to_thread(_get_or_load_model, "cat_organ", _load_cat_organ)

        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        _gecici_gorsel_yaz(tmp.name, img)
        try:
            result = await asyncio.to_thread(lambda: clf.predict(tmp.name, render=True))
        except Exception as e:
            # SG.G5: "kedi / organ bulunamadı" BİLGİDİR (FGS / segmentasyon sözleşmesi) — 500 değil, boş organ listeli yanıt.
            from ai_hub.inference_cat_organ.catorgan_predictor import bulunamadi_nedeni

            if bulunamadi_nedeni(e) is None:
                raise
            return _kedi_organ_bulunamadi_yaniti(img, bulunamadi_nedeni(e))
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        overlay = result.get("_overlay_bgr")
        image_b64 = None
        # ⚠️ ÖNCEDEN TANIMLI: overlay yoksa yanıt boyut alanı TAŞIMAZ (uydurma 0×0 DEĞİL).
        # İstemci sözleşmesi "alan yoksa oran kilidi kapalı" — 0 göndermek kutuyu bozar.
        _cat_boyut: dict = {}
        if overlay is not None:
            # Overlay orijinal çözünürlükte (ör. 4032px) → mobil için max 1280px'e küçült
            oh, ow = overlay.shape[:2]
            scale = min(1.0, 1280.0 / max(oh, ow))
            if scale < 1.0:
                overlay = cv2.resize(overlay, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode('.jpg', overlay, [cv2.IMWRITE_JPEG_QUALITY, GOSTERIM_JPEG_KALITESI])
            image_b64 = base64.b64encode(buf).decode('utf-8')
            _cat_boyut = _kare_boyutu(overlay)

        organs_dict = result.get("organs") or {}
        organs_list = [
            {
                "id": int(oid),
                "name": o.get("name"),
                "coord_3d_cm": o.get("coord_3d_cm"),
                "coord_cabin_cm": o.get("coord_cabin_cm"),
                "reliability": o.get("reliability"),
                # Sunum-katmanı XAI (2026-08-26): güvenin bileşen dökümü (pipeline zaten
                # hesaplıyordu, atılıyordu) — UI "neden düşük güven" gösterebilsin.
                "reliability_components": o.get("reliability_components"),
                # #49: kalibrasyon durumunu İLET → istemci/UI ölçülmüş (ArUco kalibreli) vs kanonik
                # şablon koordinatını ayırt edebilsin (aksi halde şablonu ölçülmüş sanabilir).
                "calibrated": o.get("calibrated"),
            }
            for oid, o in sorted(organs_dict.items(), key=lambda kv: int(kv[0]))
        ]

        return {
            "status": "success",
            "image_base64": image_b64,
            # ⚠️ ORAN KİLİDİ (ADIM 2): bu uç görsel döndürüyor ama boyutu HİÇ bildirmiyordu →
            # istemci kutunun oranını bilemeyip kareyi kırpıyor ve ORGAN İŞARETLERİ canlı
            # görüntüyle KAYIYORDU. Bu bir tıbbi karar ekranı; işaret kayması organ hatasıdır.
            **_cat_boyut,
            "n_organs": len(organs_list),
            "organs": organs_list,
            "pose_type": (result.get("pose_classifier") or {}).get("type"),
            "pnp_residual_px": round(float((result.get("pnp_fit") or {}).get("residual_px", 0.0)), 1),
            # AII-2.7: hattın ölçeği (px/cm) — AI Pro dökümü PnP hatasını çözünürlükten bağımsız ≈ cm gösterir (GPU servisiyle parite).
            "pnp_scale_px_per_cm": (result.get("pnp_fit") or {}).get("scale_px_per_cm"),
            # Sunum-katmanı XAI rozetleri (2026-08-26): sağ/sol ayna şüphesi + anatomik tutarlılık
            # ihlalleri — pipeline üretiyordu, yanıt taşımıyordu.
            "mirror_warning": bool((result.get("pnp_fit") or {}).get("mirror_warning")),
            "anatomic_consistency": result.get("anatomic_consistency"),
            # D1.E08 (İG-5.27): kabin yapılandırması yüklenemediyse sonuç KALİBRASYONSUZ — operatöre söylenir (yalnız-ek;
            # metin tek kaynakta, GPU servisi de aynısını döner — parite kapısı).
            "kabin_uyarisi": _cat_kabin_uyarisi(result),
        }
    except Exception as e:
        logger.error(f"cat_organ inference error: {e}", exc_info=True)
        raise _ai_fail(lambda d: ceviri.t("ai.hata.kediOrgan", dil=d), e)


# ═══════════════════════════════════════════════════════════════════════════════
# AI HAZIRLIK SELF-TESTİ (2026-08-27, saha bulgusu)
# ═══════════════════════════════════════════════════════════════════════════════
# NEDEN VAR: "Yara kapanma modeli bu kurulumda hazır değil" mesajı sahada, model
# paketi KURULUYKEN çıktı. Sebep model eksikliği değil, modülün bir bağımlılığının
# frozen EXE'de import edilememesiydi; hata hiçbir yere yazılmadığı için ne kullanıcı
# ne destek gerçek nedeni görebildi. Tek bir uç yanlış teşhis üretiyordu.
#
# ⚠️ SINIF SORUNU (sahibin uyarısı): her YENİ AI modeli aynı sessiz kırılmayı
# tekrarlayabilir — model paketi iner, kod gelir, ama bir transitif bağımlılık
# frozen'a girmediği için modül ölü doğar ve kullanıcı "model paketi gerekli" görür.
# Bu uç o sınıfı görünür kılar: her modül için (1) kodun import edilebilirliği,
# (2) model dosyasının çözülebilirliği AYRI AYRI raporlanır.
#
# GÜVENLİK: uç auth-muaf (`/api/ai/` prefix'i) → dosya yolu/sistem detayı DÖNMEZ;
# yalnız modül adı, durum ve hata TİPİ + kısa mesaj. Tam zincir sunucu log'una yazılır.
#
# MALİYET: varsayılan mod HAFİFTİR (find_spec + dosya varlığı, model YÜKLEMEZ).
# `?derin=1` gerçek import dener — ölü-doğmuş modülü yakalayan tek mod budur; ağır
# olduğu için istek üzerine çalışır ve canlı seans akışına girmez.
# ⚠️ DENETİM 2026-08-28 #03 — BU ENVANTERİN MODEL SÜTUNU SAHTEYDİ. 13 modülün 12'sinde model
# yolu `None`'dı; `_model_hazir_mi(None)` tek satırda `return "gomulu",""` diyor, HİÇBİR dosyaya
# bakmıyordu ve "gomulu" PASS sayılıyordu. Ölçülen sonuç: model dizini eksik bir kurulumda
# `/api/ai/sound/cat` ve `/vision/thermal` HTTP 500 verirken kapı **12/13 "gomulu"** diyordu;
# eksik dizin koşan sürece kopyalanıp uçlar 200'e dönünce kapı çıktısı BİT DÜZEYİNDE AYNI kaldı.
# Yani sütunun bilgi içeriği sıfırdı — sessiz ölümün panzehri olarak eklenen uç, kendisi kördü.
# "Gömülü" iddiası da yanlıştı: bu modüllerin çoğunun ağırlığı profil paketlerinde (model zip'i).
#
# Yollar `build_tools/make_model_zip.py::PROFILLER` + `make_base_zip.py::CORE_MODELS` ile aynı
# olmalı; sapmayı `tests/test_ai_hazirlik_envanteri.py` kilitler (frozen'da build_tools yok,
# bu yüzden liste burada AÇIK yazılır — tek-kaynak sapması testle yakalanır).
_AI_MODUL_ENVANTERI = [
    # (ad, import yolu, model göreli yolu) — model yolu None OLAMAZ (kapı testi bunu yasaklar).
    ("landmark", "ai_hub.cat_landmark.inference_cat_landmark", "ai_hub/cat_landmark/yolo26m-pose.onnx"),
    ("thermal", "ai_hub.cat_thermal.inference_cat_thermal", "ai_hub/cat_thermal/GhostNetV2.onnx"),
    (
        "segmentation",
        "ai_hub.cat_segmentation.inference_cat_segmentation",
        "ai_hub/cat_segmentation/yolov8m-seg.onnx",
    ),
    (
        "cat_sound",
        "ai_hub.inference_cat_sound.inference_cat_sound",
        "ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx",
    ),
    # cat_organ ÇEKİRDEK pakette (CORE_MODELS) — üç ONNX'ten biri yoksa modül ölür; en büyüğü kilit.
    # ⚠️ Ağırlıklar `models/` ALT DİZİNİNDE (diğer modüllerin aksine); yol buna göre yazıldı.
    (
        "cat_organ",
        "ai_hub.inference_cat_organ.catorgan_predictor",
        "ai_hub/inference_cat_organ/models/yolov8m-seg.onnx",
    ),
    (
        "reticulocytes",
        "ai_hub.feline_reticulocytes.inference_feline_reticulocytes",
        "ai_hub/feline_reticulocytes/yolov8s.onnx",
    ),
    (
        "kidney_ct",
        "ai_hub.inference_human_kidney_ct.inference_human_kidney_ct",
        "ai_hub/inference_human_kidney_ct/yolov8s.onnx",
    ),
    # D6.18 (B-5.13): çıkarımın AÇTIĞI ağırlık ONNX'tir (`KidneyRnaPredictor` → `best_model_meta.json` `onnx_file`); `.pt` yalnız
    # XAI (Integrated Gradients, araştırma profili) içindir. Eskiden `.pt` ölçülüyordu → ONNX eksikken hazırlık YEŞİL, ilk analiz
    # FileNotFoundError. Kapı: tests/test_ai_hazirlik_kidney_rna_CIKARIMIN_ONNXini_olcer_D6_18.py
    (
        "kidney_rna",
        "ai_hub.inference_human_kidney_rna.inference_human_kidney_rna",
        "ai_hub/inference_human_kidney_rna/mlp_medium_kirc.onnx",
    ),
    (
        "histopath",
        "ai_hub.inference_renal_histopath_kmc.inference_renal_histopath_kmc",
        "ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx",
    ),
    ("em_kedi", "ai_hub.em_kedi.inference_em_kedi", "ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx"),
    (
        "em_fantom",
        "ai_hub.inference_em_fantom.inference_em_fantom",
        "ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx",
    ),
    ("em_petri", "ai_hub.inference_em_petri.inference_em_petri", "ai_hub/inference_em_petri/BaggingRegressor.onnx"),
    # Denetim 2026-09-08: em_petri ANALİZİ iki ağırlık ister — doz modeli (üstteki BaggingRegressor)
    # VE kuyucuk tespiti için petri_cv_v2'nin YOLO11m-seg'i (85,5 MB, research.zip). İkincisi
    # envanterde HİÇ YOKTU: dosya eksikken /api/ai/hazirlik YEŞİL kalıyor, ilk petri isteği (ve
    # araştırma AI Pro hazırlığı) FileNotFoundError ile ölüyordu. Kapı:
    # tests/test_ai_hazirlik_envanteri.py::test_KRITIK_URETIMDE_cozulen_her_agirlik_envanterde_OLCULUYOR
    (
        "petri_yolo",
        "ai_hub.inference_petri_dish.petri_cv_v2.petri_detector",  # AI-2: v1 petri_cv emekli
        "ai_hub/inference_petri_dish/yolo11m-seg.onnx",
    ),
    (
        "scratch",
        "ai_hub.inference_paper_dilek_hoca.cell.cpn",
        "ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt",
    ),
    # Denetim #03(c): bu iki uç envanterde HİÇ YOKTU — 15 canlı AI rotasından 13'ü kapsanıyordu.
    ("cat_disease", "ai_hub.cat_disease.inference_cat_disease", "ai_hub/cat_disease/XGBoost.pkl"),
    (
        "kidney_disease",
        "ai_hub.inference_human_kidney_disease.inference_human_kidney_disease",
        "ai_hub/inference_human_kidney_disease/ExtraTrees.onnx",
    ),
]


def _modul_hazir_mi(import_yolu: str, derin: bool) -> tuple[str, str]:
    """(durum, ayrıntı). derin=False → find_spec; derin=True → GERÇEK import."""
    import importlib

    try:
        if derin:
            # ⚠️ A9: GERÇEK import süreç-geneli kilit altında. Bu prob envanterdeki HER
            # modülü import eder; istek yolundaki tembel import'larla ve `scratch-warmup`
            # thread'iyle aynı anda koşabilir. Kilitsiz hâli yarışın ikinci tarafıydı.
            _agir_import(import_yolu)
            return "ok", ""
        spec = importlib.util.find_spec(import_yolu)
        return ("ok", "") if spec is not None else ("kod_yok", "modül bulunamadı")
    except Exception as e:  # ImportError + modül-içi her hata
        return "kod_hatali", _kok_neden_zinciri(e)


def _model_hazir_mi(rel_yol: str | None) -> tuple[str, str]:
    """Model ağırlığı GERÇEKTEN çözülebiliyor mu (denetim #03).

    ⚠️ İKİ DEĞİŞMEZ, ikisi de ölçümle kondu:
      1. `rel_yol is None` artık "gomulu" DEĞİL, `envanter_eksik` HATASIDIR. Eski davranış
         (None → "gomulu" → PASS) kapının 12 modülde hiçbir şeye bakmamasının sebebiydi.
      2. Çözücü CANLI çıkarımınkiyle AYNI: `yan_dosya_coz` — önce modülün YANI, sonra `find_installed_model`'in
         5 kökü + bütünlük sağlaması. `pt_coz` yalnız PT ikizleri içindir ve farklı bir yol kümesine bakar; kapının
         canlı yoldan BAŞKA bir yere bakması, tam olarak "yeşil kapı / ölü uç" durumunu üretir.
         ⚠️ D4.E01 (İG-9.21): eskiden yalnız `find_installed_model` vardı. Katmanlı launcher düzeninde küçük model dosyaları
         (spec: <5 MB .onnx/.pkl… — D4.27) modülün YANINDA (`_internal/ai_hub/…`) sevk edilir; çıkarım onları buluyor (ölçüldü:
         böbrek-hastalık 200) ama hazırlık "model_yok" diyordu (sahte kırmızı). Kapı:
         tests/test_ai_hazirlik_CIKARIMLA_AYNI_cozucu_D4E01.py
    """
    if not rel_yol:
        return "envanter_eksik", "model yolu tanımsız — envantere gerçek yol yazılmalı (denetim #03)"
    try:
        from pathlib import Path as _P

        from utils.model_downloader import _model_integrity_ok, yan_dosya_coz
        from utils.path_utils import resource_path

        yol = yan_dosya_coz(resource_path(rel_yol), rel_yol)  # modül yanı (donmuşta `_MEIPASS/<rel>`) → model kökleri
        if not os.path.isfile(yol):
            return (
                "model_yok",
                f"{rel_yol} ne modülün yanında ne bir model kökünde bulundu (ya da bütünlük sağlaması başarısız)",
            )
        # 4B-3.6: `yan_dosya_coz` modül-yanı dosyayı bütünlük sağlamasız döndürür (kökten gelen `find_installed_model`'de
        # süzülür) → kesik modül-yanı ONNX "ok" görünüp çıkarımda (modül-yanı ÖNCE) düşüyordu. Seçilen dosya aynı süzgeçten geçer.
        if not _model_integrity_ok(_P(yol), rel_yol):  # D3.48: beklenen özet (yan dosya / takipli manifest) dahil
            return "model_yok", f"{rel_yol} bulundu ama bütünlük sağlaması başarısız (kesik/bozuk ağırlık): {yol}"
        return "ok", ""
    except Exception as e:
        return "model_yok", _kok_neden_zinciri(e)


@ai_router.get("/api/ai/hazirlik")
async def ai_hazirlik(derin: int = 0):
    """AI modüllerinin gerçek durumu (kod + model AYRI) — destek/tanılama ucu.

    derin=0 (varsayılan): hafif tarama. derin=1: gerçek import — ölü-doğmuş modülü
    yakalar (frozen'a girmemiş bağımlılık), ilk çağrıda yavaştır.
    """
    derin_mi = bool(derin)
    moduller = []
    for ad, import_yolu, model_yolu in _AI_MODUL_ENVANTERI:
        kod_durum, kod_ayrinti = await asyncio.to_thread(_modul_hazir_mi, import_yolu, derin_mi)
        model_durum, model_ayrinti = await asyncio.to_thread(_model_hazir_mi, model_yolu)
        # Denetim #03: "gomulu" PASS listesinden ÇIKARILDI — dosyaya bakmadan verilen bir
        # geçiş notuydu. Artık yalnız gerçekten çözülen ağırlık ("ok") hazır sayılır.
        hazir = kod_durum == "ok" and model_durum == "ok"
        if not hazir:
            logger.warning(
                "AI HAZIRLIK: %s HAZIR DEĞİL — kod=%s (%s) model=%s (%s)",
                ad,
                kod_durum,
                kod_ayrinti or "-",
                model_durum,
                model_ayrinti or "-",
            )
        moduller.append(
            {
                "modul": ad,
                "hazir": hazir,
                "kod": kod_durum,
                "model": model_durum,
                # Denetim #07: modül GERÇEKTE nereden yüklendi (pyd/pyenc = korumalı,
                # pyz/py = koruma yok). Yalnız derin=1'de anlamlı — sığ taramada import
                # yapılmadığı için modül henüz sys.modules'te olmayabilir.
                "yukleme": (_modul_yukleme_bicimi(import_yolu) if derin_mi else "olculmedi"),
                # Kısa sebep: tip + ilk 200 karakter (yol/sistem detayı sızdırmaz).
                "sebep": (kod_ayrinti or model_ayrinti or "")[:200],
            }
        )
    hazir_sayisi = sum(1 for m in moduller if m["hazir"])
    yanit = {
        "status": "success",
        "derin": derin_mi,
        "toplam": len(moduller),
        "hazir": hazir_sayisi,
        "eksik": [m["modul"] for m in moduller if not m["hazir"]],
        "moduller": moduller,
    }
    if derin_mi:
        yanit["xai"] = await asyncio.to_thread(_xai_zinciri_durumu)
        yanit["pip_yasagi"] = _pip_yasagi_durumu()
    # Araştırma AI Pro bayrağı: sahada "neden Onayla açılmıyor?" sorusu tek istekle yanıtlanır
    # (frozen EXE'de env'in servise geçtiği de böyle doğrulanır).
    yanit["arastirmaAiPro"] = {
        "acik": _arastirma_aipro_acik(),
        "bayrak": ARASTIRMA_AIPRO_BAYRAGI,
        # T-f (yalnız-ek): fantomun AYRI bayrağı (varsayılan KAPALI).
        "fantomAcik": _arastirma_aipro_fantom_acik(),
        "fantomBayrak": ARASTIRMA_AIPRO_FANTOM_BAYRAGI,
        "neden": (
            "" if _arastirma_aipro_acik() else "Fantom/petri 3B konum dönüşümü tezgâhta doğrulanmadı (plan kararı #6)."
        ),
    }
    return yanit


def _xai_zinciri_durumu() -> dict:
    """Açıklanabilirlik zincirinin GERÇEK durumu (denetim #03(b)).

    ⚠️ Kapı yalnız üst-seviye import deniyordu; XAI kütüphaneleri (`pytorch_grad_cam`, `captum`,
    `shap`, `ttach`) FONKSİYON İÇİNDE lazy import edilir → hiçbiri görünmüyordu. Ölçüldü:
    tüm XAI yığını `sys.meta_path` ile bloklandığında kapı 13/13 `kod=ok` demeye devam etti,
    aynı anda gerçek termal XAI `ImportError` ile patlıyordu.

    ⚠️ `TORCH_XAI_AVAILABLE` KULLANILMAZ: o bayrak yalnız `grad_cam` MODÜLÜNÜN import
    edilebildiğini söyler; `pytorch_grad_cam` yokken de `True` döner (modül kendi içinde
    `_AVAILABLE=False`'a düşüp sessizce açıklamasız çalışır). Doğru sinyal `grad_cam._AVAILABLE`.
    """
    import importlib

    durum: dict = {}
    try:
        gc = importlib.import_module("ai_hub.xai_utils.grad_cam")
        durum["grad_cam"] = "ok" if getattr(gc, "_AVAILABLE", False) else "kutuphane_yok"
    except Exception as e:
        durum["grad_cam"] = "kod_hatali"
        durum["grad_cam_sebep"] = _kok_neden_zinciri(e)[:200]

    for ad in ("pytorch_grad_cam", "captum", "shap", "ttach"):
        try:
            importlib.import_module(ad)
            durum[ad] = "ok"
        except Exception as e:
            durum[ad] = "yok"
            durum[f"{ad}_sebep"] = _kok_neden_zinciri(e)[:200]

    # EM XAI referans istatistikleri: `.npz` bir kez spec'te yoktu → EM XAI 1.9.25'ten beri
    # üretimde SESSİZ ölüydü ve kapı görmedi (denetim #03'ün kendi örneği).
    eksik_npz = []
    for modul in ("em_kedi", "inference_em_fantom", "em_petri", "em_phantom", "inference_em_petri"):
        try:
            spec = importlib.util.find_spec(f"ai_hub.{modul}")
            if spec is None or not spec.submodule_search_locations:
                continue
            from pathlib import Path as _P

            # AI1.X6: canlı duyarlılığın eğitim referansı (xai_train_ref.npz) da aynı sınıfta — biri yoksa modül eksik
            _kok = _P(list(spec.submodule_search_locations)[0])
            if not all((_kok / ad).exists() for ad in ("xai_ref_stats.npz", "xai_train_ref.npz")):
                eksik_npz.append(modul)
        except Exception:
            continue
    durum["em_ref_stats_eksik"] = eksik_npz
    # AI1.X4: CKD Kernel SHAP eğitim arka planı (`xai_train_ref_v2.npz`) — yoksa CKD açıklaması üretilmez (zarif düşüş);
    # aynı "spec'te yok → üretimde sessiz ölü" sınıfı burada görünür olsun. Ürünün KENDİ yükleyicisi ölçülür (varlık + biçim).
    try:
        from ai_hub.inference_human_kidney_disease import inference_human_kidney_disease as _ihd

        # AII-3.5: npz + açıklamanın kurulduğu shap ÖZEL API'si (DenseData) birlikte — ürünün TEK kurucusu (ağırlıksız)
        _ihd.xai_arka_plan_verisi([f"f{i}" for i in range(24)])
        durum["ckd_xai_referansi"] = "ok"
    except Exception as e:
        durum["ckd_xai_referansi"] = "eksik"
        durum["ckd_xai_referansi_sebep"] = _kok_neden_zinciri(e)[:200]
    durum["hazir"] = durum.get("grad_cam") == "ok" and not eksik_npz and durum["ckd_xai_referansi"] == "ok"
    return durum


def _modul_yukleme_bicimi(import_yolu: str) -> str:
    """Modül GERÇEKTE nereden yüklendi? (denetim 2026-08-28 #07)

    ⚠️ UZANTIYA BAKMA. PyInstaller 6.20, PYZ arşivinden yüklenen modüle de `.py` uzantılı bir
    `__file__` verir (`pyimod02_importers.py:405-418` bunu bilerek yapar — ölçüldü). `EncryptedLoader`
    da D4.13'ten beri (`utils/encrypted_import.py`, `spec_from_file_location`) `__file__`'ı diskteki
    `.pyenc`'e bağlar (has_location True). Uzantı tabanlı ayrım "PYZ bytecode" ile "diskte düz kaynak"ı
    karıştırır — oysa alanın var oluş sebebi tam olarak bu ayrımdır.

    Anlamlar:
      pyd    → Cython native uzantı. KORUMALI.
      pyenc  → şifreli yedek katman. MEŞRU koruma (build_installer.ps1:574 sahip ölçütü).
      pyz    → PYZ arşivi. KORUMA YOK — okunabilir bytecode.
      py     → diskte düz kaynak. KORUMA YOK.
    """
    import sys as _sys

    mod = _sys.modules.get(import_yolu)
    if mod is None:
        return "yok"
    ad = type(getattr(mod, "__loader__", None)).__name__
    return {
        "ExtensionFileLoader": "pyd",
        "PyiFrozenLoader": "pyz",
        "EncryptedLoader": "pyenc",
        "SourceFileLoader": "py",
        "SourcelessFileLoader": "pyc",
        "_NamespaceLoader": "nspkg",
    }.get(ad, f"bilinmiyor:{ad}")


def _pip_yasagi_durumu() -> dict:
    """Çalışma-anı pip yasağı gerçekten kurulu mu (denetim #10 kapısının teşhis görünürlüğü)."""
    try:
        from utils.runtime_guards import kurulum_yasagi_etkin_mi

        return {"etkin": bool(kurulum_yasagi_etkin_mi())}
    except Exception as e:
        return {"etkin": False, "sebep": _kok_neden_zinciri(e)[:200]}
