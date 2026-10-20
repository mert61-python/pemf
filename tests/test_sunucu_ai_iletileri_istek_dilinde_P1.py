# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10c — AI sunucusu iletileri istek dilinde (ai_router · ai_pro_hedef · kapı iletileri · AI Pro bildirimleri).

Türkçe çıktı BAYT BAYT eskisiyle aynı; `X-PEMF-Dil: en` → İngilizce. Kapı iletileri (modalite / termal / scratch / asgari girdi) AI MİKROSERVİSİYLE ORTAK yaprak modüllerde
(Türkçe sabit, `docker/Dockerfile.ai`) kalır; GÖMÜLÜ yolda backend aynı iletiyi katalogdan üretir — burada ikisinin EŞLİĞİ kilitlenir (tek kaynak çifti).

GERÇEK: modül işlevleri + `ceviri` bağlam değişkeni + gerçek uçlar (TestClient). ⚠️ Beklenen metinler BURADA sabittir. MUTASYON: katalog TR değeri değişirse /
`ceviri.t` ham metne dönerse / eşlik bozulursa / `_ai_fail` günlüğü dile bağlanırsa KIRMIZI.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _t(tr, en, dil):
    return tr if dil == "tr" else en


# ── 1) katalog: Türkçe BAYT BAYT eski metin; İngilizcede Türkçe harf YOK ──────────────────────────────────────────────────────────────

ESKI = [
    (
        "ai.pro.hata.otonomFgsOnay",
        {},
        "Otonom Biofeedback yalnız onaylı AI Pro seansında çalışır: Kontrol → AI Pro'dan öneri alıp onaylayın. Bu analiz cihazı sürmez — otonom anahtarını kapatıp yeniden analiz edin.",
    ),
    (
        "ai.pro.hata.kediSurusKapali",
        {},
        "Kedi AI Pro sürüşü, kabin konumu doğrulanana kadar kapalı. Analizi ve öneriyi inceleyebilirsiniz; seansı Kontrol ekranından elle başlatın.",
    ),
    (
        "ai.pro.hata.otomatikHedef",
        {},
        "Otomatik seçimde mühürlenecek hedef bulunamadı: seçili hedefin kimliği okunamadı. Kare üstünde bir hedef işaretlenince yeniden deneyin ya da hedefi listeden elle seçin.",
    ),
    (
        "ai.pro.hata.otomatikHedefGecersiz",
        {"mesaj": "M.", "secili": 7},
        "M. (seçili hedefin kimliği 7 bu modelde geçersiz).",
    ),
    (
        "ai.pro.hata.hedefDesteklenmiyor",
        {"oid": 9, "model": "Kedi Organ", "gecerli": "0, 1"},
        "Hedef 9 'Kedi Organ' için desteklenmiyor (geçerli: 0, 1).",
    ),
    (
        "ai.pro.hata.konumlandirilmadi",
        {"ad": "Böbrek", "ipucu": "İ."},
        "Böbrek henüz konumlandırılmadı. İ. Kamera görüntüsü akarken konumlandırma kendiliğinden tamamlanır ve öneri otomatik hazırlanır.",
    ),
    (
        "ai.pro.hata.arastirmaDogrulama",
        {"model": "Petri Kuyu"},
        "'Petri Kuyu' ile otonom seans tezgâh doğrulaması bekliyor: bu modelin 3B konum ölçümü kabin kalibrasyonuyla henüz karşılaştırılmadı. Bu sürümde analiz ve önizleme yapılabilir, bobin sürülmez.",
    ),
    (
        "ai.pro.hata.modelTanimsiz",
        {"model": "x", "gecerli": "kedi|petri"},
        "Model 'x' tanınmıyor (geçerli: kedi|petri)",
    ),
    (
        "ai.pro.hata.dozUretmedi",
        {},
        "Model bu konum için sürülebilir bir parametre üretmedi (tüm duty=0). Lokalizasyonu tekrarlayın.",
    ),
    ("ai.pro.hata.guncellemeSuruyor", {}, "Güncelleme uygulanıyor; işlem bitene kadar AI Pro başlatılamaz."),
    ("ai.pro.hata.baslatilmadiNeden", {"sebep": "disk"}, "AI Pro BAŞLATILMADI — disk"),
    (
        "ai.pro.hata.baslatmaSirasindaDurduruldu",
        {},
        "Başlatma sırasında durdurma/acil durdurma geldi; AI Pro BAŞLATILMADI.",
    ),
    ("ai.pro.hata.sahipDegilOrgan", {}, "Bu AI Pro seansının sahibi değilsiniz; organ değiştirilemez."),
    (
        "ai.pro.hata.aktifModel",
        {"ad": "kedi", "model": "petri"},
        "Aktif model 'kedi'; 'petri' için hedef değiştirilemez.",
    ),
    (
        "ai.pro.hata.onaysizHedef",
        {"ad": "Kalp"},
        "Seans sürerken onaylanmamış hedefe geçilemez: bu seansın onaylı hedefi «Kalp». Başka hedef için AI Pro'yu durdurun, yeni öneri alın ve hekimin yeni onayıyla başlatın.",
    ),
    ("ai.pro.hata.sahipDegil", {}, "Bu AI Pro seansının sahibi değilsiniz."),
    ("ai.pro.hata.sahipDegilHedef", {}, "Bu AI Pro seansının sahibi değilsiniz; hedef değiştirilemez."),
    ("ai.pro.hata.seansSurerkenHedef", {}, "Seans sürerken hedef değiştirilemez — önce AI Pro'yu durdurun."),
    ("ai.pro.sonuc.baslatilmadi", {}, "AI Pro BAŞLATILMADI"),
    ("ai.pro.mesaj.hazirlikCalisiyor", {}, "Hazırlık zaten çalışıyor"),
    ("ai.pro.mesaj.hazirlikBasladi", {}, "Hazırlık başladı"),
    (
        "ai.pro.hazirlik.modelPaketi",
        {"ad": "Kedi Organ"},
        "'Kedi Organ' model paketi bu cihazda kurulu değil. Masaüstü PEMF uygulamasının kurulum adımından ilgili model paketini ekleyip bu ekrana dönün.",
    ),
    (
        "ai.pro.hazirlik.modelYukleme",
        {"ad": "Kedi Organ"},
        "'Kedi Organ' yüklenemedi. Uygulamayı yeniden başlatıp tekrar deneyin; sorun sürerse destek kaydında bu ekranı belirtin.",
    ),
    (
        "ai.pro.hazirlik.kamera",
        {},
        "Kamera açılamadı. Kablosunu ve başka bir uygulamanın kamerayı kullanmadığını kontrol edip hazırlığı yeniden başlatın.",
    ),
    (
        "ai.pro.ipucu.kabinDisi",
        {"ad": "Böbrek"},
        "Böbrek konumu kabin DIŞINDA ölçüldü — açıyı değiştirmek çözmez: kabin işaretinin (arka duvardaki kare kod) kadrajda, düz ve parlamasız göründüğünü kontrol edin; sürerse kabin yapılandırmasını teknik desteğe doğrulatın.",
    ),
    (
        "ai.pro.ipucu.hayvanGorunuyor",
        {"ad": "Böbrek"},
        "Hayvan görünüyor ama Böbrek seçilemedi — kamerayı biraz çevirip açıyı değiştirin.",
    ),
    ("ai.pro.ipucu.hayvanYok", {}, "Kamerayı hastaya doğrultun; hayvan kadrajda görünmüyor."),
    (
        "ai.pro.ipucu.konumOlculemedi",
        {},
        "Konum ölçülemedi: kabin işareti (arka duvardaki kare kod) kadrajda görünmüyor. Kamerayı işaret ve hedef AYNI karede kalacak şekilde ayarlayın.",
    ),
    (
        "ai.pro.ipucu.hedefSecilemedi",
        {"hedef_adi": "Tümör 1"},
        "Tümör 1 seçilemedi — hedefi tepsinin ortasına alın, kabin ışığını artırın ve işaret üzerinde parlama olmadığından emin olun.",
    ),
    (
        "ai.pro.ipucu.fantomYok",
        {},
        "Kadrajda fantom görünmüyor — fantomu tepsinin ortasına düz yerleştirin ve kabin işaretiyle birlikte kadraja alın.",
    ),
    (
        "ai.pro.ipucu.petriYok",
        {},
        "Kadrajda petri plakası görünmüyor — plakayı tepsiye düz yerleştirin, kamerayı tepeden tam kadraja alın ve kabin işaretinin görünür kaldığından emin olun.",
    ),
    ("ai.pro.hedefOrgan", {}, "hedef organ"),
    (
        "bildirim.aiProKabinYapilandirma",
        {},
        "⚠️ AI Pro: kabin yapılandırması okunamıyor — hedef doğrulanamadığı için bobinler SÜRÜLMEZ. Hayvanı yeniden konumlamak çözmez: kabin yapılandırma dosyasını (kurulum) kontrol edin ya da teknik desteğe başvurun.",
    ),
    (
        "bildirim.aiProDozUretmedi",
        {},
        "⚠️ AI Pro: doz modeli geçerli doz üretmedi — bobinler bu karede SÜRÜLMEDİ (sürerse durdurulur). AI Pro'yu durdurup yeniden başlatın; tekrarlarsa teknik desteğe başvurun.",
    ),
    ("bildirim.kaynak.aiProBaslatilamadi", {}, "AI Pro başlatılamadı — durdurma"),
    ("bildirim.kaynak.aiProHedefKaybi", {}, "AI Pro hedef-kaybı durdurması"),
    ("bildirim.kaynak.aiProDurdurma", {}, "AI Pro durdurma"),
    ("bildirim.kaynak.aiProHedefKaybiMobil", {}, "AI Pro hedef-kaybı durdurması (mobil kare)"),
    ("ai.model.kedi", {}, "Kedi Organ"),
    ("ai.model.fantom", {}, "Fantom Tümör"),
    ("ai.model.petri", {}, "Petri Kuyu"),
    ("ai.model.arastirma", {}, "Araştırma modeli"),
    ("ai.hata.hastalikAnalizi", {}, "Hastalık analizi hatası"),
    ("ai.hata.landmark", {}, "Landmark model hatası"),
    (
        "ai.hata.bobrekHastalik",
        {},
        "Böbrek hastalığı analizi yapılamadı — model dosyası veya bağımlılık eksik olabilir; sunucu günlüğünü (kidney_disease inference error) kontrol edin.",
    ),
    ("ai.hata.xaiYontemi", {"xai_method": "foo"}, "xai_method geçersiz: foo"),
    ("ai.hata.fantomAnalizi", {"e": "x"}, "Fantom analizi: x"),
    ("ai.hata.petriAnalizi", {"e": "x"}, "Petri analizi: x"),
    (
        "ai.hata.genSutunSayisi",
        {"beklenen": 100, "gelen": 90},
        "Gen sütun sayısı uyuşmuyor: beklenen 100 (eğitim/TCGA sırası), gelen 90. 1. sütun hasta ID olmalı.",
    ),
    ("ai.hata.xaiEnFazla25", {}, "Açıklama en fazla 25 hastalık CSV için üretilir (IG maliyeti)."),
    (
        "ai.hata.sesSessiz",
        {},
        "Kayıt sessiz ya da çok zayıf — ses alınamamış olabilir. Mikrofonu yaklaştırıp sessiz bir ortamda ~5 saniye tekrar kaydedin.",
    ),
    ("ai.hata.scratchYonu", {}, "scratch_yonu 'dikey' ya da 'yatay' olmalı"),
    ("ai.hata.pixelMm", {}, "pixel_mm 0.00001-0.01 aralığında olmalı (mm/px)"),
    (
        "ai.hata.scratchKurulum",
        {},
        "Yara kapanma modeli bu kurulumda hazır değil — GPU AI servisi ya da model paketi gerekli.",
    ),
    ("ai.hata.scratchMesgul", {}, "Şu anda başka bir yara-kapanma analizi sürüyor — birazdan yeniden deneyin."),
    ("ai.hata.gecersizParametre", {}, "Geçersiz parametre"),
    (
        "ai.hata.petriPlakaDegil",
        {},
        "Bu modül petri kuyucuğu plakası fotoğrafı bekliyor; yüklenen görüntüde petri kuyucuğu geometrisi bulunamadı. Fantom fotoğrafını 'Fantom Tümör' modülüne, hayvan fotoğrafını ilgili kedi modülüne yükleyin — yanlış modülde üretilen sonuç yanıltıcıdır.",
    ),
    ("ai.alan.denetimKisa", {}, "Görüntü türü (modalite) denetimi çalıştırılamadı; analiz YAPILMADI."),
]


@pytest.mark.parametrize("anahtar,parametre,eski_tr", ESKI, ids=[f"{k[0]}-{i}" for i, k in enumerate(ESKI)])
def test_TR_bayt_bayt_eski_metin_EN_ingilizce(anahtar, parametre, eski_tr):
    from utils import ceviri

    assert ceviri.t(anahtar, dil="tr", **parametre) == eski_tr
    en = ceviri.t(anahtar, dil="en", **parametre)
    govde = en
    for v in parametre.values():
        govde = govde.replace(str(v), "")  # Türkçe PARAMETRE değerleri (özel ad) sayılmaz
    assert not TR_HARF.search(govde), (anahtar, en)
    assert en != eski_tr


# ── 2) kapı iletileri: yaprak modül (mikroservis) Türkçesi ↔ backend katalog Türkçesi AYNI; İngilizce katalogdan ───────────────────────────


def test_modalite_ret_metni_yaprak_Turkcesiyle_AYNI_EN_katalogdan():
    import numpy as np
    from servers import ai_kapi_metni as km
    from utils import ceviri
    from utils import image_domain as dom

    kose = {"kaynak": "test"}
    uyumsuz = dom.DomainMismatch("kidney_ct", dom.COLOR, {dom.GRAYSCALE}, kose)
    assert (
        km.alan_ret_metni(uyumsuz, "tr")
        == uyumsuz.user_message()
        == (
            "Bu modül gri tonlamalı tıbbi görüntü (CT / röntgen / ultrason) bekliyor; yüklenen görüntü renkli fotoğraf gibi görünüyor. "
            "Yanlış görüntüyle üretilen sonuç yanıltıcı olur — lütfen doğru türde bir görüntü yükleyin."
        )
    )
    en = km.alan_ret_metni(uyumsuz, "en")
    assert en == (
        "This module expects grayscale medical image (CT / X-ray / ultrasound); the uploaded image looks like color photograph. "
        "A result produced with the wrong image would be misleading — please upload an image of the right type."
    )
    iki = dom.DomainMismatch("x", dom.GRAYSCALE, {dom.STAINED, dom.COLOR}, kose)
    assert km.alan_ret_metni(iki, "tr") == iki.user_message()  # sıralama + " veya " birleştirme
    assert " or " in km.alan_ret_metni(iki, "en")
    # termal
    termal = dom.TermalUyumsuz({})
    assert km.alan_ret_metni(termal, "tr") == termal.user_message() == dom.TERMAL_UYUMSUZ_MESAJI
    assert not TR_HARF.search(km.alan_ret_metni(termal, "en"))
    # scratch: üç neden
    for neden in ("duz", "gurultu", "yapi_yok"):
        s = dom.ScratchUyumsuz({"neden": neden})
        assert km.alan_ret_metni(s, "tr") == s.user_message() == dom.SCRATCH_UYUMSUZ_MESAJLARI[neden]
        assert not TR_HARF.search(km.alan_ret_metni(s, "en"))
    # denetim çalıştırılamadı
    assert km.denetim_calismadi("tr") == dom.DENETIM_CALISMADI_MESAJI == dom.DomainCheckError("x", "y").user_message()
    assert ceviri.t("ai.alan.denetimCalismadi", dil="en").startswith("The image type (modality) check could not be run")
    assert np is not None


def test_termal_dogrulama_metinleri_yaprak_Turkcesiyle_AYNI():
    # kapalı (cihazda denetim kapalı)
    import os

    import numpy as np
    from servers import ai_kapi_metni as km
    from utils import image_domain as dom

    eski = os.environ.get("PEMF_AI_DOMAIN_GUARD")
    os.environ["PEMF_AI_DOMAIN_GUARD"] = "0"
    try:
        kapali = dom.termal_girdi_dogrulamasi(np.zeros((8, 8, 3), np.uint8))
    finally:
        if eski is None:
            os.environ.pop("PEMF_AI_DOMAIN_GUARD", None)
        else:
            os.environ["PEMF_AI_DOMAIN_GUARD"] = eski
    assert kapali["durum"] == "kapali"
    assert km.termal_dogrulama_cevir(kapali, "tr") == kapali  # TR bayt bayt (uyarı + yön notu)
    en = km.termal_dogrulama_cevir(kapali, "en")
    assert en["uyari"].startswith("The image type check is turned off") and en["yon_notu"].startswith(
        "Make sure the palette"
    )
    assert (
        en["durum"] == kapali["durum"] and en["dogrulandi"] is False and en["olcum"] == kapali["olcum"]
    )  # karar alanları değişmez
    # her palet + akromatik + kararsız (yaprak işlevleriyle)
    for palet in ("inferno", "magma", "plasma", "iron", "hot", "jet", "turbo", "rainbow", "bilinmeyen"):
        d = {
            "durum": dom.TERMAL_PALET,
            "dogrulandi": True,
            "uyari": None,
            "yon_notu": dom.termal_yon_notu(dom.TERMAL_PALET, {"palet": palet}),
            "olcum": {"palet": palet},
        }
        assert km.termal_dogrulama_cevir(d, "tr") == d, palet
        assert not TR_HARF.search(km.termal_dogrulama_cevir(d, "en")["yon_notu"]), palet
    for durum in (dom.TERMAL_AKROMATIK, dom.TERMAL_KARARSIZ):
        d = {
            "durum": durum,
            "dogrulandi": False,
            "uyari": dom.TERMAL_UYARILARI[durum],
            "yon_notu": dom.termal_yon_notu(durum, {}),
            "olcum": {},
        }
        assert km.termal_dogrulama_cevir(d, "tr") == d, durum
        assert "could not be verified as thermal" in km.termal_dogrulama_cevir(d, "en")["uyari"]


def test_asgari_girdi_metinleri_yaprak_Turkcesiyle_AYNI():
    from servers import ai_kapi_metni as km
    from utils import klinik_asgari as ka

    with pytest.raises(ka.AsgariGirdiYok) as e:
        ka.vital_kapisi({"weight": 0, "hr": 0, "temp": 0, "age": -1})
    ag = e.value
    assert ag.kod == "vital" and ag.ayrinti == ["kilo", "nabiz", "sicaklik", "yas"]
    assert (
        km.asgari_metni(ag, "tr")
        == ag.user_message()
        == (
            "Güvenilir hastalık tahmini için geçerli vital veriler gerekli: kilo (kg) 0-30 aralığında girilmeli; nabız (bpm) girilmeli (makul: ~120-220); "
            "vücut sıcaklığı (°C) girilmeli (makul: ~37-39.5); yaş negatif olamaz"
        )
    )
    en = km.asgari_metni(ag, "en")
    assert (
        en.startswith("Valid vital signs are required")
        and "weight (kg) must be entered in the 0-30 range" in en
        and "age cannot be negative" in en
    )
    assert not TR_HARF.search(en.replace("°", ""))
    with pytest.raises(ka.AsgariGirdiYok) as e2:
        ka.ckd_kapisi({"age": 5})
    ag2 = e2.value
    assert ag2.kod == "ckd" and ag2.ayrinti["eksik"] == ["sc", "bu", "sg", "al", "hemo"]
    assert km.asgari_metni(ag2, "tr") == ag2.user_message()
    en2 = km.asgari_metni(ag2, "en")
    assert (
        "missing: serum creatinine, blood urea, urine specific gravity, albumin, hemoglobin" in en2
        and not TR_HARF.search(en2)
    )
    # eski / mikroservis kaynaklı (kodsuz) istisna: kendi iletisi aynen
    assert km.asgari_metni(ka.AsgariGirdiYok("Türkçe ileti"), "en") == "Türkçe ileti"


# ── 3) `_ai_fail`: günlük HER ZAMAN Türkçe, yanıt istek dilinde ─────────────────────────────────────────────────────────────────────────


def test_ai_fail_gunluk_Turkce_yanit_istek_dilinde(dil, caplog):
    from fastapi import HTTPException
    from servers import ai_router
    from utils import ceviri

    caplog.set_level(logging.ERROR)
    h = ai_router._ai_fail(lambda d: ceviri.t("ai.hata.hastalikAnalizi", dil=d), RuntimeError("x"))
    assert h.status_code == 500 and h.detail == _t("Hastalık analizi hatası", "Disease analysis error", dil)
    assert "Hastalık analizi hatası" in caplog.text and "Disease analysis error" not in caplog.text  # günlük Türkçe
    # düz metin etiket (eski çağıran) aynen; HTTPException aynen geçer
    assert ai_router._ai_fail("düz", RuntimeError("x")).detail == "düz"
    orj = HTTPException(status_code=422, detail="d")
    assert ai_router._ai_fail(lambda d: "x", orj) is orj


# ── 4) AI Pro: organ / model adları (veri Türkçe, gösterim istek dilinde), hazırlık hatası, bildirim ─────────────────────────────────────


def test_organ_ve_model_adlari_veri_Turkce_gosterim_istek_dilinde(dil):
    from servers import ai_pro_hedef, ai_router

    k = ai_pro_hedef.KediSaglayici()
    assert k.hedef_adi(2) == "Böbrek" and ai_router._organ_adi(0) == "Tüm Vücut"  # VERİ (`mode`): dil ne olursa Türkçe
    assert k.hedef_adi_gosterim(2) == _t("Böbrek", "Kidney", dil)
    assert ai_pro_hedef.hedef_gosterim_adi(k, 9) == _t("Akciğer (sağ)", "Lung (right)", dil)
    assert ai_pro_hedef.model_adi(k) == _t("Kedi Organ", "Cat Organ", dil)
    assert k.title == "Kedi Organ"  # VERİ (`mode` / `modelName`)
    assert ai_pro_hedef.model_adi(object()) == _t("Araştırma modeli", "Research model", dil)
    assert k.ipucu(True, k.hedef_adi_gosterim(2)).startswith(
        _t("Hayvan görünüyor ama Böbrek", "The animal is visible but Kidney", dil)
    )


def test_hazirlik_hatasi_depolanan_Turkce_durum_yaniti_istek_dilinde(dil):
    from servers import ai_pro_hedef, ai_router

    k = ai_pro_hedef.KediSaglayici()
    kod, metin = ai_router._hazirlik_hata_sinifi(FileNotFoundError("x"), k)
    assert kod == "model_paketi" and metin == (
        "'Kedi Organ' model paketi bu cihazda kurulu değil. Masaüstü PEMF uygulamasının kurulum adımından ilgili model paketini ekleyip bu ekrana dönün."
    )
    kod2, metin2 = ai_router._hazirlik_hata_sinifi(RuntimeError("x"), k)
    assert kod2 == "model_yukleme" and metin2.startswith("'Kedi Organ' yüklenemedi.")
    eski = (ai_router._ai_hazirlik_hata, ai_router._ai_hazirlik_hata_kodu, ai_router._ai_hazirlik_hata_saglayici)
    try:
        ai_router._ai_hazirlik_hata, ai_router._ai_hazirlik_hata_kodu, ai_router._ai_hazirlik_hata_saglayici = (
            metin,
            kod,
            k,
        )
        assert ai_router._hazirlik_hata_goster() == _t(
            metin,
            "The 'Cat Organ' model package is not installed on this device. Add the relevant model package from the setup step of the desktop PEMF app, then come back to this screen.",
            dil,
        )
        ai_router._ai_hazirlik_hata, ai_router._ai_hazirlik_hata_kodu = "elle yazılmış", ""
        assert ai_router._hazirlik_hata_goster() == "elle yazılmış"  # kodsuz metin aynen
    finally:
        ai_router._ai_hazirlik_hata, ai_router._ai_hazirlik_hata_kodu, ai_router._ai_hazirlik_hata_saglayici = eski


def test_AI_Pro_kabin_okunamaz_bildirimi_iki_dilli(monkeypatch):
    from servers import ai_router, api_server, live_state

    giden = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", lambda m: giden.append(m))
    monkeypatch.setitem(ai_router._kabin_okunamaz_bildirilen, "anahtar", None)
    monkeypatch.setitem(api_server._active_session, "onay_kimligi", "t-10c")
    ai_router._kabin_okunamaz_bildir()
    n = giden[0]["data"]
    assert n["level"] == "error" and n["message"].startswith(
        "⚠️ AI Pro: kabin yapılandırması okunamıyor — hedef doğrulanamadığı için bobinler SÜRÜLMEZ."
    )
    assert n["mesajlar"]["tr"] == n["message"]
    assert n["mesajlar"]["en"].startswith(
        "⚠️ AI Pro: the cabin configuration cannot be read — the coils will NOT be driven"
    )
    ai_router._kabin_okunamaz_bildirilen["anahtar"] = None


# ── 5) gerçek uçlar (TestClient): istek dili ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


def test_gercek_uc_vital_kapisi_istek_dilinde(istemci):
    tr = istemci.post("/api/ai/disease", json={})
    assert tr.status_code == 422, tr.text[:200]
    assert tr.json()["detail"] == (
        "Güvenilir hastalık tahmini için geçerli vital veriler gerekli: kilo (kg) 0-30 aralığında girilmeli; nabız (bpm) girilmeli (makul: ~120-220); "
        "vücut sıcaklığı (°C) girilmeli (makul: ~37-39.5)"
    )
    en = istemci.post("/api/ai/disease", json={}, headers={"X-PEMF-Dil": "en"})
    assert en.status_code == 422
    assert en.json()["detail"] == (
        "Valid vital signs are required for a reliable disease prediction: weight (kg) must be entered in the 0-30 range; "
        "pulse (bpm) must be entered (reasonable: ~120-220); body temperature (°C) must be entered (reasonable: ~37-39.5)"
    )
    # Accept-Language YOK SAYILIR
    al = istemci.post("/api/ai/disease", json={}, headers={"Accept-Language": "en-US"})
    assert al.json()["detail"].startswith("Güvenilir hastalık tahmini")


def test_gercek_uc_xai_yontemi_istek_dilinde(istemci):
    tr = istemci.post("/api/ai/vision/thermal", data={"xai_method": "foo"})
    assert tr.status_code == 422 and tr.json()["detail"] == "xai_method geçersiz: foo", tr.text[:200]
    en = istemci.post("/api/ai/vision/thermal", data={"xai_method": "foo"}, headers={"X-PEMF-Dil": "en"})
    assert en.status_code == 422 and en.json()["detail"] == "xai_method is invalid: foo"
