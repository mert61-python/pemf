/**
 * I18N-P1 · site-12d-ticari — fiyatlandırma sayfası (Pricing), ödeme sayfası (Odeme), plan fiyat gösterimi (planFiyat), sayı / para biçimi
 * (para.ts) ve bağlantılı metin yardımcısı (metin.tsx). GERÇEK bileşenler sunucu tarafı çizilir; oturum bağlamları sahtelenir.
 * Mod: ücretsiz dönem (FREE_MODE=true — üretim ayarı).
 *  · ALTIN: göç ÖNCESİ kaynaktan Türkçe değerler (fiyat.* · odeme.* — 73 anahtar; her biri HEAD kaynağında birebir doğrulandı).
 *  · Çizim: Türkçe (bayrak kapalı) eski dizgilerle TAM metin düğümü eşitliği; bayrak AÇIK + İngilizce → her satırın İngilizcesi, Türkçesi KALMAZ.
 *  · Para: Türkçe `₺1.990` (tr-TR), İngilizce `₺1,990` (en-US); sayılar iki dilde aynı rakamlardır.
 *  · API / istemci hata dizgileri (api/*.ts, lib/checkout.ts) gösterilmez, `odemeHatasiTurkce` ile SINIFLANIR → iki dilde aynı sınıf.
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

const oturum = vi.hoisted(() => ({ session: null as unknown, email: null as string | null }))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    session: oturum.session,
    email: oturum.email,
    ready: true,
    loading: false,
    signOut: () => {},
    signIn: async () => ({}),
    signUp: async () => ({}),
    resetPassword: async () => ({}),
  }),
  AuthProvider: ({ children }: { children: unknown }) => children,
}))
vi.mock('../../context/AuthModal', () => ({
  useAuthModal: () => ({ requireAuth: () => {} }),
  AuthModalProvider: ({ children }: { children: unknown }) => children,
}))

const i18nMod = await import('../index')
const dilMod = await import('../dil')
const { createElement } = await import('react')
const { renderToString } = await import('react-dom/server')
const { MemoryRouter } = await import('react-router-dom')
const Pricing = (await import('../../pages/Pricing')).default
const Odeme = (await import('../../pages/Odeme')).default
const { planFiyatGorunumu, planKisaFiyat } = await import('../../lib/planFiyat')
const { sayi, tl } = await import('../../lib/para')
const { baglantiliMetin } = await import('../../lib/metin')
const { odemeHatasiTurkce } = await import('../../lib/authHatalari')
const { ADDONS, COMPANY, FREE_MODE, PLANS, RESEARCH_ADDON } = await import('../../config')

/** Altın tablo: anahtar → göç ÖNCESİ Türkçe değer. */
const ALTIN: Record<string, string> = {
  "fiyat.arastirmaEkle": "Araştırma profili ekle ",
  "fiyat.aylik": "Aylık",
  "fiyat.baslik": "Kliniğinize göre plan",
  "fiyat.donemYillik": "{{donem}} · yıllık {{tutar}}",
  "fiyat.ekOzellikler": "Ek özellikler",
  "fiyat.eklentiAciklama": "Uygulama içinden tek tıkla açarsınız; ücreti aboneliğinize eklenir.",
  "fiyat.eklentiler": "Eklentiler",
  "fiyat.giris1": "Planınız, ayda kaç yapay zekâ analizi yapabileceğinizi belirler:",
  "fiyat.giris2": "her analiz 1 jeton harcar",
  "fiyat.giris3": "; jetonunuz biterse ek paket alabilir ya da hiç aylık ücret ödemeden ",
  "fiyat.giris4": "kullandıkça ödeyebilirsiniz",
  "fiyat.giris5": ". Hangi yapay zekâ modellerinin ineceğini ise kurulumda seçtiğiniz profiller belirler.",
  "fiyat.ikiAyUcretsiz": "2 ay ücretsiz",
  "fiyat.iletisim": "İletişime Geçin",
  "fiyat.karsilastirmaAciklama": "Her kart tek bir özelliği tüm planlarda birlikte gösterir; aynı değeri veren planlar tek satırda birleşir, böylece farklar öne çıkar.",
  "fiyat.karsilastirmaBaslik": "Plan karşılaştırması",
  "fiyat.kdv": "Fiyatlara KDV dâhildir; ayrıca ücret eklenmez.",
  "fiyat.konuKurumsal": "Kurumsal teklif talebi",
  "fiyat.konuOdemeSorunu": "Ödeme sorunu",
  "fiyat.neKurulacak": "Ne kurulacağını siz seçin",
  "fiyat.odemeAlindi": "✓ Ödemeniz alındı, aboneliğiniz başladı. PEMF Vet’i indirip aynı hesapla giriş yapın.",
  "fiyat.odemeSorunu": "Ödeme sırasında bir sorun oluştu. Yukarıdan tekrar deneyebilir ya da {{baglanti}} adresinden bize ulaşabilirsiniz.",
  "fiyat.odemeTamamlanmadi": "Ödeme tamamlanmadı. Dilerseniz yukarıdan planınızı yeniden seçebilirsiniz.",
  "fiyat.profilAciklama": "Yalnız seçtiğiniz profillerin modelleri iner — evcil hayvan sahibi, ağır araştırma modellerini boşuna indirmez. Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir.",
  "fiyat.suAnUcretsiz": "Şu an ücretsiz",
  "fiyat.tarifeNotu": "Aşağıdaki tutarlar test sonrası tarifedir; şu an tahsil edilmez.",
  "fiyat.testBandi1": "Test aşaması: tüm planlar şu an ",
  "fiyat.testBandi2": "ücretsiz",
  "fiyat.testBandi3": ". Aşağıdaki planlardan hangisini seçerseniz seçin doğrudan indirmeye gidersiniz; kart bilgisi istenmez, ödeme alınmaz.",
  "fiyat.testSonrasiAy": "test sonrası {{tutar}}/ay",
  "fiyat.tlAy": "{{tutar}}/ay",
  "fiyat.tumPlanlardaVar": "Tüm planlarda var",
  "fiyat.ucretsizDene": "14 gün ücretsiz dene",
  "fiyat.var": "Var",
  "fiyat.yillik": "Yıllık",
  "fiyat.zincir": "Zincir klinik veya kurum musunuz?",
  "fiyat.zincirAciklama": "Sınırsız cihaz ve şube, kendi sistemlerinizle bütünleşme, yerinde kurulum ve garantili destek için özel fiyat.",
  "odeme.abonelik": " Abonelik",
  "odeme.ad": "Ad",
  "odeme.adres": "Adres",
  "odeme.arastirmaEklendi": "Araştırma modülü eklendi",
  "odeme.ay": "ay",
  "odeme.aylik": "aylık",
  "odeme.aylikEsdeger": "Aylık eşdeğeri",
  "odeme.aylikOdeme": "Aylık ödeme",
  "odeme.baslatilamadi": "Ödeme başlatılamadı. Lütfen tekrar deneyin.",
  "odeme.bugunTahsil": "Bugün tahsil edilecek",
  "odeme.faturaAciklama": "Bu bilgiler fatura düzenlemek ve ödemeyi güvenli şekilde almak için gerekiyor; TC Kimlik No, vergi mevzuatı gereği fatura bilgisi olarak isteniyor. Kart bilgilerinizi biz görmeyiz — bir sonraki adımda iyzico’nun güvenli formuna girersiniz.",
  "odeme.faturaBilgileri": "Fatura bilgileri",
  "odeme.fiyatlandirmayaDon": "Fiyatlandırmaya dön",
  "odeme.formAciliyor": "Ödeme formu birkaç saniye içinde aşağıda açılır (iyzico güvenli ödeme).",
  "odeme.formunaBakin": "'na bakabilirsiniz.",
  "odeme.girisYapin": "Devam etmek için giriş yapın.",
  "odeme.guvenliOdeme": "Güvenli ödeme",
  "odeme.hazirlaniyor": "Hazırlanıyor…",
  "odeme.indir": "PEMF Vet'i İndir",
  "odeme.istediginizZaman": "Aboneliğinizi istediğiniz zaman hesabınızdan iptal edebilirsiniz.",
  "odeme.odemeyeGec": "Ödemeye geç",
  "odeme.onay": "{{onBilgi}}'nu ve {{satis}}'ni okudum, onaylıyorum.",
  "odeme.onayGerekli": "Devam etmek için Ön Bilgilendirme Formu ve Mesafeli Satış Sözleşmesi’ni onaylayın.",
  "odeme.otoYenileme": "Otomatik yenilenen abonelik:",
  "odeme.otoYenilemeGovde": "{{tutar}} tutarındaki {{donem}} ödeme, siz iptal edene kadar her dönem sonunda otomatik tahsil edilir. Gösterilen tutar KDV dâhil toplam bedeldir; başka bir ücret eklenmez. Ayrıntılar için",
  "odeme.planYok": "Bu bağlantıdaki plan bulunamadı. Fiyatlandırma sayfasından bir plan seçebilirsiniz.",
  "odeme.planlar": "← Planlar",
  "odeme.posta": "Posta kodu (isteğe bağlı)",
  "odeme.soyad": "Soyad",
  "odeme.tc": "TC Kimlik No",
  "odeme.telefon": "Telefon (+90...)",
  "odeme.ucretsizAciklama": "Tüm kurulum profilleri şimdilik ücretsiz kullanılabiliyor; ödeme alınmıyor.",
  "odeme.ucretsizBaslik": "Şu anda tüm planlar ücretsiz",
  "odeme.yil": "yıl",
  "odeme.yillik": "yıllık",
  "odeme.yillikOdeme": "Yıllık ödeme (2 ay bedava)",
}

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/
const yerTutucu = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort()
const sayilar = (s: string) => (s.match(/\d[\d.,]*/g) ?? []).map((x) => x.replace(/[.,]+$/, '').replace(/[.,]/g, '')).sort()

const temizle = (h: string) => h.replace(/<!-- -->/g, '')
const coz = (s: string) => s.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
/** Çizilen HTML'in React `<!-- -->` ayracıyla ayrılmış HAM metin düğümleri + öznitelik değerleri (TAM eşleşme; `~` önek = ayraçsız alt dizgi, `^` önek = HAM alt dizgi [düğüm sınırları dahil]). */
const dugumler = (h: string): Set<string> => {
  const s = new Set<string>(h.split(/<[^>]*>/).map(coz))
  for (const m of h.matchAll(/="([^"]*)"/g)) s.add(coz(m[1]))
  return s
}
const var_ = (h: string, d: Set<string>, s: string) =>
  s.startsWith('~') ? coz(temizle(h)).includes(s.slice(1)) : s.startsWith('^') ? coz(h).includes(s.slice(1)) : d.has(s)
const ciz = (bilesen: unknown, konum = '/') =>
  renderToString(createElement(MemoryRouter, { initialEntries: [konum] }, createElement(bilesen as never)))

type Cift = [tr: string, en: string]
/** Aynı Türkçe dizgi başka (göçmemiş) kaynaktan da çizilir: yok (config.ts 12c'de göçtü) — küme boş kalır. */
const BASKA_KAYNAK = new Set<string>([])

afterEach(async () => {
  oturum.session = null
  oturum.email = null
  dilMod.__bayrakTestiAyarla(null)
  await i18nMod.dilSec('tr')
})

// ───────── Pricing ─────────
const planKartlari = (yillik: boolean): Cift[] => {
  const c: Cift[] = []
  for (const p of PLANS) {
    const g = planFiyatGorunumu(p, yillik)
    c.push([p.name, p.name], [p.desc, p.desc], [p.jetonHakki, p.jetonHakki], [p.cta, p.cta], [g.buyuk, g.buyuk], [g.kucuk, g.kucuk])
  }
  return c
}
const fiyatCiftleri = (): Cift[] => [
  ['Kliniğinize göre plan', 'A plan for your clinic'],
  ['Planınız, ayda kaç yapay zekâ analizi yapabileceğinizi belirler:', 'Your plan sets how many AI analyses you can run each month:'],
  ['her analiz 1 jeton harcar', 'each analysis uses 1 credit'],
  ['; jetonunuz biterse ek paket alabilir ya da hiç aylık ücret ödemeden ', '; if your credits run out you can buy an extra pack or, without paying any monthly fee, '],
  ['kullandıkça ödeyebilirsiniz', 'pay as you go'],
  ['. Hangi yapay zekâ modellerinin ineceğini ise kurulumda seçtiğiniz profiller belirler.', '. Which AI models are downloaded is determined by the profiles you select during installation.'],
  ['Aylık', 'Monthly'],
  ['Yıllık', 'Yearly'],
  ['2 ay ücretsiz', '2 months free'],
  ['Fiyatlara KDV dâhildir; ayrıca ücret eklenmez.', 'Prices include VAT; no additional fees are added.'],
  ['Araştırma profili ekle ', 'Add the Research profile '],
  ['Fiyatlandırma', 'Pricing'],
  ['^Araştırma profili ekle <span class="font-medium text-fg">+₺390/ay</span>',
   '^Add the Research profile <span class="font-medium text-fg">+₺390/mo</span>'],
  ['Var', 'Yes'],
  ['Plan karşılaştırması', 'Plan comparison'],
  ['Her kart tek bir özelliği tüm planlarda birlikte gösterir; aynı değeri veren planlar tek satırda birleşir, böylece farklar öne çıkar.', 'Each card shows a single feature across all plans; plans that give the same value are merged into one row, so the differences stand out.'],
  ['Kurulum profilleri', 'Installation profiles'],
  ['Ne kurulacağını siz seçin', 'You choose what gets installed'],
  ['Yalnız seçtiğiniz profillerin modelleri iner — evcil hayvan sahibi, ağır araştırma modellerini boşuna indirmez. Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir.',
   'Only the models of the profiles you select are downloaded — a pet owner does not download the heavy research models for nothing. The Pet Owner and Veterinarian profiles are included in your plan.'],
  ['Eklentiler', 'Add-ons'],
  ['Ek özellikler', 'Extra features'],
  ['Uygulama içinden tek tıkla açarsınız; ücreti aboneliğinize eklenir.', 'You enable them in the app with one click; the fee is added to your subscription.'],
  ['Zincir klinik veya kurum musunuz?', 'Are you a chain clinic or an institution?'],
  ['Sınırsız cihaz ve şube, kendi sistemlerinizle bütünleşme, yerinde kurulum ve garantili destek için özel fiyat.', 'Special pricing for unlimited devices and branches, integration with your own systems, on-site installation and guaranteed support.'],
  ['İletişime Geçin', 'Contact us'],
  ['14 gün ücretsiz dene', 'Try free for 14 days'],
  ['~subject=Kurumsal%20teklif%20talebi', '~subject=Enterprise%20quote%20request'],
  ...(FREE_MODE
    ? ([
        ['Test aşaması: tüm planlar şu an ', 'Test phase: all plans are '],
        ['ücretsiz', 'free'],
        ['. Aşağıdaki planlardan hangisini seçerseniz seçin doğrudan indirmeye gidersiniz; kart bilgisi istenmez, ödeme alınmaz.', ' right now. Whichever of the plans below you choose, you go straight to the download; no card details are asked for and no payment is taken.'],
        ['Aşağıdaki tutarlar test sonrası tarifedir; şu an tahsil edilmez.', 'The amounts below are the post-test pricing; they are not charged right now.'],
        ['Şu an ücretsiz', 'Free right now'],
      ] as Cift[])
    : []),
  ['Tüm planlarda var', 'In all plans'],
]
const ciftlerAraci = (c: Cift[]) => c

const SAYFALAR: [ad: string, konum: string, cizici: (k: string) => string, ciftler: () => Cift[]][] = [
  ['Pricing', '/pricing', (k) => ciz(Pricing, k), () => ciftlerAraci([...fiyatCiftleri(), ...planKartlari(true)])],
  [
    'Pricing · ödeme başarılı', '/pricing?checkout=success', (k) => ciz(Pricing, k),
    () => [['✓ Ödemeniz alındı, aboneliğiniz başladı. PEMF Vet’i indirip aynı hesapla giriş yapın.', '✓ Your payment was received and your subscription has started. Download PEMF Vet and sign in with the same account.']],
  ],
  [
    'Pricing · ödeme tamamlanmadı', '/pricing?checkout=incomplete', (k) => ciz(Pricing, k),
    () => [['Ödeme tamamlanmadı. Dilerseniz yukarıdan planınızı yeniden seçebilirsiniz.', 'The payment was not completed. If you wish, you can choose your plan again above.']],
  ],
  [
    'Pricing · ödeme hatası', '/pricing?checkout=error', (k) => ciz(Pricing, k),
    () => [
      ['Ödeme sırasında bir sorun oluştu. Yukarıdan tekrar deneyebilir ya da ', 'A problem occurred during payment. You can try again above or contact us at '],
      [' adresinden bize ulaşabilirsiniz.', '.'],
      ['~subject=%C3%96deme%20sorunu', '~subject=Payment%20issue'],
    ],
  ],
]
if (FREE_MODE) {
  SAYFALAR.push([
    'Odeme (ücretsiz dönem)', '/odeme?tier=pro', (k) => ciz(Odeme, k),
    () => [
      ['Şu anda tüm planlar ücretsiz', 'All plans are free right now'],
      ['Tüm kurulum profilleri şimdilik ücretsiz kullanılabiliyor; ödeme alınmıyor.', 'All installation profiles are free to use for now; no payment is taken.'],
      ["PEMF Vet'i İndir", 'Download PEMF Vet'],
    ],
  ])
} else {
  const ortak: Cift[] = [
    [' Abonelik', ' Subscription'],
    ['Bugün tahsil edilecek', 'Charged today'],
    ['Otomatik yenilenen abonelik:', 'Auto-renewing subscription:'],
    ['Fatura bilgileri', 'Billing details'],
    ['Bu bilgiler fatura düzenlemek ve ödemeyi güvenli şekilde almak için gerekiyor; TC Kimlik No, vergi mevzuatı gereği fatura bilgisi olarak isteniyor. Kart bilgilerinizi biz görmeyiz — bir sonraki adımda iyzico’nun güvenli formuna girersiniz.',
     'These details are needed to issue an invoice and to take the payment securely; the Turkish ID number (TC Kimlik No) is requested as invoice information under tax legislation. We do not see your card details — you will enter them in iyzico’s secure form in the next step.'],
    ['Ad', 'First name'], ['Soyad', 'Last name'], ['TC Kimlik No', 'Turkish ID number (TC Kimlik No)'], ['Telefon (+90...)', 'Phone (+90...)'],
    ['Şehir', 'City'], ['Adres', 'Address'], ['Posta kodu (isteğe bağlı)', 'Postal code (optional)'],
    ['Devam etmek için giriş yapın.', 'Sign in to continue.'],
    ['Ön Bilgilendirme Formu', 'Pre-Contract Information Form'],
    ["'nu ve ", ' and the '],
    ['Mesafeli Satış Sözleşmesi', 'Distance Sales Agreement'],
    ["'ni okudum, onaylıyorum.", '.'],
    ['Ödemeye geç', 'Proceed to payment'],
    ['Aboneliğinizi istediğiniz zaman hesabınızdan iptal edebilirsiniz.', 'You can cancel your subscription from your account at any time.'],
    ["'na bakabilirsiniz.", '.'],
    ['← Planlar', '← Plans'],
  ]
  SAYFALAR.push(
    [
      'Odeme · Pro yıllık + araştırma', '/odeme?tier=pro&yearly=1&research=1', (k) => ciz(Odeme, k),
      () => [
        ...ortak,
        ['Yıllık ödeme (2 ay bedava)', 'Annual payment (2 months free)'],
        ['Araştırma modülü eklendi', 'Research module added'],
        [tl(PLANS[2].yearly! + RESEARCH_ADDON.yearly), tl(PLANS[2].yearly! + RESEARCH_ADDON.yearly)],
        ['yıl', 'yr'],
        ['Aylık eşdeğeri', 'Monthly equivalent'],
        [`${tl(Math.round(PLANS[2].yearly! / 12) + RESEARCH_ADDON.monthly)}/ay`, `${tl(Math.round(PLANS[2].yearly! / 12) + RESEARCH_ADDON.monthly)}/mo`],
        [`${tl(PLANS[2].yearly! + RESEARCH_ADDON.yearly)} tutarındaki yıllık ödeme, siz iptal edene kadar her dönem sonunda otomatik tahsil edilir. Gösterilen tutar KDV dâhil toplam bedeldir; başka bir ücret eklenmez. Ayrıntılar için`,
         `The annual payment of ${tl(PLANS[2].yearly! + RESEARCH_ADDON.yearly)} is charged automatically at the end of each period until you cancel. The amount shown is the total price including VAT; no other fee is added. For details, see the`],
      ],
    ],
    [
      'Odeme · Pro+ aylık', '/odeme?tier=pro_plus&yearly=0&research=0', (k) => ciz(Odeme, k),
      () => [
        ...ortak,
        ['Aylık ödeme', 'Monthly payment'],
        ['ay', 'mo'],
        [`${tl(PLANS[3].monthly!)} tutarındaki aylık ödeme, siz iptal edene kadar her dönem sonunda otomatik tahsil edilir. Gösterilen tutar KDV dâhil toplam bedeldir; başka bir ücret eklenmez. Ayrıntılar için`,
         `The monthly payment of ${tl(PLANS[3].monthly!)} is charged automatically at the end of each period until you cancel. The amount shown is the total price including VAT; no other fee is added. For details, see the`],
      ],
    ],
    [
      'Odeme · bilinmeyen plan → Pro aylık', '/odeme?tier=bilinmeyen', (k) => ciz(Odeme, k),
      () => [['Aylık ödeme', 'Monthly payment']],
    ],
  )
}

describe('site-12d-ticari · altın tablo', () => {
  const anahtarlar = Object.keys(ALTIN).sort()

  it('73 anahtar (kapı küçülmesin)', () => {
    expect(anahtarlar.length).toBe(73)
  })

  for (const k of anahtarlar) {
    it(`${k} · TR değer göç öncesiyle BAYT BAYT aynı · EN dolu, Türkçe harfsiz, aynı yer tutucular ve sayılar`, () => {
      expect(TR[k], `TR değer eskisinden FARKLI: ${k}`).toBe(ALTIN[k])
      expect(String(EN[k] ?? '').trim(), `EN boş: ${k}`).not.toBe('')
      expect(TR_HARF.test(EN[k]), `EN'de Türkçe harf: ${k}: ${EN[k]}`).toBe(false)
      expect(yerTutucu(EN[k]), `yer tutucu kümesi ayrışmış: ${k}`).toEqual(yerTutucu(TR[k]))
      expect(sayilar(EN[k]), `sayılar ayrışmış: ${k}`).toEqual(sayilar(TR[k]))
    })
  }
})

describe('site-12d-ticari · çizim', () => {
  for (const [ad, konum, cizici, ciftler] of SAYFALAR) {
    it(`${ad} · Türkçe (bayrak kapalı): göç öncesiyle aynı metin`, () => {
      const h = cizici(konum)
      expect(coz(h), `${ad}: çözülmemiş {{yer tutucu}} kaldı`).not.toMatch(/\{\{\w+\}\}/)
      const d = dugumler(h)
      for (const [tr] of ciftler()) expect(var_(h, d, tr), `${ad}: ${tr}`).toBe(true)
    })

    it(`${ad} · bayrak AÇIK + İngilizce: her satır İngilizce, Türkçe kalmaz`, async () => {
      dilMod.__bayrakTestiAyarla(true)
      await i18nMod.dilSec('en')
      const h = cizici(konum)
      expect(coz(h), `${ad}: çözülmemiş {{yer tutucu}} kaldı`).not.toMatch(/\{\{\w+\}\}/)
      const d = dugumler(h)
      for (const [tr, en] of ciftler()) {
        expect(var_(h, d, en), `${ad} EN: ${en}`).toBe(true)
        if (BASKA_KAYNAK.has(tr)) continue
        // Plan kartı değerleri (ad, tutar …) iki dilde de aynı olabilir: yalnız farklı olanlarda Türkçenin kalmaması aranır
        if (tr !== en) expect(var_(h, d, tr), `${ad} TR kaldı: ${tr}`).toBe(false)
      }
    })
  }

  it('plan kartı metinleri (ad / açıklama / jeton hakkı / düğme / fiyat) İngilizcede Türkçe harf taşımaz', async () => {
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const h = ciz(Pricing, '/pricing')
    const kartlar = [...dugumler(h)].filter((s) => /credit|clinic|device|support|trial|Pay as You Go|Starter/i.test(s))
    expect(kartlar.length).toBeGreaterThan(10)
    for (const s of kartlar) expect(TR_HARF.test(s), s).toBe(false)
  })

  it('eklenti kartları (ad / açıklama / fiyat) iki dilde çizilir', async () => {
    const trH = ciz(Pricing, '/pricing')
    const trD = dugumler(trH)
    for (const a of ADDONS) for (const m of [a.name, a.desc, a.price]) expect(trD.has(m), m).toBe(true)
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    const enH = ciz(Pricing, '/pricing')
    const enD = dugumler(enH)
    for (const a of ADDONS) for (const m of [a.name, a.desc, a.price]) {
      expect(enD.has(m), m).toBe(true)
      expect(TR_HARF.test(m), m).toBe(false)
    }
  })
})

describe('site-12d-ticari · fiyat gösterimi ve sayı / para biçimi', () => {
  const pro = PLANS.find((p) => p.tier === 'pro')!
  const proPlus = PLANS.find((p) => p.tier === 'pro_plus')!
  const kullandikca = PLANS.find((p) => p.tier === 'kullandikca')!

  it('Türkçe: para ₺1.990 (tr-TR), İngilizce ₺1,990 (en-US); sayı biçimi etkin dile göre', async () => {
    expect(tl(1990)).toBe('₺1.990')
    expect(sayi(2000)).toBe('2.000')
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    expect(tl(1990)).toBe('₺1,990')
    expect(sayi(2000)).toBe('2,000')
  })

  it('planFiyatGorunumu / planKisaFiyat iki dilde', async () => {
    const tr = [planFiyatGorunumu(pro, true), planFiyatGorunumu(pro, false), planFiyatGorunumu(proPlus, true), planFiyatGorunumu(kullandikca, true), planKisaFiyat(pro), planKisaFiyat(kullandikca)]
    if (FREE_MODE) {
      expect(tr[0]).toEqual({ buyuk: 'Şu an ücretsiz', kucuk: 'test sonrası ₺990/ay' })
      expect(tr[2]).toEqual({ buyuk: 'Şu an ücretsiz', kucuk: 'test sonrası ₺1.990/ay' })
      expect(tr[4]).toBe('Şu an ücretsiz')
    } else {
      expect(tr[0]).toEqual({ buyuk: '₺825', kucuk: 'klinik / ay · yıllık ₺9.900' })
      expect(tr[1]).toEqual({ buyuk: '₺990', kucuk: 'klinik / ay' })
      expect(tr[2]).toEqual({ buyuk: '₺1.658', kucuk: 'klinik / ay · yıllık ₺19.900' })
      expect(tr[4]).toBe('₺990/ay')
    }
    // Kendi etiketi olan plan (Kullandıkça Öde) FREE_MODE'dan ÖNCE kazanır
    expect(tr[3]).toEqual({ buyuk: '₺2,90 / jeton', kucuk: 'aylık ücret yok' })
    expect(tr[5]).toBe('₺2,90 / jeton')
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    if (FREE_MODE) {
      expect(planFiyatGorunumu(pro, true)).toEqual({ buyuk: 'Free right now', kucuk: 'after the test: ₺990/mo' })
      expect(planFiyatGorunumu(proPlus, true)).toEqual({ buyuk: 'Free right now', kucuk: 'after the test: ₺1,990/mo' })
      expect(planKisaFiyat(pro)).toBe('Free right now')
    } else {
      expect(planFiyatGorunumu(pro, true)).toEqual({ buyuk: '₺825', kucuk: 'clinic / month · yearly ₺9,900' })
      expect(planFiyatGorunumu(proPlus, true)).toEqual({ buyuk: '₺1,658', kucuk: 'clinic / month · yearly ₺19,900' })
      expect(planKisaFiyat(pro)).toBe('₺990/mo')
    }
    expect(planFiyatGorunumu(kullandikca, true)).toEqual({ buyuk: '₺2.90 / credit', kucuk: 'no monthly fee' })
  })

  it('baglantiliMetin: {{ad}} işaretçileri verilen düğümlerle değişir, kalan metin aynen', () => {
    const yaz = (n: ReturnType<typeof baglantiliMetin>) => temizle(renderToString(createElement('div', null, ...n))).replace(/^<div>|<\/div>$/g, '')
    expect(yaz(baglantiliMetin('a {{x}} b {{y}} c', { x: 'X', y: 'Y' }))).toBe('a X b Y c')
    expect(baglantiliMetin('{{x}}', { x: 'X' }).length).toBe(1)
    expect(yaz(baglantiliMetin('sade metin', {}))).toBe('sade metin')
    expect(yaz(baglantiliMetin('{{bilinmeyen}} kalır', {}))).toBe('{{bilinmeyen}} kalır')
    // İngilizce kelime sırası farklı olsa da bağlantı düğümü şablondaki yerinde kalır
    expect(yaz(baglantiliMetin('Read the {{a}} now', { a: createElement('b', null, 'terms') }))).toBe('Read the <b>terms</b> now')
  })

  it('ödeme / iptal hata dizgileri (api/*.ts, lib/checkout.ts) GÖSTERİLMEZ: iki dilde aynı sınıfa çevrilir', async () => {
    const hata = vi.spyOn(console, 'error').mockImplementation(() => {})
    const ORNEK = ['Önce giriş yapın.', 'Aktif abonelik bulunamadı.', 'İptal edilemedi.', 'Ödeme başlatılamadı.', 'Ağ hatası — tekrar deneyin.', 'Ödeme formu oluşturulamadı.']
    const sinif = (dil: 'tr' | 'en') => ORNEK.map((m) => odemeHatasiTurkce(m)).map((s) => (dil === 'tr' ? TR : EN)['hesap.odeme.abonelikYok'].replace('{{email}}', COMPANY.email) === s)
    const tr = sinif('tr')
    dilMod.__bayrakTestiAyarla(true)
    await i18nMod.dilSec('en')
    expect(sinif('en')).toEqual(tr)
    for (const m of ORNEK) expect(TR_HARF.test(odemeHatasiTurkce(m)), m).toBe(false)
    expect(tr.filter(Boolean).length).toBe(1) // yalnız "bulunamadı" → abonelik yok sınıfı
    hata.mockRestore()
  })
})
