// Author: mertaygn, cglrgrkn
import { useLocation, Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { COMPANY, LEGAL_DOCS } from '../config'
import type { LegalSlug } from '../config'

/* ============================================================
   PEMF Vet — Yasal belgeler (tek bileşen, route'a göre içerik)
   ŞABLON: Metinler 6502 sy. TKHK, Mesafeli Sözleşmeler Yönetmeliği
   (2015), 6563 sy. E-Ticaret Kanunu ve 6698 sy. KVKK çerçevesinde
   hazırlanmış taslaklardır. Şirket bilgileri config.ts > COMPANY'den
   okunur (placeholder'lar doldurulunca tüm belgeler güncellenir).
   Yayına almadan önce bir hukuk danışmanınca gözden geçirilmelidir.
   ============================================================ */

/* ---- Küçük, yeniden kullanılabilir metin bileşenleri ---- */
function H2({ children }: { children: ReactNode }) {
  return <h2 className="mt-8 mb-3 text-xl font-bold text-fg">{children}</h2>
}
function H3({ children }: { children: ReactNode }) {
  return <h3 className="mt-5 mb-2 text-base font-semibold text-fg">{children}</h3>
}
function P({ children }: { children: ReactNode }) {
  return <p className="mb-3 text-sm leading-relaxed text-muted">{children}</p>
}
function UL({ children }: { children: ReactNode }) {
  return (
    <ul className="mb-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">{children}</ul>
  )
}

/* Satıcı kimliği — 6563 sy. Kanun m.5 + Yönetmelik zorunlu bilgileri. */
function SellerIdentity() {
  return (
    <UL>
      <li>Unvan: {COMPANY.legalName}</li>
      <li>İşletme türü: {COMPANY.entityType}</li>
      <li>
        Adres: {COMPANY.address}, {COMPANY.city}, {COMPANY.country}
      </li>
      {COMPANY.phone ? <li>Telefon: {COMPANY.phone}</li> : null}
      <li>E-posta: {COMPANY.email}</li>
      <li>
        Vergi Dairesi / Vergi No (veya TCKN): {COMPANY.taxOffice} / {COMPANY.taxNo}
      </li>
      <li>MERSIS No: {COMPANY.mersis}</li>
      <li>Ticaret Sicil No: {COMPANY.tradeRegistry}</li>
    </UL>
  )
}

/* ------------------------------------------------------------------
   BELGE İÇERİKLERİ — her slug için bir taslak.
   ------------------------------------------------------------------ */
const DOCS: Record<LegalSlug, ReactNode> = {
  /* =============== 1) MESAFELİ SATIŞ SÖZLEŞMESİ =============== */
  'mesafeli-satis': (
    <>
      <P>
        İşbu Mesafeli Satış Sözleşmesi ("Sözleşme"), 6502 sayılı Tüketicinin Korunması Hakkında
        Kanun ve Mesafeli Sözleşmeler Yönetmeliği hükümlerine uygun olarak, aşağıda kimlik ve iletişim
        bilgileri yer alan Satıcı ile Alıcı arasında, elektronik ortamda kurulmuştur. Alıcı, siparişini
        onayladığında işbu Sözleşme'nin tüm koşullarını okuduğunu, anladığını ve kabul ettiğini beyan eder.
      </P>

      <H2>MADDE 1 — TARAFLAR</H2>
      <H3>1.1. Satıcı</H3>
      <SellerIdentity />
      <H3>1.2. Alıcı</H3>
      <P>
        Sipariş sırasında üyelik/fatura formunda beyan ettiği ad-soyad, adres, e-posta ve iletişim
        bilgileri esas alınan tüketici ("ALICI"). Bu bilgiler sipariş özetinde ve fatura bilgilerinde yer alır.
      </P>

      <H2>MADDE 2 — SÖZLEŞMENİN KONUSU</H2>
      <P>
        İşbu Sözleşme'nin konusu; ALICI'nın Satıcı'ya ait {COMPANY.brandName} internet sitesi üzerinden
        elektronik ortamda siparişini verdiği, aşağıda nitelikleri ve satış bedeli belirtilen dijital
        yazılım hizmeti/aboneliğinin satışı ile ifasına ilişkin olarak tarafların hak ve yükümlülüklerinin
        6502 sayılı Kanun ve Mesafeli Sözleşmeler Yönetmeliği hükümleri uyarınca belirlenmesidir.
      </P>

      <H2>MADDE 3 — SÖZLEŞME KONUSU ÜRÜN/HİZMET</H2>
      <P>
        Sözleşme konusu, {COMPANY.brandName} veteriner klinik destek yazılımının internet üzerinden
        sunulan, süreli (aylık/yıllık) aboneliğe dayalı dijital hizmetidir. Hizmet; seçilen abonelik
        seviyesine göre yazılım kullanım lisansı, yapay zekâ analiz/teşhis modülleri, otomatik güncelleme
        ve destek hizmetlerini kapsar. Hizmetin temel nitelikleri, seviye kapsamı ve güncel bedeli,
        sipariş anında internet sitesinin fiyatlandırma ve sipariş özeti sayfalarında gösterilir.
      </P>
      <P>
        Hizmet fiziksel bir mal teslimi içermez; gayrimaddi (dijital) hizmet olarak elektronik ortamda ifa edilir.
      </P>

      <H2>MADDE 4 — SÖZLEŞME BEDELİ VE ÖDEME</H2>
      <UL>
        <li>
          Hizmetin, tüm vergiler (KDV) dâhil toplam bedeli, sipariş özetinde ALICI'ya açıkça gösterilen tutardır.
        </li>
        <li>
          Ödeme, ödeme kuruluşu iyzico altyapısı üzerinden kredi/banka kartı ile güvenli olarak tahsil edilir.
          Kart bilgileri Satıcı tarafından saklanmaz; ödeme sürecinde iyzico'nun güvenli ortamına aktarılır.
        </li>
        <li>
          Abonelik, seçilen döneme (aylık/yıllık) göre peşin tahsil edilir ve ALICI iptal etmediği sürece
          aynı süre için otomatik olarak yenilenir (bkz. Madde 6 ve Ön Bilgilendirme Formu).
        </li>
        <li>
          Ödemenin herhangi bir nedenle yapılamaması veya iptal edilmesi hâlinde Satıcı, hizmeti askıya
          alma veya Sözleşme'yi feshetme hakkını saklı tutar.
        </li>
      </UL>

      <H2>MADDE 5 — İFA VE ERİŞİM</H2>
      <P>
        Ödemenin onaylanmasının ardından hizmet, ALICI'nın hesabına elektronik ortamda ve kural olarak
        anında tanımlanır. İfa süresi, yasal azami otuz (30) günü aşamaz. ALICI, hizmete erişim için
        gerekli internet bağlantısı ve uyumlu cihaz/işletim sistemi koşullarını sağlamakla yükümlüdür.
      </P>

      <H2>MADDE 6 — CAYMA HAKKI VE İSTİSNASI</H2>
      <P>
        ALICI, kural olarak, hizmetin ifasına başlanmasından itibaren {COMPANY.withdrawalDays} (on dört) gün
        içinde hiçbir gerekçe göstermeksizin ve cezai şart ödemeksizin Sözleşme'den cayma hakkına sahiptir.
      </P>
      <P>
        <strong>İstisna:</strong> Mesafeli Sözleşmeler Yönetmeliği'nin 15. maddesi uyarınca; elektronik
        ortamda anında ifa edilen hizmetler ile tüketiciye anında teslim edilen gayrimaddi mallara ilişkin
        sözleşmelerde ve tüketicinin onayı ile ifasına başlanan hizmetlerde cayma hakkı kullanılamaz. Buna
        göre; ALICI'nın açık onayı ile cayma süresi dolmadan yazılım hizmeti/aboneliğinin ifasına
        başlanması hâlinde ALICI cayma hakkını kaybeder. ALICI, siparişi onaylayarak, hizmetin cayma
        süresi içinde ifasına başlanmasını açıkça talep ve kabul ettiğini beyan eder.
      </P>
      <P>
        Cayma hakkının geçerli olduğu hâllerde ALICI, {COMPANY.email} adresine yazılı bildirimde bulunarak
        hakkını kullanabilir; bu durumda tahsil edilen bedel, cayma bildiriminin ulaşmasından itibaren
        on dört (14) gün içinde aynı ödeme aracına iade edilir.
      </P>

      <H2>MADDE 7 — GENEL HÜKÜMLER</H2>
      <UL>
        <li>
          ALICI, hizmeti hukuka ve Kullanım Şartları'na uygun biçimde kullanmayı kabul eder. Yazılım,
          veteriner hekim gözetiminde kullanılan bir klinik destek aracıdır ve hekimin tıbbi karar,
          teşhis ve tedavisinin yerine geçmez.
        </li>
        <li>
          Satıcı; mücbir sebep hâllerinde, hizmet sağlayıcılarından kaynaklanan aksaklıklarda veya ALICI'nın
          koşulları sağlamamasından doğan durumlarda ifadan sorumlu tutulamaz.
        </li>
        <li>
          ALICI'nın kişisel verileri, KVKK Aydınlatma Metni ve Gizlilik Politikası çerçevesinde işlenir.
        </li>
      </UL>

      <H2>MADDE 8 — UYUŞMAZLIKLARIN ÇÖZÜMÜ</H2>
      <P>
        İşbu Sözleşme'den doğabilecek uyuşmazlıklarda, Ticaret Bakanlığı'nca ilan edilen parasal sınırlar
        dâhilinde ALICI'nın yerleşim yerindeki veya işlemin yapıldığı yerdeki Tüketici Hakem Heyetleri;
        bu sınırların üzerindeki uyuşmazlıklarda ise Tüketici Mahkemeleri yetkilidir.
      </P>

      <H2>MADDE 9 — YÜRÜRLÜK</H2>
      <P>
        İşbu Sözleşme, ALICI tarafından elektronik ortamda okunup kabul edilerek siparişin onaylanması ve
        ödemenin tamamlanması ile yürürlüğe girer. Sözleşme'nin bir örneği ALICI'nın erişimine sunulur ve/veya
        e-posta ile iletilir.
      </P>
    </>
  ),

  /* =============== 2) ÖN BİLGİLENDİRME FORMU =============== */
  'on-bilgilendirme': (
    <>
      <P>
        İşbu Ön Bilgilendirme Formu, 6502 sayılı Tüketicinin Korunması Hakkında Kanun ve Mesafeli
        Sözleşmeler Yönetmeliği uyarınca, siparişinizi onaylamadan önce sizi bilgilendirmek amacıyla
        hazırlanmıştır. Siparişin onaylanması, işbu formda yer alan hususların okunup kabul edildiği
        anlamına gelir.
      </P>

      <H2>1. Satıcı / Hizmet Sağlayıcı Kimliği</H2>
      <SellerIdentity />

      <H2>2. Hizmetin Temel Nitelikleri</H2>
      <P>
        {COMPANY.brandName}, veteriner hekim gözetiminde kullanılmak üzere tasarlanmış bir klinik destek
        yazılımıdır. Abonelik; yazılım kullanım lisansını, yapay zekâ analiz/teşhis modüllerini, otomatik
        güncellemeleri ve seçilen seviyeye göre destek hizmetini kapsar. Hizmet dijital (gayrimaddi) olarak
        internet üzerinden ifa edilir; fiziksel teslimat içermez. Hizmetin seviye kapsamı ve güncel
        özellikleri sipariş anında fiyatlandırma sayfasında gösterilir.
      </P>

      <H2>3. Toplam Fiyat ve Ödeme</H2>
      <UL>
        <li>
          Hizmetin, tüm vergiler (KDV) dâhil toplam satış bedeli, sipariş özetinde açıkça belirtilir. Fiyata
          dâhil olan/olmayan tüm kalemler sipariş ekranında gösterilir.
        </li>
        <li>Ödeme, iyzico güvenli ödeme altyapısı üzerinden kredi/banka kartı ile yapılır.</li>
        <li>Abonelik bedeli, seçilen döneme (aylık/yıllık) göre peşin tahsil edilir.</li>
      </UL>

      <H2>4. İfa (Erişim) Şekli ve Süresi</H2>
      <P>
        Hizmet, ödemenin onaylanmasının ardından elektronik ortamda ve kural olarak anında ALICI hesabına
        tanımlanır. Yasal azami ifa süresi otuz (30) gündür.
      </P>

      <H2>5. Cayma Hakkı ve İstisnaları</H2>
      <P>
        Tüketici, kural olarak {COMPANY.withdrawalDays} (on dört) gün içinde gerekçe göstermeksizin cayma
        hakkına sahiptir. Ancak Mesafeli Sözleşmeler Yönetmeliği'nin 15. maddesi gereğince; elektronik
        ortamda anında ifa edilen hizmetler ve tüketiciye anında teslim edilen gayrimaddi mallar ile
        tüketicinin onayıyla ifasına başlanan hizmetlerde cayma hakkı kullanılamaz.
      </P>
      <P>
        Bu kapsamda; abonelik hizmetinin, tüketicinin açık onayı ile cayma süresi içinde ifasına başlanması
        hâlinde cayma hakkı sona erer. Siparişi onaylayan tüketici, hizmetin derhâl ifasına başlanmasını açıkça
        talep ettiğini ve bu hâlde cayma hakkını yitireceğini bildiğini kabul eder.
      </P>

      <H2>6. Otomatik Yenilenen Abonelik Beyanı</H2>
      <P>
        Abonelik, seçilen dönemin (aylık/yıllık) sonunda, tüketici iptal etmediği sürece aynı süre için
        otomatik olarak yenilenir ve kayıtlı ödeme yöntemi üzerinden ilgili dönem bedeli tahsil edilir.
        Tüketici, aboneliğini dilediği zaman hesabı üzerinden veya {COMPANY.email} adresine bildirimle iptal
        edebilir; iptal, içinde bulunulan dönemin sonunda geçerli olur ve sonraki yenileme durdurulur.
      </P>

      <H2>7. Şikâyet ve İtiraz Başvuru Mercii</H2>
      <P>
        Tüketici, Ticaret Bakanlığı'nca belirlenen parasal sınırlar çerçevesinde, yerleşim yerindeki veya
        işlemin yapıldığı yerdeki Tüketici Hakem Heyeti'ne ya da Tüketici Mahkemesi'ne başvurabilir. Talep ve
        şikâyetler ayrıca {COMPANY.email} adresine iletilebilir.
      </P>
    </>
  ),

  /* =============== 3) İPTAL, İADE VE CAYMA HAKKI =============== */
  'iptal-iade': (
    <>
      <P>
        Bu belge; {COMPANY.brandName} aboneliğine ilişkin cayma hakkı, iptal ve iade koşullarını 6502 sayılı
        Kanun ve Mesafeli Sözleşmeler Yönetmeliği çerçevesinde açıklar.
      </P>

      <H2>1. Cayma Hakkı ({COMPANY.withdrawalDays} Gün)</H2>
      <P>
        Tüketici, kural olarak hizmetin ifasına başlandığı tarihten itibaren {COMPANY.withdrawalDays} (on dört)
        gün içinde, gerekçe göstermeksizin ve cezai şart ödemeksizin sözleşmeden cayabilir. Cayma bildirimi
        {' '}{COMPANY.email} adresine yazılı olarak yapılabilir.
      </P>

      <H2>2. Dijital Hizmet İstisnası</H2>
      <P>
        {COMPANY.brandName} aboneliği, elektronik ortamda anında ifa edilen bir dijital (gayrimaddi) hizmettir.
        Mesafeli Sözleşmeler Yönetmeliği m.15 uyarınca; tüketicinin açık onayı ile cayma süresi dolmadan
        hizmetin ifasına başlanması hâlinde cayma hakkı kullanılamaz. Sipariş onayı sırasında tüketici,
        hizmetin derhâl ifasına başlanmasını talep ettiğinde bu istisnayı kabul etmiş sayılır.
      </P>

      <H2>3. Aboneliğin İptali</H2>
      <UL>
        <li>Abonelik, hesap ayarlarınızdan veya {COMPANY.email} adresine bildirimle her zaman iptal edilebilir.</li>
        <li>
          İptal, içinde bulunulan (bedeli tahsil edilmiş) dönemin sonunda geçerli olur; bu dönem sonuna kadar
          hizmete erişim devam eder ve sonraki otomatik yenileme durdurulur.
        </li>
        <li>İptal sonrası, kural olarak, içinde bulunulan dönem için ayrıca geri ödeme yapılmaz (bkz. Madde 4).</li>
      </UL>

      <H2>4. İade Süreci</H2>
      <P>
        Cayma hakkının geçerli biçimde kullanıldığı veya Satıcı'nın uygun bulduğu hâllerde iade, tahsilatın
        yapıldığı ödeme aracına (kredi/banka kartına) yapılır. İade işlemleri iyzico ödeme altyapısı üzerinden
        gerçekleştirilir. İade tutarı, cayma/iade talebinin kabulünden itibaren on dört (14) gün içinde
        başlatılır; tutarın kart hesabına yansıma süresi, ilgili banka/ödeme kuruluşunun işleyişine bağlıdır.
      </P>

      <H2>5. İletişim</H2>
      <P>
        İptal, iade ve cayma talepleriniz için: {COMPANY.email}{COMPANY.phone ? ` — ${COMPANY.phone}` : ""}.
      </P>
    </>
  ),

  /* =============== 4) KVKK AYDINLATMA METNİ =============== */
  kvkk: (
    <>
      <P>
        İşbu Aydınlatma Metni, 6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") m.10 kapsamında,
        veri sorumlusu sıfatıyla kişisel verilerinizin işlenmesine ilişkin olarak sizi bilgilendirmek amacıyla
        hazırlanmıştır.
      </P>

      <H2>1. Veri Sorumlusu</H2>
      <SellerIdentity />

      <H2>2. İşlenen Kişisel Veriler</H2>
      <UL>
        <li>Kimlik verileri: ad-soyad, T.C. kimlik numarası (fatura/ödeme için).</li>
        <li>İletişim verileri: e-posta, telefon, adres.</li>
        <li>Müşteri/işlem verileri: abonelik seviyesi, sipariş ve ödeme kayıtları, fatura bilgileri.</li>
        <li>Hesap verileri: kullanıcı hesabı, oturum ve kimlik doğrulama bilgileri.</li>
        <li>İşlem güvenliği verileri: IP adresi, log kayıtları, çerez verileri.</li>
      </UL>
      <P>
        Not: Klinik/hasta verileri kural olarak kullanıcı cihazında şifreli tutulur; bu tür veriler yalnızca
        hizmetin gerektirdiği ölçüde ve ilgili sözleşme/aydınlatma çerçevesinde işlenir.
      </P>

      <H2>3. İşleme Amaçları</H2>
      <UL>
        <li>Abonelik sözleşmesinin kurulması, ifası ve hizmetin sunulması.</li>
        {/* İndirme artık hesap gerektirdiği için YENİ bir işleme amacı doğdu; yayımlanan metin
            fiili işlemeyi kapsamazsa aydınlatma yükümlülüğü eksik kalır. */}
        <li>Yazılım indirme talebinin karşılanması ve sürüm/güncelleme bildirimlerinin iletilmesi.</li>
        <li>Ödeme, faturalandırma ve muhasebe süreçlerinin yürütülmesi.</li>
        <li>Müşteri destek, talep ve şikâyetlerin yönetimi.</li>
        <li>Hesap güvenliği, dolandırıcılığın önlenmesi ve sistem güvenliği.</li>
        <li>Yasal yükümlülüklerin yerine getirilmesi.</li>
      </UL>

      <H2>4. Hukuki Sebepler (KVKK m.5)</H2>
      <UL>
        <li>Sözleşmenin kurulması/ifası için veri işlemenin gerekli olması.</li>
        <li>Veri sorumlusunun hukuki yükümlülüğünü yerine getirmesi.</li>
        <li>Bir hakkın tesisi, kullanılması veya korunması için zorunlu olması.</li>
        <li>Veri sorumlusunun meşru menfaatleri (temel hak ve özgürlüklere zarar vermemek kaydıyla).</li>
        <li>Gerekli hâllerde açık rızanın alınması.</li>
      </UL>

      <H2>5. Aktarım</H2>
      <P>
        Kişisel verileriniz; hizmetin sunulması amacıyla ödeme kuruluşu (iyzico), altyapı/barındırma hizmet
        sağlayıcısı (Supabase) ve gerektiğinde yetkili kamu kurum ve kuruluşları ile hukuken yetkili özel
        kişilere, KVKK m.8 ve m.9'daki şartlara uygun olarak aktarılabilir.
      </P>

      {/* ⚠️ 2026-08-09 denetimi (Tier 3): metinde YURT DIŞINA AKTARIM başlığı hiç yoktu; oysa
          hesap ve cihaz verileri fiilen yurt dışındaki bir işleyiciye (Supabase) gidiyor ve site
          yurt dışında barındırılıyor (Vercel). Aşağıdaki kalemler koddan ÖLÇÜLEREK yazıldı:
            • Supabase Auth  → e-posta, şifrenin geri döndürülemez özeti, oturum jetonları, kayıt profil alanları
            • devices tablosu (60 sn'de bir heartbeat, servers/sync_worker._publish_device_registry):
              device_id, cihaz adı, tunnel_url, yerel IP, port, eşleştirme kodu, last_seen,
              app_version, launcher_version, base_sha, at_rest_encrypted
            • hasta/seans kayıtları → VARSAYILAN OLARAK GİTMEZ (PEMF_CLOUD_PATIENT_SYNC=0);
              yalnız klinik açıkça açarsa ve o hâlde de PII şifreli gönderilir.
          ⚠️ SAHİBİNE: Supabase proje BÖLGESİ (ör. eu-central-1 / us-east-1) panodan okunup
          aşağıdaki cümleye somut olarak yazılmalıdır; ayrıca m.9 kapsamında hangi mekanizmaya
          (taahhütname / standart sözleşme / açık rıza) dayanıldığı hukuk danışmanıyla
          KESİNLEŞTİRİLMELİDİR. Bu metin fiili durumu bildirir, hukuki nitelemeyi yapmaz. */}
      <H2>5.1. Yurt Dışına Aktarım (KVKK m.9)</H2>
      <P>
        Aşağıdaki veriler, hizmetin teknik olarak sunulabilmesi için <strong>yurt dışında yerleşik</strong>{' '}
        hizmet sağlayıcıların altyapısında işlenmektedir:
      </P>
      <UL>
        <li>
          <strong>Hesap ve kimlik doğrulama verileri</strong> — e-posta adresi, şifrenin geri döndürülemez özeti, oturum
          jetonları, kayıt sırasında verilen ad-soyad/klinik/kurum bilgileri. Alıcı:{' '}
          <strong>Supabase</strong> (kimlik doğrulama ve veritabanı hizmeti).
        </li>
        <li>
          <strong>Cihaz kayıt defteri verileri</strong> — cihaz kimliği ve adı, uzaktan erişim adresi,
          yerel IP adresi ve port, eşleştirme kodu, son görülme zamanı ve kurulu yazılım sürümleri. Bu
          kayıt, mobil uygulamanın kliniğin cihazına bağlanabilmesi ve bir güvenlik güncellemesinin
          hangi cihazlara ulaştığının izlenebilmesi için <strong>yaklaşık 60 saniyede bir</strong>{' '}
          güncellenir. Alıcı: <strong>Supabase</strong>.
        </li>
        <li>
          <strong>Site kullanım ve bağlantı verileri</strong> — IP adresi ve istek kayıtları. Alıcı:{' '}
          <strong>Vercel</strong> (web sitesi barındırma).
        </li>
      </UL>
      <P>
        <strong>Hasta ve seans kayıtları (klinik verisi) yurt dışına aktarılmaz.</strong> Bu veriler
        kliniğin kendi cihazında şifreli olarak tutulur. Yazılım, klinik verisinin buluta
        eşitlenmesini <strong>varsayılan olarak kapalı</strong> tutar; bu ayar yalnızca klinik
        tarafından açıkça etkinleştirilirse devreye girer ve o durumda da kişisel veri alanları
        şifreli olarak gönderilir.
      </P>
      <P>
        Ödeme işlemleri <strong>iyzico</strong> (Türkiye'de yerleşik ödeme kuruluşu) üzerinden yürütülür;
        kart verileri tarafımızca saklanmaz.
      </P>
      <P>
        Yurt dışına aktarım, KVKK m.9'da öngörülen şartlara dayanılarak yapılır. Aktarımın kapsamı,
        alıcıları ve dayanağı hakkında bilgi talebinizi {COMPANY.kvkkEmail} adresine iletebilirsiniz.
      </P>

      <H2>6. Saklama Süresi</H2>
      <P>
        Kişisel verileriniz, işleme amacının gerektirdiği süre ile ilgili mevzuatta öngörülen (ör. ticari ve
        vergisel kayıtlar için yasal) süreler boyunca saklanır; sürelerin sonunda silinir, yok edilir veya
        anonim hâle getirilir.
      </P>
      {/* ⚠️ 2026-08-09 denetimi: metin "öngörülen süreler" diyordu ama YAZILIM somut bir süre
          uyguluyordu (varsayılan 365 gün) ve bunu operatöre hiçbir yerde söylemiyordu. Klinik
          366. günde hasta adı yerine [REDACTED] görüp sebebini bulamıyordu. Uygulanan kuralın
          hukuki metinde de somut olarak yazması gerekir. */}
      <P>
        <strong>Klinik cihazındaki tedavi kayıtları için uygulanan somut süre:</strong> seans kayıtlarındaki
        hasta ve operatör adları ile serbest metin notlar, <strong>varsayılan olarak 365 gün</strong> sonra
        geri dönüşsüz biçimde maskelenir: kayıtta adın yerinde <code>[REDACTED]</code> ibaresi görünür.
        Tedavi verileri (uygulanan doz, süre, frekans, sensör ölçümleri) maskelenmez ve klinik
        geçmişinde kalır.
      </P>
      <P>
        Bu süre klinik tarafından uygulama içinden değiştirilebilir (Ayarlar → Veri Saklama Süresi) veya
        tamamen kapatılabilir; tıbbi ve hukuki saklama yükümlülüğü ülkeye ve olaya göre değiştiğinden karar
        veri sorumlusu kliniğe aittir. Maskeleme, klinik <strong>açıkça onaylamadan başlatılmaz</strong>.
      </P>

      <H2>7. İlgili Kişinin Hakları (KVKK m.11)</H2>
      <UL>
        <li>Kişisel verinizin işlenip işlenmediğini öğrenme ve işlenmişse buna ilişkin bilgi talep etme.</li>
        <li>İşleme amacını ve amacına uygun kullanılıp kullanılmadığını öğrenme.</li>
        <li>Yurt içinde/yurt dışında aktarıldığı üçüncü kişileri bilme.</li>
        <li>Eksik/yanlış işlenmişse düzeltilmesini isteme.</li>
        <li>KVKK'da öngörülen şartlarla silinmesini/yok edilmesini isteme.</li>
        <li>Düzeltme/silme işlemlerinin aktarıldığı üçüncü kişilere bildirilmesini isteme.</li>
        <li>Otomatik sistemlerle analiz sonucu aleyhe bir sonucun ortaya çıkmasına itiraz etme.</li>
        <li>Kanuna aykırı işleme nedeniyle zarara uğraması hâlinde zararın giderilmesini talep etme.</li>
      </UL>

      <H2>8. Başvuru</H2>
      <P>
        KVKK m.11 kapsamındaki taleplerinizi, kimliğinizi tevsik eden bilgilerle birlikte {COMPANY.kvkkEmail}
        {' '}adresine iletebilir veya {COMPANY.address}, {COMPANY.city} adresine yazılı olarak başvurabilirsiniz.
        Başvurularınız, KVKK'da öngörülen süreler içinde sonuçlandırılır.
      </P>
    </>
  ),

  /* =============== 5) GİZLİLİK POLİTİKASI =============== */
  gizlilik: (
    <>
      <P>
        {COMPANY.brandName} olarak gizliliğinize önem veriyoruz. İşbu Gizlilik Politikası, internet sitemiz ve
        hizmetlerimiz aracılığıyla toplanan bilgilerin nasıl işlendiğini ve korunduğunu açıklar. Kişisel
        verilere ilişkin ayrıntılı bilgilendirme için KVKK Aydınlatma Metni'ni de inceleyiniz.
      </P>

      <H2>1. Toplanan Veriler</H2>
      <UL>
        <li>Hesap ve iletişim bilgileri (ad-soyad, e-posta, telefon).</li>
        <li>Sipariş, abonelik ve fatura/ödeme bilgileri.</li>
        <li>Oturum ve kimlik doğrulama verileri.</li>
        <li>Teknik veriler: IP adresi, cihaz/tarayıcı bilgisi, log ve çerez verileri.</li>
      </UL>

      <H2>2. Verilerin Kullanımı</H2>
      <UL>
        <li>Hizmetin sunulması, hesabınızın yönetimi ve aboneliğinizin işletilmesi.</li>
        {/* Kayıtsız indirme kaldırıldı → indirme amacı burada da açıkça yazılmalı (KVKK metniyle tutarlı). */}
        <li>Yazılım indirme talebinizin karşılanması ve sürüm/güncelleme bildirimlerinin iletilmesi.</li>
        <li>Ödeme ve faturalandırma işlemlerinin gerçekleştirilmesi.</li>
        <li>Destek taleplerinin karşılanması ve sizinle iletişim kurulması.</li>
        <li>Güvenlik, dolandırıcılığın önlenmesi ve hizmet kalitesinin iyileştirilmesi.</li>
      </UL>

      <H2>3. Üçüncü Taraf Hizmet Sağlayıcılar</H2>
      <P>
        Hizmetin sunulabilmesi için sınırlı veri, aşağıdaki güvenilir hizmet sağlayıcılarla paylaşılır:
      </P>
      <UL>
        <li>
          <strong>iyzico</strong> — ödeme işlemlerinin güvenli biçimde gerçekleştirilmesi. Kart bilgileri
          tarafımızca saklanmaz; doğrudan ödeme kuruluşunun güvenli ortamında işlenir.
        </li>
        <li>
          <strong>Supabase</strong> — kimlik doğrulama, hesap ve uygulama verilerinin barındırılması/altyapı hizmeti.
        </li>
      </UL>
      <P>
        Bu sağlayıcılar, verileri yalnızca hizmetin gerektirdiği amaçla ve kendi gizlilik/güvenlik
        yükümlülükleri çerçevesinde işler.
      </P>

      <H2>4. Veri Güvenliği</H2>
      <P>
        Kişisel verilerinizi yetkisiz erişime, kayba ve ifşaya karşı korumak için idari ve teknik tedbirler
        (şifreleme, erişim kontrolleri, güvenli iletişim vb.) uygulanır. Klinik/hasta verileri kural olarak
        kullanıcı cihazında şifreli tutulur.
      </P>

      <H2>5. Çerezler</H2>
      <P>
        İnternet sitemizde çerezler kullanılmaktadır. Ayrıntılar için Çerez Politikası'nı inceleyebilirsiniz.
      </P>

      <H2>6. Haklarınız ve İletişim</H2>
      <P>
        KVKK kapsamındaki haklarınızı kullanmak veya gizlilikle ilgili taleplerinizi iletmek için
        {' '}{COMPANY.kvkkEmail} ya da {COMPANY.email} adresine başvurabilirsiniz.
      </P>
    </>
  ),

  /* =============== 6) ÇEREZ POLİTİKASI =============== */
  'cerez-politikasi': (
    <>
      <P>
        Bu Çerez Politikası, {COMPANY.brandName} internet sitesinde kullanılan çerezleri (cookies) ve benzer
        teknolojileri, bunların amaçlarını ve nasıl yönetebileceğinizi açıklar.
      </P>

      <H2>1. Çerez Nedir?</H2>
      <P>
        Çerezler, ziyaret ettiğiniz internet siteleri tarafından tarayıcınıza kaydedilen küçük metin
        dosyalarıdır. Sitenin çalışmasını sağlamak, tercihlerinizi hatırlamak ve deneyimi iyileştirmek için kullanılır.
      </P>

      <H2>2. Kullanılan Çerez Türleri</H2>
      <UL>
        <li>
          <strong>Zorunlu çerezler:</strong> Sitenin temel işlevleri, güvenlik ve oturum yönetimi için gereklidir.
          Bu çerezler olmadan site düzgün çalışmaz. Oturum ve kimlik doğrulama, Supabase altyapısı üzerinden yönetilir.
        </li>
        <li>
          <strong>İşlevsel çerezler:</strong> Dil, tema gibi tercihlerinizi hatırlayarak deneyiminizi kişiselleştirir.
        </li>
        <li>
          <strong>Analitik çerezler:</strong> Ziyaretçi etkileşimini anonim/istatistiksel olarak ölçerek sitenin
          performansını ve içeriğini iyileştirmemize yardımcı olur. (Kullanıldığında.)
        </li>
      </UL>

      <H2>3. Oturum Yönetimi</H2>
      <P>
        Hesabınıza giriş yaptığınızda, oturumunuzun güvenli biçimde sürdürülebilmesi için kimlik doğrulama
        çerezleri/depolama kullanılır. Bu, her sayfada yeniden giriş yapmanızı önleyen zorunlu bir işlevdir.
      </P>

      <H2>4. Çerezleri Yönetme</H2>
      <P>
        Tarayıcınızın ayarlarından çerezleri silebilir, engelleyebilir veya çerez yerleştirilmeden önce
        uyarılmayı seçebilirsiniz. Zorunlu çerezlerin engellenmesi, sitenin bazı bölümlerinin (ör. giriş/oturum)
        düzgün çalışmamasına neden olabilir. Çoğu tarayıcıda çerez yönetimi, "Ayarlar &gt; Gizlilik/Güvenlik"
        bölümünden yapılabilir.
      </P>

      <H2>5. Güncellemeler ve İletişim</H2>
      <P>
        Bu politika zaman zaman güncellenebilir. Sorularınız için: {COMPANY.email}.
      </P>
    </>
  ),

  /* =============== 7) KULLANIM ŞARTLARI =============== */
  'kullanim-sartlari': (
    <>
      <P>
        İşbu Kullanım Şartları (Üyelik Sözleşmesi), {COMPANY.brandName} internet sitesi, masaüstü uygulaması ve
        yazılım hizmetlerinin kullanımına ilişkin koşulları düzenler. Hizmeti kullanarak bu şartları kabul
        etmiş sayılırsınız.
      </P>

      <H2>1. Hesap ve Üyelik</H2>
      <UL>
        <li>Hizmetten yararlanmak için doğru ve güncel bilgilerle bir hesap oluşturmanız gerekir.</li>
        <li>Hesap güvenliğinden (şifre gizliliği dâhil) ve hesabınız üzerinden yapılan işlemlerden siz sorumlusunuz.</li>
        <li>Hesabınızın yetkisiz kullanıldığını fark ederseniz derhâl bize bildirmelisiniz.</li>
      </UL>

      <H2>2. Uygun Kullanım</H2>
      <UL>
        <li>Hizmeti yalnızca hukuka uygun amaçlarla ve bu şartlara uygun olarak kullanabilirsiniz.</li>
        <li>Yazılıma tersine mühendislik uygulanması, izinsiz çoğaltılması, dağıtılması veya lisans kapsamı dışında kullanılması yasaktır.</li>
        <li>Sistemin güvenliğini tehlikeye atacak, hizmeti aksatacak veya üçüncü kişilerin haklarını ihlal edecek davranışlardan kaçınmalısınız.</li>
      </UL>

      <H2>3. Fikri Mülkiyet</H2>
      <P>
        {COMPANY.brandName} yazılımı, yapay zekâ modelleri, arayüz, marka, logo ve tüm içerik; Satıcı'ya veya
        lisans verenlerine ait olup fikri mülkiyet mevzuatı ile korunmaktadır. Abonelik size, hizmeti kişisel/
        kurumsal kullanımınız için sınırlı, münhasır olmayan ve devredilemez bir kullanım hakkı tanır; mülkiyet
        veya başkaca bir hak devri anlamına gelmez.
      </P>

      <H2>4. Sorumluluğun Sınırlandırılması ve Tıbbi Uyarı</H2>
      <div className="mb-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm leading-relaxed text-amber-200">
        <strong>Tıbbi/veteriner sorumluluk uyarısı:</strong> {COMPANY.brandName}, veteriner hekim gözetiminde
        kullanılmak üzere tasarlanmış bir klinik destek yazılımıdır. Akıllı teşhis ve yapay zekâ analiz
        çıktıları bilgilendirme amaçlıdır; veteriner hekimin tıbbi teşhis, karar ve tedavisinin yerine geçmez.
        Otonom seans (AI Pro) özellikleri de dâhil olmak üzere tüm klinik kararlar ve uygulamalar, ilgili
        veteriner hekimin gözetimi ve sorumluluğu altındadır.
      </div>
      <P>
        Hizmet "olduğu gibi" ve "mevcut hâliyle" sunulur. Yürürlükteki mevzuatın izin verdiği azami ölçüde;
        Satıcı, hizmetin kesintisiz veya hatasız olacağını garanti etmez ve hizmetin kullanımından doğan
        dolaylı zararlardan sorumlu tutulamaz. Bu madde, tüketici mevzuatından doğan haklarınızı ortadan kaldırmaz.
      </P>

      <H2>5. Ücretlendirme ve Abonelik</H2>
      <P>
        Ücretli seviyelere ilişkin bedel, ödeme, otomatik yenileme, iptal ve iade koşulları; Mesafeli Satış
        Sözleşmesi, Ön Bilgilendirme Formu ve İptal/İade/Cayma belgelerinde düzenlenmiştir.
      </P>

      <H2>6. Fesih ve Askıya Alma</H2>
      <P>
        İşbu şartların ihlali hâlinde Satıcı, hesabınızı önceden bildirimde bulunarak veya ihlalin niteliğine
        göre derhâl askıya alma ya da hizmeti sonlandırma hakkını saklı tutar. Aboneliğinizi dilediğiniz zaman
        iptal edebilirsiniz.
      </P>

      <H2>7. Değişiklikler</H2>
      <P>
        Satıcı, bu şartları güncelleyebilir. Önemli değişiklikler uygun yollarla duyurulur; güncel sürüm bu
        sayfada yayımlandığı andan itibaren geçerli olur.
      </P>

      <H2>8. Uygulanacak Hukuk ve Yetki</H2>
      <P>
        İşbu şartlara Türkiye Cumhuriyeti hukuku uygulanır. Uyuşmazlıklarda; tüketici işlemleri bakımından
        yetkili Tüketici Hakem Heyetleri ve Tüketici Mahkemeleri, diğer hâllerde {COMPANY.city} mahkemeleri ve
        icra daireleri yetkilidir.
      </P>

      <H2>9. İletişim</H2>
      <P>
        Sorularınız için: {COMPANY.legalName} — {COMPANY.email}{COMPANY.phone ? ` — ${COMPANY.phone}` : ""}.
      </P>
    </>
  ),
}

/* ------------------------------------------------------------------
   Ana bileşen — route'a göre ilgili belgeyi gösterir.
   ------------------------------------------------------------------ */
export function LegalPage() {
  const location = useLocation()
  const slug = location.pathname.replace(/^\//, '')
  const doc = LEGAL_DOCS.find((d) => d.slug === slug)

  // Bilinmeyen slug → "belge bulunamadı" + geçerli belgelere bağlantılar.
  if (!doc) {
    return (
      <section className="mx-auto max-w-3xl px-5 py-20 sm:px-6">
        <span className="chip">Yasal</span>
        <h1 className="mt-5 text-3xl font-extrabold sm:text-4xl">Belge bulunamadı</h1>
        <p className="mt-4 text-muted">
          Aradığınız yasal belge mevcut değil. Aşağıdaki belgelerden birini seçebilirsiniz:
        </p>
        <ul className="mt-6 space-y-2">
          {LEGAL_DOCS.map((d) => (
            <li key={d.slug}>
              <Link to={`/${d.slug}`} className="text-primary hover:underline">
                {d.title}
              </Link>
            </li>
          ))}
        </ul>
        <Link to="/" className="btn-ghost mt-8">
          Ana sayfaya dön
        </Link>
      </section>
    )
  }

  return (
    <article className="mx-auto max-w-3xl px-5 py-14 sm:px-6 sm:py-16">
      <Link to="/" className="text-sm text-muted hover:text-fg">
        ← Ana sayfa
      </Link>

      <h1 className="mt-4 text-3xl font-extrabold sm:text-4xl">{doc.title}</h1>

      {/* İÇ NOT KALDIRILDI (metin denetimi, 2026-08-20): burada "bu metin bir şablondur; yayına
          almadan önce hukuk danışmanınca gözden geçirilmelidir" uyarısı MÜŞTERİYE gösteriliyordu.
          Satın alma öncesi sözleşme sayfasında belgeyi taslak ilan etmek güveni doğrudan zedeler;
          hazırlık notu yayına değil, geliştirme akışına aittir. Kilit: src/__tests__/metin-guveni.test.ts */}

      <p className="mt-5 text-xs text-muted">Son güncelleme: {COMPANY.updated}</p>

      <div className="mt-6">{DOCS[doc.slug]}</div>

      {/* İlgili belgeler */}
      <nav className="mt-12 border-t border-border/60 pt-6">
        <h2 className="mb-3 text-sm font-semibold text-fg">İlgili yasal belgeler</h2>
        <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
          {LEGAL_DOCS.filter((d) => d.slug !== doc.slug).map((d) => (
            <li key={d.slug}>
              <Link to={`/${d.slug}`} className="hover:text-fg">
                {d.title}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </article>
  )
}

export default LegalPage
