# Author: mertaygn, cglrgrkn
"""S-SGI.3 (sahip kararı 2026-10-18 "Rezervasyon ekle") — KARAR ↔ TÜKETİM penceresinde eşzamanlı analiz bakiyeyi AŞAMAZ.

Ölçülen boşluk (SGI-2.5, A2): karar analiz başlarken, tüketim teslimde → pencere = analiz süresi. Bakiye 1, eşzamanlı 4 analiz →
4 teslim, 1 düşüldü, 3 deftere "borç"; çevrimdışı tavan 50 (49 dolu), eşzamanlı 4 → defter 53.
SÖZLEŞME:
 · karar anında `kalan − ayrılmış ≥ maliyet` (çevrimiçi: SAHİP başına; çevrimdışı: CİHAZ geneli defter yeri) → fazlası 402;
 · teslim edilmeyen analiz (uç istisnası) ayrımı BIRAKIR — sonraki analiz son jetonu kullanabilir; kesilen istekte ayrım 300 sn'de düşer;
 · tüketim okunan bakiyeye yansımadan (okuma tüketimden ÖNCE başladı) verilen karar o tüketimi yok SAYMAZ;
 · aynı canlı dakika kovası (sunucuda idempotent) ikinci kez ayrılmaz; sıralı analizler eskisi gibi (çifte sayım yok);
 · sunucunun KESİN `yetersiz` cevabı (başka cihaz bakiyeyi bitirdi) deftere "borç" YAZILMAZ; ağ hatası yine deftere (fail-open).
GERÇEK karar gövdesi (`_jeton_on_karari`) / `JetonYoneticisi` / uygulama + `jeton_gate` / `jeton_tuketimi`; sahte yalnız EN ALT katta:
Supabase taşıması (bakiye satırı + `rpc/jeton_tuket` taklidi — `supabase_jetonlar.sql`: satır kilidi, idempotans, `yetersiz`), termal
model, saat. Ömür değerleri DAVRANIŞLA pinlenir (modül sabiti okunmaz).
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
TERMAL = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
KEDI_FOTO = KOK / "ai_hub" / "cat_landmark" / "results" / "00000005_020.jpg"


def _jwt(sub: str) -> str:
    b = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.sahte-imza"


class _Termal:
    def predict(self, yol, threshold=0.5):
        return {"label": "Healthy", "probability_sick": 0.1, "confidence": 0.9}


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_son_uzlastirma", None, raising=False)
    monkeypatch.setattr(j, "_canli_oturumlar", {})
    saat = [5000.0]
    monkeypatch.setattr(j, "time", SimpleNamespace(monotonic=lambda: saat[0], time=lambda: 1.7e9 + saat[0]))
    sunucu = {"bakiye": 1, "defter": set(), "dusulen": [], "cevrimdisi": False, "ag_hatasi": False, "okurken": None}

    def _oku(token):
        if sunucu["cevrimdisi"]:
            raise ConnectionError("çevrimdışı")
        gorulen = sunucu["bakiye"]
        if sunucu["okurken"]:
            f, sunucu["okurken"] = sunucu["okurken"], None
            f()  # okuma sürerken başka analiz tüketir (okuma ESKİ bakiyeyi getirir)
        return {"aylik_hak": 0, "satin_alinan": gorulen, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}

    def _rpc(token, **k):
        if sunucu["ag_hatasi"]:
            return False
        iid = str(k.get("istek_id") or "")
        if iid in sunucu["defter"]:
            return True
        m = int(k.get("miktar") or 0)
        if sunucu["bakiye"] < m:
            return j.TUKETIM_REDDEDILDI  # supabase_jetonlar.sql → {"ok": false, "sebep": "yetersiz"}
        sunucu["bakiye"] -= m
        sunucu["defter"].add(iid)
        sunucu["dusulen"].append(dict(k))
        return True

    monkeypatch.setattr(j, "_bakiye_satiri_oku", _oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", _rpc)
    monkeypatch.setattr(j, "_uzlastirmayi_tetikle", lambda token: False)
    yield SimpleNamespace(j=j, sunucu=sunucu, saat=saat, tmp=tmp_path, monkeypatch=monkeypatch)


def _istek(yol="/api/ai/vision/thermal", sahip="hekim-a", oturum=None):
    h = {"authorization": f"Bearer {_jwt(sahip)}"}
    if oturum:
        h["x-pemf-canli-oturum"] = oturum
    return SimpleNamespace(url=SimpleNamespace(path=yol), headers=h)


def _karar(o, **k):
    """GERÇEK karar gövdesi: tüketici ya da 402."""
    try:
        return o.j._jeton_on_karari(_istek(**k))
    except HTTPException as e:
        assert e.status_code == 402, e.status_code
        return 402


def _defter(o) -> list:
    p = o.j._defter_yolu()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def test_KRITIK_bakiye_1_es_zamanli_4_analiz_YALNIZ_1_izin_ve_deftere_BORC_yok(ortam):
    o = ortam
    kararlar = [_karar(o) for _ in range(4)]  # dördü de analiz sürerken (hiçbiri tüketmeden) karar alır
    assert kararlar[1:] == [402, 402, 402], f"bakiye 1 iken eşzamanlı analizler: {kararlar}"
    kararlar[0]()
    assert o.sunucu["bakiye"] == 0 and len(o.sunucu["dusulen"]) == 1
    assert _defter(o) == [], f"eşzamanlı analizler deftere borç yazdı: {_defter(o)}"


def test_KRITIK_cevrimdisi_tavan_49_dolu_es_zamanli_4_analiz_defter_50yi_ASMAZ(ortam):
    o = ortam
    j = o.j
    o.monkeypatch.setattr(j, "OFFLINE_TAVAN", 50)
    o.sunucu["cevrimdisi"] = True
    j._defter_yolu().write_text(
        json.dumps([{"istek_id": f"eski-{i}", "miktar": 1, "tur": "analiz", "sahip": "x"} for i in range(49)]),
        encoding="utf-8",
    )
    kararlar = [_karar(o) for _ in range(4)]
    assert kararlar[1:] == [402, 402, 402], f"çevrimdışı tavanda eşzamanlı analizler: {kararlar}"
    kararlar[0]()
    assert len(_defter(o)) == 50, len(_defter(o))


def test_KRITIK_teslim_EDILMEYEN_analiz_ayrimi_BIRAKIR_son_jeton_sonraki_analize_kalir(ortam):
    """Uçtan uca: gerçek uygulama + jeton_gate / jeton_tuketimi. Termal kapının 422'si (uç istisnası) → jeton düşmez VE ayrım
    bırakılır; hemen ardından gelen geçerli analiz son jetonla 200 alır."""
    o = ortam
    from servers import ai_router as air
    from servers import api_server

    gercek = air._get_or_load_model
    o.monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: _Termal() if ad == "thermal" else gercek(ad, y))
    o.monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    o.monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    c = TestClient(api_server.app, client=("127.0.0.1", 51238))
    h = {"Authorization": f"Bearer {_jwt('hekim-a')}"}
    r = c.post("/api/ai/vision/thermal", files={"file": ("k.jpg", KEDI_FOTO.read_bytes(), "image/jpeg")}, headers=h)
    assert r.status_code == 422, r.text[:200]
    r2 = c.post("/api/ai/vision/thermal", files={"file": ("k.png", TERMAL.read_bytes(), "image/png")}, headers=h)
    assert r2.status_code == 200, (
        f"başarısız analizin ayrımı sızdı — son jeton kilitlendi: {r2.status_code} {r2.text[:200]}"
    )
    assert o.sunucu["bakiye"] == 0 and len(o.sunucu["dusulen"]) == 1


def test_KRITIK_kesilen_istegin_ayrimi_300_sn_sonra_duser(ortam):
    o = ortam
    assert callable(_karar(o))  # karar alındı, tüketim bağımlılığına hiç gelinmedi (istek kesildi)
    o.saat[0] += 299.0
    assert _karar(o) == 402, "ayrım ömrü dolmadan son jeton ikinci analize verildi"
    o.saat[0] += 2.0
    assert callable(_karar(o)), "kesilen isteğin ayrımı 300 sn sonra da düşmedi — son jeton kalıcı kilitli"


def test_KRITIK_okuma_tuketimden_ONCE_baslamissa_tuketim_YOK_SAYILMAZ(ortam):
    """A kararını aldı; B'nin bakiye okuması başladı (bakiye 1), okuma sürerken A teslim edip tüketti, okuma ESKİ bakiye 1'i getirdi.
    B'nin kararı A'nın tüketimini görmeli (ayrım tüketimden sonra hemen silinseydi B de izin alırdı → bakiye aşımı)."""
    o = ortam
    a = _karar(o)
    assert callable(a)

    def _a_teslim():
        o.saat[0] += 1.0
        a()

    o.sunucu["okurken"] = _a_teslim
    assert _karar(o) == 402, "okuma sürerken tamamlanan tüketim yok sayıldı — bakiye 1 ile iki analiz"
    assert o.sunucu["bakiye"] == 0


def test_KARSIT_sirali_analizler_CIFTE_sayilmaz_bakiye_3_uc_analiz_dorduncu_402(ortam):
    o = ortam
    o.sunucu["bakiye"] = 3
    for _ in range(3):
        t = _karar(o)
        assert callable(t), "sıralı analiz (önceki teslim edildi) tüketilmiş ayrımla ÇİFTE sayıldı"
        o.saat[0] += 0.5
        t()
        o.saat[0] += 0.5
    assert _karar(o) == 402 and o.sunucu["bakiye"] == 0


def test_KARSIT_ayni_canli_dakika_kovasi_ikinci_kez_AYRILMAZ_ve_baska_hesap_etkilenmez(ortam):
    o = ortam
    oturum = "canli-sgi3-0001abcd"
    a = _karar(o, oturum=oturum)
    b = _karar(o, oturum=oturum)  # aynı kova, A henüz teslim edilmedi (sunucuda aynı istek_id → idempotent)
    assert callable(a) and callable(b), "aynı canlı dakikanın ikinci karesi bakiye 1'de 402 aldı"
    a()
    b()
    assert o.sunucu["bakiye"] == 0 and len(o.sunucu["dusulen"]) == 1
    o.sunucu["bakiye"] = 1
    assert callable(_karar(o, sahip="hekim-b")), "bir hesabın ayrımı başka hesabın bakiyesinden düşüldü"


def test_KRITIK_sunucu_KESIN_yetersiz_deftere_BORC_yazilmaz_ag_hatasi_yine_deftere(ortam):
    """Başka cihaz (aynı hesap) bakiyeyi bitirdi: karar bakiye 1 gördü, tüketimde sunucu `yetersiz` der → borç YOK. Ağ hatasında
    kayıt yine deftere (fail-open — çevrimdışı uzlaştırma, Y24)."""
    o = ortam
    t = _karar(o)
    o.sunucu["bakiye"] = 0  # başka cihaz harcadı
    k = t()
    assert _defter(o) == [], f"sunucunun kesin reddi deftere borç yazıldı: {_defter(o)}"
    assert k.jeton_harcandi == 0, k
    o.sunucu["bakiye"] = 1
    o.sunucu["ag_hatasi"] = True
    _karar(o)()
    assert len(_defter(o)) == 1, "ağ hatasında tüketim deftere düşmedi (fail-open bozuldu)"


def test_KARSIT_kesin_red_UZLASTIRMADA_kaydi_SILMEZ_Y24(ortam):
    """Çevrimdışı defterdeki kayıt uzlaştırmada `yetersiz` alırsa KALIR (bakiye yüklenince geriye dönük düşer — Y24)."""
    o = ortam
    j = o.j
    o.sunucu["bakiye"] = 0
    j._defter_yolu().write_text(
        json.dumps(
            [
                {
                    "istek_id": "cd-1",
                    "miktar": 1,
                    "tur": "analiz",
                    "detay": "goruntu",
                    "sahip": j._jwt_sahip(_jwt("hekim-a")),
                }
            ]
        ),
        encoding="utf-8",
    )
    y = j._defter_yoneticisi(lambda **k: j._tuketim_gonder_canli("t", **k), sahip=j._jwt_sahip(_jwt("hekim-a")))
    assert y.bekleyenleri_uzlastir() == 0
    assert len(_defter(o)) == 1


@pytest.mark.parametrize(
    ("durum", "govde", "beklenen"),
    [
        (200, {"ok": False, "sebep": "yetersiz", "kalan": 0}, "KESIN_RED"),
        (200, {"ok": True, "kalan": 4}, True),
        (200, {"ok": True, "kalan": 4, "tekrar": True}, True),
        (200, {"ok": False, "sebep": "auth"}, False),
        (503, {"message": "upstream"}, False),
    ],
)
def test_KRITIK_GERCEK_rpc_tasimasi_yalniz_YETERSIZ_cevabini_kesin_red_sayar(monkeypatch, durum, govde, beklenen):
    """Gerçek `_tuketim_gonder_canli` (sahte yalnız `requests.post` + `get_secret`): `{"ok": false, "sebep": "yetersiz"}` →
    kesin red (deftere yazılmaz); başarı → True; başka red / HTTP hatası → False (deftere, fail-open)."""
    import requests
    import utils.secrets_manager as sm

    j = importlib.import_module("servers.jeton")
    monkeypatch.setattr(
        sm, "get_secret",
        lambda ad, default="", generate=False: {"supabase_url": "http://sahte.invalid", "supabase_anon_key": "anon-sahte"}.get(ad, default),
    )  # fmt: skip

    class _Yanit:
        ok = 200 <= durum < 300
        status_code = durum
        content = json.dumps(govde).encode()

        def json(self):
            return govde

    monkeypatch.setattr(requests, "post", lambda url, **k: _Yanit())
    sonuc = j._tuketim_gonder_canli("jeton", miktar=1, tur="analiz", detay="goruntu", istek_id="i-1", cihaz_id=None)
    if beklenen == "KESIN_RED":
        assert sonuc is j.TUKETIM_REDDEDILDI and not sonuc, sonuc
    else:
        assert sonuc is beklenen, sonuc


def test_KRITIK_SONUCSUZ_canli_kare_ayrimi_BIRAKIR_son_jeton_elle_analize_kalir(ortam):
    """Uçtan uca: canlı segmentasyon karesinde kedi YOK (bilgi yanıtı 200, TD9: dakika ücretlenmez) → ayrım bırakılır; bakiye 1 ile
    hemen ardından gelen elle termal analiz 200 alır."""
    import cv2
    import numpy as np

    o = ortam
    from servers import ai_router as air
    from servers import api_server

    class _Seg:
        def predict(self, **k):
            return [SimpleNamespace(boxes=[], masks=None)]

    gercek = air._get_or_load_model
    o.monkeypatch.setattr(
        air,
        "_get_or_load_model",
        lambda ad, y: _Termal() if ad == "thermal" else (_Seg() if ad == "seg" else gercek(ad, y)),
    )
    o.monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    o.monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    rng = np.random.default_rng(7)
    oda = np.zeros((240, 320, 3), np.float32)
    oda[:] = (150, 165, 185)
    cv2.rectangle(oda, (40, 60), (200, 200), (90, 110, 140), -1)
    oda = cv2.imencode(".jpg", np.clip(oda + rng.normal(0, 6, oda.shape), 0, 255).astype(np.uint8))[1].tobytes()
    c = TestClient(api_server.app, client=("127.0.0.1", 51239))
    h = {"Authorization": f"Bearer {_jwt('hekim-a')}"}
    r = c.post(
        "/api/ai/vision/segmentation",
        files={"file": ("k.jpg", oda, "image/jpeg")},
        headers={**h, "X-PEMF-Canli-Oturum": "canli-sgi3-sonucsuz01"},
    )
    assert r.status_code == 200 and r.json()["cat_count"] == 0, r.text[:200]
    r2 = c.post("/api/ai/vision/thermal", files={"file": ("k.png", TERMAL.read_bytes(), "image/png")}, headers=h)
    assert r2.status_code == 200, f"sonuçsuz canlı karenin ayrımı sızdı — son jeton kilitlendi: {r2.status_code}"
    assert o.sunucu["bakiye"] == 0 and [k["detay"] for k in o.sunucu["dusulen"]] == ["goruntu"], o.sunucu["dusulen"]


def test_KRITIK_KOPAN_istemcinin_ayrimi_BIRAKILIR(ortam):
    """Gerçek `jeton_tuketimi` (yield bağımlılığı) — istemci yanıtı beklemeden koptu: jeton düşmez VE ayrım bırakılır."""
    import asyncio

    o = ortam
    t = _karar(o)
    assert callable(t)

    async def _koptu():
        return True

    istek = SimpleNamespace(
        state=SimpleNamespace(**{o.j._BEKLEYEN_TUKETIM: t}),
        url=SimpleNamespace(path="/api/ai/vision/thermal"),
        is_disconnected=_koptu,
    )

    async def _kos():
        g = o.j.jeton_tuketimi(istek)
        await g.__anext__()
        with pytest.raises(StopAsyncIteration):
            await g.__anext__()

    asyncio.run(_kos())
    assert o.sunucu["dusulen"] == [] and o.sunucu["bakiye"] == 1
    assert callable(_karar(o)), "kopan istemcinin ayrımı sızdı — son jeton kilitlendi"
