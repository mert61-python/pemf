// Author: mertaygn, cglrgrkn
import {
  createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode,
} from 'react'
import { useAuth } from './AuthContext'
import { Close } from '../components/Icons'

/** Modalın hangi akış için açıldığı — yalnız alt başlık metnini değiştirir.
 *  Opsiyonel: mevcut `requireAuth(cb)` çağrıları (ödeme, hesap düğmesi) aynen çalışır. */
export type AuthReason = 'checkout' | 'download'

type ModalCtx = { requireAuth: (onAuthed?: () => void, reason?: AuthReason) => void }
const Ctx = createContext<ModalCtx | undefined>(undefined)

export function AuthModalProvider({ children }: { children: ReactNode }) {
  const { session, ready } = useAuth()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<AuthReason>('checkout')
  const pendingRef = useRef<(() => void) | null>(null)

  const requireAuth = useCallback((onAuthed?: () => void, r: AuthReason = 'checkout') => {
    pendingRef.current = onAuthed ?? null
    setReason(r)
    setOpen(true)
  }, [])

  // Giriş başarılı olur olmaz bekleyen işlemi (ör. checkout / indirme) çalıştır + kapat.
  // İndirme kapısı buna dayanır: kullanıcı giriş bitince düğmeye İKİNCİ KEZ basmaz.
  useEffect(() => {
    if (open && session) {
      const cb = pendingRef.current
      pendingRef.current = null
      setOpen(false)
      cb?.()
    }
  }, [open, session])

  return (
    <Ctx.Provider value={{ requireAuth }}>
      {children}
      {open && (
        <AuthModal
          ready={ready}
          reason={reason}
          onClose={() => {
            // Kullanıcı modalı KAPATTIYSA bekleyen işi de düşür: aksi halde daha sonra
            // (ör. hesap düğmesinden) giriş yapınca vazgeçtiği indirme kendiliğinden başlardı.
            pendingRef.current = null
            setOpen(false)
          }}
        />
      )}
    </Ctx.Provider>
  )
}

export function useAuthModal(): ModalCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuthModal must be used within AuthModalProvider')
  return c
}

// Hesap tipleri — profile göre form alanları + (ileride) abonelik/erişim eşlemesi.
type AccountType = 'individual' | 'veterinarian' | 'researcher'
const ACCOUNT_TYPES: { id: AccountType; title: string; sub: string; icon: string }[] = [
  { id: 'individual', title: 'Evcil Hayvan Sahibi', sub: 'Bireysel kullanım', icon: '🐾' },
  { id: 'veterinarian', title: 'Veteriner Hekim / Klinik', sub: 'Klinik bilgileriyle', icon: '🩺' },
  { id: 'researcher', title: 'Araştırmacı / Kurum', sub: 'Üniversite · enstitü', icon: '🔬' },
]

const FIELD =
  'w-full rounded-lg border border-border bg-bg-soft px-3.5 py-2.5 text-sm outline-none focus:border-primary/60'

function AuthModal({ ready, reason, onClose }: { ready: boolean; reason: AuthReason; onClose: () => void }) {
  const { signIn, signUp, resetPassword } = useAuth()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [accountType, setAccountType] = useState<AccountType>('individual')
  const dialogRef = useRef<HTMLDivElement>(null)

  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [fullName, setFullName] = useState('')
  // Veteriner / klinik
  const [clinicName, setClinicName] = useState('')
  const [city, setCity] = useState('')
  const [phone, setPhone] = useState('')
  const [vetLicense, setVetLicense] = useState('')
  // Araştırmacı / kurum
  const [institution, setInstitution] = useState('')
  const [department, setDepartment] = useState('')
  const [academicTitle, setAcademicTitle] = useState('')

  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null); setInfo(null); setBusy(true)
    try {
      if (mode === 'login') {
        const { error } = await signIn(email.trim(), pw)
        if (error) setMsg(error)
      } else {
        // Rol + profil bilgilerini Supabase user_metadata'ya yaz (abonelik e-postaya bağlanır).
        const meta: Record<string, unknown> = {
          account_type: accountType,
          full_name: fullName.trim(),
        }
        if (accountType === 'veterinarian') {
          meta.clinic_name = clinicName.trim()
          meta.clinic_city = city.trim()
          meta.phone = phone.trim()
          if (vetLicense.trim()) meta.vet_license = vetLicense.trim()
        } else if (accountType === 'researcher') {
          meta.institution = institution.trim()
          meta.department = department.trim()
          if (academicTitle.trim()) meta.academic_title = academicTitle.trim()
        }
        const { error, needConfirm } = await signUp(email.trim(), pw, meta)
        if (error) setMsg(error)
        // E-posta doğrulaması açıksa kayıt oturum AÇMAZ. Bekleyen iş (indirme) pendingRef'te
        // durduğu için kullanıcı doğrulayıp AYNI modalda giriş yapınca indirme kendiliğinden
        // başlar — bunu ona söyle, yoksa "kayıt oldum ama inmedi" sanır.
        else if (needConfirm)
          setInfo(
            reason === 'download'
              ? 'Doğrulama e-postası gönderildi. Onaylayıp buradan giriş yapın — indirme kaldığı yerden devam eder.'
              : 'Doğrulama e-postası gönderildi. Onayladıktan sonra giriş yapın.',
          )
      }
    } finally {
      setBusy(false)
    }
  }

  async function handleReset() {
    if (!email.trim()) { setMsg('Önce e-posta adresinizi girin.'); return }
    setMsg(null); setInfo(null); setBusy(true)
    try {
      const { error } = await resetPassword(email.trim())
      if (error) setMsg(error)
      else setInfo('Şifre sıfırlama bağlantısı e-postanıza gönderildi. E-postanızı kontrol edin.')
    } finally {
      setBusy(false)
    }
  }

  /** Formda veri varsa kazara kapanmayı önle (uzun kayıt formu tek tıkla siliniyordu). */
  const requestClose = useCallback(() => {
    const dirty = [email, pw, fullName, clinicName, city, phone, vetLicense, institution, department, academicTitle]
      .some((v) => (v ?? '').trim().length > 0)
    if (dirty && !window.confirm('Girdiğiniz bilgiler kaybolacak. Kapatılsın mı?')) return
    onClose()
  }, [email, pw, fullName, clinicName, city, phone, vetLicense, institution, department, academicTitle, onClose])

  // ⚠️ DENETİM 2026-08-06 (MOBİLDE HER HARFTE KLAVYE KAPANIYORDU — sahip bildirimi):
  // Aşağıdaki efektin bağımlılığı `[requestClose]` idi. `requestClose` ise "form kirli mi"
  // bakabilmek için TÜM alanları (email, pw, fullName…) bağımlılık alır → HER TUŞ VURUŞUNDA
  // yeni kimlik → efekt yeniden kurulur → temizlikte `prevFocus.focus()`, gövdede
  // `node.focus()` çalışır ve odak input'tan diyalog kutusuna kayar. Masaüstünde "imleç
  // kaçıyor", mobilde ise klavye tamamen KAPANIYORDU (her harf için bir kez).
  // ÇÖZÜM: efekt bir KEZ kurulsun; kapatma çağrısı ref üzerinden HER ZAMAN güncel
  // `requestClose`'a gitsin (Esc yine dolu formda onay sorar — davranış aynı).
  const requestCloseRef = useRef(requestClose)
  useEffect(() => { requestCloseRef.current = requestClose }, [requestClose])

  // Esc ile kapat + odağı diyaloğa al + ODAK HAPSİ (Tab arkadaki sayfaya kaçmasın).
  useEffect(() => {
    const node = dialogRef.current
    const prevFocus = document.activeElement as HTMLElement | null
    node?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); requestCloseRef.current(); return }
      if (e.key !== 'Tab' || !node) return
      const items = node.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (items.length === 0) return
      const first = items[0], last = items[items.length - 1]
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prevFocus?.focus?.()
    }
    // BOŞ bağımlılık KASITLI: efekt yalnız açılış/kapanışta çalışmalı. Buraya değişen bir
    // değer eklenirse (özellikle form state'ine bağlı bir fonksiyon) odak her tuşta sıfırlanır
    // ve mobil klavye kapanır — yukarıdaki denetim notuna bakın.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isSignup = mode === 'signup'
  const isVet = accountType === 'veterinarian'
  const isResearch = accountType === 'researcher'

  return (
    // a11y: modal'da role/aria yoktu, Esc kapatmıyordu ve odak hapsi olmadığı için sekme tuşu
    // arkadaki sayfada geziniyordu (ekran okuyucu kullanıcısı formda olduğunu anlamıyordu).
    // Ayrıca dışa tıklama, uzun kayıt formunu UYARISIZ siliyordu → yalnız form boşken kapat.
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) requestClose() }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
        tabIndex={-1}
        className="card flex max-h-[90vh] w-full max-w-md flex-col p-7"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 id="auth-modal-title" className="text-lg font-bold">{isSignup ? 'Hesap oluştur' : 'Giriş yap'}</h2>
            {/* Alt başlık akışa göre: indirme kapısında "aboneliğiniz tanımlanır" demek yanıltıcıydı
                (indirme ücretsiz, kart istenmiyor). */}
            <p className="mt-1 text-sm text-muted">
              {reason === 'download'
                ? 'İndirme için ücretsiz hesap yeterli — kart bilgisi istenmez. Giriş yapınca indirme kendiliğinden başlar.'
                : 'Aboneliğiniz bu hesaba tanımlanır (mobil ve masaüstü ile aynı).'}
            </p>
          </div>
          <button onClick={requestClose} className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-muted hover:text-fg" aria-label="Kapat">
            <Close className="h-5 w-5" />
          </button>
        </div>

        {!ready && (
          <p className="mt-5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-600 dark:text-amber-400">
            Giriş yapılandırması eksik (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY). Yönetici env değişkenlerini eklemeli.
          </p>
        )}

        <form onSubmit={submit} className="mt-5 flex-1 space-y-3 overflow-y-auto pr-0.5">
          {/* Kayıt: hesap tipi seçimi → profile göre form alanları */}
          {isSignup && (
            <fieldset>
              <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Hesap türü</legend>
              <div className="grid gap-2">
                {ACCOUNT_TYPES.map((t) => {
                  const active = accountType === t.id
                  return (
                    <button
                      type="button"
                      key={t.id}
                      onClick={() => setAccountType(t.id)}
                      aria-pressed={active}
                      className={`flex items-center gap-3 rounded-lg border px-3.5 py-2.5 text-left transition ${
                        active
                          ? 'border-primary/60 bg-primary/10 ring-1 ring-primary/40'
                          : 'border-border bg-bg-soft hover:border-primary/40'
                      }`}
                    >
                      <span className="text-xl leading-none">{t.icon}</span>
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold">{t.title}</span>
                        <span className="block text-xs text-muted">{t.sub}</span>
                      </span>
                      <span className={`ml-auto grid h-4 w-4 shrink-0 place-items-center rounded-full border ${active ? 'border-primary' : 'border-border'}`}>
                        {active && <span className="h-2 w-2 rounded-full bg-primary" />}
                      </span>
                    </button>
                  )
                })}
              </div>
            </fieldset>
          )}

          {isSignup && (
            <input
              type="text" required value={fullName} onChange={(e) => setFullName(e.target.value)}
              placeholder="Ad Soyad" autoComplete="name" className={FIELD}
            />
          )}

          <input
            type="email" required autoFocus={!isSignup} value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder={isResearch ? 'E-posta (kurumsal olması gerekmez)' : 'E-posta'} autoComplete="email" className={FIELD}
          />
          <input
            type="password" required minLength={6} value={pw} onChange={(e) => setPw(e.target.value)}
            placeholder="Parola (en az 6 karakter)" autoComplete={isSignup ? 'new-password' : 'current-password'} className={FIELD}
          />

          {!isSignup && (
            <div className="-mt-1 text-right">
              <button type="button" onClick={handleReset} disabled={busy} className="text-xs text-muted hover:text-primary disabled:opacity-60">
                Şifremi unuttum
              </button>
            </div>
          )}

          {/* Veteriner / klinik alanları */}
          {isSignup && isVet && (
            <div className="space-y-3 rounded-lg border border-border/70 bg-bg-soft/40 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">Klinik bilgileri</p>
              <input type="text" required value={clinicName} onChange={(e) => setClinicName(e.target.value)} placeholder="Klinik / hastane adı" autoComplete="organization" className={FIELD} />
              <div className="grid grid-cols-2 gap-3">
                <input type="text" required value={city} onChange={(e) => setCity(e.target.value)} placeholder="Şehir" autoComplete="address-level2" className={FIELD} />
                <input type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Telefon" autoComplete="tel" className={FIELD} />
              </div>
              <input type="text" value={vetLicense} onChange={(e) => setVetLicense(e.target.value)} placeholder="Veteriner oda / diploma no (opsiyonel)" className={FIELD} />
            </div>
          )}

          {/* Araştırmacı / kurum alanları */}
          {isSignup && isResearch && (
            <div className="space-y-3 rounded-lg border border-border/70 bg-bg-soft/40 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">Kurum bilgileri</p>
              <input type="text" required value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="Üniversite / kurum / enstitü" autoComplete="organization" className={FIELD} />
              <input type="text" required value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Bölüm / anabilim dalı" className={FIELD} />
              <input type="text" value={academicTitle} onChange={(e) => setAcademicTitle(e.target.value)} placeholder="Akademik ünvan (opsiyonel)" className={FIELD} />
            </div>
          )}

          {msg && <p className="text-sm text-red-500">{msg}</p>}
          {info && <p className="text-sm text-primary">{info}</p>}

          <button type="submit" disabled={busy || !ready} className="btn-primary w-full disabled:opacity-60">
            {busy ? 'Lütfen bekleyin…' : isSignup ? 'Kayıt ol' : 'Giriş yap'}
          </button>

          {isSignup && (
            <p className="text-center text-xs leading-relaxed text-muted">
              Kayıt olarak{' '}
              <a href="/kvkk" target="_blank" rel="noreferrer" className="text-primary hover:underline">KVKK Aydınlatma Metni</a>,{' '}
              <a href="/kullanim-sartlari" target="_blank" rel="noreferrer" className="text-primary hover:underline">Kullanım Şartları</a> ve{' '}
              <a href="/gizlilik" target="_blank" rel="noreferrer" className="text-primary hover:underline">Gizlilik Politikası</a>'nı kabul edersiniz.
            </p>
          )}
        </form>

        <div className="mt-4 shrink-0 text-center text-sm text-muted">
          {mode === 'login' ? (
            <button onClick={() => { setMode('signup'); setMsg(null); setInfo(null) }} className="hover:text-fg">
              Hesabınız yok mu? <span className="font-medium text-primary">Kayıt olun</span>
            </button>
          ) : (
            <button onClick={() => { setMode('login'); setMsg(null); setInfo(null) }} className="hover:text-fg">
              Zaten hesabınız var mı? <span className="font-medium text-primary">Giriş yapın</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
