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
 *   ⚠️⚠️ DÜZELTME 2026-09-11 — ÖNCEKİ KABLOLAMA İDDİASI YANLIŞTI.
 *   Burada "IN_B pinleri (PD12 PE10 PD11 PC7 PA9 PE12 PD13) FİZİKSEL OLARAK BAĞLI DEĞİL"
 *   yazıyordu. Sahip bildirimi (2026-09-11): **"donanımda 5 bobin için 2şer PWM de bağlı;
 *   yanlardaki bobinler için sürücü yüzünden tek PWM unipolar sürüş vardı."**
 *   GERÇEK KABLOLAMA:
 *     bobin 1-5 : IN_A **ve** IN_B BAĞLI  → tam köprü, bipolar sürülebilir
 *     bobin 6-7 : yalnız IN_A bağlı       → sürücü tek yönlü, YALNIZ unipolar
 *   Yanlış iddia sahibin 2026-09-10 mesajındaki "diğerlerini bağlamıcam" ifadesinin
 *   IN_B pinleri sanılmasından doğdu; o cümle bobin UÇLARININ sırasıyla ilgiliydi.
 *   ⚠️ Maske 0x00 yine de KALIR — ama gerekçesi "IN_B bağlı değil" DEĞİL, sahibin ters
 *   sargıyı DONANIMDA çevirmiş olmasıdır (aşağıdaki blok).
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
#define PEMF_SURUS_UNIPOLAR 0
#endif


/* ============================================================================
 * BOBİN BAŞINA SÜRÜŞ KİPİ — `PEMF_BOBIN_UNIPOLAR_MASKESI`
 * ----------------------------------------------------------------------------
 * Bit i SET → bobin i+1 **TEK-BACAK (unipolar)** sürülür (yalnız IN_A darbelenir).
 * Bit i CLEAR → bobin i+1 **SİMETRİK BİPOLAR** sürülür (IN_A ve IN_B aynalı).
 *
 * ⚠️ NEDEN BAYRAK DEĞİL MASKE (sahip donanım bilgisi 2026-09-11):
 *   bobin 1-5 : TAM KÖPRÜ sürücü  → bipolar DA unipolar DA sürülebilir
 *   bobin 6-7 : TEK YÖNLÜ sürücü  → YALNIZ unipolar (sağ/sol duvar bobinleri)
 * Tek bir derleme-zamanı `PEMF_SURUS_UNIPOLAR` bayrağı "5 bipolar + 2 unipolar"ı
 * İFADE EDEMEZ. Kip artık bobinin SÜRÜCÜ DONANIMININ bir özelliğidir.
 *
 * ⚠️ NEDEN DERLEME-ZAMANI SABİT, ÇALIŞMA-ZAMANI PARAMETRE DEĞİL:
 * Bu bir tedavi parametresi değil, DONANIM TOPOLOJİSİDİR. Çalışma zamanında
 * değiştirilebilir olsaydı yanlış bir değer sürücüyle uyuşmazdı; operatörün
 * değiştirebileceği bir şey olmamalı. (Aynı gerekçe `PEMF_BOBIN_TERS_MASKESI`de.)
 *
 * ⚠️ AMAÇ: dB/dt (tepe alan DEĞİL — sahip 2026-09-11). Doku indüksiyonu Faraday'dan
 * gelir ve KENARLARDA olur. Gerçek bipolar sürüşte alan `−B → +B` salınır: kenar
 * başına ΔB iki katı ve periyot başına 4 kenar (unipolarda 2). Duty tavanı farkı
 * (bipolar ~%50, unipolar ~%100) sahip için BAĞLAYICI DEĞİL — zaten en çok %50 veriliyor.
 *
 * ⚠️⚠️ KAZANÇ HEMEN ETKİLİDİR (düzeltme 2026-09-11): burada "IN_B bağlı değilken bipolar
 * zararsız ama etkisizdir, kazanç kablo çekilince ortaya çıkar" yazıyordu. Sahip bildirimi
 * bunu çürüttü: **bobin 1-5'te iki PWM de BAĞLI**. Yani maske 0x60 ile flash edildiği anda
 * bobin 1-5 GERÇEKTEN bipolar sürülür ve dB/dt kazancı ANINDA gelir.
 * ⚠️ Bunun güvenlik sonucu: duty klempi artık o bobinlerde BAĞLAYICI hâle gelir
 * (yarım-periyot − boşluk) ve shoot-through koruması CANLIDIR — aşağıya bakınız.
 *
 * ⚠️⚠️ SHOOT-THROUGH: bipolar bobinde duty tavanı `tpp/2 − DDS_BIPOLAR_GAP_TICKS`
 * OLMAK ZORUNDA — A[0,duty) ve B[yarım,yarım+duty) pencereleri çakışırsa iki bacak
 * aynı anda HIGH olur. Duty klempi ile çıkış aşaması AYNI maskeyi okumalıdır;
 * ayrışırlarsa sürücü yanar. Kapı: tests/test_stm_bobin_basina_kip.py
 * ============================================================================
 */
#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x60U  /* bit5,6 = bobin 6,7 UNIPOLAR (surucu tek yonlu) - bobin 1-5 BIPOLAR */

/* BOBİN POLARİTE MASKESİ — iki kipte ortak. Bit i = bobin i+1'in A↔B bacak rolleri yer değiştirir:
 *   UNIPOLAR: darbe IN_B'den çıkar, IN_A kalıcı LOW (mono sürüş)   ·   BİPOLAR: dalga aynalanır (faz 180°).
 *
 * ⚠️⚠️ 0x00 — SAHİP KARARI 2026-09-10: MASKE KULLANILMAYACAK. GERİ AÇMAYIN.
 *
 * SAHİP BİLDİRİMİ (birebir): "ben fiziksel çevirdim bobini hep aynı pinlerde kalmalıydı
 * PC8 PC9 PD10 PC6 VE PA8 1-5 ARASI SIRAYLA BÖYLE BAĞLI DİĞERLERİNİ BAĞLAMİCAM ZATEN"
 * Ters sargı problemi bobin UÇLARI ÇEVRİLEREK DONANIMDA çözüldü → yazılımda çevirmeye GEREK YOK.
 *
 * ⚠️ DÜZELTME 2026-09-11: burada "IN_B pinleri FİZİKSEL OLARAK BAĞLI DEĞİL ve bağlanmayacak"
 * yazıyordu — YANLIŞTI. Sahip bildirimi: bobin 1-5'te İKİ PWM DE BAĞLI (tam köprü); yalnız
 * bobin 6-7'de sürücü tek yönlü olduğu için tek PWM var. Maske 0x00 KALIR ama gerekçe
 * değişti: ters sargı zaten donanımda çözüldüğü için maskeye İHTİYAÇ YOK.
 *
 * NEDEN MASKE TEK-BACAK (UNIPOLAR) BOBİNDE YAPISAL OLARAK TEHLİKELİ: mono sürüşte maske biti
 * dalgayı değil, darbenin çıktığı PİNİ değiştirir. Bobin 6-7'de IN_B'ye giden kablo YOKTUR →
 * o bit set edilirse bobin HİÇ SÜRÜLMEZ, üstelik SESSİZCE: ACK'te duty görünür, `running`
 * true olur, arayüz "Aktif" der, ALAN SIFIRDIR. (2026-09-08'de maske 0x03 idi ve bobin 1-2
 * için tam bu arıza riskini taşıyordu.)
 * Bobin 1-5 bipolar sürüldüğü için orada maske dalgayı aynalar (faz 180° eşdeğeri) ve
 * teknik olarak anlamlıdır — ama ihtiyaç yok: yön donanımda düzeltildi. → maske 0x00 KALIR.
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
