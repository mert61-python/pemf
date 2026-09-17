# Üçüncü taraf araştırma veri kümeleri — kaynak ve atıf

> ⚠️ **DİZİN ADI YANILTICI.** `real_clinical_data` burada *"sentetik olmayan sinyal"*
> anlamına gelir — **bu kliniğin hasta verisi DEĞİLDİR.** Adı tarihsel; dosyalar
> taşınamadığı için (eğitim betikleri yola göre yazılmış) ad korundu, açıklaması buraya
> yazıldı.

## İçerik ne, PII var mı?

Ölçüldü (2026-09-17):

| Dosya | Ne | Kimlik bilgisi |
|---|---|---|
| `mitbih/*.hea` `*.dat` `*.atr` | MIT-BIH Arrhythmia Database kayıtları (5 kayıt) | **Yok** — kaynağında kimliksizleştirilmiş |
| `ecg_signals.npy` | Yukarıdaki kayıtlardan çıkarılmış ham EKG pencereleri | **Yok** |
| `hrv_features.csv` | Türetilmiş HRV metrikleri (`SDNN`, `RMSSD`, `pNN50`, `LF/HF`, `SD1/SD2`, entropi, DFA) | **Yok** |
| `predictor_features.csv` | HRV + manyetik alan + sıcaklık öznitelikleri | **Yok** |
| `predictor_targets.csv` · `monitor_labels.csv` · `monitor_sequences.npy` | Etiketler ve dizi pencereleri | **Yok** |

**Hasta adı, kimlik numarası, tarih ya da klinik kaydı içeren hiçbir sütun yoktur.**
CSV başlıkları yalnızca türetilmiş sayısal metriklerden oluşur.

## Kaynak ve atıf yükümlülüğü

Veriler `training_archive/ai_data/downloader.py` ile **PhysioNet** ve ilgili açık
depolardan alınmıştır:

- **MIT-BIH Arrhythmia Database** — PhysioNet. İnsan EKG'si; bu projede transfer öğrenme
  için kullanıldı.
- **PhysioZoo** (köpek / tavşan / fare EKG) — PhysioNet.
- **Zenodo "Paws in Pain"** (köpek ağrı değerlendirmesi, EKG'li).

⚠️ **PhysioNet veri kümeleri atıf/alıntı yükümlülüğü taşır.** Bu depo kayıtları yeniden
dağıttığı için atıf zorunludur; özet [`THIRD_PARTY_LICENSES.md`](../../../THIRD_PARTY_LICENSES.md)
dosyasındadır.

⚠️ **Ticari dağıtımdan önce doğrulanmalı:** her veri kümesinin kendi lisans sayfasındaki
güncel koşullar (ticari kullanım izni, yeniden dağıtım, atıf biçimi) hukukçuya
doğrulatılmadan ürünle birlikte sevk edilmemelidir. Bu dosya bir **kayıt**tır, hukuki
görüş değildir.

## Bu veriler üründe sevk ediliyor mu?

**Hayır.** `training_archive/` donmuş bir eğitim arşividir; frozen EXE'ye ve dağıtım
paketlerine girmez. Yalnızca modellerin nasıl eğitildiğinin izini tutar.

---

Kapı: [`tests/test_veri_kumesi_atfi.py`](../../../tests/test_veri_kumesi_atfi.py)
