// Author: mertaygn, cglrgrkn
/**
 * /register · /giris · /forgot — masaüstü uygulamasından gelen hesap bağlantılarının iniş sayfası.
 *
 * SAHA BİLDİRİMİ (2026-09-07): uygulamadaki "Hesap oluştur" düğmesi `https://…/register`e
 * yönlendiriyordu, sitede böyle bir sayfa YOKTU → "Sayfa bulunamadı". Aynı şekilde "Şifremi
 * unuttum" `/forgot`a gidiyordu, site ise yalnız `/sifre-sifirla`yı (e-posta linkinin döndüğü
 * sayfa) biliyordu. Sitede kayıt/giriş bir SAYFA değil MODAL; bu sayfa o modalı doğru sekmede açar.
 * Sahadaki uygulamalar (1.9.50 ve öncesi) bu yolları KULLANIYOR → yollar sitede kalıcıdır; iki depo
 * arasındaki sözleşme `tests/test_launcher_site_yol_sozlesmesi.py` ile kilitli.
 */
import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAuthModal, type AuthMode } from '../context/AuthModal'

export type AuthRouteKind = 'register' | 'login' | 'forgot'

const METIN: Record<AuthRouteKind, { baslik: string; aciklama: string; dugme: string; mode: AuthMode }> = {
  register: {
    baslik: 'Hesap oluştur',
    aciklama:
      'Ücretsiz hesap masaüstü uygulaması, telefon uygulaması ve bu site için ortaktır; kart bilgisi istenmez. ' +
      'Kayıt penceresi kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.',
    dugme: 'Kayıt penceresini aç',
    mode: 'signup',
  },
  login: {
    baslik: 'Giriş yap',
    aciklama: 'Hesabınızla giriş yapın. Pencere kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.',
    dugme: 'Giriş penceresini aç',
    mode: 'login',
  },
  forgot: {
    baslik: 'Şifremi unuttum',
    aciklama:
      'Giriş penceresinde e-postanızı yazıp "Şifremi unuttum" bağlantısına basın; size yeni şifre ' +
      'belirleme bağlantısı göndeririz. Pencere kapandıysa aşağıdaki düğmeyle yeniden açabilirsiniz.',
    dugme: 'Giriş penceresini aç',
    mode: 'login',
  },
}

export default function AuthRoute({ kind }: { kind: AuthRouteKind }) {
  const { session, ready } = useAuth()
  const { requireAuth } = useAuthModal()
  const navigate = useNavigate()
  const m = METIN[kind]

  // Açılışta modalı doğru sekmede aç; giriş biter bitmez ana sayfaya dön (uygulama zaten açık,
  // kullanıcı siteye "hesap işi" için geldi). Zaten girişliyse modal gereksiz.
  useEffect(() => {
    if (!ready) return
    if (session) {
      navigate('/', { replace: true })
      return
    }
    requireAuth(() => navigate('/', { replace: true }), 'download', m.mode)
    // Yalnız hazır olunca ve rota değişince: requireAuth/navigate kimlikleri sabit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, kind])

  return (
    <section className="mx-auto grid min-h-[60vh] max-w-2xl place-items-center px-4 py-20 text-center">
      <div>
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">Hesap</p>
        <h1 className="mt-3 text-3xl font-bold sm:text-4xl">{m.baslik}</h1>
        <p className="mx-auto mt-3 max-w-md text-muted">{m.aciklama}</p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => requireAuth(() => navigate('/', { replace: true }), 'download', m.mode)}
            className="btn-primary"
          >
            {m.dugme}
          </button>
          <Link to="/" className="tap rounded-lg border border-border px-4 py-2 text-sm text-muted hover:border-primary/40 hover:text-fg">
            Ana sayfa
          </Link>
        </div>
      </div>
    </section>
  )
}
