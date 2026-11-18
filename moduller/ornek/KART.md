# KART bilgi formu — örnek modül (sahte kart)

Bu formu her geliştirici kendi kartı için doldurur. Aynı bilgiler `modul.json` dosyasının `kart` alanında da bulunur.
Kabul testi, formdaki değerleri kartın gerçek davranışıyla karşılaştırır.

| alan | değer |
|---|---|
| Geliştirici | PEMF çekirdek ekibi (şablon) |
| Mikroişlemci | yok — `sahte_kart.py` (bilgisayarda ayrı süreç olarak çalışır) |
| Sürme kartı | yok |
| Bağlantı | yerel adlandırılmış boru (Windows `\.\pipe\<ad>`); ağ portu dinlemez |
| Kartı bulma | boru adı (`modul.json` → `baglanti_ayrinti.boru`); gerçek kartta USB VID / PID ya da seri numarası kullanılır, ana STM kartının portu **açılmaz** |
| Bobin | yok (benzetim) |
| Güç / akım sınırı | 0 A (benzetim) |
| Parametre sınırları | frekans 1–500 Hz · duty %0–50 · süre 0–60 dk; kart da aynı sınırları uygular |
| Bekçi (kalp atışı) | 1500 ms; sunucu 500 ms'de bir kalp atışı gönderir, kalp atışı gelmezse kart bobini **kendisi** keser |
| Açılış durumu | bobin **kapalı** |
| ACİL DURDUR | ayrı bağlantıdan gelir, kart bobini hemen keser (ölçülen: dönüş < 1 ms, kesme < 2 ms) |
| Bağlantı koparsa | bobin kesilir |
