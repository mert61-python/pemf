# STM32 Uzaktan Güncelleme + Firmware/Client Uyumsuzluğu — Plan

**Tarih:** 2026-09-14 · **Durum:** **§1 UYGULANDI (2026-09-18)** · §2 uzaktan güncelleme
hâlâ plan (yayın donmuş) · Ölçümler bu makinede yapıldı.

> ## ✅ §1 UYUM KAPISI YAZILDI — 2026-09-18
>
> | Parça | Nerede |
> |---|---|
> | Banner ayrıştırıcı (**tek kaynak**) | `utils/stm32_kimlik.py` — `banner_ayristir` · `uyum_denetle` |
> | Saha betiği artık oradan import eder | `scripts/stm_firmware_kimligi.py` (kendi regex'i **kaldırıldı**) |
> | Banner okuma | `headless_core._stm_kimligini_isle`, `STM_READY` dalından çağrılır |
> | Durum alanları | `core.stm_uyumlu` · `core.stm_uyumsuzluk_sebebi` |
> | Sağlık ucu | `/api/health` → `stmUyumlu` · `stmUyumsuzlukSebebi` |
> | Seans reddi | `/api/session/start` → **409** + eylem söyleyen mesaj |
> | Kapı | `tests/test_stm_firmware_uyum_kapisi.py` — 13 test, **5 mutasyon kırmızı** |
>
> **Karar üç durumlu:** `true` uyumlu · `false` **kesin** uyumsuz (seans reddedilir) ·
> `null` banner tanınmadı → **seans engellenmez**, ama sağlık ucunda görünür. Gerekçe:
> banner biçimi ileride değişip *uyumlu* bir firmware de tanınmayabilir; çalışan bir kliniği
> durdurmak çözdüğümüz sorundan büyük zarar olurdu. Yalnızca **bildiğimizde** reddediyoruz.
>
> ⚠️ **Acil durdurma kapılanmadı** — kendi testi var: uyumsuz firmware'de
> `POST /api/hardware/emergency_stop` → **200**.
>
> ⚠️ Mutasyonda ilk yazımda **iki kapı ısırmadı** ve düzeltildi: (a) testler uyum durumunu
> doğrudan enjekte ettiği için `headless_core`daki **bağlantıyı** ölçmüyordu — çağrıyı silmek
> hepsini yeşil bırakıyordu; (b) paket genişliği çıpası `STM_PAKET_BOBIN_SAYISI` *dizesini*
> arıyordu, sabiti elle yazan mutasyon o dizeyi yine içeriyordu. İkisi de AST ile gerçek
> çağrıya/import'a pinlendi.

---

## 0 · Kısa cevap

> **Evet, yakabilir.** LattePanda'da STM32CubeIDE kurulu olduğu için gereken **iki araç da
> zaten orada**: yakıcı (`STM32_Programmer_CLI.exe`) ve derleyici (`arm-none-eabi-gcc`).
> ST-Link kablosu bağlı ve internet varsa teknik engel yok.

**Ama sıralama önemli:** önce **uyumsuzluk kapısı**, sonra uzaktan güncelleme. Sebebi §1'de —
şu anda yanlış firmware yüklendiğinde sistem bunu **fark etmiyor**, dolayısıyla uzaktan
güncelleme eklersek "yanlış sürümü sessizce yaydık" riskini otomatikleştirmiş oluruz.

---

## 1 · ASIL PROBLEM: uyumsuzluk SESSİZ (önce bu)

### Ölçülen arıza

`firmware/stm32_pemf/Core/Src/main.c:1006` her açılışta şunu basıyor:

```
-> STM_READY: DDS v2.3 (7-ch UNIPOLAR tek-bacak uni=0x60 + HW_SYNC@PB1) Waiting for commands...
                ^^^^^^  ^^^^                    ^^^^^^^^
                sürüm   kanal sayısı            kip + maske
```

Yani kart **kim olduğunu zaten söylüyor**. Backend ise `headless_core.py:396`de şunu yapıyor:

```python
if "STM_READY" in decoded or "STM_OK:" in decoded:
    self._set_stm_connected(True)          # ⚠️ İÇERİĞE HİÇ BAKMIYOR
```

Sonuç zinciri (`scripts/stm_firmware_kimligi.py`de zaten belgeli):

| | eski firmware (5 bobin) | yeni firmware (7 bobin) |
|---|---|---|
| Beklediği paket | **88 bayt** | **120 bayt** |

Backend 120 bayt gönderir → eski firmware ilk 88 baytı paket sanar → CRC alanını yanlış
ofsetten okur → `Coil_SendNack("CRC")` → `pkt_ok = 0` → **PWM durumuna hiç dokunulmaz.**
Ama `STM_READY` basıldığı için uygulama STM'i **BAĞLI** gösterir.

> **Belirti:** bağlantı göstergesi yeşil, hata penceresi yok, hiçbir bobin başlamıyor —
> bobin 1-5 dahil. Senin tarif ettiğin "client güncel / firmware eski" problemi tam olarak budur.
> Bugün bunu ayırt etmenin **tek** yolu UART'ı elle dinlemek.

### Çözüm — 3 parça

**1.1 · Banner'ı ayrıştır ve SAKLA**
`STM_READY` satırından `surum` (`DDS v2.3`), `kanal` (7), `kip` (UNIPOLAR/SYM-BIPOLAR/KARMA),
`maske` (0x60) çıkarılır. `scripts/stm_firmware_kimligi.py` bu regex'i **zaten** içeriyor —
kopyalanmaz, ortak yardımcıya taşınır (depo kuralı: tek kaynak).

**1.2 · UYUM KAPISI — bağlıyı "hazır" saymayı bırak**

Backend'in paketlediği kanal sayısı ile kartın söylediği kanal sayısı **eşleşmiyorsa**:

- `stmConnected` = true kalabilir (kart gerçekten konuşuyor),
- ama **yeni bir alan**: `stmUyumlu = false` + `stmUyumsuzlukSebebi` = insan dilinde.
- Seans başlatma bu durumda **reddedilir**, mesajı EYLEM söyler:
  > *"Kart 5 kanallı firmware koşuyor, uygulama 7 kanallı paket gönderiyor. Bobinler
  > başlamaz. `docs/SAHA-ISLERI-REHBERI.md` B-2 ile STM'i yeniden yakın."*

⚠️ **Güvenlik değişmezi:** bu kapı **acil durdurmayı ASLA engellemez.** Uyumsuz firmware'de
bile STOP yolu açık kalır (depo kuralı: bobinler her şeyden önce durur).

**1.3 · Kapı testleri (mutasyonla kırmızı ispatlı)**
- Eski banner (5-ch) + 7 kanal paketleyici → `stmUyumlu=false` ve seans **reddedilir**.
- Karşıt kanıt: 7-ch banner → uyumlu, seans normal başlar.
- Mutasyon: uyum kontrolünü kaldır → **KIRMIZI** olmalı.

> **Bu adım tek başına bile değerli.** Uzaktan güncelleme hiç yapılmasa bile, "bağlı görünüyor
> ama çalışmıyor" sınıfını kalıcı olarak öldürür.

---

## 2 · UZAKTAN GÜNCELLEME

### 2.1 · Gereksinimler — ölçülmüş durum

| Gereksinim | Durum | Not |
|---|---|---|
| ST-Link kablo bağlantısı | ✅ sende var | SWD üzerinden yakar |
| LattePanda internet | ✅ var | |
| **Yakıcı:** `STM32_Programmer_CLI.exe` | ✅ **CubeIDE ile geliyor** | bu makinede: `C:\ST\STM32CubeIDE_1.17.0\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_2.2.0.*\tools\bin\` |
| **Derleyici:** `arm-none-eabi-gcc` | ✅ **CubeIDE ile geliyor** | `...externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.1.0.*\tools\bin\` |
| ST-Link sürücüsü | ✅ | `stlink_server` kurulu görünüyor |
| İkili üretimi | ✅ `scripts/firmware_derle.py --stm --cikti` | `pemf.bin/.hex/.elf` + SHA256 |
| Dağıtım kanalı | ⚠️ **eksik parça** | §2.3 |

⚠️ Sürüm klasör adları CubeIDE sürümüne göre değişir → yol **glob ile aranmalı**, sabit
yazılmamalı. `firmware_derle.py` gcc'yi zaten böyle buluyor; yakıcı için de aynısı yapılır.

### 2.2 · Ne gönderilecek: kaynak değil, **İKİLİ**

`main.c` göndermek teknik olarak mümkün (LattePanda'da gcc var) ama **yapılmamalı**:

- Derleme ortamı sahada farklı olabilir → **aynı kaynak farklı ikili** üretir; "sahada ne
  koşuyor" sorusu yine cevapsız kalır.
- `firmware_derle.py`nin `_printf_float` kapısı gibi kontroller merkezde bir kez koşar.
  ⚠️ O bağ kopuksa **tüm telemetri sessizce ölür** (sıcaklık + alan + akım boş gelir, ACK
  tamsayı olduğu için cihaz sağlam görünür) — bunu sahada keşfetmek istemeyiz.
- Tek ikili + tek **SHA256** = "sahadaki cihazda depodaki kaynak mı koşuyor" sorusunun
  tek kanıtı.

**Karar:** merkezde derle, **`pemf.bin` + SHA256 + beklenen banner** gönder.

### 2.3 · Dağıtım kanalı — ⛔ burada bir karar gerekiyor

Depoda zaten GitHub Release tabanlı OTA altyapısı var (app/base katmanları). Firmware de
aynı kanaldan gidebilir: manifest'e `firmware.stm32` girdisi (url + sha256 + banner + sürüm).

⚠️ **AMA YAYIN DONMUŞ.** Sahada tek makine var ve senin "yayınla" demen bekleniyor. Yani:

| Seçenek | Ne zaman |
|---|---|
| **A · Manifest'e firmware katmanı ekle** | Yayın açıldığında. Temiz, kalıcı, sürüm takipli |
| **B · Elle dosya + yerel yakma komutu** | **Şimdi.** Kanal yok; `.bin`i sen kopyalıyorsun, yakma otomatik |

Önerim: **şimdi B ile başla** (§3 Faz 2), altyapıyı A'ya hazır yaz. B, A'nın küçük hâli —
atılacak iş olmaz.

### 2.4 · Yakma akışı ve ⚠️ GÜVENLİK KAPILARI

```
1. ÖN KONTROL (hepsi geçmezse İPTAL)
   ├─ Aktif seans var mı?        → VARSA REDDET (yakma MCU'yu resetler, bobinler aniden durur)
   ├─ Tüm bobinler durdu mu?     → DOĞRULA, sadece "komut gönderdim" YETMEZ
   ├─ İkili SHA256 beklenenle eşleşiyor mu?
   └─ Mevcut firmware yedeği alındı mı?  (geri dönüş için)
2. Backend seri portu BIRAKIR (COM10) — yakma sonrası MCU reset atar
3. YAK:
   STM32_Programmer_CLI.exe -c port=SWD -w pemf.bin 0x08000000 -v -rst
                                                              ^^  ^^^^
                                                        doğrula  reset
4. DOĞRULA — asıl kabul ölçütü bu:
   ├─ UART banner'ı oku (§1.1 ayrıştırıcısı)
   ├─ Kanal sayısı + kip + maske BEKLENENLE eşleşiyor mu?
   └─ Eşleşmiyorsa → OTOMATİK GERİ DÖN (yedek .bin'i yak)
5. KAYDET: SHA256 + zaman + banner → cihaz kaydına yaz
```

⚠️ **1. adım pazarlığa kapalı.** Yakma MCU'yu resetler; hasta üzerindeyken bobinlerin
aniden durması kabul edilemez. "Seans yok" kontrolü `/api/health` içindeki `sessionActive`
alanından okunur.

⚠️ **4. adım olmadan bu iş yapılmaz.** "Yaktım, exit 0 döndü" kanıt değildir — bu depoda
build betiği başarısızken bile exit 0 döndürdü. Tek kanıt kartın **kendi söylediği** banner'dır.

### 2.5 · Tuğlalaşma riski — düşük ve kurtarılabilir

| Risk | Karşılık |
|---|---|
| Yakma yarıda kesilir | ST-Link **kablolu** ve hep bağlı → tekrar yakılır. Bootloader'a dokunulmuyor, yalnız uygulama alanı (`0x08000000`) yazılıyor |
| Yanlış ikili | SHA256 + banner doğrulaması + otomatik geri dönüş |
| Elektrik kesintisi | Flash yazımı saniyeler sürer; kesilirse kart açılmaz ama ST-Link ile kurtarılır (fiziksel erişim gerekir) |
| Uzaktan erişim koparsa | Yakma **LattePanda'nın kendi üstünde** koşar; komut gittiyse tünel kopsa da tamamlanır |

⚠️ **Tek gerçek şart:** o an klinikte biri olmalı ya da cihaz hastasız olmalı. Uzaktan
güncelleme "kimse yokken" yapılacaksa cihazın hastasız olduğundan emin olunmalı.

---

## 3 · FAZLAR

| Faz | İş | Çıktı | Süre |
|---|---|---|---|
| **1** | **Uyum kapısı** (§1) — banner ayrıştır, `stmUyumlu` alanı, seans reddi, 3 test + mutasyon | Sessiz uyumsuzluk **biter** | ~yarım gün |
| **2** | **Yerel yakma aracı** — `scripts/stm_yak.py`: CLI'yi glob ile bul, ön kontroller, yak, banner doğrula, geri dön | Tek komutla güvenli reflash | ~yarım gün |
| **3** | **Uzaktan tetik** — kimlik doğrulamalı admin ucu (`POST /api/firmware/stm/guncelle`), aynı ön kontroller, ilerleme + sonuç | Uzaktan güncelleme **çalışır** | ~yarım gün |
| **4** | **Manifest entegrasyonu** (yayın açılınca) — `firmware.stm32` girdisi, otomatik indirme, sürüm karşılaştırma | Sürüm takipli dağıtım | yayına bağlı |

**Faz 1 tek başına sevk edilebilir** ve asıl acını dindiren o.

---

## 4 · Senden gerekenler

1. **Faz sırası onayı** — özellikle "önce uyum kapısı" kararı.
2. **Yakma iznine dair kural:** uzaktan güncelleme
   (a) yalnız sen tetikleyince mi koşsun, yoksa
   (b) yeni firmware yayınlanınca cihaz kendi mi alsın (hastasızken)?
   ⚠️ Önerim **(a)** — tıbbi cihazda sessiz otomatik firmware güncellemesi istemezsin.
3. **LattePanda'da doğrulama:** aşağıdaki iki yol **var mı** (sürüm numaraları farklı olabilir):
   ```powershell
   Get-ChildItem "C:\ST" -Recurse -Filter "STM32_Programmer_CLI.exe" | Select-Object -First 1 FullName
   Get-ChildItem "C:\ST" -Recurse -Filter "arm-none-eabi-gcc.exe"    | Select-Object -First 1 FullName
   ```
   Çıktıyı bana ilet — Faz 2'deki arama listesine LattePanda'nın gerçek yolunu eklerim.
