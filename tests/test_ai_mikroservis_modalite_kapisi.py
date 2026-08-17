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

✅ KALAN İŞ 2026-08-17'DE KAPANDI (ilk turda kapsam dışı bırakılmıştı):
(a) **ses ucundaki sessizlik kapısı** artık devretmeden ÖNCE (aşağıdaki üç ses testi).
    ⚠️ İlk turda yazdığım gerekçe YANLIŞTI: "ses hattını yeniden kurgulamak gerekiyor ve bu ortamda
    ffmpeg davranışı doğrulanamıyor" dedim. İkisi de yanlış çıktı — blok ZATEN doğru sıradaydı
    (içerik oku → ffmpeg → RMS), tek yapılması gereken devretme satırını kapının ALTINA indirmekti;
    ve ffmpeg bu makinede VAR (`imageio_ffmpeg.get_ffmpeg_exe()`, PATH'te değil). Ölçüldü:
    ffmpeg 27-31 ms + RMS 2-9 ms.
(b) `:8100`e **doğrudan** çağrılar → `tests/test_ai_servis_8100_kapisi.py`. Kapılar `ai_hub/`e
    TAŞINMADI (coverage/mypy kör noktası olurdu); `utils/` imaja alındı ve `ai_service/app.py`
    AYNI modülü çağırıyor — nesne kimliği testiyle kopyalama YASAKLANDI.
"""

import base64
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
        # `kwv` DEĞERLERİ de tutar: ses ucunda `file` tükendiği için baytların gerçekten
        # geçirildiğini (BOŞ gövde gönderilmediğini) doğrulamak gerekiyor.
        cagrilar.append({"name": name, "kw": sorted(kw.keys()), "kwv": dict(kw)})
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


# ── SES UCU: sessizlik kapısı da devretmeden ÖNCE çalışmalı (2026-08-17, kalan iş kapatıldı) ──

SES = FIXTURE / "10a_KediSesi_mutlu.mp3"


def _sessiz_wav(tmp_path: Path) -> Path:
    """1 sn tam-sessiz 22050 Hz mono 16-bit WAV (~44 KB → 200 bayt alt sınırının ÜSTÜNDE).

    Gerçek bir kayıt dosyası kullanamayız (hepsi sesli); kapının ölçtüğü şey RMS olduğu için
    sıfır örnekli WAV, sahadaki "boş kayıt" vakasının birebir eşdeğeridir (ölçüldü: RMS -inf)."""
    import wave

    p = tmp_path / "sessiz.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 22050)
    assert p.stat().st_size > 200
    return p


def _ffmpeg_var() -> bool:
    """⚠️ PATH'teki `ffmpeg` DEĞİL: uç `imageio_ffmpeg.get_ffmpeg_exe()` kullanıyor."""
    try:
        import imageio_ffmpeg

        return os.path.exists(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return False


@pytest.mark.skipif(not _ffmpeg_var(), reason="imageio_ffmpeg binary yok")
def test_KRITIK_mikroserviste_SESSIZ_kayit_REDDEDILIR(client, mikroservis, tmp_path):
    """Sessiz kayıt → mikroservis modunda da 422; GPU servisine devredilmemeli.

    Sessizlik kapısı ffmpeg WAV'ı gerektirdiği için devretmenin ARDINDA kalmıştı: mikroservis
    modunda boş bir kayıt için model "duygu" döndürüyordu — kapının var olma sebebi olan
    2026-08-15 saha vakası (sahip boş kaydı analiz edince "Resting %16,7" alıyordu)."""
    p = _sessiz_wav(tmp_path)
    with p.open("rb") as f:
        r = client.post("/api/ai/sound/cat", files={"file": (p.name, f, "audio/wav")})

    assert r.status_code == 422, f"mikroservis modunda SESSIZLIK kapisi ATLANDI (HTTP {r.status_code}): {r.text[:200]}"
    assert "sessiz" in r.text.lower(), f"reddin sebebi soylenmedi: {r.text[:200]}"
    assert not mikroservis, f"kapi reddetmesine ragmen GPU servisine devredildi: {mikroservis}"


@pytest.mark.skipif(not SES.exists() or not _ffmpeg_var(), reason="ses fixture'i / ffmpeg yok")
def test_KRITIK_mikroserviste_GERCEK_kayit_hala_DEVREDILIR_karsit_kanit(client, mikroservis):
    """Karşıt-kanıt: düzeltme "her şeyi reddet"e dönüşmemeli VE baytlar gerçekten geçmeli.

    ⚠️ Asıl tuzak burada: kapı `file`'ı TÜKETİYOR. Devretmede `file=file` bırakılırsa uzak servise
    BOŞ gövde gider ve hata "başarılı analiz" gibi görünür. Bu yüzden gönderilen bayt sayısı
    dosyanın kendisiyle birebir karşılaştırılır."""
    ham = SES.read_bytes()
    with SES.open("rb") as f:
        r = client.post("/api/ai/sound/cat", files={"file": (SES.name, f, "audio/mpeg")})

    assert r.status_code == 200, f"gercek kayit reddedildi: {r.text[:200]}"
    assert mikroservis and mikroservis[0]["name"] == "sound", (
        f"gercek kayit GPU servisine devredilmedi → mikroservis modu bozuldu: {mikroservis}"
    )
    b64 = mikroservis[0]["kwv"].get("audio_base64")
    assert b64, f"audio_base64 gecirilmedi (file tukenmis olabilir): {mikroservis[0]['kw']}"
    assert len(base64.b64decode(b64)) == len(ham), (
        "devredilen bayt sayisi dosyayla AYNI DEGIL → tukenmis UploadFile'dan BOS/eksik govde gitti"
    )


@pytest.mark.skipif(not _ffmpeg_var(), reason="imageio_ffmpeg binary yok")
def test_GOMULU_mod_sessizlik_karsit_kanit(client, api, monkeypatch, tmp_path):
    """Karşıt-kanıt: mikroservis KAPALIYKEN sessizlik kapısı davranışı hiç değişmemeli."""
    monkeypatch.setattr(api, "ai_service_enabled", lambda: False)
    p = _sessiz_wav(tmp_path)
    with p.open("rb") as f:
        r = client.post("/api/ai/sound/cat", files={"file": (p.name, f, "audio/wav")})
    assert r.status_code == 422, f"gomulu modda sessizlik kapisi bozuldu: {r.text[:200]}"


def test_HICBIR_uc_kapidan_ONCE_devretmez_yapisal():
    """Yapısal kapı: `delegate_infer(...)` satırı, o ucun modalite kapısından ÖNCE gelmemeli.

    ⚠️ Yorum satırları atılır — kusuru AÇIKLAYAN bir yorum düzeltme sanılmasın, doğru deseni
    anlatan bir yorumla da kapı geçilemesin.
    ⚠️ SES UCU 2026-08-17'de KAPSAMA ALINDI: onun kapısı `_decode_image` değil `ses_sessiz_mi`.
    Kapı artık uç→kapı-dizesi haritası kullanıyor; tek bir dizeye bakan hâli sesi görmezdi.
    ⚠️ RNA ucu hâlâ kapsam dışı — CSV girdisinin modalite kapısı yok, olması da beklenmiyor.
    """
    src = (KOK / "servers" / "ai_router.py").read_text(encoding="utf-8")

    # ⚠️ `#` YORUMLARI ATMAK YETMEZ: DOCSTRING'ler de atılmalı. Bu kapı ilk yazımda kendi
    # açıklama docstring'imdeki `delegate_infer(...)` örneğini kusur sandı. Kapı yalnız GERÇEKTEN
    # YÜRÜTÜLEN satırlara bakmalı; aksi halde hem yanlış alarm verir hem de "doğru deseni anlatan
    # bir docstring yazarak" geçilebilirdi.
    # ⚠️ EK SERTLEŞTİRME (2026-08-17): SATIR-SONU yorumları da soyulur. Eskiden yalnız `#` ile
    # BAŞLAYAN satır atılıyordu, dolayısıyla `devret()  # ses_sessiz_mi(...) burada` yazan tek bir
    # satır kapıyı SAHTE-YEŞİL yapabilirdi. (Bu depoda "yorum kapıyı kandırdı" hatası üç kez oldu.)
    # Not: dosyada docstring sınırlayıcısı olarak yalnız `\"\"\"` kullanılıyor (teyit edildi);
    # `'''` kullanılmaya başlanırsa bu soyucunun kör noktası olur.
    kod, docstring_icinde = [], False
    for satir in src.splitlines():
        s_ = satir.strip()
        if s_.count('"""') == 1:
            docstring_icinde = not docstring_icinde
            continue
        if docstring_icinde or s_.startswith("#") or s_.startswith('"""'):
            continue
        kod.append(satir.split("#")[0])

    # Uç adı → o ucun kapı dizesi. Adı bu haritada olmayan uçlar `_decode_image` varsayar.
    KAPI_DIZESI = {"sound": "ses_sessiz_mi("}

    hatali = []
    for i, satir in enumerate(kod):
        if "delegate_infer(" not in satir or "_kapili_devret" in satir:
            continue
        _ad = next((a for a in KAPI_DIZESI if f'"{a}"' in satir or f"'{a}'" in satir), None)
        kapi = KAPI_DIZESI.get(_ad, "_decode_image(")
        # ⚠️ SABİT PENCERE KULLANMA. İlk yazımda 8 satırlık pencere vardı ve `em_petri`'yi KAÇIRDI:
        # onun `_decode_image` çağrısı devretmeden ~12 satır sonra geliyordu (arada `plausibility`
        # kontrolü var). Artık devretme satırından **o fonksiyonun sonuna kadar** aranır: sonraki
        # `async def`/`def` satırı sınırdır. Yanlış-yeşil veren bir kapı, kapı olmamasından kötüdür.
        # ⚠️ SINIR MODÜL DÜZEYİNDE OLMALI (lstrip YOK). İlk yazımda `kod[j].lstrip()` kullanılıyordu
        # ve İÇ İÇE `def` fonksiyon sonu sanılıyordu: `analyze_cat_sound` içindeki
        # `def _load_cat_sound():` penceresi erken kapatıyor, `ses_sessiz_mi` kapısı pencerenin
        # DIŞINDA kalıyordu → mutasyon (devretmeyi ilk satıra taşımak) bu kapıdan SESSİZCE geçti
        # (ölçüldü). Yanlış-yeşil bir kapı, kapı olmamasından kötüdür.
        son = len(kod)
        for j in range(i + 1, len(kod)):
            if kod[j].startswith(("async def ", "def ", "@ai_router.")):
                son = j
                break
        if kapi in " ".join(kod[i + 1 : son]):
            hatali.append(f"{satir.strip()[:80]}  (kapi: {kapi})")

    assert not hatali, (
        "Bu uclar kendi kapisindan ONCE GPU servisine devrediyor "
        f"(kapi ARKADA kaliyor, mikroservis modunda hic calismiyor): {hatali}"
    )


def test_yapisal_kapi_SES_ucunu_GERCEKTEN_denetliyor_karsit_kanit():
    """Karşıt-kanıt: yukarıdaki kapının ses ucunu görmezden GELMEDİĞİNİN kanıtı.

    Kapı bir haritaya dayandığı için sessizce kapsam dışı kalabilir (uç adı değişirse
    `_decode_image` varsayılanına düşer ve ses ucu HİÇ denetlenmez). Bu test hem haritanın
    kullanıldığını hem de ses kapısının kaynakta gerçekten var olduğunu bağımsız doğrular.

    ⚠️ AST TABANLI (denetim 2026-08-17). İlk yazımda HAM metin üzerinde `in`/`index` kullanıyordu:
    kusuru açıklayan (ya da doğru deseni anlatan) bir yorum/docstring kapıyı geçirebiliyordu.
    ⚠️ EK İDDİA: çağrı bir `if` KOŞULUNDA olmalı. Kardeş SIRA kapısı ters mantıklıdır (devretme
    satırından sonra kapı ARANIR), dolayısıyla kapının TAM SİLİNMESİNİ o yakalayamaz — burada
    `assert ses` ve `assert kosulda` tam o boşluğu kapatıyor.
    """
    import ast

    agac = ast.parse((KOK / "servers" / "ai_router.py").read_text(encoding="utf-8"))

    ses = [
        d.lineno
        for d in ast.walk(agac)
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "ses_sessiz_mi"
    ]
    devret = [
        d.lineno
        for d in ast.walk(agac)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "delegate_infer"
        and d.args
        and isinstance(d.args[0], ast.Constant)
        and d.args[0].value == "sound"
    ]

    assert ses, "sessizlik kapisi (ses_sessiz_mi cagrisi) KAYNAKTAN KAYBOLMUS -> ses ucu kapisiz"
    assert devret, "ses ucu artik 'sound' adiyla devretmiyor -> kapi haritasi BAYAT"
    assert min(ses) < min(devret), (
        "kaynakta sessizlik kapisi devretmeden SONRA geliyor -> mikroservis modunda HIC calismaz"
    )

    kosulda = any(
        isinstance(d, ast.If)
        and any(
            isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "ses_sessiz_mi"
            for x in ast.walk(d.test)
        )
        for d in ast.walk(agac)
    )
    assert kosulda, "ses_sessiz_mi cagrisi bir kosulda DEGIL -> olcum yapiliyor ama KARAR verilmiyor"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
