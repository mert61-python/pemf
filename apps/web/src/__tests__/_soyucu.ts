// Author: mertaygn, cglrgrkn
/**
 * TS/TSX KAYNAK YORUM-SOYUCU — STRING-BİLİNÇLİ (metin denetimi 2. parti, 2026-08-20).
 *
 * Metin kapıları YALNIZ kullanıcıya görünen dizeleri ölçmelidir. Naif soyucu iki yönden yanılır:
 *   1. Satır SONU yorumlarını kaçırır (`windowsTag: '…', // 1.9.32 = … client … Ev Sahibi …`)
 *      → geliştirici notu ekran metni sanılır, kapı yanlış-KIRMIZI yanar (ilk koşuda ölçüldü).
 *   2. String İÇİNDEKİ `//` dizisini yorum başlangıcı sanar (`'https://github.com/…'`) →
 *      satırın kalanı silinir ve GERÇEK ekran metni kapının gözünden kaçar. (Bu deponun firmware
 *      tarafında ampirik kanıtlanmış tuzağın aynısı — orada canlı bir komut dalı böyle gizlenmişti.)
 *
 * Bu soyucu string/şablon/karakter değişmezlerini AYNEN korur, yalnız gerçek yorumları siler.
 */

export function kaynakSoy(src: string): string {
  const out: string[] = []
  const KOD = 0, TEK = 1, CIFT = 2, SABLON = 3, SATIR = 4, BLOK = 5
  let durum = KOD
  for (let i = 0; i < src.length; i++) {
    const c = src[i]
    const nx = src[i + 1] ?? ''
    if (durum === KOD) {
      if (c === '/' && nx === '/') { durum = SATIR; i++; out.push('  '); continue }
      if (c === '/' && nx === '*') { durum = BLOK; i++; out.push('  '); continue }
      if (c === "'") durum = TEK
      else if (c === '"') durum = CIFT
      else if (c === '`') durum = SABLON
      out.push(c)
    } else if (durum === TEK || durum === CIFT || durum === SABLON) {
      if (c === '\\') { out.push(c, nx); i++; continue }
      const kapanis = durum === TEK ? "'" : durum === CIFT ? '"' : '`'
      if (c === kapanis) durum = KOD
      out.push(c)
    } else if (durum === SATIR) {
      if (c === '\n') { durum = KOD; out.push('\n') } else out.push(' ')
    } else {
      // BLOK
      if (c === '*' && nx === '/') { durum = KOD; i++; out.push('  '); continue }
      out.push(c === '\n' ? '\n' : ' ')
    }
  }
  return out.join('')
}
