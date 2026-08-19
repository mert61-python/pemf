# stm32_pemf — STM32F429 Bobin Sürücüsü CubeIDE Projesi (bobin 1-5) · TEK KAYNAK

**2026-08-19'dan beri derleme BURADAN yapılır** (sahip kararı) — masaüstündeki eski
`Desktop\PEMF` kopyası silindi. Donanım: NUCLEO-F429ZI (STM32F429ZITx), yazılım DDS
5 kanal + PB1'den ESP'lere donanım faz senkron darbesi.

## CubeIDE'de açma / derleme

1. Workspace'i **deponun DIŞINDA** seç (kullanılan: `C:\Users\merta\STM32CubeIDE\workspace_1.17.0`) —
   workspace `.metadata` üretir, depoya çöp girmesin (yanlışlıkla içeri seçilirse `.gitignore` yakalar).
2. **File → Import → General → Existing Projects into Workspace** → root = bu klasör →
   ⚠️ **"Copy projects into workspace" İŞARETSİZ** (kopya = ikinci kaynak = yasak) → Finish.
   (Workspace'te aynı adlı eski/askıda "PEMF" kaydı varsa import kutusu seçilemez —
   önce Project Explorer'da o girdiyi Delete edin, "contents on disk" İŞARETSİZ.)
3. **Project → Build Project** (Ctrl+B). Başarı: `Build Finished. 0 errors` +
   `Debug/PEMF.elf` (Debug/ gitignore'lu — build çıktısı depoya girmez).
4. Ölçülen referans (2026-08-19 akşam, v2.3.0 SYM-BIPOLAR): **0 hata 0 uyarı** (`-Wall`);
   `STM_READY: DDS v2.3 (5-ch SYM-BIPOLAR + HW_SYNC@PB1)` dizesi binary'de.

## ⚠️ İKİ KURAL

1. **CubeMX "Generate Code" YASAK** — `PEMF.ioc`'u Device Configuration ekranında açıp
   kod üretmek `Core/Src/main.c`'yi iskeletle EZER (dosya elle yazılmış, USER CODE
   işaretçisi yok). `.ioc` değişecekse: üret → main.c'yi `git checkout`la geri al
   (`git checkout -- firmware/stm32_pemf/Core/Src/main.c`). Kapı: `tests/test_stm_main_saglik.py`.
2. **main.c TEK dosyadır** — kanonik: `Core/Src/main.c` (BU proje). Eski kök kopya
   `firmware/main.c` 2026-08-19'da SİLİNDİ (iki kopya bir kez gerçekten ayrışmıştı —
   masaüstü 2 ay geride kalmıştı); `test_stm_main_saglik.py` geri gelmesini de engeller.
   Başka yere KOPYALAMAYIN — derleme dahil her şey bu dosyayı okur.

## Tezgâh

Flash + `[FIX-1c]` doğrulaması: `docs/VERIFICATION.md` §9. ESP senkron bağlantısı:
PB1 → S3 GPIO7 (+ GND ortak); 8266'ya sync BAĞLANMAZ (tek faz kararı).
