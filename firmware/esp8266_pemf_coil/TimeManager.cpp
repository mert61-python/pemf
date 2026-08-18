#include "TimeManager.h"
#include "SharedDefs.h"  // LOG makroları için

TimeManager::TimeManager(const char* ntpServer, long gmtOffsetSec, int daylightOffsetSec) {
    _ntpServer = ntpServer;
    _gmtOffsetSec = gmtOffsetSec;
    _daylightOffsetSec = daylightOffsetSec;
    _timeSynced = false;
}

void TimeManager::begin() {
    LOG_PRINTLN("[NTP] Zaman senkronizasyonu başlatılıyor...");

    // NTP Redundancy: Birden fazla NTP sunucusu ekle (yüksek kullanılabilirlik için)
    const char* ntpServers[] = {
        "pool.ntp.org",           // Primary: NTP Pool Project (global)
        "time.google.com",        // Secondary: Google Public NTP
        "time.cloudflare.com"     // Tertiary: Cloudflare NTP
    };

    // 3 NTP sunucusu ekle (redundancy için)
    // ESP8266 otomatik olarak sırayla dener, ilk başarılı olanı kullanır
    configTime(_gmtOffsetSec, _daylightOffsetSec,
               ntpServers[0], ntpServers[1], ntpServers[2]);

    LOG_PRINTLN("[NTP] ✓ 3 NTP sunucusu yapılandırıldı (redundancy aktif)");
    LOG_PRINTF("  Primary: %s\n", ntpServers[0]);
    LOG_PRINTF("  Secondary: %s\n", ntpServers[1]);
    LOG_PRINTF("  Tertiary: %s\n", ntpServers[2]);

    _timeSynced = false;
}

void TimeManager::update() {
    // Sadece zamanın alınıp alınmadığını kontrol ediyoruz.
    // Artık manuel hesaplama yapmıyoruz.
    if (!_timeSynced) {
        time_t now = time(nullptr);
        // 2020 yılından (epoch ~1600000000) büyükse saat gelmiş demektir
        if (now > 1600000000) {
            _timeSynced = true;
            LOG_PRINTLN("\n[NTP] Zaman senkronize edildi!");
            LOG_PRINTF("[NTP] Şu anki Epoch: %ld\n", (long)now);
        }
    }
}

bool TimeManager::isSynced() {
    return _timeSynced;
}

unsigned long long TimeManager::getCurrentTimeMs() {
    if (!_timeSynced) {
        return 0;
    }

    struct timeval tv;
    gettimeofday(&tv, NULL);

    // tv.tv_sec: Saniye cinsinden epoch (örn: 1732386000)
    // tv.tv_usec: Mikrosaniye (örn: 500123)

    // Saniyeyi 1000 ile çarpıp milisaniyeye çeviriyoruz.
    // Mikrosaniyeyi 1000'e bölüp milisaniyeye çeviriyoruz.
    unsigned long long time_ms = ((unsigned long long)tv.tv_sec * 1000) + (tv.tv_usec / 1000);

    return time_ms;
}

time_t TimeManager::getCurrentEpoch() {
    return time(nullptr);
}
