# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODAK önerisi (istem 45 A2–A4): kip girdisi + istenen DOZ → model (KNN) → işaretli duty + Y280 fazı → FİZİK DENETİMİ (karar vermez, denetler).

Fizik denetimi (zaman domeni, Y280 hizalı tepe |B|): beklenen doz hedefin EN ZAYIF noktasında; tavan (duty ≤ 0,5 köşe taraması, AYNI zaman
domeni tanımıyla); çevre ortalaması
ve oran (odak kiplerinde hedef / çevre, düzgünlük kiplerinde en zayıf / en güçlü); konum payı (hedef ±10 mm kayınca doz değişimi); petride 24 kuyunun
her birinde beklenen tepe |B| (onay ekranı haritası). SÜRME (engel kodu → i18n `ai.pro.odak.engel.<kod>`, eylem söyleyen metin):
  hedefKabinDisi · dozGecersiz · dozTavanUstu · dozSapmasi (|beklenen / istenen − 1| > %10) · modelEski (eğitim kalibrasyonu ≠ sürüşteki) ·
  modelYok (Y282: AI model katmanında ODAK dosyası yok) · plakaYok (24 kuyu ızgarası çıkarılamadı) · kuyuYok (seçili kuyu ızgarada yok) · kalibrasyonYok / kalibrasyonBozuk / kalibrasyonEski / eslemeDogrulanmadi (alan.KalibrasyonHatasi).
Girdiler BACKEND kabin çerçevesindedir (X sol, Y yukarı, Z arka; mm); çeviri `alan.backend_to_olcum`'da (tek yer).
"""
from __future__ import annotations

import functools
import json
import os

import numpy as np

from ai_hub.odak.alan import (
    DUTY_AZAMI,
    N_BOBIN,
    VERI_DIZINI,
    AlanModeli,
    backend_to_olcum,
    olcum_to_backend,
    tavan_td,
)
from ai_hub.odak.model import model_al, yerel_nokta

#: |beklenen / istenen − 1| bu sınırı aşarsa SÜRME (istem 45 A4).
DOZ_SAPMA_SINIRI = 0.10
#: Konum payı: hedef bu kadar kayınca doz ne kadar değişir (onay ekranında ±).
KONUM_PAYI_MM = 10.0
SATIRLAR = "ABCD"
DUZGUNLUK_KIPLERI = ("TUM_PETRI", "KEDI_TV")


@functools.lru_cache(maxsize=1)
def numune(yol: str = os.path.join(VERI_DIZINI, "numune.json")) -> dict:
    with open(yol, encoding="utf-8") as fh:
        return json.load(fh)


class Engel(Exception):
    def __init__(self, kod: str, **ek):
        super().__init__(kod)
        self.kod = kod
        self.ek = ek


def _dondur(u, v, th):
    c, s = np.cos(th), np.sin(th)
    return u * c - v * s, u * s + v * c


# ── kip girdileri (backend çerçevesi) → temel öznitelik (ölçüm çerçevesi) + hedef / çevre noktaları (backend) ─────────────────────
def petri_izgarasi(kuyular: list) -> dict:
    """[{etiket 'A1'..'D6', P [X, Y, Z] backend, px [u, v]}] → 24 kuyu (satır-sütun sıralı) + plaka merkezi / yönü / altlığı (ölçüm çerçevesi).
    Izgara tam değilse (ör. tekil kip W1…) Engel('plakaYok')."""
    N = numune()["plaka"]
    sat, sut = int(N["satir"]), int(N["sutun"])
    tablo = {}
    for k in kuyular or []:
        e = str(k.get("etiket") or "").strip().upper()
        if len(e) >= 2 and e[0] in SATIRLAR[:sat] and e[1:].isdigit() and 1 <= int(e[1:]) <= sut:
            P = np.asarray(k.get("P"), dtype=float)
            if P.shape == (3,) and np.all(np.isfinite(P)):
                tablo[(SATIRLAR.index(e[0]), int(e[1:]) - 1)] = {"etiket": e, "P": P, "px": k.get("px")}
    if len(tablo) != sat * sut:
        raise Engel("plakaYok", bulunan=len(tablo), beklenen=sat * sut)
    sira = [tablo[(r, c)] for r in range(sat) for c in range(sut)]
    Pm = backend_to_olcum(np.array([k["P"] for k in sira])).reshape(sat, sut, 3)
    merkez = Pm.reshape(-1, 3).mean(0)
    u = (Pm[:, -1, :] - Pm[:, 0, :]).mean(0)  # sütun artış yönü (ölçüm x, z)
    th = float(np.arctan2(u[2], u[0]))
    return {"sira": sira, "Pm": Pm.reshape(-1, 3), "merkez": merkez, "theta": th, "sat": sat, "sut": sut}


def _taban_y(A: AlanModeli) -> float:
    return float(A.taban_y)


def kip_girdisi(kip: str, A: AlanModeli, hedef_P=None, kuyular=None, hedef_etiket=None, fantom=None, kedi=None) -> dict:
    """→ {oz (temel öznitelik, ölçüm), T (hedef noktaları, backend, (nT, 3)), C (çevre, backend) | None, kuyu (24'lük sıra) | None, secili (indeks)}."""
    ty = _taban_y(A)
    N = numune()
    if kip in ("TUM_PETRI", "KUYUCUK"):
        g = petri_izgarasi(kuyular)
        altlik = float(np.mean(g["Pm"][:, 1]) - ty - float(N["plaka"]["sivi_orta_mm"]))
        oz = {"plaka_x": g["merkez"][0], "plaka_z": g["merkez"][2], "altlik": altlik,
              "sin2t": float(np.sin(2 * g["theta"])), "cos2t": float(np.cos(2 * g["theta"]))}
        Pb = np.array([k["P"] for k in g["sira"]])
        if kip == "TUM_PETRI":
            return {"oz": oz, "T": Pb, "C": None, "kuyu": g["sira"], "secili": None}
        etiketler = [k["etiket"] for k in g["sira"]]
        e = str(hedef_etiket or "").strip().upper()
        if e not in etiketler:
            raise Engel("kuyuYok", hedef=e)
        w = etiketler.index(e)
        oz.update({"hedef_x": g["Pm"][w, 0], "hedef_z": g["Pm"][w, 2]})
        C = np.delete(Pb, w, axis=0)
        return {"oz": oz, "T": Pb[w:w + 1], "C": C, "kuyu": g["sira"], "secili": w}
    if kip == "FANTOM":
        f = N["fantom"]
        T = np.asarray(hedef_P, dtype=float).reshape(1, 3)
        Tm = backend_to_olcum(T)[0]
        fan = fantom or {}
        merkez_m = backend_to_olcum(np.asarray(fan["merkez_P"], dtype=float)) if fan.get("merkez_P") is not None else Tm.copy()
        th = float(fan.get("theta", 0.0))
        W, Dp, Hf = (float(v) for v in f["boyut_mm"])
        U, V, Y = np.meshgrid(np.linspace(-W / 2 + 10, W / 2 - 10, 6), np.linspace(-Dp / 2 + 10, Dp / 2 - 10, 4),
                              np.array([10.0, 25.0, 40.0]) * Hf / 50.0, indexing="ij")
        gu, gv = _dondur(U.ravel(), V.ravel(), th)
        Cm = np.stack([merkez_m[0] + gu, ty + Y.ravel(), merkez_m[2] + gv], 1)
        Cm = Cm[np.linalg.norm(Cm - Tm[None], axis=1) > float(f["cevre_haric_yaricap_mm"])]
        oz = {"tumor_x": Tm[0], "tumor_z": Tm[2], "fantom_x": merkez_m[0], "fantom_z": merkez_m[2],
              "sin2t": float(np.sin(2 * th)), "cos2t": float(np.cos(2 * th))}
        return {"oz": oz, "T": T, "C": olcum_to_backend(Cm), "kuyu": None, "secili": None}
    if kip in ("KEDI_TV", "KEDI_ORGAN"):
        k = N["kedi"]
        yari = np.asarray(k["govde_yari_mm"], dtype=float)  # boy, yan, yükseklik
        go = np.asarray(k["govde_olcek"], dtype=float)
        L, Yy, H = np.meshgrid(np.linspace(-go[0], go[0], 7), np.linspace(-go[1], go[1], 3), np.linspace(-go[2], go[2], 3), indexing="ij")
        ic = (L ** 2 + Yy ** 2 + H ** 2) <= 1.0
        lyh = np.stack([L[ic] * yari[0], Yy[ic] * yari[1], H[ic] * yari[2] + yari[2]], 1)
        ked = kedi or {}
        T0 = np.asarray(hedef_P, dtype=float).reshape(1, 3)
        merkez_m = backend_to_olcum(np.asarray(ked.get("merkez_P", T0[0]), dtype=float))
        th = float(ked.get("theta", 0.0))
        dx, dz = _dondur(-lyh[:, 1], lyh[:, 0], th)
        Gm = np.stack([merkez_m[0] + dx, ty + lyh[:, 2], merkez_m[2] + dz], 1)
        if kip == "KEDI_TV":
            oz = {"kedi_x": merkez_m[0], "kedi_z": merkez_m[2], "sin2t": float(np.sin(2 * th)), "cos2t": float(np.cos(2 * th))}
            return {"oz": oz, "T": olcum_to_backend(Gm), "C": None, "kuyu": None, "secili": None}
        Tm = backend_to_olcum(T0)[0]
        Cm = Gm[np.linalg.norm(Gm - Tm[None], axis=1) > float(k["cevre_haric_yaricap_mm"])]
        oz = {"organ_x": Tm[0], "organ_y": Tm[1], "organ_z": Tm[2], "kedi_x": merkez_m[0], "kedi_z": merkez_m[2],
              "sin2t": float(np.sin(2 * th)), "cos2t": float(np.cos(2 * th))}
        return {"oz": oz, "T": T0, "C": olcum_to_backend(Cm), "kuyu": None, "secili": None}
    raise ValueError(kip)


# ── öneri ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _yuvarla(v, n=3):
    return None if v is None else round(float(v), n)


def oner(kip: str, A: AlanModeli, doz_mT: float, model=None, **girdi) -> dict:
    """Plan (JSON'lanabilir). Engel varsa `plan["engel"]` dolu ve duty / faz SIFIR (sürülmez)."""
    plan = {"kip": kip, "doz_mT": _yuvarla(doz_mT), "duty": [0.0] * N_BOBIN, "faz": [0.0] * N_BOBIN, "engel": None, "engel_ek": {},
            "kalibrasyon": A.kimlik, "model": "KNN k=1 + yerel alan"}
    try:
        g = kip_girdisi(kip, A, **girdi)
        T, C = g["T"], g["C"]
        if not np.all(A.cam_icinde(T)):
            raise Engel("hedefKabinDisi")
        MT = A.alan(T)
        plan["tavan_mT"] = _yuvarla(tavan_td(A, MT))
        if g["kuyu"] is not None:
            plan["kuyular"] = [{"etiket": k["etiket"], "px": k.get("px"), "mT": None, "secili": i == g["secili"]} for i, k in enumerate(g["kuyu"])]
        D = float(doz_mT)
        if not np.isfinite(D) or D <= 0:
            raise Engel("dozGecersiz")
        if D > plan["tavan_mT"] * (1 + 1e-6):
            raise Engel("dozTavanUstu", tavan=plan["tavan_mT"])
        try:
            m = model or model_al(kip)
        except FileNotFoundError:
            raise Engel("modelYok") from None
        if m.kalibrasyon_kimligi != A.kimlik:
            raise Engel("modelEski")
        Py = yerel_nokta(kip, g["oz"], A.taban_y)
        X = m.ozellik(g["oz"], A.alan_olcum(Py[None])[0], D)
        a = np.clip(m.tahmin(X)[0] * D, -1.0, 1.0)
        sd = A.isaretli_duty(a)
        faz = A.fazlar(sd)
        # FİZİK (karar vermez): zaman domeni, Y280 hizalı
        BT = A.td_tepe(MT, sd)
        beklenen = float(BT.min())
        plan["beklenen_mT"] = _yuvarla(beklenen)
        plan["dogrusal_mT"] = _yuvarla(float(A.dogrusal_tepe(MT, a).min()))
        if C is not None and len(C):
            BC = A.td_tepe(A.alan(C), sd)
            plan["cevre_mT"] = _yuvarla(float(BC.mean()))
            plan["oran"] = _yuvarla(float(BT.max()) / max(float(BC.mean()), 1e-9), 2)
        else:
            plan["cevre_mT"] = None
            plan["oran"] = _yuvarla(beklenen / max(float(BT.max()), 1e-9), 2)  # düzgünlük: en zayıf / en güçlü
        if g["kuyu"] is not None:
            BK = A.td_tepe(A.alan(np.array([k["P"] for k in g["kuyu"]])), sd)
            for k, v in zip(plan["kuyular"], BK):
                k["mT"] = _yuvarla(v)
        # konum payı: hedef kümesi ±10 mm (6 yön) kayınca en zayıf noktanın değişimi
        sap = []
        for e in np.vstack([np.eye(3), -np.eye(3)]) * KONUM_PAYI_MM:
            sap.append(float(A.td_tepe(A.alan(T + e[None]), sd).min()) / max(beklenen, 1e-9) - 1.0)
        plan["pay_yuzde"] = _yuvarla(100.0 * max(abs(v) for v in sap), 1)
        plan["sapma_yuzde"] = _yuvarla(100.0 * (beklenen / D - 1.0), 1)
        if abs(beklenen / D - 1.0) > DOZ_SAPMA_SINIRI:
            raise Engel("dozSapmasi", beklenen=plan["beklenen_mT"], istenen=plan["doz_mT"])
        plan["duty"] = [round(float(v), 4) for v in np.abs(sd)]
        plan["faz"] = [round(float(v), 2) for v in faz]
    except Engel as e:
        plan["engel"], plan["engel_ek"] = e.kod, e.ek
        plan["duty"], plan["faz"] = [0.0] * N_BOBIN, [0.0] * N_BOBIN
    assert max(plan["duty"]) <= DUTY_AZAMI + 1e-9
    return plan


def hedef_tavani(kip: str, A: AlanModeli, **girdi) -> dict:
    """Doz seçicinin üst sınırı: konumda duty ≤ 0,5 ile verilebilen en büyük doz (model ÇAĞRILMAZ). Engel → {"engel": kod}."""
    try:
        g = kip_girdisi(kip, A, **girdi)
        if not np.all(A.cam_icinde(g["T"])):
            raise Engel("hedefKabinDisi")
        return {"tavan_mT": _yuvarla(tavan_td(A, A.alan(g["T"]))), "engel": None, "engel_ek": {}}
    except Engel as e:
        return {"tavan_mT": None, "engel": e.kod, "engel_ek": e.ek}


def alan_modeli(veri_koku) -> AlanModeli:
    """Veri kökündeki kalibrasyonla alan modeli. Kalibrasyon yok / bozuk / eski / eşleme doğrulanmamış → KalibrasyonHatasi (çağıran SÜRMEZ)."""
    from ai_hub.odak.alan import kalibrasyon_oku

    return _alan_modeli_onbellek(kalibrasyon_oku(veri_koku))


_SON: dict = {}


def _alan_modeli_onbellek(K: dict) -> AlanModeli:
    """Aynı kalibrasyon içeriği için modeli yeniden kurmaz (RL dalga tablosu ~0,2 sn)."""
    from ai_hub.odak.alan import kalibrasyon_kimligi

    kim = kalibrasyon_kimligi(K)
    if _SON.get("kimlik") != kim:
        _SON["model"], _SON["kimlik"] = AlanModeli(K), kim
    return _SON["model"]
