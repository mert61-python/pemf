/* tests/firmware_host/esps3 — NVS (Preferences) taklidi (1-G · D1.102): bellek içi tek kayıt deposu; açılışta BOŞ
 * (taze kart → `loadState` "sürdürülecek durum yok"). */
#ifndef PEMF_HOST_S3_PREFERENCES_H
#define PEMF_HOST_S3_PREFERENCES_H

#include <stddef.h>
#include <string.h>

class Preferences {
 public:
  bool begin(const char *, bool) { return true; }
  void end() {}
  size_t putBytes(const char *, const void *veri, size_t boy) {
    if (boy > sizeof(_kayit)) {
      return 0;
    }
    memcpy(_kayit, veri, boy);
    _boy = boy;
    return boy;
  }
  size_t getBytes(const char *, void *hedef, size_t boy) {
    if (_boy == 0 || boy > _boy) {
      return 0;
    }
    memcpy(hedef, _kayit, boy);
    return boy;
  }

 private:
  unsigned char _kayit[64] = {0};
  size_t _boy = 0;
};

#endif /* PEMF_HOST_S3_PREFERENCES_H */
