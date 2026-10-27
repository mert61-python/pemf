# Author: mertaygn, cglrgrkn
"""LAUNCHER ↔ SİTE YOL SÖZLEŞMESİ  [saha bildirimi 2026-09-07].

Masaüstü uygulaması (launcher/app/ui/index.html) siteye `WEB + "<yol>"` ile yönlendirir: "Hesap
oluştur" → `/register`, "Şifremi unuttum" → `/forgot`, "Destek" → `/support`. Sitede `/register` ve
`/forgot` HİÇ YOKTU → kullanıcı "Sayfa bulunamadı" gördü. İki depo aynı monorepoda ama aralarında
hiçbir kapı yoktu; launcher yayınlandıktan sonra sitedeki rota silinse ya da adı değişse saha yine
404'e düşer (launcher'ı geri çağırmak GB'lık yeniden kurulum demek).

Bu kapı: launcher'ın gittiği HER site yolu, sitede TANIMLI bir rota olmalı. Çıpa iki tarafta da
gerçek çağrıya pinli: launcher'da `WEB + "…"` ifadeleri, sitede `<Route path="…">` + LEGAL_DOCS
slug'ları. SPA rewrite'ı (vercel.json) her yolu 200 döndürür — HTTP koduyla ölçülemez, kaynakla ölçülür.
"""

import pathlib
import re

import capraz
import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_APP = _KOK / "apps/web" / "src" / "App.tsx"
_CONFIG = _KOK / "apps/web" / "src" / "config.ts"


@pytest.fixture(autouse=True)
def _izlenen_kaynak():
    """D5-F (K5-F P3): `launcher/` ve `apps/web/` İZLENEN kaynaktır — yoksa atla, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de DÜŞ.

    Eskiden modül düzeyi düz `skipif(not ….exists())` idi: zorunlu kipte de sessizce ATLIYORDU. Dosyadaki HER test okur.
    """
    capraz.atla_yoksa("launcher/app/ui/index.html", izlenen=True)
    capraz.atla_yoksa("apps/web/src/App.tsx", izlenen=True)


def _soy_js(metin: str) -> str:
    metin = re.sub(r"/\*.*?\*/", " ", metin, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", metin, flags=re.MULTILINE)


def launcher_yollari() -> set[str]:
    """`WEB + "support"` → {"/support"}; yalnız üretim kodu (yorumlar soyulur)."""
    ui = _soy_js(_UI.read_text(encoding="utf-8"))
    assert 'const WEB = "https://pemf-vet-web.vercel.app/"' in ui, "WEB sabiti taşınmış — kapı güncellenmeli"
    yollar = {"/" + y.strip("/") for y in re.findall(r'WEB\s*\+\s*"([^"]*)"', ui)}
    assert yollar, "launcher hiç site yolu kullanmıyor — kapı boş kalırdı"
    return yollar


def site_rotalari() -> set[str]:
    app = _soy_js(_APP.read_text(encoding="utf-8"))
    rotalar = set(re.findall(r'<Route\s+path="(/[^"]*)"', app))
    # Yasal sayfalar `/${d.slug}` ile üretilir → slug'ları config'den al.
    cfg = _CONFIG.read_text(encoding="utf-8")
    rotalar |= {"/" + s for s in re.findall(r"slug:\s*'([^']+)'", cfg)}
    assert "/" in rotalar and "/download" in rotalar, "App.tsx rotaları okunamadı — biçim değişmiş"
    return rotalar


def test_KRITIK_launcherin_gittigi_her_site_yolu_sitede_tanimli():
    eksik = sorted(launcher_yollari() - site_rotalari())
    assert not eksik, (
        f"Launcher şu yollara yönlendiriyor ama sitede rota YOK → sahada 'Sayfa bulunamadı': {eksik}. "
        "apps/web/src/App.tsx'e rotayı ekleyin (launcher'ı değiştirmek yetmez: sahadaki sürümler bu yolu kullanıyor)."
    )


def test_hesap_yollari_modali_DOGRU_sekmede_acar():
    """/register kayıt sekmesinde, /forgot ve /login giriş sekmesinde açılmalı (AuthRoute → requireAuth mode)."""
    app = _soy_js(_APP.read_text(encoding="utf-8"))
    assert re.search(r'path="/register"[^>]*<AuthRoute kind="register"', app), "/register kayıt kipinde değil"
    assert re.search(r'path="/forgot"[^>]*<AuthRoute kind="forgot"', app), "/forgot şifre-unuttum kipinde değil"
    sayfa = _soy_js((_KOK / "apps/web" / "src" / "pages" / "AuthRoute.tsx").read_text(encoding="utf-8"))
    assert re.search(r"register:\s*\{[^}]*mode:\s*'signup'", sayfa, re.DOTALL), "register → signup kipi eşlemesi yok"
    modal = _soy_js((_KOK / "apps/web" / "src" / "context" / "AuthModal.tsx").read_text(encoding="utf-8"))
    assert "useState<AuthMode>(initialMode)" in modal, (
        "AuthModal başlangıç sekmesini `initialMode`dan almıyor → /register yine GİRİŞ sekmesinde açılır"
    )
