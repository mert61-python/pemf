# docs/ — Doküman İndeksi

PEMF Vet projesinin teknik dokümanları. (Kod alt-sistemleri için ilgili klasörün kendi `README.md`'sine bak — indeks: [`../README.md`](../README.md).)

## Belgeler
| Dosya | İçerik | Kime |
|---|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Bileşen diyagramı, veri akışı, **güven sınırları**, kritik güvenlik mekanizmaları, tek giriş noktası | Sistemi devralan geliştirici |
| [`LAUNCHER_SPEC.md`](LAUNCHER_SPEC.md) | Launcher (PEMF Vet Client) sözleşmesi — Windows/macOS/Linux, tek kaynak, geriye-uyum | Launcher üzerinde çalışan |
| [`RUNBOOK.md`](RUNBOOK.md) | Saha **operasyon / olay-müdahale** rehberi (klinik PC, `PemfBackend` NSSM servisi, hızlı komutlar) | Saha/destek |
| [`VERIFICATION.md`](VERIFICATION.md) | Üretim **doğrulama checklist'i** (çalıştırılabilir adımlar; cihaz/panel gerektirenler işaretli) | Sürüm-öncesi doğrulama |
| [`TEMIZ-MAKINE.md`](TEMIZ-MAKINE.md) | **Temiz makinede sıfırdan** — kur-kullan (Yol A) ve build/yayın (Yol B, sır geri-yükleme) akışlarını ayrık anlatır | Yeni makine / build |
| [`JETON-SISTEMI.md`](JETON-SISTEMI.md) | **Jeton (token) ücretlendirme** sistemi — sahip kararı; ⚠️ `PEMF_TIER_ENFORCED` varsayılan **KAPALI** (bugün üretimde koşmuyor) | Ürün/ücretlendirme |
| [`AGPL-KARARI.md`](AGPL-KARARI.md) | Ultralytics **AGPL-3.0** durum tespiti + karar notu (**AÇIK**; `tests/test_license_surface.py` yüzey kapısı) | Sahip/hukuk |
| [`DONANIM-UYUM-ANALIZI-2026-08-19.md`](DONANIM-UYUM-ANALIZI-2026-08-19.md) | Donanım↔backend **protokol uyum** denetim raporu (14 iddia → 12 gerçek uyumsuzluk) | Donanım/protokol |
| [`SAHA-TEST-LISTESI.md`](SAHA-TEST-LISTESI.md) | Elle koşulan **saha test** senaryoları — otomatik süitlerin göremediği gerçek donanım/OS/kullanıcı sınıfı | Saha/QA |
| [`acik-isler-2026-09-12.md`](acik-isler-2026-09-12.md) | **Açık işler** — docs/ tam taraması: sahip kararı / tezgâh / mühendislik / hiç bakılmayan katmanlar + ölçülen belge bayatlıkları | Sahip |
| [`ARIZA-LISTESI.md`](ARIZA-LISTESI.md) | **Gerçek arıza listesi** — `DEPO-DENETIMI-2026-09-15.md`ten türeyen çalışma takipçisi (A = bugün zarar verir · B = olgunluk · C = hijyen) | Mühendislik |
| [`SAHA-ISLERI-REHBERI.md`](SAHA-ISLERI-REHBERI.md) | **Saha işleri indeksi** — sende kalan 8 iş; derin adımlar kendi belgelerinde durur (ikinci kaynak değildir) | Sahip/saha |
| [`VAULT-ANAHTAR-EMANETI.md`](VAULT-ANAHTAR-EMANETI.md) | **Hasta anahtarı emaneti** — Vault kurulumu, kurtarma token'ı, disk kaybı sonrası adım adım kurtarma | Sahip |
| `version_info.txt` | Windows EXE sürüm kaynağı (`sync_versions.ps1` yazar) | Build |
| `screenshots/` | Arayüz ekran görüntüleri (kök README + TÜBİTAK raporu kullanır) | — |
| `saha-test-listesi.html` | `SAHA-TEST-LISTESI.md`'nin tarayıcıda koşulan/yazdırılabilir sürümü (ürün tasarım dizgesiyle) | Saha/QA |
| [`arsiv/`](arsiv/README.md) | ⚠️ **TARİHÇE** — bitmiş iş kayıtları; **bugünün kaynağı DEĞİLDİR**. Ölçüt "tarihli isim" değil, **kim atıf veriyor** | — |

## Donanım / STM32 sözleşmeleri
| Dosya | İçerik | Kime |
|---|---|---|
| [`stm32-pin-haritasi.md`](stm32-pin-haritasi.md) | **TAM pin haritası** (Nucleo-144 F429ZIT6) — ⚠️ `stm32_pemf_unipolar` ayna projesi 2026-09-11'de KALDIRILDI | Donanım |
| [`stm32-sensor-protokolu.md`](stm32-sensor-protokolu.md) | STM32 **sensör telemetri sözleşmesi** | Donanım/protokol |
| [`stm32-uzaktan-guncelleme-plani.md`](stm32-uzaktan-guncelleme-plani.md) | Uzaktan firmware güncelleme + firmware↔client uyumsuzluğu — §1 (09-18), Faz 2 ve Faz 3 (09-22) **uygulandı** (Faz 3 = açılış denetimi; otomatik yakma `PEMF_FW_AUTO_UPDATE` varsayılanı `"0"` — KAPALI, Y1) · Faz 4 yayına bağlı | Donanım/yayın |
| [`stm32-7-bobin-gecisi-plani-2026-09-10.md`](stm32-7-bobin-gecisi-plani-2026-09-10.md) | ESP'leri devre dışı bırak → **7 bobinin tamamını STM32'den sür** | Donanım |

## Planlar (durum belgelerin kendi başındadır)
| Dosya | İçerik | Kime |
|---|---|---|
| [`KLASOR-YAPISI-PLANI.md`](KLASOR-YAPISI-PLANI.md) | Monorepo klasör düzeni — **kısmen uygulandı** (F1 + F4 + bootstrap taşıması) | Mimari |
| [`arastirma-ai-pro-fantom-petri-plani.md`](arastirma-ai-pro-fantom-petri-plani.md) | Araştırma modu AI Pro — fantom + petri entegrasyonu; ✅ tüm fazlar (app 1.9.44). ⚠️ Kasım 2026'dan beri sürüş faz / duty'si **ODAK**'tan (`ai_hub/odak/` — bkz. [`../ai_hub/README.md`](../ai_hub/README.md)); bu plandaki em_* sürüş yolu artık sürüş kaynağı değil | AI |
| [`xai-entegrasyon-plani.md`](xai-entegrasyon-plani.md) | XAI (açıklanabilirlik) entegrasyonu — Faz 1 ✅ + Faz 2 çekirdeği ✅ | AI |
| [`scratch-entegrasyon-plani.md`](scratch-entegrasyon-plani.md) | Scratch / wound-healing entegrasyonu — ✅ Faz 1-4.5 (2026-08-27) | AI |
| [`ai-hub-gorsel-sahne-plani-2026-09-10.md`](ai-hub-gorsel-sahne-plani-2026-09-10.md) | AI Hub görsel sahnesi — ✅ **tamamlandı** (2026-09-12), 13 AI modülü | Ön-yüz/AI |

## Denetim raporları — ⚠️ TARİHLİ KAYIT
> Bunlar **o günün** ölçümüdür, bugünün durumu değil. `arsiv/`e taşınmadılar çünkü
> kapılar ve kardeş belgeler onları **dosya adıyla pinliyor** (bkz. [`arsiv/README.md`](arsiv/README.md)).
> Güncel açık işler: [`acik-isler-2026-09-12.md`](acik-isler-2026-09-12.md) ·
> [`ARIZA-LISTESI.md`](ARIZA-LISTESI.md).

| Dosya | İçerik | Kime |
|---|---|---|
| [`DEPO-DENETIMI-2026-09-15.md`](DEPO-DENETIMI-2026-09-15.md) | Depo denetimi — disk + kod organizasyonu + yapılandırma/sır hijyeni. ⚠️ Başındaki **DURUM** bloğu neyin sonradan kapandığını sayar | Sahip/mühendislik |
| [`denetim-bulgular.md`](denetim-bulgular.md) · [`denetim-bulgular-2.md`](denetim-bulgular-2.md) · [`denetim-bulgular-3.md`](denetim-bulgular-3.md) | Hata denetimi 1./2./3. tur (2026-08-17 · 08-19/20 · 08-24) — yalnız **kırık davranış** | Mühendislik |
| [`denetim-guncelleme-altyapisi-2026-08-23.md`](denetim-guncelleme-altyapisi-2026-08-23.md) | Güncelleme altyapısı denetimi — client + mobil | Mühendislik |
| [`sahip-istekleri-2026-09-12.md`](sahip-istekleri-2026-09-12.md) | Sahip istekleri — kod + kapı testleri + mutasyon kanıtı tamam; ⚠️ **yayın YAPILMADI** | Sahip |
| [`react_installer_gap_report.md`](react_installer_gap_report.md) | ⚠️ **TARİHÇE** (2026-06-04) — ana bulgu KAPANDI | — |
| [`PEMF_SISTEM_RAPORU.md`](PEMF_SISTEM_RAPORU.md) | ⚠️ **TARİHÇE** — kapsamlı tam sistem raporu (tarihi belgenin kendisinde); o günün topolojisini anlatır (ESP32-S3 ×8 bobin, PyQt6 GUI). Başındaki bant bugünü söyler; güncel mimari [`ARCHITECTURE.md`](ARCHITECTURE.md) | Yönetici/genel |

## Nereden başlamalı
1. **Kod tabanını tanı:** [`../README.md`](../README.md) dizin haritası → alt-klasör README'leri.
2. **Nasıl çalışıyor:** [`ARCHITECTURE.md`](ARCHITECTURE.md).
3. **Nasıl derlenir/yayınlanır:** [`../BUILD.md`](../BUILD.md).
4. **Sahada nasıl işletilir:** [`RUNBOOK.md`](RUNBOOK.md).

---
İlgili: [proje geneli](../README.md) · [build rehberi](../BUILD.md)
