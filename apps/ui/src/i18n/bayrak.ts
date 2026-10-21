/**
 * İNGİLİZCE BAYRAĞI (Y158) — göç bitip `14-I18N-INCELEME` onaylayana dek KAPALI.
 *
 * Kapalıyken: Ayarlar'daki dil seçeneği GİZLİ ve cihaz dili İngilizce olsa bile etkin dil `tr` (yarım çeviri kullanıcıya çıkmaz).
 * TEK KAYNAK depo kökündeki `i18n/bayrak.json`; bu sabit oradan `scripts/i18n/bayrak.py --ac|--kapat` ile yazılır ve K-5 kapısı
 * (`tests/test_i18n_kritik_K5.py`) bütün yüzeylerin aynı değeri taşıdığını denetler. ⚠️ ELLE DEĞİŞTİRME — yalnız inceleme oturumu açar.
 * Testler bayrağı `__bayrakTestiAyarla(true)` (`./dil`) ile açar, `afterEach`'te `null` ile geri alır; ürün kodu onu ÇAĞIRMAZ (K-5).
 */
export const I18N_EN_ACIK: boolean = true;
