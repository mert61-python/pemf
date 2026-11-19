# -*- coding: utf-8 -*-
"""SUNUCU ÇEVİRİSİ (I18N · Y157–Y161, T5 / T6 / T7) — kullanıcıya dönen metin isteğin DİLİNDE.

===============================================================================
KURAL
===============================================================================
  * Katalog: `apps/backend/i18n/{tr,en}.json` (i18next JSON v4: iç içe anahtar, `{{ad}}` yer tutucu, `_one` / `_other` çoğul) — arayüz
    / launcher / site kataloglarıyla AYNI biçim, AYNI kapı aracı (`scripts/i18n/katalog.py`, K-1…K-7).
  * İsteğin dili: `X-PEMF-Dil: tr|en` başlığı > `?dil=tr|en` (URL ile açılan PDF / görsel / iframe) > `tr`. ⚠️ `Accept-Language`
    OKUNMAZ: WebView2 / tarayıcı onu işletim sisteminin dilinden kendisi doldurur → İngilizce Windows'ta Türkçe seçili arayüze İngilizce
    yanıt dönerdi. Başlıksız / geçersiz = `tr` → başlık göndermeyen eski istemci (yayındaki APK, eski arayüz) bugünkü gibi Türkçe alır.
  * İstek İÇİNDE dil `istek_dili_var`'dan (api_server ara katmanı kurar); istek DIŞINDA (zamanlanmış bildirim, arka plan PDF, MQTT /
    seri iş parçacığı) cihaz düzeyindeki "arayüz dili" ayarından (`<veri kökü>/arayuz_dili.json`; masaüstü arayüz dil seçince yazar,
    launcher da okur), yoksa `tr`.
  * Eksik anahtar: test koşusunda (`PYTEST_CURRENT_TEST` / `PEMF_I18N_KATI=1`) `KeyError` (sessiz geçmez); üründe Türkçe değere, o da
    yoksa anahtarın kendisine düşer ve günlüğe ERROR yazılır (kullanıcı boş ileti görmez).
  * Günlük iletileri (logger.*) ÇEVRİLMEZ — geliştirici içindir, Türkçe kalır. DB değerleri çevrilmez (gösterimde değer → anahtar).

⚠️ YAPRAK MODÜL: yalnız stdlib (+ `utils.path_utils` cihaz ayarı için, tembel içe aktarma) — her katmandan güvenle içe aktarılır.
⚠️ DONMUŞ EXE: katalog `sys._MEIPASS/i18n` (PyInstaller `datas`: `apps/backend/i18n` → `i18n`); donmuş dal ÖNCE gelir, yukarı yürüme
YOK (hafıza "Kök ARAMA donmuş EXE"). Kapı: `tests/test_i18n_sunucu_altyapi.py` + K-6.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

DILLER = ("tr", "en")
YEDEK_DIL = "tr"
DIL_BASLIGI = "X-PEMF-Dil"
DIL_PARAMETRESI = "dil"
CIHAZ_DILI_DOSYASI = "arayuz_dili.json"

#: İNGİLİZCE BAYRAĞI (Y158) — TEK KAYNAK depo kökü `i18n/bayrak.json`; `scripts/i18n/bayrak.py` yazar, K-5 eşliği denetler. ⚠️ ELLE DEĞİŞTİRME.
#: Kapalıyken İSTEK DIŞI dil (cihaz ayarı) her zaman tr — arayüz / launcher / site / DEMA ile aynı kural (I18NI-A3.4). İstek dili (başlık)
#: etkilenmez: bayrak kapalı arayüz zaten `tr` gönderir.
I18N_EN_ACIK: bool = True

#: İsteğin dili (api_server ara katmanı kurar). None = istek dışı (arka plan) → cihaz ayarı.
istek_dili_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("pemf_istek_dili", default=None)

_log = logging.getLogger(__name__)
_kilit = threading.Lock()
_kataloglar: dict[str, dict[str, str]] | None = None
_YER_TUTUCU = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def katalog_dizini() -> Path:
    """Katalog dizini. Donmuş EXE'de `_MEIPASS/i18n` (ÖNCE); kaynak çalışmada `apps/backend/i18n` — kök DERİNLİKTEN BAĞIMSIZ
    bulunur (`kaynak_kokunu_bul`; elle `parents[N]` çıpası yasak: tests/test_kok_capasi_derinlikten_bagimsiz.py)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "i18n"
    from utils.path_utils import kaynak_kokunu_bul

    return Path(kaynak_kokunu_bul(Path(__file__))) / "apps" / "backend" / "i18n"


def _duzlestir(d: dict, onek: str = "") -> dict[str, str]:
    duz: dict[str, str] = {}
    for k, v in d.items():
        tam = f"{onek}.{k}" if onek else str(k)
        if isinstance(v, dict):
            duz.update(_duzlestir(v, tam))
        else:
            duz[tam] = v
    return duz


def kataloglar(yeniden: bool = False) -> dict[str, dict[str, str]]:
    """{dil: {düz anahtar: metin}} — ilk çağrıda okunur, önbelleklenir."""
    global _kataloglar
    with _kilit:
        if _kataloglar is None or yeniden:
            yuklu: dict[str, dict[str, str]] = {}
            for dil in DILLER:
                yol = katalog_dizini() / f"{dil}.json"
                try:
                    yuklu[dil] = _duzlestir(json.loads(yol.read_text(encoding="utf-8")))
                except Exception:
                    _log.exception("ceviri: katalog okunamadi (%s) — bu dilde anahtarlar Turkce yedege duser", yol)
                    yuklu[dil] = {}
            _kataloglar = yuklu
        return _kataloglar


def gecerli_dil(deger) -> str | None:
    d = str(deger or "").strip().lower()
    return d if d in DILLER else None


def dil_coz(baslik=None, parametre=None) -> str:
    """Başlık > ?dil= > tr. `Accept-Language` bu işleve hiç VERİLMEZ (bilinçli)."""
    return gecerli_dil(baslik) or gecerli_dil(parametre) or YEDEK_DIL


def istekten_dil(request) -> str:
    """İstek nesnesinden dil (ara katman dışındaki işleyiciler için: 500 / doğrulama zarfı)."""
    try:
        return dil_coz(request.headers.get(DIL_BASLIGI), request.query_params.get(DIL_PARAMETRESI))
    except Exception:
        return YEDEK_DIL


def _veri_koku() -> Path:
    from utils.path_utils import get_app_data_directory

    return Path(get_app_data_directory())


def cihaz_dili() -> str:
    """Cihaz düzeyindeki arayüz dili (istek dışı üretimler için). Dosya yok / bozuk / bayrak kapalı → tr."""
    if not I18N_EN_ACIK:
        return YEDEK_DIL
    try:
        veri = json.loads((_veri_koku() / CIHAZ_DILI_DOSYASI).read_text(encoding="utf-8"))
        return gecerli_dil(veri.get("dil")) or YEDEK_DIL
    except Exception:
        return YEDEK_DIL


def cihaz_dili_ayarli_mi() -> str | None:
    """Kayıtlı cihaz dili (yoksa None) — GET ucu "seçilmemiş" ile "tr seçilmiş"i ayırt etsin diye."""
    try:
        veri = json.loads((_veri_koku() / CIHAZ_DILI_DOSYASI).read_text(encoding="utf-8"))
        return gecerli_dil(veri.get("dil"))
    except Exception:
        return None


def cihaz_dili_yaz(dil: str) -> str:
    """Cihaz dilini atomik yazar (geçici dosya + os.replace). Geçersiz dil → ValueError."""
    d = gecerli_dil(dil)
    if not d:
        raise ValueError(dil)
    kok = _veri_koku()
    kok.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=str(kok), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"dil": d}, f)
        os.replace(gecici, kok / CIHAZ_DILI_DOSYASI)
    except Exception:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise
    return d


def etkin_dil() -> str:
    """İstek içinde isteğin dili; istek dışında cihaz dili; yoksa tr."""
    return istek_dili_var.get() or cihaz_dili()


def _kati() -> bool:
    return os.environ.get("PEMF_I18N_KATI") == "1" or "PYTEST_CURRENT_TEST" in os.environ


def _bul(duz: dict[str, str], anahtar: str, p: dict) -> str | None:
    if "count" in p:
        try:
            tekil = float(p["count"]) == 1
        except (TypeError, ValueError):
            tekil = False
        cogul = f"{anahtar}_{'one' if tekil else 'other'}"
        if cogul in duz:
            return duz[cogul]
    return duz.get(anahtar)


def t(anahtar: str, dil: str | None = None, **p) -> str:
    """Anahtar → metin (istek dilinde). `{{ad}}` yer tutucular `p`'den; `count` verilirse `_one` / `_other` seçilir."""
    d = gecerli_dil(dil) or etkin_dil()
    k = kataloglar()
    metin = _bul(k.get(d, {}), anahtar, p)
    if metin is None and d != YEDEK_DIL:
        metin = _bul(k.get(YEDEK_DIL, {}), anahtar, p)
    if metin is None:
        if _kati():
            raise KeyError(f"ceviri: katalogda olmayan anahtar '{anahtar}'")
        _log.error("ceviri: katalogda olmayan anahtar %r (dil=%s)", anahtar, d)
        return anahtar

    def doldur(m):
        ad = m.group(1)
        if ad in p and p[ad] is not None:
            return str(p[ad])
        if _kati():
            raise KeyError(f"ceviri: '{anahtar}' için '{ad}' yer tutucusu verilmedi")
        return ""

    return _YER_TUTUCU.sub(doldur, metin)


def sayi_metni(deger: float, basamak: int = 2, dil: str | None = None) -> str:
    """Y306 (sahip 19-11): kullanıcıya giden ONDALIK sayı dile göre — TR virgül ("14,40"), EN nokta ("14.40"); binlik ayırıcı YOK.
    Engel / neden metinlerinin sayıları bununla biçimlenir (metni üreten yerde, istek / cihaz dilinde)."""
    d = gecerli_dil(dil) or etkin_dil()
    metin = f"{float(deger):.{int(basamak)}f}"
    return metin.replace(".", ",") if d == "tr" else metin


def tarih_metni(an: datetime, dil: str | None = None, saat: bool = True) -> str:
    """Kullanıcıya tarih (24 saat): TR "13 Ekim 2026, 19:45" · EN "13 Oct 2026, 19:45"."""
    d = gecerli_dil(dil) or etkin_dil()
    ay = t(f"tarih.ay.{an.month}", dil=d)
    gun = f"{an.day} {ay} {an.year}"
    return t("tarih.tarihSaat", dil=d, tarih=gun, saat=an.strftime("%H:%M")) if saat else gun
