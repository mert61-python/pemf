// Author: mertaygn, cglrgrkn
import { CLIENT } from '../config'

/* ============================================================
   İndirme kapısı — TEK KAYNAK (2026-08-06)

   DÜRÜSTLÜK NOTU — bu bir ERİŞİM KONTROLÜ DEĞİLDİR:
   İndirme adresleri GitHub Release'te PUBLIC duruyor (kimlik doğrulamasız 302 ile
   CDN'e yönleniyor) ve `config.ts` üzerinden JS paketinde düz metin olarak zaten yer
   alıyor. Yani buradaki kapı dosyayı KORUMAZ; yalnızca "indirmeden önce hesap oluştur"
   adımıdır (kayıt/edinim + sürüm bildirimi). Gerçek koruma ancak kurulum dosyası özel
   bir kovaya (R2/S3 presigned) taşınırsa olur — ama aynı repo launcher'ın OTA
   self-update'ini beslediği için OTA varlıkları public kalmak ZORUNDA.
   Bu yüzden kodda da kullanıcıya da "korumalı indirme" DEME.
   ============================================================ */

/** İndirilebilir hedefler. Linux'un alt paketleri (AppImage/.rpm) AYRI hedeftir —
 *  Download.tsx'te ayrı bağlantı olarak duruyorlar; kapı dışında kalırlarsa arka kapı olurdu. */
export type DownloadTarget =
  | 'windows'
  | 'macos'
  | 'linux'
  | 'linux-appimage'
  | 'linux-rpm'
  | 'android'

export type ResolvedDownload = { url: string; label: string; ready: boolean }

/** Hedef → (url, etiket, hazır mı). URL üretimi config.ts'te kalır; burası yalnız çözümler. */
export function resolveDownload(t: DownloadTarget): ResolvedDownload {
  const d = CLIENT.downloads
  switch (t) {
    case 'windows':
      return { url: d.windows.url, label: d.windows.label, ready: d.windows.ready }
    case 'macos':
      return { url: d.macos.url, label: d.macos.label, ready: d.macos.ready }
    case 'linux':
      return { url: d.linux.url, label: d.linux.label, ready: d.linux.ready }
    case 'linux-appimage':
      // Alt paketlerin KENDİ hazır bayrağı var (.deb'den bağımsız yayınlanabiliyorlar).
      return { url: d.linux.appImageUrl, label: '.AppImage (universal)', ready: d.linux.appImageReady }
    case 'linux-rpm':
      return { url: d.linux.rpmUrl, label: '.rpm (Fedora / RHEL)', ready: d.linux.rpmReady }
    case 'android':
      return { url: d.android.url, label: d.android.label, ready: d.android.ready }
  }
}

/** Kapının okuduğu oturum durumu. `loading` AYRI tutulur: AuthContext ilk getSession'ı
 *  bitirene kadar `authed` false görünür — bu arada tıklamayı "giriş yok" sayarsak giriş
 *  yapmış kullanıcıya gereksiz modal açılır (Odeme.tsx da bu yüzden `ready && !session` bakar). */
export type GateAuth = { loading: boolean; authed: boolean }

/** 'wait' = oturum henüz okunuyor (buton devre dışı), 'unavailable' = platform "Yakında",
 *  'gate' = giriş/kayıt modalı açılacak, 'download' = indirme hemen başlar. */
export type GateDecision = 'wait' | 'unavailable' | 'gate' | 'download'

export function decideDownload(t: DownloadTarget, auth: GateAuth): GateDecision {
  if (!resolveDownload(t).ready) return 'unavailable'
  if (auth.loading) return 'wait'
  return auth.authed ? 'download' : 'gate'
}

/** Adrese git. Ayrı fonksiyon çünkü: (1) testte enjekte edilebilsin, (2) sunucu tarafı
 *  render/SSR'da `window` yokken çökmesin. Gizli `<a download>` KULLANMA — indirme
 *  çapraz-kaynak (github/CDN) olduğu için `download` özniteliği tarayıcıda yok sayılır;
 *  Content-Disposition zaten GitHub tarafında ayarlı. */
export function navigateTo(url: string): void {
  if (typeof window === 'undefined') return
  window.location.assign(url)
}

export type DownloadDeps = {
  /** AuthModal.requireAuth — giriş başarılı olur olmaz verilen geri çağrıyı çalıştırır. */
  requireAuth: (onAuthed: () => void, reason?: 'download') => void
  /** Test/SSR için enjekte edilebilir gezinme. */
  go?: (url: string) => void
}

/**
 * Tek indirme isteği. Giriş yoksa modalı açar ve indirmeyi BEKLEYEN İŞ olarak bırakır;
 * AuthModal oturum gelir gelmez onu çalıştırır → kullanıcı düğmeye İKİNCİ KEZ basmaz.
 * (Kayıt e-posta doğrulaması istiyorsa modal açık kalır; kullanıcı doğrulayıp aynı modalda
 *  giriş yapınca bekleyen indirme yine kendiliğinden başlar.)
 */
export function requestDownload(t: DownloadTarget, auth: GateAuth, deps: DownloadDeps): GateDecision {
  const { url } = resolveDownload(t)
  const go = deps.go ?? navigateTo
  const decision = decideDownload(t, auth)
  if (decision === 'download') go(url)
  else if (decision === 'gate') deps.requireAuth(() => go(url), 'download')
  return decision
}
