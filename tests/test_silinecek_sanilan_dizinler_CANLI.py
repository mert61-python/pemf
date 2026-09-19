# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DENETIMIN "SILINECEK" DEDIGI DIZINLER ASLINDA CANLI (2026-09-17).

⚠️ BU DOSYA BIR DENETIM HATASINI DUZELTIR — hatayi ben yaptim.

`docs/DEPO-DENETIMI-2026-09-15.md` §"Silinecekler" ve `docs/KLASOR-YAPISI-PLANI.md`
alti dizini "donmus ya da olu" diye silinmeye aday gosteriyordu. 2026-09-17'de her biri
REFERANS taramasiyla olculdu; ALTIDAN BESI CANLI cikti:

    dizin                      durum      kanit
    ────────────────────────── ────────── ──────────────────────────────────────────────
    frontend/                  ⛔ CANLI    api_server.py: `frontend/dist` -> app.mount("/")
                                          URUNUN ANA REACT ARAYUZU (11 MB dist mevcut)
    dema-terapi-simülatörü/    ⛔ CANLI    api_server.py: -> app.mount("/simulator")
                                          + spec datas'a ekliyor (EXE'ye GIRIYOR)
    web_static/                ⛔ CANLI    PEMF_Backend_onedir.spec: datas dongusunde
    lattekurulum/              ⛔ CANLI    build_installer.ps1: VC++ redist hedef dizini
    pemf_vet_landing/          ⚠️ REFERANSLI tests/test_kontrol_bayti_kapisi.py URETILMIS
                                          ciktisi olarak listeliyor
    website/                   ⛔ KENDI README'si "silme, birak" DIYOR (2026-09-17)
                                          — referanssiz ama KARARA BAGLANMIS: v1.2
                                          installer indirme sayfasi, tarihsel referans

Yani "0 takipli dosya" ya da "son commit eski" olmak OLU demek DEGILDIR: uretilen cikti
dizinleri git'te gorunmez ama URUN onlari sunar. Denetimde bu ayrimi yapmamistim.

⚠️ SILINSEYDI NE OLURDU: `frontend/` silinince backend `/` adresinde "Frontend derlemesi
bulunamadi!" uyarisi basip BOS SAYFA sunardi (api_server.py'nin kendi `else` dali).
Klinikte arayuz acilmazdi ve sebebi "silinen olu dizin" olarak hic akla gelmezdi.

BU KAPININ ISI: bayat tavsiyeye uyup bu dizinleri silen bir degisikligi KIRMIZI yapmak.
Gercekten kaldirilacaklarsa once ONLARI SUNAN KOD kaldirilmali; kapi o zaman bilincli
olarak guncellenir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
_API = KOK / "apps" / "backend" / "servers" / "api_server.py"
_SPEC = KOK / "build_tools" / "PEMF_Backend_onedir.spec"
_INSTALLER = KOK / "build_tools" / "build_installer.ps1"


def _kod(p: Path) -> str:
    """Yorumlari ayiklanmis kaynak — bir dizin adinin yalniz ACIKLAMADA gecmesi
    "canli" saymak icin yeterli degildir."""
    return "\n".join(re.sub(r"#.*$", "", s) for s in p.read_text(encoding="utf-8").splitlines())


# ═══════════════════════════════════════════════════════════════════════════════════════
# CANLI SUNUM YOLLARI
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_frontend_URUNUN_ANA_ARAYUZU():
    """⚠️ `frontend/` "0 takipli dosya" diye silinmeye aday gosterilmisti.

    Silinirse backend `/` adresinde BOS SAYFA sunar (kendi `else` dalinda uyariyor).
    """
    kod = _kod(_API)
    assert 'packaged_resource_path("frontend", "dist")' in kod, (
        "api_server artik `frontend/dist`i aramiyor -> ana arayuz sunum yolu degismis; "
        "bu kapi guncellenmeli (ya da arayuz gercekten kaldirildi)"
    )
    assert 'name="frontend"' in kod, "frontend mount'u kaybolmus"


def test_KRITIK_dema_simulatoru_CANLI_ve_EXEye_GIRIYOR():
    """⚠️ "ayri bir calisma, ayri depoya" diye isaretlenmisti — oysa URUN sunuyor."""
    kod = _kod(_API)
    assert 'packaged_resource_path("dema-terapi-simülatörü", "dist")' in kod, (
        "api_server artik DEMA simulatorunu sunmuyor -> denetim tavsiyesi uygulanmis olabilir"
    )
    assert 'name="simulator"' in kod, "/simulator mount'u kaybolmus"
    spec = _kod(_SPEC)
    assert "dema-terapi-simülatörü" in spec, (
        "spec artik simulatoru datas'a eklemiyor -> sevk edilen EXE'de /simulator BOS doner"
    )


def test_KRITIK_web_static_SPECTE_paketleniyor():
    """`web_static/` spec'in datas dongusunde — "donmus" degil, sevk ediliyor."""
    spec = _kod(_SPEC)
    assert "web_static" in spec, "spec artik web_static'i paketlemiyor"


def test_KRITIK_lattekurulum_KURULUM_yolunda():
    """`lattekurulum/` VC++ redistributable'in indirme/paketleme hedefi."""
    ps = _kod(_INSTALLER)
    assert "lattekurulum" in ps, (
        "build_installer artik lattekurulum'u kullanmiyor -> VC++ redist yolu degismis olabilir"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("dizin", ["frontend", "dema-terapi-simülatörü"])
def test_KARSIT_KANIT_sunum_dizini_VARSA_saglam(dizin: str):
    """Derleme ciktisi MEVCUTSA eksiksiz olmali (bos `dist` = sessiz 404).

    ⚠️ BU TESTIN ILK HALI CI'I KIRDI — ve hatasi ogrendigim dersin TERSIYDI.
    `dist/`in VARLIGINI sart kosuyordum; oysa bu dosyanin kendi konusu "uretilen cikti
    dizinleri git'te GORUNMEZ". Temiz checkout'ta (CI) `frontend/dist` YOKTUR, cunku
    `.gitignore`dadir. Kosu 35209803805 tam bu yuzden kirmizi dondu:

        AssertionError: frontend/dist AGACTA YOK

    ⚠️ CI'DA DOGRULANABILIR DEGISMEZ, DIZININ VARLIGI DEGIL KODUN REFERANSIDIR — onlari
    yukaridaki dort test kosulsuz olcuyor ve HER YERDE kosuyor. Burasi yalnizca yerel
    agacta ek bir emniyet: cikti varsa `index.html`i de olmali (yarim derleme = `/`
    adresinde bos sayfa).
    """
    p = KOK / dizin / "dist"
    if not p.is_dir():
        pytest.skip(
            f"{dizin}/dist yok — temiz checkout/CI (uretilen cikti, .gitignore'da). Asil koruma: kod referansi testleri."
        )
    assert (p / "index.html").exists(), (
        f"{dizin}/dist VAR ama index.html YOK -> mount bos doner; yarim derleme olabilir"
    )


def test_KARSIT_KANIT_kapi_YORUMLA_kandirilmaz():
    """Cipa yorumsuz koda pinli: dizin adinin bir ACIKLAMADA gecmesi canli saymaz."""
    ham = _API.read_text(encoding="utf-8")
    kod = _kod(_API)
    assert len(kod) < len(ham), "yorum ayiklama calismiyor -> kapi metne takilabilir"
    assert "# frontend" not in kod, "yorum satiri koda sizmis"


def test_KARSIT_KANIT_denetim_belgesi_DUZELTILDI():
    """⚠️ Kapi tek basina yetmez: BAYAT TAVSIYE belgede duruyorsa biri yine uygular.

    Denetim ve klasor plani, bu dizinlerin canli oldugunu ACIKCA soylemeli.

    ⚠️ CIPA DUZELTME METNINE PINLI. Ilk yazimda yalnizca "canlı" kelimesini ariyordu ve
    test BEDAVAYA gecti — o kelime iki belgede de baska baglamlarda ("canlı sırlar",
    "canlı yolda") zaten geciyor. Kendi kapim metne takildi.
    """
    ISARET = "SILINECEKLER LISTESI YANLISTI"
    for yol in ("docs/DEPO-DENETIMI-2026-09-15.md", "docs/KLASOR-YAPISI-PLANI.md"):
        metin = (KOK / yol).read_text(encoding="utf-8")
        assert ISARET in metin, (
            f"{yol} duzeltilmemis -> bayat 'silinecekler' tavsiyesi belgede duruyor ve biri "
            "yine uygulayabilir (frontend/ silinirse urun BOS SAYFA sunar)"
        )
        for d in ("frontend", "dema-terapi"):
            assert d in metin, f"{yol} duzeltmesi {d} dizininden soz etmiyor"


def test_KRITIK_website_KENDI_KARARINI_tasiyor():
    """⚠️ ONUNCU DENETIM HATASI — ve en utanc vericisi.

    `website/`i denetimde "donmus, silinecek" diye listelemistim. Dizinde UC dosya var ve
    BIRI tam da bu karari tasiyor:

        website/README.md -> "Bugun nereye deploy ediliyor: hicbir yere. Tarihsel referans
                              olarak duruyor — **silme, birak** (runtime ile ilgisi yok)."

    Yani dizin ZATEN incelenmis, ZATEN karara baglanmis. Ben denetimi yazarken icindeki
    README'yi OKUMAMISIM. "Referanssiz" olmasi onu silinebilir yapmiyor: karar kaydi da
    bir referanstir.

    Bu test o karari kilitler. Gercekten silinecekse ONCE README'deki karar degistirilmeli.
    """
    p = KOK / "website" / "README.md"
    if not p.exists():
        # ⚠️ SESSIZ `return` DEGIL: "dosya yoksa gecerim" diyen bir kapi, dizin bir gun
        # sessizce silindiginde KIRMIZI donmez ve kaybi kimse gormez — tam da bu dosyanin
        # anlattigi hatanin ta kendisi. Atlama GORUNUR olmali.
        pytest.skip(
            "website/README.md YOK -> dizin kaldirilmis olabilir. Icinde bir KARAR kaydi "
            "vardi; kaldirma bilincliyse denetim belgesindeki satiri da guncelleyin."
        )
    metin = p.read_text(encoding="utf-8").lower()
    assert "silme" in metin, (
        "website/README.md artik 'silme, birak' kararini tasimiyor -> ya karar degisti "
        "(o zaman bu kapi guncellenmeli) ya da karar kaydi kayboldu"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# YEDINCI ADAY — `ai/` (2026-09-19'da eklendi)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_ai_paketi_URETIM_yolunda():
    """⚠️ ONBIRINCI DENETIM HATASI — ve sinifi tanidik: OLCMEDEN yazilmis iddia.

    `docs/ARIZA-LISTESI.md` C3 satiri `ai/config.py` icin soyle diyordu:

        "ai/config.py (349 satir) uretimde SIFIR import — tek tuketicisi donmus arsiv"

    2026-09-19'da olculdu, UC yeri de yanlis:

      1. Dosya 349 degil **376** satir (iddia yazildiginda bile bayatti).
      2. `ai/hybrid_recommender.py` URETIM kodundan cagriliyor:
             apps/backend/servers/api_server.py:2451
             `from ai.hybrid_recommender import get_literature_recommendation`
      3. `config.py` de YUKLENIYOR: `ai/__init__.py:23` -> `from . import config`.
         Yani "sifir import" degil; dogru ifade "sembolleri uretimde KULLANILMIYOR".

    ⚠️ NEDEN GOZDEN KACTI — ve bu kapinin asil degeri burada:
    uretimdeki import **FONKSIYON ICINDE** (8 bosluk girintili). Modul basindaki import
    satirlarini tarayan bir "olu kod" araci onu GORMEZ. C3'un bu satiri tam da oyle bir
    taramadan cikmis olmali.

    Bugunku koruma TESADUFI: `tests/test_literatur_hedef_sozlesmesi.py` paketi modul
    duzeyinde import ettigi icin silme denemesi toplama hatasiyla kirmizi doner. O test
    bir gun kosullu hale gelirse koruma SESSIZCE kaybolur. Bu kapi korumayi BILINCLI yapar.
    """
    kod = _kod(_API)
    assert "from ai.hybrid_recommender import get_literature_recommendation" in kod, (
        "api_server artik `ai.hybrid_recommender`i cagirmiyor -> `ai/` paketi uretim "
        "yolundan cikmis olabilir; bu kapi bilincli olarak guncellenmeli"
    )
    assert (KOK / "ai" / "hybrid_recommender.py").exists(), "ai/hybrid_recommender.py YOK"
    init = (KOK / "ai" / "__init__.py").read_text(encoding="utf-8")
    assert "from . import config" in init, (
        "ai/__init__.py artik config'i yuklemiyor -> `ai/config.py` gercekten kopmus olabilir; "
        "silinecekse ONCE bu satir kaldirilir, sonra kapi guncellenir"
    )


def test_KRITIK_ai_paketi_SPECTE_paketleniyor():
    """Donmus EXE'de de bulunmali — yoksa `/auto_preset` yalniz sevk edilen surumde coker."""
    spec = _kod(_SPEC)
    assert "'ai'" in spec or '"ai"' in spec, (
        "spec artik `ai` paketini toplamiyor -> sevk edilen EXE'de auto_preset ucu "
        "ImportError verir; gelistirme makinesinde SORUNSUZ gorunur"
    )


def test_KARSIT_KANIT_modul_basi_taramasi_bu_importu_KACIRIR():
    """Kapinin varlik sebebini OLCER: import modul basinda DEGIL.

    Bu bir SART degil, bir TESHIS. Import bir gun modul basina tasinirsa bu test not
    dusup gecer — o zaman siradan bir tarama da gorur ve kapinin aciliyeti duser.
    """
    ham = _API.read_text(encoding="utf-8")
    satirlar = [s for s in ham.splitlines() if "from ai.hybrid_recommender import" in s]
    assert satirlar, "import hic bulunamadi -> yukaridaki kapi zaten kirmizi olmali"
    girintili = [s for s in satirlar if s[:1] in (" ", "\t")]
    if not girintili:
        pytest.skip(
            "import artik modul basinda — siradan olu-kod taramasi da goruyor, "
            "bu kapinin aciliyeti dustu (ama korumasi durmali)"
        )
    assert girintili, "beklenmeyen dal"
