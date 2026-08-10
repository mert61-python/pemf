# ai/ — Tedavi-Parametre Önerisi + Global AI Yapılandırması

Bu klasör **teşhis-inference katmanı DEĞİLDİR** (o [`../ai_hub/`](../ai_hub/README.md) + [`../ai_service/`](../ai_service/README.md)).
Buradaki "AI" **kural/bilgi-tabanlıdır**: PEMF tedavi parametrelerini (freq/duty/süre) önerir ve sistem-geneli AI/ECG/HRV ayarlarını tutar.

## Dosyalar
| Dosya | Görev |
|---|---|
| `__init__.py` | Paket init (v1.0.0); `config`'i yeniden dışa verir |
| `config.py` | Merkezî config: veri setleri, sinyal-işleme/HRV/PEMF-sensör parametreleri, model mimarileri, eğitim hiperparametreleri, `get_device()` (torch/CUDA algılama), runtime dizinleri `%APPDATA%\PEMF_GUI\ai`'ye yönlendirilmiş |
| `hybrid_recommender.py` | Kural-tabanlı + adaptif PEMF parametre önericisi (18+ klinik protokol, tür/yaş/kilo uyarlaması, interpolasyon, seans-geçmişinden öğrenme); Türkçe metin normalizasyonu + tür-alias haritası. **Sinir ağı yok** |

## ⚠️ Dikkat
- `config.py` içindeki **`SPECIES_PARAMS`** bloğu (50 Hz-altı frekanslar) kodda **güvenlik-tuzağı** olarak işaretlidir: **yalnız eğitim içindir, üretimde KULLANILMAZ**. Üretim parametreleri firmware güvenlik-sınırlarına tabidir.

---
İlgili: [proje geneli](../README.md) · [ai_hub/ (teşhis modelleri)](../ai_hub/README.md) · [ai_service/ (GPU inference)](../ai_service/README.md)
