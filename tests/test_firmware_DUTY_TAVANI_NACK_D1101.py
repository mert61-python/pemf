# Author: mertaygn, cglrgrkn
"""D1.101 · B-8.13 · Y20 (sahip) — STM duty ÜST sınırı SESSİZ kırpılmaz: tavan üstü istek kartça NACK'lenir.

ÖLÇÜLEN KUSUR (DENETIM-08 §B-8.13): firmware duty için yalnız ALT sınırı NACK'liyordu; bipolar bobinde 0,8 istenince
ACK `D=80` yankılanıyor, ISR klempi etkin pencereyi ~0,4996'ya kırpıyor, arayüz 80 gösteriyordu (gösterilen ≠ uygulanan).
Sahip Y20: "Bipolar tavan üstü duty isteğini FIRMWARE NACK'ler … Backend'e ve arayüze duty sınırı EKLENMEZ. Sistematik
NACK seansı durdurur; operatör nedenini açıkça görmeli."

Ölçüm aracı: ana döngü koşum takımı (`tests/firmware_dongu_aparat.py`; GERÇEK main.c + HAL 1.8.5, sanal zaman) ve
salt-okur sonda (etkin bobin maskesi `g_active`). Paketler backend'in GERÇEK kurucusundan (`HardwareController`).
Her vaka: tüm bobinler durdurulur → (varsa) ön paket → vaka paketi; kartın yanıtı (STM_OK / STM_NACK) ve maske okunur.

SÖZLEŞME:
  * bipolar bobinde duty > 0,5 → `STM_NACK: RANGE coil=<n> field=duty value_milli=<v> max_milli=500 kip=bipolar`,
    bobin HİÇ etkin olmaz; ölçüt ORANDIR (25 kHz'de tpp=2: tick ölçütü 0,99'u "kabul" ederdi);
  * tek-bacak (yetenek 0x60 YA DA Sürüş Kipi isteği) → tavan 1,0 (> 1,0 → `kip=unipolar`);
  * tavana EŞİT istek KABUL (AI Pro'nun 0,50 normalize tavanı reddedilmez); reddedilen paket çalışan bobine DOKUNMAZ;
  * simülatör (`tools/stm32_simulator.decode_packet`) aynı paketi AYNI metinle reddeder / aynı biçimde kabul eder.
⚠️ TEZGÂH (Oturum 13): kartta doğrulanır. ⚠️ Yalnız Windows (VEH): başka platformda gerekçeli SKIP (Linux portu YOK) —
simülatör kolu (`test_stm32_simulator_firmware_hizasi.py`) her platformda koşar.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="ana döngü koşum takımı Windows VEH'e dayanır; Linux portu YOK (DUZELTME-D1G açık madde)",
)

BAS_US = 2_500_000
VAKA_US = 300_000
ON_US = 100_000  # vaka başından ön pakete
PAKET_US = 150_000  # vaka başından vaka paketine
YANIT_US = 120_000  # vaka paketinden sonra yanıt penceresi


def _red(bobin: int, istenen: int, tavan: int, kip: str) -> tuple:
    return ("NACK", f"RANGE coil={bobin} field=duty value_milli={istenen} max_milli={tavan} kip={kip}")


#: (ad, ön komutlar, vaka komutları, kip isteği, beklenen) — komut = (bobin, Hz, %duty).
#: beklenen: ("NACK", "<firmware metni>") | ("OK", {bobin: ACK D yüzdesi}). Beklenen metin BURADA yazılı (kaynaktan okunmaz).
VAKALAR = [
    ("bipolar_80", [], [(1, 100.0, 80.0)], 0x00, _red(1, 800, 500, "bipolar")),
    ("bipolar_son_bobin_80", [], [(5, 100.0, 80.0)], 0x00, _red(5, 800, 500, "bipolar")),
    ("bipolar_50_TAVANA_ESIT", [], [(1, 100.0, 50.0)], 0x00, ("OK", {1: 50})),
    ("bipolar_50_1_ORAN_olcutu", [], [(1, 100.0, 50.1)], 0x00, _red(1, 501, 500, "bipolar")),
    ("bipolar_25kHz_99_TICK_deligi", [], [(1, 25000.0, 99.0)], 0x00, _red(1, 990, 500, "bipolar")),
    ("bipolar_25kHz_50", [], [(1, 25000.0, 50.0)], 0x00, ("OK", {1: 50})),
    ("unipolar_yetenek_6_80", [], [(6, 100.0, 80.0)], 0x00, ("OK", {6: 80})),
    ("unipolar_yetenek_7_100", [], [(7, 100.0, 100.0)], 0x00, ("OK", {7: 100})),
    ("unipolar_yetenek_6_120", [], [(6, 100.0, 120.0)], 0x00, _red(6, 1200, 1000, "unipolar")),
    ("unipolar_ISTEK_1_80", [], [(1, 100.0, 80.0)], 0x01, ("OK", {1: 80})),
    (
        "calisan_bobin_2_ve_1_80",
        [(2, 100.0, 30.0)],
        [(2, 100.0, 30.0), (1, 100.0, 80.0)],
        0x00,
        _red(1, 800, 500, "bipolar"),
    ),
]


def _hc_paketi(komutlar, kip: int) -> bytes:
    from kayitci_donanim import gercek_hc
    from servers import live_state as ls

    ls.stm_komut_kabulu_bildir()  # HC başlatma kapısı süreç-geneli red kararına (önceki testlerden) takılmasın
    with gercek_hc() as hc:
        hc.surus_kipi_ayarla(kip)
        for bobin, hz, duty in komutlar:
            assert hc.update_coil(bobin, hz, duty, 0.0, 5, start=True) is True, f"aparat: HC {bobin}'i kabul etmedi"
        return hc.core._hw_send_queue.paketler[-1]


def _durdurma_paketi() -> bytes:
    from kayitci_donanim import gercek_hc

    with gercek_hc() as hc:
        hc.stop_all_coils()
        return hc.core._hw_send_queue.paketler[-1]


@pytest.fixture(scope="module")
def kosu(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("d1101")
    exe = da.derle(dizin)
    dur = _durdurma_paketi()
    akis, plan = [], []
    for k, (ad, on, vaka, kip, beklenen) in enumerate(VAKALAR):
        t0 = BAS_US + k * VAKA_US
        akis.append((t0, dur))
        if on:
            akis.append((t0 + ON_US, _hc_paketi(on, 0x00)))
        paket = _hc_paketi(vaka, kip)
        akis.append((t0 + PAKET_US, paket))
        plan.append(
            {
                "ad": ad,
                "t": t0 + PAKET_US,
                "son": t0 + VAKA_US,
                "paket": paket,
                "beklenen": beklenen,
                "on": [b for b, *_ in on],
                "vaka": [b for b, *_ in vaka],
            }
        )
    s = ["SURE_US %d" % (BAS_US + len(VAKALAR) * VAKA_US), "ERISIM_NS 50", "GETTICK_NS 1000"]
    s += [f"ACS {k} 2500" for k in (0, 3, 4, 10, 13)]
    s += ["I2C 1 MLX90614 5A", "I2C 2 MLX90393 18"]
    s += [f"PAKET {t} {p.hex()}" for t, p in akis]
    k = da.kos(exe, "\n".join(s) + "\n", dizin, "d1101", sinir_sn=1500)
    k["plan"] = plan
    return k


def _yanit(kosu, v) -> str:
    """Vaka paketinden sonraki ilk STM_OK / STM_NACK satırı ("" = yanıt yok)."""
    for bas, _bit, metin in kosu["satirlar"]:
        if v["t"] < bas <= v["t"] + YANIT_US and ("STM_OK" in metin or "STM_NACK" in metin):
            return metin
    return ""


def _maske_araligi(kosu, bas_us: int, son_us: int) -> set:
    """[bas, son) aralığında GÖRÜLEN etkin maskeler (aralık başındaki geçerli değer dahil)."""
    gecerli, gorulen = 0, set()
    for t, m in kosu["aktif"]:
        if t <= bas_us:
            gecerli = m
        elif t < son_us:
            gorulen.add(m)
    return gorulen | {gecerli}


def _ack_yuzdeleri(metin: str) -> list[int]:
    d = metin.split("D=", 1)[1].split()[0]
    return [int(x) for x in d.split(",")]


@pytest.mark.parametrize("ad", [v[0] for v in VAKALAR])
def test_KRITIK_D1101_kart_yaniti_SOZLESMEYLE_ayni(kosu, ad):
    v = next(x for x in kosu["plan"] if x["ad"] == ad)
    yanit = _yanit(kosu, v)
    tur, deger = v["beklenen"]
    if tur == "NACK":
        assert "STM_NACK" in yanit, (
            f"{ad}: tavan üstü duty KABUL edildi — kart sessizce kırpıyor (B-8.13), yanıt: {yanit!r}"
        )
        assert yanit.split("STM_NACK: ", 1)[1].strip() == deger, f"{ad}: NACK metni sözleşmeden farklı: {yanit!r}"
    else:
        assert "STM_OK" in yanit, f"{ad}: tavan İÇİ istek reddedildi (AI Pro 0,50 / tek-bacak kırılır): {yanit!r}"
        yuzde = _ack_yuzdeleri(yanit)
        for bobin, beklenen_yuzde in deger.items():
            assert yuzde[bobin - 1] == beklenen_yuzde, f"{ad}: ACK D bobin {bobin} = {yuzde[bobin - 1]}: {yanit!r}"


@pytest.mark.parametrize("ad", [v[0] for v in VAKALAR])
def test_KRITIK_D1101_reddedilen_bobin_HIC_surulmez_kabul_edilen_surulur(kosu, ad):
    v = next(x for x in kosu["plan"] if x["ad"] == ad)
    maskeler = _maske_araligi(kosu, v["t"], v["son"])
    tur, deger = v["beklenen"]
    if tur == "NACK":
        yeni = [b for b in v["vaka"] if b not in v["on"]]
        surulen = sorted(b for b in yeni if any(m & (1 << (b - 1)) for m in maskeler))
        assert surulen == [], f"{ad}: reddedilen bobin(ler) {surulen} yine de SÜRÜLDÜ (maskeler {sorted(maskeler)})"
    else:
        for bobin in deger:
            assert any(m & (1 << (bobin - 1)) for m in maskeler), f"{ad}: kabul edilen bobin {bobin} sürülmedi"


def test_KRITIK_D1101_reddedilen_paket_CALISAN_bobine_dokunmaz(kosu):
    """Ret bütün paketi reddeder ama ÖNCEKİ geçerli durum sürer (ölü-adam 1,5 sn'ye dek): bobin 2 vaka penceresinde
    kesintisiz etkin kalır. (Backend bu reddedilen durumu ilk NACK'te düşürür — D1.101 backend kolu.)"""
    v = next(x for x in kosu["plan"] if x["ad"] == "calisan_bobin_2_ve_1_80")
    maskeler = _maske_araligi(kosu, v["t"], v["son"])
    assert maskeler and all(m & 0b10 for m in maskeler), f"bobin 2 ret sırasında DURDU: {sorted(maskeler)}"


@pytest.mark.parametrize("ad", [v[0] for v in VAKALAR])
def test_KRITIK_D1101_simulator_ayni_paketi_FIRMWARE_gibi_yanitlar(kosu, ad):
    """Simülatör firmware'in aynasıdır (`paket_coz` / ürün senaryoları onu kullanır): aynı paket, aynı karar, aynı metin."""
    import tools.stm32_simulator as sim

    v = next(x for x in kosu["plan"] if x["ad"] == ad)
    yanit = _yanit(kosu, v)
    sonuc, sebep = sim.decode_packet(v["paket"])
    if "STM_NACK" in yanit:
        assert sonuc is None and sebep == yanit.split("STM_NACK: ", 1)[1].strip(), (
            f"{ad}: firmware {yanit!r} — simülatör {sebep!r}"
        )
    else:
        assert sonuc is not None, f"{ad}: firmware KABUL etti, simülatör reddetti: {sebep!r}"
