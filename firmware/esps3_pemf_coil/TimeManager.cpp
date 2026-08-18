#include "TimeManager.h"

const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec = 0;
const int   daylightOffset_sec = 0;

TimeManager::TimeManager() {
}

void TimeManager::begin() {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
}

unsigned long long TimeManager::getCurrentTimeMs() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (unsigned long long)tv.tv_sec * 1000ULL + (unsigned long long)tv.tv_usec / 1000ULL;
}

bool TimeManager::isSynced() {
    struct tm timeinfo;
    if(!getLocalTime(&timeinfo)){
        return false;
    }
    return true;
}
