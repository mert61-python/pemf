"""COM port'tan gelen ham veriyi gösterir — firmware debug aracı."""
import time

import serial

PORT   = "COM10"
BAUD   = 115200    # USB CDC'de önemsiz ama gerekli
LISTEN = 15        # saniye

def main():
    print(f"\n{'='*55}")
    print(f"  STM32 USB CDC Sniffer — {PORT} @ {BAUD} baud")
    print(f"  {LISTEN} saniye dinleniyor...")
    print(f"{'='*55}\n")

    try:
        s = serial.Serial(PORT, BAUD, timeout=0.5, dsrdtr=False, rtscts=False)
    except Exception as e:
        print(f"❌ Port açılamadı: {e}")
        return

    start = time.monotonic()
    total_bytes = 0
    lines_seen  = 0

    while time.monotonic() - start < LISTEN:
        try:
            raw = s.readline()
        except Exception as e:
            print(f"❌ Okuma hatası: {e}")
            break

        if not raw:
            continue

        total_bytes += len(raw)
        lines_seen  += 1
        elapsed = time.monotonic() - start
        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        print(f"[{elapsed:6.2f}s] TEXT : {text!r}")
        print(f"         HEX  : {raw.hex(' ')}")
        print()

    s.close()
    print(f"\n{'='*55}")
    print(f"  Toplam: {lines_seen} satır, {total_bytes} byte alındı")
    if total_bytes == 0:
        print("  ⚠️  HİÇ VERİ GELMEDİ — firmware STM_READY göndermiyordur")
        print("     veya USB CDC init (MX_USB_DEVICE_Init) çağrılmamış.")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()
