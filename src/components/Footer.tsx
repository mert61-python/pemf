import { Link } from 'react-router-dom'
import { BRAND } from '../config'
import { Logo } from './Icons'

export default function Footer() {
  return (
    <footer className="border-t border-border/70">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-12 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/25">
            <Logo className="h-4.5 w-4.5" />
          </span>
          <div>
            <div className="text-sm font-bold">{BRAND.name}</div>
            <div className="text-xs text-muted">© {BRAND.year} {BRAND.company}</div>
          </div>
        </div>

        <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted">
          <Link to="/features" className="hover:text-fg">Özellikler</Link>
          <Link to="/download" className="hover:text-fg">İndir</Link>
          <Link to="/support" className="hover:text-fg">Destek</Link>
          <a href="#" className="hover:text-fg">Gizlilik</a>
          <a href="#" className="hover:text-fg">Kullanım Şartları</a>
        </nav>
      </div>
    </footer>
  )
}
