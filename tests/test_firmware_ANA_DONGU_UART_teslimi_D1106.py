# Author: mertaygn, cglrgrkn
"""D1.106 · B-8.2 · B-8.3 · B-8.4 — STM ana döngüsünde TEK UART TX'ini paylaşan satırların TESLİMİ.

GERÇEK firmware + GERÇEK HAL 1.8.5 ana makinede koşar (`tests/firmware_dongu_aparat.py`, `tests/firmware_host/dongu/`:
VEH + tek adım yazmaç modeli, sanal zaman; USART3 bayt süresi BRR'den). Model: 5 ACS712 kalibre (ADC kanal 0/3/4/10/13,
2,5 V), I2C1'de MLX90614 (0x5A), I2C2'de MLX90393 (0x18). Paketler backend'in GERÇEK paket kurucusundan
(`HardwareController`, `kayitci_donanim.gercek_hc`; 121 bayt, CRC32), 115200 baud'la hatta verilir.

ÖLÇÜLEN KUSUR (1-G önce-kırmızı; plan D1.106): akım turu (~1,2 ms) her turda TX boşsa YALNIZ C1 satırını basıyor,
ardından `gState != READY → break` → C2..C5 HİÇ gitmiyor, TX neredeyse hep meşgul. ACK yalnız TX boşken basılıyor
(çoğu düşüyor), READY ping'i / "Watchdog Timeout" / STM_STOPPED `HAL_UART_Transmit_IT`'in HAL_BUSY'sinde sessizce düşüyor,
NACK'in bloklayan `HAL_UART_Transmit`'i TX meşgulken HAL_BUSY dönüyor. I2C1'in T= satırı TX'i meşgul edince I2C2'nin
B= satırı aynı turda HER ZAMAN düşüyor; MAGCHK TX boş olmadıkça basılamıyor.

SÖZLEŞME (plan D1.106 kapısı): 40 geçerli paketin ≥ %95'ine STM_OK (kapı 40/40 ister — test notu); 78 bozuk pakete 78 STM_NACK
(paket başına tohumlu rastgele faz); I2C1 T=, I2C2 B= ve
C1..C5'in HER birinden ≥ 1 satır; ≥ 1 STM_MAGCHK; 20 sn paketsiz bekleyişte READY ping'i 10/10; sessizlikte
"Watchdog Timeout" satırı teslim. Bobin kesme (1500 ms ölü adam) değişmez — termal kesme EKLENMEZ.

⚠️ TEZGÂH (Oturum 13): gerçek UART zamanlaması, bağlı ACS712 / I2C hattı ve MAGCHK kartta ölçülür; bu takım ön kapıdır.
⚠️ Yalnız Windows (VEH): başka platformda açık gerekçeyle atlanır (Linux portu YOK — rapor: açık madde).
"""

from __future__ import annotations

import random
import re
import sys
import threading

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="ana döngü koşum takımı Windows VEH'e dayanır; Linux portu YOK (DUZELTME-D1G açık madde)",
)

ACS_KANALLARI = (0, 3, 4, 10, 13)  # pemf_akim.c g_kanal: bobin 1..5
PAKET_N = 40
#: Bozuk paket: her 500 ms aralığa İKİ (+170 / +340 ms, ±30 ms faz) → 78 NACK. Düzeltme sonrası TX çoğunlukla boş;
#: 20 NACK'te bloklayan eski NACK (TX meşgulse HAL_BUSY) hiç meşgule denk gelmedi (mutant YEŞİL kaldı, 1-G) —
#: 78 NACK telemetri/ACK satırlarıyla çakışır. Plan ölçümü: eski kodda NACK'lerin 20'de 8'i teslim.
BOZUK_ARALIK_N = PAKET_N - 1
BOZUK_N = 2 * BOZUK_ARALIK_N
PAKET_BAS_US = 2_500_000
PAKET_ARA_US = 500_000  # backend keep-alive 2 Hz
FAZ_US = 100_000  # her pakete tohumlu rastgele 0-100 ms kayma: telemetri turuna göre 40 + 20 farklı faz
SON_PAKET_US = PAKET_BAS_US + (PAKET_N - 1) * PAKET_ARA_US + FAZ_US
TESLIM_SURE_US = SON_PAKET_US + 2_500_000  # son paketten 1,5 sn sonra ölü adam → satır
READY_SURE_US = 21_000_000  # paketsiz: 2,4,…,20 sn → 10 READY ping'i
WDT_N = 10  # ölü adam olayı: tek geçerli paket (bobinler açılır) → 1,5 sn sessizlik → bobinler 0 + satır
WDT_ARA_US = 2_200_000
WDT_SURE_US = PAKET_BAS_US + WDT_N * WDT_ARA_US + 500_000
#: YÜK: geçerli CRC'li ama bobin 1 frekansı alan dışı (0,5 Hz < FREQ_MIN) paket → "RANGE … field=freq …" NACK (~88 bayt,
#: ≈ 7,6 ms TX). 25 ms arayla → TX ~%30 meşgul. Düzeltme sonrası telemetri TX'i ~%5 meşgul ettiği için doğrudan
#: `HAL_UART_Transmit_IT` (READY / Watchdog) ya da bloklayan NACK YÜKSÜZ senaryoda çoğunlukla geçiyordu (mutantlar YEŞİL
#: kaldı, 1-G) — yükte çakışır. En uzun satır (~11 ms) < 25 ms → yuvadaki NACK bir sonrakiyle ezilmez.
YUK_ARA_US = 25_000


def _paketler() -> list[bytes]:
    """Backend'in GERÇEK paketleri: bobin 1-5 100 Hz %40 5 dk başlatılır, sonra keep-alive tekrarları."""
    from kayitci_donanim import gercek_hc, paket_coz

    with gercek_hc() as hc:
        for cid in range(1, 6):
            hc.update_coil(cid, 100, 40, 0, 5, start=True)
        q = hc.core._hw_send_queue.paketler
        while len(q) < PAKET_N:
            hc._send_stm_manual_update()
        paketler = list(q[:PAKET_N])
    assert len(paketler) == PAKET_N, f"aparat: {len(paketler)} paket"
    assert all(len(p) == 121 for p in paketler), "aparat: paket boyu 121 değil"
    son = paket_coz(paketler[-1])[0]
    assert all(son[i] > 0 for i in range(5)), f"aparat: bobin 1-5 sürülmüyor (duty {son})"
    return paketler


def _alan_disi_paket() -> bytes:
    """Backend paket biçimiyle (STM_PAKET_FMT + CRC32) GEÇERLİ CRC'li ama alan dışı paket: firmware CRC'yi geçer, alan
    doğrulamasında uzun gerekçeli NACK döner; PWM'e dokunmaz (`last_communication_ms` tazelenmez)."""
    import struct
    import zlib

    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_FMT

    n = STM_PAKET_BOBIN_SAYISI
    veri = struct.pack(
        STM_PAKET_FMT,
        0xAA,
        0x55,
        *([0.4] + [0.0] * (n - 1)),
        *([0.0] * n),
        *([0.5] + [100.0] * (n - 1)),
        *([5] + [0] * (n - 1)),
        0,
        0,
    )
    return veri + struct.pack("<I", zlib.crc32(veri) & 0xFFFFFFFF)


def _senaryo(sure_us: int, paketler: list[tuple[int, bytes]]) -> str:
    s = [f"SURE_US {sure_us}", "ERISIM_NS 50", "GETTICK_NS 1000"]
    s += [f"ACS {k} 2500" for k in ACS_KANALLARI]
    s += ["I2C 1 MLX90614 5A", "I2C 2 MLX90393 18"]
    s += [f"PAKET {t} {p.hex()}" for t, p in paketler]
    return "\n".join(s) + "\n"


@pytest.fixture(scope="module")
def kosular(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("dongu")
    exe = da.derle(dizin)
    iyi = _paketler()
    bozuk = bytearray(iyi[0])
    bozuk[-1] ^= 0xFF  # CRC32'nin son baytı → firmware "-> STM_NACK: CRC"
    rnd = random.Random(1106)
    akis = [(PAKET_BAS_US + k * PAKET_ARA_US + rnd.randrange(FAZ_US), p) for k, p in enumerate(iyi)]
    # bozuk paketler iki geçerli paketin ARASINA (≥ 150 ms boşluk; 121 bayt ≈ 10,5 ms)
    for k in range(BOZUK_ARALIK_N):
        taban = PAKET_BAS_US + k * PAKET_ARA_US + FAZ_US
        akis += [
            (taban + 70_000 + rnd.randrange(60_000), bytes(bozuk)),
            (taban + 240_000 + rnd.randrange(60_000), bytes(bozuk)),
        ]
    akis.sort()
    wdt = [(PAKET_BAS_US + k * WDT_ARA_US + rnd.randrange(FAZ_US), iyi[-1]) for k in range(WDT_N)]
    yuk = _alan_disi_paket()
    ready_yuk = [(t, yuk) for t in range(1_000_000, READY_SURE_US - 500_000, YUK_ARA_US)]
    # yük sessizliğin TAMAMINDA ve ölü adam anında da sürer (bir sonraki geçerli pakete dek, t + 1,925 sn)
    wdt_yuk = [(t + 50_000 + j * YUK_ARA_US, yuk) for t, _p in wdt for j in range(76)]
    senaryolar = {
        "teslim": _senaryo(TESLIM_SURE_US, akis),
        "ready": _senaryo(READY_SURE_US, ready_yuk),
        "wdt": _senaryo(WDT_SURE_US, sorted(wdt + wdt_yuk)),
    }
    sonuc: dict = {}

    def _kos(ad):
        try:
            sonuc[ad] = da.kos(exe, senaryolar[ad], dizin, ad, sinir_sn=1500)
        except BaseException as e:  # pragma: no cover - aparat tanısı
            sonuc[ad] = e

    isler = [threading.Thread(target=_kos, args=(ad,)) for ad in senaryolar]
    for t in isler:
        t.start()
    for t in isler:
        t.join()
    for ad, v in sonuc.items():
        if isinstance(v, BaseException):
            raise v
    sonuc["son_iyi_us"] = max(t for t, p in akis if p != bytes(bozuk))
    sonuc["wdt_paket_us"] = [t for t, _p in wdt]
    sonuc["ready_yuk_n"], sonuc["wdt_yuk_n"] = len(ready_yuk), len(wdt_yuk)
    return sonuc


def _satirlar(k, desen: str) -> list:
    r = re.compile(desen)
    return [x for x in k["satirlar"] if r.search(x[2])]


# ── aparat kanıtı (ölçüm aracı ne ölçüyor?) ───────────────────────────────────


def test_APARAT_acilis_cihazlari_gorur_ve_bayt_suresi_BRR_den(kosular):
    k = kosular["ready"]
    sens = [x[2] for x in _satirlar(k, r"STM_SENS: C=6 I2C")]
    assert any("I2C1 sicaklik=0x5A alan=0x00" in s for s in sens), f"aparat: I2C1 MLX90614 görülmedi: {sens}"
    assert any("I2C2 sicaklik=0x00 alan=0x18" in s for s in sens), f"aparat: I2C2 MLX90393 görülmedi: {sens}"
    son = k["son"]
    brr, pclk1 = int(son["brr"], 16), int(son["pclk1"])
    assert (brr, pclk1) == (0x16C, 42_000_000), f"aparat: HAL BRR/PCLK1 beklenmedik: {son}"
    bayt_us = 10 * brr / pclk1 * 1e6
    banner = _satirlar(k, r"STM_READY:")[0]
    beklenen = (len(banner[2]) + 2) * bayt_us  # \r\n dahil
    assert abs((banner[1] - banner[0]) - beklenen) <= 2 * bayt_us, (
        f"aparat: banner süresi {banner[1] - banner[0]} µs, BRR'den beklenen {beklenen:.0f} µs"
    )


# ── D1.106 kapısı ─────────────────────────────────────────────────────────────


def test_KRITIK_D1106_40_paketin_HER_birine_STM_OK(kosular):
    """Plan eşiği ≥ %95; düzeltilmiş zamanlayıcı DETERMİNİSTİK olarak 40/40 verir (paketler 500 ms arayla, ACK yuvası
    bir sonraki pakete dek boşalır) → kapı 40/40 ister: "TX meşgulse ACK'i atla" gibi seyrek kayıp da KIRMIZI olsun."""
    ack = _satirlar(kosular["teslim"], r"^-> STM_OK: D=")
    assert len(ack) == PAKET_N, (
        f"40 geçerli paketin {len(ack)}'ine STM_OK teslim edildi (plan ≥ {int(0.95 * PAKET_N)}; düzeltme 40/40) — ACK, "
        "TX telemetriyle meşgulken basılmıyor"
    )


def test_KRITIK_D1106_bozuk_paketlerin_HER_birine_STM_NACK(kosular):
    nack = _satirlar(kosular["teslim"], r"^-> STM_NACK: ")
    assert len(nack) == BOZUK_N, f"{BOZUK_N} bozuk pakete {len(nack)} STM_NACK teslim edildi"


def test_KRITIK_D1106_sessizlikte_Watchdog_Timeout_satiri_TESLIM(kosular):
    wdt = _satirlar(kosular["teslim"], r"Watchdog Timeout")
    assert wdt and wdt[0][0] >= kosular["son_iyi_us"] + 1_500_000, (
        f"son paketten 1,5 sn sonra 'Watchdog Timeout' satırı teslim edilmedi (bulunan: {wdt[:2]})"
    )


def _acik_araliklar(aktif: list) -> list:
    """Sondanın etkin-maske değişimlerinden (açılış_us, kapanış_us) aralıkları."""
    araliklar, ac = [], None
    for t_us, maske in aktif:
        if maske and ac is None:
            ac = t_us
        elif not maske and ac is not None:
            araliklar.append((ac, t_us))
            ac = None
    if ac is not None:
        araliklar.append((ac, 10**12))
    return araliklar


def test_KRITIK_D1106_HER_olu_adam_kesmesinde_Watchdog_satiri_10_10(kosular):
    """Ölü adam (1500 ms) bobinleri her olayda keser — bu kapı yalnız SATIRIN teslimini ölçer; tek olay faza bağlıdır
    (TX o an boşsa eski kod da teslim ederdi) → 10 olay, her biri farklı fazda. Sonda (etkin bobin maskesi) bobinlerin
    gerçekten 1,5 sn açık kalıp ölü adamla kapandığı olayları ayırır: başlangıçta ERKEN kapanan olay (süre denetimi
    yarışı — ayrı madde, 1-G yeni bulgu) bu kapının konusu değildir; sayısı iletide görünür."""
    k = kosular["wdt"]
    wdt = _satirlar(k, r"Watchdog Timeout")
    araliklar = _acik_araliklar(k["aktif"])
    uygun, erken = [], []
    for t in kosular["wdt_paket_us"]:
        a = next(((ac, kp) for ac, kp in araliklar if t <= ac < t + 50_000), None)
        if a is None:
            continue
        (uygun if a[1] >= t + 1_450_000 else erken).append(t)
    teslim = [t for t in uygun if any(t + 1_500_000 <= x[0] < t + WDT_ARA_US for x in wdt)]
    assert len(uygun) >= 5, f"aparat: yalnız {len(uygun)} ölü adam olayı ölçülebildi (erken kapanan: {len(erken)})"
    assert len(teslim) == len(uygun), (
        f"bobinlerin ölü adamla kesildiği {len(uygun)} olayın {len(teslim)}'inde 'Watchdog Timeout' satırı teslim edildi "
        f"(başlangıçta erken kapanan olay: {len(erken)})"
    )


@pytest.mark.parametrize("kaynak", ["I2C1_T", "I2C2_B", "C1", "C2", "C3", "C4", "C5", "MAGCHK"])
def test_KRITIK_D1106_her_telemetri_KAYNAGINDAN_en_az_bir_satir(kosular, kaynak):
    desen = {
        "I2C1_T": r"^-> STM_TELE: C=6,T=",
        "I2C2_B": r"^-> STM_TELE: C=6,B=",
        "MAGCHK": r"^-> STM_MAGCHK: C=6 ",
    }.get(kaynak, rf"^-> STM_TELE: C={kaynak[1:]},I=")
    bulunan = _satirlar(kosular["teslim"], desen)
    assert bulunan, f"{kaynak} kaynağından HİÇ satır teslim edilmedi (desen {desen!r})"


def test_KRITIK_D1106_paketsiz_beklemede_READY_pingi_10_10(kosular):
    ready = [x for x in _satirlar(kosular["ready"], r"^-> STM_READY: ") if x[0] > 1_000_000]  # açılış banner'ı hariç
    assert len(ready) == 10, f"20 sn paketsiz beklemede {len(ready)}/10 READY ping'i teslim edildi"


#: Akım satırı hızı (bobin başına satır/sn) — firmware sabitinden OKUNMAZ (kapı sabiti mutasyon hedefinden okunursa
#: kördür). Üst sınır: hız sınırı yokken C1 ~400/sn basılıyor, TX'i dolduruyordu (backend'i de boğar); alt sınır:
#: backend'in tazelik penceresi 5 sn (ALAN_TAZELIK_S) — 2 sn'de bir satır rahatça yeter.
AKIM_HIZ_UST, AKIM_HIZ_ALT = 2.5, 0.5


@pytest.mark.parametrize("bobin", [1, 2, 3, 4, 5])
def test_KRITIK_D1106_akim_telemetrisi_HIZ_SINIRLI_ve_SUREKLI(kosular, bobin):
    k = kosular["teslim"]
    bas_us, bit_us = 3_000_000, kosular["son_iyi_us"]
    n = len([x for x in _satirlar(k, rf"^-> STM_TELE: C={bobin},I=") if bas_us <= x[0] < bit_us])
    hiz = n / ((bit_us - bas_us) / 1e6)
    assert AKIM_HIZ_ALT <= hiz <= AKIM_HIZ_UST, (
        f"bobin {bobin} akım satırı {hiz:.1f}/sn (beklenen {AKIM_HIZ_ALT}-{AKIM_HIZ_UST}/sn) — hız sınırı yok ya da satır düşüyor"
    )


def test_KRITIK_D1106_YUK_altinda_HER_alan_disi_pakete_NACK(kosular):
    """`ready` + `wdt` senaryolarındaki alan dışı paketlerin HER birine NACK (TX ~%30 meşgulken)."""
    for ad, n in (("ready", kosular["ready_yuk_n"]), ("wdt", kosular["wdt_yuk_n"])):
        nack = _satirlar(kosular[ad], r"^-> STM_NACK: RANGE coil=1 field=freq")
        assert len(nack) == n, f"{ad}: yük altında {n} alan dışı paketin {len(nack)}'ine NACK teslim edildi"
