// Author: mertaygn, cglrgrkn
import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { BRAND, NAV } from '../config'
import { Logo, Download, Menu, Close } from './Icons'
import AccountButton from './AccountButton'

export default function Header() {
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/25">
            <Logo className="h-5 w-5" />
          </span>
          <span className="text-[15px] font-bold tracking-tight">{BRAND.name}</span>
        </Link>

        {/* [W adım 2 / site-1] Masaüstü navigasyonu lg (1024) kırılımına taşındı: 768-1023 px
            tablette bağlantılar + CTA aynı satıra sığmıyor, "PEMF Vet'i İndir" iki satıra
            kırılıyordu. Tablet kullanıcısı artık hamburger görüyor (dokunmatik için de uygun). */}
        <nav className="hidden items-center gap-1 lg:flex">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive ? 'text-fg' : 'text-muted hover:text-fg'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-3 lg:flex">
          <AccountButton />
          <Link to="/download" className="btn-primary text-sm whitespace-nowrap">
            <Download className="h-4 w-4" />
            PEMF Vet’i İndir
          </Link>
        </div>

        <button
          className="grid h-11 w-11 place-items-center rounded-md text-muted hover:text-fg lg:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Menü"
        >
          {open ? <Close className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {open && (
        <div className="max-h-[calc(100svh-4rem)] overflow-y-auto border-t border-border/70 bg-bg-soft lg:hidden">
          <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-5 py-4">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2.5 text-sm font-medium ${
                    isActive ? 'bg-primary/10 text-fg' : 'text-muted'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
            <div className="mt-2 px-3">
              <AccountButton onNavigate={() => setOpen(false)} />
            </div>
            <Link to="/download" onClick={() => setOpen(false)} className="btn-primary mt-2 text-sm">
              <Download className="h-4 w-4" />
              PEMF Vet’i İndir
            </Link>
          </nav>
        </div>
      )}
    </header>
  )
}
