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
 *   Bobin 1 : PWM → PD12 (IN_B)  ·  PC8  (IN_A) kalıcı LOW   ← sahip kararı 2026-09-08 (maske bit0)
 *   Bobin 2 : PWM → PE10 (IN_B)  ·  PC9  (IN_A) kalıcı LOW   ← tezgâh ölçümü 2026-09-08: sargı ters (maske bit1)
 *   Bobin 3 : PWM → PD10 (IN_A)  ·  PD11 (IN_B) kalıcı LOW
 *   Bobin 4 : PWM → PC6  (IN_A)  ·  PC7  (IN_B) kalıcı LOW
 *   Bobin 5 : PWM → PA8  (IN_A)  ·  PA9  (IN_B) kalıcı LOW
 *   Hangi bacağın darbeleneceği PEMF_UNIPOLAR_B_BACAK_MASKESI ile seçilir (aşağıda): bit i set →
 *   bobin i+1 darbeyi IN_B'den alır, IN_A LOW; değilse IN_A darbelenir, IN_B LOW. Sürülmeyen pinler
 *   boşta ama AYRILMIŞ DEĞİL: çıkış kurulu + kalıcı LOW (yarım-köprü girişi için güvenli); fiziksel
 *   olarak bağlanmayabilir. Başka amaçla kullanmak için main.c'de coil_gpio[] ve Coil_GpioInit
 *   değişmeli. Bipolar projede 10 pinin hepsi darbelenir; maske orada ETKİSİZDİR.
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

/* UNIPOLAR bacak seçimi (yalnız PEMF_SURUS_UNIPOLAR=1'de okunur; bipolarda etkisiz). Bit i = bobin i+1
 * darbeyi IN_B'den alır (IN_A kalıcı LOW). 2026-09-08 tezgâh (S3 MLX90393, kart düz, aynı duruş, bobin
 * merkezinde z işareti): bobin 1 +1,4 mT · bobin 2 −4,9 · bobin 4 +0,5 · bobin 5 +3,9 → yalnız bobin 2
 * ters sargı. Bobin 1 sahip kararıyla IN_B'de; bobin 2 de IN_B'ye alınınca dört dikey bobin aynı yönde
 * (merkezde sönümleme yok). 0x03 = bit0 (bobin 1) + bit1 (bobin 2). İki projede AYNI satır (tek fark
 * PEMF_SURUS_UNIPOLAR); değiştirmek bilinçli tezgâh kararıdır — kapı: tests/test_stm_unipolar_ayna.py. */
#ifndef PEMF_UNIPOLAR_B_BACAK_MASKESI
#define PEMF_UNIPOLAR_B_BACAK_MASKESI 0x03U
#endif

#endif /* PEMF_SURUS_H */
