# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN KALİBRASYONU UÇLARI — sabit düzlem kalibrasyonu ekranının arka ucu (KD · sahip kararları Y258–Y260, 2026-11-10; KD-2 çok konum).

Akış (araştırma profili; masaüstü + telefon + web aynı uçları kullanır):
  1. `POST /api/ai/pro/kalibrasyon/kare` — seçili kabin kamerasından `KARE_ADEDI` tam çözünürlüklü kare (aynı açılış); kuyular OTOMATİK
     bulunur, kareler ortalanır, plakanın 4 dış köşesi NUMARALI çizilip döner (dokunma yok). Kare + bulunan ızgara SUNUCUDA saklanır
     (kimlikle) — hesap kameradan GELEN kareyle yapılır, yüklenen keyfi görüntüyle değil.
  2. `POST …/hesapla` — ≥ 2 konum (her biri: kare kimliği + numaralı köşelerden ≥ 2'sinin sol / ön cm'si) + lens → ortak çözüm, KAYDETMEZ.
  3. `POST …/kaydet` — aynı girdi YENİDEN hesaplanır (istemcinin sonucuna güvenilmez); geçersizse 422, lens uyarısı AÇIK onay yoksa
     409; veri köküne yazılır (+ referans kare) ve DENETİM İZİNE.
  4. `POST …/dogrula` — plaka başka yerde, ≥ 1 köşe → plaka MERKEZİ farkı ≤ 1 cm geçer (köşe farkları bilgi); denetim izine.
  5. `POST …/fantom` — fantom kalınlığı / tümör derinliği / boyu (sahip ölçer) — fantom hedef düzlemi buradan.
  6. `POST …/taban` — numune tabanı yükseltmesi: "lens → numune tabanı uzaklığı" (yükseltme = ölçülen lens yüksekliği − uzaklık).
  7. `POST …/sahne-yenile` — kamera oynamışsa "kalibre etmeden devam" (yalnız kayma ~≤ 2 cm; o anki kare yeni sahne referansı).
  8. `GET  /api/ai/pro/kalibrasyon` — durum.
Yetki: `/api/ai/pro/*` ile AYNI (sahibin AI Pro muafiyeti, `auth._EXEMPT_PREFIXES`) + araştırma eklentisi (`require_research`).
⚠️ AI Pro seansı sürerken kalibrasyon / fantom / taban / sahne DEĞİŞMEZ (hedefler kayar) → 409. ACİL DURDUR bu uçlara bağlı DEĞİL (Ö.4-Y8).
⚠️ Kalibrasyon kendi başına bobin SÜRMEZ; sürüş yine bayrak + onay + kare başına PEMF kapısı ister.
"""

from __future__ import annotations

import base64
import logging
import math
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from utils import ceviri

from servers.entitlement import require_research

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_research)])

#: Saklanan kalibrasyon karesinin ömrü ve en çok sayısı (konum başına: ızgara + küçük referans; ~2 MB).
KARE_OMRU_SN = 1800.0
AZAMI_KARE = 10
#: KD-2 (kayıtlı karelerle ölçüldü): konum başına 3 kare ortalaması kuyu izdüşümünü 2,3–2,6 → 1,7–2,2 px düşürür.
KARE_ADEDI = 3
#: Ekrana dönen işaretli karenin genişliği (bant genişliği; köşe pikselleri bu ölçekte döner).
GOSTERIM_GENISLIK = 1280
#: Fantom ayarı sınırları (cm) — kabin iç yüksekliği 35 cm, kamera kapakta.
FANTOM_AZAMI_KALINLIK_CM = 20.0
_kareler: dict[str, dict] = {}
_kilit = threading.Lock()


class LensGirdisi(BaseModel):
    solCm: float  # noqa: N815 — tel sözleşmesi (arayüz camelCase)
    onCm: float  # noqa: N815
    tabanCm: float  # noqa: N815


class OlcumGirdisi(BaseModel):
    solCm: float  # noqa: N815
    onCm: float  # noqa: N815


class KonumGirdisi(BaseModel):
    kareKimligi: str = Field(max_length=64)  # noqa: N815
    olcumler: list[OlcumGirdisi | None] = Field(min_length=4, max_length=4)


class HesaplaGirdisi(BaseModel):
    konumlar: list[KonumGirdisi] = Field(min_length=1, max_length=6)
    lens: LensGirdisi | None = None
    plakaYuksekligiCm: float = 2.0  # noqa: N815
    lensUyarisiniOnayla: bool = False  # noqa: N815


class DogrulaGirdisi(BaseModel):
    kareKimligi: str = Field(max_length=64)  # noqa: N815
    olcumler: list[OlcumGirdisi | None] = Field(min_length=4, max_length=4)


class FantomGirdisi(BaseModel):
    kalinlikCm: float  # noqa: N815
    tumorDerinligiCm: float = 0.0  # noqa: N815
    boyCm: float | None = None  # noqa: N815
    enCm: float | None = None  # noqa: N815


class TabanGirdisi(BaseModel):
    lensUzaklikCm: float  # noqa: N815


class BosGovde(BaseModel):
    """Gövdesi olmayan durum değiştiren / kamera açan uçlar JSON ister (D5 · Y204): ham (ön-uçuşsuz) POST 422 — arayüz `{}` gönderir."""


def _sd():
    from ai_hub.cv_ortak import sabit_duzlem

    return sabit_duzlem


def _veri_koku():
    from servers import ai_pro_hedef

    return ai_pro_hedef.duzlem_veri_koku()


def _seans_suruyor() -> bool:
    try:
        from servers import ai_router as air

        return bool(getattr(air, "_ai_loop_active", False))
    except Exception:
        return False


def _seans_kapisi() -> None:
    if _seans_suruyor():
        raise HTTPException(status_code=409, detail=ceviri.t("ai.kalibrasyon.seansSuruyor"))


def _denetim_izi(olay: str, yuk: dict) -> bool:
    """Append-only `session_events` (AI Pro onay izi ile aynı yol). Best-effort: yazılamazsa kayıt DURMAZ, günlüğe düşer."""
    try:
        from servers.api_server import _get_treatment_db

        _get_treatment_db().record_session_event(None, olay, payload=yuk, severity="info")
        return True
    except Exception:
        logger.warning("Kabin kalibrasyonu denetim izi yazılamadı (%s)", olay, exc_info=True)
        return False


def neden_metni(kod: str, **ek) -> str:
    """Hesap reddi nedeni → istek dilinde EYLEM metni (değişmez anahtarlar — K-3)."""
    if kod == "girdi_gecersiz":
        return ceviri.t("ai.kalibrasyon.neden.girdiGecersiz")
    if kod == "konum_az":
        return ceviri.t("ai.kalibrasyon.neden.konumAz")
    if kod == "olcum_eksik":
        return ceviri.t("ai.kalibrasyon.neden.olcumEksik")
    if kod == "olcum_tutarsiz":
        return ceviri.t("ai.kalibrasyon.neden.olcumTutarsiz")
    if kod == "cozum_yok":
        return ceviri.t("ai.kalibrasyon.neden.cozumYok")
    if kod == "kamera_duzlem_altinda":
        return ceviri.t("ai.kalibrasyon.neden.kameraDuzlemAltinda")
    if kod == "izdusum_yuksek":
        return ceviri.t("ai.kalibrasyon.neden.izdusumYuksek", px=str(ek.get("px", "?")))
    if kod == "konum_yayilimi_az":
        return ceviri.t("ai.kalibrasyon.neden.konumYayilimiAz", cm=str(ek.get("cm", "?")))
    return kod


def _ic_parametre(genislik: int, yukseklik: int):
    """Ürünün kalibrasyon iç parametresi (petri v2 YAML'ının `intrinsics_npz`'si — üç hat aynı dosya) kare boyutuna ölçekli. Kenar oranı
    farklı / dosya yok → 422 (eylem söyler)."""
    from ai_hub.cv_ortak.coord_transform import CameraIntrinsics, olcekli_intrinsics
    from ai_hub.inference_petri_dish.petri_cv_v2 import load_cabin_config

    cfg = load_cabin_config(None)
    try:
        yol = cfg.intrinsics_path()
        intr = olcekli_intrinsics(CameraIntrinsics.from_npz(str(yol)), genislik, yukseklik)
    except Exception:
        logger.warning("kalibrasyon: iç parametre okunamadı", exc_info=True)
        intr, yol = None, None
    if intr is None:
        raise HTTPException(
            status_code=422,
            detail=ceviri.t("ai.kalibrasyon.icParametreYok", genislik=str(genislik), yukseklik=str(yukseklik)),
        )
    return intr, yol


def _kabin_ext():
    from ai_hub.inference_petri_dish.petri_cv_v2 import load_cabin_config

    return load_cabin_config(None).geometry.cabin_extent_cm


def _kare(kimlik: str) -> dict:
    simdi = time.monotonic()
    with _kilit:
        for k in [k for k, v in _kareler.items() if simdi - v["zaman"] > KARE_OMRU_SN]:
            _kareler.pop(k, None)
        k = _kareler.get(str(kimlik))
    if k is None:
        raise HTTPException(status_code=404, detail=ceviri.t("ai.kalibrasyon.kareYok"))
    return k


def _kalibrasyon_yok_metni(hata) -> str:
    return ceviri.t("ai.pemf.kapi.kalibrasyonBozuk") if hata else ceviri.t("ai.pemf.kapi.kalibrasyonYok")


def _sonlu(*d) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in d)
    except (TypeError, ValueError):
        return False


def _cm_olcu(ext, p_mm) -> list[float]:
    """Kabin mm (X, Y, Z) → sahibin ölçü dili (sol cama, ön cama, taban camına; cm)."""
    return [
        round(float(ext[0]) / 2.0 - float(p_mm[0]) / 10.0, 2),
        round(float(p_mm[2]) / 10.0 + float(ext[2]) / 2.0, 2),
        round(float(p_mm[1]) / 10.0 + float(ext[1]) / 2.0, 2),
    ]


def _plaka_bul(und, sd):
    """DÜZELTİLMİŞ karede 24'lük plaka ızgarası → `sd.konum_hazirla` sözlüğü ya da None (+ ham neden, yalnız günlük)."""
    from ai_hub.inference_petri_dish.petri_cv_v2 import plate_grid

    try:
        g = plate_grid.detect_plate_wells(und, 24, yolo=None)
    except Exception as e:  # ızgara kendi hatasını `error`a yazar; beklenmeyen istisna günlüğe (KP-4 B3 testi)
        logger.warning("kalibrasyon: plaka ızgarası istisnası", exc_info=True)
        return None, type(e).__name__
    if not g.success or not g.wells_plate_mm:
        return None, str(g.error or "bulunamadi")
    H = g.H_ransac if getattr(g, "H_ransac", None) is not None else g.H_img_from_plate
    if H is None:
        return None, "homografi_yok"
    return sd.konum_hazirla(H, g.wells_plate_mm, sd.PLAKA_DIS_MM[24]), None


def _isaretle(und, konum, genislik: int):
    """Ekran karesi: plaka çerçevesi + köşe NUMARALARI (1 ön-sol, 2 ön-sağ, 3 arka-sağ, 4 arka-sol — dil bağımsız), küçültülmüş JPEG.
    @return (base64, köşe pikselleri bu karede)."""
    import cv2
    import numpy as np

    olcek = min(1.0, float(genislik) / float(und.shape[1]))
    img = cv2.resize(
        und, (int(round(und.shape[1] * olcek)), int(round(und.shape[0] * olcek))), interpolation=cv2.INTER_AREA
    )
    kose = None
    if konum is not None:
        kose = np.asarray(konum["kose_px"], dtype=np.float64) * olcek
        cv2.polylines(img, [np.round(kose).astype(np.int32)], True, (60, 220, 60), 2, cv2.LINE_AA)
        for i, p in enumerate(kose):
            c = (int(round(p[0])), int(round(p[1])))
            cv2.circle(img, c, 16, (20, 20, 20), -1, cv2.LINE_AA)
            cv2.circle(img, c, 16, (60, 220, 60), 2, cv2.LINE_AA)
            cv2.putText(
                img, str(i + 1), (c[0] - 7, c[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA
            )
    ok, tampon = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=503, detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks="?"))
    return base64.b64encode(tampon).decode("ascii"), (
        None if kose is None else [[round(float(a), 1) for a in p] for p in kose]
    )


def _kamera_karesi(adet: int):
    """Seçili kabin kamerasından `adet` kare (BGR listesi) + kare sözlüğü. AI Pro kamerayı tutuyorsa / seçim yoksa 409, alınamazsa 503."""
    import cv2
    import numpy as np
    from utils import kabin_kamerasi as kk

    from servers.settings_router import _ai_kamerasi_mesgul

    if _ai_kamerasi_mesgul():
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.kareMesgul"))
    try:
        kare = kk.kare_al(adet=adet)
    except kk.KameraSecilmedi as e:
        raise HTTPException(status_code=409, detail=kk.secim_hatasi_metni(e)) from None
    if kare is None:
        secim = kk.secili_kamera() or {}
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks=str(secim.get("indeks", "?"))),
        )
    bgrler = []
    for b64 in [kare["image_base64"], *(kare.get("ek_kareler") or [])]:
        bgr = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
        if bgr is not None and bgr.shape[:2] == (int(kare["yukseklik"]), int(kare["genislik"])):
            bgrler.append(bgr)
    if not bgrler:
        raise HTTPException(
            status_code=503, detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks=str(kare.get("indeks")))
        )
    return bgrler, kare


def _kare_isle(bgrler, intr, sd):
    """Kareleri düzelt, her birinde ızgarayı bul, AYNI kuyu sayısıyla bulunanların kuyu / köşe piksellerini ORTALA.
    @return (ilk düzeltilmiş kare, ortalanmış konum | None, ham neden | None, kullanılan kare sayısı)."""
    import numpy as np

    from ai_hub.cv_ortak.coord_transform import undistort_image

    unds = [undistort_image(b, intr) for b in bgrler]
    bulunan, neden = [], None
    for u in unds:
        k, n = _plaka_bul(u, sd)
        if k is not None:
            bulunan.append(k)
        else:
            neden = neden or n
    if not bulunan:
        return unds[0], None, neden, 0
    n0 = len(bulunan[0]["kuyu_px"])
    ayni = [
        k for k in bulunan if len(k["kuyu_px"]) == n0 and np.allclose(k["kuyu_plaka_mm"], bulunan[0]["kuyu_plaka_mm"])
    ]
    konum = dict(ayni[0])
    konum["kuyu_px"] = np.mean([k["kuyu_px"] for k in ayni], axis=0)
    konum["kose_px"] = np.mean([k["kose_px"] for k in ayni], axis=0)
    return unds[0], konum, None, len(ayni)


def _kucuk_referans(und, konum, sd):
    """Sahne referansı için küçük kare + maske (plaka DIŞLANIR) — bellekte konum başına ~1,5 MB."""
    import cv2
    import numpy as np

    h, w = und.shape[:2]
    cokgen = [] if konum is None else [np.asarray(konum["kose_px"], np.float64)]
    maske = sd.cokgen_maskesi((w, h), cokgen, genislet_px=40)
    o = sd.SAHNE_GENISLIK / float(w)
    boy = (sd.SAHNE_GENISLIK, max(1, int(round(h * o))))
    return cv2.resize(und, boy, interpolation=cv2.INTER_AREA), cv2.resize(maske, boy, interpolation=cv2.INTER_NEAREST)


def _hesapla(g: HesaplaGirdisi) -> dict:
    """Ortak hesap (hesapla + kaydet): çok konumlu çözüm + görüş alanı + sahne özniteliği. KAYDETMEZ."""
    import numpy as np

    sd = _sd()
    kareler = [_kare(k.kareKimligi) for k in g.konumlar]
    ilk = kareler[0]
    for k in kareler:
        if (k["genislik"], k["yukseklik"]) != (ilk["genislik"], ilk["yukseklik"]) or sd.kimlik_ayni(
            k.get("kimlik"), ilk.get("kimlik")
        ) is False:
            raise HTTPException(status_code=409, detail=ceviri.t("ai.pemf.kapi.kameraFarkli"))
        if k.get("konum") is None:
            raise HTTPException(status_code=422, detail=ceviri.t("ai.kalibrasyon.plakaBulunamadi"))
    intr, yol = _ic_parametre(ilk["genislik"], ilk["yukseklik"])
    ext = _kabin_ext()
    lens = (g.lens.solCm, g.lens.onCm, g.lens.tabanCm) if g.lens is not None else None
    konumlar = [
        dict(k["konum"], olcum_cm=[None if o is None else (o.solCm, o.onCm) for o in kg.olcumler])
        for k, kg in zip(kareler, g.konumlar)
    ]
    r = sd.kalibrasyon_coz(
        konumlar=konumlar,
        K=intr.K,
        D=intr.D,
        boyut=(ilk["genislik"], ilk["yukseklik"]),
        ext_cm=ext,
        plaka_yuksekligi_mm=float(g.plakaYuksekligiCm) * 10.0 if _sonlu(g.plakaYuksekligiCm) else float("nan"),
        lens_cm=lens,
    )
    r["ext_cm"] = list(ext)
    r["_intr"], r["_npz"], r["_kareler"], r["_konumlar"] = intr, yol, kareler, konumlar
    if not r.get("R"):
        return r
    hm = sd.DuzlemHaritasi.durustan(
        intr.K,
        intr.D,
        (ilk["genislik"], ilk["yukseklik"]),
        np.asarray(r["R"]),
        np.asarray(r["t_mm"]),
        ext,
        r["duzlem_y_mm"],
    )
    r["gorus_alani"] = sd.gorus_alani(hm, -float(ext[1]) * 10.0 / 2.0)
    oz = sd.sahne_ozniteligi_say(ilk["ref"], ilk["ref_maske"])
    r["sahne"] = {"oznitelik": int(oz), "denetim": bool(oz >= sd.SAHNE_ASGARI_OZNITELIK)}
    return r


def _yanit(r: dict) -> dict:
    """Hesap sonucu → tel sözleşmesi (cm, camelCase; iç alanlar `_…` gitmez)."""
    sd = _sd()
    ext = r.get("ext_cm") or [0, 0, 0]

    def _cm(v):
        return None if v is None else round(float(v) / 10.0, 2)

    nedenler = [
        {
            "kod": n,
            "metin": neden_metni(n, px=r.get("izdusum_hatasi_px"), cm=f"{sd.KONUM_YAYILIM_ESIGI_MM / 10.0:g}"),
        }
        for n in r.get("nedenler") or []
    ]
    ga = r.get("gorus_alani") or {}
    return {
        "gecerli": bool(r.get("gecerli")),
        "nedenler": nedenler,
        "izdusumHatasiPx": r.get("izdusum_hatasi_px"),
        "olcumUyumuMm": r.get("olcum_uyumu_mm"),
        "yayilimCm": _cm(r.get("yayilim_mm")),
        "konumlar": [
            {
                "koseSapmasiMm": k.get("kose_sapmasi_mm"),
                "kuyuIzdusumPx": k.get("kuyu_izdusum_px"),
                "merkezCm": _cm_olcu(ext, k["merkez_kabin_mm"])[:2],
            }
            for k in r.get("konumlar") or []
        ],
        "caprazDogrulamaCm": None
        if r.get("capraz_dogrulama_mm") is None
        else [_cm(v) for v in r["capraz_dogrulama_mm"]],
        "hesaplananLensCm": None if not r.get("kamera_konumu_mm") else _cm_olcu(ext, r["kamera_konumu_mm"]),
        "olculenLensCm": None if not r.get("olculen_lens_mm") else _cm_olcu(ext, r["olculen_lens_mm"]),
        "lensYatayFarkiCm": _cm(r.get("lens_yatay_farki_mm")),
        "lensDikeyFarkiCm": _cm(r.get("lens_dikey_farki_mm")),
        "lensUyarisi": bool(r.get("lens_uyarisi")),
        "gorusAlani": None
        if not ga
        else {"onCm": ga.get("on"), "arkaCm": ga.get("arka"), "solCm": ga.get("sol"), "sagCm": ga.get("sag")},
        "sahne": r.get("sahne"),
        "esikler": {
            "izdusumPx": sd.IZDUSUM_ESIGI_PX,
            "lensCm": sd.LENS_UYARI_ESIGI_MM / 10.0,
            "lensDikeyCm": sd.LENS_DIKEY_UYARI_ESIGI_MM / 10.0,
            "olcumMm": sd.OLCUM_UYUM_ESIGI_MM,
            "yayilimCm": sd.KONUM_YAYILIM_ESIGI_MM / 10.0,
            "konumAsgari": sd.KONUM_ASGARI,
        },
    }


def durum_ozeti() -> dict:
    sd = _sd()
    kal, hata = sd.yukle(_veri_koku())
    if kal is None:
        return {"var": hata is not None, "gecerli": False, "hata": hata, "hataMetni": _kalibrasyon_yok_metni(hata)}
    fantom = kal.get("fantom") or {}

    def _cm(v):
        return None if v is None else round(float(v) / 10.0, 2)

    dog = list(kal.get("dogrulamalar") or [])
    lens = kal.get("olculen_lens_cm") or {}
    yen = kal.get("sahne_yenileme") or {}
    kimlik = (kal.get("kamera") or {}).get("kimlik") or {}
    return {
        "var": True,
        "gecerli": True,
        "hata": None,
        "tarih": kal.get("tarih"),
        "kameraIndeksi": (kal.get("kamera") or {}).get("indeks"),
        "kameraAdi": kimlik.get("ad"),
        "kameraVidPid": kimlik.get("vidpid"),
        "cozunurluk": [kal["kamera"]["genislik"], kal["kamera"]["yukseklik"]],
        "konumSayisi": len(kal.get("konumlar") or []),
        "yayilimCm": _cm(kal.get("yayilim_mm")),
        "izdusumHatasiPx": kal.get("izdusum_hatasi_px"),
        "lensFarkiCm": _cm(kal.get("lens_farki_mm")),
        "olculenLensTabanCm": lens.get("taban"),
        "gorusAlani": kal.get("gorus_alani"),
        "sahneDenetimi": bool((kal.get("referans") or {}).get("sahne_denetimi")),
        "eski": sd.eski_mi(kal),  # OTB T-0: yenilemeden sonra Doğrula geçtiyse ESKİ değil
        "eskiTarih": yen.get("tarih"),
        "tabanYukseltmesiCm": _cm(sd.taban_yukseltmesi_mm(kal)),
        "fantom": {
            "kalinlikCm": _cm(fantom.get("kalinlik_mm")),
            "tumorDerinligiCm": _cm(fantom.get("tumor_derinligi_mm")),
            "boyCm": [_cm(v) for v in fantom.get("boy_mm")] if fantom.get("boy_mm") else None,
        },
        "sonDogrulama": dog[-1] if dog else None,
    }


@router.get("/api/ai/pro/kalibrasyon")
def kalibrasyon_durumu():
    return durum_ozeti()


@router.post("/api/ai/pro/kalibrasyon/kare")
def kalibrasyon_karesi(_g: BosGovde):
    """Seçili kabin kamerasından `KARE_ADEDI` kare → plaka ızgarası OTOMATİK (kareler ortalanır) → numaralı köşelerle ekran karesi.
    Kare SUNUCUDA saklanır (kimlik döner). Plaka bulunamazsa kare yine döner (`plaka.bulundu` False + eylem metni)."""
    sd = _sd()
    bgrler, kare = _kamera_karesi(KARE_ADEDI)
    h, w = bgrler[0].shape[:2]
    intr, _yol = _ic_parametre(w, h)
    und, konum, neden, n = _kare_isle(bgrler, intr, sd)
    if neden:
        logger.info("kalibrasyon karesi: plaka bulunamadı (%s)", neden)
    ref, ref_maske = _kucuk_referans(und, konum, sd)
    gosterim, kose_gosterim = _isaretle(und, konum, GOSTERIM_GENISLIK)
    kimlik = secrets.token_hex(8)
    with _kilit:
        while len(_kareler) >= AZAMI_KARE:
            _kareler.pop(min(_kareler, key=lambda a: _kareler[a]["zaman"]))
        _kareler[kimlik] = {
            "konum": konum,
            "ref": ref,
            "ref_maske": ref_maske,
            "indeks": kare.get("indeks"),
            "kimlik": kare.get("kimlik"),
            "genislik": int(w),
            "yukseklik": int(h),
            "zaman": time.monotonic(),
        }
    return {
        "status": "success",
        "kareKimligi": kimlik,
        "kameraIndeksi": kare.get("indeks"),
        "genislik": int(w),
        "yukseklik": int(h),
        "image_base64": gosterim,
        "plaka": {
            "bulundu": konum is not None,
            "kuyuSayisi": 0 if konum is None else len(konum["kuyu_px"]),
            "kareSayisi": n,
            "kosePx": kose_gosterim,
            "metin": None if konum is not None else ceviri.t("ai.kalibrasyon.plakaBulunamadi"),
        },
    }


@router.post("/api/ai/pro/kalibrasyon/hesapla")
def kalibrasyon_hesapla(g: HesaplaGirdisi):
    return _yanit(_hesapla(g))


@router.post("/api/ai/pro/kalibrasyon/kaydet")
def kalibrasyon_kaydet(g: HesaplaGirdisi):
    import numpy as np

    _seans_kapisi()
    sd = _sd()
    r = _hesapla(g)
    y = _yanit(r)
    if not r.get("gecerli"):
        raise HTTPException(status_code=422, detail={"mesaj": ceviri.t("ai.kalibrasyon.reddedildi"), "sonuc": y})
    if r.get("lens_uyarisi") and not g.lensUyarisiniOnayla:
        fark = {"yatay": f"{y['lensYatayFarkiCm'] or 0:.1f}", "dikey": f"{y['lensDikeyFarkiCm'] or 0:.1f}"}
        raise HTTPException(
            status_code=409,
            detail={
                "mesaj": ceviri.t("ai.kalibrasyon.lensOnayGerekli", **fark),
                "sonuc": y,
            },
        )
    kareler, intr, yol = r["_kareler"], r["_intr"], r["_npz"]
    ilk = kareler[0]
    kal = {
        "tarih": sd.zaman_damgasi(),
        "kamera": {
            "indeks": ilk.get("indeks"),
            "kimlik": ilk.get("kimlik"),
            "genislik": ilk["genislik"],
            "yukseklik": ilk["yukseklik"],
        },
        "ic_parametre": {
            "npz": getattr(yol, "name", None),
            "sha256": sd.npz_sha256(yol) if yol else None,
            "K": intr.K.tolist(),
            "D": np.asarray(intr.D).ravel().tolist(),
        },
        "kabin_ext_cm": r["ext_cm"],
        "plaka": {"tur": 24, "dis_mm": list(sd.PLAKA_DIS_MM[24]), "yukseklik_mm": float(g.plakaYuksekligiCm) * 10.0},
        "duzlem_y_mm": r["duzlem_y_mm"],
        "konumlar": [
            {
                "olcum_cm": [None if o is None else [o.solCm, o.onCm] for o in kg.olcumler],
                "kose_px_duzeltilmis": np.round(np.asarray(kn["kose_px"], np.float64), 2).tolist(),
                **ks,
            }
            for kg, kn, ks in zip(g.konumlar, r["_konumlar"], r["konumlar"])
        ],
        "R": r["R"],
        "rvec": r["rvec"],
        "t_mm": r["t_mm"],
        "kamera_konumu_mm": r["kamera_konumu_mm"],
        "olculen_lens_cm": None
        if g.lens is None
        else {"sol": g.lens.solCm, "on": g.lens.onCm, "taban": g.lens.tabanCm},
        "olculen_lens_mm": r.get("olculen_lens_mm"),
        "lens_farki_mm": r.get("lens_farki_mm"),
        "lens_yatay_farki_mm": r.get("lens_yatay_farki_mm"),
        "lens_dikey_farki_mm": r.get("lens_dikey_farki_mm"),
        "lens_uyarisi_onaylandi": bool(r.get("lens_uyarisi") and g.lensUyarisiniOnayla),
        "izdusum_hatasi_px": r["izdusum_hatasi_px"],
        "olcum_uyumu_mm": r["olcum_uyumu_mm"],
        "yayilim_mm": r["yayilim_mm"],
        "capraz_dogrulama_mm": r.get("capraz_dogrulama_mm"),
        "gorus_alani": r.get("gorus_alani"),
        "referans": {"sahne_denetimi": r["sahne"]["denetim"], "oznitelik": r["sahne"]["oznitelik"]},
    }
    # Fantom ayarı + numune tabanı yükseltmesi yeniden kalibrasyonda KORUNUR (sahibin ölçüsü; kamera duruşuyla ilgisiz).
    # "Kalibre etmeden devam" kaydı (sahne_yenileme) KORUNMAZ — yeni kalibrasyon güncel.
    eski, _h = sd.yukle(_veri_koku())
    for alan in ("fantom", "numune_tabani"):
        if eski and eski.get(alan):
            kal[alan] = eski[alan]
    try:
        sd.kaydet(_veri_koku(), kal, referans_bgr=ilk["ref"], referans_maske=ilk["ref_maske"])
    except OSError as e:
        logger.warning("kabin kalibrasyonu yazılamadı: %r", e)
        raise HTTPException(
            status_code=503, detail=ceviri.t("ai.kalibrasyon.kaydedilemedi", neden=type(e).__name__)
        ) from None
    izi = _denetim_izi(
        "kabin_kalibrasyonu_kaydedildi",
        {
            k_: kal[k_]
            for k_ in (
                "tarih",
                "kamera",
                "duzlem_y_mm",
                "kamera_konumu_mm",
                "olculen_lens_mm",
                "lens_farki_mm",
                "lens_uyarisi_onaylandi",
                "izdusum_hatasi_px",
                "olcum_uyumu_mm",
                "yayilim_mm",
                "konumlar",
            )
        },
    )
    return {"status": "success", "sonuc": y, "durum": durum_ozeti(), "denetimIziYazildi": izi}


@router.post("/api/ai/pro/kalibrasyon/dogrula")
def kalibrasyon_dogrula(g: DogrulaGirdisi):
    """Plaka BAŞKA yerde: numaralı köşelerden ölçülenlerin kalibrasyonla hesaplanan konumu ↔ cetvel ölçüsü. Ölçüt plaka MERKEZİ
    (ölçülen köşelerin ortalaması) ≤ 1 cm; köşe başına fark bilgi (cetvel σ ≈ 5–8 mm)."""
    import numpy as np

    sd = _sd()
    kal, hata = sd.yukle(_veri_koku())
    if kal is None:
        raise HTTPException(status_code=409, detail=_kalibrasyon_yok_metni(hata))
    k = _kare(g.kareKimligi)
    if (k["genislik"], k["yukseklik"]) != (kal["kamera"]["genislik"], kal["kamera"]["yukseklik"]) or sd.kimlik_ayni(
        k.get("kimlik"), kal["kamera"].get("kimlik")
    ) is False:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pemf.kapi.kameraFarkli"))
    if k.get("konum") is None:
        raise HTTPException(status_code=422, detail=ceviri.t("ai.kalibrasyon.plakaBulunamadi"))
    olc = [(i, o) for i, o in enumerate(g.olcumler) if o is not None]
    if not olc or not all(_sonlu(o.solCm, o.onCm) for _, o in olc):
        raise HTTPException(status_code=422, detail=neden_metni("girdi_gecersiz"))
    hm = sd.DuzlemHaritasi(kal)
    tah, olculen = [], []
    for i, o in olc:
        p = hm.kabin_noktasi(k["konum"]["kose_px"][i], hm.duzlem_y_mm, duzeltilmis=True, kabin_siniri=False)
        tah.append(p[[0, 2]])
        olculen.append(sd.kabin_noktasi_mm(o.solCm, o.onCm, 0.0, hm.ext_cm)[[0, 2]])
    tah, olculen = np.array(tah), np.array(olculen)
    kose = [None] * 4
    for (i, _o), t, m in zip(olc, tah, olculen):
        kose[i] = round(float(np.linalg.norm(t - m)) / 10.0, 2)
    merkez = round(float(np.linalg.norm(tah.mean(axis=0) - olculen.mean(axis=0))) / 10.0, 2)
    kayit = {
        "tarih": sd.zaman_damgasi(),
        "kose_fark_cm": kose,
        "merkez_fark_cm": merkez,
        "gecti": merkez <= sd.DOGRULAMA_ESIGI_MM / 10.0,
    }
    try:
        sd.dogrulama_ekle(_veri_koku(), kayit)
    except OSError:
        logger.warning("kalibrasyon doğrulaması dosyaya eklenemedi", exc_info=True)
    _denetim_izi("kabin_kalibrasyonu_dogrulandi", kayit)
    return {
        "status": "success",
        "farkCm": kose,
        "merkezFarkCm": merkez,
        "gecti": kayit["gecti"],
        "esikCm": sd.DOGRULAMA_ESIGI_MM / 10.0,
    }


@router.post("/api/ai/pro/kalibrasyon/fantom")
def kalibrasyon_fantom(g: FantomGirdisi):
    _seans_kapisi()
    sd = _sd()
    boy = (g.boyCm, g.enCm)
    gecerli = (
        _sonlu(g.kalinlikCm, g.tumorDerinligiCm)
        and 0 < g.kalinlikCm <= FANTOM_AZAMI_KALINLIK_CM
        and 0 <= g.tumorDerinligiCm < g.kalinlikCm
        and (all(v is None for v in boy) or (all(v is not None and _sonlu(v) and 0 < v <= 50 for v in boy)))
    )
    if not gecerli:
        raise HTTPException(status_code=422, detail=ceviri.t("ai.kalibrasyon.fantomGecersiz"))
    kal, hata = sd.yukle(_veri_koku())
    if kal is None:
        raise HTTPException(status_code=409, detail=_kalibrasyon_yok_metni(hata))
    ayar = {
        "kalinlik_mm": round(g.kalinlikCm * 10.0, 2),
        "tumor_derinligi_mm": round(g.tumorDerinligiCm * 10.0, 2),
        "boy_mm": [round(max(boy) * 10.0, 2), round(min(boy) * 10.0, 2)]
        if g.boyCm is not None
        else list((kal.get("fantom") or {}).get("boy_mm") or sd.VARSAYILAN_FANTOM_BOY_MM),
    }
    try:
        sd.fantom_ayari_yaz(_veri_koku(), ayar)
    except OSError as e:
        raise HTTPException(
            status_code=503, detail=ceviri.t("ai.kalibrasyon.kaydedilemedi", neden=type(e).__name__)
        ) from None
    izi = _denetim_izi("kabin_kalibrasyonu_fantom_ayari", ayar)
    return {"status": "success", "durum": durum_ozeti(), "denetimIziYazildi": izi}


@router.post("/api/ai/pro/kalibrasyon/taban")
def kalibrasyon_taban(g: TabanGirdisi):
    """Sahip kararı (KD-1): numune tabanı yükseltmesi. Kullanıcı yeni "lens → numune tabanı" uzaklığını girer; yükseltme = kalibrasyonda
    ölçülen lens yüksekliği − girilen (0–20 cm). Petri ızgara düzlemi + hedef ve fantom tabanı bu kadar yukarı alınır."""
    _seans_kapisi()
    sd = _sd()
    kal, hata = sd.yukle(_veri_koku())
    if kal is None:
        raise HTTPException(status_code=409, detail=_kalibrasyon_yok_metni(hata))
    lens_taban = (kal.get("olculen_lens_cm") or {}).get("taban")
    if not _sonlu(lens_taban):
        raise HTTPException(status_code=409, detail=ceviri.t("ai.kalibrasyon.lensYuksekligiYok"))
    yukseltme_cm = float(lens_taban) - float(g.lensUzaklikCm) if _sonlu(g.lensUzaklikCm) else float("nan")
    if not _sonlu(yukseltme_cm) or not (-0.5 <= yukseltme_cm <= sd.TABAN_YUKSELTME_AZAMI_MM / 10.0):
        sinir = {"lens": f"{float(lens_taban):g}", "azami": f"{sd.TABAN_YUKSELTME_AZAMI_MM / 10.0:g}"}
        raise HTTPException(status_code=422, detail=ceviri.t("ai.kalibrasyon.tabanGecersiz", **sinir))
    ayar = {
        "yukseltme_mm": round(max(0.0, yukseltme_cm) * 10.0, 2),
        "lens_uzaklik_cm": float(g.lensUzaklikCm),
        "lens_taban_cm": float(lens_taban),
        "tarih": sd.zaman_damgasi(),
    }
    try:
        sd.numune_tabani_yaz(_veri_koku(), ayar)
    except OSError as e:
        raise HTTPException(
            status_code=503, detail=ceviri.t("ai.kalibrasyon.kaydedilemedi", neden=type(e).__name__)
        ) from None
    izi = _denetim_izi("kabin_kalibrasyonu_numune_tabani", ayar)
    return {"status": "success", "durum": durum_ozeti(), "denetimIziYazildi": izi}


@router.post("/api/ai/pro/kalibrasyon/sahne-yenile")
def kalibrasyon_sahne_yenile(_g: BosGovde):
    """Sahip kararı (KD-1): "kamera oynamış olabilir" → KALİBRE ETMEDEN DEVAM. Yalnız kayma ~≤ 2 cm ise (sabit sahne ≤
    `SAHNE_YENILEME_ESIGI_PX`, karede plaka varsa kuyu aralığı ≤ %10): o anki kare yeni sahne referansı olur, kuyu aralığı toleransı %10'a
    çıkar, her karede "kalibrasyon eski" uyarısı kalır; denetim izine. Daha büyük kayma / ölçülemeyen sahne → 409 (yeniden kalibre edin)."""
    _seans_kapisi()
    sd = _sd()
    kal, hata = sd.yukle(_veri_koku())
    if kal is None:
        raise HTTPException(status_code=409, detail=_kalibrasyon_yok_metni(hata))
    bgrler, kare = _kamera_karesi(1)
    h, w = bgrler[0].shape[:2]
    if (w, h) != (kal["kamera"]["genislik"], kal["kamera"]["yukseklik"]) or sd.kimlik_ayni(
        kare.get("kimlik"), kal["kamera"].get("kimlik")
    ) is False:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pemf.kapi.kameraFarkli"))
    intr, _yol = _ic_parametre(w, h)
    und, konum, _neden, _n = _kare_isle(bgrler, intr, sd)
    ref, ref_maske = _kucuk_referans(und, konum, sd)
    eski_ref = kal.get("_referans_gri")
    s = {"olculdu": False, "neden": "referans_yok"}
    if eski_ref is not None:
        import cv2
        import numpy as np

        rm = cv2.erode((eski_ref > 0).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
        s = sd.sahne_kaymasi(eski_ref, ref, referans_maske=rm, kare_maske=ref_maske, tam_genislik=w)
    ka = None
    if konum is not None:
        try:
            ka = sd.komsu_kuyu_araligi(
                sd.DuzlemHaritasi(kal), konum, 19.3, sd.DuzlemHaritasi(kal).numune_y_mm, sd.KUYU_ARALIGI_TOLERANSI_ESKI
            )
        except Exception:
            logger.info("sahne yenileme: kuyu aralığı ölçülemedi", exc_info=True)
    kucuk = bool(s.get("olculdu")) and float(s.get("kayma_px", 1e9)) <= sd.SAHNE_YENILEME_ESIGI_PX
    if not kucuk or (ka is not None and not ka["gecti"]):
        _denetim_izi("kabin_kalibrasyonu_sahne_yenileme_reddedildi", {"sahne": s, "kuyu_araligi": ka})
        kayma = {"px": str(s.get("kayma_px", "?")), "esik": f"{sd.SAHNE_YENILEME_ESIGI_PX:g}"}
        raise HTTPException(status_code=409, detail=ceviri.t("ai.kalibrasyon.sahneYenilemeBuyuk", **kayma))
    kayit = {
        "tarih": sd.zaman_damgasi(),
        "kayma_px": s.get("kayma_px"),
        "kuyu_sapma": None if ka is None else ka["sapma"],
    }
    try:
        sd.sahne_yenile(_veri_koku(), ref, ref_maske, kayit)
    except OSError as e:
        raise HTTPException(
            status_code=503, detail=ceviri.t("ai.kalibrasyon.kaydedilemedi", neden=type(e).__name__)
        ) from None
    izi = _denetim_izi("kabin_kalibrasyonu_sahne_yenilendi", kayit)
    return {"status": "success", "kaymaPx": s.get("kayma_px"), "durum": durum_ozeti(), "denetimIziYazildi": izi}
