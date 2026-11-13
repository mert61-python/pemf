# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODAK alan modeli (istem 45 A1): CST birim alanları × 0. adım kalibrasyonu (eşleme, kazanç, işaret, çerçeve kayması, ölçülen duty eğrisi).

ÇERÇEVELER — dönüşüm YALNIZ burada (`backend_to_olcum`, `AlanModeli.olcum_to_cst`):
  backend kabin (ürün kuralı T2B, `ai_hub/cv_ortak/sabit_duzlem.py`): orijin cam içi merkez, +X önden bakanın SOLU, +Y yukarı, +Z ARKAYA (mm)
  ölçüm çerçevesi (0. adım, `DENETIM\\odak\\olcum`): +x SAĞ, +y yukarı, +z ÖNE  → (x, y, z) = (−X, Y, −Z)
  CST: X = yükseklik, Y = genişlik (+ sol), Z = derinlik (+ ön)  → X = taban_cst_x + (y − taban_y), Y = −x + merkez_cst_y, Z = z + merkez_cst_z
Alan bileşenleri CST eksenindedir (yalnız |B| ve model özniteliği olarak kullanılır — eğitimle aynı).

GENLİK BİRİMİ: a ∈ [−1, 1]; |a| = 1 ⇔ o bobin duty 0,5'teki tepe akımında. a(d) = ölçülen tepe(d) / tepe(0,5) (0. adım eğrisi).
FAZ (Y280): faz_c = (d_maks − d_c) × 360° (+ 180° işaret negatifse), mod 360 → darbe SONLARI (tepe akımlar) aynı anda.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os

import numpy as np

N_BOBIN = 7
#: Bobin 1–5 bipolar, 6–7 tek yönlü (firmware PEMF_BOBIN_UNIPOLAR_MASKESI 0x60).
BIPOLAR = (True, True, True, True, True, False, False)
#: Sahip (12 Kasım tezgâh): tedavide duty üst sınırı %50 — bütün bobinler (firmware bipolar tavanı da 0,5).
DUTY_AZAMI = 0.5
VERI_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veri")
ALAN_TABLOSU = "alan_tablosu.npz"
#: Y282 (sahip 12 Kasım 2026): alan tablosu + ONNX modelleri (CST'den türetilmiş) AÇIK DEPODA YOK — diğer ağırlıklar gibi AI MODEL
#: KATMANINDA (`release_assets/ai_models/ai_hub/odak/veri/`; kurulu: model dizini). `VERI_DIZINI`de yalnız küçük üst veri (model
#: `.json`, `numune.json`) kalır. Çözüm + bütünlük (takipli manifest SHA-256, fail-closed) `utils.model_downloader`.
MODEL_GORELI = "ai_hub/odak/veri"
#: ODK8 (sahip 13 Kasım 2026): AI Pro sürüş frekansları. Kalibrasyon (duty → genlik eğrisi, kazançlar) 100 Hz'de ÖLÇÜLDÜ; diğer
#: frekanslarda duty → genlik, kalibre RL modelinin tepe akım oranıyla taşınır (B adımında MLX ile doğrulanacak).
FREKANSLAR = (76.0, 100.0, 107.0, 147.0)
TEMEL_FREKANS = 100.0


def model_katmani_yolu(ad: str) -> str:
    """AI model katmanındaki ODAK dosyası (`alan_tablosu.npz` / `model_<KIP>.onnx`). Çözüm `yan_dosya_coz`: modül yanı (donmuş pakete
    gömülü kopya varsa) → model kökleri (başlatıcı `install_root/ai_models` — vet / research paketleri; kaynaktan koşuda
    `release_assets/ai_models`). Bulunamazsa FileNotFoundError (çağıran: ODAK engeli `modelYok` — SÜRMEZ); özeti tutmazsa
    `ModelButunlukHatasi` (YÜKLENMEZ)."""
    from utils.model_downloader import yan_dosya_coz

    yol = yan_dosya_coz(os.path.join(VERI_DIZINI, ad), f"{MODEL_GORELI}/{ad}")
    if not os.path.isfile(yol):
        raise FileNotFoundError(f"ODAK model dosyası bulunamadı: {MODEL_GORELI}/{ad}")
    return yol
#: Veri kökü altındaki kalibrasyon (0. adım; düzlem kalibrasyonuyla AYNI klasör).
KALIBRASYON_DIZINI = "kabin_kalibrasyonu"
KALIBRASYON_DOSYASI = "alan_kalibrasyonu.json"
KALIBRASYON_SURUM_EN_AZ = 2


class KalibrasyonHatasi(Exception):
    """Sürüşü engelleyen kalibrasyon durumu. `kod` → i18n `ai.pro.odak.engel.<kod>` (eylem söyleyen metin)."""

    def __init__(self, kod: str, ayrinti: str = ""):
        super().__init__(f"{kod}: {ayrinti}" if ayrinti else kod)
        self.kod = kod
        self.ayrinti = ayrinti


def backend_to_olcum(P) -> np.ndarray:
    """Backend kabin (X sol, Y yukarı, Z arka) → ölçüm çerçevesi (x sağ, y yukarı, z ön). TEK dönüşüm yeri (CST'ye `AlanModeli.olcum_to_cst`)."""
    P = np.asarray(P, dtype=float)
    out = np.empty_like(P)
    out[..., 0] = -P[..., 0]
    out[..., 1] = P[..., 1]
    out[..., 2] = -P[..., 2]
    return out


def olcum_to_backend(P) -> np.ndarray:
    """Ters dönüşüm (aynı ayna — kendisinin tersi)."""
    return backend_to_olcum(P)


_ZORUNLU = ("esleme_gercek_cst", "kazanc", "isaret", "cerceve", "duty_egrisi_olcum", "rl")


def kalibrasyon_kimligi(K: dict) -> str:
    """Modeli eğiten alan ile sürüşteki alanın AYNI olduğunu bağlayan kimlik: eşleme, kazanç, işaret, çerçeve, duty eğrisi, RL dalga biçimi."""
    cer = K.get("cerceve") or {}
    alt = {
        "esleme": {str(k): int(v) for k, v in sorted((K.get("esleme_gercek_cst") or {}).items())},
        "kazanc": [round(float(v), 4) for v in K.get("kazanc") or []],
        "isaret": [int(v) for v in K.get("isaret") or []],
        "cerceve": [round(float(cer.get(a, 0.0)), 2) for a in ("taban_cst_x", "yukseklik_ofset_mm", "merkez_cst_y", "merkez_cst_z")],
        "duty": (K.get("duty_egrisi_olcum") or {}).get("tepe_akim_A"),
        "rl": [round(float((K.get("rl") or {}).get(a, 0.0)), 3) for a in ("V", "R_ohm", "L_mH", "f_hz", "sonum_kati")],
    }
    return hashlib.sha256(json.dumps(alt, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def kalibrasyon_oku(veri_koku) -> dict:
    """Veri kökündeki alan kalibrasyonu → dict. Yok / bozuk / eski sürüm / eşleme doğrulanmamış → KalibrasyonHatasi (SÜRME)."""
    if not veri_koku:
        raise KalibrasyonHatasi("kalibrasyonYok", "veri kökü yok")
    yol = os.path.join(str(veri_koku), KALIBRASYON_DIZINI, KALIBRASYON_DOSYASI)
    if not os.path.isfile(yol):
        raise KalibrasyonHatasi("kalibrasyonYok", yol)
    try:
        with open(yol, encoding="utf-8") as fh:
            K = json.load(fh)
    except (OSError, ValueError) as e:
        raise KalibrasyonHatasi("kalibrasyonBozuk", str(e)) from None
    if not isinstance(K, dict) or any(a not in K for a in _ZORUNLU):
        raise KalibrasyonHatasi("kalibrasyonBozuk", "eksik alan")
    try:
        surum = int(K.get("surum", 0))
    except (TypeError, ValueError):
        surum = 0
    if surum < KALIBRASYON_SURUM_EN_AZ:
        raise KalibrasyonHatasi("kalibrasyonEski", f"sürüm {K.get('surum')}")
    if K.get("esleme_dogrulandi") is not True:
        raise KalibrasyonHatasi("eslemeDogrulanmadi")
    es = K["esleme_gercek_cst"]
    try:
        cst = sorted(int(es[str(r + 1)]) for r in range(N_BOBIN))
        kaz = [float(v) for v in K["kazanc"]]
        isr = [int(v) for v in K["isaret"]]
        egri = K["duty_egrisi_olcum"]
        ok = (
            cst == list(range(1, N_BOBIN + 1))
            and len(kaz) == N_BOBIN
            and all(np.isfinite(kaz)) and all(v > 0 for v in kaz)
            and len(isr) == N_BOBIN and all(v in (-1, 1) for v in isr)
            and len(egri["duty"]) >= 2 and len(egri["tepe_akim_A"]) == N_BOBIN
        )
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        raise KalibrasyonHatasi("kalibrasyonBozuk", "değer aralığı")
    return K


E_TABLOSU = "e_tablosu.npz"


@functools.lru_cache(maxsize=2)
def e_tablosu(yol: str | None = None) -> dict:
    """ODK6 · CST E tablosu (AI model katmanı, Y282): `bobin1..7_ekutu.txt` (LF 100 Hz) B tablosuyla AYNI küresel faz + Eylül işaretiyle
    gerçelleştirilmiş; E'nin SANAL (indüklenen, akım türevine orantılı) kısmı — gerçel kısım enerjinin < %0,2'si (12-11 ölçüldü). CST bobin
    sırası, CST eksenleri, V/m (CST uyarımı başına), 10 mm ızgara = alan tablosununki."""
    z = np.load(yol or model_katmani_yolu(E_TABLOSU))
    E = z["E"].astype(np.float32)
    return {
        "E": E,
        "kok": np.array([float(z["x0"]), float(z["y0"]), float(z["z0"])]),
        "adim": float(z["adim_mm"]),
        "boyut": np.array(E.shape[:3]),
        "f_cst_hz": float(z["f_cst_hz"]),
        "kimlik": str(z["kimlik"]),
    }


@functools.lru_cache(maxsize=2)
def alan_tablosu(yol: str | None = None) -> dict:
    """CST birim alan tablosu (CST bobin sırası, Eylül normalli, CST eksenleri, mT; 10 mm ızgara). `yol` yoksa AI model katmanından (Y282)."""
    z = np.load(yol or model_katmani_yolu(ALAN_TABLOSU))
    B = z["B"].astype(np.float32)
    return {
        "B": B,
        "kok": np.array([float(z["x0"]), float(z["y0"]), float(z["z0"])]),
        "adim": float(z["adim_mm"]),
        "boyut": np.array(B.shape[:3]),
        "kimlik": str(z["kimlik"]),
    }


def rl_dalga_bicimi(
    dg, bipolar: bool, V: float, R: float, L_mH: float, f: float, sonum_kati: float, n_kayit=200, n_ince=1000, periyot=12, tepe_dondur=False
):
    """Kararlı durum akım dalgası (darbe başı t = 0), her duty için KENDİ tepesine normalize. (len(dg), n_kayit).
    `tepe_dondur` → (biçim, mutlak tepe akım A (len(dg),)) — ODK8: frekans başına duty → genlik oranı için."""
    dg = np.asarray(dg, dtype=float)
    tau = (L_mH * 1e-3) / R
    dt = 1.0 / f / n_ince
    e_on, e_off = np.exp(-dt / tau), np.exp(-sonum_kati * dt / tau)
    Iinf = V / R
    i = np.zeros(len(dg))
    dalga = np.zeros((len(dg), n_kayit))
    adim = n_ince // n_kayit
    for p in range(periyot):
        for n in range(n_ince):
            ph = n / n_ince
            pos = ph < dg
            if bipolar:
                neg = (ph >= 0.5) & (ph < 0.5 + dg)
                hedef = np.where(pos, Iinf, np.where(neg, -Iinf, 0.0))
                on = pos | neg
            else:
                hedef = np.where(pos, Iinf, 0.0)
                on = pos
            i = np.where(on, hedef + (i - hedef) * e_on, i * e_off)
            if not bipolar:
                i = np.maximum(i, 0.0)
            if p == periyot - 1 and n % adim == 0:
                dalga[:, n // adim] = i
    tepe = np.maximum(np.abs(dalga).max(axis=1, keepdims=True), 1e-12)
    return (dalga / tepe, tepe[:, 0]) if tepe_dondur else dalga / tepe


class AlanModeli:
    """Kalibrasyon + tablo → gerçek bobin sırasıyla alan, duty ↔ genlik, Y280 fazı, zaman domeni tepe dozu."""

    N_DUTY = 51  # 0..0,5 duty ızgarası (dalga biçimi tablosu; aralar doğrusal ara değerlenir)
    N_ZAMAN = 1000  # periyot başına örnek (hizalama kayması çözünürlüğü %0,1 periyot = 10 µs @ 100 Hz)

    def __init__(self, K: dict, tablo: dict | None = None, f_hz: float | None = None):
        self.K = K
        self.f_cal = float(K["rl"].get("f_hz", TEMEL_FREKANS))
        self.f_hz = float(f_hz) if f_hz else self.f_cal
        # ODK8: kimlik frekansı da taşır (100 Hz'de eskisiyle AYNI) — model meta'sı aynı frekansla eğitilmiş olmalı (`modelEski`)
        self.kimlik = kalibrasyon_kimligi(K) if abs(self.f_hz - self.f_cal) < 1e-9 else f"{kalibrasyon_kimligi(K)}@{self.f_hz:g}Hz"
        self.tablo = tablo if tablo is not None else alan_tablosu()
        es = K["esleme_gercek_cst"]
        self.cst_sira = [int(es[str(r + 1)]) - 1 for r in range(N_BOBIN)]
        self.olcek = np.asarray(K["kazanc"], float) * np.asarray(K["isaret"], float)
        cer = K["cerceve"]
        self.taban_cst_x = float(cer["taban_cst_x"]) + float(cer.get("yukseklik_ofset_mm", 0.0))
        self.cam = np.asarray(cer["cam_ic_mm"], float)
        self.yc, self.zc = float(cer["merkez_cst_y"]), float(cer["merkez_cst_z"])
        self.taban_y = -self.cam[1] / 2.0
        # ölçülen duty → tepe oranı (a = tepe(d) / tepe(0,5)) bobin başına
        eg = K["duty_egrisi_olcum"]
        d = np.concatenate([[0.0], np.asarray(eg["duty"], float)])
        self.dg = np.linspace(0.0, DUTY_AZAMI, self.N_DUTY)
        a_tab = []
        for c in range(N_BOBIN):
            Ic = np.concatenate([[0.0], np.asarray(eg["tepe_akim_A"][c], float)])
            a = np.interp(self.dg, d, Ic)
            a_tab.append(np.maximum.accumulate(a / max(a[-1], 1e-12) + np.linspace(0, 1e-9, len(self.dg))))
        self.a_tab = np.array(a_tab)  # (7, 51) kesin artan
        rl = K["rl"]
        prm = (float(rl["V"]), float(rl["R_ohm"]), float(rl["L_mH"]), self.f_hz, float(rl.get("sonum_kati", 1.0)))
        bic_b, tepe_b = rl_dalga_bicimi(self.dg, True, *prm, n_kayit=self.N_ZAMAN, n_ince=self.N_ZAMAN, tepe_dondur=True)
        bic_u, tepe_u = rl_dalga_bicimi(self.dg, False, *prm, n_kayit=self.N_ZAMAN, n_ince=self.N_ZAMAN, tepe_dondur=True)
        if abs(self.f_hz - self.f_cal) > 1e-9:
            # ODK8: ölçülen (kalibrasyon frekansı) duty → genlik eğrisi × RL tepe akımı oranı (f / f_cal), bobin başına bipolar / tek yönlü
            prm_cal = prm[:3] + (self.f_cal,) + prm[4:]
            _, tb0 = rl_dalga_bicimi(self.dg, True, *prm_cal, n_kayit=self.N_ZAMAN, n_ince=self.N_ZAMAN, tepe_dondur=True)
            _, tu0 = rl_dalga_bicimi(self.dg, False, *prm_cal, n_kayit=self.N_ZAMAN, n_ince=self.N_ZAMAN, tepe_dondur=True)
            oran_b, oran_u = tepe_b / np.maximum(tb0, 1e-12), tepe_u / np.maximum(tu0, 1e-12)
            oran_b[0], oran_u[0] = oran_b[1], oran_u[1]  # duty 0: 0 / 0 → komşu
            for c in range(N_BOBIN):
                a = self.a_tab[c] * (oran_b if BIPOLAR[c] else oran_u)
                self.a_tab[c] = np.maximum.accumulate(a) + np.linspace(0, 1e-6, len(a))  # KESİN artan (ters çevrilebilir)
        # biçim[c, d] (kendi tepesine normalize); genlik td_tepe'de TAM a(d) ile (ızgaraya yuvarlama YOK — 12-11 ölçüldü: 0,01'lik ızgara küçük
        # duty'de bobin genliğini %5–10 kaydırıp doz denetimine yapay sapma katıyordu)
        self.bicim = np.stack([bic_b if BIPOLAR[c] else bic_u for c in range(N_BOBIN)])  # (7, 51, Nt)
        self.f_hz = prm[3]
        self._etablo = None  # ODK6: CST E tablosu (ilk `e_alan` çağrısında; yoksa FileNotFoundError — yalnız E gösterimi eksik kalır)

    # ── çerçeve ────────────────────────────────────────────────────────────────────────────────────────
    def olcum_to_cst(self, Pm) -> np.ndarray:
        Pm = np.asarray(Pm, dtype=float)
        out = np.empty_like(Pm)
        out[..., 0] = self.taban_cst_x + (Pm[..., 1] - self.taban_y)
        out[..., 1] = -Pm[..., 0] + self.yc
        out[..., 2] = Pm[..., 2] + self.zc
        return out

    def cam_icinde(self, P_backend, pay_mm: float = 0.0) -> np.ndarray:
        """Nokta(lar) cam içi kutuda mı (backend çerçevesi; kutu simetrik olduğundan çerçeve dönüşümünden bağımsız)."""
        P = np.asarray(P_backend, dtype=float)
        yari = self.cam / 2.0 - float(pay_mm)
        return np.all(np.isfinite(P), axis=-1) & np.all(np.abs(P) <= yari, axis=-1)

    # ── alan ──────────────────────────────────────────────────────────────────────────────────────────
    def alan_olcum(self, Pm) -> np.ndarray:
        """Ölçüm çerçevesi noktaları (..., 3) → M (..., 3, 7): GERÇEK bobin sırası, kazanç × işaret uygulanmış, CST eksenleri, mT / genlik."""
        return self._ara_deger(self.tablo, "B", Pm)

    def e_alan(self, P_backend) -> np.ndarray:
        """ODK6 · backend kabin noktaları (..., 3) → ME (..., 3, 7): CST E (V/m, indüklenen) B ile AYNI eşleme / kazanç × işaret / çerçeve —
        bobin akımı ölçekleme B kalibrasyonundan (E DOĞRUDAN ÖLÇÜLMEDİ). Zaman domeni tepe için `td_e_tepe`."""
        if self._etablo is None:
            et = e_tablosu()
            for k in ("kok", "boyut"):
                if not np.allclose(et[k], self.tablo[k]):
                    raise ValueError(f"E tablosu ızgarası alan tablosuyla aynı değil ({k})")
            if et["adim"] != self.tablo["adim"]:
                raise ValueError("E tablosu adımı alan tablosuyla aynı değil")
            self._etablo = et
        return self._ara_deger(self._etablo, "E", backend_to_olcum(P_backend))

    def _ara_deger(self, T: dict, ad: str, Pm) -> np.ndarray:
        """Tablo (B ya da E) üç doğrusal ara değerleme + GERÇEK bobin sırası + kazanç × işaret."""
        Pm = np.asarray(Pm, dtype=float)
        sh = Pm.shape[:-1]
        P = self.olcum_to_cst(Pm.reshape(-1, 3))
        idx, tt = [], []
        for ax in range(3):
            f = (P[:, ax] - T["kok"][ax]) / T["adim"]
            i = np.clip(np.floor(f).astype(int), 0, int(T["boyut"][ax]) - 2)
            idx.append(i)
            tt.append(np.clip(f - i, 0.0, 1.0))
        (i, j, k), (tx, ty, tz) = idx, tt
        B = T[ad]
        out = np.zeros((len(P), 3, N_BOBIN))
        for a, wa in ((0, 1 - tx), (1, tx)):
            for b, wb in ((0, 1 - ty), (1, ty)):
                for c, wc in ((0, 1 - tz), (1, tz)):
                    out += (wa * wb * wc)[:, None, None] * B[i + a, j + b, k + c][:, :, self.cst_sira]
        out *= self.olcek[None, None, :]
        return out.reshape(sh + (3, N_BOBIN))

    def alan(self, P_backend) -> np.ndarray:
        """Backend kabin noktaları (..., 3) → M (..., 3, 7)."""
        return self.alan_olcum(backend_to_olcum(P_backend))

    # ── duty ↔ genlik ────────────────────────────────────────────────────────────────────────────────
    def genlik(self, d) -> np.ndarray:
        """|duty| (..., 7) → |a| (..., 7) (ölçülen eğri)."""
        d = np.clip(np.abs(np.asarray(d, dtype=float)), 0.0, DUTY_AZAMI)
        return np.stack([np.interp(d[..., c], self.dg, self.a_tab[c]) for c in range(N_BOBIN)], axis=-1)

    @property
    def a_azami(self) -> np.ndarray:
        """ODK8: bobin başına duty 0,5'teki genlik (100 Hz'de 1; 76 Hz'de > 1, 147 Hz'de < 1 — RL oranı)."""
        return self.a_tab[:, -1]

    def duty(self, a) -> np.ndarray:
        """|a| (..., 7) → duty (..., 7) ∈ [0, 0,5] (genlik bobinin o frekanstaki azamisine kırpılır)."""
        a = np.minimum(np.abs(np.asarray(a, dtype=float)), self.a_azami)
        return np.stack([np.interp(a[..., c], self.a_tab[c], self.dg) for c in range(N_BOBIN)], axis=-1)

    def isaretli_duty(self, a) -> np.ndarray:
        a = np.asarray(a, dtype=float)
        return np.where(a < 0, -1.0, 1.0) * self.duty(a)

    @staticmethod
    def fazlar(sd) -> np.ndarray:
        """Y280: işaretli duty (7,) → faz (derece, 7): (d_maks − d) × 360 (+ 180 negatifse), mod 360; duty 0 → 0."""
        sd = np.asarray(sd, dtype=float)
        d = np.abs(sd)
        faz = (d.max() - d) * 360.0 + np.where(sd < 0, 180.0, 0.0)
        faz = np.mod(faz, 360.0)
        return np.where(d > 0, faz, 0.0)

    # ── zaman domeni (Y280 hizalı) ───────────────────────────────────────────────────────────────────
    def td_tepe(self, M, sd, hizala: bool = True) -> np.ndarray:
        """M (nT, 3, 7), işaretli duty (7,) → her noktada tepe |B(t)| (nT,) — fazlar `fazlar(sd)` ile (firmware gecikme anlamı)."""
        W = self._td_dalga(sd, hizala)
        Bt = np.einsum("tij,jk->tik", np.asarray(M, dtype=float), W)  # (nT, 3, Nt)
        return np.linalg.norm(Bt, axis=1).max(axis=1)

    def td_e_tepe(self, ME, sd, hizala: bool = True) -> np.ndarray:
        """ODK6 · ME (nT, 3, 7) (`e_alan`), işaretli duty → her noktada tepe |E(t)| (nT,) V/m. Faraday (CST LF, indüklenen alan): E(t) =
        Σ_c Ê_c · i_c′(t) / ω_CST — Ê_c CST'de sinüs akımda E genliği, i_c(t) B ile AYNI genlik / dalga biçimi / Y280 hizalaması."""
        W = self._td_dalga(sd, hizala)
        Nt = W.shape[1]
        dW = (np.roll(W, -1, axis=1) - np.roll(W, 1, axis=1)) * (Nt * self.f_hz / 2.0)  # dalga türevi, 1 / s (periyodik)
        f_cst = float((self._etablo or e_tablosu())["f_cst_hz"])
        Et = np.einsum("tij,jk->tik", np.asarray(ME, dtype=float), dW) / (2.0 * np.pi * f_cst)
        return np.linalg.norm(Et, axis=1).max(axis=1)

    def _td_dalga(self, sd, hizala: bool = True) -> np.ndarray:
        """İşaretli duty (7,) → bobin akım dalgaları W (7, Nt) (genlik a(d) × biçim; Y280 hizalı; ters işaret: bipolar −, tek yönlü yarım
        periyot kayması)."""
        sd = np.asarray(sd, dtype=float)
        d = np.clip(np.abs(sd), 0.0, DUTY_AZAMI)
        f = d / DUTY_AZAMI * (self.N_DUTY - 1)
        i0 = np.clip(np.floor(f).astype(int), 0, self.N_DUTY - 2)
        w = np.clip(f - i0, 0.0, 1.0)
        Nt = self.bicim.shape[2]
        a = self.genlik(d)
        W = np.stack([((1 - w[c]) * self.bicim[c, i0[c]] + w[c] * self.bicim[c, i0[c] + 1]) * a[c] for c in range(N_BOBIN)])  # (7, Nt)
        if hizala:
            kay = np.rint((d.max() - d) * Nt).astype(int)
            W = np.stack([np.roll(W[c], kay[c]) for c in range(N_BOBIN)])
        for c in range(N_BOBIN):
            if sd[c] < 0:
                W[c] = -W[c] if BIPOLAR[c] else np.roll(W[c], Nt // 2)
        return W

    def dogrusal_tepe(self, M, a) -> np.ndarray:
        """Tepe akımlar aynı anda varsayımıyla |Σ a_c M_c| (nT,) — çözücü / model ölçeği."""
        return np.linalg.norm(np.einsum("tij,j->ti", np.asarray(M, dtype=float), np.asarray(a, dtype=float)), axis=1)


#: 128 işaret deseni (tavan için köşe taraması).
ISARETLER = np.array([[1.0 if (k >> c) & 1 else -1.0 for c in range(N_BOBIN)] for k in range(2 ** N_BOBIN)])


def tavan(M) -> float:
    """Hedef kümesi M (nT, 3, 7) → duty ≤ 0,5 ile verilebilen en büyük doz, DOĞRUSAL (tepeler aynı anda) köşe taraması."""
    Bv = np.einsum("tij,vj->vti", np.asarray(M, dtype=float), ISARETLER)
    return float(np.linalg.norm(Bv, axis=2).min(axis=1).max())


def tavan_td(A: "AlanModeli", M) -> float:
    """Doz seçicinin ÜST SINIRI — fizik denetimiyle AYNI tanım (Y280 hizalı zaman domeni tepe |B|): 128 işaret deseninde bütün bobinler duty
    0,5 iken hedef kümesinin en zayıf noktasındaki tepe; en büyüğü. (Doğrusal tavandan tek yönlü 6–7'nin öbür yarım periyodu yüzünden ±%3–8
    farklı olabilir — ölçüldü 12-11.)"""
    M = np.asarray(M, dtype=float)
    return float(max(A.td_tepe(M, DUTY_AZAMI * s).min() for s in ISARETLER))
