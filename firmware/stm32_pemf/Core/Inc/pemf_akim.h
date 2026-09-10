/**
 ******************************************************************************
 * @file    pemf_akim.h
 * @brief   Bobin 1-5 akım ölçümü — ACS712-30A, ADC1, registre seviyesi
 *
 * SAHİP KARARI 2026-09-10: bobin 1-5'e ACS712 (30 A sürümü) bağlanacak, STM32'nin
 * 5 ADC kanalı açılacak. Sensör 5 V ile besleniyor ve ⚠️ **ÜZERİNDE GERİLİM BÖLÜCÜ YOK**.
 *
 * ============================================================================
 * ⚠️⚠️ SEVİYE UYUŞMAZLIĞI — DONANIM SINIRI (ölçüldü, tahmin değil)
 * ============================================================================
 * ACS712-30A: 0 A çıkışı = VCC/2 = **2,50 V**, hassasiyet **66 mV/A** (ratiometrik).
 * STM32F429 ADC referansı VREF+ = VDDA = **3,30 V**; pin absolute-maximum VDDA+0,3 = 3,60 V.
 *
 *   0 A      → 2,50 V   okunur
 *   +12,1 A  → 3,30 V   ADC TAVANI (üstü kırpılır, sayı YANLIŞ olur)
 *   +16,7 A  → 3,60 V   PİN ABSOLUTE-MAXIMUM (üstü ÇİPE ZARAR VERİR)
 *   +30 A    → 4,48 V   pin hasarı
 *
 * Yani bölücüsüz gerçek aralık **−30 A … +12 A**. Unipolar sürüşte akım TAM POZİTİF
 * tarafta olduğu için bu, kullanılan yarıyı sınırlar.
 *
 * → `AKIM_BOLUCU_ORANI` bir gerilim bölücü eklendiğinde tek satırda ayarlanır. Aslında
 *   ayarlamak bile GEREKMEZ: offset ölçümünden türetilen `k` katsayısı bölücüyü ve
 *   VCC sapmasını KENDİLİĞİNDEN yakalar (aşağıya bak). Sabit yalnız BELGELEME ve
 *   doygunluk tavanı hesabı içindir.
 * → Doygunluk SESSİZ KALMAZ: ham değer tavana yakınsa okuma `doygun` işaretlenir ve
 *   yanlış bir sayı yerine "güvenilmez" bildirilir (sahte ölçüm üretmemek kuralı).
 *
 * ============================================================================
 * KALİBRASYON — ESP'nin yöntemiyle AYNI, ama HATASI DÜZELTİLMİŞ
 * ============================================================================
 * Açılışta (bobinler KAPALI) her kanaldan N örnek alınır → `offset_v`.
 * Ratiometrik düzeltme: `k = offset_v / 2.5` · `hassasiyet = 0.066 * k`  [V/A]
 * `k`, ŞU ÜÇÜNÜ BİRDEN yakalar: (a) 5 V rayının gerçek değeri, (b) varsa gerilim
 * bölücü oranı, (c) sensörün offset toleransı.
 *
 * ⚠️ ESP'DEKİ HATA BURADA TEKRARLANMADI: `SensorManager::_deriveSensitivity()` bu `k`yı
 * hesaplıyor AMA `_readCurrent()` onu KULLANMIYOR — hassasiyeti `0.066` sabitiyle bölüyor
 * (SensorManager.cpp:508 vs 520-523). ESP'de VCC≈5 V ve bölücü yok olduğu için k≈1 ve
 * hata görünmüyordu; bir bölücü eklendiği an ESP'nin akımı ORAN KADAR yanlış olurdu.
 * Burada türetilen hassasiyet GERÇEKTEN kullanılır. Kapı: tests/test_stm_akim_firmware.py
 *
 * ============================================================================
 * NEDEN RMS
 * ============================================================================
 * Bobin akımı PWM ile kırpılmış bir dalgadır; tek örnek kırpma dalgasının rastgele bir
 * noktasını yakalar. ESP 10 örnek alıp RMS hesaplıyor (`sqrt(mean(i²))`,
 * SensorManager.cpp:499-515) — aynı büyüklük üretilsin diye burada da RMS.
 * ⚠️ `currentA` alanının anlamı bu yüzden DEĞİŞMEZ: geçmiş kayıtlarla kıyaslanabilir kalır.
 *
 * ============================================================================
 * ⚠️ BLOKLAMAMA
 * ============================================================================
 * `PEMF_Akim_Poll()` her çağrıda YALNIZ BİR kanalı okur (5 kanal → 5 tur). Her dönüşüm
 * beklemesi çevrim bütçelidir. Gerekçe `pemf_sensor.h` ile aynı: ana döngü tıkanırsa
 * ölü-adam watchdog'u SAHTE kopuş görüp TÜM bobinleri keser.
 ******************************************************************************
 */
#ifndef PEMF_AKIM_H
#define PEMF_AKIM_H

#include <stdbool.h>
#include <stdint.h>

/** Akım ölçülen bobin sayısı (bobin 1..5). Bobin 6-7'de ACS712 YOK (sahip kararı). */
#define PEMF_AKIM_BOBIN_SAYISI 5U

typedef struct {
  float amper;   /**< RMS akım, A. `ok` false iken ANLAMSIZ. */
  bool ok;       /**< false = kalibre edilmemiş / kanal okunamadı → alan GÖNDERİLMEZ */
  bool doygun;   /**< true = ADC tavanına dayandı (>~12 A, bölücüsüz) → sayı GÜVENİLMEZ */
  uint16_t ham;  /**< son ham ADC değeri (0-4095) — teşhis */
} PEMF_AkimVerisi_t;

/**
 * ADC1 + 5 kanalı hazırlar ve OFFSET KALİBRASYONU yapar.
 * ⚠️ BOBİNLER KAPALIYKEN çağrılmalı: `Coil_GpioInit()`ten SONRA, `Coil_TimInit()`ten
 * (50 kHz ISR) ÖNCE. Akım varken kalibre edilirse offset yanlış olur ve TÜM ölçümler kayar.
 */
void PEMF_Akim_Init(void);

/**
 * Bir kanalı okur (sırayla döner). Ana döngüden her turda çağrılmalı.
 * @return true → tüm kanallar bir kez tamamlandı (telemetri turu basılabilir)
 */
bool PEMF_Akim_Poll(void);

/** Son okumayı kopyalar. @param sira 0 = bobin 1 … 4 = bobin 5 */
void PEMF_Akim_Oku(uint32_t sira, PEMF_AkimVerisi_t *hedef);

#endif /* PEMF_AKIM_H */
