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
    return ag.user_message()
