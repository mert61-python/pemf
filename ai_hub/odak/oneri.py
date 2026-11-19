# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODAK önerisi (istem 45 A2–A4): kip girdisi + istenen DOZ → model (KNN) → işaretli duty + Y280 fazı → FİZİK DENETİMİ (karar vermez, denetler).

Fizik denetimi (zaman domeni, Y280 hizalı tepe |B|): beklenen doz hedefin EN ZAYIF noktasında; tavan (duty ≤ 0,5 köşe taraması, AYNI zaman
domeni tanımıyla); çevre ortalaması
ve oran (odak kiplerinde hedef / çevre, düzgünlük kiplerinde en zayıf / en güçlü); konum payı (hedef ±10 mm kayınca doz değişimi); petride 24 kuyunun
her birinde beklenen tepe |B| (onay ekranı haritası). SÜRME (engel kodu → i18n `ai.pro.odak.engel.<kod>`, eylem söyleyen metin):
  hedefKabinDisi · dozGecersiz · dozTavanUstu · dozSapmasi (|beklenen / istenen − 1| > %10) · modelEski (eğitim kalibrasyonu ≠ sürüşteki) ·
  modelYok (Y282: AI model katmanında ODAK dosyası yok) · plakaYok (ODK11: plaka yeri / yönü için < 3 kuyu ya da hepsi tek satır / sütunda) ·
  plakaUyumsuz (görülen kuyular 24'lük düzene oturmadı ya da iki yönlü belirsiz) · kuyuYok (seçili kuyu ızgarada yok ya da BOŞ) · kalibrasyonYok / kalibrasyonBozuk / kalibrasyonEski / eslemeDogrulanmadi (alan.KalibrasyonHatasi).
Girdiler BACKEND kabin çerçevesindedir (X sol, Y yukarı, Z arka; mm); çeviri `alan.backend_to_olcum`'da (tek yer).
"""
from __future__ import annotations

import functools
import logging
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
#: OTB T-3 (ODM tezgâhı 19-11: B5 1,44 istendi → beklenen 1,63, %15 → engel): tavanın altındaki dozda beklenen istenenden
#: DOZ_SAPMA_SINIRI'ndan çok saparsa öneri FİZİK DÜZELTME adımı uygular — genlik × istenen / beklenen (bobin genlik azamisine, yani duty
#: ≤ 0,5'e kırpılır) — ve zaman domeninde YENİDEN denetler; en çok bu kadar adım, düzelmezse engel AYNEN.
DUZELTME_ADIMI = 3
#: Konum payı: hedef bu kadar kayınca doz ne kadar değişir (onay ekranında ±).
KONUM_PAYI_MM = 10.0
SATIRLAR = "ABCD"
#: ODK11 (sahip 13 Kasım 2026: "kaç tane bulursa ona göre başlamalı, 24 şartını kaldır"): plaka yeri + yönü GÖRÜLEN (sıvılı) kuyulardan
#: oturtulur, boş kuyuların yeri hesaplanır. Geometrinin gerektirdiği alt sınır: ≥ 3 kuyu, en az iki satır VE iki sütunda (tek çizgide
#: yön / ayna belirsiz). Oturtma sapması (RMS) sınırı: ızgara kameranın tek dönüşümünden geldiği için görülen kuyular birkaç mm içinde
#: düzene oturur; aşarsa plaka / kalibrasyon şüpheli → SÜRÜLMEZ.
IZGARA_EN_AZ = 3
IZGARA_SAPMA_SINIRI_MM = 5.0
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
def _kati_oturt(L: np.ndarray, Q: np.ndarray) -> list:
    """Kafes düzlemi L (n, 2) → ölçüm düzlemi Q (n, 2) katı dönüşüm (ölçek 1): HER İKİ el yönü (dönme / ayna) için (R, t, rms)."""
    Lo, Qo = L.mean(0), Q.mean(0)
    U, _S, Vt = np.linalg.svd((L - Lo).T @ (Q - Qo))
    det = float(np.sign(np.linalg.det(Vt.T @ U.T))) or 1.0
    out = []
    for el in (1.0, -1.0):
        R = Vt.T @ np.diag([1.0, el * det]) @ U.T
        t = Qo - R @ Lo
        out.append((R, t, float(np.sqrt(np.mean(np.sum((L @ R.T + t - Q) ** 2, axis=1))))))
    return out


def _px_tamamla(tablo: dict, hucreler: list) -> dict:
    """Boş kuyuların kamera piksel konumu: görülen kuyuların (sütun, satır) → px doğrusal (afin) oturtması (harita yönü korunur)."""
    dolu = [(rc, v["px"]) for rc, v in tablo.items() if isinstance(v.get("px"), (list, tuple)) and len(v["px"]) >= 2]
    try:
        A = np.array([[c, r, 1.0] for (r, c), _ in dolu])
        B = np.array([[float(p[0]), float(p[1])] for _, p in dolu])
        if len(dolu) < 3 or np.linalg.matrix_rank(A) < 3 or not np.all(np.isfinite(B)):
            return {}
        X = np.linalg.lstsq(A, B, rcond=None)[0]
    except (TypeError, ValueError):
        return {}
    return {(r, c): [round(float(v), 1) for v in np.array([c, r, 1.0]) @ X] for (r, c) in hucreler}


def petri_izgarasi(kuyular: list) -> dict:
    """[{etiket 'A1'..'D6', P [X, Y, Z] backend, px [u, v]}] → 24 kuyu (satır-sütun sıralı) + plaka merkezi / yönü / altlığı (ölçüm çerçevesi).
    ODK11: kuyuların bir kısmı görülmediyse (boş — sıvı yok) plaka GÖRÜLENLERDEN katı oturtulur (kuyu aralığı numuneden), boşların yeri
    hesaplanır (`bos: True`, px görülenlerden). < 3 kuyu ya da hepsi tek satır / sütunda → Engel('plakaYok'); sapma > sınır ya da iki el
    yönü de oturuyorsa (ayna belirsiz) → Engel('plakaUyumsuz'). 24'ün hepsi görüldüyse ölçülen konumlar AYNEN (oturtma yok)."""
    N = numune()["plaka"]
    sat, sut = int(N["satir"]), int(N["sutun"])
    tablo = {}
    for k in kuyular or []:
        e = str(k.get("etiket") or "").strip().upper()
        if len(e) >= 2 and e[0] in SATIRLAR[:sat] and e[1:].isdigit() and 1 <= int(e[1:]) <= sut:
            P = np.asarray(k.get("P"), dtype=float)
            if P.shape == (3,) and np.all(np.isfinite(P)):
                tablo[(SATIRLAR.index(e[0]), int(e[1:]) - 1)] = {"etiket": e, "P": P, "px": k.get("px"), "bos": False}
    bulunan = len(tablo)
    if bulunan < sat * sut:
        if bulunan < IZGARA_EN_AZ or len({r for r, _ in tablo}) < 2 or len({c for _, c in tablo}) < 2:
            raise Engel("plakaYok", bulunan=bulunan, beklenen=IZGARA_EN_AZ)
        a = float(N["aralik_mm"])
        rc = list(tablo)
        L = np.array([[(c - (sut - 1) / 2.0) * a, (r - (sat - 1) / 2.0) * a] for r, c in rc])
        Pm_g = backend_to_olcum(np.array([tablo[k]["P"] for k in rc]))
        cozum = sorted(_kati_oturt(L, Pm_g[:, [0, 2]]), key=lambda x: x[2])
        R, t, rms = cozum[0]
        if rms > IZGARA_SAPMA_SINIRI_MM or cozum[1][2] <= IZGARA_SAPMA_SINIRI_MM:
            raise Engel("plakaUyumsuz", bulunan=bulunan, sapma=round(rms, 1))
        y = float(np.mean(Pm_g[:, 1]))
        eksik = [(r, c) for r in range(sat) for c in range(sut) if (r, c) not in tablo]
        pxler = _px_tamamla(tablo, eksik)
        for r, c in eksik:
            u, v = R @ np.array([(c - (sut - 1) / 2.0) * a, (r - (sat - 1) / 2.0) * a]) + t
            tablo[(r, c)] = {"etiket": f"{SATIRLAR[r]}{c + 1}", "P": olcum_to_backend(np.array([u, y, v])), "px": pxler.get((r, c)),
                             "bos": True}
    sira = [tablo[(r, c)] for r in range(sat) for c in range(sut)]
    Pm = backend_to_olcum(np.array([k["P"] for k in sira])).reshape(sat, sut, 3)
    merkez = Pm.reshape(-1, 3).mean(0)
    u = (Pm[:, -1, :] - Pm[:, 0, :]).mean(0)  # sütun artış yönü (ölçüm x, z)
    th = float(np.arctan2(u[2], u[0]))
    return {"sira": sira, "Pm": Pm.reshape(-1, 3), "merkez": merkez, "theta": th, "sat": sat, "sut": sut, "bulunan": bulunan}


#: OTB T-8 (sahip 19-11): seans içi SABİT NUMUNE — ızgarası DOĞRULANAN karenin kuyuları seansın ilk doğrulanan ızgarasıyla (aynı etiket)
#: ortanca bu kadar (mm, ölçüm düzlemi x-z) içindeyse plaka yerinde sayılır. ÖLÇÜLDÜ (19-11 gerçek kayıt, plaka OYNAMADAN 132 kare): ızgara
#: varsayımları kareden kareye kaydığı için ortanca sapma p90 4,6–6,5, en çok 9,8 mm; 6 mm eşik 14 / 132 karede yanlış "kaydı" diyordu,
#: 10 mm'de 0. ~1 cm kayma (20 / 20 kare) ve bir kuyu kayma 10 mm ile de yakalanıyor (Y300 STOP aynı anda) — daha küçük kayma ızgara
#: gürültüsünden ayırt EDİLEMEZ. Bir kuyu aralığı 19,3 mm.
SABIT_NUMUNE_ESIGI_MM = 10.0
#: OTB T-8: ızgarası DOĞRULANMAYAN karede (etiketler güvenilmez — ör. sıkışmış ızgara, sapma 7–11 mm ölçüldü) kaba eşik: kuyular plakanın
#: yerinde mi (en yakın referans kuyusu). Kesin kayma tespiti doğrulanan karelerde (etiketle).
SABIT_NUMUNE_KABA_ESIK_MM = 10.0


def sabit_numune_ortusmesi(referans: list, kuyular: list, *, etiketli: bool, esik_mm: float | None = None) -> dict:
    """OTB T-8: karede görülen kuyular (`kuyular`, ODAK aday biçimi) seansın referans ızgarasıyla (`referans` — ilk doğrulanan karenin
    adayları; boş kuyular `petri_izgarasi` ile tamamlanır) örtüşüyor mu.
    · `etiketli` (karenin ızgarası DOĞRULANDI): her kuyu AYNI etiketli referans kuyusuyla — ortanca sapma ≤ eşik (bir kuyu aralığı kayma
      dahil plaka kayması yakalanır);
    · değilse (ızgara oturmadı → etiketler güvenilmez): her kuyu EN YAKIN referans kuyusuyla — en az `IZGARA_EN_AZ` ve görülenlerin yarısı
      KABA eşik (`SABIT_NUMUNE_KABA_ESIK_MM`) içinde.
    → {"ortusuyor", "gorulen", "eslesen", "sapma_mm" (ortanca; görülen yoksa None)}. Referans oturtulamazsa örtüşmez (fail-closed)."""
    if esik_mm is None:
        esik_mm = SABIT_NUMUNE_ESIGI_MM if etiketli else SABIT_NUMUNE_KABA_ESIK_MM
    try:
        sira = petri_izgarasi(referans)["sira"]
    except Engel:
        return {"ortusuyor": False, "gorulen": 0, "eslesen": 0, "sapma_mm": None}
    R = {k["etiket"]: backend_to_olcum(np.asarray(k["P"], dtype=float))[[0, 2]] for k in sira}
    Rm = np.array(list(R.values()))
    gorulen = []
    for k in kuyular or []:
        P = np.asarray(k.get("P"), dtype=float)
        if P.shape == (3,) and np.all(np.isfinite(P)):
            gorulen.append((str(k.get("etiket") or "").strip().upper(), backend_to_olcum(P)[[0, 2]]))
    if etiketli:
        d = np.array([float(np.linalg.norm(q - R[e])) for e, q in gorulen if e in R])
    else:
        d = np.array([float(np.linalg.norm(Rm - q, axis=1).min()) for _e, q in gorulen])
    eslesen = int((d <= esik_mm).sum()) if d.size else 0
    sapma = round(float(np.median(d)), 1) if d.size else None
    if etiketli:
        ortusuyor = d.size >= IZGARA_EN_AZ and sapma is not None and sapma <= esik_mm
    else:
        ortusuyor = eslesen >= IZGARA_EN_AZ and eslesen >= 0.5 * len(gorulen)
    return {"ortusuyor": bool(ortusuyor), "gorulen": len(gorulen), "eslesen": eslesen, "sapma_mm": sapma}


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
        if e not in etiketler or g["sira"][etiketler.index(e)].get("bos"):
            raise Engel("kuyuYok", hedef=e)  # ODK11: boş (görülmeyen) kuyu hedef OLAMAZ
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


def ulasilabilir_tavan(A: AlanModeli, MT, a) -> float:
    """OTB T-2: modelin YÖNÜYLE (`a`, işaretli genlik) duty ≤ 0,5'te verilebilen en büyük doz (zaman domeni, hedef kümesinin en zayıf
    noktası): genlik, en çok sınırlayan bobin azamisine değene dek ölçeklenir. Yön yoksa 0."""
    a = np.asarray(a, dtype=float)
    dolu = np.abs(a) > 1e-12
    if not dolu.any():
        return 0.0
    k = float(np.min(A.a_azami[dolu] / np.abs(a[dolu])))
    return float(A.td_tepe(MT, A.isaretli_duty(a * k)).min())


def _model_ve_tavan(kip: str, A: AlanModeli, g: dict, MT, model=None) -> tuple:
    """(model, Py, fizik tavanı, ULAŞILABİLİR tavan = min(fizik, model yönüyle)) — OTB T-2: "en çok" MODELİN verebildiği. Model yok /
    eski → Engel (çağıran sürmez)."""
    try:
        m = model or model_al(kip, f_hz=A.f_hz)
    except FileNotFoundError:
        raise Engel("modelYok") from None
    if m.kalibrasyon_kimligi != A.kimlik:
        raise Engel("modelEski")
    fizik = tavan_td(A, MT)
    Py = yerel_nokta(kip, g["oz"], A.taban_y)
    at = np.clip(m.tahmin(m.ozellik(g["oz"], A.alan_olcum(Py[None])[0], fizik))[0] * fizik, -A.a_azami, A.a_azami)
    return m, Py, fizik, min(fizik, ulasilabilir_tavan(A, MT, at))


def oner(kip: str, A: AlanModeli, doz_mT, model=None, varsayilan_kesir: float = 0.8, **girdi) -> dict:
    """Plan (JSON'lanabilir). Engel varsa `plan["engel"]` dolu ve duty / faz SIFIR (sürülmez). `doz_mT` None → ulaşılabilir tavanın
    `varsayilan_kesir`i (başlangıç önerisi, Y273)."""
    plan = {"kip": kip, "doz_mT": None if doz_mT is None else _yuvarla(doz_mT), "duty": [0.0] * N_BOBIN, "faz": [0.0] * N_BOBIN,
            "engel": None, "engel_ek": {}, "kalibrasyon": A.kimlik, "model": "KNN k=1 + yerel alan", "frek_hz": A.f_hz}
    try:
        g = kip_girdisi(kip, A, **girdi)
        T, C = g["T"], g["C"]
        if not np.all(A.cam_icinde(T)):
            raise Engel("hedefKabinDisi")
        MT = A.alan(T)
        if g["kuyu"] is not None:
            plan["kuyular"] = [
                {"etiket": k["etiket"], "px": k.get("px"), "mT": None, "secili": i == g["secili"], "bos": bool(k.get("bos"))}
                for i, k in enumerate(g["kuyu"])
            ]
        m, Py, fizik, ulasilabilir = _model_ve_tavan(kip, A, g, MT, model)
        # OTB T-2: "en çok" = modelin ulaşabildiği (fizik tavanıyla sınırlı); fizik tavanı ayrıca söylenir.
        plan["fizik_tavan_mT"] = _yuvarla(fizik)
        plan["tavan_mT"] = _yuvarla(ulasilabilir)
        if doz_mT is None:
            plan["doz_mT"] = max(0.01, round(varsayilan_kesir * float(plan["tavan_mT"]), 2))
        D = float(plan["doz_mT"])
        if not np.isfinite(D) or D <= 0:
            raise Engel("dozGecersiz")
        if D > plan["tavan_mT"] * (1 + 1e-6):
            raise Engel("dozTavanUstu", tavan=plan["tavan_mT"])
        X = m.ozellik(g["oz"], A.alan_olcum(Py[None])[0], D)
        a = np.clip(m.tahmin(X)[0] * D, -A.a_azami, A.a_azami)
        sd = A.isaretli_duty(a)
        # FİZİK (karar vermez): zaman domeni, Y280 hizalı
        BT = A.td_tepe(MT, sd)
        beklenen = float(BT.min())
        # OTB T-3: sapma sınırı aşılırsa FİZİK DÜZELTME adımı (genlik × istenen / beklenen, duty ≤ 0,5) + yeniden denetim
        ilk_beklenen = beklenen
        for _ in range(DUZELTME_ADIMI):
            if beklenen <= 0 or abs(beklenen / D - 1.0) <= DOZ_SAPMA_SINIRI:
                break
            a = np.clip(a * (D / beklenen), -A.a_azami, A.a_azami)
            sd = A.isaretli_duty(a)
            BT = A.td_tepe(MT, sd)
            beklenen = float(BT.min())
        if beklenen != ilk_beklenen:
            plan["duzeltme"] = {"ilk_beklenen_mT": _yuvarla(ilk_beklenen), "kat": _yuvarla(beklenen / max(ilk_beklenen, 1e-9), 3)}
        faz = A.fazlar(sd)
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
        plan["e_hedef_Vm"], plan["e_cevre_Vm"], plan["e_ortam"] = _e_degerleri(A, T, C, sd, kip)
        plan["duty"] = [round(float(v), 4) for v in np.abs(sd)]
        plan["faz"] = [round(float(v), 2) for v in faz]
    except Engel as e:
        plan["engel"], plan["engel_ek"] = e.kod, e.ek
        plan["duty"], plan["faz"] = [0.0] * N_BOBIN, [0.0] * N_BOBIN
    assert max(plan["duty"]) <= DUTY_AZAMI + 1e-9
    return plan


#: ODK10: E'si kuyu SIVISI içinde hesaplanan kipler (ortam "kuyu"); diğerleri havada (ortamsız) CST E (ortam "hava").
KUYU_E_KIPLERI = ("TUM_PETRI", "KUYUCUK")


def _e_degerleri(A: AlanModeli, T, C, sd, kip: str = "") -> tuple:
    """Canlı E çubuğu / onay için E (tepe |E|, V/m): hedef ortalaması · çevre ortalaması (çevre yoksa None) · ortam.
    ODK10 petri (`KUYU_E_KIPLERI`): kuyu SIVISI içinde (`kuyu_e`, CST petri benzetimiyle doğrulandı; T / C = kuyu merkezleri) — havadaki
    E'ye ASLA düşmez (kuyuda ~190 kat yüksek gösterirdi). Diğer kipler (ODK6): havada CST E tablosu. YALNIZ GÖSTERİM: hesaplanamazsa
    (None, None, ortam), plan SÜRÜLÜR (doz denetimi B ile)."""
    ortam = "kuyu" if kip in KUYU_E_KIPLERI else "hava"
    try:
        if ortam == "kuyu":
            from ai_hub.odak.kuyu_e import kuyu_e_tepe

            H = 2.0 * float(numune()["plaka"]["sivi_orta_mm"])
            e_h = float(kuyu_e_tepe(A, T, sd, H).mean())
            e_c = float(kuyu_e_tepe(A, C, sd, H).mean()) if C is not None and len(C) else None
        else:
            e_h = float(A.td_e_tepe(A.e_alan(T), sd).mean())
            e_c = float(A.td_e_tepe(A.e_alan(C), sd).mean()) if C is not None and len(C) else None
    except Exception:
        logging.getLogger(__name__).warning("ODAK: E hesaplanamadı (%s; yalnız gösterim eksik, sürüş etkilenmez)", ortam, exc_info=True)
        return None, None, ortam
    return _yuvarla(e_h, 6), (None if e_c is None else _yuvarla(e_c, 6)), ortam


def petri_tavanlari(A: AlanModeli, kuyular: list, model_al_=None) -> dict:
    """OTB T-1: onay penceresinin "Doz (en çok X)"i SEÇİLİ kip / kuyuya göre — {"TUM_PETRI": mT, "KUYUCUK": {etiket: mT}}, her biri modelin
    ulaşabildiği (fizik tavanıyla sınırlı, `_model_ve_tavan`). Boş (görülmeyen) kuyu hedef olamaz → yok; hesaplanamayan hedef yok (pencere
    o seçimde sayı göstermez)."""
    al = model_al_ or model_al
    out: dict = {"KUYUCUK": {}}
    try:
        g = kip_girdisi("TUM_PETRI", A, kuyular=kuyular)
        out["TUM_PETRI"] = _yuvarla(_model_ve_tavan("TUM_PETRI", A, g, A.alan(g["T"]), al("TUM_PETRI", f_hz=A.f_hz))[3])
        sira = g["kuyu"]
    except (Engel, FileNotFoundError):
        try:
            sira = petri_izgarasi(kuyular)["sira"]
        except Engel:
            return out
    try:
        mk = al("KUYUCUK", f_hz=A.f_hz)
    except FileNotFoundError:
        return out
    for k in sira:  # boş (görülmeyen) kuyu hedef olamaz: `kip_girdisi` Engel("kuyuYok") verir → listede yok (ODK11)
        try:
            gk = kip_girdisi("KUYUCUK", A, kuyular=kuyular, hedef_etiket=k["etiket"])
            out["KUYUCUK"][k["etiket"]] = _yuvarla(_model_ve_tavan("KUYUCUK", A, gk, A.alan(gk["T"]), mk)[3])
        except Engel:
            continue
    return out


def hedef_tavani(kip: str, A: AlanModeli, **girdi) -> dict:
    """Doz seçicinin üst sınırı: konumda duty ≤ 0,5 ile verilebilen en büyük doz (model ÇAĞRILMAZ). Engel → {"engel": kod}."""
    try:
        g = kip_girdisi(kip, A, **girdi)
        if not np.all(A.cam_icinde(g["T"])):
            raise Engel("hedefKabinDisi")
        return {"tavan_mT": _yuvarla(tavan_td(A, A.alan(g["T"]))), "engel": None, "engel_ek": {}}
    except Engel as e:
        return {"tavan_mT": None, "engel": e.kod, "engel_ek": e.ek}


def alan_modeli(veri_koku, f_hz: float | None = None) -> AlanModeli:
    """Veri kökündeki kalibrasyonla alan modeli. Kalibrasyon yok / bozuk / eski / eşleme doğrulanmamış → KalibrasyonHatasi (çağıran SÜRMEZ)."""
    from ai_hub.odak.alan import kalibrasyon_oku

    return _alan_modeli_onbellek(kalibrasyon_oku(veri_koku), f_hz)


_SON: dict = {}


def _alan_modeli_onbellek(K: dict, f_hz: float | None = None) -> AlanModeli:
    """Aynı kalibrasyon içeriği için modeli yeniden kurmaz (RL dalga tablosu ~0,2 sn)."""
    from ai_hub.odak.alan import kalibrasyon_kimligi

    kim = (kalibrasyon_kimligi(K), float(f_hz) if f_hz else None)
    if kim not in _SON:
        if len(_SON) >= 8:
            _SON.clear()
        _SON[kim] = AlanModeli(K, f_hz=f_hz)
    return _SON[kim]
