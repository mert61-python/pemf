# docs/ — Doküman İndeksi

PEMF Vet projesinin teknik dokümanları. (Kod alt-sistemleri için ilgili klasörün kendi `README.md`'sine bak — indeks: [`../README.md`](../README.md).)

## Belgeler
| Dosya | İçerik | Kime |
|---|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Bileşen diyagramı, veri akışı, **güven sınırları**, kritik güvenlik mekanizmaları, tek giriş noktası | Sistemi devralan geliştirici |
| [`LAUNCHER_SPEC.md`](LAUNCHER_SPEC.md) | Launcher (PEMF Vet Client) sözleşmesi — Windows/macOS/Linux, tek kaynak, geriye-uyum | Launcher üzerinde çalışan |
| [`RUNBOOK.md`](RUNBOOK.md) | Saha **operasyon / olay-müdahale** rehberi (klinik PC, `PemfBackend` NSSM servisi, hızlı komutlar) | Saha/destek |
| [`VERIFICATION.md`](VERIFICATION.md) | Üretim **doğrulama checklist'i** (çalıştırılabilir adımlar; cihaz/panel gerektirenler işaretli) | Sürüm-öncesi doğrulama |
| [`PEMF_SISTEM_RAPORU.md`](PEMF_SISTEM_RAPORU.md) | Kapsamlı **tam sistem raporu** (2026-03) — üst-düzey genel bakış | Yönetici/genel |
| [`TEMIZ-MAKINE.md`](TEMIZ-MAKINE.md) | **Temiz makinede sıfırdan** — kur-kullan (Yol A) ve build/yayın (Yol B, sır geri-yükleme) akışlarını ayrık anlatır | Yeni makine / build |
| [`JETON-SISTEMI.md`](JETON-SISTEMI.md) | **Jeton (token) ücretlendirme** sistemi — sahip kararı; ⚠️ `PEMF_TIER_ENFORCED` varsayılan **KAPALI** (bugün üretimde koşmuyor) | Ürün/ücretlendirme |
| [`AGPL-KARARI.md`](AGPL-KARARI.md) | Ultralytics **AGPL-3.0** durum tespiti + karar notu (**AÇIK**; `tests/test_license_surface.py` yüzey kapısı) | Sahip/hukuk |
| [`DONANIM-UYUM-ANALIZI-2026-08-19.md`](DONANIM-UYUM-ANALIZI-2026-08-19.md) | Donanım↔backend **protokol uyum** denetim raporu (14 iddia → 12 gerçek uyumsuzluk) | Donanım/protokol |
| [`SAHA-TEST-LISTESI.md`](SAHA-TEST-LISTESI.md) | Elle koşulan **saha test** senaryoları — otomatik süitlerin göremediği gerçek donanım/OS/kullanıcı sınıfı | Saha/QA |
| `version_info.txt` | Windows EXE sürüm kaynağı (`sync_versions.ps1` yazar) | Build |
| `screenshots/` | Arayüz ekran görüntüleri (kök README + TÜBİTAK raporu kullanır) | — |

## Nereden başlamalı
1. **Kod tabanını tanı:** [`../README.md`](../README.md) dizin haritası → alt-klasör README'leri.
2. **Nasıl çalışıyor:** [`ARCHITECTURE.md`](ARCHITECTURE.md).
3. **Nasıl derlenir/yayınlanır:** [`../BUILD.md`](../BUILD.md).
4. **Sahada nasıl işletilir:** [`RUNBOOK.md`](RUNBOOK.md).

---
İlgili: [proje geneli](../README.md) · [build rehberi](../BUILD.md)
