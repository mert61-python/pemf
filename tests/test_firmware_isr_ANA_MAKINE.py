# Author: mertaygn, cglrgrkn
"""Firmware ISR ve paket kapıları — GERÇEK main.c ANA MAKİNEDE derlenip koşar (Dalga 1 · 1-B).

D1.21 · B-8.19  paket alan SIRASI: `BinaryCmdPacket_t` offsetof değerleri backend'in `STM_PAKET_FMT` önekleriyle
                aynı (phase↔freq takası bugünkü süitte 509/509 yeşildi); `UART_RX_BUF_SZ >= BINARY_PKT_SIZE`
                derleme zamanında (`_Static_assert`) kilitli.
D1.25 · B-8.15  shoot-through: bipolar tavan üstü duty'de iki bacak ASLA aynı anda HIGH değil; klemp uygulanır.
D1.26 · B-10.49 köprü geçişi: her açılışta önce karşı bacak kapanır (aynı tick), arada ≥ DDS_DEADTIME_NOP_ITERS NOP;
                karşı bacağın düşüşü ile bu bacağın yükselişi arası ≥ DDS_BIPOLAR_GAP_TICKS.
D1.27 · B-10.37 [FIX-1c] frekans artışında duty ORANI korunur (1 Hz %30 → 2 Hz).
D1.28 · B-10.159 klemp üst sınırında A ve B darbeleri SİMETRİK ve tavana eşit; sabitler main.c'den (yorum dışı).
İG-8.28 (1-G)   periyot ORTASINDA parametre değişiminde (faz / frekans / `ref_ms` hizalaması) de karşı bacak düşüşü →
                yükseliş ≥ GAP ve A+B asla birlikte HIGH değil (önce 2000 rastgele denemede 817 ihlal; eski strict-xfail
                normal kapı oldu). İG-8.29 "önce karşı bacağı kapat" yazımları ve İG-8.9 klemp UYGULAMA satırları
                D1.26 / D1.25 / D1.28 kollarıyla kapılı (mutantlar: DUZELTME-D1G).

Aparat: `tests/firmware_host_aparat.py` + `tests/firmware_host/` (BSRR yazım sırası ve NOP sayısı kaydedilir;
pin haritası main.c'nin kendi `coil_gpio` tablosundan). ⚠️ Derleyici yoksa FAIL (SKIP değil).

⚠️ AÇIK (uydurma ölçüm YOK): gerçek bacak aralığı ve NOP SÜRESİ (ns) yalnız tezgâhta osiloskopla ölçülür
(Oturum 13) — ana makine aparatı tick ve sayı ölçer, süre değil.
"""

from __future__ import annotations

import struct

import firmware_host_aparat as fw
import pytest

_GENIS = 0x7F  # 7 bobinin hepsi (bobin 6-7 donanımca tek-bacak)

#: Ölü-zaman ASGARİLERİ. Kaynaktan okunan sabit bunların ALTINA inemez: kapı eskiden yalnız main.c'deki değeri
#: okuyup ölçümü ona göre yapıyordu → `DDS_DEADTIME_NOP_ITERS 21U→0U` ve `DDS_BIPOLAR_GAP_TICKS 2→0` mutantları
#: (kapı mutant kaynağın KENDİ değeriyle kıyaslandığı için) YEŞİL kalıyordu [ölçüldü 2026-10-01].
#: GAP = 2 tick: ESP S3 `DEAD_TIME_TICKS` ile birebir (main.c notu). NOP = 21 iterasyon: süresi tezgâhta
#: ÖLÇÜLMEMİŞ (İG-8.28, Oturum 13) — düşürmek tezgâh ölçümüyle verilecek bilinçli karar; buradaki pin onu ZORLAR.
GAP_ASGARI = 2
NOP_ASGARI = 21


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    return fw.derle(fw.MAIN_C.read_text(encoding="utf-8"), tmp_path_factory.mktemp("isr"))


@pytest.fixture(scope="module")
def harita(exe):
    return fw.harita(exe)


@pytest.fixture(scope="module")
def sabitler():
    """Davranış ölçümlerinde EŞİK = max(kaynak, asgari): kaynaktaki sabit düşürülse de ölçüm asgariye göre yapılır."""
    kaynak = {"GAP": fw.sabit("DDS_BIPOLAR_GAP_TICKS"), "NOP": fw.sabit("DDS_DEADTIME_NOP_ITERS")}
    return {
        "GAP": max(kaynak["GAP"], GAP_ASGARI),
        "NOP": max(kaynak["NOP"], NOP_ASGARI),
        "GAP_KAYNAK": kaynak["GAP"],
        "NOP_KAYNAK": kaynak["NOP"],
    }


def test_KRITIK_D126_olu_zaman_sabitleri_ASGARININ_altina_INMEZ(sabitler):
    assert sabitler["GAP_KAYNAK"] >= GAP_ASGARI, (
        f"DDS_BIPOLAR_GAP_TICKS={sabitler['GAP_KAYNAK']} < {GAP_ASGARI} — köprü boşluğu ESP S3 ile hizalı asgarinin altında"
    )
    assert sabitler["NOP_KAYNAK"] >= NOP_ASGARI, (
        f"DDS_DEADTIME_NOP_ITERS={sabitler['NOP_KAYNAK']} < {NOP_ASGARI} — NOP ölü-zamanı tezgâh ölçümü OLMADAN düşürülmüş"
    )


# ── D1.21 ───────────────────────────────────────────────────────────────────


def test_KRITIK_D121_paket_ALAN_SIRASI_firmware_ile_backend_AYNI(exe):
    from utils.stm32_transport import STM_PAKET_FMT

    olcu = {p[1]: int(p[2]) for p in (s.split() for s in fw.kos(exe, "ofset")) if p[0] == "O"}
    olcu.update({p[0]: int(p[1]) for p in (s.split() for s in fw.kos(exe, "ofset")) if p[0] in ("Z", "R")})
    # backend'in paketleme sırası (hardware_controller: başlık, *duty, *faz, *frekans, *süre, ref_ms, kip, +crc32)
    adlar = ["header", "duty", "phase", "freq", "duration", "ref_ms", "unipolar_maskesi"]
    parcalar = STM_PAKET_FMT[1:].split()
    assert len(parcalar) == len(adlar), f"STM_PAKET_FMT parça sayısı değişti: {STM_PAKET_FMT!r}"
    beklenen = {ad: struct.calcsize("<" + " ".join(parcalar[:i])) for i, ad in enumerate(adlar)}
    beklenen["crc32"] = struct.calcsize(STM_PAKET_FMT)
    farkli = {ad: (olcu.get(ad), beklenen[ad]) for ad in beklenen if olcu.get(ad) != beklenen[ad]}
    assert farkli == {}, (
        f"firmware offsetof ≠ backend paketi (alan, firmware, backend): {farkli} — faz/frekans sessizce yer değiştirir"
    )
    assert olcu["Z"] == struct.calcsize(STM_PAKET_FMT) + 4, f"paket boyu firmware {olcu['Z']} ≠ backend"
    assert olcu["R"] >= olcu["Z"], f"UART_RX_BUF_SZ {olcu['R']} < paket {olcu['Z']} — paket tampona sığmaz"


def test_KRITIK_D121_UART_tamponu_DERLEME_ZAMANINDA_kilitli():
    """Bugünkü değer yetiyor; ama yalnız bu teste değil derleyiciye bağlı olmalı (CubeIDE de kırmızı olsun)."""
    import re

    from c_soyucu import c_soy

    soy = c_soy(fw.MAIN_C.read_text(encoding="utf-8"))
    assert re.search(r"_Static_assert\s*\(\s*UART_RX_BUF_SZ\s*>=\s*BINARY_PKT_SIZE\s*,", soy), (
        "main.c'de (yorum dışı) `_Static_assert(UART_RX_BUF_SZ >= BINARY_PKT_SIZE, …)` yok"
    )


# ── D1.25 · D1.26 · D1.28: kararlı durumda köprü değişmezleri ─────────────────


#: (frekans Hz, faz °) — 1-B bağımsız inceleme (i3): kararlı-durum kapıları yalnız faz=0'da koşuyordu; faz sarması
#: (`if (adj < 0) adj += tpp;`) silinince faz=90'da A/B boşluğu 0 tick'e iniyor ve darbeler asimetrikleşiyordu, kapı
#: YEŞİLDİ. Faz 90/270 ve tek tpp'li bir frekans (33 Hz → tpp 1515) eklendi.
KARARLI = [(100, 0), (100, 90), (100, 270), (33, 0)]
KARARLI_ID = ["100Hz_faz0", "100Hz_faz90", "100Hz_faz270", "33Hz_tek_tpp"]
_KARARLI_ONBELLEK: dict = {}


def _kararli(exe, harita, frek=100, duty=0.9, faz=0):
    anahtar = (str(exe), frek, duty, faz)
    if anahtar not in _KARARLI_ONBELLEK:
        pinler, _uni = harita
        n = 30000  # 100 Hz'de 60 periyot (33 Hz'de ~20); slew en geç ~18 periyotta (33 Hz: ~6) tavana varır
        olaylar = fw.bsrr_olaylari(fw.kos(exe, "isr", n, hex(_GENIS), frek, duty, faz))
        _KARARLI_ONBELLEK[anahtar] = fw.bacak_analizi(olaylar, pinler, sorted(pinler), baslangic_tick=15000)
    return _KARARLI_ONBELLEK[anahtar]


def _darbe_genislikleri(kenarlar, bacak):
    yuksel, genis = None, []
    for tick, b, seviye, _nop, _onceki in kenarlar:
        if b != bacak:
            continue
        if seviye == 1:
            yuksel = tick
        elif yuksel is not None:
            genis.append(tick - yuksel)
            yuksel = None
    return genis


@pytest.mark.parametrize(("frek", "faz"), KARARLI, ids=KARARLI_ID)
def test_KRITIK_D125_iki_bacak_ASLA_ayni_anda_HIGH(exe, harita, frek, faz):
    sonuc = _kararli(exe, harita, frek=frek, faz=faz)
    cakisma = {i + 1: r["cakisma"][:3] for i, r in sonuc.items() if r["cakisma"]}
    assert cakisma == {}, f"SHOOT-THROUGH: aynı anda A ve B HIGH (bobin: ilk tick'ler) {cakisma}"
    assert all(r["kenarlar"] for r in sonuc.values()), "aparat: bazı bobinler hiç sürülmedi (vakum)"


@pytest.mark.parametrize(("frek", "faz"), KARARLI, ids=KARARLI_ID)
def test_KRITIK_D126_her_acilista_ONCE_karsi_bacak_kapanir_ve_NOP_olu_zaman(exe, harita, sabitler, frek, faz):
    pinler, uni = harita
    sonuc = _kararli(exe, harita, frek=frek, faz=faz)
    ihlal = []
    for i, r in sonuc.items():
        pa, ia, pb, ib = pinler[i]
        for tick, bacak, seviye, nop, onceki in r["kenarlar"]:
            if seviye != 1:
                continue
            karsi_port, karsi_pin = (pb, ib) if bacak == "A" else (pa, ia)
            once_kapandi = onceki is not None and onceki[1] == karsi_port and ((onceki[2] >> 16) & karsi_pin)
            if not once_kapandi or nop < sabitler["NOP"]:
                ihlal.append((i + 1, tick, bacak, nop, bool(once_kapandi)))
    assert ihlal == [], f"break-before-make/NOP ihlali (bobin, tick, bacak, nop, önce-kapandı): {ihlal[:5]}"


@pytest.mark.parametrize(("frek", "faz"), KARARLI, ids=KARARLI_ID)
def test_KRITIK_D126_D128_karsi_bacak_dususu_ile_yukselis_arasi_GAP_ve_darbeler_SIMETRIK(
    exe, harita, sabitler, frek, faz
):
    pinler, uni = harita
    sonuc = _kararli(exe, harita, frek=frek, faz=faz)
    tpp, gap = int(50000 / frek), sabitler["GAP"]  # firmware: g_tpp = (uint32_t)(50000.0f / f)
    tavan_bipolar = tpp // 2 - gap
    for i, r in sonuc.items():
        A, B = _darbe_genislikleri(r["kenarlar"], "A"), _darbe_genislikleri(r["kenarlar"], "B")
        if uni[i]:
            assert not B and A and set(A) == {int(0.9 * tpp)}, f"bobin {i + 1} (tek-bacak): A={set(A)} B={B[:3]}"
            continue
        assert A and B, f"bobin {i + 1}: darbe yok"
        assert set(A) == set(B) == {tavan_bipolar}, (
            f"bobin {i + 1}: A={sorted(set(A))} B={sorted(set(B))} — klemp tavanı {tavan_bipolar} (yarım − GAP) ve simetri"
        )
        son_dusus = {"A": None, "B": None}
        kisa = []
        for tick, bacak, seviye, _n, _o in r["kenarlar"]:
            if seviye == 0:
                son_dusus[bacak] = tick
            else:
                karsi = son_dusus["B" if bacak == "A" else "A"]
                if karsi is not None and tick - karsi < gap:
                    kisa.append((tick, bacak, tick - karsi))
        assert kisa == [], f"bobin {i + 1}: karşı bacak düşüşü → yükseliş < GAP={gap}: {kisa[:4]}"


def test_KRITIK_D125_frekans_artisinda_klemp_ANINDA_periyot_sonunu_BEKLEMEZ(exe, harita, sabitler):
    """İlk klemp (`g_shadow.pending` bloğu, max_d_now) kararlı-durum testlerinde GÖRÜNMEZ: ikinci klemp her
    period_reset'te aynı işi yapar (ölçüldü: m2c2 mutantı kararlı kapılarda YEŞİL). Etkisi yalnız bekleyen güncelleme
    periyot ORTASINDA uygulanıp eski tick yeni periyoda sığdığında, period_reset'e kadar olan pencerededir.

    Senaryo: tüm bobinler 1 Hz %90 (bipolar klemp tavanı 24998) → periyodun BAŞINDA (tick≈100 < 500) 100 Hz %90.
    Oran-koruyan ölçek 24998/50000·500 = 249 → yarım − GAP = 248'i AŞAR; klemp onu AYNI ISR'da 248'e çekmeli,
    yoksa period_reset'e kadar A düşüşü → B yükselişi arası 1 tick (< GAP)."""
    pinler, uni = harita
    t2 = 100000 + 100
    sat = fw.kos(exe, "isr", t2 + 450, hex(_GENIS), 1, 0.9, 0, t2, 100, 0.9, 0)
    s_t2 = [d for d in fw.durumlar(sat) if d[0] == t2]
    assert len(s_t2) == 2 * len(pinler), f"aparat: t2 durum satırları eksik: {len(s_t2)}"
    once, sonra = s_t2[: len(pinler)], s_t2[len(pinler) :]
    tavan = 500 // 2 - sabitler["GAP"]
    for (_t, i, tpp0, d0, _h0), (_t2, _i, tpp1, d1, _h1) in zip(once, sonra):
        assert tpp0 == 50000 and tpp1 == 500, f"aparat: bobin {i + 1} frekans geçişi yok ({tpp0}→{tpp1})"
        if uni[i]:
            assert d1 <= 499, f"bobin {i + 1} (tek-bacak): {d1} > tpp−1"
            continue
        assert d0 == 24998, f"aparat: bobin {i + 1} 1 Hz'de klemp tavanında değil: {d0}"
        assert d1 <= tavan, (
            f"bobin {i + 1}: frekans artışından hemen sonra duty {d1} > yarım−GAP {tavan} — pending bloğundaki klemp "
            "uygulanmadı/yanlış kipte; period_reset'e kadar köprü boşluğu GAP'in altında"
        )
    sonuc = fw.bacak_analizi(fw.bsrr_olaylari(sat), pinler, sorted(pinler), baslangic_tick=t2)
    kisa = []
    for i, r in sonuc.items():
        if uni[i]:
            continue
        son = {"A": None, "B": None}
        for tick, bacak, seviye, _n, _o in r["kenarlar"]:
            if seviye == 0:
                son[bacak] = tick
            elif (
                son["B" if bacak == "A" else "A"] is not None
                and tick - son["B" if bacak == "A" else "A"] < sabitler["GAP"]
            ):
                kisa.append((i + 1, tick))
        kisa += [(i + 1, c) for c in r["cakisma"]]
    assert kisa == [], f"frekans artışı penceresinde köprü ihlali (bobin, tick): {kisa[:5]}"


# ── D1.27: [FIX-1c] frekans artışında duty oranı ─────────────────────────────


@pytest.mark.parametrize("bobin", [0, 5], ids=["bipolar_1", "tek_bacak_6"])
@pytest.mark.parametrize(("f1", "f2"), [(1, 2), (2, 1)], ids=["artis_1_2Hz", "dusus_2_1Hz"])
def test_KRITIK_D127_frekans_DEGISIMINDE_duty_ORANI_korunur(exe, bobin, f1, f2):
    """%30 (slew tamamlanmış) f1 → f2: g_duty_ticks / g_tpp aynı kalmalı. Ölçeklemesiz eski tick ARTIŞTA yeni
    periyodun %60'ı olur ve klempe kadar şişer (hekimin %30'u yerine ~%50 / ~%60); 1-B bağımsız inceleme (i3):
    DÜŞÜŞ yönü kapısızdı (`!=` → `<` mutantı yeşildi) — orada oran %15'e düşer (eksik doz) ve slew'le geri tırmanır."""
    sat = fw.kos(exe, "isr", 100010, hex(1 << bobin), f1, 0.3, 0, 100000, f2, 0.3, 0)
    s = [d for d in fw.durumlar(sat) if d[1] == bobin]
    once, sonra = s[1], s[2]  # (tick, i, tpp, duty_ticks, hedef): [0]=ilk tick, [1]=t2 öncesi, [2]=t2 sonrası
    assert once[2] == 50000 // f1 and abs(once[3] / once[2] - 0.3) < 1e-3, f"aparat: {f1} Hz %30 kararlı değil: {once}"
    assert sonra[2] == 50000 // f2, f"aparat: {f2} Hz uygulanmadı: {sonra}"
    assert abs(sonra[3] / sonra[2] - 0.3) < 1e-3, (
        f"{f1}→{f2} Hz'de duty oranı {sonra[3] / sonra[2]:.4f} (beklenen 0,30) — [FIX-1c] ölçeklemesi YOK"
    )


# ── İG-8.28 (1-G): periyot ORTASI parametre değişiminde köprü boşluğu ─────────────────────────────────────────────
#
# ÖLÇÜLEN (1-G önce-kırmızı, `f65402b`): `g_shadow.pending` bloğu yeni parametre setini TIM1 ISR'ında periyot ORTASINDA
# uygular — faz değişimi `g_phase_ticks`'i, `ref_ms` hizalaması `g_dds_tick`'i, frekans değişimi `g_tpp`'yi SIÇRATIR →
# `adj` A penceresinden B penceresine (ya da tersine) TEK tick'te geçebilir: kod önce karşı bacağı kapatıp NOP bekler ama
# karşı bacağın DÜŞÜŞÜ ile bu bacağın YÜKSELİŞİ aynı tick'e iner (yapısal boşluk DDS_BIPOLAR_GAP_TICKS = 2 tick İHLAL).
# Sözleşme: süreksizlikte de karşı bacak düşüşü → yükseliş ≥ GAP ve iki bacak ASLA birlikte HIGH değil. N = 2000 rastgele
# deneme (frekans, duty, faz, değişim anı, `ref_ms`); kararlı-durum dalgası değişmez (yukarıdaki kapılar).

#: Rastgele deneme sayısı (yarış/zamanlama kapısı: ≥ 2000 rastgele faz) ve frekans kümesi (tek tpp'li 33 Hz dahil).
_IG828_N = 2000
_IG828_FREK = [33, 50, 100, 200, 400]


def _kopru_ihlalleri(sonuc: dict, ilk_tick: int, gap: int) -> list:
    """(bobin, tick, bacak, boşluk) — karşı bacak düşüşü → bu bacak yükselişi < GAP, ya da iki bacak birlikte HIGH."""
    ihlal = []
    for i, r in sonuc.items():
        son = {"A": None, "B": None}
        for tick, bacak, seviye, _n, _o in r["kenarlar"]:
            if seviye == 0:
                son[bacak] = tick
                continue
            karsi = son["B" if bacak == "A" else "A"]
            if karsi is not None and tick - karsi < gap and tick >= ilk_tick:
                ihlal.append((i + 1, tick, bacak, tick - karsi))
        ihlal += [(i + 1, c, "AB", 0) for c in r["cakisma"] if c >= ilk_tick]
    return ihlal


def test_KRITIK_IG828_periyot_ORTASI_faz_180_degisiminde_GAP_ve_cakisma_YOK(exe, harita, sabitler):
    """Deterministik kol (eski strict-xfail'in ölçtüğü durum): bobin 1, 100 Hz %90, faz 0 → 180, 10 farklı değişim anı."""
    pinler, _uni = harita
    ihlal = []
    for k in range(10):
        t2 = 15000 + 37 * k + 123
        olaylar = fw.bsrr_olaylari(fw.kos(exe, "isr", t2 + 2000, hex(1), 100, 0.9, 0, t2, 100, 0.9, 180))
        r = fw.bacak_analizi(olaylar, pinler, [0], baslangic_tick=t2 - 500)
        ihlal += [(t2, *x) for x in _kopru_ihlalleri(r, t2, sabitler["GAP"])]
    assert ihlal == [], f"periyot ortası faz değişiminde köprü ihlali (t2, bobin, tick, bacak, boşluk): {ihlal[:5]}"


def test_KRITIK_IG828_periyot_ORTASI_parametre_degisiminde_GAP_RASTGELE_2000(exe, harita, sabitler):
    import random

    pinler, uni = harita
    bipolar = [i for i in sorted(pinler) if not uni[i]]
    assert bipolar, "aparat: bipolar bobin yok (kip haritası?)"
    rnd = random.Random(828)
    kotu, ornek = 0, []
    for k in range(_IG828_N):
        f1, f2 = rnd.choice(_IG828_FREK), rnd.choice(_IG828_FREK)
        d1, d2 = round(rnd.uniform(0.2, 0.95), 4), round(rnd.uniform(0.2, 0.95), 4)
        p1, p2 = round(rnd.uniform(0.0, 359.9), 2), round(rnd.uniform(0.0, 359.9), 2)
        tpp1, tpp2 = int(50000 / f1), int(50000 / f2)
        t2 = 15000 + rnd.randrange(2 * tpp1)
        ek = [rnd.randrange(0, 100000)] if k % 3 == 0 else []  # her 3 denemeden biri HW_SYNC ref_ms hizalaması
        sat = fw.kos(exe, "isr", t2 + 3 * tpp2 + 50, hex(_GENIS), f1, d1, p1, t2, f2, d2, p2, *ek)
        sonuc = fw.bacak_analizi(fw.bsrr_olaylari(sat), pinler, bipolar, baslangic_tick=t2 - tpp1)
        ih = _kopru_ihlalleri(sonuc, t2, sabitler["GAP"])
        if ih:
            kotu += 1
            if len(ornek) < 3:
                ornek.append(((f1, d1, p1), (f2, d2, p2), t2, ek, ih[:2]))
    print(f"IG828_ORAN kirmizi={kotu}/{_IG828_N} ornek={ornek}")
    assert kotu == 0, (
        f"periyot ortası parametre değişiminde {kotu}/{_IG828_N} rastgele denemede köprü boşluğu (GAP={sabitler['GAP']}) "
        f"ihlali ya da A+B birlikte HIGH — örnek ((f1,d1,p1),(f2,d2,p2),t2,ref_ms,ihlal): {ornek}"
    )


# ── 1G-YB2 (1-G yeni bulgu — İG-8.28'in yan etkisi): UÇ FREKANSTA bipolar iki bacak da sürülür ─────────────────
#: tpp < 6'da (f > 8,33 kHz) klemp `max_d < 1 → 1` → kararlı dalganın KENDİ boşluğu GAP'ten küçüktür (yarım − 1). İG-8.28
#: kuralı her tpp'de GAP istediği için B bacağı HİÇ açılmıyordu (ölçüldü: f5f417e öncesi 10 kHz %50'de 3000 B darbesi,
#: sonrası 0) — sürüş tek bacağa düşüyor, ACK `K=` bipolar diyordu. KARARLI listesi yalnız 33-100 Hz idi. (Hz, tpp)
UC_FREKANS = [(8333, 6), (10000, 5), (12500, 4), (16666, 3), (25000, 2)]


def _tasarim_boslugu(tpp: int, gap: int) -> int:
    """Klemp sonrası KARARLI bipolar dalganın karşı bacak düşüşü → yükseliş boşluğu (tick): yarım − max(1, yarım − GAP)."""
    yarim = tpp // 2
    return yarim - max(1, yarim - gap)


@pytest.mark.parametrize(("frek", "tpp"), UC_FREKANS, ids=[f"{f}Hz_tpp{t}" for f, t in UC_FREKANS])
def test_KRITIK_1GYB2_uc_frekansta_bipolar_IKI_bacak_surulur_bosluk_TASARIMDAN_kisa_degil(
    exe, harita, sabitler, frek, tpp
):
    assert int(50000.0 / frek) == tpp, "aparat: frekans → tpp eşlemesi"
    _pinler, uni = harita
    sonuc = _kararli(exe, harita, frek=frek, duty=0.5)
    gerekli = _tasarim_boslugu(tpp, sabitler["GAP"])
    for i, r in sonuc.items():
        A, B = _darbe_genislikleri(r["kenarlar"], "A"), _darbe_genislikleri(r["kenarlar"], "B")
        if uni[i]:
            assert A and not B, f"bobin {i + 1} (tek-bacak): A={len(A)} B={len(B)}"
            continue
        assert A and B and abs(len(A) - len(B)) <= 1, (
            f"bobin {i + 1} @ {frek} Hz (tpp {tpp}): A darbesi {len(A)}, B darbesi {len(B)} — bipolar TEK bacağa düştü"
        )
        ihlal = _kopru_ihlalleri({i: r}, 0, gerekli)
        assert ihlal == [], f"bobin {i + 1}: çakışma ya da boşluk tasarım değerinin ({gerekli}) altında: {ihlal[:4]}"


# ── AÇIK işaretler (uydurma ölçüm yok) ───────────────────────────────────────


@pytest.mark.skip(
    reason="TEZGÂH (Oturum 13, İG-8.28): gerçek bacak aralığı ve NOP süresi (ns) osiloskopla ölçülür; "
    "ana makine aparatı tick/sayı ölçer, süre ölçemez — burada uydurulmaz."
)
def test_TEZGAH_gercek_bacak_araligi_ve_NOP_suresi_osiloskopla():
    raise AssertionError("tezgâhta ölçülecek")


# ── D1.23 davranış kolu: hata anında bobin kesme (1-B bağımsız inceleme i3) ─────────────────────────────
#
# D1.23 kapısı Error_Handler'daki ÇAĞRIYI yorumsuz metinde arıyordu; `PEMF_ForceAllCoilOutputsLow` GÖVDESİ yoruma
# alınınca (çağrı durur, hiçbir pin kesilmez) ve çağrı `#if 0` içine alınınca 29 STM kapı dosyası 300/300 YEŞİLDİ.
# Artık GERÇEK fonksiyonlar aparatta koşar: bobinler sürülürken çağrılır, BSRR günlüğünde 7 bobinin 14 bacağına da
# RESET yazımı ve `g_prev_state == 2` (IDLE) iddia edilir; Error_Handler kesmeleri kapatmaya ÖNCE kesip varmalı.


@pytest.mark.parametrize("kip", ["zorla", "hata"], ids=["ForceAllCoilOutputsLow", "Error_Handler"])
def test_KRITIK_D123_hata_aninda_TUM_bobin_bacaklari_LOW(exe, harita, kip):
    pinler, _uni = harita
    sat = fw.kos(exe, kip, 15100, hex(_GENIS), 100, 0.9, 0)
    assert "BASLA" in sat, f"aparat: {kip} kipi koşmadı"
    bas = sat.index("BASLA")
    once = fw.bacak_analizi(fw.bsrr_olaylari(sat[:bas]), pinler, sorted(pinler))
    assert all(r["kenarlar"] for r in once.values()), "aparat: çağrıdan önce bobinler sürülmüyordu (vakum)"
    olaylar = fw.bsrr_olaylari(sat[bas:])
    resetlenen = {
        (port, pin)
        for _t, port, deger, _n in olaylar
        for (pa, ia, pb, ib) in pinler.values()
        for (p, pin) in ((pa, ia), (pb, ib))
        if port == p and (deger >> 16) & pin
    }
    beklenen = {(p, pin) for (pa, ia, pb, ib) in pinler.values() for (p, pin) in ((pa, ia), (pb, ib))}
    assert resetlenen == beklenen, f"{kip}: LOW'a çekilmeyen bacak(lar): {sorted(beklenen - resetlenen)}"
    durum = {int(p[1]): int(p[2]) for p in (s.split() for s in sat[bas:]) if p and p[0] == "P"}
    assert durum == {i: 2 for i in pinler}, f"{kip}: g_prev_state IDLE (2) değil: {durum}"
    if kip == "hata":
        assert "IRQ" in sat[bas:], "Error_Handler kesmeleri kapatmaya varmadı (aparat kancası)"
        irq = sat.index("IRQ")
        assert all(sat.index(s) < irq for s in sat[bas:irq] if s.startswith("B ")), (
            "bobin kesme kesmeler kapatıldıktan SONRA"
        )
