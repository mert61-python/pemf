# -*- coding: utf-8 -*-
"""4B-1.5 — ücretlendirme AÇIKKEN kimliği çözülemeyen (jetonsuz / `sub`'sız) AI analiz isteği, bağlantı VARKEN bile "çevrimdışı" yoluna
düşüp İZİN alıyor ve deftere SAHİPSİZ kayıt yazıyor. D4.23 eki uzlaştırmayı kayıt sahibine bağladı ve "kimliği çözülemeyen jetonla
UZLAŞTIRILMAZ" dedi → bu kayıtlar HİÇBİR ZAMAN düşülmez (Y24 "geriye dönük düşüm" olmaz: bedava analiz) ama cihaz-geneli
`OFFLINE_TAVAN` sayımına GİRER → tavan dolunca cihazdaki HER kullanıcının (kendi bekleyeni 0 olsa bile) çevrimdışı analizi KALICI 402;
ileti "internete bağlanınca devam edersiniz" der, bağlanmak çözmez. Aynı anda bakiyesi 0 olan GİRİŞ YAPMIŞ kullanıcı reddedilir.

Ölçüm: GERÇEK `_jeton_kapisi_karari` + GERÇEK `_bakiye_satiri_oku` (Supabase "erişilebilir": `get_secret` + `requests.post` SAHTE; canlı YOK).

2026-10-19 (S-4B.5 + S-4BI.8): çevrimdışı analiz ve cihaz-geneli çevrimdışı tavan KALDIRILDI — internetsiz kimlikli istek de 402
(`cevrimdisi`). Kimliksiz isteğin hiçbir cihaz-geneli durumu (defter / sayaç) değiştirmediği ve tedavi uçlarının serbestliği AYNEN ölçülür.
"""

from __future__ import annotations

import base64
import importlib
import json

import pytest
from fastapi import HTTPException


def _jwt(sub: str | None) -> str:
    govde = {"sub": sub, "role": "authenticated"} if sub else {"role": "authenticated"}
    b = base64.urlsafe_b64encode(json.dumps(govde).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.imza"


class _Istek:
    def __init__(self, token: str | None, yol: str = "/api/ai/vision/wound"):
        self.headers = {"authorization": f"Bearer {token}"} if token else {}
        self.url = type("U", (), {"path": yol})()


@pytest.fixture
def j(tmp_path, monkeypatch):
    veri = tmp_path / "veri"
    veri.mkdir()
    monkeypatch.setenv("PEMF_DATA_DIR", str(veri))
    mod = importlib.import_module("servers.jeton")
    monkeypatch.setattr(mod, "JETON_ENFORCED", True)
    monkeypatch.setattr(mod, "_son_uzlastirma", None, raising=False)
    yield mod
    t = getattr(mod, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


@pytest.fixture
def supabase_erisilebilir(monkeypatch):
    """Supabase ERİŞİLEBİLİR: geçerli jetonla bakiye satırı 0 (ön ödemeli, hakkı bitmiş) döner. Ağ YOK (requests.post sahte)."""
    import requests
    import utils.secrets_manager as sm

    monkeypatch.setattr(
        sm, "get_secret",
        lambda ad, default="", generate=False: {"supabase_url": "http://sahte.invalid", "supabase_anon_key": "anon-sahte"}.get(ad, default),
    )  # fmt: skip
    cagri = []

    class _Yanit:
        ok, status_code = True, 200
        content = b'[{"aylik_hak": 0, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}]'

        def raise_for_status(self):
            return None

        def json(self):
            return json.loads(self.content)

    class _Red(_Yanit):
        ok, status_code, content = False, 401, b'{"message": "invalid JWT"}'

        def raise_for_status(self):
            raise requests.HTTPError("401 invalid JWT")

    def _post(url, headers=None, **k):
        cagri.append(url)
        token = ((headers or {}).get("Authorization") or "")[7:]
        try:  # gerçek Supabase: imzası/`sub`'u geçersiz jeton 401 (burada: `sub` taşımayan jeton geçersiz sayılır)
            govde = token.split(".")[1]
            gecerli = bool(json.loads(base64.urlsafe_b64decode(govde + "=" * (-len(govde) % 4))).get("sub"))
        except Exception:
            gecerli = False
        return _Yanit() if gecerli else _Red()

    monkeypatch.setattr(requests, "post", _post)
    return cagri


def _defter(j) -> list:
    yol = j._defter_yolu()
    return json.loads(yol.read_text(encoding="utf-8") or "[]") if yol.exists() else []


_SON_DETAY: dict = {}


def _sonuc(j, istek) -> str:
    try:
        j._jeton_kapisi_karari(istek)
        return "izin"
    except HTTPException as e:
        _SON_DETAY["detay"] = str(e.detail)
        return f"{e.status_code}"


@pytest.mark.parametrize("token", [None, _jwt(None)], ids=["jetonsuz", "sub_siz_jeton"])
def test_KRITIK_kimliksiz_istek_BEDAVA_analiz_ve_SAHIPSIZ_kayit_URETMEZ(j, supabase_erisilebilir, token):
    sonuc = _sonuc(j, _Istek(token))
    defter = _defter(j)
    sahipsiz = [k for k in defter if not k.get("sahip")]
    assert not sahipsiz, (
        f"ücretlendirme AÇIK, Supabase erişilebilir: kimliksiz analiz isteği ({sonuc}) deftere {len(sahipsiz)} SAHİPSİZ kayıt yazdı — "
        "hiçbir hesaptan düşülmez (bedava) ama cihaz-geneli çevrimdışı tavanı doldurur"
    )
    if sonuc == "izin":
        tuket = [u for u in supabase_erisilebilir if u.endswith("/rpc/jeton_tuket")]
        assert defter or tuket, (
            "kimliksiz analiz İZİN aldı ama ne deftere ne sunucuya bir tüketim izi düştü — BEDAVA analiz"
        )
    else:
        assert "ETKİLENMEZ" in _SON_DETAY.get("detay", ""), (
            f"402 iletisi tedavinin etkilenmediğini söylemiyor: {_SON_DETAY}"
        )


def test_KRITIK_kimliksiz_istekler_GIRIS_YAPMIS_kullanicinin_analizini_KILITLEMEZ(
    j, supabase_erisilebilir, monkeypatch
):
    for _ in range(3):
        assert _sonuc(j, _Istek(None)) == "402"
    assert _defter(j) == [], f"kimliksiz istekler cihaz defterine iz bıraktı: {_defter(j)}"
    b = _jwt("kullanici-B")
    monkeypatch.setattr(
        j,
        "_bakiye_satiri_oku",
        lambda _t: {"aylik_hak": 1, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0},
    )
    assert _sonuc(j, _Istek(b)) == "izin", "kimliksiz istekler giriş yapmış B'nin (bakiye 1) analizini kilitledi"


def test_KRITIK_giris_yapmis_kullanici_INTERNETSIZ_402_cevrimdisi_ve_kayit_YOK_S4B5(j, monkeypatch):
    """S-4B.5 (2026-10-19): eskiden internetsiz kimlikli istek İZİN + sahipli defter kaydı alıyordu; artık 402 ve kayıt YOK."""
    monkeypatch.setattr(j, "_bakiye_satiri_oku", lambda _t: (_ for _ in ()).throw(ConnectionError("ag yok")))
    assert _sonuc(j, _Istek(_jwt("kullanici-A"))) == "402"
    assert "internet gerekir" in _SON_DETAY["detay"] and "ETKİLENMEZ" in _SON_DETAY["detay"], _SON_DETAY
    assert _defter(j) == []


def test_KARSIT_bakiyesi_sifir_giris_yapmis_kullanici_402(j, supabase_erisilebilir):
    assert _sonuc(j, _Istek(_jwt("kullanici-A"))) == "402"


@pytest.mark.parametrize(
    "yol", ["/api/ai/pro/stop", "/api/hardware/emergency_stop", "/api/session/stop", "/api/coil/1/control"]
)
def test_KARSIT_Y8_kimliksiz_istek_serbest_ve_tedavi_uclarinda_KAPILANMAZ(j, supabase_erisilebilir, yol):
    assert _sonuc(j, _Istek(None, yol)) == "izin"
    assert _defter(j) == []


def test_KARSIT_zorlama_KAPALIYKEN_kimliksiz_istek_serbest(j, monkeypatch):
    monkeypatch.setattr(j, "JETON_ENFORCED", False)
    assert _sonuc(j, _Istek(None)) == "izin"
    assert _defter(j) == []
