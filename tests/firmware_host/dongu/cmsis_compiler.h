/* tests/firmware_host/dongu — CMSIS derleyici katmanının ana makine (x64) karşılığı (ana döngü koşum takımı, 1-G · D1.106).
 *
 * Gerçek `Drivers/CMSIS/Include/cmsis_compiler.h` bilinmeyen derleyicide `#error` verir; aparat `core_cm4.h`'yi
 * (DEĞİŞTİRMEDEN) derleme dizinine kopyalar, bu dosya onun yanına konur → `#include "cmsis_compiler.h"` bunu bulur.
 * İç işlevler (intrinsic) Cortex-M komutları yerine koşum takımı kancalarına gider: PRIMASK (`__disable_irq` /
 * `__enable_irq`) koşum takımının kesme teslimini kilitler, `__NOP` sanal zamanı 1 çevrim ilerletir, LDREX/STREX
 * düz okuma/yazmadır (tek çekirdek; yazmaç sayfası korumalı → erişim modelden geçer).
 *
 * İKİ DERLEYİCİ (Y344-1, istem 66 CT2 f2): MSVC x64 (`_MSC_VER`) ve GCC (mingw-w64 x64 — gcov ölçümü için). Yalnız derleyiciye
 * özgü sözdizimi ayrışır (öznitelikler, bayt çevirme / bit tarama iç işlevleri); koşum takımı kancaları ORTAK. */
#ifndef __CMSIS_COMPILER_H
#define __CMSIS_COMPILER_H

#include <stdint.h>

#if defined(_MSC_VER)
#include <intrin.h>

#define __ASM __asm
#define __INLINE __inline
#define __STATIC_INLINE static __inline
#define __STATIC_FORCEINLINE static __forceinline
#define __NO_RETURN __declspec(noreturn)
#define __USED
#define __WEAK
#define __PACKED
#define __PACKED_STRUCT struct
#define __PACKED_UNION union
#define __ALIGNED(x) __declspec(align(x))
#define __RESTRICT __restrict
#define __COMPILER_BARRIER() _ReadWriteBarrier()
#define PEMF_HOST_BSWAP32(v) _byteswap_ulong(v)
#define PEMF_HOST_BSWAP16(v) _byteswap_ushort(v)
#else /* GCC (mingw-w64): CMSIS'in GCC kolundaki (cmsis_gcc.h) öznitelik anlamları — gerçek kart derlemesiyle aynı */
#define __ASM __asm__
#define __INLINE inline
#define __STATIC_INLINE static inline
#define __STATIC_FORCEINLINE static inline __attribute__((always_inline))
#define __NO_RETURN __attribute__((__noreturn__))
#define __USED __attribute__((used))
#define __WEAK __attribute__((weak))
#define __PACKED __attribute__((packed, aligned(1)))
#define __PACKED_STRUCT struct __attribute__((packed, aligned(1)))
#define __PACKED_UNION union __attribute__((packed, aligned(1)))
#define __ALIGNED(x) __attribute__((aligned(x)))
#define __RESTRICT __restrict
#define __COMPILER_BARRIER() __asm__ volatile("" ::: "memory")
#define PEMF_HOST_BSWAP32(v) __builtin_bswap32(v)
#define PEMF_HOST_BSWAP16(v) __builtin_bswap16(v)
#endif

#define __UNALIGNED_UINT32(x) (*((uint32_t *)(x)))
#define __UNALIGNED_UINT16_WRITE(addr, val) ((*((uint16_t *)(addr))) = (val))
#define __UNALIGNED_UINT16_READ(addr) (*((const uint16_t *)(addr)))
#define __UNALIGNED_UINT32_WRITE(addr, val) ((*((uint32_t *)(addr))) = (val))
#define __UNALIGNED_UINT32_READ(addr) (*((const uint32_t *)(addr)))

void pemf_host_nop(void);
void pemf_host_irq_kapat(void);
void pemf_host_irq_ac(void);
uint32_t pemf_host_primask_al(void);
void pemf_host_primask_yaz(uint32_t deger);

#define __NOP() pemf_host_nop()
#define __WFI() pemf_host_nop()
#define __WFE() pemf_host_nop()
#define __SEV() ((void)0)
#define __ISB() ((void)0)
#define __DSB() ((void)0)
#define __DMB() ((void)0)
#define __BKPT(value) ((void)(value))
#define __CLREX() ((void)0)
#define __disable_irq() pemf_host_irq_kapat()
#define __enable_irq() pemf_host_irq_ac()
#define __get_PRIMASK() pemf_host_primask_al()
#define __set_PRIMASK(x) pemf_host_primask_yaz(x)
#define __enable_fault_irq() ((void)0)
#define __disable_fault_irq() ((void)0)
#define __get_BASEPRI() 0U
#define __set_BASEPRI(x) ((void)(x))
#define __set_BASEPRI_MAX(x) ((void)(x))
#define __get_FAULTMASK() 0U
#define __set_FAULTMASK(x) ((void)(x))
#define __get_CONTROL() 0U
#define __set_CONTROL(x) ((void)(x))
#define __get_IPSR() 0U
#define __get_APSR() 0U
#define __get_xPSR() 0U
#define __get_PSP() 0U
#define __set_PSP(x) ((void)(x))
#define __get_MSP() 0U
#define __set_MSP(x) ((void)(x))
#define __get_FPSCR() 0U
#define __set_FPSCR(x) ((void)(x))

__STATIC_INLINE uint32_t __REV(uint32_t v) { return PEMF_HOST_BSWAP32(v); }
__STATIC_INLINE uint32_t __REV16(uint32_t v) { return ((v & 0x00FF00FFU) << 8) | ((v >> 8) & 0x00FF00FFU); }
__STATIC_INLINE int16_t __REVSH(int16_t v) { return (int16_t)PEMF_HOST_BSWAP16((uint16_t)v); }
__STATIC_INLINE uint32_t __ROR(uint32_t v, uint32_t n) {
  n &= 31U;
  return (n == 0U) ? v : ((v >> n) | (v << (32U - n)));
}
__STATIC_INLINE uint32_t __RBIT(uint32_t v) {
  uint32_t r = 0U;
  for (uint32_t i = 0U; i < 32U; i++) {
    r = (r << 1) | ((v >> i) & 1U);
  }
  return r;
}
__STATIC_INLINE uint8_t __CLZ(uint32_t v) {
  uint8_t n = 0U;
  if (v == 0U) {
    return 32U;
  }
  while ((v & 0x80000000U) == 0U) {
    v <<= 1;
    n++;
  }
  return n;
}
__STATIC_INLINE uint8_t __LDREXB(volatile uint8_t *p) { return *p; }
__STATIC_INLINE uint16_t __LDREXH(volatile uint16_t *p) { return *p; }
__STATIC_INLINE uint32_t __LDREXW(volatile uint32_t *p) { return *p; }
__STATIC_INLINE uint32_t __STREXB(uint8_t v, volatile uint8_t *p) {
  *p = v;
  return 0U;
}
__STATIC_INLINE uint32_t __STREXH(uint16_t v, volatile uint16_t *p) {
  *p = v;
  return 0U;
}
__STATIC_INLINE uint32_t __STREXW(uint32_t v, volatile uint32_t *p) {
  *p = v;
  return 0U;
}
__STATIC_INLINE int32_t __SSAT(int32_t v, uint32_t sat) {
  const int32_t ust = (int32_t)((1U << (sat - 1U)) - 1U);
  const int32_t alt = -ust - 1;
  return (v > ust) ? ust : ((v < alt) ? alt : v);
}
__STATIC_INLINE uint32_t __USAT(int32_t v, uint32_t sat) {
  const uint32_t ust = (1U << sat) - 1U;
  return (v < 0) ? 0U : (((uint32_t)v > ust) ? ust : (uint32_t)v);
}

#endif /* __CMSIS_COMPILER_H */
