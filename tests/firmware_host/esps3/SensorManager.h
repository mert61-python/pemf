/* tests/firmware_host/esps3 — SensorManager yerine-geçen bildirim (1-G · D1.102). `CoilController.cpp` yalnız
 * `readAll` (self-test), `setPWMActive`, `forceCalibrate` çağırır; davranış `s3_kosum.cpp`'de (sensör takılı değil). */
#ifndef PEMF_HOST_S3_SENSOR_MANAGER_H
#define PEMF_HOST_S3_SENSOR_MANAGER_H

#include "SharedDefs.h"

class SensorManager {
 public:
  SensorReadings readAll();
  void setPWMActive(bool aktif);
  void forceCalibrate();
};

#endif /* PEMF_HOST_S3_SENSOR_MANAGER_H */
