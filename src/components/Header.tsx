import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { BRAND, NAV } from '../config'
import { Logo, Download, Menu, Close } from './Icons'

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

        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'text-fg' : 'text-muted hover:text-fg'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden md:block">
          <Link to="/download" className="btn-primary text-sm">
            <Download className="h-4 w-4" />
            İstemciyi İndir
          </Link>
        </div>

        <button
          className="grid h-10 w-10 place-items-center rounded-md text-muted hover:text-fg md:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Menü"
        >
          {open ? <Close className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {open && (
        <div className="border-t border-border/70 bg-bg-soft md:hidden">
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
            <Link to="/download" onClick={() => setOpen(false)} className="btn-primary mt-2 text-sm">
              <Download className="h-4 w-4" />
              İstemciyi İndir
            </Link>
          </nav>
        </div>
      )}
    </header>
  )
}
