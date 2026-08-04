"""Denetim 2026-08-04 (P3): STM32 protokol sabitleri ÜÇ ayrı kaynakta ELLE kopyalanmış durumda —
firmware/main.c (otorite), utils/stm32_protocol_limits.py (backend) ve tools/stm32_simulator.py
(E2E test cihazı) — ve hiçbir derleme-zamanı ya da test-zamanı kontrolü bunları karşılaştırmıyordu.

Sürüklenme GERÇEKTEN OLDU: simülatörün FREQ_MAX'ı 10 kHz'de kalmıştı, firmware ve backend ise
25 kHz. Sonuç: E2E güvenlik testleri 10–25 kHz aralığını hiç görmeyen, SEVKEDİLENDEN FARKLI bir
cihazı doğruluyordu. Bu test o sınıf sürüklenmeyi bir daha sessiz bırakmaz.

Donanımsız, saf metin/aritmetik testler — firmware kaynağı `#define`'lardan okunur.
"""

import re
from pathlib import Path

import pytest

from utils import stm32_protocol_limits as lim

_FW = Path(__file__).resolve().parent.parent / "firmware" / "main.c"


@pytest.fixture(scope="module")
def fw_src() -> str:
    if not _FW.exists():  # firmware ağacı yoksa (kod-only checkout) atla
        pytest.skip(f"firmware kaynağı yok: {_FW}")
    return _FW.read_text(encoding="utf-8", errors="replace")


def _define_float(src: str, name: str) -> float:
    """`#define <name> <sayı>[f]` değerini oku (satır-devamı `\\` toleranslı)."""
    m = re.search(rf"^#define\s+{re.escape(name)}\s*\\?\s*\n?\s*([0-9]*\.?[0-9]+)f?\b", src, re.M)
    assert m, f"firmware/main.c içinde #define {name} bulunamadı"
    return float(m.group(1))


def _define_int(src: str, name: str) -> int:
    m = re.search(rf"^#define\s+{re.escape(name)}\s*\\?\s*\n?\s*([0-9]+)U?\b", src, re.M)
    assert m, f"firmware/main.c içinde #define {name} bulunamadı"
    return int(m.group(1))


# ── firmware ↔ backend (utils/stm32_protocol_limits.py) ──────────────────────


def test_freq_max_firmware_ile_backend_ayni(fw_src):
    """FREQ_MAX firmware'de TÜRETİLİR: DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD."""
    isr = _define_float(fw_src, "DDS_ISR_HZ")
    min_ticks = _define_float(fw_src, "DDS_MIN_TICKS_PER_PERIOD")
    assert isr == lim.DDS_ISR_HZ
    assert min_ticks == lim.DDS_MIN_TICKS_PER_PERIOD
    assert isr / min_ticks == lim.FREQ_MAX_HZ == 25000.0


def test_freq_min_firmware_ile_backend_ayni(fw_src):
    assert _define_float(fw_src, "FREQ_MIN") == lim.FREQ_MIN_HZ == 1.0


def test_phase_max_firmware_ile_backend_ayni(fw_src):
    assert _define_float(fw_src, "PHASE_DEG_MAX") == lim.PHASE_MAX_DEG == 360.0


def test_duration_max_firmware_ile_backend_ayni(fw_src):
    assert _define_int(fw_src, "DURATION_MAX_MINUTES") == lim.DURATION_MAX_MINUTES == 9999


# ── firmware ↔ simülatör (tools/stm32_simulator.py) ──────────────────────────


@pytest.fixture(scope="module")
def sim():
    import importlib.util

    p = Path(__file__).resolve().parent.parent / "tools" / "stm32_simulator.py"
    if not p.exists():
        pytest.skip("stm32_simulator.py yok")
    spec = importlib.util.spec_from_file_location("_stm32_sim", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_simulator_sevkedilen_cihazla_ayni_limitleri_uyguluyor(sim, fw_src):
    """Simülatör GERÇEK cihazın sınırlarını uygulamazsa E2E testleri yanlış cihazı doğrular."""
    assert sim.FREQ_MAX == lim.FREQ_MAX_HZ == 25000.0, (
        "simülatör FREQ_MAX'ı firmware/backend ile AYRIŞMIŞ — E2E güvenlik testleri "
        "sevkedilenden farklı bir cihazı doğrular"
    )
    assert sim.FREQ_MIN == lim.FREQ_MIN_HZ
    assert sim.PHASE_MAX == lim.PHASE_MAX_DEG
    assert sim.DUR_MAX == lim.DURATION_MAX_MINUTES
    assert sim.NUM_COILS == _define_int(fw_src, "NUM_COILS")
    assert sim.REF_MS_MAX == _define_int(fw_src, "REF_MS_MAX")


def test_paket_boyutu_88_uc_kaynakta_da_ayni(sim, fw_src):
    """88 bayt: firmware `#pragma pack(1)` struct'ı ↔ Python struct formatı."""
    assert sim.PKT_SIZE == 88
    # ⚠️ DENETİM 2026-08-04 (P3): burada `2 + (5*4)*3 + (5*4) + 2 + 4 == 88` yazıyordu — SAF
    # SABİT ARİTMETİĞİ, girdiden tamamen bağımsız; firmware struct'ı değişse bile HEP geçerdi.
    # Yani "üç kaynakta da aynı" iddiasının firmware ayağı hiç ölçülmüyordu.
    # NOT: `typedef\s+struct.*?\}\s*BinaryCmdPacket_t` yazmak YANLIŞ olur — dosyadaki İLK
    # `typedef struct`tan başlar ve aradaki diğer struct'ların alanlarını da sayar (ilk yazımda
    # tam olarak bu oldu). Gövdeyi kapanış etiketinden GERİYE giderek sınırlandır.
    _kapanis = fw_src.find("} BinaryCmdPacket_t")
    assert _kapanis != -1, "BinaryCmdPacket_t struct'i firmware kaynaginda bulunamadi"
    _acilis = fw_src.rfind("{", 0, _kapanis)
    assert _acilis != -1, "BinaryCmdPacket_t govdesi ayristirilamadi"

    class _M:
        def __init__(self, g):
            self._g = g

        def group(self, i):
            return self._g

    m = _M(fw_src[_acilis + 1 : _kapanis])
    # Dizi boyutları makroyla yazılı (`float duty[NUM_COILS]`) → makroyu kaynaktan çöz.
    mc = re.search(r"#define\s+NUM_COILS\s+(\d+)", fw_src)
    assert mc, "NUM_COILS #define'i bulunamadi"
    sabitler = {"NUM_COILS": int(mc.group(1))}
    boyutlar = {"uint8_t": 1, "int8_t": 1, "uint16_t": 2, "int16_t": 2,
                "uint32_t": 4, "int32_t": 4, "float": 4}
    toplam = 0
    alan_sayisi = 0
    for alan in re.finditer(
        r"\b(uint8_t|int8_t|uint16_t|int16_t|uint32_t|int32_t|float)\s+(\w+)\s*(?:\[\s*(\w+)\s*\])?\s*;",
        m.group(1),
    ):
        boyut_ifadesi = alan.group(3)
        if boyut_ifadesi is None:
            n = 1
        elif boyut_ifadesi.isdigit():
            n = int(boyut_ifadesi)
        else:
            assert boyut_ifadesi in sabitler, f"cozulemeyen dizi boyutu: {boyut_ifadesi}"
            n = sabitler[boyut_ifadesi]
        toplam += boyutlar[alan.group(1)] * n
        alan_sayisi += 1
    assert alan_sayisi >= 6, f"struct alanlari ayristirilamadi (yalniz {alan_sayisi} alan)"
    assert toplam == 88, (
        f"firmware BinaryCmdPacket_t alanlarindan hesaplanan boyut {toplam} != 88 "
        f"(Python struct formati ve simulator 88 varsayiyor -> sessiz protokol kaymasi)"
    )
    assert "BINARY_PKT_SIZE sizeof(BinaryCmdPacket_t)" in fw_src


def test_olu_adam_watchdog_esigi_uc_kaynakta_da_1500ms(sim, fw_src):
    """Firmware'in ölü-adam eşiği; backend keep-alive'ı buna göre marj bırakır."""
    from controllers.hardware_controller import HardwareController

    assert sim.WATCHDOG_MS == 1500
    assert HardwareController._FIRMWARE_DEADMAN_MS == 1500
    assert re.search(r"last_communication_ms\s*>\s*1500", fw_src), (
        "firmware ölü-adam eşiği 1500 ms değil — backend keep-alive marjı geçersiz"
    )


def test_keep_alive_deadman_esiginden_yeterince_hizli():
    """Keep-alive periyodu ölü-adam eşiğinin en az 2 katı hızlı olmalı (tek paket kaybı
    tedaviyi kesmesin). 0.5 s vs 1500 ms → 3x marj."""
    from controllers.hardware_controller import HardwareController

    ka_ms = HardwareController.KEEP_ALIVE_INTERVAL_S * 1000
    assert ka_ms * 2 <= HardwareController._FIRMWARE_DEADMAN_MS, (
        f"keep-alive ({ka_ms} ms) ölü-adam eşiğine ({HardwareController._FIRMWARE_DEADMAN_MS} ms) "
        "çok yakın — ağ/GC gecikmesinde tedavi ortasında beklenmedik durma riski"
    )


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-04 (P3 #69) — FIRMWARE SÜRE SINIRI TEK BAŞINA BİR SINIR DEĞİLDİR
#
# firmware/main.c'de her bobinin `dur_min` süresi dolunca `g_shadow.coil[i].duty = 0` yazılır
# ve `g_start_ms[i] = 0` ile sayaç sıfırlanır. Ancak ISR'daki shadow→active bloğu şunu yapar:
#
#     if (g_active.coil[i].duty > 0.0f) { if (g_start_ms[i] == 0) g_start_ms[i] = HAL_GetTick(); }
#
# Yani host AYNI paketi (duty>0 + duration=N) yeniden gönderdiğinde sayaç BAŞTAN başlar.
# Keep-alive tam olarak bunu yapar (ölü-adam watchdog'u 1500 ms; host 2 Hz paket gönderMEK
# ZORUNDA). Sonuç: firmware'in süre sınırı pratikte hiçbir zaman tedaviyi SONLANDIRMAZ —
# yalnızca döngüye sokar. Bu, hardware_controller.py'de zaten P0 olarak tespit edilmiş ve
# `_coil_deadline` (host-tarafı, bobin-başı monotonic deadline) ile karşılanmıştır.
#
# BURADAKİ RİSK: enerjilemeyi sınırlayan TEK gerçek mekanizma o host-tarafı deadline'dır.
# Bir yeniden-düzenlemede sessizce kaybolursa, firmware "süre sınırı var" görüntüsü verdiği
# için kimse fark etmez ve bobin SÜRESİZ enerjili kalabilir. Bu test o kaybolmayı engeller.
#
# ⚠️ Protokol tarafında düzeltme BİLEREK yapılmadı: firmware'in keep-alive'ı "yeni tedavi"den
# ayırt edebilmesi için 88 baytlık sabit pakete sıra-numarası/başlat-bayrağı eklemek gerekir
# (üç kaynağı birden değiştiren bir protokol değişikliği). Alternatif "süre doldu" mandalı ise
# hekimin aynı parametrelerle YENİDEN başlat demesini sessizce etkisiz kılma riski taşıyordu —
# klinik bir cihazda kötü bir başarısızlık biçimi. Karar sahibe bırakıldı.
# ─────────────────────────────────────────────────────────────────────────────

_HWC = Path(__file__).resolve().parent.parent / "controllers" / "hardware_controller.py"


def test_host_tarafi_sure_deadlineI_hala_uygulaniyor():
    """Bobin enerjilenmesini gerçekten sınırlayan TEK mekanizma bu — kaybolursa süresiz kalır.

    ⚠️ DENETİM 2026-08-04 (P2): bu test önce SALT METİN-GREP'ti (`"_coil_deadline" in src`).
    Uygulama bloğunu (expired listesi + is_running=False + duty=0 + deadline=None) tamamen
    silsen bile dosyada geriye kalan `_coil_deadline` geçişleri yüzünden YEŞİL kalıyordu —
    yani sıfır koruma sağlıyordu. Artık DAVRANIŞ testi: süresi geçmiş bir bobinin `_tick()`
    ile gerçekten durdurulduğunu doğrular.
    """
    import time as _t
    from unittest.mock import patch

    try:
        from controllers.hardware_controller import HardwareController
    except Exception as e:  # donanım bağımlılığı yoksa atla (CI'da import edilebilir olmalı)
        pytest.skip(f"HardwareController import edilemedi: {e}")

    # Keep-alive thread'i başlatmadan örnekle (yan etki istemiyoruz).
    with patch.object(HardwareController, "_keep_alive_loop", lambda self: None):
        hc = HardwareController(core_instance=None)
    try:
        gonderilen = []
        hc._send_stm_manual_update = lambda: gonderilen.append(True)

        # 1. bobin ÇALIŞIYOR ve süresi 1 sn ÖNCE doldu.
        hc.coils_state[1]["is_running"] = True
        hc.coils_state[1]["duty"] = 0.7
        hc._coil_deadline[1] = _t.monotonic() - 1.0

        hc._tick()

        assert hc.coils_state[1]["is_running"] is False, (
            "SURESI DOLAN bobin durdurulmadi — firmware'in kendi sayacini keep-alive "
            "resetledigi icin bobin SURESIZ enerjili kalir (bkz. #69)."
        )
        assert hc.coils_state[1]["duty"] == 0.0, "duty sifirlanmadi — bobin surulmeye devam eder"
        assert hc._coil_deadline[1] is None, "deadline temizlenmedi"
        assert gonderilen, "STM'e sifir-duty paketi GONDERILMEDI — donanim haberdar olmaz"

        # Süresi DOLMAYAN bobin etkilenmemeli (yanlış-pozitif durdurma tedaviyi keser).
        hc.coils_state[2]["is_running"] = True
        hc.coils_state[2]["duty"] = 0.5
        hc._coil_deadline[2] = _t.monotonic() + 3600.0
        hc._tick()
        assert hc.coils_state[2]["is_running"] is True, "suresi DOLMAYAN bobin yanlislikla durduruldu"
    finally:
        try:
            hc.stop()
        except Exception:
            pass


def test_firmware_sure_sayaci_keep_alive_ile_resetleniyor_BELGELI(fw_src):
    """Bu davranış firmware'de AÇIKÇA belgelenmiş olmalı; yoksa okuyan onu güvenlik sınırı sanar."""
    assert "keep-alive" in fw_src.lower() and "g_start_ms" in fw_src, (
        "firmware/main.c sure sayacinin keep-alive ile resetlendigini BELGELEMIYOR — sonraki "
        "okuyucu bunu bagimsiz bir guvenlik siniri sanar ve host-tarafi deadline'i gereksiz gorup silebilir."
    )


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-04 (P3 #65) — ref_ms FAZ HİZALAMASI ISR'DA OLMALI
# Hizalama eskiden main() döngüsünde, paket ayrıştırılır ayrıştırılmaz yapılıyordu; ama
# `g_tpp[i]` YALNIZCA ISR'ın pending-uygulama bloğunda güncellenir. Arada 50 kHz'lik ISR
# çalışırsa tick YENİ frekansa, tpp hâlâ ESKİ frekansa göre olur → hizalama kaybolur ve
# ESP slave'lerine SAHTE bir PB1 sync darbesi gider. Formül main'de KOPYALANMIŞ olduğu için
# daha önce zaten bir kez sürüklenmişti (main tamsayı, ISR float bölme).
# ─────────────────────────────────────────────────────────────────────────────


def test_ref_ms_hizalamasi_ISR_icinde_yapiliyor(fw_src):
    """`g_dds_tick[...] = new_tick` ataması TIM1 ISR'ının içinde olmalı, main() döngüsünde değil."""
    isr = fw_src.index("void HAL_TIM_PeriodElapsedCallback")
    atamalar = [m.start() for m in re.finditer(r"g_dds_tick\[i\]\s*=\s*new_tick", fw_src)]
    assert atamalar, "ref_ms faz hizalamasi KAYBOLMUS (g_dds_tick = new_tick yok)"
    assert all(a > isr for a in atamalar), (
        "ref_ms hizalamasi main() dongusune GERI TASINMIS — g_tpp ile ayrisip hizalamayi bozar "
        "ve ESP slave'lerine sahte sync darbesi gonderir (bkz. #65)."
    )
    # Hizalama, tpp'nin hesaplandigi ayni blokta olmali (g_tpp atamasindan SONRA gelmeli).
    tpp_atama = fw_src.index("g_tpp[i] = (uint32_t)(50000.0f / f)")
    assert all(a > tpp_atama for a in atamalar), (
        "hizalama g_tpp hesabindan ONCE yapiliyor — eski/yeni tpp ayrismasi geri gelir."
    )


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-04 (#65 REGRESYON) — ref_ms HİZALAMASI TEK ATIŞLIK OLMALI
#
# Hizalama main() döngüsünden TIM1 ISR'ına taşındığında `ref_ms_valid` hiçbir yerde
# temizlenmiyordu. Oysa `g_shadow.pending = 1` yalnız yeni bir PAKET geldiğinde değil,
# şu iki yerde daha yazılır:
#     • süre auto-stop      (bobinin dur_min'i doldu → duty = 0)
#     • ölü-adam watchdog   (1500 ms sessizlik → tüm duty = 0)
# Bu yollar `ref_ms_valid`'e dokunmaz → bayrak son gerçek paketten 1 olarak kalır ve ISR,
# BAYAT bir `ref_ms` ile HÂLÂ ÇALIŞAN bobinlerin `g_dds_tick`'ini yeniden konumlandırır:
# tedavi ortasında faz sıçraması + olası sahte/kayıp PB1 sync darbesi. Çok-bobinli faz
# senkronu bu cihazın temel işlevi olduğu için bu gerçek bir kusurdur.
#
# Düzeltme: bayrak `pending` ile AYNI şekilde hem gölgede hem aktifte sıfırlanır.
# ─────────────────────────────────────────────────────────────────────────────


def test_ref_ms_valid_pending_gibi_tuketiliyor(fw_src):
    """Hizalama bayrağı ISR'da HEM g_active HEM g_shadow üzerinde sıfırlanmalı."""
    isr = fw_src.index("void HAL_TIM_PeriodElapsedCallback")
    govde = fw_src[isr:]

    assert re.search(r"g_active\.ref_ms_valid\s*=\s*0", govde), (
        "g_active.ref_ms_valid ISR'da SIFIRLANMIYOR — hizalama tek atislik degil."
    )
    assert re.search(r"&g_shadow\)->ref_ms_valid\s*=\s*0", govde), (
        "g_shadow.ref_ms_valid ISR'da SIFIRLANMIYOR — bayrak sonraki pending'de de 1 kalir "
        "ve sure-auto-stop/watchdog BAYAT ref_ms ile calisan bobinlerin fazini kaydirir."
    )

    # Sıfırlama, hizalamayı KULLANAN bloktan SONRA gelmeli (önce sıfırlanırsa hiç hizalanmaz).
    kullanim = govde.index("g_dds_tick[i] = new_tick")
    sifirlama = govde.index("g_active.ref_ms_valid = 0")
    assert sifirlama > kullanim, (
        "ref_ms_valid, hizalama uygulanmadan ONCE sifirlaniyor — hizalama hic calismaz."
    )


def test_pending_yazan_yollar_biliniyor(fw_src):
    """`pending=1` yazan yer sayısı artarsa, yeni yolun ref_ms semantiğini gözden geçir.

    Bu test bir 'kusur' aramaz; DEĞİŞİKLİĞİ görünür kılar. Yeni bir `pending=1` eklenirse
    (ör. yeni bir güvenlik durdurması) o yolun bayat `ref_ms` ile faz kaydırıp kaydırmadığı
    DÜŞÜNÜLMELİDİR — yukarıdaki regresyon tam olarak bu gözden kaçtığı için oluştu.
    """
    n = len(re.findall(r"g_shadow\.pending\s*=\s*1", fw_src))
    assert n == 3, (
        f"`g_shadow.pending = 1` yazan yol sayisi {n} (beklenen 3: paket, sure-auto-stop, "
        f"watchdog). Yeni bir yol eklendiyse ref_ms tek-atislik semantigini dogrula ve bu "
        f"sayiyi guncelle."
    )
