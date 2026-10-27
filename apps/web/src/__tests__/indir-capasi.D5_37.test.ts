// Author: mertaygn, cglrgrkn
/**
 * D5.37 (B-10.217) — /download birincil indirme düğmesi `data-kapi="indir"` çıpasını TAŞIR.
 *
 * Responsive kapısının (`scripts/responsive_kapisi.py`) /download kritiği artık YALNIZ `main [data-kapi='indir']` seçicisine
 * pinli (eski `main button` geri düşüşü, Windows indirme düğmesi gizlense de başka bir düğmeyle karşılanıyordu). Çıpa kaynakta
 * kaybolursa CI'daki site işi "kritik YOK" der; bu test aynı şeyi tarayıcısız, commit anında söyler.
 *
 * ⚠️ DOM YOK (bu depoda jsdom yok) → ölçülen KAYNAK (yorumlar soyulur). Çıpa yalnız `PlatformCard`'ın HAZIR (indirme yapan) düğmesinde
 * ve yalnız BİRİNCİL kartta açılır; kart listesinde birincil kart Windows. Gerçek tarayıcıdaki gizleme mutantı → ORKESTRATÖR.
 */
import { describe, expect, it } from 'vitest'

import { kaynakSoy } from './_soyucu'

import DOWNLOAD_SRC from '../pages/Download.tsx?raw'

const kod = kaynakSoy(DOWNLOAD_SRC)

describe('D5.37 — indirme çıpası', () => {
  it('çıpa tek yerde ve indirme yapan düğmede, yalnız birincil kartta', () => {
    const cipalar = kod.match(/data-kapi=/g) ?? []
    expect(cipalar.length).toBe(1)
    const dugme = kod.match(/<button\b[^>]*?onClick=\{\(\) => download\(target\)\}[^>]*?>/s)
    expect(dugme, 'indirme yapan <button> bulunamadı').not.toBeNull()
    expect(dugme![0]).toContain("data-kapi={primary ? 'indir' : undefined}")
  })

  it('birincil kart Windows kartı (tek primary)', () => {
    const primaryKartlar = kod.match(/<PlatformCard\b[^>]*\bprimary\b[^>]*\/>/g) ?? []
    expect(primaryKartlar.length).toBe(1)
    expect(primaryKartlar[0]).toContain('target="windows"')
  })
})
