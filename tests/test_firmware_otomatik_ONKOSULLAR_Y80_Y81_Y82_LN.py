# -*- coding: utf-8 -*-
"""LN L1 — oto-firmware'i açmadan önceki BACKEND önkoşulları (DALGA-1-KAPANIS §6 (1)): Y80 · Y81 · Y82.

Sahip kararları (SAHIP-CEVAPLARI.md):
  * Y80 (S-İH1) — aynı SHA'lı ikili bu cihazda otomatik olarak YALNIZ BİR KEZ denenir; kart hedef sürümü bildirmezse veri kökünde
    kalıcı kayıt (`firmware_yedek/son_yakma.json`: SHA, hedef, kartın bildirdiği, zaman); sonraki açılışlarda o SHA otomatik
    YAKILMAZ, `/api/health` "sürüm tutmadı — elle bakın" der; ilk yakmanın yedeği tutma sınırıyla BUDANMAZ.
  * Y81 (S-İH2) — otomatik yakma KAPALIYKEN uyum kuralı "uyumsuz" derse backend `istemciGeriAlinmali=True` bildirir (launcher geri
    alır); bayrak açıkken önce ileri gidilir (H-10.1).
  * Y82 (S-İH3 · O-1.2) — `/api/health` `firmwareGuncelleme.yakiliyor` (yalnız-ek); yakmadan ÖNCE "yarım yakma" kaydı, doğrulamadan
    SONRA silinir; açılışta kayıt görülürse kart sürümü doğrulanır, uyumsuzsa yedekten eski firmware'e GERİ DÖNÜLÜR.

SAHTE EN ALT KATTA: ağ = `update_manager._pinli_ac` (manifest + ikili gövdesi), yakıcı = `utils.stm_yakma._kos` (`STM32_Programmer_CLI`
komutlarını bir sahte FLASH üzerinde uygular) + `programmer_cli`. Karar, indirme, SHA, yedek, yakma, geri okuma, banner ve tutma sınırı
GERÇEK kodla koşar. ⚠️ Bu makinede gerçek `STM32_Programmer_CLI.exe` VAR — `programmer_cli` HER testte sahtelenir (hafıza).
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from stlink_sahte import liste as stlink_liste  # T-b: sahte yakıcı `-l st-link` prob listesi
from utils import surum_uyumu as su

# client 1.9.51 ≥ 1.9.50 → firmware ≥ 2.4 ister; kartta 2.3 → KESİN uyumsuz, manifestteki 2.4 → ileri gidilebilir.
KURAL = [{"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.4", "firmwareMax": ""}]
# Y68 beyanlı banner (kart paket boyunu söyler → `uyum_denetle` kesin karar verir; beyansız banner "doğrulanamadı" = kod 9).
BANNER = "-> STM_READY: DDS v{} (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."


class SurecOldu(BaseException):
    """Yakma sırasında sürecin öldürülmesi (launcher kill / elektrik) — hiçbir `except Exception` yakalamaz."""


class SahteKart:
    """STM32F429 uygulama alanı + `STM32_Programmer_CLI` komutları (`-r` oku · `-w` yaz · `-rst`)."""

    def __init__(self, eski: bytes = b"ESKI-FW-" * 64):
        self.flash = bytearray(eski)
        self.eski = bytes(eski)
        self.yazilan: list[str] = []
        self.yazmada = None  # `-w` anında çağrılır (ikili yolu) — kayıt ölçümü / süreç ölümü benzetimi

    def kos(self, cli, argumanlar, timeout=300.0):
        a = list(argumanlar)
        if a[:1] == ["-l"]:  # T-b: yakma akışı ST-Link'i seri numarasıyla seçer (tek prob)
            return 0, stlink_liste()
        if "-w" in a:
            ikili = Path(a[a.index("-w") + 1])
            if self.yazmada is not None:
                self.yazmada(ikili)
            veri = ikili.read_bytes()
            self.flash[: len(veri)] = veri
            self.yazilan.append(ikili.name)
            return 0, "sahte: yazıldı + doğrulandı"
        if "-r" in a:
            i = a.index("-r")
            boy, hedef = int(a[i + 2]), Path(a[i + 3])
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(bytes(self.flash[:boy]))
            return 0, "sahte: okundu"
        return 0, "sahte: -rst"


@pytest.fixture()
def ortam(monkeypatch, tmp_path):
    """Taze `firmware_manager` (giriş VE çıkışta) + sahte ağ (EN ALT: `_pinli_ac`) + sahte kart (EN ALT: `_kos`)."""
    import servers.update_manager as um
    import utils.stm_yakma as sy

    fm = importlib.reload(importlib.import_module("servers.firmware_manager"))
    monkeypatch.setattr(um, "get_current_version", lambda: "1.9.51")
    kart = SahteKart()
    monkeypatch.setattr(sy, "_kos", kart.kos)
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path(r"C:\sahte\STM32_Programmer_CLI.exe"))
    monkeypatch.setattr(sy, "BANNER_SURESI", 0.05)
    # Süreç içi seans / bobin ön kontrolü kendi kapılarıyla ölçülür (D1.108 / D1.111); burada "seans yok".
    monkeypatch.setattr(fm, "_surec_ici_guvenlik_kontrolu", lambda: (True, "sahte: seans yok, bobin sürülmüyor"))
    durum = SimpleNamespace(
        ikili=b"YENI-FW-2.4-" * 50, fw_surum="2.4", kart_bildirir="2.3", manifest_istek=0, ikili_istek=0
    )
    fw_url = f"https://github.com/{um._UPDATE_REPO}/releases/download/fw-test/pemf_fw.bin"

    class _Yanit(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _pinli_ac(url, timeout, headers=None):
        if url == fm.UYUM_URL:
            durum.manifest_istek += 1
            veri = {
                "firmware": {
                    "stm32": {
                        "version": durum.fw_surum,
                        "url": fw_url,
                        "sha256": hashlib.sha256(durum.ikili).hexdigest(),
                    }
                },
                "uyumluluk": KURAL,
            }
            return _Yanit(json.dumps(veri).encode("utf-8"))
        if url == fw_url:
            durum.ikili_istek += 1
            return _Yanit(durum.ikili)
        raise AssertionError(f"beklenmeyen ağ isteği: {url}")

    monkeypatch.setattr(um, "_pinli_ac", _pinli_ac)

    def banner_kaynagi():
        return sy.BannerKaynagi(isaret=lambda: 1, bekle=lambda isaret, sure: BANNER.format(durum.kart_bildirir))

    veri_koku = Path(__import__("utils.path_utils", fromlist=["x"]).get_app_data_directory())
    yield SimpleNamespace(
        fm=fm, sy=sy, um=um, kart=kart, d=durum, banner=banner_kaynagi, kok=veri_koku / "firmware_yedek"
    )
    # D3I: modül-global `_durum` (son testin gerekçesi — veri kökündeki uzun yedek yolu) süreçte KALMASIN: aynı süreçte sonra koşan
    # `/api/health` ölçen testler (`test_gzip_sikistirma` küçük yanıt) sıraya bağlı kırmızıya dönüyordu (değişen küme koşusunda ölçüldü).
    importlib.reload(importlib.import_module("servers.firmware_manager"))


def _ac(o, *, surum="2.3", bagli=True, uygula=True):
    return o.fm.acilis_denetimi(firmware_surum=surum, stm_bagli=bagli, uygula=uygula, banner_kaynagi=o.banner())


def _yeni_surec(o):
    """Backend yeniden başladı: modül-global durum sıfırlanır, veri kökü (kayıtlar) aynı kalır."""
    o.fm = importlib.reload(o.fm)
    o.fm._surec_ici_guvenlik_kontrolu = lambda: (True, "sahte: seans yok, bobin sürülmüyor")


# ══════════════════════════════════════════════════════════════════════════════
# Y81 — bayrak KAPALIYKEN uyumsuz çift → launcher'a geri alma sinyali
# ══════════════════════════════════════════════════════════════════════════════


def test_KRITIK_Y81_bayrak_KAPALIYKEN_ileri_plan_varken_de_istemciGeriAlinmali_TRUE(ortam):
    d = _ac(ortam, uygula=False)
    assert d["eylem"] == su.FIRMWARE_GUNCELLE and d["uyum"] is False, f"aparat: plan {d}"
    assert d["istemciGeriAlinmali"] is True, (
        "Y81: otomatik yakma KAPALI + kesin uyumsuz + STM bağlı → firmware yakılmayacak, uyumsuz çift kalır; backend launcher'a geri alma "
        f"sinyali VERMELİ: {d}"
    )
    assert ortam.kart.yazilan == [] and ortam.d.ikili_istek == 0, (
        "bayrak kapalıyken ikili indirildi / karta yazıldı (Y1)"
    )


@pytest.mark.parametrize(
    "ad,surum,bagli,kural",
    [("uyumlu_kart", "2.4", True, KURAL), ("stm_bagli_degil", "2.3", False, KURAL), ("kural_yok", "2.3", True, [])],
)
def test_KARSIT_Y81_sinyal_yalniz_KESIN_uyumsuz_ve_STM_bagliyken(ortam, monkeypatch, ad, surum, bagli, kural):
    monkeypatch.setattr(ortam.fm, "_kurallar", lambda _m: kural)
    d = _ac(ortam, surum=surum, bagli=bagli, uygula=False)
    assert d["istemciGeriAlinmali"] is False, f"{ad}: launcher yanlış yere geri alma sinyali alır: {d}"


def test_KARSIT_Y81_bayrak_ACIKKEN_once_ILERI_gidilir_sinyal_YOK(ortam):
    ortam.d.kart_bildirir = "2.4"
    d = _ac(ortam, uygula=True)
    assert d["uygulandi"] is True and d["istemciGeriAlinmali"] is False, f"bayrak açıkken ileri gidilmeli (H-10.1): {d}"
    assert len(ortam.kart.yazilan) == 1


def test_KRITIK_Y81_GERCEK_acilis_yolunda_bayrak_YOKKEN_sinyal_TRUE(ortam, monkeypatch):
    """`backend_service._donanim_guncellemesi_safe` (açılış kararı) — bayrak ortamda YOK (Y1 varsayılanı)."""
    import backend_service as bs

    monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)
    core = SimpleNamespace(
        stm_is_connected=True,
        stm_kimlik=SimpleNamespace(surum="DDS v2.3"),
        stm_banner_isareti=lambda: 1,
        stm_banner_bekle=lambda isaret, sure: BANNER.format("2.3"),
    )
    import logging

    bs._donanim_guncellemesi_safe(core, logging.getLogger("test"))
    d = ortam.fm.durum()
    assert d["eylem"] == su.FIRMWARE_GUNCELLE and d["istemciGeriAlinmali"] is True, f"gerçek açılış yolu: {d}"
    assert ortam.kart.yazilan == [], "bayrak yokken karta yazıldı"


# ══════════════════════════════════════════════════════════════════════════════
# Y80 — aynı SHA bir kez · ilk yedek budanmaz
# ══════════════════════════════════════════════════════════════════════════════


def test_KRITIK_Y80_ayni_SHA_YALNIZ_BIR_KEZ_otomatik_denenir(ortam):
    d1 = _ac(ortam)
    assert d1["uygulandi"] is False and "hedef sürümü bildirmedi" in d1["hata"], f"aparat: ilk deneme {d1}"
    assert len(ortam.kart.yazilan) == 1
    kayit = json.loads((ortam.kok / "son_yakma.json").read_text(encoding="utf-8"))
    assert kayit["sha256"] == hashlib.sha256(ortam.d.ikili).hexdigest() and kayit["hedef"] == "2.4", kayit
    assert kayit["kartin_bildirdigi"] == "2.3" and kayit.get("zaman"), kayit

    _yeni_surec(ortam)
    d2 = _ac(ortam)
    assert len(ortam.kart.yazilan) == 1, (
        f"Y80: aynı SHA'lı ikili İKİNCİ açılışta yeniden yakıldı ({ortam.kart.yazilan}) — her açılış yakar, 5 açılışta asıl yedek budanırdı"
    )
    assert d2["uygulandi"] is False and "sürüm tutmadı" in d2["hata"] and "elle" in d2["hata"], (
        f"/api/health 'sürüm tutmadı — elle bakın' demiyor: {d2}"
    )
    assert ortam.d.ikili_istek == 1, "engellenen SHA yine de indirildi"


def test_KARSIT_Y80_FARKLI_SHA_yine_denenir(ortam):
    _ac(ortam)
    _yeni_surec(ortam)
    ortam.d.ikili = b"DUZELTILMIS-2.4-" * 40  # yeni yayın: başka ikili
    _ac(ortam)
    assert len(ortam.kart.yazilan) == 2, (
        "farklı SHA'lı yeni yayın engellendi — düzeltilmiş ikili bir daha hiç yakılamazdı"
    )


def test_KRITIK_Y80_ilk_yakmanin_yedegi_TUTMA_sinirinda_BUDANMAZ(ortam):
    ilk = None
    for i in range(ortam.fm.FIRMWARE_YEDEK_TUT + 3):
        ortam.d.ikili = f"YENI-FW-{i}-".encode() * 40
        _ac(ortam)
        yedekler = sorted(ortam.kok.glob("pemf_yedek_*.bin"))
        if ilk is None:
            ilk = yedekler[0].name
        _yeni_surec(ortam)
        __import__("time").sleep(1.05)  # yedek adı saniye çözünürlüklü zaman damgası
    kalan = sorted(p.name for p in ortam.kok.glob("pemf_yedek_*.bin"))
    assert ilk in kalan, f"Y80: İLK yakmanın yedeği (asıl saha firmware'i) budandı: {kalan}"
    assert len(kalan) == ortam.fm.FIRMWARE_YEDEK_TUT + 1, (
        f"tutma sınırı (en yeni {ortam.fm.FIRMWARE_YEDEK_TUT} + ilk) uygulanmadı: {kalan}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Y82 — yakılıyor alanı · yarım yakma kaydı · açılış kurtarması
# ══════════════════════════════════════════════════════════════════════════════


def test_KRITIK_Y82_durum_yakiliyor_PENCERE_ile_AYNI_ve_SAGLIK_ucunda(ortam):
    from servers import system_router
    from utils import firmware_yakma_penceresi as pencere

    assert ortam.fm.durum().get("yakiliyor") is False, ortam.fm.durum()
    with pencere.ac():
        assert ortam.fm.durum().get("yakiliyor") is True, "yakma penceresi açıkken `yakiliyor` True değil"
        assert system_router._firmware_guncelleme_durumu().get("yakiliyor") is True, (
            "sağlık ucunun alanı `yakiliyor` taşımıyor"
        )
    assert ortam.fm.durum().get("yakiliyor") is False


def test_KRITIK_Y82_yarim_kayit_YAKMADAN_ONCE_yazilir_DOGRULAMADAN_SONRA_silinir(ortam):
    gorulen = {}

    def _yazmada(ikili):
        if "yarim" in gorulen:
            return
        k = ortam.kok / "yarim_yakma.json"
        gorulen["yarim"] = json.loads(k.read_text(encoding="utf-8")) if k.exists() else None

    ortam.kart.yazmada = _yazmada
    ortam.d.kart_bildirir = "2.4"
    d = _ac(ortam)
    assert d["uygulandi"] is True, d
    y = gorulen.get("yarim")
    assert y is not None, "yakma (-w) başladığında 'yarım yakma' kaydı YOKTU — yarıda kalan yakma açılışta tanınamaz"
    assert y["sha256"] == hashlib.sha256(ortam.d.ikili).hexdigest() and y["hedef"] == "2.4", y
    assert Path(y["yedek"]).is_file(), f"kayıttaki yedek dosyası yok: {y}"
    assert not (ortam.kok / "yarim_yakma.json").exists(), "doğrulamadan SONRA 'yarım yakma' kaydı SİLİNMEDİ"


def test_KRITIK_Y82_yarim_kayit_YAZILAMAZSA_karta_YAZILMAZ(ortam, monkeypatch):
    gercek = ortam.fm._kayit_yaz

    def _yarim_yazilamaz(kok, ad, veri):
        if ad == ortam.fm.YARIM_YAKMA_DOSYASI:
            raise PermissionError(13, "firmware_yedek yazılamıyor (sahte)")
        return gercek(kok, ad, veri)

    monkeypatch.setattr(ortam.fm, "_kayit_yaz", _yarim_yazilamaz)
    d = _ac(ortam)
    assert ortam.kart.yazilan == [], (
        "Y82: 'yarım yakma' kaydı YAZILAMADI ama karta yazıldı — yarıda kalırsa açılış tanıyamaz"
    )
    assert f"[{ortam.sy.YARIM_KAYIT_YAZILAMADI}]" in d["hata"] and d["uygulandi"] is False, d
    assert not (ortam.kok / "son_yakma.json").exists(), (
        "karta YAZILMAYAN deneme Y80 kaydına işlendi (aynı SHA haksız yere engellenir)"
    )


def test_KRITIK_Y82_yakma_YARIDA_kalirsa_kayit_KALIR(ortam):
    def _ol(ikili):
        raise SurecOldu()

    ortam.kart.yazmada = _ol
    with pytest.raises(SurecOldu):
        _ac(ortam)
    assert (ortam.kok / "yarim_yakma.json").exists(), "süreç yakma sırasında öldüğünde 'yarım yakma' kaydı KALMALI"


def _yarim_birak(ortam):
    def _ol(ikili):
        ortam.kart.flash[:16] = b"\xff" * 16  # yarım yazılmış uygulama alanı
        raise SurecOldu()

    ortam.kart.yazmada = _ol
    with pytest.raises(SurecOldu):
        _ac(ortam)
    ortam.kart.yazmada = None
    kayit = json.loads((ortam.kok / "yarim_yakma.json").read_text(encoding="utf-8"))
    _yeni_surec(ortam)
    return kayit


def test_KRITIK_Y82_acilista_yarim_kayit_ve_kart_HEDEFI_bildirmiyor_YEDEKTEN_geri_donulur(ortam):
    kayit = _yarim_birak(ortam)
    oncesi = len(ortam.kart.yazilan)
    ortam.d.kart_bildirir = "2.3"
    d = _ac(ortam)
    assert Path(kayit["yedek"]).name in ortam.kart.yazilan[oncesi:], (
        f"Y82: yarım kalan yakmadan sonra yedek (eski firmware) karta GERİ YAZILMADI: {ortam.kart.yazilan}"
    )
    assert bytes(ortam.kart.flash[: len(ortam.kart.eski)]) == ortam.kart.eski, (
        "geri dönüşten sonra kart eski firmware'de değil"
    )
    assert not (ortam.kok / "yarim_yakma.json").exists(), "geri dönüş doğrulandı ama 'yarım yakma' kaydı silinmedi"
    assert (d.get("yarimYakma") or {}).get("sonuc") == "geri_donuldu", f"durum geri dönüşü söylemiyor: {d}"
    assert len([n for n in ortam.kart.yazilan[oncesi:] if n != Path(kayit["yedek"]).name]) == 0, (
        f"kurtarmadan sonra aynı SHA yeniden yakıldı (Y80 — yarım kalan deneme de BİR deneme): {ortam.kart.yazilan}"
    )


def test_KARSIT_Y82_kart_HEDEFI_bildiriyorsa_geri_DONULMEZ_kayit_silinir(ortam):
    _yarim_birak(ortam)
    oncesi = len(ortam.kart.yazilan)
    ortam.d.kart_bildirir = "2.4"
    d = _ac(ortam, surum="2.4")
    assert ortam.kart.yazilan[oncesi:] == [], f"kart hedef sürümü bildirirken yedek geri yazıldı: {ortam.kart.yazilan}"
    assert not (ortam.kok / "yarim_yakma.json").exists()
    assert (d.get("yarimYakma") or {}).get("sonuc") == "tamamlanmis", d


@pytest.mark.parametrize("ad,bagli,uygula", [("bayrak_kapali", True, False), ("stm_bagli_degil_Y76", False, True)])
def test_KARSIT_Y82_bayrak_kapali_ya_da_STM_yokken_KARTA_dokunulmaz_kayit_KALIR(ortam, ad, bagli, uygula):
    kayit = _yarim_birak(ortam)
    oncesi = len(ortam.kart.yazilan)
    d = _ac(ortam, surum="2.3" if bagli else "", bagli=bagli, uygula=uygula)
    assert ortam.kart.yazilan[oncesi:] == [], (
        f"{ad}: karta yazıldı ({ortam.kart.yazilan}) — Y1 / Y76: bu kipte ASLA yakılmaz"
    )
    assert (ortam.kok / "yarim_yakma.json").exists(), f"{ad}: kurtarılmamış 'yarım yakma' kaydı silindi"
    y = d.get("yarimYakma") or {}
    assert y.get("sonuc") == "elle" and kayit["yedek"] in (y.get("ayrinti") or ""), (
        f"{ad}: durum elle kurtarmayı + yedeği söylemiyor: {d}"
    )
