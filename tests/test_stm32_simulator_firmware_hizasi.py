# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.13 (B-10.267 · B-10.268) KAPISI — simülatör SEVK EDİLEN firmware'in ACK ve banner'ını basar.

ARIZA (DENETIM-10):
  B-10.267 — simülatörün ACK'i yalnız 5 bobin basıyordu ve `K=` (etkin sürüş kipi) alanı YOKTU.
    Firmware `NUM_COILS` (7) alan + ` K=<etkin maske>` basar (`main.c` ACK döngüsü). Simülatörle
    koşan ürün bobin 6-7 için `coil_update` almaz (onaysız/bayat görünür) ve kip göstergesi
    beslenmez → İG-5.3 / İG-6.1 ölçümleri simülatörle yapılırsa YANLIŞ hüküm çıkar.
  B-10.268 — banner "SYM-BIPOLAR" diyordu; firmware'in derlenen yetenek maskesi
    `PEMF_BOBIN_UNIPOLAR_MASKESI` (`pemf_surus.h`) 0x60 → firmware "KARMA uni=0x60" basar.

KAPI: ürünün GERÇEK paketi (`HardwareController`) simülatöre verilir, dönen ACK ürünün GERÇEK
ayrıştırıcısıyla (`HeadlessCore._parse_stm_ok`) çözülür: NUM_COILS kadar güncelleme ve her birinde
`unipolar` anahtarı; değer firmware kuralı `etkin = (yetenek | istek) & NUM_COILS-bit`. Her bobine
FARKLI frekans/duty/faz/süre verilir ve ACK'in her alanı firmware ACK formülüyle bobin bobin
karşılaştırılır → indis kayması görünür. Banner ürünün `stm32_kimlik.banner_ayristir`'ı ile çözülür.

D0Ö.13 ek (bağımsız inceleme tur 4): duty yüzdesi firmware gibi FLOAT32 (`(long)(duty * 100.0f)`;
double ile 1-100 arası tamsayıların 48'inde 1 eksikti) — %1-100 süpürmesiyle ölçülür; NaN/+inf duty
firmware gibi NACK'lenir ve bağlantı SÜRER; istek yetenek bitleriyle ÇAKIŞINCA da OR (XOR/toplama
mutantı görünsün); yetenek de NUM_COILS bite kırpılır; maske okuyucu YORUMA kanmaz ve TEK tanım
ister; başlık yoksa açık hata; simülatörün "firmware modeli" `main.c` metnine pinli.
MUTASYON: `_send_ack`'te alan sayısını/indisi bozmak (M3) ya da banner'a "SYM-BIPOLAR" geri yazmak → KIRMIZI.
"""

from __future__ import annotations

import math
import queue
import re
import socket
import struct
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from c_soyucu import c_soy

# ⚠️ importorskip DEĞİL: simülatör depoda izli; yüklenemezse bu kapı SESSİZCE atlanmamalı (Ö.7).
import tools.stm32_simulator as sim

KOK = Path(__file__).resolve().parents[1]
BASLIK = KOK / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_surus.h"
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


def _firmware_yetenek_maskesi() -> int:
    """Kapının KENDİ okuması (simülatörden bağımsız): yorumlar soyulur, TEK tanım şart."""
    bulunan = re.findall(
        r"^[ \t]*#[ \t]*define[ \t]+PEMF_BOBIN_UNIPOLAR_MASKESI[ \t]+(0x[0-9A-Fa-f]+|\d+)[uU]?\b",
        c_soy(BASLIK.read_text(encoding="utf-8")),
        flags=re.M,
    )
    assert len(bulunan) == 1, f"pemf_surus.h'de yorum dışı TEK tanım bekleniyordu, {len(bulunan)} bulundu"
    return int(bulunan[0], 0)


def _firmware_kip(maske: int, n: int) -> str:
    """`main.c` banner üçlüsünün AYNISI: 0 → SYM-BIPOLAR, hepsi → UNIPOLAR tek-bacak, aksi → KARMA."""
    if maske == 0:
        return "SYM-BIPOLAR"
    if maske == (1 << n) - 1:
        return "UNIPOLAR tek-bacak"
    return "KARMA"


def _firmware_ack_duty(duty: float) -> int:
    """`main.c` ACK: `(long)(parsed.coil[i].duty * 100.0f)` — float32 çarpım, sıfıra doğru kırpma."""
    return int(struct.unpack("<f", struct.pack("<f", duty * 100.0))[0])


#: bobin → (frekans Hz, duty %, faz °, süre dk). HEPSİ FARKLI: `_send_ack`'te bir indis kayarsa
#: (ör. `phase[0]`) başka bobinin değeri görünür. Duty'ler float32/double kırpmasında AYNI sonucu
#: veren değerlerden seçildi (bu testin konusu alan sayısı/indis; yuvarlama SÜPÜRME kapısında).
_DEGERLER = {
    1: (100.0, 5.0, 0.0, 1),
    2: (110.0, 10.0, 30.0, 2),
    3: (120.0, 15.0, 60.0, 3),
    4: (130.0, 20.0, 90.0, 4),
    5: (140.0, 25.0, 120.0, 5),
    6: (150.0, 30.0, 150.0, 6),
    7: (160.0, 18.0, 180.0, 7),
}
#: Sürüş kipi İSTEKLERİ: 0x82 = bobin 2 + var olmayan 8. bit (firmware yalnız NUM_COILS bit sayar);
#: 0x7F = TÜM bobinler (yetenek bitleriyle ÇAKIŞIR → OR ile XOR/toplama ayrışır); 0x00 = istek yok.
_ISTEKLER = (0x82, 0x7F, 0x00)


class _SahteCore:
    def __init__(self):
        self._hw_send_queue = queue.Queue(maxsize=100)


@pytest.fixture
def hw():
    from controllers.hardware_controller import HardwareController
    from servers import live_state as _ls

    with _ls._live_state_lock:
        _eski = _ls._live_state["stm"]
        _ls._live_state["stm"] = "online"
    c = HardwareController(_SahteCore())
    c._keep_alive_stop.set()
    c._keep_alive_thread.join(timeout=2)
    try:
        yield c
    finally:
        c.stop()
        with _ls._live_state_lock:
            _ls._live_state["stm"] = _eski


def _satirlar(sok: socket.socket, onek: str, adet: int, sure: float) -> list[str]:
    tampon, bulunan = b"", []
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis and len(bulunan) < adet:
        sok.settimeout(max(0.05, bitis - time.monotonic()))
        try:
            parca = sok.recv(4096)
        except socket.timeout:
            break
        if not parca:
            break
        tampon += parca
        *tam, tampon = tampon.split(b"\n")
        bulunan += [s.decode("utf-8", "replace").strip() for s in tam if s.decode("utf-8", "replace").startswith(onek)]
    return bulunan


def _sim_bagla(monkeypatch):
    monkeypatch.setattr(sim, "READY_DELAY_S", 0.0)
    monkeypatch.setattr(sim.Stm32SimClient, "_watchdog_worker", lambda self: None)
    monkeypatch.setattr(sim.Stm32SimClient, "_duration_worker", lambda self: None)
    istemci, karsi = socket.socketpair()
    threading.Thread(target=sim.Stm32SimClient(karsi, ("socketpair", 0)).run, name="d0o13-sim", daemon=True).start()
    return istemci, karsi


def _son_paket(hw) -> bytes:
    paket = None
    while not hw.core._hw_send_queue.empty():
        paket = bytes(hw.core._hw_send_queue.get_nowait()[0])
    assert paket is not None, "ürün paket üretmedi"
    return paket


def _ham_paket(duty1: float, phase1: float = 0.0, freq1: float = 100.0) -> bytes:
    """Ürünün ÜRETEMEYECEĞİ (clamp) ama hatta gelebilecek paket: bobin 1 alanları keyfi, CRC geçerli."""
    n = sim.NUM_COILS
    govde = struct.pack(
        sim.PKT_FMT.rsplit(" ", 1)[0],  # CRC hariç biçim
        0xAA,
        0x55,
        *([duty1] + [0.0] * (n - 1)),
        *([phase1] + [0.0] * (n - 1)),
        *([freq1] + [100.0] * (n - 1)),
        *([1] * n),
        0,
        0,
    )
    return govde + struct.pack("<I", sim.crc32_of(govde))


@pytest.mark.parametrize("istek_mask", _ISTEKLER, ids=lambda v: f"istek_{v:#04x}")
def test_KRITIK_simulator_ACK_NUM_COILS_alan_ve_etkin_KIP_basar(hw, monkeypatch, istek_mask):
    from headless_core import HeadlessCore

    n = sim.NUM_COILS
    assert len(_DEGERLER) == n, "kapı her bobine değer vermeli"
    yetenek = _firmware_yetenek_maskesi()
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        hw.surus_kipi_ayarla(istek_mask)
        for bobin, (frekans, duty_yuzde, faz, sure_dk) in _DEGERLER.items():
            assert hw.update_coil(bobin, frekans, duty_yuzde, faz, sure_dk)
        paket = _son_paket(hw)
        cozum, sebep = sim.decode_packet(paket)
        assert cozum is not None, f"ürün paketi reddedildi: {sebep}"
        duty, faz, frek, sure, _ref_ms, istek = cozum
        assert istek == istek_mask, f"ürün kip isteğini pakete koymadı ({istek:#04x}) — kapı anlamsız"
        istemci.sendall(paket)
        ack = _satirlar(istemci, "-> STM_OK:", 1, 3.0)
        assert ack, "simülatör ACK dönmedi (D0Ö.12 önkoşulu)"
        guncellemeler = HeadlessCore._parse_stm_ok(SimpleNamespace(STM_COIL_COUNT=HeadlessCore.STM_COIL_COUNT), ack[0])
        assert len(guncellemeler) == n, f"ACK {len(guncellemeler)} bobin bildirdi, firmware {n} basar: {ack[0]!r}"
        eksik_kip = [g["coil_id"] for g in guncellemeler if "unipolar" not in g]
        assert not eksik_kip, f"ACK'te K= (etkin kip) alanı YOK → bobin {eksik_kip} için kip bildirilmiyor: {ack[0]!r}"
        # Alan alan, bobin bobin: firmware'in bu pakete basacağı ACK (main.c ACK döngüsü).
        beklenen_alan = {i + 1: (_firmware_ack_duty(duty[i]), int(faz[i]), int(frek[i]), sure[i]) for i in range(n)}
        gelen_alan = {
            g["coil_id"]: (int(g["duty"]), int(g["phase"]), int(g["freq"]), g["duration_min"]) for g in guncellemeler
        }
        assert gelen_alan == beklenen_alan, f"ACK alanları firmware'in basacağıyla uyuşmuyor: {ack[0]!r}"
        # Firmware `K=` ETKİN maskeyi yalnız NUM_COILS bit üzerinden basar: etkin = yetenek || istek.
        etkin = (yetenek | istek) & ((1 << n) - 1)
        k = re.search(r"[,\s]K=(\d+)", ack[0])
        assert k and int(k.group(1)) == etkin, f"K= firmware'in etkin maskesi ({etkin}) değil: {ack[0]!r}"
        beklenen = {g["coil_id"]: bool((etkin >> (g["coil_id"] - 1)) & 1) for g in guncellemeler}
        assert {g["coil_id"]: g["unipolar"] for g in guncellemeler} == beklenen, (
            f"etkin kip firmware kuralı (yetenek|istek = {etkin:#04x}) ile uyuşmuyor: {ack[0]!r}"
        )
    finally:
        istemci.close()
        karsi.close()


def test_KRITIK_ACK_duty_FIRMWARE_float32_ile_basilir_yuzde_1_100(hw, monkeypatch):
    """Ürünün paketiyle %1-100: ACK D= firmware'in `(long)(duty * 100.0f)`sinin AYNISI (double DEĞİL)."""
    istemci, karsi = _sim_bagla(monkeypatch)
    uyusmayan = []
    try:
        for yuzde in range(1, 101):
            assert hw.update_coil(1, 100.0, float(yuzde), 0.0, 1)
            paket = _son_paket(hw)
            duty_f32 = sim.decode_packet(paket)[0][0][0]
            istemci.sendall(paket)
            ack = _satirlar(istemci, "-> STM_OK:", 1, 3.0)
            assert ack, f"%{yuzde}: ACK gelmedi"
            gelen = int(re.search(r"D=(-?\d+)", ack[0]).group(1))
            if gelen != _firmware_ack_duty(duty_f32):
                uyusmayan.append((yuzde, gelen, _firmware_ack_duty(duty_f32)))
    finally:
        istemci.close()
        karsi.close()
    assert not uyusmayan, f"(yüzde, simülatör, firmware) uyuşmuyor — {len(uyusmayan)}/100: {uyusmayan[:8]}"


@pytest.mark.parametrize("deger", [float("nan"), float("inf")], ids=["nan", "arti_sonsuz"])
def test_KRITIK_sonlu_olmayan_duty_NACK_ve_baglanti_SURER(hw, monkeypatch, deger):
    """Firmware `isfinite` ile NACK'ler ve sürer; simülatör eskiden `_send_ack`'te çöküp bağlantıyı KAPATIYORDU."""
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        istemci.sendall(_ham_paket(deger))
        nack = _satirlar(istemci, "-> STM_NACK:", 1, 3.0)
        assert nack and "RANGE coil=1 field=duty value=nonfinite" in nack[0], f"firmware NACK'i yok: {nack}"
        assert hw.update_coil(1, 100.0, 25.0, 0.0, 1)
        istemci.sendall(_son_paket(hw))
        assert _satirlar(istemci, "-> STM_OK:", 1, 3.0), "NACK'ten sonra bağlantı düştü — sonraki pakete STM_OK yok"
    finally:
        istemci.close()
        karsi.close()


@pytest.mark.parametrize("alan", ["phase", "freq"])
def test_KRITIK_sonlu_olmayan_phase_freq_NACK_METNI_firmware_ile_AYNI(hw, monkeypatch, alan):
    """D0Ö.13 ek-2 (tur 5): `main.c` sırası duty → phase → freq; phase/freq NaN'ı da AYNI metinle NACK'ler.
    Döngüyü yalnız duty'ye indiren mutant NaN'ı aralık denetimine düşürür — metin firmware'den farklı olur."""
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        nan = float("nan")
        istemci.sendall(_ham_paket(0.5, phase1=nan) if alan == "phase" else _ham_paket(0.5, freq1=nan))
        nack = _satirlar(istemci, "-> STM_NACK:", 1, 3.0)
        assert nack and f"RANGE coil=1 field={alan} value=nonfinite" in nack[0], f"firmware NACK metni yok: {nack}"
    finally:
        istemci.close()
        karsi.close()


@pytest.mark.parametrize(
    ("duty", "phase", "freq", "ilk"),
    [(math.nan, math.nan, 100.0, "duty"), (0.5, math.nan, math.nan, "phase")],
    ids=["duty_ve_phase", "phase_ve_freq"],
)
def test_KRITIK_birden_cok_sonlu_olmayan_alan_FIRMWARE_SIRASIYLA_NACK(hw, monkeypatch, duty, phase, freq, ilk):
    """D0Ö.13 ek-3 (tur 6): tek alanı NaN yapan kapı döngü SIRASINI görmüyordu; `main.c` duty → phase → freq
    sırasıyla denetler (:764/:770/:776) ve İLK sonlu-olmayanı söyler. Sırayı ters çeviren mutant yeşildi."""
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        istemci.sendall(_ham_paket(duty, phase1=phase, freq1=freq))
        nack = _satirlar(istemci, "-> STM_NACK:", 1, 3.0)
        assert nack and f"RANGE coil=1 field={ilk} value=nonfinite" in nack[0], f"firmware sırası değil: {nack}"
    finally:
        istemci.close()
        karsi.close()


def test_KRITIK_sonlu_ama_2_31_i_ASAN_carpim_ACK_da_KIRPILIR(hw, monkeypatch):
    """D0Ö.13 ek-3 (tur 6): 1e37 kapısı yalnız float32'nin TAŞTIĞI (+inf) kolu koşuyordu. Sonlu ama 2^31'i
    aşan çarpım (3e7 × 100 = 3e9, float32'de tam) firmware'de `VCVT` ile 2147483647'ye doyar; simülatörün
    `max/min` kırpması hiçbir kapıda koşmuyordu (silen mutant `D=3000000000` basar, kapılar yeşildi)."""
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        istemci.sendall(_ham_paket(3e7))
        ack = _satirlar(istemci, "-> STM_OK:", 1, 3.0)
        assert ack and "D=2147483647," in ack[0], f"2^31'i aşan sonlu çarpım ACK'te kırpılmadı: {ack}"
    finally:
        istemci.close()
        karsi.close()


def test_KRITIK_tasan_duty_ACK_da_DOYAR_ve_baglanti_SURER(hw, monkeypatch):
    """Sonlu ama float32 çarpımında taşan duty (1e37 × 100): firmware NACK'lemez (DUTY_MAX yok), `VCVT`
    doyurur → `D=2147483647`. Simülatör eskiden `struct.pack` OverflowError'ında bağlantıyı KAPATABİLİRDİ."""
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        istemci.sendall(_ham_paket(1e37))
        ack = _satirlar(istemci, "-> STM_OK:", 1, 3.0)
        assert ack and "D=2147483647," in ack[0], f"taşan duty ACK'te doymadı: {ack}"
        assert hw.update_coil(1, 100.0, 25.0, 0.0, 1)
        istemci.sendall(_son_paket(hw))
        assert _satirlar(istemci, "-> STM_OK:", 1, 3.0), "taşan duty'den sonra bağlantı düştü"
    finally:
        istemci.close()
        karsi.close()


def test_etkin_kip_YETENEGI_de_NUM_COILS_bite_kirpar(hw, monkeypatch):
    """Başlıkta 7. bit olsaydı firmware onu kırpardı (main.c:640-641); simülatör de kırpmalı."""
    monkeypatch.setattr(sim, "UNIPOLAR_YETENEK_MASKESI", 0xE0)
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        hw.surus_kipi_ayarla(0x00)
        assert hw.update_coil(1, 100.0, 25.0, 0.0, 1)
        istemci.sendall(_son_paket(hw))
        ack = _satirlar(istemci, "-> STM_OK:", 1, 3.0)
        k = re.search(r"[,\s]K=(\d+)", ack[0] if ack else "")
        assert k and int(k.group(1)) == 0x60, f"K= NUM_COILS bite kırpılmadı: {ack}"
    finally:
        istemci.close()
        karsi.close()


def test_KRITIK_simulator_banner_FIRMWARE_maskesinden_turer(monkeypatch):
    from utils.stm32_kimlik import banner_ayristir

    yetenek = _firmware_yetenek_maskesi()
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        banner = _satirlar(istemci, "-> STM_READY:", 1, 3.0)
        assert banner, "simülatör banner basmadı"
        kimlik = banner_ayristir(banner[0])
        assert kimlik is not None, f"ürün banner'ı ayrıştıramadı: {banner[0]!r}"
        assert kimlik.kanal == sim.NUM_COILS, banner[0]
        assert kimlik.maske == yetenek, f"banner maskesi {kimlik.maske} != firmware {yetenek:#04x}: {banner[0]!r}"
        assert kimlik.kip == _firmware_kip(yetenek, sim.NUM_COILS), f"banner kipi firmware'den türemiyor: {banner[0]!r}"
    finally:
        istemci.close()
        karsi.close()


@pytest.mark.parametrize("maske", [0x00, 0x60, 0x7F], ids=lambda v: f"maske_{v:#04x}")
def test_banner_kipi_UC_dalda_da_firmware_uclusu(monkeypatch, maske):
    """Banner kipi yalnız bugünkü 0x60'ta (KARMA) değil, main.c üçlüsünün HER dalında firmware'le aynı."""
    from utils.stm32_kimlik import banner_ayristir

    monkeypatch.setattr(sim, "UNIPOLAR_YETENEK_MASKESI", maske)
    istemci, karsi = _sim_bagla(monkeypatch)
    try:
        banner = _satirlar(istemci, "-> STM_READY:", 1, 3.0)
        kimlik = banner_ayristir(banner[0]) if banner else None
        assert kimlik is not None, f"banner ayrıştırılamadı: {banner}"
        assert (kimlik.maske, kimlik.kip) == (maske, _firmware_kip(maske, sim.NUM_COILS)), banner[0]
    finally:
        istemci.close()
        karsi.close()


def test_maske_okuyucu_YORUMA_kanmaz_ve_TEK_tanim_ister():
    gercek = "#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x60U  /* bit5,6 */\n"
    yorumlu = (
        "/* tarihce:\n * #define PEMF_BOBIN_UNIPOLAR_MASKESI 0x00U (eski)\n */\n"
        "// #define PEMF_BOBIN_UNIPOLAR_MASKESI 0x7FU\n"
        # ⚠️ satır BAŞINDA #define içeren blok yorum: yalnız satır-başı çıpası bunu ELEYEMEZ
        "/*\n#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x00U\n*/\n" + gercek
    )
    assert sim.maske_tanimi(yorumlu) == 0x60, "yorumdaki eski tanım okundu"
    with pytest.raises(RuntimeError):
        sim.maske_tanimi(gercek + "#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x00U\n")  # iki tanım → belirsiz
    with pytest.raises(RuntimeError):
        sim.maske_tanimi("/* #define PEMF_BOBIN_UNIPOLAR_MASKESI 0x60U */\n")  # yalnız yorumda → yok


def test_baslik_YOKSA_yol_soyleyen_RuntimeError(monkeypatch, tmp_path):
    yok = tmp_path / "yok" / "pemf_surus.h"
    monkeypatch.setattr(sim, "_SURUS_BASLIGI", yok)
    with pytest.raises(RuntimeError) as e:
        sim._firmware_unipolar_maskesi()
    assert str(yok) in str(e.value), f"hata yolu söylemiyor: {e.value}"


def test_main_c_ACK_ve_banner_METNI_simulator_modeliyle_AYNI():
    """Simülatör ve bu kapı firmware'i ELLE modelliyor: main.c'nin ilgili ifadeleri değişirse ikisi
    birlikte bayatlamasın diye metin (yorumlar soyulmuş) pinlenir."""
    kod = re.sub(r"\s+", " ", c_soy(MAIN_C.read_text(encoding="utf-8", errors="replace")))
    beklenen = [
        '{"-> STM_OK: D=", " P=", " F=", " T="}',  # ACK etiketleri
        '" K="',  # etkin kip alanı
        "(long)(parsed.coil[ai].duty * 100.0f)",  # float32 duty yüzdesi
        "(long)parsed.coil[ai].phase",
        "(long)parsed.coil[ai].freq",
        "(long)parsed.coil[ai].dur_min",
        "g_unipolar[i] = (uint8_t)(g_yalniz_unipolar[i] || (((istenen >> i) & 1U) != 0U));",  # yetenek || istek
        '"SYM-BIPOLAR"',
        '"UNIPOLAR tek-bacak"',
        '"KARMA"',
        "field=duty value=nonfinite",
        # D0Ö.13 ek-3 (tur 6): ek-2'nin phase/freq kapısının firmware tarafı da pinli (main.c metni değişirse
        # simülatör ve kapı birlikte yeşil kalıyordu).
        "field=phase value=nonfinite",
        "field=freq value=nonfinite",
    ]
    eksik = [b for b in beklenen if b not in kod]
    assert not eksik, f"main.c değişmiş — simülatör modeli ve bu kapı gözden geçirilmeli: {eksik}"
