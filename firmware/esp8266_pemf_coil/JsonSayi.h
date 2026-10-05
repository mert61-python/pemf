#ifndef JSON_SAYI_H
#define JSON_SAYI_H

#include <math.h>
#include <stdio.h>
#include <string.h>

/**
 * D1.62 (B-8.12): sensör alanını JSON SAYISI olarak yazar — sonlu değilse (NaN/±inf) `null`.
 *
 * NEDEN: SensorManager artık ölçüm YOKKEN (ACS712 takılı değil, sensör hiç sağlıklı okunmadı) NaN döner — eskiden yapıcı
 * sabitlerini (30,00 °C) ya da yüzen pinden hesaplanan akımı "ölçüldü" diye yayınlıyordu. `snprintf("%.2f", NAN)` ise
 * `nan` yazar: GEÇERSİZ JSON — backend iletinin TAMAMINI atar (sıcaklık dahil). `null` S3/ArduinoJson ile aynı sözleşmedir.
 * @param tampon en az 16 bayt  @return tampon
 */
static inline const char *jsonSayi(char *tampon, size_t boy, float deger, int basamak) {
  if (!isfinite(deger)) {
    snprintf(tampon, boy, "null");
  } else {
    snprintf(tampon, boy, "%.*f", basamak, (double)deger);
  }
  return tampon;
}

#endif /* JSON_SAYI_H */
