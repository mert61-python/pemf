// Author: mertaygn, cglrgrkn
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase, supabaseReady } from '../lib/supabase'

/* Şifre sıfırlama — e-postadaki linkin döndüğü sayfa.
   Eskiden AuthContext.resetPassword() `redirectTo` VERMEDEN çağrılıyordu: link Supabase'in Site
   URL'ine (mobil uygulamanın GitHub Pages "reset.html" sayfasına) gidiyor, web kullanıcısı hiç
   beklemediği bir sayfaya düşüyordu — sitede yeni şifre belirleyecek bir ekran yoktu.
   Supabase istemcisi `detectSessionInUrl: true` ile kurulu olduğundan, link açıldığında kurtarma
   oturumu otomatik kurulur ve updateUser çalışır. */

/** Uygulamanın kayıt ekranıyla AYNI politika: en az 8 karakter + harf + rakam.
    (Mobil `isPasswordValid` ile hizalı — aksi halde sıfırlama, kayıt politikasını atlatan bir
    "arka kapı" olur ve hesap 6 haneli zayıf bir şifreye düşürülebilir.) */
function isPasswordValid(pw: string): boolean {
  return pw.length >= 8 && /[A-Z]/.test(pw) && /[a-z]/.test(pw) && /\d/.test(pw)
}

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
    if (!isPasswordValid(pw)) {
      return setErr('Şifre en az 8 karakter olmalı; büyük harf, küçük harf ve rakam içermeli.')
    }
    if (pw !== pw2) return setErr('Şifreler eşleşmiyor.')
    setBusy(true)
    const { error } = await supabase.auth.updateUser({ password: pw })
    setBusy(false)
    if (error) return setErr(error.message)
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
      {!ready && (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-600 dark:text-amber-400">
          Sıfırlama bağlantısı doğrulanıyor… Bu mesaj kalıcıysa bağlantının süresi dolmuş olabilir;
          şifre sıfırlamayı yeniden başlatın.
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
        <p className="text-xs text-muted">En az 8 karakter; büyük harf, küçük harf ve rakam içermeli.</p>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button type="submit" disabled={!ready || busy} className="btn-primary w-full disabled:opacity-60">
          {busy ? 'Güncelleniyor…' : 'Şifreyi güncelle'}
        </button>
      </form>
    </section>
  )
}
