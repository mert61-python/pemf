# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ODK (istem 45 · Y268–Y274 · Y280) — `ai_hub.odak` alan modeli + öneri + fizik denetimi + ONNX model sarmalayıcısı.

SÖZLEŞME:
  - Çerçeve dönüşümü TEK yerde: backend (X sol, Y yukarı, Z arka) → ölçüm (x sağ, y yukarı, z ön) = (−X, Y, −Z) → CST.
  - Kalibrasyon kapısı FAIL-CLOSED: yok / bozuk / eski sürüm / eşleme doğrulanmamış → KalibrasyonHatasi(kod) (çağıran SÜRMEZ).
  - Kalibrasyon kimliği eğitimle sürüşü bağlar (model başka kalibrasyonla eğitildiyse "modelEski" → SÜRME).
  - Faz = işaret + tepe hizalama (Y280): (d_maks − d) × 360 (+180 negatifse), mod 360; zaman domeni tepe dozu hizalıda ≥ hizasız.
  - Fizik denetimi KARAR VERMEZ, DENETLER: |beklenen / istenen − 1| > %10 · doz > tavan · hedef kabin dışı · ızgara yok → engel, duty 0.
  - Petride 24 kuyu haritası (her kuyuda beklenen mT, seçili kuyu işaretli).
Gerçek alan tablosu (`ai_hub/odak/veri/alan_tablosu.npz`) + 12 Kasım tezgâh kalibrasyonunun özü (`tests/veri/odak_kalibrasyon_ornek.json`).
"""

from __future__ import annotations

import copy
import json
import os

import numpy as np
import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORNEK = os.path.join(KOK, "tests", "veri", "odak_kalibrasyon_ornek.json")


@pytest.fixture(scope="module")
def K():
    with open(ORNEK, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def A(K):
    from ai_hub.odak.alan import AlanModeli

    return AlanModeli(K)


def _kok(tmp_path, K=None, ham=None):
    d = tmp_path / "kabin_kalibrasyonu"
    d.mkdir(parents=True, exist_ok=True)
    if ham is not None:
        (d / "alan_kalibrasyonu.json").write_text(ham, encoding="utf-8")
    elif K is not None:
        (d / "alan_kalibrasyonu.json").write_text(json.dumps(K), encoding="utf-8")
    return str(tmp_path)


# ── çerçeve ────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_DONUSUM_backend_olcum_TEK_yer_ve_ayna(A):
    from ai_hub.odak.alan import backend_to_olcum, olcum_to_backend

    P = np.array([[10.0, -20.0, 30.0], [-5.0, 7.0, -9.0]])
    assert np.allclose(backend_to_olcum(P), [[-10.0, -20.0, -30.0], [5.0, 7.0, 9.0]])
    assert np.allclose(olcum_to_backend(backend_to_olcum(P)), P)
    assert np.allclose(A.alan(P), A.alan_olcum(backend_to_olcum(P)))
    # ölçüm → CST: X yükseklik (taban + ofset), Y = −x + merkez, Z = z + merkez
    c = A.olcum_to_cst(np.array([0.0, A.taban_y, 0.0]))
    assert c[0] == pytest.approx(A.taban_cst_x) and c[1] == pytest.approx(A.yc) and c[2] == pytest.approx(A.zc)


def test_KRITIK_cam_ici_kutusu(A):
    yari = A.cam / 2
    assert A.cam_icinde(np.zeros(3))
    assert not A.cam_icinde(np.array([yari[0] + 1.0, 0.0, 0.0]))
    assert not A.cam_icinde(np.array([0.0, np.nan, 0.0]))
    assert not A.cam_icinde(np.array([yari[0] - 1.0, 0.0, 0.0]), pay_mm=5.0)


# ── kalibrasyon kapısı ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "bozma,kod",
    [
        (lambda K: None, "kalibrasyonYok"),
        (lambda K: "{bozuk", "kalibrasyonBozuk"),
        (lambda K: json.dumps({k: v for k, v in K.items() if k != "kazanc"}), "kalibrasyonBozuk"),
        (lambda K: json.dumps({**K, "surum": 1}), "kalibrasyonEski"),
        (lambda K: json.dumps({**K, "surum": "x"}), "kalibrasyonEski"),
        (lambda K: json.dumps({**K, "esleme_dogrulandi": False}), "eslemeDogrulanmadi"),
        (lambda K: json.dumps({**K, "kazanc": [-1.0] * 7}), "kalibrasyonBozuk"),
        (lambda K: json.dumps({**K, "isaret": [2] * 7}), "kalibrasyonBozuk"),
        (lambda K: json.dumps({**K, "esleme_gercek_cst": {str(i): 1 for i in range(1, 8)}}), "kalibrasyonBozuk"),
        (lambda K: json.dumps({**K, "esleme_gercek_cst": {}}), "kalibrasyonBozuk"),
        (lambda K: json.dumps([1, 2]), "kalibrasyonBozuk"),
    ],
)
def test_KRITIK_kalibrasyon_kapisi_FAIL_CLOSED(tmp_path, K, bozma, kod):
    from ai_hub.odak.alan import KalibrasyonHatasi, kalibrasyon_oku

    ham = bozma(K)
    kok = _kok(tmp_path, ham=ham) if ham is not None else str(tmp_path)
    with pytest.raises(KalibrasyonHatasi) as e:
        kalibrasyon_oku(kok)
    assert e.value.kod == kod


def test_KRITIK_kalibrasyon_kokSUZ_ve_GECERLI(tmp_path, K):
    from ai_hub.odak.alan import KalibrasyonHatasi, kalibrasyon_oku

    with pytest.raises(KalibrasyonHatasi) as e:
        kalibrasyon_oku("")
    assert e.value.kod == "kalibrasyonYok" and "kalibrasyonYok" in str(e.value)
    assert kalibrasyon_oku(_kok(tmp_path, K))["kazanc"] == K["kazanc"]


def test_KRITIK_kalibrasyon_KIMLIGI_alanla_degisir_ilgisizle_degismez(K):
    from ai_hub.odak.alan import kalibrasyon_kimligi

    k0 = kalibrasyon_kimligi(K)
    assert kalibrasyon_kimligi({**K, "olcum": {"x": 1}, "kaynak": "baska"}) == k0
    K2 = copy.deepcopy(K)
    K2["kazanc"][3] *= 1.05
    assert kalibrasyon_kimligi(K2) != k0
    K3 = copy.deepcopy(K)
    K3["cerceve"]["merkez_cst_z"] += 5
    assert kalibrasyon_kimligi(K3) != k0


# ── alan / duty / faz / zaman domeni ───────────────────────────────────────────────────────────────────
def test_KRITIK_ALAN_kazanc_ve_isaretle_OLCEKLENIR(K, A):
    from ai_hub.odak.alan import AlanModeli

    P = np.array([[0.0, -150.0, 0.0], [100.0, -100.0, 50.0]])
    K2 = copy.deepcopy(K)
    K2["kazanc"] = [2 * v for v in K["kazanc"]]
    K2["isaret"] = [-v for v in K["isaret"]]
    assert np.allclose(AlanModeli(K2).alan(P), -2.0 * A.alan(P))
    assert A.alan(P).shape == (2, 3, 7) and A.alan(P[0]).shape == (3, 7)


def test_KRITIK_DUTY_genlik_TERSI_ve_KIRPMA(A):
    from ai_hub.odak.alan import DUTY_AZAMI

    d = np.array([0.05, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5])
    assert np.allclose(A.duty(A.genlik(d)), d, atol=2e-3)
    assert np.all(A.genlik(np.full(7, 0.9)) == pytest.approx(1.0))  # 0,5'in üstü kırpılır
    assert A.duty(np.full(7, 5.0)).max() == pytest.approx(DUTY_AZAMI)
    sd = A.isaretli_duty(np.array([-0.5, 0.5, 0, 0.2, -0.2, 1.0, -1.0]))
    assert sd[0] < 0 < sd[1] and sd[5] == pytest.approx(DUTY_AZAMI) and sd[6] == pytest.approx(-DUTY_AZAMI)


def test_KRITIK_Y280_FAZ_isaret_ARTI_tepe_hizalama():
    from ai_hub.odak.alan import AlanModeli

    f = AlanModeli.fazlar(np.array([0.1, -0.4, 0.0, 0.4, -0.25, 0.2, 0.0]))
    assert np.allclose(f, [108.0, 180.0, 0.0, 0.0, 234.0, 72.0, 0.0])


def test_KRITIK_TD_tepe_HIZALI_hizasizdan_KUCUK_DEGIL_ve_dogrusala_YAKIN(A):
    P = np.array([[0.0, -160.0, 0.0]])
    M = A.alan(P)
    sd = np.array(
        [0.1, -0.4, 0.0, 0.0, 0.0, 0.0, 0.0]
    )  # taban ortasında 1 ile 2 ZIT işaretle toplanır (tezgâh: 180° 1,07 / 0° 0,49 mT)
    a = np.sign(sd) * A.genlik(sd)
    hiz, hizsiz, dog = A.td_tepe(M, sd)[0], A.td_tepe(M, sd, hizala=False)[0], A.dogrusal_tepe(M, a)[0]
    assert hiz >= hizsiz - 1e-9, (hiz, hizsiz)
    assert hiz == pytest.approx(dog, rel=0.10), (hiz, dog)
    # negatif işaret: bipolar −, tek yönlü yarım periyot
    sd2 = np.array([-0.3, 0.0, 0.0, 0.0, 0.0, -0.3, 0.3])
    assert np.isfinite(A.td_tepe(M, sd2)).all()


def test_KRITIK_TD_doz_duty_IZGARASINA_yuvarlanmaz_SUREKLI(A):
    """12-11 ölçüldü: 0,01'lik duty ızgarasına yuvarlama küçük duty'de bobin genliğini %5–10 kaydırıyor, doz denetimine yapay sapma katıyordu.
    Doz duty'de SÜREKLİ olmalı: %0,5'lik duty değişimi dozu en çok ~%1,5 değiştirir. MUTANT: biçim ara değerlemesini / tam a(d)'yi kaldırın → KIRMIZI."""
    M = A.alan(np.array([[0.0, -150.0, 0.0]]))
    for c, (d1, d2) in ((0, (0.063, 0.0649)), (3, (0.021, 0.0239))):  # aynı 0,01 ızgara hücresinde iki duty
        s1, s2 = np.zeros(7), np.zeros(7)
        s1[c], s2[c] = d1, d2
        oran_td = A.td_tepe(M, s2)[0] / A.td_tepe(M, s1)[0]
        oran_a = A.genlik(s2)[c] / A.genlik(s1)[c]
        assert oran_a > 1.02 and oran_td == pytest.approx(oran_a, rel=0.02), (c, oran_td, oran_a)


def test_KRITIK_TAVAN_kose_TARAMASI_her_isaret_deseninden_BUYUK_ESIT(A):
    from ai_hub.odak.alan import ISARETLER, tavan

    M = A.alan(np.array([[30.0, -150.0, -20.0]]))
    t = tavan(M)
    assert ISARETLER.shape == (128, 7)
    assert all(t >= float(np.linalg.norm(M[0] @ s)) - 1e-9 for s in ISARETLER)


def test_KRITIK_TAVAN_ZAMAN_DOMENI_fizik_denetimiyle_AYNI_tanim(A):
    """Seçicinin üst sınırı (`tavan_td`) = 128 köşe deseninde zaman domeni hizalı dozun en büyüğü = fizik denetiminin geçireceği en büyük doz.
    12-11 ölçüldü: tek noktada doğrusalla aynı; ÇOK noktalı kümede (kedi tüm vücut, 47 nokta) tek yönlü 6–7'nin öbür yarım periyodu yüzünden
    %16 DÜŞÜK — doğrusal tavanla seçici, fizik denetiminin geçirmeyeceği bir dozu da sunardı. MUTANT: `tavan_td` → doğrusal `tavan` → KIRMIZI."""
    from ai_hub.odak import oneri
    from ai_hub.odak.alan import DUTY_AZAMI, ISARETLER, tavan, tavan_td

    kw = {"hedef_P": [0.0, -120.0, 0.0], "kedi": {"theta": 0.2}}
    M = A.alan(oneri.kip_girdisi("KEDI_TV", A, **kw)["T"])
    t = tavan_td(A, M)
    en = max(A.td_tepe(M, DUTY_AZAMI * s).min() for s in ISARETLER)
    assert t == pytest.approx(en) and t > 0
    assert 0.7 * tavan(M) <= t < 0.95 * tavan(M), (t, tavan(M))
    # seçici (onay ekranı doz üst sınırı) ve öneri AYNI tanımı kullanır
    assert oneri.hedef_tavani("KEDI_TV", A, **kw)["tavan_mT"] == pytest.approx(t, abs=1e-3)


def test_YAPISAL_rl_dalga_bicimi_KENDI_tepesine_normalize():
    from ai_hub.odak.alan import rl_dalga_bicimi

    w = rl_dalga_bicimi([0.0, 0.25, 0.5], True, 24.0, 8.7, 27.0, 100.0, 1.5)
    assert w.shape == (3, 200) and np.abs(w[1:]).max(axis=1) == pytest.approx([1.0, 1.0])
    u = rl_dalga_bicimi([0.25], False, 24.0, 8.7, 27.0, 100.0, 1.5)
    assert u.min() >= 0.0


# ── öneri / fizik denetimi ─────────────────────────────────────────────────────────────────────────
def _plaka(merkez_b=(0.0, -165.0, 0.0), th=0.3, eksik=None, px=True):
    """Backend çerçevesinde 24 kuyu (A1..D6), ölçüm çerçevesinde merkez + yön θ ile."""
    from ai_hub.odak.alan import olcum_to_backend

    m = np.array(merkez_b) * np.array([-1, 1, -1])
    out = []
    for r in range(4):
        for c in range(6):
            u, v = (c - 2.5) * 19.3, (r - 1.5) * 19.3
            du, dv = u * np.cos(th) - v * np.sin(th), u * np.sin(th) + v * np.cos(th)
            P = olcum_to_backend(np.array([m[0] + du, m[1], m[2] + dv]))
            e = f"{'ABCD'[r]}{c + 1}"
            if e != eksik:
                out.append({"etiket": e, "P": P.tolist(), "px": [100 + 40 * c, 50 + 40 * r] if px else None})
    return out


def test_KRITIK_PETRI_izgarasi_MERKEZ_YON_ve_eksik_KUYU(A):
    from ai_hub.odak import oneri

    g = oneri.petri_izgarasi(_plaka(th=0.3))
    assert np.allclose(g["merkez"], [0.0, -165.0, 0.0], atol=1e-6) and g["theta"] == pytest.approx(0.3)
    assert [k["etiket"] for k in g["sira"]][:7] == ["A1", "A2", "A3", "A4", "A5", "A6", "B1"]
    # ODK11: eksik kuyu artık ENGEL değil — yeri görülenlerden hesaplanır (`bos`); alt sınır / sapma test_ODK11_*'da
    g23 = oneri.petri_izgarasi(_plaka(th=0.3, eksik="C4"))
    c4 = next(k for k in g23["sira"] if k["etiket"] == "C4")
    assert g23["bulunan"] == 23 and c4["bos"] is True and np.allclose(g23["merkez"], g["merkez"], atol=1e-6)
    with pytest.raises(oneri.Engel):
        oneri.petri_izgarasi(
            [{"etiket": "W1", "P": [0, 0, 0]}, {"etiket": "A9", "P": [0, 0, 0]}, {"etiket": "A1", "P": [0, 0]}]
        )


class _DogruModel:
    """Fizikle TAM tutan sahte model: tavan köşesinin yönünde, istenen dozu zaman domeninde veren genlik (doz başına)."""

    ozellik_ad = ["doz_mT"]

    def __init__(self, A, P_hedef, kimlik=None, olcek=1.0):
        from ai_hub.odak.alan import ISARETLER

        self.A, self.MT = A, A.alan(np.asarray(P_hedef, float).reshape(-1, 3))
        B = np.linalg.norm(np.einsum("tij,vj->vti", self.MT, ISARETLER), axis=2).min(axis=1)
        self.u = ISARETLER[int(np.argmax(B))]
        self.kalibrasyon_kimligi = A.kimlik if kimlik is None else kimlik
        self.olcek = olcek

    def ozellik(self, oz, M, doz_mT):
        return np.array([[doz_mT]])

    def tahmin(self, X):
        D = float(X[0, 0])
        lo, hi = 0.0, 1.0
        for _ in range(40):  # td dozu = D olacak ölçek (ikiye bölme)
            k = (lo + hi) / 2
            sd = self.A.isaretli_duty(self.u * k)
            if self.A.td_tepe(self.MT, sd).min() < D:
                lo = k
            else:
                hi = k
        return (self.u * hi * self.olcek / D)[None, :]


def test_KRITIK_ONERI_KUYUCUK_basari_PLAN_alanlari_ve_24_KUYU_haritasi(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    hedef = next(k for k in kuyular if k["etiket"] == "B3")
    m = _DogruModel(A, [hedef["P"]])
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="b3")
    assert tv["engel"] is None and tv["tavan_mT"] > 0.5
    plan = oneri.oner("KUYUCUK", A, 0.6 * tv["tavan_mT"], model=m, kuyular=kuyular, hedef_etiket="B3")
    assert plan["engel"] is None, plan
    assert plan["beklenen_mT"] == pytest.approx(plan["doz_mT"], rel=0.02)
    assert plan["tavan_mT"] == pytest.approx(tv["tavan_mT"])
    assert plan["cevre_mT"] > 0 and plan["oran"] > 0 and plan["pay_yuzde"] >= 0 and abs(plan["sapma_yuzde"]) <= 10
    assert max(plan["duty"]) <= 0.5 and any(d > 0 for d in plan["duty"]) and len(plan["faz"]) == 7
    k = plan["kuyular"]
    assert (
        len(k) == 24 and sum(1 for x in k if x["secili"]) == 1 and next(x for x in k if x["secili"])["etiket"] == "B3"
    )
    assert all(isinstance(x["mT"], float) and x["mT"] > 0 for x in k)
    assert next(x for x in k if x["secili"])["mT"] == pytest.approx(plan["beklenen_mT"], rel=1e-3)


def test_KRITIK_ONERI_TUM_PETRI_duzgunluk_ORANI_en_zayif_bolu_en_guclu(A):
    from ai_hub.odak import oneri

    kuyular = _plaka(px=False)
    m = _DogruModel(A, [k["P"] for k in kuyular])
    tv = oneri.hedef_tavani("TUM_PETRI", A, kuyular=kuyular)
    plan = oneri.oner("TUM_PETRI", A, 0.5 * tv["tavan_mT"], model=m, kuyular=kuyular)
    assert plan["engel"] is None, plan
    assert plan["cevre_mT"] is None and 0 < plan["oran"] <= 1.0
    assert min(x["mT"] for x in plan["kuyular"]) == pytest.approx(plan["beklenen_mT"], rel=1e-3)
    assert not any(x["secili"] for x in plan["kuyular"])


def test_KRITIK_ONERI_FANTOM_cevre_ORANI(A):
    from ai_hub.odak import oneri

    T = [20.0, -155.0, 10.0]
    m = _DogruModel(A, [T])
    plan = oneri.oner("FANTOM", A, 0.5, model=m, hedef_P=T, fantom={"merkez_P": [0.0, -150.0, 0.0], "theta": 0.4})
    assert plan["engel"] is None, plan
    assert plan["cevre_mT"] > 0 and plan["oran"] > 0 and "kuyular" not in plan


@pytest.mark.parametrize("kip", ["KEDI_TV", "KEDI_ORGAN"])
def test_KARSIT_ONERI_KEDI_hesaplanir(A, kip):
    from ai_hub.odak import oneri

    T = [0.0, -120.0, 0.0]
    g = oneri.kip_girdisi(kip, A, hedef_P=T, kedi={"theta": 0.2})
    m = _DogruModel(A, g["T"])
    # doz TAVANA göre (zaman domeni tavanı konuma bağlı: kedi tüm vücutta ~0,3 mT olabilir — sabit doz tavanı aşıp `dozTavanUstu` verirdi)
    tv = oneri.hedef_tavani(kip, A, hedef_P=T, kedi={"theta": 0.2})
    assert tv["engel"] is None and tv["tavan_mT"] > 0, tv
    plan = oneri.oner(kip, A, 0.5 * tv["tavan_mT"], model=m, hedef_P=T, kedi={"theta": 0.2})
    assert plan["engel"] is None, plan
    assert (plan["cevre_mT"] is None) == (kip == "KEDI_TV")


def test_KRITIK_ONERI_ENGELLERI_duty_SIFIR(A):
    from ai_hub.odak import oneri

    kuyular = _plaka()
    hedef = next(k for k in kuyular if k["etiket"] == "A1")
    m = _DogruModel(A, [hedef["P"]])
    tv = oneri.hedef_tavani("KUYUCUK", A, kuyular=kuyular, hedef_etiket="A1")["tavan_mT"]

    def kod(**k):
        p = oneri.oner(**k)
        assert p["duty"] == [0.0] * 7 and p["faz"] == [0.0] * 7
        return p["engel"], p["engel_ek"]

    ortak = {"kip": "KUYUCUK", "A": A, "kuyular": kuyular, "hedef_etiket": "A1"}
    assert kod(doz_mT=0.0, model=m, **ortak)[0] == "dozGecersiz"
    assert kod(doz_mT=float("nan"), model=m, **ortak)[0] == "dozGecersiz"
    e, ek = kod(doz_mT=tv * 1.2, model=m, **ortak)
    assert e == "dozTavanUstu" and ek["tavan"] == pytest.approx(tv)
    assert kod(doz_mT=0.5 * tv, model=_DogruModel(A, [hedef["P"]], kimlik="baska"), **ortak)[0] == "modelEski"
    # OTB T-3 (sahip 19-11): %30 az veren model artık FİZİK DÜZELTMESİYLE sürülür; engel yalnız düzelmezse (test_OTB_T123_*).
    p = oneri.oner(doz_mT=0.5 * tv, model=_DogruModel(A, [hedef["P"]], olcek=0.7), **ortak)
    assert p["engel"] is None and p["duzeltme"]["kat"] > 1.2 and abs(p["beklenen_mT"] / p["doz_mT"] - 1) <= 0.1, p
    assert kod(doz_mT=0.5, model=m, kip="KUYUCUK", A=A, kuyular=kuyular, hedef_etiket="Z9")[0] == "kuyuYok"
    assert (
        kod(doz_mT=0.5, model=m, kip="KUYUCUK", A=A, kuyular=kuyular[:6], hedef_etiket="A1")[0] == "plakaYok"
    )  # tek satır (ODK11)
    assert kod(doz_mT=0.5, model=m, kip="FANTOM", A=A, hedef_P=[0.0, 500.0, 0.0])[0] == "hedefKabinDisi"
    assert oneri.hedef_tavani("FANTOM", A, hedef_P=[0.0, 500.0, 0.0])["engel"] == "hedefKabinDisi"
    with pytest.raises(ValueError):
        oneri.kip_girdisi("YOK", A)


def test_KRITIK_alan_modeli_VERI_KOKUNDEN_onbellekli_ve_kapili(tmp_path, K):
    from ai_hub.odak import oneri
    from ai_hub.odak.alan import KalibrasyonHatasi

    kok = _kok(tmp_path, K)
    a1, a2 = oneri.alan_modeli(kok), oneri.alan_modeli(kok)
    assert a1 is a2
    K2 = copy.deepcopy(K)
    K2["kazanc"][0] *= 1.1
    assert oneri.alan_modeli(_kok(tmp_path / "b", K2)) is not a1
    with pytest.raises(KalibrasyonHatasi):
        oneri.alan_modeli(str(tmp_path / "yok"))


# ── ONNX model sarmalayıcısı ─────────────────────────────────────────────────────────────────────────
def _kucuk_onnx(dizin, kip, sinir=2.0, kimlik="k1"):
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    W = numpy_helper.from_array(np.full((4, 7), 1.0, np.float32), "W")
    g = helper.make_graph(
        [helper.make_node("MatMul", ["x", "W"], ["y"])],
        "kucuk",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [None, 4])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [None, 7])],
        [W],
    )
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 12)])
    m.ir_version = 7
    onnx.save(m, os.path.join(dizin, f"model_{kip}.onnx"))
    with open(os.path.join(dizin, f"model_{kip}.json"), "w", encoding="utf-8") as fh:
        json.dump({"ozellik_ad": ["a", "doz_mT"], "kalibrasyon_kimligi": kimlik, "sinir": sinir}, fh)


def test_KRITIK_ONNX_MODEL_oznitelik_SIRASI_doz_ve_KIRPMA(tmp_path):
    from ai_hub.odak.model import KIPLER, OdakModeli, model_al

    _kucuk_onnx(str(tmp_path), "FANTOM")
    m = OdakModeli("FANTOM", str(tmp_path))
    X = m.ozellik({"a": 3.0}, np.zeros((1, 1)), 0.5)  # yerel alan (1 değer) + yerel / doz
    assert X.shape == (1, 4) and X.dtype == np.float32 and list(X[0]) == [3.0, 0.5, 0.0, 0.0]
    y = m.tahmin(X)
    assert y.shape == (1, 7) and np.all(y == 2.0)  # 3,5 → sınır 2'ye kırpıldı
    assert m.tahmin(X) is not None and m._oturum is not None  # oturum yeniden kullanılır
    assert model_al("FANTOM", str(tmp_path)) is model_al("FANTOM", str(tmp_path))
    assert set(KIPLER) == {"TUM_PETRI", "KUYUCUK", "FANTOM", "KEDI_TV", "KEDI_ORGAN"}
    with pytest.raises(ValueError):
        OdakModeli("YOK", str(tmp_path))


def test_KRITIK_YEREL_alan_noktasi_EGITIMLE_ayni():
    from ai_hub.odak.model import yerel_nokta

    ty = -175.0
    assert list(yerel_nokta("TUM_PETRI", {"plaka_x": 1, "plaka_z": 2, "altlik": 10}, ty)) == [1, ty + 15, 2]
    assert list(yerel_nokta("KUYUCUK", {"hedef_x": 3, "hedef_z": 4, "altlik": 0}, ty)) == [3, ty + 5, 4]
    assert list(yerel_nokta("FANTOM", {"tumor_x": 5, "tumor_z": 6}, ty)) == [5, ty + 15, 6]  # ODK8: fantom 3 cm
    assert list(yerel_nokta("KEDI_TV", {"kedi_x": 7, "kedi_z": 8}, ty)) == [7, pytest.approx(ty + 73.7), 8]
    assert list(yerel_nokta("KEDI_ORGAN", {"organ_x": 1, "organ_y": 2, "organ_z": 3}, ty)) == [1, 2, 3]


def test_YAPISAL_URUN_MODELLERI_kalibrasyon_kimligi_ve_AI_MODEL_KATMANINDA(K):
    """ONNX modelleri (A4 dışa aktarımı) örnek kalibrasyonla AYNI kimlikte; Y282: dosyalar AI MODEL KATMANINDAN çözülür
    (`release_assets/ai_models/ai_hub/odak/veri/`), depodaki `VERI_DIZINI`de YOK (yalnız üst veri)."""
    from ai_hub.odak.alan import ALAN_TABLOSU, VERI_DIZINI, kalibrasyon_kimligi, model_katmani_yolu
    from ai_hub.odak.model import KIPLER, model_al

    kim = kalibrasyon_kimligi(K)
    for kip in KIPLER:
        yol = model_katmani_yolu(f"model_{kip}.onnx")
        assert os.path.normcase(os.path.dirname(os.path.abspath(yol))) != os.path.normcase(
            os.path.abspath(VERI_DIZINI)
        ), yol
        assert not os.path.exists(os.path.join(VERI_DIZINI, f"model_{kip}.onnx")), (
            f"{kip}: ONNX depodaki veri dizininde (Y282)"
        )
        m = model_al(kip)
        assert os.path.samefile(m._yol, yol)
        assert m.kalibrasyon_kimligi == kim, f"{kip}: model başka kalibrasyonla eğitilmiş"
        assert "doz_mT" in m.ozellik_ad
    assert os.path.isfile(model_katmani_yolu(ALAN_TABLOSU))
    assert not os.path.exists(os.path.join(VERI_DIZINI, ALAN_TABLOSU)), "alan tablosu depodaki veri dizininde (Y282)"


def test_KRITIK_GERCEK_MODEL_tum_petri_ortada_FIZIK_denetiminden_gecer(A):
    """Uçtan uca (gerçek ONNX KNN + gerçek alan + örnek kalibrasyon): plaka taban ortasında, doz tavanın yarısı → engel yok, doz ±%10."""
    from ai_hub.odak import oneri

    kuyular = _plaka(merkez_b=(0.0, -165.0, 0.0), th=0.0)
    tv = oneri.hedef_tavani("TUM_PETRI", A, kuyular=kuyular)["tavan_mT"]
    plan = oneri.oner("TUM_PETRI", A, round(0.5 * tv, 2), kuyular=kuyular)
    assert plan["engel"] is None, plan
    assert abs(plan["sapma_yuzde"]) <= 10.0
