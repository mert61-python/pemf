# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10f (KRİTİK) — ACİL DURDUR mandalı / başlatma kapıları / STM kart iletileri / DB açılış nedeni / panel adları istek dilinde.

⚠️ ACİL DURDUR YOLU DEĞİŞMEDİ: kapı KARARI (`baslatma_engeli` boş mu / dolu mu), mandal `eylem` metni (Türkçe sabit), `neden` kodları, sıfırlama ucu aynen. Değişen YALNIZ gösterilen metnin dili:
`X-PEMF-Dil: en` → İngilizce; başlıksız = BUGÜNKÜ Türkçe (bayt bayt). Kapı metni ASLA boş / hata dönmez: katalog çökse bile Türkçe sabit (boş = "engel yok" demektir).
GERÇEK: modül işlevleri + `ceviri` bağlam değişkeni; sahte yalnız WS yayını yakalayıcısı. ⚠️ Beklenen metinler BURADA sabittir. MUTASYON: katalog TR değeri / `dil` yok sayılırsa / fail-safe düşerse KIRMIZI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
for p in (KOK, KOK / "apps" / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

MANDAL_TR = "ACİL DURDURMA MANDALLI — yeni başlatma reddedildi. Bobinleri kontrol edin, ekrandaki 'Sıfırla' ile mandalı kaldırın ve başlatmayı yeniden verin."
NESIL_TR = "Komut bir durdurma ya da acil durdurmadan ÖNCEYE ait (bayat sürüş niyeti) — uygulanmadı. Gerekirse yeniden başlatın."
KAYIP_TR = "Hedef gözlemi bir hedef-kaybı durdurmasından ÖNCEYE ait (bayat gözlem) — sürülmedi."
KAPANIS_TR = "Backend KAPANIYOR — yeni başlatma reddedildi (bobinler durduruluyor)."
YAKMA_TR = "STM32 firmware'i YAZILIYOR (donanım güncellemesi) — bitene kadar bobin başlatılamaz; ACİL DURDUR çalışır."
PAKET_TR = (
    "Cihaz kartının yazılımı bu uygulama sürümüyle uyumsuz — bobinler çalışmaz. Teknik desteği arayın (kod: FW-PAKET)."
)
KIMLIK_TR = "Cihaz kartı doğrulanamadı. Kartın üzerindeki SİYAH sıfırlama düğmesine bir kez basın (mavi değil)."
KOMUT_RED_TR = "Cihaz kartı komutları reddediyor — kartın yazılımı bu uygulama sürümüyle uyumsuz; bobinler çalışmaz. Teknik desteği arayın (kod: FW-PAKET)."
ESTOP_RED_TR = (
    "Cihaz kartı STOP komutunu reddetti — bobinler durmamış olabilir. Cihazın gücünü kesin ya da USB kablosunu çıkarın."
)


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _t(tr, en, d):
    return tr if d == "tr" else en


# ── mandal / başlatma kapısı ──────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mandalli():
    from utils import estop_mandali as em

    em.sifirla("test-onceki")
    em.mandalla("test_10f")
    try:
        yield em
    finally:
        em.sifirla("test-sonrasi")


def test_mandal_metinleri_TR_sabitle_BAYT_BAYT_AYNI_EN_ingilizce_acil_durdur_ifadesi_iki_dilde(dil, mandalli):
    em = mandalli
    # kapı KARARI: mandallıyken dolu, bayat niyette dolu — dilden BAĞIMSIZ
    assert em.baslatma_engeli() == _t(MANDAL_TR, em.mandal_mesaji("en"), dil)
    assert em.mandal_mesaji("tr") == MANDAL_TR == em.MANDAL_MESAJI
    assert em.nesil_mesaji("tr") == NESIL_TR == em.NESIL_MESAJI
    assert em.kayip_mesaji("tr") == KAYIP_TR == em.KAYIP_MESAJI
    assert em.kapanis_mesaji("tr") == KAPANIS_TR == em.KAPANIS_MESAJI
    en = em.mandal_mesaji("en")
    assert "EMERGENCY STOP LATCHED" in en and "'Reset'" in en and not TR_HARF.search(en)
    for f in (em.nesil_mesaji, em.kayip_mesaji, em.kapanis_mesaji):
        assert not TR_HARF.search(f("en")), f("en")
    em.sifirla("t")
    assert em.baslatma_engeli() == ""  # mandal yokken boş (dilden bağımsız)
    em.nesil_artir()
    assert em.baslatma_engeli(em.nesil() - 1) == _t(NESIL_TR, em.nesil_mesaji("en"), dil)
    em.kapanis_kur()
    try:
        assert em.baslatma_engeli() == _t(KAPANIS_TR, em.kapanis_mesaji("en"), dil)
    finally:
        em.kapanis_kaldir()


def test_kapi_metni_katalog_COKSE_BILE_bos_donmez_Turkce_sabit(monkeypatch, mandalli):
    """⚠️ Boş dönüş = "engel yok" → mandallı cihazda başlatma AÇILIRDI. Katalog / çeviri çökse bile kapı metni dolu (Türkçe sabit) kalır."""
    from utils import ceviri

    def coktu(*a, **k):
        raise RuntimeError("katalog yok")

    monkeypatch.setattr(ceviri, "t", coktu)
    em = mandalli
    assert em.baslatma_engeli() == MANDAL_TR
    assert em.kayip_mesaji() == KAYIP_TR
    from utils import firmware_yakma_penceresi as fy
    from utils import stm32_kimlik as sk

    with fy.ac():
        assert fy.baslatma_engeli() == YAKMA_TR
    assert sk.operator_metni(sk.UYUM_KODU_PAKET) == PAKET_TR
    assert sk.komut_red_metni() == KOMUT_RED_TR and sk.estop_kart_red_metni() == ESTOP_RED_TR


def test_kapi_karari_dilden_bagimsiz_yalniz_metin_degisir(mandalli):
    from utils import ceviri

    em = mandalli
    sonuc = {}
    for d in ("tr", "en"):
        jeton = ceviri.istek_dili_var.set(d)
        try:
            sonuc[d] = bool(em.baslatma_engeli())
        finally:
            ceviri.istek_dili_var.reset(jeton)
    assert sonuc == {"tr": True, "en": True}


# ── mandal dosyası yazılamadı ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_mandal_yazim_durumu_mesaj_TR_bayt_bayt_mesajlar_iki_dilli(monkeypatch, mandalli):
    em = mandalli
    monkeypatch.setattr(em, "_kalici_yol", Path("C:/veri/estop_mandali.json"))
    monkeypatch.setitem(em._yazim, "yazilamadi", True)
    monkeypatch.setitem(em._yazim, "disk_kurulu", False)
    d = em.yazim_durumu(yol_dahil=True)  # mandalli: hedef AÇIK, disk kurulu DEĞİL → KORUNMAYACAK
    assert d["yazilamadi"] is True and d["yenidenBaslatmada"] == "KORUNMAYACAK"
    assert (
        d["mesaj"]
        == "Mandal dosyası yazılamadı (C:\\veri\\estop_mandali.json) — yeniden başlatmada mandal KORUNMAYACAK; dosya iznini düzeltin."
    )
    assert d["mesajlar"]["tr"] == d["mesaj"]
    assert d["mesajlar"]["en"] == (
        "The latch file could not be written (C:\\veri\\estop_mandali.json) — after a restart the latch will NOT be preserved; fix the file permission."
    )
    # bitmedi
    b = em.yazim_durumu(yol_dahil=False, bitmedi=True)
    assert (
        b["mesaj"]
        == "Mandal dosyası yazılamadı — yazım 2 sn'de bitmedi, disk yanıt vermiyor — yeniden başlatmada mandal KORUNMAYACAK; dosya iznini düzeltin."
    )
    assert "the write did not finish in 2 s" in b["mesajlar"]["en"]
    # diğer sonuçlar (Türkçe veri değerleri DEĞİŞMEDİ)
    monkeypatch.setitem(em._yazim, "disk_kurulu", True)
    em.sifirla("t")  # hedef kapalı + disk kurulu → "geri gelecek"
    assert em.yazim_durumu()["yenidenBaslatmada"] == "geri gelecek"
    em.mandalla("t2")
    assert em.yazim_durumu()["yenidenBaslatmada"] == "kurulu gelecek (dosya güncellenemedi)"
    monkeypatch.setitem(em._yazim, "disk_kurulu", False)
    em.sifirla("t")
    assert em.yazim_durumu()["yenidenBaslatmada"] == "gelmeyecek (dosya güncellenemedi)"
    assert em.yazim_durumu(acilis=True)["yenidenBaslatmada"] == "KORUNMAYACAK"


def test_mandal_yazim_bildirimi_ekrana_iki_dilli_gider(monkeypatch, mandalli):
    from servers import api_server, live_state  # noqa: F401 — kanca api_server içe aktarılınca bağlanır

    em = mandalli
    giden = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", lambda m: giden.append(m))
    monkeypatch.setattr(em, "_kalici_yol", Path("C:/veri/estop_mandali.json"))
    monkeypatch.setitem(em._yazim, "yazilamadi", True)
    monkeypatch.setitem(em._yazim, "disk_kurulu", False)
    em._yazim_hatasini_bildir(em.yazim_durumu(yol_dahil=True))
    n = giden[0]["data"]
    assert n["level"] == "error"
    assert n["message"].startswith("⚠️ Mandal dosyası yazılamadı (C:\\veri\\estop_mandali.json)")
    assert n["mesajlar"]["en"].startswith("⚠️ The latch file could not be written (C:\\veri\\estop_mandali.json)")


# ── firmware yakma penceresi + STM kart iletileri ─────────────────────────────────────────────────────────────────────────────────────


def test_firmware_yakma_engeli_ve_kart_iletileri(dil):
    from utils import firmware_yakma_penceresi as fy
    from utils import stm32_kimlik as sk

    assert fy.baslatma_engeli() == ""  # pencere kapalı
    with fy.ac():
        assert fy.baslatma_engeli() == _t(
            YAKMA_TR,
            "The STM32 firmware is being WRITTEN (hardware update) — coils cannot be started until it finishes; EMERGENCY STOP works.",
            dil,
        )
        assert fy.baslatma_engeli("tr") == YAKMA_TR
    assert sk.operator_metni(sk.UYUM_KODU_PAKET, "tr") == PAKET_TR == sk.OPERATOR_METNI[sk.UYUM_KODU_PAKET]
    assert sk.operator_metni(sk.UYUM_KODU_KIMLIK, "tr") == KIMLIK_TR == sk.OPERATOR_METNI[sk.UYUM_KODU_KIMLIK]
    assert sk.operator_metni("bilinmeyen") == "" and sk.operator_metni(None) == ""
    assert sk.komut_red_metni("tr") == KOMUT_RED_TR == sk.KOMUT_RED_METNI
    assert sk.estop_kart_red_metni("tr") == ESTOP_RED_TR == sk.ESTOP_KART_RED_METNI
    assert sk.operator_metni(sk.UYUM_KODU_PAKET) == _t(PAKET_TR, sk.operator_metni(sk.UYUM_KODU_PAKET, "en"), dil)
    for metin in (
        sk.operator_metni(sk.UYUM_KODU_PAKET, "en"),
        sk.operator_metni(sk.UYUM_KODU_KIMLIK, "en"),
        sk.komut_red_metni("en"),
        sk.estop_kart_red_metni("en"),
    ):
        assert not TR_HARF.search(metin), metin
    assert "FW-PAKET" in sk.operator_metni(sk.UYUM_KODU_PAKET, "en") and "BLACK reset button" in sk.operator_metni(
        sk.UYUM_KODU_KIMLIK, "en"
    )
    assert "Cut the device's power or unplug the USB cable" in sk.estop_kart_red_metni("en")


def test_E_stop_kart_reddi_bildirimi_iki_dilli(monkeypatch):
    """ACİL DURDUR kart reddi: bildirim `message` Türkçe BAYT BAYT + `mesajlar.en`."""
    from servers import api_server, live_state

    giden = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", lambda m: giden.append(m))
    api_server._bildir(lambda d: "⛔ " + api_server._stm32_kimlik.estop_kart_red_metni(d), "error")
    n = giden[0]["data"]
    assert n["message"] == "⛔ " + ESTOP_RED_TR
    assert (
        n["mesajlar"]["en"]
        == "⛔ The device board rejected the STOP command — the coils may not have stopped. Cut the device's power or unplug the USB cable."
    )


# ── HC / headless_core / panel / not ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_surus_parametresi_hatasi_istek_dilinde(dil):
    from controllers.hardware_controller import ParametreGecersiz, surus_parametrelerini_hazirla

    with pytest.raises(ParametreGecersiz) as e:
        surus_parametrelerini_hazirla(50, 1e45, 0, 1, None)
    assert str(e.value) == _t(
        "Sürüş parametresi donanım paketine çevrilemiyor (OverflowError: sayı değil ya da taşıyor).",
        "The drive parameter cannot be converted into a hardware packet (OverflowError: not a number or overflows).",
        dil,
    )


def test_DB_acilis_nedeni_durum_alani_Turkce_operator_metni_istek_dilinde(dil):
    import types

    from headless_core import db_acilis_metni
    from servers import api_server

    assert db_acilis_metni("goc", "tedavi", "", "tr") == (
        "Tedavi kaydı veritabanı göç bekliyor: at-rest şifreleme göçü tamamlanmadı (dosya kilitli olabilir); dosya korunuyor, karantinaya alınmadı. "
        "Göç arka planda yeniden deneniyor; düzelmezse cihazı yeniden başlatın."
    )
    assert db_acilis_metni("acilamadi", "hasta", "RuntimeError", "tr") == (
        "Hasta veritabanı açılamadı (RuntimeError). Arka planda yeniden deneniyor; sürerse cihazı yeniden başlatın, yine sürerse teknik desteğe başvurun."
    )
    tr_goc = db_acilis_metni("goc", "tedavi", "", "tr")
    eski = api_server.state.core
    try:
        api_server.state.core = types.SimpleNamespace(
            db_acilis_hatalari={"tedavi": tr_goc},
            db_acilis_ayrintilari={"tedavi": ("goc", "GocBekliyorHatasi")},
        )
        beklenen_en = (
            "Treatment record database is waiting for migration: the at-rest encryption migration was not completed (the file may be locked); the file is preserved "
            "and was not quarantined. The migration is being retried in the background; if it does not clear, restart the device."
        )
        assert api_server._db_acilis_hatasi() == _t(tr_goc, beklenen_en, dil)
        # ayrıntısı olmayan (eski / sahte çekirdek): durum metni aynen
        api_server.state.core = types.SimpleNamespace(db_acilis_hatalari={"tedavi": "ham metin"})
        assert api_server._db_acilis_hatasi() == "ham metin"
    finally:
        api_server.state.core = eski


def test_panel_adlari_istek_dilinde_sira_ve_bilinmeyen_anahtar_degismez(dil):
    from utils import panel_yayin

    panels = {"07_combined": object(), "01_input": object(), "zzz_yeni": object()}
    cikti = panel_yayin.panelleri_yayina_hazirla(panels, lambda img: (b"x", {"image_w": 1, "image_h": 1}))
    assert [p["k"] for p in cikti] == ["01_input", "07_combined", "zzz_yeni"]
    assert [p["ad"] for p in cikti] == [_t("Girdi", "Input", dil), _t("Birleşik", "Combined", dil), "zzz_yeni"]
    petri = panel_yayin.panelleri_yayina_hazirla(
        {"04_classify": object(), "06_predictions": object()}, lambda img: (b"x", {}), panel_yayin.PETRI_PANEL_ADLARI
    )
    assert [p["ad"] for p in petri] == [_t("Sınıflama", "Classification", dil), _t("Tahmin", "Prediction", dil)]


def test_alan_notu_istek_dilinde(dil):
    from utils import mt_duzeltme

    assert mt_duzeltme.alan_notu_metni() == _t(
        "düzeltildi (÷5, yaklaşık — tezgâhta 4–5× ölçüldü)",
        "corrected (÷5, approximate — measured as 4–5× on the bench)",
        dil,
    )
    assert mt_duzeltme.alan_notu(mt_duzeltme.BOLUNDU) == mt_duzeltme.alan_notu_metni()
    assert mt_duzeltme.alan_notu(None) == ""
