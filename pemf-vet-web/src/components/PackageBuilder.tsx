// Author: mertaygn, cglrgrkn
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MODULES, CLIENT_BASE_MB, FREE_MODE } from '../config'
import { Check } from './Icons'

const tl = (n: number) => `₺${n.toLocaleString('tr-TR')}`

/** Kullanım profili tahmin aracı. Gerçek seçim CLIENT İÇİNDE yapılır; burada
 *  kullanıcı seçtikçe tahmini indirme boyutu + varsa eklenti ücretini gösterir.
 *  Ev Sahibi & Veteriner seviyeye dahil; Araştırma ücretli eklentidir. */
export default function PackageBuilder() {
  const [sel, setSel] = useState<Set<string>>(new Set(['home', 'vet']))

  const toggle = (id: string) =>
    setSel((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })

  const chosen = MODULES.filter((m) => sel.has(m.id))
  const gb = chosen.reduce((s, m) => s + m.sizeGB, 0) + CLIENT_BASE_MB / 1024
  const addon = chosen.reduce((s, m) => s + m.addonMonthly, 0)

  return (
    <div>
      <div className="grid gap-5 md:grid-cols-3">
        {MODULES.map((m) => {
          const on = sel.has(m.id)
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => toggle(m.id)}
              aria-pressed={on}
              className={`card relative p-6 text-left transition-all ${
                on ? 'ring-2 ring-primary/60 glow-ring' : 'hover:border-border-strong'
              }`}
            >
              {m.recommended && (
                <span className="absolute right-4 top-4 rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-semibold text-primary">
                  Önerilen
                </span>
              )}
              <div className="flex items-center gap-3">
                <span
                  className={`grid h-6 w-6 place-items-center rounded-md border transition-colors ${
                    on ? 'border-primary bg-primary text-primary-fg' : 'border-border-strong text-transparent'
                  }`}
                >
                  <Check className="h-4 w-4" />
                </span>
                <span className="text-lg font-bold">{m.name}</span>
              </div>
              <p className="mt-2 text-sm text-muted">{m.tagline}</p>

              <div className="mt-4 flex items-center gap-2.5 text-sm">
                <span className="font-semibold text-fg">≈ {m.sizeGB.toFixed(1)} GB</span>
                <span className="text-muted">·</span>
                {m.included ? (
                  <span className="font-semibold text-success">Seviyeye dahil</span>
                ) : (
                  <span className="font-semibold text-primary">+{tl(m.addonMonthly)}/ay eklenti</span>
                )}
              </div>

              <ul className="mt-4 space-y-1.5 border-t border-border pt-4">
                {m.includes.map((f, i) => (
                  <li key={i} className="flex gap-2 text-xs text-muted">
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/70" />
                    {f}
                  </li>
                ))}
              </ul>
            </button>
          )
        })}
      </div>

      {/* Canlı özet */}
      <div className="card mt-6 flex flex-col items-center justify-between gap-4 p-6 sm:flex-row">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
          <div>
            <div className="text-xs text-muted">Seçili profil</div>
            <div className="text-lg font-bold">{chosen.length || '—'}</div>
          </div>
          <div>
            <div className="text-xs text-muted">Tahmini indirme</div>
            <div className="text-lg font-bold">≈ {gb.toFixed(1)} GB</div>
          </div>
          <div>
            <div className="text-xs text-muted">Aylık eklenti</div>
            <div className="text-lg font-bold text-primary">
              {addon === 0 ? 'Yok — dahil' : `+${tl(addon)}/ay`}
            </div>
          </div>
        </div>
        <Link to="/download" className="btn-primary shrink-0">
          Client’ı indir
        </Link>
      </div>

      <p className="mt-3 text-center text-xs text-muted">
        Seçimi <span className="font-medium text-fg/80">client içinde</span> yaparsınız — yalnız
        seçtiğiniz profillerin modelleri iner.{' '}
        {FREE_MODE
          ? 'Test aşamasında tüm profiller (Araştırma dahil) ücretsizdir.'
          : 'Ev Sahibi ve Veteriner seviyenize dahildir; Araştırma ücretli eklentidir.'}
      </p>
    </div>
  )
}
