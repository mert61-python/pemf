# stm32_pemf — STM32F429 Bobin Sürücüsü CubeIDE Projesi (bobin 1-5) · TEK KAYNAK

**2026-08-19'dan beri derleme BURADAN yapılır** (sahip kararı) — masaüstündeki eski
`Desktop\PEMF` kopyası silindi. Donanım: NUCLEO-F429ZI (STM32F429ZITx), yazılım DDS
5 kanal + PB1'den ESP'lere donanım faz senkron darbesi.

## CubeIDE'de açma / derleme

1. Workspace'i **deponun DIŞINDA** seç (örn. `C:\CubeWS`) — workspace `.metadata` üretir,
   depoya çöp girmesin (yanlışlıkla içeri seçilirse `.gitignore` yakalar).
2. **File → Open Projects from File System… → Directory** → bu klasör → Finish.
3. **Project → Build Project** (Ctrl+B). Başarı: `Build Finished. 0 errors` +
   `Debug/PEMF.elf` (Debug/ gitignore'lu — build çıktısı depoya girmez).
4. Ölçülen referans (2026-08-19): 0 hata 0 uyarı (`-Wall`), text 21.5 KB / bss 2.9 KB.

## ⚠️ İKİ KURAL

1. **CubeMX "Generate Code" YASAK** — `PEMF.ioc`'u Device Configuration ekranında açıp
   kod üretmek `Core/Src/main.c`'yi iskeletle EZER (dosya elle yazılmış, USER CODE
   işaretçisi yok). `.ioc` değişecekse: üret → main.c'yi `firmware/main.c`'den geri kopyala.
2. **main.c İKİ KOPYADA BAYT-BAYT AYNI tutulur** — kanonik `firmware/main.c` ↔ buradaki
   `Core/Src/main.c`. Ayrışma `tests/test_stm_main_tek_kaynak.py` kapısıyla kilitli:
   main.c değişecekse İKİSİ BİRDEN güncellenir (bu ayrışma bir kez gerçekten yaşandı;
   masaüstü kopya 2 ay geride kalmıştı).

## Tezgâh

Flash + `[FIX-1c]` doğrulaması: `docs/VERIFICATION.md` §9. ESP senkron bağlantısı:
PB1 → S3 GPIO7 (+ GND ortak); 8266'ya sync BAĞLANMAZ (tek faz kararı).
