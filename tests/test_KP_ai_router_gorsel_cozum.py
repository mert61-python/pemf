# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/ai_router.py · sözleşmeler: görüntü çözümü ve yardımcı katman.

`_decode_image` (boyut / çözünürlük / HTML / bozuk bayt / modalite kapısı iç hatası), `_kapili_devret` (girdi yok / boyut),
`_kapakli_kodla` + `_gecici_gorsel_yaz` + `_localize_organ_gpu` (kodlayıcı başarısız), `_localize_organ_gpu` (GPU yanıtındaki bozuk
organ kimliği / overlay), `_get_or_load_model` (yükleme hatası önbelleği zehirlemez; eşzamanlı ilk yüklemede yükleyici TEK kez),
`_y51_devir_etiketi` (sözlük olmayan yanıt / kabin YAML'ı okunamaz), AI Pro seans yardımcıları (`_ai_kare_yabanci`, `_kiskac_izi`,
`_kabin_okunamaz_bildir`, `_doz_hatasi_bildir`, `_ai_pro_surus_muhru`, `_muhur_surulebilir_mi`, `_ai_pro_seans_onayi`,
`ai_pro_bobinlerini_plandan_cikar`, `_hazirlik_hata_metni`).

Sahte EN ALT katta: ağ (`ai_client.httpx`), kodlayıcı (`cv2.imencode`), bildirim gönderimi (`api_server._push_notification`),
kabin YAML okuyucusu (`phantom_cv_v3.load_cabin_config`), model indirici. Girdi görüntüleri tmp / bellekte üretilir.
"""

from __future__ import annotations

import asyncio
import base64
import io
import struct
import threading
import types
import zlib

import cv2
import httpx
import numpy as np
import pytest
from fastapi import HTTPException
from servers import ai_client
from servers import ai_router as air
from starlette.datastructures import UploadFile

MB25 = 25 * 1024 * 1024


def _kos(coro):
    """Eşyordamı ayrı bir Selector döngüsünde koşar (Proactor GC riski yok); varsayılan yürütücü kapatılır."""
    dongu = asyncio.SelectorEventLoop()
    try:
        return dongu.run_until_complete(coro)
    finally:
        dongu.run_until_complete(dongu.shutdown_default_executor())
        dongu.close()


def _jpg(h=48, w=64) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 2] = (30, 120, 200)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _png_basligi(w: int, h: int) -> bytes:
    """Geçerli ama DEV boyut bildiren 1-bit gri PNG (piksel verisi sıfırlar; başlık PIL'in okuduğu yer)."""

    def _parca(tur: bytes, veri: bytes) -> bytes:
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 1, 0, 0, 0, 0)
    satir = b"\x00" + b"\x00" * ((w + 7) // 8)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _parca(b"IHDR", ihdr)
        + _parca(b"IDAT", zlib.compress(satir * h, 9))
        + _parca(b"IEND", b"")
    )


def _yukleme(veri: bytes, ad: str = "g.jpg") -> UploadFile:
    return UploadFile(file=io.BytesIO(veri), filename=ad)


# ─────────────────────────────── _decode_image ───────────────────────────────


def test_decode_base64_girdi_sinirin_ustunde_COZULMEDEN_reddedilir():
    """base64 dizgesi (25 MB × 4/3 + 1024) sınırını aşıyor → çözülmeden ValueError('… base64 girdi > 25 MB sınırı')."""
    dev = "A" * ((MB25 * 4) // 3 + 1025)
    with pytest.raises(ValueError, match=r"base64 girdi > 25 MB sınırı"):
        _kos(air._decode_image(None, dev, label="landmark"))


def test_decode_dosya_25MB_ustu_reddedilir():
    """Yüklenen dosya 25 MB + 1 bayt → ValueError('Görüntü çok büyük (> 25 MB sınırı).'); dosyanın tamamı okunmaz."""
    with pytest.raises(ValueError, match=r"^Görüntü çok büyük \(> 25 MB sınırı\)\.$"):
        _kos(air._decode_image(_yukleme(b"\xff" * (MB25 + 1)), None, label="landmark"))


def test_decode_base64_sinir_icinde_ama_COZULMUS_icerik_25MB_ustu_reddedilir():
    """base64 kaba sınırı geçer ama çözülen içerik 25 MB'ı (100 bayt) aşar → ikinci denetim ValueError verir."""
    b64 = base64.b64encode(b"\x00" * (MB25 + 100)).decode("ascii")
    assert len(b64) <= (MB25 * 4) // 3 + 1024, "aparat: kaba sınırın içinde kalmalı"
    with pytest.raises(ValueError, match=r"^Görüntü çok büyük \(> 25 MB sınırı\)\.$"):
        _kos(air._decode_image(None, b64, label="landmark"))


def test_decode_50MP_ustu_cozunurluk_PIKSEL_cozulmeden_reddedilir():
    """Başlığı 8000×8000 (64 MP) bildiren küçük PNG → ValueError('…(8000x8000px > 50MP sınırı).'), cv2 çözmeye geçilmez."""
    png = _png_basligi(8000, 8000)
    assert len(png) < 200_000, "aparat: dosya küçük, çözünürlük dev olmalı"
    with pytest.raises(ValueError, match=r"8000x8000px > 50MP sınırı"):
        _kos(air._decode_image(None, base64.b64encode(png).decode("ascii"), label="landmark"))


def test_decode_goruntu_yerine_HTML_gelirse_eylem_soyleyen_ileti():
    """React yedeği index.html gönderdi (PIL başlık okuyamaz, cv2 çözemez) → ValueError('Görüntü yerine HTML (index.html) alındı…')."""
    html = b"  <!DOCTYPE html><html><body>uygulama</body></html>\n"
    with pytest.raises(
        ValueError, match=r"^Görüntü yerine HTML \(index\.html\) alındı\. React paketini kontrol edin\.$"
    ):
        _kos(air._decode_image(None, base64.b64encode(html).decode("ascii"), label="landmark"))
    with pytest.raises(ValueError, match=r"^Görüntü yerine HTML"):
        _kos(air._decode_image(None, base64.b64encode(b"<html><p>x</p></html>").decode("ascii"), label="landmark"))


def test_decode_bozuk_bayt_GECERSIZ_goruntu_ve_boyutu_soyler():
    """Ne görüntü ne HTML olan 37 bayt → ValueError('Geçersiz görüntü verisi. Alınan boyut: 37 bytes.')."""
    veri = b"bu bir goruntu degil, duz metin 1234"
    veri = veri + b"!" * (37 - len(veri))
    with pytest.raises(ValueError, match=r"^Geçersiz görüntü verisi\. Alınan boyut: 37 bytes\.$"):
        _kos(air._decode_image(None, base64.b64encode(veri).decode("ascii"), label="landmark"))


def test_decode_modalite_kapisi_HTTPException_firlatirsa_AYNEN_iletilir(monkeypatch):
    """Kapı kendisi HTTPException(413) verirse A-24 'denetim çalıştırılamadı' 422'sine SARILMAZ → aynı kod + detay."""
    from utils import image_domain

    def _kapi(img, label):
        raise HTTPException(status_code=413, detail="kapi-ozel-ret")

    monkeypatch.setattr(image_domain, "check", _kapi)
    with pytest.raises(HTTPException) as ex:
        _kos(air._decode_image(None, base64.b64encode(_jpg()).decode("ascii"), label="histopath"))
    assert ex.value.status_code == 413 and ex.value.detail == "kapi-ozel-ret"


def test_decode_kapi_ic_hatasi_ve_uzun_metin_URETILEMEZSE_kisa_katalog_metniyle_422(monkeypatch):
    """Modalite analizi iç hata verir (A-24) VE uzun metin üretilemez → 422 + `ai.alan.denetimKisa` (analiz yapılmaz)."""
    from servers import ai_kapi_metni
    from utils import ceviri, image_domain

    def _analiz(img):
        raise cv2.error("OpenCV(4.11) cvtColor: bozuk kanal")

    def _metin(dil=None):
        raise KeyError("ai.alan.denetimCalismadi")

    monkeypatch.setattr(image_domain, "analyze", _analiz)
    monkeypatch.setattr(ai_kapi_metni, "denetim_calismadi", _metin)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    with pytest.raises(HTTPException) as ex:
        _kos(air._decode_image(None, base64.b64encode(_jpg()).decode("ascii"), label="histopath"))
    assert ex.value.status_code == 422
    assert ex.value.detail == ceviri.t("ai.alan.denetimKisa")
    assert "YAPILMADI" in ex.value.detail


# ─────────────────────────────── _kapili_devret ───────────────────────────────


def test_kapili_devret_girdi_YOKSA_devretmez_ValueError():
    """Ne dosya ne base64 → ValueError('Görüntü verisi bulunamadı.') (GPU servisine boş istek gitmez)."""
    with pytest.raises(ValueError, match=r"^Görüntü verisi bulunamadı\.$"):
        _kos(air._kapili_devret("landmark", file=None, image_base64=None))


def test_kapili_devret_dosya_25MB_ustu_DEVRETMEDEN_reddedilir(monkeypatch):
    """25 MB + 1 baytlık yükleme → ValueError; ağ katmanına HİÇ istek gitmez."""
    giden = []

    class _Asenk:
        def __init__(self, *a, **k):
            giden.append(("kur", a, k))

    monkeypatch.setattr(ai_client, "httpx", types.SimpleNamespace(AsyncClient=_Asenk, Client=_Asenk))
    with pytest.raises(ValueError, match=r"^Görüntü çok büyük \(> 25 MB sınırı\)\.$"):
        _kos(air._kapili_devret("landmark", file=_yukleme(b"\x00" * (MB25 + 1))))
    assert giden == []


# ─────────────────────────────── kodlayıcı başarısız ───────────────────────────────


def _kodlayici_basarisiz(monkeypatch):
    cagri = []

    def _imencode(uzanti, img, *a, **k):
        cagri.append(uzanti)
        return False, None

    monkeypatch.setattr(cv2, "imencode", _imencode)
    return cagri


def test_kapakli_kodla_kodlayici_basarisizsa_RuntimeError(monkeypatch):
    """cv2.imencode False döner → RuntimeError('JPEG kodlama basarisiz') (bozuk/boş JPEG yanıta konmaz)."""
    cagri = _kodlayici_basarisiz(monkeypatch)
    with pytest.raises(RuntimeError, match=r"^JPEG kodlama basarisiz$"):
        air._kapakli_kodla(np.zeros((20, 30, 3), dtype=np.uint8))
    assert cagri == [".jpg"]


def test_gecici_gorsel_yaz_kodlanamazsa_DOSYA_yazilmaz_ve_adi_soylenir(monkeypatch, tmp_path):
    """Kodlayıcı başarısız → RuntimeError('geçici görsel kodlanamadı (kare.png)'); 0 baytlık dosya BIRAKILMAZ."""
    cagri = _kodlayici_basarisiz(monkeypatch)
    hedef = tmp_path / "kare.png"
    with pytest.raises(RuntimeError, match=r"^geçici görsel kodlanamadı \(kare\.png\)$"):
        air._gecici_gorsel_yaz(str(hedef), np.zeros((4, 4, 3), dtype=np.uint8))
    assert cagri == [".png"] and not hedef.exists()


# ─────────────────────────────── _localize_organ_gpu (GPU yanıtı) ───────────────────────────────


class _SahteYanit:
    def __init__(self, govde):
        self._govde = govde

    def raise_for_status(self):
        return None

    def json(self):
        return self._govde


def _sahte_httpx(monkeypatch, govde):
    """`ai_client`in gördüğü httpx: senkron istemci isteği kaydeder ve `govde`yi döndürür (ağ YOK)."""
    kayit = []

    class _Istemci:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            pass

        def post(self, url, **kw):
            kayit.append((url, kw))
            return _SahteYanit(govde)

    monkeypatch.setattr(ai_client, "AI_SERVICE_URL", "http://ai-servisi.invalid")
    monkeypatch.setattr(
        ai_client,
        "httpx",
        types.SimpleNamespace(
            Client=_Istemci, AsyncClient=_Istemci, ReadTimeout=httpx.ReadTimeout, HTTPStatusError=httpx.HTTPStatusError
        ),
    )
    return kayit


def test_gpu_lokalizasyon_BOZUK_organ_kimligi_atlanir_overlay_COZULUR(monkeypatch):
    """GPU yanıtı: {'id': 'bozuk'} organı atlanır, geçerli organ 2 hedeflenir (cm→mm) ve `image_base64` overlay'i BGR'ye çözülür."""
    ov = np.full((24, 32, 3), 200, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", ov)
    kayit = _sahte_httpx(
        monkeypatch,
        {
            "organs": [
                {"id": "bozuk", "reliability": 1.0},
                {"id": 2, "coord_cabin_cm": [1.0, 2.0, 3.0], "reliability": 0.9},
            ],
            "image_base64": base64.b64encode(buf.tobytes()).decode("ascii"),
        },
    )
    sonuc = air._localize_organ_gpu(np.zeros((16, 16, 3), dtype=np.uint8), 2)
    assert kayit and kayit[0][0] == "http://ai-servisi.invalid/infer/cat_organ"
    assert kayit[0][1]["data"] == {"target_oid": "2"}
    lokal, x, y, z, rel, overlay, kedi_var = sonuc[:7]
    assert (lokal, x, y, z, rel, kedi_var) == (True, 10.0, 20.0, 30.0, 0.9, True)
    assert isinstance(overlay, np.ndarray) and overlay.shape == (24, 32, 3)


def test_gpu_lokalizasyon_COZULEMEYEN_overlay_None_olur_hedef_yine_doner(monkeypatch):
    """`image_base64` geçersiz base64 → overlay None; organ hedefi (organ 2) yine çıkarılır (analiz düşmez)."""
    _sahte_httpx(
        monkeypatch,
        {"organs": [{"id": 2, "coord_cabin_cm": [1.0, 1.0, 1.0], "reliability": 0.8}], "image_base64": "%%%bozuk%%%"},
    )
    lokal, x, y, z, rel, overlay, kedi_var = air._localize_organ_gpu(np.zeros((16, 16, 3), dtype=np.uint8), 2)[:7]
    assert overlay is None
    assert (lokal, x, y, z, rel, kedi_var) == (True, 10.0, 10.0, 10.0, 0.8, True)


def test_gpu_lokalizasyon_kare_KODLANAMAZSA_servise_gitmez(monkeypatch):
    """Kare JPEG'e kodlanamaz → RuntimeError('frame JPG encode başarısız'); ağ isteği YOK."""
    kayit = _sahte_httpx(monkeypatch, {"organs": []})
    _kodlayici_basarisiz(monkeypatch)
    with pytest.raises(RuntimeError, match=r"^frame JPG encode başarısız$"):
        air._localize_organ_gpu(np.zeros((8, 8, 3), dtype=np.uint8), 2)
    assert kayit == []


# ─────────────────────────────── _get_or_load_model ───────────────────────────────


def test_model_YUKLENEMEZSE_hata_yukselir_onbellek_ZEHIRLENMEZ_sonra_yeniden_denenir(monkeypatch):
    """Yükleyici FileNotFoundError → aynı istisna yükselir, anahtar önbellekte KALMAZ; sonraki çağrı yeniden yükler."""
    monkeypatch.setattr(air, "_models", {})
    denemeler = []

    def _yukle():
        denemeler.append(1)
        if len(denemeler) == 1:
            raise FileNotFoundError("kp_test.onnx bulunamadi")
        return "MODEL-2"

    with pytest.raises(FileNotFoundError, match="kp_test.onnx"):
        air._get_or_load_model("kp_test", _yukle)
    assert "kp_test" not in air._models
    assert air._get_or_load_model("kp_test", _yukle) == "MODEL-2"
    assert air._models["kp_test"] == "MODEL-2" and len(denemeler) == 2


def test_eszamanli_ilk_yuklemede_yukleyici_TEK_kez_ikinci_cagri_ayni_nesneyi_alir(monkeypatch):
    """İkinci iş parçacığı ilk denetimi model YOKKEN geçer, kilitte bekler → kilit içi ikinci denetim modeli bulur (yükleyici 1 kez)."""
    ikinci_denetledi = threading.Event()
    birinci_yukluyor = threading.Event()
    birak = threading.Event()

    class _Izleyen(dict):
        def __contains__(self, k):
            sonuc = dict.__contains__(self, k)
            if threading.current_thread().name == "kp-ikinci" and not sonuc:
                ikinci_denetledi.set()
            return sonuc

    monkeypatch.setattr(air, "_models", _Izleyen())
    yuklemeler = []
    model = object()

    def _yukle():
        yuklemeler.append(threading.current_thread().name)
        birinci_yukluyor.set()
        assert birak.wait(10)
        return model

    sonuclar = {}

    def _calis():
        sonuclar[threading.current_thread().name] = air._get_or_load_model("kp_es", _yukle)

    t1 = threading.Thread(target=_calis, name="kp-birinci")
    t1.start()
    assert birinci_yukluyor.wait(10)
    t2 = threading.Thread(target=_calis, name="kp-ikinci")
    t2.start()
    try:
        assert ikinci_denetledi.wait(10), "aparat: ikinci iş parçacığı ilk denetime ulaşmadı"
    finally:
        birak.set()
        t1.join(10)
        t2.join(10)
    assert yuklemeler == ["kp-birinci"]
    assert sonuclar == {"kp-birinci": model, "kp-ikinci": model}


# ─────────────────────────────── _y51_devir_etiketi ───────────────────────────────


def test_y51_devir_sozluk_OLMAYAN_yanit_AYNEN_doner():
    """Servis yanıtı liste → etiket denenmez, aynı nesne döner."""
    yanit = [{"x": 1}]
    assert air._y51_devir_etiketi("fantom", yanit, None) is yanit


def test_y51_devir_kabin_YAML_okunamazsa_yanit_ETIKETSIZ_doner(monkeypatch):
    """duty_sum yok + kabin YAML'ı okunamaz (FileNotFoundError) → yanıt değişmeden döner (bilinmiyor ≠ eğitim aralığı dışı)."""
    from ai_hub.inference_em_fantom import phantom_cv_v3

    def _okunamaz(yol):
        raise FileNotFoundError("cabin_config_v3.yaml")

    monkeypatch.setattr(phantom_cv_v3, "load_cabin_config", _okunamaz)
    yanit = {"status": "success", "D": [0.1] * 7}
    assert air._y51_devir_etiketi("fantom", yanit, None) == {"status": "success", "D": [0.1] * 7}


# ─────────────────────────────── AI Pro seans yardımcıları ───────────────────────────────


@pytest.fixture
def api_seans():
    from servers import api_server as api

    with api._session_lock:
        eski = dict(api._active_session)
    yield api
    with api._session_lock:
        api._active_session.clear()
        api._active_session.update(eski)


def test_kare_yabanci_seans_OKUNAMAZSA_bastirma_YOK(monkeypatch):
    """Sahip bilinir ama seans durumu okunamaz (bozuk `_active_session`) → kare yabancı SAYILMAZ (False)."""
    from servers import api_server as api_seans

    monkeypatch.setattr(air, "_ai_owner_client", "sahip-1")
    monkeypatch.setattr(api_seans, "_active_session", None)
    assert air._ai_kare_yabanci("baska-istemci") is False


def test_kiskac_izi_256_anahtari_asinca_TEMIZLENIR_yeni_iz_yazilir(monkeypatch, caplog):
    """İz sözlüğü 256'yı aşmış → temizlenir, yalnız yeni (organ 2, 31 cm) anahtarı kalır ve UYARI yazılır."""
    monkeypatch.setattr(air, "_kiskac_iz_son", {(1, (i, 0, 0)): -1e12 for i in range(300)})
    with caplog.at_level("WARNING", logger="ai_router"):
        air._kiskac_izi(2, (310.0, 0.0, 0.0), (300.0, 0.0, 0.0))
    assert list(air._kiskac_iz_son) == [(2, (31, 0, 0))]
    assert any("eğitim aralığı (±300 mm) DIŞINDA" in r.getMessage() for r in caplog.records)


def test_kiskac_izi_BOZUK_organ_kimligi_istisna_YUKSELTMEZ(monkeypatch):
    """organ_id 'x' (int'e çevrilemez) → iz yazılamaz ama çağırana istisna gitmez; sözlük değişmez."""
    monkeypatch.setattr(air, "_kiskac_iz_son", {})
    assert air._kiskac_izi("x", (310.0, 0.0, 0.0), (300.0, 0.0, 0.0)) is None
    assert air._kiskac_iz_son == {}


@pytest.mark.parametrize(
    "islev, sozluk, anahtar",
    [
        ("_kabin_okunamaz_bildir", "_kabin_okunamaz_bildirilen", "bildirim.aiProKabinYapilandirma"),
        ("_doz_hatasi_bildir", "_doz_hatasi_bildirilen", "bildirim.aiProDozUretmedi"),
    ],
)
def test_bildirim_GONDERILEMEZSE_istisna_yukselmez_seans_anahtari_yazilir(
    monkeypatch, api_seans, islev, sozluk, anahtar
):
    """Gönderim katmanı hata verir → çağırana istisna gitmez; seans anahtarı yazılır (aynı seansta tekrar denenmez)."""
    from utils import ceviri

    monkeypatch.setattr(air, sozluk, {"anahtar": None})
    with api_seans._session_lock:
        api_seans._active_session["onay_kimligi"] = "kp-onay-7"
    gonderilen = []

    def _gonder(mesaj, seviye="info"):
        gonderilen.append((mesaj, seviye))
        raise RuntimeError("bildirim kuyruğu kapalı")

    monkeypatch.setattr(api_seans, "_push_notification", _gonder)
    assert getattr(air, islev)() is None
    assert gonderilen == [(ceviri.t(anahtar, dil="tr"), "error")]
    assert getattr(air, sozluk)["anahtar"] == "kp-onay-7"
    getattr(air, islev)()
    assert len(gonderilen) == 1, "aynı seansta ikinci bildirim denenmemeli"


def test_surus_muhru_seans_OKUNAMAZSA_None(monkeypatch):
    """`_active_session` okunamaz → mühür None (SÜRÜLMEZ)."""
    from servers import api_server as api_seans

    monkeypatch.setattr(api_seans, "_active_session", None)
    assert air._ai_pro_surus_muhru() is None


def test_surus_muhru_baslangic_ANI_yoksa_None(api_seans):
    """ai_pro seansı onaylı + nesilli ama `start_mono` YOK → mühür None (süre hesaplanamaz → sürülmez)."""
    with api_seans._session_lock:
        api_seans._active_session.clear()
        api_seans._active_session.update(
            {"is_active": True, "tur": "ai_pro", "onay_kimligi": "o-1", "surus_nesli": 3, "duration_minutes": 5}
        )
    assert air._ai_pro_surus_muhru() is None
    with api_seans._session_lock:
        api_seans._active_session["start_mono"] = "bozuk"
    assert air._ai_pro_surus_muhru() is None


def test_muhur_YOKSA_surulebilir_DEGIL():
    """Mühür None / boş sözlük → False."""
    assert air._muhur_surulebilir_mi(None) is False
    assert air._muhur_surulebilir_mi({}) is False


def test_seans_onayi_OKUNAMAZSA_None_ve_plandan_cikarma_BOS(monkeypatch):
    """Seans okunamaz → onay None; `ai_pro_bobinlerini_plandan_cikar` hiçbir bobini çıkarmaz ([])."""
    from servers import api_server as api_seans

    monkeypatch.setattr(api_seans, "_active_session", None)
    assert air._ai_pro_seans_onayi() is None
    assert air.ai_pro_bobinlerini_plandan_cikar([1, 2]) == []


def test_plandan_cikar_SAYI_olmayan_bobin_atlanir_gecerliler_cikarilir(monkeypatch, api_seans):
    """Etkin ai_pro seansı: ['x', None, '3', 2] → 'x' ve None atlanır; 3 ve 2 plandan çıkarılır (sıra korunur)."""
    monkeypatch.setattr(air, "_ai_pro_plan_disi", {"onay": None, "bobinler": set()})
    with api_seans._session_lock:
        api_seans._active_session.clear()
        api_seans._active_session.update({"is_active": True, "tur": "ai_pro", "onay_kimligi": "kp-onay-plan"})
    assert air.ai_pro_bobinlerini_plandan_cikar(["x", None, "3", 2]) == [3, 2]
    assert air._ai_pro_plan_disi_bobinler("kp-onay-plan") == {2, 3}


def test_hazirlik_hata_metni_BILINMEYEN_kod_bos_dizge():
    """Tanımsız hata kodu → '' (panel ham kodu göstermez); bilinen kod katalog metni verir."""
    from utils import ceviri

    assert air._hazirlik_hata_metni("baska_bir_kod", "Kedi") == ""
    assert air._hazirlik_hata_metni("kamera", "Kedi") == ceviri.t("ai.pro.hazirlik.kamera", dil="tr")
