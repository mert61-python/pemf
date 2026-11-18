# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A2 — CANLI 3B ALAN HESAPÇISI: AYRI SÜREÇTE (`PEMF_Backend.exe --alt-surec canli-alan`, `servers.alt_surec`) koşar;
ana sunucu (`servers.canli_alan`) her saniye çalışan bobinleri yollar, bu süreç haritayı döndürür.

FİZİK TEK KAYNAK (PLAN §6.1): ürünün kalibre alan modeli `ai_hub.odak.alan.AlanModeli` — veri kökündeki kalibrasyon (`kabin_kalibrasyonu/
alan_kalibrasyonu.json`, HER istekte okunur: ODK-B'de değişirse görünüm yenisini kullanır, kod değişmez) + AI model katmanındaki birim
alan tablosu (Y282). YALNIZ GÖSTERİM — hiçbir sürüş kararı bundan alınmaz.

IZGARA: cam içi, 20 mm, merkezli (kabin çerçevesi — backend: orijin cam içi merkez, +X önden bakanın SOLU, +Y yukarı, +Z arkaya); en alt
katman taban camının 5 mm üstü (plaka sıvı ortası, `numune.json` `sivi_orta_mm`). Birim alan + Gram matrisi kalibrasyon başına BİR kez;
her güncellemede yalnız dalga (duty → genlik, faz, frekansa göre RL biçimi) × Gram (`alan.gram_tepe`). Farklı frekanslar: ortak pencere
(`alan.ortak_dalga`, ölçüm GA.md). Tablo dışı nokta = YOK (255). Bobinler + kalibrasyon DEĞİŞMEDİYSE son sonuç (hesap yok).

İSTEK: `{"bobinler": [[bobin, frekans_hz, duty_oran, faz_derece], …]}` (boş değil — `sifir` ana sunucuda). YANIT (`alan_haritasi` verisi,
sürüm 1): durum · zaman · kalibrasyon kimliği · modelTahmini (her zaman True) · ızgara (kök / adım / boyut / çerçeve) · değer (8 bit,
base64, C sırası x-y-z, 255 = tablo dışı) × ölçek; ızgarada cam iç ölçüsü `camIc` (mm) (mT / kademe) · en yüksek değer + yeri · bobinler · uyarılar · hesapMs. Kalibrasyon /
tablo yoksa durum kodu (`ai_hub.odak.alan.KalibrasyonHatasi` kodları, `modelYok`, `modelBozuk`) — ÇÖKME YOK.
"""

from __future__ import annotations

import base64
import sys
import time

import numpy as np

SURUM = 1
ADIM_MM = 20.0
#: 8 bit kodlama: 0..254 = değer / ölçek, 255 = tablo dışı (gösterilmez).
KADEME = 254
YOK = 255
N_BOBIN = 7
#: Ölçülen duty → genlik eğrisi 0..0,5 (`alan.DUTY_AZAMI`); üstü modelde 0,5 sayılır → uyarı.
DUTY_MODEL_AZAMI = 0.5


def durum(kod: str, **ek) -> dict:
    return {"surum": SURUM, "durum": kod, "zaman": time.time(), "modelTahmini": True, **ek}


def izgara(cam_mm) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cam içi ölçüleri (3,) mm → (kök (3,), boyut (3,), noktalar (N, 3)) — merkezli, `ADIM_MM` aralıklı, hepsi cam İÇİNDE."""
    cam = np.asarray(cam_mm, dtype=float)
    boyut = (np.floor(cam / ADIM_MM + 1e-9) + 1).astype(int)
    kok = -(boyut - 1) / 2.0 * ADIM_MM
    eks = [kok[i] + np.arange(boyut[i]) * ADIM_MM for i in range(3)]
    P = np.stack(np.meshgrid(*eks, indexing="ij"), axis=-1).reshape(-1, 3)
    return kok, boyut, P


def tablo_icinde(A, P) -> np.ndarray:
    """Noktalar (backend) CST birim alan tablosunun İÇİNDE mi — dışındakiler ara değerlemede kenara kırpılır → gösterilmez."""
    from ai_hub.odak.alan import backend_to_olcum

    Pc = A.olcum_to_cst(backend_to_olcum(P))
    alt = np.asarray(A.tablo["kok"], dtype=float)
    ust = alt + (np.asarray(A.tablo["boyut"]) - 1) * float(A.tablo["adim"])
    return np.all((Pc >= alt - 1e-6) & (Pc <= ust + 1e-6), axis=-1)


def kodla(tepe: np.ndarray, ic: np.ndarray) -> tuple[str, float]:
    """Tam ızgara tepe |B| (N,) mT + tablo içi maskesi → (base64 8 bit, ölçek mT / kademe). Tablo dışı = `YOK`."""
    kod = np.full(len(ic), YOK, dtype=np.uint8)
    enb = float(tepe[ic].max()) if ic.any() else 0.0
    olcek = enb / KADEME if enb > 0 else 0.0
    kod[ic] = np.clip(np.rint(tepe[ic] / olcek), 0, KADEME).astype(np.uint8) if olcek > 0 else 0
    return base64.b64encode(kod.tobytes()).decode("ascii"), olcek


def varsayilan_model(f_hz: float):
    """Veri kökündeki kalibrasyonla frekans başına alan modeli (ODAK ile AYNI önbellek: `oneri.alan_modeli`)."""
    from utils.path_utils import get_app_data_directory

    from ai_hub.odak import oneri as odak_oneri

    return odak_oneri.alan_modeli(get_app_data_directory(), f_hz)


class Hesapci:
    """İstek → harita. `model_saglayici(f_hz)` → `AlanModeli` (kalibrasyon / tablo hataları fırlatır)."""

    def __init__(self, model_saglayici=None):
        self._model = model_saglayici or varsayilan_model
        self._izgara: dict | None = None
        self._son_anahtar = None
        self._son: dict | None = None

    def isle(self, istek: dict) -> dict:
        from utils.model_downloader import ModelButunlukHatasi

        from ai_hub.odak.alan import KalibrasyonHatasi

        bobinler = [(int(b), float(f), float(d), float(p)) for b, f, d, p in istek["bobinler"]]
        frekanslar = sorted({f for _, f, _, _ in bobinler})
        try:
            modeller = {f: self._model(f) for f in frekanslar}
        except KalibrasyonHatasi as e:
            return durum(e.kod)
        except FileNotFoundError:
            return durum("modelYok")
        except ModelButunlukHatasi:
            return durum("modelBozuk")
        kimlik = str(modeller[frekanslar[0]].kimlik).split("@", 1)[0]
        anahtar = (kimlik, tuple(bobinler))
        if anahtar != self._son_anahtar or self._son is None:
            self._son = self._hesapla(kimlik, bobinler, modeller)
            self._son_anahtar = anahtar
        return self._son

    def _izgara_al(self, kimlik: str, A) -> dict:
        if self._izgara is None or self._izgara["kimlik"] != kimlik:
            from ai_hub.odak.alan import gram

            kok, boyut, P = izgara(A.cam)
            ic = tablo_icinde(A, P)
            self._izgara = {
                "kimlik": kimlik,
                "kok": kok,
                "boyut": boyut,
                "cam": np.asarray(A.cam, dtype=float),
                "P": P,
                "ic": ic,
                "G": gram(A.alan(P[ic])),
            }
        return self._izgara

    def _hesapla(self, kimlik: str, bobinler, modeller) -> dict:
        from ai_hub.odak.alan import FREKANSLAR, gram_tepe, ortak_dalga

        t0 = time.perf_counter()
        Z = self._izgara_al(kimlik, modeller[min(modeller)])
        parcalar = []
        for f, A in sorted(modeller.items()):
            duty, faz = np.zeros(N_BOBIN), np.zeros(N_BOBIN)
            for b, fb, d, p in bobinler:
                if fb == f:
                    duty[b - 1], faz[b - 1] = d, p
            parcalar.append((f, A.td_dalga_faz(duty, faz)))
        tepe = np.zeros(len(Z["P"]))
        tepe[Z["ic"]] = gram_tepe(Z["G"], ortak_dalga(parcalar))
        deger, olcek = kodla(tepe, Z["ic"])
        uyari = []
        if any(d > DUTY_MODEL_AZAMI for _, _, d, _ in bobinler):
            uyari.append("dutyKirpildi")
        if any(not (min(FREKANSLAR) <= f <= max(FREKANSLAR)) for f in modeller):
            uyari.append("frekansKalibrasyonDisi")
        en = None
        if Z["ic"].any():
            i = int(np.argmax(np.where(Z["ic"], tepe, -1.0)))
            en = {"mT": round(float(tepe[i]), 4), "konum": [round(float(v), 1) for v in Z["P"][i]]}
        return durum(
            "tamam",
            kalibrasyon=kimlik,
            izgara={
                "kok": [round(float(v), 3) for v in Z["kok"]],
                "adim": ADIM_MM,
                "boyut": [int(v) for v in Z["boyut"]],
                "cerceve": "kabin",
                "camIc": [round(float(v), 1) for v in Z["cam"]],
            },
            deger=deger,
            olcek=olcek,
            yok=YOK,
            enYuksek=en,
            bobinler=[{"bobin": b, "frekans": f, "duty": d, "faz": p} for b, f, d, p in bobinler],
            uyarilar=uyari,
            hesapMs=round((time.perf_counter() - t0) * 1000.0, 1),
        )


def main(argv: list[str] | None = None, girdi=None, cikti=None) -> int:
    """Alt süreç girişi. Protokol akışı korunur: kütüphanelerin `print`i protokolü bozmasın diye `sys.stdout` stderr'e yönlenir."""
    from servers.alt_surec import json_satir_dongusu

    cikti = sys.stdout if cikti is None else cikti
    sys.stdout = sys.stderr
    return json_satir_dongusu(Hesapci().isle, girdi, cikti)
