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
 *   Bobin 1 : PWM → PC8  (IN_A)  ·  PD12 (IN_B) kalıcı LOW   ← maske 0x00 (sahip kararı 2026-09-10)
 *   Bobin 2 : PWM → PC9  (IN_A)  ·  PE10 (IN_B) kalıcı LOW   ← ters sargı DONANIMDA çevrildi
 *   Bobin 3 : PWM → PD10 (IN_A)  ·  PD11 (IN_B) kalıcı LOW
 *   Bobin 4 : PWM → PC6  (IN_A)  ·  PC7  (IN_B) kalıcı LOW
 *   Bobin 5 : PWM → PA8  (IN_A)  ·  PA9  (IN_B) kalıcı LOW
 *   Bobin 6 : PWM → PE13 (IN_A)  ·  PE12 (IN_B) kalıcı LOW   ← ESP'den taşındı 2026-09-10
 *   Bobin 7 : PWM → PE15 (IN_A)  ·  PD13 (IN_B) kalıcı LOW   ← ESP'den taşındı 2026-09-10
 *   ⚠️ SAHİP KABLOLAMASI (2026-09-10): darbe DAİMA IN_A'dan çıkar — bobin 1-7 sırayla
 *   PC8 PC9 PD10 PC6 PA8 PE13 PE15. IN_B pinleri (PD12 PE10 PD11 PC7 PA9 PE12 PD13)
 *   FİZİKSEL OLARAK BAĞLI DEĞİL → maske 0x00 KALMALI.
 *   Hangi bacağın darbeleneceği PEMF_BOBIN_TERS_MASKESI ile seçilir (aşağıda): bit i set →
 *   bobin i+1 darbeyi IN_B'den alır, IN_A LOW; değilse IN_A darbelenir, IN_B LOW. Sürülmeyen pinler
 *   boşta ama AYRILMIŞ DEĞİL: çıkış kurulu + kalıcı LOW (yarım-köprü girişi için güvenli); fiziksel
 *   olarak bağlanmayabilir. Başka amaçla kullanmak için main.c'de coil_gpio[] ve Coil_GpioInit
 *   değişmeli. Bipolar projede 14 pinin hepsi darbelenir; maske orada dalgayı aynalar.
 *
 * ⚠️ Unipolar tek yönlü darbe = net DC ≠ 0 (bipolar sözleşmenin tam tersi). Bu bilinçli bir tezgâh
 * karşılaştırmasıdır; doz kalibrasyonu ve termal davranış bipolar ölçümlerinden AYRI değerlendirilir.
 ******************************************************************************
 */
#ifndef PEMF_SURUS_H
#define PEMF_SURUS_H

#ifndef PEMF_SURUS_UNIPOLAR
#define PEMF_SURUS_UNIPOLAR 1
#endif

/* BOBİN POLARİTE MASKESİ — iki kipte ortak. Bit i = bobin i+1'in A↔B bacak rolleri yer değiştirir:
 *   UNIPOLAR: darbe IN_B'den çıkar, IN_A kalıcı LOW (mono sürüş)   ·   BİPOLAR: dalga aynalanır (faz 180°).
 *
 * ⚠️⚠️ 0x00 — SAHİP KARARI 2026-09-10: MASKE KULLANILMAYACAK. GERİ AÇMAYIN.
 *
 * SAHİP BİLDİRİMİ (birebir): "ben fiziksel çevirdim bobini hep aynı pinlerde kalmalıydı
 * PC8 PC9 PD10 PC6 VE PA8 1-5 ARASI SIRAYLA BÖYLE BAĞLI DİĞERLERİNİ BAĞLAMİCAM ZATEN"
 * Ters sargı problemi bobin UÇLARI ÇEVRİLEREK DONANIMDA çözüldü; darbe DAİMA IN_A'dan çıkacak,
 * IN_B pinleri (PD12 PE10 PD11 PC7 PA9) FİZİKSEL OLARAK BAĞLI DEĞİL ve bağlanmayacak.
 *
 * NEDEN MASKE UNIPOLAR KİPTE YAPISAL OLARAK YANLIŞ: mono sürüşte maske biti dalgayı değil,
 * darbenin çıktığı PİNİ değiştirir. Bağlı olmayan bir pine darbe basmak = o bobin HİÇ SÜRÜLMEZ,
 * üstelik SESSİZCE: ACK'te duty görünür, `running` true olur, arayüz "Aktif" der, ALAN SIFIRDIR.
 * Bipolar kipte maske dalgayı aynalar (iki bacak da bağlıysa anlamlı) ama IN_B hiç bağlanmadığı
 * için o kip de bu donanımda maskeyi kullanamaz. → IN_B pinleri bağlanmadıkça maske 0x00 KALIR.
 *
 * ARIZA KAYDI: 2026-09-08'de bu değer 0x03'e (bobin 1 + 2) çekilmişti; tezgâh z işaretleri
 * 1:+1,4 2:−4,9 4:+0,5 5:+3,9 mT ölçülüp bobin 2 ters bulunmuş, düzeltme YAZILIMDA yapılmıştı.
 * O firmware yakıldıysa bobin 1 ve 2'nin darbesi PD12/PE10'a gitti → BAĞLI OLMAYAN PİNLER →
 * iki bobin hiç sürülmedi. Doğru düzeltme, sahibin yaptığı gibi bobin uçlarını çevirmekti.
 * ⚠️ REFLASH gerekli — firmware pakete girmez.
 *
 * BOBİN 6-7 (STM'e taşınıyor) için de AYNI kural: tek kablo çekildiği için maske biti onlarda da
 * 0 kalmalı; yön yanlışsa bobin uçları çevrilir. Bkz. docs/stm32-7-bobin-gecisi-plani-2026-09-10.md
 *
 * İki projede AYNI satır (tek fark PEMF_SURUS_UNIPOLAR). Kapı: tests/test_stm_unipolar_ayna.py
 * (0x00'ı pinler + mekanizmanın ISR'de DURDUĞUNU pinler — IN_B'ler bağlanırsa yeniden kullanılır). */
#ifndef PEMF_BOBIN_TERS_MASKESI
#define PEMF_BOBIN_TERS_MASKESI 0x00U
#endif

#endif /* PEMF_SURUS_H */
