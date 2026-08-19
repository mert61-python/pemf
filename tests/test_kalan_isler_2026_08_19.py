# Author: mertaygn, cglrgrkn
"""DONANIM-UYUM TURUNUN KALAN 6 İŞİ — sahip talebi (2026-08-19 akşam): "kalan işleri de bitir".

1. Fault-handler yaması stm32f4xx_it.c'ye UYGULANDI (4 işleyici + extern, USER CODE içinde)
2. 8266 SELFTEST işleyicisi (S3 semantiği: asla kendini enerjilendirmez)
3. STM PB1 kapısı: boşta (coil1 duty=0) senkron darbesi basılmaz
4. Backend ≳50× freq-ayrışma uyarısı (manuel ESP yolu, `sync_warning` — reddetmez)
5. E-stop bulut aynası toplam süre bütçesi (8 sn)
6. Reconcile bildirim katlaması (5 dk'da bir; log her seferinde)
"""

from __future__ import annotations

import inspect
from pathlib import Path

import servers.api_server as api

KOK = Path(__file__).resolve().parents[1]
STM = KOK / "firmware" / "stm32_pemf" / "Core" / "Src"


def test_KRITIK_1_fault_yamasi_it_c_ye_UYGULANDI():
    """Fault'ta main() durur → ölü-adam koşamaz → bobinler enerjili kalırdı. Dört işleyici de
    önce çıkışları LOW'a çekip MCU'yu resetlemeli — ve USER CODE bloğu İÇİNDE (CubeMX korusun)."""
    itc = (STM / "stm32f4xx_it.c").read_text(encoding="utf-8", errors="replace")
    assert "extern void PEMF_ForceAllCoilOutputsLow(void);" in itc, "extern bildirim yok"
    for ad in ("HardFault_IRQn", "MemoryManagement_IRQn", "BusFault_IRQn", "UsageFault_IRQn"):
        i = itc.index(f"/* USER CODE BEGIN {ad} 0 */")
        j = itc.index(f"/* USER CODE END {ad} 0 */", i)
        blok = itc[i:j]
        assert "PEMF_ForceAllCoilOutputsLow()" in blok, f"{ad}: bobin-kesme çağrısı yok"
        assert "NVIC_SystemReset()" in blok, f"{ad}: reset çağrısı yok"
        # sıra: önce kes, sonra reset
        assert blok.index("PEMF_ForceAllCoilOutputsLow") < blok.index("NVIC_SystemReset"), (
            f"{ad}: reset kesmeden ÖNCE — bobinler enerjiliyken reset atılır"
        )
    # main.c fonksiyonu hâlâ dışa açıyor (statik yapılırsa link kırılır) — ve GÖVDESİ dolu:
    # review yanlış-yeşil bulgusu: yalnız prototipi aramak, gövdesi boşaltılmış (hiçbir pini
    # kesmeyen) bir fonksiyonla da yeşil kalırdı. Gövde saf BSRR yazmalı (fault-bağlamı güvenliği).
    mainc = (STM / "main.c").read_text(encoding="utf-8", errors="replace")
    assert "void PEMF_ForceAllCoilOutputsLow(void);" in mainc
    ig = mainc.index("void PEMF_ForceAllCoilOutputsLow(void) {")
    govde = mainc[ig : mainc.index("\n}", ig)]
    assert "BSRR" in govde and "coil_gpio" in govde, "force-low gövdesi pinleri KESMİYOR"
    assert "HAL_" not in govde, "force-low gövdesine HAL çağrısı girmiş — fault bağlamında güvensiz"


def test_KRITIK_2_8266_SELFTEST_isleyicisi_GUVENLI():
    """8266 SELFTEST komutunu artık tanımalı; S3 semantiği: PASİFKEN ASLA kendini enerjilendirmez."""
    ino = (KOK / "firmware" / "esp8266_pemf_coil" / "esp8266_pemf_coil.ino").read_text(
        encoding="utf-8", errors="replace"
    )
    i = ino.index('strcmp(command, "SELFTEST")')
    j = ino.index("} else if", i)
    blok = ino[i:j]
    assert "isActive()" in blok, "aktiflik kontrolü yok"
    assert "selftest_ok" in blok and "selftest_fail" in blok and "selftest_skipped" in blok
    assert "0.10f" in blok, "geçme eşiği (mag ≥ 0.10 mT — S3 ile aynı) yok"
    # güvenlik: blok içinde PWM başlatan hiçbir çağrı olamaz
    for yasak in ("start(", "_applyPWM", "handleCommand"):
        assert yasak not in blok, f"SELFTEST bloğu kendini enerjilendiriyor olabilir: {yasak}"


def test_KRITIK_3_STM_PB1_bosta_susturuldu():
    """Boştaki referans bobin (duty=0, varsayılan 100 Hz) ESP'lere anlamsız senkron darbesi
    basıyordu → düşük frekanslı ESP DC-yapışma rejimine girebiliyordu. PB1 artık yalnız
    coil1 GERÇEKTEN sürülürken (duty>0) darbelenir."""
    mainc = (STM / "main.c").read_text(encoding="utf-8", errors="replace")
    assert "g_pwm_started && (g_target_duty_ticks[0] > 0)" in mainc, (
        "PB1 kapısı düşmüş/bayat-değere dönmüş — kapı HEDEF duty'yi okumalı (boşta 100 Hz darbe "
        "geri gelir ya da ilk-darbe/kuyruk-darbe köşeleri açılır)"
    )


def test_KRITIK_4_freq_ayrisma_uyarisi_REDDETMEZ_uyarir():
    src = inspect.getsource(api)
    assert "sync_warning" in src, "≳50× ayrışma uyarısı yok"
    i = src.index("50.0 * max(esp_freq, 1.0)")
    blok = src[max(0, i - 1200) : i + 1200]
    # uyarı YOLU: bildirim + yanıt alanı; RED (HTTPException/4xx) YOK
    assert "_push_notification" in blok
    assert "HTTPException" not in blok, "uyarı reddetmeye dönüşmüş — operatör bilinçli olabilir (tasarım: uyar)"
    # yalnız coil1 GERÇEKTEN çalışırken (running) tetiklenir
    assert '_c1.get("running")' in blok, "koşul coil1 running'e bağlı değil (boşta yanlış uyarı)"


def test_KRITIK_5_ayna_toplam_sure_butcesi():
    src = inspect.getsource(api._estop_cloud_mirror)
    assert "son_tarih = time.monotonic() + 8.0" in src, "ayna toplam bütçesi (8sn) yok"
    assert "min(3.0, kalan)" in src, "per-publish bekleme kalan bütçeyle sınırlanmıyor"


def test_KRITIK_6_reconcile_bildirim_katlamasi():
    src = inspect.getsource(api._reconcile_esp_calisiyor)
    assert "_reconcile_last_notify" in src and "300.0" in src, "5 dk bildirim katlaması yok"
    # log katlanMAZ (teşhis kaybolmasın): warning çağrısı katlama koşulunun DIŞINDA
    i = src.index("RECONCILE: bobin")
    j = src.index("_reconcile_last_notify")
    assert i < j, "log da katlanmış — kalıcı hayaletin izi kaybolur"
