# Author: mertaygn, cglrgrkn
"""1-G · D1.102 (B-8.17; adaylar İG-8.6, İG-8.7) — ESP32-S3 tam köprüsünde DDS konumu SIÇRADIĞINDA ölü-zaman korunur.

ÖLÇÜLEN KUSUR (bu aparatla, HEAD 67a60a0): `_updatePWM`'deki duty kırpması (duty ≤ yarım − DEAD_TIME_TICKS) yalnız
KARARLI dalgada iki bacak arasında ≥ 2 tick (40 µs) boşluk bırakır. DDS konumunu (`rel`) çıkış durumuna BAKMADAN
sıçratan dört olay var: (1) ilk-darbe faz edinimi ([E4] `syncPulseISR` → `s_tick = 0`), (2) seans ortası frekans
değişimi (`s_tpp`), (3) yalnız faz güncellemesi (`s_phase_ticks`, İG-8.6), (4) frekans hafif uyumsuzken tolerans
kilidinin her periyot yaptığı sıçrama (İG-8.7). Sıçrama bir bacak açıkken karşı bacağın penceresine düşerse ISR AYNI
çağrıda `w1tc(eski)` + `w1ts(yeni)` yazar → ölü-zaman 0 tick (shoot-through sınıfı; köprü sürücüsünün kendi ölü-zamanı
hiçbir belgede yok — TEZGÂH, Oturum 13).

DÜZELTME: çıkış katında sayaç — karşı bacak en az DEAD_TIME_TICKS tick kapalı kalmadan açılmaz (sıçramanın
kaynağından bağımsız). Kararlı dalgada boşluk zaten ≥ DEAD_TIME_TICKS → normal dalga DEĞİŞMEZ (KARŞIT kapısı: darbe
genişliği, periyot ve boşluklar tick'i tick'ine model değerinde).

ARAÇ: gerçek `CoilController.cpp` AYRI çeviri biriminde (`tests/esps3_coil_aparat.py`); ISR'lar taklit tabloya kaydedilen
işaretçilerden, senkron GPIO7 SEVİYESİ sürülerek (RISING), komutlar public `handleCommand` yolundan. Her tetikleyici
kolunda N=2000 rastgele deneme. Ölçüt: her ZIT bacak açılışından önce karşı bacak ≥ 40 µs LOW — eşik bu dosyanın
sabiti, kaynaktan OKUNMAZ (mutasyon hedefi `SharedDefs.h` değişse de kapı aynı fiziği ister).
Ö.4-Y7: ESP kodu silinmez (ESP devre dışı; değişiklik kodda, yakma ESP dönüşünde). Termal kesme/restart EKLENMEZ.
"""

from __future__ import annotations

import random
import struct

import pytest

TICK_US = 20  # DDS 50 kHz (tasarım) — aparat KURULUM'da ÖLÇER
OLU_ZAMAN_TICK = 2  # karar 19 (H-köprü ölü-zamanı) — kapı sabiti, kaynaktan OKUNMAZ
ESIK_US = OLU_ZAMAN_TICK * TICK_US
N = 2000
BOSTA_US = 2000  # denemeler arası STOP → START aralığı


def _ap():
    import esps3_coil_aparat as ap

    return ap


@pytest.fixture(scope="module")
def s3(tmp_path_factory):
    dizin = tmp_path_factory.mktemp("s3_d1102")
    return _ap().derle(dizin), dizin


class _Senaryo:
    def __init__(self):
        self.satir: list[str] = []
        self.saat = 0

    def __call__(self, s: str):
        self.satir.append(s)

    def bekle(self, us: int):
        self.satir.append(f"BEKLE {us}")
        self.saat += us

    def metin(self) -> str:
        return "\n".join(self.satir) + "\n"


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _tpp(f: int) -> int:
    return max(50000 // min(max(f, 1), 1000), 8)


def _model(f: int, d: int) -> tuple[int, int, int]:
    """Kararlı dalga modeli (tasarım sabitleri bu dosyada): tpp, yarım, darbe (tick)."""
    tpp = _tpp(f)
    yarim = tpp // 2
    darbe = int(_f32(_f32(_f32(min(max(d, 1), 50)) / _f32(100.0)) * _f32(tpp)))
    ust = yarim - OLU_ZAMAN_TICK if yarim > OLU_ZAMAN_TICK else 1
    return tpp, yarim, max(min(darbe, ust), 1)


def _faz_tick(faz: int, tpp: int) -> int:
    return int(_f32(_f32(_f32(faz % 360) / _f32(360.0)) * _f32(tpp))) % tpp


def _kos(s3, ad: str, uret, n: int = N):
    """n deneme: her biri `DENEME i` + uret(...) + DURUM + DUR + boşta bekleme. → (çıktı, bilgi, zıt açılışlar)"""
    exe, dizin = s3
    sen = _Senaryo()
    rnd = random.Random(f"D1102-{ad}")
    bilgi = {}
    for i in range(n):
        sen(f"DENEME {i}")
        bilgi[i] = uret(sen, rnd) or {}
        bilgi[i]["bitis"] = sen.saat
        sen("DURUM")
        sen("DUR")
        sen.bekle(BOSTA_US)
    out = _ap().kos(exe, sen.metin(), dizin, ad)
    assert out["kurulum"] == {"dds_us": TICK_US, "senkron_pin": 7, "senkron_kip": 1, "oto": True}, (
        f"aparat: DDS/senkron kaydı beklenen değil: {out['kurulum']}"
    )
    assert sorted(out["denemeler"]) == list(range(n)), "aparat: deneme işaretleri eksik"
    for i, d in out["denemeler"].items():
        assert d["durum"] is not None and d["durum"]["aktif"], f"aparat: deneme {i} sonunda çıkış ETKİN değil: {d}"
        assert all(ok for _, ok in d["komut"]), f"aparat: deneme {i} komutu reddedildi: {d['komut']}"
    return out, bilgi, _ap().zit_acilislar(out["kenarlar"])


def _ozet(ad: str, acilis, bilgi, n: int = N) -> tuple[str, int]:
    """Zıt açılışta boşluk < ESIK_US olan deneme sayısı (bilgi[i]["sonra"] varsa yalnız o andan sonrası)."""
    ihlalli, toplam, en_kucuk, zit = set(), 0, None, 0
    for deneme, t, _bacak, bosluk in acilis:
        if bosluk is None or deneme is None or t < bilgi[deneme].get("sonra", 0):
            continue
        zit += 1
        en_kucuk = bosluk if en_kucuk is None else min(en_kucuk, bosluk)
        if bosluk < ESIK_US:
            ihlalli.add(deneme)
            toplam += 1
    assert zit >= n, f"aparat: {ad} kolunda zıt açılış ölçülmedi ({zit})"
    return (
        f"{ad}: ihlalli deneme {len(ihlalli)}/{n} ({len(ihlalli) / n:.3f}), ihlal {toplam}, en küçük boşluk {en_kucuk} µs",
        len(ihlalli),
    )


def _hiza_kaniti(ad: str, acilis, bilgi, tpp: int, periyot_us: int = 10000, tolerans_us: int = 5 * TICK_US):
    """Araç kanıtı: senkron gerçekten kilitledi — 2. darbeden son darbeye kadar her periyotta A, ilk darbeye göre
    (faz konumu mod STM periyodu) ±tolerans içinde açılır. Senkron ISR'ı çağrılmasaydı serbest koşan DDS'in ofseti ya
    rastgele (aynı frekans: deneme başına ≈ %2 şans) ya da kayan (99/100 Hz: periyotta 100 µs) olurdu."""
    a_acilis: dict[int, list[int]] = {}
    for deneme, t, bacak, _ in acilis:
        if bacak == 0 and deneme is not None:
            a_acilis.setdefault(deneme, []).append(t)
    for i, b in bilgi.items():
        darbeler = b["darbeler"]
        ofset = _faz_tick(b["faz"], tpp) * TICK_US
        hizali = 0
        for t in a_acilis.get(i, []):
            if darbeler[1] - periyot_us // 2 <= t < darbeler[-1]:
                sapma = (t - darbeler[0] - ofset) % periyot_us
                hizali += min(sapma, periyot_us - sapma) <= tolerans_us
        assert hizali >= len(darbeler) - 2, (
            f"aparat: {ad} deneme {i} — A açılışlarının yalnız {hizali}/{len(darbeler) - 2}'i darbe+faz konumunda; "
            "senkron kilitlemedi"
        )


# ── KARŞIT + ARAÇ KANITI: kararlı dalga tick'i tick'ine model değerinde, boşluk tam tasarım değerinde ──────────────
_KARARLI_F = (1, 7, 33, 100, 200, 997, 1000)
_KARARLI_D = (1, 10, 25, 49, 50)


def test_KARSIT_ARAC_kararli_dalga_MODEL_degerinde_ve_bosluk_TAM_tasarim(s3):
    sira = [(f, d, faz) for f in _KARARLI_F for d in _KARARLI_D for faz in (0, 270)]

    def uret_fabrika():
        it = iter(sira)

        def uret(sen, _rnd):
            f, d, faz = next(it)
            t0 = sen.saat
            sen(f"BASLA {f} {d} {faz} 0")
            sen.bekle(5 * _tpp(f) * TICK_US)
            return {"f": f, "d": d, "faz": faz, "t0": t0}

        return uret

    out, bilgi, acilis = _kos(s3, "kararli", uret_fabrika(), n=len(sira))
    ap = _ap()
    hatalar = []
    for i, b in bilgi.items():
        tpp, yarim, darbe = _model(b["f"], b["d"])
        alt, ust = b["t0"] + 2 * tpp * TICK_US, b["bitis"]
        kenar = [k for k in out["kenarlar"] if k[3] == i]
        a = [x for x in ap.yuksek_araliklar(kenar, 0) if x[0] >= alt and x[1] < ust]
        bb = [x for x in ap.yuksek_araliklar(kenar, 1) if x[0] >= alt and x[1] < ust]
        if len(a) < 2 or len(bb) < 2:
            hatalar.append(f"{b}: tam aralık yok A={len(a)} B={len(bb)}")
            continue
        if {y - x for x, y in a} != {darbe * TICK_US} or {y - x for x, y in bb} != {darbe * TICK_US}:
            hatalar.append(f"{b}: darbe genişliği {sorted({y - x for x, y in a + bb})} ≠ model {darbe * TICK_US} µs")
        if {a[k + 1][0] - a[k][0] for k in range(len(a) - 1)} != {tpp * TICK_US}:
            hatalar.append(f"{b}: A periyodu model ({tpp * TICK_US} µs) değil")
        if {(y[0] - x[0]) % (tpp * TICK_US) for x in a for y in bb if 0 < y[0] - x[0] < tpp * TICK_US} != {
            yarim * TICK_US
        }:
            hatalar.append(f"{b}: B, A'dan yarım periyot ({yarim * TICK_US} µs) sonra açılmıyor")
        zit = [g for d, t, _, g in acilis if d == i and g is not None and alt <= t < ust]
        beklenen = min(yarim - darbe, tpp - yarim - darbe) * TICK_US
        if not zit or min(zit) != beklenen:
            hatalar.append(f"{b}: en küçük zıt boşluk {min(zit) if zit else None} µs ≠ tasarım {beklenen} µs")
    assert not hatalar, "kararlı dalga modelden saptı:\n" + "\n".join(hatalar[:20])
    metin, ihlalli = _ozet("kararlı", acilis, bilgi, n=len(sira))
    assert ihlalli == 0, metin


# ── (1) İLK-DARBE FAZ EDİNİMİ ([E4]) ─────────────────────────────────────────────────────────────────────────────
def _edinim(duty: int, faz: int | None):
    def uret(sen, rnd):
        f = rnd.randrange(0, 360) if faz is None else faz
        sen(f"BASLA 100 {duty} {f} 0")
        sen.bekle(rnd.randrange(0, 20000))
        p1 = sen.saat
        sen("SENKRON 0 10000 4 100")
        sen.bekle(40000)
        return {"darbeler": [p1 + k * 10000 for k in range(4)], "faz": f}

    return uret


def test_KRITIK_D1102_ilk_darbe_EDINIMI_karsi_bacagi_OLU_ZAMANSIZ_acmaz(s3):
    satirlar, kirmizi = [], 0
    for ad, duty, faz in (
        ("edinim D50", 50, 0),
        ("edinim D25", 25, 0),
        ("edinim D10", 10, 0),
        ("edinim D50 faz~", 50, None),
    ):
        out, bilgi, acilis = _kos(s3, ad.replace(" ", "_").replace("~", "r"), _edinim(duty, faz))
        assert all(not d["durum"]["sync_disabled"] for d in out["denemeler"].values()), f"aparat: {ad} senkron kapandı"
        _hiza_kaniti(ad, acilis, bilgi, tpp=500)
        metin, ihlalli = _ozet(ad, acilis, bilgi)
        satirlar.append(metin)
        kirmizi += ihlalli
    assert kirmizi == 0, (
        "ilk PB1 darbesinde faz edinimi (s_tick=0) bir bacak açıkken karşı bacağı ölü-zamansız açıyor (B-8.17):\n"
        + "\n".join(satirlar)
    )


# ── (2) SEANS ORTASI FREKANS DEĞİŞİMİ ────────────────────────────────────────────────────────────────────────────
def _frekans(f1: int, f2: int):
    t1 = _tpp(f1) * TICK_US

    def uret(sen, rnd):
        sen(f"BASLA {f1} 50 0 0")
        sen.bekle(2 * t1 + rnd.randrange(0, t1))
        sen(f"GUNCELLE {f2} 0 -1 0")
        sen.bekle(3 * _tpp(f2) * TICK_US)

    return uret


def test_KRITIK_D1102_frekans_DEGISIMI_karsi_bacagi_OLU_ZAMANSIZ_acmaz(s3):
    satirlar, kirmizi = [], 0
    for f1, f2 in ((100, 200), (200, 100), (10, 7)):
        ad = f"frekans {f1}->{f2}"
        _out, bilgi, acilis = _kos(s3, f"frekans_{f1}_{f2}", _frekans(f1, f2))
        metin, ihlalli = _ozet(ad, acilis, bilgi)
        satirlar.append(metin)
        kirmizi += ihlalli
    assert kirmizi == 0, (
        "seans ortası frekans güncellemesi (s_tpp) DDS konumunu sıçratıp karşı bacağı ölü-zamansız açıyor (B-8.17):\n"
        + "\n".join(satirlar)
    )


# ── (3) YALNIZ FAZ GÜNCELLEMESİ (İG-8.6) ─────────────────────────────────────────────────────────────────────────
def _faz(p1: int | None, p2: int | None):
    def uret(sen, rnd):
        a = rnd.randrange(0, 360) if p1 is None else p1
        b = rnd.randrange(0, 360) if p2 is None else p2
        sen(f"BASLA 100 50 {a} 0")
        sen.bekle(20000 + rnd.randrange(0, 10000))
        sen(f"GUNCELLE 0 0 {b} 0")
        sen.bekle(30000)

    return uret


def test_KRITIK_D1102_yalniz_FAZ_guncellemesi_karsi_bacagi_OLU_ZAMANSIZ_acmaz(s3):
    satirlar, kirmizi = [], 0
    for ad, p1, p2 in (("faz 0->180", 0, 180), ("faz 0->90", 0, 90), ("faz rastgele", None, None)):
        _out, bilgi, acilis = _kos(s3, ad.replace(" ", "_").replace("->", "_"), _faz(p1, p2))
        metin, ihlalli = _ozet(ad, acilis, bilgi)
        satirlar.append(metin)
        kirmizi += ihlalli
    assert kirmizi == 0, (
        "yalnız faz güncellemesi (s_phase_ticks) DDS konumunu sıçratıp karşı bacağı ölü-zamansız açıyor (İG-8.6):\n"
        + "\n".join(satirlar)
    )


# ── (4) TOLERANS KİLİDİ, FREKANS HAFİF UYUMSUZ (İG-8.7) ─────────────────────────────────────────────────────────
def test_KRITIK_D1102_tolerans_KILIDI_her_periyot_OLU_ZAMANSIZ_gecis_uretmez(s3):
    """STM 100 Hz (PB1 10 ms), ESP 99 Hz (tpp 505): darbe her periyot `t >= tpp - tol` dalına düşer, sayaç 500→0 sıçrar.
    Edinim (ilk darbe) etkisini ayırmak için ilk 1,5 periyot sayılmaz."""

    def uret(sen, rnd):
        faz = rnd.randrange(0, 360)
        sen(f"BASLA 99 50 {faz} 0")
        sen.bekle(rnd.randrange(0, 10000))
        p1 = sen.saat
        sen("SENKRON 0 10000 40 100")
        sen.bekle(400000)
        return {"darbeler": [p1 + k * 10000 for k in range(40)], "faz": faz, "sonra": p1 + 15000}

    out, bilgi, acilis = _kos(s3, "tolerans_99_100", uret)
    assert all(not d["durum"]["sync_disabled"] for d in out["denemeler"].values()), "aparat: senkron kapandı"
    assert all(d["durum"]["sync_ignored"] == 0 for d in out["denemeler"].values()), (
        "aparat: darbe yok sayıldı — tolerans kilidi dalı ölçülmüyor"
    )
    _hiza_kaniti("tolerans 99/100", acilis, bilgi, tpp=505)
    metin, ihlalli = _ozet("tolerans 99/100 Hz", acilis, bilgi)
    assert ihlalli == 0, (
        "tolerans kilidi (s_tick=0, periyot sonu) frekans hafif uyumsuzken her periyot karşı bacağı ölü-zamansız "
        f"açıyor (İG-8.7):\n{metin}"
    )
