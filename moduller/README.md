# Geliştirici modülleri

Bu klasördeki her alt klasör bir **kontrol modülüdür** (istem 53, sahip kararları Y298 / Y299). Modüller satılan üründe
**varsayılan olarak gizlidir**; Ayarlar → "Geliştirici modülleri" açılınca Kontrol sekmesindeki seçicide görünürler.
Aynı anda yalnızca **bir** modül sürülebilir.

Her modül klasöründe şunlar bulunur:

| dosya | içerik |
|---|---|
| `modul.json` | kimlik (klasör adıyla aynı), görünen ad (TR + EN), sürüm, bağlantı türü, parametre sınırları, kart bekçisi süresi (`bekci_ms` ≥ 1500), kart bilgisi |
| `KART.md` | kart bilgi formu (mikroişlemci, sürme kartı, bağlantı, bobin, akım sınırı, bekçi) |
| `surucu.py` | `class Surucu(BobinSurucusu)` (`apps/backend/servers/modul_surucu.py`); sunucudan **ayrı bir süreçte** çalışır |

Panel kodu `apps/ui/src/moduller/<kimlik>/` altında bulunur.

Kurallar (PLAN §2 A + B) kabul testleriyle ve sürücü denetleyicisiyle (`servers/modul_denetleyici.py`) ölçülür. Örnek ölçüm için
`tests/test_GA_B4_ornek_modul_KABUL.py` ve `tests/test_GA_B5_surucu_denetleyici.py` dosyalarına bakın. Kuralları geçmeyen modül
birleştirilmez.

`ornek/` klasörü sahte kartla (`sahte_kart.py`, ayrı süreçte çalışır, ağ portu dinlemez) uçtan uca çalışan örnek modüldür.
Kartsız geliştirme bu modülle yapılır.
