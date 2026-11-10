# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN KALİBRASYONU UÇLARI — sabit düzlem kalibrasyonu ekranının arka ucu (KD · sahip kararları Y258–Y260, 2026-11-10).

Akış (araştırma profili; masaüstü + telefon + web aynı uçları kullanır):
  1. `POST /api/ai/pro/kalibrasyon/kare` — seçili kabin kamerasından tam çözünürlüklü kare; kare SUNUCUDA saklanır (kimlikle), istemci
     yalnız gösterir ve dokunulan pikselleri geri yollar (hesap, kameradan GELEN kareyle yapılır — yüklenen keyfi görüntüyle değil).
  2. `POST …/hesapla` — 4 köşe (ön-sol, ön-sağ, arka-sağ, arka-sol: piksel + sol / ön cm) + lens (sol / ön / taban cm) → çözüm, KAYDETMEZ.
  3. `POST …/kaydet` — aynı girdi YENİDEN hesaplanır (istemcinin sonucuna güvenilmez); geçersizse 422, lens farkı > 2 cm ise AÇIK onay
     yoksa 409; veri köküne yazılır (+ referans kare) ve DENETİM İZİNE.
  4. `POST …/dogrula` — plaka başka yerde, 1–4 köşe → hesaplanan ↔ ölçülen fark (cm); ≤ 1 cm geçer; denetim izine.
  5. `POST …/fantom` — fantom kalınlığı / tümör derinliği / boyu (sahip ölçer) — fantom hedef düzlemi buradan.
  6. `GET  /api/ai/pro/kalibrasyon` — durum.
Yetki: `/api/ai/pro/*` ile AYNI (sahibin AI Pro muafiyeti, `auth._EXEMPT_PREFIXES`) + araştırma eklentisi (`require_research`).
⚠️ AI Pro seansı sürerken kalibrasyon / fantom ayarı DEĞİŞMEZ (hedefler kayar) → 409. ACİL DURDUR bu uçlara bağlı DEĞİL (Ö.4-Y8).
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

#: Saklanan kalibrasyon karesinin ömrü ve en çok sayısı (tam çözünürlük BGR ~6 MB).
KARE_OMRU_SN = 900.0
AZAMI_KARE = 3
#: Fantom ayarı sınırları (cm) — kabin iç yüksekliği 35 cm, kamera kapakta.
FANTOM_AZAMI_KALINLIK_CM = 20.0
_kareler: dict[str, dict] = {}
_kilit = threading.Lock()


class KoseGirdisi(BaseModel):
    u: float
    v: float
    solCm: float  # noqa: N815 — tel sözleşmesi (arayüz camelCase)
    onCm: float  # noqa: N815


class LensGirdisi(BaseModel):
    solCm: float  # noqa: N815
    onCm: float  # noqa: N815
    tabanCm: float  # noqa: N815


class HesaplaGirdisi(BaseModel):
    kareKimligi: str = Field(max_length=64)  # noqa: N815
    koseler: list[KoseGirdisi] = Field(min_length=4, max_length=4)
    lens: LensGirdisi | None = None
    plakaYuksekligiCm: float = 2.0  # noqa: N815
    lensUyarisiniOnayla: bool = False  # noqa: N815


class DogrulaGirdisi(BaseModel):
    kareKimligi: str = Field(max_length=64)  # noqa: N815
    koseler: list[KoseGirdisi] = Field(min_length=1, max_length=4)


class FantomGirdisi(BaseModel):
    kalinlikCm: float  # noqa: N815
    tumorDerinligiCm: float = 0.0  # noqa: N815
    boyCm: float | None = None  # noqa: N815
    enCm: float | None = None  # noqa: N815


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
    if kod == "olcum_tutarsiz":
        return ceviri.t("ai.kalibrasyon.neden.olcumTutarsiz")
    if kod == "cozum_yok":
        return ceviri.t("ai.kalibrasyon.neden.cozumYok")
    if kod == "kamera_duzlem_altinda":
        return ceviri.t("ai.kalibrasyon.neden.kameraDuzlemAltinda")
    if kod == "izdusum_yuksek":
        return ceviri.t("ai.kalibrasyon.neden.izdusumYuksek", px=str(ek.get("px", "?")))
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


def _hesapla(g: HesaplaGirdisi) -> dict:
    """Ortak hesap (hesapla + kaydet): çözüm + kalibrasyon karesinde kuyu aralığı + sahne özniteliği. KAYDETMEZ."""
    import cv2
    import numpy as np

    from ai_hub.cv_ortak.coord_transform import undistort_image

    sd = _sd()
    k = _kare(g.kareKimligi)
    intr, yol = _ic_parametre(k["genislik"], k["yukseklik"])
    from ai_hub.inference_petri_dish.petri_cv_v2 import load_cabin_config

    ext = load_cabin_config(None).geometry.cabin_extent_cm
    lens = (g.lens.solCm, g.lens.onCm, g.lens.tabanCm) if g.lens is not None else None
    r = sd.kalibrasyon_hesapla(
        kose_px=[(c.u, c.v) for c in g.koseler],
        kose_olcum_cm=[(c.solCm, c.onCm) for c in g.koseler],
        K=intr.K,
        D=intr.D,
        boyut=(k["genislik"], k["yukseklik"]),
        ext_cm=ext,
        plaka_yuksekligi_mm=float(g.plakaYuksekligiCm) * 10.0 if _sonlu(g.plakaYuksekligiCm) else float("nan"),
        lens_cm=lens,
    )
    r["ext_cm"] = list(ext)
    r["_intr"], r["_npz"], r["_kare"] = intr, yol, k
    if not r.get("R"):
        return r
    kal = {
        "kamera": {"genislik": k["genislik"], "yukseklik": k["yukseklik"]},
        "ic_parametre": {"K": intr.K.tolist(), "D": np.asarray(intr.D).ravel().tolist()},
        "R": r["R"],
        "t_mm": r["t_mm"],
        "kabin_ext_cm": list(ext),
        "duzlem_y_mm": r["duzlem_y_mm"],
    }
    hm = sd.DuzlemHaritasi(kal)
    und = undistort_image(k["bgr"], intr)
    poly = cv2.undistortPoints(
        np.array([[c.u, c.v] for c in g.koseler], dtype=np.float64).reshape(-1, 1, 2), intr.K, intr.D, P=hm.K_yeni
    ).reshape(-1, 2)
    maske = sd.cokgen_maskesi((k["genislik"], k["yukseklik"]), [poly], genislet_px=40)
    oz = sd.sahne_ozniteligi_say(und, maske)
    r["sahne"] = {"oznitelik": int(oz), "denetim": bool(oz >= sd.SAHNE_ASGARI_OZNITELIK)}
    r["_und"], r["_maske"] = und, maske
    r["kuyu_araligi"] = None
    try:
        from ai_hub.inference_petri_dish.petri_cv_v2 import plate_grid

        grid = plate_grid.detect_plate_wells(und, 24, yolo=None)
        if grid.success and grid.H_ransac is not None:
            r["kuyu_araligi"] = sd.kuyu_araligi(
                hm, grid.H_ransac, grid.spec.rows, grid.spec.cols, grid.spec.pitch_mm, hm.duzlem_y_mm
            )
    except Exception:
        logger.info("kalibrasyon karesinde kuyu aralığı ölçülemedi", exc_info=True)
    return r


def _yanit(r: dict) -> dict:
    """Hesap sonucu → tel sözleşmesi (cm, camelCase; iç alanlar `_…` gitmez)."""

    def _cm(v):
        return None if v is None else [round(float(x) / 10.0, 2) for x in v]

    nedenler = [{"kod": n, "metin": neden_metni(n, px=r.get("izdusum_hatasi_px"))} for n in r.get("nedenler") or []]
    ka = r.get("kuyu_araligi")
    return {
        "gecerli": bool(r.get("gecerli")),
        "nedenler": nedenler,
        "izdusumHatasiPx": r.get("izdusum_hatasi_px"),
        "koseIzdusumPx": r.get("kose_izdusum_px"),
        "olcumUyumuMm": r.get("olcum_uyumu_mm"),
        "koseOlcumSapmasiMm": r.get("kose_olcum_sapmasi_mm"),
        "hesaplananLensCm": _cm(r.get("kamera_konumu_mm")),
        "olculenLensCm": _cm(r.get("olculen_lens_mm")),
        "lensFarkiCm": None if r.get("lens_farki_mm") is None else round(float(r["lens_farki_mm"]) / 10.0, 2),
        "lensUyarisi": bool(r.get("lens_uyarisi")),
        "kuyuAraligi": None
        if not ka
        else {
            "sutunMm": ka["sutun_mm"],
            "satirMm": ka["satir_mm"],
            "beklenenMm": ka["beklenen_mm"],
            "sapma": ka["sapma"],
            "gecti": ka["gecti"],
        },
        "sahne": r.get("sahne"),
        "esikler": {
            "izdusumPx": _sd().IZDUSUM_ESIGI_PX,
            "lensCm": _sd().LENS_UYARI_ESIGI_MM / 10.0,
            "kuyuAraligiOran": _sd().KUYU_ARALIGI_TOLERANSI,
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
    return {
        "var": True,
        "gecerli": True,
        "hata": None,
        "tarih": kal.get("tarih"),
        "kameraIndeksi": (kal.get("kamera") or {}).get("indeks"),
        "cozunurluk": [kal["kamera"]["genislik"], kal["kamera"]["yukseklik"]],
        "izdusumHatasiPx": kal.get("izdusum_hatasi_px"),
        "lensFarkiCm": _cm(kal.get("lens_farki_mm")),
        "sahneDenetimi": bool((kal.get("referans") or {}).get("sahne_denetimi")),
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
def kalibrasyon_karesi():
    """Seçili kabin kamerasından TAM çözünürlüklü kare — sunucuda saklanır (kimlik döner). AI Pro kamerayı tutuyorsa 409."""
    import cv2
    import numpy as np
    from utils import kabin_kamerasi as kk

    from servers.settings_router import _ai_kamerasi_mesgul

    if _ai_kamerasi_mesgul():
        raise HTTPException(status_code=409, detail=ceviri.t("ayarlar.kabinKamerasi.kareMesgul"))
    try:
        kare = kk.kare_al()
    except kk.KameraSecilmedi:
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pro.hazirlik.kameraSecilmedi")) from None
    if kare is None:
        secim = kk.secili_kamera() or {}
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks=str(secim.get("indeks", "?"))),
        )
    bgr = cv2.imdecode(np.frombuffer(base64.b64decode(kare["image_base64"]), np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise HTTPException(
            status_code=503, detail=ceviri.t("ayarlar.kabinKamerasi.kareAlinamadi", indeks=str(kare.get("indeks")))
        )
    kimlik = secrets.token_hex(8)
    with _kilit:
        while len(_kareler) >= AZAMI_KARE:
            _kareler.pop(min(_kareler, key=lambda a: _kareler[a]["zaman"]))
        _kareler[kimlik] = {
            "bgr": bgr,
            "indeks": kare.get("indeks"),
            "genislik": int(bgr.shape[1]),
            "yukseklik": int(bgr.shape[0]),
            "zaman": time.monotonic(),
        }
    return {
        "status": "success",
        "kareKimligi": kimlik,
        "kameraIndeksi": kare.get("indeks"),
        "genislik": int(bgr.shape[1]),
        "yukseklik": int(bgr.shape[0]),
        "image_base64": kare["image_base64"],
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
        raise HTTPException(
            status_code=409,
            detail={"mesaj": ceviri.t("ai.kalibrasyon.lensOnayGerekli", cm=f"{y['lensFarkiCm']:.1f}"), "sonuc": y},
        )
    k, intr, yol = r["_kare"], r["_intr"], r["_npz"]
    kal = {
        "tarih": sd.zaman_damgasi(),
        "kamera": {"indeks": k.get("indeks"), "genislik": k["genislik"], "yukseklik": k["yukseklik"]},
        "ic_parametre": {
            "npz": getattr(yol, "name", None),
            "sha256": sd.npz_sha256(yol) if yol else None,
            "K": intr.K.tolist(),
            "D": np.asarray(intr.D).ravel().tolist(),
        },
        "kabin_ext_cm": r["ext_cm"],
        "plaka": {"tur": 24, "dis_mm": list(sd.PLAKA_DIS_MM[24]), "yukseklik_mm": float(g.plakaYuksekligiCm) * 10.0},
        "duzlem_y_mm": r["duzlem_y_mm"],
        "koseler": [
            {
                "ad": ad,
                "px": [c.u, c.v],
                "sol_cm": c.solCm,
                "on_cm": c.onCm,
                "kabin_mm": kab,
                "izdusum_px": ip,
                "olcum_sapmasi_mm": os_,
            }
            for ad, c, kab, ip, os_ in zip(
                sd.KOSE_ADLARI, g.koseler, r["kose_kabin_mm"], r["kose_izdusum_px"], r["kose_olcum_sapmasi_mm"]
            )
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
        "lens_uyarisi_onaylandi": bool(r.get("lens_uyarisi") and g.lensUyarisiniOnayla),
        "izdusum_hatasi_px": r["izdusum_hatasi_px"],
        "olcum_uyumu_mm": r["olcum_uyumu_mm"],
        "kuyu_araligi": r.get("kuyu_araligi"),
        "referans": {"sahne_denetimi": r["sahne"]["denetim"], "oznitelik": r["sahne"]["oznitelik"]},
    }
    # Fantom ayarı yeniden kalibrasyonda KORUNUR (sahibin ölçüsü; kamera duruşuyla ilgisiz).
    eski, _h = sd.yukle(_veri_koku())
    if eski and eski.get("fantom"):
        kal["fantom"] = eski["fantom"]
    try:
        sd.kaydet(_veri_koku(), kal, referans_bgr=r["_und"], referans_maske=r["_maske"])
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
                "koseler",
            )
        },
    )
    return {"status": "success", "sonuc": y, "durum": durum_ozeti(), "denetimIziYazildi": izi}


@router.post("/api/ai/pro/kalibrasyon/dogrula")
def kalibrasyon_dogrula(g: DogrulaGirdisi):
    """Plaka BAŞKA yerde: dokunulan köşelerin kalibrasyonla hesaplanan konumu ↔ cetvel ölçüsü (X / Z farkı, cm). ≤ 1 cm geçer."""
    import numpy as np

    sd = _sd()
    kal, hata = sd.yukle(_veri_koku())
    if kal is None:
        raise HTTPException(status_code=409, detail=_kalibrasyon_yok_metni(hata))
    k = _kare(g.kareKimligi)
    if (k["genislik"], k["yukseklik"]) != (kal["kamera"]["genislik"], kal["kamera"]["yukseklik"]):
        raise HTTPException(status_code=409, detail=ceviri.t("ai.pemf.kapi.kameraFarkli"))
    hm = sd.DuzlemHaritasi(kal)
    farklar = []
    for c in g.koseler:
        if not _sonlu(c.u, c.v, c.solCm, c.onCm):
            raise HTTPException(status_code=422, detail=neden_metni("girdi_gecersiz"))
        p = hm.kabin_noktasi((c.u, c.v), hm.duzlem_y_mm, duzeltilmis=False, kabin_siniri=False)
        o = sd.kabin_noktasi_mm(c.solCm, c.onCm, 0.0, hm.ext_cm)
        farklar.append(round(float(np.hypot(p[0] - o[0], p[2] - o[2])) / 10.0, 2))
    maks = max(farklar)
    kayit = {
        "tarih": sd.zaman_damgasi(),
        "fark_cm": farklar,
        "maks_cm": maks,
        "gecti": maks <= sd.DOGRULAMA_ESIGI_MM / 10.0,
    }
    try:
        sd.dogrulama_ekle(_veri_koku(), kayit)
    except OSError:
        logger.warning("kalibrasyon doğrulaması dosyaya eklenemedi", exc_info=True)
    _denetim_izi("kabin_kalibrasyonu_dogrulandi", kayit)
    return {
        "status": "success",
        "farkCm": farklar,
        "maksCm": maks,
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
