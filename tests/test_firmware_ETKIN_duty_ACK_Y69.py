# Author: mertaygn, cglrgrkn
"""Y69 (sahip, S-G4) — yüksek frekansta yapısal ölü zamanın ve tick nicelemesinin düşürdüğü ETKİN duty raporlanır: kartın
ACK'i (`E=<binde>`) ve arayüz İSTENEN değerin yanında UYGULANANI da gösterir. Sürüş DEĞİŞMEZ, ölü zaman KISALTILMAZ
(shoot-through), backend'e kıskaç EKLENMEZ (Ö.4-Y9).

ÖLÇÜLEN KUSUR (1-G §(b)4, DUZELTME-D1G.md:314): kabul edilen bipolar %50'de etkin oran 1 Hz %50,00 · 100 Hz %49,6 ·
1 kHz %46 · 5 kHz %30 · 10 kHz %20 — ACK hepsinde `D=50`; 10 kHz'de %10 → 0 tick (bobin SÜRÜLMEZ ama `D=10`). Arayüz
istenen değeri tek duty olarak gösteriyordu (gösterilen ≠ uygulanan).

KAPILAR
  (a) ISR DÜRÜSTLÜĞÜ — GERÇEK main.c ISR takımında firmware'in rapor işlevi (`Coil_EtkinDutyBinde`, takımın `etkin` kipi)
      ile ISR'ın GPIO kenarlarından ÖLÇÜLEN kararlı-durum bacak oranı bir ızgarada (bipolar / unipolar-yetenek /
      unipolar-istek × 1 Hz–25 kHz × duty) BİREBİR aynı. 1-G ölçüm tablosu burada YAZILI (kaynaktan okunmaz).
  (b) ACK — ana döngü takımı (GERÇEK firmware + HAL; paket GERÇEK `HardwareController`'dan): ACK satırı `E=` ile bobin
      bobin etkin oranı taşır; `D=` İSTENEN olarak kalır (D1.101 sözleşmesi), `K=` aynı.
  (c) BACKEND — `HeadlessCore._parse_stm_ok` `E=`'yi (etiket firmware'in YORUMSUZ kaynağından) `duty_etkin` (%) olarak
      çözer; alan yoksa (eski firmware) ya da sayısı tutmazsa anahtar HİÇ konmaz; GERÇEK olay işleyicisi canlı duruma
      `dutyEtkin` yazar, anahtar yoksa dokunmaz (None ≠ 0), STM kopunca None.
  (d) SİMÜLATÖR — sevk edilen firmware'in ACK'ini basar (D0Ö.13): aynı pakete aynı `E=`.
Arayüz kolu (jest): CoilCard.Y69.etkinDuty · CoilParameterPanel.Y69.etkinDuty · LiveDataContext.Y69.etkinDuty.
⚠️ TEZGÂH (Oturum 13): kartta osiloskopla etkin oran (NOP ölü-zaman süresi dahil) doğrulanır.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import firmware_host_aparat as fw
import pytest

KOK = Path(__file__).resolve().parents[1]
_DIZE = r'"((?:[^"\\]|\\.)*)"'

#: 1-G §(b)4 ölçümü (bobin 1 bipolar) + Y69 sahip metni — BEKLENEN binde. (Hz, duty, binde)
TABLO_BIPOLAR = [
    (1.0, 0.50, 500),  # %50,00 (AI Pro 1 Hz) — 24998/50000, binde yuvarlaması
    (100.0, 0.50, 496),  # %49,6
    (1000.0, 0.50, 460),  # %46
    (5000.0, 0.50, 300),  # %30
    (10000.0, 0.50, 200),  # %20
    (10000.0, 0.10, 0),  # 0 tick → bobin SÜRÜLMEZ (ACK D=10)
    (1000.0, 0.40, 400),  # karşıt (1-G): tavan altında kırpma yok
    (5000.0, 0.30, 300),  # karşıt (1-G): 5 kHz %30 → %30,0
]
#: Tek bacak (bobin 6 donanım yeteneği / bobin 1 Sürüş Kipi isteği): tavan tpp−1. (Hz, duty, binde)
TABLO_UNIPOLAR = [
    (100.0, 0.80, 800),  # tavan altı: kırpma yok
    (100.0, 1.00, 998),  # 499/500
    (10000.0, 0.50, 400),  # tpp 5: (int)2,5 = 2 tick → %40 (nicelenme)
    (25000.0, 1.00, 500),  # tpp 2: tavan 1 tick
]
IZGARA_HZ = [1.0, 7.0, 50.0, 100.0, 333.0, 1000.0, 2500.0, 5000.0, 7000.0, 10000.0, 12500.0, 25000.0]
IZGARA_BIPOLAR_DUTY = [0.05, 0.10, 0.25, 0.40, 0.50]
IZGARA_UNIPOLAR_DUTY = [0.10, 0.50, 0.80, 1.00]


#: Takımın `etkin` kipini açan sonda — main.c metninin SONUNA eklenir (isr_kosum.c `#ifdef PEMF_HOST_ETKIN_SONDASI`).
SONDA = "\n/* Y69 sondası (test_firmware_ETKIN_duty_ACK_Y69.py ekler) */\n#define PEMF_HOST_ETKIN_SONDASI 1\n"


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    """ISR ölçümü — rapor işlevinden BAĞIMSIZ (eski firmware'le de derlenir)."""
    return fw.derle(fw.MAIN_C.read_text(encoding="utf-8"), tmp_path_factory.mktemp("y69"))


@pytest.fixture(scope="module")
def exe_rapor(tmp_path_factory):
    from c_soyucu import c_soy

    src = fw.MAIN_C.read_text(encoding="utf-8")
    assert "Coil_EtkinDutyBinde(" in c_soy(src), (
        "firmware'de ETKİN duty rapor işlevi YOK — ACK yalnız İSTENEN `D=`'yi yankılar (Y69)"
    )
    return fw.derle(src + SONDA, tmp_path_factory.mktemp("y69_rapor"))


@pytest.fixture(scope="module")
def harita(exe):
    return fw.harita(exe)


def _rapor(exe_rapor, vakalar) -> list[int]:
    """Firmware'in rapor işlevi (`etkin f d u ...` → "E f d u binde")."""
    arg = []
    for f, d, u in vakalar:
        arg += [f, d, int(u)]
    sat = [s.split() for s in fw.kos(exe_rapor, "etkin", *arg) if s.startswith("E ")]
    assert len(sat) == len(vakalar), f"aparat: {len(vakalar)} vakaya {len(sat)} rapor satırı"
    return [int(p[4]) for p in sat]


def _a_yuksek(olaylar, pin, bas: int, son: int) -> int:
    """[bas, son) tick aralığında `pin` (port, bit) HIGH kaldığı tick sayısı (BSRR günlüğünden yeniden kurulur)."""
    port, bit = pin
    seviye, t0, toplam = 0, 0, 0
    for tick, p, deger, _nop in olaylar:
        if p != port:
            continue
        yeni = 1 if (deger & 0xFFFF) & bit else (0 if ((deger >> 16) & 0xFFFF) & bit else seviye)
        if yeni == seviye:
            continue
        if seviye:
            toplam += max(0, min(tick, son) - max(t0, bas))
        seviye, t0 = yeni, tick
    if seviye:
        toplam += max(0, son - max(t0, bas))
    return toplam


def _olculen(exe, harita, bobin: int, f: float, d: float, kip_bas: int | None = None) -> tuple[int, int]:
    """ISR kararlı duruma varana dek koşar; son İKİ tam periyotta A bacağının HIGH tick'i → (binde, tpp).

    tpp ISR'ın kendi durum satırından (S) okunur. Kararlılık: son periyot = bir önceki (değilse aparat kısa koştu)."""
    ilk = [x for x in fw.durumlar(fw.kos(exe, "isr", 1, hex(1 << bobin), f, d, 0, kip_bas=kip_bas)) if x[1] == bobin]
    tpp = ilk[0][2]
    n = tpp * (80 if tpp < 2000 else 6)
    olaylar = fw.bsrr_olaylari(fw.kos(exe, "isr", n, hex(1 << bobin), f, d, 0, kip_bas=kip_bas))
    pa, ia, _pb, _ib = harita[0][bobin]
    son1 = _a_yuksek(olaylar, (pa, ia), n - tpp, n)
    son2 = _a_yuksek(olaylar, (pa, ia), n - 2 * tpp, n - tpp)
    assert son1 == son2, f"aparat: {f} Hz d={d} kararlı duruma varmadı ({son2} → {son1} tick, tpp={tpp})"
    return (son1 * 1000 + tpp // 2) // tpp, tpp


# ── (a) ISR dürüstlüğü ────────────────────────────────────────────────────────


@pytest.mark.parametrize("f,d,beklenen", TABLO_BIPOLAR)
def test_KRITIK_bipolar_ETKIN_duty_1G_olcum_tablosu_RAPOR_ve_GPIO(request, exe, harita, f, d, beklenen):
    olcu, tpp = _olculen(exe, harita, 0, f, d)
    assert olcu == beklenen, f"aparat/ISR: {f} Hz %{d * 100:g} GPIO'da binde {olcu} (tpp {tpp}), 1-G ölçümü {beklenen}"
    rapor = _rapor(request.getfixturevalue("exe_rapor"), [(f, d, 0)])[0]
    assert rapor == beklenen, (
        f"{f} Hz %{d * 100:g}: firmware binde {rapor} RAPORLUYOR, ISR binde {olcu} SÜRÜYOR — ACK uygulananı söylemiyor"
    )


@pytest.mark.parametrize("f,d,beklenen", TABLO_UNIPOLAR)
@pytest.mark.parametrize("kaynak", ["yetenek_bobin6", "istek_bobin1"])
def test_KRITIK_unipolar_ETKIN_duty_RAPOR_ve_GPIO(request, exe, harita, f, d, beklenen, kaynak):
    bobin, kip_bas = (5, None) if kaynak == "yetenek_bobin6" else (0, 0x01)
    olcu, tpp = _olculen(exe, harita, bobin, f, d, kip_bas=kip_bas)
    assert olcu == beklenen, (
        f"aparat/ISR: {kaynak} {f} Hz %{d * 100:g} GPIO binde {olcu} (tpp {tpp}), beklenen {beklenen}"
    )
    rapor = _rapor(request.getfixturevalue("exe_rapor"), [(f, d, 1)])[0]
    assert rapor == beklenen, f"{kaynak} {f} Hz %{d * 100:g}: rapor {rapor} ≠ ISR {olcu}"


def test_KRITIK_rapor_islevi_ISR_ile_IZGARADA_birebir(exe, exe_rapor, harita):
    """Sürüklenme kapısı: ISR formülü (tpp, hedef tick, ölü-zaman tavanı, nicelenme) değişir de rapor değişmezse — ya da
    tersi — en az bir ızgara noktası ayrışır."""
    vakalar = [(f, d, 0, 0, None) for f in IZGARA_HZ for d in IZGARA_BIPOLAR_DUTY]
    vakalar += [(f, d, 1, 5, None) for f in IZGARA_HZ for d in IZGARA_UNIPOLAR_DUTY]
    vakalar += [(f, d, 1, 0, 0x01) for f in IZGARA_HZ for d in IZGARA_UNIPOLAR_DUTY]
    raporlar = _rapor(exe_rapor, [(f, d, u) for f, d, u, _b, _k in vakalar])
    ayrisan = []
    for (f, d, u, bobin, kip_bas), rapor in zip(vakalar, raporlar):
        olcu, tpp = _olculen(exe, harita, bobin, f, d, kip_bas=kip_bas)
        if rapor != olcu:
            ayrisan.append((f, d, "uni" if u else "bi", bobin + 1, tpp, rapor, olcu))
    assert not ayrisan, (
        f"rapor ≠ ISR (Hz, duty, kip, bobin, tpp, rapor, ölçülen): {ayrisan[:8]} (toplam {len(ayrisan)})"
    )


# ── (b) ACK — ana döngü takımı ──────────────────────────────────────────────

#: (bobin, Hz, %duty) — HEPSİ FARKLI: ACK'te bir indis kayarsa görünür.
ACK_KOMUTLARI = [(1, 1000.0, 50.0), (2, 5000.0, 50.0), (3, 10000.0, 50.0), (4, 10000.0, 10.0), (5, 100.0, 50.0)]
ACK_KOMUTLARI += [(6, 100.0, 80.0), (7, 1.0, 100.0)]
ACK_BEKLENEN_E = [460, 300, 200, 0, 496, 800, 1000]  # tablolardan; bobin 7: 49999/50000 → binde 1000
ACK_BEKLENEN_D = [50, 50, 50, 10, 50, 80, 100]


def _hc_paketi(komutlar) -> bytes:
    from kayitci_donanim import gercek_hc
    from servers import live_state as ls

    ls.stm_komut_kabulu_bildir()
    with gercek_hc() as hc:
        hc.surus_kipi_ayarla(0)
        for bobin, hz, duty in komutlar:
            assert hc.update_coil(bobin, hz, duty, 0.0, 5, start=True) is True, f"aparat: HC {bobin}'i kabul etmedi"
        return hc.core._hw_send_queue.paketler[-1]


@pytest.mark.skipif(sys.platform != "win32", reason="ana döngü koşum takımı Windows VEH'e dayanır; Linux portu YOK")
def test_KRITIK_ACK_satiri_E_alaninda_bobin_bobin_ETKIN_orani_tasir(tmp_path_factory):
    import firmware_dongu_aparat as da

    dizin = tmp_path_factory.mktemp("y69_dongu")
    exe = da.derle(dizin)
    paket, bas = _hc_paketi(ACK_KOMUTLARI), 2_500_000
    s = ["SURE_US %d" % (bas + 400_000), "ERISIM_NS 50", "GETTICK_NS 1000"]
    s += [f"ACS {k} 2500" for k in (0, 3, 4, 10, 13)]
    s += ["I2C 1 MLX90614 5A", "I2C 2 MLX90393 18", f"PAKET {bas + 150_000} {paket.hex()}"]
    k = da.kos(exe, "\n".join(s) + "\n", dizin, "y69", sinir_sn=1500)
    ack = [m for t, _b, m in k["satirlar"] if bas + 150_000 < t <= bas + 270_000 and "STM_OK" in m]
    assert ack, f"paketten sonra STM_OK yok: {[m for _t, _b, m in k['satirlar']][-6:]}"
    e = re.search(r"[,\s]E=([0-9,]+)", ack[0])
    assert e, f"ACK etkin duty TAŞIMIYOR (istenen D= tek başına): {ack[0]!r}"
    assert [int(x) for x in e.group(1).split(",")] == ACK_BEKLENEN_E, f"E= bobin bobin etkin oran değil: {ack[0]!r}"
    dd = re.search(r"D=([0-9,]+)", ack[0])
    assert dd and [int(x) for x in dd.group(1).split(",")] == ACK_BEKLENEN_D, f"D= artık İSTENEN değil: {ack[0]!r}"
    kk = re.search(r"[,\s]K=(\d+)", ack[0])
    assert kk and int(kk.group(1)) == 0x60, f"K= (etkin kip) bozuldu: {ack[0]!r}"


# ── (c) backend ─────────────────────────────────────────────────────────────


def etkin_etiketi(src: str) -> str:
    """Yorumu soyulmuş main.c'de rapor işlevini basan döngüden HEMEN önceki ACK etiketi."""
    from c_soyucu import c_soy

    soy = c_soy(src)
    i = soy.find("Coil_EtkinDutyBinde(parsed")
    assert i > 0, "main.c'de (yorum dışı) ACK'e etkin duty basan çağrı yok"
    etiketler = re.findall(
        r"Coil_AckMetin\(\s*ack_msg\s*,\s*sizeof\(ack_msg\)\s*,\s*len\s*,\s*" + _DIZE + r"\s*\)", soy[:i]
    )
    etiketler = [e for e in etiketler if e != ","]
    assert etiketler, "etkin duty etiketi bulunamadı"
    return etiketler[-1]


@pytest.fixture(scope="module")
def ack_kur():
    from test_stm_ack_firmwareden_TURETILIR import ack_bicimi, ack_satiri

    src = fw.MAIN_C.read_text(encoding="utf-8")
    bicim, e_et = ack_bicimi(src), etkin_etiketi(src)
    gruplar = [ACK_BEKLENEN_D, [0] * 7, [int(f) for _b, f, _d in ACK_KOMUTLARI], [5] * 7]

    def kur(etkin: list[int] | None) -> str:
        satir = ack_satiri(bicim, gruplar, 0x60)
        if etkin is not None:
            satir += e_et + bicim["ayrac"].join(str(v) for v in etkin)
        return satir

    return kur


def _parse(satir: str):
    import headless_core

    class _Cekirdek:
        STM_COIL_COUNT = 7

    return headless_core.HeadlessCore._parse_stm_ok(_Cekirdek(), satir)


def test_KRITIK_backend_E_alanini_duty_etkin_YUZDE_olarak_cozer(ack_kur):
    g = _parse(ack_kur(ACK_BEKLENEN_E))
    assert len(g) == 7
    assert [u.get("duty_etkin") for u in g] == [46.0, 30.0, 20.0, 0.0, 49.6, 80.0, 100.0], g
    assert [u["duty"] for u in g] == [float(x) for x in ACK_BEKLENEN_D], "istenen duty (D=) değişmemeli"


@pytest.mark.parametrize("etkin", [None, [460, 300, 200, 0, 496, 800]], ids=["alan_yok_eski_firmware", "sayi_tutmaz"])
def test_KARSIT_E_yoksa_ya_da_sayisi_tutmazsa_anahtar_KONMAZ(ack_kur, etkin):
    g = _parse(ack_kur(etkin))
    assert len(g) == 7, "D/P/F/T yine çözülmeli"
    assert all("duty_etkin" not in u for u in g), f"bildirilmeyen etkin duty uyduruldu: {g}"


def _olay(data: dict) -> None:
    from servers import api_server

    class _Olay:
        event_type = "hardware.stm.coil_update"

    _Olay.data = data
    api_server._handle_backend_event(_Olay())


def test_KRITIK_canli_durum_dutyEtkin_yazilir_yoksa_DOKUNULMAZ_STM_kopunca_None():
    from servers import live_state

    with live_state._live_state_lock:
        eski_bobinler = {k: dict(v) for k, v in live_state._live_state["coils"].items()}
        eski_stm = live_state._live_state["stm"]
        live_state._live_state["coils"][0]["dutyEtkin"] = None
    try:
        temel = {"coil_id": 1, "duty": 50.0, "freq": 1000.0, "duration_min": 5, "running": True}
        _olay(dict(temel))
        with live_state._live_state_lock:
            assert live_state._live_state["coils"][0]["dutyEtkin"] is None, "bildirilmeyen etkin duty yazıldı (0 ≠ —)"
        _olay({**temel, "duty_etkin": 46.0})
        with live_state._live_state_lock:
            assert live_state._live_state["coils"][0]["dutyEtkin"] == 46.0, "ACK'in etkin duty'si canlı duruma ULAŞMADI"
            assert live_state._live_state["coils"][0]["dutyCycle"] == 50.0, "istenen duty ezildi"
        _olay(dict(temel))
        with live_state._live_state_lock:
            assert live_state._live_state["coils"][0]["dutyEtkin"] == 46.0, "anahtarsız olay bildirilmiş değeri SİLDİ"
        live_state.update_live_stm_status(False)
        with live_state._live_state_lock:
            assert live_state._live_state["coils"][0]["dutyEtkin"] is None, (
                "STM koptu ama etkin duty kaldı — doğrulanmamış değer doğrulanmış gibi görünür"
            )
    finally:
        with live_state._live_state_lock:
            for k, eski in eski_bobinler.items():
                live_state._live_state["coils"][k].clear()
                live_state._live_state["coils"][k].update(eski)
            live_state._live_state["stm"] = eski_stm


# ── (d) simülatör ───────────────────────────────────────────────────────────


def _sim_ack(paket: bytes) -> str:
    """GERÇEK `_send_ack` (bağlantısız istemci; `_send` yakalanır) — simülatörün kabloya yazacağı satır."""
    # ⚠️ importorskip DEĞİL: simülatör depoda izli; yüklenemezse kapı sessizce atlanmamalı (Ö.7).
    import tools.stm32_simulator as sim

    cozum, sebep = sim.decode_packet(paket)
    assert cozum is not None, f"simülatör paketi reddetti: {sebep}"
    duty, faz, frek, sure, _ref, kip = cozum
    yakalanan: list[str] = []
    istemci = sim.Stm32SimClient.__new__(sim.Stm32SimClient)
    istemci._send = yakalanan.append
    istemci._send_ack(duty, faz, frek, sure, kip)
    assert len(yakalanan) == 1, yakalanan
    return yakalanan[0]


def test_KRITIK_simulator_ayni_pakete_ayni_E_basar():
    satir = _sim_ack(_hc_paketi(ACK_KOMUTLARI))
    e = re.search(r"[,\s]E=([0-9,]+)", satir)
    assert e, f"simülatör ACK'i etkin duty TAŞIMIYOR (sevk edilen firmware taşır): {satir!r}"
    assert [int(x) for x in e.group(1).split(",")] == ACK_BEKLENEN_E, f"simülatör E= firmware'den ayrışık: {satir!r}"


def test_KRITIK_simulator_rapor_islevi_firmware_ile_IZGARADA_birebir(exe_rapor):
    """Simülatörün `firmware_etkin_binde`'i (float32 benzetimi) GERÇEK firmware işleviyle aynı ızgarada birebir."""
    import struct

    import tools.stm32_simulator as sim

    def f32(x: float) -> float:
        return struct.unpack("<f", struct.pack("<f", x))[0]

    vakalar = [(f, d, u) for f in IZGARA_HZ for d in IZGARA_BIPOLAR_DUTY + [1.0] for u in (0, 1)]
    raporlar = _rapor(exe_rapor, vakalar)
    ayrisan = [
        (f, d, u, r, s)
        for (f, d, u), r in zip(vakalar, raporlar)
        if (s := sim.firmware_etkin_binde(f32(d), f32(f), u)) != r
    ]
    assert not ayrisan, f"simülatör ≠ firmware (Hz, duty, tek_bacak, firmware, simülatör): {ayrisan[:8]}"
