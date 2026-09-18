// Author: mertaygn, cglrgrkn
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase, supabaseReady } from '../lib/supabase'
import { authHatasiTurkce, SIFRE_KURALI, sifreGecerliMi } from '../lib/authHatalari'

/* Şifre sıfırlama — e-postadaki linkin döndüğü sayfa.
   Eskiden AuthContext.resetPassword() `redirectTo` VERMEDEN çağrılıyordu: link Supabase'in Site
   URL'ine (mobil uygulamanın GitHub Pages "reset.html" sayfasına) gidiyor, web kullanıcısı hiç
   beklemediği bir sayfaya düşüyordu — sitede yeni şifre belirleyecek bir ekran yoktu.
   Supabase istemcisi `detectSessionInUrl: true` ile kurulu olduğundan, link açıldığında kurtarma
   oturumu otomatik kurulur ve updateUser çalışır. */

/* ŞİFRE KURALI ARTIK TEK KAYNAKTAN (metin denetimi 2026-08-20): buradaki yorum "kayıt ekranıyla
   AYNI politika" diyordu ama kayıt formu `minLength={6}` ile 6 haneye izin veriyordu — iddia
   gerçek DEĞİLDİ ve kayıtta kabul edilen şifre burada reddediliyordu. Kural + metin
   `src/lib/authHatalari.ts`'te; iki ekran da oradan okur. */

export default function ResetPassword() {
  const [ready, setReady] = useState(false)
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!supabaseReady) return
    // Kurtarma oturumu URL'den çözülünce hazır ol.
    const { data: sub } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'PASSWORD_RECOVERY' || event === 'SIGNED_IN') setReady(true)
    })
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) setReady(true)
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    if (!sifreGecerliMi(pw)) {
      return setErr(`Şifre yeterince güçlü değil. ${SIFRE_KURALI.aciklama}`)
    }
    if (pw !== pw2) return setErr('Şifreler eşleşmiyor.')
    setBusy(true)
    const { error } = await supabase.auth.updateUser({ password: pw })
    setBusy(false)
    if (error) return setErr(authHatasiTurkce(error.message))
    setDone(true)
  }

  if (done) {
    return (
      <section className="mx-auto max-w-md px-5 py-20 text-center">
        <h1 className="text-2xl font-bold">Şifreniz güncellendi</h1>
        <p className="mt-2 text-sm text-muted">Yeni şifrenizle giriş yapabilirsiniz.</p>
        <Link to="/" className="btn-primary mt-6">Ana sayfaya dön</Link>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-md px-5 py-20">
      <h1 className="text-2xl font-bold">Yeni şifre belirle</h1>
      {/* Metin denetimi 2026-08-20: "yeniden başlatın" deniyordu ama sayfada hiçbir bağlantı
          yoktu — kullanıcı akışı yeniden başlatamıyordu. Artık ana sayfaya dönüp "Şifremi
          unuttum" adımını tekrarlayabileceği bir yol var. */}
      {!ready && (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-warning">
          Sıfırlama bağlantısı doğrulanıyor… Bu mesaj kalıcıysa bağlantının süresi dolmuş olabilir.
          Yeni bir bağlantı almak için{' '}
          <Link to="/" className="font-medium underline">ana sayfadan giriş penceresini açıp</Link>{' '}
          “Şifremi unuttum” adımını tekrarlayın.
        </p>
      )}
      <form onSubmit={submit} className="card mt-6 space-y-4 p-6">
        <input
          type="password" required autoComplete="new-password" placeholder="Yeni şifre"
          value={pw} onChange={(e) => setPw(e.target.value)} className="input" disabled={!ready}
        />
        <input
          type="password" required autoComplete="new-password" placeholder="Yeni şifre (tekrar)"
          value={pw2} onChange={(e) => setPw2(e.target.value)} className="input" disabled={!ready}
        />
        <p className="text-xs text-muted">{SIFRE_KURALI.aciklama}</p>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button type="submit" disabled={!ready || busy} className="btn-primary w-full disabled:opacity-60">
          {busy ? 'Güncelleniyor…' : 'Şifreyi güncelle'}
        </button>
      </form>
    </section>
  )
}
