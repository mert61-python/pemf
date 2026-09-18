// Author: mertaygn, cglrgrkn
/* JETON UÇLARI — bakiye okuma + tüketim + (satış açılınca) yükleme.
   ==============================================================================================
   Sahip kararı 2026-08-20: ücretlendirme jeton tüketimine bağlı (bkz. database/supabase_jetonlar.sql).

   TASARIM KARARLARI:
   · Bakiye SUNUCU-OTORİTER: istemci (klinik uygulaması / mobil) yalnız okur ve tüketim İSTER;
     düşme işlemi Supabase RPC `jeton_tuket` içinde ATOMİK yapılır (satır kilidi) → iki cihaz
     aynı anda analiz isterse bakiye çift düşmez.
   · İDEMPOTANS ZORUNLU: `istek_id` benzersizdir. Ağ kopar da istemci yeniden denerse jeton İKİ
     KEZ düşmez (defterdeki UNIQUE ihlali yakalanır ve mevcut bakiye döner). Çevrimdışı klinikte
     biriken tüketimin uzlaştırılması da bu anahtara dayanır.
   · ⚠️ TIBBİ CİHAZ GÜVENLİĞİ: bu uç TİCARİ bir kapıdır. Cihaz tarafı (servers/jeton.py) yetersiz
     bakiyede YALNIZ yeni yapay zekâ analizini reddeder; süren seansı, acil durdurmayı, sensör
     okumayı ve cihaz kontrolünü ASLA engellemez. Uç erişilemezse cihaz FAIL-OPEN davranır
     (yerel rezerv + sonradan uzlaştırma) — internet yokluğu kliniği durdurmaz.
   ============================================================================================== */
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { env, verifyUser } from './_lib/util.js'

type Bakiye = {
  aylik_hak: number
  satin_alinan: number
  bekleyen_borc: number
  /** 'on_odemeli' | 'kullandikca' — kullandıkça-öde üyelikte bakiye yerine borç birikir. */
  odeme_modeli: string
  /** Faturalanmamış kullanım (yalnız kullandıkça-öde). */
  kullandikca_borc: number
  donem_sonu: string | null
}

async function bakiyeOku(token: string): Promise<Bakiye | null> {
  // ⚠️ RPC ÜZERİNDEN (sahip kararı 2026-08-21): eskiden doğrudan `/rest/v1/token_balances`
  // okunuyordu ve bu, `authenticated` rolüne tabloda SELECT yetkisi BIRAKILMASINI zorunlu
  // kılıyordu (Postgres'te RLS politikası tek başına yetmez). O yetki, Supabase'in yeni tabloya
  // verdiği varsayılan yetkileri kaynağında kapatmayı da engelliyordu.
  // `jeton_bakiyem()` SECURITY DEFINER'dır ve kimliği PARAMETREDEN değil `auth.uid()`ten alır →
  // başkasının bakiyesi istenemez. Kullanıcının KENDİ JWT'si gönderilir (spoof edilemez).
  const r = await fetch(`${env('SUPABASE_URL')}/rest/v1/rpc/jeton_bakiyem`, {
    method: 'POST',
    headers: {
      apikey: env('SUPABASE_ANON_KEY'),
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: '{}',
  })
  if (!r.ok) return null
  const satirlar = (await r.json()) as Bakiye[]
  return Array.isArray(satirlar) ? satirlar[0] ?? null : null
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    const token =
      (req.headers.authorization ?? '').replace(/^Bearer\s+/i, '') ||
      ((req.body ?? {}) as { token?: string }).token ||
      ''
    const user = await verifyUser(token)
    if (!user) return res.status(401).json({ error: 'auth', message: 'Önce giriş yapın.' })

    // ── BAKİYE ────────────────────────────────────────────────────────────────
    if (req.method === 'GET') {
      const b = await bakiyeOku(token)
      if (!b) {
        // Satırı olmayan kullanıcı: henüz jeton yüklenmemiş. Sıfır dönmek, istemcinin
        // "deneme hakkı" varsayılanını uygulamasına izin verir (bkz. servers/jeton.py).
        return res.status(200).json({
          kalan: 0, aylik_hak: 0, satin_alinan: 0, odeme_modeli: 'on_odemeli', kullandikca_borc: 0,
          kayit_yok: true,
        })
      }
      return res.status(200).json({
        kalan: b.aylik_hak + b.satin_alinan,
        aylik_hak: b.aylik_hak,
        satin_alinan: b.satin_alinan,
        bekleyen_borc: b.bekleyen_borc,
        // Kullandıkça-öde üyelikte gösterilecek şey bakiye DEĞİL, biriken borçtur; istemci
        // (AccountButton + cihaz) hangisini yazacağını buna bakarak seçer.
        odeme_modeli: b.odeme_modeli ?? 'on_odemeli',
        kullandikca_borc: b.kullandikca_borc ?? 0,
        donem_sonu: b.donem_sonu,
      })
    }

    // ── TÜKETİM ───────────────────────────────────────────────────────────────
    if (req.method === 'POST') {
      const { miktar, tur, detay, istek_id, cihaz_id } = (req.body ?? {}) as {
        miktar?: number; tur?: string; detay?: string; istek_id?: string; cihaz_id?: string
      }
      if (!Number.isInteger(miktar) || (miktar as number) <= 0) {
        return res.status(400).json({ error: 'miktar', message: 'Geçersiz jeton miktarı.' })
      }
      // İDEMPOTANS ANAHTARI ZORUNLU: yoksa yeniden denemede çift düşme kapısı açılırdı.
      if (!istek_id || typeof istek_id !== 'string' || istek_id.length < 8) {
        return res.status(400).json({ error: 'istek_id', message: 'Geçersiz istek kimliği.' })
      }

      const r = await fetch(`${env('SUPABASE_URL')}/rest/v1/rpc/jeton_tuket`, {
        method: 'POST',
        headers: {
          apikey: env('SUPABASE_ANON_KEY'),
          Authorization: `Bearer ${token}`, // RPC `auth.uid()` kullanır → kullanıcı JWT'si ŞART
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          p_miktar: miktar,
          p_tur: tur ?? 'analiz',
          p_detay: detay ?? null,
          p_istek_id: istek_id,
          p_cihaz_id: cihaz_id ?? null,
        }),
      })
      if (!r.ok) {
        // Sağlayıcı ayrıntısı günlüğe; kullanıcıya sade mesaj (metin kılavuzu §4).
        console.error('[jeton] RPC hatası:', r.status, await r.text().catch(() => ''))
        return res.status(502).json({ error: 'altyapi', message: 'Jeton işlemi tamamlanamadı.' })
      }
      const sonuc = (await r.json()) as {
        ok?: boolean; kalan?: number; sebep?: string; tekrar?: boolean
        /** Kullandıkça-öde: bu tüketimden sonra biriken faturalanmamış borç. */
        borc?: number; model?: string
      }
      if (!sonuc?.ok) {
        if (sonuc?.sebep === 'yetersiz') {
          return res.status(402).json({
            error: 'yetersiz_jeton',
            kalan: sonuc.kalan ?? 0,
            // ⚠️ Mesaj, tedavi tarafının etkilenmediğini AÇIKÇA söyler (hasta güvenliği algısı).
            message:
              'Jeton hakkınız bitti; yeni yapay zekâ analizi başlatılamadı. Seans, acil durdurma ve ' +
              'sensör izleme etkilenmez. Ek jeton paketiyle hemen devam edebilirsiniz.',
          })
        }
        if (sonuc?.sebep === 'bakiye_yok') {
          return res.status(402).json({ error: 'bakiye_yok', kalan: 0, message: 'Hesabınızda jeton tanımlı değil.' })
        }
        return res.status(400).json({ error: sonuc?.sebep ?? 'bilinmeyen', message: 'Jeton işlemi tamamlanamadı.' })
      }
      return res.status(200).json({
        ok: true,
        kalan: sonuc.kalan ?? 0,
        tekrar: !!sonuc.tekrar,
        // Kullandıkça-öde dalında RPC 'borc' döndürür; istemci bunu "bu ay birikmiş kullanım"
        // olarak gösterir. Ön-ödemeli dalda alan gelmez ve gönderilmez.
        ...(sonuc.model === 'kullandikca' ? { model: 'kullandikca', borc: sonuc.borc ?? 0 } : {}),
      })
    }

    return res.status(405).json({ error: 'method' })
  } catch (e) {
    console.error('[jeton] beklenmeyen hata:', e)
    return res.status(500).json({ error: 'sunucu', message: 'Beklenmeyen bir hata oluştu.' })
  }
}
