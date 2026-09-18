// Author: mertaygn, cglrgrkn
import { describe, expect, it } from 'vitest'
// Kaynak metni Vite'ın `?raw` içe aktarımıyla okuruz — `node:fs` KULLANMAYIN: bu proje
// tarayıcı hedefli ve `npm run build` içindeki `tsc -b` test dosyalarını da derliyor,
// node tipleri olmadığı için build TS2591 ile DÜŞER (2026-08-06'da bu şekilde patladı).
import SRC from '../AuthModal.tsx?raw'

/* ============================================================
   AuthModal — ODAK KAYBI REGRESYONU (2026-08-06, sahip bildirimi)

   ARIZA: mobilde giriş modalında her harfte klavye kapanıyordu (hem e-posta hem şifre).
   SEBEP: odak-hapsi useEffect'inin bağımlılığı `[requestClose]` idi. `requestClose` ise
   "form kirli mi?" kontrolü için TÜM alanları bağımlılık alıyor → her tuş vuruşunda yeni
   fonksiyon kimliği → efekt teardown+setup → `prevFocus.focus()` / `node.focus()` odağı
   input'tan alıyor → mobil klavye kapanıyor.

   Bu testler KAYNAK METNİ denetler (davranış testi jsdom'da odak/klavye simüle edemez:
   sanal klavye diye bir şey yok, `focus()` çağrısı da hata vermez → yanlış-yeşil olurdu).
   ============================================================ */

/** Odak-hapsi efektinin gövdesini (useEffect'ten kapanış bağımlılık dizisine) çıkarır. */
function focusTrapEffect(): string {
  const start = SRC.indexOf('// Esc ile kapat + odağı diyaloğa al')
  expect(start, 'odak-hapsi efekti bulunamadı — test güncellenmeli').toBeGreaterThan(-1)
  const end = SRC.indexOf('const isSignup', start)
  return SRC.slice(start, end)
}

describe('AuthModal odak hapsi', () => {
  it('efekt BOŞ bağımlılıkla kurulur (her tuşta yeniden kurulmaz)', () => {
    const eff = focusTrapEffect()
    expect(eff, 'efekt `}, [])` ile bitmeli — aksi halde odak her tuşta sıfırlanır').toMatch(/\}\s*,\s*\[\s*\]\s*\)/)
  })

  it('bağımlılık dizisinde requestClose YOKTUR (asıl regresyon)', () => {
    const eff = focusTrapEffect()
    const dep = eff.slice(eff.lastIndexOf('}, ['))
    expect(dep).not.toContain('requestClose')
  })

  it('bağımlılık dizisinde hiçbir form alanı YOKTUR', () => {
    const eff = focusTrapEffect()
    const dep = eff.slice(eff.lastIndexOf('}, ['))
    for (const alan of ['email', 'pw', 'fullName', 'clinicName', 'city', 'phone',
                        'vetLicense', 'institution', 'department', 'academicTitle']) {
      expect(dep, `bağımlılıkta '${alan}' var → odak her tuşta kayar`).not.toContain(alan)
    }
  })

  it('Esc yine GÜNCEL requestClose çağırır (ref üzerinden — davranış korunur)', () => {
    const eff = focusTrapEffect()
    expect(eff).toContain('requestCloseRef.current()')
  })

  it('requestCloseRef her render güncellenir (bayat kapanış çağrısı olmasın)', () => {
    expect(SRC).toMatch(/requestCloseRef\.current\s*=\s*requestClose/)
  })

  it('requestClose hâlâ kirli-form onayı yapar (kazara kapanma koruması kaybolmadı)', () => {
    expect(SRC).toContain('window.confirm')
    expect(SRC).toMatch(/const dirty = \[/)
  })
})
