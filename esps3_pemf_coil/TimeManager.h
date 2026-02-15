#ifndef TIME_MANAGER_H
#define TIME_MANAGER_H

#include <Arduino.h>
#include "time.h"

class TimeManager {
public:
    TimeManager();
    void begin();
    unsigned long long getCurrentTimeMs();
    bool isSynced();
};

#endif
