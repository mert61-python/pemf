# -*- coding: utf-8 -*-
"""I18N · METİN TARAYAN KAPI YARDIMCISI (`tests/i18n_yardimci.py`) — ölçütü GEVŞETMEDİĞİNİN kanıtı (T13).

Çevrilmiş bir kapı `gorunen_metin_var` / `metin_kapisi` / `gorunur_satir` ile metni KATALOGDAN okur. Bu dosya üç yönü sınar:
  * anahtar kullanımı her yüzeyin çağrı biçiminde tanınır (t / i18n.t / ceviri.t / kritikMetin / dil::t / data-i18n / NSIS $(PEMF_…));
  * metin kataloğa taşınınca görünür kalır; `t()` kaynaktan kalkınca, TR değeri değişince ya da EN BOŞKEN görünmez (kapı KIRMIZI);
  * `metin_kapisi` yanlış anahtar / yanlış TR / boş EN'de assert eder.
"""

from __future__ import annotations

import i18n_yardimci as iy
import pytest

GES = "apps/ui/src/components/ui/GlobalEmergencyStop.tsx"


def test_anahtar_kullanimi_her_yuzey_bicimi():
    kaynak = (
        't("ayarlar.dil.baslik") i18n.t(\'ortak.iptal\') ceviri.t("hasta.hata.yok", ad=x) kritikMetin("guvenlik.acilDurdur.dugme") '
        'dil::t("ui.kurulum.basla") <b data-i18n="ui.baslik"></b> DetailPrint "$(PEMF_estopDogrulandi)" t(degisken) obj.t("a.b") '
        '<Trans i18nKey="zengin.metin" components={{}} /> <Trans i18nKey={"zengin.suslu"} />'
    )
    assert iy.kullanilan_anahtarlar(kaynak) == {
        "ayarlar.dil.baslik",
        "ortak.iptal",
        "hasta.hata.yok",
        "guvenlik.acilDurdur.dugme",
        "ui.kurulum.basla",
        "ui.baslik",
        "nsis.estopDogrulandi",
        "zengin.metin",  # <Trans i18nKey> — zengin metin (iç içe kalın / bağlantı) anahtarı da KULLANIMDIR
        "zengin.suslu",
        "a.b",  # obj.t("a.b") da bir çeviri çağrısı biçimidir (i18n örneği) — kaçırmaktansa saymak güvenli
    }


def test_gorunen_metin_kataloga_tasininca_GORUNUR_yoksa_DEGIL():
    assert iy.gorunen_metin_var(GES, "bağlantı yok"), "taşınmış metin kaynağın anahtarından okunmalı"
    assert not iy.gorunen_metin_var(GES, "Bu metin hiçbir yerde yok")


def test_EN_bos_anahtar_metni_GORUNUR_SAYMAZ(monkeypatch):
    gercek = iy.katalog

    def sahte(yuzey, dil="tr"):
        d = dict(gercek(yuzey, dil))
        if dil == "en":
            d["guvenlik.acilDurdur.dugmeBaglantiYok"] = "  "
        return d

    monkeypatch.setattr(iy, "katalog", sahte)
    assert not iy.gorunen_metin_var(GES, "bağlantı yok"), "yarım çeviri (EN boş) ölçütü geçememeli"
    with pytest.raises(AssertionError, match="EN değeri BOŞ"):
        iy.metin_kapisi(GES, "guvenlik.acilDurdur.dugmeBaglantiYok", "🚨 ACİL DURDUR (bağlantı yok)")


def test_metin_kapisi_yanlis_anahtar_ve_yanlis_TR_KIRMIZI():
    iy.metin_kapisi(GES, "guvenlik.acilDurdur.dugmeBaglantiYok", "🚨 ACİL DURDUR (bağlantı yok)")
    with pytest.raises(AssertionError, match="KULLANMIYOR"):
        iy.metin_kapisi(GES, "guvenlik.acilDurdur.olmayan", "x")
    with pytest.raises(AssertionError, match="TR değeri değişmiş"):
        iy.metin_kapisi(GES, "guvenlik.acilDurdur.dugmeBaglantiYok", "🚨 ACİL DURDUR (bağlantı kesik)")


def test_gorunur_satir_NSIS_iletisini_TR_degeriyle_acar():
    satir = '    MessageBox MB_ICONEXCLAMATION|MB_OK "$(PEMF_estopDogrulanamadiKutu)"'
    acik = iy.gorunur_satir(satir, "launcher")
    assert "ELLE kontrol edin" in acik and "$(PEMF_estopDogrulanamadiKutu)" in acik
    assert (
        iy.gorunur_satir('DetailPrint "$(PEMF_olmayanAnahtar)"', "launcher") == 'DetailPrint "$(PEMF_olmayanAnahtar)"'
    )
