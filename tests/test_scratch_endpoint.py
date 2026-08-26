# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Yara Kapanma (Scratch) ucu — wiring + sözleşme kilitleri (mock'lu, cell'siz).

Plan §6: param geçişi (yön/pixel_mm/explain STRING/xai_method allowlist),
zarif 503 (model kurulu değil), jeton sınıfı (3=ağır araştırma), delegate
STRING paritesi, ai_service imza paritesi (yapısal).
"""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

KOK = Path(__file__).resolve().parents[1]


def _ornek_goruntu_b64(tmp_path) -> str:
    img = np.random.default_rng(7).integers(0, 255, (64, 96, 3), dtype=np.uint8)
    yol = tmp_path / "hucre.png"
    assert cv2.imwrite(str(yol), img)
    return base64.b64encode(yol.read_bytes()).decode()


_SAHTE_SONUC = {
    "n_cells": 2085,
    "coverage_ratio": 0.47,
    "cell_area_mean": 100.0,
    "cell_area_median": 90.0,
    "score_mean": 0.6,
    "score_min": 0.3,
    "image_shape": [64, 96],
    "closure": {
        "closure_pct": 29.3,
        "mean_gap_um": 428.0,
        "max_gap_um": 1278.4,
        "gap_area_mm2": 1.0422,
        "roi_left": 10,
        "roi_right": 80,
        "max_gap_col": 40,
        "mean_gap_col": 50,
        "pixel_mm": 0.0016,
    },
    "scratch_yonu": "dikey",
    "pixel_mm": 0.0016,
    "device": "cpu",
    "input_image_base64": "GIRDI",
    "seg_image_base64": "SEG",
    "overlay_image_base64": "OV",
    "analysis_image_base64": "AN",
    "closure_image_base64": "CL",
}


@pytest.fixture()
def istemci(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    return TestClient(apis.app), air


def test_KRITIK_scratch_endpoint_param_gecisi(istemci, monkeypatch, tmp_path):
    """yön + pixel_mm + explain + xai_method scratch_analiz'e AYNEN ulaşır;
    yanıt status=success + tüm alanlar."""
    client, _ = istemci
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as ipd

    cagri = {}

    def sahte(image_path, *, scratch_yonu, pixel_mm, explain, xai_method):
        cagri.update(yon=scratch_yonu, pmm=pixel_mm, exp=explain, met=xai_method)
        return dict(_SAHTE_SONUC)

    monkeypatch.setattr(ipd, "scratch_analiz", sahte)
    r = client.post(
        "/api/ai/vision/scratch",
        data={
            "image_base64": _ornek_goruntu_b64(tmp_path),
            "scratch_yonu": "yatay",
            "pixel_mm": "0.00065",
            "explain": "true",
            "xai_method": "gradcam++",
        },
    )
    assert r.status_code == 200, r.text
    assert cagri == {"yon": "yatay", "pmm": 0.00065, "exp": True, "met": "gradcam++"}
    b = r.json()
    assert b["status"] == "success" and b["closure"]["closure_pct"] == 29.3
    for alan in ("input_image_base64", "seg_image_base64", "analysis_image_base64", "closure_image_base64"):
        assert b[alan]


def test_KRITIK_model_kurulu_degilse_zarif_503(istemci, monkeypatch, tmp_path):
    """cell/ paketi/PT yokken jenerik 500 DEĞİL, dürüst 503 + yönlendirme mesajı."""
    client, _ = istemci
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as ipd

    def kurulu_degil(*a, **k):
        raise ipd.ModelKurulumEksik("cell/ paketi eksik (test)")

    monkeypatch.setattr(ipd, "scratch_analiz", kurulu_degil)
    r = client.post("/api/ai/vision/scratch", data={"image_base64": _ornek_goruntu_b64(tmp_path)})
    assert r.status_code == 503, r.text
    assert "hazır değil" in r.json()["detail"]


def test_KARSIT_gecersiz_parametreler_422(istemci, tmp_path):
    client, _ = istemci
    b64 = _ornek_goruntu_b64(tmp_path)
    r1 = client.post("/api/ai/vision/scratch", data={"image_base64": b64, "scratch_yonu": "capraz"})
    assert r1.status_code == 422 and "dikey" in r1.json()["detail"]
    r2 = client.post("/api/ai/vision/scratch", data={"image_base64": b64, "xai_method": "scorecam"})
    assert r2.status_code == 422, "xai_method allowlist dışı kabul edildi"
    r3 = client.post("/api/ai/vision/scratch", data={"image_base64": b64, "pixel_mm": "5.0"})
    assert r3.status_code == 422, "pixel_mm sınırı yok"


def test_KRITIK_delegate_STRING_paritesi(istemci, monkeypatch, tmp_path):
    """Mikroservis açıkken alanlar STRING data'yla devredilir (ai_client str()
    tuzağı — plan v2 bulgu 3); explain yalnız true iken eklenir."""
    client, air = istemci
    monkeypatch.setattr(air, "ai_service_enabled", lambda: True)
    yakalanan = {}

    async def sahte_devret(ad, *, file=None, image_base64=None, data=None):
        yakalanan.update(ad=ad, data=data)
        return {"status": "success", "delege": True}

    monkeypatch.setattr(air, "_kapili_devret", sahte_devret)
    b64 = _ornek_goruntu_b64(tmp_path)
    r = client.post(
        "/api/ai/vision/scratch",
        data={"image_base64": b64, "scratch_yonu": "yatay", "pixel_mm": "0.00033", "explain": "true"},
    )
    assert r.status_code == 200 and r.json().get("delege")
    assert yakalanan["ad"] == "scratch"
    assert yakalanan["data"] == {
        "scratch_yonu": "yatay",
        "pixel_mm": "0.00033",
        "xai_method": "eigencam",
        "explain": "true",
    }

    r2 = client.post("/api/ai/vision/scratch", data={"image_base64": b64})
    assert r2.status_code == 200
    assert "explain" not in yakalanan["data"], "explain=false delege data'ya sızdı"


def test_KRITIK_delegate_503_429_AYNEN_gecer(istemci, monkeypatch, tmp_path):
    """Deneysel-kanıtlı bulgu: :8100'ün 503'ü raise_for_status→HTTPStatusError→
    jenerik 500 oluyordu; zarif sözleşme BİRİNCİL (mikroservis) modda kayboluyordu.
    Artık alt-servisin 503/429'u anlamlı mesajla aynen geçer."""
    import httpx

    client, air = istemci
    monkeypatch.setattr(air, "ai_service_enabled", lambda: True)

    def durum_hatasi(kod):
        async def sahte(*a, **k):
            istek = httpx.Request("POST", "http://ai/infer/scratch")
            raise httpx.HTTPStatusError(
                "hata", request=istek, response=httpx.Response(kod, request=istek, json={"error": "x"})
            )

        return sahte

    b64 = _ornek_goruntu_b64(tmp_path)
    monkeypatch.setattr(air, "_kapili_devret", durum_hatasi(503))
    r = client.post("/api/ai/vision/scratch", data={"image_base64": b64})
    assert r.status_code == 503 and "hazır değil" in r.json()["detail"], r.text

    monkeypatch.setattr(air, "_kapili_devret", durum_hatasi(429))
    r2 = client.post("/api/ai/vision/scratch", data={"image_base64": b64})
    assert r2.status_code == 429 and "yeniden deneyin" in r2.json()["detail"], r2.text


def test_KRITIK_mesgul_429_ve_OOM_500_ayrimi(istemci, monkeypatch, tmp_path):
    """Dar eşleme: ScratchMesgul→429; genel RuntimeError (örn. CUDA OOM) 503'e
    DEĞİL jenerik 500'e gider (yanlış 'model paketi gerekli' teşhisi ölçülmüştü)."""
    client, _ = istemci
    import ai_hub.inference_paper_dilek_hoca.inference_paper_dilek_hoca as ipd

    b64 = _ornek_goruntu_b64(tmp_path)
    monkeypatch.setattr(ipd, "scratch_analiz", lambda *a, **k: (_ for _ in ()).throw(ipd.ScratchMesgul("meşgul")))
    r = client.post("/api/ai/vision/scratch", data={"image_base64": b64})
    assert r.status_code == 429, r.text

    monkeypatch.setattr(
        ipd, "scratch_analiz", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA out of memory"))
    )
    r2 = client.post("/api/ai/vision/scratch", data={"image_base64": b64})
    assert r2.status_code == 500, "OOM 503-model-yok sanıldı (yanlış teşhis)"
    assert "hazır değil" not in (r2.json().get("detail") or "")


def test_YAPISAL_dockerfile_cift_cv2_temizligi():
    """requirements-ai'nin şart koştuğu önlem İMAJDA uygulanmalı (yorum yetmez —
    ölçüldü: Dockerfile'da adım yoktu, pin fiilen düşüyordu)."""
    src = (KOK / "docker" / "Dockerfile.ai").read_text(encoding="utf-8")
    assert "pip3 uninstall -y opencv-python-headless" in src
    assert "--force-reinstall --no-deps opencv-python==4.11.0.86" in src
    assert "torch.__version__.startswith('2.7.1')" in src, "torch-ezilme build kanıtı yok"


# ── Yapısal pariteler ────────────────────────────────────────────────────────
def test_YAPISAL_ai_service_scratch_paritesi():
    """:8100 /infer/scratch AYNI scratch_analiz'i çağırır; delegate None-atlama
    kuralı gereği her alan Form(None); kayıpsız .png tmp kullanır."""
    src = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    i = src.index('post("/infer/scratch")')
    govde = src[i : i + 3000]
    assert "scratch_analiz" in govde, ":8100 scratch TEK-KAYNAK fonksiyonu çağırmıyor"
    assert 'scratch_yonu: str = Form(None)' in govde
    assert '_save_temp(data, ".png")' in govde, "ölçüm görüntüsü kayıplı formata yazılıyor"
    assert 'str(explain).lower() == "true"' in govde
    assert "GECERLI_XAI_YONTEMLERI" in govde, "xai_method allowlist paritesi yok"


def test_YAPISAL_jeton_sinifi_AGIR_arastirma():
    """Karar 0.6: scratch 3 jeton (histopath sınıfı) — _islem_turu üzerinden ölçülür."""
    from servers.jeton import MALIYET, _islem_turu

    assert _islem_turu("/api/ai/vision/scratch") == "agir_arastirma"
    assert MALIYET["agir_arastirma"] == 3


def test_YAPISAL_router_kayipsiz_png_ve_503():
    src = (KOK / "servers" / "ai_router.py").read_text(encoding="utf-8")
    i = src.index('"/api/ai/vision/scratch"')
    govde = src[i : i + 4200]
    assert 'suffix=".png"' in govde, "gömülü yol ölçüm görüntüsünü JPEG'e yazıyor"
    assert "status_code=503" in govde and "require_research" in govde
    assert '"pixel_mm": str(pixel_mm)' in govde, "delegate pixel_mm STRING değil"


def test_YAPISAL_scratch_pt_dagitim_karari_KAYITLI():
    """FAZ 4.5 sozlesmesi: iki buyuk PT (renal 858MB + scratch 872MB) ANA profil
    listelerine GIREMEZ (2 GiB — HTTP 422 OLCULDU); dagitimlari PARCALAR
    (research-2.zip, launcher model_parts) uzerindendir + uretim-ani 2GiB bekcisi.
    (Ilk surum yorum-satiri bekcisiydi ve VACUOUS cikmisti — artik VERIYE bakar.)"""
    mz = _mmz()

    BUYUKLER = (
        "ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.pt",
        "ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt",
    )
    for profil, dosyalar in mz.PROFILLER.items():
        for buyuk in BUYUKLER:
            assert buyuk not in dosyalar, f"{buyuk} ANA {profil} listesine girmis (2GiB/422)"
    assert set(BUYUKLER) <= set(mz.PARCALAR["research-2"]), "buyuk PT'ler research-2 parcasinda degil"
    # ad sozlesmesi: <profil>-<n>, profil PROFILLER'de var olmali (launcher etiketleriyle uyum)
    import re as _re

    for ad in mz.PARCALAR:
        m = _re.fullmatch(r"([a-z]+)-(\d+)", ad)
        assert m and m.group(1) in mz.PROFILLER, f"parca adi sozlesme disi: {ad}"
    # uretim-ani siniri: sabit dogru + zip_yaz gercekten denetliyor
    assert mz.GITHUB_ASSET_SINIRI == 2147483648
    src = (KOK / "build_tools" / "make_model_zip.py").read_text(encoding="utf-8")
    zy = src[src.index("def zip_yaz") : src.index("def sha256")]
    assert "GITHUB_ASSET_SINIRI" in zy and "SystemExit" in zy, "2GiB uretim bekcisi zip_yaz'da yok"
    assert zy.index("GITHUB_ASSET_SINIRI") < zy.index("os.replace"), "bekci rename'den SONRA (gec)"


def test_YAPISAL_celldetection_DORT_yuzeyde_pinli():
    """Karar 0.1 (frozen): requirements + myenv + spec + requirements-ai. Eksik yüzey
    = frozen'da sessiz ImportError → 503 (yanlış sınıf) ya da imajda eksik paket."""
    pin = "celldetection==0.4.9"
    assert pin in (KOK / "requirements.txt").read_text(encoding="utf-8")
    assert pin in (KOK / "build_tools" / "myenv-requirements.txt").read_text(encoding="utf-8")
    assert pin in (KOK / "ai_service" / "requirements-ai.txt").read_text(encoding="utf-8")
    spec = (KOK / "build_tools" / "PEMF_Backend_onedir.spec").read_text(encoding="utf-8")
    assert "'celldetection'" in spec, "spec hiddenimports'ta celldetection yok"
    # çift-cv2 tuzağı üç requirements yüzeyinde de NOTLU olmalı (albumentations→headless)
    for dosya in ("requirements.txt", "build_tools/myenv-requirements.txt", "ai_service/requirements-ai.txt"):
        icerik = (KOK / dosya).read_text(encoding="utf-8")
        i = icerik.index("celldetection==")
        assert "headless" in icerik[max(0, i - 900) : i], f"{dosya}: çift-cv2 notu pinin yanında yok"


def test_YAPISAL_warmup_baglantisi():
    """Plan v2 bulgu 12: konteyner açılışında CPN warmup (küresel predictor
    kilidinin ilk-istekte tutulmasına karşı)."""
    src = (KOK / "ai_service" / "app.py").read_text(encoding="utf-8")
    assert "PEMF_SCRATCH_WARMUP" in src and "_ipd.isit" in src
    # CI exit-134 dersi: cell yokken daemon thread HIC baslamamali (find_spec on-kontrolu)
    i = src.index("_scratch_warmup")
    govde = src[i : i + 1600]
    assert 'find_spec("ai_hub.inference_paper_dilek_hoca.cell.cpn")' in govde, (
        "warmup ALT-MODULE bakmali: iskelet cell/ paketi repoda — paket-varligi "
        "yanlis-pozitif olur ve exit-134 yarisi geri gelir"
    )
    assert govde.index("find_spec") < govde.index("threading.Thread"), "on-kontrol thread'den SONRA"
    msrc = (KOK / "ai_hub" / "inference_paper_dilek_hoca" / "inference_paper_dilek_hoca.py").read_text(encoding="utf-8")
    assert "def isit(" in msrc and "with _KILIT:" in msrc[msrc.index("def isit(") :]


def _mmz():
    """make_model_zip'i TEK-ISIM kuralıyla import et (atomik suite'in modül-kimlik
    kapısı — paket-nitelikli import İKİNCİ kimlik doğurur; ölçüldü: kapı patladı)."""
    import sys as _sys

    yol = str(KOK / "build_tools")
    if yol not in _sys.path:
        _sys.path.insert(0, yol)
    import make_model_zip as m

    return m


def test_KRITIK_2gib_bekcisi_DAVRANISSAL(monkeypatch, tmp_path):
    """'Varlık değil UYGULAMA ölç' — yapısal metin-dilimi bekçisi mutasyona dayanmaz
    (eşik '*2' yapılsa yeşil kalırdı). Sınır küçültülüp zip_yaz'ın GERÇEKTEN
    SystemExit verdiği, geçici .tmp'nin silindiği ve hedefin OLUŞMADIĞI ölçülür."""
    mz = _mmz()

    kaynak = tmp_path / "kaynak"
    (kaynak / "ai_hub" / "x").mkdir(parents=True)
    (kaynak / "ai_hub" / "x" / "buyuk.bin").write_bytes(b"B" * 4096)
    monkeypatch.setattr(mz, "KAYNAK", kaynak)
    monkeypatch.setattr(mz, "CIKTI", tmp_path / "cikti")
    monkeypatch.setattr(mz, "GITHUB_ASSET_SINIRI", 1024)  # 4KB dosya > 1KB sinir
    tablo = {"deneme-2": ("ai_hub/x/buyuk.bin",)}
    with pytest.raises(SystemExit, match="bayti asiyor"):
        mz.zip_yaz("deneme-2", tablo)
    assert not (tmp_path / "cikti" / "deneme-2.zip").exists(), "sinir asan paket diske cikti"
    assert not list((tmp_path / "cikti").glob("*.tmp")), "gecici .tmp artigi kaldi"
    # sinir genisken ayni paket UretILIR (bekci yanlis-pozitif degil)
    monkeypatch.setattr(mz, "GITHUB_ASSET_SINIRI", 10_000_000)
    assert mz.zip_yaz("deneme-2", tablo).exists()


def test_YAPISAL_PARCALAR_ile_PARCA_ASSETS_esli():
    """Çapraz-tutarlılık kapısı (düşman-doğrulama): parça yalnız bir tarafa eklenirse
    ya zip üretilir manifest'e girmez (sahaya sessizce inmez) ya da alan yazılır
    dosya hiç üretilmez. İki sözlüğün anahtar kümesi birebir eşleşmeli."""
    import importlib.util

    mz = _mmz()

    spec = importlib.util.spec_from_file_location("mmani", KOK / "scripts" / "make_manifest.py")
    mmani = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mmani)
    zip_taraf = {f"{ad}.zip" for ad in mz.PARCALAR}
    manifest_taraf = set(mmani.PARCA_ASSETS)
    assert zip_taraf == manifest_taraf, (
        f"parça sözlükleri ayrıştı: make_model_zip={zip_taraf} make_manifest={manifest_taraf}"
    )
    # profil eşlemesi de ana PROFILLER'le tutarlı olmalı
    for dosya, (profil, _idx) in mmani.PARCA_ASSETS.items():
        assert profil in mz.PROFILLER, f"{dosya}: bilinmeyen profil {profil}"
        assert dosya.startswith(f"{profil}-"), f"{dosya}: ad sözleşmesi (profil-N.zip) dışı"
