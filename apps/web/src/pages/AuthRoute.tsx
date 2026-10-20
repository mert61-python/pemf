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
import type { ParseKeys } from 'i18next'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAuthModal, type AuthMode } from '../context/AuthModal'
import { useTranslation } from 'react-i18next'

export type AuthRouteKind = 'register' | 'login' | 'forgot'

// `baslik` / `aciklama` / `dugme` katalog ANAHTARIDIR (modül düzeyi sabit; gösterimde `t(m.baslik)` ile çevrilir).
const METIN: Record<AuthRouteKind, { baslik: ParseKeys; aciklama: ParseKeys; dugme: ParseKeys; mode: AuthMode }> = {
  register: {
    baslik: 'hesap.hesapOlustur',
    aciklama: 'hesap.rota.kayit.aciklama',
    dugme: 'hesap.rota.kayit.dugme',
    mode: 'signup',
  },
  login: {
    baslik: 'hesap.girisYap',
    aciklama: 'hesap.rota.giris.aciklama',
    dugme: 'hesap.rota.giris.dugme',
    mode: 'login',
  },
  forgot: {
    baslik: 'hesap.sifremiUnuttum',
    aciklama: 'hesap.rota.sifre.aciklama',
    dugme: 'hesap.rota.giris.dugme',
    mode: 'login',
  },
}

export default function AuthRoute({ kind }: { kind: AuthRouteKind }) {
  const { t } = useTranslation()
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
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">{t('hesap.rota.rozet')}</p>
        <h1 className="mt-3 text-3xl font-bold sm:text-4xl">{t(m.baslik)}</h1>
        <p className="mx-auto mt-3 max-w-md text-muted">{t(m.aciklama)}</p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => requireAuth(() => navigate('/', { replace: true }), 'download', m.mode)}
            className="btn-primary"
          >
            {t(m.dugme)}
          </button>
          <Link to="/" className="tap rounded-lg border border-border px-4 py-2 text-sm text-muted hover:border-primary/40 hover:text-fg">
            {t('ortak.anaSayfa')}
          </Link>
        </div>
      </div>
    </section>
  )
}
