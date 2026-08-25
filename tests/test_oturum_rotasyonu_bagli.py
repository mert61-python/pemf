# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""JETON ROTASYON SENKRONU URETIM KODUNA BAGLI (saha arizasi 2026-08-24).

SEMPTOM: "Beni hatirla" duzgun calismiyordu; client guncellemesinden sonra e-posta+parola
yeniden soruluyordu.

OLCULEN KOK NEDEN: tek bir Supabase refresh-token ailesi IKI yerde yasiyordu.
  1. Launcher: DPAPI ile `auth_session.bin`e yazar, acilista yeniler.
  2. Uygulama penceresi: ayni jetonlari devir yoluyla alir (`setSession`) ve supabase-js
     `autoRefreshToken: true` ile ARKA PLANDA yeniler.
Supabase yenilemede refresh token'i DONDURUR (rotation). Pencerenin dondurdugu jeton yalnizca
tarayici deposunda kaliyor; launcher'in diskteki kopyasi BAYATLIYORDU. Bir sonraki acilista
launcher bayat jetonla yenileme deniyor -> GoTrue accikca reddediyor -> `SessionRevoked` ->
`secret_store::clear()` -> kayitli oturum SILINIYOR -> parola yeniden soruluyor.
Guncelleme bunu guvenilir bicimde tetikliyor: pencere bir sure acik kalip jetonu donduruyor,
ardindan zorunlu yeniden baslatma geliyor.

⚠️ Kanit: yayindaki masaustu paketinde (`_internal/frontend/dist`) `autoRefreshToken:!0`
dogrulandi; sahadaki blob DPAPI ile cozulup `expires_at` okundu (jeton gercekten dolmustu).

SOZLESME (uc halka, uctan uca):
  1. Pencere jetonu her DONDURDUGUNDE yeni oturumu backend'e geri yazar.
  2. Launcher backend'ten OKUR.
  3. Launcher diske ISLER (kapilari `secret_store::rotasyonu_isle`de).
Herhangi bir halka kopuksa dongu tamamlanmaz ve ariza geri gelir — bu yuzden ucu de olculur.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_AUTHCTX = _KOK / "pf" / "src" / "context" / "AuthContext.tsx"
_DESKTOP = _KOK / "pf" / "src" / "services" / "desktopSession.ts"
_MAIN = _KOK / "launcher" / "app" / "src" / "main.rs"
_BACKEND = _KOK / "launcher" / "core" / "src" / "backend.rs"
_STORE = _KOK / "launcher" / "core" / "src" / "secret_store.rs"


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def test_KRITIK_1_pencere_DONDURULEN_jetonu_geri_yazar():
    """Halka 1: `TOKEN_REFRESHED` olayina bagli degilse rotasyon hic duyulmaz."""
    s = _oku(_AUTHCTX)
    assert "TOKEN_REFRESHED" in s, (
        "AuthContext jeton DONDURME olayini dinlemiyor — pencere jetonu yeniler, launcher "
        "haberdar olmaz ve diskteki kopya bayatlar (saha arizasi 2026-08-24)"
    )
    i = s.find("TOKEN_REFRESHED")
    assert "pushDesktopSession" in s[i : i + 500], "olay dinleniyor ama oturum GERI YAZILMIYOR"


def test_KRITIK_1b_geri_yazma_ucu_dogru():
    s = _oku(_DESKTOP)
    m = re.search(r"export async function pushDesktopSession\(.*?\n\}", s, re.S)
    assert m, "pushDesktopSession yok"
    g = m.group(0)
    assert "/auth/desktop-session" in g, "geri yazma yanlis uca gidiyor"
    assert "isDesktopHost()" in g, "mobilde de POST atiliyor (masaustu client YOK)"
    assert "refresh_token" in g, "refresh jetonu geri yazilmiyor — rotasyonun TA KENDISI o"


def test_KRITIK_2_launcher_backendten_OKUR():
    """Halka 2: okuma yoksa geri yazilan jeton backend belleginde olur."""
    s = _oku(_BACKEND)
    assert "pub fn pull_desktop_session" in s, "launcher devir oturumunu OKUMUYOR"
    # 3. tur F5: okuma gövdesi timeout-parametrized `pull_desktop_session_kisa`e çıkarıldı (60 sn
    # döngüsü 5 sn, teardown son-yakalama KISA bütçeyle çağırır). Loopback doğrulaması O gövdede →
    # gerçek okuma+loopback-kontrolü taşıyan fonksiyona pinle (thin wrapper'a değil).
    m = re.search(r"pub fn pull_desktop_session_kisa\(.*?\n\}", s, re.S)
    assert m and "is_loopback_http_url" in m.group(0), (
        "okuma loopback dogrulamasi yapmiyor — oturum yalniz 127.0.0.1'den alinmali"
    )


def test_KRITIK_3_launcher_diske_ISLER():
    """Halka 3: okunan jeton diske islenmezse bir sonraki acilista yine bayat kopya kullanilir."""
    s = _oku(_MAIN)
    assert "pull_desktop_session" in s, "senkron gorevi backend'ten OKUMUYOR"
    # 3. tur F4: doc-comment'ler artik `pull_desktop_session` adini metinde daha once aniyor →
    # cipla ilk-gecise degil GERCEK CAGRI YERINE (`pull_desktop_session(port)`) pinle.
    i = s.find("pull_desktop_session(port)")
    assert i > 0, "gercek pull_desktop_session(port) cagrisi bulunamadi"
    assert "rotasyonu_isle" in s[i : i + 600], "okunan oturum diske ISLENMIYOR"
    assert "oturum_rotasyon_senkronu_baslat" in s, "senkron gorevi HIC baslatilmiyor"
    # Gorev backend hazir olunca baslamali (port o an bilinir).
    j = s.find("fn on_backend_ready")
    assert "oturum_rotasyon_senkronu_baslat" in s[j : j + 1500], (
        "senkron backend hazir oldugunda baslatilmiyor — pencere acikken hic calismaz"
    )


def test_KRITIK_4_SAHIPLENILEN_backend_de_senkronlar():
    """🔴 C3 (denetim 2026-08-24): crash-sonrasi ORPHAN backend'i sahiplenen yolda da rotasyon
    senkronu baslamali.

    `start_installed`, calisan bir backend bulursa (`detect_running_backend`) yenisini baslatmaz,
    mevcut olani SAHIPLENIR — `on_backend_ready` CAGRILMAZ (child yok, sureci biz baslatmadik,
    oldurme hakkimiz da yok). `test_KRITIK_3` senkronu YALNIZ on_backend_ready'de kilitliyor; bu
    sahiplenme dali onun disinda kaliyordu. Senkron burada baslamazsa: pencere jetonu dondurup
    backend'e push eder, launcher pull etmez, diskteki kopya bayatlar, sonraki acilista
    SessionRevoked -> "Beni hatirla" SILINIR (saha arizasinin sahiplenme yolunda acik kalan kolu).
    """
    s = _oku(_MAIN)
    # start_installed sahiplenme dalinin GOVDESINI yakala (`Some(port) = detect_running_backend`
    # blogu, kapanan `}`e kadar). repair'daki dal `Some(p)` oldugundan bu regex onu secmez.
    m = re.search(r"if let Some\(port\) = backend::detect_running_backend\(&root\) \{(.*?)\n    \}", s, re.S)
    assert m, "start_installed sahiplenme dali bulunamadi — main.rs bicimi degismis"
    assert "oturum_rotasyon_senkronu_baslat" in m.group(1), (
        "sahiplenilen backend'in rotasyon senkronu BASLATILMIYOR — o oturumun jeton donmeleri diske "
        "islenmez ve sonraki acilista 'Beni hatirla' silinir (C3)"
    )


def test_KARSIT_KANIT_senkron_CIFT_thread_baslatmaz():
    """⚠️ Sahiplenme dali her Baslat'ta kosabilir (state.proc'a KOYULMAZ) → guard olmadan her cagri
    yeni bir thread biriktirirdi (L7 cift-thread). Senkron baslatma bir kez-guard ile korunmali
    (baslatici guard'i CAGIRMALI + guard'in kendisi atomik compare_exchange olmali)."""
    s = _oku(_MAIN)
    m = re.search(r"fn oturum_rotasyon_senkronu_baslat\(.*?\n\}\n", s, re.S)
    assert m, "senkron gorevi bulunamadi"
    assert "senkron_baslamali" in m.group(0), (
        "senkron baslatma guard'i CAGIRMIYOR — sahiplenme dali her Baslat'ta thread biriktirir (L7)"
    )
    g = re.search(r"fn senkron_baslamali\(.*?\n\}\n", s, re.S)
    assert g and "compare_exchange" in g.group(0), (
        "guard atomik degil (compare_exchange yok) — yaris altinda iki thread birden acilabilir"
    )


@pytest.mark.parametrize(
    "kapi,mesaj",
    [
        ("load(install_root)", "kayitli oturum YOKKEN yazmama kapisi"),
        ("eq_ignore_ascii_case", "baska e-posta kapisi"),
        ("refresh_token.trim().is_empty()", "bos jeton kapisi"),
    ],
)
def test_KRITIK_yazma_kapilari_YERINDE(kapi, mesaj):
    """⚠️ Uc kapi da pazarlik edilemez — ayrintili gerekce `rotasyonu_isle` docstring'inde."""
    m = re.search(r"pub fn rotasyonu_isle\(.*?\n\}", _oku(_STORE), re.S)
    assert m, "rotasyonu_isle yok"
    assert kapi in m.group(0), f"{mesaj} kaldirilmis"


def test_KARSIT_KANIT_senkron_backend_olunce_BITER():
    """Sonsuz thread sizintisi olmamali: backend kapandiginda gorev kendiliginden bitmeli."""
    s = _oku(_MAIN)
    m = re.search(r"fn oturum_rotasyon_senkronu_baslat\(.*?\n\}\n", s, re.S)
    assert m, "senkron gorevi bulunamadi"
    assert "return" in m.group(0), "gorev hicbir kosulda bitmiyor — thread sizar"


def test_KRITIK_duzeltme_YAYINLANAN_pakete_giriyor():
    """⚠️ Kaynakta olması YETMEZ: düzeltme uygulama penceresinin SERVİS EDİLEN paketinde olmalı.

    Pencere frontend'i `PEMF_Backend/_internal/frontend/dist` altından servis edilir ve o dizin
    web export'undan gelir. `pf/` kaynağını düzeltip paketi yeniden üretmemek, arızayı KAYNAKTA
    kapatıp SAHADA açık bırakırdı — bu deponun tekrar eden hata deseni ("düzeltildi ama
    dağıtılmadı") tam olarak budur.

    Bu kapı yalnız YAYIN MAKİNESİNDE anlamlıdır: taze klonda/CI'da derlenmiş paket yoktur.
    """
    dist = _KOK / "frontend" / "dist"
    if not dist.exists():
        pytest.skip("frontend/dist yok — yayın makinesi değil (CI/taze klon)")
    paketler = list((dist / "_expo" / "static" / "js" / "web").glob("entry-*.js"))
    if not paketler:
        pytest.skip("web paketi bulunamadı (export yapılmamış)")
    icerik = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in paketler)
    assert "TOKEN_REFRESHED" in icerik, (
        "SERVİS EDİLEN web paketi jeton döndürme olayını dinlemiyor — düzeltme kaynakta var ama "
        "pakette YOK; sahada 'Beni hatırla' bozulmaya devam eder (web export'u yeniden çalıştırın)"
    )
    assert "desktop-session" in icerik, "pakette devir ucu yok — geri yazma hedefsiz kalır"
