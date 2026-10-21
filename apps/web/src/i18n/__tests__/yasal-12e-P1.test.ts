/**
 * I18N-P1 · site-12e-yasal — yedi yasal belge (Mesafeli Satış, Ön Bilgilendirme, İptal / İade / Cayma, KVKK Aydınlatma, Gizlilik, Çerez,
 * Kullanım Şartları) + sayfa kabuğu (`src/pages/Legal.tsx`). Her paragraf TEK anahtar + `<Trans>` (KURALLAR §4.1b); şirket alanları
 * (`COMPANY`) `values` ile, kalın / kod parçaları `components` ile. GERÇEK sayfa sunucu tarafı çizilir.
 *  · ALTIN: göç ÖNCESİ kaynaktan Türkçe değerler (yasal.* — 185 anahtar; her biri HEAD kaynağında birebir doğrulandı; tek istisna: yalnız
 *    İngilizce sayfada gösterilen "Türkçe metin bağlayıcıdır" notu).
 *  · Çizim: her belgenin HER paragrafı Türkçede göç öncesi metinle aynı (yer tutucular COMPANY değerleriyle doldurulmuş düz metin); bayrak AÇIK +
 *    İngilizce → her paragrafın İngilizcesi, Türkçesi KALMAZ; "Türkçe metin bağlayıcıdır" notu YALNIZ İngilizce sayfada.
 *  · Hukuki / ticari İngilizce metnin yayın onayı SAHİBE aittir (ceviri anlam birebir; sayılar, süreler, madde numaraları iki dilde aynı).
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
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const { LegalPage } = await import('../../pages/Legal')
const { COMPANY, LEGAL_DOCS } = await import('../../config')

/** Altın tablo: anahtar → göç ÖNCESİ Türkçe değer. */
const ALTIN: Record<string, string> = {
  "yasal.cerez.01": "Bu Çerez Politikası, {{marka}} internet sitesinde kullanılan çerezleri (cookies) ve benzer teknolojileri, bunların amaçlarını ve nasıl yönetebileceğinizi açıklar.",
  "yasal.cerez.02": "1. Çerez Nedir?",
  "yasal.cerez.03": "Çerezler, ziyaret ettiğiniz internet siteleri tarafından tarayıcınıza kaydedilen küçük metin dosyalarıdır. Sitenin çalışmasını sağlamak, tercihlerinizi hatırlamak ve deneyimi iyileştirmek için kullanılır.",
  "yasal.cerez.04": "2. Kullanılan Çerez Türleri",
  "yasal.cerez.05": "<kalin>Zorunlu çerezler:</kalin> Sitenin temel işlevleri, güvenlik ve oturum yönetimi için gereklidir. Bu çerezler olmadan site düzgün çalışmaz. Oturum ve kimlik doğrulama, Supabase altyapısı üzerinden yönetilir.",
  "yasal.cerez.06": "<kalin>İşlevsel çerezler:</kalin> Dil, tema gibi tercihlerinizi hatırlayarak deneyiminizi kişiselleştirir.",
  "yasal.cerez.07": "<kalin>Analitik çerezler:</kalin> Ziyaretçi etkileşimini anonim/istatistiksel olarak ölçerek sitenin performansını ve içeriğini iyileştirmemize yardımcı olur. (Kullanıldığında.)",
  "yasal.cerez.08": "3. Oturum Yönetimi",
  "yasal.cerez.09": "Hesabınıza giriş yaptığınızda, oturumunuzun güvenli biçimde sürdürülebilmesi için kimlik doğrulama çerezleri/depolama kullanılır. Bu, her sayfada yeniden giriş yapmanızı önleyen zorunlu bir işlevdir.",
  "yasal.cerez.10": "4. Çerezleri Yönetme",
  "yasal.cerez.11": "Tarayıcınızın ayarlarından çerezleri silebilir, engelleyebilir veya çerez yerleştirilmeden önce uyarılmayı seçebilirsiniz. Zorunlu çerezlerin engellenmesi, sitenin bazı bölümlerinin (ör. giriş/oturum) düzgün çalışmamasına neden olabilir. Çoğu tarayıcıda çerez yönetimi, \"Ayarlar > Gizlilik/Güvenlik\" bölümünden yapılabilir.",
  "yasal.cerez.12": "5. Güncellemeler ve İletişim",
  "yasal.cerez.13": "Bu politika zaman zaman güncellenebilir. Sorularınız için: {{eposta}}.",
  "yasal.gizlilik.01": "{{marka}} olarak gizliliğinize önem veriyoruz. İşbu Gizlilik Politikası, internet sitemiz ve hizmetlerimiz aracılığıyla toplanan bilgilerin nasıl işlendiğini ve korunduğunu açıklar. Kişisel verilere ilişkin ayrıntılı bilgilendirme için KVKK Aydınlatma Metni'ni de inceleyiniz.",
  "yasal.gizlilik.02": "1. Toplanan Veriler",
  "yasal.gizlilik.03": "Hesap ve iletişim bilgileri (ad-soyad, e-posta, telefon).",
  "yasal.gizlilik.04": "Sipariş, abonelik ve fatura/ödeme bilgileri.",
  "yasal.gizlilik.05": "Oturum ve kimlik doğrulama verileri.",
  "yasal.gizlilik.06": "Teknik veriler: IP adresi, cihaz/tarayıcı bilgisi, log ve çerez verileri.",
  "yasal.gizlilik.07": "2. Verilerin Kullanımı",
  "yasal.gizlilik.08": "Hizmetin sunulması, hesabınızın yönetimi ve aboneliğinizin işletilmesi.",
  "yasal.gizlilik.09": "Yazılım indirme talebinizin karşılanması ve sürüm/güncelleme bildirimlerinin iletilmesi.",
  "yasal.gizlilik.10": "Ödeme ve faturalandırma işlemlerinin gerçekleştirilmesi.",
  "yasal.gizlilik.11": "Destek taleplerinin karşılanması ve sizinle iletişim kurulması.",
  "yasal.gizlilik.12": "Güvenlik, dolandırıcılığın önlenmesi ve hizmet kalitesinin iyileştirilmesi.",
  "yasal.gizlilik.13": "3. Üçüncü Taraf Hizmet Sağlayıcılar",
  "yasal.gizlilik.14": "Hizmetin sunulabilmesi için sınırlı veri, aşağıdaki güvenilir hizmet sağlayıcılarla paylaşılır:",
  "yasal.gizlilik.15": "<kalin>iyzico</kalin> — ödeme işlemlerinin güvenli biçimde gerçekleştirilmesi. Kart bilgileri tarafımızca saklanmaz; doğrudan ödeme kuruluşunun güvenli ortamında işlenir.",
  "yasal.gizlilik.16": "<kalin>Supabase</kalin> — kimlik doğrulama, hesap ve uygulama verilerinin barındırılması/altyapı hizmeti.",
  "yasal.gizlilik.17": "Bu sağlayıcılar, verileri yalnızca hizmetin gerektirdiği amaçla ve kendi gizlilik/güvenlik yükümlülükleri çerçevesinde işler.",
  "yasal.gizlilik.18": "4. Veri Güvenliği",
  "yasal.gizlilik.19": "Kişisel verilerinizi yetkisiz erişime, kayba ve ifşaya karşı korumak için idari ve teknik tedbirler (şifreleme, erişim kontrolleri, güvenli iletişim vb.) uygulanır. Klinik/hasta verileri kural olarak kullanıcı cihazında şifreli tutulur.",
  "yasal.gizlilik.20": "5. Çerezler",
  "yasal.gizlilik.21": "İnternet sitemizde çerezler kullanılmaktadır. Ayrıntılar için Çerez Politikası'nı inceleyebilirsiniz.",
  "yasal.gizlilik.22": "6. Haklarınız ve İletişim",
  "yasal.gizlilik.23": "KVKK kapsamındaki haklarınızı kullanmak veya gizlilikle ilgili taleplerinizi iletmek için {{kvkkEposta}} ya da {{eposta}} adresine başvurabilirsiniz.",
  "yasal.iptal.01": "Bu belge; {{marka}} aboneliğine ilişkin cayma hakkı, iptal ve iade koşullarını 6502 sayılı Kanun ve Mesafeli Sözleşmeler Yönetmeliği çerçevesinde açıklar.",
  "yasal.iptal.02": "1. Cayma Hakkı ({{gun}} Gün)",
  "yasal.iptal.03": "Tüketici, kural olarak hizmetin ifasına başlandığı tarihten itibaren {{gun}} (on dört) gün içinde, gerekçe göstermeksizin ve cezai şart ödemeksizin sözleşmeden cayabilir. Cayma bildirimi {{eposta}} adresine yazılı olarak yapılabilir.",
  "yasal.iptal.04": "2. Dijital Hizmet İstisnası",
  "yasal.iptal.05": "{{marka}} aboneliği, elektronik ortamda anında ifa edilen bir dijital (gayrimaddi) hizmettir. Mesafeli Sözleşmeler Yönetmeliği m.15 uyarınca; tüketicinin açık onayı ile cayma süresi dolmadan hizmetin ifasına başlanması hâlinde cayma hakkı kullanılamaz. Sipariş onayı sırasında tüketici, hizmetin derhâl ifasına başlanmasını talep ettiğinde bu istisnayı kabul etmiş sayılır.",
  "yasal.iptal.06": "3. Aboneliğin İptali",
  "yasal.iptal.07": "Abonelik, hesap ayarlarınızdan veya {{eposta}} adresine bildirimle her zaman iptal edilebilir.",
  "yasal.iptal.08": "İptal, içinde bulunulan (bedeli tahsil edilmiş) dönemin sonunda geçerli olur; bu dönem sonuna kadar hizmete erişim devam eder ve sonraki otomatik yenileme durdurulur.",
  "yasal.iptal.09": "İptal sonrası, kural olarak, içinde bulunulan dönem için ayrıca geri ödeme yapılmaz (bkz. Madde 4).",
  "yasal.iptal.10": "4. İade Süreci",
  "yasal.iptal.11": "Cayma hakkının geçerli biçimde kullanıldığı veya Satıcı'nın uygun bulduğu hâllerde iade, tahsilatın yapıldığı ödeme aracına (kredi/banka kartına) yapılır. İade işlemleri iyzico ödeme altyapısı üzerinden gerçekleştirilir. İade tutarı, cayma/iade talebinin kabulünden itibaren on dört (14) gün içinde başlatılır; tutarın kart hesabına yansıma süresi, ilgili banka/ödeme kuruluşunun işleyişine bağlıdır.",
  "yasal.iptal.12": "5. İletişim",
  "yasal.iptal.13": "İptal, iade ve cayma talepleriniz için: {{eposta}}{{telefon}}.",
  "yasal.kabuk.anaSayfa": "← Ana sayfa",
  "yasal.kabuk.baglayici": "Bu belgenin hukuken bağlayıcı metni Türkçedir.",
  "yasal.kabuk.bulunamadi": "Belge bulunamadı",
  "yasal.kabuk.bulunamadiAciklama": "Aradığınız yasal belge mevcut değil. Aşağıdaki belgelerden birini seçebilirsiniz:",
  "yasal.kabuk.ilgili": "İlgili yasal belgeler",
  "yasal.kabuk.sonGuncelleme": "Son güncelleme: {{tarih}}",
  "yasal.kullanim.01": "İşbu Kullanım Şartları (Üyelik Sözleşmesi), {{marka}} internet sitesi, masaüstü uygulaması ve yazılım hizmetlerinin kullanımına ilişkin koşulları düzenler. Hizmeti kullanarak bu şartları kabul etmiş sayılırsınız.",
  "yasal.kullanim.02": "1. Hesap ve Üyelik",
  "yasal.kullanim.03": "Hizmetten yararlanmak için doğru ve güncel bilgilerle bir hesap oluşturmanız gerekir.",
  "yasal.kullanim.04": "Hesap güvenliğinden (şifre gizliliği dâhil) ve hesabınız üzerinden yapılan işlemlerden siz sorumlusunuz.",
  "yasal.kullanim.05": "Hesabınızın yetkisiz kullanıldığını fark ederseniz derhâl bize bildirmelisiniz.",
  "yasal.kullanim.06": "2. Uygun Kullanım",
  "yasal.kullanim.07": "Hizmeti yalnızca hukuka uygun amaçlarla ve bu şartlara uygun olarak kullanabilirsiniz.",
  "yasal.kullanim.08": "Yazılıma tersine mühendislik uygulanması, izinsiz çoğaltılması, dağıtılması veya lisans kapsamı dışında kullanılması yasaktır.",
  "yasal.kullanim.09": "Sistemin güvenliğini tehlikeye atacak, hizmeti aksatacak veya üçüncü kişilerin haklarını ihlal edecek davranışlardan kaçınmalısınız.",
  "yasal.kullanim.10": "3. Fikri Mülkiyet",
  "yasal.kullanim.11": "{{marka}} yazılımı, yapay zekâ modelleri, arayüz, marka, logo ve tüm içerik; Satıcı'ya veya lisans verenlerine ait olup fikri mülkiyet mevzuatı ile korunmaktadır. Abonelik size, hizmeti kişisel/ kurumsal kullanımınız için sınırlı, münhasır olmayan ve devredilemez bir kullanım hakkı tanır; mülkiyet veya başkaca bir hak devri anlamına gelmez.",
  "yasal.kullanim.12": "4. Sorumluluğun Sınırlandırılması ve Tıbbi Uyarı",
  "yasal.kullanim.13": "<kalin>Tıbbi/veteriner sorumluluk uyarısı:</kalin> {{marka}}, veteriner hekim gözetiminde kullanılmak üzere tasarlanmış bir klinik destek yazılımıdır. Akıllı teşhis ve yapay zekâ analiz çıktıları bilgilendirme amaçlıdır; veteriner hekimin tıbbi teşhis, karar ve tedavisinin yerine geçmez. Otonom seans (AI Pro) özellikleri de dâhil olmak üzere tüm klinik kararlar ve uygulamalar, ilgili veteriner hekimin gözetimi ve sorumluluğu altındadır.",
  "yasal.kullanim.14": "Hizmet \"olduğu gibi\" ve \"mevcut hâliyle\" sunulur. Yürürlükteki mevzuatın izin verdiği azami ölçüde; Satıcı, hizmetin kesintisiz veya hatasız olacağını garanti etmez ve hizmetin kullanımından doğan dolaylı zararlardan sorumlu tutulamaz. Bu madde, tüketici mevzuatından doğan haklarınızı ortadan kaldırmaz.",
  "yasal.kullanim.15": "5. Ücretlendirme ve Abonelik",
  "yasal.kullanim.16": "Ücretli seviyelere ilişkin bedel, ödeme, otomatik yenileme, iptal ve iade koşulları; Mesafeli Satış Sözleşmesi, Ön Bilgilendirme Formu ve İptal/İade/Cayma belgelerinde düzenlenmiştir.",
  "yasal.kullanim.17": "6. Fesih ve Askıya Alma",
  "yasal.kullanim.18": "İşbu şartların ihlali hâlinde Satıcı, hesabınızı önceden bildirimde bulunarak veya ihlalin niteliğine göre derhâl askıya alma ya da hizmeti sonlandırma hakkını saklı tutar. Aboneliğinizi dilediğiniz zaman iptal edebilirsiniz.",
  "yasal.kullanim.19": "7. Değişiklikler",
  "yasal.kullanim.20": "Satıcı, bu şartları güncelleyebilir. Önemli değişiklikler uygun yollarla duyurulur; güncel sürüm bu sayfada yayımlandığı andan itibaren geçerli olur.",
  "yasal.kullanim.21": "8. Uygulanacak Hukuk ve Yetki",
  "yasal.kullanim.22": "İşbu şartlara Türkiye Cumhuriyeti hukuku uygulanır. Uyuşmazlıklarda; tüketici işlemleri bakımından yetkili Tüketici Hakem Heyetleri ve Tüketici Mahkemeleri, diğer hâllerde {{sehir}} mahkemeleri ve icra daireleri yetkilidir.",
  "yasal.kullanim.23": "9. İletişim",
  "yasal.kullanim.24": "Sorularınız için: {{unvan}} — {{eposta}}{{telefon}}.",
  "yasal.kvkk.01": "İşbu Aydınlatma Metni, 6698 sayılı Kişisel Verilerin Korunması Kanunu (\"KVKK\") m.10 kapsamında, veri sorumlusu sıfatıyla kişisel verilerinizin işlenmesine ilişkin olarak sizi bilgilendirmek amacıyla hazırlanmıştır.",
  "yasal.kvkk.02": "1. Veri Sorumlusu",
  "yasal.kvkk.03": "2. İşlenen Kişisel Veriler",
  "yasal.kvkk.04": "Kimlik verileri: ad-soyad, T.C. kimlik numarası (fatura/ödeme için).",
  "yasal.kvkk.05": "İletişim verileri: e-posta, telefon, adres.",
  "yasal.kvkk.06": "Müşteri/işlem verileri: abonelik seviyesi, sipariş ve ödeme kayıtları, fatura bilgileri.",
  "yasal.kvkk.07": "Hesap verileri: kullanıcı hesabı, oturum ve kimlik doğrulama bilgileri.",
  "yasal.kvkk.08": "İşlem güvenliği verileri: IP adresi, log kayıtları, çerez verileri.",
  "yasal.kvkk.09": "Not: Klinik/hasta verileri kural olarak kullanıcı cihazında şifreli tutulur; bu tür veriler yalnızca hizmetin gerektirdiği ölçüde ve ilgili sözleşme/aydınlatma çerçevesinde işlenir.",
  "yasal.kvkk.10": "3. İşleme Amaçları",
  "yasal.kvkk.11": "Abonelik sözleşmesinin kurulması, ifası ve hizmetin sunulması.",
  "yasal.kvkk.12": "Yazılım indirme talebinin karşılanması ve sürüm/güncelleme bildirimlerinin iletilmesi.",
  "yasal.kvkk.13": "Ödeme, faturalandırma ve muhasebe süreçlerinin yürütülmesi.",
  "yasal.kvkk.14": "Müşteri destek, talep ve şikâyetlerin yönetimi.",
  "yasal.kvkk.15": "Hesap güvenliği, dolandırıcılığın önlenmesi ve sistem güvenliği.",
  "yasal.kvkk.16": "Yasal yükümlülüklerin yerine getirilmesi.",
  "yasal.kvkk.17": "4. Hukuki Sebepler (KVKK m.5)",
  "yasal.kvkk.18": "Sözleşmenin kurulması/ifası için veri işlemenin gerekli olması.",
  "yasal.kvkk.19": "Veri sorumlusunun hukuki yükümlülüğünü yerine getirmesi.",
  "yasal.kvkk.20": "Bir hakkın tesisi, kullanılması veya korunması için zorunlu olması.",
  "yasal.kvkk.21": "Veri sorumlusunun meşru menfaatleri (temel hak ve özgürlüklere zarar vermemek kaydıyla).",
  "yasal.kvkk.22": "Gerekli hâllerde açık rızanın alınması.",
  "yasal.kvkk.23": "5. Aktarım",
  "yasal.kvkk.24": "Kişisel verileriniz; hizmetin sunulması amacıyla ödeme kuruluşu (iyzico), altyapı/barındırma hizmet sağlayıcısı (Supabase) ve gerektiğinde yetkili kamu kurum ve kuruluşları ile hukuken yetkili özel kişilere, KVKK m.8 ve m.9'daki şartlara uygun olarak aktarılabilir.",
  "yasal.kvkk.25": "5.1. Yurt Dışına Aktarım (KVKK m.9)",
  "yasal.kvkk.26": "Aşağıdaki veriler, hizmetin teknik olarak sunulabilmesi için <kalin>yurt dışında yerleşik</kalin> hizmet sağlayıcıların altyapısında işlenmektedir:",
  "yasal.kvkk.27": "<kalin>Hesap ve kimlik doğrulama verileri</kalin> — e-posta adresi, şifrenin geri döndürülemez özeti, oturum jetonları, kayıt sırasında verilen ad-soyad/klinik/kurum bilgileri. Alıcı: <kalin>Supabase</kalin> (kimlik doğrulama ve veritabanı hizmeti).",
  "yasal.kvkk.28": "<kalin>Cihaz kayıt defteri verileri</kalin> — cihaz kimliği ve adı, uzaktan erişim adresi, yerel IP adresi ve port, eşleştirme kodu, son görülme zamanı, kurulu yazılım sürümleri, cihazdaki veri şifrelemesinin açık olup olmadığı ve kaydı yalnız o cihazın güncelleyebilmesi için cihaza özgü bir doğrulama anahtarı. Bu kayıt, mobil uygulamanın kliniğin cihazına bağlanabilmesi ve bir güvenlik güncellemesinin hangi cihazlara ulaştığının izlenebilmesi için <kalin>yaklaşık 60 saniyede bir</kalin> güncellenir. Alıcı: <kalin>Supabase</kalin>.",
  "yasal.kvkk.29": "<kalin>Site kullanım ve bağlantı verileri</kalin> — IP adresi ve istek kayıtları. Alıcı: <kalin>Vercel</kalin> (web sitesi barındırma).",
  "yasal.kvkk.30": "<kalin>Hasta ve seans kayıtları (klinik verisi) yurt dışına aktarılmaz.</kalin> Bu veriler kliniğin kendi cihazında şifreli olarak tutulur. Yazılım, klinik verisinin buluta eşitlenmesini <kalin>varsayılan olarak kapalı</kalin> tutar; bu ayar yalnızca klinik tarafından açıkça etkinleştirilirse devreye girer ve o durumda da kişisel veri alanları şifreli olarak gönderilir.",
  "yasal.kvkk.31": "Ödeme işlemleri <kalin>iyzico</kalin> (Türkiye'de yerleşik ödeme kuruluşu) üzerinden yürütülür; kart verileri tarafımızca saklanmaz.",
  "yasal.kvkk.32": "Yurt dışına aktarım, KVKK m.9'da öngörülen şartlara dayanılarak yapılır. Aktarımın kapsamı, alıcıları ve dayanağı hakkında bilgi talebinizi {{kvkkEposta}} adresine iletebilirsiniz.",
  "yasal.kvkk.33": "6. Saklama Süresi",
  "yasal.kvkk.34": "Kişisel verileriniz, işleme amacının gerektirdiği süre ile ilgili mevzuatta öngörülen (ör. ticari ve vergisel kayıtlar için yasal) süreler boyunca saklanır; sürelerin sonunda silinir, yok edilir veya anonim hâle getirilir.",
  "yasal.kvkk.35": "<kalin>Klinik cihazındaki tedavi kayıtları için yazılımın uyguladığı somut süreler</kalin> (yazılımın varsayılanları):",
  "yasal.kvkk.36": "Seans sırasında kaydedilen sensör ölçümleri (bobin sıcaklığı, manyetik alan, akım): <kalin>90 gün</kalin>.",
  "yasal.kvkk.37": "Uygulanan doz kayıtları (hangi bobin, hangi frekans ve oranla, ne kadar süre çalıştı): <kalin>3650 gün (10 yıl)</kalin>.",
  "yasal.kvkk.38": "Seans olay kayıtları (başlatma, bitiş ve benzeri): <kalin>365 gün</kalin>. Acil durdurma kayıtları (nedeniyle birlikte: aşırı akım, iletişim reddi, kart bağlantısının kopması ve benzeri), acil durdurma kilidinin sıfırlanması, AI önerisinin hekim tarafından onaylanması ya da reddedilmesi ve seansı kesen servis kapanışı <kalin>SÜRESİZ</kalin> saklanır. Süresi dolan olayların silinmesi, silinen kayıt sayısıyla denetim izine yazılır.",
  "yasal.kvkk.39": "Hasta kimlik bilgileri: <kalin>1825 gün (5 yıl)</kalin> boyunca tedavi kaydı olmayan hastanın adı, sahibinin adı, iletişim bilgileri, yaşı ve kilosu — seans ve AI analiz kayıtlarındaki adı dahil — anonimleştirilir; bu işlem geri alınamaz olduğu için klinik <kalin>açıkça onaylamadan başlamaz</kalin> (Ayarlar → Veri Saklama Süresi, bekleyen hasta sayısı gösterilir). Tedavi verileri (uygulanan doz, süre, sensör ölçümleri), tür/ırk bilgisi ve tedaviyi uygulayan hekimin adı kalır.",
  "yasal.kvkk.40": "Seans kayıtlarındaki adların maskelenmesi <kalin>varsayılan olarak KAPALI</kalin>dır ve klinik açıkça onaylamadan başlamaz. Klinik onaylarsa, seçilen süreden (varsayılan <kalin>365 gün</kalin>) eski seans kayıtlarındaki hasta ve operatör adları ile serbest metin notlar geri dönüşsüz biçimde maskelenir: kayıtta adın yerinde <kod>[REDACTED]</kod> ibaresi görünür. Tedavi verileri maskelenmez. Onay yalnız verildiği süre için geçerlidir: süre değiştirilirse onay düşer ve yeni süreyle etkilenecek kayıt sayısı gösterilerek<kalin> yeniden onay</kalin> istenir.",
  "yasal.kvkk.41": "Maskeleme süresi klinik tarafından uygulama içinden değiştirilebilir (Ayarlar → Veri Saklama Süresi) veya tamamen kapatılabilir; tıbbi ve hukuki saklama yükümlülüğü ülkeye ve olaya göre değiştiğinden karar veri sorumlusu kliniğe aittir.",
  "yasal.kvkk.42": "7. İlgili Kişinin Hakları (KVKK m.11)",
  "yasal.kvkk.43": "Kişisel verinizin işlenip işlenmediğini öğrenme ve işlenmişse buna ilişkin bilgi talep etme.",
  "yasal.kvkk.44": "İşleme amacını ve amacına uygun kullanılıp kullanılmadığını öğrenme.",
  "yasal.kvkk.45": "Yurt içinde/yurt dışında aktarıldığı üçüncü kişileri bilme.",
  "yasal.kvkk.46": "Eksik/yanlış işlenmişse düzeltilmesini isteme.",
  "yasal.kvkk.47": "KVKK'da öngörülen şartlarla silinmesini/yok edilmesini isteme.",
  "yasal.kvkk.48": "Düzeltme/silme işlemlerinin aktarıldığı üçüncü kişilere bildirilmesini isteme.",
  "yasal.kvkk.49": "Otomatik sistemlerle analiz sonucu aleyhe bir sonucun ortaya çıkmasına itiraz etme.",
  "yasal.kvkk.50": "Kanuna aykırı işleme nedeniyle zarara uğraması hâlinde zararın giderilmesini talep etme.",
  "yasal.kvkk.51": "8. Başvuru",
  "yasal.kvkk.52": "KVKK m.11 kapsamındaki taleplerinizi, kimliğinizi tevsik eden bilgilerle birlikte {{kvkkEposta}} adresine iletebilir veya {{adres}}, {{sehir}} adresine yazılı olarak başvurabilirsiniz. Başvurularınız, KVKK'da öngörülen süreler içinde sonuçlandırılır.",
  "yasal.mesafeli.01": "İşbu Mesafeli Satış Sözleşmesi (\"Sözleşme\"), 6502 sayılı Tüketicinin Korunması Hakkında Kanun ve Mesafeli Sözleşmeler Yönetmeliği hükümlerine uygun olarak, aşağıda kimlik ve iletişim bilgileri yer alan Satıcı ile Alıcı arasında, elektronik ortamda kurulmuştur. Alıcı, siparişini onayladığında işbu Sözleşme'nin tüm koşullarını okuduğunu, anladığını ve kabul ettiğini beyan eder.",
  "yasal.mesafeli.02": "MADDE 1 — TARAFLAR",
  "yasal.mesafeli.03": "1.1. Satıcı",
  "yasal.mesafeli.04": "1.2. Alıcı",
  "yasal.mesafeli.05": "Sipariş sırasında üyelik/fatura formunda beyan ettiği ad-soyad, adres, e-posta ve iletişim bilgileri esas alınan tüketici (\"ALICI\"). Bu bilgiler sipariş özetinde ve fatura bilgilerinde yer alır.",
  "yasal.mesafeli.06": "MADDE 2 — SÖZLEŞMENİN KONUSU",
  "yasal.mesafeli.07": "İşbu Sözleşme'nin konusu; ALICI'nın Satıcı'ya ait {{marka}} internet sitesi üzerinden elektronik ortamda siparişini verdiği, aşağıda nitelikleri ve satış bedeli belirtilen dijital yazılım hizmeti/aboneliğinin satışı ile ifasına ilişkin olarak tarafların hak ve yükümlülüklerinin 6502 sayılı Kanun ve Mesafeli Sözleşmeler Yönetmeliği hükümleri uyarınca belirlenmesidir.",
  "yasal.mesafeli.08": "MADDE 3 — SÖZLEŞME KONUSU ÜRÜN/HİZMET",
  "yasal.mesafeli.09": "Sözleşme konusu, {{marka}} veteriner klinik destek yazılımının internet üzerinden sunulan, süreli (aylık/yıllık) aboneliğe dayalı dijital hizmetidir. Hizmet; seçilen abonelik seviyesine göre yazılım kullanım lisansı, yapay zekâ analiz/teşhis modülleri, otomatik güncelleme ve destek hizmetlerini kapsar. Hizmetin temel nitelikleri, seviye kapsamı ve güncel bedeli, sipariş anında internet sitesinin fiyatlandırma ve sipariş özeti sayfalarında gösterilir.",
  "yasal.mesafeli.10": "Hizmet fiziksel bir mal teslimi içermez; gayrimaddi (dijital) hizmet olarak elektronik ortamda ifa edilir.",
  "yasal.mesafeli.11": "MADDE 4 — SÖZLEŞME BEDELİ VE ÖDEME",
  "yasal.mesafeli.12": "Hizmetin, tüm vergiler (KDV) dâhil toplam bedeli, sipariş özetinde ALICI'ya açıkça gösterilen tutardır.",
  "yasal.mesafeli.13": "Ödeme, ödeme kuruluşu iyzico altyapısı üzerinden kredi/banka kartı ile güvenli olarak tahsil edilir. Kart bilgileri Satıcı tarafından saklanmaz; ödeme sürecinde iyzico'nun güvenli ortamına aktarılır.",
  "yasal.mesafeli.14": "Abonelik, seçilen döneme (aylık/yıllık) göre peşin tahsil edilir ve ALICI iptal etmediği sürece aynı süre için otomatik olarak yenilenir (bkz. Madde 6 ve Ön Bilgilendirme Formu).",
  "yasal.mesafeli.15": "Ödemenin herhangi bir nedenle yapılamaması veya iptal edilmesi hâlinde Satıcı, hizmeti askıya alma veya Sözleşme'yi feshetme hakkını saklı tutar.",
  "yasal.mesafeli.16": "MADDE 5 — İFA VE ERİŞİM",
  "yasal.mesafeli.17": "Ödemenin onaylanmasının ardından hizmet, ALICI'nın hesabına elektronik ortamda ve kural olarak anında tanımlanır. İfa süresi, yasal azami otuz (30) günü aşamaz. ALICI, hizmete erişim için gerekli internet bağlantısı ve uyumlu cihaz/işletim sistemi koşullarını sağlamakla yükümlüdür.",
  "yasal.mesafeli.18": "MADDE 6 — CAYMA HAKKI VE İSTİSNASI",
  "yasal.mesafeli.19": "ALICI, kural olarak, hizmetin ifasına başlanmasından itibaren {{gun}} (on dört) gün içinde hiçbir gerekçe göstermeksizin ve cezai şart ödemeksizin Sözleşme'den cayma hakkına sahiptir.",
  "yasal.mesafeli.20": "<kalin>İstisna:</kalin> Mesafeli Sözleşmeler Yönetmeliği'nin 15. maddesi uyarınca; elektronik ortamda anında ifa edilen hizmetler ile tüketiciye anında teslim edilen gayrimaddi mallara ilişkin sözleşmelerde ve tüketicinin onayı ile ifasına başlanan hizmetlerde cayma hakkı kullanılamaz. Buna göre; ALICI'nın açık onayı ile cayma süresi dolmadan yazılım hizmeti/aboneliğinin ifasına başlanması hâlinde ALICI cayma hakkını kaybeder. ALICI, siparişi onaylayarak, hizmetin cayma süresi içinde ifasına başlanmasını açıkça talep ve kabul ettiğini beyan eder.",
  "yasal.mesafeli.21": "Cayma hakkının geçerli olduğu hâllerde ALICI, {{eposta}} adresine yazılı bildirimde bulunarak hakkını kullanabilir; bu durumda tahsil edilen bedel, cayma bildiriminin ulaşmasından itibaren on dört (14) gün içinde aynı ödeme aracına iade edilir.",
  "yasal.mesafeli.22": "MADDE 7 — GENEL HÜKÜMLER",
  "yasal.mesafeli.23": "ALICI, hizmeti hukuka ve Kullanım Şartları'na uygun biçimde kullanmayı kabul eder. Yazılım, veteriner hekim gözetiminde kullanılan bir klinik destek aracıdır ve hekimin tıbbi karar, teşhis ve tedavisinin yerine geçmez.",
  "yasal.mesafeli.24": "Satıcı; mücbir sebep hâllerinde, hizmet sağlayıcılarından kaynaklanan aksaklıklarda veya ALICI'nın koşulları sağlamamasından doğan durumlarda ifadan sorumlu tutulamaz.",
  "yasal.mesafeli.25": "ALICI'nın kişisel verileri, KVKK Aydınlatma Metni ve Gizlilik Politikası çerçevesinde işlenir.",
  "yasal.mesafeli.26": "MADDE 8 — UYUŞMAZLIKLARIN ÇÖZÜMÜ",
  "yasal.mesafeli.27": "İşbu Sözleşme'den doğabilecek uyuşmazlıklarda, Ticaret Bakanlığı'nca ilan edilen parasal sınırlar dâhilinde ALICI'nın yerleşim yerindeki veya işlemin yapıldığı yerdeki Tüketici Hakem Heyetleri; bu sınırların üzerindeki uyuşmazlıklarda ise Tüketici Mahkemeleri yetkilidir.",
  "yasal.mesafeli.28": "MADDE 9 — YÜRÜRLÜK",
  "yasal.mesafeli.29": "İşbu Sözleşme, ALICI tarafından elektronik ortamda okunup kabul edilerek siparişin onaylanması ve ödemenin tamamlanması ile yürürlüğe girer. Sözleşme'nin bir örneği ALICI'nın erişimine sunulur ve/veya e-posta ile iletilir.",
  "yasal.onbilgi.01": "İşbu Ön Bilgilendirme Formu, 6502 sayılı Tüketicinin Korunması Hakkında Kanun ve Mesafeli Sözleşmeler Yönetmeliği uyarınca, siparişinizi onaylamadan önce sizi bilgilendirmek amacıyla hazırlanmıştır. Siparişin onaylanması, işbu formda yer alan hususların okunup kabul edildiği anlamına gelir.",
  "yasal.onbilgi.02": "1. Satıcı / Hizmet Sağlayıcı Kimliği",
  "yasal.onbilgi.03": "2. Hizmetin Temel Nitelikleri",
  "yasal.onbilgi.04": "{{marka}}, veteriner hekim gözetiminde kullanılmak üzere tasarlanmış bir klinik destek yazılımıdır. Abonelik; yazılım kullanım lisansını, yapay zekâ analiz/teşhis modüllerini, otomatik güncellemeleri ve seçilen seviyeye göre destek hizmetini kapsar. Hizmet dijital (gayrimaddi) olarak internet üzerinden ifa edilir; fiziksel teslimat içermez. Hizmetin seviye kapsamı ve güncel özellikleri sipariş anında fiyatlandırma sayfasında gösterilir.",
  "yasal.onbilgi.05": "3. Toplam Fiyat ve Ödeme",
  "yasal.onbilgi.06": "Hizmetin, tüm vergiler (KDV) dâhil toplam satış bedeli, sipariş özetinde açıkça belirtilir. Fiyata dâhil olan/olmayan tüm kalemler sipariş ekranında gösterilir.",
  "yasal.onbilgi.07": "Ödeme, iyzico güvenli ödeme altyapısı üzerinden kredi/banka kartı ile yapılır.",
  "yasal.onbilgi.08": "Abonelik bedeli, seçilen döneme (aylık/yıllık) göre peşin tahsil edilir.",
  "yasal.onbilgi.09": "4. İfa (Erişim) Şekli ve Süresi",
  "yasal.onbilgi.10": "Hizmet, ödemenin onaylanmasının ardından elektronik ortamda ve kural olarak anında ALICI hesabına tanımlanır. Yasal azami ifa süresi otuz (30) gündür.",
  "yasal.onbilgi.11": "5. Cayma Hakkı ve İstisnaları",
  "yasal.onbilgi.12": "Tüketici, kural olarak {{gun}} (on dört) gün içinde gerekçe göstermeksizin cayma hakkına sahiptir. Ancak Mesafeli Sözleşmeler Yönetmeliği'nin 15. maddesi gereğince; elektronik ortamda anında ifa edilen hizmetler ve tüketiciye anında teslim edilen gayrimaddi mallar ile tüketicinin onayıyla ifasına başlanan hizmetlerde cayma hakkı kullanılamaz.",
  "yasal.onbilgi.13": "Bu kapsamda; abonelik hizmetinin, tüketicinin açık onayı ile cayma süresi içinde ifasına başlanması hâlinde cayma hakkı sona erer. Siparişi onaylayan tüketici, hizmetin derhâl ifasına başlanmasını açıkça talep ettiğini ve bu hâlde cayma hakkını yitireceğini bildiğini kabul eder.",
  "yasal.onbilgi.14": "6. Otomatik Yenilenen Abonelik Beyanı",
  "yasal.onbilgi.15": "Abonelik, seçilen dönemin (aylık/yıllık) sonunda, tüketici iptal etmediği sürece aynı süre için otomatik olarak yenilenir ve kayıtlı ödeme yöntemi üzerinden ilgili dönem bedeli tahsil edilir. Tüketici, aboneliğini dilediği zaman hesabı üzerinden veya {{eposta}} adresine bildirimle iptal edebilir; iptal, içinde bulunulan dönemin sonunda geçerli olur ve sonraki yenileme durdurulur.",
  "yasal.onbilgi.16": "7. Şikâyet ve İtiraz Başvuru Mercii",
  "yasal.onbilgi.17": "Tüketici, Ticaret Bakanlığı'nca belirlenen parasal sınırlar çerçevesinde, yerleşim yerindeki veya işlemin yapıldığı yerdeki Tüketici Hakem Heyeti'ne ya da Tüketici Mahkemesi'ne başvurabilir. Talep ve şikâyetler ayrıca {{eposta}} adresine iletilebilir.",
  "yasal.satici.adres": "Adres: {{adres}}, {{sehir}}, {{ulke}}",
  "yasal.satici.eposta": "E-posta: {{eposta}}",
  "yasal.satici.mersis": "MERSIS No: {{mersis}}",
  "yasal.satici.sicil": "Ticaret Sicil No: {{sicil}}",
  "yasal.satici.tel": "Telefon: {{tel}}",
  "yasal.satici.tur": "İşletme türü: {{tur}}",
  "yasal.satici.unvan": "Unvan: {{unvan}}",
  "yasal.satici.vergi": "Vergi Dairesi / Vergi No (veya TCKN): {{daire}} / {{vergiNo}}",
}

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/
const yerTutucu = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort()
const etiketler = (s: string) => [...s.matchAll(/<\/?(\w+)>/g)].map((m) => m[0]).sort()
const sayilar = (s: string) => (s.replace(/<\/?\w+>/g, '').match(/\d[\d.,]*/g) ?? []).map((x) => x.replace(/[.,]+$/, '').replace(/[.,]/g, '')).sort()

const DEGER: Record<string, string> = {
  marka: COMPANY.brandName,
  eposta: COMPANY.email,
  kvkkEposta: COMPANY.kvkkEmail,
  gun: String(COMPANY.withdrawalDays),
  adres: COMPANY.address,
  sehir: COMPANY.city,
  ulke: COMPANY.country,
  unvan: COMPANY.legalName,
  tur: COMPANY.entityType,
  tel: COMPANY.phone,
  daire: COMPANY.taxOffice,
  vergiNo: COMPANY.taxNo,
  mersis: COMPANY.mersis,
  sicil: COMPANY.tradeRegistry,
  telefon: COMPANY.phone ? ` — ${COMPANY.phone}` : '',
}
const coz = (s: string) => s.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
const bosluk = (s: string) => s.replace(/\s+/g, ' ').trim()
/** Çizilen HTML'in düz metni (etiketsiz, `<!-- -->` ayraçsız, varlıklar çözülmüş, boşluklar tek). */
const duz = (h: string) => bosluk(coz(h.replace(/<!-- -->/g, '').replace(/<[^>]*>/g, '')))
/** Katalog değerinin ekranda görünmesi beklenen düz metni (yer tutucular COMPANY ile, etiketler atılmış). */
const beklenen = (deger: string) => bosluk(deger.replace(/<\/?\w+>/g, '').replace(/\{\{(\w+)\}\}/g, (_, a) => DEGER[a] ?? `{{${a}}}`))

const ciz = (slug: string) =>
  renderToString(createElement(MemoryRouter, { initialEntries: [`/${slug}`] }, createElement(LegalPage)))

const BELGE: Record<string, string> = {
  'mesafeli-satis': 'mesafeli',
  'on-bilgilendirme': 'onbilgi',
  'iptal-iade': 'iptal',
  kvkk: 'kvkk',
  gizlilik: 'gizlilik',
  'cerez-politikasi': 'cerez',
  'kullanim-sartlari': 'kullanim',
}
const SATICI_BELGELERI = new Set(['mesafeli-satis', 'on-bilgilendirme', 'kvkk'])
const belgeAnahtarlari = (slug: string) =>
  Object.keys(ALTIN)
    .filter((k) => k.startsWith(`yasal.${BELGE[slug]}.`) || (SATICI_BELGELERI.has(slug) && k.startsWith('yasal.satici.') && (k !== 'yasal.satici.tel' || COMPANY.phone)))
    .sort()

afterEach(async () => {
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

describe('site-12e-yasal · altın tablo', () => {
  const anahtarlar = Object.keys(ALTIN).sort()

  it('185 anahtar (kapı küçülmesin)', () => {
    expect(anahtarlar.length).toBe(185)
  })

  for (const k of anahtarlar) {
    it(`${k} · TR değer göç öncesiyle BAYT BAYT aynı · EN dolu; aynı yer tutucu / etiket / SAYI`, () => {
      expect(TR[k], `TR değer eskisinden FARKLI: ${k}`).toBe(ALTIN[k])
      expect(String(EN[k] ?? '').trim(), `EN boş: ${k}`).not.toBe('')
      // "Türkiye" resmî İngilizce devlet adıdır; başka Türkçe harf EN'de bulunmamalı
      expect(TR_HARF.test(EN[k].replace(/Türkiye/g, '')), `EN'de Türkçe harf: ${k}: ${EN[k]}`).toBe(false)
      expect(yerTutucu(EN[k]), `yer tutucu kümesi ayrışmış: ${k}`).toEqual(yerTutucu(TR[k]))
      expect(etiketler(EN[k]), `etiket kümesi ayrışmış: ${k}`).toEqual(etiketler(TR[k]))
      expect(sayilar(EN[k]), `sayılar ayrışmış: ${k}`).toEqual(sayilar(TR[k]))
    })
  }
})

describe('site-12e-yasal · çizim', () => {
  for (const slug of Object.keys(BELGE)) {
    it(`${slug} · Türkçe (bayrak kapalı): HER paragraf göç öncesiyle aynı düz metin; bağlayıcılık notu YOK`, () => {
      const h = ciz(slug)
      const metin = duz(h)
      const anahtarlar = belgeAnahtarlari(slug)
      expect(anahtarlar.length).toBeGreaterThan(10)
      for (const k of anahtarlar) expect(metin.includes(beklenen(ALTIN[k])), `${slug}: ${k}`).toBe(true)
      expect(coz(h)).not.toMatch(/\{\{\w+\}\}/)
      expect(metin).not.toContain(ALTIN['yasal.kabuk.baglayici'])
      expect(metin).toContain(`Son güncelleme: ${COMPANY.updated}`)
    })

    it(`${slug} · bayrak AÇIK + İngilizce: HER paragraf İngilizce, Türkçesi KALMAZ; bağlayıcılık notu VAR`, async () => {
      dilMod.__bayrakTestiAyarla(true)
      await i18nMod.dilSec('en')
      const h = ciz(slug)
      const metin = duz(h)
      for (const k of belgeAnahtarlari(slug)) {
        expect(metin.includes(beklenen(EN[k])), `${slug} EN: ${k}`).toBe(true)
        const tr = beklenen(ALTIN[k])
        if (tr !== beklenen(EN[k]) && tr.length > 12) expect(metin.includes(tr), `${slug} TR kaldı: ${k}`).toBe(false)
      }
      expect(coz(h)).not.toMatch(/\{\{\w+\}\}/)
      expect(metin).toContain(EN['yasal.kabuk.baglayici'])
      expect(metin).toContain(`Last updated: ${COMPANY.updated}`)
      if (SATICI_BELGELERI.has(slug) || slug === 'kullanim-sartlari') expect(h).toContain(COMPANY.legalName) // yasal kimlik verisi (ünvan) iki dilde aynı
    })
  }

  it('yasal belge başlığı ve ilgili belgeler listesi iki dilde (config getter)', async () => {
    const trMetin = duz(ciz('kvkk'))
    for (const d of LEGAL_DOCS.filter((x) => x.slug !== 'kvkk')) expect(trMetin).toContain(d.title)
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const enMetin = duz(ciz('kvkk'))
    expect(enMetin).toContain('Related legal documents')
    for (const d of LEGAL_DOCS.filter((x) => x.slug !== 'kvkk')) expect(enMetin).toContain(d.title)
    expect(enMetin).toContain('Distance Sales Agreement')
  })

  it('bilinmeyen belge sayfası iki dilde', async () => {
    const trMetin = duz(ciz('olmayan-belge'))
    expect(trMetin).toContain('Belge bulunamadı')
    expect(trMetin).toContain('Aradığınız yasal belge mevcut değil. Aşağıdaki belgelerden birini seçebilirsiniz:')
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const enMetin = duz(ciz('olmayan-belge'))
    expect(enMetin).toContain('Document not found')
    expect(enMetin).toContain('Back to the home page')
    expect(enMetin).not.toContain('Belge bulunamadı')
  })

  it('kritik hukuki / güvenlik ifadeleri iki dilde korunur (KVKK saklama süreleri, hasta verisi yurt dışına gitmez, hekim sorumluluğu)', async () => {
    const trKvkk = duz(ciz('kvkk'))
    expect(trKvkk).toContain('Hasta ve seans kayıtları (klinik verisi) yurt dışına aktarılmaz.')
    for (const s of ['90 gün', '3650 gün (10 yıl)', '365 gün', 'SÜRESİZ', '1825 gün (5 yıl)']) expect(trKvkk).toContain(s)
    const trKullanim = duz(ciz('kullanim-sartlari'))
    expect(trKullanim).toContain('veteriner hekimin tıbbi teşhis, karar ve tedavisinin yerine geçmez')
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const enKvkk = duz(ciz('kvkk'))
    expect(enKvkk).toContain('Patient and session records (clinical data) are not transferred abroad.')
    for (const s of ['90 days', '3650 days (10 years)', '365 days', 'INDEFINITELY', '1825 days (5 years)', 'Supabase', 'Vercel', 'iyzico']) expect(enKvkk).toContain(s)
    const enKullanim = duz(ciz('kullanim-sartlari'))
    expect(enKullanim).toContain('do not replace the veterinarian’s medical diagnosis, decisions and treatment')
    expect(enKullanim).toContain('under the supervision and responsibility of the relevant veterinarian')
  })
})
