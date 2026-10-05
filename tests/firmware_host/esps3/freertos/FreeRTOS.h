/* tests/firmware_host/esps3 — FreeRTOS taklidi (1-G · D1.102). Yalnız `SharedDefs.h` LOG makrolarının ve kuyruk
 * bildirimlerinin derlenmesi için; `serialMutex` aparatta NULL → LOG makroları hiçbir şey yazmaz. */
#ifndef PEMF_HOST_S3_FREERTOS_H
#define PEMF_HOST_S3_FREERTOS_H

#include <stdint.h>

typedef int BaseType_t;
typedef uint32_t TickType_t;
typedef void *SemaphoreHandle_t;
#define pdTRUE 1
#define pdFALSE 0
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))

inline BaseType_t xSemaphoreTake(SemaphoreHandle_t, TickType_t) { return pdFALSE; }
inline BaseType_t xSemaphoreGive(SemaphoreHandle_t) { return pdTRUE; }

#endif /* PEMF_HOST_S3_FREERTOS_H */
