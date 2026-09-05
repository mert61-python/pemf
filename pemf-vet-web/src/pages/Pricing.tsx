// Author: mertaygn, cglrgrkn
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PLANS, ADDONS, COMPARE, RESEARCH_ADDON, FREE_MODE, COMPANY, type Plan } from '../config'
import { planFiyatGorunumu } from '../lib/planFiyat'
import { Check, Sparkle, Bolt } from '../components/Icons'
import PackageBuilder from '../components/PackageBuilder'

const tl = (n: number) => `₺${n.toLocaleString('tr-TR')}`

// ⚠️ Fiyat gösterimi ARTIK BURADA DEĞİL. Aynı hesap ana sayfada da satır içi yazılıydı; aylık
// ücreti olmayan "Kullandıkça Öde" planı eklenince ikisi ayrı ayrı "₺0/ay" üretti (ikisi de
// yanlış — ücret jeton başına). Tek kaynak: src/lib/planFiyat.ts.

/**
 * MOBİL KARŞILAŞTIRMA — SATIR kartı  [2026-09-05, responsive denetimi kalanı]
 * ==========================================================================
 * ÖLÇÜLEN DURUM (headless Edge + CDP): karşılaştırma tablosu 560 px genişlikte ve
 * `overflow-x-auto` içinde. 320 px telefonda kabı 280 px'e düşüyor → tablonun 280 px'i
 * gizli, 5 sütundan yalnız 2'si görünüyor (390 px'te 3'ü). Satır etiketi yapışkan
 * OLMADIĞI için kullanıcı sağa kaydırdığında hangi satıra baktığını da kaybediyordu.
 *
 * NEDEN PLAN BAŞINA DEĞİL SATIR BAŞINA KART: plan başına kartta karşılaştırma ekseni
 * TAMAMEN kaybolur — kullanıcı iki planın aynı satırını yan yana tutamaz, oysa bu sayfaya
 * gelme sebebi tam olarak budur. Satır kartında eksen kartın İÇİNDE kalır.
 *
 * ⚠️ İKİ GÖRÜNÜM DE tek kaynaktan (PLANS + COMPARE) türer; gömülü dizi YOKTUR.
 * ⚠️ Kart bloğunda `lg:grid-cols-*` KULLANILMAZ: kullandikca-ode testi dosyadaki İLK
 *    `lg:grid-cols-(\d)` eşleşmesini okuyor ve o çıpa plan ızgarasına (yukarıda) pinli.
 * ⚠️ Kart bloğunda etkileşimli öge YOKTUR (düğme/bağlantı/summary) → 44 px dokunma
 *    kapısında yeni hedef doğmaz.
 */

/** Bir karşılaştırma satırını AYNI DEĞERİ paylaşan plan gruplarına böler (PLANS sırası korunur).
 *  Amaç: dar ekranda 4 satır yerine YALNIZ FARK KADAR satır çizmek.
 *  ⚠️ Gruplar KESİNTİLİ olabilir: 'Jeton başına ücret' bugün "Başlangıç · Pro · Pro+" üretiyor
 *  (Kullandıkça Öde aradan atlanıyor). Çıktı doğru ve okunur; sürpriz değil, bilinen davranış. */
function degerGruplari(row: (typeof COMPARE)[number]) {
  const gruplar: { deger: string; planlar: Plan[] }[] = []
  for (const p of PLANS) {
    const g = gruplar.find((x) => x.deger === row.values[p.tier])
    if (g) g.planlar.push(p)
    else gruplar.push({ deger: row.values[p.tier], planlar: [p] })
  }
  return gruplar
}

/** Tüm planlarda aynı olan satır AYIRT EDİCİ değildir; tek bir "hepsinde var" kartına toplanır. */
const ayirtEdici = (row: (typeof COMPARE)[number]) => degerGruplari(row).length > 1

/** Değer rozeti. "✓" ve "✓ (…)" site tik diline çevrilir; parantezli açıklama KORUNUR
 *  (AI Pro'nun seans başına 5 jeton yaktığı bilgisi kartta kaybolmamalı).
 *  ⚠️ `Yok` kontrolü CONFIG SÖZLÜĞÜNE bağlıdır: "Yok" = bu planda yok (eksiklik, soluk),
 *  "Alınmıyor" = ücret alınmıyor (avantaj, normal). Etiketten valans TAHMİN EDİLMEZ. */
function Deger({ v }: { v: string }) {
  if (!v.startsWith('✓')) {
    return <span className={/^Yok/.test(v) ? 'text-muted' : 'font-medium text-fg'}>{v}</span>
  }
  const ek = v.slice(1).trim()
  return (
    <span className="inline-flex items-center justify-end gap-1.5">
      <Check className="h-4 w-4 shrink-0 text-primary" />
      <span className="text-xs text-muted">{ek || 'Var'}</span>
    </span>
  )
}

export default function Pricing() {
  const [yearly, setYearly] = useState(true)
  const [research, setResearch] = useState(false)
  const navigate = useNavigate()
  const [sp] = useSearchParams()
  const checkout = sp.get('checkout') // success | incomplete | error (iyzico callback dönüşü)

  // Ödeme sayfasına yönlendir (fatura bilgisi + iyzico formu orada). Giriş /odeme'de istenir.
  // TEST AŞAMASI (FREE_MODE): satış kapalı → "Seç" ücretsiz indirmeye götürür.
  function buy(p: Plan) {
    if (!p.paid) return
    if (FREE_MODE) return navigate('/download')
    navigate(`/odeme?tier=${p.tier}&yearly=${yearly ? 1 : 0}&research=${research ? 1 : 0}`)
  }

  return (
    <>
      {checkout && (
        <div className="mx-auto max-w-6xl px-5 pt-6 sm:px-6">
          <div className={`rounded-lg border px-4 py-3 text-sm ${
            checkout === 'success'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-success'
              : 'border-amber-500/40 bg-amber-500/10 text-warning'
          }`}>
            {/* Metin denetimi 2026-08-20: "tekrar deneyin veya destek ile iletişime geçin" diyordu
                ama hiçbiri tıklanabilir değildi — kullanıcı hata bandında sıkışıp kalıyordu. */}
            {checkout === 'success' ? (
              '✓ Ödemeniz alındı, aboneliğiniz başladı. PEMF Vet’i indirip aynı hesapla giriş yapın.'
            ) : checkout === 'incomplete' ? (
              'Ödeme tamamlanmadı. Dilerseniz yukarıdan planınızı yeniden seçebilirsiniz.'
            ) : (
              <>
                Ödeme sırasında bir sorun oluştu. Yukarıdan tekrar deneyebilir ya da{' '}
                <a
                  href={`mailto:${COMPANY.email}?subject=${encodeURIComponent('Ödeme sorunu')}`}
                  className="font-medium underline"
                >
                  {COMPANY.email}
                </a>{' '}
                adresinden bize ulaşabilirsiniz.
              </>
            )}
          </div>
        </div>
      )}

      {FREE_MODE && (
        <div className="mx-auto max-w-6xl px-5 pt-6 sm:px-6">
          <div className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-sm text-primary">
            Test aşaması: tüm planlar şu an <strong>ücretsiz</strong>. Aşağıdaki planlardan hangisini seçerseniz seçin doğrudan indirmeye gidersiniz; kart bilgisi istenmez, ödeme alınmaz.
          </div>
        </div>
      )}

      {/* Hero + billing toggle */}
      <section className="bg-hero border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 text-center sm:px-6 sm:py-20">
          <span className="chip"><Sparkle className="h-3.5 w-3.5" /> Fiyatlandırma</span>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">Kliniğinize göre plan</h1>
          <p className="mx-auto mt-4 max-w-2xl text-muted">
            Planınız, ayda kaç yapay zekâ analizi yapabileceğinizi belirler:{' '}
            <span className="text-fg/90 font-medium">her analiz 1 jeton harcar</span>; jetonunuz biterse ek paket
            alabilir ya da hiç aylık ücret ödemeden <span className="text-fg/90 font-medium">kullandıkça ödeyebilirsiniz</span>.
            Hangi yapay zekâ modellerinin ineceğini ise kurulumda seçtiğiniz profiller belirler.
          </p>

          <div className="mt-8 inline-flex items-center gap-1 rounded-full border border-border-strong bg-bg-soft p-1 text-sm">
            <button onClick={() => setYearly(false)} className={`rounded-full px-4 py-1.5 font-medium transition-colors ${!yearly ? 'bg-primary text-primary-fg' : 'text-muted'}`}>Aylık</button>
            <button onClick={() => setYearly(true)} className={`rounded-full px-4 py-1.5 font-medium transition-colors ${yearly ? 'bg-primary text-primary-fg' : 'text-muted'}`}>
              Yıllık<span className={`ml-1.5 text-xs ${yearly ? 'text-primary-fg/80' : 'text-primary'}`}>2 ay ücretsiz</span>
            </button>
          </div>

          {/* KDV BEYANI (7. parti kararı): ödeme sayfası "gösterilen tutar KDV dâhil toplam
              bedeldir" diyordu; fiyat sayfası suskundu — aynı rakam iki sayfada farklı anlaşılıyordu.
              Tahsilat tarafı vergi EKLEMEDİĞİ için doğru beyan "dâhil"dir. */}
          <p className="mt-4 text-xs text-muted">Fiyatlara KDV dâhildir; ayrıca ücret eklenmez.</p>

          {/* Araştırma eklentisi — Pro/Pro+ satın alımına eklenir */}
          <div className="mt-5">
            <label className="inline-flex cursor-pointer items-center gap-2.5 rounded-full border border-border bg-bg-soft px-4 py-2 text-sm">
              <input type="checkbox" checked={research} onChange={(e) => setResearch(e.target.checked)} className="h-4 w-4 accent-primary" />
              <span className="text-muted">
                Araştırma profili ekle <span className="font-medium text-fg">+{tl(RESEARCH_ADDON.monthly)}/ay</span>
              </span>
            </label>
          </div>
        </div>
      </section>

      {/* Seviyeler */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="grid items-start gap-6 md:grid-cols-2 lg:grid-cols-4">
            {PLANS.map((p) => {
              const pv = planFiyatGorunumu(p, yearly)
              return (
                <div key={p.name} className={`card relative flex flex-col p-7 ${p.highlight ? 'ring-2 ring-primary/50 glow-ring' : ''}`}>
                  {p.badge && (
                    <span className="absolute -top-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-bold text-primary-fg">
                      <Bolt className="h-3 w-3" /> {p.badge}
                    </span>
                  )}
                  <div className="text-lg font-bold">{p.name}</div>
                  <p className="mt-1 text-sm text-muted">{p.desc}</p>

                  <div className="mt-5 text-4xl font-extrabold tracking-tight">{pv.buyuk}</div>
                  <div className="mt-1 text-xs text-muted">{pv.kucuk}</div>

                  {/* Jeton hakkı rozeti (eski "işlem önceliği" vurgusunun yerine — 8. parti) */}
                  <div className={`mt-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${
                    p.highlight ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted'
                  }`}>
                    {p.highlight ? <Bolt className="h-4 w-4" /> : <span className="h-1.5 w-1.5 rounded-full bg-muted" />}
                    {p.jetonHakki}
                  </div>

                  {p.paid ? (
                    <button onClick={() => buy(p)} className={`mt-6 ${p.highlight ? 'btn-primary' : 'btn-ghost'}`}>
                      {p.cta}
                    </button>
                  ) : (
                    <Link to={p.to} className={`mt-6 ${p.highlight ? 'btn-primary' : 'btn-ghost'}`}>{p.cta}</Link>
                  )}

                  <ul className="mt-6 space-y-2.5 border-t border-border pt-6">
                    {p.features.map((f, i) => (
                      <li key={i} className="flex gap-2.5 text-sm text-muted">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Karşılaştırma — 1024 altı SATIR kartları, üstü mevcut tablo (bkz. degerGruplari yorumu) */}
      <section className="border-b border-border/60 bg-bg-soft/50">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <h2 id="plan-karsilastirmasi" className="text-2xl font-bold sm:text-3xl">Plan karşılaştırması</h2>
          <p className="mt-3 max-w-2xl text-sm text-muted lg:hidden">
            Her kart tek bir özelliği tüm planlarda birlikte gösterir; aynı değeri veren planlar
            tek satırda birleşir, böylece farklar öne çıkar.
          </p>
          {/* COMPARE tarifeyi FREE_MODE'dan bağımsız yazar; test aşamasında tutar tahsil edilmez.
              Sayfa başındaki band mobilde ekran dışında kaldığı için burada bir kez daha söylenir. */}
          {FREE_MODE && (
            <p className="mt-3 max-w-2xl text-sm text-primary">
              Aşağıdaki tutarlar test sonrası tarifedir; şu an tahsil edilmez.
            </p>
          )}

          {/* ——— DAR + ORTA EKRAN (1024 altı): satır kartları ———
              ⚠️ `lg:grid-cols-*` YAZILMAZ: kullandikca-ode testi dosyadaki İLK `lg:grid-cols-(\d)`
              eşleşmesini okur ve o çıpa yukarıdaki plan ızgarasına pinlidir. */}
          <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:hidden">
            {COMPARE.filter(ayirtEdici).map((row) => (
              <div key={row.label} className="card min-w-0 p-5">
                <h3 className="text-sm font-semibold">{row.label}</h3>
                <dl className="mt-3 space-y-2">
                  {degerGruplari(row).map((g) => (
                    <div
                      key={g.deger}
                      className={`flex min-w-0 items-start justify-between gap-3 rounded-lg border px-3 py-2 ${
                        g.planlar.some((p) => p.highlight)
                          ? 'border-primary/40 bg-primary/10'
                          : 'border-border bg-bg/40'
                      }`}
                    >
                      <dt className="min-w-0 flex-1 text-xs leading-snug">
                        {g.planlar.map((p, i) => (
                          <span key={p.tier} className={p.highlight ? 'font-semibold text-primary' : 'text-muted'}>
                            {i > 0 && <span className="text-muted"> · </span>}
                            {p.name}
                          </span>
                        ))}
                      </dt>
                      <dd className="min-w-0 max-w-[58%] break-words pl-3 text-right text-sm">
                        <Deger v={g.deger} />
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}

            {COMPARE.filter((r) => !ayirtEdici(r)).length > 0 && (
              <div className="card min-w-0 p-5 sm:col-span-2">
                {/* Sayı YAZILMAZ ("dört") — PLANS büyüyünce metin yalan olurdu. */}
                <h3 className="text-sm font-semibold">Tüm planlarda var</h3>
                <ul className="mt-3 space-y-2.5">
                  {COMPARE.filter((r) => !ayirtEdici(r)).map((row) => (
                    <li key={row.label} className="flex min-w-0 gap-2.5 text-sm text-muted">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span className="min-w-0 break-words">
                        {row.label}
                        {row.values[PLANS[0].tier] !== '✓' && ` — ${row.values[PLANS[0].tier]}`}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* ——— MASAÜSTÜ (1024 üstü): mevcut tablo. `overflow-x-auto` + `min-w-[560px]` KALIR:
              sayfa gövdesinin yatay kaymasını o kap engelliyor. ——— */}
          <div className="mt-8 hidden overflow-x-auto lg:block">
            <table
              className="w-full min-w-[560px] border-collapse text-sm"
              aria-labelledby="plan-karsilastirmasi"
            >
              <thead>
                <tr className="border-b border-border">
                  {/* Boş köşe hücresi BAŞLIK değildir → td (ekran okuyucu boş başlık okumaz). */}
                  <td className="py-3" />
                  {/* ⚠️ TEK KAYNAK: başlıklar PLANS’ten türer. Eskiden gömülü diziydi ve PLANS’e
                      eklenen plan tabloda görünmüyordu (8. partide kullandıkça-öde eklenince ölçüldü). */}
                  {PLANS.map((c) => (
                    <th key={c.tier} scope="col" className={`px-3 py-3 text-center font-bold ${c.highlight ? 'text-primary' : ''}`}>{c.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE.map((row) => (
                  <tr key={row.label} className="border-b border-border/60">
                    {/* Satır etiketi de BAŞLIKTIR: `scope="row"` olmadan ekran okuyucu "₺990"un
                        hangi satıra ait olduğunu söyleyemiyordu. Görünüm text-left ile korunur. */}
                    <th scope="row" className="py-3 pr-3 text-left font-medium">{row.label}</th>
                    {PLANS.map((c) => (
                      <td key={c.tier} className={`px-3 py-3 text-center ${c.highlight ? 'text-fg' : 'text-muted'}`}>{row.values[c.tier]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Kullanım profilleri (kurulum) */}
      <section className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="max-w-2xl">
            <span className="chip">Kurulum profilleri</span>
            <h2 className="mt-4 text-2xl font-bold sm:text-3xl">Ne kurulacağını siz seçin</h2>
            <p className="mt-3 text-muted">
              Yalnız seçtiğiniz profillerin modelleri iner — evcil hayvan sahibi, ağır araştırma
              modellerini boşuna indirmez. Evcil Hayvan Sahibi ve Veteriner profilleri planınıza dahildir.
            </p>
          </div>
          <div className="mt-10">
            <PackageBuilder />
          </div>
        </div>
      </section>

      {/* Eklentiler */}
      <section className="border-b border-border/60 bg-bg-soft/50">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="max-w-xl">
            <span className="chip">Eklentiler</span>
            <h2 className="mt-4 text-2xl font-bold sm:text-3xl">Ek özellikler</h2>
            <p className="mt-3 text-muted">Uygulama içinden tek tıkla açarsınız; ücreti aboneliğinize eklenir.</p>
          </div>
          {/* 2026-08-09: eklenti sayısı 3'ten 2'ye indi ("Genişletilmiş Yedekleme" kaldırıldı —
              arkasında ürün yoktu, bkz. config.ts). Sabit 3 sütun boş bir hücre bırakıyordu;
              ızgara kalem sayısına göre daralıyor. */}
          <div className={`mt-10 grid gap-5 ${ADDONS.length > 2 ? 'sm:grid-cols-3' : 'sm:grid-cols-2 lg:max-w-3xl'}`}>
            {ADDONS.map((a) => (
              <div key={a.name} className="card p-6">
                <div className="flex items-baseline justify-between">
                  <h3 className="font-semibold">{a.name}</h3>
                  <span className="text-sm font-bold text-primary">{a.price}</span>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{a.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Kurumsal + trial */}
      <section>
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
          <div className="card flex flex-col items-center gap-6 p-8 text-center sm:flex-row sm:justify-between sm:p-10 sm:text-left">
            <div>
              <h2 className="text-2xl font-bold">Zincir klinik veya kurum musunuz?</h2>
              <p className="mt-2 max-w-lg text-muted">Sınırsız cihaz ve şube, kendi sistemlerinizle bütünleşme, yerinde kurulum ve garantili destek için özel fiyat.</p>
            </div>
            {/* Metin denetimi 2026-08-20: "İletişime Geçin" /support'a (SSS başlığına) gidiyordu;
                kurumsal teklif bekleyen ziyaretçi sık sorulan sorular sayfasına düşüyordu.
                Artık doğrudan konu satırı hazır bir e-posta açar. */}
            <div className="flex shrink-0 flex-col gap-3 sm:flex-row">
              <a
                href={`mailto:${COMPANY.email}?subject=${encodeURIComponent('Kurumsal teklif talebi')}`}
                className="btn-ghost"
              >
                İletişime Geçin
              </a>
              <Link to="/download" className="btn-primary">14 gün ücretsiz dene</Link>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
