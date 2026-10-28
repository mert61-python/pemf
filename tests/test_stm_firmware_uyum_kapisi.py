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

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

ESKI_BANNER = "-> STM_READY: DDS v2.3 (5-ch SYM-BIPOLAR uni=0x00 + HW_SYNC@PB1) Waiting for commands..."
#: TD1 · Y68: TD1 sonrası firmware paket boyunu BEYAN eder (`proto=` / `pkt=`); `uni=` basıp pkt= basmayan eski banner
#: 120 / 121 baytı ayırt edemez → karar None (tezgâh 2026-10-14).
YENI_BANNER = (
    "-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."
)
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
    # D6.57 (B-10.191): eskiden yalniz "SAHA-ISLERI-REHBERI" ALT-DIZESINE bakiliyordu — hedef bolum (B-2) KALDIRILMISTI.
    assert "Yapilacak" in sebep and "scripts/stm_yak.py" in sebep, (
        "mesaj operatore YAPILACAK ISI (yakma araci) gostermiyor"
    )
    _rehber_basvurulari_GECERLI(sebep)


#: Belge bolum basvurusu: `<yol>.md B-2` / `<yol>.md §9` / `<yol>.md 'Baslik'`
_BOLUM_RE = r"([\w./-]+\.md)\s+(B-\d+|§\s?\d+|'[^']+')"


def _rehber_basvurulari_GECERLI(sebep: str) -> None:
    """Destek metnindeki her dosya yolu depoda VAR; bolum basvurusu varsa o baslik VAR ve ⛔ / KALDIRILDI DEGIL (D6.57)."""
    import re

    for yol in re.findall(r"(?<![\w/])((?:docs|scripts|firmware|apps|tools)/[\w./-]+\.(?:md|py))", sebep):
        assert (KOK / yol).exists(), f"mesaj olmayan dosyaya yonlendiriyor: {yol} — {sebep!r}"
    for yol, bolum in re.findall(_BOLUM_RE, sebep):
        bolum = bolum.strip("'").replace("§", "").strip()
        # Tur 2 (D67 çürütme, mutant c1): önek-siz / olmayan dosyaya bölüm başvurusu AssertionError ile kırmızı (çöküş değil).
        assert (KOK / yol).is_file(), f"mesaj olmayan dosyanin bolumune yonlendiriyor: {yol} '{bolum}' — {sebep!r}"
        basliklar = [s for s in (KOK / yol).read_text(encoding="utf-8").splitlines() if s.startswith("#")]
        hedef = [b for b in basliklar if re.search(rf"(?<![\w-]){re.escape(bolum)}(?![\w])", b)]
        assert hedef, f"mesajin gosterdigi bolum {yol} '{bolum}' YOK — {sebep!r}"
        assert not any("⛔" in b or "KALDIRILDI" in b for b in hedef), (
            f"mesaj operatoru KALDIRILMIS bir bolume yonlendiriyor: {hedef} — {sebep!r}"
        )


@pytest.mark.parametrize(
    "banner",
    [
        ESKI_BANNER,  # kanal uyusmazligi
        "-> STM_READY: DDS v2.5 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=2 pkt=120 Waiting for commands...",  # pkt beyani
        "-> STM_READY: DDS v2.3 (7-ch SYM-BIPOLAR + HW_SYNC@PB1) Waiting for commands...",  # uni= yok → 120 B eski imaj
    ],
    ids=["kanal", "pkt_beyani", "uni_yok_eski"],
)
def test_KRITIK_KESIN_uyumsuzluk_mesajlari_GECERLI_rehbere_yonlendirir_D6_57(banner):
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle

    uyumlu, sebep = uyum_denetle(banner_ayristir(banner), 7)
    assert uyumlu is False, f"{banner!r} KESIN uyumsuz olmali: {uyumlu} {sebep!r}"
    assert "Yapilacak" in sebep and "scripts/stm_yak.py" in sebep, sebep
    assert "SAHA-ISLERI-REHBERI.md B-2" not in sebep, sebep
    _rehber_basvurulari_GECERLI(sebep)


def test_KRITIK_RED_kaniti_mesaji_GECERLI_rehbere_yonlendirir_D6_57():
    from utils.stm32_kimlik import KANIT_RED, uyum_karari

    uyumlu, sebep, _kod = uyum_karari(None, KANIT_RED, crc=5)
    assert uyumlu is False and "scripts/stm_yak.py" in sebep, sebep
    _rehber_basvurulari_GECERLI(sebep)


def test_KARSIT_D6_57_bolum_denetimi_KALDIRILMIS_bolumu_YAKALAR():
    """Aparat kendi kendine yesil olmasin: eski metnin gosterdigi bolum gercekten ⛔ KALDIRILDI basligi."""
    with pytest.raises(AssertionError, match="KALDIRILMIS"):
        _rehber_basvurulari_GECERLI("Yapilacak: docs/SAHA-ISLERI-REHBERI.md B-2 ile STM'i yeniden yakin.")


def test_KRITIK_servis_betigi_ESKI_firmware_cozumu_GUNCEL_yolu_onerir_D6_57(monkeypatch, capsys):
    """scripts/stm_firmware_kimligi.py eski-firmware dalinda sabit tarihli masaustu klasoru DEGIL, yakma araci + temiz workspace."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_stm_firmware_kimligi_d657", KOK / "scripts" / "stm_firmware_kimligi.py"
    )
    betik = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(betik)
    eski = "-> STM_READY: DDS v2.3 (5-ch SYM-BIPOLAR uni=0x00 + HW_SYNC@PB1) Waiting for commands..."
    monkeypatch.setattr(betik, "_portlari_bul", lambda _p: ["COM_D657"])
    monkeypatch.setattr(betik, "_kart_dogrula", lambda port, sure: ([eski], {"crc_nack": 0}))
    monkeypatch.setattr("sys.argv", ["stm_firmware_kimligi.py", "--port", "COM_D657"])
    rc = betik.main()
    out = capsys.readouterr().out
    assert rc == 1 and "ESKI FIRMWARE" in out, out
    assert "PEMF_STM32_workspace_20" not in out, f"sabit tarihli masaustu klasoru oneriliyor:\n{out}"
    assert "scripts/stm_yak.py" in out and "scripts/stm_workspace_kopyala.py" in out, out
    for yol in (
        "scripts/stm_yak.py",
        "scripts/stm_workspace_kopyala.py",
        "scripts/README.md",
        "firmware/stm32_pemf/README.md",
    ):
        assert yol in out and (KOK / yol).exists(), f"{yol} onerilmiyor ya da yok:\n{out}"
    # Tur 2 kolu (D67 çürütme, mutant c2): betiğin önerdiği BÖLÜM başvuruları (ör. README 'CubeIDE'de açma / derleme') da GERÇEK
    # ve kaldırılmamış başlık — KESİN mesajlarla aynı doğrulayıcı.
    _rehber_basvurulari_GECERLI(out)


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


def test_KRITIK_UYUMSUZ_firmware_ACIL_DURDURMAYI_engellemez(istemci, uyumsuz_cekirdek, monkeypatch):
    """⚠️ EN ONEMLI TEST. Uyumsuz kartta tedaviyi DURDURAMAMAK, cozdugumuz sorundan
    kat kat tehlikelidir. Kapi YALNIZCA BASLATMADADIR.

    ⚠️ D1.04 (B-10.50): eskiden yalniz HTTP 200'e bakiyordu ve `_SahteDonanim.stop_all_coils`
    hic sayilmiyordu — "uyumsuzlukta STM STOP'u atla" mutantinda YESIL kaliyordu (kor). Artik
    GERCEK `HardwareController` STOP'u verir, paket donanim kuyruguna gider (firmware aynasiyla
    cozulur, duty 0) ve yanit `stmStopped` der. Teyit (`confirmed`) BILEREK olculmez (A-63 → D1.105)."""
    from kayitci_donanim import gercek_hc, paket_coz
    from servers import api_server
    from topoloji import TUM_STM

    # ESP yayini olculmez; False → ack-bekcisi is parcacigi DOGMAZ (test sonrasina tasmasin).
    monkeypatch.setattr(api_server, "_mqtt_publish", lambda topic, payload: False)
    with gercek_hc() as hc:
        monkeypatch.setattr(api_server.state, "hardware", hc)
        # Bağımsız inceleme (r1): E-stop'tan ÖNCE bobinler GERÇEKTEN sürülüyor olmalı — yoksa "son paket
        # duty 0" her pakette zaten doğrudur ve `stop_all_coils` bobin durumunu sıfırlamasa da kapı
        # yeşil kalırdı (eski duty ile giden E-stop paketi).
        surulen = sorted({1, max(TUM_STM)})
        for b in surulen:
            assert hc.update_coil(b, 100.0, 30.0, 0.0, duration=1) is True
        once = paket_coz(hc.core._hw_send_queue.paketler[-1])[0]
        assert all(once[b - 1] == pytest.approx(0.30) for b in surulen), f"senaryo: bobinler sürülmüyor {once}"
        y = istemci.post("/api/hardware/emergency_stop", json={})
        assert y.status_code == 200, (
            f"UYUMSUZ firmware'de ACIL DURDURMA {y.status_code} dondu — bu kapi STOP yolunu "
            "ASLA kapatmamali (depo degismezi: bobinler her seyden once durur)"
        )
        assert hc.stop_all_cagri >= 1, "UYUMSUZ firmware'de acil durdurma STM'e STOP VERMEDI (yalniz 200 dondu)"
        assert y.json().get("stmStopped") is True, f"yanit STM STOP'unu bildirmiyor: {y.json()!r}"
        assert hc.core._hw_send_queue.paketler, "STOP paketi donanim kuyruguna HIC gitmedi"
        duty = paket_coz(hc.core._hw_send_queue.paketler[-1])[0]
        assert all(d == 0.0 for d in duty), f"son paket STOP degil (duty): {duty}"


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
    # TD1 · K1: 409 operatöre SADE metin + kod söyler (CubeIDE / kanal sayısı / '7-ch' YOK); çatışan kanal sayıları
    # DESTEK ayrıntısında (`/api/health` `stmUyumsuzlukSebebi`) kalır.
    detay = str(y.json().get("detail", ""))
    assert "FW-PAKET" in detay and "uyumsuz" in detay, f"409 metni sade + kodlu değil: {detay!r}"
    assert "CubeIDE" not in detay and "7-ch" not in detay, f"409 metninde geliştirici talimatı: {detay!r}"
    assert "5" in sebep and "7" in sebep, f"destek ayrıntısı çatışan kanal sayılarını söylemiyor: {sebep!r}"


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
