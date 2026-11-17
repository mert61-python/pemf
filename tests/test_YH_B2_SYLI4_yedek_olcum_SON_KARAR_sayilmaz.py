# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YH B2 · S-YLI.4 (Tezgâh-2 "bir sonraki yayına" listesi 1) — STM 20 sn'de bağlanmazsa yapılan YEDEK ÖLÇÜM son karar DEĞİLDİR.

ÖLÇÜLEN KUSUR (Tezgâh-2, 13 Kasım 12:35, `TEZGAH-2-YAYIN.md` #5): kart USB'si çekiliyken güncelleme → yeni backend 20 sn sonra
`STM 20 sn içinde bağlanmadı — YALNIZ ÖLÇÜM (yakma YOK); karar ilk bağlantıda` yazdı; `/api/health` → `firmwareGuncelleme`
`kontrol_edildi: true` oldu ve başlatıcının bekleyicisi (`firmware_kararini_bekle`) bunu SON karar sayıp (Devam) güncellemeyi
ONAYLADI (`runtime.old` silindi). Kart sonra takılınca GERÇEK karar el sıkışmada verildi — kural olsaydı `istemciGeriAlinmali:
true` çıkacaktı ama başlatıcı artık beklemiyordu. Bugün kural (firmware uyum varlığı) olmadığı için zararsız; uyum varlığı v2.6
yayınlanmadan ÖNCE kapanmalı (Y285).
Kilitlenen (backend tarafı, yalnız-ek): `firmwareGuncelleme.yedekOlcum` — yedek ölçüm yazdıysa `true` (gerçek karar ilk
bağlantıda GELECEK), gerçek karar yazdıysa `false`. Başlatıcı tarafı: `launcher/core/src/backend.rs` `KRITIK_SYLI4_*` (yalnız
JSON `true` yedek ölçüm → `Bekliyor`; bütçe dolarsa `Bilinmiyor` = geri alma YOK). Y253 / Y254 onay davranışı DEĞİŞMEDİ.
⚠️ Gerçek kart, seri port, ST-Link, ağ YOK — çekirdek SAHTE, uyum varlığı yamalı (aparat H11: kart 2.3, kural firmwareMin 2.4).
"""

from __future__ import annotations

import logging
import time

import backend_service as bs
import pytest
from test_firmware_yakma_sonrasi_SURUM_TEYIDI_H11 import BANNER_FMT, zincir  # noqa: F401 — fikstür
from utils import stm32_kimlik

_LOG = logging.getLogger("yh_b2_syli4")


class _Cekirdek:
    """HeadlessCore yerine: yalnız `_donanim_guncellemesi_safe`in okuduğu alanlar (banner hazır → bekleme yok)."""

    def __init__(self, bagli: bool, surum: str = "2.3"):
        self.stm_is_connected = bagli
        self.stm_kimlik = stm32_kimlik.banner_ayristir(BANNER_FMT.format(surum)) if bagli else None


class _Veriyolu:
    def __init__(self):
        self.abone: dict = {}

    def subscribe(self, olay, cb, kimlik):
        self.abone[olay] = cb
        return True


@pytest.fixture()
def bayraksiz(monkeypatch):
    monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)  # Y1 varsayılanı: yalnız ölçer


def test_KRITIK_SYLI4_yedek_olcum_YEDEK_oldugunu_soyler_son_karar_DEGIL(zincir, bayraksiz):
    """STM bağlanmadan (20 sn yedeği) → `kontrol_edildi` true ama `yedekOlcum` TRUE: başlatıcı bunu son karar saymaz."""
    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=False), _LOG, yalniz_olcum=True)
    d = zincir["fm"].durum()
    assert d["kontrol_edildi"] is True and d["istemciGeriAlinmali"] is False, f"aparat: yedek ölçüm {d}"
    assert d.get("yedekOlcum") is True, (
        "S-YLI.4: yedek ölçüm (STM bağlı değil) `/api/health`te SON karardan AYIRT EDİLEMİYOR — başlatıcı onu son karar sayıp "
        f"geç el sıkışmadaki geri alma kararını kaçırır: {d}"
    )


def test_KRITIK_SYLI4_gec_el_sikismadaki_GERCEK_karar_yedegi_EZER_yedekOlcum_false(zincir, bayraksiz):
    """Yedekten SONRA kart bağlanır → gerçek karar (kesin uyumsuz + STM bağlı + ileri kapalı) `istemciGeriAlinmali` true,
    `yedekOlcum` FALSE (son karar)."""
    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=False), _LOG, yalniz_olcum=True)
    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=True, surum="2.3"), _LOG)
    d = zincir["fm"].durum()
    assert d["istemciGeriAlinmali"] is True and d["uyum"] is False, (
        f"aparat: kart 2.3 / kural 2.4 kesin uyumsuz değil: {d}"
    )
    assert d.get("yedekOlcum") is False, (
        f"gerçek karar yazıldı ama hâlâ 'yedek ölçüm' görünüyor — başlatıcı bütçe boyunca bekler: {d}"
    )


def test_KRITIK_SYLI4_manifest_YOKKEN_de_yedek_isaretlenir_gercek_kararda_kalkar(zincir, bayraksiz):
    """Uyum varlığı okunamadı (internet yok) dalı da `kontrol_edildi` true yazar → yedekte işaretli, gerçek kararda değil."""
    zincir["mp"].setattr(zincir["fm"], "manifest_oku", lambda **_k: None)
    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=False), _LOG, yalniz_olcum=True)
    d = zincir["fm"].durum()
    assert d["kontrol_edildi"] is True and "manifest okunamadı" in d["gerekce"], f"aparat: {d}"
    assert d.get("yedekOlcum") is True, f"manifest yok + yedek ölçüm son karar gibi görünüyor: {d}"
    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=True), _LOG)
    assert zincir["fm"].durum().get("yedekOlcum") is False, zincir["fm"].durum()


def test_KARSIT_SYLI4_dogrudan_GERCEK_karar_yedek_DEGIL_ve_baslangicta_alan_false(zincir, bayraksiz):
    """Kart zamanında bağlanırsa (olağan saha) karar baştan gerçek: `yedekOlcum` false. Açılışta (karar yokken) alan false —
    `kontrol_edildi` false zaten `Bekliyor` demektir."""
    assert zincir["fm"].durum().get("yedekOlcum") is False, (
        f"başlangıç durumunda alan yok / yanlış: {zincir['fm'].durum()}"
    )
    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=True, surum="2.4"), _LOG)
    d = zincir["fm"].durum()
    assert d["kontrol_edildi"] is True and d["uyum"] is True and d.get("yedekOlcum") is False, d


def test_KRITIK_SYLI4_saglik_ucu_yedekOlcum_alanini_TASIR(zincir, bayraksiz):
    """Başlatıcının okuduğu yer `/api/health` → `firmwareGuncelleme` (system_router `_firmware_guncelleme_durumu`)."""
    from servers import system_router as sr

    bs._donanim_guncellemesi_safe(_Cekirdek(bagli=False), _LOG, yalniz_olcum=True)
    fg = sr._firmware_guncelleme_durumu()
    assert fg is not None and fg.get("yedekOlcum") is True, f"sağlık ucu yedek işaretini taşımıyor: {fg}"


def test_KRITIK_SYLI4_AKIS_20sn_yedegi_sonra_GEC_el_sikisma_karari_SON_soz(zincir, bayraksiz, monkeypatch):
    """GERÇEK `_donanim_guncellemesi_kur` akışı (sahte veriyolu, yedek süresi kısaltılmış): STM bağlanmaz → yedek ölçüm
    (`yedekOlcum` true) → kart geç takılır (`hardware.stm.connected`) → gerçek karar (`istemciGeriAlinmali` true, `yedekOlcum` false)."""
    monkeypatch.setattr(bs, "DONANIM_KARAR_YEDEK_S", 0.2)
    cekirdek = _Cekirdek(bagli=False)
    bus = _Veriyolu()
    bs._donanim_guncellemesi_kur(cekirdek, _LOG, event_bus=bus)
    fm = zincir["fm"]
    son = time.monotonic() + 10
    while time.monotonic() < son and not fm.durum()["kontrol_edildi"]:
        time.sleep(0.05)
    d = fm.durum()
    assert d["kontrol_edildi"] is True and d.get("yedekOlcum") is True, f"yedek ölçüm son karar gibi göründü: {d}"
    gec = _Cekirdek(bagli=True, surum="2.3")
    cekirdek.stm_is_connected, cekirdek.stm_kimlik = gec.stm_is_connected, gec.stm_kimlik
    bus.abone["hardware.stm.connected"]({"kaynak": "yh-b2"})
    son = time.monotonic() + 10
    while time.monotonic() < son and fm.durum().get("yedekOlcum") is not False:
        time.sleep(0.05)
    d = fm.durum()
    assert d.get("yedekOlcum") is False and d["istemciGeriAlinmali"] is True, (
        f"geç el sıkışma kararı yedeği ezmedi: {d}"
    )
