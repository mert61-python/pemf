# Author: mertaygn, cglrgrkn
"""KP-1 · apps/backend/servers/api_server.py · sözleşmeler: İTHAL ANI dağıtım profili kararları (KP1-IA.3 — TUR 1'de "DONMUS /
yeniden yükleme yasak" ADAY'ı sayılmıştı; çürütüldü) — `PEMF_ENABLE_DOCS` 0/1 kesin karar verir (auth / tünelden bağımsız), boşsa
auth zorunlu YA DA tünel açıkken /docs KAPALI, yerel geliştirmede açık; `PEMF_CORS_ORIGINS` "*" açık opt-in, virgüllü liste
kırpılır / boşlar atılır, boşsa LAN düzenli ifadesi; `PEMF_ALLOWED_HOSTS` "auto,…" → DNS-rebind koruma ara katmanı (ekstra adlar
küçük harf), liste → `TrustedHostMiddleware`; bozuk `PEMF_RATELIMIT_REMOTE_PER_MIN` → 600 varsayılanı; eksik paketli yapıda
(`headless_core` yok) geri-düşüş tanımları (None, `get_patient_database()` None); süre kapağı kancası bağlanamazsa "D1.68" uyarısı;
paketlenmiş simülatör / arayüz `OnbellekPolitikaliStatik` ile mount, arayüz yoksa mount YOK + uyarı.

Teknik: modül YENİDEN YÜKLENMEZ (sys.modules silme yok). İlgili üst düzey deyimler ürünün KENDİ kaynağından GERÇEK satır
numaralarıyla derlenir ve modül globallerinin KOPYASINDA koşar (canlı `app` ve modül durumu değişmez). Sahte EN ALT katta: yalnız
kopya ad alanında `app` (add_middleware / mount kaydedici), `packaged_resource_path` (tmp); ortam `monkeypatch.setenv`;
`sys.modules["headless_core"] = None` (üst paketi yok; monkeypatch geri koyar); `hardware_controller.sure_doldu_kancasi_bagla`
özniteliği yok (uyumsuz eski HC; monkeypatch geri koyar).
"""

from __future__ import annotations

import ast
import functools
import logging
import sys
from pathlib import Path

import pytest


def _log(caplog):
    return [r.getMessage() for r in caplog.records]


@functools.lru_cache(maxsize=1)
def _agac(dosya: str):
    kaynak = Path(dosya).read_text(encoding="utf-8")
    satirlar = kaynak.splitlines()
    govde = ast.parse(kaynak, filename=dosya).body
    metin = ["\n".join(satirlar[d.lineno - 1 : d.end_lineno]) for d in govde]
    return govde, metin


def _ust_duzey(a, isaret: str, adet: int = 1):
    """Kaynakta `isaret`i içeren İLK üst düzey deyim + sonraki `adet-1` deyim → GERÇEK satır numaralı kod nesnesi."""
    govde, metin = _agac(a.__file__)
    for i, m in enumerate(metin):
        if isaret in m:
            return compile(ast.Module(body=govde[i : i + adet], type_ignores=[]), a.__file__, "exec", dont_inherit=True)
    raise AssertionError(f"api_server kaynağında yok: {isaret}")


class _App:
    """Kopya ad alanındaki `app` yerine: ara katman / mount kayıtlarını tutar (canlı uygulamaya dokunulmaz)."""

    def __init__(self):
        self.cagri: list = []

    def add_middleware(self, sinif, **k):
        self.cagri.append(("mw", sinif, k))

    def mount(self, yol, app=None, name=None):
        self.cagri.append(("mount", yol, type(app).__name__, getattr(app, "directory", None), name))


def _kos(a, isaret, adet=1, **ek):
    ad_alani = dict(vars(a))
    ad_alani.update(ek)
    exec(_ust_duzey(a, isaret, adet), ad_alani)  # noqa: S102 — ürünün KENDİ kaynağı, kopya ad alanında
    return ad_alani


@pytest.mark.parametrize(
    ("docs", "auth", "tunel", "beklenen"),
    [
        ("0", "0", "0", False),  # açık 0 → yerel geliştirmede bile KAPALI
        ("1", "1", "1", True),  # açık 1 → auth + tünel açıkken bile AÇIK
        (" 1 ", "0", "0", True),  # kırpılır
        ("", "1", "0", False),  # boş + auth zorunlu → KAPALI
        ("", "0", "1", False),  # boş + tünel açık (internete açık yüzey) → KAPALI
        ("", "0", "0", True),  # boş + yerel geliştirme → AÇIK
        ("evet", "0", "0", True),  # 0/1 dışı değer = boş gibi (varsayılan kural)
    ],
)
def test_ITHAL_ANI_PEMF_ENABLE_DOCS_kararlari(monkeypatch, docs, auth, tunel, beklenen):
    """PEMF_ENABLE_DOCS "0"/"1" (kırpılmış) → kesin karar (auth / tünelden bağımsız); başka değer → auth zorunlu YA DA tünel açıksa
    /docs KAPALI, ikisi de kapalıysa AÇIK (api_server.py:143-147)."""
    from servers import api_server as a

    monkeypatch.setenv("PEMF_ENABLE_DOCS", docs)
    monkeypatch.setenv("PEMF_REQUIRE_AUTH", auth)
    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", tunel)
    assert _kos(a, '_docs_env = os.getenv("PEMF_ENABLE_DOCS"', 2)["_docs_enabled"] is beklenen


@pytest.mark.parametrize(
    ("deger", "beklenen"),
    [
        ("*", {"allow_origins": ["*"]}),
        (" https://a.ornek , https://b.ornek ,", {"allow_origins": ["https://a.ornek", "https://b.ornek"]}),
        ("", None),  # None → LAN düzenli ifadesi (aşağıda modülün kendi sabitiyle)
    ],
)
def test_ITHAL_ANI_PEMF_CORS_ORIGINS_yildiz_liste_ve_LAN_varsayilani(monkeypatch, deger, beklenen):
    """PEMF_CORS_ORIGINS "*" → açık opt-in `["*"]`; virgüllü liste → kırpılmış, boşları atılmış liste; boş → açık köken YOK +
    `_LAN_ORIGIN_REGEX` (api_server.py:268-274)."""
    from servers import api_server as a

    monkeypatch.setenv("PEMF_CORS_ORIGINS", deger)
    if beklenen is None:
        beklenen = {"allow_origins": [], "allow_origin_regex": a._LAN_ORIGIN_REGEX}
    assert _kos(a, '_cors_env = os.getenv("PEMF_CORS_ORIGINS"', 2)["_cors_kwargs"] == beklenen


def test_ITHAL_ANI_PEMF_ALLOWED_HOSTS_auto_ve_liste_ara_katmani(monkeypatch):
    """ "auto,Klinik.Local" → `_RebindKorumaMiddleware(ekstra=("klinik.local",))`; "a.ornek,b.ornek" → `TrustedHostMiddleware`
    (allowed_hosts listesi); "*" → ara katman EKLENMEZ (api_server.py:413-419)."""
    from servers import api_server as a
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    isaret = '_allowed_hosts_secimi(os.getenv("PEMF_ALLOWED_HOSTS"'
    monkeypatch.setenv("PEMF_ALLOWED_HOSTS", "auto,Klinik.Local")
    app = _App()
    _kos(a, isaret, 2, app=app)
    assert app.cagri == [("mw", a._RebindKorumaMiddleware, {"ekstra": ("klinik.local",)})]
    monkeypatch.setenv("PEMF_ALLOWED_HOSTS", "a.ornek,b.ornek")
    app = _App()
    _kos(a, isaret, 2, app=app)
    assert app.cagri == [("mw", TrustedHostMiddleware, {"allowed_hosts": ["a.ornek", "b.ornek"]})]
    monkeypatch.setenv("PEMF_ALLOWED_HOSTS", "*")
    app = _App()
    _kos(a, isaret, 2, app=app)
    assert app.cagri == []


@pytest.mark.parametrize(("deger", "beklenen"), [("abc", 600), ("", 600), ("42", 42), ("0", 0)])
def test_ITHAL_ANI_bozuk_hiz_siniri_600_varsayilanina_duser(monkeypatch, deger, beklenen):
    """PEMF_RATELIMIT_REMOTE_PER_MIN sayı değil / boş → 600; sayı → aynen (0 = kapalı, uydurulmaz) (api_server.py:589-592)."""
    from servers import api_server as a

    monkeypatch.setenv("PEMF_RATELIMIT_REMOTE_PER_MIN", deger)
    assert _kos(a, "PEMF_RATELIMIT_REMOTE_PER_MIN")["_RL_REMOTE_MAX"] == beklenen


def test_ITHAL_ANI_eksik_paketli_yapida_geri_dusus_tanimlari(monkeypatch):
    """`headless_core` içe aktarılamıyor (eksik paketli yapı) → HeadlessCore / HardwareController None, `get_patient_database()`
    None (çağıranlar "DB yok" koluna düşer) (api_server.py:114-123)."""
    from servers import api_server as a

    assert a.HeadlessCore is not None  # kopya ad alanının başlangıcı gerçek sınıf — None'ı ürün kodu üretmeli
    monkeypatch.setitem(sys.modules, "headless_core", None)
    ns = _kos(a, "from headless_core import HeadlessCore")
    assert (ns["HeadlessCore"], ns["HardwareController"], ns["get_patient_database"]()) == (None, None, None)
    assert ns["get_patient_database"]("C:/herhangi") is None
    assert a.HeadlessCore is not None  # canlı modül DEĞİŞMEDİ


def test_ITHAL_ANI_sure_kapagi_kancasi_BAGLANAMAZSA_uyari(monkeypatch, caplog):
    """Uyumsuz HC (`sure_doldu_kancasi_bagla` yok) → ithal istisnasız sürer + UYARI "D1.68: sure kapagi kancasi baglanamadi"
    (api_server.py:3359-3364)."""
    from controllers import hardware_controller as hcm
    from servers import api_server as a

    monkeypatch.delattr(hcm, "sure_doldu_kancasi_bagla")
    caplog.set_level(logging.WARNING)
    _kos(a, "sure_doldu_kancasi_bagla(_bobin_suresi_doldu)")
    uyari = [r for r in caplog.records if r.getMessage() == "D1.68: sure kapagi kancasi baglanamadi"]
    assert len(uyari) == 1 and uyari[0].levelno == logging.WARNING and uyari[0].exc_info is not None


def test_ITHAL_ANI_paketli_SIMULATOR_ve_ARAYUZ_onbellek_politikasiyla_mount(tmp_path, caplog):
    """Paketlenmiş simülatör `dist` varsa "/simulator"a, `frontend/dist/index.html` varsa "/"ye `OnbellekPolitikaliStatik` ile mount
    (api_server.py:7894-7908); `frontend/dist`te index.html yok ama `frontend_temp`te varsa o; hiç arayüz yoksa mount YOK ve
    "Frontend derlemesi bulunamadı!" uyarısı."""
    from servers import api_server as a

    (tmp_path / "dema-terapi-simülatörü" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("<!doctype html>", encoding="utf-8")

    def _yol(*p):
        return tmp_path.joinpath(*p)

    app = _App()
    _kos(a, 'sim_path = str(packaged_resource_path("dema-terapi', 2, app=app, packaged_resource_path=_yol)
    _kos(a, "frontend_candidates = [", 3, app=app, packaged_resource_path=_yol)
    assert app.cagri == [
        (
            "mount",
            "/simulator",
            "OnbellekPolitikaliStatik",
            str(tmp_path / "dema-terapi-simülatörü" / "dist"),
            "simulator",
        ),
        ("mount", "/", "OnbellekPolitikaliStatik", str(tmp_path / "frontend" / "dist"), "frontend"),
    ]

    yedek = tmp_path / "ikinci"
    (yedek / "frontend" / "dist").mkdir(parents=True)  # index.html YOK → aday atlanır
    (yedek / "frontend_temp").mkdir(parents=True)
    (yedek / "frontend_temp" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    app2 = _App()
    _kos(a, "frontend_candidates = [", 3, app=app2, packaged_resource_path=lambda *p: yedek.joinpath(*p))
    assert app2.cagri == [("mount", "/", "OnbellekPolitikaliStatik", str(yedek / "frontend_temp"), "frontend")]

    bos = _App()
    caplog.set_level(logging.WARNING)
    _kos(
        a,
        'sim_path = str(packaged_resource_path("dema-terapi',
        2,
        app=bos,
        packaged_resource_path=lambda *p: tmp_path.joinpath("yok", *p),
    )
    _kos(a, "frontend_candidates = [", 3, app=bos, packaged_resource_path=lambda *p: tmp_path.joinpath("yok", *p))
    assert bos.cagri == []
    assert "Frontend derlemesi bulunamadı! Tarayıcıda boş sayfa çıkabilir." in _log(caplog)
