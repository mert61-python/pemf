#ifndef TIME_MANAGER_H
#define TIME_MANAGER_H

#include <Arduino.h>
#include <time.h>
#include <sys/time.h>  // gettimeofday için gerekli
#include "SharedDefs.h"  // LOG makroları için

class TimeManager {
public:
    TimeManager(const char* ntpServer = "pool.ntp.org",
                long gmtOffsetSec = 10800,
                int daylightOffsetSec = 0);

    void begin();  // WiFi bağlantısı kurulduktan sonra çağrılmalı
    void update();  // Loop'ta sürekli çağrılacak (gerekirse)

    // Zaman sorgulama
    bool isSynced();
    unsigned long long getCurrentTimeMs();  // Artık sistem saatini direkt okur
    time_t getCurrentEpoch();  // Epoch time (saniye)

private:
    const char* _ntpServer;
    long _gmtOffsetSec;
    int _daylightOffsetSec;
    bool _timeSynced;
};

#endif
