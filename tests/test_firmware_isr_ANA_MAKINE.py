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

Aparat: `tests/firmware_host_aparat.py` + `tests/firmware_host/` (BSRR yazım sırası ve NOP sayısı kaydedilir;
pin haritası main.c'nin kendi `coil_gpio` tablosundan). ⚠️ Derleyici yoksa FAIL (SKIP değil).

⚠️ AÇIK (uydurma ölçüm YOK): periyot ORTASINDA parametre değişimi (İG-8.28) bugün köprü değişmezini bozabiliyor —
o kol `xfail(strict=True)` (İG-8.28 düzeltilince XPASS → KIRMIZI, işaret kaldırılır). Gerçek bacak aralığı ve NOP
SÜRESİ (ns) yalnız tezgâhta osiloskopla ölçülür (Oturum 13) — ana makine aparatı tick ve sayı ölçer, süre değil.
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


def _kararli(exe, harita, frek=100, duty=0.9, faz=0):
    pinler, _uni = harita
    n = 30000  # 60 periyot @100 Hz; slew en geç ~18 periyotta tavana varır
    olaylar = fw.bsrr_olaylari(fw.kos(exe, "isr", n, hex(_GENIS), frek, duty, faz))
    return fw.bacak_analizi(olaylar, pinler, sorted(pinler), baslangic_tick=15000)


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


def test_KRITIK_D125_iki_bacak_ASLA_ayni_anda_HIGH(exe, harita):
    sonuc = _kararli(exe, harita)
    cakisma = {i + 1: r["cakisma"][:3] for i, r in sonuc.items() if r["cakisma"]}
    assert cakisma == {}, f"SHOOT-THROUGH: aynı anda A ve B HIGH (bobin: ilk tick'ler) {cakisma}"
    assert all(r["kenarlar"] for r in sonuc.values()), "aparat: bazı bobinler hiç sürülmedi (vakum)"


def test_KRITIK_D126_her_acilista_ONCE_karsi_bacak_kapanir_ve_NOP_olu_zaman(exe, harita, sabitler):
    pinler, uni = harita
    sonuc = _kararli(exe, harita)
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


def test_KRITIK_D126_D128_karsi_bacak_dususu_ile_yukselis_arasi_GAP_ve_darbeler_SIMETRIK(exe, harita, sabitler):
    pinler, uni = harita
    sonuc = _kararli(exe, harita)
    tpp, gap = 500, sabitler["GAP"]
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
def test_KRITIK_D127_frekans_ARTISINDA_duty_ORANI_korunur(exe, bobin):
    """1 Hz %30 (slew tamamlanmış) → 2 Hz: g_duty_ticks / g_tpp aynı kalmalı. Ölçeklemesiz eski tick yeni periyodun
    %60'ı olur ve klempe kadar şişer (hekimin %30'u yerine ~%50 / ~%60)."""
    sat = fw.kos(exe, "isr", 100010, hex(1 << bobin), 1, 0.3, 0, 100000, 2, 0.3, 0)
    s = [d for d in fw.durumlar(sat) if d[1] == bobin]
    once, sonra = s[1], s[2]  # (tick, i, tpp, duty_ticks, hedef): [0]=ilk tick, [1]=t2 öncesi, [2]=t2 sonrası
    assert once[2] == 50000 and abs(once[3] / once[2] - 0.3) < 1e-3, f"aparat: 1 Hz %30 kararlı değil: {once}"
    assert sonra[2] == 25000, f"aparat: 2 Hz uygulanmadı: {sonra}"
    assert abs(sonra[3] / sonra[2] - 0.3) < 1e-3, (
        f"frekans artışında duty oranı {sonra[3] / sonra[2]:.4f} (beklenen 0,30) — [FIX-1c] ölçeklemesi YOK"
    )


# ── AÇIK işaretler (uydurma ölçüm yok) ───────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason="AÇIK İG-8.28 (tezgâh, Oturum 13): periyot ORTASINDA faz değişimi bugün köprü değişmezini bozabiliyor "
    "(plan ölçümü: faz 0→180'de 57/100). Düzeltilince XPASS → KIRMIZI: işareti kaldırın.",
)
def test_ACIK_IG828_periyot_ORTASI_faz_degisiminde_de_GAP_ve_cakisma_yok(exe, harita, sabitler):
    pinler, _uni = harita
    ihlal = []
    for k in range(10):
        t2 = 15000 + 37 * k + 123
        olaylar = fw.bsrr_olaylari(fw.kos(exe, "isr", t2 + 2000, hex(1), 100, 0.9, 0, t2, 100, 0.9, 180))
        r = fw.bacak_analizi(olaylar, pinler, [0], baslangic_tick=t2)[0]
        son = {"A": None, "B": None}
        for tick, bacak, seviye, _n, _o in r["kenarlar"]:
            if seviye == 0:
                son[bacak] = tick
            elif (
                son["B" if bacak == "A" else "A"] is not None
                and tick - son["B" if bacak == "A" else "A"] < sabitler["GAP"]
            ):
                ihlal.append((t2, tick))
        ihlal += [(t2, c) for c in r["cakisma"]]
    assert ihlal == [], f"periyot ortası değişimde köprü ihlali: {ihlal[:5]}"


@pytest.mark.skip(
    reason="TEZGÂH (Oturum 13, İG-8.28): gerçek bacak aralığı ve NOP süresi (ns) osiloskopla ölçülür; "
    "ana makine aparatı tick/sayı ölçer, süre ölçemez — burada uydurulmaz."
)
def test_TEZGAH_gercek_bacak_araligi_ve_NOP_suresi_osiloskopla():
    raise AssertionError("tezgâhta ölçülecek")
