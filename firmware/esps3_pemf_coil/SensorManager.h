#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MLX90393.h>
#include <Preferences.h>
#include "SharedDefs.h"

// ============================================================================
// SensorManager v1.2.0
//
// ACS712 Kalibrasyon Stratejisi (güncellenmiş):
//   - NVS'de geçerli offset varsa → yükle, boot'ta ölçüm YOK
//   - NVS boşsa / sürüm uyumsuzsa → taze ölçüm, kaydet
//   - forceCalibrate() → MQTT/buton ile zorla; PWM kapalıyken çağır
//
// Akım Okuma Stratejisi:
//   - PWM KAPALI → DC ortalama (32 örnek) + deadband
//   - PWM AÇIK   → AC RMS (100 örnek, 2 periyot)
//   - Her iki modda: |current| < CURRENT_NOISE_FLOOR → 0.0A
//
// ADC:
//   - analogReadMilliVolts() — ESP32-S3 dahili kalibrasyon eğrisi
// ============================================================================

class SensorManager {
public:
    SensorManager();

    // İki adımlı başlatma (önerilen):
    //   1. beginWithoutCalibration() → ADC + I2C
    //   2. coilController.begin()   → timer
    //   3. calibrate()              → NVS öncelikli kalibrasyon
    void beginWithoutCalibration();
    void calibrate();

    // Legacy wrapper (tek adım, eski uyumluluk)
    void begin();

    // Dış tetikleyici — MQTT veya buton
    // ⚠ Çağrılmadan önce PWM durdurulmuş olmalıdır!
    void forceCalibrate();

    // Core 1 loop içinden çağrılır
    SensorReadings readAll();

    /**
     * Manyetik boru hattini BIR adim ilerletir: bekleyen olcumu oku, zirveyi guncelle,
     * yenisini baslat. Saniyelik pencere dolunca zirveyi mandallar.
     *
     * ⚠️ `_mlxMag`e (Wire1) DOKUNAN TEK YER BURASIDIR — `readAll()` artik yalniz
     * mandallanmis degeri kopyalar. Iki yer birden I2C'ye girerse ayni bus'ta iki gorev
     * carpisir; bunu mutex'le degil, SAHIPLIGI TEK YERE TASIYARAK cozduk.
     *
     * Cagiran: TaskMagnetic (esps3_pemf_coil.ino), ~`MAG_ORNEK_GECIKME_MS` periyotla.
     */
    void pollMagnetic();

private:
    /**
     * MLX90393 olcek/hiz ayarlarini uygular — **TEK KAYNAK**.
     *
     * ⚠️ NEDEN AYRI FONKSIYON (2026-09-11): bu ayarlar IKI yerde yaziliydi — `_initI2C()`
     * ve `recoverI2CBus(1)`. Olcegi yalniz birinde guncellemek, sensor bir kez hat
     * kurtarmasindan gectikten SONRA sessizce ESKI aralia (±12,3 mT) donmesi demekti:
     * sahibin 10 mT'lik alani o andan itibaren SARAR ve kucuk okunur, hicbir uyari cikmaz.
     * Bu deponun kayitli "sihirli sayi ikinci yerde" arizasinin ta kendisi.
     */
    void _yapilandirMag();

public:

    // PWM durumu bildirimi
    void setPWMActive(bool active);

    // I2C Bus Recovery
    void recoverI2CBus(int busNumber);

    // Kalibrasyon durumu sorgulama
    bool isCalibrated() const { return _calibrated; }
    float getAcsOffset() const { return _acsOffset; }
    float getAcsSensitivity() const { return _acsSensitivity; }

private:
    Adafruit_MLX90614 _mlxTemp;
    Adafruit_MLX90393 _mlxMag;
    Preferences       _prefs;

    // Sensör durumu
    bool _tempOk;
    bool _magOk;

    // PWM takibi
    bool _pwmActive;

    // Kalibrasyon durumu
    bool  _calibrated;      // true = NVS'den yüklendi veya başarıyla ölçüldü
    float _acsOffset;       // [V]   0A'da ölçülen ADC gerilimi
    float _acsSensitivity;  // [V/A] = ACS712_BASE_SENSITIVITY × (_acsOffset / ACS712_VCC_HALF)

    // Pipelined manyetik okuma
    bool _magMeasurementPending;

    // PWM aktifken max değerler
    float _maxMagneticField;

    // ── SANIYELIK ZIRVE PENCERESI (sahip karari 2026-09-11) ───────────────────
    unsigned long _magPencereBitisMs; /**< pencere kapanis damgasi */
    float    _magBirikenZirve;        /**< pencere ici en buyuk |B| (mT) */
    uint32_t _magBirikenOrnek;        /**< pencere ici gecerli ornek sayisi */
    bool     _magBirikenDoygun;
    float    _magBirikenX, _magBirikenY, _magBirikenZ; /**< ZIRVE aninin eksenleri */
    // Mandallanmis (readAll'in okudugu) degerler:
    float    _magZirveMt;
    uint16_t _magZirveOrnek;
    bool     _magZirveDoygun;
    float    _magZirveX, _magZirveY, _magZirveZ;
    /**
     * Mandal koruyucusu. `pollMagnetic()` (TaskMagnetic) yazar, `readAll()` (ControlTask)
     * okur — AYRI CEKIRDEKLERDE. 32-bit hizalanmis tek yazma atomiktir ama BES DEGER BIR
     * KUMEDIR: koruma olmadan zirve N. pencereden, ornek sayisi N+1'den gelebilir ve
     * "1 orneklik 8 mT zirve" gibi imkansiz bir satir uretilirdi.
     */
    portMUX_TYPE _magMux;
    /**
     * I2C KURULUMU BITTI MI. `pollMagnetic()` bu bayrak set edilene kadar HICBIR SEY YAPMAZ.
     *
     * ⚠️ NEDEN SART (yarissiz baslangic): TaskMagnetic, ControlTask'in `beginWithoutCalibration()`
     * icindeki `delay()`leri sirasinda calisabilir (delay teslim eder). O anda Wire1 HENUZ
     * kurulmamistir; `_magOk` de false oldugu icin `pollMagnetic()` dogrudan
     * `recoverI2CBus(1)`e girer ve KURULUMLA CAKISIR — sensor ne kurulur ne kurtarilir,
     * acilista sessizce olur. Bayrak `_initI2C()` bitiminde set edilir.
     */
    bool _i2cHazir;
    float _maxCurrent;

    // Hata sayaçları
    int _tempFailCount;
    int _magFailCount;
    int _currentFailCount;
    static const int CRITICAL_FAIL_THRESHOLD = 10;
    static const int I2C_RECOVERY_THRESHOLD  = 5;
    // 2026-09-08 (sahip): sensor koptugunda cihaz YENIDEN BASLAMAZ. Kopan sensor cevrimdisi
    // isaretlenir (I2C trafigi kesilir → dongu bloklanmaz), 1→2→5→10→30 sn geri-cekilmeyle
    // TEK bounded yeniden baglanma denemesi yapilir; tak-cikar (hot-plug) kendiliginden toparlar.
    uint32_t _tempNextRetryMs;
    uint32_t _magNextRetryMs;
    uint8_t  _tempRetryStep;
    uint8_t  _magRetryStep;
    static uint32_t _geriCekilmeMs(uint8_t step);

    // Moving average (şu an kullanılmıyor; ileride aktifleştirilebilir)
    float _tempObjectFiltered;
    float _tempAmbientFiltered;
    float _magFieldFiltered;
    float _currentFiltered;
    static constexpr float FILTER_ALPHA = 0.2f;

    // Dahili yardımcılar
    void  _initI2C();
    void  _calibrateCurrent(bool force);
    void  _deriveSensitivity();
    float _readCurrent();
    float _applyFilter(float newValue, float& filteredValue);
};

#endif // SENSOR_MANAGER_H
