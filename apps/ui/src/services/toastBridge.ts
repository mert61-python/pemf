// Author: mertaygn, cglrgrkn
// F-6 (prod-readiness): service katmanının (apiClient — React hook'u KULLANAMAZ) non-blocking
// toast göndermesi için köprü. ToastProvider mount'ta `setToastHandler(showToast)` kaydeder;
// kayıtlı değilse `emitToast` false döner → çağıran bloklayan `platformAlert`'e fallback yapar.
type ToastType = "success" | "error" | "info";

let _handler: ((message: string, type?: ToastType) => void) | null = null;

export function setToastHandler(fn: ((message: string, type?: ToastType) => void) | null): void {
  _handler = fn;
}

/** Toast göster; handler kayıtlı+başarılıysa true, aksi (fallback gerek) false döner. */
export function emitToast(message: string, type: ToastType = "info"): boolean {
  if (_handler) {
    try {
      _handler(message, type);
      return true;
    } catch {
      /* handler patlarsa fallback'e düş */
    }
  }
  return false;
}
