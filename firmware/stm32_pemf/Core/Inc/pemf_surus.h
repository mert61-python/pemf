/**
 ******************************************************************************
 * @file    pemf_surus.h
 * @brief   Bobin SÜRÜŞ KİPİ seçimi — iki CubeIDE projesi arasındaki TEK FARK.
 *
 * 2026-09-08 (sahip isteği): aynı main.c iki projede derlenir, tezgâhta ikisi de ayrı denenir:
 *   firmware/stm32_pemf/           → PEMF_SURUS_UNIPOLAR 0  (SİMETRİK BİPOLAR, bobin başı IN_A + IN_B)
 *   firmware/stm32_pemf_unipolar/  → PEMF_SURUS_UNIPOLAR 1  (TEK-BACAK DÜZ SÜRÜŞ, bobin başı yalnız IN_A)
 *
 * ⚠️ TEK KAYNAK KURALI: Core/ altındaki her dosya iki projede BAYT-BAYT AYNI olmalı — yalnız bu
 * başlık farklıdır. Kanonik kaynak stm32_pemf/; unipolar projeyi elle DÜZENLEMEYİN, senkronlayın:
 *     python scripts/stm_unipolar_senkronla.py
 * Kapı: tests/test_stm_main_saglik.py (ayrışma → kırmızı).
 *
 * Kipin ne değiştirdiği (main.c'de `#if PEMF_SURUS_UNIPOLAR` ile işaretli, 4 yer):
 *   · duty tavanı: bipolar yarım-periyot − DDS_BIPOLAR_GAP_TICKS · unipolar tam-periyot − 1
 *   · ISR durum makinesi: bipolar A=[0,duty), B=[yarım,yarım+duty) · unipolar yalnız A=[0,duty)
 *   · STM_READY dizesi: "SYM-BIPOLAR" / "UNIPOLAR tek-bacak"
 * Değişmeyen: protokol (88 bayt), ölü-adam watchdog, süre auto-stop, slew, NTC, PB1 senkron,
 * IN_B pini yine çıkış olarak kurulur ve LOW tutulur (yanlış projeyle yakılsa bile tanımsız değil).
 *
 * PİN DURUMU (UNIPOLAR projede — "hangi pinde PWM kaldı, hangisi boşta?"):
 *   PWM ÇIKAN  (IN_A)      : PC8 (bobin 1) · PC9 (2) · PD10 (3) · PC6 (4) · PA8 (5)
 *   SÜRÜLMEYEN (IN_B, LOW) : PD12 (bobin 1) · PE10 (2) · PD11 (3) · PC7 (4) · PA9 (5)
 *   IN_B pinleri boşta ama AYRILMIŞ DEĞİL: çıkış kurulu + kalıcı LOW (yarım-köprü girişi için
 *   güvenli); fiziksel olarak bağlanmayabilir. Başka amaçla kullanmak için main.c'de
 *   coil_gpio[].portB/pinB ve Coil_GpioInit değişmeli. Bipolar projede 10 pinin hepsi darbelenir.
 *
 * ⚠️ Unipolar tek yönlü darbe = net DC ≠ 0 (bipolar sözleşmenin tam tersi). Bu bilinçli bir tezgâh
 * karşılaştırmasıdır; doz kalibrasyonu ve termal davranış bipolar ölçümlerinden AYRI değerlendirilir.
 ******************************************************************************
 */
#ifndef PEMF_SURUS_H
#define PEMF_SURUS_H

#ifndef PEMF_SURUS_UNIPOLAR
#define PEMF_SURUS_UNIPOLAR 0
#endif

#endif /* PEMF_SURUS_H */
