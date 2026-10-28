# -*- coding: utf-8 -*-
"""AI KAPI İLETİLERİ — istek dilinde (I18N-P1 · sunucu 10c).

`utils/image_domain.py`, `utils/klinik_asgari.py` ve `utils/ses_kalitesi.py` AI MİKROSERVİSİYLE ORTAK yaprak modüllerdir (`docker/Dockerfile.ai`
imajına YALNIZ bu üç dosya girer; `ceviri` ve katalog YOK) → kendi Türkçe iletileri kaynakta kalır (muaf, gerekçeli). Bu modül, GÖMÜLÜ (backend) yolda
aynı iletileri KATALOGDAN istek dilinde üretir: yaprak modüller yapılandırılmış bilgiyi (`DomainMismatch.detected / expected / metrics`,
`AsgariGirdiYok.kod / ayrinti`, termal `durum / olcum`) zaten taşır; metin burada kurulur. Türkçe çıktı yaprak modülün sabitiyle BAYT BAYT aynıdır
(eşlik testi: `tests/test_sunucu_ai_iletileri_istek_dilinde_P1.py`). Mikroservis yolunda (delegate) yanıt metni mikroservisin Türkçesidir (dil bilinmez).
"""

from __future__ import annotations

from utils import ceviri
from utils import image_domain as _dom


def modalite_adi(modalite: str, dil: str | None = None) -> str:
    if modalite == _dom.GRAYSCALE:
        return ceviri.t("ai.alan.gri", dil=dil)
    if modalite == _dom.STAINED:
        return ceviri.t("ai.alan.boyali", dil=dil)
    if modalite == _dom.COLOR:
        return ceviri.t("ai.alan.renkli", dil=dil)
    return str(modalite)


def scratch_metni(neden, dil: str | None = None) -> str:
    if neden == "duz":
        return ceviri.t("ai.scratch.duz", dil=dil)
    if neden == "gurultu":
        return ceviri.t("ai.scratch.gurultu", dil=dil)
    return ceviri.t("ai.scratch.yapiYok", dil=dil)


def denetim_calismadi(dil: str | None = None) -> str:
    return ceviri.t("ai.alan.denetimCalismadi", dil=dil)


def alan_ret_metni(dm, dil: str | None = None) -> str:
    """`DomainMismatch` (ve alt sınıfları) için kullanıcı iletisi — yaprak modülün `user_message()` karşılığı, istek dilinde."""
    if isinstance(dm, _dom.ScratchUyumsuz):
        return scratch_metni(dm.metrics.get("neden"), dil)
    if isinstance(dm, _dom.TermalUyumsuz):
        return ceviri.t("ai.termal.uyumsuz", dil=dil)
    bekl = ceviri.t("ai.alan.ayrac", dil=dil).join(sorted(modalite_adi(e, dil) for e in dm.expected))
    return ceviri.t("ai.alan.uyusmuyor", dil=dil, bekl=bekl, tespit=modalite_adi(dm.detected, dil))


def _petri_olcum(m: dict, dil: str | None) -> str:
    """`plausibility.user_message`ın ölçüm parçası — aynı biçim (`.2f` / `.0f`), aynı ETKİN eşikler; ölçülemezse "" (kaynaktaki gibi)."""
    try:
        from ai_hub.inference_petri_dish import (
            plausibility as _pl,  # tembel: yalnız ret anında (ağır zincir yok — numpy / cv2)
        )

        esik = _pl.esikleri_coz(m.get("thresholds"))
        p = {
            "c": f"{float(m.get('circularity_med', 0.0)):.2f}",
            "mc": f"{esik['circularity_med']:.2f}",
            "k": f"{float(m.get('conf_med', 0.0)):.2f}",
            "mk": f"{esik['conf_med']:.2f}",
            "a": f"{100.0 * float(m.get('max_area_frac', 0.0)):.0f}",
            "ma": f"{100.0 * esik['max_area_frac']:.0f}",
        }
        return ceviri.t("ai.hata.petriOlcum", dil=dil, **p)
    except Exception:
        return ""


def petri_ret_katalog_metni(m: dict, dil: str | None = None) -> str:
    """Petri makullik reddinin KATALOGDAN kurulan hâli (ölçüm sözlüğünden; `message` okunmaz). Eşlik testi bunun Türkçesini kaynağın
    metniyle karşılaştırır — güvence dalı (aşağıda) bu karşılaştırmayı GİZLEMESİN diye ayrı işlev."""
    if m.get("kip") == "plaka":
        # T3 · Y193: tekil kipe yönlendirmeyen metin (eski `petriPlakaIzgara` yalnız TR taban kapısı için katalogda durur).
        return ceviri.t("ai.hata.petriPlakaIzgaraYalnizPlaka", dil=dil)
    olculer = {k: v for k, v in m.items() if k != "message"}  # kaynak ölçüm parçasını ölçüm sözlüğü BOŞ değilse yazar
    return ceviri.t("ai.hata.petriGeometriYok", dil=dil, olcum=_petri_olcum(olculer, dil) if olculer else "")


def petri_ret_metni(m, dil: str | None = None) -> str:
    """I18NI-O.2: petri MAKULLİK REDDİ iletisi istek dilinde. Denetim ve Türkçe metin `ai_hub/inference_petri_dish/plausibility.py`'dedir
    (mikroservisle ortak; i18n yüzeyi değil): `plate_user_message` (plaka kipi) / `user_message` (ölçümlü). Burada AYNI ileti katalogdan kurulur.
    Katalog Türkçesi kaynağın metniyle BAYT BAYT aynıdır (eşlik testi `tests/test_I18NI_petri_makullik_reddi_istek_dilinde.py`). GÜVENCE:
    kaynak metin değişir de katalog geride kalırsa Türkçede kaynağın metni AYNEN döner (görünüm hiç değişmez) ve eşlik kapısı KIRMIZI olur."""
    msg = m.get("message") if isinstance(m, dict) else None
    if not (isinstance(msg, str) and msg.strip()):
        return ceviri.t("ai.hata.petriPlakaDegil", dil=dil)
    aday = petri_ret_katalog_metni(m, dil)
    if (ceviri.gecerli_dil(dil) or ceviri.etkin_dil()) == "tr" and aday != msg:
        return msg
    return aday


def termal_yon_ipucu(palet: str, dil: str | None = None) -> str:
    if palet == "inferno":
        return ceviri.t("ai.termal.yon.inferno", dil=dil)
    if palet == "magma":
        return ceviri.t("ai.termal.yon.magma", dil=dil)
    if palet == "plasma":
        return ceviri.t("ai.termal.yon.plasma", dil=dil)
    if palet == "iron":
        return ceviri.t("ai.termal.yon.iron", dil=dil)
    if palet == "hot":
        return ceviri.t("ai.termal.yon.hot", dil=dil)
    if palet == "jet":
        return ceviri.t("ai.termal.yon.jet", dil=dil)
    if palet == "turbo":
        return ceviri.t("ai.termal.yon.turbo", dil=dil)
    if palet == "rainbow":
        return ceviri.t("ai.termal.yon.rainbow", dil=dil)
    return ceviri.t("ai.termal.yon.varsayilan", dil=dil)


def termal_dogrulama_cevir(d: dict, dil: str | None = None) -> dict:
    """`termal_girdi_dogrulamasi` çıktısındaki `uyari` / `yon_notu` metinlerini istek diline çevirir (`durum` / `olcum.palet` makine-okur alanlardan).
    Kapı kararı, `durum`, `dogrulandi`, `olcum` DEĞİŞMEZ."""
    if not isinstance(d, dict):
        return d
    cikti = dict(d)
    durum = d.get("durum")
    if d.get("uyari"):
        if durum == "kapali":
            cikti["uyari"] = ceviri.t("ai.termal.kapali", dil=dil)
        elif durum == _dom.TERMAL_AKROMATIK:
            cikti["uyari"] = ceviri.t("ai.termal.akromatik", dil=dil)
        else:
            cikti["uyari"] = ceviri.t("ai.termal.kararsiz", dil=dil)
    if d.get("yon_notu"):
        palet = str((d.get("olcum") or {}).get("palet") or "")
        cikti["yon_notu"] = ceviri.t("ai.termal.yonNotu", dil=dil, ipucu=termal_yon_ipucu(palet, dil))
    return cikti


def _vital_sorunu(kod: str, dil: str | None) -> str:
    if kod == "kilo":
        return ceviri.t("ai.klinik.kilo", dil=dil)
    if kod == "nabiz":
        return ceviri.t("ai.klinik.nabiz", dil=dil)
    if kod == "sicaklik":
        return ceviri.t("ai.klinik.sicaklik", dil=dil)
    return ceviri.t("ai.klinik.yas", dil=dil)


def _ckd_alani(anahtar: str, dil: str | None) -> str:
    if anahtar == "sc":
        return ceviri.t("ai.klinik.alan.sc", dil=dil)
    if anahtar == "bu":
        return ceviri.t("ai.klinik.alan.bu", dil=dil)
    if anahtar == "sg":
        return ceviri.t("ai.klinik.alan.sg", dil=dil)
    if anahtar == "al":
        return ceviri.t("ai.klinik.alan.al", dil=dil)
    return ceviri.t("ai.klinik.alan.hemo", dil=dil)


def asgari_metni(ag, dil: str | None = None) -> str:
    """`AsgariGirdiYok` kullanıcı iletisi — `kod` / `ayrinti` varsa katalogdan istek dilinde; yoksa (eski / mikroservis kaynaklı) kendi iletisi."""
    kod = getattr(ag, "kod", None)
    ayrinti = getattr(ag, "ayrinti", None)
    if kod == "vital" and ayrinti:
        return ceviri.t("ai.klinik.vitalGerekli", dil=dil, sorunlar="; ".join(_vital_sorunu(k, dil) for k in ayrinti))
    if kod == "ckd" and isinstance(ayrinti, dict):
        eksik = ", ".join(_ckd_alani(k, dil) for k in ayrinti.get("eksik", []))
        ek = {
            "dolu": ayrinti.get("dolu"),
            "toplam": ayrinti.get("toplam"),
            "asgari": ayrinti.get("asgari"),
            "eksik": eksik,
        }
        return ceviri.t("ai.klinik.yetersiz", dil=dil, **ek)
    if kod == "ckd_kategorik" and isinstance(ayrinti, dict):
        # D6.20 (B-5.21): sözlük DIŞI kategorik değer — alan kodu + gelen değer + geçerli değerler (kodlar çevrilmez).
        parca = [(d.get("alan", ""), d.get("deger", ""), ", ".join(d.get("gecerli", []))) for d in ayrinti["alanlar"]]
        alanlar = "; ".join(
            ceviri.t("ai.klinik.kategorikDeger", dil=dil, alan=a, deger=v, gecerli=g) for a, v, g in parca
        )
        return ceviri.t("ai.klinik.kategorikGecersiz", dil=dil, alanlar=alanlar)
    return ag.user_message()
