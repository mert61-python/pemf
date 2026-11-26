# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y308 (sahip 19-11) — KABİN SENSÖRÜ (MLX) KONUM DİLİMLERİ: seansın sensör konumu girişleri (`database.thdb_sensor_konumu`) ölçümleri
zaman DİLİMLERİNE ayırır. Dilim başına: konum (ya da "serbest"), süre, kabin sensörünün ortalama / en yüksek alanı (dakika ortalamaları,
mT) ve KONUMLU dilimde aynı noktada ODAK alan modelinin o dilimdeki sürüş planıyla (bobin koşuları: duty / frekans / faz) TAHMİNİ +
fark %. Serbest dilimde tahmin YOK. Giriş HİÇ yoksa dilim de yok → seans detayı / PDF / CSV bugünküyle BİREBİR.

Konum çevirisi Doğrula'nın kullandığı kabin kalibrasyonu kuralıyla AYNI (`sabit_duzlem.kabin_noktasi_mm`, ölçü kabin kalibrasyonunun
iç ölçüsünden; ikinci bir çerçeve YOK). Model: canlı alan haritasıyla AYNI fizik (`canli_alan_hesapci` — `AlanModeli.td_dalga_faz` +
`gram_tepe`, ortak dalga). YALNIZ GÖSTERİM — sürüşe ve ACİL DURDUR'a hiçbir koşul eklemez."""

from __future__ import annotations

import math
from typing import Callable

#: Kabin sensörünün (MLX90393) telemetri kanalı — TEK sabit (`utils.kabin_sensoru`); firmware DEĞİŞMEZ.
from utils.kabin_sensoru import kabin_sensoru_kanali_mi

#: Konum girdisinin kabul aralığı (cm; kabin ~54 × 40 × 37 cm — çıkıntı / taban kuralı Doğrula ile aynı) ve not uzunluğu.
SINIR_CM = (0.0, 100.0)
NOT_AZAMI = 200
#: Seans dışı zamanda giriş: başlangıç / bitiş damgasına bu kadar pay (saat yuvarlaması).
ZAMAN_PAYI_SN = 5.0

from pydantic import BaseModel  # noqa: E402


class SensorKonumuGovde(BaseModel):
    """Tel sözleşmesi (arayüz camelCase). `serbest` = konumsuz dilim; `zamanEpoch` yalnız seans sonrası girişte (canlıda sunucu saati)."""

    serbest: bool = False
    solCm: float | None = None  # noqa: N815
    onCm: float | None = None  # noqa: N815
    yukseklikCm: float | None = None  # noqa: N815
    notMetni: str = ""  # noqa: N815
    zamanEpoch: float | None = None  # noqa: N815


def dogrula(g: SensorKonumuGovde) -> dict:
    """Gövde → DB alanları; geçersizse ValueError (çağıran 422 + `gecmis.sensorKonumu.gecersiz`)."""
    not_metni = (g.notMetni or "").strip()
    if len(not_metni) > NOT_AZAMI:
        raise ValueError("not")
    if g.serbest:
        return {"serbest": True, "sol_cm": None, "on_cm": None, "yukseklik_cm": None, "not_metni": not_metni}
    v = (g.solCm, g.onCm, g.yukseklikCm)
    if not all(_sonlu(x) and SINIR_CM[0] <= float(x) <= SINIR_CM[1] for x in v):
        raise ValueError("konum")
    return {
        "serbest": False,
        "sol_cm": float(v[0]),
        "on_cm": float(v[1]),
        "yukseklik_cm": float(v[2]),
        "not_metni": not_metni,
    }


def zaman_seansta_mi(zaman: float, baslangic, bitis) -> bool:
    """Seans sonrası girişin zamanı seansın [başlangıç, bitiş] aralığında mı (bilinmeyen uç denetlenmez)."""
    if _sonlu(baslangic) and zaman < float(baslangic) - ZAMAN_PAYI_SN:
        return False
    return not (_sonlu(bitis) and zaman > float(bitis) + ZAMAN_PAYI_SN)


def _sonlu(*v) -> bool:
    return all(isinstance(x, (int, float)) and math.isfinite(float(x)) for x in v)


def _ort(d: list) -> float | None:
    return round(sum(d) / len(d), 4) if d else None


def kabin_noktasi(sol_cm: float, on_cm: float, yukseklik_cm: float) -> list | None:
    """Sol / ön çıkıntıdan + tabandan cm → kabin mm (Doğrula kuralı). Kabin kalibrasyonu yoksa None."""
    from ai_hub.cv_ortak import sabit_duzlem as sd
    from servers.kabin_kalibrasyonu import _veri_koku

    kal, _hata = sd.yukle(_veri_koku())
    if kal is None:
        return None
    hm = sd.DuzlemHaritasi(kal)
    return [float(v) for v in sd.kabin_noktasi_mm(sol_cm, on_cm, yukseklik_cm, hm.ext_cm)]


def nokta_tahmini(P_mm: list, bobinler: list, model_saglayici: Callable | None = None) -> float | None:
    """`bobinler` = [(bobin, frekans_hz, duty_oran, faz_derece)] ile `P_mm` noktasında tepe |B| (mT) — canlı alan haritasının fiziği.
    Model / kalibrasyon yoksa, nokta tablo dışındaysa ya da bobin yoksa None."""
    import numpy as np

    from servers import canli_alan_hesapci as h

    if not bobinler:
        return None
    model = model_saglayici or h.varsayilan_model
    try:
        from ai_hub.odak.alan import gram, gram_tepe, ortak_dalga

        frek = sorted({f for _, f, _, _ in bobinler})
        modeller = {f: model(f) for f in frek}
        A0 = modeller[frek[0]]
        P = np.asarray([P_mm], dtype=float)
        if not bool(h.tablo_icinde(A0, P)[0]):
            return None
        G = gram(A0.alan(P))
        parcalar = []
        for f in frek:
            duty, faz = np.zeros(h.N_BOBIN), np.zeros(h.N_BOBIN)
            for b, fb, d, p in bobinler:
                if fb == f and 1 <= b <= h.N_BOBIN:
                    duty[b - 1], faz[b - 1] = d, p
            parcalar.append((f, modeller[f].td_dalga_faz(duty, faz)))
        return round(float(gram_tepe(G, ortak_dalga(parcalar))[0]), 4)
    except Exception:  # kalibrasyon / tablo / bütünlük hatası → tahmin YOK (gösterim; çökme yok)
        import logging

        logging.getLogger(__name__).warning("sensör konumu: model tahmini hesaplanamadı", exc_info=True)
        return None


def _surus(kosular: list, t0: float, t1: float) -> list:
    """Dilimle örtüşen bobin koşularından sürüş planı: bobin başına dilimle EN ÇOK örtüşen koşu."""
    en: dict = {}
    for k in kosular:
        b, s, e = k.get("coil_id"), k.get("started_epoch"), k.get("ended_epoch")
        if not _sonlu(b, s) or not _sonlu(k.get("frequency_hz"), k.get("duty_percent")):
            continue
        e = float(e) if _sonlu(e) else t1
        ortusme = min(e, t1) - max(float(s), t0)
        if ortusme <= 0 or float(k["duty_percent"]) <= 0:
            continue
        if ortusme > en.get(int(b), (0.0, None))[0]:
            en[int(b)] = (ortusme, k)
    return [
        (b, float(k["frequency_hz"]), float(k["duty_percent"]) / 100.0, float(k.get("phase") or 0.0))
        for b, (_, k) in sorted(en.items())
    ]


def konum_metni(d: dict, serbest_metni: str) -> str:
    """Dilim / giriş konumu: "sol / ön / yükseklik" cm (rapor biçimi) ya da serbest."""
    if d.get("serbest") or not _sonlu(d.get("sol_cm"), d.get("on_cm"), d.get("yukseklik_cm")):
        return serbest_metni
    return " / ".join(f"{float(d[k]):g}" for k in ("sol_cm", "on_cm", "yukseklik_cm"))


def dilimler(
    konumlar: list,
    baslangic: float | None,
    bitis: float | None,
    ornekler: list,
    kosular: list,
    *,
    nokta: Callable | None = None,
    tahmin: Callable | None = None,
) -> list:
    """Girişler → zaman dilimleri (giriş yoksa BOŞ liste — çıktı bugünküyle birebir). İlk girişten önceki süre "serbest" dilimdir."""
    if not konumlar:
        return []
    nokta = nokta or kabin_noktasi
    tahmin = tahmin or nokta_tahmini
    sirali = sorted(konumlar, key=lambda k: (float(k["zaman_epoch"]), k.get("id") or 0))
    bas = float(baslangic) if _sonlu(baslangic) else float(sirali[0]["zaman_epoch"])
    son = (
        float(bitis)
        if _sonlu(bitis)
        else max(
            [float(sirali[-1]["zaman_epoch"])] + [float(o["sample_ts"]) for o in ornekler if _sonlu(o.get("sample_ts"))]
        )
    )
    araliklar = []
    if float(sirali[0]["zaman_epoch"]) > bas:
        araliklar.append((bas, float(sirali[0]["zaman_epoch"]), None))
    for i, k in enumerate(sirali):
        t0 = max(bas, float(k["zaman_epoch"]))
        t1 = float(sirali[i + 1]["zaman_epoch"]) if i + 1 < len(sirali) else son
        if t1 > t0:
            araliklar.append((t0, t1, k))
    sonuc = []
    for t0, t1, k in araliklar:
        mT = [
            float(o["magnetic_field_mt"])
            for o in ornekler
            if kabin_sensoru_kanali_mi(o.get("coil_id"))
            and _sonlu(o.get("sample_ts"), o.get("magnetic_field_mt"))
            and t0 <= float(o["sample_ts"]) < t1
        ]
        serbest = k is None or bool(k.get("serbest"))
        d = {
            "baslangic_epoch": t0,
            "bitis_epoch": t1,
            "sure_sn": round(t1 - t0, 1),
            "serbest": serbest,
            "kayit_id": None if k is None else k.get("id"),
            "sol_cm": None if serbest else k.get("sol_cm"),
            "on_cm": None if serbest else k.get("on_cm"),
            "yukseklik_cm": None if serbest else k.get("yukseklik_cm"),
            "not": "" if k is None else (k.get("not_metni") or ""),
            "olcum_sayisi": len(mT),
            "ortalama_mt": _ort(mT),
            "tepe_mt": round(max(mT), 4) if mT else None,
            "tahmin_mt": None,
            "fark_yuzde": None,
        }
        if not serbest and _sonlu(d["sol_cm"], d["on_cm"], d["yukseklik_cm"]):
            P = nokta(float(d["sol_cm"]), float(d["on_cm"]), float(d["yukseklik_cm"]))
            if P is not None:
                d["tahmin_mt"] = tahmin(P, _surus(kosular, t0, t1))
        if d["tahmin_mt"] and d["ortalama_mt"] is not None:
            d["fark_yuzde"] = round((d["ortalama_mt"] - d["tahmin_mt"]) / d["tahmin_mt"] * 100.0, 1)
        sonuc.append(d)
    return sonuc


#: FK · K1 d2 (istem 58): tezgâh MLX ölçümünün HAZIR NOKTA listesi — veri kökünde `kabin_kalibrasyonu/sensor_noktalari.json` (kedi fizik
#: planı `DENETIM\odak\kedi_fizik\kedi_b3.py plan` üretir; kalibrasyon gibi VERİ KÖKÜNDE — güncelleme ezmez). Yeni şema / uç YOK: canlı uç
#: listeyi `hazir` alanında döner, arayüz dokununca formun sol / ön / yükseklik / not (= nokta adı) alanlarını doldurur; kayıt mevcut
#: girişle. Dosya yok / bozuk → boş liste (form bugünküyle aynı). Geçersiz nokta (aralık dışı / sayı değil / adsız) ATLANIR.
HAZIR_DOSYA = ("kabin_kalibrasyonu", "sensor_noktalari.json")
HAZIR_AZAMI = 40


def hazir_noktalar(veri_koku) -> list[dict]:
    """→ [{"ad": {"tr", "en"}, "sol_cm", "on_cm", "yukseklik_cm"}] (dosyadaki sıra = ölçüm sırası, en çok `HAZIR_AZAMI`)."""
    import json
    import os

    try:
        with open(os.path.join(str(veri_koku), *HAZIR_DOSYA), encoding="utf-8") as f:
            veri = json.load(f)
    except (OSError, ValueError):
        return []
    cikti: list[dict] = []
    for n in (veri.get("noktalar") if isinstance(veri, dict) else None) or []:
        if not isinstance(n, dict):
            continue
        ad = n.get("ad")
        ad = {"tr": ad, "en": ad} if isinstance(ad, str) else ad
        tr = str((ad or {}).get("tr") or "").strip() if isinstance(ad, dict) else ""
        if not tr:
            continue
        try:
            alan = dogrula(
                SensorKonumuGovde(solCm=n.get("sol_cm"), onCm=n.get("on_cm"), yukseklikCm=n.get("yukseklik_cm"))
            )
        except ValueError:  # aralık dışı / sayı değil (pydantic ValidationError da ValueError)
            continue
        en = str(ad.get("en") or "").strip() or tr
        cikti.append(
            {
                "ad": {"tr": tr[:NOT_AZAMI], "en": en[:NOT_AZAMI]},
                "sol_cm": alan["sol_cm"],
                "on_cm": alan["on_cm"],
                "yukseklik_cm": alan["yukseklik_cm"],
            }
        )
        if len(cikti) >= HAZIR_AZAMI:
            break
    return cikti
