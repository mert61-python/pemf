/* tests/firmware_host/dongu — her çeviri birimine ZORUNLU dahil edilen başlık (`cl /FI`), ana döngü koşum takımı.
 *
 * GCC'ye özgü üç yapı MSVC'de karşılanır (kaynak metni değişmez):
 *   `__weak`          → boş: HAL'in zayıf tanımlarını aparat derlemeden önce `<ad>__zayif` + `/alternatename` yapar
 *                       (güçlü tanım — main.c / koşum takımı — varsa o bağlanır; MSVC'de zayıf sembol yok).
 *   `__packed`        → boş (vendored HAL'de yalnız USB/ETH yapılarında; o modüller sürülmez).
 *   `__builtin_ctz`   → `_BitScanForward` (pemf_sensor.c, pin numarası). */
#ifndef PEMF_HOST_ON_H
#define PEMF_HOST_ON_H

#include <intrin.h>

#define __weak
#define __packed
/* hal_def.h'nin GCC/ARMCC/IAR dışı derleyici için TANIMLAMADIĞI üç makro (USB/ETH/FLASH başlıkları kullanır). */
#define __ALIGN_BEGIN
#define __ALIGN_END
#define __RAM_FUNC
#define __NOINLINE __declspec(noinline)

static __inline unsigned pemf_host_ctz(unsigned x) {
  unsigned long i;
  _BitScanForward(&i, x);
  return (unsigned)i;
}
#define __builtin_ctz(x) pemf_host_ctz((unsigned)(x))

void pemf_host_nop(void);

/* CPU SÜRESİ MODELİ (isteğe bağlı): firmware'in `snprintf` çağrıları koşum takımında sanal zamanı senaryonun
 * `SNPRINTF_NS` değeri kadar ilerletir (varsayılan 0 = CPU "anlık"). ⚠️ stdio.h ÖNCE dahil edilir: makro yalnız
 * firmware kaynağındaki ÇAĞRILARI yeniden adlandırır, CRT bildirimini değil. */
#include <stdio.h>
int pemf_host_snprintf(char *tampon, size_t boy, const char *bicim, ...);
#define snprintf pemf_host_snprintf

#endif /* PEMF_HOST_ON_H */
