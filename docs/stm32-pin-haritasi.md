# STM32F429ZIT6 (Nucleo-144) — TAM PİN HARİTASI

> ⚠️ **GÜNCELLEME 2026-09-11 — `stm32_pemf_unipolar` AYNA PROJESİ KALDIRILDI.**
> Sürüş kipi artık `PEMF_BOBIN_UNIPOLAR_MASKESI` ile **bobin başına** seçiliyor
> (`0x60` = bobin 1-5 bipolar, 6-7 unipolar) → ikinci bir derleme gerekmiyor.
> **TEK kaynak: `firmware/stm32_pemf`.** `scripts/stm_unipolar_senkronla.py` ve
> ayna kapısı da silindi. Aşağıdaki iki-proje anlatımı TARİHÇEDİR.


**Kaynak:** `firmware/stm32_pemf/Core/Src/main.c` (`coil_gpio[]`, `Coil_GpioInit`) +
`PEMF_UNIPOLAR.ioc`. Elle yazılmadı, kaynaktan üretildi — 2026-09-10, faz 1 sonrası
(`NUM_COILS = 7`, paket 120 bayt).

**Toplam:** LQFP144'te 114 GPIO (PA-PG tam 16, PH yalnız 0/1). **53'ü kullanımda, 61'i boş.**

---

## 1. BOBİN ÇIKIŞLARI — 7 bobin (yazılımsal DDS, `GPIO->BSRR`)

⚠️ **Donanım PWM kanalı YOK.** TIM1 yalnız 50 kHz kesme üretir; çıkışlar o kesmenin içinde
bit-bang edilir. Bu yüzden bobin eklemek timer kanalı değil, **boş GPIO** ister.

| Bobin | IN_A — **darbe buradan, KABLO VAR** | IN_B — kablo YOK, kalıcı LOW | Kabindeki yeri |
|---|---|---|---|
| 1 | **PC8** | PD12 | alt sağ |
| 2 | **PC9** | PE10 | alt sol |
| 3 | **PD10** | PD11 | arka duvar |
| 4 | **PC6** | PC7 | üst sol |
| 5 | **PA8** | PA9 | üst sağ |
| 6 | **PE13** | PE12 | **sağ duvar** · ESP'den taşındı |
| 7 | **PE15** | PD13 | **sol duvar** · ESP'den taşındı |

⚠️ **KONUM SÜTUNU İKİ KEZ DÜZELTİLDİ.** İlk yazımda 3'e "üst", 5'e "duvar" demiştim (yanlış).
Sonra ölçüm kayıtlarından "3 ve 6 duvar çifti, 7 arka duvar" diye çıkardım — o da yanlıştı,
çünkü kayıttaki "7 = arka duvar" satırı sahibin BEYANI değil benim VARSAYIMIMDI.
**Sahip beyanı (2026-09-11): sağ duvar = 6, sol duvar = 7.** Arka duvar elemeyle **3**.
Tutarlı: ESP'den taşınan iki bobin (6, 7) tam olarak duvar çifti; arka duvar zaten STM'deydi.
Ders: ölçüm kaydına bobin numarasını SAHİP söylemeden yazma.

⚠️ **Maske 0x00 (sahip kararı 2026-09-10):** darbe DAİMA IN_A'dan çıkar. `PEMF_BOBIN_TERS_MASKESI`
bitini set etmek darbeyi **kablosuz** IN_B pinine taşır → o bobin **sessizce sürülmez** (ACK'te
duty görünür, arayüz "Aktif" der, alan sıfırdır). 2026-09-08'de maske 0x03'tü ve bobin 1-2 tam
bu şekilde ölüydü. Yön yanlışsa çözüm **bobin uçlarını fiziksel çevirmek**.

IN_B pinleri boş bırakılabilir ama **ayrılmış değildir**: firmware onları push-pull çıkış olarak
kurar ve kalıcı LOW tutar (yarım-köprü girişi için güvenli durum). Başka işe almak için
`coil_gpio[]` **ve** `Coil_GpioInit` birlikte değişmeli.

---

## 2. FİRMWARE'İN AYRICA KURDUĞU PİNLER

| Pin | İşlev |
|---|---|
| **PD8** | USART3_TX (AF7) → ST-Link VCP → backend seri hattı |
| **PD9** | USART3_RX (AF7) → ST-Link VCP → backend seri hattı |
| **PB0** | LD1 yeşil LED — her geçerli ACK'te toggle (yaşam işareti) |
| **PB1** | MASTER SYNC çıkışı: bobin 1'in periyot başında 100 µs HIGH |

⚠️ **PB1 artık işlevsiz.** ESP slave'lerin faz kilidi içindi; 8266 sahip kararıyla tek faz
sürülüyor ve bu darbeyi **hiç kullanmıyor** (`CoilController.cpp:63-75`). ESP'ler tamamen
kalkınca PB1 serbest bırakılabilir — ihtiyaç olursa **8. yedek pin** olarak düşünülebilir.

---

## 3. PLANLI — I2C sensör hattı (faz 3, henüz kod YOK)

| Pin | İşlev | Konum / not |
|---|---|---|
| **PB8** | I2C1_SCL (AF4) | MLX90614 #1 + MLX90393 #1 (bobin 6) |
| **PB9** | I2C1_SDA (AF4) | — |
| **PB10** | I2C2_SCL (AF4) | ⚠️ **CN12 TEK sıra, üstten 13.** (pin 25) |
| **PB11** | I2C2_SDA (AF4) | ⚠️ **CN12 ÇİFT sıra, üstten 9.** (pin 18) — üstü PB12, **altı GND** |

Kural: her iki bus'ta da **çift numara = SCL, tek numara = SDA**. Pull-up 4,7k (uzun kabloda 2,2k).

**Neden iki ayrı bus:** MLX90614 adresi fabrikada sabit **0x5A**, aynı bus'ta iki tanesi çalışmaz.
MLX90393 A0/A1 straplarıyla 0x0C-0x0F alabildiği için o sorunu yaşamıyor.

**Neden I2C3 kullanılamaz:** I2C3_SCL = PA8 (**bobin 5**), I2C3_SDA = PC9 (**bobin 2**).

Alternatifler: I2C1_SCL/SDA'nın PB6/PB7 seçeneği **kullanılamaz** (PB7 = LD2 mavi LED).
I2C2 için PF1/PF0 da var ama `GPIOF` saati açık değil → `Coil_GpioInit`'e bir satır gerekir.
PB10 aranmak istenmezse: PB8/PB9'daki tek bus'a **2 kanallı I2C mux** (PCA9540 / TCA9543A).

---

## 4. ADC — ACS712-30A AKIM SENSÖRLERİ (bobin 1-5)

Sahip kararı 2026-09-10: bobin 1-5'e ACS712 (30 A sürümü) bağlanıyor. NTC'ler hiç
bağlanmadığı ve termal kesme istenmediği için o beş ADC pini **akıma devredildi**.

| Pin | ADC1 kanalı | Bobin |
|---|---|---|
| **PA0** | IN0 | 1 |
| **PA3** | IN3 | 2 |
| **PA4** | IN4 | 3 |
| **PC0** | IN10 | 4 |
| **PC3** | IN13 | 5 |

Sürücü: `firmware/stm32_pemf/Core/Src/pemf_akim.c` (registre seviyesi — `HAL_ADC` kapalı).
Bobin 6-7'de ACS712 **yok**.

⚠️⚠️ **SEVİYE UYUŞMAZLIĞI — KABLOLAMADAN ÖNCE OKU.** ACS712-30A **5 V** ile besleniyor,
0 A çıkışı **2,50 V**, hassasiyet 66 mV/A. STM32'nin ADC referansı **3,30 V**, pin
absolute-maximum 3,60 V. Sensörün üzerinde **gerilim bölücü yok**:

| Akım | ADC girişi | Sonuç |
|---|---|---|
| 0 A | 2,50 V | okunur |
| **+12,1 A** | **3,30 V** | **ADC tavanı — üstü kırpılır, sayı YANLIŞ** |
| +16,7 A | 3,60 V | **pin absolute-maximum — üstü çipe ZARAR VERİR** |
| +30 A | 4,48 V | pin hasarı |

Bölücüsüz gerçek aralık **−30 A … +12 A** ve unipolar sürüşte akım **tam pozitif tarafta**.
Doygunluk sessiz kalmıyor: firmware ham değeri izler, tavana dayanınca telemetriye `X=1`
koyar ve backend operatöre uyarı basar. 12 A üstü akım bekleniyorsa **10k/20k bölücü**
eklenmeli; oranı kod öğrenmek zorunda değil — offset kalibrasyonundaki `k` katsayısı
bölücüyü ve 5 V rayının gerçek değerini kendiliğinden yakalar.

⚠️ **NTC bloğu ile ÇAKIŞIR.** `PEMF_NTC_TERMAL_ENABLED` 1 yapılırsa aynı beş kanalı iki
modül kurar → `pemf_akim.c` bunu `#error` ile derleme zamanında keser.

---

## 5. KART-SABİT İŞLEVLER (Nucleo-144 donanımı)

| Pin | İşlev | Pin | İşlev |
|---|---|---|---|
| PA1 | RMII_REF_CLK | PC1 | RMII_MDC |
| PA2 | RMII_MDIO | PC4 | RMII_RXD0 |
| PA7 | RMII_CRS_DV | PC5 | RMII_RXD1 |
| PB13 | **RMII_TXD1** | PG11 | RMII_TX_EN |
| PG13 | RMII_TXD0 | | |
| PA10 | USB_ID | PG6 | USB_PowerSwitchOn |
| PA11 | USB_DM | PG7 | USB_OverCurrent |
| PA12 | USB_DP | | |
| PA13 | SWDIO (TMS) | PA14 | SWCLK (TCK) |
| PB7 | LD2 mavi LED | PB14 | LD3 kırmızı LED |
| PC13 | USER_Btn (B1) | PH0 | MCO / HSE giriş |
| PC14 | LSE OSC32_IN | PC15 | LSE OSC32_OUT |
| PH1 | HSE OSC_OUT | | |

⚠️ **PB13 ve PB14 dikkat:** kablolarken "PB1x" diye okunan pinler arasında bu ikisi var.
PB13 **Ethernet**, PB14 **kırmızı LED**. I2C ararken yanlışlıkla bunlara denk gelmek gerçek risk.

⚠️ **PA8/PA9 ÇAKIŞMASI:** `.ioc` bu ikisini **USB_OTG_FS SOF / VBUS** olarak gösteriyor,
firmware ise **bobin 5** olarak sürüyor. Yani bu kartta USB device kipi **kullanılamaz** ve
PA9'un USB VBUS algılamasına giden bir yolu olabilir (solder bridge). Bobin 5 çalışıyorsa
pratikte sorun çıkmamış demektir, ama USB'yi bir gün kullanmak gerekirse burası çakışır.

---

## 6. ⚠️ `.ioc` SAHTE KAYITLARI — firmware'i TARİF ETMİYOR

`.ioc` bir CubeMX kart şablonu; **bu firmware'in gerçeğini yansıtmıyor**:

| `.ioc` ne diyor | Gerçek |
|---|---|
| PE9 = TIM1_CH1 | **BOŞ** — firmware TIM1'i yalnız base timer olarak kullanır |
| PE11 = TIM1_CH2 | **BOŞ** |
| PE13 = TIM1_CH3 | **Bobin 6 IN_A** (2026-09-10) |
| PE14 = TIM1_CH4 | **BOŞ** |
| PA8/PA9 = USB SOF/VBUS | **Bobin 5 IN_A/IN_B** |
| PC6 PC7 PC8 PC9 PD10 PD11 PD12 PE10 PB1 | `.ioc`'de **HİÇ YOK** ama firmware sürüyor |

⚠️⚠️ **CubeMX'te "Generate Code"a BASMA.** `MX_GPIO_Init` ve `main.c` yeniden üretilir → elle
yazılmış bobin GPIO kurulumu ve DDS kodu **silinir**, PA8/PA9 USB'ye döner. I2C dahil her yeni
çevre birimi **elle** eklenecek (`Coil_GpioInit` desenini izleyerek).

---

## 7. BOŞ PİNLER — 61 adet

| Port | Boş pinler |
|---|---|
| PA | PA5 PA6 PA15 |
| PB | PB2 PB3 PB4 PB5 PB6 PB12 PB15 |
| PC | PC2 PC10 PC11 PC12 |
| PD | PD0 PD1 PD2 PD3 PD4 PD5 PD6 PD7 PD14 PD15 |
| PE | PE0 PE1 PE2 PE3 PE4 PE5 PE6 PE7 PE8 **+ PE9 PE11 PE14** (bkz. §6) |
| PF | PF0 … PF15 (16 pin, hepsi boş) |
| PG | PG0 PG1 PG2 PG3 PG4 PG5 PG8 PG9 PG10 PG12 PG14 PG15 |

**Yeni bobin/çevre birimi seçerken tercih sırası:**

1. **PE / PD** — `Coil_GpioInit`'te `GPIOD`/`GPIOE` saatleri **zaten açık**, ek satır gerekmez
2. **PA / PB / PC** — saatleri de açık, ama boş pin az ve LED/ETH komşuluğu var
3. **PF / PG** — bol boş pin, ama `__HAL_RCC_GPIOF/G_CLK_ENABLE()` eklemek gerekir

⚠️ Başlık konumunu bağlamadan **UM1974'ten teyit et**. Bu tabloda MCU pin adı var, CN11/CN12
üzerindeki fiziksel sıra yok. Doğrulanmış tek çıpa: **CN12 çift sıra üstten 2. = PC6, 3. = PC5.**

---

## 8. Kaynak dosyalar

| Ne | Nerede |
|---|---|
| Bobin pin tablosu | `firmware/stm32_pemf/Core/Src/main.c` → `coil_gpio[]` |
| GPIO kurulumu | aynı dosya → `Coil_GpioInit()` |
| Sürüş kipi + maske | `firmware/stm32_pemf/Core/Inc/pemf_surus.h` |
| Unipolar ayna | `firmware/stm32_pemf_unipolar/` — **elle düzenlenmez**, `python scripts/stm_unipolar_senkronla.py` |
| Kapılar | `tests/test_stm_unipolar_ayna.py` · `test_stm_bobin_sayisi_tek_kaynak.py` · `test_stm32_source_parity.py` |
| Geçiş planı | `docs/stm32-7-bobin-gecisi-plani-2026-09-10.md` |

⚠️ Firmware pakete **hiç girmez** → her değişiklikte STM'e **elle reflash** (ST-Link/USB).
Bekleyen reflash borcu: maske 0x00 + `NUM_COILS = 7` (paket 88→120, **atomik sevk** —
uygulama yayınıyla aynı turda gitmeli, yoksa hiçbir bobin çalışmaz).
