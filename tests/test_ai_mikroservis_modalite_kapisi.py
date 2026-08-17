# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI MİKROSERVİS MODUNDA MODALİTE KAPISI ATLANIYORDU (yanlış modaliteye "%100 güven").

DENETİM BULGUSU (2026-08-17). Her görüntü ucunda `delegate_infer` çağrısı modalite kapısından
(`_decode_image` → `utils/image_domain.check`) **ÖNCE** dönüyordu:

    if ai_service_enabled():
        return await delegate_infer("histopath", file=file, image_base64=image_base64)
    img = await _decode_image(file, image_base64, label="histopath")   # ← KAPI, ARTIK ULAŞILMAZ

`ai_service/app.py` (730 satır) ne modalite denetimi ne sessizlik kapısı içeriyor ve
`docker/Dockerfile.ai` imaja yalnız `ai_hub/` + `ai_service/` kopyaladığı için `utils/` orada YOK.
Deneysel olarak ölçüldü (gerçek CT fixture'ı → Böbrek Patoloji ucu):

    GÖMÜLÜ mod      (PEMF_AI_SERVICE_URL yok)  →  HTTP 422 "boyalı patoloji preparatı bekliyor"
    MİKROSERVİS mod (PEMF_AI_SERVICE_URL var)  →  HTTP 200 {"top_1_class":"Grade 4","top_1_prob":1.0}

Yani kapının var olma sebebi olan saha vakası (2026-08-06: "CT → Grade 4 · %100") mikroservis
profilinde **birebir geri gelmişti**. Kapsam ~8 uç: landmark, segmentation, thermal,
reticulocytes, em_fantom, kidney_ct, histopath, cat_organ.

⚠️ Deponun KENDİ kuralı bunu yazıyor (`ai_hub/inference_petri_dish/plausibility.py`):
*"denetim ROUTER'da DEĞİL burada durmalı, çünkü `PEMF_AI_SERVICE_URL` tanımlıyken
`servers/ai_router.py` HİÇ çalışmaz."* Petri kapısı bu kurala uyuyor; diğerleri `utils/`te kaldı.

⚠️ SEVK EDİLEN KLİNİKTE ETKİN DEĞİL: `PEMF_AI_SERVICE_URL` tüm depoda yalnız
`docker/docker-compose.micro.yml`de set ediliyor; `deploy/*.env`de yok, launcher geçirmiyor,
`ai_service/README.md` servisi "opsiyoneldir" diye tanımlıyor. Ciddiyet bu yüzden 3.

⚠️ KALAN İŞ (bu düzeltmenin KAPSAMI DIŞINDA, bilerek): (a) **ses ucundaki sessizlik kapısı** hâlâ
devretmeden sonra — kapı ffmpeg transcode + RMS ölçümüne bağlı olduğu için devretmenin önüne almak
ses hattını yeniden kurgulamayı gerektiriyor ve bu ortamda ffmpeg davranışı doğrulanamıyor;
(b) `:8100`e **doğrudan** yapılan çağrılar (backend'i atlayan bir istemci) hâlâ kapısız — deponun
kendi kuralına göre kalıcı çözüm kapıları `ai_hub/`e taşımaktır.
"""

import os
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parent.parent
FIXTURE = KOK / "ai_hub" / "PEMF_AI_Test_Girdileri"
CT = FIXTURE / "07a_BobrekCT_tas.jpg"
PATOLOJI = FIXTURE / "08c_BobrekPatoloji_grade4.jpg"


@pytest.fixture(scope="module")
def api():
    from servers import ai_router

    return ai_router


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


@pytest.fixture()
def mikroservis(api, monkeypatch):
    """Mikroservis modunu AÇ ve `delegate_infer`i CASUSLA (gerçek HTTP yok)."""
    cagrilar = []

    async def _sahte_devret(name, **kw):
        cagrilar.append({"name": name, "kw": sorted(kw.keys())})
        return {"status": "success", "top_1_class": "Grade 4", "top_1_prob": 1.0, "_sahte": True}

    monkeypatch.setattr(api, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(api, "delegate_infer", _sahte_devret)
    return cagrilar


def _gonder(client, uc: str, p: Path):
    """⚠️ `image_base64` bir **Form** alanıdır, JSON gövdesi DEĞİL (uç `File(None)`/`Form(None)`
    ikilisi kullanıyor). İlk denememde `json=` gönderip "Görüntü verisi bulunamadı" ile 500 aldım —
    kapının atlandığını sandım. Mevcut `tests/test_image_domain_guard.py` de multipart kullanıyor."""
    with p.open("rb") as f:
        return client.post(uc, files={"file": (p.name, f, "image/jpeg")})


@pytest.mark.skipif(not CT.exists(), reason="CT fixture yok")
def test_KRITIK_mikroserviste_YANLIS_modalite_REDDEDILIR(client, mikroservis):
    """CT kesiti → Böbrek Patoloji ucu: mikroservis modunda da 422 ile reddedilmeli."""
    r = _gonder(client, "/api/ai/vision/histopath", CT)

    assert r.status_code == 422, (
        f"mikroservis modunda modalite kapisi ATLANDI (HTTP {r.status_code}). "
        f"Kapinin var olma sebebi olan saha vakasi geri geldi: CT kesiti icin 'Grade 4 %100'. "
        f"Yanit: {r.text[:200]}"
    )
    assert not mikroservis, f"kapi reddetmesine ragmen GPU servisine devredildi: {mikroservis}"


@pytest.mark.skipif(not PATOLOJI.exists(), reason="patoloji fixture yok")
def test_KRITIK_DOGRU_modalite_hala_DEVREDILIR_karsit_kanit(client, mikroservis):
    """Karşı-kanıt: düzeltme mikroservis modunu BOZMAMALI — doğru modalite devredilmeli."""
    r = _gonder(client, "/api/ai/vision/histopath", PATOLOJI)

    assert r.status_code == 200, f"dogru modalite reddedildi: {r.text[:200]}"
    assert mikroservis and mikroservis[0]["name"] == "histopath", (
        f"dogru modalite GPU servisine devredilmedi → mikroservis modu bozuldu: {mikroservis}"
    )


@pytest.mark.skipif(not CT.exists(), reason="CT fixture yok")
def test_KRITIK_DOGRU_ucta_CT_devredilir_karsit_kanit(client, mikroservis):
    """Karşı-kanıt: aynı CT görüntüsü DOĞRU ucunda (kidney_ct) devredilmeli.

    Aynı fixture'ın bir uçta reddedilip diğerinde geçmesi, kapının modaliteyi gerçekten ölçtüğünü
    ve düzeltmenin "her şeyi reddet"e dönüşmediğini kanıtlar."""
    r = _gonder(client, "/api/ai/vision/kidney_ct", CT)

    assert r.status_code == 200, f"CT, kidney_ct ucunda reddedildi: {r.text[:200]}"
    assert mikroservis and mikroservis[0]["name"] == "kidney_ct"


def test_GOMULU_mod_etkilenmez_karsit_kanit(client, api, monkeypatch):
    """Karşı-kanıt: mikroservis KAPALIYKEN davranış hiç değişmemeli (kapı zaten çalışıyordu)."""
    monkeypatch.setattr(api, "ai_service_enabled", lambda: False)
    if not CT.exists():
        pytest.skip("CT fixture yok")
    r = _gonder(client, "/api/ai/vision/histopath", CT)
    assert r.status_code == 422, f"gomulu modda kapi bozuldu: {r.text[:200]}"


def test_HICBIR_uc_kapidan_ONCE_devretmez_yapisal():
    """Yapısal kapı: `delegate_infer(...)` satırı, o ucun modalite kapısından ÖNCE gelmemeli.

    ⚠️ Yorum satırları atılır — kusuru AÇIKLAYAN bir yorum düzeltme sanılmasın, doğru deseni
    anlatan bir yorumla da kapı geçilemesin.
    ⚠️ Ses ve RNA uçları BİLEREK kapsam dışı: RNA'nın modalite kapısı yok; sesin sessizlik kapısı
    transcode'a bağlı ve bu düzeltmenin kapsamı dışında (bkz. dosya başlığı).
    """
    src = (KOK / "servers" / "ai_router.py").read_text(encoding="utf-8")

    # ⚠️ `#` YORUMLARI ATMAK YETMEZ: DOCSTRING'ler de atılmalı. Bu kapı ilk yazımda kendi
    # açıklama docstring'imdeki `delegate_infer(...)` örneğini kusur sandı. Kapı yalnız GERÇEKTEN
    # YÜRÜTÜLEN satırlara bakmalı; aksi halde hem yanlış alarm verir hem de "doğru deseni anlatan
    # bir docstring yazarak" geçilebilirdi.
    kod, docstring_icinde = [], False
    for satir in src.splitlines():
        s_ = satir.strip()
        if s_.count('"""') == 1:
            docstring_icinde = not docstring_icinde
            continue
        if docstring_icinde or s_.startswith("#") or s_.startswith('"""'):
            continue
        kod.append(satir)

    hatali = []
    for i, satir in enumerate(kod):
        if "delegate_infer(" not in satir or "_kapili_devret" in satir:
            continue
        # ⚠️ SABİT PENCERE KULLANMA. İlk yazımda 8 satırlık pencere vardı ve `em_petri`'yi KAÇIRDI:
        # onun `_decode_image` çağrısı devretmeden ~12 satır sonra geliyordu (arada `plausibility`
        # kontrolü var). Artık devretme satırından **o fonksiyonun sonuna kadar** aranır: sonraki
        # `async def`/`def` satırı sınırdır. Yanlış-yeşil veren bir kapı, kapı olmamasından kötüdür.
        son = len(kod)
        for j in range(i + 1, len(kod)):
            if kod[j].lstrip().startswith(("async def ", "def ", "@ai_router.")):
                son = j
                break
        if "_decode_image(" in " ".join(kod[i + 1 : son]):
            hatali.append(satir.strip()[:90])

    assert not hatali, (
        "Bu uclar modalite kapisindan ONCE GPU servisine devrediyor "
        f"(kapi ARKADA kaliyor, mikroservis modunda hic calismiyor): {hatali}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
