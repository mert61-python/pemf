# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""STM32 FIRMWARE UYUM KAPISI — "bagli" ile "uyumlu" AYRI SEYDIR (2026-09-18).

⚠️ COZDUGU ARIZA (`docs/stm32-uzaktan-guncelleme-plani.md` §1, olculmus):
Kart acilista kim oldugunu SOYLUYOR:

    -> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) ...

`headless_core` ise yalnizca `"STM_READY" in decoded` bakip baglantıyı YESIL yapiyordu —
satirin ICERIGINE HIC bakmadan. Eski firmware (5 bobin) 88 baytlik paket bekler; backend
120 bayt gonderir → kart CRC'yi YANLIS OFSETTEN okur, her pakete NACK doner, PWM durumuna
HIC dokunmaz.

    Belirti: gosterge YESIL, hata penceresi YOK, HICBIR bobin baslamiyor (1-5 dahil).
    Teshis icin tek yol UART'i elle dinlemekti.

⚠️ DEPODA ZATEN TEPKISEL BIR KAPI VAR (`live_state.stm_komutlari_reddediyor`): kart NACK
dondurmeye BASLADIKTAN sonra seansi reddeder. Buradaki kapi ONLEYICI ikizidir — banner'dan,
daha seans baslatilmadan. Ikisi kardestir; biri otekinin yerine gecmez.

⚠️ UC DURUMLU KARAR — ve "bilinmiyor" SEANSI ENGELLEMEZ:
    True  = kanal sayisi paket genisligimizle esit
    False = KESIN uyumsuz  -> seans reddedilir (409)
    None  = banner taninmadi -> seans ENGELLENMEZ, ama /api/health'te GORUNUR
Sebep: banner bicimi ileride degisip UYUMLU bir firmware de taninmayabilir; calisan bir
kligini durdurmak cozdugumuz sorundan buyuk zarar olurdu. Yalnizca BILDIGIMIZDE reddediyoruz.

⚠️ GUVENLIK DEGISMEZI — ACIL DURDURMA ASLA KAPILANMAZ. Uyumsuz firmware'de bile STOP yolu
acik kalir (depo kurali: bobinler her seyden once durur). Bunun kendi testi asagida.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")

ESKI_BANNER = "-> STM_READY: DDS v2.3 (5-ch SYM-BIPOLAR uni=0x00 + HW_SYNC@PB1) Waiting for commands..."
YENI_BANNER = "-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) Waiting for commands..."
BOZUK_BANNER = "-> STM_READY: eski surum, kanal bilgisi yok"


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · AYRISTIRICI — TEK KAYNAK
# ═══════════════════════════════════════════════════════════════════════════════


def test_KRITIK_banner_ayristirici_GERCEK_firmware_bicimini_okuyor():
    """⚠️ Desen firmware KAYNAGINDAN dogrulanir, uydurulmaz.

    `main.c:1006` biçimi: `"-> STM_READY: DDS v2.3 (%u-ch %s uni=0x%02X + HW_SYNC@PB1) ..."`
    Kip dizesi BOSLUKLU olabilir ("UNIPOLAR tek-bacak") — naif `\\S+` ile ayristirilirsa ikiye
    bolunur ve maske kaybolur.
    """
    from utils.stm32_kimlik import banner_ayristir

    k = banner_ayristir(YENI_BANNER)
    assert k is not None, "gercek firmware banner'i AYRISTIRILAMADI"
    assert k.kanal == 7
    assert k.kip == "UNIPOLAR tek-bacak", f"kip bolunmus: {k.kip!r}"
    assert k.maske == 0x60
    assert k.surum == "DDS v2.3"


def test_KRITIK_desen_TEK_KAYNAKTAN_geliyor():
    """⚠️ `scripts/stm_firmware_kimligi.py` KENDI regex'ini TASIMAMALI.

    Saha betigi ile backend kapisi AYNI banner'i FARKLI okursa, biri "uyumlu" digeri
    "uyumsuz" der ve hangisine inanilacagi belirsizlesir. (Bu depoda bedeli olculmus sinif:
    `_DB_ERROR` demetleri iki DB modulunde sessizce ayrismisti.)
    """
    metin = (KOK / "scripts" / "stm_firmware_kimligi.py").read_text(encoding="utf-8")
    assert "from utils.stm32_kimlik import" in metin, (
        "saha betigi ortak ayristiriciyi kullanmiyor -> kendi kopyasini tasiyor olabilir"
    )
    assert "STM_READY:.*?" not in metin, (
        "saha betiginde HALA kendi banner regex'i var -> iki ayristirici sessizce ayrisir"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · UYUM KARARI
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "banner,beklenen",
    [(ESKI_BANNER, False), (YENI_BANNER, True), (BOZUK_BANNER, None)],
)
def test_KRITIK_uyum_karari_UC_DURUMLU(banner, beklenen):
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle

    uyumlu, sebep = uyum_denetle(banner_ayristir(banner), 7)
    assert uyumlu is beklenen, f"{banner!r} -> {uyumlu}, beklenen {beklenen}"
    if beklenen is not True:
        assert sebep, "uyumsuz/bilinmeyen durumda SEBEP bos olamaz (operatore ne diyecegiz?)"


def test_KRITIK_uyumsuzluk_mesaji_EYLEM_soyluyor():
    """Hata mesaji ne oldugunu DEGIL ne yapilacagini soylemeli (depo kurali)."""
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle

    _, sebep = uyum_denetle(banner_ayristir(ESKI_BANNER), 7)
    assert "5" in sebep and "7" in sebep, f"mesaj hangi sayilarin catistigini soylemiyor: {sebep!r}"
    assert "SAHA-ISLERI-REHBERI" in sebep, "mesaj operatore YAPILACAK ISI gostermiyor"


def _headless_agac():
    import ast

    return ast.parse((KOK / "apps" / "backend" / "headless_core.py").read_text(encoding="utf-8"))


def _fonksiyon(agac, ad):
    import ast

    return next((n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == ad), None)


def test_KRITIK_banner_isleme_OKUYUCUYA_BAGLI():
    """⚠️ MUTASYONLA OLCULDU: kapilarim uyum durumunu DOGRUDAN enjekte ediyordu, yani
    `headless_core`daki BAGLANTIYI hic olcmuyorlardi. `self._stm_kimligini_isle(decoded)`
    cagrisini silmek 12 testi de YESIL birakiyordu — oysa uretimde banner hic ayristirilmaz,
    `stm_uyumlu` sonsuza dek `None` kalir ve HICBIR seans reddedilmez.

    Capa, cagriyi ULASILABILIR kilan `STM_READY` dalinin ICINE pinli.
    """
    import ast

    agac = _headless_agac()
    bagli = False
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.If):
            continue
        if "STM_READY" not in ast.unparse(dugum.test):
            continue
        govde = ast.Module(body=dugum.body, type_ignores=[])
        if any(
            isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "_stm_kimligini_isle" for c in ast.walk(govde)
        ):
            bagli = True
            break
    assert bagli, (
        "`_stm_kimligini_isle` STM_READY dalindan CAGRILMIYOR -> banner uretimde hic okunmaz; "
        "uyum kapisi var gorunur ama HICBIR ZAMAN tetiklenmez."
    )


def test_KARSIT_KANIT_paket_genisligi_KAYNAKTAN_IMPORT_ediliyor():
    """⚠️ MUTASYONLA OLCULDU: once yalnizca `"STM_PAKET_BOBIN_SAYISI" in metin` bakiyordum.
    Sabiti `STM_PAKET_BOBIN_SAYISI = 7` diye ELLE YAZAN mutasyon o dizeyi yine icerdigi icin
    kapi YESIL kaliyordu — capa adin GECMESINE takilmisti, KAYNAGINA degil.

    Artik AST ile IMPORT ifadesine pinli: deger `utils.stm32_transport`tan GELMELI.
    """
    import ast

    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    agac = _headless_agac()
    import_var = any(
        isinstance(n, ast.ImportFrom)
        and (n.module or "").endswith("stm32_transport")
        and any(a.name == "STM_PAKET_BOBIN_SAYISI" for a in n.names)
        for n in ast.walk(agac)
    )
    assert import_var, (
        "headless_core paket genisligini `utils.stm32_transport`tan IMPORT ETMIYOR — "
        "elle yazilmis bir sabit, firmware genisligi degisince kapiyi SESSIZCE yanlis yapar"
    )
    assert STM_PAKET_BOBIN_SAYISI >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · SEANS KAPISI + ⚠️ ACIL DURDURMA DEGISMEZI
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


class _SahteCekirdek:
    """Uyum alanlarini tasiyan asgari `state.core` vekili.

    ⚠️ ONCE `pytest.skip("core baslatilmamis")` yaziyordum ve TEST ATLANIYORDU — yani en
    onemli degismez (acil durdurma kapilanmaz) HICBIR SEY kanitlamiyordu. Atlanan test,
    gecen test degildir. Depoda kullanilan desen: `monkeypatch.setattr(state, "core", ...)`.
    """

    def __init__(self, uyumlu=None, sebep=""):
        self.stm_uyumlu = uyumlu
        self.stm_uyumsuzluk_sebebi = sebep
        self.stm_is_connected = True

    def get_service_status(self):
        return {}


def _karar(banner: str):
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    return uyum_denetle(banner_ayristir(banner), STM_PAKET_BOBIN_SAYISI)


class _SahteDonanim:
    """Asgari `state.hardware` vekili — komutlari KABUL eder.

    ⚠️ NEDEN GEREKLI: `state.hardware` yoksa seans zaten **503** ile reddedilir ve testim
    UYUM kapisina HIC ULASMAZ. Ilk yazimda tam bu oldu: test kirmizi dondu ama sebebi benim
    kapim degildi. Donanimi KABUL EDER yapmak sart — aksi halde 409'u hangi kapinin
    urettigini ayirt edemeyiz.
    """

    def update_coil(self, coil_id, freq, duty, phase, duration, start=True, duration_seconds=None):
        return True

    def stop_all_coils(self):
        return True

    def get_all_coils_state(self):
        return {}


@pytest.fixture
def uyumsuz_cekirdek(monkeypatch):
    from servers import api_server

    u, s = _karar(ESKI_BANNER)
    assert u is False, "on kosul: eski banner KESIN uyumsuz sayilmali"
    monkeypatch.setattr(api_server.state, "core", _SahteCekirdek(u, s), raising=False)
    monkeypatch.setattr(api_server.state, "hardware", _SahteDonanim(), raising=False)
    return u, s


def test_KRITIK_UYUMSUZ_firmware_ACIL_DURDURMAYI_engellemez(istemci, uyumsuz_cekirdek):
    """⚠️ EN ONEMLI TEST. Uyumsuz kartta tedaviyi DURDURAMAMAK, cozdugumuz sorundan
    kat kat tehlikelidir. Kapi YALNIZCA BASLATMADADIR."""
    y = istemci.post("/api/hardware/emergency_stop", json={})
    assert y.status_code == 200, (
        f"UYUMSUZ firmware'de ACIL DURDURMA {y.status_code} dondu — bu kapi STOP yolunu "
        "ASLA kapatmamali (depo degismezi: bobinler her seyden once durur)"
    )


def test_KRITIK_UYUMSUZ_firmware_SEANS_BASLATMAYI_reddediyor(istemci, uyumsuz_cekirdek):
    """⚠️ Kapinin asil isi. MUTASYON: `api_server.py`deki `stm_uyumlu is False` kontrolunu
    sil → bu test KIRMIZI olmali."""
    _, sebep = uyumsuz_cekirdek
    y = istemci.post(
        "/api/session/start",
        json={
            "mode": "Manuel",
            "frequency": 100,
            "duty": 50,
            "phase": 0,
            "intensity": 0.0,
            "duration_minutes": 20,
            "coil_ids": [1, 2],
            "patient_name": "UyumTesti",
        },
    )
    assert y.status_code == 409, (
        f"UYUMSUZ firmware'de seans {y.status_code} ile gecti — bobinler calismayacakken "
        "operatore 'basladi' denmis olur (tam da cozulen ariza)."
    )
    detay = str(y.json().get("detail", ""))
    assert "5" in detay and "7" in detay, f"409 mesaji catisan kanal sayilarini soylemiyor: {detay!r}"


def test_KRITIK_saglik_ucu_UYUM_alanlarini_bildiriyor(istemci):
    """`stmConnected` bu ayrimi yapamaz — destek muhendisi icin AYRI alan sart."""
    y = istemci.get("/api/health")
    assert y.status_code == 200
    j = y.json()
    assert "stmUyumlu" in j, "/api/health `stmUyumlu` alanini bildirmiyor -> 'yesil ama calismiyor' yine gorunmez"
    assert "stmUyumsuzlukSebebi" in j, "sebep alani yok -> operatore ne diyecegiz?"


def test_KARSIT_KANIT_UYUMLU_bannerda_kapi_KAPANMIYOR(istemci, monkeypatch):
    """⚠️ Kapi HEP reddetseydi ustteki testler yine gecerdi. Uyumlu banner seansi
    ENGELLEMEMELI — kapinin ayirt edici oldugunu bu test kanitlar."""
    from servers import api_server

    u, s = _karar(YENI_BANNER)
    assert u is True, 'on kosul: yeni banner uyumlu sayilmali'
    monkeypatch.setattr(api_server.state, 'core', _SahteCekirdek(u, s), raising=False)

    y = istemci.get('/api/health')
    assert y.json().get('stmUyumlu') is True, 'uyumlu bannerda saglik ucu hala uyumsuz diyor'

    y2 = istemci.post(
        '/api/session/start',
        json={
            'mode': 'Manuel',
            'frequency': 100,
            'duty': 50,
            'phase': 0,
            'intensity': 0.0,
            'duration_minutes': 20,
            'coil_ids': [1, 2],
            'patient_name': 'UyumluTest',
        },
    )
    assert y2.status_code != 409 or 'kanalli firmware' not in str(y2.json().get('detail', '')), (
        'UYUMLU bannerda seans UYUM sebebiyle reddedildi -> kapi hep reddediyor demektir'
    )
    try:
        istemci.post('/api/session/stop')
    except Exception:
        pass


def test_KARSIT_KANIT_BILINMEYEN_banner_seansi_ENGELLEMEZ(istemci):
    """Banner taninmadiginda karar `None` kalmali — `False` DEGIL.

    `None`i `False` gibi ele almak, banner bicimi degisen UYUMLU bir firmware'de calisan
    bir kligini durdururdu.
    """
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle

    u, sebep = uyum_denetle(banner_ayristir(BOZUK_BANNER), 7)
    assert u is None, f"bilinmeyen banner {u} dondu — 'False' olsaydi calisan klinik dururdu"
    assert "OKUNAMADI" in sebep.upper()
