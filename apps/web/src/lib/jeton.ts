// Author: mertaygn, cglrgrkn
/* JETON BAKİYESİ — istemci tarafı okuma (7. parti, 2026-08-20).
   Bakiye SUNUCU-OTORİTERDİR; burada yalnız OKUNUR ve gösterilir. Tüketim istemciden
   yapılmaz — cihaz tarafı (servers/jeton.py) `api/tokens.ts` üzerinden ister.

   ⚠️ Hata durumunda EKRANI BOZMA: bakiye okunamazsa `null` döner ve arayüz o bölümü hiç
   göstermez (yanlış sayı göstermektense hiç göstermemek — DownloadStats ile aynı ilke). */
import { supabase } from './supabase'

export type JetonBakiyesi = {
  kalan: number
  aylikHak: number
  satinAlinan: number
  donemSonu: string | null
}

export async function jetonBakiyesiniOku(): Promise<JetonBakiyesi | null> {
  try {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (!token) return null

    // Yarı-açık bağlantıda menü sonsuza kadar "…" göstermesin.
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), 6000)
    const r = await fetch('/api/tokens', {
      headers: { Authorization: `Bearer ${token}` },
      signal: ctrl.signal,
    })
    clearTimeout(t)
    if (!r.ok) return null
    const j = (await r.json()) as {
      kalan?: number; aylik_hak?: number; satin_alinan?: number; donem_sonu?: string | null
    }
    return {
      kalan: Number(j.kalan ?? 0),
      aylikHak: Number(j.aylik_hak ?? 0),
      satinAlinan: Number(j.satin_alinan ?? 0),
      donemSonu: j.donem_sonu ?? null,
    }
  } catch {
    return null
  }
}
