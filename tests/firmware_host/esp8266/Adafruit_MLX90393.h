/* tests/firmware_host/esp8266 — Adafruit_MLX90393 taklidi (manyetik alan; eksenler µT, arıza `sensor_kosum.cpp`'den). */
#ifndef PEMF_HOST_MLX90393_H
#define PEMF_HOST_MLX90393_H

#include <Arduino.h>

enum mlx90393_gain { MLX90393_GAIN_5X, MLX90393_GAIN_4X, MLX90393_GAIN_3X, MLX90393_GAIN_2_5X, MLX90393_GAIN_2X,
                     MLX90393_GAIN_1_67X, MLX90393_GAIN_1_33X, MLX90393_GAIN_1X };
enum mlx90393_axis { MLX90393_X, MLX90393_Y, MLX90393_Z };
enum mlx90393_resolution { MLX90393_RES_16, MLX90393_RES_17, MLX90393_RES_18, MLX90393_RES_19 };
enum mlx90393_filter { MLX90393_FILTER_0, MLX90393_FILTER_1, MLX90393_FILTER_2, MLX90393_FILTER_3,
                       MLX90393_FILTER_4, MLX90393_FILTER_5, MLX90393_FILTER_6, MLX90393_FILTER_7 };

class Adafruit_MLX90393 {
 public:
  bool begin_I2C(uint8_t adres = 0x0C, void *wire = nullptr);
  bool setGain(mlx90393_gain) { return true; }
  bool setResolution(mlx90393_axis, mlx90393_resolution) { return true; }
  bool setFilter(mlx90393_filter) { return true; }
  bool readData(float *x, float *y, float *z);
};

#endif /* PEMF_HOST_MLX90393_H */
