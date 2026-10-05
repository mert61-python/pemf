/* tests/firmware_host/dongu/dongu_win.c — ana döngü koşum takımının WINDOWS katmanı (1-G · D1.106).
 *
 * STM32 başlıklarını İÇERMEZ (kısa makroları — CRC, RCC, ADC, ERROR — Windows başlıklarıyla çakışır); modelle yalnız düz
 * C türleriyle konuşur (`dongu_kosum.c`). Görevleri: çevre birimi adres bölgelerini GERÇEK adreslerinde ayırmak
 * (0x40000000 + 512 KB, 0xE0000000 + 1 MB), sayfa koruması, VEH (erişim ihlali → model + TF; tek adım → model),
 * firmware'i ayrı iş parçacığında koşturmak ve bekçi (sanal zaman 20 sn ilerlemezse "ASILI", üst süre sınırı). */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int dk_erisim_basla(uintptr_t adr, int yazma);
int dk_bekleyen_var(void);
void dk_erisim_bitir(void);
int dk_hazirla(const char *senaryo);
void dk_firmware(void);
uint64_t dk_vt(void);
uint64_t dk_erisim(void);

void dw_bitir(int kod) {
  fflush(stdout);
  TerminateProcess(GetCurrentProcess(), (UINT)kod);
}

void dw_sayfa_kilitle(uintptr_t taban, int kilit) {
  DWORD eski;
  VirtualProtect((void *)taban, 0x1000U, kilit ? PAGE_NOACCESS : PAGE_READWRITE, &eski);
}

static LONG CALLBACK veh(PEXCEPTION_POINTERS ep) {
  EXCEPTION_RECORD *er = ep->ExceptionRecord;
  if ((er->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) && (er->NumberParameters >= 2U) &&
      (er->ExceptionInformation[0] != 8U)) {
    if (!dk_erisim_basla((uintptr_t)er->ExceptionInformation[1], er->ExceptionInformation[0] == 1U)) {
      /* modellenmeyen adres: firmware ya da model hatası — sessiz çökme yerine TANI ile çık */
      printf("!!! ERISIM IHLALI adr=0x%llX tur=%llu rip=0x%llX vt_us=%llu\n",
             (unsigned long long)er->ExceptionInformation[1], (unsigned long long)er->ExceptionInformation[0],
             (unsigned long long)ep->ContextRecord->Rip, (unsigned long long)(dk_vt() / 1000U));
      dw_bitir(8);
    }
    ep->ContextRecord->EFlags |= 0x100U; /* TF: komut koşsun, ardından tek adım istisnası */
    return EXCEPTION_CONTINUE_EXECUTION;
  }
  if ((er->ExceptionCode == EXCEPTION_SINGLE_STEP) && dk_bekleyen_var()) {
    ep->ContextRecord->EFlags &= ~0x100U;
    dk_erisim_bitir(); /* kesmeler burada teslim edilebilir (iç içe istisnalar kendi bağlamlarıyla) */
    return EXCEPTION_CONTINUE_EXECUTION;
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

int dw_bellek_kur(void) {
  /* çevre birimleri · RCC bit-band takma adları · Cortex-M çekirdek çevre birimleri (SCS, DWT) */
  static const struct {
    uintptr_t taban;
    SIZE_T boy;
  } bolge[] = {{0x40000000U, 0x80000U}, {0x42470000U, 0x2000U}, {0xE0000000U, 0x100000U}};
  for (size_t i = 0; i < sizeof(bolge) / sizeof(bolge[0]); i++) {
    void *p = VirtualAlloc((void *)bolge[i].taban, bolge[i].boy, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (p != (void *)bolge[i].taban) {
      printf("!!! OLUMCUL cevre birimi adresi ayrilamadi (0x%llX dolu)\n", (unsigned long long)bolge[i].taban);
      return 0;
    }
  }
  AddVectoredExceptionHandler(1, veh);
  return 1;
}

static DWORD WINAPI cpu_is(LPVOID arg) {
  (void)arg;
  dk_firmware();
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "kullanim: dongu_kosum.exe <senaryo.txt> [host_sinir_sn]\n");
    return 2;
  }
  static char tampon[1 << 20];
  setvbuf(stdout, tampon, _IOFBF, sizeof(tampon));
  if (!dk_hazirla(argv[1])) {
    dw_bitir(6);
  }
  const DWORD sinir_ms = (argc >= 3) ? (DWORD)(atoi(argv[2]) * 1000) : 600000U;
  HANDLE th = CreateThread(NULL, 16U << 20, cpu_is, NULL, STACK_SIZE_PARAM_IS_A_RESERVATION, NULL);
  if (!th) {
    printf("!!! OLUMCUL CPU is parcacigi acilamadi\n");
    dw_bitir(7);
  }
  uint64_t son_vt = 0U;
  int durgun = 0;
  const DWORD bas = GetTickCount();
  for (;;) {
    if (WaitForSingleObject(th, 1000U) == WAIT_OBJECT_0) {
      dw_bitir(5);
    }
    const uint64_t vt = dk_vt();
    durgun = (vt == son_vt) ? durgun + 1 : 0;
    son_vt = vt;
    if (durgun >= 20) { /* 20 sn ana makine zamanı boyunca sanal zaman ilerlemedi: firmware asılı (ör. Error_Handler) */
      SuspendThread(th);
      printf("!!! ASILI vt_us=%llu erisim=%llu\n", (unsigned long long)(vt / 1000U), (unsigned long long)dk_erisim());
      dw_bitir(3);
    }
    if (GetTickCount() - bas > sinir_ms) {
      SuspendThread(th);
      printf("!!! SURE ASIMI vt_us=%llu erisim=%llu\n", (unsigned long long)(vt / 1000U),
             (unsigned long long)dk_erisim());
      dw_bitir(4);
    }
  }
}
