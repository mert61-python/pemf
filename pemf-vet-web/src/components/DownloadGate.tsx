// Author: mertaygn, cglrgrkn
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAuthModal } from '../context/AuthModal'
import { requestDownload, type DownloadTarget, type GateDecision } from '../lib/download'

/** Oturum okuması bu kadar sürerse artık bekleme (ms). Bkz. useDownloadGate içindeki gerekçe. */
const OTURUM_BEKLEME_MS = 8000

/**
 * İndirme kapısı hook'u — İKİ indirme yüzeyi (Home hero'daki DownloadButtons ve
 * /download sayfasındaki PlatformCard) AYNI mantığı kullansın diye burada.
 * İki yerde ayrı koşul yazılırsa biri unutulup açıkta kalır (Linux'un AppImage/.rpm
 * alt bağlantıları tam olarak böyle bir arka kapı riskiydi).
 *
 * NOT: kapı bir erişim kontrolü değil, kayıt adımıdır — gerekçesi lib/download.ts başında.
 */
export function useDownloadGate() {
  const { session, loading } = useAuth()
  const { requireAuth } = useAuthModal()

  /* DENETIM 2026-08-06 (kilitlenme): `loading` iken indirme düğmeleri devre dışı. Ama
     AuthContext `loading`'i YALNIZCA `getSession()` sonuçlanınca kapatıyor ve supabase-js
     bu çağrıyı `navigator.locks` üzerinden SÜRESİZ bekleyebiliyor (başka bir sekme kilidi
     tutup donarsa promise hiç sonuçlanmaz). O durumda tüm indirme yüzeyi kalıcı olarak
     tıklanamaz kalırdı — üstelik hiçbir açıklama olmadan; eskiden düz `<a href>` olduğu için
     böyle bir ölü durum YOKTU, yani kapı bunu yeni getirdi.
     Bu yüzden bekleme sınırlı: süre dolunca oturumu "yok" say → düğme çalışır ve kullanıcı
     giriş modalını görür. Oturum sonradan gelirse AuthModal bekleyen indirmeyi zaten
     kendiliğinden çalıştırıyor, yani yol kendini onarır. */
  const [beklemeAsildi, setBeklemeAsildi] = useState(false)
  useEffect(() => {
    if (!loading) {
      setBeklemeAsildi(false)
      return
    }
    const id = setTimeout(() => setBeklemeAsildi(true), OTURUM_BEKLEME_MS)
    return () => clearTimeout(id)
  }, [loading])
  const okunuyor = loading && !beklemeAsildi

  const download = useCallback(
    (t: DownloadTarget): GateDecision =>
      requestDownload(t, { loading: okunuyor, authed: Boolean(session) }, { requireAuth }),
    [okunuyor, session, requireAuth],
  )

  return {
    /** Oturum henüz okunuyor → butonlar devre dışı (giriş yapmış kullanıcıya modal yanıp sönmesin). */
    loading: okunuyor,
    /** Giriş yok → düğme metni "Giriş yap ve indir" olur.
     *  `loading` DEĞİL `okunuyor`: bekleme aşıldığında etiket ile tıklama davranışı ayrışmasın
     *  (düğme "Windows için indir" derken modal açması kullanıcıyı şaşırtırdı). */
    gated: !okunuyor && !session,
    download,
  }
}

/** Kapının NEDENİNİ açıklayan tek satır. Yanıltmamak için "korumalı indirme" demiyoruz;
 *  yapılan şey hesap açtırmak. Giriş yapılmışsa hiç gösterilmez.
 *
 *  DENETIM 2026-08-06 (dayanaksız vaat): metin "sürüm bildirimleri ... hesabınıza tanımlanır"
 *  diyordu; sitede böyle bir bildirim listesi/telemetri YOK (Supabase yalnız doğrulama ve
 *  şifre-sıfırlama e-postası gönderiyor, `downloads` tablosu hiç yazılmadı). Vaadi gerçekte
 *  olan şeye indir: aynı hesap uygulamada ve destekte geçerli. (Aynı gerekçeyle Download.tsx'te
 *  "SHA-256 doğrulanır" ifadesi de daha önce düzeltilmişti.) */
export function DownloadGateNote() {
  const { gated } = useDownloadGate()
  if (!gated) return null
  return (
    <p className="mt-4 text-sm text-muted">
      İndirmek için ücretsiz hesap oluşturun veya giriş yapın — aynı hesapla uygulamaya ve
      destek taleplerinize giriş yaparsınız. Kart bilgisi istenmez.
    </p>
  )
}
