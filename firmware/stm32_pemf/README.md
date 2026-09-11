# stm32_pemf — STM32F429 Bobin Sürücüsü CubeIDE Projesi (bobin 1-7) · TEK KAYNAK

> ⚠️ **GÜNCELLEME 2026-09-11 — `stm32_pemf_unipolar` AYNA PROJESİ KALDIRILDI.**
> **TEK kaynak: `firmware/stm32_pemf`.** `scripts/stm_unipolar_senkronla.py`, ayna kapısı
> ve mirror'ın `.rar` arşivi silindi (git geçmişinde duruyorlar).
>
> Sürüş kipi artık İKİ katmanlı:
> | Katman | Nerede | Ne |
> |---|---|---|
> | **Yetenek** (derleme zamanı) | `PEMF_BOBIN_UNIPOLAR_MASKESI = 0x60` → `g_yalniz_unipolar[]` | Bobin 6-7 sürücüsünde ikinci yarım köprü **fiziksel olarak yok** → bunlar **daima** unipolar. TABAN'dır, seçim değil. |
> | **İstek** (çalışma zamanı) | Paketin `unipolar_maskesi` baytı → `Coil_KipUygula()` | Arayüzdeki **Sürüş Kipi** düğmesi. Yalnız yetenekli bobinleri etkiler. |
>
> Etkin kip: `g_unipolar[i] = g_yalniz_unipolar[i] || istenen[i]` — ACK'te `K=<maske>` döner.
> ⚠️ Paket bu yüzden **121 bayt** (120 → 121). **ATOMİK SEVK:** backend güncellenince kart
> MUTLAKA yeniden flaşlanır, yoksa her komut CRC'den düşer ve hiçbir bobin çalışmaz.


**2026-08-19'dan beri derleme BURADAN yapılır** (sahip kararı) — masaüstündeki eski
`Desktop\PEMF` kopyası silindi. Donanım: NUCLEO-F429ZI (STM32F429ZITx), yazılım DDS
**7 kanal** + PB1'den ESP'lere donanım faz senkron darbesi.
Masaüstüne temiz bir kopya çıkarmak için (derleme artığı TAŞIMAZ, protokol aşamasını
DOĞRULAR): `python scripts/stm_workspace_kopyala.py`.

## CubeIDE'de açma / derleme

1. Workspace'i **deponun DIŞINDA** seç (kullanılan: `C:\Users\merta\STM32CubeIDE\workspace_1.17.0`) —
   workspace `.metadata` üretir, depoya çöp girmesin (yanlışlıkla içeri seçilirse `.gitignore` yakalar).
2. **File → Import → General → Existing Projects into Workspace** → root = bu klasör →
   ⚠️ **"Copy projects into workspace" İŞARETSİZ** (kopya = ikinci kaynak = yasak) → Finish.
   (Workspace'te aynı adlı eski/askıda "PEMF" kaydı varsa import kutusu seçilemez —
   önce Project Explorer'da o girdiyi Delete edin, "contents on disk" İŞARETSİZ.)
3. **Project → Build Project** (Ctrl+B). Başarı: `Build Finished. 0 errors` +
   `Debug/PEMF.elf` (Debug/ gitignore'lu — build çıktısı depoya girmez).
4. Ölçülen referans (2026-09-11, printf-float düzeltmesinden SONRA): **0 hata 0 uyarı**
   (`-Wall -Wextra`), **33.272 B flash / 4.472 B bss**. (Düzeltme öncesi 21.340 B idi;
   fark `_printf_float`ın ~11,5 KB'ı — aşağıya bakın.)
   Banner: `STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 + HW_SYNC@PB1)`.
   ⚠️ **`5-ch` görüyorsanız ESKİ ikili yüklenmiştir** — Clean → Build → Debug tekrar.
   Hızlı kontrol: `python scripts/stm_firmware_kimligi.py`.
   Derleme CubeIDE'siz de doğrulanabilir: `python scripts/firmware_derle.py`.

## ⚠️⚠️ ASLA KALDIRMAYIN — `g_printf_float_zorla`

`Core/Src/main.c` başında şu iki satır var:

```c
extern int _printf_float(void);
void *const g_printf_float_zorla = (void *)&_printf_float;
```

**Bunlar silinirse cihazın BÜTÜN sensörleri sessizce ölür.** Proje `-specs=nano.specs`
(newlib-nano) ile bağlanıyor ve newlib-nano'da `printf` ailesinin **float dönüşümü
varsayılan olarak bağlanmaz**. O zaman `snprintf(..., "%.3f", x)` hiçbir şey basmaz ve
**hata da vermez**; telemetri hatta şöyle çıkar:

```
-> STM_TELE: C=6,T=,A=,B=,N=412,XN=,XP=,YN=,YP=,ZN=,ZP=
```

Backend sayısal alan bulamayıp satırı reddeder → **sıcaklık, manyetik alan ve akım arayüze
bir daha hiç ulaşmaz**; seans CSV'si bomboş çıkar. ACK (`STM_OK`) tamsayı biçimleyicilerle
kurulduğu için ETKİLENMEZ → arıza "cihaz çalışıyor ama sensörler bozuk" gibi görünür ve
I2C/kabloda aranır. 2026-09-11'de sahada tam olarak bu yaşandı.

⚠️ **Neden linker bayrağı (`-u _printf_float`) değil:** bayrak CubeIDE proje ayarında yaşar
ve yeniden import / ayar sıfırlama / başka makinede derleme ile **sessizce kaybolur**.
Kaynaktaki başvuru her IDE ve her makinede taşınır.

Kapılar: `tests/test_stm_printf_float_kapisi.py` (kaynak + belirti) ve
`scripts/firmware_derle.py` (bağlanan ELF'te `nm` ile sembolü ARAR, yoksa derleme DÜŞER).
⚠️ Derleme betiğine `-u _printf_float` **EKLENMEZ** — eklerse kendi bayrağını doğrular,
CubeIDE'nin ürettiği ikiliyi ölçmez.

## 🧲 BOŞTA SENSÖR ÖZ-TESTİ (`STM_MAGCHK`)

Kart açılışta, **daha hiç bobin sürülmemişken** gördüğü manyetik alanı bir kez bildirir ve
yorumlar:

```
-> STM_MAGCHK: C=6 ilk-pencere |B|=0.047mT N=412 -> NORMAL (dunya alani ~47uT)
```

| Okunan | Anlamı |
|---|---|
| **0,02–0,08 mT** | NORMAL — dünyanın manyetik alanı (Türkiye ~47 µT). Beklenen budur. |
| **~0,000 mT** | ŞÜPHELİ — sensör ACK veriyor ama eksenler okumuyor olabilir. |
| **> 0,15 mT** | YÜKSEK DC OFSET — yakında demir/mıknatıs var. |

⚠️ **Boşta sıfır OKUMAZ.** Dünya alanı bir **DC ofsettir**: `B=` (büyüklük) ona biner, ama
eksen uçlarından türetilen **tepeden-tepeye** (`pp_x/pp_y/pp_z`) ofsetten etkilenmez.
Bu yüzden sürüş kipi / faz karşılaştırmaları `pp_*` üzerinden yapılmalıdır.
Aynı eşikler ESP-S3 tarafında da var (`SharedDefs.h`, `MAGCHK_*`) — ayrışırlarsa iki kartı
karşılaştırmak anlamsızlaşır.

## ⚠️ İKİ KURAL

1. **CubeMX "Generate Code" YASAK** — `PEMF.ioc`'u Device Configuration ekranında açıp
   kod üretmek `Core/Src/main.c`'yi iskeletle EZER (dosya elle yazılmış, USER CODE
   işaretçisi yok). `.ioc` değişecekse: üret → main.c'yi `git checkout`la geri al
   (`git checkout -- firmware/stm32_pemf/Core/Src/main.c`). Kapı: `tests/test_stm_main_saglik.py`.
2. **main.c TEK dosyadır** — kanonik: `Core/Src/main.c` (BU proje). Eski kök kopya
   `firmware/main.c` 2026-08-19'da SİLİNDİ (iki kopya bir kez gerçekten ayrışmıştı —
   masaüstü 2 ay geride kalmıştı); `test_stm_main_saglik.py` geri gelmesini de engeller.
   Başka yere KOPYALAMAYIN — derleme dahil her şey bu dosyayı okur.
   **İstisna YOK** (2026-09-11): ayna proje kaldırıldı, CubeIDE'de **tek** proje import edilir: `PEMF`.
   Workspace'te askıda bir `PEMF_UNIPOLAR` kaydı kaldıysa Project Explorer'da Delete edin
   ("contents on disk" İŞARETSİZ) — yoksa yanlışlıkla o eski ikili flaşlanabilir.

   ⚠️ **KABLOLAMA (sahip bildirimi 2026-09-11):** bobin 1-5'te **iki PWM de BAĞLI** (tam köprü):
   IN_A = PC8 PC9 PD10 PC6 PA8, IN_B = PD12 PE10 PD11 PC7 PA9. Bobin 6-7'de sürücü tek yönlü,
   yalnız IN_A kullanılır. `PEMF_BOBIN_TERS_MASKESI` **0x00** ve öyle kalır (sahip kararı
   2026-09-10: ters sargı bobin uçları çevrilerek donanımda düzeltildi).
   ⚠️ Bu README daha önce "IN_B pinleri fiziksel olarak bağlı değil" diyordu — **YANLIŞTI**,
   sahip düzeltti. Yanlış bir kablolama iddiası bipolar kazancını "etkisiz" sandırıyordu.

## Tezgâh

Flash + `[FIX-1c]` doğrulaması: `docs/VERIFICATION.md` §9. ESP senkron bağlantısı:
PB1 → S3 GPIO7 (+ GND ortak); 8266'ya sync BAĞLANMAZ (tek faz kararı).
