/**
 * I18N-P1 · site-12c-icerik — `src/config.ts` metin alanları (yasal belge başlıkları, tıbbi uyarı, indirme notları, profiller, planlar,
 * eklentiler, kurulum adımları, özellikler, sürüm notları, plan karşılaştırması, SSS). Alanlar GETTER'dır: her okumada etkin dilde
 * katalogdan gelir (tüketici kodu aynı alan adlarını okur). Sabit KİMLİK verisi (COMPANY unvan / adres / vergi dairesi, dosya adları,
 * işletim sistemi gereksinimleri) çevrilmez.
 *  · ALTIN: göç ÖNCESİ config.ts'in DEĞERLENMİŞ metin alanları (HEAD) — Türkçe (bayrak kapalı) bunlarla BAYT BAYT aynı.
 *  · İngilizce (bayrak AÇIK): her metin yaprağı Türkçe harfsiz, Türkçeden farklı (marka adları hariç), SAYILAR aynı (fiyat / jeton / gün /
 *    cihaz), güvenlik ifadeleri (acil durdurma → emergency stop) korunmuş, plan karşılaştırma "yok" vurgusu iki dilde aynı hücrelerde.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EN, TR } from '../../__tests__/_kaynakMetni'

;(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true
const depo = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => (depo.has(k) ? depo.get(k)! : null),
  setItem: (k: string, v: string) => void depo.set(k, String(v)),
  removeItem: (k: string) => void depo.delete(k),
})
vi.stubGlobal('document', { documentElement: { lang: '' }, title: '', querySelector: () => null })

const i18nMod = await import('../index')
const dilMod = await import('../dil')
const C = await import('../../config')

/** Altın tablo: göç ÖNCESİ değerlenmiş config metin alanları. */
const ALTIN: Record<string, unknown> = {
 "LEGAL_DOCS": [
  {
   "slug": "mesafeli-satis",
   "title": "Mesafeli Satış Sözleşmesi"
  },
  {
   "slug": "on-bilgilendirme",
   "title": "Ön Bilgilendirme Formu"
  },
  {
   "slug": "iptal-iade",
   "title": "İptal, İade ve Cayma Hakkı"
  },
  {
   "slug": "kvkk",
   "title": "KVKK Aydınlatma Metni"
  },
  {
   "slug": "gizlilik",
   "title": "Gizlilik Politikası"
  },
  {
   "slug": "cerez-politikasi",
   "title": "Çerez Politikası"
  },
  {
   "slug": "kullanim-sartlari",
   "title": "Kullanım Şartları"
  }
 ],
 "COMPANY_updated": "10 Ekim 2026",
 "MEDICAL_DISCLAIMER": "PEMF Vet, veteriner hekim gözetiminde kullanılmak üzere tasarlanmış klinik destek yazılımıdır. Akıllı teşhis ve AI analiz çıktıları bilgilendirme amaçlıdır; veteriner hekimin tıbbi teşhis, karar ve tedavisinin yerine geçmez. Otonom seans (AI Pro) özellikleri veteriner hekim sorumluluğunda kullanılır.",
 "DOWNLOAD_HOST": {
  "androidRolNotu": "Kliniğinizdeki cihaza bağlanır: seans başlatıp durdurabilir, bobin ayarlarını değiştirebilir, sensörleri izleyebilir ve hasta kayıtlarına bakabilirsiniz. Cihazın bağlı olduğu klinik bilgisayarı açık olmalıdır.",
  "androidVersionNote": "Telefon uygulamasının sürüm numarası bilgisayar uygulamasından ayrıdır; ikisi bağımsız güncellenir."
 },
 "CLIENT": {
  "channel": "Sürüm 2026.1",
  "releaseDate": "7 Kas 2026",
  "androidOs": "Android 8.0 ve üzeri · telefona doğrudan kurulur"
 },
 "MODULES": [
  {
   "id": "home",
   "name": "Evcil Hayvan Sahibi",
   "tagline": "Hekiminizin belirlediği protokolü evde uygulayın; kamera destekli ön-değerlendirme.",
   "includes": [
    "Kedide yüz ifadesinden ağrı skoru (FGS)",
    "Görüntüde bölge ayırma",
    "Kedide organ konumu (üç boyutlu)",
    "Kedi sesi analizi",
    "Hastalık ön-değerlendirme (bilgilendirme amaçlı — teşhis değildir)"
   ]
  },
  {
   "id": "vet",
   "name": "Veteriner Hekim",
   "tagline": "Tam klinik kontrol: frekansı elle ayarlama, canlı sensör, hasta kayıtları.",
   "includes": [
    "Frekans ve bobinleri elle ayarlama",
    "Canlı sensör ekranı (alan şiddeti mT · sıcaklık °C)",
    "Şifreli hasta kayıtları + klinik istatistikleri",
    "AI Pro: ölçümlere göre kendini ayarlayan otomatik seans",
    "Tüm klinik AI modelleri"
   ]
  },
  {
   "id": "research",
   "name": "Araştırma Profili",
   "tagline": "Kanser-araştırma modelleri — test aşamasında ücretsiz.",
   "includes": [
    "Fantom tümör + elektromanyetik alan ölçümü",
    "Petri kuyucuğu (kanser hücre analizi)",
    "Böbrek RNA analizi (KIRC — berrak hücreli böbrek kanseri)",
    "Böbrek bilgisayarlı tomografi (BT)",
    "Böbrek patoloji (histopatoloji)",
    "Kronik böbrek hastalığı (CKD) tahmini"
   ]
  }
 ],
 "PLANS": [
  {
   "tier": "baslangic",
   "name": "Başlangıç",
   "priceLabel": "Ücretsiz",
   "period": "14 gün deneme",
   "desc": "Evcil Hayvan Sahibi profiliyle sistemi ücretsiz deneyin.",
   "jetonHakki": "Ayda 50 jeton (≈50 yapay zekâ analizi)",
   "features": [
    "Evcil Hayvan Sahibi profili · 1 cihaz",
    "Yapay zekâ teşhis — jeton hakkınız kadar",
    "Şifreli hasta kaydı",
    "14 gün tam erişim"
   ],
   "cta": "Denemeyi Başlat",
   "badge": null
  },
  {
   "tier": "kullandikca",
   "name": "Kullandıkça Öde",
   "priceLabel": "₺2,90 / jeton",
   "period": "aylık ücret yok",
   "desc": "Önden ödeme yok: yalnız yaptığınız analizler kadar ödersiniz.",
   "jetonHakki": "Aylık jeton hakkı yok — harcadığınız kadar faturalanır",
   "features": [
    "Aylık ücret ve önden jeton alımı YOK",
    "Kullanmadığınız ay ücret çıkmaz",
    "Veteriner profili · 2 cihaza kadar",
    "Harcanan jetonlar dönem sonunda faturalanır",
    "E-posta ve uzak destek — 1 iş günü içinde yanıt"
   ],
   "cta": "Kullandıkça Öde ile Başla",
   "badge": null
  },
  {
   "tier": "pro",
   "name": "Pro",
   "priceLabel": null,
   "period": "klinik / ay",
   "desc": "Aktif klinikler için tam sürüm — ayda 500 jeton.",
   "jetonHakki": "Ayda 500 jeton (≈500 yapay zekâ analizi)",
   "features": [
    "Veteriner profili · 5 cihaza kadar",
    "Yapay Zekâ Merkezi + AI Pro (sensöre göre otomatik seans)",
    "Biten jetonu ek paketle tamamlarsınız",
    "Şifreli hasta kayıtları + klinik istatistikleri",
    "E-posta ve uzak destek — 1 iş günü içinde yanıt"
   ],
   "cta": "Pro’yu Seç",
   "badge": null
  },
  {
   "tier": "pro_plus",
   "name": "Pro+",
   "priceLabel": null,
   "period": "klinik / ay",
   "desc": "Yoğun klinikler için — ayda 2.000 jeton ve 15 cihaz.",
   "jetonHakki": "Ayda 2.000 jeton (≈2.000 yapay zekâ analizi)",
   "features": [
    "Pro’daki her şey",
    "AI Pro otomatik seans (seans başına 5 jeton)",
    "15 cihaza kadar aynı anda bağlantı",
    "Araştırma profili eklenebilir (+₺390/ay)",
    "Öncelikli destek — aynı iş günü içinde yanıt"
   ],
   "cta": "Pro+’ya Yükselt",
   "badge": null
  }
 ],
 "RESEARCH_ADDON_label": "Araştırma profili",
 "ADDONS": [
  {
   "name": "Ek Jeton Paketi",
   "desc": "Jetonunuz bittiğinde tamamlayın — satın alınan jetonların süresi dolmaz.",
   "price": "₺249’dan başlayan"
  },
  {
   "name": "Ek Cihaz Hakkı",
   "desc": "Aynı anda bağlanabilecek cihaz sayısını bir artırır.",
   "price": "₺149 / ay"
  },
  {
   "name": "Uzaktan Erişim",
   "desc": "Klinik dışındayken cihazı şifreli bağlantıyla izleyip yönetin.",
   "price": "₺249 / ay"
  }
 ],
 "LAUNCHER_STEPS": [
  {
   "step": "01",
   "title": "PEMF Vet’i indirin",
   "desc": "Sitemizden küçük kurulum dosyasını (yaklaşık 3 MB) indirip birkaç tıkla kurun. Masaüstünüze PEMF Vet kısayolu eklenir."
  },
  {
   "step": "02",
   "title": "Başlatıcı gerisini halleder",
   "desc": "Kurduğunuz başlatıcı, asıl PEMF Vet uygulamasını — yapay zekâ modelleri ve cihaz yazılımı dahil — sizin için indirip kurar. Beklemeniz yeterli."
  },
  {
   "step": "03",
   "title": "“Başlat”a basın",
   "desc": "İndirme bitince “Başlat” düğmesi çıkar; tek tıkla uygulama açılır. Yeni sürümler de kendiliğinden gelir — elle kurulum yapmanız gerekmez."
  }
 ],
 "FEATURES": [
  {
   "n": "01",
   "title": "Otomatik Cihaz Bağlantısı",
   "desc": "Cihazı aynı Wi-Fi ağında otomatik bulur; frekans ve şiddet değişiklikleri anında uygulanır, sensör verisi canlı akar."
  },
  {
   "n": "02",
   "title": "Hasta Veritabanı",
   "desc": "Her hasta için özelleştirilmiş protokoller oluşturun; seans geçmişini şifreli olarak detaylı grafiklerle takip edin."
  },
  {
   "n": "03",
   "title": "Otomatik Güncellemeler",
   "desc": "Cihaz yazılımınız ve yapay zekâ modelleriniz tek tıkla güncellenir; her zaman en yeni sürümle çalışırsınız."
  },
  {
   "n": "04",
   "title": "Yapay Zekâ Merkezi",
   "desc": "Kamerayla desteklenen teşhis: yüz ifadesinden ağrı skoru, organların üç boyutlu konumu ve AI Pro — sensörden gelen ölçümlere göre seansı kendi kendine ayarlayan otomatik mod."
  },
  {
   "n": "05",
   "title": "Klinik Güvenlik",
   "desc": "Acil durdurma düğmesi ve otomatik süre sınırı: seans her an durdurulabilir ve ayarlanan süre dolunca sona erer."
  },
  {
   "n": "06",
   "title": "Çoklu Platform",
   "desc": "Windows bilgisayarlarda ve Android telefonlarda tek uygulama (macOS ve Linux hazırlanıyor); klinik verileri cihazda şifreli tutulur, klinik dışından erişim şifreli bağlantıyla yapılır."
  }
 ],
 "PATCH": {
  "date": "7 Kas 2026",
  "notes": [
   "Güncellemeler artık sorulmadan indirilmez: yeni sürüm bulununca neyin güncelleneceği, inecek boyut ve kısa bir not gösterilip onayınız istenir.",
   "“Güncelle” derseniz güncelleme kurulur ve uygulama kendiliğinden yeniden başlar (seans sürüyorsa bitmesi beklenir); “Şimdi değil” derseniz bir sonraki açılışta yeniden sorulur."
  ]
 },
 "COMPARE": [
  {
   "label": "Aylık jeton hakkı",
   "values": {
    "baslangic": "50",
    "kullandikca": "Yok — kullandıkça",
    "pro": "500",
    "pro_plus": "2.000"
   }
  },
  {
   "label": "Aylık ücret",
   "values": {
    "baslangic": "Alınmıyor",
    "kullandikca": "Alınmıyor",
    "pro": "₺990",
    "pro_plus": "₺1.990"
   }
  },
  {
   "label": "Jeton başına ücret",
   "values": {
    "baslangic": "Alınmıyor",
    "kullandikca": "₺2,90",
    "pro": "Alınmıyor",
    "pro_plus": "Alınmıyor"
   }
  },
  {
   "label": "Ek jeton paketi",
   "values": {
    "baslangic": "✓",
    "kullandikca": "✓",
    "pro": "✓",
    "pro_plus": "✓"
   }
  },
  {
   "label": "AI Pro otomatik seans",
   "values": {
    "baslangic": "Yok",
    "kullandikca": "✓ (5 jeton/seans)",
    "pro": "✓ (5 jeton/seans)",
    "pro_plus": "✓ (5 jeton/seans)"
   }
  },
  {
   "label": "Aynı anda bağlanan cihaz",
   "values": {
    "baslangic": "1",
    "kullandikca": "2",
    "pro": "5",
    "pro_plus": "15"
   }
  },
  {
   "label": "Kurulum profilleri",
   "values": {
    "baslangic": "Evcil Hayvan Sahibi",
    "kullandikca": "Evcil Hayvan Sahibi + Veteriner",
    "pro": "Evcil Hayvan Sahibi + Veteriner",
    "pro_plus": "Evcil Hayvan Sahibi + Veteriner"
   }
  },
  {
   "label": "Araştırma profili",
   "values": {
    "baslangic": "Yok",
    "kullandikca": "+₺390/ay",
    "pro": "+₺390/ay",
    "pro_plus": "+₺390/ay"
   }
  },
  {
   "label": "Hasta kayıtları + istatistikler",
   "values": {
    "baslangic": "Temel",
    "kullandikca": "✓",
    "pro": "✓",
    "pro_plus": "✓"
   }
  },
  {
   "label": "Otomatik güncelleme",
   "values": {
    "baslangic": "✓",
    "kullandikca": "✓",
    "pro": "✓",
    "pro_plus": "✓"
   }
  },
  {
   "label": "Destek yanıt süresi",
   "values": {
    "baslangic": "2 iş günü",
    "kullandikca": "1 iş günü",
    "pro": "1 iş günü",
    "pro_plus": "Aynı iş günü"
   }
  }
 ],
 "FAQ": [
  {
   "q": "İndirdiğim program tam olarak nedir?",
   "a": "Siteden indirdiğiniz küçük kurulum dosyasına “başlatıcı” diyoruz (indirilen dosyanın adı PEMFVetClient-Setup-…exe’dir). Kurulumu birkaç tıkla tamamlarsınız; program açıldığında asıl PEMF Vet uygulamasını — yapay zekâ modelleri ve cihaz yazılımı dahil — sizin için indirip kurar, bitince “Başlat” ile açarsınız. Sonraki güncellemeleri de o getirir; siz bir daha dosya indirmezsiniz."
  },
  {
   "q": "Neden doğrudan uygulamayı indirmiyorum?",
   "a": "Uygulama ve yapay zekâ modelleri birkaç gigabayt tutuyor ve sık güncelleniyor. Başlatıcı yalnız değişen parçaları indirir; böylece ilk kurulumdan sonraki güncellemeler küçük ve hızlı olur, siz de her seferinde büyük bir dosya indirmezsiniz."
  },
  {
   "q": "Hangi işletim sistemleri destekleniyor?",
   "a": "Şu an Windows 10/11 (64-bit) bilgisayarlar ve Android 8.0+ telefonlar. macOS ile Linux sürümleri hazırlanıyor; hazır olduklarında İndir sayfasında görünecekler."
  },
  {
   "q": "İnternet olmadan çalışır mı?",
   "a": "İlk kurulum ve güncellemeler için internet gerekir. Kurulumdan sonra yapay zekâ modelleri cihazınızda çalışır ve klinik verileriniz cihazda şifreli tutulur — seans, acil durdurma ve sensör izleme için internet şart değildir. Yapay zekâ analizi ise internet ister: her analizin jetonu hesabınızdan çevrimiçi düşülür, internet yokken yeni analiz başlatılmaz (süren seans etkilenmez). İnternet ayrıca güncelleme, hesap doğrulama ve (açtıysanız) klinik dışından erişim için kullanılır. Planınız ayda kaç yapay zekâ analizi yapabileceğinizi belirler (bkz. “Pro ile Pro+ arasındaki fark ne?”)."
  },
  {
   "q": "Jeton nedir, neye harcanır?",
   "a": "Jeton, yapay zekâ analizlerinin birimidir: bir görüntü, ses veya sensör analizi 1 jeton; ağır araştırma modelleri (patoloji, RNA, tomografi) 3 jeton; AI Pro’nun otomatik seansı seans başına 5 jeton harcar. Planınız her ay belirli bir jeton hakkıyla yenilenir; hakkınız biterse ek paket alabilirsiniz. ⚠️ Jeton yalnız YAPAY ZEKÂ ANALİZİ içindir: seans başlatma, süren seansı sürdürme, acil durdurma, sensör izleme ve cihaz kontrolü jetondan BAĞIMSIZDIR — jeton bitse bile seans ve acil durdurma engellenmez."
  },
  {
   "q": "Jetonum biterse ne olur? Kullanmadığım jetonlar ne oluyor?",
   "a": "Jetonunuz bittiğinde yeni yapay zekâ analizi başlatamazsınız; tedavi tarafı etkilenmez (seans, acil durdurma ve sensör izleme çalışmaya devam eder). Ek paket alarak hemen devam edebilirsiniz. Planınızın aylık hakkı her dönem yenilenir ve bir sonraki aya devretmez; buna karşılık satın aldığınız jetonların süresi yoktur — kullanana kadar hesabınızda durur. Yapay zekâ analizi internet ister: jeton analiz anında hesabınızdan çevrimiçi düşülür; internet yokken yeni analiz başlatılmaz (süren seans etkilenmez)."
  },
  {
   "q": "Kullandıkça Öde nasıl çalışıyor?",
   "a": "Aylık ücret ödemez, önden jeton satın almazsınız. Kartınızı bir kez tanımlarsınız; yalnız yaptığınız analizler kadar, jeton başına ₺2,90 üzerinden ücretlendirilirsiniz. O ay hiç analiz yapmazsanız hiç ücret çıkmaz. Harcamanız ay sonunda toplu olarak faturalanır. Faturalanmamış kullanım 300 jetona ulaşırsa, ödeme alınana kadar yeni analiz başlatılamaz — böylece beklemediğiniz büyüklükte bir fatura oluşmaz. ⚠️ Bu sınır yalnız yapay zekâ analizleri içindir: seans başlatma, süren seansı sürdürme, acil durdurma ve sensör izleme her koşulda çalışır. Düzenli olarak ayda 340’tan fazla analiz yapıyorsanız Pro planı daha ucuza gelir."
  },
  {
   "q": "Pro ile Pro+ arasındaki fark ne?",
   "a": "İkisinde de aynı uygulama ve aynı yapay zekâ modelleri vardır; fark aylık jeton hakkı, cihaz sayısı ve destek hızıdır. Pro: ayda 500 jeton, 5 cihaza kadar bağlantı, 1 iş günü içinde destek. Pro+: ayda 2.000 jeton, 15 cihaza kadar bağlantı, aynı iş günü içinde öncelikli destek. Kliniğinizde tek cihaz varsa ve ayda birkaç yüz analiz yetiyorsa Pro çoğu durumda yeterlidir; jeton biterse her iki planda da ek paket alabilirsiniz."
  },
  {
   "q": "AI Pro nedir? Hayvana kendi başına seans mı başlatır?",
   "a": "AI Pro, seans sırasında sensörlerden gelen ölçümlere (sıcaklık, alan şiddeti, kamera görüntüsü) bakarak seans ayarlarını otomatik güncelleyen moddur. Seansı HER ZAMAN siz başlatır, siz durdurursunuz; acil durdurma ve süre sınırı her koşulda önceliklidir. Cihaz kendi kendine ve hekim denetimi olmadan seans başlatmaz — nihai karar ve sorumluluk hekimindir."
  },
  {
   "q": "14 günlük deneme sonunda ne oluyor?",
   "a": "Deneme süresi bittiğinde hiçbir ücret çekilmez; kart bilgisi zaten istemiyoruz. Hesabınız ücretsiz Başlangıç düzeyinde çalışmaya devam eder: ayda 50 jeton ve 1 cihaz. Uygulama, hasta kayıtlarınız ve cihaz kontrolü aynen kalır. Daha çok analiz gerekiyorsa hesabınızdan bir plan seçersiniz. (Test aşamasında tüm planlar ücretsiz olduğu için şu an bir kısıtlama uygulanmıyor.)"
  },
  {
   "q": "Aboneliğimi nasıl iptal ederim? Param iade edilir mi?",
   "a": "“Hesabım” menüsündeki “Aboneliği iptal et” ile iptal edersiniz; kısa bir onay adımından sonra otomatik yenileme durur ve bir daha ücret alınmaz. İade koşulları Mesafeli Satış Sözleşmesi ve Ön Bilgilendirme Formu’nda yazılıdır; sorunuz olursa ibiatechnology@gmail.com adresine yazın."
  },
  {
   "q": "Araştırma profili kime gerekli?",
   "a": "Üniversite, laboratuvar ve Ar-Ge ekipleri için: fantom tümör ve elektromanyetik alan ölçümü, petri kuyucuğu analizi, böbrek RNA, bilgisayarlı tomografi ve patoloji modelleri gibi araştırma araçlarını içerir. Günlük klinik pratiği için gerekli değildir — Veteriner profili yeterlidir."
  },
  {
   "q": "Telefon uygulaması ne işe yarıyor?",
   "a": "Telefon uygulaması kliniğinizdeki cihaza bağlanan tam bir kumandadır: seans başlatıp durdurabilir, bobin ayarlarını değiştirebilir, sensör ölçümlerini canlı izleyebilir, acil durdurma yapabilir ve hasta kayıtlarına bakabilirsiniz. Cihaz klinikteki bilgisayara bağlı olduğu için o bilgisayarın açık olması gerekir; aynı ağdayken doğrudan, dışarıdayken güvenli bağlantıyla erişirsiniz. Giriş için masaüstüyle aynı hesabı kullanırsınız."
  },
  {
   "q": "Güncellemeler ücretli mi?",
   "a": "Hayır. Uygulama, cihaz yazılımı ve yapay zekâ modeli güncellemelerinin tamamı planınıza dahildir."
  }
 ]
}

const goruntu = (): Record<string, unknown> => ({
  LEGAL_DOCS: C.LEGAL_DOCS.map((d) => ({ slug: d.slug, title: d.title })),
  COMPANY_updated: C.COMPANY.updated,
  MEDICAL_DISCLAIMER: C.tibbiUyari(),
  DOWNLOAD_HOST: { androidRolNotu: C.DOWNLOAD_HOST.androidRolNotu, androidVersionNote: C.DOWNLOAD_HOST.androidVersionNote },
  CLIENT: { channel: C.CLIENT.channel, releaseDate: C.CLIENT.releaseDate, androidOs: C.CLIENT.downloads.android.os },
  MODULES: C.MODULES.map((m) => ({ id: m.id, name: m.name, tagline: m.tagline, includes: [...m.includes] })),
  PLANS: C.PLANS.map((p) => ({
    tier: p.tier, name: p.name, priceLabel: p.priceLabel ?? null, period: p.period, desc: p.desc, jetonHakki: p.jetonHakki,
    features: [...p.features], cta: p.cta, badge: p.badge ?? null,
  })),
  RESEARCH_ADDON_label: C.RESEARCH_ADDON.label,
  ADDONS: C.ADDONS.map((a) => ({ name: a.name, desc: a.desc, price: a.price })),
  LAUNCHER_STEPS: C.LAUNCHER_STEPS.map((a) => ({ step: a.step, title: a.title, desc: a.desc })),
  FEATURES: C.FEATURES.map((f) => ({ n: f.n, title: f.title, desc: f.desc })),
  PATCH: { date: C.PATCH.date, notes: [...C.PATCH.notes] },
  COMPARE: C.COMPARE.map((r) => ({ label: r.label, values: { ...r.values } })),
  FAQ: C.FAQ.map((f) => ({ q: f.q, a: f.a })),
})

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/
/** Kimlik / yapı alanları (çevrilmez): bu anahtarların değerleri karşılaştırılmaz. */
const YAPI = new Set(['slug', 'id', 'tier', 'step', 'n'])
/** Her iki dilde AYNI olması beklenen marka / kısaltma adları. */
const AYNI = new Set(['Pro', 'Pro+'])

type Yaprak = [yol: string, deger: string]
function yapraklar(o: unknown, yol = ''): Yaprak[] {
  if (typeof o === 'string') return [[yol, o]]
  if (Array.isArray(o)) return o.flatMap((x, i) => yapraklar(x, `${yol}[${i}]`))
  if (o && typeof o === 'object') {
    return Object.entries(o).flatMap(([k, v]) => (YAPI.has(k) ? [] : yapraklar(v, yol ? `${yol}.${k}` : k)))
  }
  return []
}
/** Sayılar (binlik / ondalık ayracı atılarak): fiyat, jeton, gün, cihaz sayısı iki dilde AYNI olmalı. */
const sayilar = (s: string) => (s.match(/\d[\d.,]*/g) ?? []).map((x) => x.replace(/[.,]+$/, '').replace(/[.,]/g, '')).sort()
const harfli = (s: string) => /[A-Za-zÇĞİÖŞÜçğıöşü]{3,}/.test(s)

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

const trGoruntu = () => goruntu()
const enGoruntu = async () => {
  dilMod.__bayrakTestiAyarla(true)
  await i18nMod.dilSec('en')
  return goruntu()
}

describe('site-12c-icerik · Türkçe (bayrak kapalı): göç öncesiyle BAYT BAYT aynı', () => {
  for (const bolum of Object.keys(ALTIN)) {
    it(bolum, () => {
      expect(trGoruntu()[bolum]).toEqual(ALTIN[bolum])
    })
  }
})

describe('site-12c-icerik · İngilizce (bayrak AÇIK)', () => {
  it('her metin yaprağı dolu, Türkçe harfsiz, Türkçeden farklı; sayılar AYNI', async () => {
    const tr = yapraklar(ALTIN)
    const en = new Map(yapraklar(await enGoruntu()))
    expect(tr.length).toBeGreaterThan(150)
    const sorun: string[] = []
    for (const [yol, trDeger] of tr) {
      const enDeger = en.get(yol)
      if (enDeger === undefined || enDeger.trim() === '') { sorun.push(`${yol}: EN boş`); continue }
      if (TR_HARF.test(enDeger)) sorun.push(`${yol}: EN'de Türkçe harf: ${enDeger}`)
      if (harfli(trDeger) && enDeger === trDeger && !AYNI.has(trDeger)) sorun.push(`${yol}: EN = TR (çevrilmemiş): ${trDeger}`)
      if (JSON.stringify(sayilar(trDeger)) !== JSON.stringify(sayilar(enDeger))) sorun.push(`${yol}: sayılar ayrışmış: ${trDeger} ⇄ ${enDeger}`)
    }
    expect(sorun, sorun.join('\n')).toEqual([])
  })

  it('güvenlik ifadeleri korunur: TR "acil durdurma" geçen her metinde EN "emergency stop" geçer', async () => {
    const tr = yapraklar(ALTIN)
    const en = new Map(yapraklar(await enGoruntu()))
    const eksik = tr.filter(([yol, d]) => /acil durdurma/i.test(d) && !/emergency stop/i.test(en.get(yol) ?? '')).map(([yol]) => yol)
    expect(tr.filter(([, d]) => /acil durdurma/i.test(d)).length).toBeGreaterThanOrEqual(6)
    expect(eksik).toEqual([])
  })

  it('tıbbi uyarı: veteriner gözetimi + bilgilendirme amaçlı + teşhisin yerine geçmez iki dilde', async () => {
    expect(C.tibbiUyari()).toMatch(/veteriner hekim gözetiminde/)
    expect(C.tibbiUyari()).toMatch(/bilgilendirme amaçlıdır/)
    expect(C.tibbiUyari()).toMatch(/yerine geçmez/)
    await enGoruntu()
    expect(C.tibbiUyari()).toMatch(/supervision of a veterinarian/)
    expect(C.tibbiUyari()).toMatch(/for information only/)
    expect(C.tibbiUyari()).toMatch(/do not replace/)
  })

  it('SSS iç göndermeleri tutarlı: soru başlıkları / düğme adları / belge adları EN karşılıklarıyla aynı yazılır', async () => {
    await enGoruntu()
    const sss = (id: string, k: 'q' | 'a') => EN[`icerik.sss.${id}.${k}`]
    expect(sss('internet', 'a')).toContain(`“${sss('proProPlus', 'q')}”`)
    const iptal = sss('iptal', 'a')
    expect(iptal).toContain(`“${EN['hesap.hesabim']}”`)
    expect(iptal).toContain(`“${EN['hesap.abonelik.iptalEt']}”`)
    expect(iptal).toContain(EN['icerik.yasal.mesafeliSatis'])
    expect(iptal).toContain(EN['icerik.yasal.onBilgilendirme'])
    expect(C.LEGAL_DOCS.map((d) => d.title)).toContain(EN['icerik.yasal.mesafeliSatis'])
  })

  it('plan karşılaştırma "yok" vurgusu (soluk hücre) iki dilde AYNI hücrelerde', async () => {
    const hucreler = () => C.COMPARE.flatMap((r) => (Object.keys(r.values) as (keyof typeof r.values)[]).map((t) => C.karsilastirmaYokMu(r.values[t])))
    const tr = hucreler()
    await enGoruntu()
    expect(hucreler()).toEqual(tr)
    expect(tr.filter(Boolean).length).toBe(3) // Yok ×2 + Yok — kullandıkça
    expect(C.karsilastirmaYokMu(EN['icerik.karsilastir.alinmiyor'])).toBe(false) // "ücret alınmıyor" = avantaj, soluk DEĞİL
  })
})

// Y166 (S-I18N-P1.11, sahip 2026-10-21; YH A4): SSS'te ürünle çelişen iki cümle ürüne göre düzeltildi (TR + EN; ALTIN'daki iki değer BİLEREK
// değişti): (1) "İnternetiniz yokken de analiz yapabilirsiniz" — ücretlendirme açıkken AI internet ister (S-4B.5, 10-19 K8);
// (2) "sıcaklık kesmesi" — termal kesme / 48 °C interlock YOK (sahip 2026-09-29).
describe('site-12c-icerik · Y166 SSS ürünle çelişmez', () => {
  const SSS_TR = Object.entries(TR).filter(([k]) => k.startsWith('icerik.sss.')).map(([, v]) => String(v))
  const SSS_EN = Object.entries(EN).filter(([k]) => k.startsWith('icerik.sss.')).map(([, v]) => String(v))
  it('SSS taranıyor (boş küme yeşil demez)', () => {
    expect(SSS_TR.length).toBeGreaterThan(10)
    expect(SSS_EN.length).toBe(SSS_TR.length)
  })
  it('internetsiz analiz iddiası YOK; jeton cevabı internet şartını söyler', () => {
    for (const v of SSS_TR) expect(v).not.toMatch(/internet(iniz)? yokken de analiz|tüketim cihazınızda tutulur/i)
    for (const v of SSS_EN) expect(v).not.toMatch(/analys[ie]s while your internet is down|consumption is kept on your device/i)
    expect(TR['icerik.sss.jetonBitince.a']).toMatch(/Yapay zekâ analizi internet ister/)
    expect(EN['icerik.sss.jetonBitince.a']).toMatch(/AI analysis needs the internet/)
  })
  it('termal (sıcaklık) kesme iddiası YOK', () => {
    for (const v of SSS_TR) expect(v).not.toMatch(/sıcaklık kesme|termal kesme/i)
    for (const v of SSS_EN) expect(v).not.toMatch(/temperature cut-?off|thermal cut-?off/i)
    expect(TR['icerik.sss.aiPro.a']).toMatch(/acil durdurma ve süre sınırı her koşulda önceliklidir/)
    expect(EN['icerik.sss.aiPro.a']).toMatch(/emergency stop and the time limit always take priority/)
  })
  it('Y175: AI Pro cevabı "tedavi uygulamaz" demez — seans başlatmaz (Tedavi → Seans kararı); hukuki / sorumluluk cümlesi aynı', () => {
    expect(TR['icerik.sss.aiPro.a']).not.toMatch(/tedavi uygula/i)
    expect(EN['icerik.sss.aiPro.a']).not.toMatch(/apply treatment|treatment/i)
    expect(TR['icerik.sss.aiPro.a']).toMatch(/Cihaz kendi kendine ve hekim denetimi olmadan seans başlatmaz — nihai karar ve sorumluluk hekimindir\./)
    expect(EN['icerik.sss.aiPro.a']).toMatch(/does not start a session on its own or without veterinarian supervision — the final decision and responsibility belong to the veterinarian\./)
  })
  it('Y181 (S-YLI.2): AI Pro SSS SORUSU da "terapi uygular" demez — "seans mı başlatır" (Tedavi → Seans; Y175 cevabıyla tutarlı)', () => {
    expect(TR['icerik.sss.aiPro.q']).toBe('AI Pro nedir? Hayvana kendi başına seans mı başlatır?')
    expect(EN['icerik.sss.aiPro.q']).toBe('What is AI Pro? Does it start a session on the animal on its own?')
    expect(TR['icerik.sss.aiPro.q']).not.toMatch(/terapi|tedavi/i)
    expect(EN['icerik.sss.aiPro.q']).not.toMatch(/therapy|treatment/i)
  })
})

describe('site-12c-icerik · katalog', () => {
  it('config.ts anahtarları iki dilde dolu', () => {
    const anahtarlar = Object.keys(TR).filter((k) => k.startsWith('icerik.'))
    expect(anahtarlar.length).toBeGreaterThanOrEqual(140)
    for (const k of anahtarlar) {
      expect(String(EN[k] ?? '').trim(), `EN boş: ${k}`).not.toBe('')
      expect(TR_HARF.test(EN[k]), `EN'de Türkçe harf: ${k}: ${EN[k]}`).toBe(false)
    }
  })
})
