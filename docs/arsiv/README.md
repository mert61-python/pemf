# docs/arsiv/ — Bitmiş İş Kayıtları

Bu dizin **tarihçedir**. Buradaki belgeler o günün durumunu anlatır; bugünün
kaynağı değildir. Güncel belgeler bir üst dizindedir (`docs/`).

## İçerik

| Ne | Neden burada |
|---|---|
| `responsive-denetim-2026-09-04.*` · `responsive-duzeltme-plani-2026-09-04.*` | Responsive denetimi + düzeltme planı **bitti ve yayınlandı**. Dört dosya birbirine link veriyor, o yüzden BİRLİKTE taşındı |
| `ekran-goruntuleri-2026-07-29/` | Headless geçişinden **önceki** PyQt/eski arayüzün ekran görüntüleri (13 dosya). Hiçbir belge atıf vermiyor (ölçüldü 2026-09-19) |
| `pemf_optimized_table.html` · `working_time.txt` | Sıfır atıf, sahipsiz kalıntı |

## ⚠️ Buraya taşınmayan bitmiş işler ve NEDENİ

Ölçüm, bazı "bitmiş" görünen belgelerin aslında **canlı bir kümenin parçası**
olduğunu gösterdi — onlar `docs/` içinde KALDI:

- `denetim-bulgular-2.md` → `denetim-bulgular-3.md` (kapıya pinli, kalıyor) sekiz
  yerden anıyor; küme bölünmez. CHANGELOG da anıyor ve CHANGELOG düzenlenmez.
- `stm32-7-bobin-gecisi-plani-2026-09-10.md` → **canlı** `stm32-pin-haritasi.md`
  "Geçiş planı" satırından anıyor.
- `denetim-guncelleme-altyapisi-2026-08-23.md` → `denetim-bulgular-3.md` anıyor.
- `sahip-istekleri-2026-09-12.md` → `acik-isler-2026-09-12.md` anıyor.
- `DEPO-DENETIMI-2026-09-15.md` → **iki kapı** dosya adıyla pinliyor
  (`test_denetim_kalan_maddeler_OLCULDU`, `test_linux_runtime_YOKLUGU_karardir`).

Yani ölçüt "tarihli isim" değil, **kim atıf veriyor**. Bir sonraki temizlikte de
önce bu ölçülmeli.
