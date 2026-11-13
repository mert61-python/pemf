# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK10 · petri kuyusunun SIVISI İÇİNDE E (sahip 13 Kasım 2026: "petri kabı koy simülasyona … alt camın üstündeymiş gibi").

FİZİK: 100 Hz'de kuyu sıvısı yarı-durağan bir iletkendir, kuyu duvarı (plastik) yalıtkandır → kuyuda E = −∂(A + ∇ψ)/∂t,
A = ½ B × (r − r_c) (kuyu boyunca düzgün B), ∇²ψ = 0, n·(A + ∇ψ) = 0 duvarda (akım duvardan çıkmaz). Sıvının σ / ε'u kuyu İÇİNDEKİ
E'yi değiştirmez (yalnız akım yoğunluğu J = σE'yi); E'yi geometri + B belirler. Çözüm: sonlu hacim (yalnız numpy, bir kez,
önbellek) → şekil fonksiyonları G_k(r) (mm): E(r, t) = −Σ_k G_k(r) · dB_k/dt.
DOĞRULAMA (13-11): CST LF (petri plakası camın üstünde + 24 kuyu sıvısı, εr 1e6 / σ 0,15 S/m) bobin 1–7 × 24 kuyu (168 durum), bu
çözücü CST noktalarında (duvar / yüzeyden ≥ 2 mm; daha yakında CST ağı dış alanla karışır): kuyu ortalaması |E| CST / model medyan 0,99
(%5–95: 0,98–1,00), vektör göreli hata %6–16. Kuyu E'si aynı yerde HAVADAKİ E'nin (CST ekutu) ~1/190'ı — eski "havada hesaplanan"
gösterim kuyu için ÇOK yüksekti.
Kuyu ölçüsü: 24'lük plaka, iç çap 15,6 mm; sıvı yüksekliği = 2 × `numune.plaka.sivi_orta_mm` (T noktaları sıvı ortasındadır).
"""
from __future__ import annotations

import functools

import numpy as np

#: 24'lük plaka kuyu iç yarıçapı (mm) — CST petri modeliyle aynı.
KUYU_YARICAP_MM = 7.8
#: Şekil çözümünün hücre boyu (mm) ve değerlendirme seyreltmesi (her eksende kaç hücrede bir nokta → ~2 mm aralık).
SEKIL_ADIM_MM = 0.5
SEYREK = 4


def _cg(matvec, b: np.ndarray, tol: float = 1e-10, azami: int = 20000) -> np.ndarray:
    """Pozitif yarı-tanımlı sistem için eşlenik gradyan (sabit sıfır uzayı: ortalama çıkarılır)."""
    x = np.zeros_like(b)
    r = b - matvec(x)
    p = r.copy()
    rr = float(r @ r)
    esik = tol * tol * float(b @ b)
    for _ in range(azami):
        if rr <= esik:
            break
        Ap = matvec(p)
        al = rr / float(p @ Ap)
        x += al * p
        r -= al * Ap
        r -= r.mean()
        rr2 = float(r @ r)
        p = r + (rr2 / rr) * p
        rr = rr2
    else:  # pragma: no cover — yakınsamadı: gösterim güvenilmez → çağıran E'yi göstermez
        raise RuntimeError("kuyu E şekil çözümü yakınsamadı")
    return x - x.mean()


@functools.lru_cache(maxsize=4)
def sekil(R_mm: float = KUYU_YARICAP_MM, H_mm: float = 10.0, h_mm: float = SEKIL_ADIM_MM, seyrek: int = SEYREK) -> tuple:
    """Kuyu (yarıçap R, sıvı yüksekliği H) için şekil fonksiyonları → (P (n, 3), G (3, n, 3)), mm. Eksenler: u = yükseklik (CST X),
    v, w = yatay (CST Y, Z) — alan modelinin bileşen ekseniyle AYNI. P kuyu merkezine (sıvı ortası) göre; `seyrek` hücrede bir nokta."""
    nu, nr = int(round(H_mm / h_mm)), int(np.ceil(R_mm / h_mm))
    u = (np.arange(nu) + 0.5) * h_mm - H_mm / 2
    v = (np.arange(-nr, nr) + 0.5) * h_mm
    U, V, Wg = np.meshgrid(u, v, v, indexing="ij")
    ic = V ** 2 + Wg ** 2 <= R_mm ** 2
    idx = -np.ones(ic.shape, dtype=np.int64)
    n = int(ic.sum())
    idx[ic] = np.arange(n)
    P = np.stack((U[ic], V[ic], Wg[ic]), 1)
    yuzler = []
    for ax in range(3):
        a, b = [slice(None)] * 3, [slice(None)] * 3
        a[ax], b[ax] = slice(0, -1), slice(1, None)
        I, J = idx[tuple(a)], idx[tuple(b)]
        m = (I >= 0) & (J >= 0)
        yuzler.append((I[m], J[m], ax))
    I_t = np.concatenate([y[0] for y in yuzler])
    J_t = np.concatenate([y[1] for y in yuzler])

    def eksi_laplas(x):  # −L x (pozitif yarı-tanımlı): Σ_yüz (x_i − x_j) her iki uca
        d = x[I_t] - x[J_t]
        return np.bincount(I_t, d, n) - np.bincount(J_t, d, n)

    G = np.zeros((3, n, 3))
    for k in range(3):
        e = np.zeros(3)
        e[k] = 1.0
        rhs = np.zeros(n)
        for I, J, ax in yuzler:
            Af = 0.5 * np.cross(e, (P[I] + P[J]) / 2.0)[:, ax]  # A·n_ij (n_ij = +eksen, i → j)
            rhs += np.bincount(I, -h_mm * Af, n) - np.bincount(J, -h_mm * Af, n)
        # Σ_j (ψ_j − ψ_i) = −h Σ_j A·n_ij  ⇔  −L ψ = −rhs
        psi = _cg(eksi_laplas, -rhs)
        Psi = np.full(ic.shape, np.nan)
        Psi[ic] = psi
        grad = np.zeros((n, 3))
        for ax in range(3):
            ileri, geri = np.roll(Psi, -1, ax), np.roll(Psi, 1, ax)
            sl = [slice(None)] * 3
            sl[ax] = -1
            ileri[tuple(sl)] = np.nan
            sl[ax] = 0
            geri[tuple(sl)] = np.nan
            vi, vg = ~np.isnan(ileri), ~np.isnan(geri)
            with np.errstate(invalid="ignore"):
                g = np.where(vi & vg, (ileri - geri) / (2 * h_mm),
                             np.where(vi, (ileri - Psi) / h_mm, np.where(vg, (Psi - geri) / h_mm, 0.0)))
            grad[:, ax] = g[ic]
        G[k] = 0.5 * np.cross(e[None, :], P) + grad
    iu, iv, iw = np.nonzero(ic)
    s = seyrek // 2
    sec = ((iu % seyrek) == s) & ((iv % seyrek) == s) & ((iw % seyrek) == s)
    return P[sec], G[:, sec, :]


def kuyu_e_tepe(A, T_backend, sd, sivi_yukseklik_mm: float, hizala: bool = True) -> np.ndarray:
    """Kuyu merkezleri (backend, sıvı ortası; (nT, 3)), işaretli duty (7,) → her kuyuda sıvı hacmi ortalaması tepe |E(t)| (nT,), V/m.
    B: alan modeli (CST birim alanları × ölçülen kalibrasyon, kuyu merkezinde); zaman biçimi: B ile AYNI dalga / Y280 hizalaması."""
    _P, G = sekil(KUYU_YARICAP_MM, float(sivi_yukseklik_mm))
    M = A.alan(np.asarray(T_backend, dtype=float).reshape(-1, 3))  # (nT, 3, 7) mT / genlik, CST eksenleri (X = yükseklik = u)
    dW = A.td_turev(sd, hizala)  # (7, Nt) 1 / s
    out = np.empty(len(M))
    for i, m in enumerate(M):
        Gm = np.einsum("kpc,kj->pcj", G, m)  # (p, 3, 7) mm · mT
        Et = np.einsum("pcj,jt->pct", Gm, dW) * 1e-6  # V/m (mm → m · mT → T)
        out[i] = np.linalg.norm(Et, axis=1).max(axis=1).mean()
    return out
