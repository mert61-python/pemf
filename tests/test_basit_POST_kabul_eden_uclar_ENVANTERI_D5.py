# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 · 1-C §9 #14 — CSRF benzeri "basit POST" ENVANTER KAPISI: basit (ön-uçuşsuz) POST'u KABUL eden her uç GEREKÇELİ listede.

NEDEN: tarayıcı çapraz kökenden ön-uçuşsuz yalnız `GET/HEAD/POST` + `text/plain` / `application/x-www-form-urlencoded` /
`multipart/form-data` gövde (ya da gövdesiz / içerik türsüz Blob) gönderebilir; sunucu isteği YÜRÜTÜR — CORS yalnız YANITI okumayı
engeller. A-01'de LAN (ve cihazın kendisi, loopback) jetonsuz yetkilidir → LAN'daki ya da cihazdaki bir tarayıcıda açılan HERHANGİ
bir sayfa bu uçları operatör eylemi olmadan tetikleyebilir. 1-C i3-F-6 Sıfırla'yı JSON şartına geçirdi (`Content-Type:
application/json` + `{"onay": true}`); öteki uçlar taranmamıştı. Bu kapı bugünkü kümeyi DONDURUR:

* listede olmayan YENİ basit-POST-kabul eden uç → KIRMIZI ("JSON zorunlu yap ya da gerekçeyle listeye ekle");
* listedeki uç artık reddediyorsa / kalktıysa → KIRMIZI ("listeden çıkar" — bayat liste kalmasın);
* sınıfı ya da kimlik muafiyeti değişen uç → KIRMIZI (gerekçe gözden geçirilsin).

ACİL DURDUR ve durdurma uçları listede "STOP yalnız güvenliği artırır" gerekçesiyle KALIR (Ö.4-Y8, A-25: hiçbir kapıya bağlanmaz) —
bu kapı ürünü DEĞİŞTİRMEZ; riskli uçların önerisi `[SAHİBE]` (rapor `_inceleme/RAPOR_D.md`).

SINIFLANDIRICI testin içinde (ürün sabiti OKUNMAZ) ve FastAPI'nin KENDİ gövde doğrulayıcısını (`request_body_to_args`) uç ÇAĞRILMADAN
koşar: (a) zorunlu JSON gövde → basit POST'u REDDEDER; (b) gövde yok / varsayılanlı → gövdesiz basit POST KABUL; (c) `Form` / `File`
→ form / multipart basit POST KABUL; (d) gövde parametresi yok ama uç `request.json()/body()/form()/stream()` okuyor → içerik türü
denetimi (AST: `if <headers.get("content-type")…>: raise`) yoksa KABUL. Belge dizesi / yorumdaki "content-type" SAYILMAZ (AST).
KARŞIT kol: sentetik bir uygulamada her sınıf doğru sınıflanır VE sınıf gerçek basit isteklerle ölçülen davranışla TUTARLIDIR.
Dinamik örneklem (süreç içi TestClient; LAN istemcisi, üretim profili `PEMF_REQUIRE_AUTH=1`, `Origin: http://kotu.example`): her
sınıftan ≥ 2 uç. Yıkıcı uçlar (silme, sıfırlama, güncelleme, yeniden başlatma) DİNAMİK KOŞULMAZ. Jeton yalnız bu teste özgü sahte dize.
"""

from __future__ import annotations

import ast
import asyncio
import functools
import inspect
import json
import textwrap
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import Request, UploadFile
from pydantic import BaseModel

_SAHTE_TOKEN = "kapi-sahte-basit-post-tokeni"
_KOTU = {"Origin": "http://kotu.example"}
_LAN = ("192.168.1.50", 50123)
_LOOPBACK = ("127.0.0.1", 50124)

# ───────────────────────────────────────────── SINIFLANDIRICI ─────────────────────────────────────────────

#: Basit POST'u KABUL eden sınıflar (öteki sınıflar reddeder).
_KABUL_SINIFLARI = frozenset(
    {
        "a_DUZ_METIN",  # zorunlu gövde ama tipi ham baytı kabul ediyor (str / bytes / Any)
        "a_GEVSEK_ICERIK_TURU",  # strict_content_type=False: içerik türsüz gövde JSON diye çözülür (Blob, ön-uçuşsuz)
        "b_GOVDESIZ",
        "b_GOVDESIZ_VARSAYILANLI",
        "c_FORM",
        "d_HAM",
        "x_BILINMEYEN_ROTA",  # APIRoute olmayan POST rotası: sınıflanamaz → kabul sayılır (fail-closed)
    }
)
#: SON (Y204 · S-D5.8): gövdesiz uç da `if <content-type okuması>: raise` kapısıyla basit POST'u reddeder (`b_GOVDESIZ_ICERIK_TURU_KAPILI`) —
#: eskiden kapı yalnız ham gövde OKUYAN uçta (d) sayılıyordu; gövdesiz + kapılı uç "kabul" görünürdü (sentetik `b_icerik_turu_kapili` ölçer).
_RED_SINIFLARI = frozenset(
    {"a_JSON_ZORUNLU", "b_GOVDESIZ_ICERIK_TURU_KAPILI", "d_HAM_ICERIK_TURU_KAPILI", "h_OZEL_BASLIK"}
)
#: CORS'ta "güvenli" (ön-uçuş istemeyen) istek başlıkları — bunların dışındaki ZORUNLU başlık ön-uçuş ister.
_GUVENLI_BASLIKLAR = frozenset({"accept", "accept-language", "content-language", "content-type"})
_HAM_OKUMALAR = frozenset({"json", "body", "form", "stream"})
_DUZ_METIN_GOVDE = b'{"x": 1}'


def _strict(route) -> bool:
    from fastapi.datastructures import DefaultPlaceholder

    v = getattr(route, "strict_content_type", True)
    if isinstance(v, DefaultPlaceholder):
        v = v.value
    return bool(v)


def _govde_gecer(route, govde) -> bool:
    """FastAPI'nin KENDİ doğrulayıcısı: `govde` (None = gövdesiz; bytes = text/plain / form / multipart ham gövde — JSON olmayan
    içerik türünde FastAPI gövdeyi ham bayt olarak verir) gövde doğrulamasını geçer mi? Uç ÇAĞRILMAZ."""
    from fastapi.dependencies.utils import request_body_to_args

    alanlar = route._flat_dependant.body_params
    # Ayrı döngü — `asyncio.run` geçerli döngüyü None'a çeker (aynı oturumdaki sonraki testler `get_event_loop` ile düşerdi).
    dongu = asyncio.new_event_loop()
    try:
        _deger, hatalar = dongu.run_until_complete(
            request_body_to_args(body_fields=alanlar, received_body=govde, embed_body_fields=route._embed_body_fields)
        )
    finally:
        dongu.close()
    return not hatalar


def _fonksiyon_dugumu(fn):
    try:
        kaynak = textwrap.dedent(inspect.getsource(inspect.unwrap(fn)))
    except (OSError, TypeError):
        return None
    for d in ast.parse(kaynak).body:
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return d
    return None


def _istek_adlari(fdef) -> set:
    adlar = set()
    for a in list(fdef.args.posonlyargs) + list(fdef.args.args) + list(fdef.args.kwonlyargs):
        etiket = ast.unparse(a.annotation) if a.annotation is not None else ""
        if etiket.split(".")[-1] == "Request" or a.arg in ("request", "req"):
            adlar.add(a.arg)
    return adlar


def _icerik_turu_okumasi(dugum) -> bool:
    for x in ast.walk(dugum):
        if (
            isinstance(x, ast.Call)
            and isinstance(x.func, ast.Attribute)
            and x.func.attr == "get"
            and isinstance(x.func.value, ast.Attribute)
            and x.func.value.attr == "headers"
            and x.args
            and isinstance(x.args[0], ast.Constant)
            and str(x.args[0].value).lower() == "content-type"
        ):
            return True
        if (
            isinstance(x, ast.Subscript)
            and isinstance(x.value, ast.Attribute)
            and x.value.attr == "headers"
            and isinstance(x.slice, ast.Constant)
            and str(x.slice.value).lower() == "content-type"
        ):
            return True
    return False


def _icerik_turu_kapisi(fdef) -> bool:
    """`if <content-type okuması …>: … raise …` — yalnız ÇALIŞAN kod (belge dizesi / yorum AST'de yok)."""
    for x in ast.walk(fdef):
        if isinstance(x, ast.If) and _icerik_turu_okumasi(x.test):
            if any(isinstance(y, ast.Raise) for govde in x.body for y in ast.walk(govde)):
                return True
    return False


def _ham_okuma(fdef) -> bool:
    adlar = _istek_adlari(fdef)
    for x in ast.walk(fdef):
        if (
            isinstance(x, ast.Call)
            and isinstance(x.func, ast.Attribute)
            and x.func.attr in _HAM_OKUMALAR
            and isinstance(x.func.value, ast.Name)
            and x.func.value.id in adlar
        ):
            return True
    return False


def _rota_sinifi(route) -> str:
    from fastapi import params

    flat = route._flat_dependant
    for h in flat.header_params:
        if h.field_info.is_required() and str(h.alias).lower() not in _GUVENLI_BASLIKLAR:
            return "h_OZEL_BASLIK"
    govde = flat.body_params
    if any(isinstance(f.field_info, (params.Form, params.File)) for f in govde):
        return "c_FORM"
    if govde:
        if _govde_gecer(route, None):
            return "b_GOVDESIZ_VARSAYILANLI"
        if _govde_gecer(route, _DUZ_METIN_GOVDE):
            return "a_DUZ_METIN"
        if not _strict(route):
            return "a_GEVSEK_ICERIK_TURU"
        return "a_JSON_ZORUNLU"
    fdef = _fonksiyon_dugumu(route.endpoint)
    if fdef is None:
        return "d_HAM"  # kaynak okunamadı → içerik türü denetimi KANITLANAMAZ → kabul (fail-closed)
    if _ham_okuma(fdef):
        return "d_HAM_ICERIK_TURU_KAPILI" if _icerik_turu_kapisi(fdef) else "d_HAM"
    return "b_GOVDESIZ_ICERIK_TURU_KAPILI" if _icerik_turu_kapisi(fdef) else "b_GOVDESIZ"


def siniflandir(app) -> dict:
    """{"POST /yol": sınıf} — uygulamanın HER POST rotası (APIRoute olmayan POST rotası `x_BILINMEYEN_ROTA`)."""
    from fastapi.routing import APIRoute

    sonuc = {}
    for r in app.routes:
        yontemler = set(getattr(r, "methods", None) or ())
        if "POST" not in yontemler:
            continue
        anahtar = f"POST {r.path}"
        sonuc[anahtar] = _rota_sinifi(r) if isinstance(r, APIRoute) else "x_BILINMEYEN_ROTA"
    return sonuc


@functools.lru_cache(maxsize=1)
def _urun_siniflari() -> dict:
    from servers import api_server as api

    return siniflandir(api.app)


def _urun_kabul_edenler() -> dict:
    return {k: v for k, v in _urun_siniflari().items() if v in _KABUL_SINIFLARI}


# ───────────────────────────────────────────── ENVANTER (gerekçeli izin listesi) ─────────────────────────────────────────────
# Alanlar: sinif · muaf (auth.is_exempt) · durum (STOP | EVET = durum değiştirir | HAYIR | ETKISIZ = handler basit POST'u
# etkisiz kılar) · risk (YOK | DUSUK | ORTA) · sahibe ([SAHİBE] önerisi raporda) · gerekce.
_STOP = "STOP yalnız güvenliği artırır"
_ANALIZ = (
    "Yalnız ANALİZ (geçici dosya; kalıcı kayıt yok; jeton Y194 KOD düzeyinde kapalı). Sahip kararı: AI uçları kimliksiz açık; "
    "yükleme protokolü multipart (eski APK 2.3.34 FormData + Accept + koşullu X-API-Key) → JSON zorunlu yapılamaz. Risk: CPU/GPU yükü."
)


def _e(sinif, muaf, durum, risk, gerekce, sahibe=False):
    return {"sinif": sinif, "muaf": muaf, "durum": durum, "risk": risk, "sahibe": sahibe, "gerekce": gerekce}


ENVANTER = {
    # ── durdurma uçları (Ö.4-Y8 · A-25): KALIR ──
    "POST /api/hardware/emergency_stop": _e(
        "b_GOVDESIZ",
        True,
        "STOP",
        "YOK",
        f"ACİL DURDUR — {_STOP} (Ö.4-Y8, A-25): hiçbir kapıya bağlanmaz; basit POST'la da 200 + porta STOP KALMALI "
        "(D3I A1 matrisi 60/60; /api/v1 takma adı dahil).",
    ),
    "POST /api/session/stop": _e(
        "b_GOVDESIZ",
        False,
        "STOP",
        "YOK",
        f"Seans durdurma — {_STOP} (Ö.4-Y8); kapılanmaz. Çapraz köken seansı kesebilir (güvenli yön: tedavi kesintisi).",
    ),
    "POST /api/ai/pro/stop": _e(
        "b_GOVDESIZ",
        True,
        "STOP",
        "YOK",
        f"AI Pro durdurma — {_STOP} (Ö.4-Y8); `_ai_kare_yabanci` belgesi: GÖVDESİZ ve HERKESE AÇIK kalır.",
    ),
    "POST /api/hardware/reset_pwm": _e(
        "b_GOVDESIZ",
        False,
        "STOP",
        "YOK",
        f"Bakım reset'i = stop_all_coils + ESP 'stop' — {_STOP} (Ö.4-Y8).",
    ),
    "POST /api/ai/pro/hazirlik/durdur": _e(
        "b_GOVDESIZ",
        True,
        "STOP",
        "YOK",
        f"Hazırlık önizlemesini (sunucu kamerası) bırakır, bobin sürmez — durdurma yönü, {_STOP}.",
    ),
    "POST /api/settings/kabin-kamerasi/canli/durdur": _e(
        "b_GOVDESIZ",
        False,
        "STOP",
        "YOK",
        f"Canlı kabin kamerası oturumunu kapatır (yalnız bırakır) — durdurma yönü, {_STOP}.",
    ),
    # ── kabul eder ama handler basit POST'u ETKİSİZ kılar ──
    "POST /api/ai/pro/start": _e(
        "b_GOVDESIZ_VARSAYILANLI",
        True,
        "ETKISIZ",
        "YOK",
        "Gövde varsayılanlı ama handler ONAYLI `proposal_id` ister (boş → 428); onay `/api/ai/pro/approve` JSON ZORUNLU → basit "
        "POST tedavi BAŞLATAMAZ.",
    ),
    "POST /api/patients/delete_all": _e(
        "b_GOVDESIZ_VARSAYILANLI",
        False,
        "ETKISIZ",
        "YOK",
        "Handler: yalnız cihazın kendisi (A-03) + kayıtlı operatörlü klinikte jeton + JSON `confirm: DELETE_ALL` — gövdesiz 400, "
        "düz metin 422 → basit POST silemez.",
    ),
    "POST /api/auth/desktop-session": _e(
        "d_HAM",
        False,
        "ETKISIZ",
        "YOK",
        "`_desktop_forbidden`: sıkı loopback + Origin yalnız loopback kökeni → çapraz köken 403 (dinamik kolda ölçülür).",
    ),
    "POST /api/operators/lock": _e(
        "b_GOVDESIZ",
        False,
        "ETKISIZ",
        "YOK",
        "Etki yalnız `X-PEMF-Operator` jetonuyla (özel başlık → ön-uçuş); başlıksız basit POST `iptal: false` döner.",
    ),
    # ── AI analiz (muaf, durum değiştirmez) ──
    **{
        f"POST /api/ai/{yol}": _e("c_FORM", True, "HAYIR", "DUSUK", _ANALIZ)
        for yol in (
            "vision/cat_organ",
            "vision/em_fantom",
            "vision/em_petri",
            "vision/histopath",
            "vision/kidney_ct",
            "vision/landmark",
            "vision/reticulocytes",
            "vision/scratch",
            "vision/segmentation",
            "vision/thermal",
            "rna/kidney",
            "sound/cat",
        )
    },
    # ── AI Pro (muaf — sahip kararı 2026-07-01) ──
    "POST /api/ai/ai_pro/frame": _e(
        "c_FORM",
        True,
        "EVET",
        "ORTA",
        "AKTİF onaylı AI Pro seansında kare bobin sürüşünü yönlendirir; modern sahip istemcide yabancı kare SÜRMEZ "
        "(`_ai_kare_yabanci`), sahipsiz (eski/kimliksiz) başlatımda sürer. Sahip kararı: AI Pro uçları kimliksiz; multipart protokol.",
        sahibe=True,
    ),
    "POST /api/ai/pro/propose": _e(
        "b_GOVDESIZ_VARSAYILANLI",
        True,
        "EVET",
        "DUSUK",
        "Öneri (mühür) oluşturur; tedavi başlatmaz — onay JSON zorunlu (approve). Taze lokalizasyon yoksa 409.",
    ),
    "POST /api/ai/pro/organ": _e(
        "b_GOVDESIZ_VARSAYILANLI",
        True,
        "EVET",
        "DUSUK",
        "Seanssızken küresel hedef organı değiştirir (gövdesiz → 0); seans sürerken mühür dışı hedef 409 (A-16). Öneri hekime "
        "gösterilip ayrıca onaylanır.",
    ),
    "POST /api/ai/pro/calibrate": _e(
        "b_GOVDESIZ_VARSAYILANLI",
        True,
        "EVET",
        "YOK",
        "Yalnız yeniden-lokalize bayrağı; sürüş / mühür / organ değişmez.",
    ),
    "POST /api/ai/pro/hazirlik/baslat": _e(
        "b_GOVDESIZ_VARSAYILANLI",
        True,
        "EVET",
        "DUSUK",
        "Sunucu kamerasını hazırlık önizlemesi için açar; bobin SÜRMEZ, seans başlatmaz.",
    ),
    # ── donanım (LAN jetonsuz, A-01) ──
    "POST /api/hardware/selftest": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "ESP 6-8'e SELFTEST yayını (ESP sahada devre dışı; 8266'da işleyici yok); STM'ye gitmez. Eski APK `{}` JSON gönderir.",
        sahibe=True,
    ),
    "POST /api/hardware/cleanup_esp": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "Yalnız canlı durumda bağlantısız ESP'nin `running` bayrağını düşürür (görünüm); istemci çağırmıyor.",
    ),
    # ── veri / sistem ──
    # SON (Y204 · S-D5.8): `/api/notifications/clear` ve `/api/patients/{patient_id}/delete` artık `application/json` değilse 415
    # (`b_GOVDESIZ_ICERIK_TURU_KAPILI`) → listeden ÇIKTI; davranış kapısı `test_bildirim_temizle_ve_hasta_sil_JSON_ZORUNLU_Y204.py`.
    "POST /api/client/error": _e(
        "d_HAM",
        False,
        "EVET",
        "DUSUK",
        "İstemci çökme günlüğüne satır ekler (alanlar kırpılı, ~4 MB rotasyon); sel meşru kaydı döndürebilir. Eski APK JSON gönderir.",
    ),
    "POST /api/system/recovery-ack": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "enforce_privileged: LAN jetonsuz 403; YALNIZ cihazın kendi tarayıcısından (loopback) basit POST kurtarma kodu uyarısını "
        "susturur. Eski APK `{}` JSON gönderir.",
        sahibe=True,
    ),
    "POST /api/support/bundle": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "enforce_privileged: LAN jetonsuz 403; paket YANITTA (çapraz kökenden okunamaz), diske yazılmaz; denetim izi satırı.",
    ),
    "POST /api/update/apply": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "enforce_privileged (loopback ya da jeton); eski EXE kanalı varsayılan KAPALI (PEMF_LEGACY_EXE_UPDATE) → 'kanal kapalı'; "
        "açıksa imzalı + SHA256'lı kurulum, tedavi sürerken red.",
    ),
    "POST /api/update/rollback": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "enforce_privileged; eski EXE kanalı varsayılan KAPALI (update/apply ile aynı kapılar).",
    ),
    "POST /api/settings/kabin-kamerasi/tara": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "Kameraları kısa açıp listeler (önizleme yanıtta; çapraz kökenden okunamaz).",
    ),
    "POST /api/settings/kabin-kamerasi/kare": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "Seçili kabin kamerasından tek kare (yanıtta; çapraz kökenden okunamaz).",
    ),
    "POST /api/settings/kabin-kamerasi/canli/baslat": _e(
        "b_GOVDESIZ",
        False,
        "EVET",
        "DUSUK",
        "Canlı kamera oturumu açar (kare istenmezse kendiliğinden kapanır); bobin yok.",
    ),
    "POST /api/auth/exchange": _e(
        "d_HAM",
        True,
        "EVET",
        "DUSUK",
        "Kod kimliğin kendisi (muaf); başarıda jeton YANITTA — çapraz kökenden okunamaz (CORS izni yok, dinamik kolda ölçülür); "
        "8 hatada 60 sn kilit (istemci adresi kovası).",
    ),
}

#: Durdurma uçları — listede "STOP yalnız güvenliği artırır" gerekçesiyle KALMALI (testte pinli; ENVANTER'den türetilmez).
_DURDURMA_UCLARI = (
    "POST /api/hardware/emergency_stop",
    "POST /api/session/stop",
    "POST /api/ai/pro/stop",
    "POST /api/hardware/reset_pwm",
    "POST /api/ai/pro/hazirlik/durdur",
    "POST /api/settings/kabin-kamerasi/canli/durdur",
)
_DUZELTME = (
    "JSON zorunlu yap (Sıfırla emsali `estop_mandalini_sifirla`: `Content-Type: application/json` denetimi → 415 + açık onay "
    "alanı) ya da GEREKÇEYLE ENVANTER'e ekle"
)


# ───────────────────────────────────────────── STATİK KAPI ─────────────────────────────────────────────


def test_KRITIK_basit_POST_kabul_eden_YENI_uc_YOK():
    yeni = {k: v for k, v in _urun_kabul_edenler().items() if k not in ENVANTER}
    assert not yeni, (
        f"basit (ön-uçuşsuz) POST'u KABUL eden {len(yeni)} uç gerekçeli listede DEĞİL — {_DUZELTME}: "
        + "; ".join(f"{k} [{v}]" for k, v in sorted(yeni.items()))
    )


def test_KRITIK_ENVANTER_BAYAT_DEGIL():
    kabul = _urun_kabul_edenler()
    siniflar = _urun_siniflari()
    bayat = {k: siniflar.get(k, "ROTA YOK") for k in ENVANTER if k not in kabul}
    assert not bayat, (
        "listedeki uç artık basit POST'u REDDEDİYOR ya da kalktı — listeden çıkar (bayat liste kalmasın): "
        + "; ".join(f"{k} [{v}]" for k, v in sorted(bayat.items()))
    )


def test_envanter_SINIF_ve_KIMLIK_MUAFIYETI_degismedi():
    from servers import auth

    siniflar = _urun_siniflari()
    fark = []
    for k, e in sorted(ENVANTER.items()):
        yol = k.split(" ", 1)[1]
        if k in siniflar and siniflar[k] != e["sinif"]:
            fark.append(f"{k}: sınıf {e['sinif']} → {siniflar[k]}")
        if bool(auth.is_exempt(yol)) != e["muaf"]:
            fark.append(f"{k}: kimlik muafiyeti {e['muaf']} → {bool(auth.is_exempt(yol))}")
    assert not fark, "envanterdeki uçların sınıfı / muafiyeti değişti — gerekçeyi gözden geçir: " + " · ".join(fark)


def test_envanter_GEREKCELI_ve_DURDURMA_uclari_STOP_gerekcesiyle_LISTEDE():
    sorun = []
    for k, e in sorted(ENVANTER.items()):
        if len(e["gerekce"].strip()) < 30:
            sorun.append(f"{k}: gerekçe boş/kısa")
        if e["sinif"] not in _KABUL_SINIFLARI:
            sorun.append(f"{k}: sınıf {e['sinif']} basit POST'u kabul eden bir sınıf değil")
        if e["durum"] not in ("STOP", "EVET", "HAYIR", "ETKISIZ") or e["risk"] not in ("YOK", "DUSUK", "ORTA"):
            sorun.append(f"{k}: durum/risk alanı geçersiz")
        if e["risk"] == "ORTA" and not e["sahibe"]:
            sorun.append(f"{k}: ORTA riskli uç [SAHİBE] önerisiz listeye giremez")
    for k in _DURDURMA_UCLARI:
        e = ENVANTER.get(k)
        if e is None:
            sorun.append(f"{k}: durdurma ucu listede YOK")
            continue
        if e["durum"] != "STOP" or _STOP not in e["gerekce"]:
            sorun.append(f"{k}: durdurma ucu '{_STOP}' gerekçesiyle kalmalı")
        if _urun_siniflari().get(k) not in _KABUL_SINIFLARI:
            sorun.append(
                f"{k}: durdurma ucu basit POST'u REDDEDİYOR ({_urun_siniflari().get(k)}) — Ö.4-Y8: STOP kapılanmaz"
            )
    assert not sorun, " · ".join(sorun)


# ───────────────────────────────────────────── KARŞIT KOL: sentetik uygulama (araç kanıtı) ─────────────────────────────────────


class _Model(BaseModel):
    """Sentetik uygulamanın gövde modeli — MODÜL düzeyinde: `from __future__ import annotations` altında FastAPI ek açıklamaları
    fonksiyonun `__globals__`'ından çözer; yerel sınıf çözülemez ve parametre sessizce SORGU parametresine düşer (ölçüldü)."""

    a: int


def _sentetik_uygulamalar():
    from fastapi import Body, FastAPI, File, Form, Header, HTTPException
    from fastapi.responses import PlainTextResponse

    app = FastAPI()

    @app.post("/a_model")
    def a_model(m: _Model):
        return {"ok": True}

    @app.post("/a_sozluk")
    def a_sozluk(d: dict):
        return {"ok": True}

    @app.post("/a_duz_metin")
    def a_duz_metin(s: str = Body(...)):
        return {"ok": True}

    @app.post("/b_bos")
    def b_bos():
        return {"ok": True}

    @app.post("/b_varsayilanli")
    def b_varsayilanli(m: Optional[_Model] = None):
        return {"ok": True}

    @app.post("/b_icerik_turu_kapili")
    def b_icerik_turu_kapili(request: Request):
        if "application/json" not in (request.headers.get("content-type") or "").lower():
            raise HTTPException(status_code=415)
        return {"ok": True}

    @app.post("/b_yorumda_kalan")
    def b_yorumda_kalan(request: Request):
        """Belge dizesi: if "application/json" not in request.headers.get("content-type"): raise HTTPException(415)."""
        # if "application/json" not in (request.headers.get("content-type") or "").lower(): raise HTTPException(415)
        return {"ok": True}

    @app.post("/c_form")
    def c_form(x: str = Form(...)):
        return {"ok": True}

    @app.post("/c_dosya")
    def c_dosya(f: UploadFile = File(...)):
        return {"ok": True}

    @app.post("/d_ham")
    async def d_ham(request: Request):
        try:
            await request.json()
        except ValueError:
            pass
        return {"ok": True}

    @app.post("/d_icerik_turu_kapili")
    async def d_icerik_turu_kapili(request: Request):
        if "application/json" not in (request.headers.get("content-type") or "").lower():
            raise HTTPException(status_code=415)
        await request.json()
        return {"ok": True}

    @app.post("/d_yorumda_kalan")
    async def d_yorumda_kalan(request: Request):
        """Belge dizesi: if "application/json" not in request.headers.get("content-type"): raise HTTPException(415)."""
        # if "application/json" not in (request.headers.get("content-type") or "").lower(): raise HTTPException(415)
        await request.body()
        return {"ok": True}

    @app.post("/d_okuyup_reddetmeyen")
    async def d_okuyup_reddetmeyen(request: Request):
        if request.headers.get("content-type"):
            pass
        await request.body()
        return {"ok": True}

    @app.post("/h_ozel_baslik")
    def h_ozel_baslik(x_ozel: str = Header(...)):
        return {"ok": True}

    async def x_ham_starlette(request):
        return PlainTextResponse("ok")

    app.add_route("/x_ham_starlette", x_ham_starlette, methods=["POST"])  # APIRoute DEĞİL → sınıflanamaz → kabul

    gevsek = FastAPI(strict_content_type=False)

    @gevsek.post("/a_gevsek")
    def a_gevsek(m: _Model):
        return {"ok": True}

    beklenen = {
        "POST /a_model": "a_JSON_ZORUNLU",
        "POST /a_sozluk": "a_JSON_ZORUNLU",
        "POST /a_duz_metin": "a_DUZ_METIN",
        "POST /b_bos": "b_GOVDESIZ",
        "POST /b_varsayilanli": "b_GOVDESIZ_VARSAYILANLI",
        "POST /b_icerik_turu_kapili": "b_GOVDESIZ_ICERIK_TURU_KAPILI",
        "POST /b_yorumda_kalan": "b_GOVDESIZ",
        "POST /c_form": "c_FORM",
        "POST /c_dosya": "c_FORM",
        "POST /d_ham": "d_HAM",
        "POST /d_icerik_turu_kapili": "d_HAM_ICERIK_TURU_KAPILI",
        "POST /d_yorumda_kalan": "d_HAM",
        "POST /d_okuyup_reddetmeyen": "d_HAM",
        "POST /h_ozel_baslik": "h_OZEL_BASLIK",
        "POST /x_ham_starlette": "x_BILINMEYEN_ROTA",
    }
    return app, gevsek, beklenen


def _basit_istekler(c, yol) -> list:
    """Tarayıcının çapraz kökenden ÖN-UÇUŞSUZ gönderebildiği istek biçimleri → HTTP kodları."""
    return [
        c.post(yol, headers=_KOTU).status_code,  # gövdesiz
        c.post(yol, headers={**_KOTU, "Content-Type": "text/plain"}, content=b"").status_code,
        c.post(yol, headers={**_KOTU, "Content-Type": "text/plain"}, content=b'{"a": 1}').status_code,
        c.post(yol, headers=_KOTU, content=b'{"a": 1}').status_code,  # içerik türsüz Blob
        c.post(yol, headers=_KOTU, data={"x": "1", "a": "1"}).status_code,  # x-www-form-urlencoded
        c.post(
            yol, headers=_KOTU, data={"x": "1"}, files={"f": ("f.bin", b"veri", "application/octet-stream")}
        ).status_code,
    ]


def test_KRITIK_siniflandirici_SENTETIK_uygulamada_her_sinifi_DOGRU_ve_DAVRANISLA_TUTARLI():
    from fastapi.testclient import TestClient

    app, gevsek, beklenen = _sentetik_uygulamalar()
    olculen = siniflandir(app)
    yanlis = {k: (olculen.get(k), v) for k, v in beklenen.items() if olculen.get(k) != v}
    assert not yanlis, f"sınıflandırıcı sentetik uçları YANLIŞ sınıfladı (ölçülen, beklenen): {yanlis}"
    assert siniflandir(gevsek) == {"POST /a_gevsek": "a_GEVSEK_ICERIK_TURU"}, siniflandir(gevsek)
    kapsanan = set(olculen.values()) | {"a_GEVSEK_ICERIK_TURU"}
    assert kapsanan == _KABUL_SINIFLARI | _RED_SINIFLARI, (
        f"sentetik uygulama sınıflandırıcının HER kolunu sınamıyor: eksik {(_KABUL_SINIFLARI | _RED_SINIFLARI) - kapsanan}"
    )
    tutarsiz = []
    for uyg, siniflar in ((app, olculen), (gevsek, siniflandir(gevsek))):
        c = TestClient(uyg, client=_LAN)
        for k, sinif in siniflar.items():
            kodlar = _basit_istekler(c, k.split(" ", 1)[1])
            kabul = any(kod < 400 for kod in kodlar)
            if kabul != (sinif in _KABUL_SINIFLARI):
                tutarsiz.append(f"{k} [{sinif}] basit istek kodları {kodlar}")
    assert not tutarsiz, "sınıf ile GERÇEK basit-istek davranışı tutarsız (araç kanıtı): " + " · ".join(tutarsiz)


# ───────────────────────────────────────────── DİNAMİK ÖRNEKLEM (ürün; süreç içi) ─────────────────────────────────────────────


@pytest.fixture
def ortam(monkeypatch):
    from kayitci_donanim import gercek_hc
    from servers import api_server as api
    from servers import auth

    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "1")
    monkeypatch.setenv("PEMF_API_TOKEN", _SAHTE_TOKEN)
    for ad in ("_require", "_token", "_LOOPBACK_BIND", "_TRUSTED_PROXIES"):
        monkeypatch.setattr(auth, ad, None)
    monkeypatch.setattr(auth, "_warned", True)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0)
    monkeypatch.setattr(api, "_estop_cloud_mirror", lambda *a, **k: None)
    monkeypatch.setattr(api, "_estop_ack_watch", lambda *a, **k: None)
    monkeypatch.setattr(api, "_mqtt_publish", lambda topic, payload: False)
    monkeypatch.setitem(api._active_session, "is_active", False)
    with gercek_hc() as hc:
        monkeypatch.setattr(api.state, "hardware", hc)
        try:
            yield SimpleNamespace(api=api, hc=hc)
        finally:
            from utils import estop_mandali as m

            m.sifirla("test")


def _istemci(o, adres=_LAN):
    from fastapi.testclient import TestClient

    return TestClient(o.api.app, client=adres)


def _duz_metin(c, yol, govde=b""):
    return c.post(yol, headers={**_KOTU, "Content-Type": "text/plain"}, content=govde)


def _fastapi_dogrulama_reddi(r) -> bool:
    """FastAPI GÖVDE doğrulama reddi (uygulamanın 422 işleyicisi `errors` listesi taşır) — handler'ın kendi 4xx'i DEĞİL."""
    try:
        return r.status_code == 422 and "errors" in r.json()
    except ValueError:
        return False


def _statik_tutarli(anahtar: str, beklenen: str) -> None:
    """Dinamik ölçüm GEÇTİKTEN SONRA: statik sınıf aynı uç için aynı şeyi söylüyor mu (ölçüm önce — ürün mutantında dinamik kol
    kendi davranış iletisiyle düşsün, statik ön koşulla değil)."""
    olculen = _urun_siniflari().get(anahtar)
    assert olculen == beklenen, (
        f"statik sınıf dinamik ölçümle TUTARSIZ: {anahtar} statik {olculen}, ölçülen davranış {beklenen}"
    )


@pytest.mark.parametrize(
    "yol,gecerli_json_karsit",
    [
        ("/api/settings/arayuz-dili", {"dil": "xx-gecersiz"}),
        ("/api/coil/surus_kipi", {"unipolar": []}),
    ],
)
def test_KRITIK_dinamik_a_JSON_zorunlu_uclar_basit_POSTu_REDDEDER(ortam, yol, gecerli_json_karsit):
    from utils import ceviri

    dil_once = ceviri.cihaz_dili_ayarli_mi()
    c = _istemci(ortam)
    yanitlar = {
        "text/plain gövdesiz": _duz_metin(c, yol),
        "text/plain {}": _duz_metin(c, yol, b"{}"),
        "text/plain JSON": _duz_metin(c, yol, json.dumps(gecerli_json_karsit).encode()),
        "içerik türsüz Blob JSON": c.post(yol, headers=_KOTU, content=json.dumps(gecerli_json_karsit).encode()),
        "form": c.post(yol, headers=_KOTU, data={"dil": "tr"}),
    }
    kabul = {ad: r.status_code for ad, r in yanitlar.items() if not _fastapi_dogrulama_reddi(r)}
    assert not kabul, f"{yol}: (a) sınıfı uç basit POST'u FastAPI doğrulamasında REDDETMEDİ: {kabul}"
    # KARŞIT: aynı uç gerçek JSON'la handler'a ULAŞIR (422 içerik türünden; handler'ın kendi 400'ü, durum değişmez)
    karsit = c.post(yol, json=gecerli_json_karsit, headers=_KOTU)
    assert karsit.status_code == 400 and not _fastapi_dogrulama_reddi(karsit), (
        f"aparat: {yol} JSON'la handler'a ulaşmadı ({karsit.status_code} {karsit.text[:120]})"
    )
    assert ceviri.cihaz_dili_ayarli_mi() == dil_once, "aparat: örneklem durum DEĞİŞTİRDİ"
    _statik_tutarli(f"POST {yol}", "a_JSON_ZORUNLU")


@pytest.mark.parametrize("yol", ["/api/hardware/emergency_stop", "/api/v1/hardware/emergency_stop"])
@pytest.mark.parametrize("govde", [b"", b"{}"])
def test_KRITIK_dinamik_b_ACIL_DURDUR_basit_POSTla_da_200_ve_porta_STOP(ortam, yol, govde):
    """Ö.4-Y8: ACİL DURDUR her hücrede 200 — çapraz kökenli düz metin basit POST dahil (KALMALI). Yanıt okunamaz (CORS izni yok)."""
    hc = ortam.hc
    once_cagri, once_paket = hc.stop_all_cagri, len(hc.core._hw_send_queue.paketler)
    r = _duz_metin(_istemci(ortam), yol, govde)
    assert r.status_code == 200, (
        f"ACİL DURDUR basit POST'ta {r.status_code} (Ö.4-Y8: hiçbir şeye kapılanmaz): {r.text[:200]}"
    )
    assert hc.stop_all_cagri > once_cagri and len(hc.core._hw_send_queue.paketler) > once_paket, (
        "ACİL DURDUR 200 döndü ama donanıma STOP GİTMEDİ"
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}, (
        "çapraz köken (kotu.example) yanıtı OKUYABİLİYOR — CORS izni verilmemeliydi"
    )
    _statik_tutarli("POST /api/hardware/emergency_stop", "b_GOVDESIZ")


def test_KRITIK_dinamik_b_GOVDESIZ_ICERIK_TURU_KAPILI_uc_basit_POSTu_REDDEDER_bildirimler_DURUR(ortam):
    """SON (Y204 · S-D5.8): eskiden bu kol "basit POST bildirimleri SİLER" ölçüyordu (envanter EVET / ORTA, [SAHİBE] S-D5.8); sahip
    kararıyla uç `application/json` değilse 415 → aynı istek artık REDDEDİLİR ve bildirim DURUR (statik sınıf da red sınıfında)."""
    api = ortam.api
    with api._live_state_lock:
        eski = list(api._live_state["notifications"])
        api._live_state["notifications"].append({"message": "kapi-sahte-guvenlik-bildirimi", "type": "error"})
    try:
        r = _duz_metin(_istemci(ortam), "/api/notifications/clear", b"{}")
        with api._live_state_lock:
            kalan = list(api._live_state["notifications"])
    finally:
        with api._live_state_lock:
            api._live_state["notifications"][:] = eski
    # 22-SON kapanış: süitte önceki dosyaların bildirimleri listede durabilir → ölçüt "eski + sahte AYNEN kaldı" (sayı 1 değil).
    assert (
        r.status_code == 415
        and kalan[: len(eski)] == eski
        and [b.get("message") for b in kalan[len(eski) :]] == ["kapi-sahte-guvenlik-bildirimi"]
    ), f"çapraz kökenli basit POST güvenlik bildirimlerini SİLMEMELİ (Y204) — {r.status_code}, kalan {kalan}"
    _statik_tutarli("POST /api/notifications/clear", "b_GOVDESIZ_ICERIK_TURU_KAPILI")


@pytest.mark.parametrize("yol", ["/api/ai/vision/thermal", "/api/ai/sound/cat"])
def test_dinamik_c_FORM_uclari_basit_form_ve_multipart_POSTu_HANDLERA_ulastirir(ortam, yol):
    """Handler'ın İLK satırı (geçersiz `xai_method` → kendi 422'si) — model yüklenmez, durum değişmez."""
    c = _istemci(ortam)
    yanitlar = {
        "urlencoded": c.post(yol, headers=_KOTU, data={"xai_method": "kapi-gecersiz-yontem"}),
        "multipart": c.post(
            yol,
            headers=_KOTU,
            data={"xai_method": "kapi-gecersiz-yontem"},
            files={"file": ("x.bin", b"\x00\x01", "application/octet-stream")},
        ),
    }
    for ad, r in yanitlar.items():
        assert r.status_code == 422 and not _fastapi_dogrulama_reddi(r) and "kapi-gecersiz-yontem" in r.text, (
            f"{yol} {ad}: basit form POST handler'a ulaşmadı ({r.status_code} {r.text[:160]})"
        )
    _statik_tutarli(f"POST {yol}", "c_FORM")


def test_dinamik_d_HAM_uclar_icerik_turune_BAKMADAN_yurutur(ortam, monkeypatch):
    from servers import auth_router
    from utils import secrets_manager

    c = _istemci(ortam)
    r = _duz_metin(c, "/api/client/error", json.dumps({"message": "kapi-kotu-sayfa-izi"}).encode())
    yol = ortam.api._app_data_dir() / "client_errors.jsonl"
    icerik = yol.read_text(encoding="utf-8") if yol.exists() else ""
    assert r.status_code == 200 and "kapi-kotu-sayfa-izi" in icerik, (
        f"ölçüm: /api/client/error düz metin JSON'u işlemeliydi — {r.status_code}, günlükte {'VAR' if icerik else 'YOK'}"
    )
    monkeypatch.setattr(auth_router, "_exchange_throttle", {})
    monkeypatch.setattr(secrets_manager, "get_secret", lambda ad, *a, **k: "KOD123" if ad == "pairing_code" else None)
    r = _duz_metin(c, "/api/auth/exchange", b'{"code": "KOD123"}')
    assert r.status_code == 200 and r.json().get("token") == _SAHTE_TOKEN, (
        f"ölçüm: exchange {r.status_code} {r.text[:120]}"
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}, (
        "çapraz köken (kotu.example) eşleştirme JETONUNU okuyabiliyor — CORS izni verilmemeliydi"
    )
    _statik_tutarli("POST /api/client/error", "d_HAM")
    _statik_tutarli("POST /api/auth/exchange", "d_HAM")


def test_KRITIK_dinamik_d_icerik_turu_ve_KOKEN_kapili_uclar_basit_POSTu_REDDEDER(ortam):
    from servers import auth_router
    from utils import estop_mandali as m

    m.mandalla("manual")
    r = _duz_metin(_istemci(ortam), "/api/hardware/estop_mandali/sifirla", b'{"onay": true}')
    kalkti = not m.mandalli_mi()
    assert r.status_code == 415 and not kalkti, (
        f"Sıfırla çapraz kökenli düz metin basit POST'u REDDETMEDİ ({r.status_code}, mandal kalktı={kalkti}) — i3-F-6"
    )
    once = dict(auth_router._desktop_session)
    r = _duz_metin(_istemci(ortam, _LOOPBACK), "/api/auth/desktop-session", b'{"access_token": "kapi-sahte-oturum"}')
    assert r.status_code == 403 and dict(auth_router._desktop_session) == once, (
        f"desktop-session çapraz kökenli basit POST'u REDDETMEDİ ({r.status_code}) — envanter gerekçesi (Origin) geçersiz"
    )
    _statik_tutarli("POST /api/hardware/estop_mandali/sifirla", "d_HAM_ICERIK_TURU_KAPILI")
    assert ENVANTER["POST /api/auth/desktop-session"]["durum"] == "ETKISIZ"
