/* tests/firmware_host/esp8266/json_sayi_kosum.cpp — GERÇEK 8266 `JsonSayi.h` (bayt bayt kopya) ana makinede (1-G · D1.62).
 * Kullanım: json_sayi_kosum.exe → her satır "<girdi> <basamak> <çıktı>" (nan, inf, -inf ve sonlu örnekler). */
#include <math.h>
#include <stdio.h>

#include "JsonSayi.h"

int main() {
  const struct {
    const char *ad;
    float v;
    int b;
  } vakalar[] = {{"nan", NAN, 2}, {"inf", INFINITY, 2}, {"-inf", -INFINITY, 3}, {"36.5", 36.5f, 2},
                 {"0.37416", 0.37416f, 3}, {"0", 0.0f, 2}, {"-1.25", -1.25f, 2}};
  for (const auto &v : vakalar) {
    char tampon[16];
    printf("%s %d %s\n", v.ad, v.b, jsonSayi(tampon, sizeof(tampon), v.v, v.b));
  }
  return 0;
}
